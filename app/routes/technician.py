from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.models.user import User
from app.models.workorder import WorkOrder
from app.models.maintenance import MaintenanceSchedule
from app import db
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.decorators import roles_required
from app.utils.license import check_user_limit
from app.utils.security import is_password_strong, PASSWORD_POLICY_MESSAGE
from datetime import datetime, timedelta

tech_bp = Blueprint('tech', __name__)

@tech_bp.route('/dashboard')
@roles_required('technician', 'admin') # Admins can also see tech dash
def dashboard():
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)

    # Technician Metrics
    my_os = WorkOrder.query.filter_by(technician_id=user.id).all()
    total_my_os = len(my_os)
    completed_my_os = sum(1 for wo in my_os if wo.status == 'Completed')
    pending_my_os = sum(1 for wo in my_os if wo.status == 'Pending')
    in_progress_my_os = sum(1 for wo in my_os if wo.status == 'In Progress')

    # Alertas
    today = datetime.utcnow().date()
    
    # Serviços atrasados (do técnico)
    overdue_services = WorkOrder.query.filter(
        WorkOrder.technician_id == user.id,
        WorkOrder.scheduled_date < datetime.combine(today, datetime.min.time()),
        WorkOrder.status.in_(['Pending', 'In Progress'])
    ).all()

    return render_template('technician/dashboard.html',
                           my_os=my_os,
                           total_my_os=total_my_os,
                           completed_my_os=completed_my_os,
                           pending_my_os=pending_my_os,
                           in_progress_my_os=in_progress_my_os,
                           overdue_services=overdue_services)

@tech_bp.route('/list')
@roles_required('admin')
def list_technicians():
    technicians = User.query.all() # Fetch all employees
    return render_template('technician/list.html', technicians=technicians)

def normalize_job_title(permission_level, job_title, other_job_title=None):
    if permission_level == 'secretary':
        return 'Atendente'

    if job_title == 'Outros':
        return other_job_title or 'Outros'

    if job_title:
        return job_title

    return 'Técnico'

@tech_bp.route('/add', methods=['GET', 'POST'])
@roles_required('admin')
def add_technician():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        specialty = request.form.get('specialty')
        is_active = request.form.get('is_active') == 'on'
        permission_level = request.form.get('permission_level', 'user')
        job_title = normalize_job_title(
            permission_level,
            request.form.get('job_title'),
            request.form.get('other_job_title')
        )

        # Backend validation for password
        if not is_password_strong(password):
            flash(PASSWORD_POLICY_MESSAGE, 'danger')
            return render_template('technician/add.html')

        limit_error = check_user_limit(permission_level=permission_level, is_active=is_active)
        if limit_error:
            flash(limit_error, 'danger')
            return render_template('technician/add.html')

        user = User(name=name, email=email, role='technician', permission_level=permission_level, job_title=job_title, specialty=specialty, is_active=is_active)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash('Funcionário adicionado com sucesso!', 'success')
        return redirect(url_for('tech.list_technicians'))
    return render_template('technician/add.html')

@tech_bp.route('/edit/<int:user_id>', methods=['GET', 'POST'])
@roles_required('admin')
def edit_technician(user_id):
    user = User.query.get_or_404(user_id)

    if request.method == 'POST':
        user.name = request.form.get('name')
        user.email = request.form.get('email')
        user.specialty = request.form.get('specialty')
        user.is_active = request.form.get('is_active') == 'on'
        user.permission_level = request.form.get('permission_level', 'user')
        user.job_title = normalize_job_title(
            user.permission_level,
            request.form.get('job_title'),
            request.form.get('other_job_title')
        )

        password = request.form.get('password')
        if password: # only update if a new password was provided
            if not is_password_strong(password):
                flash(PASSWORD_POLICY_MESSAGE, 'danger')
                return render_template('technician/edit.html', user=user)
            user.set_password(password)

        limit_error = check_user_limit(permission_level=user.permission_level, existing_user=user, is_active=user.is_active)
        if limit_error:
            flash(limit_error, 'danger')
            return render_template('technician/edit.html', user=user)

        db.session.commit()
        flash('Funcionário atualizado com sucesso!', 'success')
        return redirect(url_for('tech.list_technicians'))

    return render_template('technician/edit.html', user=user)
