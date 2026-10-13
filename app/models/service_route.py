from datetime import datetime
import json
from app import db

class ServiceRoute(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    technician_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    work_order_ids = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(30), nullable=False, default='In Progress')
    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    client = db.relationship('Client', backref=db.backref('service_routes', lazy=True))
    technician = db.relationship('User', backref=db.backref('service_routes', lazy=True))

    @property
    def order_ids(self):
        try:
            return json.loads(self.work_order_ids or '[]')
        except (TypeError, ValueError):
            return []

    @order_ids.setter
    def order_ids(self, value):
        self.work_order_ids = json.dumps([int(item) for item in value])
