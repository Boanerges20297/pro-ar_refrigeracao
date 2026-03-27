from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.models.equipment import Equipment
from app.models.client import Client
from app import db
from flask_jwt_extended import jwt_required
from app.utils.decorators import roles_required

equip_bp = Blueprint('equipment', __name__)

@equip_bp.route('/')
@roles_required('admin', 'technician')
def index():
    equipments = Equipment.query.all()
    return render_template('equipment/index.html', equipments=equipments)

@equip_bp.route('/view/<serial_number>')
@roles_required('admin', 'technician')
def view_by_serial(serial_number):
    equip = Equipment.query.filter_by(serial_number=serial_number).first()
    if not equip:
        flash(f'Equipamento com número de série/código {serial_number} não encontrado.', 'danger')
        return redirect(url_for('equipment.index'))

    return render_template('equipment/view.html', equip=equip)

@equip_bp.route('/add', methods=['GET', 'POST'])
@roles_required('admin', 'technician')
def add():
    clients = Client.query.all()
    if request.method == 'POST':
        name = request.form.get('name')
        brand = request.form.get('brand')
        model = request.form.get('model')
        raw_serial = request.form.get('serial_number')
        serial_number = raw_serial.strip() if raw_serial and raw_serial.strip() != "" else None
        location = request.form.get('location')
        client_id = request.form.get('client_id')

        equip = Equipment(name=name, brand=brand, model=model, serial_number=serial_number, location=location, client_id=client_id)
        db.session.add(equip)
        db.session.commit()
        flash('Equipamento adicionado com sucesso!', 'success')
        return redirect(url_for('equipment.index'))
    return render_template('equipment/add.html', clients=clients)
