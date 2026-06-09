import sqlite3
import os

def check_schema():
    possible_paths = [
        'instance/pronto_ar.db',
        'pronto_ar.db',
        'instance/pro_ar.db',
        'pro_ar.db'
    ]
    
    db_path = None
    for path in possible_paths:
        if os.path.exists(path):
            db_path = path
            break
            
    if not db_path:
        print("Banco de dados não encontrado.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print(f"Verificando colunas da tabela 'user' em: {db_path}")
    cursor.execute("PRAGMA table_info(user)")
    columns = [row[1] for row in cursor.fetchall()]
    print(f"Colunas em 'user': {columns}")

    print(f"\nVerificando colunas da tabela 'client' em: {db_path}")
    cursor.execute("PRAGMA table_info(client)")
    columns = [row[1] for row in cursor.fetchall()]
    print(f"Colunas em 'client': {columns}")

    conn.close()

if __name__ == "__main__":
    check_schema()
