from app import db
from datetime import datetime

class ServiceCatalog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False) # e.g., Limpeza, Manutenção Preventiva
    description = db.Column(db.Text, nullable=True)
    base_price = db.Column(db.Float, nullable=False, default=0.0)
    estimated_duration = db.Column(db.Integer, nullable=True) # Duration in minutes

    # Relationship
    work_orders = db.relationship('WorkOrder', backref='service_type', lazy=True)

    def __repr__(self):
        return f'<Service {self.name}>'
