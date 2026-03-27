from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.models.workorder import WorkOrder
from app.models.client import Client
from app.models.equipment import Equipment
from app.models.service import ServiceCatalog
from app.models.user import User
from app import db
from datetime import datetime
from flask_jwt_extended import jwt_required
from app.utils.decorators import roles_required

services_bp = Blueprint('services', __name__)

@services_bp.route('/')
@roles_required('admin', 'technician')
def index():
    work_orders = WorkOrder.query.all()
    return render_template('services/index.html', work_orders=work_orders)

@services_bp.route('/add', methods=['GET', 'POST'])
@roles_required('admin')
def add():
    clients = Client.query.all()
    equipments = Equipment.query.all()
    services = ServiceCatalog.query.all()
    technicians = User.query.filter_by(role='technician', is_active=True).all()

    if request.method == 'POST':
        client_id = request.form.get('client_id')
        equipment_id = request.form.get('equipment_id') or None
        service_id = request.form.get('service_id')
        technician_id = request.form.get('technician_id') or None

        # Safely parse total_value
        raw_total_value = request.form.get('total_value')
        try:
            total_value = float(raw_total_value) if raw_total_value else 0.0
        except ValueError:
            total_value = 0.0

        description = request.form.get('description')
        scheduled_date_str = request.form.get('scheduled_date')

        scheduled_date = datetime.strptime(scheduled_date_str, '%Y-%m-%dT%H:%M') if scheduled_date_str else None

        wo = WorkOrder(
            client_id=client_id,
            equipment_id=equipment_id,
            service_id=service_id,
            technician_id=technician_id,
            total_value=total_value,
            description=description,
            scheduled_date=scheduled_date
        )
        db.session.add(wo)
        db.session.commit()
        flash('Ordem de Serviço criada com sucesso!', 'success')
        return redirect(url_for('services.index'))

    return render_template('services/add.html', clients=clients, equipments=equipments, services=services, technicians=technicians)
