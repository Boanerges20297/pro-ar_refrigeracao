from flask import Blueprint, abort, current_app, make_response, redirect, send_from_directory, url_for
import os
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
from app.models.user import User

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    try:
        verify_jwt_in_request(optional=True)
        current_user_id = get_jwt_identity()
        if current_user_id:
            user = User.query.get(current_user_id)
            if user and user.permission_level == 'admin':
                return redirect(url_for('admin.dashboard'))
            elif user and user.permission_level == 'secretary':
                return redirect(url_for('secretary.dashboard'))
            elif user:
                return redirect(url_for('tech.dashboard'))
    except Exception:
        pass

    return redirect(url_for('auth.login'))



@main_bp.route('/manifest.webmanifest')
def pwa_manifest():
    if not current_app.config.get('PWA_ENABLED', False):
        abort(404)
    response = make_response(send_from_directory(
        os.path.join(current_app.static_folder, 'pwa'),
        'manifest.webmanifest',
        mimetype='application/manifest+json',
    ))
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@main_bp.route('/sw.js')
def pwa_service_worker():
    # Desativar PWA entrega um worker de limpeza aos clientes ja instalados.
    filename = 'sw.js' if current_app.config.get('PWA_ENABLED', False) else 'sw-disable.js'
    response = make_response(send_from_directory(
        os.path.join(current_app.static_folder, 'pwa'),
        filename,
        mimetype='application/javascript',
    ))
    response.headers['Cache-Control'] = 'no-store, max-age=0'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Service-Worker-Allowed'] = '/'
    return response
