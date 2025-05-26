# bot/keyboards.py
import logging
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from .config import (
    COUNTRIES_DATA, RUSSIAN_MONTHS, CALLBACK_SKIP, CALLBACK_NO_SPECIFIC_DATES,
    CALLBACK_YES_OTHER_AIRPORTS, CALLBACK_NO_OTHER_AIRPORTS,
    # Импорты для кнопок цены
    CALLBACK_PRICE_CUSTOM, CALLBACK_PRICE_LOWEST, CALLBACK_PRICE_ALL
)

logger = logging.getLogger(__name__)

def get_main_menu_keyboard(): #
    """Возвращает клавиатуру с выбором типа поиска."""
    keyboard = [ #
        [InlineKeyboardButton("✈️ Стандартный поиск", callback_data="start_standard_search")], #
        [InlineKeyboardButton("✨ Гибкий поиск", callback_data="start_flex_search")], #
        [InlineKeyboardButton("🎯 Найти самый дешёвый билет (куда угодно)", callback_data="start_flex_anywhere")] #
    ]
    return InlineKeyboardMarkup(keyboard) #

def get_flight_type_reply_keyboard(): #
    """Клавиатура для выбора типа рейса (1 или 2)."""
    reply_keyboard = [['1', '2']] #
    return ReplyKeyboardMarkup( #
        reply_keyboard, one_time_keyboard=True, resize_keyboard=True,
        input_field_placeholder='1 (в одну) или 2 (туда-обратно)'
    )

def get_country_reply_keyboard(): #
    """Клавиатура для выбора страны."""
    if not COUNTRIES_DATA: #
        logger.warning("Нет данных о странах для генерации клавиатуры.") #
        return ReplyKeyboardMarkup([["Ошибка: нет данных о странах"]], one_time_keyboard=True) #
    
    country_names = sorted(list(COUNTRIES_DATA.keys())) #
    keyboard = [country_names[i:i + 3] for i in range(0, len(country_names), 3)] #
    return ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True) #

def get_city_reply_keyboard( #
        country_name: str,
        override_cities: dict[str, str] | None = None,
):
    """
    Клавиатура городов. Если override_cities передан —
    строим клавиатуру из него, иначе берём данные из COUNTRIES_DATA.
    """
    cities_dict = override_cities or COUNTRIES_DATA.get(country_name, {}) #
    if not cities_dict: #
        logger.warning(f"Нет городов для страны «{country_name}»") #
        return ReplyKeyboardMarkup([["Нет доступных городов"]], one_time_keyboard=True) #

    city_names = sorted(cities_dict.keys()) #
    keyboard = [city_names[i:i + 3] for i in range(0, len(city_names), 3)] #
    return ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True) #

def generate_year_buttons(callback_prefix: str = ""): #
    """Генерирует Inline Keyboard с текущим и следующим годом."""
    current_year = datetime.now().year #
    next_year = current_year + 1 #
    keyboard = [ #
        [InlineKeyboardButton(text=str(current_year), callback_data=f"{callback_prefix}{current_year}")], #
        [InlineKeyboardButton(text=str(next_year), callback_data=f"{callback_prefix}{next_year}")] #
    ]
    return InlineKeyboardMarkup(keyboard) #

def generate_month_buttons( #
        callback_prefix: str = "",
        year_for_months: int | None = None,
        min_departure_month: int | None = None,
        departure_year_for_comparison: int | None = None,
):
    """Генерирует Inline-keyboard с месяцами, скрывая уже прошедшие или невалидные."""
    now = datetime.now() #
    cur_year, cur_month = now.year, now.month #
    keyboard_rows = [] #
    month_items = list(RUSSIAN_MONTHS.items()) #

    if year_for_months is None: #
        year_for_months = cur_year #

    current_row = [] #
    for idx, month_name in month_items: #
        is_past_month = (year_for_months == cur_year and idx < cur_month) #
        
        is_before_min_departure = ( #
            min_departure_month is not None and
            departure_year_for_comparison is not None and 
            departure_year_for_comparison == year_for_months and
            idx < min_departure_month
        )

        if is_past_month or is_before_min_departure: #
            continue #

        callback_data = f"{callback_prefix}{str(idx).zfill(2)}" #
        # logger.info( #
        #     "generate_month_buttons: создаю кнопку '%s' с callback_data '%s'",
        #     month_name, callback_data
        # )
        current_row.append(InlineKeyboardButton(text=month_name, callback_data=callback_data)) #
        
        if len(current_row) == 3: #
            keyboard_rows.append(current_row) #
            current_row = [] #
            
    if current_row: #
        keyboard_rows.append(current_row) #

    if not keyboard_rows: #
        # logger.warning(f"Для {year_for_months} (min_dep_month: {min_departure_month} in {departure_year_for_comparison}) не найдено доступных месяцев.") #
        keyboard_rows.append([InlineKeyboardButton("Нет доступных месяцев", callback_data="no_valid_months_error")]) #
        
    return InlineKeyboardMarkup(keyboard_rows) #

def generate_date_range_buttons(year: int, month: int, callback_prefix: str = ""): #
    """Inline-клава с диапазонами дат; в текущем месяце скрывает уже прошедшие."""
    today = datetime.now().date() #

    try:
        if month == 12: #
            days_in_month = (datetime(year + 1, 1, 1) - datetime(year, month, 1)).days #
        else:
            days_in_month = (datetime(year, month + 1, 1) - datetime(year, month, 1)).days #
    except ValueError: #
        logger.error(f"Неверный год/месяц {year}-{month} для generate_date_range_buttons") #
        return InlineKeyboardMarkup([]) #

    ranges = [(1, 10), (11, 20), (21, days_in_month)] #
    keyboard_buttons = [] #

    for start, end in ranges: #
        actual_end = min(end, days_in_month) #
        if start > actual_end: #
            continue #

        if year == today.year and month == today.month and actual_end < today.day: #
            # logger.info("generate_date_range_buttons: пропустил диапазон %s-%s для %s-%s (уже прошло, сегодня %s)", #
            #             start, actual_end, month, year, today.day)
            continue #

        cb = f"{callback_prefix}{start}-{actual_end}" #
        keyboard_buttons.append([InlineKeyboardButton(f"{start}-{actual_end}", callback_data=cb)]) #

    if not keyboard_buttons: #
        # logger.info(f"Для {year}-{month} не найдено подходящих диапазонов дат (сегодня: {today.strftime('%Y-%m-%d')}).") #
        keyboard_buttons.append([InlineKeyboardButton("Нет доступных дат в этом месяце", callback_data="no_valid_dates_error")]) #

    return InlineKeyboardMarkup(keyboard_buttons) #

def generate_specific_date_buttons( #
        year: int, month: int, date_range_start: int, date_range_end: int, 
        callback_prefix: str = "", min_allowed_date: datetime | None = None
    ):
    """Генерирует Inline Keyboard с конкретными датами в выбранном диапазоне, фильтруя прошедшие."""
    buttons_rows = [] #
    current_row = [] #

    if min_allowed_date is None: #
        min_allowed_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) #

    any_button_created = False #
    for day in range(date_range_start, date_range_end + 1): #
        try:
            date_obj = datetime(year, month, day) #
            if date_obj < min_allowed_date: #
                continue #

            any_button_created = True #
            date_str_callback = date_obj.strftime("%Y-%m-%d") #
            display_date = date_obj.strftime("%d") #
            
            current_row.append(InlineKeyboardButton(text=display_date, callback_data=f"{callback_prefix}{date_str_callback}")) #
            if len(current_row) == 5: #
                buttons_rows.append(current_row) #
                current_row = [] #
        except ValueError: #
            logger.warning(f"Попытка создать кнопку для несуществующей даты: {year}-{month}-{day}") #
            continue #
            
    if current_row: #
        buttons_rows.append(current_row) #
    
    if not any_button_created and date_range_start <= date_range_end: #
        # logger.info(f"В диапазоне {year}-{month} ({date_range_start}-{date_range_end}) нет доступных для выбора дат (все прошли или отфильтрованы).") #
        buttons_rows.append([InlineKeyboardButton("Нет доступных дат в этом диапазоне", callback_data="no_valid_dates_error")]) #
        
    return InlineKeyboardMarkup(buttons_rows) #

def get_skip_or_select_keyboard(prompt_message: str, callback_skip_action: str, callback_select_action: str): #
    """Клавиатура "Пропустить" или "Выбрать"."""
    keyboard = [ #
        [InlineKeyboardButton(f"✏️ {prompt_message}", callback_data=callback_select_action)], #
        [InlineKeyboardButton("➡️ Пропустить", callback_data=callback_skip_action)], #
    ]
    return InlineKeyboardMarkup(keyboard) #

def get_yes_no_keyboard(yes_callback: str, no_callback: str, yes_text="Да", no_text="Нет"): #
    """Клавиатура Да/Нет."""
    keyboard = [ #
        [
            InlineKeyboardButton(yes_text, callback_data=yes_callback), #
            InlineKeyboardButton(no_text, callback_data=no_callback), #
        ]
    ]
    return InlineKeyboardMarkup(keyboard) #

def get_skip_dates_keyboard(callback_select_dates: str): #
    """Клавиатура для выбора дат или пропуска (поиск без указания дат)."""
    keyboard = [ #
        [InlineKeyboardButton("🗓 Выбрать конкретные даты", callback_data=callback_select_dates)], #
        [InlineKeyboardButton("✨ Искать без указания дат", callback_data=CALLBACK_NO_SPECIFIC_DATES)], #
    ]
    return InlineKeyboardMarkup(keyboard) #

def get_search_other_airports_keyboard(country_name: str): #
    """Клавиатура Да/Нет для поиска из других аэропортов указанной страны."""
    keyboard = [ #
        [
            InlineKeyboardButton(f"Да, искать из других в {country_name}", callback_data=CALLBACK_YES_OTHER_AIRPORTS), #
            InlineKeyboardButton("Нет, спасибо", callback_data=CALLBACK_NO_OTHER_AIRPORTS), #
        ]
    ]
    return InlineKeyboardMarkup(keyboard) #

# НОВАЯ ФУНКЦИЯ
def get_price_options_keyboard() -> InlineKeyboardMarkup:
    """Возвращает клавиатуру с выбором опции цены."""
    keyboard = [
        [InlineKeyboardButton("✏️ Задать свою цену", callback_data=CALLBACK_PRICE_CUSTOM)],
        [InlineKeyboardButton("📉 Самая низкая", callback_data=CALLBACK_PRICE_LOWEST)],
        [InlineKeyboardButton("📊 Показать всё", callback_data=CALLBACK_PRICE_ALL)],
    ]
    return InlineKeyboardMarkup(keyboard)