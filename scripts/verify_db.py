from app import create_app, db
from sqlalchemy import text

app = create_app()
with app.app_context():
    try:
        # Check current columns in user table
        result = db.session.execute(text("PRAGMA table_info(user);")).fetchall()
        columns = [row[1] for row in result]
        print("Columns in user table:", columns)
        
        # Also let's print the DB URI
        print("Database URI:", app.config['SQLALCHEMY_DATABASE_URI'])
    except Exception as e:
        print("Error:", e)
