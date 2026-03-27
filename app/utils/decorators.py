from functools import wraps
from flask import redirect, url_for, flash
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
from app.models.user import User

def permission_level_required(*levels):
    def wrapper(fn):
        @wraps(fn)
        def decorator(*args, **kwargs):
            try:
                # Tell JWT to skip its own CSRF check here, since we rely on Flask-WTF
                verify_jwt_in_request(optional=False)
            except Exception as e:
                flash("Por favor, faça login para acessar esta página.", "danger")
                return redirect(url_for("auth.login"))

            current_user_id = get_jwt_identity()
            user = User.query.get(current_user_id)

            # Map old role kwargs to permission_level if needed, but best is to update the calls.
            # 'technician' maps to 'user'
            allowed_levels = ['user' if l == 'technician' else l for l in levels]

            if not user or user.permission_level not in allowed_levels:
                flash("Você não tem permissão para acessar esta página.", "danger")
                # Redirect based on user's permission_level or to login if user not found
                if user and user.permission_level == 'admin':
                    return redirect(url_for("admin.dashboard"))
                elif user and user.permission_level == 'user':
                    return redirect(url_for("tech.dashboard"))
                else:
                    return redirect(url_for("auth.login"))

            return fn(*args, **kwargs)
        return decorator
    return wrapper

# Alias for backwards compatibility for now, so we don't break everything instantly
roles_required = permission_level_required
