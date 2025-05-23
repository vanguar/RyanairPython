# bot/config.py
import os
import json
import logging
from dotenv import load_dotenv

# Загрузка переменных окружения из .env файла
# Это полезно для локальной разработки
load_dotenv()

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_TELEGRAM_ID = os.getenv("ADMIN_TELEGRAM_ID") # Опционально

if not TELEGRAM_BOT_TOKEN:
    logger.critical("Переменная окружения TELEGRAM_BOT_TOKEN не установлена!")
    # В реальном приложении здесь можно было бы возбудить исключение или завершить работу
    # exit("Ошибка: TELEGRAM_BOT_TOKEN не найден.") # Раскомментируйте, если хотите жесткого завершения

# --- Загрузка данных о странах и аэропортах ---
COUNTRIES_DATA_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'countries_data.json')
COUNTRIES_DATA = {}

try:
    with open(COUNTRIES_DATA_PATH, 'r', encoding='utf-8') as f:
        COUNTRIES_DATA = json.load(f)
    if not COUNTRIES_DATA:
        logger.warning(f"Файл {COUNTRIES_DATA_PATH} пуст или не содержит данных.")
except FileNotFoundError:
    logger.error(f"Файл данных о странах не найден: {COUNTRIES_DATA_PATH}")
except json.JSONDecodeError:
    logger.error(f"Ошибка декодирования JSON из файла: {COUNTRIES_DATA_PATH}")
except Exception as e:
    logger.error(f"Непредвиденная ошибка при загрузке данных о странах: {e}")

if not COUNTRIES_DATA:
    logger.critical("Данные о странах и аэропортах не загружены. Функциональность бота будет ограничена.")
    # Можно добавить логику аварийного завершения, если эти данные критичны
    # exit("Критическая ошибка: не удалось загрузить данные об аэропортах.")

# --- Названия месяцев для клавиатур (независимо от локали) ---
RUSSIAN_MONTHS = {
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
    5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
    9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"
}

# --- Константы для ConversationHandler ---
# Стандартный поиск
(
    SELECTING_FLIGHT_TYPE,
    SELECTING_DEPARTURE_COUNTRY,
    SELECTING_DEPARTURE_CITY,
    SELECTING_DEPARTURE_YEAR,
    SELECTING_DEPARTURE_MONTH,
    SELECTING_DEPARTURE_DATE_RANGE,
    SELECTING_DEPARTURE_DATE,
    SELECTING_ARRIVAL_COUNTRY,
    SELECTING_ARRIVAL_CITY,
    SELECTING_RETURN_YEAR,
    SELECTING_RETURN_MONTH,
    SELECTING_RETURN_DATE_RANGE,
    SELECTING_RETURN_DATE,
    SELECTING_MAX_PRICE,
    PROCESSING_STANDARD_SEARCH
) = range(15)

# Гибкий поиск (начинаем нумерацию с предыдущего значения + 1)
(
    SELECTING_FLEX_FLIGHT_TYPE, # 15
    SELECTING_FLEX_MAX_PRICE,   # 16
    ASK_FLEX_DEPARTURE_AIRPORT, # 17
    SELECTING_FLEX_DEPARTURE_COUNTRY, # 18
    SELECTING_FLEX_DEPARTURE_CITY,    # 19
    ASK_FLEX_ARRIVAL_AIRPORT,   # 20
    SELECTING_FLEX_ARRIVAL_COUNTRY,   # 21
    SELECTING_FLEX_ARRIVAL_CITY,      # 22
    ASK_FLEX_DATES,             # 23
    # Если даты важны, можно переиспользовать состояния стандартного поиска для дат
    # или создать новые, если логика отличается
    SELECTING_FLEX_DEPARTURE_YEAR,    # 24
    SELECTING_FLEX_DEPARTURE_MONTH,   # 25
    SELECTING_FLEX_DEPARTURE_DATE_RANGE, # 26
    SELECTING_FLEX_DEPARTURE_DATE,    # 27
    SELECTING_FLEX_RETURN_YEAR,       # 28
    SELECTING_FLEX_RETURN_MONTH,      # 29
    SELECTING_FLEX_RETURN_DATE_RANGE, # 30
    SELECTING_FLEX_RETURN_DATE,       # 31
    PROCESSING_FLEX_SEARCH      # 32
) = range(15, 15 + 18)


# Callback data префиксы для различения кнопок в разных диалогах, если нужно
CALLBACK_PREFIX_STANDARD = "std_"
CALLBACK_PREFIX_FLEX = "flex_"
CALLBACK_SKIP = "skip_step"
CALLBACK_NO_SPECIFIC_DATES = "no_specific_dates"

# Сообщения
MSG_WELCOME = (
    "Добро пожаловать в бот поиска билетов на Ryanair!\n"
    "Выберите тип поиска:\n"
    "/search - Стандартный поиск с указанием всех параметров.\n"
    "/flexsearch - Гибкий поиск (можно пропустить даты или направление)."
)
MSG_FLIGHT_TYPE_PROMPT = (
    "Выберите тип рейса:\n"
    "1 - В одну сторону\n"
    "2 - Туда и обратно"
)
MSG_MAX_PRICE_PROMPT = "Введите максимальную цену (EUR), например, 50:"
MSG_SEARCHING_FLIGHTS = "Начинаю поиск рейсов..."
MSG_NO_FLIGHTS_FOUND = "К сожалению, по вашим критериям рейсы не найдены."
MSG_FLIGHTS_FOUND_SEE_BELOW = "Найдены следующие рейсы:"
MSG_ERROR_OCCURRED = "Произошла ошибка. Попробуйте позже или свяжитесь с администратором."
MSG_CANCELLED = "Поиск отменен. Чтобы начать новый, выберите команду /search или /flexsearch."
MSG_NEW_SEARCH_PROMPT = "Хотите сделать новый поиск? Выберите /search или /flexsearch."