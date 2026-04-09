import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from license_api.config import settings
from license_api.models import IssuedLicense
from license_api.schemas import LicenseDetailsResponse, LicenseIssueRequest, LicensePayload, LicenseVerifyResponse
from license_api.security import sign_payload, token_hash, verify_token


PLAN_FEATURES = {
    'basic': [],
    'premium': ['reports', 'audit', 'maintenance', 'branding', 'email'],
}


def plan_features(plan_name: str) -> list[str]:
    return list(PLAN_FEATURES.get((plan_name or '').strip().lower(), []))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def build_payload(request: LicenseIssueRequest) -> dict:
    issued_at = _utcnow()
    expires_at = None
    if request.license_type == "subscription":
        if request.expires_at is not None:
            expires_at = _normalize_datetime(request.expires_at)
        else:
            expires_at = issued_at + timedelta(days=request.duration_days or 0)

    return {
        "license_id": f"lic_{uuid4().hex[:24]}",
        "company_name": request.company_name,
        "instance_fingerprint": request.instance_fingerprint,
        "license_type": request.license_type,
        "status": request.status,
        "issued_at": issued_at.isoformat(),
        "expires_at": expires_at.isoformat() if expires_at else None,
        "max_users": request.max_users,
        "max_admin_users": request.max_admin_users,
        "max_secretary_users": request.max_secretary_users,
        "features": request.features,
        "metadata": request.metadata,
    }


def issue_license(db: Session, request: LicenseIssueRequest):
    if request.license_type == "perpetual" and not settings.allow_perpetual_licenses:
        raise HTTPException(status_code=400, detail="perpetual_licenses_disabled")

    payload = build_payload(request)
    token = sign_payload(payload)
    token_digest = token_hash(token)

    license_row = IssuedLicense(
        license_id=payload["license_id"],
        company_name=payload["company_name"],
        instance_fingerprint=payload["instance_fingerprint"],
        status=payload["status"],
        license_type=payload["license_type"],
        issued_at=datetime.fromisoformat(payload["issued_at"]),
        expires_at=datetime.fromisoformat(payload["expires_at"]) if payload["expires_at"] else None,
        max_users=payload["max_users"],
        max_admin_users=payload["max_admin_users"],
        max_secretary_users=payload["max_secretary_users"],
        features_json=json.dumps(payload["features"]),
        metadata_json=json.dumps(payload["metadata"]),
        token_hash=token_digest,
    )
    db.add(license_row)
    db.commit()
    db.refresh(license_row)

    return {
        "license_key": token,
        "payload": LicensePayload.model_validate(payload),
    }


def verify_license(db: Session, token: str, expected_company_name: str | None = None, expected_instance_fingerprint: str | None = None) -> LicenseVerifyResponse:
    try:
        payload = verify_token(token)
    except Exception as exc:
        return LicenseVerifyResponse(valid=False, reason=f"invalid_signature:{exc}", payload=None, revoked=False)

    license_row = db.query(IssuedLicense).filter_by(license_id=payload.get("license_id")).first()
    if not license_row:
        return LicenseVerifyResponse(valid=False, reason="license_not_found", payload=None, revoked=False)

    if license_row.revoked_at is not None or license_row.status == "revoked":
        return LicenseVerifyResponse(valid=False, reason="license_revoked", payload=LicensePayload.model_validate(payload), revoked=True)

    if license_row.token_hash != token_hash(token):
        return LicenseVerifyResponse(valid=False, reason="token_mismatch", payload=LicensePayload.model_validate(payload), revoked=False)

    if expected_company_name and payload.get("company_name", "").strip().lower() != expected_company_name.strip().lower():
        return LicenseVerifyResponse(valid=False, reason="company_name_mismatch", payload=LicensePayload.model_validate(payload), revoked=False)

    token_fingerprint = (payload.get("instance_fingerprint") or "").strip() or None
    if expected_instance_fingerprint and token_fingerprint not in {None, "*", expected_instance_fingerprint}:
        return LicenseVerifyResponse(valid=False, reason="instance_fingerprint_mismatch", payload=LicensePayload.model_validate(payload), revoked=False)

    expires_at = payload.get("expires_at")
    if payload.get("license_type") == "subscription" and expires_at:
        if datetime.fromisoformat(expires_at) < _utcnow():
            return LicenseVerifyResponse(valid=False, reason="license_expired", payload=LicensePayload.model_validate(payload), revoked=False)

    return LicenseVerifyResponse(valid=True, reason=None, payload=LicensePayload.model_validate(payload), revoked=False)


def revoke_license(db: Session, license_id: str, reason: str) -> LicenseDetailsResponse:
    license_row = db.query(IssuedLicense).filter_by(license_id=license_id).first()
    if not license_row:
        raise HTTPException(status_code=404, detail="license_not_found")

    if license_row.revoked_at is None:
        license_row.revoked_at = datetime.utcnow()
        license_row.revocation_reason = reason
        license_row.status = "revoked"
        db.commit()
        db.refresh(license_row)

    return to_details_response(license_row)


def get_license_details(db: Session, license_id: str) -> LicenseDetailsResponse:
    license_row = db.query(IssuedLicense).filter_by(license_id=license_id).first()
    if not license_row:
        raise HTTPException(status_code=404, detail="license_not_found")
    return to_details_response(license_row)


def to_details_response(license_row: IssuedLicense) -> LicenseDetailsResponse:
    return LicenseDetailsResponse(
        license_id=license_row.license_id,
        company_name=license_row.company_name,
        instance_fingerprint=license_row.instance_fingerprint,
        status=license_row.status,
        license_type=license_row.license_type,
        issued_at=license_row.issued_at,
        expires_at=license_row.expires_at,
        revoked_at=license_row.revoked_at,
        revocation_reason=license_row.revocation_reason,
        max_users=license_row.max_users,
        max_admin_users=license_row.max_admin_users,
        max_secretary_users=license_row.max_secretary_users,
        features=json.loads(license_row.features_json or "[]"),
        metadata=json.loads(license_row.metadata_json or "{}"),
    )


def list_licenses(db: Session) -> list[LicenseDetailsResponse]:
    rows = db.query(IssuedLicense).order_by(IssuedLicense.created_at.desc()).all()
    return [to_details_response(row) for row in rows]
