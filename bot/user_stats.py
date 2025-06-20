# bot/user_stats.py
import aiosqlite
import os
import logging
from datetime import datetime, timedelta

log = logging.getLogger(__name__)
# Используем ту же самую базу данных, что и для истории поиска
DB_PATH = os.path.join(os.path.dirname(__file__), 'user_search_history.db')

# --- ИЗМЕНЕНИЕ 1: Новая структура таблицы с полем 'username' ---
CREATE_USERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id      INTEGER PRIMARY KEY,
    username     TEXT,                -- <-- НОВОЕ ПОЛЕ ДЛЯ НИКНЕЙМА
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


# --- ИЗМЕНЕНИЕ 2: Модифицированная функция touch_user ---
async def touch_user(user_id: int, username: str | None):
    """
    Регистрирует нового пользователя или обновляет last_seen.
    Сохраняет или обновляет username, если он не пустой.
    """
    if not user_id:
        return
    now = datetime.utcnow()
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # ON CONFLICT обрабатывает новых и существующих пользователей одним запросом.
            # COALESCE гарантирует, что мы не затрём существующий username значением NULL,
            # если пользователь позже скроет свой @username.
            await db.execute(
                """
                INSERT INTO users (user_id, username, first_seen, last_seen)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE
                SET last_seen = excluded.last_seen,
                    username  = COALESCE(excluded.username, users.username)
                """,
                (user_id, username, now, now),
            )
            await db.commit()
    except Exception as e:
        log.error(f"Ошибка в touch_user для user_id {user_id}: {e}", exc_info=True)


# Словарь с SQL-условиями для разных периодов (остается без изменений)
PERIOD_SQL_WHERE = {
    "day": "first_seen >= datetime('now', '-1 day', 'localtime')",
    "week": "first_seen >= datetime('now', '-7 days', 'localtime')",
    "month": "first_seen >= datetime('now', '-30 days', 'localtime')",
    "total": "1=1"
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

# --- ИЗМЕНЕНИЕ 3: Новая функция для получения списка всех пользователей ---
async def get_all_users() -> list[tuple[int, str | None]]:
    """Возвращает список кортежей (user_id, username) для отчёта."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT user_id, username FROM users ORDER BY first_seen"
            ) as cur:
                return await cur.fetchall()
    except Exception as e:
        log.error(f"Не удалось получить список всех пользователей: {e}", exc_info=True)
        return []