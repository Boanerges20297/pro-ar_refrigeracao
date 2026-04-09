from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class LicenseIssueRequest(BaseModel):
    company_name: str = Field(min_length=2, max_length=120)
    instance_fingerprint: str | None = Field(default=None, max_length=64)
    license_type: Literal["perpetual", "subscription"] = "perpetual"
    status: Literal["active", "trial"] = "active"
    duration_days: int | None = Field(default=None, ge=1, le=3650)
    expires_at: datetime | None = None
    max_users: int | None = Field(default=None, ge=1, le=100000)
    max_admin_users: int | None = Field(default=None, ge=1, le=100000)
    max_secretary_users: int | None = Field(default=None, ge=1, le=100000)
    features: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_expiration(self):
        if self.license_type == "subscription" and not self.duration_days and not self.expires_at:
            raise ValueError("subscription licenses require duration_days or expires_at")
        if self.license_type == "perpetual" and self.expires_at is not None:
            raise ValueError("perpetual licenses must not define expires_at")
        return self


class LicenseVerifyRequest(BaseModel):
    license_key: str
    expected_company_name: str | None = None
    expected_instance_fingerprint: str | None = None


class LicenseRevokeRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class LicensePayload(BaseModel):
    license_id: str
    company_name: str
    instance_fingerprint: str | None = None
    license_type: Literal["perpetual", "subscription"]
    status: Literal["active", "trial", "revoked"]
    issued_at: datetime
    expires_at: datetime | None = None
    max_users: int | None = None
    max_admin_users: int | None = None
    max_secretary_users: int | None = None
    features: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LicenseIssueResponse(BaseModel):
    license_key: str
    payload: LicensePayload


class LicenseVerifyResponse(BaseModel):
    valid: bool
    reason: str | None = None
    payload: LicensePayload | None = None
    revoked: bool = False


class LicenseDetailsResponse(BaseModel):
    license_id: str
    company_name: str
    instance_fingerprint: str | None = None
    status: str
    license_type: str
    issued_at: datetime
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    revocation_reason: str | None = None
    max_users: int | None = None
    max_admin_users: int | None = None
    max_secretary_users: int | None = None
    features: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
