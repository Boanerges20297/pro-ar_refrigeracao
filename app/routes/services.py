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
from app.utils.images import save_and_resize_image

services_bp = Blueprint('services', __name__)

from sqlalchemy import func

@services_bp.route('/')
@roles_required('admin', 'technician')
def index():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    
    # Subquery to get the latest OS date for each client
    latest_os_subquery = db.session.query(
        WorkOrder.client_id,
        func.max(WorkOrder.created_at).label('latest_os')
    ).group_by(WorkOrder.client_id).subquery()

    # Query clients who have OS, ordered by their latest OS date
    pagination = Client.query.join(
        latest_os_subquery, Client.id == latest_os_subquery.c.client_id
    ).order_by(latest_os_subquery.c.latest_os.desc()).paginate(page=page, per_page=per_page, error_out=False)
    
    clients = pagination.items
    
    # For each client, we'll need their OS in descending order. 
    # We can pre-fetch them or rely on the relationship with a custom order if needed.
    # In the template, we'll use: client.work_orders | sort(attribute='created_at', reverse=True)
    
    return render_template('services/index.html', clients=clients, pagination=pagination, per_page=per_page)

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
            total_value = round(float(raw_total_value), 2) if raw_total_value else 0.0
        except ValueError:
            total_value = 0.0

        description = request.form.get('description')
        scheduled_date_str = request.form.get('scheduled_date')

        scheduled_date = datetime.strptime(scheduled_date_str, '%Y-%m-%dT%H:%M') if scheduled_date_str else None

        # --- Handle Image Uploads ---
        photo_before_file = request.files.get('photo_before')
        photo_after_file = request.files.get('photo_after')
        
        photo_before_path = None
        photo_after_path = None
        
        if photo_before_file and photo_before_file.filename:
            photo_before_path = save_and_resize_image(photo_before_file, 'uploads/work_orders')
            
        if photo_after_file and photo_after_file.filename:
            photo_after_path = save_and_resize_image(photo_after_file, 'uploads/work_orders')

        wo = WorkOrder(
            client_id=client_id,
            equipment_id=equipment_id,
            service_id=service_id,
            technician_id=technician_id,
            total_value=total_value,
            description=description,
            scheduled_date=scheduled_date,
            photo_before=photo_before_path,
            photo_after=photo_after_path
        )
        db.session.add(wo)
        db.session.commit()
        flash('Ordem de Serviço criada com sucesso!', 'success')
        return redirect(url_for('services.index'))

    return render_template('services/add.html', clients=clients, equipments=equipments, services=services, technicians=technicians)
@services_bp.route('/edit/<int:id>', methods=['GET', 'POST'])
@roles_required('admin', 'technician')
def edit(id):
    wo = WorkOrder.query.get_or_404(id)
    clients = Client.query.all()
    equipments = Equipment.query.all()
    services = ServiceCatalog.query.all()
    technicians = User.query.filter_by(role='technician', is_active=True).all()

    if request.method == 'POST':
        # Technician can only edit status, description and photos? 
        # For now, let's allow all fields for both, but focus on photos and status.
        wo.status = request.form.get('status')
        wo.description = request.form.get('description')
        
        try:
            wo.total_value = round(float(raw_total_value), 2) if raw_total_value else 0.0
        except ValueError:
            pass

        scheduled_date_str = request.form.get('scheduled_date')
        if scheduled_date_str:
            wo.scheduled_date = datetime.strptime(scheduled_date_str, '%Y-%m-%dT%H:%M')

        # --- Handle Image Uploads ---
        photo_before_file = request.files.get('photo_before')
        photo_after_file = request.files.get('photo_after')
        
        if photo_before_file and photo_before_file.filename:
            wo.photo_before = save_and_resize_image(photo_before_file, 'uploads/work_orders')
            
        if photo_after_file and photo_after_file.filename:
            wo.photo_after = save_and_resize_image(photo_after_file, 'uploads/work_orders')

        db.session.commit()
        flash(f'Ordem de Serviço #{id} atualizada com sucesso!', 'success')
        return redirect(url_for('services.index'))

    return render_template('services/edit.html', wo=wo, clients=clients, equipments=equipments, services=services, technicians=technicians)
