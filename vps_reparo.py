import os
from app import create_app, db
from sqlalchemy import text

app = create_app()
with app.app_context():
    try:
        # Verifica o que tem no banco
        result = db.session.execute(text("SELECT * FROM alembic_version")).fetchall()
        print("Banco (alembic_version) ->", result)

        print("\nArquivos na pasta migrations/versions:")
        versions_dir = 'migrations/versions'
        for root, dirs, files in os.walk(versions_dir):
            for file in files:
                if file.endswith('.py') or file.endswith('.pyc'):
                    print(file)
                    
        print("\nLendo arquivos para achar quem tem down_revision = '1a2b3c4d5e6f'...")
        for file in os.listdir(versions_dir):
            if file.endswith('.py'):
                with open(os.path.join(versions_dir, file), 'r') as f:
                    content = f.read()
                    if '1a2b3c4d5e6f' in content:
                        print(f"ACHEI A REFERENCIA NO ARQUIVO: {file}")

    except Exception as e:
        print("Erro:", e)
