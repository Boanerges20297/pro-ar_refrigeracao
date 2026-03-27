from app import db
from datetime import datetime

class AppConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    logo_path = db.Column(db.String(255), nullable=True, default='/static/img/logo.jpg')
    company_name = db.Column(db.String(100), default='Pronto Ar Refrigeração')

    # Colors
    primary_color = db.Column(db.String(20), default='#3b82f6') # Azul
    secondary_color = db.Column(db.String(20), default='#9ca3af') # Cinza claro
    background_color = db.Column(db.String(20), default='#ffffff') # Branco
    text_color = db.Column(db.String(20), default='#111827') # Preto/Cinza escuro

    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<AppConfig {self.company_name}>'
