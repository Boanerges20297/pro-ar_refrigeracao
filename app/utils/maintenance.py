from datetime import datetime

from sqlalchemy import func

from app import db
from app.models.service import ServiceCatalog


def get_or_create_maintenance_service():
    service = ServiceCatalog.query.filter(
        func.lower(ServiceCatalog.name) == 'manutenção preventiva'
    ).first()
    if service:
        return service

    service = ServiceCatalog.query.filter(
        func.lower(ServiceCatalog.name).like('%manuten%')
    ).order_by(ServiceCatalog.id.asc()).first()
    if service:
        return service

    service = ServiceCatalog(
        name='Manutenção Preventiva',
        description='Serviço criado automaticamente a partir de um agendamento de manutenção.',
        base_price=0.0,
        estimated_duration=60,
    )
    db.session.add(service)
    db.session.flush()
    return service


def sync_schedule_with_workorder(workorder, previous_status=None):
    schedule = getattr(workorder, 'maintenance_schedule', None)
    if not schedule:
        return

    if workorder.status == 'Completed':
        completed_at = workorder.completed_date or datetime.utcnow()
        workorder.completed_date = completed_at
        schedule.last_maintenance_date = completed_at
        schedule.is_active = False
        return

    if previous_status == 'Completed':
        workorder.completed_date = None
        schedule.last_maintenance_date = None
        schedule.is_active = True