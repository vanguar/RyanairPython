import sqlite3
import os

# Путь к БД относительно папки, где лежит скрипт
DB_PATH = os.path.join('bot', 'user_search_history.db')

def migrate():
    """Добавляет колонку 'username' в таблицу 'users', если её ещё нет."""
    if not os.path.exists(DB_PATH):
        print(f"Файл базы данных не найден по пути: {DB_PATH}")
        print("База данных будет создана с новой структурой при первом запуске бота. Миграция не требуется.")
        return

    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        
        # 1. Проверяем, существует ли уже колонка
        cur.execute("PRAGMA table_info(users)")
        columns = [info[1] for info in cur.fetchall()]
        
        if 'username' in columns:
            print("Колонка 'username' уже существует в таблице 'users'. Миграция не требуется.")
            return

        # 2. Если колонки нет, добавляем её
        cur.execute("ALTER TABLE users ADD COLUMN username TEXT;")
        con.commit()
        print("Успешно добавлена колонка 'username' в таблицу 'users'.")

    except sqlite3.Error as e:
        print(f"Произошла ошибка SQLite во время миграции: {e}")
    except Exception as e:
        print(f"Произошла непредвиденная ошибка: {e}")
    finally:
        if 'con' in locals() and con:
            con.close()

if __name__ == "__main__":
    print(f"Запускаю миграцию базы данных: {DB_PATH}")
    # Перед запуском этого скрипта остановите вашего бота!
    migrate()
    print("Миграция завершена.")