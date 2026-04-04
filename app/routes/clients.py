from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app.models.client import Client
from app.models.equipment import Equipment
from app import db
from flask_jwt_extended import jwt_required
from app.utils.decorators import roles_required

clients_bp = Blueprint('clients', __name__)

@clients_bp.route('/')
@roles_required('admin', 'technician')
def index():
    clients = Client.query.all()
    return render_template('clients/index.html', clients=clients)

@clients_bp.route('/add', methods=['GET', 'POST'])
@roles_required('admin', 'technician')
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

@clients_bp.route('/api/<int:client_id>/equipment')
@roles_required('admin', 'technician')
def api_get_equipment(client_id):
    client = Client.query.get_or_404(client_id)
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
