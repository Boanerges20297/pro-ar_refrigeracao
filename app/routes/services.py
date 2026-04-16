from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, current_app, send_from_directory, abort, jsonify
from app.models.workorder import WorkOrder
from app.models.client import Client
from app.models.equipment import Equipment
from app.models.service import ServiceCatalog
from app.models.user import User
from app.models.config import AppConfig
from app import db
from datetime import datetime
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.decorators import roles_required, get_technician_client_ids
from app.utils.images import save_and_resize_image
from app.utils.maintenance import sync_schedule_with_workorder
from app.utils.audit import log_action
import io
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from sqlalchemy import or_, func
from xml.sax.saxutils import escape

services_bp = Blueprint('services', __name__)


def get_current_user():
    current_user_id = get_jwt_identity()
    return User.query.get(current_user_id) if current_user_id else None


def get_status_label(status):
    return {
        'Completed': 'Concluída',
        'Pending': 'Pendente',
        'In Progress': 'Em Andamento'
    }.get(status, status)


def normalize_return_to(target):
    if not target:
        return None

    if target.startswith('/') and not target.startswith('//'):
        return target

    return None


def can_access_workorder_photo(user, workorder):
    if not user:
        return False

    if user.permission_level in ['admin', 'secretary']:
        return True

    return workorder.technician_id == user.id


def can_access_workorder(user, workorder):
    if not user:
        return False

    if user.permission_level in ['admin', 'secretary']:
        return True

    return workorder.technician_id == user.id


def serialize_service_catalog(service):
    return {
        'id': service.id,
        'name': service.name,
        'description': service.description or '',
        'base_price': float(service.base_price or 0.0),
        'base_price_label': f'R$ {service.base_price:.2f}',
        'estimated_duration': service.estimated_duration,
    }


@services_bp.route('/catalog', methods=['POST'])
@roles_required('admin')
def create_service_catalog():
    payload = request.get_json(silent=True) or request.form
    name = (payload.get('name') or '').strip()
    description = (payload.get('description') or '').strip() or None
    base_price_raw = payload.get('base_price')
    estimated_duration_raw = payload.get('estimated_duration')

    if not name:
        if request.is_json:
            return jsonify({'ok': False, 'message': 'Informe o nome do tipo de serviço.'}), 400
        flash('Informe o nome do tipo de serviço.', 'danger')
        return redirect(request.referrer or url_for('services.add'))

    existing_service = ServiceCatalog.query.filter(func.lower(ServiceCatalog.name) == name.lower()).first()
    if existing_service:
        response_body = {
            'ok': False,
            'message': 'Já existe um tipo de serviço com esse nome.',
            'service': serialize_service_catalog(existing_service),
        }
        if request.is_json:
            return jsonify(response_body), 409
        flash('Já existe um tipo de serviço com esse nome.', 'warning')
        return redirect(request.referrer or url_for('services.add'))

    try:
        base_price = round(float(base_price_raw), 2) if base_price_raw not in (None, '') else 0.0
    except (TypeError, ValueError):
        base_price = 0.0

    try:
        estimated_duration = int(estimated_duration_raw) if estimated_duration_raw not in (None, '') else None
    except (TypeError, ValueError):
        estimated_duration = None

    service = ServiceCatalog(
        name=name,
        description=description,
        base_price=base_price,
        estimated_duration=estimated_duration,
    )
    db.session.add(service)
    db.session.commit()

    response_body = {
        'ok': True,
        'message': 'Tipo de serviço cadastrado com sucesso.',
        'service': serialize_service_catalog(service),
    }
    if request.is_json:
        return jsonify(response_body), 201

    flash('Tipo de serviço cadastrado com sucesso.', 'success')
    return redirect(request.referrer or url_for('services.add'))


@services_bp.route('/catalog')
@roles_required('admin')
def service_catalog():
    services = ServiceCatalog.query.order_by(ServiceCatalog.name.asc()).all()
    usage_counts = dict(
        db.session.query(WorkOrder.service_id, func.count(WorkOrder.id))
        .group_by(WorkOrder.service_id)
        .all()
    )

    return render_template(
        'services/catalog.html',
        services=services,
        usage_counts=usage_counts,
    )


@services_bp.route('/catalog/<int:service_id>/update', methods=['POST'])
@roles_required('admin')
def update_service_catalog(service_id):
    service = ServiceCatalog.query.get_or_404(service_id)
    name = (request.form.get('name') or '').strip()
    description = (request.form.get('description') or '').strip() or None
    base_price_raw = request.form.get('base_price')
    estimated_duration_raw = request.form.get('estimated_duration')

    if not name:
        flash('Informe o nome do tipo de serviço.', 'danger')
        return redirect(url_for('services.service_catalog'))

    existing_service = ServiceCatalog.query.filter(
        func.lower(ServiceCatalog.name) == name.lower(),
        ServiceCatalog.id != service.id,
    ).first()
    if existing_service:
        flash('Já existe outro tipo de serviço com esse nome.', 'warning')
        return redirect(url_for('services.service_catalog'))

    try:
        base_price = round(float(base_price_raw), 2) if base_price_raw not in (None, '') else 0.0
    except (TypeError, ValueError):
        base_price = 0.0

    try:
        estimated_duration = int(estimated_duration_raw) if estimated_duration_raw not in (None, '') else None
    except (TypeError, ValueError):
        estimated_duration = None

    service.name = name
    service.description = description
    service.base_price = base_price
    service.estimated_duration = estimated_duration
    db.session.commit()

    flash('Tipo de serviço atualizado com sucesso.', 'success')
    return redirect(url_for('services.service_catalog'))


@services_bp.route('/catalog/<int:service_id>/delete', methods=['POST'])
@roles_required('admin')
def delete_service_catalog(service_id):
    service = ServiceCatalog.query.get_or_404(service_id)
    usage_count = WorkOrder.query.filter_by(service_id=service.id).count()

    if usage_count > 0:
        flash('Não é possível excluir um tipo de serviço que já possui OS vinculadas.', 'danger')
        return redirect(url_for('services.service_catalog'))

    db.session.delete(service)
    db.session.commit()
    flash('Tipo de serviço excluído com sucesso.', 'success')
    return redirect(url_for('services.service_catalog'))


@services_bp.route('/uploads/work-orders/<path:filename>')
@roles_required('admin', 'secretary', 'technician')
def workorder_photo(filename):
    normalized_filename = filename.replace('\\', '/').lstrip('/')
    if '..' in normalized_filename:
        abort(404)

    workorder = WorkOrder.query.filter(
        or_(
            WorkOrder.photo_before == normalized_filename,
            WorkOrder.photo_after == normalized_filename,
        )
    ).first_or_404()

    user = get_current_user()
    if not can_access_workorder_photo(user, workorder):
        abort(403)

    return send_from_directory(current_app.config['UPLOAD_ROOT'], normalized_filename)


@services_bp.route('/receipt/<int:id>')
@roles_required('admin', 'secretary', 'technician')
def receipt(id):
    """Exibir recibo imprimível de uma ordem de serviço."""
    current_user = get_current_user()
    wo = WorkOrder.query.get_or_404(id)

    if not can_access_workorder(current_user, wo):
        abort(403)

    config = AppConfig.query.first()
    company_name = config.company_name if config and config.company_name else 'Pronto Ar Refrigeração'

    company_responsible_name = '-'
    company_responsible_role = 'Responsável da Empresa'
    if wo.technician:
        company_responsible_name = wo.technician.name
        company_responsible_role = wo.technician.job_title or 'Técnico Responsável'
    elif current_user:
        company_responsible_name = current_user.name
        company_responsible_role = current_user.job_title or 'Responsável da Empresa'

    return render_template(
        'services/receipt.html',
        wo=wo,
        config=config,
        company_name=company_name,
        company_responsible_name=company_responsible_name,
        company_responsible_role=company_responsible_role,
        issued_at=datetime.now(),
        status_label=get_status_label(wo.status),
    )

@services_bp.route('/')
@roles_required('admin', 'secretary', 'technician')
def index():
    """Mostrar ordens de serviço agrupadas por cliente com os últimos 5 de cada"""
    current_user = get_current_user()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    search = (request.args.get('search') or '').strip()

    if per_page not in [1, 10, 20]:
        per_page = 10
    
    # Check if user is technician
    is_technician = current_user and current_user.permission_level == 'user'
    filtered_client_ids = None

    if search:
        search_term = f'%{search}%'
        matching_workorders_query = WorkOrder.query.join(WorkOrder.client).outerjoin(WorkOrder.equipment).outerjoin(WorkOrder.service_type).outerjoin(WorkOrder.technician)

        if is_technician:
            matching_workorders_query = matching_workorders_query.filter(WorkOrder.technician_id == current_user.id)

        matching_workorders = matching_workorders_query.filter(
            or_(
                Client.name.ilike(search_term),
                Equipment.name.ilike(search_term),
                Equipment.location.ilike(search_term),
                Equipment.serial_number.ilike(search_term),
                ServiceCatalog.name.ilike(search_term),
                User.name.ilike(search_term),
                WorkOrder.description.ilike(search_term),
            )
        ).all()
        filtered_client_ids = sorted({workorder.client_id for workorder in matching_workorders if workorder.client_id})
    
    if is_technician:
        # Técnico vê apenas seus próprios serviços
        tech_os_query = db.session.query(
            WorkOrder.client_id,
            func.max(WorkOrder.created_at).label('latest_os')
        ).filter(
            WorkOrder.technician_id == current_user.id
        ).group_by(WorkOrder.client_id).subquery()
        
        clients_query = Client.query.join(
            tech_os_query, Client.id == tech_os_query.c.client_id
        )
        if filtered_client_ids is not None:
            if filtered_client_ids:
                clients_query = clients_query.filter(Client.id.in_(filtered_client_ids))
            else:
                clients_query = clients_query.filter(Client.id == None)
        clients_pagination = clients_query.order_by(tech_os_query.c.latest_os.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
    else:
        # Admin e Secretary veem todos os serviços
        # Subquery to get the latest OS date for each client
        latest_os_subquery = db.session.query(
            WorkOrder.client_id,
            func.max(WorkOrder.created_at).label('latest_os')
        ).group_by(WorkOrder.client_id).subquery()

        # Query clients who have OS, ordered by their latest OS date
        clients_query = Client.query.join(
            latest_os_subquery, Client.id == latest_os_subquery.c.client_id
        )
        if filtered_client_ids is not None:
            if filtered_client_ids:
                clients_query = clients_query.filter(Client.id.in_(filtered_client_ids))
            else:
                clients_query = clients_query.filter(Client.id == None)
        clients_pagination = clients_query.order_by(latest_os_subquery.c.latest_os.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
    
    # Para cada cliente, pegar apenas os últimos 5 OS
    clients_with_os = []
    for client in clients_pagination.items:
        if is_technician:
            recent_os_query = WorkOrder.query.filter(
                WorkOrder.client_id == client.id,
                WorkOrder.technician_id == current_user.id
            )
            if search:
                search_term = f'%{search}%'
                recent_os_query = recent_os_query.outerjoin(WorkOrder.equipment).outerjoin(WorkOrder.service_type).outerjoin(WorkOrder.technician).filter(
                    or_(
                        Equipment.name.ilike(search_term),
                        Equipment.location.ilike(search_term),
                        Equipment.serial_number.ilike(search_term),
                        ServiceCatalog.name.ilike(search_term),
                        User.name.ilike(search_term),
                        WorkOrder.description.ilike(search_term),
                    )
                )

            recent_os = recent_os_query.order_by(
                WorkOrder.created_at.desc()
            ).limit(5).all()
            
            total_os_query = WorkOrder.query.filter(
                WorkOrder.client_id == client.id,
                WorkOrder.technician_id == current_user.id
            )
            if search:
                search_term = f'%{search}%'
                total_os_query = total_os_query.outerjoin(WorkOrder.equipment).outerjoin(WorkOrder.service_type).outerjoin(WorkOrder.technician).filter(
                    or_(
                        Equipment.name.ilike(search_term),
                        Equipment.location.ilike(search_term),
                        Equipment.serial_number.ilike(search_term),
                        ServiceCatalog.name.ilike(search_term),
                        User.name.ilike(search_term),
                        WorkOrder.description.ilike(search_term),
                    )
                )
            total_os = total_os_query.count()
        else:
            recent_os_query = WorkOrder.query.filter_by(client_id=client.id)
            if search:
                search_term = f'%{search}%'
                recent_os_query = recent_os_query.outerjoin(WorkOrder.equipment).outerjoin(WorkOrder.service_type).outerjoin(WorkOrder.technician).filter(
                    or_(
                        Equipment.name.ilike(search_term),
                        Equipment.location.ilike(search_term),
                        Equipment.serial_number.ilike(search_term),
                        ServiceCatalog.name.ilike(search_term),
                        User.name.ilike(search_term),
                        WorkOrder.description.ilike(search_term),
                    )
                )

            recent_os = recent_os_query.order_by(
                WorkOrder.created_at.desc()
            ).limit(5).all()
            
            total_os_query = WorkOrder.query.filter_by(client_id=client.id)
            if search:
                search_term = f'%{search}%'
                total_os_query = total_os_query.outerjoin(WorkOrder.equipment).outerjoin(WorkOrder.service_type).outerjoin(WorkOrder.technician).filter(
                    or_(
                        Equipment.name.ilike(search_term),
                        Equipment.location.ilike(search_term),
                        Equipment.serial_number.ilike(search_term),
                        ServiceCatalog.name.ilike(search_term),
                        User.name.ilike(search_term),
                        WorkOrder.description.ilike(search_term),
                    )
                )
            total_os = total_os_query.count()

        if search and not recent_os:
            continue
        
        clients_with_os.append({
            'client': client,
            'recent_os': recent_os,
            'total_os': total_os,
            'has_more': total_os > 5
        })
    
    return render_template(
        'services/index.html',
        clients_with_os=clients_with_os,
        search=search,
        pagination=clients_pagination,
        per_page=per_page,
    )

@services_bp.route('/add', methods=['GET', 'POST'])
@roles_required('admin', 'secretary')
def add():
    clients = Client.query.all()
    equipments = Equipment.query.all()
    services = ServiceCatalog.query.all()
    service_catalog_items = [serialize_service_catalog(service) for service in services]
    technicians = User.query.filter_by(role='technician', is_active=True).all()

    if request.method == 'POST':
        client_id = request.form.get('client_id')
        equipment_id = request.form.get('equipment_id') or None
        service_id = request.form.get('service_id')
        technician_id = request.form.get('technician_id') or None

        if not service_id:
            flash('Selecione um tipo de serviço válido.', 'danger')
            return redirect(url_for('services.add'))

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
            photo_before_path = save_and_resize_image(photo_before_file, 'work_orders')
            
        if photo_after_file and photo_after_file.filename:
            photo_after_path = save_and_resize_image(photo_after_file, 'work_orders')

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

    return render_template('services/add.html', clients=clients, equipments=equipments, services=services, service_catalog_items=service_catalog_items, technicians=technicians)
@services_bp.route('/edit/<int:id>', methods=['GET', 'POST'])
@roles_required('admin', 'secretary', 'technician')
def edit(id):
    current_user = get_current_user()
    prompt_receipt_requested = request.method == 'GET' and request.args.get('prompt_receipt', type=int) == 1
    return_to = normalize_return_to(request.values.get('return_to')) or request.referrer or url_for('services.index')
    
    wo = WorkOrder.query.get_or_404(id)
    is_admin = current_user and current_user.permission_level == 'admin'
    is_completed_locked = wo.status == 'Completed' and not is_admin
    
    # Verificar se técnico tem acesso a este serviço
    is_technician = current_user and current_user.permission_level == 'user'
    if is_technician:
        if wo.technician_id != current_user.id:
            flash('Você não tem permissão para editar este serviço.', 'danger')
            return redirect(url_for('services.index'))

    clients = Client.query.all()
    equipments = Equipment.query.all()
    services = ServiceCatalog.query.all()
    technicians = User.query.filter_by(role='technician', is_active=True).all()

    if request.method == 'POST':
        if wo.status == 'Completed' and not is_admin:
            flash('Apenas administradores podem alterar uma OS já concluída.', 'danger')
            return redirect(return_to or url_for('services.index'))

        old_values = {
            'status': wo.status,
            'description': wo.description,
            'total_value': wo.total_value,
            'scheduled_date': wo.scheduled_date.isoformat() if wo.scheduled_date else None,
            'technician_id': wo.technician_id,
        }
        previous_status = wo.status

        # Technician can only edit status, description and photos? 
        # For now, let's allow all fields for both, but focus on photos and status.
        wo.status = request.form.get('status')
        wo.description = request.form.get('description')
        raw_total_value = request.form.get('total_value')
        
        try:
            wo.total_value = round(float(raw_total_value), 2) if raw_total_value else 0.0
        except ValueError:
            pass

        if wo.status == 'Completed' and previous_status != 'Completed':
            wo.completed_date = datetime.utcnow()
        elif wo.status != 'Completed' and previous_status == 'Completed':
            wo.completed_date = None

        scheduled_date_str = request.form.get('scheduled_date')
        if scheduled_date_str:
            wo.scheduled_date = datetime.strptime(scheduled_date_str, '%Y-%m-%dT%H:%M')

        # --- Handle Image Uploads ---
        photo_before_file = request.files.get('photo_before')
        photo_after_file = request.files.get('photo_after')
        
        if photo_before_file and photo_before_file.filename:
            wo.photo_before = save_and_resize_image(photo_before_file, 'work_orders')
            
        if photo_after_file and photo_after_file.filename:
            wo.photo_after = save_and_resize_image(photo_after_file, 'work_orders')

        sync_schedule_with_workorder(wo, previous_status=previous_status)

        db.session.commit()
        log_action(
            action='UPDATE',
            resource_type='WorkOrder',
            resource_id=wo.id,
            resource_name=f'WO-{wo.id}',
            details={
                'old_values': old_values,
                'new_values': {
                    'status': wo.status,
                    'description': wo.description,
                    'total_value': wo.total_value,
                    'scheduled_date': wo.scheduled_date.isoformat() if wo.scheduled_date else None,
                    'technician_id': wo.technician_id,
                }
            }
        )
        flash(f'Ordem de Serviço #{id} atualizada com sucesso!', 'success')

        if previous_status != 'Completed' and wo.status == 'Completed':
            return redirect(url_for('services.edit', id=id, prompt_receipt=1, return_to=return_to))

        return redirect(url_for('services.index'))

    return render_template(
        'services/edit.html',
        wo=wo,
        clients=clients,
        equipments=equipments,
        services=services,
        technicians=technicians,
        prompt_receipt=prompt_receipt_requested and wo.status == 'Completed',
        return_to=return_to,
        is_completed_locked=is_completed_locked
    )

@services_bp.route('/history')
@roles_required('admin', 'secretary', 'technician')
def history():
    """Visualizar histórico completo de ordens de serviço com paginação"""
    current_user = get_current_user()
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 5, type=int)
    
    # Validar per_page
    if per_page not in [5, 10, 20, 50]:
        per_page = 5
    
    # Filtros opcionais
    client_id = request.args.get('client_id', type=int)
    equipment_id = request.args.get('equipment_id', type=int)
    status = request.args.get('status', type=str)
    
    # Check if user is technician
    is_technician = current_user and current_user.permission_level == 'user'
    technician_client_ids = []
    
    query = WorkOrder.query
    
    # Técnico vê apenas seus próprios serviços
    if is_technician:
        query = query.filter_by(technician_id=current_user.id)
        technician_client_ids = get_technician_client_ids(current_user.id)
    
    if client_id:
        query = query.filter_by(client_id=client_id)

    available_equipments = []
    if client_id:
        if not is_technician or client_id in technician_client_ids:
            available_equipments = Equipment.query.filter_by(client_id=client_id).order_by(Equipment.name.asc()).all()

    selected_equipment = None
    if equipment_id:
        selected_equipment = Equipment.query.get(equipment_id)
        if not selected_equipment:
            equipment_id = None
        elif client_id and selected_equipment.client_id != client_id:
            equipment_id = None
            selected_equipment = None
        elif is_technician and selected_equipment.client_id not in technician_client_ids:
            equipment_id = None
            selected_equipment = None

    if equipment_id:
        query = query.filter_by(equipment_id=equipment_id)
    if status:
        query = query.filter_by(status=status)
    
    pagination = query.order_by(WorkOrder.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Técnico vê apenas clientes que atendeu
    if is_technician:
        if technician_client_ids:
            clients = Client.query.filter(Client.id.in_(technician_client_ids)).all()
        else:
            clients = []
    else:
        clients = Client.query.all()
    
    return render_template('services/history.html', 
                         pagination=pagination, 
                         per_page=per_page,
                         clients=clients,
                         available_equipments=available_equipments,
                         selected_client_id=client_id,
                         selected_equipment_id=equipment_id,
                         selected_equipment=selected_equipment,
                         selected_status=status)

@services_bp.route('/export-pdf')
@roles_required('admin', 'secretary', 'technician')
def export_pdf():
    """Gerar relatório em PDF das ordens de serviço"""
    current_user = get_current_user()
    
    client_id = request.args.get('client_id', type=int)
    equipment_id = request.args.get('equipment_id', type=int)
    status = request.args.get('status', type=str)
    
    # Check if user is technician
    is_technician = current_user and current_user.permission_level == 'user'
    technician_client_ids = []
    
    # Construir query
    query = WorkOrder.query
    
    # Técnico vê apenas seus próprios serviços
    if is_technician:
        query = query.filter_by(technician_id=current_user.id)
        technician_client_ids = get_technician_client_ids(current_user.id)
    
    if client_id:
        query = query.filter_by(client_id=client_id)

    if equipment_id:
        selected_equipment = Equipment.query.get(equipment_id)
        if selected_equipment and (not client_id or selected_equipment.client_id == client_id):
            if not is_technician or selected_equipment.client_id in technician_client_ids:
                query = query.filter_by(equipment_id=equipment_id)
    if status:
        query = query.filter_by(status=status)
    
    work_orders = query.order_by(WorkOrder.created_at.desc()).all()
    
    # Criar PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, 
                           topMargin=0.5*inch, bottomMargin=0.5*inch,
                           leftMargin=0.75*inch, rightMargin=0.75*inch)
    
    elements = []
    styles = getSampleStyleSheet()
    
    # Estilo personalizado
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#3b82f6'),
        spaceAfter=6,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    # Cabeçalho com logo
    config = AppConfig.query.first()
    header_data = []
    
    if config and config.logo_path:
        try:
            # Tentar adicionar a logo
            img = Image(current_app.static_folder + config.logo_path.replace('/static', ''), 
                       width=1*inch, height=1*inch)
            header_data.append([img, Paragraph(f"<b>{config.company_name or 'Pronto Ar Refrigeração'}</b><br/>Relatório de Ordens de Serviço", title_style)])
        except:
            header_data.append([Paragraph(f"<b>{config.company_name or 'Pronto Ar Refrigeração'}</b><br/>Relatório de Ordens de Serviço", title_style)])
    else:
        header_data.append([Paragraph("<b>Pronto Ar Refrigeração</b><br/>Relatório de Ordens de Serviço", title_style)])
    
    header_table = Table(header_data, colWidths=[1.5*inch, 5.5*inch])
    header_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Data do relatório
    elements.append(Paragraph(f"<b>Data:</b> {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles['Normal']))
    elements.append(Spacer(1, 0.2*inch))

    section_title_style = ParagraphStyle(
        'SectionTitle',
        parent=styles['Heading2'],
        fontSize=13,
        textColor=colors.HexColor('#111827'),
        spaceAfter=6,
        spaceBefore=6,
        fontName='Helvetica-Bold'
    )

    summary_style = ParagraphStyle(
        'Summary',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#374151'),
        leading=12,
    )

    table_header_style = ParagraphStyle(
        'PdfTableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=9,
        alignment=TA_CENTER,
        textColor=colors.whitesmoke,
    )

    table_cell_style = ParagraphStyle(
        'PdfTableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7,
        leading=8,
        alignment=TA_LEFT,
        wordWrap='CJK',
        textColor=colors.HexColor('#111827'),
    )

    table_cell_center_style = ParagraphStyle(
        'PdfTableCellCenter',
        parent=table_cell_style,
        alignment=TA_CENTER,
    )
    
    # Tabelas agrupadas por cliente
    if work_orders:
        grouped_work_orders = {}
        for wo in work_orders:
            client_name = wo.client.name if wo.client else 'Cliente não identificado'
            grouped_work_orders.setdefault(client_name, []).append(wo)

        ordered_clients = sorted(
            grouped_work_orders.items(),
            key=lambda item: item[1][0].created_at if item[1] else datetime.min,
            reverse=True,
        )

        for index, (client_name, client_work_orders) in enumerate(ordered_clients):
            elements.append(Paragraph(client_name, section_title_style))

            data = [[
                Paragraph('ID', table_header_style),
                Paragraph('Equipamento', table_header_style),
                Paragraph('Série', table_header_style),
                Paragraph('Tipo/Serviço', table_header_style),
                Paragraph('Status', table_header_style),
                Paragraph('Data', table_header_style),
                Paragraph('Valor', table_header_style),
            ]]
            total_value = 0.0

            for wo in client_work_orders:
                total_value += wo.total_value or 0.0
                equipment_name = wo.equipment.name if wo.equipment else 'Genérico'
                serial_number = wo.equipment.serial_number if wo.equipment and wo.equipment.serial_number else '-'
                service_name = wo.service_type.name if wo.service_type else '-'
                status_label = get_status_label(wo.status)
                data.append([
                    Paragraph(str(wo.id), table_cell_center_style),
                    Paragraph(escape(equipment_name), table_cell_style),
                    Paragraph(escape(serial_number), table_cell_style),
                    Paragraph(escape(service_name), table_cell_style),
                    Paragraph(escape(status_label), table_cell_center_style),
                    Paragraph(wo.created_at.strftime('%d/%m/%Y'), table_cell_center_style),
                    Paragraph(f'R$ {wo.total_value:.2f}', table_cell_center_style),
                ])

            table = Table(
                data,
                colWidths=[0.4*inch, 1.35*inch, 0.85*inch, 1.2*inch, 0.9*inch, 0.75*inch, 0.7*inch],
                repeatRows=1
            )
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3b82f6')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 7),
                ('TOPPADDING', (0, 0), (-1, 0), 7),
                ('GRID', (0, 0), (-1, -1), 0.75, colors.HexColor('#9ca3af')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9fafb')]),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 1), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
                ('ALIGN', (1, 1), (3, -1), 'LEFT'),
            ]))
            elements.append(table)
            elements.append(Spacer(1, 0.12*inch))
            elements.append(Paragraph(
                f"<b>Subtotal do cliente:</b> {len(client_work_orders)} serviços realizados | <b>Total em OS:</b> R$ {total_value:.2f}",
                summary_style,
            ))

            if index < len(ordered_clients) - 1:
                elements.append(Spacer(1, 0.2*inch))
    else:
        elements.append(Paragraph("<i>Nenhuma ordem de serviço encontrada</i>", styles['Normal']))
    
    elements.append(Spacer(1, 0.5*inch))
    elements.append(Paragraph(f"_" * 80, styles['Normal']))
    elements.append(Paragraph("Documento gerado automaticamente pelo sistema Pronto Ar", 
                            ParagraphStyle('footer', parent=styles['Normal'], fontSize=8, 
                                         textColor=colors.grey)))
    
    doc.build(elements)
    buffer.seek(0)
    
    # Gerar nome do arquivo com empresa e data
    empresa_nome = 'completo'
    if client_id:
        cliente = Client.query.get(client_id)
        if cliente:
            # Limpar nome da empresa para usar em filename
            empresa_nome = cliente.name.lower().replace(' ', '_')
    
    data_formatada = datetime.now().strftime("%d%m%Y")
    filename = f'relatorio_{empresa_nome}_{data_formatada}.pdf'
    
    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )
