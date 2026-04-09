from datetime import datetime

from app import db


class License(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    license_key = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='inactive', index=True)
    company_name = db.Column(db.String(100), nullable=True)
    instance_fingerprint = db.Column(db.String(64), nullable=True, index=True)
    issued_at = db.Column(db.DateTime, nullable=True)
    activated_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True, index=True)
    last_validated_at = db.Column(db.DateTime, nullable=True)
    last_validation_status = db.Column(db.String(20), nullable=True)
    last_validation_error = db.Column(db.Text, nullable=True)
    max_users = db.Column(db.Integer, nullable=True)
    max_admin_users = db.Column(db.Integer, nullable=True)
    max_secretary_users = db.Column(db.Integer, nullable=True)
    feature_flags = db.Column(db.Text, nullable=True)
    warning_days = db.Column(db.Integer, nullable=False, default=15)
    grace_days = db.Column(db.Integer, nullable=False, default=7)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<License {self.status}>'