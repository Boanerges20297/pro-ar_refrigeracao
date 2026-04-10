from app import db
from datetime import datetime

class MaintenanceSchedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    equipment_id = db.Column(db.Integer, db.ForeignKey('equipment.id'), nullable=False)
    workorder_id = db.Column(db.Integer, db.ForeignKey('work_order.id'), nullable=True, unique=True)
    next_maintenance_date = db.Column(db.DateTime, nullable=False)
    last_maintenance_date = db.Column(db.DateTime, nullable=True)
    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    work_order = db.relationship('WorkOrder', back_populates='maintenance_schedule', uselist=False)

    def __repr__(self):
        return f'<MaintenanceSchedule Eq:{self.equipment_id} - Next:{self.next_maintenance_date}>'
