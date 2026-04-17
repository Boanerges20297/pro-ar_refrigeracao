#!/usr/bin/env python3
from app import create_app
from types import SimpleNamespace
from flask import render_template
from datetime import datetime
import os

app = create_app()
# Ensure output dir
os.makedirs('tmp', exist_ok=True)
# Provide a test request context so url_for/static links can be built
app.config.setdefault('SERVER_NAME', 'localhost')
with app.app_context():
    with app.test_request_context('/'):
        wo = SimpleNamespace(
        id=123,
        client=SimpleNamespace(name='Cliente Exemplo', phone='(11) 99999-0000', email='cliente@example.com', address='Rua A, 123'),
        equipment=SimpleNamespace(name='Ar Condicionado', serial_number='SN123', location='Sala'),
        service_type=SimpleNamespace(name='Manutenção'),
        technician=SimpleNamespace(name='Técnico Um'),
        created_at=datetime.now(),
        total_value=150.0,
        description='Troca de filtro e limpeza completa do equipamento.',
        status='Completed',
    )
        config = SimpleNamespace(company_name='Pronto Ar Refrigeração', logo_path='/static/img/logo.jpg', cnpj='12.345.678/0001-99', primary_color='#3b82f6')
        html = render_template('services/receipt.html', wo=wo, config=config, company_name=config.company_name, company_responsible_name='Técnico Um', company_responsible_role='Técnico', company_cnpj=config.cnpj, issued_at=datetime.now(), status_label='Concluída')
        with open('tmp/receipt_test.html','w',encoding='utf-8') as f:
            f.write(html)
print('WROTE tmp/receipt_test.html')
