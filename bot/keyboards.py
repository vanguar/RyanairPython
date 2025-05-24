# bot/keyboards.py
import logging
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from .config import COUNTRIES_DATA, RUSSIAN_MONTHS, CALLBACK_SKIP, CALLBACK_NO_SPECIFIC_DATES, \
                    CALLBACK_YES_OTHER_AIRPORTS, CALLBACK_NO_OTHER_AIRPORTS

logger = logging.getLogger(__name__)

def get_main_menu_keyboard():
    """Возвращает клавиатуру с выбором типа поиска."""
    keyboard = [
        [InlineKeyboardButton("✈️ Стандартный поиск", callback_data="start_standard_search")],
        [InlineKeyboardButton("✨ Гибкий поиск", callback_data="start_flex_search")],
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
    keyboard = [country_names[i:i + 3] for i in range(0, len(country_names), 3)]
    return ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

def get_city_reply_keyboard(country_name: str):
    """Клавиатура для выбора города в указанной стране."""
    if country_name not in COUNTRIES_DATA or not COUNTRIES_DATA[country_name]:
        logger.warning(f"Нет данных о городах для страны '{country_name}' или страна не найдена.")
        return ReplyKeyboardMarkup([["Ошибка: нет данных о городах"]], one_time_keyboard=True)

    city_names = sorted(list(COUNTRIES_DATA[country_name].keys()))
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

def generate_month_buttons(callback_prefix: str = "", year_for_months: int = None, 
                           min_departure_month: int = None, departure_year_for_comparison: int = None):
    """
    Генерирует Inline Keyboard с месяцами.
    year_for_months: год, для которого генерируются месяцы.
    min_departure_month: если указан и year_for_months == departure_year_for_comparison — минимальный допустимый месяц (месяц вылета).
    departure_year_for_comparison: год вылета, для сравнения с 'year_for_months' при использовании min_departure_month.
    """
    now = datetime.now()
    current_system_year = now.year
    current_system_month = now.month

    keyboard = []
    month_items = list(RUSSIAN_MONTHS.items())
    
    row = []
    buttons_in_row_count = 0

    for month_number, month_name in month_items:
        show_disabled = False
        
        # Условие 1: Месяц прошел в текущем системном году
        if year_for_months == current_system_year and month_number < current_system_month:
            show_disabled = True
        
        # Условие 2: Месяц раньше минимально допустимого месяца вылета (для выбора месяца возврата)
        if not show_disabled and min_departure_month is not None and departure_year_for_comparison is not None:
            if year_for_months == departure_year_for_comparison and month_number < min_departure_month:
                show_disabled = True
            # Также, если год выбора (year_for_months) раньше года вылета (departure_year_for_comparison) - все месяцы невалидны
            elif year_for_months < departure_year_for_comparison:
                 show_disabled = True

        if show_disabled:
            row.append(InlineKeyboardButton(f"⛔️ {month_name}", callback_data="ignore_past_month"))
        else:
            callback_data_month = f"{callback_prefix}{str(month_number).zfill(2)}"
            row.append(InlineKeyboardButton(text=month_name, callback_data=callback_data_month))
        
        buttons_in_row_count += 1
        if buttons_in_row_count == 3:
            keyboard.append(row)
            row = []
            buttons_in_row_count = 0
            
    if row: # Добавляем оставшиеся кнопки, если их меньше 3 в последнем ряду
        keyboard.append(row)

    if not keyboard: # Если не осталось доступных месяцев для выбора
        keyboard.append([InlineKeyboardButton("Нет доступных месяцев", callback_data="no_valid_months_error")]) # Изменен callback_data для уникальности
        
    return InlineKeyboardMarkup(keyboard)

def generate_date_range_buttons(year: int, month: int, callback_prefix: str = ""):
    """Генерирует Inline Keyboard с диапазонами дат (1-10, 11-20, 21-конец месяца)."""
    try:
        if month == 12:
            days_in_month = (datetime(year + 1, 1, 1) - datetime(year, month, 1)).days
        else:
            days_in_month = (datetime(year, month + 1, 1) - datetime(year, month, 1)).days
    except ValueError:
        logger.error(f"Неверный год ({year}) или месяц ({month}) для генерации диапазонов дат.")
        return InlineKeyboardMarkup([])

    ranges = [
        (1, 10),
        (11, 20),
        (21, days_in_month)
    ]

    keyboard = []
    for start, end in ranges:
        actual_end = min(end, days_in_month)
        if start > actual_end :
            continue
        range_str = f"{start}-{actual_end}"
        callback_data = f"{callback_prefix}{start}-{actual_end}"
        keyboard.append([InlineKeyboardButton(text=range_str, callback_data=callback_data)])
    return InlineKeyboardMarkup(keyboard)

def generate_specific_date_buttons(year: int, month: int, date_range_start: int, date_range_end: int, 
                                   callback_prefix: str = "", min_allowed_date: datetime = None):
    """
    Генерирует Inline Keyboard с конкретными датами в выбранном диапазоне.
    min_allowed_date — минимальная допустимая дата (объект datetime).
    """
    buttons = []
    row = []
    
    # Если min_allowed_date не передан, по умолчанию считаем, что ограничений нет (кроме самой даты)
    # Но для дат вылета это должна быть полночь текущего дня. Для дат возврата - дата вылета.
    # Это должно быть установлено в хендлере и передано сюда.

    for day in range(date_range_start, date_range_end + 1):
        try:
            current_date_obj = datetime(year, month, day).replace(hour=0, minute=0, second=0, microsecond=0) # Сравниваем только даты
            display_date = current_date_obj.strftime("%d")
            
            show_disabled = False
            if min_allowed_date and current_date_obj < min_allowed_date.replace(hour=0, minute=0, second=0, microsecond=0):
                show_disabled = True
            
            if show_disabled:
                row.append(InlineKeyboardButton(f"⛔️ {display_date}", callback_data="ignore_past_day"))
            else:
                date_str_callback = current_date_obj.strftime("%Y-%m-%d")
                row.append(InlineKeyboardButton(text=display_date, callback_data=f"{callback_prefix}{date_str_callback}"))

            if len(row) == 5:
                buttons.append(row)
                row = []
        except ValueError:
            logger.warning(f"Попытка создать кнопку для несуществующей даты: {year}-{month}-{day}")
            continue
    if row:
        buttons.append(row)
        
    if not buttons: # Если в диапазоне нет доступных дат
         buttons.append([InlineKeyboardButton("Нет доступных дат", callback_data="no_valid_dates_error")]) # Изменен callback_data
         
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

def get_search_other_airports_keyboard(country_name: str):
    """Клавиатура Да/Нет для поиска из других аэропортов указанной страны."""
    keyboard = [
        [
            InlineKeyboardButton(f"Да, искать из других в {country_name}", callback_data=CALLBACK_YES_OTHER_AIRPORTS),
            InlineKeyboardButton("Нет, спасибо", callback_data=CALLBACK_NO_OTHER_AIRPORTS),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)