from app import db
from datetime import datetime

class FinancialCategory(db.Model):
    __tablename__ = 'financial_category'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(20), nullable=False) # 'revenue' or 'expense'
    
    transactions = db.relationship('FinancialTransaction', back_populates='category', lazy=True)

    def __repr__(self):
        return f'<FinancialCategory {self.name} ({self.type})>'

class FinancialTransaction(db.Model):
    __tablename__ = 'financial_transaction'
    
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(20), nullable=False) # 'revenue' or 'expense'
    category_id = db.Column(db.Integer, db.ForeignKey('financial_category.id'), nullable=True)
    description = db.Column(db.String(255), nullable=False)
    amount = db.Column(db.Float, nullable=False, default=0.0)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    status = db.Column(db.String(20), nullable=False, default='paid') # 'paid' or 'pending'
    
    # Integration fields
    work_order_id = db.Column(db.Integer, db.ForeignKey('work_order.id', ondelete='SET NULL'), nullable=True)
    work_order_expense_id = db.Column(db.Integer, db.ForeignKey('workorder_expense.id', ondelete='SET NULL'), nullable=True)
    
    is_automated = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    category = db.relationship('FinancialCategory', back_populates='transactions')
    work_order = db.relationship('WorkOrder', backref=db.backref('finance_entries', lazy=True))
    work_order_expense = db.relationship('WorkOrderExpense', backref=db.backref('finance_entries', lazy=True))

    def __repr__(self):
        return f'<FinancialTransaction {self.type} - {self.description} - R$ {self.amount}>'
