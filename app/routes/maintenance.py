from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from app.models.client import Client
from app.models.maintenance import MaintenanceSchedule
from app.models.equipment import Equipment
from app.models.workorder import WorkOrder
from app.models.user import User
from app import db
from datetime import datetime
from flask_jwt_extended import get_jwt_identity
from app.utils.decorators import license_feature_required, roles_required
from app.utils.maintenance import get_or_create_maintenance_service
from sqlalchemy import or_

maint_bp = Blueprint('maintenance', __name__)


def can_access_schedule(user, schedule):
    if not user:
        return False

    if user.permission_level in ['admin', 'secretary']:
        return True

    return bool(schedule.work_order and schedule.work_order.technician_id == user.id)

@maint_bp.route('/')
@roles_required('admin', 'secretary', 'technician')
@license_feature_required('maintenance')
def index():
    # Get current user
    current_user_id = get_jwt_identity()
    current_user = User.query.get(current_user_id) if current_user_id else None
    search = (request.args.get('search') or '').strip()
    
    # Check if user is technician
    is_technician = current_user and current_user.permission_level == 'user'

    query = MaintenanceSchedule.query.join(MaintenanceSchedule.equipment).join(Equipment.owner).outerjoin(MaintenanceSchedule.work_order).outerjoin(WorkOrder.technician)
    
    if is_technician:
        # Técnico vê apenas manutenções vinculadas às OS atribuídas a ele
        query = query.filter(
            WorkOrder.technician_id == current_user.id
        )

    if search:
        search_term = f'%{search}%'
        query = query.filter(
            or_(
                Client.name.ilike(search_term),
                Equipment.name.ilike(search_term),
                Equipment.serial_number.ilike(search_term),
                Equipment.location.ilike(search_term),
                User.name.ilike(search_term),
                WorkOrder.description.ilike(search_term),
                MaintenanceSchedule.description.ilike(search_term),
            )
        )

    schedules = query.order_by(MaintenanceSchedule.next_maintenance_date).all()
    
    return render_template('maintenance/index.html', schedules=schedules, now=datetime.utcnow(), search=search)

@maint_bp.route('/add', methods=['GET', 'POST'])
@roles_required('admin', 'secretary')
@license_feature_required('maintenance')
def add():
    equipments = Equipment.query.all()

    if request.method == 'POST':
        equipment_id = request.form.get('equipment_id')
        next_maintenance_date_str = request.form.get('next_maintenance_date')
        description = request.form.get('description')

        next_maintenance_date = datetime.strptime(next_maintenance_date_str, '%Y-%m-%d') if next_maintenance_date_str else None

        schedule = MaintenanceSchedule(
            equipment_id=equipment_id,
            next_maintenance_date=next_maintenance_date,
            description=description,
            is_active=True
        )
        db.session.add(schedule)
        db.session.commit()
        flash('Agendamento de Manutenção criado com sucesso!', 'success')
        return redirect(url_for('maintenance.index'))

    return render_template('maintenance/add.html', equipments=equipments)

@maint_bp.route('/<int:schedule_id>/workorder')
@roles_required('admin', 'secretary', 'technician')
@license_feature_required('maintenance')
def open_workorder(schedule_id):
    schedule = MaintenanceSchedule.query.get_or_404(schedule_id)

    current_user_id = get_jwt_identity()
    current_user = User.query.get(current_user_id) if current_user_id else None
    if not can_access_schedule(current_user, schedule):
        abort(403)

    workorder = schedule.work_order
    if not workorder:
        maintenance_service = get_or_create_maintenance_service()
        technician_id = current_user.id if current_user and current_user.permission_level == 'user' else None

        workorder = WorkOrder(
            client_id=schedule.equipment.client_id,
            equipment_id=schedule.equipment_id,
            service_id=maintenance_service.id,
            technician_id=technician_id,
            scheduled_date=schedule.next_maintenance_date,
            description=schedule.description or 'OS gerada a partir do agendamento de manutenção preventiva.',
            status='Pending',
            total_value=maintenance_service.base_price or 0.0,
        )
        db.session.add(workorder)
        db.session.flush()

        schedule.work_order = workorder

    db.session.commit()
    return redirect(url_for('services.edit', id=workorder.id, return_to=url_for('maintenance.index')))
