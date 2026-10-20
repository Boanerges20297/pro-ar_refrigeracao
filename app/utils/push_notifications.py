import json
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import current_app

from app import db
from app.models.push_notification import NotificationJob
from app.models.user import User
from app.models.workorder import WorkOrder


def _local_zone():
    return ZoneInfo(current_app.config.get('NOTIFICATION_TIMEZONE', 'America/Fortaleza'))


def _utc_naive(local_datetime):
    return local_datetime.replace(tzinfo=_local_zone()).astimezone(timezone.utc).replace(tzinfo=None)


def sync_workorder_reminders(workorder):
    """Upsert reminders for active recipients and cancel obsolete schedules."""
    if not workorder.scheduled_date or workorder.status not in {'Pending', 'In Progress'}:
        NotificationJob.query.filter_by(workorder_id=workorder.id, status='pending').update({'status': 'cancelled'})
        return

    recipients = User.query.filter(
        User.is_active.is_(True),
        User.permission_level.in_(['admin', 'secretary']),
    ).all()
    if workorder.technician_id:
        technician = User.query.filter_by(id=workorder.technician_id, is_active=True).first()
        if technician and technician not in recipients:
            recipients.append(technician)

    local_service_date = workorder.scheduled_date.date()
    local_today = datetime.now(_local_zone()).date()
    schedules = [] if local_service_date < local_today else [
        ('day_before', local_service_date - timedelta(days=1), int(current_app.config.get('NOTIFICATION_DAY_BEFORE_HOUR', 8))),
        ('today', local_service_date, int(current_app.config.get('NOTIFICATION_TODAY_HOUR', 8))),
    ]
    valid_keys = set()
    for recipient in recipients:
        valid_keys.add((recipient.id, 'open_4h', workorder.scheduled_date))
    for kind, reminder_date, hour in schedules:
        local_due = datetime.combine(reminder_date, time(hour=max(0, min(23, hour))))
        due_at = _utc_naive(local_due)
        for recipient in recipients:
            valid_keys.add((recipient.id, kind, workorder.scheduled_date))
            job = NotificationJob.query.filter_by(
                user_id=recipient.id, workorder_id=workorder.id,
                reminder_kind=kind, scheduled_at=workorder.scheduled_date,
            ).first()
            if not job:
                db.session.add(NotificationJob(
                    user_id=recipient.id, workorder_id=workorder.id,
                    reminder_kind=kind, scheduled_at=workorder.scheduled_date,
                    due_at=due_at,
                ))
            elif job.status == 'cancelled':
                job.status, job.due_at, job.attempts, job.last_error = 'pending', due_at, 0, None

    for job in NotificationJob.query.filter_by(workorder_id=workorder.id, status='pending').all():
        if (job.user_id, job.reminder_kind, job.scheduled_at) not in valid_keys:
            job.status = 'cancelled'


def queue_open_workorder_followups(now=None):
    """Queue at most one follow-up every four hours for an overdue open order."""
    now = now or datetime.utcnow()
    local_now = now.replace(tzinfo=timezone.utc).astimezone(_local_zone()).replace(tzinfo=None)
    threshold = now - timedelta(hours=4)
    workorders = WorkOrder.query.filter(
        WorkOrder.scheduled_date <= local_now,
        WorkOrder.status.in_(['Pending', 'In Progress']),
    ).all()
    for workorder in workorders:
        recipients = User.query.filter(
            User.is_active.is_(True),
            User.permission_level.in_(['admin', 'secretary']),
        ).all()
        if workorder.technician_id:
            technician = User.query.filter_by(id=workorder.technician_id, is_active=True).first()
            if technician and technician not in recipients:
                recipients.append(technician)
        for recipient in recipients:
            latest_sent = NotificationJob.query.filter_by(
                user_id=recipient.id, workorder_id=workorder.id,
                scheduled_at=workorder.scheduled_date, status='sent',
            ).order_by(NotificationJob.sent_at.desc()).first()
            if not latest_sent or not latest_sent.sent_at or latest_sent.sent_at > threshold:
                continue
            pending_followup = NotificationJob.query.filter_by(
                user_id=recipient.id, workorder_id=workorder.id,
                reminder_kind='open_4h', scheduled_at=workorder.scheduled_date,
                status='pending',
            ).first()
            if not pending_followup:
                db.session.add(NotificationJob(
                    user_id=recipient.id,
                    workorder_id=workorder.id,
                    reminder_kind='open_4h',
                    scheduled_at=workorder.scheduled_date,
                    due_at=now,
                ))


def _payload(job):
    wo = job.workorder
    when = wo.scheduled_date.strftime('%d/%m às %H:%M') if wo.scheduled_date else 'horário não informado'
    if job.reminder_kind == 'today':
        title = 'Serviço de hoje'
        body = f"Hoje às {when.split(' às ')[-1]}: {wo.client.name if wo.client else 'Cliente'}"
    elif job.reminder_kind == 'open_4h':
        title = 'Serviço ainda em aberto'
        body = f"OS #{wo.id} · {wo.client.name if wo.client else 'Cliente'} · agendado para {when}"
    else:
        title = 'Serviço agendado para amanhã'
        body = f"Amanhã às {when.split(' às ')[-1]}: {wo.client.name if wo.client else 'Cliente'}"
    tag = f'workorder-{wo.id}-{job.reminder_kind}'
    if job.reminder_kind == 'open_4h':
        tag += '-' + (job.due_at.strftime('%Y%m%d%H%M') if job.due_at else str(job.id))
    return {'title': title, 'body': body, 'url': f'/services/view/{wo.id}', 'tag': tag}


def dispatch_due_notifications(limit=100):
    """Send due outbox messages. Intended to run from cron every few minutes."""
    now = datetime.utcnow()
    jobs = NotificationJob.query.filter(
        NotificationJob.status == 'pending', NotificationJob.due_at <= now,
    ).order_by(NotificationJob.due_at.asc()).limit(limit).all()
    last_delivery = {}
    sent = failed = skipped = 0
    vapid_private = current_app.config.get('VAPID_PRIVATE_KEY')
    vapid_email = current_app.config.get('VAPID_CLAIMS_EMAIL')
    if not vapid_private or not vapid_email:
        return {'sent': 0, 'failed': 0, 'skipped': len(jobs), 'error': 'VAPID não configurado'}

    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        current_app.logger.exception('Dependência pywebpush não instalada')
        return {'sent': 0, 'failed': 0, 'skipped': len(jobs), 'error': 'pywebpush não instalado'}

    for job in jobs:
        wo = job.workorder
        if not wo or wo.status not in {'Pending', 'In Progress'} or wo.scheduled_date != job.scheduled_at:
            job.status = 'cancelled'
            skipped += 1
            continue
        delivery_key = (job.user_id, job.workorder_id)
        if delivery_key not in last_delivery:
            recent = NotificationJob.query.filter(
                NotificationJob.user_id == job.user_id,
                NotificationJob.workorder_id == job.workorder_id,
                NotificationJob.scheduled_at == job.scheduled_at,
                NotificationJob.status == 'sent',
                NotificationJob.sent_at.isnot(None),
            ).order_by(NotificationJob.sent_at.desc()).first()
            last_delivery[delivery_key] = recent.sent_at if recent else None
        prior_sent_at = last_delivery[delivery_key]
        if prior_sent_at and prior_sent_at > now - timedelta(hours=4):
            job.due_at = prior_sent_at + timedelta(hours=4)
            skipped += 1
            continue
        subscriptions = list(job.user.push_subscriptions) if job.user and job.user.is_active else []
        if not subscriptions:
            # Keep pending: the account may enable push before a later retry.
            skipped += 1
            continue
        payload = json.dumps(_payload(job), ensure_ascii=False)
        any_success = False
        for subscription in subscriptions:
            try:
                webpush(
                    subscription_info=json.loads(subscription.subscription_json),
                    data=payload,
                    vapid_private_key=vapid_private,
                    vapid_claims={'sub': f'mailto:{vapid_email}'},
                    timeout=10,
                )
                any_success = True
            except WebPushException as error:
                status_code = getattr(getattr(error, 'response', None), 'status_code', None)
                if status_code in (404, 410):
                    db.session.delete(subscription)
                else:
                    current_app.logger.warning('Web Push falhou para inscrição %s: %s', subscription.id, error)
            except Exception:
                current_app.logger.exception('Falha ao enviar Web Push para inscrição %s', subscription.id)
        if any_success:
            job.status, job.sent_at, job.last_error = 'sent', now, None
            last_delivery[delivery_key] = now
            sent += 1
        else:
            job.attempts += 1
            job.last_error = 'Nenhuma inscrição recebeu o aviso'
            if job.attempts >= 8:
                job.status = 'failed'
            else:
                job.due_at = now + timedelta(minutes=min(60, 2 ** job.attempts))
            failed += 1
    db.session.commit()
    return {'sent': sent, 'failed': failed, 'skipped': skipped}


def register_notification_commands(app):
    @app.cli.command('dispatch-notifications')
    def dispatch_notifications_command():
        """Dispatch scheduled service reminders from the persistent outbox."""
        # Reconcile records so schedule edits made through any screen stay in sync.
        workorders = WorkOrder.query.filter(WorkOrder.status.in_(['Pending', 'In Progress'])).all()
        for workorder in workorders:
            sync_workorder_reminders(workorder)
        queue_open_workorder_followups()
        db.session.commit()
        result = dispatch_due_notifications()
        print(json.dumps(result, ensure_ascii=False))
