from app import create_app, db
from sqlalchemy import text

app = create_app()
with app.app_context():
    result = db.session.execute(text("SELECT * FROM alembic_version")).fetchall()
    print("Alembic versions in DB:", result)
