from app.models.workorder import WorkOrder
from app.models.maintenance import MaintenanceSchedule
from app.models.user import User
from datetime import datetime, timedelta


def _serialize_overdue_service(service, today):
    scheduled_date = service.scheduled_date.date() if service.scheduled_date else None
    days_overdue = (today - scheduled_date).days if scheduled_date else 0
    return {
        'id': service.id,
        'client_name': service.client.name if service.client else '-',
        'equipment_name': service.equipment.name if service.equipment else 'Serviço Geral',
        'service_name': service.service_type.name if getattr(service, 'service_type', None) else '-',
        'technician_name': service.technician.name if service.technician else 'Não atribuído',
        'scheduled_date': service.scheduled_date,
        'days_overdue': max(days_overdue, 0),
        'status': service.status,
        'edit_url': f'/services/edit/{service.id}'
    }


def _serialize_maintenance(maintenance, today):
    maintenance_date = maintenance.next_maintenance_date.date() if maintenance.next_maintenance_date else None
    days_overdue = (today - maintenance_date).days if maintenance_date else 0
    return {
        'id': maintenance.id,
        'client_name': maintenance.equipment.owner.name if maintenance.equipment and maintenance.equipment.owner else '-',
        'equipment_name': maintenance.equipment.name if maintenance.equipment else '-',
        'scheduled_date': maintenance.next_maintenance_date,
        'days_overdue': max(days_overdue, 0),
    }


def _serialize_service_today(service):
    return {
        'id': service.id,
        'client_name': service.client.name if service.client else '-',
        'equipment_name': service.equipment.name if service.equipment else 'Serviço Geral',
        'technician_name': service.technician.name if service.technician else 'Não atribuído',
        'scheduled_date': service.scheduled_date,
    }


def _serialize_pending_assignment(service):
    return {
        'id': service.id,
        'client_name': service.client.name if service.client else '-',
        'equipment_name': service.equipment.name if service.equipment else 'Serviço Geral',
        'scheduled_date': service.scheduled_date,
        'service_name': service.service_type.name if getattr(service, 'service_type', None) else '-',
    }

def get_alerts(user=None):
    """
    Retorna alertas personalizados por tipo de usuário:
    - Admin: Visão completa de todos os alertas
    - Secretary: Alertas de agendamentos e ordens de serviço
    - User (Técnico): Apenas serviços atrasados atribuídos
    """
    today = datetime.utcnow().date()
    tomorrow = today + timedelta(days=1)
    in_7_days = today + timedelta(days=7)
    
    alerts = {
        'services_today': [],
        'overdue_services': [],
        'overdue_maintenance': [],
        'upcoming_maintenance': [],
        'pending_assignment': [],  # Para secretários - ordens sem técnico
        'total_count': 0,
        'overdue_services_details': [],
        'overdue_maintenance_details': [],
        'services_today_details': [],
        'pending_assignment_details': [],
    }
    
    if user and user.permission_level == 'secretary':
        # Alertas do secretário
        # Serviços para hoje
        alerts['services_today'] = WorkOrder.query.filter(
            WorkOrder.scheduled_date >= datetime.combine(today, datetime.min.time()),
            WorkOrder.scheduled_date < datetime.combine(tomorrow, datetime.min.time()),
            WorkOrder.status.in_(['Pending', 'In Progress'])
        ).all()
        alerts['services_today_details'] = [_serialize_service_today(service) for service in alerts['services_today']]
        
        # Serviços atrasados
        alerts['overdue_services'] = WorkOrder.query.filter(
            WorkOrder.scheduled_date < datetime.combine(today, datetime.min.time()),
            WorkOrder.status.in_(['Pending', 'In Progress'])
        ).all()
        alerts['overdue_services_details'] = [_serialize_overdue_service(service, today) for service in alerts['overdue_services']]
        
        # Ordens sem técnico atribuído
        alerts['pending_assignment'] = WorkOrder.query.filter(
            WorkOrder.technician_id == None,
            WorkOrder.status.in_(['Pending', 'In Progress'])
        ).all()
        alerts['pending_assignment_details'] = [_serialize_pending_assignment(service) for service in alerts['pending_assignment']]
        
        # Manutenções próximas
        alerts['upcoming_maintenance'] = MaintenanceSchedule.query.filter(
            MaintenanceSchedule.next_maintenance_date >= datetime.combine(today, datetime.min.time()),
            MaintenanceSchedule.next_maintenance_date <= datetime.combine(in_7_days, datetime.max.time()),
            MaintenanceSchedule.is_active == True
        ).limit(5).all()
    
    elif user and user.permission_level == 'user':
        # Alertas do técnico - apenas serviços atrasados
        alerts['overdue_services'] = WorkOrder.query.filter(
            WorkOrder.technician_id == user.id,
            WorkOrder.scheduled_date < datetime.combine(today, datetime.min.time()),
            WorkOrder.status.in_(['Pending', 'In Progress'])
        ).all()
        alerts['overdue_services_details'] = [_serialize_overdue_service(service, today) for service in alerts['overdue_services']]
    else:
        # Alertas globais (admin)
        alerts['services_today'] = WorkOrder.query.filter(
            WorkOrder.scheduled_date >= datetime.combine(today, datetime.min.time()),
            WorkOrder.scheduled_date < datetime.combine(tomorrow, datetime.min.time()),
            WorkOrder.status.in_(['Pending', 'In Progress'])
        ).all()
        alerts['services_today_details'] = [_serialize_service_today(service) for service in alerts['services_today']]
        
        alerts['overdue_services'] = WorkOrder.query.filter(
            WorkOrder.scheduled_date < datetime.combine(today, datetime.min.time()),
            WorkOrder.status.in_(['Pending', 'In Progress'])
        ).all()
        alerts['overdue_services_details'] = [_serialize_overdue_service(service, today) for service in alerts['overdue_services']]
        
        alerts['pending_assignment'] = WorkOrder.query.filter(
            WorkOrder.technician_id == None,
            WorkOrder.status.in_(['Pending', 'In Progress'])
        ).all()
        alerts['pending_assignment_details'] = [_serialize_pending_assignment(service) for service in alerts['pending_assignment']]
        
        alerts['overdue_maintenance'] = MaintenanceSchedule.query.filter(
            MaintenanceSchedule.next_maintenance_date < datetime.combine(today, datetime.min.time()),
            MaintenanceSchedule.is_active == True
        ).all()
        alerts['overdue_maintenance_details'] = [_serialize_maintenance(maintenance, today) for maintenance in alerts['overdue_maintenance']]
        
        alerts['upcoming_maintenance'] = MaintenanceSchedule.query.filter(
            MaintenanceSchedule.next_maintenance_date >= datetime.combine(today, datetime.min.time()),
            MaintenanceSchedule.next_maintenance_date <= datetime.combine(in_7_days, datetime.max.time()),
            MaintenanceSchedule.is_active == True
        ).all()
    
    # Calcular contagem total
    alerts['total_count'] = (
        len(alerts['services_today']) + 
        len(alerts['overdue_services']) + 
        len(alerts['overdue_maintenance']) + 
        len(alerts['upcoming_maintenance']) +
        len(alerts['pending_assignment'])
    )
    
    return alerts
