from datetime import datetime

from app import db


class PushSubscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    endpoint = db.Column(db.Text, nullable=False, unique=True)
    subscription_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('push_subscriptions', cascade='all, delete-orphan'))


class NotificationJob(db.Model):
    """Persistent outbox for scheduled service reminders."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    workorder_id = db.Column(db.Integer, db.ForeignKey('work_order.id', ondelete='CASCADE'), nullable=False, index=True)
    reminder_kind = db.Column(db.String(20), nullable=False)
    scheduled_at = db.Column(db.DateTime, nullable=False)
    due_at = db.Column(db.DateTime, nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default='pending', index=True)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    last_error = db.Column(db.String(500), nullable=True)
    sent_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship('User')
    workorder = db.relationship('WorkOrder')
    __table_args__ = (db.UniqueConstraint('user_id', 'workorder_id', 'reminder_kind', 'scheduled_at', name='uq_notification_workorder_reminder'),)
