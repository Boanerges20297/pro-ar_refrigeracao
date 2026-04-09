from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.models.maintenance import MaintenanceSchedule
from app.models.equipment import Equipment
from app.models.user import User
from app import db
from datetime import datetime
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.decorators import license_feature_required, roles_required, get_technician_client_ids

maint_bp = Blueprint('maintenance', __name__)

@maint_bp.route('/')
@roles_required('admin', 'secretary', 'technician')
@license_feature_required('maintenance')
def index():
    # Get current user
    current_user_id = get_jwt_identity()
    current_user = User.query.get(current_user_id) if current_user_id else None
    
    # Check if user is technician
    is_technician = current_user and current_user.permission_level == 'user'
    
    if is_technician:
        # Técnico vê apenas manutenções de equipamentos de clientes que atendeu
        client_ids = get_technician_client_ids(current_user.id)
        if client_ids:
            # Get all equipments from the clients the technician has served
            equip_ids = db.session.query(Equipment.id).filter(Equipment.client_id.in_(client_ids)).all()
            equip_ids = [eid[0] for eid in equip_ids]
            schedules = MaintenanceSchedule.query.filter(
                MaintenanceSchedule.equipment_id.in_(equip_ids)
            ).order_by(MaintenanceSchedule.next_maintenance_date).all()
        else:
            schedules = []
    else:
        # Admin e Secretary veem todas as manutenções
        schedules = MaintenanceSchedule.query.order_by(MaintenanceSchedule.next_maintenance_date).all()
    
    return render_template('maintenance/index.html', schedules=schedules, now=datetime.utcnow())

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

@maint_bp.route('/<int:schedule_id>/complete', methods=['POST'])
@roles_required('admin', 'technician')
@license_feature_required('maintenance')
def complete(schedule_id):
    schedule = MaintenanceSchedule.query.get_or_404(schedule_id)
    schedule.last_maintenance_date = datetime.utcnow()
    # In a real app we might automatically schedule the next one, but for now we mark it inactive
    schedule.is_active = False
    db.session.commit()
    flash('Manutenção marcada como realizada.', 'success')
    return redirect(url_for('maintenance.index'))
