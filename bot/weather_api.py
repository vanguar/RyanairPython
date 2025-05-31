# bot/weather_api.py
import httpx # Используем httpx для асинхронных запросов, как и ryanair-py
import logging
from bot import config # Для доступа к API ключу

logger = logging.getLogger(__name__)

# Упрощенная карта для основных погодных условий к эмодзи
WEATHER_EMOJI_MAP = {
    "clear": "☀️",  # Ясно
    "clouds": "☁️", # Облачно
    "rain": "🌧️",   # Дождь
    "drizzle": "🌦️",# Морось
    "snow": "❄️",   # Снег
    "thunderstorm": "⛈️", # Гроза
    "atmosphere": "🌫️", # Туман, дымка и т.д. (Mist, Smoke, Haze, Fog, Dust, Sand, Ash, Squall, Tornado)
    "unknown": "❓" # Неизвестно
}

def _map_weather_condition_to_emoji(weather_id: int) -> str:
    """Маппит ID погодного условия OpenWeatherMap на эмодзи."""
    if 200 <= weather_id <= 232: # Гроза
        return WEATHER_EMOJI_MAP["thunderstorm"]
    elif 300 <= weather_id <= 321: # Морось
        return WEATHER_EMOJI_MAP["drizzle"]
    elif 500 <= weather_id <= 531: # Дождь
        return WEATHER_EMOJI_MAP["rain"]
    elif 600 <= weather_id <= 622: # Снег
        return WEATHER_EMOJI_MAP["snow"]
    elif 701 <= weather_id <= 781: # Атмосферные явления (туман, дымка и т.д.)
        return WEATHER_EMOJI_MAP["atmosphere"]
    elif weather_id == 800: # Ясно
        return WEATHER_EMOJI_MAP["clear"]
    elif 801 <= weather_id <= 804: # Облака
        return WEATHER_EMOJI_MAP["clouds"]
    return WEATHER_EMOJI_MAP["unknown"]

async def get_weather_forecast(city_name: str) -> dict | None:
    """
    Получает текущий прогноз погоды для указанного города.
    Возвращает словарь с температурой и эмодзи или None в случае ошибки.
    """
    if not config.OPENWEATHER_API_KEY:
        logger.warning("API ключ для OpenWeatherMap не настроен.")
        return None
    if not city_name:
        logger.debug("Не указано имя города для прогноза погоды.")
        return None

    base_url = "http://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": city_name,
        "appid": config.OPENWEATHER_API_KEY,
        "units": "metric",  # Для градусов Цельсия
        "lang": "ru"        # Для описания погоды на русском (если понадобится)
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(base_url, params=params)
            response.raise_for_status()  # Вызовет исключение для HTTP ошибок (4xx, 5xx)
            data = response.json()

            if data.get("cod") != 200: 
                logger.error(f"Ошибка API OpenWeatherMap для города '{city_name}': {data.get('message', 'Неизвестная ошибка API')}")
                return None

            main_data = data.get("main")
            weather_data = data.get("weather")

            if main_data and weather_data and len(weather_data) > 0:
                temperature = main_data.get("temp")
                weather_id = weather_data[0].get("id") 
                city_name_from_api = data.get("name", city_name) 

                if temperature is not None and weather_id is not None:
                    emoji = _map_weather_condition_to_emoji(weather_id)
                    return {
                        "city": city_name_from_api,
                        "temperature": round(float(temperature)), 
                        "emoji": emoji
                    }
            logger.warning(f"Неполные данные о погоде для города '{city_name}': {data}")
            return None
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP ошибка при запросе погоды для '{city_name}': {e.response.status_code} - {e.response.text}")
        return None
    except httpx.RequestError as e:
        logger.error(f"Ошибка сети при запросе погоды для '{city_name}': {e}")
        return None
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при получении погоды для '{city_name}': {e}", exc_info=True)
        return None