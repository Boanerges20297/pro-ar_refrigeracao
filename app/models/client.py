from app import db
from datetime import datetime

class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    cnpj = db.Column(db.String(18), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    address = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    equipments = db.relationship('Equipment', backref='owner', lazy=True)
    work_orders = db.relationship('WorkOrder', backref='client', lazy=True)
    users = db.relationship('User', backref='client_record', lazy=True)

    def __repr__(self):
        return f'<Client {self.name}>'
