# bot/fx_rates.py
import logging
import httpx
import aiosqlite
import json
from datetime import datetime
from typing import Dict, Optional, Set

logger = logging.getLogger(__name__)

# Используем единый файл БД для всех данных бота, чтобы не плодить файлы.
DB_FILE = "user_data.db"
BASE_CURRENCY = "EUR"
# Основные валюты для ежедневного кэширования. USD убран как нерелевантный.
CURRENCIES_TO_CACHE = ["PLN", "UAH", "GBP", "CHF", "CZK", "HUF", "RON", "SEK", "NOK", "DKK", "TRY"]

# --- Управление HTTP-клиентом ---
_http_client: Optional[httpx.AsyncClient] = None

async def get_client() -> httpx.AsyncClient:
    """Возвращает синглтон экземпляра httpx.AsyncClient."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=10.0)
    return _http_client

async def close_client():
    """Корректно закрывает HTTP-клиент при остановке бота."""
    global _http_client
    if _http_client:
        await _http_client.aclose()
        _http_client = None
        logger.info("HTTP-клиент для fx_rates был успешно закрыт.")

# --- Работа с БД и API ---
async def init_db():
    """Инициализирует таблицу для кэширования курсов валют в общей БД."""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS fx_rates (
                date TEXT PRIMARY KEY,
                rates_json TEXT NOT NULL
            )
        """)
        await db.commit()
    logger.info("Таблица 'fx_rates' для кэша валют инициализирована.")

async def get_rates() -> Optional[Dict[str, float]]:
    """Получает курсы валют из кэша (SQLite) или через API, если кэш устарел."""
    today_str = datetime.now().strftime("%Y-%m-%d")

    # 1. Проверяем кэш в БД с обработкой ошибок
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT rates_json FROM fx_rates WHERE date = ?", (today_str,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    try:
                        rates = json.loads(row[0])
                        logger.info(f"Курсы валют за {today_str} найдены в кэше БД.")
                        return rates
                    except json.JSONDecodeError:
                        logger.error(f"Ошибка декодирования JSON из кэша БД для даты {today_str}. Данные будут запрошены заново.")
    except Exception as e:
        logger.error(f"Ошибка при доступе к кэшу БД fx_rates: {e}")

    # 2. Если в кэше нет, запрашиваем API
    logger.info("Курсы в кэше не найдены или устарели. Запрос к API...")
    try:
        client = await get_client()
        response = await client.get(f"https://api.exchangerate.host/latest?base={BASE_CURRENCY}&symbols={','.join(CURRENCIES_TO_CACHE)}")
        response.raise_for_status()
        data = response.json()

        if data.get("success") and "rates" in data:
            rates = data["rates"]
            # 3. Сохраняем свежие данные в кэш БД
            async with aiosqlite.connect(DB_FILE) as db:
                await db.execute("INSERT OR REPLACE INTO fx_rates (date, rates_json) VALUES (?, ?)", (today_str, json.dumps(rates)))
                await db.commit()
            logger.info(f"Свежие курсы валют за {today_str} сохранены в кэш БД.")
            return rates
        else:
            logger.error(f"API exchangerate.host не вернул успешный ответ: {data}")
            return None
    except Exception as e:
        logger.error(f"Ошибка при получении или сохранении курсов валют: {e}", exc_info=True)
        return None

async def format_rates(origin_currency: str, destination_currency: str) -> Optional[str]:
    """Форматирует строку с курсами валют с уточненной логикой."""
    if origin_currency == destination_currency:
        return None

    all_rates = await get_rates()
    if not all_rates:
        return None # Если нет данных, просто ничего не показываем

    symbols_to_display: Set[str] = set()

    if origin_currency != BASE_CURRENCY:
        symbols_to_display.add(origin_currency)
    if destination_currency != BASE_CURRENCY:
        symbols_to_display.add(destination_currency)

    # Показываем курс гривны, если в маршруте есть Польша (из-за большого кол-ва украинцев)
    if "PLN" in {origin_currency, destination_currency}:
        if "UAH" in CURRENCIES_TO_CACHE:
            symbols_to_display.add("UAH")

    if not symbols_to_display:
        return None

    parts = []
    for symbol in sorted(list(symbols_to_display)):
        rate = all_rates.get(symbol)
        if rate:
            # Улучшенное форматирование: без копеек для целых чисел >= 20
            if rate >= 20 and rate == int(rate):
                rate_str = f"{rate:.0f}"
            else:
                rate_str = f"{rate:.2f}"
            parts.append(f"1 {BASE_CURRENCY} = {rate_str} {symbol}")

    if not parts:
        return None

    return f"💱 { ' • '.join(parts) }\n"