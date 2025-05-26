# bot/config.py
import os
import json
import logging
from dotenv import load_dotenv
from typing import Literal # <--- ДОБАВЛЕН ИМПОРТ

# Загрузка переменных окружения из .env файла
load_dotenv()

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_TELEGRAM_ID = os.getenv("ADMIN_TELEGRAM_ID") # Опционально

if not TELEGRAM_BOT_TOKEN:
    logger.critical("Переменная окружения TELEGRAM_BOT_TOKEN не установлена!")
    # exit("Ошибка: TELEGRAM_BOT_TOKEN не найден.")

# --- Загрузка данных о странах и аэропортах ---
COUNTRIES_DATA_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'countries_data.json') #
COUNTRIES_DATA = {}

try:
    with open(COUNTRIES_DATA_PATH, 'r', encoding='utf-8') as f: #
        COUNTRIES_DATA = json.load(f) #
    if not COUNTRIES_DATA: #
        logger.warning(f"Файл {COUNTRIES_DATA_PATH} пуст или не содержит данных.") #
except FileNotFoundError: #
    logger.error(f"Файл данных о странах не найден: {COUNTRIES_DATA_PATH}") #
except json.JSONDecodeError: #
    logger.error(f"Ошибка декодирования JSON из файла: {COUNTRIES_DATA_PATH}") #
except Exception as e: #
    logger.error(f"Непредвиденная ошибка при загрузке данных о странах: {e}") #

if not COUNTRIES_DATA: #
    logger.critical("Данные о странах и аэропортах не загружены. Функциональность бота будет ограничена.") #
    # exit("Критическая ошибка: не удалось загрузить данные об аэропортах.")

# --- Названия месяцев для клавиатур (независимо от локали) ---
RUSSIAN_MONTHS = { #
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель", #
    5: "Май", 6: "Июнь", 7: "Июль", 8: "Август", #
    9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь" #
}

# --- Константы для ConversationHandler ---

# Стандартный поиск
(
    S_SELECTING_FLIGHT_TYPE,             # 0
    S_SELECTING_DEPARTURE_COUNTRY,       # 1
    S_SELECTING_DEPARTURE_CITY,          # 2
    S_SELECTING_DEPARTURE_YEAR,          # 3
    S_SELECTING_DEPARTURE_MONTH,         # 4
    S_SELECTING_DEPARTURE_DATE_RANGE,    # 5
    S_SELECTING_DEPARTURE_DATE,          # 6
    S_SELECTING_ARRIVAL_COUNTRY,         # 7
    S_SELECTING_ARRIVAL_CITY,            # 8  (переходит в SELECTING_PRICE_OPTION)
    S_SELECTING_RETURN_YEAR,             # 9
    S_SELECTING_RETURN_MONTH,            # 10
    S_SELECTING_RETURN_DATE_RANGE,       # 11
    S_SELECTING_RETURN_DATE,             # 12 (переходит в SELECTING_PRICE_OPTION)
) = range(13)

# Гибкий поиск
offset_flex = 13
(
    SELECTING_FLEX_FLIGHT_TYPE,        # 13 (переходит в SELECTING_PRICE_OPTION)
    ASK_FLEX_DEPARTURE_AIRPORT,        # 14 (вызывается ПОСЛЕ выбора цены/сохранения предпочтения)
    SELECTING_FLEX_DEPARTURE_COUNTRY,  # 15
    SELECTING_FLEX_DEPARTURE_CITY,     # 16
    ASK_FLEX_ARRIVAL_AIRPORT,          # 17
    SELECTING_FLEX_ARRIVAL_COUNTRY,    # 18
    SELECTING_FLEX_ARRIVAL_CITY,       # 19
    ASK_FLEX_DATES,                    # 20 (здесь может запускаться launch_flight_search)
    SELECTING_FLEX_DEPARTURE_YEAR,     # 21
    SELECTING_FLEX_DEPARTURE_MONTH,    # 22
    SELECTING_FLEX_DEPARTURE_DATE_RANGE, # 23
    SELECTING_FLEX_DEPARTURE_DATE,     # 24 (здесь может запускаться launch_flight_search)
    SELECTING_FLEX_RETURN_YEAR,        # 25
    SELECTING_FLEX_RETURN_MONTH,       # 26
    SELECTING_FLEX_RETURN_DATE_RANGE,  # 27
    SELECTING_FLEX_RETURN_DATE,        # 28 (здесь может запускаться launch_flight_search)
    ASK_SEARCH_OTHER_AIRPORTS          # 29
) = range(offset_flex, offset_flex + 17)

# ОБЩИЕ СОСТОЯНИЯ для выбора и ввода цены (добавляем после всех существующих)
# Последнее состояние было ASK_SEARCH_OTHER_AIRPORTS = 29
SELECTING_PRICE_OPTION = 30
ENTERING_CUSTOM_PRICE = 31

# КОНСТАНТЫ для определения потока поиска
FLOW_STANDARD = "standard_flow"
FLOW_FLEX = "flex_flow"

# Callback data префиксы
CALLBACK_PREFIX_STANDARD = "std_" #
CALLBACK_PREFIX_FLEX = "flex_" #
CALLBACK_SKIP = "skip_step" #
CALLBACK_NO_SPECIFIC_DATES = "no_specific_dates" #

# Callback data для кнопок выбора опции цены
CALLBACK_PRICE_CUSTOM = "price_custom"
CALLBACK_PRICE_LOWEST = "price_lowest"
CALLBACK_PRICE_ALL = "price_all"

# Тип для вариантов выбора цены
PriceChoice = Literal[CALLBACK_PRICE_CUSTOM, CALLBACK_PRICE_LOWEST, CALLBACK_PRICE_ALL]

# Callback data для поиска из других аэропортов
CALLBACK_YES_OTHER_AIRPORTS = "yes_other_airports" #
CALLBACK_NO_OTHER_AIRPORTS = "no_other_airports" #
# CALLBACK_PERFORM_SEARCH_OTHER_AIRPORTS = "perform_search_other_airports" # # Пока не используется

# Сообщения
MSG_WELCOME = ( #
    "Добро пожаловать в бот поиска билетов на Ryanair!\n"
    "Выберите тип поиска:\n"
    "/search - Стандартный поиск с указанием всех параметров.\n"
    "/flexsearch - Гибкий поиск (можно пропустить даты или направление).\n"
    "Или выберите опцию ниже:" #
)
MSG_FLIGHT_TYPE_PROMPT = ( #
    "Выберите тип рейса:\n"
    "1 - В одну сторону\n"
    "2 - Туда и обратно"
)
MSG_PRICE_OPTION_PROMPT = "Выберите, как определить цену для поиска:"
MSG_MAX_PRICE_PROMPT = "Введите желаемую максимальную цену (EUR), например, 50:" #
MSG_SEARCHING_FLIGHTS = "Начинаю поиск рейсов..." #
MSG_NO_FLIGHTS_FOUND = "К сожалению, по вашим критериям рейсы не найдены." #
MSG_FLIGHTS_FOUND_SEE_BELOW = "Найдены следующие рейсы:" #
MSG_ERROR_OCCURRED = "Произошла ошибка. Попробуйте позже или свяжитесь с администратором." #
MSG_CANCELLED = "Поиск отменен. Чтобы начать новый, выберите команду /start." #
MSG_NEW_SEARCH_PROMPT = "Хотите сделать новый поиск? Выберите опцию через /start." #

# Сообщения для гибкого поиска и обработки цен
MSG_ASK_FLEX_DEPARTURE_AIRPORT_PROMPT = "Указать аэропорт вылета?"
MSG_INVALID_PRICE_INPUT = "Неверная цена. Введите положительное число (например, 50).\nИли выберите другую опцию:"
MSG_PRICE_CHOICE_SAVED_FLEX = "Ценовое предпочтение сохранено. Продолжаем..."
MSG_PRICE_CHOICE_LOWEST_STANDARD = "Ищу самые дешевые билеты..."
MSG_PRICE_CHOICE_ALL_STANDARD = "Ищу все доступные билеты..."
MSG_MAX_PRICE_SET_INFO = "Максимальная цена для поиска: {price} EUR."
MSG_INVALID_PRICE_CHOICE_FALLBACK = "Этот выбор сейчас недоступен. Пожалуйста, следуйте диалогу или начните заново /start."


FLIGHTS_CHUNK_SIZE = 3 #