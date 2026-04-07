from flask import Blueprint, redirect, url_for
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
