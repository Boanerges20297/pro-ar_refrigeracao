from app import db
from app.models.finance import FinancialCategory, FinancialTransaction
from app.models.workorder import WorkOrder
from app.models.workorder_expense import WorkOrderExpense
from datetime import datetime

def get_or_create_category(name, type):
    category = FinancialCategory.query.filter_by(name=name, type=type).first()
    if not category:
        category = FinancialCategory(name=name, type=type)
        db.session.add(category)
        db.session.flush()
    return category

def sync_wo_to_finance(work_order):
    """Sincroniza uma Ordem de Serviço com o módulo financeiro (Receita)"""
    category = get_or_create_category('Receita de Serviço', 'revenue')
    
    transaction = FinancialTransaction.query.filter_by(
        work_order_id=work_order.id, 
        is_automated=True,
        work_order_expense_id=None
    ).first()
    
    if not transaction:
        transaction = FinancialTransaction(
            type='revenue',
            category_id=category.id,
            description=f'OS #{work_order.id} - {work_order.client.name}',
            amount=work_order.total_value,
            date=work_order.completed_date or work_order.created_at or datetime.utcnow(),
            status='paid' if work_order.is_paid else 'pending',
            work_order_id=work_order.id,
            is_automated=True
        )
        db.session.add(transaction)
    else:
        transaction.amount = work_order.total_value
        transaction.status = 'paid' if work_order.is_paid else 'pending'
        transaction.description = f'OS #{work_order.id} - {work_order.client.name}'
        if work_order.completed_date:
            transaction.date = work_order.completed_date
            
    db.session.commit()

def sync_expense_to_finance(expense):
    """Sincroniza uma despesa de OS com o módulo financeiro (Despesa)"""
    category = get_or_create_category('Material / Peças', 'expense')
    
    transaction = FinancialTransaction.query.filter_by(
        work_order_expense_id=expense.id,
        is_automated=True
    ).first()
    
    amount = expense.quantity * expense.unit_price
    
    if not transaction:
        transaction = FinancialTransaction(
            type='expense',
            category_id=category.id,
            description=f'Despesa OS #{expense.work_order_id}: {expense.description}',
            amount=amount,
            date=expense.created_at or datetime.utcnow(),
            status='paid', # Conforme solicitado: despesas de OS são consideradas pagas
            work_order_id=expense.work_order_id,
            work_order_expense_id=expense.id,
            is_automated=True
        )
        db.session.add(transaction)
    else:
        transaction.amount = amount
        transaction.description = f'Despesa OS #{expense.work_order_id}: {expense.description}'
        
    db.session.commit()

def delete_finance_sync(work_order_id=None, work_order_expense_id=None):
    """Remove transações sincronizadas se a fonte for excluída"""
    if work_order_expense_id:
        FinancialTransaction.query.filter_by(work_order_expense_id=work_order_expense_id, is_automated=True).delete()
    elif work_order_id:
        FinancialTransaction.query.filter_by(work_order_id=work_order_id, is_automated=True).delete()
    
    db.session.commit()

def run_retroactive_sync():
    """Importa todos os dados existentes de OS e Despesas para o financeiro"""
    # 1. Sync WorkOrders
    work_orders = WorkOrder.query.all()
    for wo in work_orders:
        sync_wo_to_finance(wo)
        
    # 2. Sync Expenses
    expenses = WorkOrderExpense.query.all()
    for exp in expenses:
        sync_expense_to_finance(exp)
    
    return len(work_orders), len(expenses)
