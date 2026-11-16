from flask import Blueprint, render_template, request, redirect, url_for, flash, make_response, current_app, session
from app.models.user import User
from flask_jwt_extended import create_access_token, set_access_cookies, unset_jwt_cookies, jwt_required, get_jwt_identity, get_jwt
from itsdangerous import URLSafeTimedSerializer, BadSignature
from urllib.parse import urlsplit
from hmac import compare_digest, new as hmac_new
from hashlib import sha256
from flask_bcrypt import generate_password_hash
from app.utils.email import send_dynamic_email, send_password_reset_email
from app.utils.audit import log_login, log_logout
from app.utils.license import evaluate_license, get_license_record, log_license_event
from app.utils.security import (
    is_password_strong,
    PASSWORD_POLICY_MESSAGE,
    build_password_version,
    build_session_nonce,
    build_user_agent_fingerprint,
)
from app import db
from app import limiter
from datetime import datetime
import time

from app.utils.login_otp import (
    OTPStoreUnavailable, OTP_TTL_SECONDS, TRUST_SECONDS, TRUST_COOKIE_NAME,
    create_challenge, delete_challenge, challenge_matches_user, verify_challenge,
    acquire_resend_cooldown, rotate_trusted_device, issue_trusted_device,
    list_trusted_devices, revoke_trusted_device, revoke_all_trusted_devices,
)
from app.utils.audit import log_action
from app.utils.jwt_sessions import register_jwt, revoke_jwt, JWTSessionStoreUnavailable


auth_bp = Blueprint('auth', __name__)


def account_rate_limit_key():
    """Stable pseudonymous account key shared across origins and workers."""
    email = (request.form.get('email') or '').strip().casefold()
    signing_key = current_app.config['SECRET_KEY']
    if isinstance(signing_key, str):
        signing_key = signing_key.encode('utf-8')
    return 'account:' + hmac_new(signing_key, email.encode('utf-8'), sha256).hexdigest()

def public_url_for(endpoint, **values):
    """Build email links only from the configured HTTPS origin, never request Host."""
    origin = (current_app.config.get('PUBLIC_BASE_URL') or '').rstrip('/')
    parsed = urlsplit(origin)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username
            or parsed.password or parsed.port not in (None, 443)
            or parsed.path not in ('', '/') or parsed.query or parsed.fragment):
        raise ValueError('PUBLIC_BASE_URL deve conter apenas a origem HTTPS pública.')
    return origin + url_for(endpoint, **values)


def generate_reset_token(email):
    user = User.query.filter_by(email=email).first()
    if user is None:
        raise ValueError('Não é possível gerar recuperação para conta inexistente.')
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    return serializer.dumps({
        'email': user.email,
        'pwdv': build_password_version(user.password_hash),
    }, salt='password-reset-salt')


def confirm_reset_token(token, expiration=3600):
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        payload = serializer.loads(token, salt='password-reset-salt', max_age=expiration)
        if not isinstance(payload, dict) or not isinstance(payload.get('email'), str):
            return False
        user = User.query.filter_by(email=payload['email']).first()
        if not user or not isinstance(payload.get('pwdv'), str):
            return False
        if not compare_digest(payload['pwdv'], build_password_version(user.password_hash)):
            return False
        return user.email
    except (BadSignature, TypeError, ValueError):
        return False


def build_authenticated_response(user, redirect_url):
    session_nonce = None
    if current_app.config.get('SECURITY_BIND_JWT_SESSION_NONCE', False):
        session_nonce = build_session_nonce()
        session['jwt_session_nonce'] = session_nonce
        session.modified = True

    additional_claims = {
        'uid': str(user.id),
        'permission_level': user.permission_level,
        'pwdv': build_password_version(user.password_hash),
    }

    if current_app.config.get('SECURITY_BIND_JWT_SESSION_NONCE', False):
        additional_claims['session_nonce'] = session_nonce

    if current_app.config.get('SECURITY_BIND_JWT_USER_AGENT', False):
        additional_claims['ua_hash'] = build_user_agent_fingerprint(request.headers.get('User-Agent'))

    access_token = create_access_token(
        identity=str(user.id),
        additional_claims=additional_claims,
    )

    if current_app.config.get('SECURITY_JWT_SERVER_SESSIONS', False):
        register_jwt(access_token, user.id)
    resp = make_response(redirect(redirect_url))
    set_access_cookies(resp, access_token)
    return resp

def _license_allows_login(user):
    if not user.is_active:
        flash('Sua conta está inativa. Contate o administrador.', 'danger')
        log_login(user.id, success=False, details={'reason': 'inactive_account'})
        return False
    from app.utils.superadmin import is_superadmin
    state = {'blocking': False} if is_superadmin(user) else evaluate_license(get_license_record(create=False))
    if state['blocking'] and user.permission_level != 'admin':
        flash('O acesso operacional está bloqueado por licença ausente, expirada ou inválida. Contate o administrador.', 'danger')
        log_license_event(
            'LICENSE_LOGIN_BLOCKED',
            details={'status': state['status'], 'message': state['message'], 'email': user.email},
            status='error', explicit_user_id=user.id,
        )
        return False
    return True


def _finish_login(user, method):
    # A login is audited only after a JWT session has actually been issued.
    if user.must_change_password:
        flash('Por segurança, defina uma nova senha antes de acessar o sistema.', 'warning')
        return redirect(url_for('auth.reset_password', token=generate_reset_token(user.email)))
    destinations = {
        'admin': 'admin.dashboard',
        'secretary': 'secretary.dashboard',
        'client': 'client_portal.dashboard',
        'common': 'common_portal.dashboard',
    }
    endpoint = destinations.get(user.permission_level, 'tech.dashboard')
    response = build_authenticated_response(user, url_for(endpoint))
    log_login(user.id, success=True, details={'method': method})
    return response


def _otp_rate_limit_key():
    pending = session.get('otp_pending')
    if isinstance(pending, dict) and str(pending.get('uid', '')).isdigit():
        return 'otp-account:' + str(pending['uid'])
    return 'otp-ip:' + str(request.remote_addr)


def _pending_otp_user():
    pending = session.get('otp_pending')
    if not isinstance(pending, dict):
        return None, None
    try:
        uid, started = int(pending.get('uid', 0)), int(pending.get('issued', 0))
    except (TypeError, ValueError):
        session.pop('otp_pending', None)
        return None, None
    if uid <= 0 or not started or time.time() - started > OTP_TTL_SECONDS:
        session.pop('otp_pending', None)
        return None, None
    user = User.query.get(uid)
    if (not user or not user.is_active
            or pending.get('pwdv') != build_password_version(user.password_hash)
            or pending.get('role') != user.permission_level
            or not challenge_matches_user(user, pending.get('nonce'))):
        session.pop('otp_pending', None)
        return None, None
    return user, pending


def _mask_email(value):
    local, separator, domain = (value or '').partition('@')
    return local[:1] + '***@' + domain if separator else 'e-mail cadastrado'


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit('5 per minute', methods=['POST'])
@limiter.limit('15 per 15 minutes', key_func=account_rate_limit_key, methods=['POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            if not _license_allows_login(user):
                return redirect(url_for('auth.login'))

            if current_app.config.get('EMAIL_OTP_ENABLED', False):
                try:
                    rotated = rotate_trusted_device(user, request.cookies.get(TRUST_COOKIE_NAME))
                    if rotated:
                        # A trusted cookie is single-use: rotate on each login.
                        response = _finish_login(user, 'trusted_device')
                        response.set_cookie(
                            TRUST_COOKIE_NAME, rotated[0], max_age=rotated[1],
                            secure=True, httponly=True, samesite='Lax', path='/auth',
                        )
                        return response
                    previous = session.get('otp_pending')
                    if isinstance(previous, dict):
                        delete_challenge(previous.get('nonce'))
                    nonce, code = create_challenge(user)
                    success, _ = send_dynamic_email(
                        user.email, 'Código de acesso - Pronto Ar',
                        'email/login_otp.html', user=user, code=code,
                    )
                    if not success:
                        delete_challenge(nonce)
                        session.pop('otp_pending', None)
                        flash('Não foi possível enviar o código. Tente novamente ou contate o administrador.', 'danger')
                        return redirect(url_for('auth.login'))

                    session['otp_pending'] = {
                        'uid': user.id, 'nonce': nonce,
                        'issued': int(time.time()),
                        'pwdv': build_password_version(user.password_hash),
                        'role': user.permission_level,
                    }
                    acquire_resend_cooldown(user.id)
                    response = make_response(redirect(url_for('auth.verify_otp')))
                    unset_jwt_cookies(response)
                    return response
                except (OTPStoreUnavailable, JWTSessionStoreUnavailable):
                    session.pop('otp_pending', None)
                    flash('A verificação por e-mail está temporariamente indisponível. Tente novamente.', 'danger')
                    return redirect(url_for('auth.login'))
            try:
                return _finish_login(user, 'password')
            except JWTSessionStoreUnavailable:
                session.pop('jwt_session_nonce', None)
                flash('Validação da sessão indisponível. Tente novamente.', 'danger')
                return redirect(url_for('auth.login'))
        flash('Email ou senha inválidos.', 'danger')
        log_login(user.id if user else None, success=False, details={'reason': 'invalid_credentials'})
    return render_template('auth/login.html')


@auth_bp.route('/otp', methods=['GET', 'POST'])
@limiter.limit('10 per minute', methods=['POST'])
@limiter.limit('10 per 15 minutes', key_func=_otp_rate_limit_key, methods=['POST'])
def verify_otp():
    if not current_app.config.get('EMAIL_OTP_ENABLED', False):
        return redirect(url_for('auth.login'))
    try:
        user, pending = _pending_otp_user()
        if not user:
            flash('A verificação expirou. Informe sua senha novamente.', 'warning')
            return redirect(url_for('auth.login'))
        if request.method == 'POST':
            outcome = verify_challenge(user, pending['nonce'], request.form.get('otp_code'))
            if outcome == 'success':
                session.pop('otp_pending', None)
                if not _license_allows_login(user):
                    return redirect(url_for('auth.login'))
                response = _finish_login(user, 'email_otp')
                if request.form.get('remember_device') == 'on' and not user.must_change_password:
                    try:
                        raw_token = issue_trusted_device(user, request.headers.get('User-Agent'))
                        response.set_cookie(
                            TRUST_COOKIE_NAME, raw_token, max_age=TRUST_SECONDS,
                            secure=True, httponly=True, samesite='Lax', path='/auth',
                        )
                        log_action('TRUSTED_DEVICE_ADD', 'User', user.id,
                                   explicit_user_id=user.id)
                    except OTPStoreUnavailable:
                        flash('Login concluído, mas não foi possível confiar neste dispositivo.', 'warning')
                return response
            if outcome in {'locked', 'expired'}:
                session.pop('otp_pending', None)
                log_login(user.id, success=False, details={'reason': 'otp_' + outcome})
                flash('Código expirado ou tentativas excedidas. Comece novamente pelo login.', 'danger')
                return redirect(url_for('auth.login'))
            flash('Código inválido. Confira o e-mail e tente novamente.', 'danger')
            log_login(user.id, success=False, details={'reason': 'otp_invalid'})
        return render_template('auth/verify_otp.html', masked_email=_mask_email(user.email))
    except (OTPStoreUnavailable, JWTSessionStoreUnavailable):
        flash('A verificação está temporariamente indisponível. Tente novamente.', 'danger')
        return redirect(url_for('auth.login'))


@auth_bp.route('/otp/resend', methods=['POST'])
@limiter.limit('3 per 15 minutes', key_func=_otp_rate_limit_key)
@limiter.limit('5 per 15 minutes')
def resend_otp():
    if not current_app.config.get('EMAIL_OTP_ENABLED', False):
        return redirect(url_for('auth.login'))
    try:
        user, pending = _pending_otp_user()
        if not user:
            flash('Sua verificação expirou. Inicie novamente o login.', 'warning')
            return redirect(url_for('auth.login'))
        if not acquire_resend_cooldown(user.id):
            flash('Aguarde 60 segundos antes de solicitar outro código.', 'warning')
            return redirect(url_for('auth.verify_otp'))
        nonce, code = create_challenge(user)
        success, _ = send_dynamic_email(
            user.email, 'Novo código de acesso - Pronto Ar',
            'email/login_otp.html', user=user, code=code,
        )
        if not success:
            delete_challenge(nonce)
            flash('Não foi possível reenviar o código. Tente novamente.', 'danger')
            return redirect(url_for('auth.verify_otp'))
        delete_challenge(pending['nonce'])
        session['otp_pending'] = dict(pending, nonce=nonce, issued=int(time.time()))
        flash('Enviamos um novo código. O anterior foi invalidado.', 'info')
        return redirect(url_for('auth.verify_otp'))
    except OTPStoreUnavailable:
        flash('A verificação está temporariamente indisponível.', 'danger')
        return redirect(url_for('auth.login'))


@auth_bp.route('/trusted-devices', methods=['GET'])
@jwt_required()
def trusted_devices():
    user = User.query.get(get_jwt_identity())
    if not user:
        return redirect(url_for('auth.login'))
    try:
        devices = list_trusted_devices(user)
    except OTPStoreUnavailable:
        flash('Não foi possível consultar os dispositivos neste momento.', 'danger')
        devices = []
    return render_template('auth/trusted_devices.html', devices=devices)


@auth_bp.route('/trusted-devices/revoke/<device_id>', methods=['POST'])
@jwt_required()
def revoke_trusted_device_route(device_id):
    user_id = get_jwt_identity()
    try:
        if revoke_trusted_device(user_id, device_id):
            log_action('TRUSTED_DEVICE_REVOKE', 'User', int(user_id),
                       explicit_user_id=int(user_id))
            flash('Dispositivo revogado.', 'success')
        else:
            flash('Dispositivo não encontrado.', 'warning')
        response = make_response(redirect(url_for('auth.trusted_devices')))
        raw_token = request.cookies.get(TRUST_COOKIE_NAME)
        if raw_token and sha256(raw_token.encode('utf-8')).hexdigest() == device_id:
            response.delete_cookie(TRUST_COOKIE_NAME, path='/auth')
        return response
    except OTPStoreUnavailable:
        flash('Não foi possível revogar o dispositivo. Tente novamente.', 'danger')
        return redirect(url_for('auth.trusted_devices'))


@auth_bp.route('/trusted-devices/revoke-all', methods=['POST'])
@jwt_required()
def revoke_all_trusted_devices_route():
    user_id = get_jwt_identity()
    try:
        revoke_all_trusted_devices(user_id)
        log_action('TRUSTED_DEVICE_REVOKE_ALL', 'User', int(user_id),
                   explicit_user_id=int(user_id))
        flash('Todos os dispositivos foram revogados.', 'success')
        response = make_response(redirect(url_for('auth.trusted_devices')))
        response.delete_cookie(TRUST_COOKIE_NAME, path='/auth')
        return response
    except OTPStoreUnavailable:
        flash('Não foi possível revogar agora. Tente novamente.', 'danger')
        return redirect(url_for('auth.trusted_devices'))


@auth_bp.route('/logout', methods=['POST'])
@jwt_required(optional=True)
def logout():
    # Log logout action
    current_user_id = get_jwt_identity()
    if current_user_id:
        if current_app.config.get('SECURITY_JWT_SERVER_SESSIONS', False):
            try:
                revoke_jwt(get_jwt())
            except JWTSessionStoreUnavailable:
                return 'Não foi possível revogar esta sessão. Tente novamente.', 503
        log_logout(int(current_user_id))

    session.pop('jwt_session_nonce', None)
    
    resp = make_response(redirect(url_for('auth.login')))
    unset_jwt_cookies(resp)
    return resp

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit('3 per 15 minutes', methods=['POST'])
@limiter.limit('3 per hour', key_func=account_rate_limit_key, methods=['POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()
        
        # Genericamente dizemos que enviamos o e-mail por segurança
        flash('Se o e-mail estiver cadastrado, você receberá um link de recuperação em instantes.', 'info')
        
        if user:
            token = generate_reset_token(user.email)
            try:
                reset_url = public_url_for('auth.reset_password', token=token)
            except ValueError:
                current_app.logger.error('PUBLIC_BASE_URL precisa de uma origem HTTPS válida.')
                return redirect(url_for('auth.login'))
            
            # Use absolute logo URL or fallback
            logo_url = None
            if current_app.config.get('APP_CONFIG'):
                app_config = current_app.config['APP_CONFIG']
                if app_config.logo_path:
                    if app_config.logo_path.startswith('http'):
                        logo_url = app_config.logo_path
                    else:
                        # Clean-up path and make it absolute
                        clean_path = app_config.logo_path.lstrip('/')
                        if clean_path.startswith('static/'):
                            clean_path = clean_path.replace('static/', '', 1)
                        logo_url = public_url_for('static', filename=clean_path)
            
            success, message = send_password_reset_email(user, reset_url, logo_url)
            if not success:
                # Log error internally but message to user is helpful for debugging if SMTP fails
                current_app.logger.error(f"Failed to send reset email: {message}")


        
        return redirect(url_for('auth.login'))
        
    return render_template('auth/forgot_password.html')

@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
@limiter.limit('5 per 15 minutes', methods=['POST'])
def reset_password(token):
    email = confirm_reset_token(token)
    if not email:
        flash('O link de recuperação é inválido ou expirou.', 'danger')
        return redirect(url_for('auth.forgot_password'))
        
    user = User.query.filter_by(email=email).first()
    if not user:
        flash('Usuário não encontrado.', 'danger')
        return redirect(url_for('auth.login'))
        
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if password != confirm_password:
            flash('As senhas não coincidem.', 'danger')
            return render_template('auth/reset_password.html', token=token)

        if not is_password_strong(password):
            flash(PASSWORD_POLICY_MESSAGE, 'danger')
            return render_template('auth/reset_password.html', token=token)
            
        # Compare-and-swap closes concurrent replay of the same reset link.
        previous_hash = user.password_hash
        new_hash = generate_password_hash(password).decode('utf-8')
        changed = User.query.filter_by(id=user.id, password_hash=previous_hash).update(
            {'password_hash': new_hash, 'must_change_password': False},
            synchronize_session=False,
        )
        if changed != 1:
            db.session.rollback()
            flash('Este link já foi utilizado. Solicite um novo.', 'danger')
            return redirect(url_for('auth.forgot_password'))
        db.session.commit()
        
        # Log password reset
        from app.utils.audit import log_action
        log_action(
            action='PASSWORD_RESET',
            resource_type='User',
            resource_id=user.id,
            resource_name=user.email
        )
        
        flash('Sua senha foi atualizada com sucesso! Agora você pode fazer login.', 'success')

        # Recovery proves control of an email link, not a full authenticated login.
        session.pop('jwt_session_nonce', None)
        response = make_response(redirect(url_for('auth.login')))
        unset_jwt_cookies(response)
        return response
        
    return render_template('auth/reset_password.html', token=token)

