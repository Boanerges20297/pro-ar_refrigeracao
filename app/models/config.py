from app import db
from datetime import datetime

class AppConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    logo_path = db.Column(db.String(255), nullable=True, default='/static/img/logo.jpg')
    company_name = db.Column(db.String(100), default='Pronto Ar Refrigeração')
    cnpj = db.Column(db.String(32), nullable=True)

    # Colors
    primary_color = db.Column(db.String(20), default='#3b82f6') # Azul
    secondary_color = db.Column(db.String(20), default='#000000') # Preto
    background_color = db.Column(db.String(20), default='#dbd6d6') # Cinza de fundo
    text_color = db.Column(db.String(20), default='#000000') # Preto

    # Navbar
    navbar_bg_color    = db.Column(db.String(20), default='#ffffff')   # Fundo do menu
    navbar_link_color  = db.Column(db.String(20), default='#000000')   # Cor da fonte/links
    navbar_hover_color = db.Column(db.String(20), default='#787c7d')   # Cor de hover e ativo

    # SMTP Settings (for password recovery)
    smtp_provider = db.Column(db.String(50), default='gmail') # 'gmail', 'outlook', 'yahoo', 'custom'
    smtp_server = db.Column(db.String(100), default='smtp.gmail.com')

    smtp_port = db.Column(db.Integer, default=587)
    smtp_user = db.Column(db.String(120), nullable=True)
    smtp_password = db.Column(db.String(128), nullable=True)
    smtp_use_tls = db.Column(db.Boolean, default=True)
    smtp_use_ssl = db.Column(db.Boolean, default=False)
    mail_sender_name = db.Column(db.String(100), default='Pronto Ar Refrigeração')

    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


    def __repr__(self):
        return f'<AppConfig {self.company_name}>'
