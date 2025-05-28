# bot/keyboards.py
import logging
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from .config import (
    COUNTRIES_DATA, RUSSIAN_MONTHS, CALLBACK_SKIP, CALLBACK_NO_SPECIFIC_DATES,
    CALLBACK_YES_OTHER_AIRPORTS, CALLBACK_NO_OTHER_AIRPORTS,
    # Импорты для кнопок цены
    CALLBACK_PRICE_CUSTOM, CALLBACK_PRICE_LOWEST, CALLBACK_PRICE_ALL,
    MSG_BACK, # <--- ДОБАВИТЬ ЭТУ СТРОКУ
    CB_BACK_STD_DEP_YEAR_TO_CITY, CB_BACK_STD_DEP_MONTH_TO_YEAR,
    CB_BACK_STD_DEP_RANGE_TO_MONTH, CB_BACK_STD_DEP_DATE_TO_RANGE,
    CB_BACK_PRICE_TO_STD_ARR_CITY_ONEWAY, CB_BACK_PRICE_TO_STD_RET_DATE_TWOWAY,
    CB_BACK_STD_RET_YEAR_TO_ARR_CITY, CB_BACK_STD_RET_MONTH_TO_YEAR,
    CB_BACK_STD_RET_RANGE_TO_MONTH, CB_BACK_STD_RET_DATE_TO_RANGE,
    CB_BACK_PRICE_TO_ENTERING_CUSTOM,
    # ... и для гибкого поиска ...
    CB_BACK_PRICE_TO_FLEX_FLIGHT_TYPE, CB_BACK_FLEX_ASK_DEP_TO_PRICE,
    CB_BACK_FLEX_DEP_COUNTRY_TO_ASK_DEP, CB_BACK_FLEX_DEP_CITY_TO_DEP_COUNTRY,
    CB_BACK_FLEX_ASK_ARR_TO_DEP_CITY, CB_BACK_FLEX_ARR_COUNTRY_TO_ASK_ARR,
    CB_BACK_FLEX_ARR_CITY_TO_ARR_COUNTRY, CB_BACK_FLEX_ASK_DATES_TO_ARR_CITY,
    CB_BACK_FLEX_ASK_DATES_TO_DEP_CITY_NO_ARR, CB_BACK_FLEX_DEP_YEAR_TO_ASK_DATES,
    CB_BACK_FLEX_DEP_MONTH_TO_YEAR, CB_BACK_FLEX_DEP_RANGE_TO_MONTH,
    CB_BACK_FLEX_DEP_DATE_TO_RANGE, CB_BACK_FLEX_RET_YEAR_TO_DEP_DATE,
    CB_BACK_FLEX_RET_MONTH_TO_YEAR, CB_BACK_FLEX_RET_RANGE_TO_MONTH,
    CB_BACK_FLEX_RET_DATE_TO_RANGE,
    # Убедитесь, что MSG_FLIGHT_TYPE_PROMPT тоже импортирован, если используется напрямую в хендлерах
    MSG_FLIGHT_TYPE_PROMPT
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

# bot/keyboards.py
def get_flight_type_reply_keyboard():
    """Клавиатура для выбора типа рейса (1 или 2)."""
    reply_keyboard = [['1', '2']]
    return ReplyKeyboardMarkup(
        reply_keyboard,
        one_time_keyboard=False,  # ИЗМЕНЕНО
        resize_keyboard=True,
        input_field_placeholder='1 (в одну) или 2 (в обе стороны)' # ИЗМЕНЕНО
    )

# bot/keyboards.py
def get_country_reply_keyboard():
    """Клавиатура для выбора страны."""
    if not COUNTRIES_DATA:
        logger.warning("Нет данных о странах для генерации клавиатуры.")
        return ReplyKeyboardMarkup([["Ошибка: нет данных о странах"]], one_time_keyboard=False, resize_keyboard=True) # ИЗМЕНЕНО one_time_keyboard

    country_names = sorted(list(COUNTRIES_DATA.keys()))
    # Можно добавить кнопку "Назад" сюда, если это первый шаг после выбора типа рейса
    # keyboard = [country_names[i:i + 3] for i in range(0, len(country_names), 3)]
    # keyboard.append([MSG_BACK]) # Пример, если кнопка "Назад" нужна здесь как Reply кнопка
    # Но для ReplyKeyboard "Назад" лучше обрабатывать как текстовую команду в fallbacks или MessageHandler.
    # Для инлайн-переходов "Назад" будет инлайн-кнопкой.
    # Пока оставим без кнопки "Назад", т.к. предыдущий шаг - выбор типа рейса (ReplyKeyboard).
    # Возврат к типу рейса проще сделать командой /start или если пользователь введет неверную страну.
    keyboard = [country_names[i:i + 3] for i in range(0, len(country_names), 3)]
    return ReplyKeyboardMarkup(keyboard, one_time_keyboard=False, resize_keyboard=True) # ИЗМЕНЕНО one_time_keyboard

# bot/keyboards.py
def get_city_reply_keyboard(
        country_name: str,
        override_cities: dict[str, str] | None = None,
):
    """
    Клавиатура городов. Если override_cities передан —
    строим клавиатуру из него, иначе берём данные из COUNTRIES_DATA.
    """
    cities_dict = override_cities or COUNTRIES_DATA.get(country_name, {})
    if not cities_dict:
        logger.warning(f"Нет городов для страны «{country_name}»")
        return ReplyKeyboardMarkup([["Нет доступных городов"]], one_time_keyboard=False, resize_keyboard=True) # ИЗМЕНЕНО one_time_keyboard

    city_names = sorted(cities_dict.keys())
    keyboard = [city_names[i:i + 3] for i in range(0, len(city_names), 3)]
    # Аналогично get_country_reply_keyboard, кнопку "Назад" как Reply кнопку здесь не добавляем.
    # Возврат к выбору страны при ошибке ввода города уже реализован.
    return ReplyKeyboardMarkup(keyboard, one_time_keyboard=False, resize_keyboard=True) # ИЗМЕНЕНО one_time_keyboard

# bot/keyboards.py

def generate_year_buttons(callback_prefix: str = "", back_callback_data: str | None = None):
    current_year = datetime.now().year
    next_year = current_year + 1
    keyboard = [
        [InlineKeyboardButton(text=str(current_year), callback_data=f"{callback_prefix}{current_year}")],
        [InlineKeyboardButton(text=str(next_year), callback_data=f"{callback_prefix}{next_year}")]
    ]
    if back_callback_data:
        keyboard.append([InlineKeyboardButton(MSG_BACK, callback_data=back_callback_data)])
    return InlineKeyboardMarkup(keyboard)

def generate_month_buttons(
        callback_prefix: str = "",
        year_for_months: int | None = None,
        min_departure_month: int | None = None,
        departure_year_for_comparison: int | None = None,
        back_callback_data: str | None = None
):
    now = datetime.now()
    cur_year, cur_month = now.year, now.month
    keyboard_rows = []
    month_items = list(RUSSIAN_MONTHS.items())

    if year_for_months is None:
        year_for_months = cur_year

    current_row = []
    valid_month_found = False
    for idx, month_name in month_items:
        is_past_month = (year_for_months == cur_year and idx < cur_month)
        is_before_min_departure = (
            min_departure_month is not None and
            departure_year_for_comparison is not None and
            departure_year_for_comparison == year_for_months and
            idx < min_departure_month
        )
        if is_past_month or is_before_min_departure:
            continue
        valid_month_found = True
        callback_data = f"{callback_prefix}{str(idx).zfill(2)}"
        current_row.append(InlineKeyboardButton(text=month_name, callback_data=callback_data))
        if len(current_row) == 3:
            keyboard_rows.append(current_row)
            current_row = []
    if current_row:
        keyboard_rows.append(current_row)

    if not valid_month_found:
        # Если нет валидных месяцев, но есть кнопка "Назад", не показываем "Нет доступных месяцев"
        if not back_callback_data:
             keyboard_rows.append([InlineKeyboardButton("Нет доступных месяцев", callback_data="no_valid_months_error")])
        elif not keyboard_rows: # Если keyboard_rows пуст и есть back_callback_data
             keyboard_rows = [] # Убедимся, что не будет кнопки "Нет доступных месяцев"

    if back_callback_data:
        if not keyboard_rows and not valid_month_found : # Если список кнопок пуст (например, все отфильтровано)
             keyboard_rows = [[InlineKeyboardButton(MSG_BACK, callback_data=back_callback_data)]]
        else:
             keyboard_rows.append([InlineKeyboardButton(MSG_BACK, callback_data=back_callback_data)])
    return InlineKeyboardMarkup(keyboard_rows)

def generate_date_range_buttons(year: int, month: int, callback_prefix: str = "", back_callback_data: str | None = None):
    today = datetime.now().date()
    try:
        days_in_month = (datetime(year, month + 1, 1) - datetime(year, month, 1)).days if month != 12 else (datetime(year + 1, 1, 1) - datetime(year, month, 1)).days
    except ValueError:
        logger.error(f"Неверный год/месяц {year}-{month} для generate_date_range_buttons")
        rows = []
        if back_callback_data:
            rows.append([InlineKeyboardButton(MSG_BACK, callback_data=back_callback_data)])
        return InlineKeyboardMarkup(rows)

    ranges = [(1, 10), (11, 20), (21, days_in_month)]
    keyboard_buttons = []
    valid_range_found = False

    for start, end_limit in ranges:
        actual_end = min(end_limit, days_in_month)
        if start > actual_end: continue
        if year == today.year and month == today.month and actual_end < today.day: continue
        valid_range_found = True
        cb = f"{callback_prefix}{start}-{actual_end}"
        keyboard_buttons.append([InlineKeyboardButton(f"{start}-{actual_end}", callback_data=cb)])

    if not valid_range_found:
        if not back_callback_data:
            keyboard_buttons.append([InlineKeyboardButton("Нет доступных дат в этом месяце", callback_data="no_valid_date_ranges_error")])
        elif not keyboard_buttons:
             keyboard_buttons = []


    if back_callback_data:
        if not keyboard_buttons and not valid_range_found:
             keyboard_buttons = [[InlineKeyboardButton(MSG_BACK, callback_data=back_callback_data)]]
        else:
             keyboard_buttons.append([InlineKeyboardButton(MSG_BACK, callback_data=back_callback_data)])
    return InlineKeyboardMarkup(keyboard_buttons)

def generate_specific_date_buttons(
        year: int, month: int, date_range_start: int, date_range_end: int,
        callback_prefix: str = "", min_allowed_date: datetime | None = None,
        back_callback_data: str | None = None
    ):
    buttons_rows = []
    current_row = []
    if min_allowed_date is None:
        min_allowed_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    any_button_created = False
    for day in range(date_range_start, date_range_end + 1):
        try:
            date_obj = datetime(year, month, day)
            if date_obj < min_allowed_date: continue
            any_button_created = True
            date_str_callback = date_obj.strftime("%Y-%m-%d")
            display_date = date_obj.strftime("%d")
            current_row.append(InlineKeyboardButton(text=display_date, callback_data=f"{callback_prefix}{date_str_callback}"))
            if len(current_row) == 5:
                buttons_rows.append(current_row)
                current_row = []
        except ValueError:
            logger.warning(f"Попытка создать кнопку для несуществующей даты: {year}-{month}-{day}")
            continue
    if current_row:
        buttons_rows.append(current_row)

    if not any_button_created and date_range_start <= date_range_end:
        if not back_callback_data:
            buttons_rows.append([InlineKeyboardButton("Нет доступных дат в этом диапазоне", callback_data="no_specific_dates_in_range_error")])
        elif not buttons_rows: # Если buttons_rows пуст и есть back_callback_data
             buttons_rows = []

    if back_callback_data:
        if not buttons_rows and not any_button_created:
             buttons_rows = [[InlineKeyboardButton(MSG_BACK, callback_data=back_callback_data)]]
        else:
             buttons_rows.append([InlineKeyboardButton(MSG_BACK, callback_data=back_callback_data)])

    return InlineKeyboardMarkup(buttons_rows)

def get_price_options_keyboard(back_callback_data: str | None = None) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("✏️ Задать свою цену", callback_data=CALLBACK_PRICE_CUSTOM)],
        [InlineKeyboardButton("📉 Самая низкая", callback_data=CALLBACK_PRICE_LOWEST)],
        [InlineKeyboardButton("📊 Показать всё", callback_data=CALLBACK_PRICE_ALL)],
    ]
    if back_callback_data:
        keyboard.append([InlineKeyboardButton(MSG_BACK, callback_data=back_callback_data)])
    return InlineKeyboardMarkup(keyboard)

def get_yes_no_keyboard(yes_callback: str, no_callback: str, yes_text="Да", no_text="Нет", back_callback_data: str | None = None):
    keyboard = [
        [
            InlineKeyboardButton(yes_text, callback_data=yes_callback),
            InlineKeyboardButton(no_text, callback_data=no_callback),
        ]
    ]
    if back_callback_data:
        keyboard.append([InlineKeyboardButton(MSG_BACK, callback_data=back_callback_data)])
    return InlineKeyboardMarkup(keyboard)

def get_skip_dates_keyboard(callback_select_dates: str, back_callback_data: str | None = None):
    keyboard = [
        [InlineKeyboardButton("🗓 Выбрать конкретные даты", callback_data=callback_select_dates)],
        [InlineKeyboardButton("✨ Искать без указания дат", callback_data=CALLBACK_NO_SPECIFIC_DATES)],
    ]
    if back_callback_data:
        keyboard.append([InlineKeyboardButton(MSG_BACK, callback_data=back_callback_data)])
    return InlineKeyboardMarkup(keyboard)

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