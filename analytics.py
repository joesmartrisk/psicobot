import sqlite3
from datetime import datetime, timedelta

DB_FILE = "trader_bot.db"

def get_analytics():
    """
    Gera e imprime um relatório de análise de utilização do bot.
    """
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        # 1. Número total de usuários
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        print(f"--- Relatório de Utilização do Mentor Bot ---")
        print(f"\n[+] Total de Usuários Registrados: {total_users}")

        # 2. Usuários ativos na última semana
        one_week_ago = datetime.now() - timedelta(days=7)
        cursor.execute("SELECT COUNT(DISTINCT user_id) FROM interactions WHERE timestamp >= ?", (one_week_ago.isoformat(),))
        active_users_last_week = cursor.fetchone()[0]
        print(f"[+] Usuários Ativos na Última Semana: {active_users_last_week}")

        # 3. Frequência de uso por usuário
        print("\n--- Frequência de Uso por Usuário (Total de Interações) ---")
        cursor.execute("""
            SELECT p.name, u.user_id, COUNT(i.interaction_id)
            FROM users u
            JOIN user_profiles p ON u.user_id = p.user_id
            LEFT JOIN interactions i ON u.user_id = i.user_id
            GROUP BY u.user_id
            ORDER BY COUNT(i.interaction_id) DESC
        """)
        
        user_frequency = cursor.fetchall()

        if not user_frequency:
            print("Nenhuma interação registrada ainda.")
        else:
            for name, user_id, count in user_frequency:
                print(f"- {name} (ID: {user_id}): {count} interações")

        conn.close()

    except sqlite3.OperationalError as e:
        print(f"\nERRO: Não foi possível aceder à base de dados '{DB_FILE}'.")
        print(f"Detalhe: {e}")
        print("Verifique se o ficheiro da base de dados existe na mesma pasta que este script.")
    except Exception as e:
        print(f"Ocorreu um erro inesperado: {e}")

if __name__ == "__main__":
    get_analytics()
