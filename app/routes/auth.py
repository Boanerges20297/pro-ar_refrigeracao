from flask import Blueprint, render_template, request, redirect, url_for, flash, make_response, current_app, session
from app.models.user import User
from flask_jwt_extended import create_access_token, set_access_cookies, unset_jwt_cookies, jwt_required, get_jwt_identity
from itsdangerous import URLSafeTimedSerializer
from app.utils.email import send_password_reset_email
from app.utils.audit import log_login, log_logout
from app.utils.license import evaluate_license, get_license_record, log_license_event
from app.utils.security import (
    is_password_strong,
    PASSWORD_POLICY_MESSAGE,
    build_password_version,
    build_session_nonce,
    build_user_agent_fingerprint,
)
from app import db
from app import limiter
from datetime import datetime

auth_bp = Blueprint('auth', __name__)

def generate_reset_token(email):
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    return serializer.dumps(email, salt='password-reset-salt')

def confirm_reset_token(token, expiration=3600):
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        email = serializer.loads(
            token,
            salt='password-reset-salt',
            max_age=expiration
        )
    except:
        return False
    return email

@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit('5 per minute', methods=['POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            if not user.is_active:
                flash('Sua conta está inativa. Contate o administrador.', 'danger')
                # Log failed login attempt (inactive user)
                log_login(user.id, success=False, details={'reason': 'inactive_account'})
                return redirect(url_for('auth.login'))

            license_state = evaluate_license(get_license_record(create=False))
            if license_state['blocking'] and user.permission_level != 'admin':
                flash('O acesso operacional está bloqueado por licença ausente, expirada ou inválida. Contate o administrador.', 'danger')
                log_license_event(
                    'LICENSE_LOGIN_BLOCKED',
                    details={
                        'status': license_state['status'],
                        'message': license_state['message'],
                        'email': user.email,
                    },
                    status='error',
                    explicit_user_id=user.id,
                )
                return redirect(url_for('auth.login'))

            session_nonce = build_session_nonce()
            session['jwt_session_nonce'] = session_nonce
            session.modified = True

            access_token = create_access_token(
                identity=str(user.id),
                additional_claims={
                    'uid': str(user.id),
                    'permission_level': user.permission_level,
                    'pwdv': build_password_version(user.password_hash),
                    'session_nonce': session_nonce,
                    'ua_hash': build_user_agent_fingerprint(request.headers.get('User-Agent')),
                },
            )

            # Log successful login
            log_login(user.id, success=True)

            # Determine where to redirect based on permission_level
            if user.permission_level == 'admin':
                redirect_url = url_for('admin.dashboard')
            elif user.permission_level == 'secretary':
                redirect_url = url_for('secretary.dashboard')
            else:
                redirect_url = url_for('tech.dashboard')

            resp = make_response(redirect(redirect_url))
            set_access_cookies(resp, access_token)
            return resp
        else:
            flash('Email ou senha inválidos.', 'danger')
            # Log failed login attempt
            log_login(user.id if user else None, success=False, details={'reason': 'invalid_credentials'})

    return render_template('auth/login.html')

@auth_bp.route('/logout', methods=['POST'])
@jwt_required(optional=True)
def logout():
    # Log logout action
    current_user_id = get_jwt_identity()
    if current_user_id:
        log_logout(int(current_user_id))

    session.pop('jwt_session_nonce', None)
    
    resp = make_response(redirect(url_for('auth.login')))
    unset_jwt_cookies(resp)
    return resp

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit('3 per 15 minutes', methods=['POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()
        
        # Genericamente dizemos que enviamos o e-mail por segurança
        flash('Se o e-mail estiver cadastrado, você receberá um link de recuperação em instantes.', 'info')
        
        if user:
            token = generate_reset_token(user.email)
            reset_url = url_for('auth.reset_password', token=token, _external=True)
            
            # Use absolute logo URL or fallback
            logo_url = None
            if current_app.config.get('APP_CONFIG'):
                app_config = current_app.config['APP_CONFIG']
                if app_config.logo_path:
                    if app_config.logo_path.startswith('http'):
                        logo_url = app_config.logo_path
                    else:
                        # Clean-up path and make it absolute
                        clean_path = app_config.logo_path.lstrip('/')
                        if clean_path.startswith('static/'):
                            clean_path = clean_path.replace('static/', '', 1)
                        logo_url = url_for('static', filename=clean_path, _external=True)
            
            success, message = send_password_reset_email(user, reset_url, logo_url)
            if not success:
                # Log error internally but message to user is helpful for debugging if SMTP fails
                current_app.logger.error(f"Failed to send reset email: {message}")


        
        return redirect(url_for('auth.login'))
        
    return render_template('auth/forgot_password.html')

@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
@limiter.limit('5 per 15 minutes', methods=['POST'])
def reset_password(token):
    email = confirm_reset_token(token)
    if not email:
        flash('O link de recuperação é inválido ou expirou.', 'danger')
        return redirect(url_for('auth.forgot_password'))
        
    user = User.query.filter_by(email=email).first()
    if not user:
        flash('Usuário não encontrado.', 'danger')
        return redirect(url_for('auth.login'))
        
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if password != confirm_password:
            flash('As senhas não coincidem.', 'danger')
            return render_template('auth/reset_password.html', token=token)

        if not is_password_strong(password):
            flash(PASSWORD_POLICY_MESSAGE, 'danger')
            return render_template('auth/reset_password.html', token=token)
            
        user.set_password(password)
        db.session.commit()
        
        # Log password reset
        from app.utils.audit import log_action
        log_action(
            action='PASSWORD_RESET',
            resource_type='User',
            resource_id=user.id,
            resource_name=user.email
        )
        
        flash('Sua senha foi atualizada com sucesso! Agora você pode fazer login.', 'success')
        return redirect(url_for('auth.login'))
        
    return render_template('auth/reset_password.html', token=token)

