# bot/handlers.py
import logging
from telegram import Update, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
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
    await update.message.reply_text(message_text, reply_markup=keyboards.get_country_reply_keyboard())

async def ask_departure_city(update: Update, context: ContextTypes.DEFAULT_TYPE, country_name: str):
    await update.message.reply_text("Выберите город вылета:", reply_markup=keyboards.get_city_reply_keyboard(country_name))

async def ask_arrival_country(update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str):
    await update.message.reply_text(message_text, reply_markup=keyboards.get_country_reply_keyboard())

async def ask_arrival_city(update: Update, context: ContextTypes.DEFAULT_TYPE, country_name: str):
    await update.message.reply_text("Выберите город прилёта:", reply_markup=keyboards.get_city_reply_keyboard(country_name))

async def ask_year(message_or_update: Update | object, context: ContextTypes.DEFAULT_TYPE, message_text: str, callback_prefix: str = ""):
    target_message_object = None
    if hasattr(message_or_update, 'callback_query') and message_or_update.callback_query:
        await message_or_update.callback_query.edit_message_text(
            text=message_text,
            reply_markup=keyboards.generate_year_buttons(callback_prefix)
        )
        return
    elif hasattr(message_or_update, 'message') and message_or_update.message:
        target_message_object = message_or_update.message
    elif hasattr(message_or_update, 'reply_text'):
        target_message_object = message_or_update
    
    if target_message_object:
        await target_message_object.reply_text(
            message_text,
            reply_markup=keyboards.generate_year_buttons(callback_prefix)
        )
    else:
        logger.warning("ask_year: не удалось определить объект для ответа.")

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
    context.user_data.pop('remaining_flights_to_show', None)

    if not flights:
        await context.bot.send_message(chat_id=chat_id, text=config.MSG_NO_FLIGHTS_FOUND)
    else:
        await context.bot.send_message(chat_id=chat_id, text=config.MSG_FLIGHTS_FOUND_SEE_BELOW)
        
        sent_count = 0
        for i, flight in enumerate(flights):
            if i < config.FLIGHTS_CHUNK_SIZE:
                formatted_flight = helpers.format_flight_details(flight)
                await context.bot.send_message(chat_id=chat_id, text=formatted_flight, parse_mode='Markdown')
                sent_count += 1
            else:
                if i == config.FLIGHTS_CHUNK_SIZE:
                    remaining_count = len(flights) - config.FLIGHTS_CHUNK_SIZE
                    if remaining_count > 0:
                        context.user_data['remaining_flights_to_show'] = flights[config.FLIGHTS_CHUNK_SIZE:]
                        keyboard = InlineKeyboardMarkup([[
                            InlineKeyboardButton(f"Показать остальные {remaining_count} рейсов", callback_data="show_all_remaining_flights")
                        ]])
                        await context.bot.send_message(chat_id=chat_id, text=f"... и еще {remaining_count} рейсов:", reply_markup=keyboard)
                break 
        
        if sent_count == 0 and flights: 
             await context.bot.send_message(chat_id=chat_id, text="Найдены рейсы, но произошла ошибка при отображении первой порции.")

    if not context.user_data.get('remaining_flights_to_show'):
        await context.bot.send_message(
            chat_id=chat_id,
            text="Что дальше?",
            reply_markup=keyboards.get_yes_no_keyboard(
                yes_callback="prompt_new_search_type",
                no_callback="end_search_session",
                yes_text="✅ Начать новый поиск",
                no_text="❌ Закончить"
            )
        )

async def show_all_remaining_flights_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.message: # Убедимся, что есть сообщение для редактирования
      try:
        await query.edit_message_reply_markup(reply_markup=None)
      except Exception as e:
        logger.debug(f"Не удалось убрать клавиатуру из сообщения '{query.message.message_id if query.message else 'N/A'}': {e}")

    remaining_flights = context.user_data.pop('remaining_flights_to_show', [])
    chat_id = update.effective_chat.id

    if not remaining_flights:
        await context.bot.send_message(chat_id=chat_id, text="Нет оставшихся рейсов для отображения.")
    else:
        for flight in remaining_flights:
            formatted_flight = helpers.format_flight_details(flight)
            await context.bot.send_message(chat_id=chat_id, text=formatted_flight, parse_mode='Markdown')
        await context.bot.send_message(chat_id=chat_id, text="Все дополнительные рейсы отображены.")
    
    await context.bot.send_message(
        chat_id=chat_id,
        text="Что дальше?",
        reply_markup=keyboards.get_yes_no_keyboard(
            yes_callback="prompt_new_search_type",
            no_callback="end_search_session",
            yes_text="✅ Начать новый поиск",
            no_text="❌ Закончить"
        )
    )

async def prompt_new_search_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.message: # Убедимся, что есть сообщение для редактирования
      await query.edit_message_text( 
          text=config.MSG_WELCOME,
          reply_markup=keyboards.get_main_menu_keyboard()
      )
    else: # Если вдруг нет, отправляем новое
      await context.bot.send_message(
          chat_id=update.effective_chat.id,
          text=config.MSG_WELCOME,
          reply_markup=keyboards.get_main_menu_keyboard()
      )


async def end_search_session_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.message: # Убедимся, что есть сообщение для редактирования
      await query.edit_message_text(text="Поиск завершен. Если понадоблюсь, вы знаете, как меня найти! /start")
    else:
      await context.bot.send_message(chat_id=update.effective_chat.id, text="Поиск завершен. Если понадоблюсь, вы знаете, как меня найти! /start")
    context.user_data.clear()

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(config.MSG_WELCOME, reply_markup=keyboards.get_main_menu_keyboard())
    elif update.callback_query: 
        await update.callback_query.answer()
        # Если callback_query.message существует, редактируем его. Иначе - новое.
        if update.callback_query.message:
            await update.callback_query.edit_message_text(config.MSG_WELCOME, reply_markup=keyboards.get_main_menu_keyboard())
        elif update.effective_chat:
             await context.bot.send_message(chat_id=update.effective_chat.id, text=config.MSG_WELCOME, reply_markup=keyboards.get_main_menu_keyboard())


async def start_search_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data.clear() 

    if query.data == "start_standard_search":
        if query.message: await query.edit_message_text(text="Выбран стандартный поиск.")
        await context.bot.send_message(chat_id=update.effective_chat.id, text=config.MSG_FLIGHT_TYPE_PROMPT, reply_markup=keyboards.get_flight_type_reply_keyboard())
        return config.SELECTING_FLIGHT_TYPE
    elif query.data == "start_flex_search":
        if query.message: await query.edit_message_text(text="Выбран гибкий поиск.")
        await context.bot.send_message(chat_id=update.effective_chat.id, text=config.MSG_FLIGHT_TYPE_PROMPT, reply_markup=keyboards.get_flight_type_reply_keyboard())
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
        await ask_departure_country(update, context, "Выберите страну вылета:") 
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
        await ask_departure_city(update, context, country) 
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
    context.user_data['departure_month_name'] = month_name 
    await ask_date_range(update, context, year, selected_month, f"Выбран: {month_name} {year}. Выберите диапазон дат:", callback_prefix=config.CALLBACK_PREFIX_STANDARD + "dep_range_")
    return config.SELECTING_DEPARTURE_DATE_RANGE

async def standard_departure_date_range_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selected_range_str = query.data.replace(config.CALLBACK_PREFIX_STANDARD + "dep_range_", "")
    try:
        start_day, end_day = map(int, selected_range_str.split('-'))
        context.user_data['departure_date_range_str'] = selected_range_str 
    except ValueError:
        await query.edit_message_text(text="Некорректный диапазон дат. Пожалуйста, выберите снова.")
        year = context.user_data['departure_year']
        month = context.user_data['departure_month']
        month_name = config.RUSSIAN_MONTHS.get(month, "")
        await ask_date_range(update, context, year, month, f"Выбран: {month_name} {year}. Выберите диапазон дат:", callback_prefix=config.CALLBACK_PREFIX_STANDARD + "dep_range_")
        return config.SELECTING_DEPARTURE_DATE_RANGE
    
    year = context.user_data['departure_year']
    month = context.user_data['departure_month']
    await ask_specific_date(update, context, year, month, start_day, end_day, f"Диапазон: {selected_range_str}. Выберите дату:", callback_prefix=config.CALLBACK_PREFIX_STANDARD + "dep_date_")
    return config.SELECTING_DEPARTURE_DATE

async def standard_departure_date_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selected_date_str = query.data.replace(config.CALLBACK_PREFIX_STANDARD + "dep_date_", "") 
    
    date_obj = helpers.validate_date_format(selected_date_str)
    current_date_midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    if not date_obj or date_obj < current_date_midnight :
        await query.edit_message_text("Некорректная дата или дата в прошлом. Попробуйте снова.")
        year = context.user_data['departure_year']
        month = context.user_data['departure_month']
        selected_range_str = context.user_data.get('departure_date_range_str', "1-10") 
        try:
            start_day, end_day = map(int, selected_range_str.split('-'))
        except ValueError: 
            start_day, end_day = 1, 10 
        await ask_specific_date(update, context, year, month, start_day, end_day, f"Диапазон: {selected_range_str}. Выберите дату:", callback_prefix=config.CALLBACK_PREFIX_STANDARD + "dep_date_")
        return config.SELECTING_DEPARTURE_DATE

    context.user_data['departure_date'] = selected_date_str
    formatted_date = date_obj.strftime('%d-%m-%Y')
    await query.edit_message_text(text=f"Дата вылета: {formatted_date}")
    
    await query.message.reply_text( 
        "Выберите страну прилёта:",
        reply_markup=keyboards.get_country_reply_keyboard() 
    )
    return config.SELECTING_ARRIVAL_COUNTRY

async def standard_arrival_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    country = update.message.text
    if country not in config.COUNTRIES_DATA:
        await update.message.reply_text("Страна не найдена! Пожалуйста, выберите из списка.")
        await ask_arrival_country(update, context, "Выберите страну прилёта:") 
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
    context.user_data['return_month_name'] = month_name 
    await ask_date_range(update, context, year, selected_month, f"Выбран: {month_name} {year}. Выберите диапазон дат:", callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_range_")
    return config.SELECTING_RETURN_DATE_RANGE

async def standard_return_date_range_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selected_range_str = query.data.replace(config.CALLBACK_PREFIX_STANDARD + "ret_range_", "")
    try:
        start_day, end_day = map(int, selected_range_str.split('-'))
        context.user_data['return_date_range_str'] = selected_range_str
    except ValueError: 
        await query.edit_message_text("Ошибка в диапазоне дат. Попробуйте выбрать месяц заново.")
        year = context.user_data['return_year']
        month_name = context.user_data.get('return_month_name', "")
        await ask_month(update, context, f"Год обратного вылета: {year}. Выберите месяц:", callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_month_")
        return config.SELECTING_RETURN_MONTH

    year = context.user_data['return_year']
    month = context.user_data['return_month']
    await ask_specific_date(update, context, year, month, start_day, end_day, f"Диапазон: {selected_range_str}. Выберите дату:", callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_date_")
    return config.SELECTING_RETURN_DATE

async def standard_return_date_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selected_date_str = query.data.replace(config.CALLBACK_PREFIX_STANDARD + "ret_date_", "") 

    departure_date_obj = helpers.validate_date_format(context.user_data['departure_date'])
    return_date_obj = helpers.validate_date_format(selected_date_str)

    if not return_date_obj or not departure_date_obj or return_date_obj < departure_date_obj:
        await query.edit_message_text("Некорректная дата возвращения или она раньше даты вылета. Попробуйте снова.")
        year = context.user_data['return_year']
        month = context.user_data['return_month']
        selected_range_str = context.user_data.get('return_date_range_str', "1-10")
        try:
            start_day, end_day = map(int, selected_range_str.split('-'))
        except ValueError:
            start_day, end_day = 1, 10
        await ask_specific_date(update, context, year, month, start_day, end_day, f"Диапазон: {selected_range_str}. Выберите дату:", callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_date_")
        return config.SELECTING_RETURN_DATE
        
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
        if query.message: await query.edit_message_text(text="Аэропорт вылета: ДА")
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Выберите страну вылета:", reply_markup=keyboards.get_country_reply_keyboard())
        return config.SELECTING_FLEX_DEPARTURE_COUNTRY
    else: 
        if query.message: await query.edit_message_text(text="Аэропорт вылета: НЕТ (будет запрошен позже, если не указан прилёт).")
        context.user_data['departure_airport_iata'] = None 
        logger.info("Гибкий поиск: пользователь пропустил аэропорт вылета.")
        await context.bot.send_message(chat_id=update.effective_chat.id,
            text="Указать аэропорт прилёта?",
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
        if query.message: await query.edit_message_text(text="Аэропорт прилёта: ДА")
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Выберите страну прилёта:", reply_markup=keyboards.get_country_reply_keyboard())
        return config.SELECTING_FLEX_ARRIVAL_COUNTRY
    else: 
        if query.message: await query.edit_message_text(text="Аэропорт прилёта: НЕТ (поиск в любом направлении)")
        context.user_data['arrival_airport_iata'] = None 
        
        # Если не указан ни аэропорт вылета, ни аэропорт прилета, это проблема для API
        if context.user_data.get('departure_airport_iata') is None and context.user_data.get('arrival_airport_iata') is None:
             if query.message:
                await query.message.reply_text("Ошибка: Нужно указать хотя бы аэропорт вылета или аэропорт прилёта. Начните /flexsearch заново.", reply_markup=ReplyKeyboardRemove())
             else: # Если вдруг нет query.message
                await context.bot.send_message(chat_id=update.effective_chat.id, text="Ошибка: Нужно указать хотя бы аэропорт вылета или аэропорт прилёта. Начните /flexsearch заново.", reply_markup=ReplyKeyboardRemove())
             context.user_data.clear()
             return ConversationHandler.END

        await context.bot.send_message(chat_id=update.effective_chat.id,
            text="Указать конкретные даты?",
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
    
    if context.user_data.get('departure_airport_iata') and iata_code == context.user_data['departure_airport_iata']:
        await update.message.reply_text("Аэропорт прилёта не может совпадать с аэропортом вылета. Выберите другой город.")
        await update.message.reply_text("Выберите город прилёта:", reply_markup=keyboards.get_city_reply_keyboard(country))
        return config.SELECTING_FLEX_ARRIVAL_CITY

    context.user_data['arrival_airport_iata'] = iata_code
    context.user_data['arrival_city_name'] = city
    
    # Если аэропорт вылета не был указан ранее, но указан аэропорт прилета, это валидный сценарий для API
    # (например, ищем все рейсы В указанный город)
    # Однако, наша flight_api.find_flights_with_fallback ожидает departure_airport_iata.
    # Здесь нужно либо адаптировать flight_api, либо потребовать аэропорт вылета.
    # Пока что оставим как есть, предполагая, что departure_airport_iata будет получен или API его не потребует (что маловероятно)
    if context.user_data.get('departure_airport_iata') is None and context.user_data.get('arrival_airport_iata') is not None:
        logger.warning("Гибкий поиск: указан прилёт, но не вылет. API может этого не поддерживать без вылета.")
        # Можно здесь запросить аэропорт вылета, если он не был указан.
        # Для простоты пока идем дальше.

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

    # Проверка, что хотя бы один аэропорт (вылета или прилета) указан, если пользователь хочет искать без дат.
    # Эта проверка ужесточена: для поиска без дат нужен аэропорт ВЫЛЕТА.
    departure_airport_is_set = context.user_data.get('departure_airport_iata') is not None

    if query.data == config.CALLBACK_PREFIX_FLEX + "ask_dates_yes":
        if query.message: await query.edit_message_text(text="Даты: ДА, указать конкретные.")
        await ask_year(query.message, context, "Выберите год вылета:", callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_year_")
        return config.SELECTING_FLEX_DEPARTURE_YEAR 
    
    elif query.data == config.CALLBACK_NO_SPECIFIC_DATES: 
        if query.message: await query.edit_message_text(text="Даты: НЕТ, искать на ближайший год.")
        context.user_data['departure_date'] = None 
        context.user_data['return_date'] = None

        if not departure_airport_is_set: # Если аэропорт вылета НЕ указан
            if query.message:
                await query.message.reply_text(
                    "Ошибка: для поиска без дат (или с поиском 'в любом направлении') необходимо указать аэропорт вылета.\n"
                    "Начните гибкий поиск заново: /start",
                    reply_markup=ReplyKeyboardRemove()
                )
            context.user_data.clear()
            return ConversationHandler.END
            
        await query.message.reply_text(config.MSG_SEARCHING_FLIGHTS, reply_markup=ReplyKeyboardRemove())
        flights = await flight_api.find_flights_with_fallback(
            departure_airport_iata=context.user_data.get('departure_airport_iata'), 
            arrival_airport_iata=context.user_data.get('arrival_airport_iata'), 
            departure_date_str=None, 
            max_price=context.user_data['max_price'],
            return_date_str=None, 
            is_one_way=context.user_data.get('flight_type_one_way', True)
        )
        await process_and_send_flights(update, context, flights) 
        context.user_data.clear()
        return ConversationHandler.END
    return config.ASK_FLEX_DATES

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
    context.user_data['departure_month_name'] = month_name
    await ask_date_range(update, context, year, selected_month, f"Выбран: {month_name} {year}. Выберите диапазон дат:", callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_range_")
    return config.SELECTING_FLEX_DEPARTURE_DATE_RANGE

async def flex_departure_date_range_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selected_range_str = query.data.replace(config.CALLBACK_PREFIX_FLEX + "dep_range_", "")
    try:
        start_day, end_day = map(int, selected_range_str.split('-'))
        context.user_data['departure_date_range_str'] = selected_range_str
    except ValueError:
        await query.edit_message_text("Некорректный диапазон дат. Попробуйте выбрать месяц заново.")
        year = context.user_data['departure_year']
        month_name = context.user_data.get('departure_month_name', "")
        await ask_month(update, context, f"Год вылета: {year}. Выберите месяц:", callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_month_")
        return config.SELECTING_FLEX_DEPARTURE_MONTH
        
    year = context.user_data['departure_year']
    month = context.user_data['departure_month']
    await ask_specific_date(update, context, year, month, start_day, end_day, f"Диапазон: {selected_range_str}. Выберите дату:", callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_date_")
    return config.SELECTING_FLEX_DEPARTURE_DATE

async def flex_departure_date_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selected_date_str = query.data.replace(config.CALLBACK_PREFIX_FLEX + "dep_date_", "")
    date_obj = helpers.validate_date_format(selected_date_str)
    current_date_midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    if not date_obj or date_obj < current_date_midnight:
        await query.edit_message_text("Некорректная дата или дата в прошлом. Попробуйте снова.")
        year = context.user_data['departure_year']
        month = context.user_data['departure_month']
        selected_range_str = context.user_data.get('departure_date_range_str', "1-10")
        try:
            start_day, end_day = map(int, selected_range_str.split('-'))
        except ValueError:
            start_day, end_day = 1,10
        await ask_specific_date(update, context, year, month, start_day, end_day, f"Диапазон: {selected_range_str}. Выберите дату:", callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_date_")
        return config.SELECTING_FLEX_DEPARTURE_DATE

    context.user_data['departure_date'] = selected_date_str
    formatted_date = date_obj.strftime('%d-%m-%Y')
    
    if context.user_data.get('flight_type_one_way', True):
        if query.message: await query.edit_message_text(text=f"Дата вылета: {formatted_date}")
        await context.bot.send_message(chat_id=update.effective_chat.id, text=config.MSG_SEARCHING_FLIGHTS, reply_markup=ReplyKeyboardRemove())
        
        flights = await flight_api.find_flights_with_fallback(
            departure_airport_iata=context.user_data.get('departure_airport_iata'),
            arrival_airport_iata=context.user_data.get('arrival_airport_iata'),
            departure_date_str=context.user_data['departure_date'],
            max_price=context.user_data['max_price'],
            is_one_way=True
        )
        await process_and_send_flights(update, context, flights)
        context.user_data.clear()
        return ConversationHandler.END
    else:
        if query.message: await query.edit_message_text(text=f"Дата вылета: {formatted_date}")
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
    context.user_data['return_month_name'] = month_name
    await ask_date_range(update, context, year, selected_month, f"Выбран: {month_name} {year}. Выберите диапазон дат:", callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_range_")
    return config.SELECTING_FLEX_RETURN_DATE_RANGE

async def flex_return_date_range_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selected_range_str = query.data.replace(config.CALLBACK_PREFIX_FLEX + "ret_range_", "")
    try:
        start_day, end_day = map(int, selected_range_str.split('-'))
        context.user_data['return_date_range_str'] = selected_range_str
    except ValueError:
        await query.edit_message_text("Некорректный диапазон дат. Попробуйте выбрать месяц заново.")
        year = context.user_data['return_year']
        month_name = context.user_data.get('return_month_name', "")
        await ask_month(update, context, f"Год обратного вылета: {year}. Выберите месяц:", callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_month_")
        return config.SELECTING_FLEX_RETURN_MONTH

    year = context.user_data['return_year']
    month = context.user_data['return_month']
    await ask_specific_date(update, context, year, month, start_day, end_day, f"Диапазон: {selected_range_str}. Выберите дату:", callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_date_")
    return config.SELECTING_FLEX_RETURN_DATE

async def flex_return_date_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selected_date_str = query.data.replace(config.CALLBACK_PREFIX_FLEX + "ret_date_", "")
    
    departure_date_obj = helpers.validate_date_format(context.user_data['departure_date'])
    return_date_obj = helpers.validate_date_format(selected_date_str)

    if not return_date_obj or not departure_date_obj or return_date_obj < departure_date_obj:
        await query.edit_message_text("Некорректная дата возвращения или она раньше даты вылета. Попробуйте снова.")
        year = context.user_data['return_year']
        month = context.user_data['return_month']
        selected_range_str = context.user_data.get('return_date_range_str', "1-10")
        try:
            start_day, end_day = map(int, selected_range_str.split('-'))
        except ValueError:
            start_day, end_day = 1,10
        await ask_specific_date(update, context, year, month, start_day, end_day, f"Диапазон: {selected_range_str}. Выберите дату:", callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_date_")
        return config.SELECTING_FLEX_RETURN_DATE
        
    context.user_data['return_date'] = selected_date_str
    formatted_date = return_date_obj.strftime('%d-%m-%Y')
    if query.message: await query.edit_message_text(text=f"Дата обратного вылета: {formatted_date}")
    
    await context.bot.send_message(chat_id=update.effective_chat.id, text=config.MSG_SEARCHING_FLIGHTS, reply_markup=ReplyKeyboardRemove())
    flights = await flight_api.find_flights_with_fallback(
        departure_airport_iata=context.user_data.get('departure_airport_iata'),
        arrival_airport_iata=context.user_data.get('arrival_airport_iata'),
        departure_date_str=context.user_data['departure_date'],
        max_price=context.user_data['max_price'],
        return_date_str=context.user_data['return_date'],
        is_one_way=False
    )
    await process_and_send_flights(update, context, flights)
    context.user_data.clear()
    return ConversationHandler.END

# --- Общие обработчики ---
async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message_to_send = config.MSG_CANCELLED
    reply_markup_to_send = ReplyKeyboardRemove()
    chat_id_to_send = update.effective_chat.id

    if update.callback_query:
        await update.callback_query.answer()
        if update.callback_query.message:
             # Пытаемся отредактировать сообщение, убрав кнопки
            try:
                await update.callback_query.edit_message_text(text=message_to_send)
            except Exception: # Если не получилось (например, текст тот же), отправляем новое
                if chat_id_to_send:
                    await context.bot.send_message(chat_id=chat_id_to_send, text=message_to_send, reply_markup=reply_markup_to_send)
        elif chat_id_to_send: # Если нет .message у callback_query, но есть чат
            await context.bot.send_message(chat_id=chat_id_to_send, text=message_to_send, reply_markup=reply_markup_to_send)
    elif update.message and chat_id_to_send: 
        await update.message.reply_text(message_to_send, reply_markup=reply_markup_to_send)
    
    context.user_data.clear()
    return ConversationHandler.END

async def error_handler_conv(update: Update | None, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    logger.error(f"Ошибка в ConversationHandler: {context.error}", exc_info=context.error)
    
    chat_id_to_send_error = None
    if update and hasattr(update, 'effective_chat') and update.effective_chat:
        chat_id_to_send_error = update.effective_chat.id
    elif isinstance(context.error, Exception) and hasattr(context.error, 'update'):
        error_update = getattr(context.error, 'update', None)
        if error_update and hasattr(error_update, 'effective_chat') and error_update.effective_chat:
            chat_id_to_send_error = error_update.effective_chat.id

    if chat_id_to_send_error:
        try:
            await context.bot.send_message(
                chat_id=chat_id_to_send_error,
                text=config.MSG_ERROR_OCCURRED + " Пожалуйста, попробуйте начать заново с /start.",
                reply_markup=ReplyKeyboardRemove()
            )
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение об ошибке пользователю: {e}")

    if context.user_data: context.user_data.clear()
    return ConversationHandler.END

# --- Создание ConversationHandler ---
def create_conversation_handler() -> ConversationHandler:
    # Паттерны для CallbackQueryHandlers (чтобы избежать дублирования)
    std_dep_year_pattern = f"^{config.CALLBACK_PREFIX_STANDARD}dep_year_"
    std_dep_month_pattern = f"^{config.CALLBACK_PREFIX_STANDARD}dep_month_"
    std_dep_range_pattern = f"^{config.CALLBACK_PREFIX_STANDARD}dep_range_"
    std_dep_date_pattern = f"^{config.CALLBACK_PREFIX_STANDARD}dep_date_"
    std_ret_year_pattern = f"^{config.CALLBACK_PREFIX_STANDARD}ret_year_"
    std_ret_month_pattern = f"^{config.CALLBACK_PREFIX_STANDARD}ret_month_"
    std_ret_range_pattern = f"^{config.CALLBACK_PREFIX_STANDARD}ret_range_"
    std_ret_date_pattern = f"^{config.CALLBACK_PREFIX_STANDARD}ret_date_"

    flex_ask_dep_pattern = f"^{config.CALLBACK_PREFIX_FLEX}ask_dep_"
    flex_ask_arr_pattern = f"^{config.CALLBACK_PREFIX_FLEX}ask_arr_"
    flex_ask_dates_pattern = f"^(?:{config.CALLBACK_PREFIX_FLEX}ask_dates_yes|{config.CALLBACK_NO_SPECIFIC_DATES})$"
    flex_dep_year_pattern = f"^{config.CALLBACK_PREFIX_FLEX}dep_year_"
    flex_dep_month_pattern = f"^{config.CALLBACK_PREFIX_FLEX}dep_month_"
    flex_dep_range_pattern = f"^{config.CALLBACK_PREFIX_FLEX}dep_range_"
    flex_dep_date_pattern = f"^{config.CALLBACK_PREFIX_FLEX}dep_date_"
    flex_ret_year_pattern = f"^{config.CALLBACK_PREFIX_FLEX}ret_year_"
    flex_ret_month_pattern = f"^{config.CALLBACK_PREFIX_FLEX}ret_month_"
    flex_ret_range_pattern = f"^{config.CALLBACK_PREFIX_FLEX}ret_range_"
    flex_ret_date_pattern = f"^{config.CALLBACK_PREFIX_FLEX}ret_date_"

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start_command),
            CommandHandler('search', start_command), 
            CommandHandler('flexsearch', start_command), 
            CallbackQueryHandler(start_search_callback, pattern='^start_standard_search$|^start_flex_search$')
        ],
        states={
            # Стандартный поиск
            config.SELECTING_FLIGHT_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, standard_flight_type)],
            config.SELECTING_DEPARTURE_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, standard_departure_country)],
            config.SELECTING_DEPARTURE_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, standard_departure_city)],
            config.SELECTING_DEPARTURE_YEAR: [CallbackQueryHandler(standard_departure_year_selected, pattern=std_dep_year_pattern)],
            config.SELECTING_DEPARTURE_MONTH: [CallbackQueryHandler(standard_departure_month_selected, pattern=std_dep_month_pattern)],
            config.SELECTING_DEPARTURE_DATE_RANGE: [CallbackQueryHandler(standard_departure_date_range_selected, pattern=std_dep_range_pattern)],
            config.SELECTING_DEPARTURE_DATE: [CallbackQueryHandler(standard_departure_date_selected, pattern=std_dep_date_pattern)],
            config.SELECTING_ARRIVAL_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, standard_arrival_country)],
            config.SELECTING_ARRIVAL_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, standard_arrival_city)],
            config.SELECTING_RETURN_YEAR: [CallbackQueryHandler(standard_return_year_selected, pattern=std_ret_year_pattern)],
            config.SELECTING_RETURN_MONTH: [CallbackQueryHandler(standard_return_month_selected, pattern=std_ret_month_pattern)],
            config.SELECTING_RETURN_DATE_RANGE: [CallbackQueryHandler(standard_return_date_range_selected, pattern=std_ret_range_pattern)],
            config.SELECTING_RETURN_DATE: [CallbackQueryHandler(standard_return_date_selected, pattern=std_ret_date_pattern)],
            config.SELECTING_MAX_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, standard_max_price)],
            
            # Гибкий поиск
            config.SELECTING_FLEX_FLIGHT_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, flex_flight_type)],
            config.SELECTING_FLEX_MAX_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, flex_max_price)],
            config.ASK_FLEX_DEPARTURE_AIRPORT: [CallbackQueryHandler(flex_ask_departure_airport, pattern=flex_ask_dep_pattern)],
            config.SELECTING_FLEX_DEPARTURE_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, flex_departure_country)],
            config.SELECTING_FLEX_DEPARTURE_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, flex_departure_city)],
            config.ASK_FLEX_ARRIVAL_AIRPORT: [CallbackQueryHandler(flex_ask_arrival_airport, pattern=flex_ask_arr_pattern)],
            config.SELECTING_FLEX_ARRIVAL_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, flex_arrival_country)],
            config.SELECTING_FLEX_ARRIVAL_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, flex_arrival_city)],
            config.ASK_FLEX_DATES: [CallbackQueryHandler(flex_ask_dates, pattern=flex_ask_dates_pattern)],
            config.SELECTING_FLEX_DEPARTURE_YEAR: [CallbackQueryHandler(flex_departure_year_selected, pattern=flex_dep_year_pattern)],
            config.SELECTING_FLEX_DEPARTURE_MONTH: [CallbackQueryHandler(flex_departure_month_selected, pattern=flex_dep_month_pattern)],
            config.SELECTING_FLEX_DEPARTURE_DATE_RANGE: [CallbackQueryHandler(flex_departure_date_range_selected, pattern=flex_dep_range_pattern)],
            config.SELECTING_FLEX_DEPARTURE_DATE: [CallbackQueryHandler(flex_departure_date_selected, pattern=flex_dep_date_pattern)],
            config.SELECTING_FLEX_RETURN_YEAR: [CallbackQueryHandler(flex_return_year_selected, pattern=flex_ret_year_pattern)],
            config.SELECTING_FLEX_RETURN_MONTH: [CallbackQueryHandler(flex_return_month_selected, pattern=flex_ret_month_pattern)],
            config.SELECTING_FLEX_RETURN_DATE_RANGE: [CallbackQueryHandler(flex_return_date_range_selected, pattern=flex_ret_range_pattern)],
            config.SELECTING_FLEX_RETURN_DATE: [CallbackQueryHandler(flex_return_date_selected, pattern=flex_ret_date_pattern)],
        },
        fallbacks=[CommandHandler('cancel', cancel_handler)],
    )
    return conv_handler