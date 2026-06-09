import sqlite3
import os

def update_db():
    db_path = 'instance/pronto_ar.db' # Caminho correto do SQLite no projeto
    if not os.path.exists(db_path):
        # Tenta procurar em outros locais comuns se não achar
        if os.path.exists('pronto_ar.db'):
            db_path = 'pronto_ar.db'
        elif os.path.exists('instance/pro_ar.db'):
            db_path = 'instance/pro_ar.db'
        else:
            print("Banco de dados não encontrado. Verifique o caminho.")
            return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print(f"Atualizando banco de dados: {db_path}")

    # Adicionar coluna must_change_password
    try:
        cursor.execute("ALTER TABLE user ADD COLUMN must_change_password BOOLEAN DEFAULT 0 NOT NULL")
        print("Coluna 'must_change_password' adicionada.")
    except sqlite3.OperationalError:
        print("Coluna 'must_change_password' já existe ou erro ao adicionar.")

    # Adicionar coluna client_id
    try:
        cursor.execute("ALTER TABLE user ADD COLUMN client_id INTEGER REFERENCES client(id)")
        print("Coluna 'client_id' adicionada.")
    except sqlite3.OperationalError:
        print("Coluna 'client_id' já existe ou erro ao adicionar.")

    conn.commit()
    conn.close()
    print("Atualização concluída.")

if __name__ == "__main__":
    update_db()
