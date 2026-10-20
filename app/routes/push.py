import json
from datetime import datetime, time, timedelta

from flask import Blueprint, current_app, jsonify, render_template, request
from flask_jwt_extended import get_jwt_identity

from app import db
from app.models.push_notification import PushSubscription
from app.models.user import User
from app.utils.decorators import roles_required


push_bp = Blueprint('push', __name__, url_prefix='/notifications')


@push_bp.route('/preferences')
@roles_required('admin', 'secretary', 'technician', 'client')
def preferences():
    return render_template('push/preferences.html')


@push_bp.route('/vapid-public-key')
@roles_required('admin', 'secretary', 'technician', 'client')
def vapid_public_key():
    key = current_app.config.get('VAPID_PUBLIC_KEY')
    if not key or not current_app.config.get('PWA_ENABLED', False):
        return jsonify({'enabled': False}), 503
    return jsonify({'enabled': True, 'publicKey': key})


@push_bp.route('/subscribe', methods=['POST'])
@roles_required('admin', 'secretary', 'technician', 'client')
def subscribe():
    if not current_app.config.get('VAPID_PUBLIC_KEY') or not current_app.config.get('VAPID_PRIVATE_KEY'):
        return jsonify({'ok': False, 'message': 'Notificações push não estão configuradas no servidor.'}), 503
    data = request.get_json(silent=True) or {}
    subscription = data.get('subscription')
    endpoint = subscription.get('endpoint') if isinstance(subscription, dict) else None
    if not endpoint or not isinstance(subscription.get('keys'), dict):
        return jsonify({'ok': False, 'message': 'Inscrição inválida.'}), 400

    user = User.query.get_or_404(get_jwt_identity())
    row = PushSubscription.query.filter_by(endpoint=endpoint).first()
    if row and row.user_id != user.id:
        return jsonify({'ok': False, 'message': 'Esta inscrição já está vinculada a outra conta.'}), 409
    if row:
        row.subscription_json = json.dumps(subscription)
    else:
        db.session.add(PushSubscription(user_id=user.id, endpoint=endpoint, subscription_json=json.dumps(subscription)))
    db.session.commit()
    return jsonify({'ok': True})


@push_bp.route('/unsubscribe', methods=['POST'])
@roles_required('admin', 'secretary', 'technician', 'client')
def unsubscribe():
    data = request.get_json(silent=True) or {}
    endpoint = (data.get('endpoint') or '').strip()
    if endpoint:
        PushSubscription.query.filter_by(user_id=get_jwt_identity(), endpoint=endpoint).delete()
        db.session.commit()
    return jsonify({'ok': True})


@push_bp.route('/today')
@roles_required('admin', 'secretary', 'technician')
def today_schedule():
    from sqlalchemy import and_
    from app.models.workorder import WorkOrder
    from app.utils.push_notifications import _local_zone

    user = User.query.get_or_404(get_jwt_identity())
    today = datetime.now(_local_zone()).date()
    start = datetime.combine(today, time.min)
    end = datetime.combine(today + timedelta(days=1), time.min)
    query = WorkOrder.query.filter(
        WorkOrder.scheduled_date >= start,
        WorkOrder.scheduled_date < end,
        WorkOrder.status.in_(['Pending', 'In Progress']),
    )
    if user.permission_level == 'user':
        query = query.filter(WorkOrder.technician_id == user.id)
    workorders = query.order_by(WorkOrder.scheduled_date.asc()).all()
    return jsonify({
        'date': today.isoformat(),
        'services': [{
            'id': wo.id,
            'client': wo.client.name if wo.client else 'Cliente',
            'time': wo.scheduled_date.strftime('%H:%M'),
            'service': wo.service_type.name if wo.service_type else 'Serviço',
            'url': f'/services/view/{wo.id}',
        } for wo in workorders],
    })
