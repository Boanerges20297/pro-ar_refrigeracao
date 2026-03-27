from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.models.user import User
from app.models.workorder import WorkOrder
from app import db
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.decorators import roles_required

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

    return render_template('technician/dashboard.html',
                           my_os=my_os,
                           total_my_os=total_my_os,
                           completed_my_os=completed_my_os,
                           pending_my_os=pending_my_os,
                           in_progress_my_os=in_progress_my_os)

@tech_bp.route('/list')
@roles_required('admin')
def list_technicians():
    technicians = User.query.filter_by(role='technician').all()
    return render_template('technician/list.html', technicians=technicians)

import re

@tech_bp.route('/add', methods=['GET', 'POST'])
@roles_required('admin')
def add_technician():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        specialty = request.form.get('specialty')
        is_active = request.form.get('is_active') == 'on'

        # Backend validation for password
        if not re.match(r"^(?=.*[A-Za-z])(?=.*\d)[A-Za-z\d]{8,}$", password):
            flash('A senha deve ter no mínimo 8 caracteres, incluindo letras e números.', 'danger')
            return render_template('technician/add.html')

        user = User(name=name, email=email, role='technician', specialty=specialty, is_active=is_active)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash('Técnico adicionado com sucesso!', 'success')
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

        password = request.form.get('password')
        if password: # only update if a new password was provided
            if not re.match(r"^(?=.*[A-Za-z])(?=.*\d)[A-Za-z\d]{8,}$", password):
                flash('A senha deve ter no mínimo 8 caracteres, incluindo letras e números.', 'danger')
                return render_template('technician/edit.html', user=user)
            user.set_password(password)

        db.session.commit()
        flash('Técnico atualizado com sucesso!', 'success')
        return redirect(url_for('tech.list_technicians'))

    return render_template('technician/edit.html', user=user)
