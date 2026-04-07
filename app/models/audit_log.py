from app import db
from datetime import datetime

class AuditLog(db.Model):
    """
    Table to store audit logs of all user actions.
    Keeps records for the last 7 days.
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    action = db.Column(db.String(100), nullable=False)  # e.g., CREATE, READ, UPDATE, DELETE, LOGIN
    resource_type = db.Column(db.String(50), nullable=False)  # e.g., WorkOrder, Client, Equipment
    resource_id = db.Column(db.Integer, nullable=True)  # ID of the affected resource
    resource_name = db.Column(db.String(255), nullable=True)  # Name/description of the resource
    status = db.Column(db.String(20), default='success')  # success, error
    ip_address = db.Column(db.String(45), nullable=True)  # IPv4 or IPv6
    user_agent = db.Column(db.String(255), nullable=True)  # Browser/client info
    details = db.Column(db.Text, nullable=True)  # Additional details in JSON format
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # Relationship
    user = db.relationship('User', backref='audit_logs')

    def __repr__(self):
        return f'<AuditLog {self.id}: {self.user_id} - {self.action} {self.resource_type}>'

    @staticmethod
    def cleanup_old_logs(days=7):
        """Delete logs older than specified days."""
        from datetime import timedelta
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        deleted = AuditLog.query.filter(AuditLog.timestamp < cutoff_date).delete()
        db.session.commit()
        return deleted
