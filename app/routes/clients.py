from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from app.models.client import Client
from app.models.equipment import Equipment
from app.models.user import User
from app import db
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.decorators import roles_required, get_technician_client_ids
from sqlalchemy import or_, func
from app.utils.text import remove_accents

clients_bp = Blueprint('clients', __name__)

@clients_bp.route('/')
@roles_required('admin', 'secretary', 'technician')
def index():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    if per_page not in [10, 20, 50]:
        per_page = 10
    search = (request.args.get('search') or '').strip()
    
    # Get current user
    current_user_id = get_jwt_identity()
    current_user = User.query.get(current_user_id) if current_user_id else None
    
    # Check if user is technician
    is_technician = current_user and current_user.permission_level == 'user'

    query = Client.query
    
    if is_technician:
        # Técnico vê apenas clientes que atendeu
        client_ids = get_technician_client_ids(current_user.id)
        if client_ids:
            query = query.filter(Client.id.in_(client_ids))
        else:
            query = query.filter(Client.id == None)

    if search:
        search_term = f'%{search}%'
        query = query.filter(
            or_(
                Client.name.ilike(search_term),
                Client.email.ilike(search_term),
                Client.phone.ilike(search_term),
                Client.address.ilike(search_term)
            )
        )

    pagination = query.order_by(Client.name.asc()).paginate(page=page, per_page=per_page)
    clients = pagination.items
    
    return render_template('clients/index.html', 
                           clients=clients, 
                           pagination=pagination, 
                           search=search, 
                           per_page=per_page)

@clients_bp.route('/delete/<int:id>', methods=['POST'])
@roles_required('admin')
def delete(id):
    client = Client.query.get_or_404(id)
    try:
        # Check if client has related data that would prevent deletion
        if client.equipments or client.work_orders:
            # For safety, we could prevent deletion here, but the DB will catch it anyway.
            # I'll try to delete and handle the exception if it fails due to FK constraints.
            pass
            
        db.session.delete(client)
        db.session.commit()
        flash('Cliente excluído com sucesso.', 'success')
    except Exception as e:
        db.session.rollback()
        # Common error is ForeignKeyViolation
        flash('Não foi possível excluir o cliente pois ele possui equipamentos ou ordens de serviço vinculadas.', 'danger')
        current_app.logger.error(f"Erro ao excluir cliente: {str(e)}")
    return redirect(url_for('clients.index'))

@clients_bp.route('/add', methods=['GET', 'POST'])
@roles_required('admin', 'secretary')
def add():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        address = request.form.get('address')

        client = Client(name=name, email=email, phone=phone, address=address)
        db.session.add(client)
        db.session.commit()
        flash('Cliente adicionado com sucesso!', 'success')
        return redirect(url_for('clients.index'))
    return render_template('clients/add.html')

@clients_bp.route('/edit/<int:id>', methods=['GET', 'POST'])
@roles_required('admin', 'secretary')
def edit(id):
    client = Client.query.get_or_404(id)
    if request.method == 'POST':
        client.name = request.form.get('name')
        client.email = request.form.get('email')
        client.phone = request.form.get('phone')
        client.address = request.form.get('address')
        db.session.commit()
        flash('Cliente atualizado com sucesso!', 'success')
        return redirect(url_for('clients.index'))
    return render_template('clients/edit.html', client=client)

@clients_bp.route('/api/<int:client_id>/equipment')
@roles_required('admin', 'secretary', 'technician')
def api_get_equipment(client_id):
    client = Client.query.get_or_404(client_id)
    current_user_id = get_jwt_identity()
    current_user = User.query.get(current_user_id) if current_user_id else None

    is_technician = current_user and current_user.permission_level == 'user'
    if is_technician:
        client_ids = get_technician_client_ids(current_user.id)
        if client.id not in client_ids:
            return jsonify({'message': 'Acesso negado.'}), 403

    equipments = []
    for eq in client.equipments:
        equipments.append({
            'id': eq.id,
            'name': eq.name,
            'brand': eq.brand,
            'model': eq.model,
            'serial_number': eq.serial_number,
            'location': eq.location,
            'view_url': url_for('equipment.view_by_serial', serial_number=eq.serial_number or eq.id)
        })
    return jsonify({'client_name': client.name, 'equipments': equipments})

@clients_bp.route('/search')
@roles_required('admin', 'secretary', 'technician')
def search_clients():
    query_str = request.args.get('q', '').strip()
    if not query_str:
        return jsonify([])
    
    # Get current user
    current_user_id = get_jwt_identity()
    current_user = User.query.get(current_user_id) if current_user_id else None
    is_technician = current_user and current_user.permission_level == 'user'

    query = Client.query
    if is_technician:
        client_ids = get_technician_client_ids(current_user.id)
        if client_ids:
            query = query.filter(Client.id.in_(client_ids))
        else:
            return jsonify([])

    # Fetch all relevant clients to filter in Python (more robust for accents/engines)
    # We order by created_at desc to show newest first
    all_clients = query.order_by(Client.created_at.desc()).all()
    
    q_norm = remove_accents(query_str)
    results = []
    
    for c in all_clients:
        # Check name, email, phone, address with normalization
        searchable_text = f"{c.name} {c.email or ''} {c.phone or ''} {c.address or ''}"
        if q_norm in remove_accents(searchable_text):
            results.append({
                'id': c.id,
                'name': c.name,
                'email': c.email,
                'phone': c.phone,
                'address': c.address
            })
            if len(results) >= 10:
                break
    
    response = jsonify(results)
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response
