"""Create or update the dedicated system superadmin from environment variables.

Usage:
  SUPERADMIN_EMAIL=... SUPERADMIN_PASSWORD=... flask --app wsgi run-command create-superadmin
"""
import os
import click
from flask import current_app
from app import db
from app.models.user import User


def register(app):
    @app.cli.command('create-superadmin')
    @click.option('--email', default=None, help='Superadmin email.')
    @click.option('--password', default=None, help='Superadmin password.')
    def create_superadmin(email, password):
        email = (email or os.getenv('SUPERADMIN_EMAIL') or '').strip().lower()
        password = password or os.getenv('SUPERADMIN_PASSWORD')
        if not email or not password:
            raise click.ClickException('Informe SUPERADMIN_EMAIL e SUPERADMIN_PASSWORD ou use --email/--password.')
        if len(password) < 8:
            raise click.ClickException('A senha do superadmin deve ter pelo menos 8 caracteres.')

        user = User.query.filter_by(email=email).first()
        if not user:
            user = User(name='Superadmin', email=email, role='admin', permission_level='admin', job_title='Superadmin', is_active=True)
            db.session.add(user)
        else:
            user.name = 'Superadmin'
            user.role = 'admin'
            user.permission_level = 'admin'
            user.job_title = 'Superadmin'
            user.is_active = True
        user.client_id = None
        user.set_password(password)
        user.must_change_password = False
        db.session.commit()
        click.echo(f'Superadmin pronto: {email}')
