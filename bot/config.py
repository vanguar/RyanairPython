# bot/config.py
import os
import json
import logging
from dotenv import load_dotenv
from typing import Literal

# Загрузка переменных окружения из .env файла
load_dotenv()

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_TELEGRAM_ID = os.getenv("ADMIN_TELEGRAM_ID") # Опционально

if not TELEGRAM_BOT_TOKEN:
    logger.critical("Переменная окружения TELEGRAM_BOT_TOKEN не установлена!")
    # exit("Ошибка: TELEGRAM_BOT_TOKEN не найден.")

# --- Путь к приветственному изображению ---
# Изображение должно быть размещено в директории, доступной боту.
# os.path.dirname(__file__) указывает на директорию config.py (bot/)
# Таким образом, '../data/images/welcome_image.png' будет указывать на 'корень_проекта/data/images/welcome_image.png'
WELCOME_IMAGE_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'images', 'welcome_image.png') # Замените 'welcome_image.png' на имя вашего файла

# Проверка, существует ли файл изображения (опционально, полезно для отладки)
if WELCOME_IMAGE_PATH and not os.path.exists(WELCOME_IMAGE_PATH):
    logger.warning(f"Файл приветственного изображения не найден по пути: {WELCOME_IMAGE_PATH}")
elif not WELCOME_IMAGE_PATH:
    logger.info("Путь к приветственному изображению не настроен.")    

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
    S_SELECTING_FLIGHT_TYPE,             # 0
    S_SELECTING_DEPARTURE_COUNTRY,       # 1
    S_SELECTING_DEPARTURE_CITY,          # 2
    S_SELECTING_DEPARTURE_YEAR,          # 3
    S_SELECTING_DEPARTURE_MONTH,         # 4
    S_SELECTING_DEPARTURE_DATE_RANGE,    # 5
    S_SELECTING_DEPARTURE_DATE,          # 6
    S_SELECTING_ARRIVAL_COUNTRY,         # 7
    S_SELECTING_ARRIVAL_CITY,            # 8  (переходит в SELECTING_PRICE_OPTION или S_SELECTING_RETURN_YEAR)
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

# ОБЩИЕ СОСТОЯНИЯ для выбора и ввода цены
SELECTING_PRICE_OPTION = 30
ENTERING_CUSTOM_PRICE = 31

# КОНСТАНТЫ для определения потока поиска
FLOW_STANDARD = "standard_flow"
FLOW_FLEX = "flex_flow"

# Callback data префиксы
CALLBACK_PREFIX_STANDARD = "std_"
CALLBACK_PREFIX_FLEX = "flex_"
CALLBACK_SKIP = "skip_step"
CALLBACK_NO_SPECIFIC_DATES = "no_specific_dates"

# Callback data для кнопок выбора опции цены
CALLBACK_PRICE_CUSTOM = "price_custom"
CALLBACK_PRICE_LOWEST = "price_lowest"
CALLBACK_PRICE_ALL = "price_all"

# Тип для вариантов выбора цены
PriceChoice = Literal[CALLBACK_PRICE_CUSTOM, CALLBACK_PRICE_LOWEST, CALLBACK_PRICE_ALL]

# Callback data для поиска из других аэропортов
CALLBACK_YES_OTHER_AIRPORTS = "yes_other_airports"
CALLBACK_NO_OTHER_AIRPORTS = "no_other_airports"

# --- Сообщения ---
MSG_BACK = "⬅️ Назад" # Текст для кнопки "Назад"

MSG_WELCOME = (
    "Добро пожаловать в бот поиска билетов на Ryanair!\n"
    "Выберите тип поиска:\n"
    "/search - Стандартный поиск с указанием всех параметров.\n"
    "/flexsearch - Гибкий поиск (можно пропустить даты или направление).\n"
    "Или выберите опцию ниже:"
)
MSG_FLIGHT_TYPE_PROMPT = (
    "Выберите тип рейса:\n"
    "➡️ 1 - В одну сторону\n"
    "🔄 2 - В обе стороны"  # ИЗМЕНЕНО
)
MSG_PRICE_OPTION_PROMPT = "💰 Выберите, как определить цену для поиска:"
MSG_MAX_PRICE_PROMPT = "💶 Введите желаемую максимальную цену (EUR), например, 50:"
MSG_SEARCHING_FLIGHTS = "⏳ Начинаю поиск рейсов..."
MSG_NO_FLIGHTS_FOUND = "🤷 К сожалению, по вашим критериям рейсы не найдены."
MSG_FLIGHTS_FOUND_SEE_BELOW = "✈️✨ Найдены следующие рейсы:"
MSG_ERROR_OCCURRED = "❗Произошла ошибка. Попробуйте позже или свяжитесь с администратором."
MSG_CANCELLED = "🛑 Поиск отменен. Чтобы начать новый, выберите команду /start."
MSG_NEW_SEARCH_PROMPT = "🆕 Хотите сделать новый поиск? Выберите опцию через /start."

# Сообщения для гибкого поиска и обработки цен
MSG_ASK_FLEX_DEPARTURE_AIRPORT_PROMPT = "🛫 Указать аэропорт вылета?"
MSG_INVALID_PRICE_INPUT = "⚠️ Неверная цена. Введите положительное число (например, 50).\nИли выберите другую опцию:"
MSG_PRICE_CHOICE_SAVED_FLEX = "💾 Ценовое предпочтение сохранено. Продолжаем..."
MSG_PRICE_CHOICE_LOWEST_STANDARD = "📉 Ищу самые дешевые билеты..."
MSG_PRICE_CHOICE_ALL_STANDARD = "📊 Ищу все доступные билеты..."
MSG_MAX_PRICE_SET_INFO = "✅ Максимальная цена для поиска: {price} EUR."
MSG_INVALID_PRICE_CHOICE_FALLBACK = "🚫 Этот выбор сейчас недоступен. Пожалуйста, следуйте диалогу или начните заново /start."

FLIGHTS_CHUNK_SIZE = 3

# --- Callback Data для кнопок "Назад" ---

# Стандартный поиск: Назад к выбору типа рейса (от выбора страны вылета)
CB_BACK_STD_DEP_COUNTRY_TO_FLIGHT_TYPE = "cb_back_std_dep_country_to_ft"
# Стандартный поиск: Назад к выбору страны вылета (от выбора города вылета)
CB_BACK_STD_DEP_CITY_TO_COUNTRY = "cb_back_std_dep_city_to_country"
# Стандартный поиск: Выбор дат вылета
CB_BACK_STD_DEP_YEAR_TO_CITY = "cb_back_std_dep_year_to_city"
CB_BACK_STD_DEP_MONTH_TO_YEAR = "cb_back_std_dep_month_to_year"
CB_BACK_STD_DEP_RANGE_TO_MONTH = "cb_back_std_dep_range_to_month"
CB_BACK_STD_DEP_DATE_TO_RANGE = "cb_back_std_dep_date_to_range"
# Стандартный поиск: Назад к выбору даты вылета (от выбора страны прилета)
CB_BACK_STD_ARR_COUNTRY_TO_DEP_DATE = "cb_back_std_arr_country_to_dep_date"
# Стандартный поиск: Назад к выбору страны прилета (от выбора города прилета)
CB_BACK_STD_ARR_CITY_TO_COUNTRY = "cb_back_std_arr_city_to_country"

# Стандартный поиск: Выбор дат возврата
CB_BACK_STD_RET_YEAR_TO_ARR_CITY = "cb_back_std_ret_year_to_arr_city"
CB_BACK_STD_RET_MONTH_TO_YEAR = "cb_back_std_ret_month_to_year"
CB_BACK_STD_RET_RANGE_TO_MONTH = "cb_back_std_ret_range_to_month"
CB_BACK_STD_RET_DATE_TO_RANGE = "cb_back_std_ret_date_to_range"

# Стандартный поиск: От выбора цены назад
CB_BACK_PRICE_TO_STD_ARR_CITY_ONEWAY = "cb_back_price_to_std_arr_city_oneway" # Если в одну сторону, назад к городу прилета
CB_BACK_PRICE_TO_STD_RET_DATE_TWOWAY = "cb_back_price_to_std_ret_date_twoway" # Если в обе, назад к дате возврата
CB_BACK_PRICE_TO_ENTERING_CUSTOM = "cb_back_price_to_entering_custom" # От ввода кастомной цены назад к выбору опции

# Гибкий поиск
CB_BACK_PRICE_TO_FLEX_FLIGHT_TYPE = "cb_back_price_to_flex_ft"
CB_BACK_FLEX_ASK_DEP_TO_PRICE = "cb_back_flex_ask_dep_to_price"
CB_BACK_FLEX_DEP_COUNTRY_TO_ASK_DEP = "cb_back_flex_dep_country_to_ask_dep"
CB_BACK_FLEX_DEP_CITY_TO_DEP_COUNTRY = "cb_back_flex_dep_city_to_dep_country"
CB_BACK_FLEX_ASK_ARR_TO_DEP_CITY = "cb_back_flex_ask_arr_to_dep_city"
CB_BACK_FLEX_ARR_COUNTRY_TO_ASK_ARR = "cb_back_flex_arr_country_to_ask_arr"
CB_BACK_FLEX_ARR_CITY_TO_ARR_COUNTRY = "cb_back_flex_arr_city_to_arr_country"

CB_BACK_FLEX_ASK_DATES_TO_ARR_CITY = "cb_back_flex_ask_dates_to_arr_city" # Если город прилета был указан
CB_BACK_FLEX_ASK_DATES_TO_DEP_CITY_NO_ARR = "cb_back_flex_ask_dates_to_dep_city_no_arr" # Если город прилета был пропущен

CB_BACK_FLEX_DEP_YEAR_TO_ASK_DATES = "cb_back_flex_dep_year_to_ask_dates"
CB_BACK_FLEX_DEP_MONTH_TO_YEAR = "cb_back_flex_dep_month_to_year"
CB_BACK_FLEX_DEP_RANGE_TO_MONTH = "cb_back_flex_dep_range_to_month"
CB_BACK_FLEX_DEP_DATE_TO_RANGE = "cb_back_flex_dep_date_to_range"

CB_BACK_FLEX_RET_YEAR_TO_DEP_DATE = "cb_back_flex_ret_year_to_dep_date"
CB_BACK_FLEX_RET_MONTH_TO_YEAR = "cb_back_flex_ret_month_to_year"
CB_BACK_FLEX_RET_RANGE_TO_MONTH = "cb_back_flex_ret_range_to_month"
CB_BACK_FLEX_RET_DATE_TO_RANGE = "cb_back_flex_ret_date_to_range"