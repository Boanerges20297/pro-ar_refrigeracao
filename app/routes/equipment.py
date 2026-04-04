import os
import qrcode
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from app.models.equipment import Equipment
from app.models.client import Client
from app.models.maintenance import MaintenanceSchedule
from app import db
from datetime import datetime
from dateutil.relativedelta import relativedelta
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
    return render_template('equipment/view.html', equip=equip, now=datetime.utcnow())

@equip_bp.route('/add', methods=['GET', 'POST'])
@roles_required('admin', 'technician')
def add():
    clients = Client.query.all()
    if request.method == 'POST':
        name       = request.form.get('name')
        brand      = request.form.get('brand')
        model      = request.form.get('model')
        raw_serial = request.form.get('serial_number')
        serial_number = raw_serial.strip() if raw_serial and raw_serial.strip() != "" else None
        location   = request.form.get('location')
        client_id  = request.form.get('client_id')
        m_interval = request.form.get('maintenance_interval')
        maintenance_interval = int(m_interval) if m_interval else 6

        equip = Equipment(name=name, brand=brand, model=model,
                          serial_number=serial_number, location=location,
                          client_id=client_id, maintenance_interval=maintenance_interval)
        db.session.add(equip)
        db.session.commit()  # commit first to get equip.id

        # --- Automatic Maintenance Schedule ---
        next_date = datetime.utcnow() + relativedelta(months=maintenance_interval)
        schedule = MaintenanceSchedule(equipment_id=equip.id, 
                                       next_maintenance_date=next_date,
                                       description="Manutenção preventiva automática")
        db.session.add(schedule)

        # --- Generate QR Code ---
        qr_value = serial_number if serial_number else str(equip.id)
        qr_dir   = os.path.join(current_app.static_folder, 'img', 'qrcodes')
        os.makedirs(qr_dir, exist_ok=True)
        qr_filename = f'equip_{equip.id}.png'
        qr_filepath = os.path.join(qr_dir, qr_filename)

        img = qrcode.make(qr_value)
        img.save(qr_filepath)

        equip.qr_code_path = f'/static/img/qrcodes/{qr_filename}'
        db.session.commit()
        # --------------------------

        flash('Equipamento adicionado com sucesso! QR Code gerado.', 'success')
        return redirect(url_for('equipment.index'))
    return render_template('equipment/add.html', clients=clients)

@equip_bp.route('/edit/<int:id>', methods=['GET', 'POST'])
@roles_required('admin', 'technician')
def edit(id):
    equip = Equipment.query.get_or_404(id)
    clients = Client.query.all()
    if request.method == 'POST':
        equip.name = request.form.get('name')
        equip.brand = request.form.get('brand')
        equip.model = request.form.get('model')
        raw_serial = request.form.get('serial_number')
        new_serial = raw_serial.strip() if raw_serial and raw_serial.strip() != "" else None
        
        # If serial number changed, regenerate QR code
        if new_serial != equip.serial_number:
            equip.serial_number = new_serial
            qr_value = equip.serial_number if equip.serial_number else str(equip.id)
            qr_dir = os.path.join(current_app.static_folder, 'img', 'qrcodes')
            os.makedirs(qr_dir, exist_ok=True)
            qr_filename = f'equip_{equip.id}.png'
            img = qrcode.make(qr_value)
            img.save(os.path.join(qr_dir, qr_filename))
            equip.qr_code_path = f'/static/img/qrcodes/{qr_filename}'
        
        equip.location = request.form.get('location')
        equip.client_id = request.form.get('client_id')
        m_interval = request.form.get('maintenance_interval')
        if m_interval:
            equip.maintenance_interval = int(m_interval)
            
        db.session.commit()
        flash('Equipamento atualizado com sucesso!', 'success')
        return redirect(url_for('equipment.index'))
        
    return render_template('equipment/edit.html', equip=equip, clients=clients)

@equip_bp.route('/regenerate-qr/<int:equip_id>', methods=['POST'])
@roles_required('admin', 'technician')
def regenerate_qr(equip_id):
    equip = Equipment.query.get_or_404(equip_id)
    qr_value = equip.serial_number if equip.serial_number else str(equip.id)
    qr_dir   = os.path.join(current_app.static_folder, 'img', 'qrcodes')
    os.makedirs(qr_dir, exist_ok=True)
    qr_filename = f'equip_{equip.id}.png'
    img = qrcode.make(qr_value)
    img.save(os.path.join(qr_dir, qr_filename))
    equip.qr_code_path = f'/static/img/qrcodes/{qr_filename}'
    db.session.commit()
    flash('QR Code gerado com sucesso!', 'success')
    return redirect(url_for('equipment.view_by_serial', serial_number=equip.serial_number or str(equip.id)))
