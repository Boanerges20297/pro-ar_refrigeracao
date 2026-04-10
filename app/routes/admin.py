import json
import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_jwt_extended import get_jwt_identity, jwt_required
from app.utils.decorators import license_feature_required, roles_required, permission_level_required
from app.utils.license import activate_license_key, evaluate_license, get_instance_fingerprint, get_license_record, revalidate_license
from app.models.workorder import WorkOrder
from app.models.maintenance import MaintenanceSchedule
from app.models.user import User
from app.models.config import AppConfig
from app.models.audit_log import AuditLog
from app import db
from sqlalchemy import func
from datetime import datetime, timedelta

ALLOWED_LOGO_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp', 'svg'}
MAX_LOGO_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB

admin_bp = Blueprint('admin', __name__)

AUDIT_ACTION_LABELS = {
    'LOGIN': 'Login',
    'LOGOUT': 'Logout',
    'CREATE': 'Criação',
    'UPDATE': 'Alteração',
    'DELETE': 'Exclusão',
    'READ': 'Consulta',
    'PASSWORD_RESET': 'Redefinição de Senha',
    'LICENSE_KEY_CHANGED': 'Alteração de Licença',
    'LICENSE_LOGIN_BLOCKED': 'Bloqueio por Licença',
    'LICENSE_REVALIDATED': 'Revalidação de Licença',
    'LICENSE_ACTIVATED': 'Ativação de Licença',
}

AUDIT_RESOURCE_LABELS = {
    'WorkOrder': 'Ordem de Serviço',
    'User': 'Usuário',
    'Client': 'Cliente',
    'Equipment': 'Equipamento',
    'MaintenanceSchedule': 'Manutenção',
    'ServiceCatalog': 'Serviço',
    'License': 'Licença',
}

AUDIT_DETAIL_LABELS = {
    'reason': 'Motivo',
    'error': 'Erro',
    'message': 'Mensagem',
    'status_change': 'Mudança de Status',
    'completed_by': 'Concluído Por',
    'technician_changed': 'Técnico Alterado',
    'date_changed': 'Data Alterada',
    'new_technician_id': 'Novo Técnico',
    'new_date': 'Nova Data',
    'old_values': 'Valores Anteriores',
    'new_values': 'Valores Novos',
    'status': 'Status',
    'description': 'Descrição',
    'total_value': 'Valor Total',
    'scheduled_date': 'Data Agendada',
    'technician_id': 'Técnico',
    'email': 'E-mail',
    'expires_at': 'Expira em',
    'company_name': 'Empresa',
}


def translate_audit_action(action):
    return AUDIT_ACTION_LABELS.get(action, action.replace('_', ' ').title())


def translate_resource_type(resource_type):
    return AUDIT_RESOURCE_LABELS.get(resource_type, resource_type)


def humanize_detail_value(value):
    if isinstance(value, bool):
        return 'Sim' if value else 'Não'
    if value is None or value == '':
        return '-'
    return str(value)


def normalize_audit_details(details):
    if not details:
        return []

    parsed = details
    if isinstance(details, str):
        try:
            parsed = json.loads(details)
        except (TypeError, ValueError, json.JSONDecodeError):
            return [{'label': 'Detalhes', 'value': details}]

    if not isinstance(parsed, dict):
        return [{'label': 'Detalhes', 'value': humanize_detail_value(parsed)}]

    rows = []
    for key, value in parsed.items():
        label = AUDIT_DETAIL_LABELS.get(key, key.replace('_', ' ').title())
        if isinstance(value, dict):
            for subkey, subvalue in value.items():
                sublabel = AUDIT_DETAIL_LABELS.get(subkey, subkey.replace('_', ' ').title())
                rows.append({
                    'label': f'{label} - {sublabel}',
                    'value': humanize_detail_value(subvalue)
                })
        else:
            rows.append({'label': label, 'value': humanize_detail_value(value)})

    return rows

@admin_bp.route('/dashboard')
@roles_required('admin')
def dashboard():
    today = datetime.utcnow().date()
    selected_period = request.args.get('period', 'month').strip().lower()
    start_date_raw = request.args.get('start_date', '').strip()
    end_date_raw = request.args.get('end_date', '').strip()

    if selected_period == 'today':
        start_date = today
        end_date = today
    elif selected_period == 'last_30_days':
        start_date = today - timedelta(days=29)
        end_date = today
    elif selected_period == 'year':
        start_date = today.replace(month=1, day=1)
        end_date = today
    elif start_date_raw and end_date_raw:
        try:
            start_date = datetime.strptime(start_date_raw, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_raw, '%Y-%m-%d').date()
            selected_period = 'custom'
        except ValueError:
            start_date = today.replace(day=1)
            end_date = today
            selected_period = 'month'
    else:
        start_date = today.replace(day=1)
        end_date = today
        selected_period = 'month'

    if start_date > end_date:
        start_date, end_date = end_date, start_date

    period_start = datetime.combine(start_date, datetime.min.time())
    period_end = datetime.combine(end_date + timedelta(days=1), datetime.min.time())
    workorder_period_filters = [
        WorkOrder.created_at >= period_start,
        WorkOrder.created_at < period_end,
    ]

    # Metrics
    total_os = WorkOrder.query.filter(*workorder_period_filters).count()
    completed_os = WorkOrder.query.filter(*workorder_period_filters, WorkOrder.status == 'Completed').count()
    pending_os = WorkOrder.query.filter(*workorder_period_filters, WorkOrder.status == 'Pending').count()

    # Financials
    total_revenue = db.session.query(func.sum(WorkOrder.total_value)).filter(*workorder_period_filters, WorkOrder.status == 'Completed').scalar() or 0.0
    pending_revenue = db.session.query(func.sum(WorkOrder.total_value)).filter(*workorder_period_filters, WorkOrder.status != 'Completed').scalar() or 0.0

    # Technicians Performance
    techs = User.query.filter_by(role='technician').all()
    tech_performance = []
    for tech in techs:
        tech_os_count = WorkOrder.query.filter(*workorder_period_filters, WorkOrder.technician_id == tech.id).count()
        tech_performance.append({
            'name': tech.name,
            'specialty': tech.specialty,
            'os_count': tech_os_count
        })

    # Alertas
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

    return render_template('admin/dashboard.html',
                           total_os=total_os,
                           completed_os=completed_os,
                           pending_os=pending_os,
                           total_revenue=total_revenue,
                           pending_revenue=pending_revenue,
                           tech_performance=tech_performance,
                           selected_period=selected_period,
                           selected_start_date=start_date.isoformat(),
                           selected_end_date=end_date.isoformat(),
                           services_today=services_today,
                           overdue_services=overdue_services,
                           overdue_maintenance=overdue_maintenance,
                           upcoming_maintenance=upcoming_maintenance)

@admin_bp.route('/settings', methods=['GET', 'POST'])
@roles_required('admin')
def settings():
    config = AppConfig.query.first()
    if not config:
        config = AppConfig()
        db.session.add(config)
        db.session.commit()

    if request.method == 'POST':
        config.primary_color     = request.form.get('primary_color')
        config.secondary_color   = request.form.get('secondary_color')
        config.background_color  = request.form.get('background_color')
        config.text_color        = request.form.get('text_color')
        config.navbar_bg_color    = request.form.get('navbar_bg_color')
        config.navbar_link_color  = request.form.get('navbar_link_color')
        config.navbar_hover_color = request.form.get('navbar_hover_color')

        # SMTP Settings
        config.smtp_provider    = request.form.get('smtp_provider')
        config.smtp_server      = request.form.get('smtp_server')

        config.smtp_port        = int(request.form.get('smtp_port') or 587)
        config.smtp_user        = request.form.get('smtp_user')
        config.smtp_password    = request.form.get('smtp_password')
        config.smtp_use_tls     = 'smtp_use_tls' in request.form
        config.smtp_use_ssl     = 'smtp_use_ssl' in request.form
        config.mail_sender_name = request.form.get('mail_sender_name')

        db.session.commit()
        flash('Configurações atualizadas com sucesso!', 'success')
        return redirect(url_for('admin.settings'))

    license_record = get_license_record(create=True)
    license_state = evaluate_license(license_record)
    return render_template(
        'admin/settings.html',
        config=config,
        license_record=license_record,
        license_state=license_state,
        license_instance_fingerprint=get_instance_fingerprint(),
    )


@admin_bp.route('/license', methods=['POST'])
@permission_level_required('admin')
def activate_license():
    license_key = (request.form.get('license_key') or '').strip()
    if not license_key:
        flash('Informe uma chave de licença para ativar ou renovar.', 'danger')
        return redirect(url_for('admin.settings'))

    state = activate_license_key(license_key, explicit_user_id=int(get_jwt_identity()))
    flash(state['message'], 'success' if state['valid'] and not state['blocking'] else 'danger')
    return redirect(url_for('admin.settings'))


@admin_bp.route('/license/revalidate', methods=['POST'])
@permission_level_required('admin')
def validate_license():
    state = revalidate_license(explicit_user_id=int(get_jwt_identity()))
    flash(state['message'], 'success' if state['valid'] and not state['blocking'] else state['flash_category'])
    return redirect(url_for('admin.settings'))


@admin_bp.route('/audit-logs', methods=['GET'])
@permission_level_required('admin')
@license_feature_required('audit')
def audit_logs():
    """Visualizar logs de auditoria - APENAS ADMIN"""
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    # Filtros opcionais
    user_id_filter = request.args.get('user_id', type=int)
    action_filter = request.args.get('action', '').upper()
    resource_type_filter = request.args.get('resource_type', '').upper()
    status_filter = request.args.get('status', '').lower()
    days_back = request.args.get('days', 7, type=int)
    
    query = AuditLog.query
    
    # Apply filters
    if days_back:
        cutoff_date = datetime.utcnow() - timedelta(days=days_back)
        query = query.filter(AuditLog.timestamp >= cutoff_date)
    
    if user_id_filter:
        query = query.filter(AuditLog.user_id == user_id_filter)
    
    if action_filter:
        query = query.filter(AuditLog.action == action_filter)
    
    if resource_type_filter:
        query = query.filter(AuditLog.resource_type == resource_type_filter)
    
    if status_filter:
        query = query.filter(AuditLog.status == status_filter)
    
    # Pagination
    logs_page = query.order_by(AuditLog.timestamp.desc()).paginate(page=page, per_page=per_page)
    
    # Get unique values for filters
    all_users = User.query.order_by(User.name).all()
    actions_list = db.session.query(AuditLog.action).distinct().order_by(AuditLog.action).all()
    resource_types_list = db.session.query(AuditLog.resource_type).distinct().order_by(AuditLog.resource_type).all()

    serialized_logs = []
    user_lookup = {user.id: user for user in all_users}
    for log in logs_page.items:
        user = user_lookup.get(log.user_id)
        serialized_logs.append({
            'id': log.id,
            'timestamp': log.timestamp.isoformat() if log.timestamp else None,
            'timestamp_label': log.timestamp.strftime('%d/%m/%Y %H:%M:%S') if log.timestamp else '-',
            'user_name': user.name if user else 'Desconhecido',
            'action': log.action,
            'action_label': translate_audit_action(log.action),
            'resource_type': log.resource_type,
            'resource_label': translate_resource_type(log.resource_type),
            'resource_id': log.resource_id,
            'resource_name': log.resource_name,
            'status': log.status,
            'ip_address': log.ip_address,
            'user_agent': log.user_agent,
            'details_rows': normalize_audit_details(log.details),
        })
    
    return render_template('admin/audit_logs.html',
                         logs=serialized_logs,
                         pagination=logs_page,
                         users=all_users,
                         actions=actions_list,
                         resource_types=resource_types_list,
                         action_labels=AUDIT_ACTION_LABELS,
                         resource_labels=AUDIT_RESOURCE_LABELS,
                         user_id_filter=user_id_filter,
                         action_filter=action_filter,
                         resource_type_filter=resource_type_filter,
                         status_filter=status_filter,
                         days_back=days_back)


@admin_bp.route('/audit-logs/stats')
@permission_level_required('admin')
@license_feature_required('audit')
def audit_logs_stats():
    """Estatísticas de auditoria - APENAS ADMIN"""
    # Total logs
    total_logs = AuditLog.query.count()
    
    # Logs dos últimos 7 dias
    cutoff_7days = datetime.utcnow() - timedelta(days=7)
    recent_logs = AuditLog.query.filter(AuditLog.timestamp >= cutoff_7days).count()
    
    # Logs por tipo de ação
    from sqlalchemy import func
    actions = db.session.query(
        AuditLog.action,
        func.count(AuditLog.id).label('count')
    ).group_by(AuditLog.action).order_by(
        func.count(AuditLog.id).desc()
    ).all()
    
    # Logs por usuário (últimos 7 dias)
    user_activity = db.session.query(
        User.name,
        func.count(AuditLog.id).label('count')
    ).join(AuditLog, AuditLog.user_id == User.id).filter(
        AuditLog.timestamp >= cutoff_7days
    ).group_by(User.name).order_by(
        func.count(AuditLog.id).desc()
    ).limit(10).all()
    
    # Erros (últimos 7 dias)
    errors = AuditLog.query.filter(
        AuditLog.status == 'error',
        AuditLog.timestamp >= cutoff_7days
    ).order_by(AuditLog.timestamp.desc()).limit(20).all()
    
    return render_template('admin/audit_logs_stats.html',
                         total_logs=total_logs,
                         recent_logs=recent_logs,
                         actions=actions,
                         user_activity=user_activity,
                         errors=errors)


@admin_bp.route('/audit-logs/export')
@permission_level_required('admin')
@license_feature_required('audit')
def audit_logs_export():
    """Exportar logs de auditoria como CSV - APENAS ADMIN"""
    import csv
    from io import StringIO
    from flask import send_file
    
    days_back = request.args.get('days', 30, type=int)
    cutoff_date = datetime.utcnow() - timedelta(days=days_back)
    
    logs = AuditLog.query.filter(
        AuditLog.timestamp >= cutoff_date
    ).order_by(AuditLog.timestamp.desc()).all()
    
    # Create CSV in memory
    si = StringIO()
    writer = csv.writer(si)
    
    # Headers
    writer.writerow([
        'Data/Hora', 'Usuário', 'Ação', 'Recurso', 'ID Recurso', 
        'Status', 'IP', 'Detalhes'
    ])
    
    # Data rows
    for log in logs:
        user = User.query.get(log.user_id)
        writer.writerow([
            log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            user.name if user else 'Desconhecido',
            log.action,
            log.resource_type,
            log.resource_id or '',
            log.status,
            log.ip_address or '',
            log.details or ''
        ])
    
    si.seek(0)
    
    return send_file(
        StringIO(si.getvalue()),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'audit_logs_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.csv'
    )
