from app import create_app, db
from sqlalchemy import text

app = create_app()
with app.app_context():
    try:
        # Tenta atualizar primeiro, caso a tabela tenha linhas
        db.session.execute(text("UPDATE alembic_version SET version_num='cafd02fb47b0'"))
        db.session.commit()
        print("Versao ajustada com UPDATE!")
    except Exception as e:
        print("Erro no update:", e)
