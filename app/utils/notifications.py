from app.models.workorder import WorkOrder
from app.models.maintenance import MaintenanceSchedule
from app.models.user import User
from datetime import datetime, timedelta

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
        'total_count': 0
    }
    
    if user and user.permission_level == 'secretary':
        # Alertas do secretário
        # Serviços para hoje
        alerts['services_today'] = WorkOrder.query.filter(
            WorkOrder.scheduled_date >= datetime.combine(today, datetime.min.time()),
            WorkOrder.scheduled_date < datetime.combine(tomorrow, datetime.min.time()),
            WorkOrder.status.in_(['Pending', 'In Progress'])
        ).all()
        
        # Serviços atrasados
        alerts['overdue_services'] = WorkOrder.query.filter(
            WorkOrder.scheduled_date < datetime.combine(today, datetime.min.time()),
            WorkOrder.status.in_(['Pending', 'In Progress'])
        ).all()
        
        # Ordens sem técnico atribuído
        alerts['pending_assignment'] = WorkOrder.query.filter(
            WorkOrder.technician_id == None,
            WorkOrder.status.in_(['Pending', 'In Progress'])
        ).all()
        
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
    else:
        # Alertas globais (admin)
        alerts['services_today'] = WorkOrder.query.filter(
            WorkOrder.scheduled_date >= datetime.combine(today, datetime.min.time()),
            WorkOrder.scheduled_date < datetime.combine(tomorrow, datetime.min.time()),
            WorkOrder.status.in_(['Pending', 'In Progress'])
        ).all()
        
        alerts['overdue_services'] = WorkOrder.query.filter(
            WorkOrder.scheduled_date < datetime.combine(today, datetime.min.time()),
            WorkOrder.status.in_(['Pending', 'In Progress'])
        ).all()
        
        alerts['pending_assignment'] = WorkOrder.query.filter(
            WorkOrder.technician_id == None,
            WorkOrder.status.in_(['Pending', 'In Progress'])
        ).all()
        
        alerts['overdue_maintenance'] = MaintenanceSchedule.query.filter(
            MaintenanceSchedule.next_maintenance_date < datetime.combine(today, datetime.min.time()),
            MaintenanceSchedule.is_active == True
        ).all()
        
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
