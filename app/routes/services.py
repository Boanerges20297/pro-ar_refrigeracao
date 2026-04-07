from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, current_app
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
import io
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

services_bp = Blueprint('services', __name__)

from sqlalchemy import func

@services_bp.route('/')
@roles_required('admin', 'secretary', 'technician')
def index():
    """Mostrar ordens de serviço agrupadas por cliente com os últimos 5 de cada"""
    # Get current user
    current_user_id = get_jwt_identity()
    current_user = User.query.get(current_user_id) if current_user_id else None
    
    # Check if user is technician
    is_technician = current_user and current_user.permission_level == 'user'
    
    if is_technician:
        # Técnico vê apenas seus próprios serviços
        tech_os_query = db.session.query(
            WorkOrder.client_id,
            func.max(WorkOrder.created_at).label('latest_os')
        ).filter(
            WorkOrder.technician_id == current_user.id
        ).group_by(WorkOrder.client_id).subquery()
        
        clients = Client.query.join(
            tech_os_query, Client.id == tech_os_query.c.client_id
        ).order_by(tech_os_query.c.latest_os.desc()).all()
    else:
        # Admin e Secretary veem todos os serviços
        # Subquery to get the latest OS date for each client
        latest_os_subquery = db.session.query(
            WorkOrder.client_id,
            func.max(WorkOrder.created_at).label('latest_os')
        ).group_by(WorkOrder.client_id).subquery()

        # Query clients who have OS, ordered by their latest OS date
        clients = Client.query.join(
            latest_os_subquery, Client.id == latest_os_subquery.c.client_id
        ).order_by(latest_os_subquery.c.latest_os.desc()).all()
    
    # Para cada cliente, pegar apenas os últimos 5 OS
    clients_with_os = []
    for client in clients:
        if is_technician:
            recent_os = WorkOrder.query.filter(
                WorkOrder.client_id == client.id,
                WorkOrder.technician_id == current_user.id
            ).order_by(
                WorkOrder.created_at.desc()
            ).limit(5).all()
            
            total_os = WorkOrder.query.filter(
                WorkOrder.client_id == client.id,
                WorkOrder.technician_id == current_user.id
            ).count()
        else:
            recent_os = WorkOrder.query.filter_by(client_id=client.id).order_by(
                WorkOrder.created_at.desc()
            ).limit(5).all()
            
            total_os = WorkOrder.query.filter_by(client_id=client.id).count()
        
        clients_with_os.append({
            'client': client,
            'recent_os': recent_os,
            'total_os': total_os,
            'has_more': total_os > 5
        })
    
    return render_template('services/index.html', clients_with_os=clients_with_os)

@services_bp.route('/add', methods=['GET', 'POST'])
@roles_required('admin', 'secretary')
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
@roles_required('admin', 'secretary', 'technician')
def edit(id):
    # Get current user
    current_user_id = get_jwt_identity()
    current_user = User.query.get(current_user_id) if current_user_id else None
    
    wo = WorkOrder.query.get_or_404(id)
    
    # Verificar se técnico tem acesso a este serviço
    is_technician = current_user and current_user.permission_level == 'user'
    if is_technician:
        if wo.technician_id != current_user.id:
            flash('Você não tem permissão para editar este serviço.', 'danger')
            return redirect(url_for('services.index'))
        
        # Bloquear edição se o serviço for marcado como Concluído
        if wo.status == 'Completed':
            flash('Não é possível editar um serviço já concluído.', 'danger')
            return redirect(url_for('services.index'))
    
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

@services_bp.route('/history')
@roles_required('admin', 'secretary', 'technician')
def history():
    """Visualizar histórico completo de ordens de serviço com paginação"""
    # Get current user
    current_user_id = get_jwt_identity()
    current_user = User.query.get(current_user_id) if current_user_id else None
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    
    # Validar per_page
    if per_page not in [10, 20, 50]:
        per_page = 10
    
    # Filtros opcionais
    client_id = request.args.get('client_id', type=int)
    status = request.args.get('status', type=str)
    
    # Check if user is technician
    is_technician = current_user and current_user.permission_level == 'user'
    
    query = WorkOrder.query
    
    # Técnico vê apenas seus próprios serviços
    if is_technician:
        query = query.filter_by(technician_id=current_user.id)
    
    if client_id:
        query = query.filter_by(client_id=client_id)
    if status:
        query = query.filter_by(status=status)
    
    pagination = query.order_by(WorkOrder.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Técnico vê apenas clientes que atendeu
    if is_technician:
        client_ids = get_technician_client_ids(current_user.id)
        if client_ids:
            clients = Client.query.filter(Client.id.in_(client_ids)).all()
        else:
            clients = []
    else:
        clients = Client.query.all()
    
    return render_template('services/history.html', 
                         pagination=pagination, 
                         per_page=per_page,
                         clients=clients,
                         selected_client_id=client_id,
                         selected_status=status)

@services_bp.route('/export-pdf')
@roles_required('admin', 'secretary', 'technician')
def export_pdf():
    """Gerar relatório em PDF das ordens de serviço"""
    # Get current user
    current_user_id = get_jwt_identity()
    current_user = User.query.get(current_user_id) if current_user_id else None
    
    # Mapeamento de status para português
    status_translations = {
        'Completed': 'Concluída',
        'Pending': 'Pendente',
        'In Progress': 'Em Andamento'
    }
    
    client_id = request.args.get('client_id', type=int)
    status = request.args.get('status', type=str)
    
    # Check if user is technician
    is_technician = current_user and current_user.permission_level == 'user'
    
    # Construir query
    query = WorkOrder.query
    
    # Técnico vê apenas seus próprios serviços
    if is_technician:
        query = query.filter_by(technician_id=current_user.id)
    
    if client_id:
        query = query.filter_by(client_id=client_id)
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
    
    # Tabela de dados
    if work_orders:
        data = [['ID', 'Cliente', 'Equipamento', 'Status', 'Data', 'Valor']]
        
        for wo in work_orders:
            # Traduzir status
            status_pt = status_translations.get(wo.status, wo.status)
            data.append([
                str(wo.id),
                wo.client.name if wo.client else '-',
                wo.equipment.name if wo.equipment else 'Genérico',
                status_pt,
                wo.created_at.strftime('%d/%m/%Y'),
                f'R$ {wo.total_value:.2f}'
            ])
        
        table = Table(data, colWidths=[0.6*inch, 1.8*inch, 1.8*inch, 1.2*inch, 1.0*inch, 1.0*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3b82f6')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f3f4f6')]),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
        ]))
        elements.append(table)
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
