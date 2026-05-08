from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app.models.user import User
from app.models.workorder import WorkOrder
from app.models.maintenance import MaintenanceSchedule
from app import db
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.decorators import roles_required
from app.utils.license import check_user_limit
from app.utils.security import is_password_strong, PASSWORD_POLICY_MESSAGE
from app.utils.email import send_dynamic_email
from app.utils.audit import log_action
from datetime import datetime, timedelta
from sqlalchemy import or_

tech_bp = Blueprint('tech', __name__)


def normalize_email(email):
    return (email or '').strip().lower()


def send_staff_message(recipients, subject, message_body, sender_name):
    sent_count = 0
    failed_recipients = []

    for recipient in recipients:
        success, error_message = send_dynamic_email(
            to_email=recipient.email,
            subject=subject,
            template='email/staff_message.html',
            recipient=recipient,
            sender_name=sender_name,
            message_subject=subject,
            message_body=message_body,
        )

        if success:
            sent_count += 1
        else:
            failed_recipients.append({
                'name': recipient.name,
                'email': recipient.email,
                'error': error_message,
            })

    return sent_count, failed_recipients

@tech_bp.route('/dashboard')
@roles_required('technician', 'admin') # Admins can also see tech dash
def dashboard():
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)

    # Technician Metrics
    my_os = WorkOrder.query.filter_by(technician_id=user.id).all()
    total_my_os = len(my_os)
    completed_my_os = sum(1 for wo in my_os if wo.status == 'Completed')
    pending_my_os = sum(1 for wo in my_os if wo.status == 'Pending')
    in_progress_my_os = sum(1 for wo in my_os if wo.status == 'In Progress')

    # Alertas
    today = datetime.utcnow().date()
    
    # Serviços atrasados (do técnico)
    overdue_services = WorkOrder.query.filter(
        WorkOrder.technician_id == user.id,
        WorkOrder.scheduled_date < datetime.combine(today, datetime.min.time()),
        WorkOrder.status.in_(['Pending', 'In Progress'])
    ).all()

    return render_template('technician/dashboard.html',
                           my_os=my_os,
                           total_my_os=total_my_os,
                           completed_my_os=completed_my_os,
                           pending_my_os=pending_my_os,
                           in_progress_my_os=in_progress_my_os,
                           overdue_services=overdue_services)


@tech_bp.route('/assignments/status')
@roles_required('technician')
def assignment_status():
    current_user_id = get_jwt_identity()
    user = User.query.get_or_404(current_user_id)

    active_workorders = WorkOrder.query.filter(
        WorkOrder.technician_id == user.id,
        WorkOrder.status.in_(['Pending', 'In Progress'])
    ).order_by(WorkOrder.scheduled_date.asc(), WorkOrder.id.asc()).all()

    return jsonify({
        'workorders': [
            {
                'id': workorder.id,
                'client_name': workorder.client.name if workorder.client else '-',
                'service_name': workorder.service_type.name if getattr(workorder, 'service_type', None) else '-',
                'edit_url': url_for('services.edit', id=workorder.id, return_to=url_for('tech.dashboard')),
            }
            for workorder in active_workorders
        ]
    })

@tech_bp.route('/list')
@roles_required('admin')
def list_technicians():
    search = (request.args.get('search') or '').strip()
    query = User.query

    if search:
        search_term = f'%{search}%'
        query = query.filter(
            or_(
                User.name.ilike(search_term),
                User.email.ilike(search_term),
                User.job_title.ilike(search_term),
                User.specialty.ilike(search_term),
                User.permission_level.ilike(search_term),
            )
        )

    technicians = query.order_by(User.name.asc()).all()
    return render_template('technician/list.html', technicians=technicians, search=search)


@tech_bp.route('/message/<int:user_id>', methods=['GET', 'POST'])
@roles_required('admin')
def message_user(user_id):
    current_user = User.query.get_or_404(get_jwt_identity())
    user = User.query.get_or_404(user_id)

    if request.method == 'POST':
        subject = (request.form.get('subject') or '').strip()
        message_body = (request.form.get('message') or '').strip()

        if not subject or not message_body:
            flash('Informe o assunto e a mensagem para continuar.', 'danger')
            return render_template(
                'technician/message_form.html',
                mode='single',
                recipient=user,
                form_subject=subject,
                form_message=message_body,
            )

        sent_count, failed_recipients = send_staff_message([user], subject, message_body, current_user.name)
        if sent_count:
            log_action(
                action='MESSAGE_SENT',
                resource_type='User',
                resource_id=user.id,
                resource_name=user.email,
                details={'scope': 'single', 'subject': subject, 'recipient_email': user.email}
            )
            flash(f'Mensagem enviada para {user.name}.', 'success')
            return redirect(url_for('tech.list_technicians'))

        flash(f"Não foi possível enviar a mensagem para {user.name}: {failed_recipients[0]['error']}", 'danger')

    return render_template('technician/message_form.html', mode='single', recipient=user)


@tech_bp.route('/message-all', methods=['GET', 'POST'])
@roles_required('admin')
def message_all_users():
    current_user = User.query.get_or_404(get_jwt_identity())
    recipients = User.query.filter(
        User.is_active == True,
        User.permission_level.in_(['admin', 'user'])
    ).order_by(User.name.asc()).all()

    if request.method == 'POST':
        subject = (request.form.get('subject') or '').strip()
        message_body = (request.form.get('message') or '').strip()

        if not subject or not message_body:
            flash('Informe o assunto e a mensagem para continuar.', 'danger')
            return render_template(
                'technician/message_form.html',
                mode='all',
                recipients=recipients,
                form_subject=subject,
                form_message=message_body,
            )

        if not recipients:
            flash('Nenhum usuário ativo com permissão admin ou user foi encontrado.', 'danger')
            return redirect(url_for('tech.list_technicians'))

        sent_count, failed_recipients = send_staff_message(recipients, subject, message_body, current_user.name)

        if sent_count:
            log_action(
                action='MESSAGE_SENT',
                resource_type='User',
                details={
                    'scope': 'broadcast',
                    'subject': subject,
                    'sent_count': sent_count,
                    'failed_count': len(failed_recipients),
                }
            )

        if failed_recipients:
            flash(
                f'Mensagem enviada para {sent_count} usuário(s). Falha em {len(failed_recipients)} envio(s).',
                'danger'
            )
        else:
            flash(f'Mensagem enviada para {sent_count} usuário(s).', 'success')

        return redirect(url_for('tech.list_technicians'))

    return render_template('technician/message_form.html', mode='all', recipients=recipients)

def normalize_job_title(permission_level, job_title, other_job_title=None):
    if permission_level == 'secretary':
        return 'Atendente'

    if job_title == 'Outros':
        return other_job_title or 'Outros'

    if job_title:
        return job_title

    return 'Técnico'

@tech_bp.route('/add', methods=['GET', 'POST'])
@roles_required('admin')
def add_technician():
    from app.models.client import Client
    clients = Client.query.order_by(Client.name.asc()).all()

    if request.method == 'POST':
        name = request.form.get('name')
        email = normalize_email(request.form.get('email'))
        password = request.form.get('password')
        specialty = request.form.get('specialty')
        is_active = request.form.get('is_active') == 'on'
        permission_level = request.form.get('permission_level', 'user')
        raw_client_ids = request.form.getlist('client_ids')
        client_ids = [int(cid) for cid in raw_client_ids if str(cid).strip().isdigit()]
        must_change_password = request.form.get('must_change_password') == 'on'
        cpf = (request.form.get('cpf') or '').strip()
        phone = (request.form.get('phone') or '').strip()

        job_title = normalize_job_title(
            permission_level,
            request.form.get('job_title'),
            request.form.get('other_job_title')
        )

        if permission_level == 'client':
            job_title = 'Cliente'
            if not client_ids:
                flash('Para o perfil Cliente, é obrigatório selecionar ao menos uma empresa vinculada.', 'danger')
                return render_template('technician/add.html', clients=clients)
        else:
            client_ids = []

        # Backend validation for password
        if not is_password_strong(password):
            flash(PASSWORD_POLICY_MESSAGE, 'danger')
            return render_template('technician/add.html', clients=clients)

        if not email:
            flash('Informe um e-mail válido para continuar.', 'danger')
            return render_template('technician/add.html', clients=clients)

        if User.query.filter_by(email=email).first():
            flash('Já existe um usuário cadastrado com este e-mail.', 'danger')
            return render_template('technician/add.html', clients=clients)

        # Mandatory CPF and Phone for non-admin
        if permission_level != 'admin':
            if not cpf:
                flash('O CPF é obrigatório para este perfil.', 'danger')
                return render_template('technician/add.html', clients=clients)
            if not phone:
                flash('O Telefone é obrigatório para este perfil.', 'danger')
                return render_template('technician/add.html', clients=clients)

        if cpf and User.query.filter(User.cpf == cpf).first():
            flash('Já existe um usuário cadastrado com este CPF.', 'danger')
            return render_template('technician/add.html', clients=clients)

        limit_error = check_user_limit(permission_level=permission_level, is_active=is_active)
        if limit_error:
            flash(limit_error, 'danger')
            return render_template('technician/add.html', clients=clients)

        user = User(
            name=name, 
            email=email, 
            role='technician', 
            permission_level=permission_level, 
            job_title=job_title, 
            specialty=specialty, 
            is_active=is_active,
            client_id=int(client_ids[0]) if client_ids else None, # Legacy support
            must_change_password=must_change_password,
            cpf=cpf or None,
            phone=phone or None
        )
        
        # Associated clients (Many-to-Many)
        if client_ids:
            from app.models.client import Client
            selected_clients = Client.query.filter(Client.id.in_(client_ids)).all()
            user.clients = selected_clients

        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash('Usuário adicionado com sucesso!', 'success')
        return redirect(url_for('tech.list_technicians'))
    return render_template('technician/add.html', clients=clients)

@tech_bp.route('/edit/<int:user_id>', methods=['GET', 'POST'])
@roles_required('admin')
def edit_technician(user_id):
    user = User.query.get_or_404(user_id)
    from app.models.client import Client
    clients = Client.query.order_by(Client.name.asc()).all()

    if request.method == 'POST':
        name = request.form.get('name')
        email = normalize_email(request.form.get('email'))
        specialty = request.form.get('specialty')
        is_active = request.form.get('is_active') == 'on'
        permission_level = request.form.get('permission_level', 'user')
        raw_client_ids = request.form.getlist('client_ids')
        client_ids = [int(cid) for cid in raw_client_ids if str(cid).strip().isdigit()]
        must_change_password = request.form.get('must_change_password') == 'on'
        cpf = (request.form.get('cpf') or '').strip()
        phone = (request.form.get('phone') or '').strip()
        job_title = normalize_job_title(
            permission_level,
            request.form.get('job_title'),
            request.form.get('other_job_title')
        )

        password = request.form.get('password')
        if password: # only update if a new password was provided
            if not is_password_strong(password):
                flash(PASSWORD_POLICY_MESSAGE, 'danger')
                return render_template('technician/edit.html', user=user, clients=clients)

        if not email:
            flash('Informe um e-mail válido para continuar.', 'danger')
            return render_template('technician/edit.html', user=user, clients=clients)

        existing_user = User.query.filter(User.email == email, User.id != user.id).first()
        if existing_user:
            flash('Já existe um usuário cadastrado com este e-mail.', 'danger')
            return render_template('technician/edit.html', user=user, clients=clients)

        # Mandatory CPF and Phone for non-admin
        if permission_level != 'admin':
            if not cpf:
                flash('O CPF é obrigatório para este perfil.', 'danger')
                return render_template('technician/edit.html', user=user, clients=clients)
            if not phone:
                flash('O Telefone é obrigatório para este perfil.', 'danger')
                return render_template('technician/edit.html', user=user, clients=clients)

        if cpf:
            existing_cpf = User.query.filter(User.cpf == cpf, User.id != user.id).first()
            if existing_cpf:
                flash('Já existe outro usuário cadastrado com este CPF.', 'danger')
                return render_template('technician/edit.html', user=user, clients=clients)

        limit_error = check_user_limit(permission_level=permission_level, existing_user=user, is_active=is_active)
        if limit_error:
            flash(limit_error, 'danger')
            return render_template('technician/edit.html', user=user, clients=clients)

        user.name = name
        user.email = email
        user.specialty = specialty
        user.is_active = is_active
        user.permission_level = permission_level
        user.job_title = job_title
        user.must_change_password = must_change_password
        user.cpf = cpf or None
        user.phone = phone or None
        
        if permission_level == 'client':
            if not client_ids:
                flash('Para o perfil Cliente, é obrigatório selecionar ao menos uma empresa vinculada.', 'danger')
                return render_template('technician/edit.html', user=user, clients=clients)
            
            from app.models.client import Client
            selected_clients = Client.query.filter(Client.id.in_(client_ids)).all()
            user.clients = selected_clients
            user.client_id = int(client_ids[0]) if client_ids else None # Legacy support
        else:
            user.clients = []
            user.client_id = None

        if password:
            user.set_password(password)

        db.session.commit()
        flash('Usuário atualizado com sucesso!', 'success')
        return redirect(url_for('tech.list_technicians'))

    return render_template('technician/edit.html', user=user, clients=clients)
