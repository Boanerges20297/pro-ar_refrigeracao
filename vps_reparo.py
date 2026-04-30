from app import create_app, db
from sqlalchemy import text

app = create_app()
with app.app_context():
    try:
        # Verifica o que tem no banco
        result = db.session.execute(text("SELECT * FROM alembic_version")).fetchall()
        print("Antes do reparo, o banco tinha:", result)

        # Deleta tudo e forca a versao base
        db.session.execute(text("DELETE FROM alembic_version"))
        db.session.execute(text("INSERT INTO alembic_version (version_num) VALUES ('cafd02fb47b0')"))
        db.session.commit()
        
        print("Agora o banco tem apenas cafd02fb47b0!")
    except Exception as e:
        print("Erro profundo:", e)
