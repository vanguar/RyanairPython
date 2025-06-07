# bot/fx_rates.py
import logging
import httpx
import aiosqlite
import json
from datetime import datetime
from typing import Dict, Optional, Set

logger = logging.getLogger(__name__)

DB_FILE = "user_data.db"
BASE_CURRENCY = "EUR"
# ФИНАЛЬНЫЙ СПИСОК ВАЛЮТ, ПОДДЕРЖИВАЕМЫХ FRANKFURTER.DEV
CURRENCIES_TO_CACHE = ["PLN", "UAH", "GBP", "CHF", "CZK", "HUF", "RON", "SEK", "NOK", "DKK", "BGN"]

_http_client: Optional[httpx.AsyncClient] = None

async def get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None: _http_client = httpx.AsyncClient(timeout=10.0)
    return _http_client

async def close_client():
    global _http_client
    if _http_client:
        await _http_client.aclose()
        _http_client = None
        logger.info("HTTP-клиент для fx_rates был успешно закрыт.")

async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS fx_rates (date TEXT PRIMARY KEY, rates_json TEXT NOT NULL)")
        await db.commit()
    logger.info("Таблица 'fx_rates' для кэша валют инициализирована.")

async def get_rates() -> Optional[Dict[str, float]]:
    today_str = datetime.now().strftime("%Y-%m-%d")
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT rates_json FROM fx_rates WHERE date = ?", (today_str,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    try: return json.loads(row[0])
                    except json.JSONDecodeError: logger.error(f"Ошибка декодирования JSON из кэша БД для даты {today_str}.")
    except Exception as e: logger.error(f"Ошибка при доступе к кэшу БД fx_rates: {e}")

    logger.info("Курсы в кэше не найдены. Запрос к API frankfurter.dev...")
    try:
        client = await get_client()
        params = {"base": BASE_CURRENCY, "symbols": ",".join(CURRENCIES_TO_CACHE)}
        response = await client.get("https://api.frankfurter.dev/v1/latest", params=params)
        response.raise_for_status()
        data = response.json()
        if "rates" in data:
            rates = data["rates"]
            async with aiosqlite.connect(DB_FILE) as db:
                await db.execute("INSERT OR REPLACE INTO fx_rates (date, rates_json) VALUES (?, ?)", (today_str, json.dumps(rates)))
                await db.commit()
            logger.info(f"Свежие курсы валют от frankfurter.dev сохранены в кэш.")
            return rates
        else:
            logger.error(f"API frankfurter.dev не вернул ожидаемый ответ: {data}")
            return None
    except Exception as e:
        logger.error(f"Ошибка при получении или сохранении курсов валют: {e}", exc_info=True)
        return None

async def format_rates(origin_currency: str, destination_currency: str) -> Optional[str]:
    if origin_currency == destination_currency: return None
    all_rates = await get_rates()
    if not all_rates: return None

    symbols_to_display: Set[str] = set()
    if origin_currency != BASE_CURRENCY: symbols_to_display.add(origin_currency)
    if destination_currency != BASE_CURRENCY: symbols_to_display.add(destination_currency)
    if "PLN" in {origin_currency, destination_currency}:
        if "UAH" in CURRENCIES_TO_CACHE: symbols_to_display.add("UAH")

    if not symbols_to_display: return None
    
    parts = []
    for symbol in sorted(list(symbols_to_display)):
        rate = all_rates.get(symbol)
        if rate:
            rate_str = f"{rate:.0f}" if rate >= 20 and rate == int(rate) else f"{rate:.2f}"
            parts.append(f"1 {BASE_CURRENCY} = {rate_str} {symbol}")
    
    if not parts: return None
    
    return f"💱 { ' • '.join(parts) }\n"