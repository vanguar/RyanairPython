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
from collections import defaultdict #NEW

from . import config, keyboards, helpers, flight_api

logger = logging.getLogger(__name__)

# --- Вспомогательные функции для обработчиков ---
async def ask_departure_country(update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str):
    # Отправляем сообщение с клавиатурой стран, если update.message существует
    if hasattr(update, 'message') and update.message:
        await update.message.reply_text(message_text, reply_markup=keyboards.get_country_reply_keyboard())
    # Если это callback_query, отправляем как новое сообщение в чат callback_query
    elif hasattr(update, 'callback_query') and update.callback_query and update.effective_chat:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=message_text, reply_markup=keyboards.get_country_reply_keyboard())
    else:
        logger.warning("ask_departure_country: Не удалось определить, как отправить сообщение.")


async def ask_departure_city(update: Update, context: ContextTypes.DEFAULT_TYPE, country_name: str):
    if hasattr(update, 'message') and update.message:
        await update.message.reply_text("Выберите город вылета:", reply_markup=keyboards.get_city_reply_keyboard(country_name))
    elif hasattr(update, 'callback_query') and update.callback_query and update.effective_chat:
         await context.bot.send_message(chat_id=update.effective_chat.id, text="Выберите город вылета:", reply_markup=keyboards.get_city_reply_keyboard(country_name))

async def ask_arrival_country(update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str):
    if hasattr(update, 'message') and update.message:
        await update.message.reply_text(message_text, reply_markup=keyboards.get_country_reply_keyboard())
    elif hasattr(update, 'callback_query') and update.callback_query and update.effective_chat:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=message_text, reply_markup=keyboards.get_country_reply_keyboard())


async def ask_arrival_city(update: Update, context: ContextTypes.DEFAULT_TYPE, country_name: str):
    if hasattr(update, 'message') and update.message:
        await update.message.reply_text("Выберите город прилёта:", reply_markup=keyboards.get_city_reply_keyboard(country_name))
    elif hasattr(update, 'callback_query') and update.callback_query and update.effective_chat:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Выберите город прилёта:", reply_markup=keyboards.get_city_reply_keyboard(country_name))


async def ask_year(message_or_update: Update | object, context: ContextTypes.DEFAULT_TYPE, message_text: str, callback_prefix: str = ""):
    target_message_object = None
    if hasattr(message_or_update, 'callback_query') and message_or_update.callback_query:
        # Редактируем существующее сообщение, если это callback от inline кнопки
        await message_or_update.callback_query.edit_message_text(
            text=message_text,
            reply_markup=keyboards.generate_year_buttons(callback_prefix)
        )
        return
    elif hasattr(message_or_update, 'message') and message_or_update.message:
        # Если это новое сообщение от пользователя (текстовое)
        target_message_object = message_or_update.message
    elif hasattr(message_or_update, 'reply_text'): # Если это объект Update после команды
        target_message_object = message_or_update
    
    if target_message_object and hasattr(target_message_object, 'reply_text'):
        await target_message_object.reply_text(
            message_text,
            reply_markup=keyboards.generate_year_buttons(callback_prefix)
        )
    # NEW: Если это callback, но нет message для редактирования (например, после ReplyKeyboard), отправляем новое
    elif hasattr(message_or_update, 'effective_chat') and message_or_update.effective_chat:
         await context.bot.send_message(
            chat_id=message_or_update.effective_chat.id,
            text=message_text,
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

# MODIFIED: Логика process_and_send_flights для обработки словаря рейсов по датам
async def process_and_send_flights(update: Update, context: ContextTypes.DEFAULT_TYPE, flights_by_date: dict):
    chat_id = update.effective_chat.id
    context.user_data.pop('remaining_flights_to_show', None) # Очищаем старые остатки, если есть

    if not flights_by_date:
        await context.bot.send_message(chat_id=chat_id, text=config.MSG_NO_FLIGHTS_FOUND)
        # NEW: Предложение поиска из других аэропортов
        dep_country = context.user_data.get('departure_country')
        dep_airport_iata = context.user_data.get('departure_airport_iata')
        if dep_country and dep_airport_iata and config.COUNTRIES_DATA.get(dep_country) and \
           len(config.COUNTRIES_DATA[dep_country]) > 1: # Если есть другие аэропорты в стране
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"Хотите поискать вылеты из других аэропортов в стране {dep_country} по этому же направлению и датам?",
                reply_markup=keyboards.get_search_other_airports_keyboard(dep_country)
            )
            return config.ASK_SEARCH_OTHER_AIRPORTS # Переходим в состояние ожидания ответа на этот вопрос
        # Если нет, то просто предлагаем новый поиск / завершение
        await context.bot.send_message(
            chat_id=chat_id, text="Что дальше?",
            reply_markup=keyboards.get_yes_no_keyboard(
                yes_callback="prompt_new_search_type", no_callback="end_search_session",
                yes_text="✅ Начать новый поиск", no_text="❌ Закончить"
            )
        )
        return ConversationHandler.END # Завершаем текущий диалог, если нет альтернатив

    else:
        await context.bot.send_message(chat_id=chat_id, text=config.MSG_FLIGHTS_FOUND_SEE_BELOW)
        
        total_flights_shown_count = 0
        flights_message_parts = []

        sorted_dates = sorted(flights_by_date.keys())

        for flight_date_str in sorted_dates:
            flights_on_this_date = flights_by_date[flight_date_str]
            if not flights_on_this_date:
                continue

            date_obj = datetime.strptime(flight_date_str, "%Y-%m-%d")
            formatted_date_header = f"\n--- 📅 *{date_obj.strftime('%d %B %Y (%A)')}* ---\n"
            flights_message_parts.append(formatted_date_header)
            
            for i, flight in enumerate(flights_on_this_date):
                if i < config.FLIGHTS_CHUNK_SIZE: # Показываем ограниченное кол-во на каждую дату для начала
                    formatted_flight = helpers.format_flight_details(flight)
                    flights_message_parts.append(formatted_flight)
                    total_flights_shown_count += 1
                else:
                    flights_message_parts.append(f"...и еще {len(flights_on_this_date) - i} рейс(ов) на эту дату.")
                    break # Переходим к следующей дате
            
            if not flights_message_parts[-1].endswith("рейс(ов) на эту дату."): # если не было "...и еще"
                 flights_message_parts.append("\n")


        if flights_message_parts:
            full_message = "".join(flights_message_parts)
            # Разделение на части, если сообщение слишком длинное
            max_length = 4096
            for i in range(0, len(full_message), max_length):
                await context.bot.send_message(chat_id=chat_id, text=full_message[i:i+max_length], parse_mode='Markdown')

        if total_flights_shown_count == 0 and any(flights_by_date.values()):
             await context.bot.send_message(chat_id=chat_id, text="Найдены рейсы, но произошла ошибка при отображении.")

    # Общая кнопка для нового поиска / завершения
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
    context.user_data.clear() # Очищаем user_data после отображения результатов
    return ConversationHandler.END


# MODIFIED: show_all_remaining_flights_callback is now less relevant with grouped dates,
# this function can be removed or adapted if complex pagination per date is re-introduced.
# For now, it's not used by the modified process_and_send_flights.
async def show_all_remaining_flights_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # ... (старая логика, которая теперь неактуальна)
    await query.edit_message_text(text="Эта функция отображения оставшихся рейсов обновляется.")


async def prompt_new_search_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.message: 
      await query.edit_message_text( 
          text=config.MSG_WELCOME,
          reply_markup=keyboards.get_main_menu_keyboard()
      )
    else: 
      await context.bot.send_message(
          chat_id=update.effective_chat.id,
          text=config.MSG_WELCOME,
          reply_markup=keyboards.get_main_menu_keyboard()
      )
    # NEW: Возвращаем управление ConversationHandler, если это часть его fallbacks или entry_points
    # Если это глобальный callback, то ConversationHandler.END не нужен здесь
    # В данном случае, это callback от кнопок после завершения диалога, так что END не нужен.


async def end_search_session_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.message:
      await query.edit_message_text(text="Поиск завершен. Если понадоблюсь, вы знаете, как меня найти! /start")
    else:
      await context.bot.send_message(chat_id=update.effective_chat.id, text="Поиск завершен. Если понадоблюсь, вы знаете, как меня найти! /start")
    context.user_data.clear()


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(config.MSG_WELCOME, reply_markup=keyboards.get_main_menu_keyboard())
    elif update.callback_query: 
        await update.callback_query.answer()
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

# NEW: Callback handler for "Куда угодно" button
async def start_flex_anywhere_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    
    context.user_data['arrival_airport_iata'] = None  # Прилёт куда угодно
    context.user_data['departure_date'] = None       # Даты не важны
    context.user_data['return_date'] = None          # И обратные даты тоже
    # Флаги для возможного пропуска шагов в flex диалоге (если понадобится)
    # context.user_data['skip_arrival_selection'] = True
    # context.user_data['skip_date_selection'] = True
    
    if query.message:
        await query.edit_message_text(text="Выбран поиск \"Куда угодно\".")
    
    # Начинаем стандартный гибкий поиск, но с уже предустановленными значениями
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=config.MSG_FLIGHT_TYPE_PROMPT,
        reply_markup=keyboards.get_flight_type_reply_keyboard()
    )
    return config.SELECTING_FLEX_FLIGHT_TYPE


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
    # ... (без изменений) ...
    query = update.callback_query
    await query.answer()
    selected_year = int(query.data.replace(config.CALLBACK_PREFIX_STANDARD + "dep_year_", ""))
    context.user_data['departure_year'] = selected_year
    await ask_month(update, context, f"Год вылета: {selected_year}. Выберите месяц:", callback_prefix=config.CALLBACK_PREFIX_STANDARD + "dep_month_")
    return config.SELECTING_DEPARTURE_MONTH

async def standard_departure_month_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (без изменений) ...
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
    # ... (без изменений) ...
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
    # ... (без изменений) ...
    query = update.callback_query
    await query.answer()
    selected_date_str = query.data.replace(config.CALLBACK_PREFIX_STANDARD + "dep_date_", "") 
    
    date_obj = helpers.validate_date_format(selected_date_str)
    current_date_midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    if not date_obj or date_obj < current_date_midnight :
        await query.edit_message_text("Некорректная дата или дата в прошлом. Попробуйте снова.")
        # ... (код для повторного запроса даты)
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
    
    # Используем ask_arrival_country, который теперь может отправить новое сообщение
    await ask_arrival_country(update, context, "Выберите страну прилёта:")
    return config.SELECTING_ARRIVAL_COUNTRY

# MODIFIED: standard_arrival_country - фикс бага с одинаковым городом
async def standard_arrival_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    country = update.message.text
    if country not in config.COUNTRIES_DATA:
        await update.message.reply_text("Страна не найдена! Пожалуйста, выберите из списка.")
        await ask_arrival_country(update, context, "Выберите страну прилёта:") 
        return config.SELECTING_ARRIVAL_COUNTRY
    
    # NEW: Проверка на единственный совпадающий аэропорт
    departure_airport_iata = context.user_data.get('departure_airport_iata')
    if departure_airport_iata and country in config.COUNTRIES_DATA and len(config.COUNTRIES_DATA[country]) == 1:
        single_city_name = list(config.COUNTRIES_DATA[country].keys())[0]
        single_airport_iata = helpers.get_airport_iata(country, single_city_name)
        if single_airport_iata == departure_airport_iata:
            await update.message.reply_text(
                f"Единственный аэропорт в стране \"{country}\" ({single_city_name}) совпадает с вашим аэропортом вылета. "
                "Выберите другую страну прилёта или введите /cancel для отмены и изменения аэропорта вылета."
            )
            await ask_arrival_country(update, context, "Выберите другую страну прилёта:")
            return config.SELECTING_ARRIVAL_COUNTRY

    context.user_data['arrival_country'] = country
    await ask_arrival_city(update, context, country)
    return config.SELECTING_ARRIVAL_CITY

async def standard_arrival_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (без изменений, основная логика проверки совпадения аэропортов остается) ...
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
        # Отправляем новое сообщение для запроса цены
        await update.message.reply_text(config.MSG_MAX_PRICE_PROMPT, reply_markup=ReplyKeyboardRemove())
        return config.SELECTING_MAX_PRICE
    else:
        await ask_year(update, context, "Выберите год обратного вылета:", callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_year_")
        return config.SELECTING_RETURN_YEAR


async def standard_return_year_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (без изменений) ...
    query = update.callback_query
    await query.answer()
    selected_year = int(query.data.replace(config.CALLBACK_PREFIX_STANDARD + "ret_year_", ""))
    context.user_data['return_year'] = selected_year
    await ask_month(update, context, f"Год обратного вылета: {selected_year}. Выберите месяц:", callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_month_")
    return config.SELECTING_RETURN_MONTH

async def standard_return_month_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (без изменений) ...
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
    # ... (без изменений) ...
    query = update.callback_query
    await query.answer()
    selected_range_str = query.data.replace(config.CALLBACK_PREFIX_STANDARD + "ret_range_", "")
    try:
        start_day, end_day = map(int, selected_range_str.split('-'))
        context.user_data['return_date_range_str'] = selected_range_str
    except ValueError: 
        await query.edit_message_text("Ошибка в диапазоне дат. Попробуйте выбрать месяц заново.")
        # ... (код для возврата к выбору месяца)
        year = context.user_data['return_year']
        month_name = context.user_data.get('return_month_name', "") # Используем сохраненное имя месяца
        await ask_month(update, context, f"Год обратного вылета: {year}. Выберите месяц:", callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_month_")
        return config.SELECTING_RETURN_MONTH


    year = context.user_data['return_year']
    month = context.user_data['return_month']
    await ask_specific_date(update, context, year, month, start_day, end_day, f"Диапазон: {selected_range_str}. Выберите дату:", callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_date_")
    return config.SELECTING_RETURN_DATE

async def standard_return_date_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (без изменений) ...
    query = update.callback_query
    await query.answer()
    selected_date_str = query.data.replace(config.CALLBACK_PREFIX_STANDARD + "ret_date_", "") 

    departure_date_obj = helpers.validate_date_format(context.user_data['departure_date'])
    return_date_obj = helpers.validate_date_format(selected_date_str)

    if not return_date_obj or not departure_date_obj or return_date_obj < departure_date_obj:
        await query.edit_message_text("Некорректная дата возвращения или она раньше даты вылета. Попробуйте снова.")
        # ... (код для повторного запроса даты)
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
    
    # Отправляем новое сообщение для запроса цены, т.к. предыдущее было отредактировано
    await query.message.reply_text(config.MSG_MAX_PRICE_PROMPT, reply_markup=ReplyKeyboardRemove())
    return config.SELECTING_MAX_PRICE

async def standard_max_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    price = helpers.validate_price(update.message.text)
    if price is None:
        await update.message.reply_text("Некорректная цена. Введите положительное число, например, 50:")
        return config.SELECTING_MAX_PRICE
    
    context.user_data['max_price'] = price
    await update.message.reply_text(config.MSG_SEARCHING_FLIGHTS, reply_markup=ReplyKeyboardRemove()) # MODIFIED: Remove keyboard
    
    # MODIFIED: find_flights_with_fallback теперь возвращает словарь
    flights_by_date = await flight_api.find_flights_with_fallback(
        departure_airport_iata=context.user_data['departure_airport_iata'],
        arrival_airport_iata=context.user_data['arrival_airport_iata'],
        departure_date_str=context.user_data['departure_date'],
        max_price=context.user_data['max_price'],
        return_date_str=context.user_data.get('return_date'),
        is_one_way=context.user_data.get('flight_type_one_way', True)
    )
    # MODIFIED: process_and_send_flights теперь может вернуть новое состояние
    return await process_and_send_flights(update, context, flights_by_date)


# --- ГИБКИЙ ПОИСК ---
async def flex_flight_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (без изменений) ...
    user_input = update.message.text
    if user_input not in ['1', '2']:
        await update.message.reply_text("Пожалуйста, выберите 1 или 2.", reply_markup=keyboards.get_flight_type_reply_keyboard())
        return config.SELECTING_FLEX_FLIGHT_TYPE
    context.user_data['flight_type_one_way'] = (user_input == '1')
    await update.message.reply_text(config.MSG_MAX_PRICE_PROMPT, reply_markup=ReplyKeyboardRemove())
    return config.SELECTING_FLEX_MAX_PRICE

async def flex_max_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (без изменений) ...
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
    # ... (без изменений, но возможно, понадобится адаптация, если skip_arrival_selection установлен) ...
    query = update.callback_query
    await query.answer()
    
    if query.data == config.CALLBACK_PREFIX_FLEX + "ask_dep_yes":
        if query.message: await query.edit_message_text(text="Аэропорт вылета: ДА")
        # Используем ask_departure_country, который теперь может отправить новое сообщение
        await ask_departure_country(update, context, "Выберите страну вылета:")
        return config.SELECTING_FLEX_DEPARTURE_COUNTRY
    else: 
        if query.message: await query.edit_message_text(text="Аэропорт вылета: НЕТ (нельзя пропустить, если не указаны даты или прилёт).")
        context.user_data['departure_airport_iata'] = None 
        # Если пользователь пропустил аэропорт вылета, но у нас "anywhere" поиск,
        # мы должны его запросить, т.к. он обязателен.
        # Или, если это часть "anywhere" флоу, этот шаг может быть пропущен, если мы уверены, что аэропорт вылета будет запрошен.
        # Пока оставляем как есть, т.к. `flex_ask_dates` проверяет это.
        logger.info("Гибкий поиск: пользователь пропустил аэропорт вылета (пока).")

        # Проверяем, не был ли это "anywhere" поиск, где arrival_airport_iata уже None
        if context.user_data.get('arrival_airport_iata') is None:
             # Если arrival уже None (из-за "anywhere"), то сразу спрашиваем про даты
            await query.message.reply_text( # Отправляем новым сообщением
                "Указать конкретные даты?",
                reply_markup=keyboards.get_skip_dates_keyboard(
                    callback_select_dates=config.CALLBACK_PREFIX_FLEX + "ask_dates_yes"
                )
            )
            return config.ASK_FLEX_DATES

        await query.message.reply_text( # Отправляем новым сообщением
            "Указать аэропорт прилёта?",
            reply_markup=keyboards.get_yes_no_keyboard(
                yes_callback=config.CALLBACK_PREFIX_FLEX + "ask_arr_yes",
                no_callback=config.CALLBACK_PREFIX_FLEX + "ask_arr_no"
            )
        )
        return config.ASK_FLEX_ARRIVAL_AIRPORT


async def flex_departure_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (без изменений) ...
    country = update.message.text
    if country not in config.COUNTRIES_DATA:
        await update.message.reply_text("Страна не найдена! Пожалуйста, выберите из списка.")
        await ask_departure_country(update, context, "Выберите страну вылета:")
        return config.SELECTING_FLEX_DEPARTURE_COUNTRY
    context.user_data['departure_country'] = country
    await ask_departure_city(update, context, country)
    return config.SELECTING_FLEX_DEPARTURE_CITY

async def flex_departure_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (без изменений) ...
    city = update.message.text
    country = context.user_data.get('departure_country')
    iata_code = helpers.get_airport_iata(country, city)
    if not iata_code:
        await update.message.reply_text("Город не найден! Пожалуйста, выберите из списка.")
        await ask_departure_city(update, context, country)
        return config.SELECTING_FLEX_DEPARTURE_CITY
        
    context.user_data['departure_airport_iata'] = iata_code
    context.user_data['departure_city_name'] = city
    
    # Если arrival_airport_iata уже None (из "anywhere" потока), сразу переходим к датам
    if context.user_data.get('arrival_airport_iata') is None:
        await update.message.reply_text( # Отправляем новым сообщением
            "Указать конкретные даты?",
            reply_markup=keyboards.get_skip_dates_keyboard(
                callback_select_dates=config.CALLBACK_PREFIX_FLEX + "ask_dates_yes"
            )
        )
        return config.ASK_FLEX_DATES

    await update.message.reply_text( # Отправляем новым сообщением
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
    
    # Если arrival_airport_iata уже None (из "anywhere" потока), этот шаг должен быть пропущен
    # или его логика должна это учитывать. Текущий код callback'а start_flex_anywhere_callback
    # устанавливает arrival_airport_iata=None, но поток все равно может сюда попасть.
    # Добавим проверку.
    if context.user_data.get('arrival_airport_iata') is None and context.user_data.get('departure_date') is None:
        # Этот случай уже обработан в start_flex_anywhere, где arrival и date устанавливаются в None.
        # Переход должен быть сразу к ASK_FLEX_DATES или запросу недостающих данных (аэропорта вылета).
        # Для простоты, если мы здесь оказались с arrival_airport_iata=None, значит, это "anywhere"
        # и мы должны были перейти к датам.
        if query.message: await query.edit_message_text(text="Аэропорт прилёта: Любой (пропущено)")
        await context.bot.send_message(chat_id=update.effective_chat.id,
            text="Указать конкретные даты?",
            reply_markup=keyboards.get_skip_dates_keyboard(
                callback_select_dates=config.CALLBACK_PREFIX_FLEX + "ask_dates_yes"
            )
        )
        return config.ASK_FLEX_DATES

    if query.data == config.CALLBACK_PREFIX_FLEX + "ask_arr_yes":
        if query.message: await query.edit_message_text(text="Аэропорт прилёта: ДА")
        await ask_arrival_country(update, context, "Выберите страну прилёта:")
        return config.SELECTING_FLEX_ARRIVAL_COUNTRY
    else: # ask_arr_no
        if query.message: await query.edit_message_text(text="Аэропорт прилёта: НЕТ (поиск в любом направлении)")
        context.user_data['arrival_airport_iata'] = None 
        
        if context.user_data.get('departure_airport_iata') is None: # И вылет тоже не указан
             if query.message:
                await query.message.reply_text("Ошибка: Нужно указать хотя бы аэропорт вылета для поиска 'в любом направлении'. Начните /start заново.", reply_markup=ReplyKeyboardRemove())
             else:
                await context.bot.send_message(chat_id=update.effective_chat.id, text="Ошибка: Нужно указать хотя бы аэропорт вылета для поиска 'в любом направлении'. Начните /start заново.", reply_markup=ReplyKeyboardRemove())
             context.user_data.clear()
             return ConversationHandler.END

        await context.bot.send_message(chat_id=update.effective_chat.id,
            text="Указать конкретные даты?",
            reply_markup=keyboards.get_skip_dates_keyboard(
                callback_select_dates=config.CALLBACK_PREFIX_FLEX + "ask_dates_yes"
            )
        )
        return config.ASK_FLEX_DATES

# MODIFIED: flex_arrival_country - фикс бага с одинаковым городом
async def flex_arrival_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    country = update.message.text
    if country not in config.COUNTRIES_DATA:
        await update.message.reply_text("Страна не найдена! Пожалуйста, выберите из списка.")
        await ask_arrival_country(update, context, "Выберите страну прилёта:")
        return config.SELECTING_FLEX_ARRIVAL_COUNTRY

    # NEW: Проверка на единственный совпадающий аэропорт
    departure_airport_iata = context.user_data.get('departure_airport_iata')
    if departure_airport_iata and country in config.COUNTRIES_DATA and len(config.COUNTRIES_DATA[country]) == 1:
        single_city_name = list(config.COUNTRIES_DATA[country].keys())[0]
        single_airport_iata = helpers.get_airport_iata(country, single_city_name)
        if single_airport_iata == departure_airport_iata:
            await update.message.reply_text(
                f"Единственный аэропорт в стране \"{country}\" ({single_city_name}) совпадает с вашим аэропортом вылета. "
                "Выберите другую страну прилёта или введите /cancel для отмены."
            )
            await ask_arrival_country(update, context, "Выберите другую страну прилёта:")
            return config.SELECTING_FLEX_ARRIVAL_COUNTRY
            
    context.user_data['arrival_country'] = country
    await ask_arrival_city(update, context, country)
    return config.SELECTING_FLEX_ARRIVAL_CITY

async def flex_arrival_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (без изменений, основная логика проверки совпадения аэропортов остается) ...
    city = update.message.text
    country = context.user_data.get('arrival_country')
    iata_code = helpers.get_airport_iata(country, city)
    if not iata_code:
        await update.message.reply_text("Город не найден! Пожалуйста, выберите из списка.")
        await ask_arrival_city(update, context, country)
        return config.SELECTING_FLEX_ARRIVAL_CITY
    
    if context.user_data.get('departure_airport_iata') and iata_code == context.user_data['departure_airport_iata']:
        await update.message.reply_text("Аэропорт прилёта не может совпадать с аэропортом вылета. Выберите другой город.")
        await ask_arrival_city(update, context, country)
        return config.SELECTING_FLEX_ARRIVAL_CITY

    context.user_data['arrival_airport_iata'] = iata_code
    context.user_data['arrival_city_name'] = city
    
    # Если departure_date уже None (из "anywhere" потока), то сразу ищем
    if context.user_data.get('departure_date') is None:
        await update.message.reply_text(config.MSG_SEARCHING_FLIGHTS, reply_markup=ReplyKeyboardRemove())
        flights_by_date = await flight_api.find_flights_with_fallback(
            departure_airport_iata=context.user_data.get('departure_airport_iata'), 
            arrival_airport_iata=context.user_data.get('arrival_airport_iata'), 
            departure_date_str=None, 
            max_price=context.user_data['max_price'],
            return_date_str=None, 
            is_one_way=context.user_data.get('flight_type_one_way', True)
        )
        return await process_and_send_flights(update, context, flights_by_date)

    await update.message.reply_text( # Отправляем новым сообщением
        "Указать конкретные даты?",
        reply_markup=keyboards.get_skip_dates_keyboard(
            callback_select_dates=config.CALLBACK_PREFIX_FLEX + "ask_dates_yes"
        )
    )
    return config.ASK_FLEX_DATES


async def flex_ask_dates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    departure_airport_is_set = context.user_data.get('departure_airport_iata') is not None

    if query.data == config.CALLBACK_PREFIX_FLEX + "ask_dates_yes":
        # Если это "anywhere" поиск (departure_date уже None), то эта ветка не должна была вызваться
        # start_flex_anywhere_callback устанавливает departure_date=None
        # Этот if для случая, когда пользователь выбрал указать даты
        if query.message: await query.edit_message_text(text="Даты: ДА, указать конкретные.")
        # Используем ask_year, который теперь может отправить новое сообщение
        await ask_year(query, context, "Выберите год вылета:", callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_year_")
        return config.SELECTING_FLEX_DEPARTURE_YEAR 
    
    elif query.data == config.CALLBACK_NO_SPECIFIC_DATES: 
        # Это если пользователь нажал "Искать без указания дат"
        if query.message: await query.edit_message_text(text="Даты: НЕТ, искать на ближайший год.")
        context.user_data['departure_date'] = None 
        context.user_data['return_date'] = None

        if not departure_airport_is_set:
            msg_text = ("Ошибка: Для поиска без дат или 'в любом направлении' необходимо указать аэропорт вылета. "
                        "Начните поиск заново через /start.")
            if query.message: await query.edit_message_text(text=msg_text, reply_markup=None)
            else: await context.bot.send_message(chat_id=update.effective_chat.id, text=msg_text, reply_markup=ReplyKeyboardRemove())
            context.user_data.clear()
            return ConversationHandler.END
            
        await context.bot.send_message(chat_id=update.effective_chat.id, text=config.MSG_SEARCHING_FLIGHTS, reply_markup=ReplyKeyboardRemove())
        flights_by_date = await flight_api.find_flights_with_fallback(
            departure_airport_iata=context.user_data.get('departure_airport_iata'), 
            arrival_airport_iata=context.user_data.get('arrival_airport_iata'), 
            departure_date_str=None, 
            max_price=context.user_data['max_price'],
            return_date_str=None, 
            is_one_way=context.user_data.get('flight_type_one_way', True)
        )
        return await process_and_send_flights(update, context, flights_by_date) 
    return config.ASK_FLEX_DATES # По умолчанию остаемся на этом же шаге, если callback не распознан


async def flex_departure_year_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (без изменений) ...
    query = update.callback_query
    await query.answer()
    selected_year = int(query.data.replace(config.CALLBACK_PREFIX_FLEX + "dep_year_", ""))
    context.user_data['departure_year'] = selected_year
    await ask_month(update, context, f"Год вылета: {selected_year}. Выберите месяц:", callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_month_")
    return config.SELECTING_FLEX_DEPARTURE_MONTH

async def flex_departure_month_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (без изменений) ...
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
    # ... (без изменений) ...
    query = update.callback_query
    await query.answer()
    selected_range_str = query.data.replace(config.CALLBACK_PREFIX_FLEX + "dep_range_", "")
    try:
        start_day, end_day = map(int, selected_range_str.split('-'))
        context.user_data['departure_date_range_str'] = selected_range_str
    except ValueError:
        await query.edit_message_text("Некорректный диапазон дат. Попробуйте выбрать месяц заново.")
        # ... (код для возврата к выбору месяца)
        year = context.user_data['departure_year']
        month_name = context.user_data.get('departure_month_name', "")
        await ask_month(update, context, f"Год вылета: {year}. Выберите месяц:", callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_month_")
        return config.SELECTING_FLEX_DEPARTURE_MONTH
        
    year = context.user_data['departure_year']
    month = context.user_data['departure_month']
    await ask_specific_date(update, context, year, month, start_day, end_day, f"Диапазон: {selected_range_str}. Выберите дату:", callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_date_")
    return config.SELECTING_FLEX_DEPARTURE_DATE

async def flex_departure_date_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (без изменений в логике выбора даты, но далее вызов API) ...
    query = update.callback_query
    await query.answer()
    selected_date_str = query.data.replace(config.CALLBACK_PREFIX_FLEX + "dep_date_", "")
    date_obj = helpers.validate_date_format(selected_date_str)
    current_date_midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    if not date_obj or date_obj < current_date_midnight:
        await query.edit_message_text("Некорректная дата или дата в прошлом. Попробуйте снова.")
        # ... (код для повторного запроса)
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
        
        flights_by_date = await flight_api.find_flights_with_fallback(
            departure_airport_iata=context.user_data.get('departure_airport_iata'),
            arrival_airport_iata=context.user_data.get('arrival_airport_iata'),
            departure_date_str=context.user_data['departure_date'],
            max_price=context.user_data['max_price'],
            is_one_way=True
        )
        return await process_and_send_flights(update, context, flights_by_date)
    else:
        if query.message: await query.edit_message_text(text=f"Дата вылета: {formatted_date}")
        await ask_year(query, context, "Выберите год обратного вылета:", callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_year_")
        return config.SELECTING_FLEX_RETURN_YEAR

async def flex_return_year_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (без изменений) ...
    query = update.callback_query
    await query.answer()
    selected_year = int(query.data.replace(config.CALLBACK_PREFIX_FLEX + "ret_year_", ""))
    context.user_data['return_year'] = selected_year
    await ask_month(update, context, f"Год обратного вылета: {selected_year}. Выберите месяц:", callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_month_")
    return config.SELECTING_FLEX_RETURN_MONTH

async def flex_return_month_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (без изменений) ...
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
    # ... (без изменений) ...
    query = update.callback_query
    await query.answer()
    selected_range_str = query.data.replace(config.CALLBACK_PREFIX_FLEX + "ret_range_", "")
    try:
        start_day, end_day = map(int, selected_range_str.split('-'))
        context.user_data['return_date_range_str'] = selected_range_str
    except ValueError:
        await query.edit_message_text("Некорректный диапазон дат. Попробуйте выбрать месяц заново.")
        # ... (код для возврата к выбору месяца)
        year = context.user_data['return_year']
        month_name = context.user_data.get('return_month_name', "")
        await ask_month(update, context, f"Год обратного вылета: {year}. Выберите месяц:", callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_month_")
        return config.SELECTING_FLEX_RETURN_MONTH


    year = context.user_data['return_year']
    month = context.user_data['return_month']
    await ask_specific_date(update, context, year, month, start_day, end_day, f"Диапазон: {selected_range_str}. Выберите дату:", callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_date_")
    return config.SELECTING_FLEX_RETURN_DATE

async def flex_return_date_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (без изменений в логике выбора даты, но далее вызов API) ...
    query = update.callback_query
    await query.answer()
    selected_date_str = query.data.replace(config.CALLBACK_PREFIX_FLEX + "ret_date_", "")
    
    departure_date_obj = helpers.validate_date_format(context.user_data['departure_date'])
    return_date_obj = helpers.validate_date_format(selected_date_str)

    if not return_date_obj or not departure_date_obj or return_date_obj < departure_date_obj:
        await query.edit_message_text("Некорректная дата возвращения или она раньше даты вылета. Попробуйте снова.")
        # ... (код для повторного запроса)
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
    flights_by_date = await flight_api.find_flights_with_fallback(
        departure_airport_iata=context.user_data.get('departure_airport_iata'),
        arrival_airport_iata=context.user_data.get('arrival_airport_iata'),
        departure_date_str=context.user_data['departure_date'],
        max_price=context.user_data['max_price'],
        return_date_str=context.user_data['return_date'],
        is_one_way=False
    )
    return await process_and_send_flights(update, context, flights_by_date)

# NEW: Обработчик ответа на предложение поиска из других аэропортов
async def handle_search_other_airports_decision(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    if query.data == config.CALLBACK_YES_OTHER_AIRPORTS:
        departure_country = context.user_data.get('departure_country')
        original_departure_iata = context.user_data.get('departure_airport_iata')
        
        if not departure_country or not original_departure_iata:
            await query.edit_message_text(text="Не удалось получить данные для поиска из других аэропортов. Начните новый поиск.")
            return ConversationHandler.END # Или перенаправить на главное меню

        await query.edit_message_text(text=f"Ищу рейсы из других аэропортов в {departure_country}...")

        all_airports_in_country = config.COUNTRIES_DATA.get(departure_country, {})
        alternative_airports = {
            city: iata for city, iata in all_airports_in_country.items() if iata != original_departure_iata
        }

        if not alternative_airports:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"В стране {departure_country} нет других аэропортов для поиска.")
            # Предлагаем новый поиск / завершение
            await context.bot.send_message(
                chat_id=update.effective_chat.id, text="Что дальше?",
                reply_markup=keyboards.get_yes_no_keyboard(
                    yes_callback="prompt_new_search_type", no_callback="end_search_session",
                    yes_text="✅ Начать новый поиск", no_text="❌ Закончить"
                )
            )
            return ConversationHandler.END


        found_alternative_flights = False
        for city, iata_code in alternative_airports.items():
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Пробую поиск из {city} ({iata_code})...")
            
            # Сохраняем текущий аэропорт вылета для API запроса
            context.user_data['current_search_departure_airport_iata'] = iata_code
            
            flights_by_date_alt = await flight_api.find_flights_with_fallback(
                departure_airport_iata=iata_code, # Новый аэропорт вылета
                arrival_airport_iata=context.user_data.get('arrival_airport_iata'), # Остальные параметры из user_data
                departure_date_str=context.user_data.get('departure_date'), # Может быть None для гибкого
                max_price=context.user_data.get('max_price'),
                return_date_str=context.user_data.get('return_date'),
                is_one_way=context.user_data.get('flight_type_one_way', True)
            )
            if flights_by_date_alt:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Найдены рейсы из {city}:")
                # process_and_send_flights сам завершит диалог или предложит опции
                return await process_and_send_flights(update, context, flights_by_date_alt)
        
        # Если ни из одного альтернативного аэропорта ничего не найдено
        await context.bot.send_message(chat_id=update.effective_chat.id, text="К сожалению, из других аэропортов этой страны по вашим критериям также ничего не найдено.")
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text="Что дальше?",
            reply_markup=keyboards.get_yes_no_keyboard(
                yes_callback="prompt_new_search_type", no_callback="end_search_session",
                yes_text="✅ Начать новый поиск", no_text="❌ Закончить"
            )
        )
        context.user_data.clear()
        return ConversationHandler.END

    elif query.data == config.CALLBACK_NO_OTHER_AIRPORTS:
        await query.edit_message_text(text="Понял. Поиск из других аэропортов отменен.")
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text="Что дальше?",
            reply_markup=keyboards.get_yes_no_keyboard(
                yes_callback="prompt_new_search_type", no_callback="end_search_session",
                yes_text="✅ Начать новый поиск", no_text="❌ Закончить"
            )
        )
        context.user_data.clear()
        return ConversationHandler.END
    
    return config.ASK_SEARCH_OTHER_AIRPORTS # Остаемся в этом состоянии, если callback не распознан

# --- Общие обработчики ---
async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (без изменений) ...
    message_to_send = config.MSG_CANCELLED
    reply_markup_to_send = ReplyKeyboardRemove()
    chat_id_to_send = update.effective_chat.id

    if update.callback_query:
        await update.callback_query.answer()
        if update.callback_query.message:
            try:
                await update.callback_query.edit_message_text(text=message_to_send)
            except Exception:
                if chat_id_to_send:
                    await context.bot.send_message(chat_id=chat_id_to_send, text=message_to_send, reply_markup=reply_markup_to_send)
        elif chat_id_to_send:
            await context.bot.send_message(chat_id=chat_id_to_send, text=message_to_send, reply_markup=reply_markup_to_send)
    elif update.message and chat_id_to_send: 
        await update.message.reply_text(message_to_send, reply_markup=reply_markup_to_send)
    
    context.user_data.clear()
    return ConversationHandler.END

async def error_handler_conv(update: Update | None, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    # ... (без изменений) ...
    logger.error(f"Ошибка в ConversationHandler: {context.error}", exc_info=context.error)
    # ... (остальная часть без изменений)
    chat_id_to_send_error = None
    if update and hasattr(update, 'effective_chat') and update.effective_chat:
        chat_id_to_send_error = update.effective_chat.id
    # ... (остальная часть без изменений)
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
    # Паттерны для CallbackQueryHandlers
    # ... (без изменений) ...
    std_dep_year_pattern = f"^{config.CALLBACK_PREFIX_STANDARD}dep_year_"
    flex_dep_year_pattern = f"^{config.CALLBACK_PREFIX_FLEX}dep_year_"
    # ... (остальные паттерны без изменений) ...
    flex_ret_date_pattern = f"^{config.CALLBACK_PREFIX_FLEX}ret_date_"


    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start_command),
            # Убраны /search и /flexsearch, так как /start теперь центральный вход с кнопками
            CallbackQueryHandler(start_search_callback, pattern='^start_standard_search$|^start_flex_search$'),
            # NEW: Entry point for "Куда угодно"
            CallbackQueryHandler(start_flex_anywhere_callback, pattern='^start_flex_anywhere$')
        ],
        states={
            # Стандартный поиск
            config.SELECTING_FLIGHT_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, standard_flight_type)],
            config.SELECTING_DEPARTURE_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, standard_departure_country)],
            # ... (остальные состояния стандартного поиска без изменений в определениях) ...
            config.SELECTING_DEPARTURE_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, standard_departure_city)],
            config.SELECTING_DEPARTURE_YEAR: [CallbackQueryHandler(standard_departure_year_selected, pattern=std_dep_year_pattern)],
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
            # ... (остальные состояния гибкого поиска без изменений в определениях) ...
            config.SELECTING_FLEX_MAX_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, flex_max_price)],
            config.ASK_FLEX_DEPARTURE_AIRPORT: [CallbackQueryHandler(flex_ask_departure_airport, pattern=f"^{config.CALLBACK_PREFIX_FLEX}ask_dep_")],
            config.SELECTING_FLEX_DEPARTURE_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, flex_departure_country)],
            config.SELECTING_FLEX_DEPARTURE_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, flex_departure_city)],
            config.ASK_FLEX_ARRIVAL_AIRPORT: [CallbackQueryHandler(flex_ask_arrival_airport, pattern=f"^{config.CALLBACK_PREFIX_FLEX}ask_arr_")],
            config.SELECTING_FLEX_ARRIVAL_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, flex_arrival_country)],
            config.SELECTING_FLEX_ARRIVAL_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, flex_arrival_city)],
            config.ASK_FLEX_DATES: [CallbackQueryHandler(flex_ask_dates, pattern=f"^(?:{config.CALLBACK_PREFIX_FLEX}ask_dates_yes|{config.CALLBACK_NO_SPECIFIC_DATES})$")],
            config.SELECTING_FLEX_DEPARTURE_YEAR: [CallbackQueryHandler(flex_departure_year_selected, pattern=flex_dep_year_pattern)],
            config.SELECTING_FLEX_DEPARTURE_MONTH: [CallbackQueryHandler(flex_departure_month_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}dep_month_")],
            config.SELECTING_FLEX_DEPARTURE_DATE_RANGE: [CallbackQueryHandler(flex_departure_date_range_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}dep_range_")],
            config.SELECTING_FLEX_DEPARTURE_DATE: [CallbackQueryHandler(flex_departure_date_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}dep_date_")],
            config.SELECTING_FLEX_RETURN_YEAR: [CallbackQueryHandler(flex_return_year_selected, pattern=flex_ret_year_pattern)],
            config.SELECTING_FLEX_RETURN_MONTH: [CallbackQueryHandler(flex_return_month_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}ret_month_")],
            config.SELECTING_FLEX_RETURN_DATE_RANGE: [CallbackQueryHandler(flex_return_date_range_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}ret_range_")],
            config.SELECTING_FLEX_RETURN_DATE: [CallbackQueryHandler(flex_return_date_selected, pattern=flex_ret_date_pattern)],
            
            # NEW: Состояние для ожидания ответа на поиск из других аэропортов
            config.ASK_SEARCH_OTHER_AIRPORTS: [
                CallbackQueryHandler(handle_search_other_airports_decision, pattern=f"^{config.CALLBACK_YES_OTHER_AIRPORTS}$|^{config.CALLBACK_NO_OTHER_AIRPORTS}$")
            ],
        },
        fallbacks=[
            CommandHandler('cancel', cancel_handler),
            # Можно добавить общий обработчик ошибок для ConversationHandler, если нужно
            # MessageHandler(filters.ALL, error_handler_conv) # Пример
            ],
        # error_handler=error_handler_conv, # Раскомментировать, если error_handler_conv используется для всех ошибок ConvHandler
        map_to_parent={ # Пример, если этот ConversationHandler вложен в другой
            # ConversationHandler.END: SOME_PARENT_STATE,
        }
    )
    return conv_handler