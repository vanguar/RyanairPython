# bot/keyboards.py
import logging
from datetime import datetime # Если используется для чего-то еще в этом файле
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from .config import (
    COUNTRIES_DATA, RUSSIAN_MONTHS, CALLBACK_SKIP, CALLBACK_NO_SPECIFIC_DATES,
    CALLBACK_YES_OTHER_AIRPORTS, CALLBACK_NO_OTHER_AIRPORTS,
    CALLBACK_PRICE_CUSTOM, CALLBACK_PRICE_LOWEST, CALLBACK_PRICE_ALL,
    MSG_BACK,
    # ... ваш существующий список импортов CB_BACK_... констант ...
    # Пример: CB_BACK_STD_DEP_YEAR_TO_CITY, CB_BACK_FLEX_RET_DATE_TO_RANGE, и т.д.
    MSG_FLIGHT_TYPE_PROMPT, # Если используется здесь

    # НОВЫЕ КОНСТАНТЫ ДЛЯ ИМПОРТА:
    CALLBACK_SAVE_SEARCH_YES, CALLBACK_SAVE_SEARCH_NO,
    CALLBACK_START_LAST_SAVED_SEARCH,
    CALLBACK_START_TOP3,
    CALLBACK_ENTIRE_RANGE_SELECTED
)

logger = logging.getLogger(__name__)

def get_main_menu_keyboard(has_saved_searches: bool = False) -> InlineKeyboardMarkup:
    """
    Главное меню бота. Вверху – новая кнопка «Топ-3 направления».
    """
    keyboard_buttons = [
        [InlineKeyboardButton("🔥 Топ-3 направления", callback_data=CALLBACK_START_TOP3)],
        [InlineKeyboardButton("✈️ Стандартный поиск", callback_data="start_standard_search")],
        [InlineKeyboardButton("✨ Гибкий поиск",        callback_data="start_flex_search")],
        [InlineKeyboardButton("🎯 Найти самый дешёвый билет (куда угодно)",
                              callback_data="start_flex_anywhere")],
    ]
    if has_saved_searches:
        keyboard_buttons.append(
            [InlineKeyboardButton("💾 Мой последний поиск",
                                  callback_data=CALLBACK_START_LAST_SAVED_SEARCH)]
        )
    return InlineKeyboardMarkup(keyboard_buttons)


def get_flight_type_reply_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура для выбора типа рейса (1 или 2)."""
    reply_keyboard = [['1', '2']]
    return ReplyKeyboardMarkup(
        reply_keyboard,
        one_time_keyboard=False,
        resize_keyboard=True,
        input_field_placeholder='1 (в одну) или 2 (в обе стороны)'
    )

def get_country_reply_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура для выбора страны."""
    if not COUNTRIES_DATA:
        logger.warning("Нет данных о странах для генерации клавиатуры.")
        return ReplyKeyboardMarkup([["Ошибка: нет данных о странах"]], one_time_keyboard=False, resize_keyboard=True)

    country_names = sorted(list(COUNTRIES_DATA.keys()))
    keyboard = [country_names[i:i + 3] for i in range(0, len(country_names), 3)]
    return ReplyKeyboardMarkup(keyboard, one_time_keyboard=False, resize_keyboard=True)

def get_city_reply_keyboard(
        country_name: str,
        override_cities: dict[str, str] | None = None,
) -> ReplyKeyboardMarkup:
    """
    Клавиатура городов. Если override_cities передан —
    строим клавиатуру из него, иначе берём данные из COUNTRIES_DATA.
    """
    cities_dict = override_cities or COUNTRIES_DATA.get(country_name, {})
    if not cities_dict:
        logger.warning(f"Нет городов для страны «{country_name}»")
        return ReplyKeyboardMarkup([["Нет доступных городов"]], one_time_keyboard=False, resize_keyboard=True)

    city_names = sorted(cities_dict.keys())
    keyboard = [city_names[i:i + 3] for i in range(0, len(city_names), 3)]
    return ReplyKeyboardMarkup(keyboard, one_time_keyboard=False, resize_keyboard=True)

def generate_year_buttons(callback_prefix: str = "", back_callback_data: str | None = None) -> InlineKeyboardMarkup:
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
) -> InlineKeyboardMarkup:
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
        if not back_callback_data:
             keyboard_rows.append([InlineKeyboardButton("Нет доступных месяцев", callback_data="no_valid_months_error")])
        elif not keyboard_rows:
             keyboard_rows = []

    if back_callback_data:
        if not keyboard_rows and not valid_month_found :
             keyboard_rows = [[InlineKeyboardButton(MSG_BACK, callback_data=back_callback_data)]]
        else:
             keyboard_rows.append([InlineKeyboardButton(MSG_BACK, callback_data=back_callback_data)])
    return InlineKeyboardMarkup(keyboard_rows)

def generate_date_range_buttons(year: int, month: int, callback_prefix: str = "", back_callback_data: str | None = None) -> InlineKeyboardMarkup:
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
        # Проверяем, чтобы конец диапазона был не раньше сегодняшнего дня, если это текущий месяц и год
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
        callback_prefix: str = "", # Это для callback'ов отдельных дат
        min_allowed_date: datetime | None = None,
        back_callback_data: str | None = None,
        # НОВЫЙ ПАРАМЕТР для определения типа диапазона (вылет/возврат)
        range_selection_type: str = "dep"  # "dep" или "ret"
    ) -> InlineKeyboardMarkup:
    final_button_rows = [] # Собираем все ряды кнопок здесь

    if min_allowed_date is None:
        min_allowed_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    # Корректируем date_range_start для отображения, если он раньше min_allowed_date
    # Это для того, чтобы не показывать кнопки для уже прошедших дней в начальном диапазоне
    # но для кнопки "Выбрать весь диапазон" используем оригинальные date_range_start, date_range_end
    # так как API сам отфильтрует, а пользователю может быть нужен весь указанный диапазон
    display_range_start = date_range_start
    if year == min_allowed_date.year and month == min_allowed_date.month:
        display_range_start = max(date_range_start, min_allowed_date.day)

    # 1. Кнопка "Выбрать весь диапазон"
    # Формат callback: entire_range_slctd_dep_YYYY-MM-DDstart-DDend
    # или entire_range_slctd_ret_YYYY-MM-DDstart-DDend
    entire_range_callback_data = (
        f"{CALLBACK_ENTIRE_RANGE_SELECTED}{range_selection_type}_"
        f"{year}-{month:02d}-{date_range_start:02d}-{date_range_end:02d}"
    )
    entire_range_button_text = f"Выбрать весь диапазон {date_range_start}-{date_range_end}"
    final_button_rows.append([InlineKeyboardButton(text=entire_range_button_text, callback_data=entire_range_callback_data)])

    # 2. Кнопки для отдельных дат
    individual_date_buttons_rows = []
    current_row = []
    any_button_created = False

    for day in range(display_range_start, date_range_end + 1): # Используем display_range_start для итерации
        try:
            # Проверяем, что сама дата не раньше минимально разрешенной
            current_date_obj_for_check = datetime(year, month, day)
            if current_date_obj_for_check < min_allowed_date:
                continue # Пропускаем даты раньше минимально разрешенной

            any_button_created = True
            date_str_callback = current_date_obj_for_check.strftime("%Y-%m-%d") # Полная дата для callback
            display_date_text = current_date_obj_for_check.strftime("%d") # Показываем только день
            current_row.append(InlineKeyboardButton(text=display_date_text, callback_data=f"{callback_prefix}{date_str_callback}"))
            if len(current_row) == 5: # Количество кнопок в ряду
                individual_date_buttons_rows.append(current_row)
                current_row = []
        except ValueError:
            logger.warning(f"Попытка создать кнопку для несуществующей даты: {year}-{month}-{day}")
            continue
    
    if current_row: # Добавляем оставшиеся кнопки, если есть
        individual_date_buttons_rows.append(current_row)
    
    final_button_rows.extend(individual_date_buttons_rows)

    # 3. Сообщение "Нет доступных дат", если не создано ни одной кнопки для отдельных дат
    # и диапазон display_range_start <= date_range_end был потенциально валиден
    if not any_button_created and display_range_start <= date_range_end:
        if not back_callback_data: # И нет кнопки "Назад", чтобы не было пусто
            # Эта кнопка-заглушка важна, чтобы пользователь понимал, почему нет дат
            final_button_rows.append([InlineKeyboardButton("Нет доступных дат в этом диапазоне", callback_data="no_specific_dates_in_range_error")])
        # Если есть кнопка "Назад", то сообщение "Нет доступных дат" не добавляем,
        # т.к. пользователь может вернуться назад. Пустая клавиатура (только с "Назад" и "Выбрать весь диапазон") допустима.

    # 4. Кнопка "Назад"
    if back_callback_data:
        final_button_rows.append([InlineKeyboardButton(MSG_BACK, callback_data=back_callback_data)])

    return InlineKeyboardMarkup(final_button_rows)

def get_price_options_keyboard(back_callback_data: str | None = None) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("✏️ Задать свою цену", callback_data=CALLBACK_PRICE_CUSTOM)],
        [InlineKeyboardButton("📉 Самая низкая", callback_data=CALLBACK_PRICE_LOWEST)],
        [InlineKeyboardButton("📊 Показать всё", callback_data=CALLBACK_PRICE_ALL)],
    ]
    if back_callback_data:
        keyboard.append([InlineKeyboardButton(MSG_BACK, callback_data=back_callback_data)])
    return InlineKeyboardMarkup(keyboard)

def get_yes_no_keyboard(yes_callback: str, no_callback: str, yes_text="Да", no_text="Нет", back_callback_data: str | None = None) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(yes_text, callback_data=yes_callback),
            InlineKeyboardButton(no_text, callback_data=no_callback),
        ]
    ]
    if back_callback_data:
        keyboard.append([InlineKeyboardButton(MSG_BACK, callback_data=back_callback_data)])
    return InlineKeyboardMarkup(keyboard)

def get_skip_dates_keyboard(callback_select_dates: str, back_callback_data: str | None = None) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🗓 Выбрать конкретные даты", callback_data=callback_select_dates)],
        [InlineKeyboardButton("✨ Искать без указания дат", callback_data=CALLBACK_NO_SPECIFIC_DATES)],
    ]
    if back_callback_data:
        keyboard.append([InlineKeyboardButton(MSG_BACK, callback_data=back_callback_data)])
    return InlineKeyboardMarkup(keyboard)

def get_search_other_airports_keyboard(country_name: str) -> InlineKeyboardMarkup:
    """Клавиатура Да/Нет для поиска из других аэропортов указанной страны."""
    keyboard = [
        [
            InlineKeyboardButton(f"Да, искать из других в {country_name}", callback_data=CALLBACK_YES_OTHER_AIRPORTS),
            InlineKeyboardButton("Нет, спасибо", callback_data=CALLBACK_NO_OTHER_AIRPORTS),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# НОВАЯ ФУНКЦИЯ (повторно, для полноты)
def get_save_search_keyboard() -> InlineKeyboardMarkup:
    """Возвращает клавиатуру с вопросом о сохранении поиска."""
    keyboard = [
        [
            InlineKeyboardButton("Да 👍", callback_data=CALLBACK_SAVE_SEARCH_YES),
            InlineKeyboardButton("Нет 👎", callback_data=CALLBACK_SAVE_SEARCH_NO),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)