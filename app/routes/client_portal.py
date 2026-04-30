from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models.user import User
from app.models.client import Client
from app.models.equipment import Equipment
from app.models.workorder import WorkOrder
from app.utils.decorators import roles_required
from app import db
from datetime import datetime

client_portal_bp = Blueprint('client_portal', __name__, url_prefix='/client')

@client_portal_bp.route('/dashboard')
@roles_required('client')
def dashboard():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    
    # Check both legacy and many-to-many
    user_clients = user.clients
    if not user_clients and user.client_id:
        # Auto-migration fallback for this session if not yet migrated
        legacy_client = Client.query.get(user.client_id)
        if legacy_client:
            user_clients = [legacy_client]

    if not user_clients:
        flash('Usuário sem cliente vinculado. Contate o administrador.', 'danger')
        return redirect(url_for('auth.login'))
    
    # Select which client to view
    client_id = request.args.get('client_id', type=int)
    client = None
    if client_id:
        client = next((c for c in user_clients if c.id == client_id), None)
    
    if not client:
        client = user_clients[0]
    
    # Metrics
    equipments_count = len(client.equipments)
    work_orders = WorkOrder.query.filter_by(client_id=client.id).order_by(WorkOrder.created_at.desc()).all()
    total_spent = sum(wo.total_value for wo in work_orders if wo.status == 'Completed')
    pending_payments = sum(wo.total_value - (wo.paid_value or 0) for wo in work_orders if not wo.is_paid and wo.status != 'Cancelled')
    
    recent_os = work_orders[:5]
    
    # Busca administradores para contato
    admins = User.query.filter_by(permission_level='admin', is_active=True).all()
    
    return render_template('client_portal/dashboard.html', 
                           client=client, 
                           all_clients=user_clients if len(user_clients) > 1 else None,
                           equipments_count=equipments_count,
                           total_spent=total_spent,
                           pending_payments=pending_payments,
                           recent_os=recent_os,
                           admins=admins)

@client_portal_bp.route('/equipments')
@roles_required('client')
def equipments():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    
    client_id = request.args.get('client_id', type=int)
    user_clients = user.clients
    client = next((c for c in user_clients if c.id == client_id), None) if client_id else (user_clients[0] if user_clients else None)
    
    if not client and user.client_id:
        client = Client.query.get(user.client_id)

    if not client:
        flash('Cliente não encontrado.', 'danger')
        return redirect(url_for('client_portal.dashboard'))
    
    return render_template('client_portal/equipments.html', client=client, equipments=client.equipments)

@client_portal_bp.route('/services')
@roles_required('client')
def services():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    
    client_id = request.args.get('client_id', type=int)
    user_clients = user.clients
    client = next((c for c in user_clients if c.id == client_id), None) if client_id else (user_clients[0] if user_clients else None)
    
    if not client and user.client_id:
        client = Client.query.get(user.client_id)

    if not client:
        flash('Cliente não encontrado.', 'danger')
        return redirect(url_for('client_portal.dashboard'))
    
    work_orders = WorkOrder.query.filter_by(client_id=client.id).order_by(WorkOrder.created_at.desc()).all()
    
    return render_template('client_portal/services.html', client=client, work_orders=work_orders)

@client_portal_bp.route('/payments')
@roles_required('client')
def payments():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    
    client_id = request.args.get('client_id', type=int)
    user_clients = user.clients
    client = next((c for c in user_clients if c.id == client_id), None) if client_id else (user_clients[0] if user_clients else None)
    
    if not client and user.client_id:
        client = Client.query.get(user.client_id)

    if not client:
        flash('Cliente não encontrado.', 'danger')
        return redirect(url_for('client_portal.dashboard'))
    
    # Pagamentos são baseados nas O.S. concluídas ou com valores lançados
    work_orders = WorkOrder.query.filter_by(client_id=client.id).filter(WorkOrder.total_value > 0).order_by(WorkOrder.created_at.desc()).all()
    
    return render_template('client_portal/payments.html', client=client, work_orders=work_orders)

@client_portal_bp.route('/service/<int:id>')
@roles_required('client')
def service_details(id):
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    
    # We need to find which client this OS belongs to and if the user has access to it
    os = WorkOrder.query.get_or_404(id)
    
    user_clients_ids = [c.id for c in user.clients]
    if user.client_id and user.client_id not in user_clients_ids:
        user_clients_ids.append(user.client_id)
        
    if os.client_id not in user_clients_ids:
        flash('Você não tem permissão para visualizar esta ordem de serviço.', 'danger')
        return redirect(url_for('client_portal.dashboard'))
    
    client = Client.query.get(os.client_id)
    
    return render_template('client_portal/service_details.html', client=client, os=os)
