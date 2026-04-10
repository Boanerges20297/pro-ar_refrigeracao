import os
import qrcode
from urllib.parse import unquote, urlparse
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, jsonify
from app.models.equipment import Equipment
from app.models.client import Client
from app.models.maintenance import MaintenanceSchedule
from app.models.user import User
from app import db
from datetime import datetime
from dateutil.relativedelta import relativedelta
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.decorators import roles_required, get_technician_client_ids
from sqlalchemy import or_

equip_bp = Blueprint('equipment', __name__)


def resolve_equipment_lookup(raw_reference):
    if raw_reference is None:
        return None, None

    reference = str(raw_reference).strip()
    if not reference:
        return None, None

    parsed = urlparse(reference)
    if parsed.scheme or parsed.netloc:
        path_parts = [part for part in parsed.path.split('/') if part]
        if path_parts:
            reference = path_parts[-1]

    reference = unquote(reference).strip().strip('/')
    if not reference:
        return None, None

    equipment = Equipment.query.filter_by(serial_number=reference).first()
    if equipment:
        return equipment, reference

    if reference.isdigit():
        equipment = Equipment.query.get(int(reference))
        if equipment:
            return equipment, reference

    return None, reference

@equip_bp.route('/')
@roles_required('admin', 'secretary', 'technician')
def index():
    # Get current user
    current_user_id = get_jwt_identity()
    current_user = User.query.get(current_user_id) if current_user_id else None
    search = (request.args.get('search') or '').strip()
    
    # Check if user is technician
    is_technician = current_user and current_user.permission_level == 'user'

    query = Equipment.query.join(Equipment.owner)
    
    if is_technician:
        # Técnico vê apenas equipamentos de clientes que atendeu
        client_ids = get_technician_client_ids(current_user.id)
        if client_ids:
            query = query.filter(Equipment.client_id.in_(client_ids))
        else:
            query = query.filter(Equipment.id == None)

    if search:
        search_term = f'%{search}%'
        query = query.filter(
            or_(
                Client.name.ilike(search_term),
                Equipment.name.ilike(search_term),
                Equipment.brand.ilike(search_term),
                Equipment.model.ilike(search_term),
                Equipment.serial_number.ilike(search_term),
                Equipment.location.ilike(search_term),
            )
        )

    equipments = query.order_by(Client.name.asc(), Equipment.name.asc()).all()
    
    return render_template('equipment/index.html', equipments=equipments, search=search)

@equip_bp.route('/view/<serial_number>')
@roles_required('admin', 'secretary', 'technician')
def view_by_serial(serial_number):
    # Get current user
    current_user_id = get_jwt_identity()
    current_user = User.query.get(current_user_id) if current_user_id else None
    
    equip, normalized_reference = resolve_equipment_lookup(serial_number)
    
    # Verificar se técnico tem acesso a este equipamento
    is_technician = current_user and current_user.permission_level == 'user'
    if is_technician:
        client_ids = get_technician_client_ids(current_user.id)
        if not equip or equip.client_id not in client_ids:
            flash('Você não tem acesso a este equipamento.', 'danger')
            return redirect(url_for('equipment.index'))
    
    if not equip:
        flash(f'Equipamento com número de série/código {normalized_reference or serial_number} não encontrado.', 'danger')
        return redirect(url_for('equipment.index'))
    return render_template('equipment/view.html', equip=equip, now=datetime.utcnow())

@equip_bp.route('/add', methods=['GET', 'POST'])
@roles_required('admin', 'secretary')
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
@roles_required('admin', 'secretary')
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
@roles_required('admin', 'secretary')
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

@equip_bp.route('/generate-qr-ajax/<int:equip_id>', methods=['POST'])
@roles_required('admin', 'secretary')
def generate_qr_ajax(equip_id):
    """Generate and save QR code via AJAX"""
    try:
        equip = Equipment.query.get_or_404(equip_id)
        
        # Generate QR code value
        qr_value = equip.serial_number if equip.serial_number else str(equip.id)
        
        # Create directory if not exists
        qr_dir = os.path.join(current_app.static_folder, 'img', 'qrcodes')
        os.makedirs(qr_dir, exist_ok=True)
        
        # Generate and save QR code
        qr_filename = f'equip_{equip.id}.png'
        qr_filepath = os.path.join(qr_dir, qr_filename)
        img = qrcode.make(qr_value)
        img.save(qr_filepath)
        
        # Update equipment with QR code path
        equip.qr_code_path = f'/static/img/qrcodes/{qr_filename}'
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'QR Code gerado e salvo com sucesso!',
            'qr_code_path': equip.qr_code_path
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Erro ao gerar QR Code: {str(e)}'
        }), 500
