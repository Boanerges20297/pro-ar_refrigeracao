from app import db
from datetime import datetime

class WorkOrder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.String(50), nullable=False, default='Pending') # Pending, In Progress, Completed, Cancelled
    scheduled_date = db.Column(db.DateTime, nullable=True) # Data/Hora do agendamento
    completed_date = db.Column(db.DateTime, nullable=True)
    description = db.Column(db.Text, nullable=True) # Observações do serviço

    # Financials
    total_value = db.Column(db.Float, nullable=False, default=0.0) # Valor total cobrado
    paid_value = db.Column(db.Float, nullable=False, default=0.0)
    is_paid = db.Column(db.Boolean, default=False)

    # Foreign Keys
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    equipment_id = db.Column(db.Integer, db.ForeignKey('equipment.id'), nullable=True) # Optional, can be a general service
    service_id = db.Column(db.Integer, db.ForeignKey('service_catalog.id'), nullable=False)
    technician_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True) # Assign a technician

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<WorkOrder #{self.id} - {self.status}>'
