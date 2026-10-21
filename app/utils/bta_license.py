"""Adaptador opt-in para licenciamento BTA S2S.

A configuração padrão da ProntoAr permanece no emissor legado. Este módulo
não emite licenças: consulta o backend BTA, verifica snapshots com chave pública
fixada localmente e mantém somente um cache assinado para indisponibilidade.
"""
import base64
import hashlib
import json
import os
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from flask import current_app


class BtaLicenseError(RuntimeError):
    pass


class BtaTransportError(BtaLicenseError):
    pass


def _time(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise BtaLicenseError("Timestamp sem fuso no snapshot BTA")
    return parsed.astimezone(timezone.utc)


def _expected_identity():
    from app.utils.license import get_instance_fingerprint
    return (
        current_app.config.get("BTA_LICENSE_CUSTOMER_KEY")
        or get_instance_fingerprint()
    ).strip()


def _pinned_public_key():
    filename = current_app.config.get("BTA_SNAPSHOT_PUBLIC_KEY_PATH")
    if not filename:
        raise BtaLicenseError("Chave pública de snapshot BTA não configurada")
    raw = Path(filename).read_bytes()
    key = serialization.load_pem_public_key(raw)
    if not isinstance(key, Ed25519PublicKey):
        raise BtaLicenseError("Chave pública BTA deve ser Ed25519")
    return key


def _verify_envelope(envelope):
    if not isinstance(envelope, dict):
        raise BtaLicenseError("Snapshot BTA ausente")
    try:
        snapshot = envelope["snapshot"]
        signature = envelope["signature"]
        if signature["algorithm"] != "ed25519":
            raise BtaLicenseError("Algoritmo BTA inesperado")
        raw = json.dumps(
            snapshot, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        signature_bytes = base64.b64decode(signature["value"], validate=True)
        _pinned_public_key().verify(signature_bytes, raw)
        if snapshot["schema_version"] != 1:
            raise BtaLicenseError("Versão do snapshot BTA não suportada")
        if snapshot["product"] != current_app.config["BTA_LICENSE_PRODUCT_CODE"]:
            raise BtaLicenseError("Snapshot BTA de outro produto")
        if snapshot["customer_key"] != _expected_identity():
            raise BtaLicenseError("Snapshot BTA de outro cliente/instalação")
        now = datetime.now(timezone.utc)
        issued_at = _time(snapshot["issued_at"])
        offline_until = _time(snapshot["offline_valid_until"])
        if not issued_at or issued_at > now + timedelta(minutes=5):
            raise BtaLicenseError("Emissão do snapshot BTA fora da janela")
        if not offline_until or offline_until <= now:
            raise BtaLicenseError("Snapshot BTA offline expirado")
        return snapshot
    except (KeyError, TypeError, ValueError, InvalidSignature, OSError) as exc:
        raise BtaLicenseError("Snapshot BTA não passou na verificação criptográfica") from exc


def _cache_path():
    return Path(current_app.config["BTA_SNAPSHOT_CACHE_PATH"])


def _load_cached():
    try:
        return _verify_envelope(json.loads(_cache_path().read_text("utf-8")))
    except (OSError, json.JSONDecodeError, BtaLicenseError):
        return None


def _store_cached(envelope):
    # Não armazena credenciais; gravação atômica evita snapshots truncados.
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".bta-",
            delete=False,
        ) as handle:
            temporary = handle.name
            json.dump(envelope, handle, ensure_ascii=False, separators=(",", ":"))
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def _resolve_remote():
    base_url = str(current_app.config.get("BTA_LICENSE_BASE_URL") or "").rstrip("/")
    client_id = current_app.config.get("BTA_LICENSE_CLIENT_ID")
    key_id = current_app.config.get("BTA_LICENSE_KEY_ID")
    private_path = current_app.config.get("BTA_LICENSE_PRIVATE_KEY_PATH")
    if not all((base_url, client_id, key_id, private_path)):
        raise BtaLicenseError("Cliente S2S BTA sem configuração completa")
    if not base_url.startswith(("https://", "http://")):
        raise BtaLicenseError("URL BTA inválida")
    # Nunca emitir a credencial S2S por HTTP em endereço público.
    if base_url.startswith("http://") and not any(
        base_url.startswith(p) for p in ("http://127.0.0.1:", "http://localhost:")
    ):
        raise BtaLicenseError("Endpoint S2S remoto requer HTTPS")

    path = "/api/v1/licenses/resolve"
    body = json.dumps(
        {"customer_key": _expected_identity()}, separators=(",", ":")
    ).encode("utf-8")
    body_hash = hashlib.sha256(body).hexdigest()
    timestamp = str(int(time.time()))
    nonce = uuid4().hex
    message = "\n".join(("POST", path, timestamp, nonce, body_hash)).encode("utf-8")

    key = serialization.load_pem_private_key(Path(private_path).read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise BtaLicenseError("Cliente S2S deve usar chave privada Ed25519")
    signature = base64.b64encode(key.sign(message)).decode("ascii")
    request = urllib.request.Request(
        base_url + path,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-BTA-Client-Id": client_id,
            "X-BTA-Key-Id": key_id,
            "X-BTA-Timestamp": timestamp,
            "X-BTA-Nonce": nonce,
            "X-BTA-Body-SHA256": body_hash,
            "X-BTA-Signature": signature,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            document = json.load(response)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise BtaTransportError("BTA inacessível ou resposta indisponível") from exc

    if not isinstance(document, dict) or document.get("contract_version") != 1:
        raise BtaLicenseError("Contrato S2S BTA inválido")
    if document.get("product") != current_app.config["BTA_LICENSE_PRODUCT_CODE"]:
        raise BtaLicenseError("Resposta S2S de outro produto")
    if not document.get("licensed"):
        # A negativa central (revogada/suspensa/ausente) prevalece sobre cache antigo.
        try:
            _cache_path().unlink(missing_ok=True)
        except OSError:
            pass
        return {"licensed": False, "reason": document.get("reason")}
    envelope = document.get("snapshot")
    snapshot = _verify_envelope(envelope)
    _store_cached(envelope)
    return {"licensed": True, "snapshot": snapshot}


def evaluate_bta_license():
    from app.utils.license import _state_template, _apply_limit_issues, PREMIUM_FEATURES

    state = _state_template()
    cached = _load_cached()
    fresh = cached and (
        datetime.now(timezone.utc) - _time(cached["issued_at"])
    ).total_seconds() < max(30, current_app.config["BTA_LICENSE_REFRESH_SECONDS"])

    try:
        if fresh:
            result = {"licensed": True, "snapshot": cached}
        else:
            result = _resolve_remote()
    except BtaTransportError:
        if cached:
            result = {"licensed": True, "snapshot": cached}
            state["last_validation_error"] = "BTA indisponível; operando com snapshot assinado"
        else:
            result = {"licensed": False, "reason": "validation_required"}
    except (BtaLicenseError, OSError, ValueError):
        result = {"licensed": False, "reason": "validation_required"}

    if not result["licensed"]:
        state.update({
            "status": "invalid",
            "status_label": "Validação necessária",
            "message": "Licença BTA não autorizada ou não pôde ser validada.",
            "notice_key": "license:bta:validation_required",
            "validation_error_code": result.get("reason"),
        })
        return state

    snapshot = result["snapshot"]
    effective_state = snapshot["state"]
    licensed = effective_state in {"active", "grace"}
    entitlements = snapshot.get("entitlements") or {}
    limits = snapshot.get("limits") or {}
    features = [
        key for key in PREMIUM_FEATURES if entitlements.get(key) == "enabled"
    ]
    paid_perpetual = snapshot.get("modality") == "paid" and not snapshot.get("expires_at")
    is_grace = effective_state == "grace"

    state.update({
        "valid": licensed,
        "status": "expired" if is_grace else ("active" if licensed else "invalid"),
        "status_label": "Carência" if is_grace else ("Ativa" if licensed else "Inválida"),
        "blocking": not licensed,
        "severity": "warning" if is_grace else ("success" if licensed else "danger"),
        "flash_category": "warning" if is_grace else ("success" if licensed else "danger"),
        "message": (
            "Licença vitalícia autorizada pelo BTA." if licensed and paid_perpetual
            else "Licença autorizada pelo BTA." if licensed
            else "Licença não autorizada pelo BTA."
        ),
        "notice_key": f"license:bta:{effective_state}",
        "license_type": "perpetual" if paid_perpetual else "subscription",
        "license_type_label": "Perpétua" if paid_perpetual else "Assinatura",
        "issued_at": _time(snapshot["issued_at"]).replace(tzinfo=None),
        "expires_at": _time(snapshot.get("expires_at")).replace(tzinfo=None) if snapshot.get("expires_at") else None,
        "last_validated_at": _time(snapshot["issued_at"]).replace(tzinfo=None),
        "within_grace_period": is_grace,
        "payload": {"features": features},
        "limits": {
            "max_users": limits.get("max_users"),
            "max_admin_users": limits.get("max_admin_users"),
            "max_secretary_users": limits.get("max_secretary_users"),
        },
        "badge_classes": (
            "bg-emerald-100 text-emerald-800 border border-emerald-200"
            if licensed and not is_grace
            else "bg-amber-100 text-amber-800 border border-amber-200"
        ),
    })
    _apply_limit_issues(state)
    return state
