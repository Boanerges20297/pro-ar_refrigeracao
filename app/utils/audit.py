from flask import request, g
from flask_jwt_extended import get_jwt_identity
from app.models.audit_log import AuditLog
from app.models.user import User
from app import db
import json

def log_action(action, resource_type, resource_id=None, resource_name=None, status='success', details=None, explicit_user_id=None):
    """
    Log an action to the AuditLog table.
    
    Args:
        action (str): Type of action (CREATE, READ, UPDATE, DELETE, LOGIN, LOGOUT, etc.)
        resource_type (str): Type of resource (WorkOrder, Client, Equipment, User, Service, etc.)
        resource_id (int): ID of the affected resource
        resource_name (str): Name or description of the resource
        status (str): 'success' or 'error'
        details (dict): Additional context information to store
    """
    try:
        user_id = explicit_user_id
        if user_id is None:
            try:
                user_id = get_jwt_identity()
            except Exception:
                user_id = None

        if not user_id:
            # For login/logout or unauthenticated actions, user_id might be None temporarily
            return

        if isinstance(user_id, str) and user_id.isdigit():
            user_id = int(user_id)
        
        ip_address = request.remote_addr if request else None
        user_agent = request.headers.get('User-Agent', '')[:255] if request else None
        
        details_json = json.dumps(details) if details else None
        
        audit_log = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            status=status,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details_json
        )
        
        db.session.add(audit_log)
        db.session.commit()
    except Exception as e:
        # Don't let logging errors break the application
        print(f"Error logging action: {e}")
        db.session.rollback()


def log_login(user_id, success=True, details=None):
    """Log a login attempt."""
    ip_address = request.remote_addr if request else None
    user_agent = request.headers.get('User-Agent', '')[:255] if request else None
    details_json = json.dumps(details or {}) if details else None
    
    try:
        audit_log = AuditLog(
            user_id=user_id,
            action='LOGIN',
            resource_type='User',
            resource_id=user_id,
            status='success' if success else 'error',
            ip_address=ip_address,
            user_agent=user_agent,
            details=details_json
        )
        db.session.add(audit_log)
        db.session.commit()
    except Exception as e:
        print(f"Error logging login: {e}")
        db.session.rollback()


def log_logout(user_id):
    """Log a logout."""
    ip_address = request.remote_addr if request else None
    user_agent = request.headers.get('User-Agent', '')[:255] if request else None
    
    try:
        audit_log = AuditLog(
            user_id=user_id,
            action='LOGOUT',
            resource_type='User',
            resource_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent
        )
        db.session.add(audit_log)
        db.session.commit()
    except Exception as e:
        print(f"Error logging logout: {e}")
        db.session.rollback()
