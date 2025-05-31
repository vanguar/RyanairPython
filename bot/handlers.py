# bot/handlers.py
import logging
import os
from telegram import Update, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery # Добавлен CallbackQuery
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
from typing import Dict, Any, Union

from . import config, keyboards, helpers, flight_api, message_formatter
from .config import PriceChoice
# Импортируем ВСЕ константы, включая новые CB_BACK_... и MSG_FLIGHT_TYPE_PROMPT
from .config import (
    S_SELECTING_FLIGHT_TYPE, S_SELECTING_DEPARTURE_COUNTRY, S_SELECTING_DEPARTURE_CITY,
    S_SELECTING_DEPARTURE_YEAR, S_SELECTING_DEPARTURE_MONTH, S_SELECTING_DEPARTURE_DATE_RANGE,
    S_SELECTING_DEPARTURE_DATE, S_SELECTING_ARRIVAL_COUNTRY, S_SELECTING_ARRIVAL_CITY,
    S_SELECTING_RETURN_YEAR, S_SELECTING_RETURN_MONTH, S_SELECTING_RETURN_DATE_RANGE,
    S_SELECTING_RETURN_DATE, SELECTING_FLEX_FLIGHT_TYPE, ASK_FLEX_DEPARTURE_AIRPORT,
    SELECTING_FLEX_DEPARTURE_COUNTRY, SELECTING_FLEX_DEPARTURE_CITY, ASK_FLEX_ARRIVAL_AIRPORT,
    SELECTING_FLEX_ARRIVAL_COUNTRY, SELECTING_FLEX_ARRIVAL_CITY, ASK_FLEX_DATES,
    SELECTING_FLEX_DEPARTURE_YEAR, SELECTING_FLEX_DEPARTURE_MONTH,
    SELECTING_FLEX_DEPARTURE_DATE_RANGE, SELECTING_FLEX_DEPARTURE_DATE,
    SELECTING_FLEX_RETURN_YEAR, SELECTING_FLEX_RETURN_MONTH, SELECTING_FLEX_RETURN_DATE_RANGE,
    SELECTING_FLEX_RETURN_DATE, ASK_SEARCH_OTHER_AIRPORTS, SELECTING_PRICE_OPTION,
    ENTERING_CUSTOM_PRICE, FLOW_STANDARD, FLOW_FLEX, CALLBACK_PREFIX_STANDARD,
    CALLBACK_PREFIX_FLEX, CALLBACK_NO_SPECIFIC_DATES, CALLBACK_PRICE_CUSTOM,
    CALLBACK_PRICE_LOWEST, CALLBACK_PRICE_ALL, CALLBACK_YES_OTHER_AIRPORTS,
    CALLBACK_NO_OTHER_AIRPORTS, MSG_FLIGHT_TYPE_PROMPT, RUSSIAN_MONTHS, COUNTRIES_DATA,

    CB_BACK_STD_DEP_COUNTRY_TO_FLIGHT_TYPE, CB_BACK_STD_DEP_CITY_TO_COUNTRY,
    CB_BACK_STD_DEP_YEAR_TO_CITY, CB_BACK_STD_DEP_MONTH_TO_YEAR,
    CB_BACK_STD_DEP_RANGE_TO_MONTH, CB_BACK_STD_DEP_DATE_TO_RANGE,
    CB_BACK_STD_ARR_COUNTRY_TO_DEP_DATE, CB_BACK_STD_ARR_CITY_TO_COUNTRY,
    CB_BACK_STD_RET_YEAR_TO_ARR_CITY, CB_BACK_STD_RET_MONTH_TO_YEAR,
    CB_BACK_STD_RET_RANGE_TO_MONTH, CB_BACK_STD_RET_DATE_TO_RANGE,
    CB_BACK_PRICE_TO_STD_ARR_CITY_ONEWAY, CB_BACK_PRICE_TO_STD_RET_DATE_TWOWAY,
    CB_BACK_PRICE_TO_ENTERING_CUSTOM, CB_BACK_PRICE_TO_FLEX_FLIGHT_TYPE,
    CB_BACK_FLEX_ASK_DEP_TO_PRICE, CB_BACK_FLEX_DEP_COUNTRY_TO_ASK_DEP,
    CB_BACK_FLEX_DEP_CITY_TO_DEP_COUNTRY, CB_BACK_FLEX_ASK_ARR_TO_DEP_CITY,
    CB_BACK_FLEX_ARR_COUNTRY_TO_ASK_ARR, CB_BACK_FLEX_ARR_CITY_TO_ARR_COUNTRY,
    CB_BACK_FLEX_ASK_DATES_TO_ARR_CITY, CB_BACK_FLEX_ASK_DATES_TO_DEP_CITY_NO_ARR,
    CB_BACK_FLEX_DEP_YEAR_TO_ASK_DATES, CB_BACK_FLEX_DEP_MONTH_TO_YEAR,
    CB_BACK_FLEX_DEP_RANGE_TO_MONTH, CB_BACK_FLEX_DEP_DATE_TO_RANGE,
    CB_BACK_FLEX_RET_YEAR_TO_DEP_DATE, CB_BACK_FLEX_RET_MONTH_TO_YEAR,
    CB_BACK_FLEX_RET_RANGE_TO_MONTH, CB_BACK_FLEX_RET_DATE_TO_RANGE
)

logger = logging.getLogger(__name__)

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ОТОБРАЖЕНИЯ КЛАВИАТУР (ОБНОВЛЕННЫЕ) ---
# В файле /app/bot/handlers.py

async def ask_year(message_or_update_or_query: Union[Update, CallbackQuery, Any], # Тип параметра обновлен
                   context: ContextTypes.DEFAULT_TYPE,
                   message_text: str,
                   callback_prefix: str = "",
                   keyboard_back_callback: str | None = None):
    """
    Отправляет или редактирует сообщение с клавиатурой выбора года.
    Может принимать как объект Update, так и напрямую CallbackQuery.
    """
    query_to_edit: CallbackQuery | None = None
    chat_id_to_send_new: int | None = None
    message_to_reply_to = None # Для случая MessageHandler

    if isinstance(message_or_update_or_query, Update):
        update_obj = message_or_update_or_query
        if update_obj.callback_query:
            query_to_edit = update_obj.callback_query
        elif update_obj.message: # Вызов из MessageHandler (например, standard_departure_city)
            chat_id_to_send_new = update_obj.message.chat_id
            message_to_reply_to = update_obj.message # Сохраняем для reply_text
        elif update_obj.effective_chat: # Общий случай для Update
            chat_id_to_send_new = update_obj.effective_chat.id

    # Проверяем, не передали ли нам напрямую CallbackQuery (например, из "back" хендлера)
    # или если мы не смогли извлечь его из Update, но это мог быть CallbackQuery
    elif isinstance(message_or_update_or_query, CallbackQuery): # Явная проверка типа
        query_to_edit = message_or_update_or_query
    elif hasattr(message_or_update_or_query, 'id') and hasattr(message_or_update_or_query, 'data') and hasattr(message_or_update_or_query, 'message'):
        # Альтернативная проверка (duck typing), если CallbackQuery не импортирован
        # и message_or_update_or_query не является Update
        try:
            query_to_edit = message_or_update_or_query
        except Exception: # На случай, если это не CallbackQuery
            logger.warning("ask_year: переданный объект не является ни Update, ни ожидаемым CallbackQuery.")


    reply_markup = keyboards.generate_year_buttons(callback_prefix, back_callback_data=keyboard_back_callback)

    if query_to_edit and query_to_edit.message: # Если есть что редактировать
        try:
            await query_to_edit.edit_message_text(
                text=message_text,
                reply_markup=reply_markup
            )
            return
        except Exception as e:
            logger.error(f"ask_year: Ошибка при редактировании сообщения: {e}. Попытка отправить новое.")
            # Если редактирование не удалось, пытаемся отправить новое сообщение, если есть chat_id
            if query_to_edit.message.chat_id:
                 chat_id_to_send_new = query_to_edit.message.chat_id
            # Если chat_id не удалось получить, то выходим или логируем


    # Если нужно отправить новое сообщение (например, первый вызов из MessageHandler)
    if chat_id_to_send_new:
        if message_to_reply_to and hasattr(message_to_reply_to, 'reply_text'): # Если это был MessageUpdate
            await message_to_reply_to.reply_text(
                message_text,
                reply_markup=reply_markup
            )
        else: # Общий случай отправки нового сообщения
            await context.bot.send_message(
                chat_id=chat_id_to_send_new,
                text=message_text,
                reply_markup=reply_markup
            )
    elif query_to_edit and query_to_edit.message and query_to_edit.message.chat_id: # Если не удалось отредактировать, но есть chat_id из query
        await context.bot.send_message(
                chat_id=query_to_edit.message.chat_id,
                text=message_text,
                reply_markup=reply_markup
            )
    else:
        logger.warning("ask_year: не удалось определить чат для отправки или редактирования сообщения.")

# В файле /app/bot/handlers.py
async def ask_month(message_or_update_or_query: Union[Update, Any], context: ContextTypes.DEFAULT_TYPE, # Изменено имя параметра
                    year_for_months: int, message_text: str, callback_prefix: str = "",
                    departure_year_for_comparison: Union[int, None] = None,
                    departure_month_for_comparison: Union[int, None] = None,
                    keyboard_back_callback: str | None = None):

    # Определяем, что нам передали: Update или уже CallbackQuery
    actual_query_object: CallbackQuery | None = None
    effective_chat_id: int | None = None

    if isinstance(message_or_update_or_query, Update):
        update_obj = message_or_update_or_query
        if update_obj.callback_query:
            actual_query_object = update_obj.callback_query
        if update_obj.effective_chat:
            effective_chat_id = update_obj.effective_chat.id
    elif hasattr(message_or_update_or_query, 'id') and hasattr(message_or_update_or_query, 'data'):
        # Похоже на CallbackQuery, если это не Update
        # Это упрощенная проверка, в идеале использовать isinstance(message_or_update_or_query, CallbackQuery)
        # но для этого нужно импортировать CallbackQuery из telegram
        actual_query_object = message_or_update_or_query
        if actual_query_object.message: # Получаем chat_id из сообщения CallbackQuery
            effective_chat_id = actual_query_object.message.chat_id

    logger.info(f"ask_month: Год: {year_for_months}, Префикс: {callback_prefix}, BackCallback: {keyboard_back_callback}")

    if not actual_query_object:
        logger.error("ask_month: не удалось получить объект CallbackQuery.")
        # Попытка отправить новое сообщение, если CallbackQuery отсутствует, но есть chat_id
        if effective_chat_id:
             await context.bot.send_message(
                chat_id=effective_chat_id,
                text=message_text,
                reply_markup=keyboards.generate_month_buttons(
                    callback_prefix=callback_prefix,
                    year_for_months=year_for_months,
                    min_departure_month=departure_month_for_comparison,
                    departure_year_for_comparison=departure_year_for_comparison,
                    back_callback_data=keyboard_back_callback
                )
            )
        return

    # Теперь используем actual_query_object для редактирования сообщения
    try:
        await actual_query_object.edit_message_text( # ИСПОЛЬЗУЕМ actual_query_object
            text=message_text,
            reply_markup=keyboards.generate_month_buttons(
                callback_prefix=callback_prefix,
                year_for_months=year_for_months,
                min_departure_month=departure_month_for_comparison,
                departure_year_for_comparison=departure_year_for_comparison,
                back_callback_data=keyboard_back_callback
            )
        )
    except TypeError as e:
        logger.error(f"ask_month: TypeError при вызове generate_month_buttons: {e}")
        await actual_query_object.edit_message_text("Произошла ошибка при отображении месяцев. Попробуйте /start")
    except Exception as e:
        logger.error(f"ask_month: Непредвиденная ошибка: {e}", exc_info=True)
        await actual_query_object.edit_message_text("Произошла внутренняя ошибка. Попробуйте /start")

# В файле /app/bot/handlers.py

async def ask_date_range(source_update_or_query: Union[Update, CallbackQuery, Any], # Тип параметра обновлен
                         context: ContextTypes.DEFAULT_TYPE,
                         year: int, month: int,
                         message_text: str, callback_prefix: str = "",
                         keyboard_back_callback: str | None = None):
    """
    Редактирует сообщение, предлагая выбрать диапазон дат.
    Ожидает, что source_update_or_query содержит CallbackQuery.
    """
    query_to_edit: CallbackQuery | None = None
    effective_chat_id: int | None = None # Для возможной отправки нового сообщения при ошибке

    if isinstance(source_update_or_query, Update):
        update_obj = source_update_or_query
        if update_obj.callback_query:
            query_to_edit = update_obj.callback_query
        if update_obj.effective_chat: # На случай, если query_to_edit не будет, но нужно будет ответить
            effective_chat_id = update_obj.effective_chat.id
    elif isinstance(source_update_or_query, CallbackQuery): # Явная проверка типа
        query_to_edit = source_update_or_query
        if query_to_edit.message:
             effective_chat_id = query_to_edit.message.chat_id # Для единообразия и возможного fallback
    elif hasattr(source_update_or_query, 'id') and hasattr(source_update_or_query, 'data') and hasattr(source_update_or_query, 'message'):
        try:
            query_to_edit = source_update_or_query
            if query_to_edit.message:
                effective_chat_id = query_to_edit.message.chat_id
        except Exception:
            logger.warning("ask_date_range: переданный объект не является ни Update, ни ожидаемым CallbackQuery.")

    if not query_to_edit or not query_to_edit.message:
        logger.error("ask_date_range: не удалось получить объект CallbackQuery или связанное сообщение для редактирования.")
        # Попытка отправить новое сообщение, если известен чат
        if effective_chat_id:
            await context.bot.send_message(
                chat_id=effective_chat_id,
                text=message_text, # Отправляем исходный текст запроса
                reply_markup=keyboards.generate_date_range_buttons(year, month, callback_prefix, back_callback_data=keyboard_back_callback)
            )
            logger.info("ask_date_range: Отправлено новое сообщение вместо редактирования.")
        return

    try:
        await query_to_edit.edit_message_text(
            text=message_text,
            reply_markup=keyboards.generate_date_range_buttons(year, month, callback_prefix, back_callback_data=keyboard_back_callback)
        )
    except Exception as e:
        logger.error(f"ask_date_range: Ошибка при редактировании сообщения: {e}")
        # Можно попытаться отправить новое сообщение, если редактирование не удалось
        if query_to_edit.message and query_to_edit.message.chat_id: # Проверяем еще раз
            try:
                await context.bot.send_message(
                    chat_id=query_to_edit.message.chat_id,
                    text=message_text,
                    reply_markup=keyboards.generate_date_range_buttons(year, month, callback_prefix, back_callback_data=keyboard_back_callback)
                )
            except Exception as e_send:
                 logger.error(f"ask_date_range: Ошибка и при отправке нового сообщения: {e_send}")

# В файле /app/bot/handlers.py

async def ask_specific_date(source_update_or_query: Union[Update, CallbackQuery, Any], # Тип параметра обновлен
                            context: ContextTypes.DEFAULT_TYPE,
                            year: int, month: int, range_start: int, range_end: int,
                            message_text: str, callback_prefix: str = "",
                            min_allowed_date_for_comparison: Union[datetime, None] = None,
                            keyboard_back_callback: str | None = None):
    """
    Редактирует сообщение, предлагая выбрать конкретную дату.
    Ожидает, что source_update_or_query содержит CallbackQuery.
    """
    query_to_edit: CallbackQuery | None = None
    effective_chat_id: int | None = None # Для возможной отправки нового сообщения при ошибке

    if isinstance(source_update_or_query, Update):
        update_obj = source_update_or_query
        if update_obj.callback_query:
            query_to_edit = update_obj.callback_query
        if update_obj.effective_chat:
            effective_chat_id = update_obj.effective_chat.id
    elif isinstance(source_update_or_query, CallbackQuery): # Явная проверка типа
        query_to_edit = source_update_or_query
        if query_to_edit.message:
             effective_chat_id = query_to_edit.message.chat_id
    elif hasattr(source_update_or_query, 'id') and hasattr(source_update_or_query, 'data') and hasattr(source_update_or_query, 'message'):
        try:
            query_to_edit = source_update_or_query
            if query_to_edit.message:
                effective_chat_id = query_to_edit.message.chat_id
        except Exception:
            logger.warning("ask_specific_date: переданный объект не является ни Update, ни ожидаемым CallbackQuery.")


    if not query_to_edit or not query_to_edit.message:
        logger.error("ask_specific_date: не удалось получить объект CallbackQuery или связанное сообщение для редактирования.")
        if effective_chat_id:
            await context.bot.send_message(
                chat_id=effective_chat_id,
                text=message_text,
                reply_markup=keyboards.generate_specific_date_buttons(
                    year, month, range_start, range_end,
                    callback_prefix=callback_prefix,
                    min_allowed_date=min_allowed_date_for_comparison,
                    back_callback_data=keyboard_back_callback
                )
            )
            logger.info("ask_specific_date: Отправлено новое сообщение вместо редактирования.")
        return

    try:
        await query_to_edit.edit_message_text(
            text=message_text,
            reply_markup=keyboards.generate_specific_date_buttons(
                year, month, range_start, range_end,
                callback_prefix=callback_prefix,
                min_allowed_date=min_allowed_date_for_comparison,
                back_callback_data=keyboard_back_callback
            )
        )
    except Exception as e:
        logger.error(f"ask_specific_date: Ошибка при редактировании сообщения: {e}")
        if query_to_edit.message and query_to_edit.message.chat_id:
            try:
                await context.bot.send_message(
                    chat_id=query_to_edit.message.chat_id,
                    text=message_text,
                    reply_markup=keyboards.generate_specific_date_buttons(
                        year, month, range_start, range_end,
                        callback_prefix=callback_prefix,
                        min_allowed_date=min_allowed_date_for_comparison,
                        back_callback_data=keyboard_back_callback
                    )
                )
            except Exception as e_send:
                logger.error(f"ask_specific_date: Ошибка и при отправке нового сообщения: {e_send}")

# --- ОСНОВНЫЕ ОБРАБОТЧИКИ ---
async def launch_flight_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    effective_chat_id = update.effective_chat.id
    try:
        dep_iata: Union[str, None] = context.user_data.get('departure_airport_iata')
        arr_iata: Union[str, None] = context.user_data.get('arrival_airport_iata')
        dep_date_str: Union[str, None] = context.user_data.get('departure_date')
        ret_date_str: Union[str, None] = context.user_data.get('return_date')
        user_max_price: Union[Decimal, None] = context.user_data.get('max_price')
        price_preference: Union[PriceChoice, None] = context.user_data.get('price_preference_choice')
        is_one_way: bool = context.user_data.get('flight_type_one_way', True)
        current_flow: Union[str, None] = context.user_data.get('current_search_flow')

        logger.info("=== Запуск launch_flight_search ===")
        logger.info(
            "Параметры: price_pref=%s, user_max_price=%s, dep_iata=%s, arr_iata=%s, dep_date=%s, ret_date=%s, one_way=%s, current_flow=%s",
            price_preference, user_max_price, dep_iata, arr_iata, dep_date_str, ret_date_str, is_one_way, current_flow
        )

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

        all_flights_data: Dict[str, list] = await flight_api.find_flights_with_fallback(
            departure_airport_iata=dep_iata,
            arrival_airport_iata=arr_iata,
            departure_date_str=dep_date_str,
            max_price=user_max_price,
            return_date_str=ret_date_str,
            is_one_way=is_one_way
        )

        logger.info(f"API flight_api.find_flights_with_fallback вернул: {'Данные есть (ключи: ' + str(list(all_flights_data.keys())) + ')' if isinstance(all_flights_data, dict) and all_flights_data else 'Пустой результат или не словарь'}")
        if not isinstance(all_flights_data, dict):
             logger.warning(f"find_flights_with_fallback вернул не словарь: {type(all_flights_data)}")
             all_flights_data = {}

        final_flights_to_show: Dict[str, list]
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

async def process_and_send_flights(update: Update, context: ContextTypes.DEFAULT_TYPE, flights_by_date: Dict[str, list]) -> int:
    chat_id = update.effective_chat.id
    context.user_data.pop('remaining_flights_to_show', None)

    if not flights_by_date:
        await context.bot.send_message(chat_id=chat_id, text=config.MSG_NO_FLIGHTS_FOUND) #
        dep_country = context.user_data.get('departure_country') #
        dep_airport_iata = context.user_data.get('departure_airport_iata') #

        if dep_country and dep_airport_iata and \
           config.COUNTRIES_DATA.get(dep_country) and \
           len(config.COUNTRIES_DATA[dep_country]) > 1 and \
           not context.user_data.get("_already_searched_alternatives", False): #
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"Хотите поискать вылеты из других аэропортов в стране {dep_country} по этому же направлению и датам?", #
                reply_markup=keyboards.get_search_other_airports_keyboard(dep_country) #
            )
            return config.ASK_SEARCH_OTHER_AIRPORTS #

        await context.bot.send_message(
            chat_id=chat_id, text="Что дальше?", #
            reply_markup=keyboards.get_yes_no_keyboard(
                yes_callback="prompt_new_search_type", no_callback="end_search_session", #
                yes_text="✅ Начать новый поиск", no_text="❌ Закончить" #
            )
        )
        return ConversationHandler.END #

    await context.bot.send_message(chat_id=chat_id, text=config.MSG_FLIGHTS_FOUND_SEE_BELOW) #

    # --- НАЧАЛО ИЗМЕНЕНИЙ ДЛЯ ГЛОБАЛЬНОЙ СОРТИРОВКИ ---
    all_flights_with_original_date = []
    for date_str, flights_list in flights_by_date.items():
        for flight_obj in flights_list:
            all_flights_with_original_date.append({'original_date_str': date_str, 'flight': flight_obj})

    # Глобальная сортировка всех рейсов по цене
    # Функция helpers.get_flight_price должна корректно извлекать цену из 'flight'
    globally_sorted_flights_with_date = sorted(all_flights_with_original_date, key=lambda x: helpers.get_flight_price(x['flight']))

    flights_message_parts = []
    last_printed_date_str = None

    for item in globally_sorted_flights_with_date:
        flight = item['flight']
        original_date_str = item['original_date_str']

        # Отображаем заголовок с датой, если она изменилась или это первый рейс в списке с этой датой
        # Это поможет сохранить контекст даты, даже при глобальной сортировке
        if original_date_str != last_printed_date_str:
            try:
                date_obj = datetime.strptime(original_date_str, "%Y-%m-%d") #
                formatted_date_header = f"\n--- 📅 *{date_obj.strftime('%d %B %Y (%A)')}* ---\n" #
                flights_message_parts.append(formatted_date_header)
                last_printed_date_str = original_date_str
            except ValueError:
                 # Если дата в неожиданном формате, просто используем строку как есть
                formatted_date_header = f"\n--- 📅 *{original_date_str}* ---\n" #
                flights_message_parts.append(formatted_date_header)
                last_printed_date_str = original_date_str


        formatted_flight = message_formatter.format_flight_details(flight) # flights_message_parts.append(formatted_flight)
        flights_message_parts.append(formatted_flight)
    
    # --- КОНЕЦ ИЗМЕНЕНИЙ ДЛЯ ГЛОБАЛЬНОЙ СОРТИРОВКИ ---

    if flights_message_parts:
        full_text = "".join(flights_message_parts) #
        if not full_text.strip():
            # Эта ситуация маловероятна, если flights_by_date не пуст, но на всякий случай
            await context.bot.send_message(chat_id=chat_id, text=config.MSG_NO_FLIGHTS_FOUND)
        else:
            max_telegram_message_length = 4096 #
            for i in range(0, len(full_text), max_telegram_message_length):
                chunk = full_text[i:i + max_telegram_message_length]
                try:
                    await context.bot.send_message(chat_id=chat_id, text=chunk)
                except Exception as e_md:
                    logger.warning(f"Ошибка при отправке чанка рейсов с MarkdownV2: {e_md}. Попытка отправить как простой текст.") #
                    try:
                        await context.bot.send_message(chat_id=chat_id, text=chunk) #
                    except Exception as fallback_e:
                        logger.error(f"Не удалось отправить чанк даже как простой текст: {fallback_e}") #
                        # Сообщение об ошибке уже отправлено выше в e_md, или можно добавить специфичное здесь
                        await context.bot.send_message(chat_id=chat_id, text="Произошла ошибка при отображении части результатов.") #
    else:
        # Если после всех обработок список для вывода пуст
        await context.bot.send_message(chat_id=chat_id, text=config.MSG_NO_FLIGHTS_FOUND)


    await context.bot.send_message(
        chat_id=chat_id, text="Что дальше?", #
        reply_markup=keyboards.get_yes_no_keyboard(
            yes_callback="prompt_new_search_type", no_callback="end_search_session", #
            yes_text="✅ Начать новый поиск", no_text="❌ Закончить" #
        )
    )
    return ConversationHandler.END #

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
    main_menu_keyboard = keyboards.get_main_menu_keyboard()
    chat_id = update.effective_chat.id
    
    image_sent_successfully = False
    # Пытаемся отправить изображение, если путь к нему указан в конфигурации
    welcome_image_path = getattr(config, 'WELCOME_IMAGE_PATH', None)

    if welcome_image_path and os.path.exists(welcome_image_path):
        try:
            with open(welcome_image_path, 'rb') as photo_file:
                await context.bot.send_photo(chat_id=chat_id, photo=photo_file)
            image_sent_successfully = True
        except Exception as e:
            # Используйте logger, если он доступен, иначе можно просто проигнорировать ошибку или вывести в print
            # logger.error(f"Ошибка при отправке приветственного изображения: {e}")
            print(f"Ошибка при отправке приветственного изображения: {e}") # Замените на logger.error, если logger настроен

    # Отправка текстового сообщения и клавиатуры
    if update.message:
        # Изображение (если было) уже отправлено. Теперь отправляем текст.
        await update.message.reply_text(config.MSG_WELCOME, reply_markup=main_menu_keyboard)
    elif update.callback_query:
        await update.callback_query.answer()
        if update.callback_query.message:
            if image_sent_successfully:
                # Если изображение отправлено, нельзя редактировать старое сообщение, чтобы добавить к нему фото.
                # Отправляем новое сообщение с текстом и клавиатурой.
                await context.bot.send_message(chat_id=chat_id, text=config.MSG_WELCOME, reply_markup=main_menu_keyboard)
                # Опционально: удалить сообщение, с которого пришел callback, чтобы не было дублирования
                try:
                    await update.callback_query.message.delete()
                except Exception as e:
                    # logger.warning(f"Не удалось удалить предыдущее сообщение (callback): {e}")
                    print(f"Не удалось удалить предыдущее сообщение (callback): {e}") # Замените на logger.warning
            else:
                # Изображение не отправлено, пытаемся отредактировать существующее сообщение
                try:
                    await update.callback_query.edit_message_text(config.MSG_WELCOME, reply_markup=main_menu_keyboard)
                except Exception as e:
                    # logger.warning(f"Не удалось отредактировать сообщение в start_command (callback): {e}")
                    print(f"Не удалось отредактировать сообщение в start_command (callback): {e}") # Замените на logger.warning
                    # Если редактирование не удалось, отправляем новое сообщение
                    await context.bot.send_message(chat_id=chat_id, text=config.MSG_WELCOME, reply_markup=main_menu_keyboard)
        else:
            # Если нет update.callback_query.message (маловероятно), отправляем новое сообщение
            await context.bot.send_message(chat_id=chat_id, text=config.MSG_WELCOME, reply_markup=main_menu_keyboard)


async def start_search_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data.clear()

    if query.message:
        try:
            if query.data == "start_standard_search": await query.edit_message_text(text="Выбран стандартный поиск.")
            elif query.data == "start_flex_search": await query.edit_message_text(text="Выбран гибкий поиск.")
        except Exception as e: logger.warning(f"Не удалось отредактировать сообщение в start_search_callback: {e}")

    if query.data == "start_standard_search":
        await context.bot.send_message(chat_id=update.effective_chat.id, text=config.MSG_FLIGHT_TYPE_PROMPT, reply_markup=keyboards.get_flight_type_reply_keyboard())
        return config.S_SELECTING_FLIGHT_TYPE
    elif query.data == "start_flex_search":
        await context.bot.send_message(chat_id=update.effective_chat.id, text=config.MSG_FLIGHT_TYPE_PROMPT, reply_markup=keyboards.get_flight_type_reply_keyboard())
        return config.SELECTING_FLEX_FLIGHT_TYPE
    elif query.data == "start_flex_anywhere":
        return await start_flex_anywhere_callback(update, context)
    return ConversationHandler.END

async def start_flex_anywhere_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        query = update.callback_query
        if query.message:
            try: await query.edit_message_text(text="Выбран поиск \"Куда угодно\".")
            except Exception as e: logger.warning(f"Не удалось отредактировать сообщение в start_flex_anywhere_callback: {e}")
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Выбран поиск \"Куда угодно\".")

    context.user_data.clear()
    context.user_data['arrival_airport_iata'] = None
    context.user_data['departure_date'] = None
    context.user_data['return_date'] = None
    context.user_data['current_search_flow'] = config.FLOW_FLEX

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=config.MSG_FLIGHT_TYPE_PROMPT,
        reply_markup=keyboards.get_flight_type_reply_keyboard()
    )
    return config.SELECTING_FLEX_FLIGHT_TYPE

# --- ОБРАБОТЧИКИ "НАЗАД" ---
# Стандартный поиск - даты вылета
# В файле /app/bot/handlers.py
async def back_std_dep_year_to_city_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data.pop('departure_year', None) 
    context.user_data.pop('departure_month', None)
    context.user_data.pop('departure_date_range_str', None)
    context.user_data.pop('departure_date', None)

    country = context.user_data.get('departure_country')
    if not country:
        logger.error("back_std_dep_year_to_city_handler: departure_country не найден в user_data.")
        if query.message: # Проверяем, есть ли query.message
            await query.edit_message_text("Ошибка: страна вылета не найдена. Пожалуйста, начните поиск заново: /start")
        elif update.effective_chat: # Используем update.effective_chat для отправки нового сообщения
             await context.bot.send_message(chat_id=update.effective_chat.id, text="Ошибка: страна вылета не найдена. Пожалуйста, начните поиск заново: /start")
        else:
             logger.error("back_std_dep_year_to_city_handler: не удалось получить chat_id для сообщения об ошибке.")
        return ConversationHandler.END
    try:
        if query.message: # Убедимся, что query.message существует
            await query.delete_message()
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение при возврате к выбору города: {e}. Попытка редактирования.")
        try:
            if query.message: # Убедимся, что query.message существует
                await query.edit_message_text("Возврат к выбору города вылета...")
        except Exception:
            pass

    # Определяем chat_id для отправки сообщения
    chat_id_to_send = None
    if query.message:
        chat_id_to_send = query.message.chat_id
    elif update.effective_chat: # Запасной вариант, если query.message отсутствует
        chat_id_to_send = update.effective_chat.id
    
    if chat_id_to_send:
        await context.bot.send_message(
            chat_id=chat_id_to_send, # ИСПОЛЬЗУЕМ ИСПРАВЛЕННЫЙ chat_id
            text="Выберите город вылета:",
            reply_markup=keyboards.get_city_reply_keyboard(country)
        )
    else:
        logger.error("back_std_dep_year_to_city_handler: не удалось определить chat_id для отправки сообщения.")
        return ConversationHandler.END

    return config.S_SELECTING_DEPARTURE_CITY

async def back_std_dep_month_to_year_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data.pop('departure_year', None)
    context.user_data.pop('departure_month', None)
    context.user_data.pop('departure_date_range_str', None)
    context.user_data.pop('departure_date', None)

    await ask_year(query, context,
                   "Выберите год вылета:",
                   callback_prefix=config.CALLBACK_PREFIX_STANDARD + "dep_year_",
                   keyboard_back_callback=config.CB_BACK_STD_DEP_YEAR_TO_CITY)
    return config.S_SELECTING_DEPARTURE_YEAR

async def back_std_dep_range_to_month_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    year = context.user_data.get('departure_year')
    context.user_data.pop('departure_month', None)
    context.user_data.pop('departure_date_range_str', None)
    context.user_data.pop('departure_date', None)

    if not year:
        await query.edit_message_text("Ошибка: год вылета не найден. /start")
        return ConversationHandler.END

    await ask_month(query, context,
                  year_for_months=year,
                  message_text=f"Год вылета: {year}. Выберите месяц:",
                  callback_prefix=config.CALLBACK_PREFIX_STANDARD + "dep_month_",
                  keyboard_back_callback=config.CB_BACK_STD_DEP_MONTH_TO_YEAR)
    return config.S_SELECTING_DEPARTURE_MONTH

async def back_std_dep_date_to_range_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    year = context.user_data.get('departure_year')
    month = context.user_data.get('departure_month')
    context.user_data.pop('departure_date_range_str', None)
    context.user_data.pop('departure_date', None)

    if not year or not month:
        await query.edit_message_text("Ошибка: год или месяц вылета не найдены. /start")
        return ConversationHandler.END

    month_name = config.RUSSIAN_MONTHS.get(month, str(month))
    await ask_date_range(query, context, year, month,
                       f"Выбран: {month_name} {year}. 📏Выберите диапазон дат:",
                       callback_prefix=config.CALLBACK_PREFIX_STANDARD + "dep_range_",
                       keyboard_back_callback=config.CB_BACK_STD_DEP_RANGE_TO_MONTH)
    return config.S_SELECTING_DEPARTURE_DATE_RANGE

# Стандартный поиск - даты возврата
async def back_std_ret_year_to_arr_city_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data.pop('return_year', None) # Год возврата еще не выбран
    # Очищаем также последующие возможные данные для возврата
    context.user_data.pop('return_month', None)
    context.user_data.pop('return_date_range_str', None)
    context.user_data.pop('return_date', None)

    country = context.user_data.get('arrival_country')
    if not country:
        logger.error("back_std_ret_year_to_arr_city_handler: arrival_country не найден.")
        await query.edit_message_text("Ошибка: страна прилета не найдена. /start")
        return ConversationHandler.END
    try:
        await query.delete_message()
    except Exception:
        try: await query.edit_message_text("Возврат к выбору города прилета...")
        except Exception: pass

    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="Выберите город прилёта:",
        reply_markup=keyboards.get_city_reply_keyboard(country)
    )
    return config.S_SELECTING_ARRIVAL_CITY

async def back_std_ret_month_to_year_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data.pop('return_year', None)
    context.user_data.pop('return_month', None)
    context.user_data.pop('return_date_range_str', None)
    context.user_data.pop('return_date', None)

    departure_year = context.user_data.get('departure_year') # для сравнения в ask_month
    await ask_year(query, context,
                   "Выберите год обратного вылета:",
                   callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_year_",
                   keyboard_back_callback=config.CB_BACK_STD_RET_YEAR_TO_ARR_CITY)
    return config.S_SELECTING_RETURN_YEAR

async def back_std_ret_range_to_month_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    year = context.user_data.get('return_year')
    context.user_data.pop('return_month', None)
    context.user_data.pop('return_date_range_str', None)
    context.user_data.pop('return_date', None)

    if not year:
        await query.edit_message_text("Ошибка: год возврата не найден. /start")
        return ConversationHandler.END
    
    departure_year = context.user_data.get('departure_year')
    departure_month_val = context.user_data.get('departure_month') # может быть None

    await ask_month(query, context,
                  year_for_months=year,
                  message_text=f"Год обратного вылета: {year}. Выберите месяц:",
                  callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_month_",
                  departure_year_for_comparison=departure_year if year == departure_year else None, # Только если годы совпадают
                  departure_month_for_comparison=departure_month_val if year == departure_year else None,
                  keyboard_back_callback=config.CB_BACK_STD_RET_MONTH_TO_YEAR)
    return config.S_SELECTING_RETURN_MONTH

async def back_std_ret_date_to_range_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    year = context.user_data.get('return_year')
    month = context.user_data.get('return_month')
    context.user_data.pop('return_date_range_str', None)
    context.user_data.pop('return_date', None)

    if not year or not month:
        await query.edit_message_text("Ошибка: год или месяц возврата не найдены. /start")
        return ConversationHandler.END

    month_name = config.RUSSIAN_MONTHS.get(month, str(month))
    await ask_date_range(query, context, year, month,
                       f"Выбран: {month_name} {year}. Выберите диапазон дат для возврата:",
                       callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_range_",
                       keyboard_back_callback=config.CB_BACK_STD_RET_RANGE_TO_MONTH)
    return config.S_SELECTING_RETURN_DATE_RANGE

# От выбора цены назад
async def back_price_to_std_arr_city_oneway_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data.pop('price_preference_choice', None)
    context.user_data.pop('max_price', None)

    arrival_country = context.user_data.get('arrival_country')
    if not arrival_country:
        logger.error("back_price_to_std_arr_city_oneway_handler: arrival_country не найден.")
        # Если нет страны прилета, значит, мы не дошли до выбора города прилета.
        # Нужно вернуться к выбору страны прилета.
        try: await query.delete_message()
        except Exception: pass
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Выберите страну прилёта:",
            reply_markup=keyboards.get_country_reply_keyboard()
        )
        return config.S_SELECTING_ARRIVAL_COUNTRY

    try: await query.delete_message()
    except Exception: pass

    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="Выберите город прилёта:",
        reply_markup=keyboards.get_city_reply_keyboard(arrival_country)
    )
    return config.S_SELECTING_ARRIVAL_CITY

async def back_price_to_std_ret_date_twoway_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data.pop('price_preference_choice', None)
    context.user_data.pop('max_price', None)

    year = context.user_data.get('return_year')
    month = context.user_data.get('return_month')
    range_str = context.user_data.get('return_date_range_str')
    dep_date_obj = helpers.validate_date_format(context.user_data.get('departure_date'))

    if not all([year, month, range_str, dep_date_obj]):
        await query.edit_message_text("Ошибка: не хватает данных для возврата. /start")
        return ConversationHandler.END
    try:
        start_day, end_day = map(int, range_str.split('-'))
    except ValueError:
        await query.edit_message_text("Ошибка формата диапазона. /start")
        return ConversationHandler.END

    await ask_specific_date(query, context, year, month, start_day, end_day,
                            f"Диапазон: {range_str}. Выберите дату обратного вылета:",
                            callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_date_",
                            min_allowed_date_for_comparison=dep_date_obj,
                            keyboard_back_callback=config.CB_BACK_STD_RET_DATE_TO_RANGE)
    return config.S_SELECTING_RETURN_DATE

async def back_price_to_entering_custom_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Возврат от ввода кастомной цены к выбору опции цены."""
    query = update.callback_query # Этот хендлер будет вызван, если мы добавим кнопку "Назад" к сообщению о вводе цены
    await query.answer()
    context.user_data.pop('max_price', None) # Очищаем введенную цену, если она была

    current_flow = context.user_data.get('current_search_flow')
    back_cb_for_price_options = None
    if current_flow == config.FLOW_STANDARD:
        if context.user_data.get('flight_type_one_way'):
            back_cb_for_price_options = config.CB_BACK_PRICE_TO_STD_ARR_CITY_ONEWAY
        else:
            back_cb_for_price_options = config.CB_BACK_PRICE_TO_STD_RET_DATE_TWOWAY
    elif current_flow == config.FLOW_FLEX:
        back_cb_for_price_options = config.CB_BACK_PRICE_TO_FLEX_FLIGHT_TYPE

    await query.edit_message_text(
        text=config.MSG_PRICE_OPTION_PROMPT,
        reply_markup=keyboards.get_price_options_keyboard(back_callback_data=back_cb_for_price_options)
    )
    return config.SELECTING_PRICE_OPTION

# Гибкий поиск - основные шаги
async def back_price_to_flex_flight_type_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data.pop('price_preference_choice', None)
    context.user_data.pop('max_price', None)
    context.user_data.pop('flight_type_one_way', None)

    try: await query.delete_message()
    except Exception: pass

    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=config.MSG_FLIGHT_TYPE_PROMPT,
        reply_markup=keyboards.get_flight_type_reply_keyboard()
    )
    return config.SELECTING_FLEX_FLIGHT_TYPE

async def back_flex_ask_dep_to_price_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    # Аэропорт вылета еще не был выбран/пропущен
    # Возвращаемся к выбору цены
    await query.edit_message_text(
        text=config.MSG_PRICE_OPTION_PROMPT,
        reply_markup=keyboards.get_price_options_keyboard(back_callback_data=config.CB_BACK_PRICE_TO_FLEX_FLIGHT_TYPE)
    )
    return config.SELECTING_PRICE_OPTION

async def back_flex_dep_country_to_ask_dep_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query # Ожидается, что этот "назад" будет от инлайн клавиатуры, если бы она была на шаге выбора страны
                                  # Но страна выбирается ReplyKeyboard. Поэтому этот хендлер для инлайн "назад" кнопки.
    # Если бы мы добавили инлайн "назад" на этапе выбора страны:
    if query: await query.answer()
    context.user_data.pop('departure_country', None)
    # Удаляем сообщение с выбором страны (если оно было инлайн)
    if query and query.message: await query.delete_message()
    # Показываем предыдущий шаг - вопрос об указании аэропорта вылета
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=config.MSG_ASK_FLEX_DEPARTURE_AIRPORT_PROMPT,
        reply_markup=keyboards.get_yes_no_keyboard(
            yes_callback=config.CALLBACK_PREFIX_FLEX + "ask_dep_yes",
            no_callback=config.CALLBACK_PREFIX_FLEX + "ask_dep_no",
            back_callback_data=config.CB_BACK_FLEX_ASK_DEP_TO_PRICE # Кнопка назад отсюда ведет к выбору цены
        )
    )
    return config.ASK_FLEX_DEPARTURE_AIRPORT

async def back_flex_dep_city_to_dep_country_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query # Аналогично предыдущему, для инлайн "назад"
    if query: await query.answer()
    context.user_data.pop('departure_country', None) # Очищаем страну, чтобы выбрать заново
    context.user_data.pop('departure_city_name', None)
    context.user_data.pop('departure_airport_iata', None)

    if query and query.message: await query.delete_message() # Если "назад" было от инлайн сообщения
    await context.bot.send_message(
        chat_id=update.effective_chat.id, # или query.effective_chat.id
        text="Выберите страну вылета:",
        reply_markup=keyboards.get_country_reply_keyboard()
    )
    return config.SELECTING_FLEX_DEPARTURE_COUNTRY

async def back_flex_ask_arr_to_dep_city_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    # Аэропорт прилета еще не выбран/пропущен
    country = context.user_data.get('departure_country')
    if not country:
        await query.edit_message_text("Ошибка: страна вылета не найдена для возврата. /start")
        return ConversationHandler.END
    try:
        await query.delete_message() # Удаляем сообщение с вопросом об аэропорте прилета
    except Exception:
        try: await query.edit_message_text("Возврат к выбору города вылета...")
        except Exception: pass

    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="Выберите город вылета:",
        reply_markup=keyboards.get_city_reply_keyboard(country)
    )
    return config.SELECTING_FLEX_DEPARTURE_CITY

async def back_flex_arr_country_to_ask_arr_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query # Ожидаем инлайн "назад" от выбора страны прилета
    if query: await query.answer()
    context.user_data.pop('arrival_country', None)
    if query and query.message: await query.delete_message()

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=config.MSG_ASK_FLEX_DEPARTURE_AIRPORT_PROMPT.replace("вылета", "прилёта"),
        reply_markup=keyboards.get_yes_no_keyboard(
            yes_callback=config.CALLBACK_PREFIX_FLEX + "ask_arr_yes",
            no_callback=config.CALLBACK_PREFIX_FLEX + "ask_arr_no",
            back_callback_data=config.CB_BACK_FLEX_ASK_ARR_TO_DEP_CITY
        )
    )
    return config.ASK_FLEX_ARRIVAL_AIRPORT

async def back_flex_arr_city_to_arr_country_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query # Ожидаем инлайн "назад" от выбора города прилета
    if query: await query.answer()
    context.user_data.pop('arrival_country', None) # Очищаем страну прилета, чтобы выбрать заново
    context.user_data.pop('arrival_city_name', None)
    context.user_data.pop('arrival_airport_iata', None)

    if query and query.message: await query.delete_message()
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Выберите страну прилёта:",
        reply_markup=keyboards.get_country_reply_keyboard()
    )
    return config.SELECTING_FLEX_ARRIVAL_COUNTRY

async def back_flex_ask_dates_to_location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Возвращает к выбору города прилета (если он был) или к вопросу об аэропорте прилета."""
    query = update.callback_query
    await query.answer()
    context.user_data.pop('departure_date', None) # Очищаем даты
    context.user_data.pop('return_date', None)

    arrival_iata = context.user_data.get('arrival_airport_iata')
    arrival_country = context.user_data.get('arrival_country') # Проверяем, был ли указан город/страна прилета

    if arrival_iata is not None and arrival_country: # Если был указан конкретный город прилета
        # Возвращаемся к выбору города прилета
        try: await query.delete_message() # Удаляем сообщение с вопросом о датах
        except Exception: pass
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Выберите город прилёта:",
            reply_markup=keyboards.get_city_reply_keyboard(arrival_country)
        )
        return config.SELECTING_FLEX_ARRIVAL_CITY
    else: # Если город прилета был пропущен (arrival_airport_iata is None) или не дошли до него
        # Возвращаемся к вопросу об аэропорте прилета
        await query.edit_message_text(
            text=config.MSG_ASK_FLEX_DEPARTURE_AIRPORT_PROMPT.replace("вылета", "прилёта"),
            reply_markup=keyboards.get_yes_no_keyboard(
                yes_callback=config.CALLBACK_PREFIX_FLEX + "ask_arr_yes",
                no_callback=config.CALLBACK_PREFIX_FLEX + "ask_arr_no",
                back_callback_data=config.CB_BACK_FLEX_ASK_ARR_TO_DEP_CITY # Назад отсюда - к городу вылета
            )
        )
        return config.ASK_FLEX_ARRIVAL_AIRPORT

# Вам потребуется создать хендлеры для CB_BACK_FLEX_DEP_... и CB_BACK_FLEX_RET_...
# по аналогии с CB_BACK_STD_DEP_... и CB_BACK_STD_RET_...


# --- СТАНДАРТНЫЙ ПОИСК (ОБНОВЛЕННЫЕ ХЕНДЛЕРЫ) ---
async def standard_flight_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_input = update.message.text
    if user_input not in ['1', '2']:
        await update.message.reply_text("Пожалуйста, выберите 1 или 2.", reply_markup=keyboards.get_flight_type_reply_keyboard())
        return config.S_SELECTING_FLIGHT_TYPE
    context.user_data['flight_type_one_way'] = (user_input == '1')
    await update.message.reply_text("🌍 Выберите страну вылета:", reply_markup=keyboards.get_country_reply_keyboard())
    return config.S_SELECTING_DEPARTURE_COUNTRY

async def standard_departure_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    country = update.message.text
    if country not in config.COUNTRIES_DATA:
        await update.message.reply_text("Страна не найдена! Пожалуйста, выберите из списка.", reply_markup=keyboards.get_country_reply_keyboard())
        return config.S_SELECTING_DEPARTURE_COUNTRY
    context.user_data['departure_country'] = country
    await update.message.reply_text("🏙️ Выберите город вылета:", reply_markup=keyboards.get_city_reply_keyboard(country))
    return config.S_SELECTING_DEPARTURE_CITY

async def standard_departure_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    city = update.message.text
    country = context.user_data.get('departure_country')
    if not country:
        await update.message.reply_text("Ошибка: страна вылета не определена. Начните заново /start.")
        return ConversationHandler.END
    iata_code = helpers.get_airport_iata(country, city)
    if not iata_code:
        await update.message.reply_text("Город не найден! Пожалуйста, выберите из списка.", reply_markup=keyboards.get_city_reply_keyboard(country))
        return config.S_SELECTING_DEPARTURE_CITY

    context.user_data['departure_airport_iata'] = iata_code
    context.user_data['departure_city_name'] = city
    await update.message.reply_text(f"Город вылета: {city}.", reply_markup=ReplyKeyboardRemove())

    await ask_year(update, context, "📅 Выберите год вылета:",
                   callback_prefix=config.CALLBACK_PREFIX_STANDARD + "dep_year_",
                   keyboard_back_callback=config.CB_BACK_STD_DEP_YEAR_TO_CITY)
    return config.S_SELECTING_DEPARTURE_YEAR

async def standard_departure_year_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    selected_year = int(query.data.replace(config.CALLBACK_PREFIX_STANDARD + "dep_year_", ""))
    context.user_data['departure_year'] = selected_year
    await ask_month(update, context,
                  year_for_months=selected_year,
                  message_text=f"Год вылета: {selected_year}. 🗓️ Выберите месяц:",
                  callback_prefix=config.CALLBACK_PREFIX_STANDARD + "dep_month_",
                  keyboard_back_callback=config.CB_BACK_STD_DEP_MONTH_TO_YEAR)
    return config.S_SELECTING_DEPARTURE_MONTH

async def standard_departure_month_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    try:
        selected_month = int(query.data.replace(config.CALLBACK_PREFIX_STANDARD + "dep_month_", ""))
    except ValueError:
        await query.edit_message_text("Ошибка формата месяца. Попробуйте снова.")
        # Возврат к выбору года с кнопкой "Назад"
        await ask_year(query, context, "Выберите год вылета:",
                       callback_prefix=config.CALLBACK_PREFIX_STANDARD + "dep_year_",
                       keyboard_back_callback=config.CB_BACK_STD_DEP_YEAR_TO_CITY)
        return config.S_SELECTING_DEPARTURE_YEAR

    year = context.user_data.get('departure_year')
    if not year:
        await query.edit_message_text("Год вылета не найден. Начните /start.")
        return ConversationHandler.END

    server_now_datetime = datetime.now()
    current_month_start_on_server = server_now_datetime.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    selected_month_start_by_user = datetime(year, selected_month, 1)
    if selected_month_start_by_user < current_month_start_on_server:
        month_name_rus = config.RUSSIAN_MONTHS.get(selected_month, str(selected_month))
        await query.edit_message_text(text=f"Выбран прошедший месяц ({month_name_rus} {year}). Пожалуйста, выберите корректный месяц.")
        await ask_month(update, context, year_for_months=year,
                        message_text=f"Год вылета: {year}. Выберите месяц:",
                        callback_prefix=config.CALLBACK_PREFIX_STANDARD + "dep_month_",
                        keyboard_back_callback=config.CB_BACK_STD_DEP_MONTH_TO_YEAR)
        return config.S_SELECTING_DEPARTURE_MONTH

    context.user_data['departure_month'] = selected_month
    month_name = config.RUSSIAN_MONTHS.get(selected_month, str(selected_month))
    await ask_date_range(update, context, year, selected_month,
                       f"Выбран: {month_name} {year}. 📏 Выберите диапазон дат:",
                       callback_prefix=config.CALLBACK_PREFIX_STANDARD + "dep_range_",
                       keyboard_back_callback=config.CB_BACK_STD_DEP_RANGE_TO_MONTH)
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
        year = context.user_data.get('departure_year')
        if year: # Должен быть установлен
             await ask_month(update, context, year_for_months=year,
                             message_text=f"Год вылета: {year}. Выберите месяц:",
                             callback_prefix=config.CALLBACK_PREFIX_STANDARD + "dep_month_",
                             keyboard_back_callback=config.CB_BACK_STD_DEP_MONTH_TO_YEAR)
             return config.S_SELECTING_DEPARTURE_MONTH
        return ConversationHandler.END

    context.user_data['departure_date_range_str'] = selected_range_str
    year = context.user_data['departure_year']
    month = context.user_data['departure_month']
    min_date_for_dep = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    await ask_specific_date(update, context, year, month, start_day, end_day,
                            f"Диапазон: {selected_range_str}. 🎯 Выберите дату:",
                            callback_prefix=config.CALLBACK_PREFIX_STANDARD + "dep_date_",
                            min_allowed_date_for_comparison=min_date_for_dep,
                            keyboard_back_callback=config.CB_BACK_STD_DEP_DATE_TO_RANGE)
    return config.S_SELECTING_DEPARTURE_DATE

async def standard_departure_date_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    selected_date_str = query.data.replace(config.CALLBACK_PREFIX_STANDARD + "dep_date_", "")
    date_obj = helpers.validate_date_format(selected_date_str)
    min_allowed_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    if not date_obj or date_obj < min_allowed_date :
        year = context.user_data.get('departure_year')
        month = context.user_data.get('departure_month')
        range_str = context.user_data.get('departure_date_range_str')
        if year and month and range_str:
            try:
                start_day, end_day = map(int, range_str.split('-'))
                await query.edit_message_text("Некорректная дата или дата в прошлом. Попробуйте снова.")
                await ask_specific_date(update, context, year, month, start_day, end_day,
                                        f"Диапазон: {range_str}. Выберите дату:",
                                        callback_prefix=config.CALLBACK_PREFIX_STANDARD + "dep_date_",
                                        min_allowed_date_for_comparison=min_allowed_date,
                                        keyboard_back_callback=config.CB_BACK_STD_DEP_DATE_TO_RANGE)
                return config.S_SELECTING_DEPARTURE_DATE
            except ValueError: pass # Ошибка в range_str, провалится ниже
        await query.edit_message_text("Ошибка даты. Начните /start.")
        return ConversationHandler.END


    context.user_data['departure_date'] = selected_date_str
    await query.edit_message_text(text=f"Дата вылета: {date_obj.strftime('%d-%m-%Y')}")
    # Переход к выбору страны прилета. Кнопку "Назад" отсюда не добавляем, т.к. это ReplyKeyboard.
    # "Назад" от страны прилета должен вести сюда (S_SELECTING_DEPARTURE_DATE)
    await context.bot.send_message(chat_id=update.effective_chat.id, text="🌍 Выберите страну прилёта:", reply_markup=keyboards.get_country_reply_keyboard())
    return config.S_SELECTING_ARRIVAL_COUNTRY

async def standard_arrival_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    country = update.message.text
    if country not in config.COUNTRIES_DATA:
        await update.message.reply_text("Страна не найдена! Пожалуйста, выберите из списка.", reply_markup=keyboards.get_country_reply_keyboard())
        return config.S_SELECTING_ARRIVAL_COUNTRY

    departure_airport_iata = context.user_data.get('departure_airport_iata')
    if departure_airport_iata and country in config.COUNTRIES_DATA and len(config.COUNTRIES_DATA[country]) == 1:
        single_city_name = list(config.COUNTRIES_DATA[country].keys())[0]
        single_airport_iata = helpers.get_airport_iata(country, single_city_name)
        if single_airport_iata == departure_airport_iata:
            await update.message.reply_text(
                f"Единственный аэропорт в стране \"{country}\" ({single_city_name}) совпадает с вашим аэропортом вылета. "
                "Выберите другую страну прилёта."
            )
            await update.message.reply_text("Выберите другую страну прилёта:", reply_markup=keyboards.get_country_reply_keyboard())
            return config.S_SELECTING_ARRIVAL_COUNTRY

    context.user_data['arrival_country'] = country
    await update.message.reply_text("🏙️ Выберите город прилёта:", reply_markup=keyboards.get_city_reply_keyboard(country))
    return config.S_SELECTING_ARRIVAL_CITY

async def standard_arrival_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        logger.warning("standard_arrival_city: пустое сообщение")
        await update.message.reply_text(
            "Пожалуйста, выберите город прилёта. Для начала, выберите страну прилёта:",
            reply_markup=keyboards.get_country_reply_keyboard()
        )
        return config.S_SELECTING_ARRIVAL_COUNTRY

    city = update.message.text
    country = context.user_data.get('arrival_country')
    if not country:
        await update.message.reply_text("Ошибка: страна прилёта не определена. Начните /start.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    iata_code = helpers.get_airport_iata(country, city)
    if not iata_code:
        await update.message.reply_text(
            f"Город '{city}' не найден. Выберите другую страну прилёта:",
            reply_markup=keyboards.get_country_reply_keyboard()
        )
        return config.S_SELECTING_ARRIVAL_COUNTRY
    if iata_code == context.user_data.get('departure_airport_iata'):
        await update.message.reply_text(
            "Аэропорт прилёта не может совпадать с аэропортом вылета. Выберите другую страну:",
            reply_markup=keyboards.get_country_reply_keyboard()
        )
        return config.S_SELECTING_ARRIVAL_COUNTRY

    context.user_data['arrival_airport_iata'] = iata_code
    context.user_data['arrival_city_name'] = city
    await update.message.reply_text(f"Город прилёта: {city}.", reply_markup=ReplyKeyboardRemove())
    context.user_data['current_search_flow'] = config.FLOW_STANDARD

    if context.user_data.get('flight_type_one_way'):
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=config.MSG_PRICE_OPTION_PROMPT,
            reply_markup=keyboards.get_price_options_keyboard(back_callback_data=config.CB_BACK_PRICE_TO_STD_ARR_CITY_ONEWAY)
        )
        return config.SELECTING_PRICE_OPTION
    else:
        # update - это MessageUpdate, ask_year его обработает для reply_text
        await ask_year(update, context, "📅 Выберите год обратного вылета:",
                       callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_year_",
                       keyboard_back_callback=config.CB_BACK_STD_RET_YEAR_TO_ARR_CITY)
        return config.S_SELECTING_RETURN_YEAR

async def standard_return_year_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    selected_return_year = int(query.data.replace(config.CALLBACK_PREFIX_STANDARD + "ret_year_", ""))
    departure_year = context.user_data.get('departure_year')
    if not departure_year or selected_return_year < departure_year:
        await query.edit_message_text(text=f"Год возврата ({selected_return_year}) не может быть раньше года вылета ({departure_year}).")
        await ask_year(query, context, "Выберите корректный год обратного вылета:", # query - для edit_message_text
                       callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_year_",
                       keyboard_back_callback=config.CB_BACK_STD_RET_YEAR_TO_ARR_CITY)
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
                  departure_year_for_comparison=departure_year, # Для корректной фильтрации месяцев
                  departure_month_for_comparison=min_return_month, # Для корректной фильтрации месяцев
                  keyboard_back_callback=config.CB_BACK_STD_RET_MONTH_TO_YEAR)
    return config.S_SELECTING_RETURN_MONTH

async def standard_return_month_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    try: selected_return_month = int(query.data.replace(config.CALLBACK_PREFIX_STANDARD + "ret_month_", ""))
    except ValueError:
        await query.edit_message_text("Ошибка формата месяца.")
        # Возврат к выбору года возврата
        await ask_year(query, context, "Выберите год обратного вылета:",
                       callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_year_",
                       keyboard_back_callback=config.CB_BACK_STD_RET_YEAR_TO_ARR_CITY)
        return config.S_SELECTING_RETURN_YEAR

    return_year = context.user_data.get('return_year')
    dep_year = context.user_data.get('departure_year') # 'departure_year' а не 'departure_year'
    dep_month = context.user_data.get('departure_month')

    if not all([return_year, dep_year, dep_month]):
        await query.edit_message_text("Ошибка данных о датах. /start")
        return ConversationHandler.END

    if return_year == dep_year and selected_return_month < dep_month:
        await query.edit_message_text("Месяц возврата не может быть раньше месяца вылета.")
        await ask_month(update, context, return_year,
                        f"Год обратного вылета: {return_year}. Выберите месяц:",
                        config.CALLBACK_PREFIX_STANDARD + "ret_month_",
                        dep_year, dep_month, # Передаем для сравнения
                        keyboard_back_callback=config.CB_BACK_STD_RET_MONTH_TO_YEAR)
        return config.S_SELECTING_RETURN_MONTH

    context.user_data['return_month'] = selected_return_month
    month_name = config.RUSSIAN_MONTHS.get(selected_return_month, str(selected_return_month))
    await ask_date_range(update, context, return_year, selected_return_month,
                         f"Выбран: {month_name} {return_year}. Диапазон дат для возврата:",
                         callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_range_",
                         keyboard_back_callback=config.CB_BACK_STD_RET_RANGE_TO_MONTH)
    return config.S_SELECTING_RETURN_DATE_RANGE

async def standard_return_date_range_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    selected_range_str = query.data.replace(config.CALLBACK_PREFIX_STANDARD + "ret_range_", "")
    try: start_day, end_day = map(int, selected_range_str.split('-'))
    except ValueError:
        await query.edit_message_text("Некорректный диапазон.")
        year = context.user_data.get('return_year')
        dep_year_comp = context.user_data.get('departure_year')
        dep_month_comp = context.user_data.get('departure_month')
        if year:
            await ask_month(update, context, year, f"Год обратного вылета: {year}. Выберите месяц:",
                            config.CALLBACK_PREFIX_STANDARD + "ret_month_",
                            dep_year_comp, dep_month_comp,
                            keyboard_back_callback=config.CB_BACK_STD_RET_MONTH_TO_YEAR)
            return config.S_SELECTING_RETURN_MONTH
        return ConversationHandler.END

    context.user_data['return_date_range_str'] = selected_range_str
    year = context.user_data['return_year']
    month = context.user_data['return_month']
    departure_date_obj = helpers.validate_date_format(context.user_data.get('departure_date'))
    if not departure_date_obj:
        await query.edit_message_text("Ошибка: дата вылета не найдена. /start")
        return ConversationHandler.END

    await ask_specific_date(update, context, year, month, start_day, end_day,
                            f"Диапазон: {selected_range_str}. Выберите дату возврата:",
                            callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_date_",
                            min_allowed_date_for_comparison=departure_date_obj,
                            keyboard_back_callback=config.CB_BACK_STD_RET_DATE_TO_RANGE)
    return config.S_SELECTING_RETURN_DATE

async def standard_return_date_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    selected_date_str = query.data.replace(config.CALLBACK_PREFIX_STANDARD + "ret_date_", "")
    return_date_obj = helpers.validate_date_format(selected_date_str)
    departure_date_obj = helpers.validate_date_format(context.user_data.get('departure_date'))

    if not return_date_obj or not departure_date_obj or return_date_obj < departure_date_obj:
        year = context.user_data.get('return_year')
        month = context.user_data.get('return_month')
        range_str = context.user_data.get('return_date_range_str')
        if year and month and range_str and departure_date_obj:
             try:
                 start_day, end_day = map(int, range_str.split('-'))
                 await query.edit_message_text("Некорректная дата или раньше даты вылета. Попробуйте снова.")
                 await ask_specific_date(update, context, year, month, start_day, end_day,
                                        f"Диапазон: {range_str}. Выберите дату возврата:",
                                        callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_date_",
                                        min_allowed_date_for_comparison=departure_date_obj,
                                        keyboard_back_callback=config.CB_BACK_STD_RET_DATE_TO_RANGE)
                 return config.S_SELECTING_RETURN_DATE
             except ValueError: pass
        await query.edit_message_text("Ошибка даты возврата. /start")
        return ConversationHandler.END


    context.user_data['return_date'] = selected_date_str
    await query.edit_message_text(text=f"Дата обратного вылета: {return_date_obj.strftime('%d-%m-%Y')}")
    context.user_data['current_search_flow'] = config.FLOW_STANDARD
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=config.MSG_PRICE_OPTION_PROMPT,
        reply_markup=keyboards.get_price_options_keyboard(back_callback_data=config.CB_BACK_PRICE_TO_STD_RET_DATE_TWOWAY)
    )
    return config.SELECTING_PRICE_OPTION

# --- ГИБКИЙ ПОИСК (ОБНОВЛЕННЫЕ ХЕНДЛЕРЫ) ---
async def flex_flight_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_input = update.message.text
    if user_input not in ['1', '2']:
        await update.message.reply_text("Пожалуйста, выберите 1 или 2.", reply_markup=keyboards.get_flight_type_reply_keyboard()) #
        return config.SELECTING_FLEX_FLIGHT_TYPE #
    context.user_data['flight_type_one_way'] = (user_input == '1')
    context.user_data['current_search_flow'] = config.FLOW_FLEX #

    # Сообщаем о выборе и убираем ReplyKeyboard
    flight_type_description = "В одну сторону" if context.user_data['flight_type_one_way'] else "В обе стороны"
    await update.message.reply_text(
        f"Тип рейса: {flight_type_description}.",
        reply_markup=ReplyKeyboardRemove()  # <--- Вот эта строка убирает клавиатуру "1, 2"
    )

    # Теперь отправляем следующее сообщение с InlineKeyboardMarkup
    await context.bot.send_message(
        chat_id=update.effective_chat.id, # Используем context.bot.send_message для чистоты
        text=config.MSG_PRICE_OPTION_PROMPT, #
        reply_markup=keyboards.get_price_options_keyboard(back_callback_data=config.CB_BACK_PRICE_TO_FLEX_FLIGHT_TYPE) #
    )
    return config.SELECTING_PRICE_OPTION #

async def flex_ask_departure_airport(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()

    if query.data == config.CALLBACK_PREFIX_FLEX + "ask_dep_yes":
        if query.message:
            try: await query.edit_message_text(text="Хорошо, выберите страну вылета:", reply_markup=None)
            except Exception: await context.bot.send_message(update.effective_chat.id, "Хорошо, выберите страну вылета:")
        await context.bot.send_message(chat_id=update.effective_chat.id, text="🌍 Выберите страну вылета:", reply_markup=keyboards.get_country_reply_keyboard())
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
        await update.message.reply_text("🤷 Страна не найдена! Пожалуйста, выберите из списка.", reply_markup=keyboards.get_country_reply_keyboard())
        return config.SELECTING_FLEX_DEPARTURE_COUNTRY
    context.user_data['departure_country'] = country
    await update.message.reply_text("🏙️ Выберите город вылета:", reply_markup=keyboards.get_city_reply_keyboard(country))
    return config.SELECTING_FLEX_DEPARTURE_CITY

async def flex_departure_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    city = update.message.text
    country = context.user_data.get('departure_country')
    if not country:
        await update.message.reply_text("❗Ошибка: страна вылета не определена. /start")
        return ConversationHandler.END
    iata_code = helpers.get_airport_iata(country, city)
    if not iata_code:
        await update.message.reply_text("🤷 Город не найден! Выберите из списка.", reply_markup=keyboards.get_city_reply_keyboard(country))
        return config.SELECTING_FLEX_DEPARTURE_CITY

    context.user_data['departure_airport_iata'] = iata_code
    context.user_data['departure_city_name'] = city
    await update.message.reply_text(f"🏙️ Город вылета: {city}.", reply_markup=ReplyKeyboardRemove())

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=config.MSG_ASK_FLEX_DEPARTURE_AIRPORT_PROMPT.replace("вылета", "прилёта"),
        reply_markup=keyboards.get_yes_no_keyboard(
            yes_callback=config.CALLBACK_PREFIX_FLEX + "ask_arr_yes",
            no_callback=config.CALLBACK_PREFIX_FLEX + "ask_arr_no",
            back_callback_data=config.CB_BACK_FLEX_ASK_ARR_TO_DEP_CITY
        )
    )
    return config.ASK_FLEX_ARRIVAL_AIRPORT

async def flex_ask_arrival_airport(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()

    if query.data == config.CALLBACK_PREFIX_FLEX + "ask_arr_yes":
        if query.message:
            try: await query.edit_message_text(text="👍 Аэропорт прилёта: ДА")
            except Exception: pass
        await context.bot.send_message(chat_id=update.effective_chat.id, text="🌍 Выберите страну прилёта:", reply_markup=keyboards.get_country_reply_keyboard())
        return config.SELECTING_FLEX_ARRIVAL_COUNTRY
    else: # ask_arr_no
        if query.message:
            try: await query.edit_message_text(text="✨ Аэропорт прилёта: НЕТ (любой доступный).")
            except Exception: pass
        context.user_data['arrival_airport_iata'] = None

        await context.bot.send_message(chat_id=update.effective_chat.id,
            text="🗓️ Указать конкретные даты?",
            reply_markup=keyboards.get_skip_dates_keyboard(
                callback_select_dates=config.CALLBACK_PREFIX_FLEX + "ask_dates_yes",
                # Назад отсюда - к вопросу об аэропорте прилета (если город прилета был пропущен)
                back_callback_data=config.CB_BACK_FLEX_ASK_DATES_TO_DEP_CITY_NO_ARR # Или CB_BACK_FLEX_ASK_DATES_TO_ARR_CITY если город был
            ))
        return config.ASK_FLEX_DATES

async def flex_arrival_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    country = update.message.text
    if country not in config.COUNTRIES_DATA:
        await update.message.reply_text("🤷 Страна не найдена! Выберите из списка.", reply_markup=keyboards.get_country_reply_keyboard())
        return config.SELECTING_FLEX_ARRIVAL_COUNTRY
    context.user_data['arrival_country'] = country
    await update.message.reply_text("🏙️ Выберите город прилёта:", reply_markup=keyboards.get_city_reply_keyboard(country))
    return config.SELECTING_FLEX_ARRIVAL_CITY

async def flex_arrival_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        logger.warning("flex_arrival_city: пустое сообщение")
        await update.message.reply_text("🏙️ Выберите город прилёта. Для начала, выберите страну:", reply_markup=keyboards.get_country_reply_keyboard())
        return config.SELECTING_FLEX_ARRIVAL_COUNTRY # Возврат к выбору страны

    city = update.message.text
    country = context.user_data.get('arrival_country')
    if not country:
        await update.message.reply_text("🤷 Ошибка: страна прилёта не определена. /start", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    iata_code = helpers.get_airport_iata(country, city)
    if not iata_code:
        await update.message.reply_text(
            f"Город '{city}' 🤷 не найден. Выберите другую страну прилёта:",
            reply_markup=keyboards.get_country_reply_keyboard()
        )
        return config.SELECTING_FLEX_ARRIVAL_COUNTRY
    departure_iata = context.user_data.get('departure_airport_iata')
    if departure_iata and iata_code == departure_iata:
        await update.message.reply_text("🤷 Аэропорт прилёта не совпадает с вылетом. Выберите другую страну:", reply_markup=keyboards.get_country_reply_keyboard())
        return config.SELECTING_FLEX_ARRIVAL_COUNTRY

    context.user_data['arrival_airport_iata'] = iata_code
    context.user_data['arrival_city_name'] = city
    await update.message.reply_text(f"🏙️ Город прилёта (гибкий поиск): {city}.", reply_markup=ReplyKeyboardRemove())

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="🗓️ Указать конкретные даты?",
        reply_markup=keyboards.get_skip_dates_keyboard(
            callback_select_dates=config.CALLBACK_PREFIX_FLEX + "ask_dates_yes",
            back_callback_data=config.CB_BACK_FLEX_ASK_DATES_TO_ARR_CITY # Назад к выбору города прилета
        )
    )
    return config.ASK_FLEX_DATES

async def flex_ask_dates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()

    if query.data == config.CALLBACK_PREFIX_FLEX + "ask_dates_yes":
        if query.message:
            try: await query.edit_message_text(text="🗓️ Даты: ДА, указать конкретные.")
            except Exception: pass
        # update (query) содержит message для edit_message_text в ask_year
        await ask_year(query, context, "🗓️ Выберите год вылета:",
                       callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_year_",
                       keyboard_back_callback=config.CB_BACK_FLEX_DEP_YEAR_TO_ASK_DATES)
        return config.SELECTING_FLEX_DEPARTURE_YEAR
    elif query.data == config.CALLBACK_NO_SPECIFIC_DATES:
        if query.message:
            try: await query.edit_message_text(text="🗓️ Даты: НЕТ, искать на ближайший год.")
            except Exception: pass
        context.user_data['departure_date'] = None
        context.user_data['return_date'] = None
        if not context.user_data.get('departure_airport_iata'):
            msg_text = ("❗Ошибка: Для поиска без дат необходимо указать аэропорт вылета. /start")
            if query.message:
                try: await query.edit_message_text(text=msg_text, reply_markup=None)
                except Exception: await context.bot.send_message(update.effective_chat.id, msg_text)
            else: await context.bot.send_message(chat_id=update.effective_chat.id, text=msg_text)
            context.user_data.clear()
            return ConversationHandler.END
        return await launch_flight_search(update, context)
    return config.ASK_FLEX_DATES # Если callback не совпал (маловероятно с паттерном)

# Остальные flex_..._selected хендлеры для дат (FLEX_DEPARTURE_YEAR, ..., FLEX_RETURN_DATE)
# должны быть обновлены, чтобы передавать keyboard_back_callback в ask_... функции,
# аналогично стандартному поиску. Например:
async def flex_departure_year_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    try:
        selected_year = int(query.data.replace(config.CALLBACK_PREFIX_FLEX + "dep_year_", ""))
    except ValueError:
        logger.warning("flex_departure_year_selected: ValueError parsing year.")
        await query.edit_message_text("❗Ошибка формата года. Пожалуйста, начните заново /start.")
        return ConversationHandler.END

    context.user_data['departure_year'] = selected_year

    await ask_month(update, context, # Используем update, т.к. он содержит query для edit_message_text
                  year_for_months=selected_year,
                  message_text=f"Год вылета: {selected_year}. 🗓️ Выберите месяц:",
                  callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_month_",
                  keyboard_back_callback=config.CB_BACK_FLEX_DEP_MONTH_TO_YEAR)
    return config.SELECTING_FLEX_DEPARTURE_MONTH

async def flex_departure_month_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    try:
        selected_month = int(query.data.replace(config.CALLBACK_PREFIX_FLEX + "dep_month_", ""))
    except ValueError:
        logger.warning("flex_departure_month_selected: ValueError parsing month.")
        await query.edit_message_text("❗Ошибка формата месяца. Попробуйте снова.")
        await ask_year(query, context, "🗓️ Выберите год вылета:", # query для edit_message_text
                       callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_year_",
                       keyboard_back_callback=config.CB_BACK_FLEX_DEP_YEAR_TO_ASK_DATES)
        return config.SELECTING_FLEX_DEPARTURE_YEAR

    year = context.user_data.get('departure_year')
    if not year:
        await query.edit_message_text("🤷 Год вылета не найден. Начните /start.")
        return ConversationHandler.END

    now = datetime.now()
    if year == now.year and selected_month < now.month:
        month_name_rus = config.RUSSIAN_MONTHS.get(selected_month, str(selected_month))
        await query.edit_message_text(text=f"🗓️ Выбран прошедший месяц ({month_name_rus} {year}). Пожалуйста, выберите корректный месяц.")
        await ask_month(update, context, year_for_months=year,
                        message_text=f"Год вылета: {year}. 🗓️ Выберите месяц:",
                        callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_month_",
                        keyboard_back_callback=config.CB_BACK_FLEX_DEP_MONTH_TO_YEAR)
        return config.SELECTING_FLEX_DEPARTURE_MONTH

    context.user_data['departure_month'] = selected_month
    month_name = config.RUSSIAN_MONTHS.get(selected_month, str(selected_month))
    await ask_date_range(update, context, year, selected_month, # update содержит query
                       f"Выбран: {month_name} {year}. 📏 Выберите диапазон дат:",
                       callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_range_",
                       keyboard_back_callback=config.CB_BACK_FLEX_DEP_RANGE_TO_MONTH)
    return config.SELECTING_FLEX_DEPARTURE_DATE_RANGE

# НОВАЯ ФУНКЦИЯ (добавьте ее)
async def flex_departure_date_range_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    selected_range_str = query.data.replace(config.CALLBACK_PREFIX_FLEX + "dep_range_", "")
    try:
        start_day, end_day = map(int, selected_range_str.split('-'))
    except ValueError:
        logger.warning("flex_departure_date_range_selected: ValueError parsing range.")
        await query.edit_message_text("🚫 Некорректный диапазон. Выберите снова.")
        year = context.user_data.get('departure_year')
        if year:
             await ask_month(update, context, year_for_months=year,
                             message_text=f"Год вылета: {year}. 🗓️ Выберите месяц:",
                             callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_month_",
                             keyboard_back_callback=config.CB_BACK_FLEX_DEP_MONTH_TO_YEAR)
             return config.SELECTING_FLEX_DEPARTURE_MONTH
        return ConversationHandler.END

    context.user_data['departure_date_range_str'] = selected_range_str
    year = context.user_data['departure_year']
    month = context.user_data['departure_month']
    min_date_for_dep = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    month_name_rus = config.RUSSIAN_MONTHS.get(month, str(month))
    await ask_specific_date(update, context, year, month, start_day, end_day, # update содержит query
                            f"Диапазон: {start_day}-{end_day} {month_name_rus}. 🗓️ Выберите дату вылета:",
                            callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_date_",
                            min_allowed_date_for_comparison=min_date_for_dep,
                            keyboard_back_callback=config.CB_BACK_FLEX_DEP_DATE_TO_RANGE)
    return config.SELECTING_FLEX_DEPARTURE_DATE

async def flex_departure_date_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    selected_date_str = query.data.replace(config.CALLBACK_PREFIX_FLEX + "dep_date_", "")
    date_obj = helpers.validate_date_format(selected_date_str)
    min_allowed_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    if not date_obj or date_obj < min_allowed_date :
        year = context.user_data.get('departure_year')
        month = context.user_data.get('departure_month')
        range_str = context.user_data.get('departure_date_range_str')
        if year and month and range_str:
            try:
                start_day, end_day = map(int, range_str.split('-'))
                month_name_rus = config.RUSSIAN_MONTHS.get(month, str(month))
                await query.edit_message_text("🚫 Некорректная дата или дата в прошлом. Попробуйте снова.")
                await ask_specific_date(update, context, year, month, start_day, end_day,
                                        f"Диапазон: {start_day}-{end_day} {month_name_rus}. 🗓️ Выберите дату вылета:",
                                        callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_date_",
                                        min_allowed_date_for_comparison=min_allowed_date,
                                        keyboard_back_callback=config.CB_BACK_FLEX_DEP_DATE_TO_RANGE)
                return config.SELECTING_FLEX_DEPARTURE_DATE
            except ValueError: pass
        await query.edit_message_text("🚫 Ошибка даты. Начните /start.")
        return ConversationHandler.END

    context.user_data['departure_date'] = selected_date_str
    if query.message:
      try: await query.edit_message_text(text=f"🗓️ Дата вылета: {date_obj.strftime('%d-%m-%Y')}")
      except Exception as e: logger.warning(f"flex_departure_date_selected: edit_message_text failed: {e}")

    if context.user_data.get('flight_type_one_way', True):
        return await launch_flight_search(update, context)
    else:
        await ask_year(query, context, "🗓️ Выберите год обратного вылета:", # query для edit_message_text
                       callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_year_",
                       keyboard_back_callback=config.CB_BACK_FLEX_RET_YEAR_TO_DEP_DATE)
        return config.SELECTING_FLEX_RETURN_YEAR

# НОВАЯ ФУНКЦИЯ (добавьте ее)
async def flex_return_year_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    try:
        selected_return_year = int(query.data.replace(config.CALLBACK_PREFIX_FLEX + "ret_year_", ""))
    except ValueError:
        logger.error("flex_return_year_selected: ValueError parsing year")
        await query.edit_message_text("🚫 Ошибка формата года возврата. /start")
        return ConversationHandler.END

    departure_date_obj = helpers.validate_date_format(context.user_data.get('departure_date'))
    if not departure_date_obj:
        await query.edit_message_text("🚫 Ошибка: дата вылета не найдена. Начните /start.")
        return ConversationHandler.END

    if selected_return_year < departure_date_obj.year:
        await query.edit_message_text(text=f"🗓️ Год возврата ({selected_return_year}) не может быть раньше года вылета ({departure_date_obj.year}).")
        await ask_year(query, context, "🗓️ Выберите корректный год обратного вылета:",
                       callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_year_",
                       keyboard_back_callback=config.CB_BACK_FLEX_RET_YEAR_TO_DEP_DATE)
        return config.SELECTING_FLEX_RETURN_YEAR

    context.user_data['return_year'] = selected_return_year

    min_ret_month_for_comp = 1
    if selected_return_year == departure_date_obj.year:
        min_ret_month_for_comp = departure_date_obj.month

    await ask_month(update, context, # update содержит query
                  year_for_months=selected_return_year,
                  message_text=f"Год обратного вылета: {selected_return_year}. 🗓️ Выберите месяц:",
                  callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_month_",
                  departure_year_for_comparison=departure_date_obj.year,
                  departure_month_for_comparison=min_ret_month_for_comp,
                  keyboard_back_callback=config.CB_BACK_FLEX_RET_MONTH_TO_YEAR)
    return config.SELECTING_FLEX_RETURN_MONTH

# НОВАЯ ФУНКЦИЯ (добавьте ее)
async def flex_return_month_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    try:
        selected_return_month = int(query.data.replace(config.CALLBACK_PREFIX_FLEX + "ret_month_", ""))
    except ValueError:
        logger.warning("flex_return_month_selected: ValueError parsing month.")
        await query.edit_message_text("🚫 Ошибка формата месяца.")
        await ask_year(query, context, "🗓️ Выберите год обратного вылета:",
                       callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_year_",
                       keyboard_back_callback=config.CB_BACK_FLEX_RET_YEAR_TO_DEP_DATE)
        return config.SELECTING_FLEX_RETURN_YEAR

    return_year = context.user_data.get('return_year')
    departure_date_obj = helpers.validate_date_format(context.user_data.get('departure_date'))

    if not return_year or not departure_date_obj:
        await query.edit_message_text("🚫 Ошибка данных о датах. /start")
        return ConversationHandler.END

    if return_year == departure_date_obj.year and selected_return_month < departure_date_obj.month:
        await query.edit_message_text("🗓️ Месяц возврата не может быть раньше месяца вылета в том же году.")
        min_ret_month_for_comp = departure_date_obj.month # Гарантированно тот же год
        await ask_month(update, context, return_year,
                        f"🗓️ Год обратного вылета: {return_year}. Выберите месяц:",
                        config.CALLBACK_PREFIX_FLEX + "ret_month_",
                        departure_date_obj.year, min_ret_month_for_comp,
                        keyboard_back_callback=config.CB_BACK_FLEX_RET_MONTH_TO_YEAR)
        return config.SELECTING_FLEX_RETURN_MONTH

    context.user_data['return_month'] = selected_return_month
    month_name = config.RUSSIAN_MONTHS.get(selected_return_month, str(selected_return_month))
    await ask_date_range(update, context, return_year, selected_return_month, # update содержит query
                         f"Выбран: {month_name} {return_year}. Диапазон дат для возврата:",
                         callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_range_",
                         keyboard_back_callback=config.CB_BACK_FLEX_RET_RANGE_TO_MONTH)
    return config.SELECTING_FLEX_RETURN_DATE_RANGE

# НОВАЯ ФУНКЦИЯ (добавьте ее)
async def flex_return_date_range_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    selected_range_str = query.data.replace(config.CALLBACK_PREFIX_FLEX + "ret_range_", "")
    try:
        start_day, end_day = map(int, selected_range_str.split('-'))
    except ValueError:
        logger.warning("flex_return_date_range_selected: ValueError parsing range.")
        await query.edit_message_text("🚫 Некорректный диапазон.")
        year = context.user_data.get('return_year')
        dep_date_obj = helpers.validate_date_format(context.user_data.get('departure_date'))
        min_ret_month_for_comp = 1
        if dep_date_obj and year == dep_date_obj.year:
            min_ret_month_for_comp = dep_date_obj.month

        if year and dep_date_obj:
            await ask_month(update, context, year, f"🗓️ Год обратного вылета: {year}. Выберите месяц:",
                            config.CALLBACK_PREFIX_FLEX + "ret_month_",
                            dep_date_obj.year, min_ret_month_for_comp,
                            keyboard_back_callback=config.CB_BACK_FLEX_RET_MONTH_TO_YEAR)
            return config.SELECTING_FLEX_RETURN_MONTH
        return ConversationHandler.END

    context.user_data['return_date_range_str'] = selected_range_str
    year = context.user_data['return_year']
    month = context.user_data['return_month']
    departure_date_obj = helpers.validate_date_format(context.user_data.get('departure_date'))
    if not departure_date_obj:
        await query.edit_message_text("❗Ошибка: дата вылета не найдена. /start")
        return ConversationHandler.END

    # Минимальная дата для возврата - это дата вылета (включительно)
    min_allowed_return_date = departure_date_obj
    
    # Корректируем start_day для клавиатуры, если он раньше даты вылета в том же месяце
    # Это для корректного отображения кнопок generate_specific_date_buttons
    temp_start_day_for_buttons = start_day
    if year == departure_date_obj.year and month == departure_date_obj.month:
        temp_start_day_for_buttons = max(start_day, departure_date_obj.day)
    
    # Если после коррекции temp_start_day_for_buttons стал больше end_day, значит в этом диапазоне нет валидных дат.
    if temp_start_day_for_buttons > end_day:
        await query.edit_message_text("🚫 В этом диапазоне нет доступных дат после учета даты вылета. Пожалуйста, выберите другой диапазон или месяц.")
        # Возврат к выбору месяца возврата
        min_ret_month_fallback = departure_date_obj.month if year == departure_date_obj.year else 1
        await ask_month(update, context, year,
                        f"🗓️ Год обратного вылета: {year}. Выберите месяц:",
                        config.CALLBACK_PREFIX_FLEX + "ret_month_",
                        departure_date_obj.year, min_ret_month_fallback,
                        keyboard_back_callback=config.CB_BACK_FLEX_RET_MONTH_TO_YEAR)
        return config.SELECTING_FLEX_RETURN_MONTH

    month_name_rus = config.RUSSIAN_MONTHS.get(month, str(month))
    await ask_specific_date(update, context, year, month, temp_start_day_for_buttons, end_day, # update содержит query
                            f"Диапазон: {start_day}-{end_day} {month_name_rus}. 🗓️ Выберите дату возврата:",
                            callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_date_",
                            min_allowed_date_for_comparison=min_allowed_return_date,
                            keyboard_back_callback=config.CB_BACK_FLEX_RET_DATE_TO_RANGE)
    return config.SELECTING_FLEX_RETURN_DATE

async def flex_return_date_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    selected_date_str = query.data.replace(config.CALLBACK_PREFIX_FLEX + "ret_date_", "")
    return_date_obj = helpers.validate_date_format(selected_date_str)
    departure_date_obj = helpers.validate_date_format(context.user_data.get('departure_date'))

    if not return_date_obj or not departure_date_obj or return_date_obj < departure_date_obj:
        year = context.user_data.get('return_year')
        month = context.user_data.get('return_month')
        range_str = context.user_data.get('return_date_range_str')
        if year and month and range_str and departure_date_obj:
             try:
                 start_day_orig, end_day_orig = map(int, range_str.split('-'))
                 # Корректируем start_day для кнопок, как это делалось в flex_return_date_range_selected
                 start_day_buttons = start_day_orig
                 if year == departure_date_obj.year and month == departure_date_obj.month:
                     start_day_buttons = max(start_day_orig, departure_date_obj.day)

                 month_name_rus = config.RUSSIAN_MONTHS.get(month, str(month))
                 await query.edit_message_text("🚫 Некорректная дата возврата (раньше даты вылета или в прошлом). Попробуйте снова.")
                 await ask_specific_date(update, context, year, month, start_day_buttons, end_day_orig,
                                        f"📏 Диапазон: {start_day_orig}-{end_day_orig} {month_name_rus}. 🗓️ Выберите дату возврата:",
                                        callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_date_",
                                        min_allowed_date_for_comparison=departure_date_obj,
                                        keyboard_back_callback=config.CB_BACK_FLEX_RET_DATE_TO_RANGE)
                 return config.SELECTING_FLEX_RETURN_DATE
             except ValueError: pass
        await query.edit_message_text("❗Ошибка даты возврата. Начните /start.")
        return ConversationHandler.END

    context.user_data['return_date'] = selected_date_str
    if query.message:
        try: await query.edit_message_text(text=f"🗓️ Дата обратного вылета: {return_date_obj.strftime('%d-%m-%Y')}")
        except Exception as e: logger.warning(f"flex_return_date_selected: edit_message_text failed: {e}")
    return await launch_flight_search(update, context)


# --- ГИБКИЙ ПОИСК - ОБРАБОТЧИКИ "НАЗАД" ДЛЯ ДАТ ---

async def back_flex_dep_year_to_ask_dates_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    context.user_data.pop('departure_year', None)
    context.user_data.pop('departure_month', None)
    context.user_data.pop('departure_date_range_str', None)
    context.user_data.pop('departure_date', None)

    back_cb_for_ask_dates = config.CB_BACK_FLEX_ASK_DATES_TO_DEP_CITY_NO_ARR
    if context.user_data.get('arrival_airport_iata') is not None and context.user_data.get('arrival_city_name'):
        back_cb_for_ask_dates = config.CB_BACK_FLEX_ASK_DATES_TO_ARR_CITY
    elif context.user_data.get('departure_city_name') and context.user_data.get('arrival_airport_iata') is None: # Если город вылета есть, а прилета нет
        back_cb_for_ask_dates = config.CB_BACK_FLEX_ASK_DATES_TO_DEP_CITY_NO_ARR

    await query.edit_message_text(
        text="🗓️ Указать конкретные даты?",
        reply_markup=keyboards.get_skip_dates_keyboard(
            callback_select_dates=config.CALLBACK_PREFIX_FLEX + "ask_dates_yes",
            back_callback_data=back_cb_for_ask_dates
        )
    )
    return config.ASK_FLEX_DATES

async def back_flex_dep_month_to_year_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    context.user_data.pop('departure_month', None)
    context.user_data.pop('departure_date_range_str', None)
    context.user_data.pop('departure_date', None)

    await ask_year(query, context,
                   "🗓️ Выберите год вылета:",
                   callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_year_",
                   keyboard_back_callback=config.CB_BACK_FLEX_DEP_YEAR_TO_ASK_DATES)
    return config.SELECTING_FLEX_DEPARTURE_YEAR

async def back_flex_dep_range_to_month_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    year = context.user_data.get('departure_year')
    context.user_data.pop('departure_date_range_str', None)
    context.user_data.pop('departure_date', None)

    if not year:
        await query.edit_message_text("❗Ошибка: год вылета не найден. /start")
        return ConversationHandler.END

    await ask_month(query, context,
                  year_for_months=year,
                  message_text=f"Год вылета: {year}. 🗓️ Выберите месяц:",
                  callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_month_",
                  keyboard_back_callback=config.CB_BACK_FLEX_DEP_MONTH_TO_YEAR)
    return config.SELECTING_FLEX_DEPARTURE_MONTH

async def back_flex_dep_date_to_range_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    year = context.user_data.get('departure_year')
    month = context.user_data.get('departure_month')
    context.user_data.pop('departure_date', None)

    if not year or not month:
        await query.edit_message_text("❗Ошибка: год или месяц вылета не найдены. /start")
        return ConversationHandler.END

    month_name = config.RUSSIAN_MONTHS.get(month, str(month))
    await ask_date_range(query, context, year, month,
                       f"Выбран: {month_name} {year}. 📏 Выберите диапазон дат:",
                       callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_range_",
                       keyboard_back_callback=config.CB_BACK_FLEX_DEP_RANGE_TO_MONTH)
    return config.SELECTING_FLEX_DEPARTURE_DATE_RANGE

async def back_flex_ret_year_to_dep_date_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    context.user_data.pop('return_year', None)
    context.user_data.pop('return_month', None)
    context.user_data.pop('return_date_range_str', None)
    context.user_data.pop('return_date', None)

    # Возвращаемся к этапу выбора конкретной даты вылета
    year = context.user_data.get('departure_year')
    month = context.user_data.get('departure_month')
    range_str = context.user_data.get('departure_date_range_str')

    if not (year and month and range_str):
        await query.edit_message_text("🛑 Не удалось восстановить предыдущий шаг выбора даты вылета. /start")
        return ConversationHandler.END
    try:
        start_day, end_day = map(int, range_str.split('-'))
    except ValueError:
        await query.edit_message_text("❗Ошибка в данных диапазона дат вылета. /start")
        return ConversationHandler.END

    min_date_for_dep = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    month_name_rus = config.RUSSIAN_MONTHS.get(month, str(month))
    await ask_specific_date(query, context, year, month, start_day, end_day,
                            f"Диапазон: {start_day}-{end_day} {month_name_rus}. 🗓️ Выберите дату вылета:",
                            callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_date_",
                            min_allowed_date_for_comparison=min_date_for_dep,
                            keyboard_back_callback=config.CB_BACK_FLEX_DEP_DATE_TO_RANGE)
    return config.SELECTING_FLEX_DEPARTURE_DATE

async def back_flex_ret_month_to_year_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    context.user_data.pop('return_month', None)
    context.user_data.pop('return_date_range_str', None)
    context.user_data.pop('return_date', None)

    # Возвращаемся к выбору года возврата
    dep_date_obj = helpers.validate_date_format(context.user_data.get('departure_date'))
    if not dep_date_obj:
        await query.edit_message_text("❗Ошибка: дата вылета не найдена. /start")
        return ConversationHandler.END

    await ask_year(query, context,
                   "🗓️ Выберите год обратного вылета:",
                   callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_year_",
                   keyboard_back_callback=config.CB_BACK_FLEX_RET_YEAR_TO_DEP_DATE)
    return config.SELECTING_FLEX_RETURN_YEAR

async def back_flex_ret_range_to_month_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    year = context.user_data.get('return_year')
    context.user_data.pop('return_date_range_str', None)
    context.user_data.pop('return_date', None)

    if not year:
        await query.edit_message_text("❗Ошибка: год возврата не найден. /start")
        return ConversationHandler.END

    departure_date_obj = helpers.validate_date_format(context.user_data.get('departure_date'))
    if not departure_date_obj:
        await query.edit_message_text("❗Ошибка: дата вылета не найдена. /start")
        return ConversationHandler.END

    min_ret_month_for_comp = 1
    if year == departure_date_obj.year:
        min_ret_month_for_comp = departure_date_obj.month

    await ask_month(query, context,
                  year_for_months=year,
                  message_text=f"Год обратного вылета: {year}. 🗓️ Выберите месяц:",
                  callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_month_",
                  departure_year_for_comparison=departure_date_obj.year,
                  departure_month_for_comparison=min_ret_month_for_comp,
                  keyboard_back_callback=config.CB_BACK_FLEX_RET_MONTH_TO_YEAR)
    return config.SELECTING_FLEX_RETURN_MONTH

async def back_flex_ret_date_to_range_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    year = context.user_data.get('return_year')
    month = context.user_data.get('return_month')
    context.user_data.pop('return_date', None)

    if not year or not month:
        await query.edit_message_text("❗Ошибка: год или месяц возврата не найдены. /start")
        return ConversationHandler.END

    departure_date_obj = helpers.validate_date_format(context.user_data.get('departure_date'))
    if not departure_date_obj: # Должна быть всегда, но на всякий случай
        await query.edit_message_text("❗Ошибка: дата вылета не найдена. /start")
        return ConversationHandler.END
    
    month_name = config.RUSSIAN_MONTHS.get(month, str(month))
    await ask_date_range(query, context, year, month,
                       f"Выбран: {month_name} {year}. 📏 Выберите диапазон дат для возврата:",
                       callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_range_",
                       keyboard_back_callback=config.CB_BACK_FLEX_RET_RANGE_TO_MONTH)
    return config.SELECTING_FLEX_RETURN_DATE_RANGE

# --- УНИВЕРСАЛЬНЫЕ ОБРАБОТЧИКИ ДЛЯ ЦЕНЫ (ОБНОВЛЕННЫЕ) ---
async def handle_price_option_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    choice: PriceChoice = query.data # type: ignore
    context.user_data['price_preference_choice'] = choice
    current_flow = context.user_data.get('current_search_flow', config.FLOW_STANDARD)

    next_step_msg = ""
    next_state: int = ConversationHandler.END

    if choice == config.CALLBACK_PRICE_CUSTOM:
        # При выборе "Задать свою цену", добавляем кнопку "Назад" к сообщению о вводе цены
        back_cb = None
        if current_flow == config.FLOW_STANDARD:
            back_cb = config.CB_BACK_PRICE_TO_STD_ARR_CITY_ONEWAY if context.user_data.get('flight_type_one_way') else config.CB_BACK_PRICE_TO_STD_RET_DATE_TWOWAY
        elif current_flow == config.FLOW_FLEX:
            back_cb = config.CB_BACK_PRICE_TO_FLEX_FLIGHT_TYPE
        
        # Формируем клавиатуру с кнопкой "Назад" для сообщения о вводе кастомной цены
        custom_price_keyboard_buttons = []
        if back_cb: # Этот back_cb будет вести НАЗАД ОТ ВЫБОРА ОПЦИИ ЦЕНЫ, а не от ввода.
                     # Для возврата от ввода цены к выбору опций нужен другой CB_BACK_...
            # Правильнее: кнопка назад от ввода цены должна вести к выбору опции цены.
            custom_price_keyboard_buttons.append([InlineKeyboardButton(config.MSG_BACK, callback_data=config.CB_BACK_PRICE_TO_ENTERING_CUSTOM)])

        reply_markup_custom = InlineKeyboardMarkup(custom_price_keyboard_buttons) if custom_price_keyboard_buttons else None

        if query.message:
            try:
                await query.edit_message_text(text=config.MSG_MAX_PRICE_PROMPT, reply_markup=reply_markup_custom)
            except Exception:
                await context.bot.send_message(update.effective_chat.id, config.MSG_MAX_PRICE_PROMPT, reply_markup=reply_markup_custom)
        else:
             await context.bot.send_message(update.effective_chat.id, config.MSG_MAX_PRICE_PROMPT, reply_markup=reply_markup_custom)
        return config.ENTERING_CUSTOM_PRICE

    # ... (остальная логика handle_price_option_selected без изменений) ...
    elif choice == config.CALLBACK_PRICE_LOWEST or choice == config.CALLBACK_PRICE_ALL:
        context.user_data['max_price'] = None
        if current_flow == config.FLOW_STANDARD:
            next_step_msg = config.MSG_PRICE_CHOICE_LOWEST_STANDARD if choice == config.CALLBACK_PRICE_LOWEST else config.MSG_PRICE_CHOICE_ALL_STANDARD
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
                    logger.warning(f"🛑 Не удалось изменить сообщение (lowest/all flex): {e_edit}. Отправляю новое.")
                    await context.bot.send_message(update.effective_chat.id, next_step_msg)

            back_cb_for_ask_dep = config.CB_BACK_FLEX_ASK_DEP_TO_PRICE
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=config.MSG_ASK_FLEX_DEPARTURE_AIRPORT_PROMPT,
                reply_markup=keyboards.get_yes_no_keyboard(
                    yes_callback=config.CALLBACK_PREFIX_FLEX + "ask_dep_yes",
                    no_callback=config.CALLBACK_PREFIX_FLEX + "ask_dep_no",
                    back_callback_data=back_cb_for_ask_dep
                )
            )
            return config.ASK_FLEX_DEPARTURE_AIRPORT
    else:
        logger.warning(f"🛑 Неизвестный выбор опции цены: {choice}")
        if query.message:
            try: await query.edit_message_text("🛑 Неизвестный выбор. Попробуйте снова.")
            except Exception: pass
        return ConversationHandler.END


async def enter_custom_price_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return config.ENTERING_CUSTOM_PRICE

    user_input = update.message.text
    price = helpers.validate_price(user_input)
    current_flow = context.user_data.get('current_search_flow', config.FLOW_STANDARD)

    if price is None:
        # При неверном вводе цены, предлагаем снова выбрать опцию, включая "Назад"
        back_cb = None
        if current_flow == config.FLOW_STANDARD:
            back_cb = config.CB_BACK_PRICE_TO_STD_ARR_CITY_ONEWAY if context.user_data.get('flight_type_one_way') else config.CB_BACK_PRICE_TO_STD_RET_DATE_TWOWAY
        elif current_flow == config.FLOW_FLEX:
            back_cb = config.CB_BACK_PRICE_TO_FLEX_FLIGHT_TYPE

        await update.message.reply_text(
            config.MSG_INVALID_PRICE_INPUT,
            reply_markup=keyboards.get_price_options_keyboard(back_callback_data=back_cb) # Передаем "Назад" для выбора опций
        )
        return config.SELECTING_PRICE_OPTION

    context.user_data['max_price'] = price
    context.user_data['price_preference_choice'] = config.CALLBACK_PRICE_CUSTOM
    await update.message.reply_text(config.MSG_MAX_PRICE_SET_INFO.format(price=price))

    if current_flow == config.FLOW_STANDARD:
        return await launch_flight_search(update, context)
    else: # FLOW_FLEX
        back_cb_for_ask_dep = config.CB_BACK_FLEX_ASK_DEP_TO_PRICE # Назад от вопроса об аэропорте вылета -> к выбору цены
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=config.MSG_ASK_FLEX_DEPARTURE_AIRPORT_PROMPT,
            reply_markup=keyboards.get_yes_no_keyboard(
                yes_callback=config.CALLBACK_PREFIX_FLEX + "ask_dep_yes",
                no_callback=config.CALLBACK_PREFIX_FLEX + "ask_dep_no",
                back_callback_data=back_cb_for_ask_dep
            )
        )
        return config.ASK_FLEX_DEPARTURE_AIRPORT

# ... (handle_search_other_airports_decision, cancel_handler, error_handler_conv, handle_invalid_price_choice_fallback БЕЗ ИЗМЕНЕНИЙ) ...
async def handle_search_other_airports_decision(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int: # type: ignore
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()

    effective_chat_id = update.effective_chat.id

    if query.data == config.CALLBACK_YES_OTHER_AIRPORTS:
        departure_country = context.user_data.get('departure_country')
        original_departure_iata = context.user_data.get('departure_airport_iata')

        if not departure_country or not original_departure_iata:
            if query.message: await query.edit_message_text(text="🤷 Не удалось получить данные для поиска. Начните новый поиск.")
            else: await context.bot.send_message(effective_chat_id, "🤷 Не удалось получить данные для поиска. Начните новый поиск.")
            return ConversationHandler.END

        if query.message: await query.edit_message_text(text=f"⏳ Ищу рейсы из других аэропортов в {departure_country}...")
        else: await context.bot.send_message(effective_chat_id, f"⏳ Ищу рейсы из других аэропортов в {departure_country}...")

        context.user_data["_already_searched_alternatives"] = True

        all_airports_in_country = config.COUNTRIES_DATA.get(departure_country, {})
        alternative_airports = {
            city: iata for city, iata in all_airports_in_country.items() if iata != original_departure_iata
        }

        if not alternative_airports:
            await context.bot.send_message(chat_id=effective_chat_id, text=f"🤷 В стране {departure_country} нет других аэропортов для поиска.")
            await context.bot.send_message(
                chat_id=update.effective_chat.id, text="Что дальше?",
                reply_markup=keyboards.get_yes_no_keyboard(
                    yes_callback="prompt_new_search_type", no_callback="end_search_session",
                    yes_text="✅ Начать новый поиск", no_text="❌ Закончить"
                ))
            return ConversationHandler.END


        original_max_price = context.user_data.get('max_price')
        price_preference = context.user_data.get('price_preference_choice')

        found_alternative_flights_data = defaultdict(dict)
        found_any = False

        for city, iata_code in alternative_airports.items():
            logger.info(f"⏳ Поиск из альтернативного аэропорта: {city} ({iata_code})")
            await context.bot.send_message(chat_id=effective_chat_id, text=f"⏳ Проверяю вылеты из {city} ({iata_code})...")

            flights_from_alt_by_date = await flight_api.find_flights_with_fallback(
                departure_airport_iata=iata_code,
                arrival_airport_iata=context.user_data.get('arrival_airport_iata'),
                departure_date_str=context.user_data.get('departure_date'),
                max_price=original_max_price,
                return_date_str=context.user_data.get('return_date'),
                is_one_way=context.user_data.get('flight_type_one_way', True)
            )
            if flights_from_alt_by_date:
                if price_preference == config.CALLBACK_PRICE_LOWEST:
                    filtered_for_this_airport = helpers.filter_cheapest_flights(flights_from_alt_by_date)
                    if filtered_for_this_airport:
                        found_any = True
                        found_alternative_flights_data[f"{city} ({iata_code})"] = filtered_for_this_airport
                else: # 'all' or 'custom'
                    found_any = True
                    found_alternative_flights_data[f"{city} ({iata_code})"] = flights_from_alt_by_date

        if found_any:
            alt_flights_final_message_parts = [f"✈️✨ Найдены рейсы из других аэропортов в {departure_country}:\n"]
            for source_airport_info, flights_by_sub_date_dict in found_alternative_flights_data.items():
                if not flights_by_sub_date_dict: continue
                alt_flights_final_message_parts.append(f"\n✈️ Из аэропорта: {source_airport_info} ---\n")
                for date_key, flights_on_this_date in sorted(flights_by_sub_date_dict.items()):
                    try:
                        date_obj_alt = datetime.strptime(date_key, "%Y-%m-%d")
                        alt_flights_final_message_parts.append(f"\n--- 📅 *{date_obj_alt.strftime('%d %B %Y (%A)')}* ---\n")
                    except ValueError:
                        alt_flights_final_message_parts.append(f"\n--- 📅 {date_key} ---\n")
                    for flight_alt in flights_on_this_date:
                        alt_flights_final_message_parts.append(message_formatter.format_flight_details(flight_alt)) # <--- ИЗМЕНЕНИЕ
                    alt_flights_final_message_parts.append("\n")

            full_alt_message = "".join(alt_flights_final_message_parts)
            if len(full_alt_message) > len(f"✈️✨ Найдены рейсы из других аэропортов в {departure_country}:\n") + 20:
                escaped_full_alt_message = full_alt_message
                for i_alt_msg in range(0, len(escaped_full_alt_message), 4096):
                    chunk_alt = escaped_full_alt_message[i_alt_msg:i_alt_msg + 4096]
                    try:
                        await context.bot.send_message(chat_id=update.effective_chat.id, text=chunk_alt)
                    except Exception:
                        await context.bot.send_message(chat_id=update.effective_chat.id, text=chunk_alt)
            else:
                 await context.bot.send_message(chat_id=effective_chat_id, text=f"🤷 Из других аэропортов в {departure_country} рейсов по вашим критериям не найдено.")
        else:
            await context.bot.send_message(chat_id=effective_chat_id, text=f"🤷 Из других аэропортов в {departure_country} рейсов по вашим критериям не найдено.")

        await context.bot.send_message(
            chat_id=update.effective_chat.id, text="Что дальше?",
            reply_markup=keyboards.get_yes_no_keyboard(
                yes_callback="prompt_new_search_type", no_callback="end_search_session",
                yes_text="✅ Начать новый поиск", no_text="❌ Закончить"
            ))
        return ConversationHandler.END

    elif query.data == config.CALLBACK_NO_OTHER_AIRPORTS:
        if query.message: await query.edit_message_text(text="🛑 Понял. Поиск из других аэропортов отменен.")
        else: await context.bot.send_message(effective_chat_id, "🛑 Понял. Поиск из других аэропортов отменен.")
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text="🤷 Что дальше?",
            reply_markup=keyboards.get_yes_no_keyboard(
                yes_callback="prompt_new_search_type", no_callback="end_search_session",
                yes_text="✅ Начать новый поиск", no_text="❌ Закончить"
            ))
        return ConversationHandler.END

    return config.ASK_SEARCH_OTHER_AIRPORTS


async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message_to_send = config.MSG_CANCELLED
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

async def error_handler_conv(update: Union[Update, None], context: ContextTypes.DEFAULT_TYPE) -> Union[int, None]:
    logger.error(f"Ошибка в ConversationHandler: {context.error}", exc_info=context.error)
    chat_id_to_send_error = None
    if update and hasattr(update, 'effective_chat') and update.effective_chat:
        chat_id_to_send_error = update.effective_chat.id

    if chat_id_to_send_error:
        try:
            await context.bot.send_message(
                chat_id=chat_id_to_send_error,
                text=config.MSG_ERROR_OCCURRED + " 🙏 Пожалуйста, попробуйте начать заново с /start.",
                reply_markup=ReplyKeyboardRemove()
            )
        except Exception as e:
            logger.error(f"🤷 Не удалось отправить сообщение об ошибке пользователю: {e}")

    if context.user_data: context.user_data.clear()
    return ConversationHandler.END

async def handle_invalid_price_choice_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query:
        await query.answer(config.MSG_INVALID_PRICE_CHOICE_FALLBACK, show_alert=True)
        logger.warning(
            f"Пользователь {query.from_user.id} нажал кнопку цены '{query.data}' на сообщении "
            f"{query.message.message_id if query.message else 'unknown'} в несоответствующем состоянии диалога."
        )


# --- СОЗДАНИЕ CONVERSATIONHANDLER (ОБНОВЛЕННОЕ) ---
# В файле bot/handlers.py

def create_conversation_handler() -> ConversationHandler:
    price_option_pattern = f"^({config.CALLBACK_PRICE_CUSTOM}|{config.CALLBACK_PRICE_LOWEST}|{config.CALLBACK_PRICE_ALL})$" #
    # Паттерн для отлова любых callback_data, начинающихся с "price_", чтобы обработать их в fallback, если они невалидны для текущего состояния.
    price_fallback_pattern = r"^price_.*$" #

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start_command), #
            CallbackQueryHandler(start_search_callback, pattern='^(start_standard_search|start_flex_search)$'), #
            CallbackQueryHandler(start_flex_anywhere_callback, pattern='^start_flex_anywhere$') #
        ],
        states={
            # --- Стандартный поиск ---
            config.S_SELECTING_FLIGHT_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, standard_flight_type)], #
            config.S_SELECTING_DEPARTURE_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, standard_departure_country)], #
            config.S_SELECTING_DEPARTURE_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, standard_departure_city)], #
            config.S_SELECTING_DEPARTURE_YEAR: [ #
                CallbackQueryHandler(standard_departure_year_selected, pattern=f"^{config.CALLBACK_PREFIX_STANDARD}dep_year_"), #
                CallbackQueryHandler(back_std_dep_year_to_city_handler, pattern=f"^{config.CB_BACK_STD_DEP_YEAR_TO_CITY}$") #
            ],
            config.S_SELECTING_DEPARTURE_MONTH: [ #
                CallbackQueryHandler(standard_departure_month_selected, pattern=f"^{config.CALLBACK_PREFIX_STANDARD}dep_month_"), #
                CallbackQueryHandler(back_std_dep_month_to_year_handler, pattern=f"^{config.CB_BACK_STD_DEP_MONTH_TO_YEAR}$") #
            ],
            config.S_SELECTING_DEPARTURE_DATE_RANGE: [ #
                CallbackQueryHandler(standard_departure_date_range_selected, pattern=f"^{config.CALLBACK_PREFIX_STANDARD}dep_range_"), #
                CallbackQueryHandler(back_std_dep_range_to_month_handler, pattern=f"^{config.CB_BACK_STD_DEP_RANGE_TO_MONTH}$") #
            ],
            config.S_SELECTING_DEPARTURE_DATE: [ #
                CallbackQueryHandler(standard_departure_date_selected, pattern=f"^{config.CALLBACK_PREFIX_STANDARD}dep_date_"), #
                CallbackQueryHandler(back_std_dep_date_to_range_handler, pattern=f"^{config.CB_BACK_STD_DEP_DATE_TO_RANGE}$") #
            ],
            config.S_SELECTING_ARRIVAL_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, standard_arrival_country)], #
            config.S_SELECTING_ARRIVAL_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, standard_arrival_city)], #

            config.S_SELECTING_RETURN_YEAR: [ #
                CallbackQueryHandler(standard_return_year_selected, pattern=f"^{config.CALLBACK_PREFIX_STANDARD}ret_year_"), #
                CallbackQueryHandler(back_std_ret_year_to_arr_city_handler, pattern=f"^{config.CB_BACK_STD_RET_YEAR_TO_ARR_CITY}$") #
            ],
            config.S_SELECTING_RETURN_MONTH: [ #
                CallbackQueryHandler(standard_return_month_selected, pattern=f"^{config.CALLBACK_PREFIX_STANDARD}ret_month_"), #
                CallbackQueryHandler(back_std_ret_month_to_year_handler, pattern=f"^{config.CB_BACK_STD_RET_MONTH_TO_YEAR}$") #
            ],
            config.S_SELECTING_RETURN_DATE_RANGE: [ #
                CallbackQueryHandler(standard_return_date_range_selected, pattern=f"^{config.CALLBACK_PREFIX_STANDARD}ret_range_"), #
                CallbackQueryHandler(back_std_ret_range_to_month_handler, pattern=f"^{config.CB_BACK_STD_RET_RANGE_TO_MONTH}$") #
            ],
            config.S_SELECTING_RETURN_DATE: [ #
                CallbackQueryHandler(standard_return_date_selected, pattern=f"^{config.CALLBACK_PREFIX_STANDARD}ret_date_"), #
                CallbackQueryHandler(back_std_ret_date_to_range_handler, pattern=f"^{config.CB_BACK_STD_RET_DATE_TO_RANGE}$") #
            ],

            # --- Гибкий поиск ---
            config.SELECTING_FLEX_FLIGHT_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, flex_flight_type)], #
            config.ASK_FLEX_DEPARTURE_AIRPORT: [ #
                CallbackQueryHandler(flex_ask_departure_airport, pattern=f"^{config.CALLBACK_PREFIX_FLEX}ask_dep_"), #
                CallbackQueryHandler(back_flex_ask_dep_to_price_handler, pattern=f"^{config.CB_BACK_FLEX_ASK_DEP_TO_PRICE}$") #
            ],
            config.SELECTING_FLEX_DEPARTURE_COUNTRY: [ #
                MessageHandler(filters.TEXT & ~filters.COMMAND, flex_departure_country), #
                # Кнопка "Назад" для ReplyKeyboard обычно обрабатывается через /cancel или неявный возврат при ошибке
            ],
            config.SELECTING_FLEX_DEPARTURE_CITY: [ #
                MessageHandler(filters.TEXT & ~filters.COMMAND, flex_departure_city), #
            ],
            config.ASK_FLEX_ARRIVAL_AIRPORT: [ #
                CallbackQueryHandler(flex_ask_arrival_airport, pattern=f"^{config.CALLBACK_PREFIX_FLEX}ask_arr_"), #
                CallbackQueryHandler(back_flex_ask_arr_to_dep_city_handler, pattern=f"^{config.CB_BACK_FLEX_ASK_ARR_TO_DEP_CITY}$") #
            ],
            config.SELECTING_FLEX_ARRIVAL_COUNTRY: [ #
                MessageHandler(filters.TEXT & ~filters.COMMAND, flex_arrival_country), #
            ],
            config.SELECTING_FLEX_ARRIVAL_CITY: [ #
                MessageHandler(filters.TEXT & ~filters.COMMAND, flex_arrival_city), #
            ],
            config.ASK_FLEX_DATES: [ #
                CallbackQueryHandler(flex_ask_dates, pattern=f"^(?:{config.CALLBACK_PREFIX_FLEX}ask_dates_yes|{config.CALLBACK_NO_SPECIFIC_DATES})$"), #
                CallbackQueryHandler(back_flex_ask_dates_to_location_handler, pattern=f"^{config.CB_BACK_FLEX_ASK_DATES_TO_ARR_CITY}$"), #
                CallbackQueryHandler(back_flex_ask_dates_to_location_handler, pattern=f"^{config.CB_BACK_FLEX_ASK_DATES_TO_DEP_CITY_NO_ARR}$") #
            ],
            config.SELECTING_FLEX_DEPARTURE_YEAR: [ #
                CallbackQueryHandler(flex_departure_year_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}dep_year_"), #
                CallbackQueryHandler(back_flex_dep_year_to_ask_dates_handler, pattern=f"^{config.CB_BACK_FLEX_DEP_YEAR_TO_ASK_DATES}$") #
            ],
            config.SELECTING_FLEX_DEPARTURE_MONTH: [ #
                CallbackQueryHandler(flex_departure_month_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}dep_month_"), #
                CallbackQueryHandler(back_flex_dep_month_to_year_handler, pattern=f"^{config.CB_BACK_FLEX_DEP_MONTH_TO_YEAR}$") #
            ],
            config.SELECTING_FLEX_DEPARTURE_DATE_RANGE: [ #
                CallbackQueryHandler(flex_departure_date_range_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}dep_range_"), #
                CallbackQueryHandler(back_flex_dep_range_to_month_handler, pattern=f"^{config.CB_BACK_FLEX_DEP_RANGE_TO_MONTH}$") #
            ],
            config.SELECTING_FLEX_DEPARTURE_DATE: [ #
                CallbackQueryHandler(flex_departure_date_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}dep_date_"), #
                CallbackQueryHandler(back_flex_dep_date_to_range_handler, pattern=f"^{config.CB_BACK_FLEX_DEP_DATE_TO_RANGE}$") #
            ],
            config.SELECTING_FLEX_RETURN_YEAR: [ #
                CallbackQueryHandler(flex_return_year_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}ret_year_"), #
                CallbackQueryHandler(back_flex_ret_year_to_dep_date_handler, pattern=f"^{config.CB_BACK_FLEX_RET_YEAR_TO_DEP_DATE}$") #
            ],
            config.SELECTING_FLEX_RETURN_MONTH: [ #
                CallbackQueryHandler(flex_return_month_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}ret_month_"), #
                CallbackQueryHandler(back_flex_ret_month_to_year_handler, pattern=f"^{config.CB_BACK_FLEX_RET_MONTH_TO_YEAR}$") #
            ],
            config.SELECTING_FLEX_RETURN_DATE_RANGE: [ #
                CallbackQueryHandler(flex_return_date_range_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}ret_range_"), #
                CallbackQueryHandler(back_flex_ret_range_to_month_handler, pattern=f"^{config.CB_BACK_FLEX_RET_RANGE_TO_MONTH}$") #
            ],
            config.SELECTING_FLEX_RETURN_DATE: [ #
                CallbackQueryHandler(flex_return_date_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}ret_date_"), #
                CallbackQueryHandler(back_flex_ret_date_to_range_handler, pattern=f"^{config.CB_BACK_FLEX_RET_DATE_TO_RANGE}$") #
            ],

            # --- ОБЩИЕ СОСТОЯНИЯ ДЛЯ ЦЕНЫ ---
            config.SELECTING_PRICE_OPTION: [ #
                CallbackQueryHandler(handle_price_option_selected, pattern=price_option_pattern), #
                CallbackQueryHandler(back_price_to_std_arr_city_oneway_handler, pattern=f"^{config.CB_BACK_PRICE_TO_STD_ARR_CITY_ONEWAY}$"), #
                CallbackQueryHandler(back_price_to_std_ret_date_twoway_handler, pattern=f"^{config.CB_BACK_PRICE_TO_STD_RET_DATE_TWOWAY}$"), #
                CallbackQueryHandler(back_price_to_flex_flight_type_handler, pattern=f"^{config.CB_BACK_PRICE_TO_FLEX_FLIGHT_TYPE}$"), #
                CallbackQueryHandler(back_price_to_entering_custom_handler, pattern=f"^{config.CB_BACK_PRICE_TO_ENTERING_CUSTOM}$") #
            ],
            config.ENTERING_CUSTOM_PRICE: [ #
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_custom_price_handler), #
                # "Назад" отсюда обрабатывается при неверном вводе цены, показывая снова опции цены
                CallbackQueryHandler(back_price_to_entering_custom_handler, pattern=f"^{config.CB_BACK_PRICE_TO_ENTERING_CUSTOM}$") #
            ],

            config.ASK_SEARCH_OTHER_AIRPORTS: [ #
                CallbackQueryHandler(handle_search_other_airports_decision, pattern=f"^{config.CALLBACK_YES_OTHER_AIRPORTS}$|^{config.CALLBACK_NO_OTHER_AIRPORTS}$") #
            ],
        },
        fallbacks=[
            CommandHandler('cancel', cancel_handler), #
            # Отлов "неправильных" нажатий на кнопки цен, если диалог не в том состоянии
            CallbackQueryHandler(handle_invalid_price_choice_fallback, pattern=price_fallback_pattern), #
            # Отлов callback_data от неактуальных клавиатур (например, если пользователь долго думал)
            CallbackQueryHandler(lambda u, c: u.callback_query.answer("Нет доступных опций.", show_alert=True), pattern="^no_valid_months_error$"), #
            CallbackQueryHandler(lambda u, c: u.callback_query.answer("Нет доступных опций.", show_alert=True), pattern="^no_valid_dates_error$"), #
            CallbackQueryHandler(lambda u, c: u.callback_query.answer("Нет доступных опций.", show_alert=True), pattern="^no_specific_dates_in_range_error$"), #
            CallbackQueryHandler(lambda u, c: u.callback_query.answer("Нет доступных опций.", show_alert=True), pattern="^no_valid_date_ranges_error$"), #
            CallbackQueryHandler(lambda u, c: u.callback_query.answer("Нет доступных опций.", show_alert=True), pattern="^no_dates$"), #

        ],
        map_to_parent={}, #
        per_message=False, #
        allow_reentry=True, #
    )
    return conv_handler