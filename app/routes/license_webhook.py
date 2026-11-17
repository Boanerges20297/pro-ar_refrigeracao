"""Webhook exclusivamente BTA -> Pronto Ar; não usa sessão de usuário."""
from flask import Blueprint, jsonify, request

from app.utils.bta_license import BtaLicenseError, accept_pushed_snapshot

license_webhook_bp = Blueprint("license_webhook", __name__)


@license_webhook_bp.post("/api/internal/bta-license/events")
def receive():
    # A autenticação é a assinatura Ed25519 do snapshot, não o cookie/JWT.
    if not request.is_json:
        return jsonify({"error": "json_required"}), 415
    if request.content_length is not None and request.content_length > 16384:
        return jsonify({"error": "payload_too_large"}), 413
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("snapshot"), dict):
        return jsonify({"error": "invalid_payload"}), 400
    try:
        outcome = accept_pushed_snapshot(data["snapshot"])
    except BtaLicenseError:
        return jsonify({"error": "signature_or_decision_rejected"}), 403
    except OSError:
        return jsonify({"error": "persistence_unavailable"}), 503
    response = jsonify({"accepted": True, "result": outcome})
    response.headers["Cache-Control"] = "no-store"
    return response, 200
