from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from license_api.database import Base


class IssuedLicense(Base):
    __tablename__ = "issued_license"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    license_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    company_name: Mapped[str] = mapped_column(String(120), index=True)
    instance_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    license_type: Mapped[str] = mapped_column(String(20), default="perpetual", index=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    max_users: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_admin_users: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_secretary_users: Mapped[int | None] = mapped_column(Integer, nullable=True)
    features_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
