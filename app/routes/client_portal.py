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
    if not user.client_id:
        flash('Usuário sem cliente vinculado. Contate o administrador.', 'danger')
        return redirect(url_for('auth.login'))
    
    client = Client.query.get(user.client_id)
    
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
    client = Client.query.get(user.client_id)
    
    return render_template('client_portal/equipments.html', client=client, equipments=client.equipments)

@client_portal_bp.route('/services')
@roles_required('client')
def services():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    client = Client.query.get(user.client_id)
    
    work_orders = WorkOrder.query.filter_by(client_id=client.id).order_by(WorkOrder.created_at.desc()).all()
    
    return render_template('client_portal/services.html', client=client, work_orders=work_orders)

@client_portal_bp.route('/payments')
@roles_required('client')
def payments():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    client = Client.query.get(user.client_id)
    
    # Pagamentos são baseados nas O.S. concluídas ou com valores lançados
    work_orders = WorkOrder.query.filter_by(client_id=client.id).filter(WorkOrder.total_value > 0).order_by(WorkOrder.created_at.desc()).all()
    
    return render_template('client_portal/payments.html', client=client, work_orders=work_orders)

@client_portal_bp.route('/service/<int:id>')
@roles_required('client')
def service_details(id):
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    client = Client.query.get(user.client_id)
    
    # Busca a OS garantindo que pertença a este cliente
    os = WorkOrder.query.filter_by(id=id, client_id=client.id).first_or_404()
    
    return render_template('client_portal/service_details.html', client=client, os=os)
