# bot/user_history.py
import aiosqlite
import json
import logging
import os
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)
DB_NAME = os.path.join(os.path.dirname(__file__), 'user_search_history.db')

SEARCH_PARAM_KEYS = [
    'departure_airport_iata', 'arrival_airport_iata', 'departure_date', 'return_date',
    'flight_type_one_way', 'max_price', 'price_preference_choice',
    'current_search_flow', 'departure_country', 'departure_city_name',
    'arrival_country', 'arrival_city_name'
]

async def _get_db_connection():
    return await aiosqlite.connect(DB_NAME, timeout=10)

async def init_db():
    try:
        async with await _get_db_connection() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS search_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    search_parameters TEXT NOT NULL
                )
            ''')
            await conn.commit()
            logger.info(f"База данных {DB_NAME} инициализирована, таблица search_history проверена/создана.")
    except Exception as e:
        logger.error(f"Ошибка инициализации базы данных: {e}", exc_info=True)

async def save_search_parameters(user_id: int, search_params: Dict[str, Any]):
    if not user_id or not search_params:
        logger.warning("Попытка сохранить параметры поиска без user_id или с пустыми параметрами.")
        return

    params_to_save = {}
    for key in SEARCH_PARAM_KEYS:
        if key in search_params:
            value = search_params[key]
            if isinstance(value, Decimal):
                params_to_save[key] = str(value)
            else:
                params_to_save[key] = value
        else:
            params_to_save[key] = None
    
    if not params_to_save.get('departure_airport_iata') or not params_to_save.get('current_search_flow'):
        logger.warning(f"Недостаточно данных для сохранения поиска для user_id {user_id}. Отсутствуют departure_airport_iata или current_search_flow.")
        return

    params_json = json.dumps(params_to_save)
    try:
        async with await _get_db_connection() as conn:
            await conn.execute('''
                INSERT INTO search_history (user_id, search_parameters)
                VALUES (?, ?)
            ''', (user_id, params_json))
            await conn.commit()
            logger.info(f"Параметры поиска сохранены для user_id {user_id}.")
    except Exception as e:
        logger.error(f"Ошибка сохранения параметров поиска для user_id {user_id}: {e}", exc_info=True)

async def get_last_saved_search(user_id: int) -> Optional[Dict[str, Any]]:
    if not user_id:
        return None
    try:
        async with await _get_db_connection() as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute('''
                SELECT search_parameters FROM search_history
                WHERE user_id = ?
                ORDER BY timestamp DESC
                LIMIT 1
            ''', (user_id,)) as cursor:
                row = await cursor.fetchone()
            
            if row:
                params_json = row['search_parameters']
                loaded_params = json.loads(params_json)
                if 'max_price' in loaded_params and loaded_params['max_price'] is not None:
                    try:
                        loaded_params['max_price'] = Decimal(loaded_params['max_price'])
                    except Exception:
                        logger.warning(f"Не удалось конвертировать max_price обратно в Decimal для user {user_id}")
                        loaded_params['max_price'] = None
                logger.info(f"Извлечен последний сохраненный поиск для user_id {user_id}.")
                return loaded_params
            return None
    except Exception as e:
        logger.error(f"Ошибка извлечения последнего сохраненного поиска для user_id {user_id}: {e}", exc_info=True)
        return None

async def has_saved_searches(user_id: int) -> bool:
    if not user_id:
        return False
    try:
        async with await _get_db_connection() as conn:
            async with conn.execute('''
                SELECT 1 FROM search_history
                WHERE user_id = ?
                LIMIT 1
            ''', (user_id,)) as cursor:
                row = await cursor.fetchone()
            return row is not None
    except Exception as e:
        logger.error(f"Ошибка проверки наличия сохраненных поисков для user_id {user_id}: {e}", exc_info=True)
        return False