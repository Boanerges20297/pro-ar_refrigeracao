from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_jwt_extended import jwt_required
from app.utils.decorators import roles_required
from app.models.workorder import WorkOrder
from app.models.user import User
from app.models.config import AppConfig
from app import db
from sqlalchemy import func

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
        config.company_name = request.form.get('company_name')
        config.primary_color = request.form.get('primary_color')
        config.secondary_color = request.form.get('secondary_color')
        config.background_color = request.form.get('background_color')
        config.text_color = request.form.get('text_color')

        # In a real app we would handle file uploads for logo here
        # For this prototype we will allow URL editing
        config.logo_path = request.form.get('logo_path') or config.logo_path

        db.session.commit()
        flash('Configurações atualizadas com sucesso!', 'success')
        return redirect(url_for('admin.settings'))

    return render_template('admin/settings.html', config=config)
