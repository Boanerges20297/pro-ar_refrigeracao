from functools import wraps
from flask import redirect, url_for, flash
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
from app.models.user import User

def roles_required(*roles):
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

            if not user or user.role not in roles:
                flash("Você não tem permissão para acessar esta página.", "danger")
                # Redirect based on user's actual role or to login if user not found
                if user and user.role == 'admin':
                    return redirect(url_for("admin.dashboard"))
                elif user and user.role == 'technician':
                    return redirect(url_for("tech.dashboard"))
                else:
                    return redirect(url_for("auth.login"))

            return fn(*args, **kwargs)
        return decorator
    return wrapper
