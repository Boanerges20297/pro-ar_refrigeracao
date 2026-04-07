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
                elif user and user.permission_level == 'secretary':
                    return redirect(url_for("secretary.dashboard"))
                elif user and user.permission_level == 'user':
                    return redirect(url_for("tech.dashboard"))
                else:
                    return redirect(url_for("auth.login"))

            return fn(*args, **kwargs)
        return decorator
    return wrapper

# Alias for backwards compatibility for now, so we don't break everything instantly
roles_required = permission_level_required


def get_technician_client_ids(technician_id):
    """
    Retorna uma lista de IDs de clientes que um técnico atendeu
    (baseado em ordens de serviço atribuídas a ele)
    """
    from app.models.workorder import WorkOrder
    from app import db
    from sqlalchemy import distinct
    
    client_ids = db.session.query(distinct(WorkOrder.client_id)).filter(
        WorkOrder.technician_id == technician_id
    ).all()
    
    return [cid[0] for cid in client_ids if cid[0] is not None]


def log_action_decorator(action, resource_type, get_resource_id=None, get_resource_name=None):
    """
    Decorator to automatically log actions to AuditLog.
    
    Args:
        action: Type of action (CREATE, READ, UPDATE, DELETE)
        resource_type: Type of resource (WorkOrder, Client, Equipment, etc.)
        get_resource_id: Function to extract resource_id from view function args/kwargs
        get_resource_name: Function to extract resource_name from view function args/kwargs
    
    Usage:
        @log_action_decorator('CREATE', 'WorkOrder', 
                            get_resource_id=lambda args, kwargs: kwargs.get('workorder_id'))
        def create_workorder():
            ...
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                from app.utils.audit import log_action
                resource_id = get_resource_id(args, kwargs) if get_resource_id else None
                resource_name = get_resource_name(args, kwargs) if get_resource_name else None
                
                # Execute the actual function
                result = fn(*args, **kwargs)
                
                # Log the action after successful execution
                log_action(
                    action=action,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    resource_name=resource_name,
                    status='success'
                )
                
                return result
            except Exception as e:
                # Log failed action
                try:
                    from app.utils.audit import log_action
                    resource_id = get_resource_id(args, kwargs) if get_resource_id else None
                    resource_name = get_resource_name(args, kwargs) if get_resource_name else None
                    log_action(
                        action=action,
                        resource_type=resource_type,
                        resource_id=resource_id,
                        resource_name=resource_name,
                        status='error',
                        details={'error': str(e)}
                    )
                except Exception:
                    pass
                raise
        return wrapper
    return decorator


def secretary_cannot_access(fn):
    """
    Decorator to prevent secretary from accessing sensitive data
    (financial info, photos, deletions)
    """
    @wraps(fn)
    def decorator(*args, **kwargs):
        try:
            verify_jwt_in_request(optional=False)
            current_user_id = get_jwt_identity()
            user = User.query.get(current_user_id)
            
            # Only secretaries are blocked; admin and technicians can access
            if user and user.permission_level == 'secretary':
                flash("Você não tem permissão para acessar esta funcionalidade.", "danger")
                return redirect(url_for("secretary.dashboard"))
            
            return fn(*args, **kwargs)
        except Exception:
            flash("Acesso não autorizado.", "danger")
            return redirect(url_for("auth.login"))
    
    return decorator

