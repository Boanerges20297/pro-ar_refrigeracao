from app import create_app, db
from sqlalchemy import text

app = create_app()
with app.app_context():
    db.session.execute(text("DELETE FROM alembic_version"))
    db.session.commit()
    print("Tabela alembic_version limpa com sucesso!")
