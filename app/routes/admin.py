import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_jwt_extended import jwt_required
from app.utils.decorators import roles_required
from app.models.workorder import WorkOrder
from app.models.user import User
from app.models.config import AppConfig
from app import db
from sqlalchemy import func

ALLOWED_LOGO_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp', 'svg'}
MAX_LOGO_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/dashboard')
@roles_required('admin')
def dashboard():
    # Metrics
    total_os = WorkOrder.query.count()
    completed_os = WorkOrder.query.filter_by(status='Completed').count()
    pending_os = WorkOrder.query.filter_by(status='Pending').count()

    # Financials
    total_revenue = db.session.query(func.sum(WorkOrder.total_value)).filter(WorkOrder.status == 'Completed').scalar() or 0.0
    pending_revenue = db.session.query(func.sum(WorkOrder.total_value)).filter(WorkOrder.status != 'Completed').scalar() or 0.0

    # Technicians Performance
    techs = User.query.filter_by(role='technician').all()
    tech_performance = []
    for tech in techs:
        tech_os_count = WorkOrder.query.filter_by(technician_id=tech.id).count()
        tech_performance.append({
            'name': tech.name,
            'specialty': tech.specialty,
            'os_count': tech_os_count
        })

    return render_template('admin/dashboard.html',
                           total_os=total_os,
                           completed_os=completed_os,
                           pending_os=pending_os,
                           total_revenue=total_revenue,
                           pending_revenue=pending_revenue,
                           tech_performance=tech_performance)

@admin_bp.route('/settings', methods=['GET', 'POST'])
@roles_required('admin')
def settings():
    config = AppConfig.query.first()
    if not config:
        config = AppConfig()
        db.session.add(config)
        db.session.commit()

    if request.method == 'POST':
        config.company_name      = request.form.get('company_name')
        config.primary_color     = request.form.get('primary_color')
        config.secondary_color   = request.form.get('secondary_color')
        config.background_color  = request.form.get('background_color')
        config.text_color        = request.form.get('text_color')
        config.navbar_bg_color    = request.form.get('navbar_bg_color')
        config.navbar_link_color  = request.form.get('navbar_link_color')
        config.navbar_hover_color = request.form.get('navbar_hover_color')

        # SMTP Settings
        config.smtp_provider    = request.form.get('smtp_provider')
        config.smtp_server      = request.form.get('smtp_server')

        config.smtp_port        = int(request.form.get('smtp_port') or 587)
        config.smtp_user        = request.form.get('smtp_user')
        config.smtp_password    = request.form.get('smtp_password')
        config.smtp_use_tls     = 'smtp_use_tls' in request.form
        config.smtp_use_ssl     = 'smtp_use_ssl' in request.form
        config.mail_sender_name = request.form.get('mail_sender_name')


        # Handle logo file upload
        logo_file = request.files.get('logo_file')
        if logo_file and logo_file.filename:
            ext = logo_file.filename.rsplit('.', 1)[-1].lower()
            if ext not in ALLOWED_LOGO_EXTENSIONS:
                flash(f'Formato inválido. Use: JPG, PNG, WEBP ou SVG.', 'danger')
                return render_template('admin/settings.html', config=config)

            logo_file.seek(0, 2)  # seek to end
            file_size = logo_file.tell()
            logo_file.seek(0)
            if file_size > MAX_LOGO_SIZE_BYTES:
                flash('A imagem excede o limite de 2 MB. Escolha um arquivo menor.', 'danger')
                return render_template('admin/settings.html', config=config)

            save_dir = os.path.join(current_app.static_folder, 'img')
            os.makedirs(save_dir, exist_ok=True)
            filename = f'logo.{ext}'
            logo_file.save(os.path.join(save_dir, filename))
            config.logo_path = f'/static/img/{filename}'
        else:
            # Allow manual URL if no file was chosen
            manual = request.form.get('logo_path')
            if manual:
                config.logo_path = manual

        db.session.commit()
        flash('Configurações atualizadas com sucesso!', 'success')
        return redirect(url_for('admin.settings'))

    return render_template('admin/settings.html', config=config)
