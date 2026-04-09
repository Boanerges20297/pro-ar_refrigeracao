import base64
import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from flask import current_app
from itsdangerous import BadData, BadSignature, URLSafeSerializer

from app import db
from app.models.config import AppConfig
from app.models.license import License
from app.models.user import User
from app.utils.audit import log_action


LICENSE_ALLOWED_STATUSES = {'active', 'trial'}
PREMIUM_FEATURES = {'reports', 'audit', 'maintenance', 'branding', 'email'}


def _utcnow():
    return datetime.utcnow()


def _serializer():
    return URLSafeSerializer(
        current_app.config['LICENSE_SIGNING_SECRET'],
        salt='pronto-ar-license-key'
    )


def _b64url_decode(value):
    padding = '=' * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _parse_datetime(value):
    if not value:
        return None

    if isinstance(value, datetime):
        return value

    text = str(value).strip()
    if not text:
        return None

    if text.endswith('Z'):
        text = text[:-1] + '+00:00'

    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)

    return parsed


def _coerce_limit(value):
    if value in (None, ''):
        return None

    coerced = int(value)
    return coerced if coerced > 0 else None


def _load_public_key():
    public_key_path = current_app.config.get('LICENSE_PUBLIC_KEY_PATH')
    if not public_key_path:
        return None

    path = Path(public_key_path)
    if not path.exists():
        return None

    return serialization.load_pem_public_key(path.read_bytes())


def _decode_public_token(license_key):
    if '.' not in license_key:
        raise ValueError('invalid_token_format')

    message_b64, signature_b64 = license_key.split('.', 1)
    message = _b64url_decode(message_b64)
    signature = _b64url_decode(signature_b64)
    public_key = _load_public_key()
    if public_key is None:
        raise ValueError('public_key_not_configured')

    public_key.verify(signature, message)
    return json.loads(message.decode('utf-8'))


def get_installation_id():
    configured = current_app.config.get('LICENSE_INSTANCE_ID')
    if configured:
        return configured.strip()

    installation_path = Path(current_app.config['LICENSE_INSTALLATION_ID_PATH'])
    if installation_path.exists():
        installation_id = installation_path.read_text(encoding='utf-8').strip()
        if installation_id:
            return installation_id

    installation_id = f'inst_{uuid4().hex}'
    installation_path.parent.mkdir(parents=True, exist_ok=True)
    installation_path.write_text(installation_id, encoding='utf-8')
    return installation_id


def get_instance_fingerprint():
    return get_installation_id()


def issue_license_key(payload):
    return _serializer().dumps(payload)


def decode_license_key(license_key):
    errors = []

    if _load_public_key() is not None:
        try:
            return _decode_public_token(license_key)
        except (InvalidSignature, ValueError, json.JSONDecodeError) as exc:
            errors.append(str(exc))

    if current_app.config.get('LICENSE_ALLOW_LEGACY_TOKENS', True):
        try:
            return _serializer().loads(license_key)
        except (BadSignature, BadData, ValueError, TypeError) as exc:
            errors.append(str(exc))

    raise ValueError('; '.join(errors) or 'license_decode_failed')


def get_license_record(create=False):
    license_record = License.query.order_by(License.id.asc()).first()
    if not license_record and create:
        license_record = License(
            instance_fingerprint=get_instance_fingerprint(),
            warning_days=current_app.config['LICENSE_WARNING_DAYS'],
            grace_days=current_app.config['LICENSE_GRACE_DAYS'],
        )
        db.session.add(license_record)
        db.session.commit()

    return license_record


def get_user_counts():
    active_users = User.query.filter_by(is_active=True).all()
    counts = {
        'total': len(active_users),
        'admin': 0,
        'secretary': 0,
        'user': 0,
    }

    for user in active_users:
        if user.permission_level in counts:
            counts[user.permission_level] += 1

    return counts


def _get_app_company_name():
    app_config = AppConfig.query.first()
    return app_config.company_name.strip() if app_config and app_config.company_name else None


def _state_template():
    return {
        'valid': False,
        'status': 'inactive',
        'status_label': 'Sem licença',
        'severity': 'warning',
        'flash_category': 'warning',
        'blocking': True,
        'message': 'Nenhuma licença foi ativada. O sistema está liberado apenas para login administrativo e ativação da licença.',
        'details': [],
        'days_remaining': None,
        'within_grace_period': False,
        'company_name': None,
        'issued_at': None,
        'expires_at': None,
        'license_type': 'unknown',
        'license_type_label': 'Não definida',
        'instance_fingerprint': get_instance_fingerprint(),
        'limits': {
            'max_users': None,
            'max_admin_users': None,
            'max_secretary_users': None,
        },
        'current_counts': get_user_counts(),
        'limit_issues': [],
        'badge_classes': 'bg-amber-100 text-amber-800 border border-amber-200',
        'notice_key': 'license:inactive',
        'payload': None,
        'last_validated_at': None,
        'last_validation_error': None,
    }


def _apply_limit_issues(state):
    limit_issues = []
    limits = state['limits']
    counts = state['current_counts']

    checks = (
        ('max_users', 'total', 'Total de usuários ativos acima do contratado.'),
        ('max_admin_users', 'admin', 'Quantidade de administradores acima do contratado.'),
        ('max_secretary_users', 'secretary', 'Quantidade de secretárias acima do contratado.'),
    )

    for limit_key, count_key, message in checks:
        limit = limits.get(limit_key)
        if limit is not None and counts[count_key] > limit:
            limit_issues.append(message)

    state['limit_issues'] = limit_issues
    if limit_issues and state['status'] in {'active', 'expiring', 'expired'}:
        state['details'].extend(limit_issues)


def get_license_features(state=None):
    state = state or evaluate_license()
    payload = state.get('payload') or {}
    raw_features = payload.get('features')

    if raw_features is None:
        return set(PREMIUM_FEATURES)

    return {feature.strip().lower() for feature in raw_features if str(feature).strip()}


def has_license_feature(feature_name, state=None):
    if not feature_name:
        return True

    feature_key = feature_name.strip().lower()
    if feature_key not in PREMIUM_FEATURES:
        return True

    features = get_license_features(state)
    return feature_key in features


def evaluate_license(license_record=None):
    license_record = license_record or get_license_record(create=False)
    state = _state_template()

    if license_record:
        state['last_validated_at'] = license_record.last_validated_at
        state['last_validation_error'] = license_record.last_validation_error

    if not license_record or not license_record.license_key:
        return state

    try:
        payload = decode_license_key(license_record.license_key)
    except (BadSignature, BadData, ValueError, TypeError) as exc:
        state.update({
            'status': 'invalid',
            'status_label': 'Inválida',
            'severity': 'danger',
            'flash_category': 'danger',
            'blocking': True,
            'message': 'A licença salva não pôde ser validada. Reative uma chave válida para liberar a operação.',
            'details': [str(exc)],
            'badge_classes': 'bg-red-100 text-red-800 border border-red-200',
            'notice_key': 'license:invalid',
        })
        return state

    if not isinstance(payload, dict):
        state.update({
            'status': 'invalid',
            'status_label': 'Inválida',
            'severity': 'danger',
            'flash_category': 'danger',
            'blocking': True,
            'message': 'O formato da licença é inválido.',
            'badge_classes': 'bg-red-100 text-red-800 border border-red-200',
            'notice_key': 'license:invalid-format',
        })
        return state

    issued_at = _parse_datetime(payload.get('issued_at'))
    expires_at = _parse_datetime(payload.get('expires_at'))
    company_name = (payload.get('company_name') or '').strip() or None
    payload_status = (payload.get('status') or 'active').strip().lower()
    license_type = (payload.get('license_type') or ('perpetual' if not expires_at else 'subscription')).strip().lower()
    payload_fingerprint = (payload.get('instance_fingerprint') or '').strip() or None
    current_fingerprint = get_instance_fingerprint()
    app_company_name = _get_app_company_name()

    state['payload'] = payload
    state['company_name'] = company_name
    state['issued_at'] = issued_at
    state['expires_at'] = expires_at
    state['license_type'] = license_type
    state['license_type_label'] = 'Perpétua' if license_type == 'perpetual' else 'Assinatura'
    state['limits'] = {
        'max_users': _coerce_limit(payload.get('max_users')),
        'max_admin_users': _coerce_limit(payload.get('max_admin_users')),
        'max_secretary_users': _coerce_limit(payload.get('max_secretary_users')),
    }

    if payload_status not in LICENSE_ALLOWED_STATUSES:
        state.update({
            'status': 'invalid',
            'status_label': 'Revogada',
            'severity': 'danger',
            'flash_category': 'danger',
            'blocking': True,
            'message': 'A licença informada está revogada ou suspensa.',
            'badge_classes': 'bg-red-100 text-red-800 border border-red-200',
            'notice_key': 'license:revoked',
        })
        return state

    if license_type not in {'perpetual', 'subscription'}:
        state.update({
            'status': 'invalid',
            'status_label': 'Inválida',
            'severity': 'danger',
            'flash_category': 'danger',
            'blocking': True,
            'message': 'A licença não informa um tipo válido.',
            'badge_classes': 'bg-red-100 text-red-800 border border-red-200',
            'notice_key': 'license:invalid-type',
        })
        return state

    if license_type == 'subscription' and not expires_at:
        state.update({
            'status': 'invalid',
            'status_label': 'Inválida',
            'severity': 'danger',
            'flash_category': 'danger',
            'blocking': True,
            'message': 'A licença não informa uma data de expiração válida.',
            'badge_classes': 'bg-red-100 text-red-800 border border-red-200',
            'notice_key': 'license:missing-expiry',
        })
        return state

    if company_name and app_company_name and company_name.lower() != app_company_name.lower():
        state.update({
            'status': 'invalid',
            'status_label': 'Inválida',
            'severity': 'danger',
            'flash_category': 'danger',
            'blocking': True,
            'message': 'A licença não corresponde ao nome da empresa configurada neste sistema.',
            'badge_classes': 'bg-red-100 text-red-800 border border-red-200',
            'notice_key': 'license:company-mismatch',
        })
        return state

    if payload_fingerprint and payload_fingerprint not in {'*', current_fingerprint}:
        state.update({
            'status': 'invalid',
            'status_label': 'Inválida',
            'severity': 'danger',
            'flash_category': 'danger',
            'blocking': True,
            'message': 'A licença foi emitida para outra instalação da aplicação.',
            'badge_classes': 'bg-red-100 text-red-800 border border-red-200',
            'notice_key': 'license:fingerprint-mismatch',
        })
        return state

    state['valid'] = True

    if license_type == 'perpetual':
        state.update({
            'status': 'active',
            'status_label': 'Ativa',
            'severity': 'success',
            'flash_category': 'success',
            'blocking': False,
            'days_remaining': None,
            'message': 'Licença perpétua válida para esta instalação.',
            'badge_classes': 'bg-emerald-100 text-emerald-800 border border-emerald-200',
            'notice_key': 'license:perpetual',
        })
        _apply_limit_issues(state)
        return state

    warning_days = license_record.warning_days if license_record else current_app.config['LICENSE_WARNING_DAYS']
    grace_days = license_record.grace_days if license_record else current_app.config['LICENSE_GRACE_DAYS']
    days_remaining = (expires_at.date() - _utcnow().date()).days
    state['days_remaining'] = days_remaining

    if days_remaining < 0:
        overdue_days = abs(days_remaining)
        blocking = overdue_days > grace_days
        state.update({
            'status': 'expired',
            'status_label': 'Expirada',
            'severity': 'danger' if blocking else 'warning',
            'flash_category': 'danger' if blocking else 'warning',
            'blocking': blocking,
            'within_grace_period': not blocking,
            'badge_classes': 'bg-red-100 text-red-800 border border-red-200' if blocking else 'bg-orange-100 text-orange-800 border border-orange-200',
            'notice_key': f'license:expired:{days_remaining}',
        })
        if blocking:
            state['message'] = (
                f'A licença expirou há {overdue_days} dia(s) e o período de carência terminou. '
                'A operação está bloqueada até a renovação.'
            )
        else:
            remaining_grace = grace_days - overdue_days
            state['message'] = (
                f'A licença expirou há {overdue_days} dia(s). '
                f'O sistema ainda está no período de carência por mais {remaining_grace} dia(s).'
            )
    elif days_remaining <= warning_days:
        state.update({
            'status': 'expiring',
            'status_label': 'A vencer',
            'severity': 'warning',
            'flash_category': 'warning',
            'blocking': False,
            'message': f'A licença vence em {days_remaining} dia(s). Providencie a renovação para evitar bloqueios.',
            'badge_classes': 'bg-amber-100 text-amber-800 border border-amber-200',
            'notice_key': f'license:expiring:{days_remaining}',
        })
    else:
        state.update({
            'status': 'active',
            'status_label': 'Ativa',
            'severity': 'success',
            'flash_category': 'success',
            'blocking': False,
            'message': f'Licença válida por mais {days_remaining} dia(s).',
            'badge_classes': 'bg-emerald-100 text-emerald-800 border border-emerald-200',
            'notice_key': f'license:active:{days_remaining}',
        })

    _apply_limit_issues(state)
    return state


def sync_license_record(license_record, state, commit=True):
    payload = state.get('payload') or {}
    changed = False

    updates = {
        'status': state['status'],
        'company_name': state.get('company_name'),
        'instance_fingerprint': state.get('instance_fingerprint') or get_instance_fingerprint(),
        'issued_at': state.get('issued_at'),
        'expires_at': state.get('expires_at'),
        'last_validated_at': _utcnow(),
        'last_validation_status': state['status'],
        'last_validation_error': None if state['valid'] else state['message'],
        'max_users': state['limits'].get('max_users'),
        'max_admin_users': state['limits'].get('max_admin_users'),
        'max_secretary_users': state['limits'].get('max_secretary_users'),
        'feature_flags': json.dumps(payload.get('features') or []),
    }

    for field_name, value in updates.items():
        if getattr(license_record, field_name) != value:
            setattr(license_record, field_name, value)
            changed = True

    if changed and commit:
        db.session.commit()

    return changed


def log_license_event(action, license_record=None, details=None, status='success', explicit_user_id=None):
    resource_id = license_record.id if license_record else None
    resource_name = license_record.company_name if license_record else 'License'
    log_action(
        action=action,
        resource_type='License',
        resource_id=resource_id,
        resource_name=resource_name,
        status=status,
        details=details,
        explicit_user_id=explicit_user_id,
    )


def activate_license_key(license_key, explicit_user_id=None):
    license_record = get_license_record(create=True)
    previous_key = license_record.license_key
    license_record.license_key = license_key.strip()
    state = evaluate_license(license_record)

    if not state['valid']:
        license_record.license_key = previous_key
        license_record.status = state['status']
        license_record.last_validated_at = _utcnow()
        license_record.last_validation_status = state['status']
        license_record.last_validation_error = state['message']
        db.session.commit()
        log_license_event(
            'LICENSE_VALIDATION_ERROR',
            license_record=license_record,
            details={'message': state['message']},
            status='error',
            explicit_user_id=explicit_user_id,
        )
        return state

    license_record.activated_at = _utcnow()
    sync_license_record(license_record, state, commit=False)
    db.session.commit()

    if previous_key and previous_key != license_record.license_key:
        log_license_event(
            'LICENSE_KEY_CHANGED',
            license_record=license_record,
            details={'expires_at': state['expires_at'].isoformat() if state['expires_at'] else None},
            explicit_user_id=explicit_user_id,
        )

    log_license_event(
        'LICENSE_ACTIVATED',
        license_record=license_record,
        details={
            'company_name': state['company_name'],
            'expires_at': state['expires_at'].isoformat() if state['expires_at'] else None,
            'license_type': state.get('license_type'),
            'limits': state['limits'],
        },
        explicit_user_id=explicit_user_id,
    )

    return state


def revalidate_license(explicit_user_id=None):
    license_record = get_license_record(create=True)
    state = evaluate_license(license_record)
    sync_license_record(license_record, state)

    event_action = 'LICENSE_VALIDATED' if state['valid'] else 'LICENSE_VALIDATION_ERROR'
    event_status = 'success' if state['valid'] else 'error'
    log_license_event(
        event_action,
        license_record=license_record,
        details={
            'status': state['status'],
            'license_type': state.get('license_type'),
            'message': state['message'],
            'limit_issues': state['limit_issues'],
        },
        status=event_status,
        explicit_user_id=explicit_user_id,
    )

    return state


def check_user_limit(permission_level, existing_user=None, is_active=True):
    license_record = get_license_record(create=False)
    with db.session.no_autoflush:
        state = evaluate_license(license_record)

    if state['blocking']:
        return 'A licença atual está bloqueando novas alterações operacionais. Regularize-a antes de cadastrar usuários.'

    current_counts = state['current_counts']
    projected_counts = dict(current_counts)

    if existing_user and existing_user.is_active:
        projected_counts['total'] -= 1
        if existing_user.permission_level in projected_counts:
            projected_counts[existing_user.permission_level] -= 1

    if is_active:
        projected_counts['total'] += 1
        if permission_level in projected_counts:
            projected_counts[permission_level] += 1

    checks = (
        ('max_users', 'total', 'O plano atual atingiu o limite total de usuários ativos.'),
        ('max_admin_users', 'admin', 'O plano atual atingiu o limite de administradores.'),
        ('max_secretary_users', 'secretary', 'O plano atual atingiu o limite de secretárias.'),
    )

    for limit_key, count_key, message in checks:
        limit = state['limits'].get(limit_key)
        if limit is None:
            continue

        current_value = current_counts[count_key]
        projected_value = projected_counts[count_key]
        if projected_value > limit and projected_value > current_value:
            license_record = get_license_record(create=True)
            log_license_event(
                'LICENSE_USER_LIMIT_EXCEEDED',
                license_record=license_record,
                details={
                    'limit': limit_key,
                    'count_key': count_key,
                    'current': current_value,
                    'projected': projected_value,
                },
                status='error',
            )
            return message

    return None