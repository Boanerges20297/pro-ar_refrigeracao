from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models.finance import FinancialCategory, FinancialTransaction
from app.models.user import User
from app.models.workorder import WorkOrder
from app import db
from app.utils.decorators import roles_required
from sqlalchemy import func, extract
from datetime import datetime, timedelta

finance_bp = Blueprint('finance', __name__)

def get_current_user():
    current_user_id = get_jwt_identity()
    return User.query.get(current_user_id) if current_user_id else None

@finance_bp.route('/')
@roles_required('admin')
def index():
    """Dashboard Financeiro"""
    today = datetime.utcnow().date()
    
    # Período padrão: mês atual
    start_date = today.replace(day=1)
    end_date = today
    
    # Filtro de período via query params
    period = request.args.get('period', 'month')
    if period == 'today':
        start_date = today
    elif period == 'year':
        start_date = today.replace(month=1, day=1)
    elif period == 'last_30_days':
        start_date = today - timedelta(days=30)
    
    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt = datetime.combine(end_date, datetime.max.time())

    # Métricas principais
    total_revenue = db.session.query(func.sum(FinancialTransaction.amount))\
        .filter(FinancialTransaction.type == 'revenue', FinancialTransaction.date >= start_dt, FinancialTransaction.date <= end_dt).scalar() or 0.0
    
    total_expense = db.session.query(func.sum(FinancialTransaction.amount))\
        .filter(FinancialTransaction.type == 'expense', FinancialTransaction.date >= start_dt, FinancialTransaction.date <= end_dt).scalar() or 0.0
    
    pending_revenue = db.session.query(func.sum(FinancialTransaction.amount))\
        .filter(FinancialTransaction.type == 'revenue', FinancialTransaction.status == 'pending', FinancialTransaction.date >= start_dt, FinancialTransaction.date <= end_dt).scalar() or 0.0
        
    cash_flow = total_revenue - total_expense

    # Dados para gráfico de pizza (Categorias)
    categories_data = db.session.query(FinancialCategory.name, func.sum(FinancialTransaction.amount))\
        .join(FinancialTransaction)\
        .filter(FinancialTransaction.date >= start_dt, FinancialTransaction.date <= end_dt)\
        .group_by(FinancialCategory.id).all()
    
    # Dados para gráfico de linha (Tendência Diária)
    # Se for "Hj", mostramos por hora. Se for mês/ano, por dia.
    if period == 'today':
        trend_query = db.session.query(
            extract('hour', FinancialTransaction.date).label('label'),
            func.sum(db.case((FinancialTransaction.type == 'revenue', FinancialTransaction.amount), else_=0)).label('revenue'),
            func.sum(db.case((FinancialTransaction.type == 'expense', FinancialTransaction.amount), else_=0)).label('expense')
        ).filter(FinancialTransaction.date >= start_dt, FinancialTransaction.date <= end_dt)\
        .group_by('label').all()
    else:
        # DB Agnostic grouping by date
        trend_query = db.session.query(
            func.date(FinancialTransaction.date).label('label'),
            func.sum(db.case((FinancialTransaction.type == 'revenue', FinancialTransaction.amount), else_=0)).label('revenue'),
            func.sum(db.case((FinancialTransaction.type == 'expense', FinancialTransaction.amount), else_=0)).label('expense')
        ).filter(FinancialTransaction.date >= start_dt, FinancialTransaction.date <= end_dt)\
        .group_by(func.date(FinancialTransaction.date)).order_by(func.date(FinancialTransaction.date)).all()
    
    # Prepara dados para JSON de forma segura
    trend_data_list = []
    for row in trend_query:
        label = row.label
        if hasattr(label, 'strftime'):
            label = label.strftime('%Y-%m-%d')
        trend_data_list.append({
            'label': str(label),
            'revenue': float(row.revenue or 0),
            'expense': float(row.expense or 0)
        })

    return render_template('admin/finance/dashboard.html',
                           total_revenue=total_revenue,
                           total_expense=total_expense,
                           pending_revenue=pending_revenue,
                           cash_flow=cash_flow,
                           categories_data=categories_data,
                           trend_data=trend_data_list,
                           period=period)

@finance_bp.route('/transactions')
@roles_required('admin')
def transactions():
    """Lista de todas as transações com filtros"""
    page = request.args.get('page', 1, type=int)
    type_filter = request.args.get('type')
    status_filter = request.args.get('status')
    category_id = request.args.get('category_id', type=int)
    
    query = FinancialTransaction.query
    
    if type_filter:
        query = query.filter_by(type=type_filter)
    if status_filter:
        query = query.filter_by(status=status_filter)
    if category_id:
        query = query.filter_by(category_id=category_id)
        
    transactions_pagination = query.order_by(FinancialTransaction.date.desc()).paginate(page=page, per_page=20)
    categories = FinancialCategory.query.order_by(FinancialCategory.name).all()
    
    return render_template('admin/finance/transactions.html',
                           pagination=transactions_pagination,
                           categories=categories,
                           type_filter=type_filter,
                           status_filter=status_filter,
                           selected_category_id=category_id)

@finance_bp.route('/transaction/add', methods=['GET', 'POST'])
@roles_required('admin')
def add_transaction():
    if request.method == 'POST':
        type = request.form.get('type')
        category_id = request.form.get('category_id')
        description = request.form.get('description')
        amount = float(request.form.get('amount') or 0)
        date_str = request.form.get('date')
        status = request.form.get('status')
        
        transaction = FinancialTransaction(
            type=type,
            category_id=category_id or None,
            description=description,
            amount=amount,
            date=datetime.strptime(date_str, '%Y-%m-%d') if date_str else datetime.utcnow(),
            status=status,
            is_automated=False
        )
        db.session.add(transaction)
        db.session.commit()
        flash('Lançamento realizado com sucesso!', 'success')
        return redirect(url_for('finance.transactions'))
        
    categories = FinancialCategory.query.order_by(FinancialCategory.name).all()
    return render_template('admin/finance/transaction_form.html', categories=categories, transaction=None, now=datetime.utcnow())

@finance_bp.route('/transaction/edit/<int:id>', methods=['GET', 'POST'])
@roles_required('admin')
def edit_transaction(id):
    transaction = FinancialTransaction.query.get_or_404(id)
    
    if request.method == 'POST':
        transaction.description = request.form.get('description')
        transaction.amount = float(request.form.get('amount') or 0)
        date_str = request.form.get('date')
        if date_str:
            transaction.date = datetime.strptime(date_str, '%Y-%m-%d')
        transaction.status = request.form.get('status')
        if not transaction.is_automated:
            transaction.type = request.form.get('type')
            transaction.category_id = request.form.get('category_id') or None
            
        db.session.commit()
        flash('Transação atualizada com sucesso!', 'success')
        return redirect(url_for('finance.transactions'))
        
    categories = FinancialCategory.query.order_by(FinancialCategory.name).all()
    return render_template('admin/finance/transaction_form.html', categories=categories, transaction=transaction, now=datetime.utcnow())

@finance_bp.route('/transaction/delete/<int:id>', methods=['POST'])
@roles_required('admin')
def delete_transaction(id):
    transaction = FinancialTransaction.query.get_or_404(id)
    if transaction.is_automated:
        flash('Não é possível excluir diretamente uma transação vinda de uma OS. Exclua a OS ou a despesa na OS correspondente.', 'danger')
        return redirect(url_for('finance.transactions'))
        
    db.session.delete(transaction)
    db.session.commit()
    flash('Transação excluída!', 'success')
    return redirect(url_for('finance.transactions'))

@finance_bp.route('/categories', methods=['GET', 'POST'])
@roles_required('admin')
def categories():
    """Gerenciamento de tipos de receita/despesa"""
    if request.method == 'POST':
        name = request.form.get('name')
        type = request.form.get('type')
        
        category = FinancialCategory(name=name, type=type)
        db.session.add(category)
        db.session.commit()
        flash('Categoria criada!', 'success')
        return redirect(url_for('finance.categories'))
        
    revenue_categories = FinancialCategory.query.filter_by(type='revenue').all()
    expense_categories = FinancialCategory.query.filter_by(type='expense').all()
    return render_template('admin/finance/categories.html', 
                           revenue_categories=revenue_categories, 
                           expense_categories=expense_categories)

@finance_bp.route('/category/add/api', methods=['POST'])
@roles_required('admin')
def add_category_api():
    """Endpoint para criação rápida de categoria via AJAX"""
    try:
        data = request.get_json() or {}
        name = data.get('name') or request.form.get('name')
        type = data.get('type') or request.form.get('type')
        
        if not name or not type:
            return jsonify({'success': False, 'message': 'Nome e Tipo são obrigatórios'}), 400
            
        category = FinancialCategory(name=name, type=type)
        db.session.add(category)
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'id': category.id, 
            'name': f"{category.name} ({'Receita' if category.type == 'revenue' else 'Despesa'})"
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@finance_bp.cli.command('sync')
def sync_finance_command():
    """Comando CLI para sincronização retroativa de OS e Despesas"""
    from app.utils.finance import run_retroactive_sync
    print("Iniciando sincronização retroativa...")
    wo_count, exp_count = run_retroactive_sync()
    print(f"Sincronização concluída: {wo_count} O.S. e {exp_count} Despesas processadas.")
