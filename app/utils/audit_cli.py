"""
CLI commands for managing audit logs.
Run with: flask audit-cleanup
"""
import click
from flask.cli import with_appcontext
from datetime import timedelta, datetime
from app.models.audit_log import AuditLog
from app import db


@click.command('audit-cleanup')
@click.option('--days', default=7, help='Delete logs older than this many days (default: 7)')
@with_appcontext
def cleanup_audit_logs(days):
    """Delete audit logs older than specified days."""
    deleted = AuditLog.cleanup_old_logs(days=days)
    click.echo(f"✓ Deleted {deleted} audit log entries older than {days} days")


@click.command('audit-stats')
@with_appcontext
def audit_stats():
    """Display statistics about audit logs."""
    total_logs = AuditLog.query.count()
    recent_logs = AuditLog.query.filter(
        AuditLog.timestamp >= datetime.utcnow() - timedelta(days=7)
    ).count()
    
    # Get top actions
    from sqlalchemy import func
    top_actions = db.session.query(
        AuditLog.action, 
        func.count(AuditLog.id).label('count')
    ).group_by(AuditLog.action).order_by(
        func.count(AuditLog.id).desc()
    ).limit(10).all()
    
    click.echo(f"Total audit logs: {total_logs}")
    click.echo(f"Logs from last 7 days: {recent_logs}")
    click.echo("\nTop 10 actions:")
    for action, count in top_actions:
        click.echo(f"  {action}: {count}")


@click.command('audit-cleanup-schedule')
@click.option('--interval', default=1, help='Run cleanup every N days (default: 1)')
@with_appcontext
def schedule_audit_cleanup(interval):
    """Schedule automatic audit log cleanup."""
    import atexit
    from apscheduler.schedulers.background import BackgroundScheduler
    
    scheduler = BackgroundScheduler()
    
    def cleanup_task():
        deleted = AuditLog.cleanup_old_logs(days=7)
        print(f"[AuditLog] Auto-cleanup: Deleted {deleted} old entries")
    
    scheduler.add_job(
        func=cleanup_task,
        trigger="interval",
        days=interval,
        id='audit_log_cleanup',
        name='Audit Log Cleanup',
        replace_existing=True
    )
    
    scheduler.start()
    atexit.register(lambda: scheduler.shutdown())
    
    click.echo(f"✓ Scheduled audit log cleanup every {interval} day(s)")


def register_commands(app):
    """Register all CLI commands."""
    app.cli.add_command(cleanup_audit_logs)
    app.cli.add_command(audit_stats)
    app.cli.add_command(schedule_audit_cleanup)
