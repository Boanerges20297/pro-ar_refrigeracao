from app import create_app, db
from sqlalchemy import text

app = create_app()
with app.app_context():
    db.session.execute(text("INSERT INTO alembic_version (version_num) VALUES ('c9a3fd93c9c5')"))
    db.session.commit()
    print("Alembic version set manually to c9a3fd93c9c5!")
