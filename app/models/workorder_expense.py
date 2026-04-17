from app import db
from datetime import datetime


class WorkOrderExpense(db.Model):
    __tablename__ = 'workorder_expense'

    id = db.Column(db.Integer, primary_key=True)
    work_order_id = db.Column(db.Integer, db.ForeignKey('work_order.id', ondelete='CASCADE'), nullable=False)

    description = db.Column(db.String(255), nullable=False)  # Ex: "Gás R-410A", "Válvula solenoide"
    category = db.Column(db.String(100), nullable=True)       # Ex: "Peça", "Material Hidráulico", "Mão de Obra"
    quantity = db.Column(db.Float, nullable=False, default=1.0)
    unit_price = db.Column(db.Float, nullable=False, default=0.0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship back to WorkOrder
    work_order = db.relationship('WorkOrder', back_populates='expenses')

    @property
    def total(self):
        return round((self.quantity or 1.0) * (self.unit_price or 0.0), 2)

    def __repr__(self):
        return f'<WorkOrderExpense #{self.id} - {self.description}>'
