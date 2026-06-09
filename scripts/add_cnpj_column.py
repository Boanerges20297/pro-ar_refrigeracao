import sqlite3
import os

def update_db():
    # Detect the database path
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

    print(f"Atualizando banco de dados: {db_path}")

    # Adicionar coluna cnpj à tabela client
    try:
        cursor.execute("ALTER TABLE client ADD COLUMN cnpj VARCHAR(18)")
        print("Coluna 'cnpj' adicionada à tabela 'client'.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("Coluna 'cnpj' já existe na tabela 'client'.")
        else:
            print(f"Erro ao adicionar coluna 'cnpj': {e}")

    conn.commit()
    conn.close()
    print("Atualização concluída.")

if __name__ == "__main__":
    update_db()
