from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.models.client import Client
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
