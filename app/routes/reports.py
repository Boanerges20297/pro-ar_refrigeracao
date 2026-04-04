from flask import Blueprint, render_template, request, flash, redirect, url_for
from app.utils.decorators import roles_required
from app.models.workorder import WorkOrder
from app.models.client import Client
from app.models.service import ServiceCatalog
from app import db
from sqlalchemy import func
from datetime import datetime, time

reports_bp = Blueprint('reports', __name__)

@reports_bp.route('/')
@reports_bp.route('/index')
@roles_required('admin')
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
    
    return render_template('reports/finance.html', 
                           orders=orders, 
                           total_revenue=total_revenue, 
                           total_paid=total_paid, 
                           total_pending=total_pending,
                           start_str=start_str,
                           end_str=end_str)

@reports_bp.route('/clients')
@roles_required('admin')
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
     
    return render_template('reports/clients.html',
                           client_stats=client_stats,
                           new_clients_count=new_clients_count,
                           start_str=start_str,
                           end_str=end_str)

@reports_bp.route('/services')
@roles_required('admin')
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
     
    return render_template('reports/services.html',
                           service_stats=service_stats,
                           start_str=start_str,
                           end_str=end_str)
