import os

from dotenv import load_dotenv
load_dotenv()  # carrega o .env antes de qualquer config

from app import create_app

app = create_app()

if __name__ == '__main__':
    debug_enabled = os.environ.get('FLASK_DEBUG', '').strip().lower() in {'1', 'true', 'yes', 'on'}
    app.run(debug=debug_enabled, port=5000, host='0.0.0.0')
