# bot/keyboards.py
import logging
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
# MODIFIED: Added CALLBACK_YES_OTHER_AIRPORTS, CALLBACK_NO_OTHER_AIRPORTS
from .config import COUNTRIES_DATA, RUSSIAN_MONTHS, CALLBACK_SKIP, CALLBACK_NO_SPECIFIC_DATES, \
                    CALLBACK_YES_OTHER_AIRPORTS, CALLBACK_NO_OTHER_AIRPORTS


logger = logging.getLogger(__name__)

def get_main_menu_keyboard():
    """Возвращает клавиатуру с выбором типа поиска."""
    keyboard = [
        [InlineKeyboardButton("✈️ Стандартный поиск", callback_data="start_standard_search")],
        [InlineKeyboardButton("✨ Гибкий поиск", callback_data="start_flex_search")],
        # NEW: Кнопка "Куда угодно"
        [InlineKeyboardButton("🎯 Найти самый дешёвый билет (куда угодно)", callback_data="start_flex_anywhere")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_flight_type_reply_keyboard():
    """Клавиатура для выбора типа рейса (1 или 2)."""
    reply_keyboard = [['1', '2']]
    return ReplyKeyboardMarkup(
        reply_keyboard, one_time_keyboard=True, resize_keyboard=True,
        input_field_placeholder='1 (в одну) или 2 (туда-обратно)'
    )

def get_country_reply_keyboard():
    """Клавиатура для выбора страны."""
    if not COUNTRIES_DATA:
        logger.warning("Нет данных о странах для генерации клавиатуры.")
        return ReplyKeyboardMarkup([["Ошибка: нет данных о странах"]], one_time_keyboard=True)
    
    country_names = sorted(list(COUNTRIES_DATA.keys()))
    # Группируем по 3 страны в ряд
    keyboard = [country_names[i:i + 3] for i in range(0, len(country_names), 3)]
    return ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

def get_city_reply_keyboard(country_name: str):
    """Клавиатура для выбора города в указанной стране."""
    if country_name not in COUNTRIES_DATA or not COUNTRIES_DATA[country_name]:
        logger.warning(f"Нет данных о городах для страны '{country_name}' или страна не найдена.")
        return ReplyKeyboardMarkup([["Ошибка: нет данных о городах"]], one_time_keyboard=True)

    city_names = sorted(list(COUNTRIES_DATA[country_name].keys()))
    # Группируем по 3 города в ряд
    keyboard = [city_names[i:i + 3] for i in range(0, len(city_names), 3)]
    return ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)


def generate_year_buttons(callback_prefix: str = ""):
    """Генерирует Inline Keyboard с текущим и следующим годом."""
    current_year = datetime.now().year
    next_year = current_year + 1
    keyboard = [
        [InlineKeyboardButton(text=str(current_year), callback_data=f"{callback_prefix}{current_year}")],
        [InlineKeyboardButton(text=str(next_year), callback_data=f"{callback_prefix}{next_year}")]
    ]
    return InlineKeyboardMarkup(keyboard)

def generate_month_buttons(callback_prefix: str = ""):
    """Генерирует Inline Keyboard с месяцами."""
    keyboard = []
    # Группируем месяцы по 3 в ряд для компактности
    month_items = list(RUSSIAN_MONTHS.items())
    for i in range(0, len(month_items), 3):
        row = []
        for idx, month_name in month_items[i:i+3]:
            callback_data = f"{callback_prefix}{str(idx).zfill(2)}" # Номер месяца с ведущим нулём
            row.append(InlineKeyboardButton(text=month_name, callback_data=callback_data))
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)

def generate_date_range_buttons(year: int, month: int, callback_prefix: str = ""):
    """Генерирует Inline Keyboard с диапазонами дат (1-10, 11-20, 21-конец месяца)."""
    try:
        # Определяем количество дней в месяце
        if month == 12:
            # Для декабря следующий месяц - январь следующего года
            days_in_month = (datetime(year + 1, 1, 1) - datetime(year, month, 1)).days
        else:
            days_in_month = (datetime(year, month + 1, 1) - datetime(year, month, 1)).days
    except ValueError:
        logger.error(f"Неверный год ({year}) или месяц ({month}) для генерации диапазонов дат.")
        return InlineKeyboardMarkup([]) # Возвращаем пустую клавиатуру в случае ошибки

    ranges = [
        (1, 10),
        (11, 20),
        (21, days_in_month)
    ]

    keyboard = []
    for start, end in ranges:
        # Убедимся, что конечная дата диапазона не превышает количество дней в месяце
        actual_end = min(end, days_in_month)
        if start > actual_end : # Если начальная дата уже больше конца месяца (например, для 21-20 в феврале)
            continue
        range_str = f"{start}-{actual_end}"
        callback_data = f"{callback_prefix}{start}-{actual_end}"
        keyboard.append([InlineKeyboardButton(text=range_str, callback_data=callback_data)])
    return InlineKeyboardMarkup(keyboard)

def generate_specific_date_buttons(year: int, month: int, date_range_start: int, date_range_end: int, callback_prefix: str = ""):
    """Генерирует Inline Keyboard с конкретными датами в выбранном диапазоне."""
    buttons = []
    row = []
    # Генерируем кнопки с датами, по 5 в ряду
    for day in range(date_range_start, date_range_end + 1):
        try:
            date_obj = datetime(year, month, day)
            date_str_callback = date_obj.strftime("%Y-%m-%d") # Формат для callback_data
            display_date = date_obj.strftime("%d") # Отображаем только число
            
            row.append(InlineKeyboardButton(text=display_date, callback_data=f"{callback_prefix}{date_str_callback}"))
            if len(row) == 5: # 5 кнопок в ряду
                buttons.append(row)
                row = []
        except ValueError:
            # Пропускаем несуществующие даты (например, 30 февраля)
            logger.warning(f"Попытка создать кнопку для несуществующей даты: {year}-{month}-{day}")
            continue
    if row: # Добавляем оставшиеся кнопки, если их меньше 5
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)

def get_skip_or_select_keyboard(prompt_message: str, callback_skip_action: str, callback_select_action: str):
    """Клавиатура "Пропустить" или "Выбрать"."""
    keyboard = [
        [InlineKeyboardButton(f"✏️ {prompt_message}", callback_data=callback_select_action)],
        [InlineKeyboardButton("➡️ Пропустить", callback_data=callback_skip_action)],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_yes_no_keyboard(yes_callback: str, no_callback: str, yes_text="Да", no_text="Нет"):
    """Клавиатура Да/Нет."""
    keyboard = [
        [
            InlineKeyboardButton(yes_text, callback_data=yes_callback),
            InlineKeyboardButton(no_text, callback_data=no_callback),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_skip_dates_keyboard(callback_select_dates: str):
    """Клавиатура для выбора дат или пропуска (поиск без указания дат)."""
    keyboard = [
        [InlineKeyboardButton("🗓 Выбрать конкретные даты", callback_data=callback_select_dates)],
        [InlineKeyboardButton("✨ Искать без указания дат", callback_data=CALLBACK_NO_SPECIFIC_DATES)],
    ]
    return InlineKeyboardMarkup(keyboard)

# NEW: Клавиатура для предложения поиска из других аэропортов
def get_search_other_airports_keyboard(country_name: str):
    """Клавиатура Да/Нет для поиска из других аэропортов указанной страны."""
    keyboard = [
        [
            InlineKeyboardButton(f"Да, искать из других в {country_name}", callback_data=CALLBACK_YES_OTHER_AIRPORTS),
            InlineKeyboardButton("Нет, спасибо", callback_data=CALLBACK_NO_OTHER_AIRPORTS),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)