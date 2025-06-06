# bot/user_stats.py
import aiosqlite
import os
import logging
from datetime import datetime, timedelta

log = logging.getLogger(__name__)
# Используем ту же самую базу данных, что и для истории поиска
DB_PATH = os.path.join(os.path.dirname(__file__), 'user_search_history.db')

CREATE_USERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id      INTEGER PRIMARY KEY,
    first_seen   TIMESTAMP NOT NULL,
    last_seen    TIMESTAMP NOT NULL
);
"""

async def init_db():
    """Инициализирует таблицу users в базе данных."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(CREATE_USERS_TABLE_SQL)
            await db.commit()
            log.info("Таблица 'users' для статистики готова.")
    except Exception as e:
        log.error(f"Ошибка при инициализации таблицы 'users': {e}", exc_info=True)


async def touch_user(user_id: int):
    """
    Регистрирует нового пользователя или обновляет время последнего визита (last_seen) для существующего.
    Вызывается при каждом использовании команды /start.
    """
    if not user_id:
        return
    now = datetime.utcnow()
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # Если user_id уже есть, обновится только поле last_seen. Если нет - создастся новая запись.
            await db.execute(
                """
                INSERT INTO users(user_id, first_seen, last_seen) VALUES(?,?,?)
                ON CONFLICT(user_id) DO UPDATE SET last_seen=excluded.last_seen
                """,
                (user_id, now, now)
            )
            await db.commit()
    except Exception as e:
        log.error(f"Ошибка в touch_user для user_id {user_id}: {e}", exc_info=True)


# Словарь с SQL-условиями для разных периодов
PERIOD_SQL_WHERE = {
    "day": "first_seen >= datetime('now', '-1 day', 'localtime')",
    "week": "first_seen >= datetime('now', '-7 days', 'localtime')",
    "month": "first_seen >= datetime('now', '-30 days', 'localtime')", # Используем 30 дней для простоты
    "total": "1=1"  # Условие, которое всегда истинно, для подсчета всех записей
}

async def count_new_users(period: str) -> int:
    """Подсчитывает количество НОВЫХ пользователей за указанный период."""
    where_clause = PERIOD_SQL_WHERE.get(period)
    if not where_clause:
        return 0
    
    query = f"SELECT COUNT(*) FROM users WHERE {where_clause}"
    
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(query) as cursor:
                (count,) = await cursor.fetchone()
                return count
    except Exception as e:
        log.error(f"Ошибка при подсчете новых пользователей за период '{period}': {e}", exc_info=True)
        return 0