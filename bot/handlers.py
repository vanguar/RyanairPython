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
from collections import defaultdict
from telegram.helpers import escape_markdown
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, Union # Добавляем для аннотаций

# Импортируем обновленный config с PriceChoice и FLOW_* константами
from . import config, keyboards, helpers, flight_api
from .config import PriceChoice # Импортируем новый тип

logger = logging.getLogger(__name__)

# bot/handlers.py
# ... (другие импорты и определения функций выше) ...

async def launch_flight_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Централизованно запускает поиск рейсов API, обрабатывает результаты 
    и передает их функции отображения.

    Эта функция является ключевой точкой выполнения поиска после того, как все
    необходимые параметры (маршрут, даты, ценовые предпочтения) собраны.

    В зависимости от 'price_preference_choice' в context.user_data:
    - Если CALLBACK_PRICE_LOWEST: фильтрует все найденные рейсы, оставляя только самые дешевые.
    - Для CALLBACK_PRICE_ALL или CALLBACK_PRICE_CUSTOM (где max_price уже учтен в API запросе):
      отображает все полученные рейсы.

    Возвращает:
        Результат вызова `process_and_send_flights`, который обычно является
        `ConversationHandler.END` после отображения рейсов или предложения нового поиска.
        Может также вернуть `config.ASK_SEARCH_OTHER_AIRPORTS`, если рейсы не найдены
        и предложен поиск из других аэропортов.
        В случае критической ошибки при поиске или обработке, также возвращает
        `ConversationHandler.END` после уведомления пользователя.
    """
    effective_chat_id = update.effective_chat.id
    try:
        # Получение параметров из user_data
        dep_iata: Union[str, None] = context.user_data.get('departure_airport_iata')
        arr_iata: Union[str, None] = context.user_data.get('arrival_airport_iata')
        dep_date_str: Union[str, None] = context.user_data.get('departure_date')
        ret_date_str: Union[str, None] = context.user_data.get('return_date')
        user_max_price: Union[Decimal, None] = context.user_data.get('max_price')
        price_preference: Union[PriceChoice, None] = context.user_data.get('price_preference_choice')
        is_one_way: bool = context.user_data.get('flight_type_one_way', True)
        current_flow: Union[str, None] = context.user_data.get('current_search_flow')


        # === Логирование параметров перед вызовом API (предложение AI-B) ===
        logger.info("=== Запуск launch_flight_search ===")
        logger.info(
            "Параметры: price_pref=%s, user_max_price=%s, dep_iata=%s, arr_iata=%s, dep_date=%s, ret_date=%s, one_way=%s, current_flow=%s",
            price_preference, user_max_price, dep_iata, arr_iata, dep_date_str, ret_date_str, is_one_way, current_flow
        )
        # logger.info(f"Полный user_data (часть): {dict(list(context.user_data.items())[:10])}") # Опционально для более детального лога
        # ====================================================================

        if not dep_iata:
            msg = "Ошибка: Аэропорт вылета не был указан. Пожалуйста, начните поиск заново: /start"
            if update.callback_query and update.callback_query.message: 
                try: await update.callback_query.edit_message_text(msg)
                except Exception: await context.bot.send_message(effective_chat_id, msg)
            elif update.message:
                await update.message.reply_text(msg)
            else:
                await context.bot.send_message(effective_chat_id, msg)
            return ConversationHandler.END

        await context.bot.send_message(chat_id=effective_chat_id, text=config.MSG_SEARCHING_FLIGHTS)

        all_flights_data: Dict[str, List[Any]] = await flight_api.find_flights_with_fallback(
            departure_airport_iata=dep_iata,
            arrival_airport_iata=arr_iata,
            departure_date_str=dep_date_str,
            max_price=user_max_price, # Это значение user_max_price
            return_date_str=ret_date_str,
            is_one_way=is_one_way
        )
        
        # Логирование результата от API
        logger.info(f"API flight_api.find_flights_with_fallback вернул: {'Данные есть (ключи: ' + str(list(all_flights_data.keys())) + ')' if isinstance(all_flights_data, dict) and all_flights_data else 'Пустой результат или не словарь'}")
        if not isinstance(all_flights_data, dict): # Дополнительная проверка типа
             logger.warning(f"find_flights_with_fallback вернул не словарь: {type(all_flights_data)}")
             all_flights_data = {} # Приводим к ожидаемому типу для дальнейшей обработки


        final_flights_to_show: Dict[str, List[Any]]
        if price_preference == config.CALLBACK_PRICE_LOWEST:
            final_flights_to_show = helpers.filter_cheapest_flights(all_flights_data)
            logger.info(f"После filter_cheapest_flights для 'lowest': {'Данные есть' if final_flights_to_show else 'Пусто'}")
        else: 
            final_flights_to_show = all_flights_data
            logger.info(f"Для '{price_preference}': используются все полученные рейсы ({'Данные есть' if final_flights_to_show else 'Пусто'})")
        
        return await process_and_send_flights(update, context, final_flights_to_show)

    except Exception as e:
        logger.error(f"Ошибка в launch_flight_search: {e}", exc_info=True)
        error_msg = config.MSG_ERROR_OCCURRED + " Пожалуйста, попробуйте /start"
        target_chat_id = update.effective_chat.id
        if update.callback_query:
            await update.callback_query.answer() 
            try: 
                if update.callback_query.message: 
                    await update.callback_query.edit_message_text(text=error_msg)
                else: 
                    await context.bot.send_message(target_chat_id, error_msg)
            except Exception: 
                 await context.bot.send_message(target_chat_id, error_msg)
        elif update.message:
             await update.message.reply_text(error_msg)
        else:
             if target_chat_id:
                await context.bot.send_message(target_chat_id, error_msg)
             else:
                logger.error("Не удалось определить chat_id для отправки сообщения об ошибке в launch_flight_search.")
        return ConversationHandler.END

# Убедитесь, что эта функция `launch_flight_search` находится ВЫШЕ
# функций, которые ее вызывают, например:
# handle_price_option_selected, enter_custom_price_handler,
# flex_departure_date_selected, flex_return_date_selected, flex_ask_dates

# async def handle_price_option_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
# ... вызывает launch_flight_search ...

# async def enter_custom_price_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
# ... вызывает launch_flight_search ...

# и так далее для других функций, если они ее вызывают.

# --- Вспомогательные функции для отображения клавиатур (если они были в handlers.py) ---
# Если ask_year, ask_month, ask_date_range, ask_specific_date были здесь,
# и они не менялись, их можно оставить.
# Для примера, я оставлю их здесь, предполагая, что они нужны и не были в helpers.py

async def ask_year(message_or_update: Union[Update, Any], context: ContextTypes.DEFAULT_TYPE, message_text: str, callback_prefix: str = ""): # type: ignore
    target_message_object = None
    if hasattr(message_or_update, 'callback_query') and message_or_update.callback_query:
        await message_or_update.callback_query.edit_message_text(
            text=message_text,
            reply_markup=keyboards.generate_year_buttons(callback_prefix)
        )
        return
    elif hasattr(message_or_update, 'message') and message_or_update.message:
        target_message_object = message_or_update.message
    elif hasattr(message_or_update, 'reply_text'): # Fallback for direct message object
        target_message_object = message_or_update

    if target_message_object and hasattr(target_message_object, 'reply_text'):
        await target_message_object.reply_text(
            message_text,
            reply_markup=keyboards.generate_year_buttons(callback_prefix)
        )
    elif hasattr(message_or_update, 'effective_chat') and message_or_update.effective_chat:
         await context.bot.send_message(
            chat_id=message_or_update.effective_chat.id,
            text=message_text,
            reply_markup=keyboards.generate_year_buttons(callback_prefix)
        )
    else:
        logger.warning("ask_year: не удалось определить объект для ответа.")

async def ask_month(update: Update, context: ContextTypes.DEFAULT_TYPE,
                    year_for_months: int, message_text: str, callback_prefix: str = "",
                    departure_year_for_comparison: Union[int, None] = None,
                    departure_month_for_comparison: Union[int, None] = None):
    logger.info(f"ask_month: Год: {year_for_months}, Префикс: {callback_prefix}")
    if not update.callback_query:
        logger.error("ask_month был вызван без callback_query.")
        return
    try:
        await update.callback_query.edit_message_text(
            text=message_text,
            reply_markup=keyboards.generate_month_buttons(
                callback_prefix=callback_prefix,
                year_for_months=year_for_months,
                min_departure_month=departure_month_for_comparison,
                departure_year_for_comparison=departure_year_for_comparison
            )
        )
    except TypeError as e:
        logger.error(f"ask_month: TypeError при вызове generate_month_buttons: {e}")
        await update.callback_query.edit_message_text("Произошла ошибка при отображении месяцев. Попробуйте /start")
    except Exception as e:
        logger.error(f"ask_month: Непредвиденная ошибка: {e}", exc_info=True)
        await update.callback_query.edit_message_text("Произошла внутренняя ошибка. Попробуйте /start")


async def ask_date_range(update: Update, context: ContextTypes.DEFAULT_TYPE, year: int, month: int, message_text: str, callback_prefix: str = ""):
    if not update.callback_query:
        logger.error("ask_date_range был вызван без callback_query.")
        return
    await update.callback_query.edit_message_text(
        text=message_text,
        reply_markup=keyboards.generate_date_range_buttons(year, month, callback_prefix)
    )

async def ask_specific_date(update: Update, context: ContextTypes.DEFAULT_TYPE,
                            year: int, month: int, range_start: int, range_end: int,
                            message_text: str, callback_prefix: str = "",
                            min_allowed_date_for_comparison: Union[datetime, None] = None):
    if not update.callback_query:
        logger.error("ask_specific_date был вызван без callback_query.")
        return
    await update.callback_query.edit_message_text(
        text=message_text,
        reply_markup=keyboards.generate_specific_date_buttons(
            year, month, range_start, range_end,
            callback_prefix=callback_prefix,
            min_allowed_date=min_allowed_date_for_comparison
        )
    )
# --- Конец вспомогательных функций для клавиатур ---

async def process_and_send_flights(update: Update, context: ContextTypes.DEFAULT_TYPE, flights_by_date: Dict[str, list]) -> int: # type: ignore
    """
    Форматирует и отправляет найденные рейсы пользователю.
    Завершает диалог или предлагает альтернативные действия.
    """
    chat_id = update.effective_chat.id
    context.user_data.pop('remaining_flights_to_show', None) # Очистка старых данных для постраничного вывода, если он был

    if not flights_by_date:
        await context.bot.send_message(chat_id=chat_id, text=config.MSG_NO_FLIGHTS_FOUND)
        dep_country = context.user_data.get('departure_country')
        dep_airport_iata = context.user_data.get('departure_airport_iata')

        # Предложение поиска из других аэропортов
        if dep_country and dep_airport_iata and \
           config.COUNTRIES_DATA.get(dep_country) and \
           len(config.COUNTRIES_DATA[dep_country]) > 1 and \
           not context.user_data.get("_already_searched_alternatives", False):
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"Хотите поискать вылеты из других аэропортов в стране {dep_country} по этому же направлению и датам?",
                reply_markup=keyboards.get_search_other_airports_keyboard(dep_country)
            )
            return config.ASK_SEARCH_OTHER_AIRPORTS

        await context.bot.send_message(
            chat_id=chat_id, text="Что дальше?",
            reply_markup=keyboards.get_yes_no_keyboard(
                yes_callback="prompt_new_search_type", no_callback="end_search_session",
                yes_text="✅ Начать новый поиск", no_text="❌ Закончить"
            )
        )
        return ConversationHandler.END

    await context.bot.send_message(chat_id=chat_id, text=config.MSG_FLIGHTS_FOUND_SEE_BELOW)

    flights_message_parts = []
    sorted_dates = sorted(flights_by_date.keys())

    for flight_date_str in sorted_dates:
        flights_on_this_date = flights_by_date[flight_date_str]
        if not flights_on_this_date:
            continue
        try:
            date_obj = datetime.strptime(flight_date_str, "%Y-%m-%d")
            formatted_date_header = f"\n--- 📅 *{date_obj.strftime('%d %B %Y (%A)')}* ---\n"
        except ValueError: 
            formatted_date_header = f"\n--- 📅 *{flight_date_str}* ---\n"
        flights_message_parts.append(formatted_date_header)

        for flight in flights_on_this_date:
            formatted_flight = helpers.format_flight_details(flight)
            flights_message_parts.append(formatted_flight)
        flights_message_parts.append("\n") # Пустая строка после рейсов за одну дату

    if flights_message_parts:
        full_text = "".join(flights_message_parts)
        
        # Экранирование Markdown V2 символов
        # Важно: ryanair-py может возвращать строки с дефисами, которые Markdown V2 интерпретирует.
        # Простой escape_markdown может быть недостаточен, если в названиях городов/аэропортов есть спецсимволы.
        # Для простоты используем стандартный escape_markdown.
        escaped_full_text = escape_markdown(full_text, version=2)
        
        max_telegram_message_length = 4096 
        for i in range(0, len(escaped_full_text), max_telegram_message_length):
            chunk = escaped_full_text[i:i + max_telegram_message_length]
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=chunk, 
                    parse_mode='MarkdownV2'
                )
            except Exception as e_md:
                logger.warning(f"Ошибка при отправке чанка рейсов с MarkdownV2: {e_md}. Попытка отправить как простой текст (без parse_mode).")
                try:
                    # Отправляем УЖЕ ЭКРАНИРОВАННЫЙ чанк, но без parse_mode.
                    # Пользователь может увидеть экранирующие символы, но бот не упадет.
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=chunk 
                    )
                except Exception as fallback_e:
                    logger.error(f"Не удалось отправить чанк даже как простой текст (после ошибки MarkdownV2): {fallback_e}")
                    await context.bot.send_message(chat_id=chat_id, text="Произошла ошибка при отображении части результатов.")
    
    await context.bot.send_message(
        chat_id=chat_id, text="Что дальше?",
        reply_markup=keyboards.get_yes_no_keyboard(
            yes_callback="prompt_new_search_type", no_callback="end_search_session",
            yes_text="✅ Начать новый поиск", no_text="❌ Закончить"
        )
    )
    return ConversationHandler.END

async def prompt_new_search_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    if query.message:
      await query.edit_message_text(text=config.MSG_WELCOME, reply_markup=keyboards.get_main_menu_keyboard())
    elif update.effective_chat:
      await context.bot.send_message(chat_id=update.effective_chat.id, text=config.MSG_WELCOME, reply_markup=keyboards.get_main_menu_keyboard())

async def end_search_session_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    if query.message:
      await query.edit_message_text(text="Поиск завершен. Если понадоблюсь, вы знаете, как меня найти! /start")
    elif update.effective_chat:
      await context.bot.send_message(chat_id=update.effective_chat.id, text="Поиск завершен. Если понадоблюсь, вы знаете, как меня найти! /start")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    welcome_text = escape_markdown(config.MSG_WELCOME, version=2)
    main_menu_keyboard = keyboards.get_main_menu_keyboard()

    if update.message:
        await update.message.reply_text(welcome_text, reply_markup=main_menu_keyboard)
    elif update.callback_query:
        await update.callback_query.answer()
        if update.callback_query.message:
            try:
                await update.callback_query.edit_message_text(welcome_text, reply_markup=main_menu_keyboard)
            except Exception as e: # Если сообщение не может быть отредактировано
                logger.warning(f"Не удалось отредактировать сообщение в start_command: {e}")
                await context.bot.send_message(chat_id=update.effective_chat.id, text=welcome_text, reply_markup=main_menu_keyboard)
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=welcome_text, reply_markup=main_menu_keyboard)

async def start_search_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data.clear() 
    
    if query.message: # Попытаемся отредактировать сообщение, если оно есть
        try:
            if query.data == "start_standard_search":
                await query.edit_message_text(text="Выбран стандартный поиск.")
            elif query.data == "start_flex_search":
                await query.edit_message_text(text="Выбран гибкий поиск.")
            # Для start_flex_anywhere редактирование происходит в самой функции
        except Exception as e:
            logger.warning(f"Не удалось отредактировать сообщение в start_search_callback: {e}")
            # Если не удалось отредактировать, просто продолжим отправкой нового сообщения ниже

    if query.data == "start_standard_search":
        await context.bot.send_message(chat_id=update.effective_chat.id, text=config.MSG_FLIGHT_TYPE_PROMPT, reply_markup=keyboards.get_flight_type_reply_keyboard())
        return config.S_SELECTING_FLIGHT_TYPE # Используем S_ префикс для стандартного
    elif query.data == "start_flex_search":
        await context.bot.send_message(chat_id=update.effective_chat.id, text=config.MSG_FLIGHT_TYPE_PROMPT, reply_markup=keyboards.get_flight_type_reply_keyboard())
        return config.SELECTING_FLEX_FLIGHT_TYPE
    elif query.data == "start_flex_anywhere":
        return await start_flex_anywhere_callback(update, context)
    return ConversationHandler.END

async def start_flex_anywhere_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        query = update.callback_query
        # await query.answer() # Уже вызван в start_search_callback, если переход оттуда
        if query.message:
            try: await query.edit_message_text(text="Выбран поиск \"Куда угодно\".")
            except Exception as e: logger.warning(f"Не удалось отредактировать сообщение в start_flex_anywhere_callback: {e}")
    else: 
        # Этот else блок может быть не достижим, если start_flex_anywhere_callback вызывается только из start_search_callback
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Выбран поиск \"Куда угодно\".")

    context.user_data.clear()
    context.user_data['arrival_airport_iata'] = None 
    context.user_data['departure_date'] = None    
    context.user_data['return_date'] = None       
    context.user_data['current_search_flow'] = config.FLOW_FLEX # Для "куда угодно" это гибкий поиск

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=config.MSG_FLIGHT_TYPE_PROMPT,
        reply_markup=keyboards.get_flight_type_reply_keyboard()
    )
    return config.SELECTING_FLEX_FLIGHT_TYPE # Переход к выбору типа рейса в гибком потоке

# --- СТАНДАРТНЫЙ ПОИСК ---
async def standard_flight_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_input = update.message.text
    if user_input not in ['1', '2']:
        await update.message.reply_text("Пожалуйста, выберите 1 или 2.", reply_markup=keyboards.get_flight_type_reply_keyboard())
        return config.S_SELECTING_FLIGHT_TYPE
    context.user_data['flight_type_one_way'] = (user_input == '1')
    # await ask_departure_country(update, context, "Выберите страну вылета:") # Если это хелпер
    await update.message.reply_text("Выберите страну вылета:", reply_markup=keyboards.get_country_reply_keyboard())
    return config.S_SELECTING_DEPARTURE_COUNTRY

async def standard_departure_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    country = update.message.text
    if country not in config.COUNTRIES_DATA:
        await update.message.reply_text("Страна не найдена! Пожалуйста, выберите из списка.", reply_markup=keyboards.get_country_reply_keyboard())
        return config.S_SELECTING_DEPARTURE_COUNTRY
    context.user_data['departure_country'] = country
    # await ask_departure_city(update, context, country) # Если это хелпер
    await update.message.reply_text("Выберите город вылета:", reply_markup=keyboards.get_city_reply_keyboard(country))
    return config.S_SELECTING_DEPARTURE_CITY

async def standard_departure_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    city = update.message.text
    country = context.user_data.get('departure_country')
    if not country: # На случай если что-то пошло не так
        await update.message.reply_text("Ошибка: страна вылета не определена. Начните заново /start.")
        return ConversationHandler.END
    iata_code = helpers.get_airport_iata(country, city)
    if not iata_code:
        await update.message.reply_text("Город не найден! Пожалуйста, выберите из списка.", reply_markup=keyboards.get_city_reply_keyboard(country))
        return config.S_SELECTING_DEPARTURE_CITY
    
    context.user_data['departure_airport_iata'] = iata_code
    context.user_data['departure_city_name'] = city
    await update.message.reply_text(f"Город вылета: {city}.", reply_markup=ReplyKeyboardRemove())
    
    await ask_year(update, context, "Выберите год вылета:", callback_prefix=config.CALLBACK_PREFIX_STANDARD + "dep_year_")
    return config.S_SELECTING_DEPARTURE_YEAR

async def standard_departure_year_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    selected_year = int(query.data.replace(config.CALLBACK_PREFIX_STANDARD + "dep_year_", "")) 
    context.user_data['departure_year'] = selected_year
    await ask_month(update, context,
                  year_for_months=selected_year,
                  message_text=f"Год вылета: {selected_year}. Выберите месяц:",
                  callback_prefix=config.CALLBACK_PREFIX_STANDARD + "dep_month_")
    return config.S_SELECTING_DEPARTURE_MONTH

async def standard_departure_month_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    try:
        selected_month = int(query.data.replace(config.CALLBACK_PREFIX_STANDARD + "dep_month_", ""))
    except ValueError:
        await query.edit_message_text("Ошибка формата месяца. Попробуйте снова.")
        return config.S_SELECTING_DEPARTURE_YEAR # Возврат к выбору года
        
    year = context.user_data.get('departure_year')
    if not year:
        await query.edit_message_text("Год вылета не найден. Начните /start.")
        return ConversationHandler.END

    # ... (проверка на прошедший месяц, как и ранее) ...
    server_now_datetime = datetime.now() #
    current_month_start_on_server = server_now_datetime.replace(day=1, hour=0, minute=0, second=0, microsecond=0) #
    selected_month_start_by_user = datetime(year, selected_month, 1) #
    if selected_month_start_by_user < current_month_start_on_server: #
        month_name_rus = config.RUSSIAN_MONTHS.get(selected_month, str(selected_month)) #
        await query.edit_message_text(text=f"Выбран прошедший месяц ({month_name_rus} {year}). Пожалуйста, выберите корректный месяц.") #
        await ask_month(update, context, year_for_months=year, message_text=f"Год вылета: {year}. Выберите месяц:", callback_prefix=config.CALLBACK_PREFIX_STANDARD + "dep_month_") #
        return config.S_SELECTING_DEPARTURE_MONTH #

    context.user_data['departure_month'] = selected_month
    month_name = config.RUSSIAN_MONTHS.get(selected_month, str(selected_month))
    await ask_date_range(update, context, year, selected_month,
                       f"Выбран: {month_name} {year}. Выберите диапазон дат:",
                       callback_prefix=config.CALLBACK_PREFIX_STANDARD + "dep_range_")
    return config.S_SELECTING_DEPARTURE_DATE_RANGE

async def standard_departure_date_range_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    selected_range_str = query.data.replace(config.CALLBACK_PREFIX_STANDARD + "dep_range_", "")
    try:
        start_day, end_day = map(int, selected_range_str.split('-'))
    except ValueError:
        await query.edit_message_text("Некорректный диапазон. Выберите снова.")
        # Вернуться к выбору месяца
        year = context.user_data.get('departure_year')
        selected_month = context.user_data.get('departure_month')
        if year and selected_month:
             await ask_month(update, context, year_for_months=year, message_text=f"Год вылета: {year}. Выберите месяц:", callback_prefix=config.CALLBACK_PREFIX_STANDARD + "dep_month_")
             return config.S_SELECTING_DEPARTURE_MONTH
        return ConversationHandler.END # Fallback
        
    context.user_data['departure_date_range_str'] = selected_range_str
    year = context.user_data['departure_year']
    month = context.user_data['departure_month']
    min_date_for_dep = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    await ask_specific_date(update, context, year, month, start_day, end_day,
                            f"Диапазон: {selected_range_str}. Выберите дату:",
                            callback_prefix=config.CALLBACK_PREFIX_STANDARD + "dep_date_",
                            min_allowed_date_for_comparison=min_date_for_dep)
    return config.S_SELECTING_DEPARTURE_DATE

async def standard_departure_date_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    selected_date_str = query.data.replace(config.CALLBACK_PREFIX_STANDARD + "dep_date_", "")
    date_obj = helpers.validate_date_format(selected_date_str)
    min_allowed_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    if not date_obj or date_obj < min_allowed_date :
        await query.edit_message_text("Некорректная дата или дата в прошлом. Попробуйте снова.")
        # ... (код для повторного запроса)
        return config.S_SELECTING_DEPARTURE_DATE

    context.user_data['departure_date'] = selected_date_str 
    await query.edit_message_text(text=f"Дата вылета: {date_obj.strftime('%d-%m-%Y')}")
    # await ask_arrival_country(update, context, "Выберите страну прилёта:") # Если это хелпер
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Выберите страну прилёта:", reply_markup=keyboards.get_country_reply_keyboard())
    return config.S_SELECTING_ARRIVAL_COUNTRY

async def standard_arrival_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    country = update.message.text
    # ... (валидация страны, как раньше) ...
    if country not in config.COUNTRIES_DATA: #
        await update.message.reply_text("Страна не найдена! Пожалуйста, выберите из списка.", reply_markup=keyboards.get_country_reply_keyboard()) #
        return config.S_SELECTING_ARRIVAL_COUNTRY #
    # ... (проверка на единственный аэропорт, совпадающий с вылетом, как раньше)
    departure_airport_iata = context.user_data.get('departure_airport_iata') #
    if departure_airport_iata and country in config.COUNTRIES_DATA and len(config.COUNTRIES_DATA[country]) == 1: #
        single_city_name = list(config.COUNTRIES_DATA[country].keys())[0] #
        single_airport_iata = helpers.get_airport_iata(country, single_city_name) #
        if single_airport_iata == departure_airport_iata: #
            await update.message.reply_text( #
                f"Единственный аэропорт в стране \"{country}\" ({single_city_name}) совпадает с вашим аэропортом вылета. " #
                "Выберите другую страну прилёта." #
            )
            # await ask_arrival_country(update, context, "Выберите другую страну прилёта:") #
            await update.message.reply_text("Выберите другую страну прилёта:", reply_markup=keyboards.get_country_reply_keyboard()) #
            return config.S_SELECTING_ARRIVAL_COUNTRY #

    context.user_data['arrival_country'] = country
    # await ask_arrival_city(update, context, country) # Если это хелпер
    await update.message.reply_text("Выберите город прилёта:", reply_markup=keyboards.get_city_reply_keyboard(country)) #
    return config.S_SELECTING_ARRIVAL_CITY

async def standard_arrival_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    city = update.message.text
    country = context.user_data.get('arrival_country')
    if not country:
        await update.message.reply_text("Ошибка: страна прилёта не определена. Начните заново /start.")
        return ConversationHandler.END
    iata_code = helpers.get_airport_iata(country, city)
    if not iata_code:
        await update.message.reply_text("Город не найден! Пожалуйста, выберите из списка.", reply_markup=keyboards.get_city_reply_keyboard(country))
        return config.S_SELECTING_ARRIVAL_CITY
    if iata_code == context.user_data.get('departure_airport_iata'):
        await update.message.reply_text("Аэропорт прилёта не может совпадать с аэропортом вылета. Выберите другой город.", reply_markup=keyboards.get_city_reply_keyboard(country))
        return config.S_SELECTING_ARRIVAL_CITY
    context.user_data['arrival_airport_iata'] = iata_code
    context.user_data['arrival_city_name'] = city
    
    await update.message.reply_text(f"Город прилёта: {city}.", reply_markup=ReplyKeyboardRemove())
    
    if context.user_data.get('flight_type_one_way', True):
        context.user_data['current_search_flow'] = config.FLOW_STANDARD
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=config.MSG_PRICE_OPTION_PROMPT,
            reply_markup=keyboards.get_price_options_keyboard()
        )
        return config.SELECTING_PRICE_OPTION 
    else: 
        await ask_year(update, context, "Выберите год обратного вылета:", callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_year_")
        return config.S_SELECTING_RETURN_YEAR

async def standard_return_year_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    selected_return_year = int(query.data.replace(config.CALLBACK_PREFIX_STANDARD + "ret_year_", ""))
    departure_year = context.user_data.get('departure_year')
    if not departure_year or selected_return_year < departure_year:
        await query.edit_message_text(text=f"Год возврата ({selected_return_year}) не может быть раньше года вылета ({departure_year}).")
        await ask_year(query, context, "Выберите корректный год обратного вылета:", callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_year_")
        return config.S_SELECTING_RETURN_YEAR

    context.user_data['return_year'] = selected_return_year
    departure_month = context.user_data.get('departure_month')
    min_return_month = 1
    if selected_return_year == departure_year and departure_month:
        min_return_month = departure_month

    await ask_month(update, context,
                  year_for_months=selected_return_year,
                  message_text=f"Год обратного вылета: {selected_return_year}. Выберите месяц:",
                  callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_month_",
                  departure_year_for_comparison=departure_year,
                  departure_month_for_comparison=min_return_month) 
    return config.S_SELECTING_RETURN_MONTH

async def standard_return_month_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    try:
        selected_return_month = int(query.data.replace(config.CALLBACK_PREFIX_STANDARD + "ret_month_", ""))
    except ValueError:
        await query.edit_message_text("Ошибка формата месяца. Попробуйте снова.")
        return config.S_SELECTING_RETURN_YEAR # Возврат к выбору года

    return_year = context.user_data.get('return_year')
    departure_year = context.user_data.get('departure_year')
    departure_month = context.user_data.get('departure_month')

    if not all([return_year, departure_year, departure_month]):
        await query.edit_message_text("Ошибка: не хватает данных о датах. Начните /start.")
        return ConversationHandler.END
    
    if return_year == departure_year and selected_return_month < departure_month:
        # ... (сообщение об ошибке и повторный вызов ask_month)
        await query.edit_message_text("Месяц возврата не может быть раньше месяца вылета. Выберите снова.")
        await ask_month(update, context, return_year, f"Год обратного вылета: {return_year}. Выберите месяц:", config.CALLBACK_PREFIX_STANDARD + "ret_month_", departure_year, departure_month)
        return config.S_SELECTING_RETURN_MONTH

    context.user_data['return_month'] = selected_return_month
    month_name = config.RUSSIAN_MONTHS.get(selected_return_month, str(selected_return_month))
    await ask_date_range(update, context, return_year, selected_return_month, 
                         f"Выбран: {month_name} {return_year}. Выберите диапазон дат:", 
                         callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_range_")
    return config.S_SELECTING_RETURN_DATE_RANGE

async def standard_return_date_range_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    selected_range_str = query.data.replace(config.CALLBACK_PREFIX_STANDARD + "ret_range_", "")
    try:
        start_day, end_day = map(int, selected_range_str.split('-'))
    except ValueError:
        await query.edit_message_text("Некорректный диапазон. Выберите снова.")
        # Вернуться к выбору месяца
        return_year = context.user_data.get('return_year')
        departure_year = context.user_data.get('departure_year')
        departure_month = context.user_data.get('departure_month')
        if return_year and departure_year and departure_month:
            await ask_month(update, context, return_year, f"Год обратного вылета: {return_year}. Выберите месяц:", config.CALLBACK_PREFIX_STANDARD + "ret_month_", departure_year, departure_month)
            return config.S_SELECTING_RETURN_MONTH
        return ConversationHandler.END # Fallback

    context.user_data['return_date_range_str'] = selected_range_str
    year = context.user_data['return_year']
    month = context.user_data['return_month']
    departure_date_obj = helpers.validate_date_format(context.user_data.get('departure_date'))
    if not departure_date_obj:
        await query.edit_message_text("Ошибка: дата вылета не найдена. Начните /start.")
        return ConversationHandler.END

    await ask_specific_date(update, context, year, month, start_day, end_day,
                            f"Диапазон: {selected_range_str}. Выберите дату:",
                            callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_date_",
                            min_allowed_date_for_comparison=departure_date_obj)
    return config.S_SELECTING_RETURN_DATE

async def standard_return_date_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    selected_date_str = query.data.replace(config.CALLBACK_PREFIX_STANDARD + "ret_date_", "")
    return_date_obj = helpers.validate_date_format(selected_date_str)
    departure_date_obj = helpers.validate_date_format(context.user_data.get('departure_date'))

    if not return_date_obj or not departure_date_obj or return_date_obj < departure_date_obj:
        await query.edit_message_text("Некорректная дата возвращения или она раньше даты вылета. Попробуйте снова.")
        # ... (код для повторного запроса даты)
        return config.S_SELECTING_RETURN_DATE

    context.user_data['return_date'] = selected_date_str
    await query.edit_message_text(text=f"Дата обратного вылета: {return_date_obj.strftime('%d-%m-%Y')}")
    
    context.user_data['current_search_flow'] = config.FLOW_STANDARD
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=config.MSG_PRICE_OPTION_PROMPT,
        reply_markup=keyboards.get_price_options_keyboard()
    )
    return config.SELECTING_PRICE_OPTION


# --- ГИБКИЙ ПОИСК ---
async def flex_flight_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_input = update.message.text
    if user_input not in ['1', '2']:
        await update.message.reply_text("Пожалуйста, выберите 1 или 2.", reply_markup=keyboards.get_flight_type_reply_keyboard())
        return config.SELECTING_FLEX_FLIGHT_TYPE
    context.user_data['flight_type_one_way'] = (user_input == '1')
    
    context.user_data['current_search_flow'] = config.FLOW_FLEX
    # ReplyKeyboard от типа рейса уже использована (one_time_keyboard=True)
    await update.message.reply_text( 
        config.MSG_PRICE_OPTION_PROMPT,
        reply_markup=keyboards.get_price_options_keyboard()
    )
    return config.SELECTING_PRICE_OPTION

# Остальные обработчики гибкого поиска (flex_ask_departure_airport и т.д.)
# Их логика остается прежней, КРОМЕ тех моментов, где они раньше инициировали поиск
# или переходили к вводу цены. Теперь они должны корректно работать с тем,
# что ценовые предпочтения УЖЕ установлены в user_data после SELECTING_PRICE_OPTION.

async def flex_ask_departure_airport(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()

    if query.data == config.CALLBACK_PREFIX_FLEX + "ask_dep_yes":
        if query.message:
            try: await query.edit_message_text(text="Хорошо, выберите страну вылета:", reply_markup=None)
            except Exception: await context.bot.send_message(update.effective_chat.id, "Хорошо, выберите страну вылета:")
        # await ask_departure_country(update, context, "Выберите страну вылета:") # Если хелпер
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Выберите страну вылета:", reply_markup=keyboards.get_country_reply_keyboard())
        return config.SELECTING_FLEX_DEPARTURE_COUNTRY
    else: # ask_dep_no
        logger.info("Гибкий поиск: пользователь попытался пропустить аэропорт вылета – сценарий остановлен.")
        warn_text = ("⚠️ Для поиска рейсов Ryanair нужно указать конкретный аэропорт вылета.\n\n"
                     "Нажмите /start и начните новый поиск, указав аэропорт.")
        if query.message: 
            try: await query.edit_message_text(text=warn_text, reply_markup=None)
            except Exception: await context.bot.send_message(update.effective_chat.id, warn_text)
        else: await context.bot.send_message(chat_id=update.effective_chat.id, text=warn_text)
        context.user_data.clear()
        return ConversationHandler.END

async def flex_departure_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    country = update.message.text
    if country not in config.COUNTRIES_DATA:
        await update.message.reply_text("Страна не найдена! Пожалуйста, выберите из списка.", reply_markup=keyboards.get_country_reply_keyboard())
        return config.SELECTING_FLEX_DEPARTURE_COUNTRY
    context.user_data['departure_country'] = country
    await update.message.reply_text("Выберите город вылета:", reply_markup=keyboards.get_city_reply_keyboard(country))
    return config.SELECTING_FLEX_DEPARTURE_CITY

async def flex_departure_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    city = update.message.text
    country = context.user_data.get('departure_country')
    if not country:
        await update.message.reply_text("Ошибка: страна вылета не определена. Начните заново /start.")
        return ConversationHandler.END
    iata_code = helpers.get_airport_iata(country, city)
    if not iata_code:
        await update.message.reply_text("Город не найден! Пожалуйста, выберите из списка.", reply_markup=keyboards.get_city_reply_keyboard(country))
        return config.SELECTING_FLEX_DEPARTURE_CITY
        
    context.user_data['departure_airport_iata'] = iata_code
    context.user_data['departure_city_name'] = city
    await update.message.reply_text(f"Город вылета: {city}.", reply_markup=ReplyKeyboardRemove())
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=config.MSG_ASK_FLEX_DEPARTURE_AIRPORT_PROMPT.replace("вылета", "прилёта"), # Адаптируем сообщение
        reply_markup=keyboards.get_yes_no_keyboard(
            yes_callback=config.CALLBACK_PREFIX_FLEX + "ask_arr_yes",
            no_callback=config.CALLBACK_PREFIX_FLEX + "ask_arr_no"
        )
    )
    return config.ASK_FLEX_ARRIVAL_AIRPORT

async def flex_ask_arrival_airport(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()

    if query.data == config.CALLBACK_PREFIX_FLEX + "ask_arr_yes":
        if query.message: 
            try: await query.edit_message_text(text="Аэропорт прилёта: ДА")
            except Exception: pass
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Выберите страну прилёта:", reply_markup=keyboards.get_country_reply_keyboard())
        return config.SELECTING_FLEX_ARRIVAL_COUNTRY
    else: # ask_arr_no
        if query.message: 
            try: await query.edit_message_text(text="Аэропорт прилёта: НЕТ (любой доступный).")
            except Exception: pass
        context.user_data['arrival_airport_iata'] = None
        
        await context.bot.send_message(chat_id=update.effective_chat.id,
            text="Указать конкретные даты?",
            reply_markup=keyboards.get_skip_dates_keyboard(
                callback_select_dates=config.CALLBACK_PREFIX_FLEX + "ask_dates_yes"
            ))
        return config.ASK_FLEX_DATES

async def flex_arrival_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    country = update.message.text
    if country not in config.COUNTRIES_DATA:
        await update.message.reply_text("Страна не найдена! Пожалуйста, выберите из списка.", reply_markup=keyboards.get_country_reply_keyboard())
        return config.SELECTING_FLEX_ARRIVAL_COUNTRY
    context.user_data['arrival_country'] = country
    await update.message.reply_text("Выберите город прилёта:", reply_markup=keyboards.get_city_reply_keyboard(country))
    return config.SELECTING_FLEX_ARRIVAL_CITY

async def flex_arrival_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    city = update.message.text 
    country = context.user_data.get('arrival_country')
    if not country:
        await update.message.reply_text("Ошибка: страна прилёта не определена. Начните заново /start.")
        return ConversationHandler.END
    iata_code = helpers.get_airport_iata(country, city)
    if not iata_code:
        await update.message.reply_text("Город не найден! Пожалуйста, выберите из списка.", reply_markup=keyboards.get_city_reply_keyboard(country))
        return config.SELECTING_FLEX_ARRIVAL_CITY
    if context.user_data.get('departure_airport_iata') and iata_code == context.user_data['departure_airport_iata']:
        await update.message.reply_text("Аэропорт прилёта не может совпадать с аэропортом вылета. Выберите другой город.", reply_markup=keyboards.get_city_reply_keyboard(country))
        return config.SELECTING_FLEX_ARRIVAL_CITY
        
    context.user_data['arrival_airport_iata'] = iata_code
    context.user_data['arrival_city_name'] = city
    await update.message.reply_text(f"Город прилёта: {city}.", reply_markup=ReplyKeyboardRemove())

    await context.bot.send_message(chat_id=update.effective_chat.id,
        text="Указать конкретные даты?",
        reply_markup=keyboards.get_skip_dates_keyboard(
            callback_select_dates=config.CALLBACK_PREFIX_FLEX + "ask_dates_yes"
        ))
    return config.ASK_FLEX_DATES

async def flex_ask_dates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()

    if query.data == config.CALLBACK_PREFIX_FLEX + "ask_dates_yes":
        if query.message: 
            try: await query.edit_message_text(text="Даты: ДА, указать конкретные.")
            except Exception: pass
        await ask_year(query, context, "Выберите год вылета:", callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_year_")
        return config.SELECTING_FLEX_DEPARTURE_YEAR
    elif query.data == config.CALLBACK_NO_SPECIFIC_DATES:
        if query.message: 
            try: await query.edit_message_text(text="Даты: НЕТ, искать на ближайший год.")
            except Exception: pass
        context.user_data['departure_date'] = None
        context.user_data['return_date'] = None  
        
        # Проверка на наличие аэропорта вылета для поиска без дат
        if not context.user_data.get('departure_airport_iata'):
            msg_text = ("Ошибка: Для поиска 'куда угодно' без дат необходимо указать аэропорт вылета. "
                        "Начните поиск заново /start.")
            if query.message: 
                try: await query.edit_message_text(text=msg_text, reply_markup=None)
                except Exception: await context.bot.send_message(update.effective_chat.id, msg_text) # fallback
            else: await context.bot.send_message(chat_id=update.effective_chat.id, text=msg_text)
            context.user_data.clear()
            return ConversationHandler.END
        
        return await launch_flight_search(update, context)
    
    return config.ASK_FLEX_DATES


async def flex_departure_year_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    selected_year = int(query.data.replace(config.CALLBACK_PREFIX_FLEX + "dep_year_", ""))
    context.user_data['departure_year'] = selected_year
    await ask_month(update, context,
                  year_for_months=selected_year,
                  message_text=f"Год вылета: {selected_year}. Выберите месяц:",
                  callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_month_")
    return config.SELECTING_FLEX_DEPARTURE_MONTH

async def flex_departure_month_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    try:
        selected_month = int(query.data.replace(config.CALLBACK_PREFIX_FLEX + "dep_month_", ""))
    except ValueError:
        await query.edit_message_text("Ошибка формата месяца. Попробуйте снова.")
        return config.SELECTING_FLEX_DEPARTURE_YEAR

    year = context.user_data.get('departure_year')
    if not year:
        await query.edit_message_text("Год вылета не найден. Начните /start.")
        return ConversationHandler.END
    
    # ... (проверка на прошедший месяц) ...
    server_now_datetime = datetime.now() #
    current_month_start_on_server = server_now_datetime.replace(day=1, hour=0, minute=0, second=0, microsecond=0) #
    selected_month_start_by_user = datetime(year, selected_month, 1) #
    if selected_month_start_by_user < current_month_start_on_server: #
        # ... (сообщение и повторный вызов ask_month)
        month_name_rus = config.RUSSIAN_MONTHS.get(selected_month, str(selected_month)) #
        await query.edit_message_text(text=f"Выбран прошедший месяц ({month_name_rus} {year}). Пожалуйста, выберите корректный месяц.") #
        await ask_month(update, context, year_for_months=year, message_text=f"Год вылета: {year}. Выберите месяц:", callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_month_") #
        return config.SELECTING_FLEX_DEPARTURE_MONTH #
        
    context.user_data['departure_month'] = selected_month
    month_name = config.RUSSIAN_MONTHS.get(selected_month, str(selected_month))
    await ask_date_range(update, context, year, selected_month, 
                         f"Выбран: {month_name} {year}. Выберите диапазон дат:", 
                         callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_range_")
    return config.SELECTING_FLEX_DEPARTURE_DATE_RANGE

async def flex_departure_date_range_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    selected_range_str = query.data.replace(config.CALLBACK_PREFIX_FLEX + "dep_range_", "")
    try: 
        start_day, end_day = map(int, selected_range_str.split('-'))
    except ValueError: 
        await query.edit_message_text("Неверный диапазон. Выберите снова.")
        # ... (возврат к выбору месяца) ...
        return config.SELECTING_FLEX_DEPARTURE_MONTH #
        
    context.user_data['departure_date_range_str'] = selected_range_str
    year = context.user_data['departure_year']
    month = context.user_data['departure_month']
    min_date_for_dep = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    await ask_specific_date(update, context, year, month, start_day, end_day,
                            f"Диапазон: {selected_range_str}. Выберите дату:",
                            callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_date_",
                            min_allowed_date_for_comparison=min_date_for_dep)
    return config.SELECTING_FLEX_DEPARTURE_DATE

async def flex_departure_date_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    selected_date_str = query.data.replace(config.CALLBACK_PREFIX_FLEX + "dep_date_", "")
    date_obj = helpers.validate_date_format(selected_date_str)
    min_allowed_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    if not date_obj or date_obj < min_allowed_date :
        await query.edit_message_text("Некорректная дата или дата в прошлом. Попробуйте снова.")
        # ... (повторный запрос даты) ...
        return config.SELECTING_FLEX_DEPARTURE_DATE
        
    context.user_data['departure_date'] = selected_date_str
    if query.message:
      try: await query.edit_message_text(text=f"Дата вылета: {date_obj.strftime('%d-%m-%Y')}")
      except Exception: pass # Если сообщение уже неактуально
    
    if context.user_data.get('flight_type_one_way', True):
        return await launch_flight_search(update, context)
    else: 
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Выберите год обратного вылета:",
            reply_markup=keyboards.generate_year_buttons(config.CALLBACK_PREFIX_FLEX + "ret_year_")
        )
        return config.SELECTING_FLEX_RETURN_YEAR

async def flex_return_year_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    selected_return_year = int(query.data.replace(config.CALLBACK_PREFIX_FLEX + "ret_year_", ""))
    departure_year = context.user_data.get('departure_year')
    if not departure_year or selected_return_year < departure_year:
        await query.edit_message_text(f"Год возврата ({selected_return_year}) не может быть раньше года вылета ({departure_year}).")
        await ask_year(query, context, "Выберите корректный год обратного вылета:", callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_year_")
        return config.SELECTING_FLEX_RETURN_YEAR

    context.user_data['return_year'] = selected_return_year
    departure_month = context.user_data.get('departure_month')
    min_return_month = 1
    if selected_return_year == departure_year and departure_month:
        min_return_month = departure_month
        
    await ask_month(update, context, 
                  year_for_months=selected_return_year, 
                  message_text=f"Год обратного вылета: {selected_return_year}. Выберите месяц:",
                  callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_month_",
                  departure_year_for_comparison=departure_year,
                  departure_month_for_comparison=min_return_month)
    return config.SELECTING_FLEX_RETURN_MONTH

async def flex_return_month_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    try:
        selected_return_month = int(query.data.replace(config.CALLBACK_PREFIX_FLEX + "ret_month_", ""))
    except ValueError:
        await query.edit_message_text("Ошибка формата месяца. Попробуйте снова.")
        return config.SELECTING_FLEX_RETURN_YEAR

    return_year = context.user_data.get('return_year')
    dep_year = context.user_data.get('departure_year')
    dep_month = context.user_data.get('departure_month')
    
    if not all([return_year, dep_year, dep_month]):
        await query.edit_message_text("Ошибка: не хватает данных о датах. Начните /start.")
        return ConversationHandler.END

    if return_year == dep_year and selected_return_month < dep_month:
        # ... (сообщение об ошибке и повторный вызов ask_month) ...
        await query.edit_message_text("Месяц возврата не может быть раньше месяца вылета. Выберите снова.")
        await ask_month(update, context, return_year, f"Год обратного вылета: {return_year}. Выберите месяц:", config.CALLBACK_PREFIX_FLEX + "ret_month_", dep_year, dep_month)
        return config.SELECTING_FLEX_RETURN_MONTH
        
    context.user_data['return_month'] = selected_return_month
    month_name = config.RUSSIAN_MONTHS.get(selected_return_month, str(selected_return_month))
    await ask_date_range(update, context, return_year, selected_return_month, 
                         f"Выбран: {month_name} {return_year}. Выберите диапазон дат:", 
                         callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_range_")
    return config.SELECTING_FLEX_RETURN_DATE_RANGE


async def flex_return_date_range_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    selected_range_str = query.data.replace(config.CALLBACK_PREFIX_FLEX + "ret_range_", "")
    try: 
        start_day, end_day = map(int, selected_range_str.split('-'))
    except ValueError: 
        await query.edit_message_text("Неверный диапазон. Выберите снова.")
        # ... (возврат к выбору месяца) ...
        return config.SELECTING_FLEX_RETURN_MONTH
        
    context.user_data['return_date_range_str'] = selected_range_str
    year = context.user_data['return_year']
    month = context.user_data['return_month']
    departure_date_obj = helpers.validate_date_format(context.user_data.get('departure_date'))
    if not departure_date_obj:
        await query.edit_message_text("Ошибка: дата вылета не найдена. Начните /start.")
        return ConversationHandler.END
        
    await ask_specific_date(update, context, year, month, start_day, end_day,
                            f"Диапазон: {selected_range_str}. Выберите дату:",
                            callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_date_",
                            min_allowed_date_for_comparison=departure_date_obj)
    return config.SELECTING_FLEX_RETURN_DATE

async def flex_return_date_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    selected_date_str = query.data.replace(config.CALLBACK_PREFIX_FLEX + "ret_date_", "")
    return_date_obj = helpers.validate_date_format(selected_date_str)
    departure_date_obj = helpers.validate_date_format(context.user_data.get('departure_date'))
    
    if not return_date_obj or not departure_date_obj or return_date_obj < departure_date_obj:
        await query.edit_message_text("Некорректная дата возвращения или она раньше даты вылета. Попробуйте снова.")
        # ... (повторный запрос даты) ...
        return config.SELECTING_FLEX_RETURN_DATE
        
    context.user_data['return_date'] = selected_date_str
    if query.message:
        try: await query.edit_message_text(text=f"Дата обратного вылета: {return_date_obj.strftime('%d-%m-%Y')}")
        except Exception: pass
    
    return await launch_flight_search(update, context)

# --- НОВЫЕ УНИВЕРСАЛЬНЫЕ ОБРАБОТЧИКИ ДЛЯ ЦЕНЫ ---
async def handle_price_option_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор пользователя на клавиатуре опций цены."""
    query = update.callback_query
    if not query: return ConversationHandler.END # На всякий случай
    await query.answer() 
    choice: PriceChoice = query.data # type: ignore 
    context.user_data['price_preference_choice'] = choice
    current_flow = context.user_data.get('current_search_flow', config.FLOW_STANDARD)

    next_step_msg = "" 
    next_state: int = ConversationHandler.END # Значение по умолчанию

    if choice == config.CALLBACK_PRICE_CUSTOM:
        next_step_msg = config.MSG_MAX_PRICE_PROMPT
        next_state = config.ENTERING_CUSTOM_PRICE
    elif choice == config.CALLBACK_PRICE_LOWEST or choice == config.CALLBACK_PRICE_ALL:
        context.user_data['max_price'] = None # Для API это означает "без ограничения"
        
        if current_flow == config.FLOW_STANDARD:
            if choice == config.CALLBACK_PRICE_LOWEST:
                next_step_msg = config.MSG_PRICE_CHOICE_LOWEST_STANDARD
            else: # CALLBACK_PRICE_ALL
                next_step_msg = config.MSG_PRICE_CHOICE_ALL_STANDARD
            
            if query.message: 
                try: await query.edit_message_text(text=next_step_msg)
                except Exception as e_edit: 
                    logger.warning(f"Не удалось изменить сообщение (lowest/all standard): {e_edit}. Отправляю новое.")
                    await context.bot.send_message(update.effective_chat.id, next_step_msg)

            return await launch_flight_search(update, context)
        else: # FLOW_FLEX
            next_step_msg = config.MSG_PRICE_CHOICE_SAVED_FLEX
            if query.message: 
                try: await query.edit_message_text(text=next_step_msg)
                except Exception as e_edit: 
                    logger.warning(f"Не удалось изменить сообщение (lowest/all flex): {e_edit}. Отправляю новое.")
                    await context.bot.send_message(update.effective_chat.id, next_step_msg)

            # Следующий шаг для flex - запрос аэропорта вылета
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=config.MSG_ASK_FLEX_DEPARTURE_AIRPORT_PROMPT,
                reply_markup=keyboards.get_yes_no_keyboard(
                    yes_callback=config.CALLBACK_PREFIX_FLEX + "ask_dep_yes",
                    no_callback=config.CALLBACK_PREFIX_FLEX + "ask_dep_no"
                )
            )
            next_state = config.ASK_FLEX_DEPARTURE_AIRPORT # Следующее состояние гибкого поиска
    else: 
        logger.warning(f"Неизвестный выбор опции цены: {choice}")
        if query.message:
            try: await query.edit_message_text("Неизвестный выбор. Попробуйте снова.")
            except Exception: pass
        return ConversationHandler.END

    # Для CALLBACK_PRICE_CUSTOM редактируем сообщение или отправляем новое, если не удалось
    if query.message and next_step_msg and choice == config.CALLBACK_PRICE_CUSTOM:
        try:
            await query.edit_message_text(text=next_step_msg)
        except Exception as e_edit:
            logger.warning(f"Не удалось изменить сообщение в handle_price_option_selected для CUSTOM: {e_edit}")
            await context.bot.send_message(
                chat_id=update.effective_chat.id, # Используем update.effective_chat.id для надежности
                text=config.MSG_MAX_PRICE_PROMPT
            )
    elif not query.message and choice == config.CALLBACK_PRICE_CUSTOM: # Если исходного сообщения не было
         await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=config.MSG_MAX_PRICE_PROMPT
            )
    return next_state

async def enter_custom_price_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает введенную пользователем максимальную цену."""
    if not update.message or not update.message.text: # Проверка на пустое сообщение
        return config.ENTERING_CUSTOM_PRICE # Остаемся в том же состоянии, если что-то пошло не так

    user_input = update.message.text
    price = helpers.validate_price(user_input)
    current_flow = context.user_data.get('current_search_flow', config.FLOW_STANDARD)

    if price is None:
        await update.message.reply_text(
            config.MSG_INVALID_PRICE_INPUT,
            reply_markup=keyboards.get_price_options_keyboard()
        )
        return config.SELECTING_PRICE_OPTION 

    context.user_data['max_price'] = price
    context.user_data['price_preference_choice'] = config.CALLBACK_PRICE_CUSTOM
    
    await update.message.reply_text(config.MSG_MAX_PRICE_SET_INFO.format(price=price))

    if current_flow == config.FLOW_STANDARD:
        return await launch_flight_search(update, context)
    else: # FLOW_FLEX
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=config.MSG_ASK_FLEX_DEPARTURE_AIRPORT_PROMPT,
            reply_markup=keyboards.get_yes_no_keyboard(
                yes_callback=config.CALLBACK_PREFIX_FLEX + "ask_dep_yes",
                no_callback=config.CALLBACK_PREFIX_FLEX + "ask_dep_no"
            )
        )
        return config.ASK_FLEX_DEPARTURE_AIRPORT

# --- Обработка поиска из других аэропортов ---
async def handle_search_other_airports_decision(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int: # type: ignore
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    
    effective_chat_id = update.effective_chat.id

    if query.data == config.CALLBACK_YES_OTHER_AIRPORTS:
        departure_country = context.user_data.get('departure_country')
        original_departure_iata = context.user_data.get('departure_airport_iata')

        if not departure_country or not original_departure_iata:
            if query.message: await query.edit_message_text(text="Не удалось получить данные для поиска. Начните новый поиск.")
            else: await context.bot.send_message(effective_chat_id, "Не удалось получить данные для поиска. Начните новый поиск.")
            return ConversationHandler.END
        
        if query.message: await query.edit_message_text(text=f"Ищу рейсы из других аэропортов в {departure_country}...")
        else: await context.bot.send_message(effective_chat_id, f"Ищу рейсы из других аэропортов в {departure_country}...")

        context.user_data["_already_searched_alternatives"] = True

        all_airports_in_country = config.COUNTRIES_DATA.get(departure_country, {})
        alternative_airports = { 
            city: iata for city, iata in all_airports_in_country.items() if iata != original_departure_iata 
        }

        if not alternative_airports:
            await context.bot.send_message(chat_id=effective_chat_id, text=f"В стране {departure_country} нет других аэропортов для поиска.")
            # ... (кнопки "Что дальше?")
            return ConversationHandler.END

        # ... (остальная логика поиска по альтернативным аэропортам, как и была)
        # ВАЖНО: Убедитесь, что вызов flight_api.find_flights_with_fallback
        # внутри этого цикла использует параметры из context.user_data, включая
        # ценовые предпочтения ('max_price', 'price_preference_choice'), если это релевантно.
        # Скорее всего, для альтернативных аэропортов сохраняются те же критерии цены.
        original_max_price = context.user_data.get('max_price') # Используем ранее установленную цену
        price_preference = context.user_data.get('price_preference_choice')

        found_alternative_flights_data = defaultdict(dict)
        found_any = False

        for city, iata_code in alternative_airports.items():
            logger.info(f"Поиск из альтернативного аэропорта: {city} ({iata_code})")
            await context.bot.send_message(chat_id=effective_chat_id, text=f"Проверяю вылеты из {city} ({iata_code})...")
            
            flights_from_alt_by_date = await flight_api.find_flights_with_fallback( #
                departure_airport_iata=iata_code, #
                arrival_airport_iata=context.user_data.get('arrival_airport_iata'), #
                departure_date_str=context.user_data.get('departure_date'), #
                max_price=original_max_price, # Используем сохраненную цену
                return_date_str=context.user_data.get('return_date'), #
                is_one_way=context.user_data.get('flight_type_one_way', True) #
            )
            if flights_from_alt_by_date:
                if price_preference == config.CALLBACK_PRICE_LOWEST:
                    # Фильтруем для каждого альтернативного аэропорта отдельно
                    filtered_for_this_airport = helpers.filter_cheapest_flights(flights_from_alt_by_date)
                    if filtered_for_this_airport:
                        found_any = True
                        found_alternative_flights_data[f"{city} ({iata_code})"] = filtered_for_this_airport
                else: # 'all' or 'custom'
                    found_any = True
                    found_alternative_flights_data[f"{city} ({iata_code})"] = flights_from_alt_by_date
        
        if found_any:
            alt_flights_final_message_parts = [f"Найдены рейсы из других аэропортов в {departure_country}:\n"]
            for source_airport_info, flights_by_sub_date_dict in found_alternative_flights_data.items():
                if not flights_by_sub_date_dict: continue # Пропускаем, если для этого аэропорта после фильтрации ничего не осталось
                alt_flights_final_message_parts.append(f"\n✈️ --- *Из аэропорта: {escape_markdown(source_airport_info, version=2)}* ---\n")
                for date_key, flights_on_this_date in sorted(flights_by_sub_date_dict.items()):
                    # ... (форматирование и отправка как раньше) ...
                    try: #
                        date_obj_alt = datetime.strptime(date_key, "%Y-%m-%d") #
                        alt_flights_final_message_parts.append(f"\n--- 📅 *{date_obj_alt.strftime('%d %B %Y (%A)')}* ---\n") #
                    except ValueError: #
                        alt_flights_final_message_parts.append(f"\n--- 📅 *{escape_markdown(date_key,version=2)}* ---\n") #
                    for flight_alt in flights_on_this_date: #
                        alt_flights_final_message_parts.append(helpers.format_flight_details(flight_alt)) #
                    alt_flights_final_message_parts.append("\n")#

            full_alt_message = "".join(alt_flights_final_message_parts)
            if len(full_alt_message) > len(f"Найдены рейсы из других аэропортов в {departure_country}:\n") + 20:
                # ... (отправка чанками как раньше) ...
                escaped_full_alt_message = escape_markdown(full_alt_message, version=2) # Экранируем все сообщение целиком
                for i_alt_msg in range(0, len(escaped_full_alt_message), 4096): #
                    chunk_alt = escaped_full_alt_message[i_alt_msg:i_alt_msg + 4096] #
                    try: #
                        await context.bot.send_message(chat_id=update.effective_chat.id, text=chunk_alt, parse_mode='MarkdownV2') #
                    except Exception: #
                        await context.bot.send_message(chat_id=update.effective_chat.id, text=chunk_alt) #
            else:
                 await context.bot.send_message(chat_id=effective_chat_id, text=f"Из других аэропортов в {departure_country} рейсов по вашим критериям не найдено.")
        else:
            await context.bot.send_message(chat_id=effective_chat_id, text=f"Из других аэропортов в {departure_country} рейсов по вашим критериям не найдено.")

        # ... (кнопки "Что дальше?")
        await context.bot.send_message( #
            chat_id=update.effective_chat.id, text="Что дальше?", #
            reply_markup=keyboards.get_yes_no_keyboard( #
                yes_callback="prompt_new_search_type", no_callback="end_search_session", #
                yes_text="✅ Начать новый поиск", no_text="❌ Закончить" #
            )) #
        return ConversationHandler.END

    elif query.data == config.CALLBACK_NO_OTHER_AIRPORTS:
        if query.message: await query.edit_message_text(text="Понял. Поиск из других аэропортов отменен.")
        else: await context.bot.send_message(effective_chat_id, "Понял. Поиск из других аэропортов отменен.")
        # ... (кнопки "Что дальше?")
        await context.bot.send_message( #
            chat_id=update.effective_chat.id, text="Что дальше?", #
            reply_markup=keyboards.get_yes_no_keyboard( #
                yes_callback="prompt_new_search_type", no_callback="end_search_session", #
                yes_text="✅ Начать новый поиск", no_text="❌ Закончить" #
            )) #
        return ConversationHandler.END
    
    return config.ASK_SEARCH_OTHER_AIRPORTS


# --- Отмена и обработка ошибок ---
async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (код без изменений) ...
    message_to_send = config.MSG_CANCELLED  #
    reply_markup_to_send = ReplyKeyboardRemove() #
    chat_id_to_send = update.effective_chat.id #
    if update.callback_query: #
        await update.callback_query.answer() #
        if update.callback_query.message: #
            try: await update.callback_query.edit_message_text(text=message_to_send) #
            except Exception: 
                if chat_id_to_send: await context.bot.send_message(chat_id=chat_id_to_send, text=message_to_send, reply_markup=reply_markup_to_send) #
        elif chat_id_to_send: await context.bot.send_message(chat_id=chat_id_to_send, text=message_to_send, reply_markup=reply_markup_to_send) #
    elif update.message and chat_id_to_send: #
        await update.message.reply_text(message_to_send, reply_markup=reply_markup_to_send) #
    context.user_data.clear() #
    return ConversationHandler.END #

async def error_handler_conv(update: Union[Update, None], context: ContextTypes.DEFAULT_TYPE) -> Union[int, None]: #
    # ... (код без изменений) ...
    logger.error(f"Ошибка в ConversationHandler: {context.error}", exc_info=context.error) #
    chat_id_to_send_error = None #
    if update and hasattr(update, 'effective_chat') and update.effective_chat: #
        chat_id_to_send_error = update.effective_chat.id #
    
    if chat_id_to_send_error: #
        try:
            await context.bot.send_message( #
                chat_id=chat_id_to_send_error, #
                text=config.MSG_ERROR_OCCURRED + " Пожалуйста, попробуйте начать заново с /start.", #
                reply_markup=ReplyKeyboardRemove() #
            )
        except Exception as e: #
            logger.error(f"Не удалось отправить сообщение об ошибке пользователю: {e}") #
            
    if context.user_data: context.user_data.clear() #
    return ConversationHandler.END #

# Именованный обработчик для fallback'а
async def handle_invalid_price_choice_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query:
        await query.answer(config.MSG_INVALID_PRICE_CHOICE_FALLBACK, show_alert=True)
        logger.warning(
            f"Пользователь {query.from_user.id} нажал кнопку цены '{query.data}' на сообщении "
            f"{query.message.message_id if query.message else 'unknown'} в несоответствующем состоянии диалога."
        )

# --- Создание ConversationHandler ---
def create_conversation_handler() -> ConversationHandler:
    price_option_pattern = f"^({config.CALLBACK_PRICE_CUSTOM}|{config.CALLBACK_PRICE_LOWEST}|{config.CALLBACK_PRICE_ALL})$"
    price_fallback_pattern = r"^price_.*$" 

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start_command),
            CallbackQueryHandler(start_search_callback, pattern='^(start_standard_search|start_flex_search)$'), # Упрощен паттерн
            CallbackQueryHandler(start_flex_anywhere_callback, pattern='^start_flex_anywhere$')
        ],
        states={
            # --- Стандартный поиск ---
            config.S_SELECTING_FLIGHT_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, standard_flight_type)],
            config.S_SELECTING_DEPARTURE_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, standard_departure_country)],
            config.S_SELECTING_DEPARTURE_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, standard_departure_city)],
            config.S_SELECTING_DEPARTURE_YEAR: [CallbackQueryHandler(standard_departure_year_selected, pattern=f"^{config.CALLBACK_PREFIX_STANDARD}dep_year_")],
            config.S_SELECTING_DEPARTURE_MONTH: [CallbackQueryHandler(standard_departure_month_selected, pattern=f"^{config.CALLBACK_PREFIX_STANDARD}dep_month_")],
            config.S_SELECTING_DEPARTURE_DATE_RANGE: [CallbackQueryHandler(standard_departure_date_range_selected, pattern=f"^{config.CALLBACK_PREFIX_STANDARD}dep_range_")],
            config.S_SELECTING_DEPARTURE_DATE: [CallbackQueryHandler(standard_departure_date_selected, pattern=f"^{config.CALLBACK_PREFIX_STANDARD}dep_date_")],
            config.S_SELECTING_ARRIVAL_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, standard_arrival_country)],
            config.S_SELECTING_ARRIVAL_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, standard_arrival_city)], # Переходит в SELECTING_PRICE_OPTION
            config.S_SELECTING_RETURN_YEAR: [CallbackQueryHandler(standard_return_year_selected, pattern=f"^{config.CALLBACK_PREFIX_STANDARD}ret_year_")],
            config.S_SELECTING_RETURN_MONTH: [CallbackQueryHandler(standard_return_month_selected, pattern=f"^{config.CALLBACK_PREFIX_STANDARD}ret_month_")],
            config.S_SELECTING_RETURN_DATE_RANGE: [CallbackQueryHandler(standard_return_date_range_selected, pattern=f"^{config.CALLBACK_PREFIX_STANDARD}ret_range_")],
            config.S_SELECTING_RETURN_DATE: [CallbackQueryHandler(standard_return_date_selected, pattern=f"^{config.CALLBACK_PREFIX_STANDARD}ret_date_")], # Переходит в SELECTING_PRICE_OPTION

            # --- Гибкий поиск ---
            config.SELECTING_FLEX_FLIGHT_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, flex_flight_type)], # Переходит в SELECTING_PRICE_OPTION
            config.ASK_FLEX_DEPARTURE_AIRPORT: [CallbackQueryHandler(flex_ask_departure_airport, pattern=f"^{config.CALLBACK_PREFIX_FLEX}ask_dep_")],
            config.SELECTING_FLEX_DEPARTURE_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, flex_departure_country)],
            config.SELECTING_FLEX_DEPARTURE_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, flex_departure_city)],
            config.ASK_FLEX_ARRIVAL_AIRPORT: [CallbackQueryHandler(flex_ask_arrival_airport, pattern=f"^{config.CALLBACK_PREFIX_FLEX}ask_arr_")],
            config.SELECTING_FLEX_ARRIVAL_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, flex_arrival_country)],
            config.SELECTING_FLEX_ARRIVAL_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, flex_arrival_city)],
            config.ASK_FLEX_DATES: [CallbackQueryHandler(flex_ask_dates, pattern=f"^(?:{config.CALLBACK_PREFIX_FLEX}ask_dates_yes|{config.CALLBACK_NO_SPECIFIC_DATES})$")], # Может вызвать launch_flight_search
            config.SELECTING_FLEX_DEPARTURE_YEAR: [CallbackQueryHandler(flex_departure_year_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}dep_year_")],
            config.SELECTING_FLEX_DEPARTURE_MONTH: [CallbackQueryHandler(flex_departure_month_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}dep_month_")],
            config.SELECTING_FLEX_DEPARTURE_DATE_RANGE: [CallbackQueryHandler(flex_departure_date_range_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}dep_range_")],
            config.SELECTING_FLEX_DEPARTURE_DATE: [CallbackQueryHandler(flex_departure_date_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}dep_date_")], # Может вызвать launch_flight_search
            config.SELECTING_FLEX_RETURN_YEAR: [CallbackQueryHandler(flex_return_year_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}ret_year_")],
            config.SELECTING_FLEX_RETURN_MONTH: [CallbackQueryHandler(flex_return_month_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}ret_month_")],
            config.SELECTING_FLEX_RETURN_DATE_RANGE: [CallbackQueryHandler(flex_return_date_range_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}ret_range_")],
            config.SELECTING_FLEX_RETURN_DATE: [CallbackQueryHandler(flex_return_date_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}ret_date_")], # Может вызвать launch_flight_search
            
            # --- ОБЩИЕ СОСТОЯНИЯ ДЛЯ ЦЕНЫ ---
            config.SELECTING_PRICE_OPTION: [
                CallbackQueryHandler(handle_price_option_selected, pattern=price_option_pattern)
            ],
            config.ENTERING_CUSTOM_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_custom_price_handler)
            ],

            # --- Поиск из других аэропортов ---
            config.ASK_SEARCH_OTHER_AIRPORTS: [
                CallbackQueryHandler(handle_search_other_airports_decision, pattern=f"^{config.CALLBACK_YES_OTHER_AIRPORTS}$|^{config.CALLBACK_NO_OTHER_AIRPORTS}$")
            ],
        },
        fallbacks=[
            CommandHandler('cancel', cancel_handler),
            CallbackQueryHandler(
                handle_invalid_price_choice_fallback, 
                pattern=price_fallback_pattern 
            ),
            # Другие fallbacks для невалидных дат/месяцев, если они были
            CallbackQueryHandler(lambda u, c: u.callback_query.answer("Нет доступных опций.", show_alert=True), pattern="^no_valid_months_error$"),
            CallbackQueryHandler(lambda u, c: u.callback_query.answer("Нет доступных опций.", show_alert=True), pattern="^no_valid_dates_error$"),
            CallbackQueryHandler(lambda u, c: u.callback_query.answer("Нет доступных опций.", show_alert=True), pattern="^no_specific_dates_in_range_error$"),
            CallbackQueryHandler(lambda u, c: u.callback_query.answer("Нет доступных опций.", show_alert=True), pattern="^no_valid_date_ranges_error$"),
            CallbackQueryHandler(lambda u, c: u.callback_query.answer("Нет доступных опций.", show_alert=True), pattern="^no_dates$"),
        ],
        map_to_parent={},
        per_message=False, 
        allow_reentry=True, # Важно для /start внутри диалога
        # persistent=True, # Рассмотрите, если нужна персистентность состояний между перезапусками (требует настройки persistence)
        # name="flight_search_conversation", # Можно дать имя для отладки
    )
    return conv_handler