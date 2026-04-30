import sys
import os

# Adiciona o diretório raiz ao path para encontrar o módulo 'app'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from app.models.user import User
from app.models.client import Client

def migrate():
    app = create_app()
    with app.app_context():
        # Cria as tabelas caso não existam (necessário para a tabela de associação)
        db.create_all()
        
        print("Starting migration of user-client associations...")
        users_with_clients = User.query.filter(User.client_id.isnot(None)).all()
        
        migrated_count = 0
        for user in users_with_clients:
            # Check if association already exists
            client = Client.query.get(user.client_id)
            if client and client not in user.clients:
                user.clients.append(client)
                migrated_count += 1
        
        db.session.commit()
        print(f"Migration completed. {migrated_count} associations migrated.")

if __name__ == '__main__':
    migrate()
