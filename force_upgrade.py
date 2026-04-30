from app import create_app, db
from sqlalchemy import text

app = create_app()
with app.app_context():
    try:
        # Adicionar coluna CPF
        db.session.execute(text("ALTER TABLE user ADD COLUMN cpf VARCHAR(14);"))
        print("Coluna 'cpf' adicionada.")
        
        # Adicionar constraint UNIQUE no CPF
        db.session.execute(text("CREATE UNIQUE INDEX uq_user_cpf ON user (cpf);"))
        print("Restrição UNIQUE adicionada ao 'cpf'.")
    except Exception as e:
        print("Aviso CPF:", e)

    try:
        # Adicionar coluna Phone
        db.session.execute(text("ALTER TABLE user ADD COLUMN phone VARCHAR(20);"))
        print("Coluna 'phone' adicionada.")
    except Exception as e:
        print("Aviso Phone:", e)
        
    db.session.commit()
    print("Força bruta concluída com sucesso! Banco atualizado.")
