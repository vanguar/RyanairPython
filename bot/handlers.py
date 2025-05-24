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
from datetime import datetime, timedelta # timedelta может понадобиться для min_date
from collections import defaultdict

from . import config, keyboards, helpers, flight_api

logger = logging.getLogger(__name__)

# --- Вспомогательные функции для обработчиков ---
async def ask_departure_country(update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str):
    if hasattr(update, 'message') and update.message:
        await update.message.reply_text(message_text, reply_markup=keyboards.get_country_reply_keyboard()) #
    elif hasattr(update, 'callback_query') and update.callback_query and update.effective_chat:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=message_text, reply_markup=keyboards.get_country_reply_keyboard()) #
    else:
        logger.warning("ask_departure_country: Не удалось определить, как отправить сообщение.")

async def ask_departure_city(update: Update, context: ContextTypes.DEFAULT_TYPE, country_name: str):
    if hasattr(update, 'message') and update.message:
        await update.message.reply_text("Выберите город вылета:", reply_markup=keyboards.get_city_reply_keyboard(country_name)) #
    elif hasattr(update, 'callback_query') and update.callback_query and update.effective_chat:
         await context.bot.send_message(chat_id=update.effective_chat.id, text="Выберите город вылета:", reply_markup=keyboards.get_city_reply_keyboard(country_name)) #

async def ask_arrival_country(update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str):
    if hasattr(update, 'message') and update.message:
        await update.message.reply_text(message_text, reply_markup=keyboards.get_country_reply_keyboard()) #
    elif hasattr(update, 'callback_query') and update.callback_query and update.effective_chat:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=message_text, reply_markup=keyboards.get_country_reply_keyboard()) #

async def ask_arrival_city(update: Update, context: ContextTypes.DEFAULT_TYPE, country_name: str):
    if hasattr(update, 'message') and update.message:
        await update.message.reply_text("Выберите город прилёта:", reply_markup=keyboards.get_city_reply_keyboard(country_name)) #
    elif hasattr(update, 'callback_query') and update.callback_query and update.effective_chat:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Выберите город прилёта:", reply_markup=keyboards.get_city_reply_keyboard(country_name)) #

async def ask_year(message_or_update: Update | object, context: ContextTypes.DEFAULT_TYPE, message_text: str, callback_prefix: str = ""):
    target_message_object = None
    if hasattr(message_or_update, 'callback_query') and message_or_update.callback_query:
        await message_or_update.callback_query.edit_message_text(
            text=message_text,
            reply_markup=keyboards.generate_year_buttons(callback_prefix) #
        )
        return
    elif hasattr(message_or_update, 'message') and message_or_update.message:
        target_message_object = message_or_update.message
    elif hasattr(message_or_update, 'reply_text'):
        target_message_object = message_or_update

    if target_message_object and hasattr(target_message_object, 'reply_text'):
        await target_message_object.reply_text(
            message_text,
            reply_markup=keyboards.generate_year_buttons(callback_prefix) #
        )
    elif hasattr(message_or_update, 'effective_chat') and message_or_update.effective_chat:
         await context.bot.send_message(
            chat_id=message_or_update.effective_chat.id,
            text=message_text,
            reply_markup=keyboards.generate_year_buttons(callback_prefix) #
        )
    else:
        logger.warning("ask_year: не удалось определить объект для ответа.")

async def ask_month(update: Update, context: ContextTypes.DEFAULT_TYPE,
                  year_for_months: int, message_text: str, callback_prefix: str = "",
                  departure_year_for_comparison: int = None,
                  departure_month_for_comparison: int = None):
    await update.callback_query.edit_message_text(
        text=message_text,
        reply_markup=keyboards.generate_month_buttons( #
            callback_prefix=callback_prefix,
            year_for_months=year_for_months,
            min_departure_month=departure_month_for_comparison,  # ИСПРАВЛЕНО
            departure_year_for_comparison=departure_year_for_comparison  # ИСПРАВЛЕНО
        )
    )

async def ask_date_range(update: Update, context: ContextTypes.DEFAULT_TYPE, year: int, month: int, message_text: str, callback_prefix: str = ""):
    await update.callback_query.edit_message_text(
        text=message_text,
        reply_markup=keyboards.generate_date_range_buttons(year, month, callback_prefix) #
    )

async def ask_specific_date(update: Update, context: ContextTypes.DEFAULT_TYPE,
                            year: int, month: int, range_start: int, range_end: int,
                            message_text: str, callback_prefix: str = "",
                            min_allowed_date_for_comparison: datetime = None):
    await update.callback_query.edit_message_text(
        text=message_text,
        reply_markup=keyboards.generate_specific_date_buttons( #
            year, month, range_start, range_end,
            callback_prefix=callback_prefix,
            min_allowed_date=min_allowed_date_for_comparison
        )
    )

async def process_and_send_flights(update: Update, context: ContextTypes.DEFAULT_TYPE, flights_by_date: dict): #
    chat_id = update.effective_chat.id
    context.user_data.pop('remaining_flights_to_show', None)

    if not flights_by_date:
        await context.bot.send_message(chat_id=chat_id, text=config.MSG_NO_FLIGHTS_FOUND) #
        dep_country = context.user_data.get('departure_country')
        dep_airport_iata = context.user_data.get('departure_airport_iata')
        if dep_country and dep_airport_iata and config.COUNTRIES_DATA.get(dep_country) and \
           len(config.COUNTRIES_DATA[dep_country]) > 1: #
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"Хотите поискать вылеты из других аэропортов в стране {dep_country} по этому же направлению и датам?", #
                reply_markup=keyboards.get_search_other_airports_keyboard(dep_country) #
            )
            return config.ASK_SEARCH_OTHER_AIRPORTS #
        await context.bot.send_message(
            chat_id=chat_id, text="Что дальше?",
            reply_markup=keyboards.get_yes_no_keyboard( #
                yes_callback="prompt_new_search_type", no_callback="end_search_session",
                yes_text="✅ Начать новый поиск", no_text="❌ Закончить"
            )
        )
        return ConversationHandler.END

    else:
        await context.bot.send_message(chat_id=chat_id, text=config.MSG_FLIGHTS_FOUND_SEE_BELOW) #
        total_flights_shown_count = 0
        flights_message_parts = []
        sorted_dates = sorted(flights_by_date.keys())

        for flight_date_str in sorted_dates:
            flights_on_this_date = flights_by_date[flight_date_str]
            if not flights_on_this_date:
                continue
            try:
                date_obj = datetime.strptime(flight_date_str, "%Y-%m-%d")
                formatted_date_header = f"\n--- 📅 *{date_obj.strftime('%d %B %Y (%A)')}* ---\n"
            except ValueError: # Fallback for "unknown_date" or other non-standard keys
                formatted_date_header = f"\n--- 📅 *{flight_date_str}* ---\n"

            flights_message_parts.append(formatted_date_header)

            for i, flight in enumerate(flights_on_this_date):
                if i < config.FLIGHTS_CHUNK_SIZE: #
                    formatted_flight = helpers.format_flight_details(flight) #
                    flights_message_parts.append(formatted_flight)
                    total_flights_shown_count += 1
                else:
                    flights_message_parts.append(f"...и еще {len(flights_on_this_date) - i} рейс(ов) на эту дату.")
                    break

            if not flights_message_parts[-1].endswith("рейс(ов) на эту дату."):
                 flights_message_parts.append("\n")

        if flights_message_parts:
            full_message = "".join(flights_message_parts)
            max_length = 4096
            for i in range(0, len(full_message), max_length):
                await context.bot.send_message(chat_id=chat_id, text=full_message[i:i+max_length], parse_mode='Markdown')

        if total_flights_shown_count == 0 and any(flights_by_date.values()):
             await context.bot.send_message(chat_id=chat_id, text="Найдены рейсы, но произошла ошибка при отображении.")

    await context.bot.send_message(
        chat_id=chat_id, text="Что дальше?",
        reply_markup=keyboards.get_yes_no_keyboard( #
            yes_callback="prompt_new_search_type", no_callback="end_search_session",
            yes_text="✅ Начать новый поиск", no_text="❌ Закончить"
        )
    )
    context.user_data.clear()
    return ConversationHandler.END

async def show_all_remaining_flights_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text="Эта функция отображения оставшихся рейсов обновляется.")

async def prompt_new_search_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.message:
      await query.edit_message_text(text=config.MSG_WELCOME, reply_markup=keyboards.get_main_menu_keyboard()) # [cite: 1]
    elif update.effective_chat:
      await context.bot.send_message(chat_id=update.effective_chat.id, text=config.MSG_WELCOME, reply_markup=keyboards.get_main_menu_keyboard()) # [cite: 1]

async def end_search_session_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.message:
      await query.edit_message_text(text="Поиск завершен. Если понадоблюсь, вы знаете, как меня найти! /start")
    elif update.effective_chat:
      await context.bot.send_message(chat_id=update.effective_chat.id, text="Поиск завершен. Если понадоблюсь, вы знаете, как меня найти! /start")
    context.user_data.clear()

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(config.MSG_WELCOME, reply_markup=keyboards.get_main_menu_keyboard()) # [cite: 1]
    elif update.callback_query:
        await update.callback_query.answer()
        if update.callback_query.message:
            await update.callback_query.edit_message_text(config.MSG_WELCOME, reply_markup=keyboards.get_main_menu_keyboard()) # [cite: 1]
        elif update.effective_chat:
             await context.bot.send_message(chat_id=update.effective_chat.id, text=config.MSG_WELCOME, reply_markup=keyboards.get_main_menu_keyboard()) # [cite: 1]

async def start_search_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    if query.data == "start_standard_search":
        if query.message: await query.edit_message_text(text="Выбран стандартный поиск.")
        await context.bot.send_message(chat_id=update.effective_chat.id, text=config.MSG_FLIGHT_TYPE_PROMPT, reply_markup=keyboards.get_flight_type_reply_keyboard()) # [cite: 1]
        return config.SELECTING_FLIGHT_TYPE #
    elif query.data == "start_flex_search":
        if query.message: await query.edit_message_text(text="Выбран гибкий поиск.")
        await context.bot.send_message(chat_id=update.effective_chat.id, text=config.MSG_FLIGHT_TYPE_PROMPT, reply_markup=keyboards.get_flight_type_reply_keyboard()) # [cite: 1]
        return config.SELECTING_FLEX_FLIGHT_TYPE #
    # NEW "Куда угодно"
    elif query.data == "start_flex_anywhere": # Handler defined separately below
        return await start_flex_anywhere_callback(update, context)
    return ConversationHandler.END

async def start_flex_anywhere_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # query may not be present if called directly (though pattern suggests it's from callback)
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        if query.message:
            await query.edit_message_text(text="Выбран поиск \"Куда угодно\".")
    else: # Should not happen with current setup but good for robustness
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Выбран поиск \"Куда угодно\".")

    context.user_data.clear()
    context.user_data['arrival_airport_iata'] = None
    context.user_data['departure_date'] = None
    context.user_data['return_date'] = None

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=config.MSG_FLIGHT_TYPE_PROMPT, #
        reply_markup=keyboards.get_flight_type_reply_keyboard() #
    )
    return config.SELECTING_FLEX_FLIGHT_TYPE #

# --- СТАНДАРТНЫЙ ПОИСК ---
async def standard_flight_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_input = update.message.text
    if user_input not in ['1', '2']:
        await update.message.reply_text("Пожалуйста, выберите 1 или 2.", reply_markup=keyboards.get_flight_type_reply_keyboard()) #
        return config.SELECTING_FLIGHT_TYPE #
    context.user_data['flight_type_one_way'] = (user_input == '1')
    await ask_departure_country(update, context, "Выберите страну вылета:")
    return config.SELECTING_DEPARTURE_COUNTRY #

async def standard_departure_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    country = update.message.text
    if country not in config.COUNTRIES_DATA: #
        await update.message.reply_text("Страна не найдена! Пожалуйста, выберите из списка.")
        await ask_departure_country(update, context, "Выберите страну вылета:")
        return config.SELECTING_DEPARTURE_COUNTRY #
    context.user_data['departure_country'] = country
    await ask_departure_city(update, context, country)
    return config.SELECTING_DEPARTURE_CITY #

async def standard_departure_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    city = update.message.text
    country = context.user_data.get('departure_country')
    iata_code = helpers.get_airport_iata(country, city) #
    if not iata_code:
        await update.message.reply_text("Город не найден или неверная страна! Пожалуйста, выберите из списка.")
        await ask_departure_city(update, context, country)
        return config.SELECTING_DEPARTURE_CITY #
    context.user_data['departure_airport_iata'] = iata_code
    context.user_data['departure_city_name'] = city
    await ask_year(update, context, "Выберите год вылета:", callback_prefix=config.CALLBACK_PREFIX_STANDARD + "dep_year_") #
    return config.SELECTING_DEPARTURE_YEAR #

async def standard_departure_year_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selected_year = int(query.data.replace(config.CALLBACK_PREFIX_STANDARD + "dep_year_", "")) #
    context.user_data['departure_year'] = selected_year
    await ask_month(update, context,
                  year_for_months=selected_year,
                  message_text=f"Год вылета: {selected_year}. Выберите месяц:",
                  callback_prefix=config.CALLBACK_PREFIX_STANDARD + "dep_month_") #
    return config.SELECTING_DEPARTURE_MONTH #

async def standard_departure_month_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selected_month = int(query.data.replace(config.CALLBACK_PREFIX_STANDARD + "dep_month_", "")) #

    # Серверная валидация выбранного месяца (на всякий случай, если клавиатура не отфильтровала)
    year = context.user_data['departure_year']
    now = datetime.now()
    if year == now.year and selected_month < now.month:
        await query.edit_message_text(text=f"Выбран прошедший месяц ({config.RUSSIAN_MONTHS[selected_month]}). Пожалуйста, выберите корректный месяц.") #
        await ask_month(update, context,
                      year_for_months=year,
                      message_text=f"Год вылета: {year}. Выберите месяц:",
                      callback_prefix=config.CALLBACK_PREFIX_STANDARD + "dep_month_") #
        return config.SELECTING_DEPARTURE_MONTH #

    context.user_data['departure_month'] = selected_month
    month_name = config.RUSSIAN_MONTHS.get(selected_month, "") #
    context.user_data['departure_month_name'] = month_name
    await ask_date_range(update, context, year, selected_month, f"Выбран: {month_name} {year}. Выберите диапазон дат:", callback_prefix=config.CALLBACK_PREFIX_STANDARD + "dep_range_") #
    return config.SELECTING_DEPARTURE_DATE_RANGE #

async def standard_departure_date_range_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selected_range_str = query.data.replace(config.CALLBACK_PREFIX_STANDARD + "dep_range_", "") #
    try:
        start_day, end_day = map(int, selected_range_str.split('-'))
        context.user_data['departure_date_range_str'] = selected_range_str
    except ValueError:
        await query.edit_message_text(text="Некорректный диапазон дат. Пожалуйста, выберите снова.")
        year = context.user_data['departure_year']
        month = context.user_data['departure_month']
        month_name = config.RUSSIAN_MONTHS.get(month, "") #
        await ask_date_range(update, context, year, month, f"Выбран: {month_name} {year}. Выберите диапазон дат:", callback_prefix=config.CALLBACK_PREFIX_STANDARD + "dep_range_") #
        return config.SELECTING_DEPARTURE_DATE_RANGE #

    year = context.user_data['departure_year']
    month = context.user_data['departure_month']
    min_date_for_dep = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    await ask_specific_date(update, context, year, month, start_day, end_day,
                            f"Диапазон: {selected_range_str}. Выберите дату:",
                            callback_prefix=config.CALLBACK_PREFIX_STANDARD + "dep_date_", #
                            min_allowed_date_for_comparison=min_date_for_dep)
    return config.SELECTING_DEPARTURE_DATE #

async def standard_departure_date_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selected_date_str = query.data.replace(config.CALLBACK_PREFIX_STANDARD + "dep_date_", "") #
    date_obj = helpers.validate_date_format(selected_date_str) #
    min_allowed_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    if not date_obj or date_obj < min_allowed_date :
        await query.edit_message_text("Некорректная дата или дата в прошлом. Попробуйте снова.")
        year = context.user_data['departure_year']
        month = context.user_data['departure_month']
        selected_range_str = context.user_data.get('departure_date_range_str', "1-10")
        try:
            start_day, end_day = map(int, selected_range_str.split('-'))
        except ValueError: start_day, end_day = 1, 10
        await ask_specific_date(update, context, year, month, start_day, end_day,
                                f"Диапазон: {selected_range_str}. Выберите дату:",
                                callback_prefix=config.CALLBACK_PREFIX_STANDARD + "dep_date_", #
                                min_allowed_date_for_comparison=min_allowed_date)
        return config.SELECTING_DEPARTURE_DATE #

    context.user_data['departure_date'] = selected_date_str # Сохраняем строку ГГГГ-ММ-ДД
    formatted_date = date_obj.strftime('%d-%m-%Y')
    await query.edit_message_text(text=f"Дата вылета: {formatted_date}")
    await ask_arrival_country(update, context, "Выберите страну прилёта:")
    return config.SELECTING_ARRIVAL_COUNTRY #

async def standard_arrival_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    country = update.message.text
    if country not in config.COUNTRIES_DATA: #
        await update.message.reply_text("Страна не найдена! Пожалуйста, выберите из списка.")
        await ask_arrival_country(update, context, "Выберите страну прилёта:")
        return config.SELECTING_ARRIVAL_COUNTRY #
    departure_airport_iata = context.user_data.get('departure_airport_iata')
    if departure_airport_iata and country in config.COUNTRIES_DATA and len(config.COUNTRIES_DATA[country]) == 1: #
        single_city_name = list(config.COUNTRIES_DATA[country].keys())[0] #
        single_airport_iata = helpers.get_airport_iata(country, single_city_name) #
        if single_airport_iata == departure_airport_iata:
            await update.message.reply_text(
                f"Единственный аэропорт в стране \"{country}\" ({single_city_name}) совпадает с вашим аэропортом вылета. "
                "Выберите другую страну прилёта или введите /cancel для отмены и изменения аэропорта вылета."
            )
            await ask_arrival_country(update, context, "Выберите другую страну прилёта:")
            return config.SELECTING_ARRIVAL_COUNTRY #
    context.user_data['arrival_country'] = country
    await ask_arrival_city(update, context, country)
    return config.SELECTING_ARRIVAL_CITY #

async def standard_arrival_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    city = update.message.text
    country = context.user_data.get('arrival_country')
    iata_code = helpers.get_airport_iata(country, city) #
    if not iata_code:
        await update.message.reply_text("Город не найден или неверная страна! Пожалуйста, выберите из списка.")
        await ask_arrival_city(update, context, country)
        return config.SELECTING_ARRIVAL_CITY #
    if iata_code == context.user_data.get('departure_airport_iata'):
        await update.message.reply_text("Аэропорт прилёта не может совпадать с аэропортом вылета. Выберите другой город.")
        await ask_arrival_city(update, context, country)
        return config.SELECTING_ARRIVAL_CITY #
    context.user_data['arrival_airport_iata'] = iata_code
    context.user_data['arrival_city_name'] = city
    if context.user_data.get('flight_type_one_way', True):
        await update.message.reply_text(config.MSG_MAX_PRICE_PROMPT, reply_markup=ReplyKeyboardRemove()) #
        return config.SELECTING_MAX_PRICE #
    else:
        await ask_year(update, context, "Выберите год обратного вылета:", callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_year_") #
        return config.SELECTING_RETURN_YEAR #

async def standard_return_year_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selected_return_year = int(query.data.replace(config.CALLBACK_PREFIX_STANDARD + "ret_year_", "")) #

    departure_year = context.user_data.get('departure_year')
    if selected_return_year < departure_year:
        await query.edit_message_text(text=f"Год возврата ({selected_return_year}) не может быть раньше года вылета ({departure_year}).")
        await ask_year(query, context, "Выберите корректный год обратного вылета:", callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_year_") #
        return config.SELECTING_RETURN_YEAR #

    context.user_data['return_year'] = selected_return_year
    departure_month = context.user_data.get('departure_month')
    await ask_month(update, context,
                  year_for_months=selected_return_year,
                  message_text=f"Год обратного вылета: {selected_return_year}. Выберите месяц:",
                  callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_month_", #
                  departure_year_for_comparison=departure_year,
                  departure_month_for_comparison=departure_month)
    return config.SELECTING_RETURN_MONTH #

async def standard_return_month_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selected_return_month = int(query.data.replace(config.CALLBACK_PREFIX_STANDARD + "ret_month_", "")) #

    return_year = context.user_data['return_year']
    departure_year = context.user_data['departure_year']
    departure_month = context.user_data['departure_month']

    if return_year == departure_year and selected_return_month < departure_month:
        await query.edit_message_text(text=f"Месяц возврата ({config.RUSSIAN_MONTHS[selected_return_month]}) не может быть раньше месяца вылета ({config.RUSSIAN_MONTHS[departure_month]} {departure_year}).") #
        await ask_month(update, context,
                      year_for_months=return_year,
                      message_text=f"Год обратного вылета: {return_year}. Выберите месяц:",
                      callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_month_", #
                      departure_year_for_comparison=departure_year,
                      departure_month_for_comparison=departure_month)
        return config.SELECTING_RETURN_MONTH #

    context.user_data['return_month'] = selected_return_month
    month_name = config.RUSSIAN_MONTHS.get(selected_return_month, "") #
    context.user_data['return_month_name'] = month_name
    await ask_date_range(update, context, return_year, selected_return_month, f"Выбран: {month_name} {return_year}. Выберите диапазон дат:", callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_range_") #
    return config.SELECTING_RETURN_DATE_RANGE #

async def standard_return_date_range_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selected_range_str = query.data.replace(config.CALLBACK_PREFIX_STANDARD + "ret_range_", "") #
    try:
        start_day, end_day = map(int, selected_range_str.split('-'))
        context.user_data['return_date_range_str'] = selected_range_str
    except ValueError:
        await query.edit_message_text("Ошибка в диапазоне дат. Попробуйте выбрать месяц заново.")
        year = context.user_data['return_year']
        # month_name = context.user_data.get('return_month_name', "")
        departure_year = context.user_data.get('departure_year')
        departure_month = context.user_data.get('departure_month')
        await ask_month(update, context,
                        year_for_months=year,
                        message_text=f"Год обратного вылета: {year}. Выберите месяц:",
                        callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_month_", #
                        departure_year_for_comparison=departure_year,
                        departure_month_for_comparison=departure_month)
        return config.SELECTING_RETURN_MONTH #

    year = context.user_data['return_year']
    month = context.user_data['return_month']
    departure_date_str = context.user_data.get('departure_date')
    min_date_for_return = None
    if departure_date_str:
        min_date_for_return = helpers.validate_date_format(departure_date_str) #
        if not min_date_for_return: # Should not happen if departure_date is always valid
            logger.error(f"Не удалось получить дату вылета для сравнения: {departure_date_str}")
            await query.edit_message_text("Произошла ошибка с датой вылета. Попробуйте начать заново /start.")
            context.user_data.clear()
            return ConversationHandler.END

    await ask_specific_date(update, context, year, month, start_day, end_day,
                            f"Диапазон: {selected_range_str}. Выберите дату:",
                            callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_date_", #
                            min_allowed_date_for_comparison=min_date_for_return)
    return config.SELECTING_RETURN_DATE #

async def standard_return_date_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selected_date_str = query.data.replace(config.CALLBACK_PREFIX_STANDARD + "ret_date_", "") #
    return_date_obj = helpers.validate_date_format(selected_date_str) #
    departure_date_obj = helpers.validate_date_format(context.user_data.get('departure_date')) #

    if not return_date_obj or not departure_date_obj or return_date_obj < departure_date_obj:
        await query.edit_message_text("Некорректная дата возвращения или она раньше даты вылета. Попробуйте снова.")
        year = context.user_data['return_year']
        month = context.user_data['return_month']
        selected_range_str = context.user_data.get('return_date_range_str', "1-10")
        try:
            start_day, end_day = map(int, selected_range_str.split('-'))
        except ValueError: start_day, end_day = 1, 10
        await ask_specific_date(update, context, year, month, start_day, end_day,
                                f"Диапазон: {selected_range_str}. Выберите дату:",
                                callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_date_", #
                                min_allowed_date_for_comparison=departure_date_obj)
        return config.SELECTING_RETURN_DATE #

    context.user_data['return_date'] = selected_date_str
    formatted_date = return_date_obj.strftime('%d-%m-%Y')
    await query.edit_message_text(text=f"Дата обратного вылета: {formatted_date}")
    await query.message.reply_text(config.MSG_MAX_PRICE_PROMPT, reply_markup=ReplyKeyboardRemove()) #
    return config.SELECTING_MAX_PRICE #

async def standard_max_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    price = helpers.validate_price(update.message.text) #
    if price is None:
        await update.message.reply_text("Некорректная цена. Введите положительное число, например, 50:")
        return config.SELECTING_MAX_PRICE #
    context.user_data['max_price'] = price
    await update.message.reply_text(config.MSG_SEARCHING_FLIGHTS, reply_markup=ReplyKeyboardRemove()) #
    flights_by_date = await flight_api.find_flights_with_fallback( #
        departure_airport_iata=context.user_data['departure_airport_iata'],
        arrival_airport_iata=context.user_data['arrival_airport_iata'],
        departure_date_str=context.user_data['departure_date'],
        max_price=context.user_data['max_price'],
        return_date_str=context.user_data.get('return_date'),
        is_one_way=context.user_data.get('flight_type_one_way', True)
    )
    return await process_and_send_flights(update, context, flights_by_date)

# --- ГИБКИЙ ПОИСК ---
# (Аналогичные изменения для flex_* функций, касающихся выбора дат и месяцев)

async def flex_flight_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_input = update.message.text
    if user_input not in ['1', '2']:
        await update.message.reply_text("Пожалуйста, выберите 1 или 2.", reply_markup=keyboards.get_flight_type_reply_keyboard()) #
        return config.SELECTING_FLEX_FLIGHT_TYPE #
    context.user_data['flight_type_one_way'] = (user_input == '1')
    await update.message.reply_text(config.MSG_MAX_PRICE_PROMPT, reply_markup=ReplyKeyboardRemove()) #
    return config.SELECTING_FLEX_MAX_PRICE #

async def flex_max_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    price = helpers.validate_price(update.message.text) #
    if price is None:
        await update.message.reply_text("Некорректная цена. Введите положительное число, например, 50:")
        return config.SELECTING_FLEX_MAX_PRICE #
    context.user_data['max_price'] = price
    await update.message.reply_text(
        "Указать аэропорт вылета?",
        reply_markup=keyboards.get_yes_no_keyboard( #
            yes_callback=config.CALLBACK_PREFIX_FLEX + "ask_dep_yes", #
            no_callback=config.CALLBACK_PREFIX_FLEX + "ask_dep_no" #
        )
    )
    return config.ASK_FLEX_DEPARTURE_AIRPORT #

async def flex_ask_departure_airport(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == config.CALLBACK_PREFIX_FLEX + "ask_dep_yes": #
        if query.message: await query.edit_message_text(text="Аэропорт вылета: ДА")
        await ask_departure_country(update, context, "Выберите страну вылета:")
        return config.SELECTING_FLEX_DEPARTURE_COUNTRY #
    else:
        if query.message: await query.edit_message_text(text="Аэропорт вылета: НЕТ (пропущено).")
        context.user_data['departure_airport_iata'] = None
        logger.info("Гибкий поиск: пользователь пропустил аэропорт вылета.")
        if context.user_data.get('arrival_airport_iata') is None: # "Куда угодно" поток
            if query.message: await query.message.reply_text(
                "Указать конкретные даты?",
                reply_markup=keyboards.get_skip_dates_keyboard( #
                    callback_select_dates=config.CALLBACK_PREFIX_FLEX + "ask_dates_yes" #
                ))
            return config.ASK_FLEX_DATES #
        if query.message: await query.message.reply_text(
            "Указать аэропорт прилёта?",
            reply_markup=keyboards.get_yes_no_keyboard( #
                yes_callback=config.CALLBACK_PREFIX_FLEX + "ask_arr_yes", #
                no_callback=config.CALLBACK_PREFIX_FLEX + "ask_arr_no" #
            ))
        return config.ASK_FLEX_ARRIVAL_AIRPORT #

async def flex_departure_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (аналогично standard_departure_country)
    country = update.message.text
    if country not in config.COUNTRIES_DATA: #
        await update.message.reply_text("Страна не найдена! Пожалуйста, выберите из списка.")
        await ask_departure_country(update, context, "Выберите страну вылета:")
        return config.SELECTING_FLEX_DEPARTURE_COUNTRY #
    context.user_data['departure_country'] = country
    await ask_departure_city(update, context, country)
    return config.SELECTING_FLEX_DEPARTURE_CITY #

async def flex_departure_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (аналогично standard_departure_city)
    city = update.message.text
    country = context.user_data.get('departure_country')
    iata_code = helpers.get_airport_iata(country, city) #
    if not iata_code:
        await update.message.reply_text("Город не найден! Пожалуйста, выберите из списка.")
        await ask_departure_city(update, context, country)
        return config.SELECTING_FLEX_DEPARTURE_CITY #
    context.user_data['departure_airport_iata'] = iata_code
    context.user_data['departure_city_name'] = city
    if context.user_data.get('arrival_airport_iata') is None: # "Куда угодно"
        await update.message.reply_text(
            "Указать конкретные даты?",
            reply_markup=keyboards.get_skip_dates_keyboard( #
                callback_select_dates=config.CALLBACK_PREFIX_FLEX + "ask_dates_yes" #
            ))
        return config.ASK_FLEX_DATES #
    await update.message.reply_text(
        "Указать аэропорт прилёта?",
        reply_markup=keyboards.get_yes_no_keyboard( #
            yes_callback=config.CALLBACK_PREFIX_FLEX + "ask_arr_yes", #
            no_callback=config.CALLBACK_PREFIX_FLEX + "ask_arr_no" #
        ))
    return config.ASK_FLEX_ARRIVAL_AIRPORT #

async def flex_ask_arrival_airport(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if context.user_data.get('arrival_airport_iata') is None and context.user_data.get('departure_date') is None: # "Куда угодно"
        if query.message: await query.edit_message_text(text="Аэропорт прилёта: Любой (пропущено)")
        await context.bot.send_message(chat_id=update.effective_chat.id,
            text="Указать конкретные даты?",
            reply_markup=keyboards.get_skip_dates_keyboard( #
                callback_select_dates=config.CALLBACK_PREFIX_FLEX + "ask_dates_yes" #
            ))
        return config.ASK_FLEX_DATES #
    if query.data == config.CALLBACK_PREFIX_FLEX + "ask_arr_yes": #
        if query.message: await query.edit_message_text(text="Аэропорт прилёта: ДА")
        await ask_arrival_country(update, context, "Выберите страну прилёта:")
        return config.SELECTING_FLEX_ARRIVAL_COUNTRY #
    else: # ask_arr_no
        if query.message: await query.edit_message_text(text="Аэропорт прилёта: НЕТ (поиск в любом направлении)")
        context.user_data['arrival_airport_iata'] = None
        if context.user_data.get('departure_airport_iata') is None:
             msg = "Ошибка: Нужно указать хотя бы аэропорт вылета для поиска 'в любом направлении'. Начните /start заново."
             if query.message: await query.message.reply_text(msg, reply_markup=ReplyKeyboardRemove())
             else: await context.bot.send_message(chat_id=update.effective_chat.id, text=msg, reply_markup=ReplyKeyboardRemove())
             context.user_data.clear()
             return ConversationHandler.END
        await context.bot.send_message(chat_id=update.effective_chat.id,
            text="Указать конкретные даты?",
            reply_markup=keyboards.get_skip_dates_keyboard( #
                callback_select_dates=config.CALLBACK_PREFIX_FLEX + "ask_dates_yes" #
            ))
        return config.ASK_FLEX_DATES #

async def flex_arrival_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (аналогично standard_arrival_country)
    country = update.message.text
    # ... (остальная логика)
    if country not in config.COUNTRIES_DATA: # Пример #
        await update.message.reply_text("Страна не найдена!")
        return config.SELECTING_FLEX_ARRIVAL_COUNTRY #
    context.user_data['arrival_country'] = country
    await ask_arrival_city(update, context, country)
    return config.SELECTING_FLEX_ARRIVAL_CITY #


async def flex_arrival_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (аналогично standard_arrival_city)
    city = update.message.text # Пример
    country = context.user_data.get('arrival_country')
    iata_code = helpers.get_airport_iata(country, city) #
    if not iata_code:
        await update.message.reply_text("Город не найден!")
        return config.SELECTING_FLEX_ARRIVAL_CITY #
    if context.user_data.get('departure_airport_iata') and iata_code == context.user_data['departure_airport_iata']:
        await update.message.reply_text("Аэропорты совпадают!")
        return config.SELECTING_FLEX_ARRIVAL_CITY #
    context.user_data['arrival_airport_iata'] = iata_code
    context.user_data['arrival_city_name'] = city
    if context.user_data.get('departure_date') is None: # "Куда угодно"
        await update.message.reply_text(config.MSG_SEARCHING_FLIGHTS, reply_markup=ReplyKeyboardRemove()) #
        # ... (вызов flight_api)
        flights_by_date = await flight_api.find_flights_with_fallback( #
            departure_airport_iata=context.user_data.get('departure_airport_iata'),
            arrival_airport_iata=context.user_data.get('arrival_airport_iata'),
            departure_date_str=None, max_price=context.user_data['max_price'],
            return_date_str=None, is_one_way=context.user_data.get('flight_type_one_way', True)
        )
        return await process_and_send_flights(update, context, flights_by_date)
    await update.message.reply_text(
        "Указать конкретные даты?",
        reply_markup=keyboards.get_skip_dates_keyboard( #
            callback_select_dates=config.CALLBACK_PREFIX_FLEX + "ask_dates_yes" #
        ))
    return config.ASK_FLEX_DATES #

async def flex_ask_dates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    departure_airport_is_set = context.user_data.get('departure_airport_iata') is not None
    if query.data == config.CALLBACK_PREFIX_FLEX + "ask_dates_yes": #
        if query.message: await query.edit_message_text(text="Даты: ДА, указать конкретные.")
        await ask_year(query, context, "Выберите год вылета:", callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_year_") #
        return config.SELECTING_FLEX_DEPARTURE_YEAR #
    elif query.data == config.CALLBACK_NO_SPECIFIC_DATES: #
        if query.message: await query.edit_message_text(text="Даты: НЕТ, искать на ближайший год.")
        context.user_data['departure_date'] = None
        context.user_data['return_date'] = None
        if not departure_airport_is_set and context.user_data.get('arrival_airport_iata') is not None : # Если не "куда угодно" и не указан вылет
            msg_text = ("Ошибка: Для поиска без дат необходимо указать аэропорт вылета. Начните поиск заново /start.")
            if query.message: await query.edit_message_text(text=msg_text, reply_markup=None)
            else: await context.bot.send_message(chat_id=update.effective_chat.id, text=msg_text, reply_markup=ReplyKeyboardRemove())
            context.user_data.clear()
            return ConversationHandler.END
        await context.bot.send_message(chat_id=update.effective_chat.id, text=config.MSG_SEARCHING_FLIGHTS, reply_markup=ReplyKeyboardRemove()) #
        flights_by_date = await flight_api.find_flights_with_fallback( #
            departure_airport_iata=context.user_data.get('departure_airport_iata'),
            arrival_airport_iata=context.user_data.get('arrival_airport_iata'),
            departure_date_str=None, max_price=context.user_data['max_price'],
            return_date_str=None, is_one_way=context.user_data.get('flight_type_one_way', True)
        )
        return await process_and_send_flights(update, context, flights_by_date)
    return config.ASK_FLEX_DATES #

async def flex_departure_year_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Аналогично standard_departure_year_selected
    query = update.callback_query
    await query.answer()
    selected_year = int(query.data.replace(config.CALLBACK_PREFIX_FLEX + "dep_year_", "")) #
    context.user_data['departure_year'] = selected_year
    await ask_month(update, context,
                  year_for_months=selected_year,
                  message_text=f"Год вылета: {selected_year}. Выберите месяц:",
                  callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_month_") #
    return config.SELECTING_FLEX_DEPARTURE_MONTH #

async def flex_departure_month_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Аналогично standard_departure_month_selected
    query = update.callback_query
    await query.answer()
    selected_month = int(query.data.replace(config.CALLBACK_PREFIX_FLEX + "dep_month_", "")) #
    year = context.user_data['departure_year']
    now = datetime.now()
    if year == now.year and selected_month < now.month:
        await query.edit_message_text(text=f"Выбран прошедший месяц ({config.RUSSIAN_MONTHS[selected_month]}). Пожалуйста, выберите корректный месяц.") #
        await ask_month(update, context, year, f"Год вылета: {year}. Выберите месяц:", callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_month_") #
        return config.SELECTING_FLEX_DEPARTURE_MONTH #
    context.user_data['departure_month'] = selected_month
    month_name = config.RUSSIAN_MONTHS.get(selected_month, "") #
    context.user_data['departure_month_name'] = month_name
    await ask_date_range(update, context, year, selected_month, f"Выбран: {month_name} {year}. Выберите диапазон дат:", callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_range_") #
    return config.SELECTING_FLEX_DEPARTURE_DATE_RANGE #

async def flex_departure_date_range_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Аналогично standard_departure_date_range_selected
    query = update.callback_query
    await query.answer()
    selected_range_str = query.data.replace(config.CALLBACK_PREFIX_FLEX + "dep_range_", "") #
    # ... (логика start_day, end_day)
    try: start_day, end_day = map(int, selected_range_str.split('-'))
    except ValueError: # ... обработка ошибки ...
        await query.edit_message_text("Неверный диапазон")
        return config.SELECTING_FLEX_DEPARTURE_DATE_RANGE # Пример #
    context.user_data['departure_date_range_str'] = selected_range_str
    year = context.user_data['departure_year']
    month = context.user_data['departure_month']
    min_date_for_dep = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    await ask_specific_date(update, context, year, month, start_day, end_day,
                            f"Диапазон: {selected_range_str}. Выберите дату:",
                            callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_date_", #
                            min_allowed_date_for_comparison=min_date_for_dep)
    return config.SELECTING_FLEX_DEPARTURE_DATE #

async def flex_departure_date_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Аналогично standard_departure_date_selected
    query = update.callback_query
    await query.answer()
    selected_date_str = query.data.replace(config.CALLBACK_PREFIX_FLEX + "dep_date_", "") #
    date_obj = helpers.validate_date_format(selected_date_str) #
    min_allowed_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    if not date_obj or date_obj < min_allowed_date :
        await query.edit_message_text("Некорректная дата или дата в прошлом. Попробуйте снова.")
        # ... (логика повторного запроса)
        year, month = context.user_data['departure_year'], context.user_data['departure_month']
        s_range = context.user_data.get('departure_date_range_str', "1-10")
        try: start_day, end_day = map(int, s_range.split('-'))
        except: start_day, end_day = 1,10
        await ask_specific_date(update, context, year, month, start_day, end_day, "Выберите дату:",
                                callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_date_", #
                                min_allowed_date_for_comparison=min_allowed_date)
        return config.SELECTING_FLEX_DEPARTURE_DATE #
    context.user_data['departure_date'] = selected_date_str
    formatted_date = date_obj.strftime('%d-%m-%Y')
    if context.user_data.get('flight_type_one_way', True):
        if query.message: await query.edit_message_text(text=f"Дата вылета: {formatted_date}")
        await context.bot.send_message(chat_id=update.effective_chat.id, text=config.MSG_SEARCHING_FLIGHTS, reply_markup=ReplyKeyboardRemove()) #
        flights_by_date = await flight_api.find_flights_with_fallback( #
            departure_airport_iata=context.user_data.get('departure_airport_iata'),
            arrival_airport_iata=context.user_data.get('arrival_airport_iata'),
            departure_date_str=context.user_data['departure_date'],
            max_price=context.user_data['max_price'], is_one_way=True)
        return await process_and_send_flights(update, context, flights_by_date)
    else:
        if query.message: await query.edit_message_text(text=f"Дата вылета: {formatted_date}")
        await ask_year(query, context, "Выберите год обратного вылета:", callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_year_") #
        return config.SELECTING_FLEX_RETURN_YEAR #

async def flex_return_year_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Аналогично standard_return_year_selected
    query = update.callback_query
    await query.answer()
    selected_return_year = int(query.data.replace(config.CALLBACK_PREFIX_FLEX + "ret_year_", "")) #
    departure_year = context.user_data.get('departure_year')
    if selected_return_year < departure_year: # Проверка
        await query.edit_message_text(f"Год возврата ({selected_return_year}) не может быть раньше года вылета ({departure_year}).")
        await ask_year(query, context, "Выберите год обратного вылета:", callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_year_") #
        return config.SELECTING_FLEX_RETURN_YEAR #
    context.user_data['return_year'] = selected_return_year
    departure_month = context.user_data.get('departure_month')
    await ask_month(update, context, selected_return_year, f"Год обратного вылета: {selected_return_year}. Выберите месяц:",
                  callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_month_", #
                  departure_year_for_comparison=departure_year,
                  departure_month_for_comparison=departure_month)
    return config.SELECTING_FLEX_RETURN_MONTH #

async def flex_return_month_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Аналогично standard_return_month_selected
    query = update.callback_query
    await query.answer()
    selected_return_month = int(query.data.replace(config.CALLBACK_PREFIX_FLEX + "ret_month_", "")) #
    return_year, dep_year, dep_month = context.user_data['return_year'], context.user_data['departure_year'], context.user_data['departure_month']
    if return_year == dep_year and selected_return_month < dep_month: # Проверка
        await query.edit_message_text(f"Месяц возврата не может быть раньше месяца вылета в том же году.")
        await ask_month(update, context, return_year, "Выберите месяц:", callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_month_", #
                        departure_year_for_comparison=dep_year, departure_month_for_comparison=dep_month)
        return config.SELECTING_FLEX_RETURN_MONTH #
    context.user_data['return_month'] = selected_return_month
    # ... (остальное)
    month_name = config.RUSSIAN_MONTHS.get(selected_return_month, "") #
    context.user_data['return_month_name'] = month_name
    await ask_date_range(update, context, return_year, selected_return_month, f"Выбран: {month_name} {return_year}. Выберите диапазон дат:", callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_range_") #
    return config.SELECTING_FLEX_RETURN_DATE_RANGE #


async def flex_return_date_range_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Аналогично standard_return_date_range_selected
    query = update.callback_query
    await query.answer()
    selected_range_str = query.data.replace(config.CALLBACK_PREFIX_FLEX + "ret_range_", "") #
    # ... (логика start_day, end_day)
    try: start_day, end_day = map(int, selected_range_str.split('-'))
    except ValueError: # ... обработка ошибки ...
        await query.edit_message_text("Неверный диапазон")
        return config.SELECTING_FLEX_RETURN_DATE_RANGE # Пример #
    context.user_data['return_date_range_str'] = selected_range_str
    year, month = context.user_data['return_year'], context.user_data['return_month']
    departure_date_str = context.user_data.get('departure_date')
    min_date_for_return = helpers.validate_date_format(departure_date_str) if departure_date_str else None #
    if departure_date_str and not min_date_for_return:
        logger.error("Flex return: departure_date parsing failed.") # Обработка ошибки
        await query.edit_message_text("Ошибка даты вылета. Начните заново.")
        return ConversationHandler.END
    await ask_specific_date(update, context, year, month, start_day, end_day,
                            f"Диапазон: {selected_range_str}. Выберите дату:",
                            callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_date_", #
                            min_allowed_date_for_comparison=min_date_for_return)
    return config.SELECTING_FLEX_RETURN_DATE #

async def flex_return_date_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Аналогично standard_return_date_selected
    query = update.callback_query
    await query.answer()
    selected_date_str = query.data.replace(config.CALLBACK_PREFIX_FLEX + "ret_date_", "") #
    return_date_obj = helpers.validate_date_format(selected_date_str) #
    departure_date_obj = helpers.validate_date_format(context.user_data.get('departure_date')) #
    if not return_date_obj or not departure_date_obj or return_date_obj < departure_date_obj:
        await query.edit_message_text("Некорректная дата возвращения или она раньше даты вылета. Попробуйте снова.")
        # ... (логика повторного запроса)
        year, month = context.user_data['return_year'], context.user_data['return_month']
        s_range = context.user_data.get('return_date_range_str', "1-10")
        try: start_day, end_day = map(int, s_range.split('-'))
        except: start_day, end_day = 1,10
        await ask_specific_date(update, context, year, month, start_day, end_day, "Выберите дату:",
                                callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_date_", #
                                min_allowed_date_for_comparison=departure_date_obj)
        return config.SELECTING_FLEX_RETURN_DATE #
    context.user_data['return_date'] = selected_date_str
    formatted_date = return_date_obj.strftime('%d-%m-%Y')
    if query.message: await query.edit_message_text(text=f"Дата обратного вылета: {formatted_date}")
    await context.bot.send_message(chat_id=update.effective_chat.id, text=config.MSG_SEARCHING_FLIGHTS, reply_markup=ReplyKeyboardRemove()) #
    flights_by_date = await flight_api.find_flights_with_fallback( #
        departure_airport_iata=context.user_data.get('departure_airport_iata'),
        arrival_airport_iata=context.user_data.get('arrival_airport_iata'),
        departure_date_str=context.user_data['departure_date'],
        max_price=context.user_data['max_price'],
        return_date_str=context.user_data['return_date'], is_one_way=False)
    return await process_and_send_flights(update, context, flights_by_date)

async def handle_search_other_airports_decision(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == config.CALLBACK_YES_OTHER_AIRPORTS: #
        # ... (логика поиска из других аэропортов, без изменений здесь)
        departure_country = context.user_data.get('departure_country')
        original_departure_iata = context.user_data.get('departure_airport_iata')
        if not departure_country or not original_departure_iata: # defensive
            await query.edit_message_text(text="Не удалось получить данные для поиска. Начните новый поиск.")
            return ConversationHandler.END
        await query.edit_message_text(text=f"Ищу рейсы из других аэропортов в {departure_country}...")
        # ... (остальная логика)
        all_airports_in_country = config.COUNTRIES_DATA.get(departure_country, {}) #
        alternative_airports = { city: iata for city, iata in all_airports_in_country.items() if iata != original_departure_iata }
        if not alternative_airports:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"В стране {departure_country} нет других аэропортов.")
            # ... (предложение нового поиска)
            return ConversationHandler.END
        # --- Начало добавленной логики для реального поиска по альтернативным аэропортам ---
        found_alternative_flights = False
        all_alternative_flights_by_date = defaultdict(list)

        original_search_params = {
            "arrival_airport_iata": context.user_data.get('arrival_airport_iata'),
            "departure_date_str": context.user_data.get('departure_date'),
            "max_price": context.user_data['max_price'],
            "return_date_str": context.user_data.get('return_date'),
            "is_one_way": context.user_data.get('flight_type_one_way', True)
        }

        for city, iata_code in alternative_airports.items():
            logger.info(f"Поиск из альтернативного аэропорта: {city} ({iata_code})")
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Ищу из {city} ({iata_code})...")
            flights_from_alt_airport_by_date = await flight_api.find_flights_with_fallback( #
                departure_airport_iata=iata_code,
                **original_search_params
            )
            if flights_from_alt_airport_by_date:
                found_alternative_flights = True
                for date_str, flights_list in flights_from_alt_airport_by_date.items():
                    all_alternative_flights_by_date[f"{city} ({iata_code}) - {date_str}"].extend(flights_list) # Добавляем префикс с городом

        if found_alternative_flights:
            # Важно: process_and_send_flights может снова предложить поиск из других аэропортов,
            # если ничего не найдет. Чтобы избежать цикла, мы передаем новый user_data или флаг.
            # Но проще сейчас просто вывести и завершить.
            # Для корректного отображения, возможно, потребуется адаптация process_and_send_flights
            # или отдельная функция форматирования для этого случая.
            # Пока просто выведем через process_and_send_flights, осознавая возможные артефакты с предложением снова.
            # Или, лучше, не вызывать process_and_send_flights, а сформировать сообщение здесь.
            
            # --- Формирование сообщения об альтернативных рейсах ---
            alt_flights_message_parts = [f"Найдены рейсы из других аэропортов в {departure_country}:\n"]
            for source_and_date, flights_on_date in all_alternative_flights_by_date.items():
                date_obj = datetime.strptime(source_and_date.split(" - ")[-1], "%Y-%m-%d")
                formatted_date_header = f"\n--- ✈️ Вылет из {source_and_date.split(' - ')[0]}, 📅 *{date_obj.strftime('%d %B %Y (%A)')}* ---\n"
                alt_flights_message_parts.append(formatted_date_header)
                for i, flight in enumerate(flights_on_date):
                    if i < config.FLIGHTS_CHUNK_SIZE: #
                        alt_flights_message_parts.append(helpers.format_flight_details(flight)) #
                    else:
                        alt_flights_message_parts.append(f"...и еще {len(flights_on_date) - i} рейс(ов) на эту дату из {source_and_date.split(' - ')[0]}.\n")
                        break
                if not alt_flights_message_parts[-1].endswith("рейс(ов) на эту дату.\n"):
                    alt_flights_message_parts.append("\n")
            
            full_alt_message = "".join(alt_flights_message_parts)
            max_length = 4096
            for i in range(0, len(full_alt_message), max_length):
                await context.bot.send_message(chat_id=update.effective_chat.id, text=full_alt_message[i:i+max_length], parse_mode='Markdown')
            
            await context.bot.send_message(
                chat_id=update.effective_chat.id, text="Что дальше?",
                reply_markup=keyboards.get_yes_no_keyboard( #
                    yes_callback="prompt_new_search_type", no_callback="end_search_session",
                    yes_text="✅ Начать новый поиск", no_text="❌ Закончить"
                )
            )
            context.user_data.clear() # Очищаем user_data после завершения этого поиска
            return ConversationHandler.END
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Из других аэропортов в {departure_country} также ничего не найдено.")
        # --- Конец добавленной логики ---

        await context.bot.send_message(
            chat_id=update.effective_chat.id, text="Что дальше?",
            reply_markup=keyboards.get_yes_no_keyboard( #
                yes_callback="prompt_new_search_type", no_callback="end_search_session",
                yes_text="✅ Начать новый поиск", no_text="❌ Закончить"
            )
        )
        context.user_data.clear()
        return ConversationHandler.END


    elif query.data == config.CALLBACK_NO_OTHER_AIRPORTS: #
        await query.edit_message_text(text="Понял. Поиск из других аэропортов отменен.")
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text="Что дальше?",
            reply_markup=keyboards.get_yes_no_keyboard( #
                yes_callback="prompt_new_search_type", no_callback="end_search_session",
                yes_text="✅ Начать новый поиск", no_text="❌ Закончить"
            ))
        context.user_data.clear()
        return ConversationHandler.END
    return config.ASK_SEARCH_OTHER_AIRPORTS #

async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message_to_send = config.MSG_CANCELLED #
    reply_markup_to_send = ReplyKeyboardRemove()
    chat_id_to_send = update.effective_chat.id
    if update.callback_query:
        await update.callback_query.answer()
        if update.callback_query.message:
            try: await update.callback_query.edit_message_text(text=message_to_send)
            except Exception:
                if chat_id_to_send: await context.bot.send_message(chat_id=chat_id_to_send, text=message_to_send, reply_markup=reply_markup_to_send)
        elif chat_id_to_send: await context.bot.send_message(chat_id=chat_id_to_send, text=message_to_send, reply_markup=reply_markup_to_send)
    elif update.message and chat_id_to_send:
        await update.message.reply_text(message_to_send, reply_markup=reply_markup_to_send)
    context.user_data.clear()
    return ConversationHandler.END

async def error_handler_conv(update: Update | None, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    logger.error(f"Ошибка в ConversationHandler: {context.error}", exc_info=context.error)
    chat_id_to_send_error = None
    if update and hasattr(update, 'effective_chat') and update.effective_chat:
        chat_id_to_send_error = update.effective_chat.id
    if chat_id_to_send_error:
        try:
            await context.bot.send_message(
                chat_id=chat_id_to_send_error,
                text=config.MSG_ERROR_OCCURRED + " Пожалуйста, попробуйте начать заново с /start.", #
                reply_markup=ReplyKeyboardRemove()
            )
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение об ошибке пользователю: {e}")
    if context.user_data: context.user_data.clear()
    return ConversationHandler.END

def create_conversation_handler() -> ConversationHandler:
    std_dep_year_pattern = f"^{config.CALLBACK_PREFIX_STANDARD}dep_year_" #
    flex_dep_year_pattern = f"^{config.CALLBACK_PREFIX_FLEX}dep_year_" #
    flex_ret_year_pattern = f"^{config.CALLBACK_PREFIX_FLEX}ret_year_" #
    flex_ret_date_pattern = f"^{config.CALLBACK_PREFIX_FLEX}ret_date_" #

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start_command),
            CallbackQueryHandler(start_search_callback, pattern='^start_standard_search$|^start_flex_search$'),
            CallbackQueryHandler(start_flex_anywhere_callback, pattern='^start_flex_anywhere$')
        ],
        states={
            config.SELECTING_FLIGHT_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, standard_flight_type)], #
            config.SELECTING_DEPARTURE_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, standard_departure_country)], #
            config.SELECTING_DEPARTURE_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, standard_departure_city)], #
            config.SELECTING_DEPARTURE_YEAR: [CallbackQueryHandler(standard_departure_year_selected, pattern=std_dep_year_pattern)], #
            config.SELECTING_DEPARTURE_MONTH: [CallbackQueryHandler(standard_departure_month_selected, pattern=f"^{config.CALLBACK_PREFIX_STANDARD}dep_month_")], #
            config.SELECTING_DEPARTURE_DATE_RANGE: [CallbackQueryHandler(standard_departure_date_range_selected, pattern=f"^{config.CALLBACK_PREFIX_STANDARD}dep_range_")], #
            config.SELECTING_DEPARTURE_DATE: [CallbackQueryHandler(standard_departure_date_selected, pattern=f"^{config.CALLBACK_PREFIX_STANDARD}dep_date_")], #
            config.SELECTING_ARRIVAL_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, standard_arrival_country)], #
            config.SELECTING_ARRIVAL_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, standard_arrival_city)], #
            config.SELECTING_RETURN_YEAR: [CallbackQueryHandler(standard_return_year_selected, pattern=f"^{config.CALLBACK_PREFIX_STANDARD}ret_year_")], #
            config.SELECTING_RETURN_MONTH: [CallbackQueryHandler(standard_return_month_selected, pattern=f"^{config.CALLBACK_PREFIX_STANDARD}ret_month_")], #
            config.SELECTING_RETURN_DATE_RANGE: [CallbackQueryHandler(standard_return_date_range_selected, pattern=f"^{config.CALLBACK_PREFIX_STANDARD}ret_range_")], #
            config.SELECTING_RETURN_DATE: [CallbackQueryHandler(standard_return_date_selected, pattern=f"^{config.CALLBACK_PREFIX_STANDARD}ret_date_")], #
            config.SELECTING_MAX_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, standard_max_price)], #

            config.SELECTING_FLEX_FLIGHT_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, flex_flight_type)], #
            config.SELECTING_FLEX_MAX_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, flex_max_price)], #
            config.ASK_FLEX_DEPARTURE_AIRPORT: [CallbackQueryHandler(flex_ask_departure_airport, pattern=f"^{config.CALLBACK_PREFIX_FLEX}ask_dep_")], #
            config.SELECTING_FLEX_DEPARTURE_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, flex_departure_country)], #
            config.SELECTING_FLEX_DEPARTURE_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, flex_departure_city)], #
            config.ASK_FLEX_ARRIVAL_AIRPORT: [CallbackQueryHandler(flex_ask_arrival_airport, pattern=f"^{config.CALLBACK_PREFIX_FLEX}ask_arr_")], #
            config.SELECTING_FLEX_ARRIVAL_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, flex_arrival_country)], #
            config.SELECTING_FLEX_ARRIVAL_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, flex_arrival_city)], #
            config.ASK_FLEX_DATES: [CallbackQueryHandler(flex_ask_dates, pattern=f"^(?:{config.CALLBACK_PREFIX_FLEX}ask_dates_yes|{config.CALLBACK_NO_SPECIFIC_DATES})$")], #
            config.SELECTING_FLEX_DEPARTURE_YEAR: [CallbackQueryHandler(flex_departure_year_selected, pattern=flex_dep_year_pattern)], #
            config.SELECTING_FLEX_DEPARTURE_MONTH: [CallbackQueryHandler(flex_departure_month_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}dep_month_")], #
            config.SELECTING_FLEX_DEPARTURE_DATE_RANGE: [CallbackQueryHandler(flex_departure_date_range_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}dep_range_")], #
            config.SELECTING_FLEX_DEPARTURE_DATE: [CallbackQueryHandler(flex_departure_date_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}dep_date_")], #
            config.SELECTING_FLEX_RETURN_YEAR: [CallbackQueryHandler(flex_return_year_selected, pattern=flex_ret_year_pattern)], #
            config.SELECTING_FLEX_RETURN_MONTH: [CallbackQueryHandler(flex_return_month_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}ret_month_")], #
            config.SELECTING_FLEX_RETURN_DATE_RANGE: [CallbackQueryHandler(flex_return_date_range_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}ret_range_")], #
            config.SELECTING_FLEX_RETURN_DATE: [CallbackQueryHandler(flex_return_date_selected, pattern=flex_ret_date_pattern)], #

            config.ASK_SEARCH_OTHER_AIRPORTS: [ #
                CallbackQueryHandler(handle_search_other_airports_decision, pattern=f"^{config.CALLBACK_YES_OTHER_AIRPORTS}$|^{config.CALLBACK_NO_OTHER_AIRPORTS}$") #
            ],
        },
        fallbacks=[
            CommandHandler('cancel', cancel_handler),
            CallbackQueryHandler(lambda u, c: u.callback_query.answer("Этот месяц уже прошёл или недоступен для выбора.", show_alert=True), pattern="^ignore_past_month$"),
            CallbackQueryHandler(lambda u, c: u.callback_query.answer("Эта дата уже прошла или недоступна для выбора.", show_alert=True), pattern="^ignore_past_day$"),
            CallbackQueryHandler(lambda u, c: u.callback_query.answer("Нет доступных месяцев для выбора.", show_alert=True), pattern="^no_valid_months_error$"),
            CallbackQueryHandler(lambda u, c: u.callback_query.answer("Нет доступных дат для выбора.", show_alert=True), pattern="^no_valid_dates_error$"),
        ],
        map_to_parent={},
        # per_message=False, # Раскомментируйте, если это необходимо для логики вашего ConversationHandler
        # per_user=True, # По умолчанию True, можно явно указать
        # per_chat=True, # По умолчанию True
        # allow_reentry=False # По умолчанию False, установите True, если команда /start должна прерывать и перезапускать диалог
    )
    # Добавление обработчика ошибок именно для этого ConversationHandler
    conv_handler.error_handler = error_handler_conv
    return conv_handler