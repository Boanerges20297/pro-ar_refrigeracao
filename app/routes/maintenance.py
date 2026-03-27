from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.models.maintenance import MaintenanceSchedule
from app.models.equipment import Equipment
from app import db
from datetime import datetime
from flask_jwt_extended import jwt_required
from app.utils.decorators import roles_required

maint_bp = Blueprint('maintenance', __name__)

@maint_bp.route('/')
@roles_required('admin', 'technician')
def index():
    schedules = MaintenanceSchedule.query.order_by(MaintenanceSchedule.next_maintenance_date).all()
    return render_template('maintenance/index.html', schedules=schedules, now=datetime.utcnow())

@maint_bp.route('/add', methods=['GET', 'POST'])
@roles_required('admin')
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
def complete(schedule_id):
    schedule = MaintenanceSchedule.query.get_or_404(schedule_id)
    schedule.last_maintenance_date = datetime.utcnow()
    # In a real app we might automatically schedule the next one, but for now we mark it inactive
    schedule.is_active = False
    db.session.commit()
    flash('Manutenção marcada como realizada.', 'success')
    return redirect(url_for('maintenance.index'))
