from app import db
from datetime import datetime

class Equipment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False) # E.g., Ar Condicionado Split 12000 BTUs
    brand = db.Column(db.String(100), nullable=True)
    model = db.Column(db.String(100), nullable=True)
    serial_number = db.Column(db.String(100), unique=True, nullable=True) # Useful for barcodes
    location = db.Column(db.String(200), nullable=True)
    qr_code_path = db.Column(db.String(255), nullable=True)  # path to QR code image

    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    work_orders = db.relationship('WorkOrder', backref='equipment', lazy=True)
    maintenance_schedules = db.relationship('MaintenanceSchedule', backref='equipment', lazy=True)

    def __repr__(self):
        return f'<Equipment {self.name} - SN: {self.serial_number}>'
