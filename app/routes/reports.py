from flask import Blueprint, render_template, request, flash, redirect, url_for
from app.utils.decorators import license_feature_required, roles_required
from app.models.workorder import WorkOrder
from app.models.client import Client
from app.models.service import ServiceCatalog
from app import db
from sqlalchemy import func
from datetime import datetime, time

reports_bp = Blueprint('reports', __name__)


def format_date_br(value):
    if not value:
        return '-'
    if isinstance(value, str):
        try:
            value = datetime.strptime(value, '%Y-%m-%d')
        except ValueError:
            return value
    return value.strftime('%d/%m/%Y')


def build_period_label(start_str, end_str):
    return f'{format_date_br(start_str)} a {format_date_br(end_str)}'

@reports_bp.route('/')
@reports_bp.route('/index')
@roles_required('admin')
@license_feature_required('reports')
def index():
    return render_template('reports/index.html')

def get_date_range():
    start_str = request.args.get('start_date')
    end_str = request.args.get('end_date')
    
    start_date = None
    end_date = None
    
    if start_str and end_str:
        try:
            start_date = datetime.combine(datetime.strptime(start_str, '%Y-%m-%d'), time.min)
            end_date = datetime.combine(datetime.strptime(end_str, '%Y-%m-%d'), time.max)
        except ValueError:
            pass
            
    return start_date, end_date, start_str, end_str

@reports_bp.route('/finance')
@roles_required('admin')
@license_feature_required('reports')
def finance():
    start_date, end_date, start_str, end_str = get_date_range()
    
    if not start_date or not end_date:
        flash("Período inválido.", "warning")
        return redirect(url_for('reports.index'))
        
    query = WorkOrder.query.filter(WorkOrder.created_at >= start_date, WorkOrder.created_at <= end_date)
    orders = query.all()
    
    total_revenue = sum(o.total_value for o in orders)
    total_paid = sum(o.paid_value for o in orders)
    total_pending = sum(o.total_value - o.paid_value for o in orders if not o.is_paid)
    total_orders = len(orders)
    paid_orders = sum(1 for o in orders if o.is_paid)
    average_ticket = (total_revenue / total_orders) if total_orders else 0.0
    received_rate = ((total_paid / total_revenue) * 100) if total_revenue else 0.0
    
    return render_template('reports/finance.html', 
                           orders=orders, 
                           total_revenue=total_revenue, 
                           total_paid=total_paid, 
                           total_pending=total_pending,
                           total_orders=total_orders,
                           paid_orders=paid_orders,
                           average_ticket=average_ticket,
                           received_rate=received_rate,
                           start_str=start_str,
                           end_str=end_str,
                           period_label=build_period_label(start_str, end_str),
                           generated_at_label=format_date_br(datetime.utcnow()))

@reports_bp.route('/clients')
@roles_required('admin')
@license_feature_required('reports')
def clients():
    start_date, end_date, start_str, end_str = get_date_range()
    
    if not start_date or not end_date:
        flash("Período inválido.", "warning")
        return redirect(url_for('reports.index'))
        
    client_stats = db.session.query(
        Client.name,
        func.count(WorkOrder.id).label('os_count'),
        func.sum(WorkOrder.total_value).label('total_spent')
    ).join(WorkOrder, Client.id == WorkOrder.client_id) \
     .filter(WorkOrder.created_at >= start_date, WorkOrder.created_at <= end_date) \
     .group_by(Client.id) \
     .order_by(func.sum(WorkOrder.total_value).desc()).all()
     
    new_clients_count = Client.query.filter(Client.created_at >= start_date, Client.created_at <= end_date).count()
    total_active_clients = len(client_stats)
    total_generated = sum((row.total_spent or 0) for row in client_stats)
    top_client = client_stats[0] if client_stats else None
     
    return render_template('reports/clients.html',
                           client_stats=client_stats,
                           new_clients_count=new_clients_count,
                           total_active_clients=total_active_clients,
                           total_generated=total_generated,
                           top_client=top_client,
                           start_str=start_str,
                           end_str=end_str,
                           period_label=build_period_label(start_str, end_str),
                           generated_at_label=format_date_br(datetime.utcnow()))

@reports_bp.route('/services')
@roles_required('admin')
@license_feature_required('reports')
def services():
    start_date, end_date, start_str, end_str = get_date_range()
    
    if not start_date or not end_date:
        flash("Período inválido.", "warning")
        return redirect(url_for('reports.index'))
        
    service_stats = db.session.query(
        ServiceCatalog.name,
        func.count(WorkOrder.id).label('os_count'),
        func.sum(WorkOrder.total_value).label('total_generated')
    ).join(WorkOrder, ServiceCatalog.id == WorkOrder.service_id) \
     .filter(WorkOrder.created_at >= start_date, WorkOrder.created_at <= end_date) \
     .group_by(ServiceCatalog.id) \
     .order_by(func.count(WorkOrder.id).desc()).all()
    total_categories = len(service_stats)
    total_executions = sum((row.os_count or 0) for row in service_stats)
    total_generated = sum((row.total_generated or 0) for row in service_stats)
    top_service = service_stats[0] if service_stats else None
     
    return render_template('reports/services.html',
                           service_stats=service_stats,
                           total_categories=total_categories,
                           total_executions=total_executions,
                           total_generated=total_generated,
                           top_service=top_service,
                           start_str=start_str,
                           end_str=end_str,
                           period_label=build_period_label(start_str, end_str),
                           generated_at_label=format_date_br(datetime.utcnow()))
