"""Área de usuário comum com privilégios mínimos.

O perfil comum não é técnico e não recebe autorização para consultar
dados comerciais, equipamentos ou ordens de serviço de outros usuários.
"""
from flask import Blueprint, render_template
from flask_jwt_extended import get_jwt_identity

from app.models.user import User
from app.utils.decorators import roles_required

common_portal_bp = Blueprint('common_portal', __name__, url_prefix='/common')


@common_portal_bp.route('/dashboard')
@roles_required('common')
def dashboard():
    user = User.query.get_or_404(get_jwt_identity())
    return render_template('common/dashboard.html', user=user)
