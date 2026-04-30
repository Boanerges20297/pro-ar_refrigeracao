from app import db
from datetime import datetime
from flask_bcrypt import generate_password_hash, check_password_hash

user_client_association = db.Table('user_client_association',
    db.Column('id', db.Integer, primary_key=True, autoincrement=True),
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), nullable=False),
    db.Column('client_id', db.Integer, db.ForeignKey('client.id'), nullable=False)
)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    permission_level = db.Column(db.String(20), nullable=False, default='user') # 'admin', 'secretary', or 'user'
    job_title = db.Column(db.String(50), nullable=False, default='Usuário') # e.g. Técnico, Secretário(a), Administrador (unisex)
    role = db.Column(db.String(20), nullable=False, default='technician') # Deprecated: 'admin', 'secretary', or 'technician', kept for compatibility if needed.
    specialty = db.Column(db.String(100), nullable=True) # E.g., Refrigeration, Electrical
    is_active = db.Column(db.Boolean, default=True)
    must_change_password = db.Column(db.Boolean, default=False, nullable=False)
    # Deprecated: use 'clients' relationship (many-to-many) instead. 
    # Kept for backward compatibility during migration.
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=True)
    cpf = db.Column(db.String(14), unique=True, nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    work_orders = db.relationship('WorkOrder', backref='technician', lazy=True)
    clients = db.relationship('Client', secondary=user_client_association, backref=db.backref('associated_users', lazy='dynamic'))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.name} - {self.job_title} ({self.permission_level})>'
