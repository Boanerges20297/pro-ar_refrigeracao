from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app.models.client import Client
from app.models.equipment import Equipment
from app.models.user import User
from app import db
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.decorators import roles_required, get_technician_client_ids
from sqlalchemy import or_

clients_bp = Blueprint('clients', __name__)

@clients_bp.route('/')
@roles_required('admin', 'secretary', 'technician')
def index():
    # Get current user
    current_user_id = get_jwt_identity()
    current_user = User.query.get(current_user_id) if current_user_id else None
    search = (request.args.get('search') or '').strip()
    
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
                Client.address.ilike(search_term),
            )
        )

    clients = query.order_by(Client.name.asc()).all()
    
    return render_template('clients/index.html', clients=clients, search=search)

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
            query = query.filter(Client.id == None)

    search_term = f'%{query_str}%'
    clients = query.filter(
        or_(
            Client.name.ilike(search_term),
            Client.email.ilike(search_term),
            Client.phone.ilike(search_term),
            Client.address.ilike(search_term)
        )
    ).limit(10).all()
    
    results = [
        {
            'id': c.id,
            'name': c.name,
            'email': c.email,
            'phone': c.phone,
            'address': c.address
        } for c in clients
    ]
    return jsonify(results)
