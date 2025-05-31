# bot/weather_api.py
import httpx  # Используем httpx для асинхронных запросов
import logging
from datetime import datetime
from bot import config  # Для доступа к API ключу

logger = logging.getLogger(__name__)

# Упрощённая карта погодных условий к эмодзи
WEATHER_EMOJI_MAP = {
    "clear": "☀️",       # Ясно
    "clouds": "☁️",      # Облачно
    "rain": "🌧️",        # Дождь
    "drizzle": "🌦️",     # Морось
    "snow": "❄️",        # Снег
    "thunderstorm": "⛈️",# Гроза
    "atmosphere": "🌫️",  # Туман, дымка и т.д.
    "unknown": "❓"       # Неизвестно
}

def _map_weather_condition_to_emoji(weather_id: int) -> str:
    """
    Маппит ID погодного условия OpenWeatherMap на эмодзи.
    """
    if 200 <= weather_id <= 232:
        return WEATHER_EMOJI_MAP["thunderstorm"]
    elif 300 <= weather_id <= 321:
        return WEATHER_EMOJI_MAP["drizzle"]
    elif 500 <= weather_id <= 531:
        return WEATHER_EMOJI_MAP["rain"]
    elif 600 <= weather_id <= 622:
        return WEATHER_EMOJI_MAP["snow"]
    elif 701 <= weather_id <= 781:
        return WEATHER_EMOJI_MAP["atmosphere"]
    elif weather_id == 800:
        return WEATHER_EMOJI_MAP["clear"]
    elif 801 <= weather_id <= 804:
        return WEATHER_EMOJI_MAP["clouds"]
    return WEATHER_EMOJI_MAP["unknown"]

async def get_weather_with_forecast(city_name: str, target_dt: datetime) -> dict | None:
    """
    Возвращает погоду (текущую или прогноз) для заданного города и времени.
    - Если target_dt близок к текущему моменту (±3 часа), запрашивает текущую погоду (/weather).
    - Если target_dt дальше (до 5 дней), запрашивает 5-дневный прогноз (/forecast) 
      и выбирает ближайший по времени слот.
    Возвращает словарь:
    {
      "city": <имя города из API или переданное>,
      "temperature": <целая температура, округлённая>,
      "emoji": <символ погоды>,
      "type": "current" или "forecast",
      "dt": <datetime UTC, к которому привязан вывод>
    }
    В случае ошибки возвращает None.
    """
    if not config.OPENWEATHER_API_KEY:
        logger.warning("API ключ для OpenWeatherMap не настроен.")
        return None
    if not city_name:
        logger.debug("Не указано имя города для прогноза погоды.")
        return None

    now_utc = datetime.utcnow()
    # Разница в секундах между целевым временем и настоящим (UTC)
    diff_seconds = (target_dt.replace(tzinfo=None) - now_utc).total_seconds()

    try:
        async with httpx.AsyncClient() as client:
            # Если целевая дата в пределах ±3 часов, берем текущую погоду
            if abs(diff_seconds) <= 3 * 3600:
                url_current = "http://api.openweathermap.org/data/2.5/weather"
                params = {
                    "q": city_name,
                    "appid": config.OPENWEATHER_API_KEY,
                    "units": "metric",
                    "lang": "ru"
                }
                resp = await client.get(url_current, params=params)
                resp.raise_for_status()
                data = resp.json()

                if data.get("cod") != 200:
                    logger.error(f"Ошибка API OpenWeatherMap (current) для '{city_name}': {data.get('message', 'Неизвестная ошибка')}") 
                    return None

                main_data = data.get("main")
                weather_data = data.get("weather")
                if main_data and weather_data and len(weather_data) > 0:
                    temp = main_data.get("temp")
                    weather_id = weather_data[0].get("id")
                    city_from_api = data.get("name", city_name)
                    if temp is not None and weather_id is not None:
                        emoji = _map_weather_condition_to_emoji(weather_id)
                        return {
                            "city": city_from_api,
                            "temperature": round(float(temp)),
                            "emoji": emoji,
                            "type": "current",
                            "dt": now_utc
                        }
                logger.warning(f"Неполные данные (current) для города '{city_name}': {data}")
                return None

            # Иначе: target_dt дальше чем ±3 часа → запрашиваем 5-дневный прогноз
            url_forecast = "http://api.openweathermap.org/data/2.5/forecast"
            params = {
                "q": city_name,
                "appid": config.OPENWEATHER_API_KEY,
                "units": "metric",
                "lang": "ru"
            }
            resp = await client.get(url_forecast, params=params)
            resp.raise_for_status()
            data = resp.json()

            if data.get("cod") != "200" or "list" not in data:
                logger.error(f"Ошибка API OpenWeatherMap (forecast) для '{city_name}': {data.get('message', data)}")
                return None

            forecast_list = data["list"]  # Список слотов каждый 3 часа (обычно 40 элементов)
            best_item = None
            best_diff = None

            # Ищем элемент, у которого timestamp ближе всего к target_dt
            for item in forecast_list:
                item_dt = datetime.utcfromtimestamp(item.get("dt", 0))
                diff = abs((item_dt - target_dt).total_seconds())
                if best_diff is None or diff < best_diff:
                    best_diff = diff
                    best_item = item

            if best_item:
                main_data = best_item.get("main", {})
                weather_data = best_item.get("weather", [{}])
                if main_data and "temp" in main_data and weather_data and weather_data[0].get("id") is not None:
                    temp = main_data.get("temp")
                    weather_id = weather_data[0].get("id")
                    city_from_api = data.get("city", {}).get("name", city_name)
                    if temp is not None and weather_id is not None:
                        emoji = _map_weather_condition_to_emoji(weather_id)
                        return {
                            "city": city_from_api,
                            "temperature": round(float(temp)),
                            "emoji": emoji,
                            "type": "forecast",
                            "dt": datetime.utcfromtimestamp(best_item.get("dt", 0))
                        }
            logger.warning(f"Не найден подходящий слот (forecast) для города '{city_name}' и времени {target_dt}")
            return None

    except httpx.HTTPStatusError as e:
        status = e.response.status_code if e.response else "?"
        text = e.response.text if e.response else ""
        logger.error(f"HTTP ошибка при запросе погоды для '{city_name}': {status} - {text}")
        return None
    except httpx.RequestError as e:
        logger.error(f"Сетевая ошибка при запросе погоды для '{city_name}': {e}")
        return None
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при получении прогноза для '{city_name}': {e}", exc_info=True)
        return None
