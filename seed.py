from app import create_app, db
from app.models.user import User
from app.models.client import Client
from app.models.equipment import Equipment
from app.models.service import ServiceCatalog
from app.models.workorder import WorkOrder
from app.models.config import AppConfig
from app.models.license import License
from app.utils.license import get_instance_fingerprint
from datetime import datetime, timedelta
from license_api.security import ensure_keypair, sign_payload
import random

def seed_database():
    app = create_app()
    with app.app_context():
        # Clear existing data
        print("Clearing database...")
        db.drop_all()
        db.create_all()

        print("Seeding Config...")
        config = AppConfig(
            company_name='Pronto Ar Refrigeração',
            logo_path='/static/img/logo.jpg',
            primary_color='#3b82f6', # Azul
            secondary_color='#9ca3af', # Cinza
            background_color='#ffffff',
            text_color='#111827'
        )
        db.session.add(config)
        db.session.commit()

        print("Seeding License...")
        ensure_keypair()
        trial_issued_at = datetime.utcnow()
        trial_expires_at = trial_issued_at + timedelta(days=365)
        trial_payload = {
            'license_id': 'lic_seed_trial',
            'company_name': config.company_name,
            'status': 'trial',
            'license_type': 'subscription',
            'issued_at': trial_issued_at.isoformat(),
            'expires_at': trial_expires_at.isoformat(),
            'max_users': 12,
            'max_admin_users': 2,
            'max_secretary_users': 3,
            'instance_fingerprint': get_instance_fingerprint(),
            'features': ['reports', 'audit', 'maintenance', 'branding', 'email'],
            'metadata': {'plan': 'premium'},
        }
        license_record = License(
            license_key=sign_payload(trial_payload),
            status='active',
            company_name=config.company_name,
            instance_fingerprint=trial_payload['instance_fingerprint'],
            issued_at=trial_issued_at,
            activated_at=trial_issued_at,
            expires_at=trial_expires_at,
            last_validated_at=trial_issued_at,
            last_validation_status='active',
            max_users=trial_payload['max_users'],
            max_admin_users=trial_payload['max_admin_users'],
            max_secretary_users=trial_payload['max_secretary_users'],
            feature_flags='["reports", "audit", "maintenance", "branding", "email"]',
        )
        db.session.add(license_record)

        print("Seeding Users...")
        admin = User(name='Administrador', email='admin@prontoar.com', role='admin', permission_level='admin', job_title='Administrador', must_change_password=True)
        admin.set_password('prontoar123')

        tech1 = User(name='Carlos Técnico', email='carlos@prontoar.com', role='technician', specialty='Refrigeração')
        tech1.set_password('tech1234')

        tech2 = User(name='João Elétrica', email='joao@prontoar.com', role='technician', specialty='Elétrica')
        tech2.set_password('tech1234')

        db.session.add_all([admin, tech1, tech2])
        db.session.commit()

        print("Seeding Clients & Equipment...")
        clients = [
            Client(name='Empresa ABC Ltda', email='contato@abc.com', phone='(11) 99999-1111', address='Rua A, 123 - Centro'),
            Client(name='Supermercado XYZ', email='gerencia@xyz.com', phone='(11) 88888-2222', address='Av. B, 456 - Bairro Novo'),
            Client(name='Maria Souza', email='maria@email.com', phone='(11) 77777-3333', address='Rua C, 789 - Vila Velha')
        ]
        db.session.add_all(clients)
        db.session.commit()

        equipments = [
            Equipment(name='Ar Condicionado Split 12000 BTUs', brand='LG', model='Dual Inverter', serial_number='SN123456', location='Sala de Reuniões', client_id=clients[0].id),
            Equipment(name='Ar Condicionado Central', brand='Carrier', model='X Power', serial_number='SN987654', location='Loja Principal', client_id=clients[1].id),
            Equipment(name='Ar Condicionado Split 9000 BTUs', brand='Samsung', model='WindFree', serial_number='SN456123', location='Quarto Suíte', client_id=clients[2].id)
        ]
        db.session.add_all(equipments)
        db.session.commit()

        print("Seeding Service Catalog...")
        services = [
            ServiceCatalog(name='Limpeza Completa', description='Limpeza dos filtros, serpentina e bandeja', base_price=150.00, estimated_duration=60),
            ServiceCatalog(name='Carga de Gás', description='Recarga de fluido refrigerante', base_price=250.00, estimated_duration=90),
            ServiceCatalog(name='Instalação de Split', description='Instalação completa de equipamento novo', base_price=450.00, estimated_duration=180),
            ServiceCatalog(name='Manutenção Preventiva', description='Revisão geral do sistema', base_price=120.00, estimated_duration=45)
        ]
        db.session.add_all(services)
        db.session.commit()

        print("Seeding Work Orders...")
        now = datetime.utcnow()
        statuses = ['Completed', 'Pending', 'In Progress']

        for i in range(15):
            status = random.choice(statuses)
            client = random.choice(clients)
            # 50% chance of specific equipment vs general service
            equip = random.choice([e for e in equipments if e.client_id == client.id]) if random.random() > 0.5 and [e for e in equipments if e.client_id == client.id] else None
            service = random.choice(services)
            tech = random.choice([tech1, tech2]) if random.random() > 0.2 else None # 80% chance of having a tech assigned

            # Scatter dates over the last 30 days and next 7 days
            days_offset = random.randint(-30, 7)
            scheduled = now + timedelta(days=days_offset, hours=random.randint(9, 17))

            completed_date = None
            if status == 'Completed':
                completed_date = scheduled + timedelta(minutes=service.estimated_duration)
                if not tech:
                    tech = random.choice([tech1, tech2]) # Completed must have tech

            wo = WorkOrder(
                status=status,
                scheduled_date=scheduled,
                completed_date=completed_date,
                description=f'Observação para OS de {service.name} (Teste Automático)',
                total_value=service.base_price * random.uniform(0.9, 1.2), # Slight price variation
                paid_value=service.base_price if status == 'Completed' else 0,
                is_paid=(status == 'Completed'),
                client_id=client.id,
                equipment_id=equip.id if equip else None,
                service_id=service.id,
                technician_id=tech.id if tech else None
            )
            db.session.add(wo)

        db.session.commit()
        print("Database seeded successfully! You can login with:")
        print("Admin: admin@prontoar.com / prontoar123")
        print("Tech: carlos@prontoar.com / tech1234")

if __name__ == '__main__':
    seed_database()
