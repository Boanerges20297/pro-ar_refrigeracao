import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app, render_template
from app.models.config import AppConfig
import logging

def send_dynamic_email(to_email, subject, template, **kwargs):
    """
    Sends an email using SMTP settings from the database (AppConfig).
    """
    config = AppConfig.query.first()
    if not config or not config.smtp_user or not config.smtp_password:
        logging.error("SMTP not configured in AppConfig.")
        return False, "E-mail não configurado no sistema."

    try:
        current_app.logger.info(f"Preparing email for {to_email} via {config.smtp_provider}")
        # Create message
        from email.header import Header
        msg = MIMEMultipart()
        # Yahoo is strict. Use simpler 'From' if name is empty or if it's Yahoo.
        if config.smtp_provider == 'yahoo' or not config.mail_sender_name:
            msg['From'] = config.smtp_user
        else:
            msg['From'] = f"{Header(config.mail_sender_name, 'utf-8')} <{config.smtp_user}>"


            
        msg['To'] = to_email
        msg['Subject'] = subject

        # Render HTML body
        from datetime import datetime
        body = render_template(template, config=config, now=datetime.utcnow(), **kwargs)

        msg.attach(MIMEText(body, 'html'))

        current_app.logger.info(f"Connecting to {config.smtp_server}:{config.smtp_port} (SSL: {config.smtp_use_ssl})")

        # Connect to server
        if config.smtp_use_ssl:
            server = smtplib.SMTP_SSL(config.smtp_server, config.smtp_port, timeout=10)
        else:
            server = smtplib.SMTP(config.smtp_server, config.smtp_port, timeout=10)
            if config.smtp_use_tls:
                server.starttls()

        # Login and send
        current_app.logger.info("Logging in...")
        server.login(config.smtp_user, config.smtp_password)
        current_app.logger.info("Sending message...")
        server.send_message(msg)
        server.quit()

        current_app.logger.info("✅ Email sent successfully.")
        return True, "E-mail enviado com sucesso."

    except Exception as e:
        error_msg = f"❌ FAILED: {str(e)}"
        current_app.logger.error(error_msg)
        print(error_msg) # Direct print to console
        return False, error_msg


def send_password_reset_email(user, reset_url, logo_url=None):
    """
    Helper to send the password reset email specifically.
    """
    subject = "Recuperação de Senha - Pronto Ar Refrigeração"
    return send_dynamic_email(
        to_email=user.email,
        subject=subject,
        template='email/reset_email.html',
        user=user,
        reset_url=reset_url,
        logo_url=logo_url
    )


