from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_jwt_extended import get_jwt_identity
from app.utils.decorators import roles_required, permission_level_required
from app.utils.audit import log_action
from app.models.user import User
from app.models.workorder import WorkOrder
from app.models.maintenance import MaintenanceSchedule
from app.models.client import Client
from app.models.equipment import Equipment
from app.models.config import AppConfig
from app import db
from sqlalchemy import func
from datetime import datetime, timedelta

secretary_bp = Blueprint('secretary', __name__)

@secretary_bp.route('/dashboard')
@roles_required('secretary', 'admin')
def dashboard():
    """Dashboard da Secretária com acesso limitado"""
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)

    # Métricas gerais (sem valores financeiros)
    total_clients = Client.query.count()
    total_equipment = Equipment.query.count()
    total_os = WorkOrder.query.count()
    pending_os = WorkOrder.query.filter_by(status='Pending').count()

    # Alertas
    today = datetime.utcnow().date()
    tomorrow = today + timedelta(days=1)
    in_7_days = today + timedelta(days=7)
    
    # Serviços para hoje
    services_today = WorkOrder.query.filter(
        WorkOrder.scheduled_date >= datetime.combine(today, datetime.min.time()),
        WorkOrder.scheduled_date < datetime.combine(tomorrow, datetime.min.time()),
        WorkOrder.status.in_(['Pending', 'In Progress'])
    ).all()
    
    # Serviços atrasados
    overdue_services = WorkOrder.query.filter(
        WorkOrder.scheduled_date < datetime.combine(today, datetime.min.time()),
        WorkOrder.status.in_(['Pending', 'In Progress'])
    ).all()
    
    # Manutenção atrasada
    overdue_maintenance = MaintenanceSchedule.query.filter(
        MaintenanceSchedule.next_maintenance_date < datetime.combine(today, datetime.min.time()),
        MaintenanceSchedule.is_active == True
    ).all()
    
    # Manutenção próxima (7 dias)
    upcoming_maintenance = MaintenanceSchedule.query.filter(
        MaintenanceSchedule.next_maintenance_date >= datetime.combine(today, datetime.min.time()),
        MaintenanceSchedule.next_maintenance_date <= datetime.combine(in_7_days, datetime.max.time()),
        MaintenanceSchedule.is_active == True
    ).all()

    # Técnicos (visualização apenas)
    technicians = User.query.filter_by(permission_level='user').all()
    tech_performance = []
    for tech in technicians:
        tech_os_count = WorkOrder.query.filter_by(technician_id=tech.id).count()
        tech_performance.append({
            'name': tech.name,
            'specialty': tech.specialty,
            'os_count': tech_os_count
        })

    return render_template('secretary/dashboard.html',
                           total_clients=total_clients,
                           total_equipment=total_equipment,
                           total_os=total_os,
                           pending_os=pending_os,
                           services_today=services_today,
                           overdue_services=overdue_services,
                           overdue_maintenance=overdue_maintenance,
                           upcoming_maintenance=upcoming_maintenance,
                           tech_performance=tech_performance)


@secretary_bp.route('/workorder/schedule', methods=['GET', 'POST'])
@permission_level_required('secretary', 'admin')
def schedule_workorder():
    """Agendar nova ordem de serviço"""
    if request.method == 'POST':
        try:
            client_id = request.form.get('client_id')
            equipment_id = request.form.get('equipment_id')
            technician_id = request.form.get('technician_id')
            description = request.form.get('description')
            scheduled_date_str = request.form.get('scheduled_date')
            
            if not all([client_id, equipment_id, technician_id, scheduled_date_str]):
                flash("Todos os campos são obrigatórios!", "danger")
                return redirect(url_for('secretary.schedule_workorder'))
            
            scheduled_date = datetime.fromisoformat(scheduled_date_str)
            
            workorder = WorkOrder(
                client_id=int(client_id),
                equipment_id=int(equipment_id),
                technician_id=int(technician_id),
                description=description,
                scheduled_date=scheduled_date,
                status='Pending'
            )
            
            db.session.add(workorder)
            db.session.commit()
            
            # Log action
            log_action(
                action='CREATE',
                resource_type='WorkOrder',
                resource_id=workorder.id,
                resource_name=f"WO-{workorder.id}",
                details={
                    'client_id': client_id,
                    'equipment_id': equipment_id,
                    'technician_id': technician_id,
                    'description': description[:100]
                }
            )
            
            flash(f"Ordem de serviço {workorder.id} agendada com sucesso!", "success")
            return redirect(url_for('secretary.dashboard'))
        
        except Exception as e:
            flash(f"Erro ao agendar: {str(e)}", "danger")
            log_action(
                action='CREATE',
                resource_type='WorkOrder',
                status='error',
                details={'error': str(e)}
            )
    
    # GET request - show form
    clients = Client.query.all()
    equipment = Equipment.query.all()
    technicians = User.query.filter_by(permission_level='user').all()
    
    return render_template('secretary/schedule_workorder.html',
                         clients=clients,
                         equipment=equipment,
                         technicians=technicians)


@secretary_bp.route('/workorder/<int:wo_id>/edit-schedule', methods=['GET', 'POST'])
@permission_level_required('secretary', 'admin')
def edit_workorder_schedule(wo_id):
    """Editar agendamento de ordem de serviço"""
    workorder = WorkOrder.query.get_or_404(wo_id)
    
    # Secretariado não pode editar ordens concluídas ou finalizadas
    if workorder.status == 'Completed':
        flash("Não é possível editar ordens de serviço concluídas!", "warning")
        return redirect(url_for('secretary.dashboard'))
    
    if request.method == 'POST':
        try:
            technician_id = request.form.get('technician_id')
            scheduled_date_str = request.form.get('scheduled_date')
            description = request.form.get('description')
            
            old_technician = workorder.technician_id
            old_date = workorder.scheduled_date
            
            if technician_id:
                workorder.technician_id = int(technician_id)
            
            if scheduled_date_str:
                workorder.scheduled_date = datetime.fromisoformat(scheduled_date_str)
            
            if description:
                workorder.description = description
            
            db.session.commit()
            
            # Log action
            log_action(
                action='UPDATE',
                resource_type='WorkOrder',
                resource_id=wo_id,
                resource_name=f"WO-{wo_id}",
                details={
                    'technician_changed': old_technician != workorder.technician_id,
                    'date_changed': old_date != workorder.scheduled_date,
                    'new_technician_id': workorder.technician_id,
                    'new_date': str(workorder.scheduled_date)
                }
            )
            
            flash("Agendamento atualizado com sucesso!", "success")
            return redirect(url_for('secretary.dashboard'))
        
        except Exception as e:
            flash(f"Erro ao atualizar: {str(e)}", "danger")
            log_action(
                action='UPDATE',
                resource_type='WorkOrder',
                resource_id=wo_id,
                status='error',
                details={'error': str(e)}
            )
    
    technicians = User.query.filter_by(permission_level='user').all()
    
    return render_template('secretary/edit_workorder_schedule.html',
                         workorder=workorder,
                         technicians=technicians)


@secretary_bp.route('/workorder/<int:wo_id>/conclude', methods=['POST'])
@permission_level_required('secretary', 'admin')
def conclude_workorder(wo_id):
    """Concluir ordem de serviço (mudança de status)"""
    workorder = WorkOrder.query.get_or_404(wo_id)
    
    try:
        if workorder.status == 'Completed':
            flash("Esta ordem de serviço já foi concluída!", "info")
            return redirect(url_for('secretary.pending_workorders'))
        
        old_status = workorder.status
        workorder.status = 'Completed'
        workorder.completed_date = datetime.utcnow()
        
        db.session.commit()
        
        # Log action
        log_action(
            action='UPDATE',
            resource_type='WorkOrder',
            resource_id=wo_id,
            resource_name=f"WO-{wo_id}",
            details={
                'status_change': f"{old_status} → Completed",
                'completed_by': 'secretary'
            }
        )
        
        flash(f"Ordem de serviço {wo_id} concluída!", "success")
    
    except Exception as e:
        flash(f"Erro ao concluir: {str(e)}", "danger")
        log_action(
            action='UPDATE',
            resource_type='WorkOrder',
            resource_id=wo_id,
            status='error',
            details={'error': str(e)}
        )
    
    return redirect(url_for('secretary.pending_workorders'))


@secretary_bp.route('/workorders/pending')
@permission_level_required('secretary', 'admin')
def pending_workorders():
    """Listar ordens de serviço pendentes"""
    workorders = WorkOrder.query.filter(
        WorkOrder.status.in_(['Pending', 'In Progress'])
    ).order_by(WorkOrder.scheduled_date).all()
    
    return render_template('secretary/pending_workorders.html',
                         workorders=workorders)
