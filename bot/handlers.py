# bot/handlers.py
import logging
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
    CallbackQueryHandler,
)
from datetime import datetime

from . import config, keyboards, helpers, flight_api

logger = logging.getLogger(__name__)

# --- Вспомогательные функции для обработчиков ---
async def ask_departure_country(update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str):
    await update.message.reply_text(
        message_text,
        reply_markup=keyboards.get_country_reply_keyboard()
    )

async def ask_departure_city(update: Update, context: ContextTypes.DEFAULT_TYPE, country_name: str):
    await update.message.reply_text(
        "Выберите город вылета:",
        reply_markup=keyboards.get_city_reply_keyboard(country_name)
    )

async def ask_arrival_country(update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str):
    await update.message.reply_text(
        message_text,
        reply_markup=keyboards.get_country_reply_keyboard()
    )

async def ask_arrival_city(update: Update, context: ContextTypes.DEFAULT_TYPE, country_name: str):
    await update.message.reply_text(
        "Выберите город прилёта:",
        reply_markup=keyboards.get_city_reply_keyboard(country_name)
    )

async def ask_year(update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str, callback_prefix: str = ""):
    if update.callback_query: # Если это callback от inline кнопки
        await update.callback_query.edit_message_text(
            text=message_text,
            reply_markup=keyboards.generate_year_buttons(callback_prefix)
        )
    else: # Если это сообщение от пользователя
        await update.message.reply_text(
            message_text,
            reply_markup=keyboards.generate_year_buttons(callback_prefix)
        )

async def ask_month(update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str, callback_prefix: str = ""):
    await update.callback_query.edit_message_text(
        text=message_text,
        reply_markup=keyboards.generate_month_buttons(callback_prefix)
    )

async def ask_date_range(update: Update, context: ContextTypes.DEFAULT_TYPE, year: int, month: int, message_text: str, callback_prefix: str = ""):
    await update.callback_query.edit_message_text(
        text=message_text,
        reply_markup=keyboards.generate_date_range_buttons(year, month, callback_prefix)
    )

async def ask_specific_date(update: Update, context: ContextTypes.DEFAULT_TYPE, year: int, month: int, range_start: int, range_end: int, message_text: str, callback_prefix: str = ""):
    await update.callback_query.edit_message_text(
        text=message_text,
        reply_markup=keyboards.generate_specific_date_buttons(year, month, range_start, range_end, callback_prefix)
    )

async def process_and_send_flights(update: Update, context: ContextTypes.DEFAULT_TYPE, flights: list):
    chat_id = update.effective_chat.id
    if not flights:
        await context.bot.send_message(chat_id=chat_id, text=config.MSG_NO_FLIGHTS_FOUND)
    else:
        await context.bot.send_message(chat_id=chat_id, text=config.MSG_FLIGHTS_FOUND_SEE_BELOW)
        for flight in flights[:10]: # Ограничиваем вывод, чтобы не спамить (например, первые 10)
            formatted_flight = helpers.format_flight_details(flight)
            await context.bot.send_message(chat_id=chat_id, text=formatted_flight, parse_mode='Markdown')
        if len(flights) > 10:
            await context.bot.send_message(chat_id=chat_id, text=f"... и еще {len(flights) - 10} рейсов.")
    
    await context.bot.send_message(chat_id=chat_id, text=config.MSG_NEW_SEARCH_PROMPT, reply_markup=ReplyKeyboardRemove())


# --- Обработчики команды /start и выбора типа поиска ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет приветственное сообщение и кнопки выбора типа поиска."""
    await update.message.reply_text(config.MSG_WELCOME, reply_markup=keyboards.get_main_menu_keyboard())

async def start_search_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает нажатие на inline кнопки выбора типа поиска."""
    query = update.callback_query
    await query.answer()
    
    context.user_data.clear() # Очищаем данные предыдущего поиска

    if query.data == "start_standard_search":
        await query.edit_message_text(text="Выбран стандартный поиск.")
        await query.message.reply_text(config.MSG_FLIGHT_TYPE_PROMPT, reply_markup=keyboards.get_flight_type_reply_keyboard())
        return config.SELECTING_FLIGHT_TYPE
    elif query.data == "start_flex_search":
        await query.edit_message_text(text="Выбран гибкий поиск.")
        await query.message.reply_text(config.MSG_FLIGHT_TYPE_PROMPT, reply_markup=keyboards.get_flight_type_reply_keyboard())
        return config.SELECTING_FLEX_FLIGHT_TYPE
    return ConversationHandler.END


# --- СТАНДАРТНЫЙ ПОИСК ---
async def standard_flight_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_input = update.message.text
    if user_input not in ['1', '2']:
        await update.message.reply_text("Пожалуйста, выберите 1 или 2.", reply_markup=keyboards.get_flight_type_reply_keyboard())
        return config.SELECTING_FLIGHT_TYPE
    context.user_data['flight_type_one_way'] = (user_input == '1')
    await ask_departure_country(update, context, "Выберите страну вылета:")
    return config.SELECTING_DEPARTURE_COUNTRY

async def standard_departure_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    country = update.message.text
    if country not in config.COUNTRIES_DATA:
        await update.message.reply_text("Страна не найдена! Пожалуйста, выберите из списка.")
        return config.SELECTING_DEPARTURE_COUNTRY
    context.user_data['departure_country'] = country
    await ask_departure_city(update, context, country)
    return config.SELECTING_DEPARTURE_CITY

async def standard_departure_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    city = update.message.text
    country = context.user_data.get('departure_country')
    iata_code = helpers.get_airport_iata(country, city)
    if not iata_code:
        await update.message.reply_text("Город не найден или неверная страна! Пожалуйста, выберите из списка.")
        # Можно вернуть к выбору страны или города
        await ask_departure_city(update, context, country) # Повторный запрос города
        return config.SELECTING_DEPARTURE_CITY
        
    context.user_data['departure_airport_iata'] = iata_code
    context.user_data['departure_city_name'] = city
    await ask_year(update, context, "Выберите год вылета:", callback_prefix=config.CALLBACK_PREFIX_STANDARD + "dep_year_")
    return config.SELECTING_DEPARTURE_YEAR

async def standard_departure_year_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selected_year = int(query.data.replace(config.CALLBACK_PREFIX_STANDARD + "dep_year_", ""))
    context.user_data['departure_year'] = selected_year
    await ask_month(update, context, f"Год вылета: {selected_year}. Выберите месяц:", callback_prefix=config.CALLBACK_PREFIX_STANDARD + "dep_month_")
    return config.SELECTING_DEPARTURE_MONTH

async def standard_departure_month_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selected_month = int(query.data.replace(config.CALLBACK_PREFIX_STANDARD + "dep_month_", ""))
    context.user_data['departure_month'] = selected_month
    year = context.user_data['departure_year']
    month_name = config.RUSSIAN_MONTHS.get(selected_month, "")
    await ask_date_range(update, context, year, selected_month, f"Выбран: {month_name} {year}. Выберите диапазон дат:", callback_prefix=config.CALLBACK_PREFIX_STANDARD + "dep_range_")
    return config.SELECTING_DEPARTURE_DATE_RANGE

async def standard_departure_date_range_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selected_range = query.data.replace(config.CALLBACK_PREFIX_STANDARD + "dep_range_", "")
    try:
        start_day, end_day = map(int, selected_range.split('-'))
    except ValueError:
        await query.edit_message_text(text="Некорректный диапазон дат. Пожалуйста, выберите снова.")
        # Вернуть к выбору месяца или диапазона
        return config.SELECTING_DEPARTURE_MONTH # Пример
    
    year = context.user_data['departure_year']
    month = context.user_data['departure_month']
    await ask_specific_date(update, context, year, month, start_day, end_day, f"Диапазон: {selected_range}. Выберите дату:", callback_prefix=config.CALLBACK_PREFIX_STANDARD + "dep_date_")
    return config.SELECTING_DEPARTURE_DATE

async def standard_departure_date_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selected_date_str = query.data.replace(config.CALLBACK_PREFIX_STANDARD + "dep_date_", "") # YYYY-MM-DD
    
    date_obj = helpers.validate_date_format(selected_date_str)
    if not date_obj or date_obj < datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) :
        await query.edit_message_text("Некорректная дата или дата в прошлом. Попробуйте снова.")
        # Можно вернуть к предыдущему шагу
        return config.SELECTING_DEPARTURE_DATE_RANGE

    context.user_data['departure_date'] = selected_date_str
    formatted_date = date_obj.strftime('%d-%m-%Y')
    await query.edit_message_text(text=f"Дата вылета: {formatted_date}")
    
    # Убираем ReplyKeyboard после выбора даты через Inline
    await query.message.reply_text("Теперь выберите страну прилёта:", reply_markup=ReplyKeyboardRemove())
    await ask_arrival_country(query.message, context, "Выберите страну прилёта:") # Используем query.message для отправки нового сообщения
    return config.SELECTING_ARRIVAL_COUNTRY

async def standard_arrival_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    country = update.message.text
    if country not in config.COUNTRIES_DATA:
        await update.message.reply_text("Страна не найдена! Пожалуйста, выберите из списка.")
        return config.SELECTING_ARRIVAL_COUNTRY
    context.user_data['arrival_country'] = country
    await ask_arrival_city(update, context, country)
    return config.SELECTING_ARRIVAL_CITY

async def standard_arrival_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    city = update.message.text
    country = context.user_data.get('arrival_country')
    iata_code = helpers.get_airport_iata(country, city)

    if not iata_code:
        await update.message.reply_text("Город не найден или неверная страна! Пожалуйста, выберите из списка.")
        await ask_arrival_city(update, context, country)
        return config.SELECTING_ARRIVAL_CITY
    
    if iata_code == context.user_data.get('departure_airport_iata'):
        await update.message.reply_text("Аэропорт прилёта не может совпадать с аэропортом вылета. Выберите другой город.")
        await ask_arrival_city(update, context, country)
        return config.SELECTING_ARRIVAL_CITY

    context.user_data['arrival_airport_iata'] = iata_code
    context.user_data['arrival_city_name'] = city
    
    if context.user_data.get('flight_type_one_way', True):
        await update.message.reply_text(config.MSG_MAX_PRICE_PROMPT, reply_markup=ReplyKeyboardRemove())
        return config.SELECTING_MAX_PRICE
    else:
        await ask_year(update, context, "Выберите год обратного вылета:", callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_year_")
        return config.SELECTING_RETURN_YEAR

async def standard_return_year_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selected_year = int(query.data.replace(config.CALLBACK_PREFIX_STANDARD + "ret_year_", ""))
    context.user_data['return_year'] = selected_year
    await ask_month(update, context, f"Год обратного вылета: {selected_year}. Выберите месяц:", callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_month_")
    return config.SELECTING_RETURN_MONTH

async def standard_return_month_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selected_month = int(query.data.replace(config.CALLBACK_PREFIX_STANDARD + "ret_month_", ""))
    context.user_data['return_month'] = selected_month
    year = context.user_data['return_year']
    month_name = config.RUSSIAN_MONTHS.get(selected_month, "")
    await ask_date_range(update, context, year, selected_month, f"Выбран: {month_name} {year}. Выберите диапазон дат:", callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_range_")
    return config.SELECTING_RETURN_DATE_RANGE

async def standard_return_date_range_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selected_range = query.data.replace(config.CALLBACK_PREFIX_STANDARD + "ret_range_", "")
    try:
        start_day, end_day = map(int, selected_range.split('-'))
    except ValueError: # Обработка ошибки, если диапазон некорректен
        await query.edit_message_text("Ошибка в диапазоне дат. Попробуйте выбрать месяц заново.")
        # Вернуть к выбору месяца
        year = context.user_data['return_year']
        await ask_month(update, context, f"Год обратного вылета: {year}. Выберите месяц:", callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_month_")
        return config.SELECTING_RETURN_MONTH

    year = context.user_data['return_year']
    month = context.user_data['return_month']
    await ask_specific_date(update, context, year, month, start_day, end_day, f"Диапазон: {selected_range}. Выберите дату:", callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_date_")
    return config.SELECTING_RETURN_DATE

async def standard_return_date_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selected_date_str = query.data.replace(config.CALLBACK_PREFIX_STANDARD + "ret_date_", "") # YYYY-MM-DD

    departure_date_obj = helpers.validate_date_format(context.user_data['departure_date'])
    return_date_obj = helpers.validate_date_format(selected_date_str)

    if not return_date_obj or not departure_date_obj or return_date_obj < departure_date_obj:
        await query.edit_message_text("Некорректная дата возвращения или она раньше даты вылета. Попробуйте снова.")
        # Можно вернуть к предыдущему шагу
        return config.SELECTING_RETURN_DATE_RANGE
        
    context.user_data['return_date'] = selected_date_str
    formatted_date = return_date_obj.strftime('%d-%m-%Y')
    await query.edit_message_text(text=f"Дата обратного вылета: {formatted_date}")
    
    await query.message.reply_text(config.MSG_MAX_PRICE_PROMPT, reply_markup=ReplyKeyboardRemove())
    return config.SELECTING_MAX_PRICE

async def standard_max_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    price = helpers.validate_price(update.message.text)
    if price is None:
        await update.message.reply_text("Некорректная цена. Введите положительное число, например, 50:")
        return config.SELECTING_MAX_PRICE
    
    context.user_data['max_price'] = price
    await update.message.reply_text(config.MSG_SEARCHING_FLIGHTS)
    
    # Вызов логики поиска
    flights = await flight_api.find_flights_with_fallback(
        departure_airport_iata=context.user_data['departure_airport_iata'],
        arrival_airport_iata=context.user_data['arrival_airport_iata'],
        departure_date_str=context.user_data['departure_date'],
        max_price=context.user_data['max_price'],
        return_date_str=context.user_data.get('return_date'),
        is_one_way=context.user_data.get('flight_type_one_way', True)
    )
    await process_and_send_flights(update, context, flights)
    context.user_data.clear()
    return ConversationHandler.END

# (Продолжение в следующей части для гибкого поиска)

# bot/handlers.py (Продолжение)
import logging
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import ConversationHandler, ContextTypes
from . import config, keyboards, helpers, flight_api

logger = logging.getLogger(__name__)

# --- ГИБКИЙ ПОИСК ---
async def flex_flight_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_input = update.message.text
    if user_input not in ['1', '2']:
        await update.message.reply_text("Пожалуйста, выберите 1 или 2.", reply_markup=keyboards.get_flight_type_reply_keyboard())
        return config.SELECTING_FLEX_FLIGHT_TYPE
    context.user_data['flight_type_one_way'] = (user_input == '1')
    await update.message.reply_text(config.MSG_MAX_PRICE_PROMPT, reply_markup=ReplyKeyboardRemove())
    return config.SELECTING_FLEX_MAX_PRICE

async def flex_max_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    price = helpers.validate_price(update.message.text)
    if price is None:
        await update.message.reply_text("Некорректная цена. Введите положительное число, например, 50:")
        return config.SELECTING_FLEX_MAX_PRICE
    context.user_data['max_price'] = price
    
    # Спрашиваем про аэропорт вылета
    await update.message.reply_text(
        "Указать аэропорт вылета?",
        reply_markup=keyboards.get_yes_no_keyboard(
            yes_callback=config.CALLBACK_PREFIX_FLEX + "ask_dep_yes",
            no_callback=config.CALLBACK_PREFIX_FLEX + "ask_dep_no"
        )
    )
    return config.ASK_FLEX_DEPARTURE_AIRPORT

async def flex_ask_departure_airport(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    if query.data == config.CALLBACK_PREFIX_FLEX + "ask_dep_yes":
        await query.edit_message_text(text="Аэропорт вылета: ДА")
        # Переходим к выбору страны вылета
        await query.message.reply_text("Выберите страну вылета:", reply_markup=keyboards.get_country_reply_keyboard())
        return config.SELECTING_FLEX_DEPARTURE_COUNTRY
    else: # "ask_dep_no"
        await query.edit_message_text(text="Аэропорт вылета: НЕТ (поиск из любого)")
        context.user_data['departure_airport_iata'] = None # Признак "любой аэропорт вылета"
        # Сразу переходим к вопросу об аэропорте прилёта
        await query.message.reply_text(
            "Указать аэропорт прилёта?",
            reply_markup=keyboards.get_yes_no_keyboard(
                yes_callback=config.CALLBACK_PREFIX_FLEX + "ask_arr_yes",
                no_callback=config.CALLBACK_PREFIX_FLEX + "ask_arr_no"
            )
        )
        return config.ASK_FLEX_ARRIVAL_AIRPORT

async def flex_departure_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    country = update.message.text
    if country not in config.COUNTRIES_DATA:
        await update.message.reply_text("Страна не найдена! Пожалуйста, выберите из списка.")
        return config.SELECTING_FLEX_DEPARTURE_COUNTRY
    context.user_data['departure_country'] = country
    await update.message.reply_text("Выберите город вылета:", reply_markup=keyboards.get_city_reply_keyboard(country))
    return config.SELECTING_FLEX_DEPARTURE_CITY

async def flex_departure_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    city = update.message.text
    country = context.user_data.get('departure_country')
    iata_code = helpers.get_airport_iata(country, city)
    if not iata_code:
        await update.message.reply_text("Город не найден! Пожалуйста, выберите из списка.")
        await update.message.reply_text("Выберите город вылета:", reply_markup=keyboards.get_city_reply_keyboard(country))
        return config.SELECTING_FLEX_DEPARTURE_CITY
        
    context.user_data['departure_airport_iata'] = iata_code
    context.user_data['departure_city_name'] = city
    
    # Переходим к вопросу об аэропорте прилёта
    await update.message.reply_text(
        "Указать аэропорт прилёта?",
        reply_markup=keyboards.get_yes_no_keyboard(
            yes_callback=config.CALLBACK_PREFIX_FLEX + "ask_arr_yes",
            no_callback=config.CALLBACK_PREFIX_FLEX + "ask_arr_no"
        )
    )
    return config.ASK_FLEX_ARRIVAL_AIRPORT

async def flex_ask_arrival_airport(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    if query.data == config.CALLBACK_PREFIX_FLEX + "ask_arr_yes":
        await query.edit_message_text(text="Аэропорт прилёта: ДА")
        await query.message.reply_text("Выберите страну прилёта:", reply_markup=keyboards.get_country_reply_keyboard())
        return config.SELECTING_FLEX_ARRIVAL_COUNTRY
    else: # "ask_arr_no"
        await query.edit_message_text(text="Аэропорт прилёта: НЕТ (поиск в любом направлении)")
        context.user_data['arrival_airport_iata'] = None # Признак "любое направление"
        # Переходим к вопросу о датах
        await query.message.reply_text(
            "Указать конкретные даты?",
            reply_markup=keyboards.get_skip_dates_keyboard(
                callback_select_dates=config.CALLBACK_PREFIX_FLEX + "ask_dates_yes"
            )
        )
        return config.ASK_FLEX_DATES

async def flex_arrival_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    country = update.message.text
    if country not in config.COUNTRIES_DATA:
        await update.message.reply_text("Страна не найдена! Пожалуйста, выберите из списка.")
        return config.SELECTING_FLEX_ARRIVAL_COUNTRY
    context.user_data['arrival_country'] = country
    await update.message.reply_text("Выберите город прилёта:", reply_markup=keyboards.get_city_reply_keyboard(country))
    return config.SELECTING_FLEX_ARRIVAL_CITY

async def flex_arrival_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    city = update.message.text
    country = context.user_data.get('arrival_country')
    iata_code = helpers.get_airport_iata(country, city)
    if not iata_code:
        await update.message.reply_text("Город не найден! Пожалуйста, выберите из списка.")
        await update.message.reply_text("Выберите город прилёта:", reply_markup=keyboards.get_city_reply_keyboard(country))
        return config.SELECTING_FLEX_ARRIVAL_CITY
    
    # Проверка, что аэропорт прилета не совпадает с аэропортом вылета, если вылет указан
    if context.user_data.get('departure_airport_iata') and iata_code == context.user_data['departure_airport_iata']:
        await update.message.reply_text("Аэропорт прилёта не может совпадать с аэропортом вылета. Выберите другой город.")
        await update.message.reply_text("Выберите город прилёта:", reply_markup=keyboards.get_city_reply_keyboard(country))
        return config.SELECTING_FLEX_ARRIVAL_CITY

    context.user_data['arrival_airport_iata'] = iata_code
    context.user_data['arrival_city_name'] = city
    
    # Переходим к вопросу о датах
    await update.message.reply_text(
        "Указать конкретные даты?",
        reply_markup=keyboards.get_skip_dates_keyboard(
            callback_select_dates=config.CALLBACK_PREFIX_FLEX + "ask_dates_yes"
        )
    )
    return config.ASK_FLEX_DATES

async def flex_ask_dates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == config.CALLBACK_PREFIX_FLEX + "ask_dates_yes":
        await query.edit_message_text(text="Даты: ДА, указать конкретные.")
        # Начинаем выбор дат (год вылета)
        await ask_year(query.message, context, "Выберите год вылета:", callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_year_")
        return config.SELECTING_FLEX_DEPARTURE_YEAR # Используем новые состояния для гибкого поиска дат
    
    elif query.data == config.CALLBACK_NO_SPECIFIC_DATES: # Искать без указания дат
        await query.edit_message_text(text="Даты: НЕТ, искать на ближайший год.")
        context.user_data['departure_date'] = None # Признак поиска без даты
        context.user_data['return_date'] = None

        # Проверяем, был ли указан аэропорт вылета. Если нет, то поиск невозможен.
        if context.user_data.get('departure_airport_iata') is None:
            await query.message.reply_text(
                "Ошибка: для поиска без указания дат необходимо указать хотя бы аэропорт вылета.\n"
                "Пожалуйста, начните гибкий поиск заново: /flexsearch",
                reply_markup=ReplyKeyboardRemove()
            )
            context.user_data.clear()
            return ConversationHandler.END
            
        await query.message.reply_text(config.MSG_SEARCHING_FLIGHTS, reply_markup=ReplyKeyboardRemove())
        # Сразу переходим к поиску
        flights = await flight_api.find_flights_with_fallback(
            departure_airport_iata=context.user_data['departure_airport_iata'],
            arrival_airport_iata=context.user_data.get('arrival_airport_iata'), # Может быть None
            departure_date_str=None, # Искать на год
            max_price=context.user_data['max_price'],
            return_date_str=None, # Искать на год
            is_one_way=context.user_data.get('flight_type_one_way', True)
        )
        await process_and_send_flights(query.message, context, flights) # Используем query.message
        context.user_data.clear()
        return ConversationHandler.END
    return config.ASK_FLEX_DATES # Остаемся в этом состоянии, если callback не распознан

# Обработчики для выбора дат в гибком поиске (аналогичны стандартному, но с префиксом FLEX)
async def flex_departure_year_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selected_year = int(query.data.replace(config.CALLBACK_PREFIX_FLEX + "dep_year_", ""))
    context.user_data['departure_year'] = selected_year
    await ask_month(update, context, f"Год вылета: {selected_year}. Выберите месяц:", callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_month_")
    return config.SELECTING_FLEX_DEPARTURE_MONTH

async def flex_departure_month_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selected_month = int(query.data.replace(config.CALLBACK_PREFIX_FLEX + "dep_month_", ""))
    context.user_data['departure_month'] = selected_month
    year = context.user_data['departure_year']
    month_name = config.RUSSIAN_MONTHS.get(selected_month, "")
    await ask_date_range(update, context, year, selected_month, f"Выбран: {month_name} {year}. Выберите диапазон дат:", callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_range_")
    return config.SELECTING_FLEX_DEPARTURE_DATE_RANGE

async def flex_departure_date_range_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selected_range = query.data.replace(config.CALLBACK_PREFIX_FLEX + "dep_range_", "")
    start_day, end_day = map(int, selected_range.split('-'))
    year = context.user_data['departure_year']
    month = context.user_data['departure_month']
    await ask_specific_date(update, context, year, month, start_day, end_day, f"Диапазон: {selected_range}. Выберите дату:", callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_date_")
    return config.SELECTING_FLEX_DEPARTURE_DATE

async def flex_departure_date_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selected_date_str = query.data.replace(config.CALLBACK_PREFIX_FLEX + "dep_date_", "")
    date_obj = helpers.validate_date_format(selected_date_str)
    if not date_obj or date_obj < datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) :
        await query.edit_message_text("Некорректная дата или дата в прошлом. Попробуйте снова.")
        return config.SELECTING_FLEX_DEPARTURE_DATE_RANGE

    context.user_data['departure_date'] = selected_date_str
    formatted_date = date_obj.strftime('%d-%m-%Y')
    
    if context.user_data.get('flight_type_one_way', True):
        await query.edit_message_text(text=f"Дата вылета: {formatted_date}")
        await query.message.reply_text(config.MSG_SEARCHING_FLIGHTS, reply_markup=ReplyKeyboardRemove())
        # Сразу поиск
        flights = await flight_api.find_flights_with_fallback(
            departure_airport_iata=context.user_data['departure_airport_iata'],
            arrival_airport_iata=context.user_data.get('arrival_airport_iata'),
            departure_date_str=context.user_data['departure_date'],
            max_price=context.user_data['max_price'],
            is_one_way=True
        )
        await process_and_send_flights(query.message, context, flights)
        context.user_data.clear()
        return ConversationHandler.END
    else:
        # Нужна дата возврата
        await query.edit_message_text(text=f"Дата вылета: {formatted_date}")
        await ask_year(query.message, context, "Выберите год обратного вылета:", callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_year_")
        return config.SELECTING_FLEX_RETURN_YEAR

async def flex_return_year_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selected_year = int(query.data.replace(config.CALLBACK_PREFIX_FLEX + "ret_year_", ""))
    context.user_data['return_year'] = selected_year
    await ask_month(update, context, f"Год обратного вылета: {selected_year}. Выберите месяц:", callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_month_")
    return config.SELECTING_FLEX_RETURN_MONTH

async def flex_return_month_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selected_month = int(query.data.replace(config.CALLBACK_PREFIX_FLEX + "ret_month_", ""))
    context.user_data['return_month'] = selected_month
    year = context.user_data['return_year']
    month_name = config.RUSSIAN_MONTHS.get(selected_month, "")
    await ask_date_range(update, context, year, selected_month, f"Выбран: {month_name} {year}. Выберите диапазон дат:", callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_range_")
    return config.SELECTING_FLEX_RETURN_DATE_RANGE

async def flex_return_date_range_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selected_range = query.data.replace(config.CALLBACK_PREFIX_FLEX + "ret_range_", "")
    start_day, end_day = map(int, selected_range.split('-'))
    year = context.user_data['return_year']
    month = context.user_data['return_month']
    await ask_specific_date(update, context, year, month, start_day, end_day, f"Диапазон: {selected_range}. Выберите дату:", callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_date_")
    return config.SELECTING_FLEX_RETURN_DATE

async def flex_return_date_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selected_date_str = query.data.replace(config.CALLBACK_PREFIX_FLEX + "ret_date_", "")
    
    departure_date_obj = helpers.validate_date_format(context.user_data['departure_date'])
    return_date_obj = helpers.validate_date_format(selected_date_str)

    if not return_date_obj or not departure_date_obj or return_date_obj < departure_date_obj:
        await query.edit_message_text("Некорректная дата возвращения или она раньше даты вылета. Попробуйте снова.")
        return config.SELECTING_FLEX_RETURN_DATE_RANGE
        
    context.user_data['return_date'] = selected_date_str
    formatted_date = return_date_obj.strftime('%d-%m-%Y')
    await query.edit_message_text(text=f"Дата обратного вылета: {formatted_date}")
    
    await query.message.reply_text(config.MSG_SEARCHING_FLIGHTS, reply_markup=ReplyKeyboardRemove())
    # Сразу поиск
    flights = await flight_api.find_flights_with_fallback(
        departure_airport_iata=context.user_data['departure_airport_iata'],
        arrival_airport_iata=context.user_data.get('arrival_airport_iata'),
        departure_date_str=context.user_data['departure_date'],
        max_price=context.user_data['max_price'],
        return_date_str=context.user_data['return_date'],
        is_one_way=False
    )
    await process_and_send_flights(query.message, context, flights)
    context.user_data.clear()
    return ConversationHandler.END

# --- Общие обработчики ---
async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет текущий диалог."""
    await update.message.reply_text(config.MSG_CANCELLED, reply_markup=ReplyKeyboardRemove())
    context.user_data.clear()
    return ConversationHandler.END

async def error_handler_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Логирует ошибки, возникшие внутри ConversationHandler."""
    logger.error(f"Ошибка в ConversationHandler: {context.error}", exc_info=context.error)
    if update and update.effective_message:
        await update.effective_message.reply_text(
            config.MSG_ERROR_OCCURRED + " Попробуйте /start.",
            reply_markup=ReplyKeyboardRemove()
        )
    # Важно завершить диалог, чтобы избежать застревания
    context.user_data.clear()
    return ConversationHandler.END


# --- Создание ConversationHandler ---
def create_conversation_handler() -> ConversationHandler:
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start_command),
            CommandHandler('search', start_command), # /search тоже будет вызывать start_command
            CommandHandler('flexsearch', start_command), # /flexsearch тоже
            CallbackQueryHandler(start_search_callback, pattern='^start_standard_search$|^start_flex_search$')
        ],
        states={
            # Стандартный поиск
            config.SELECTING_FLIGHT_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, standard_flight_type)],
            config.SELECTING_DEPARTURE_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, standard_departure_country)],
            config.SELECTING_DEPARTURE_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, standard_departure_city)],
            config.SELECTING_DEPARTURE_YEAR: [CallbackQueryHandler(standard_departure_year_selected, pattern=f"^{config.CALLBACK_PREFIX_STANDARD}dep_year_")],
            config.SELECTING_DEPARTURE_MONTH: [CallbackQueryHandler(standard_departure_month_selected, pattern=f"^{config.CALLBACK_PREFIX_STANDARD}dep_month_")],
            config.SELECTING_DEPARTURE_DATE_RANGE: [CallbackQueryHandler(standard_departure_date_range_selected, pattern=f"^{config.CALLBACK_PREFIX_STANDARD}dep_range_")],
            config.SELECTING_DEPARTURE_DATE: [CallbackQueryHandler(standard_departure_date_selected, pattern=f"^{config.CALLBACK_PREFIX_STANDARD}dep_date_")],
            config.SELECTING_ARRIVAL_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, standard_arrival_country)],
            config.SELECTING_ARRIVAL_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, standard_arrival_city)],
            config.SELECTING_RETURN_YEAR: [CallbackQueryHandler(standard_return_year_selected, pattern=f"^{config.CALLBACK_PREFIX_STANDARD}ret_year_")],
            config.SELECTING_RETURN_MONTH: [CallbackQueryHandler(standard_return_month_selected, pattern=f"^{config.CALLBACK_PREFIX_STANDARD}ret_month_")],
            config.SELECTING_RETURN_DATE_RANGE: [CallbackQueryHandler(standard_return_date_range_selected, pattern=f"^{config.CALLBACK_PREFIX_STANDARD}ret_range_")],
            config.SELECTING_RETURN_DATE: [CallbackQueryHandler(standard_return_date_selected, pattern=f"^{config.CALLBACK_PREFIX_STANDARD}ret_date_")],
            config.SELECTING_MAX_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, standard_max_price)],
            
            # Гибкий поиск
            config.SELECTING_FLEX_FLIGHT_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, flex_flight_type)],
            config.SELECTING_FLEX_MAX_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, flex_max_price)],
            config.ASK_FLEX_DEPARTURE_AIRPORT: [CallbackQueryHandler(flex_ask_departure_airport, pattern=f"^{config.CALLBACK_PREFIX_FLEX}ask_dep_")],
            config.SELECTING_FLEX_DEPARTURE_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, flex_departure_country)],
            config.SELECTING_FLEX_DEPARTURE_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, flex_departure_city)],
            config.ASK_FLEX_ARRIVAL_AIRPORT: [CallbackQueryHandler(flex_ask_arrival_airport, pattern=f"^{config.CALLBACK_PREFIX_FLEX}ask_arr_")],
            config.SELECTING_FLEX_ARRIVAL_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, flex_arrival_country)],
            config.SELECTING_FLEX_ARRIVAL_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, flex_arrival_city)],
            config.ASK_FLEX_DATES: [CallbackQueryHandler(flex_ask_dates, pattern=f"^(?:{config.CALLBACK_PREFIX_FLEX}ask_dates_yes|{config.CALLBACK_NO_SPECIFIC_DATES})$")],
            config.SELECTING_FLEX_DEPARTURE_YEAR: [CallbackQueryHandler(flex_departure_year_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}dep_year_")],
            config.SELECTING_FLEX_DEPARTURE_MONTH: [CallbackQueryHandler(flex_departure_month_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}dep_month_")],
            config.SELECTING_FLEX_DEPARTURE_DATE_RANGE: [CallbackQueryHandler(flex_departure_date_range_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}dep_range_")],
            config.SELECTING_FLEX_DEPARTURE_DATE: [CallbackQueryHandler(flex_departure_date_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}dep_date_")],
            config.SELECTING_FLEX_RETURN_YEAR: [CallbackQueryHandler(flex_return_year_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}ret_year_")],
            config.SELECTING_FLEX_RETURN_MONTH: [CallbackQueryHandler(flex_return_month_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}ret_month_")],
            config.SELECTING_FLEX_RETURN_DATE_RANGE: [CallbackQueryHandler(flex_return_date_range_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}ret_range_")],
            config.SELECTING_FLEX_RETURN_DATE: [CallbackQueryHandler(flex_return_date_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}ret_date_")],
        },
        fallbacks=[CommandHandler('cancel', cancel_handler)],
        # persistent=True, # Если нужно сохранять состояние между перезапусками (требует настройки persistence)
        # name="ryanair_search_conversation"
    )
    return conv_handler