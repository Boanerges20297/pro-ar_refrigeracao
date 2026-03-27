from flask import Blueprint, render_template, request, redirect, url_for, flash, make_response
from app.models.user import User
from flask_jwt_extended import create_access_token, set_access_cookies, unset_jwt_cookies, jwt_required, get_jwt_identity

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            if not user.is_active:
                flash('Sua conta está inativa. Contate o administrador.', 'danger')
                return redirect(url_for('auth.login'))

            access_token = create_access_token(identity=str(user.id))

            # Determine where to redirect based on role
            if user.role == 'admin':
                redirect_url = url_for('admin.dashboard')
            else:
                redirect_url = url_for('tech.dashboard')

            resp = make_response(redirect(redirect_url))
            set_access_cookies(resp, access_token)
            return resp
        else:
            flash('Email ou senha inválidos.', 'danger')

    return render_template('auth/login.html')

@auth_bp.route('/logout')
def logout():
    resp = make_response(redirect(url_for('auth.login')))
    unset_jwt_cookies(resp)
    return resp
