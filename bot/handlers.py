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
from . import user_history
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
    CB_BACK_FLEX_RET_RANGE_TO_MONTH, CB_BACK_FLEX_RET_DATE_TO_RANGE,
    ASK_SAVE_SEARCH_PREFERENCES,
    CALLBACK_SAVE_SEARCH_YES, # Для определения в ConversationHandler, если паттерн используется там напрямую
    CALLBACK_SAVE_SEARCH_NO,  # Аналогично
    CALLBACK_START_LAST_SAVED_SEARCH, # Для entry_points в ConversationHandler
    CALLBACK_ENTIRE_RANGE_SELECTED
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

# В файле /app/bot/handlers.py

async def ask_specific_date(source_update_or_query: Union[Update, CallbackQuery, Any], # Тип параметра обновлен
                            context: ContextTypes.DEFAULT_TYPE,
                            year: int, month: int, range_start: int, range_end: int,
                            message_text: str, callback_prefix: str = "",
                            min_allowed_date_for_comparison: Union[datetime, None] = None,
                            keyboard_back_callback: str | None = None,
                            # ДОБАВЬТЕ ЭТОТ ПАРАМЕТР:
                            range_selection_type: str = "dep" # "dep" или "ret" - значение по умолчанию "dep"
                           ):
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
                reply_markup=keyboards.generate_specific_date_buttons( # <--- ЗДЕСЬ ПЕРЕДАЕМ range_selection_type
                    year, month, range_start, range_end,
                    callback_prefix=callback_prefix,
                    min_allowed_date=min_allowed_date_for_comparison,
                    back_callback_data=keyboard_back_callback,
                    range_selection_type=range_selection_type # <--- ПЕРЕДАЧА НОВОГО ПАРАМЕТРА
                )
            )
            logger.info("ask_specific_date: Отправлено новое сообщение вместо редактирования.")
        return

    try:
        await query_to_edit.edit_message_text(
            text=message_text,
            reply_markup=keyboards.generate_specific_date_buttons( # <--- И ЗДЕСЬ ПЕРЕДАЕМ range_selection_type
                year, month, range_start, range_end,
                callback_prefix=callback_prefix,
                min_allowed_date=min_allowed_date_for_comparison,
                back_callback_data=keyboard_back_callback,
                range_selection_type=range_selection_type # <--- ПЕРЕДАЧА НОВОГО ПАРАМЕТРА
            )
        )
    except Exception as e:
        logger.error(f"ask_specific_date: Ошибка при редактировании сообщения: {e}")
        if query_to_edit.message and query_to_edit.message.chat_id:
            try:
                await context.bot.send_message(
                    chat_id=query_to_edit.message.chat_id,
                    text=message_text,
                    reply_markup=keyboards.generate_specific_date_buttons( # <--- И ЗДЕСЬ ПЕРЕДАЕМ range_selection_type
                        year, month, range_start, range_end,
                        callback_prefix=callback_prefix,
                        min_allowed_date=min_allowed_date_for_comparison,
                        back_callback_data=keyboard_back_callback,
                        range_selection_type=range_selection_type # <--- ПЕРЕДАЧА НОВОГО ПАРАМЕТРА
                    )
                )
            except Exception as e_send:
                logger.error(f"ask_specific_date: Ошибка и при отправке нового сообщения: {e_send}")

# --- ОСНОВНЫЕ ОБРАБОТЧИКИ ---
# bot/handlers.py
# ... (после ask_... функций) ...

# ПОЛНОСТЬЮ ИСПРАВЛЕННЫЙ МЕТОД launch_flight_search
async def launch_flight_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Собирает параметры из context.user_data, вызывает API поиска рейсов
    и передает результат в process_and_send_flights.
    """
    effective_chat_id = update.effective_chat.id if update.effective_chat else None
    if not effective_chat_id and update.callback_query and update.callback_query.message:
        effective_chat_id = update.callback_query.message.chat_id

    try:
        dep_iata: Union[str, None] = context.user_data.get('departure_airport_iata')
        arr_iata: Union[str, None] = context.user_data.get('arrival_airport_iata')
        user_max_price: Union[Decimal, None] = context.user_data.get('max_price')
        price_preference: Union[PriceChoice, None] = context.user_data.get('price_preference_choice')
        is_one_way: bool = context.user_data.get('flight_type_one_way', True)
        current_flow: Union[str, None] = context.user_data.get('current_search_flow')

        # --- Новая логика для дат ---
        # Даты вылета
        single_dep_date_str: Union[str, None] = context.user_data.get('departure_date')
        is_dep_range_search: bool = context.user_data.get('is_departure_range_search', False)
        explicit_dep_date_from: Union[str, None] = context.user_data.get('departure_date_from') if is_dep_range_search else None
        explicit_dep_date_to: Union[str, None] = context.user_data.get('departure_date_to') if is_dep_range_search else None
        
        # Если выбран диапазон, то single_dep_date_str для find_flights_with_fallback должен быть None,
        # чтобы не активировать логику +/- offset для одиночной даты.
        # Параметр departure_date_str в find_flights_with_fallback теперь используется только для +/- offset или годового поиска.
        dep_date_for_offset_or_year_search = single_dep_date_str if not is_dep_range_search else None

        # Даты возврата
        single_ret_date_str: Union[str, None] = None
        is_ret_range_search: bool = False
        explicit_ret_date_from: Union[str, None] = None
        explicit_ret_date_to: Union[str, None] = None
        ret_date_for_offset_search = None

        if not is_one_way:
            single_ret_date_str = context.user_data.get('return_date')
            is_ret_range_search = context.user_data.get('is_return_range_search', False)
            explicit_ret_date_from = context.user_data.get('return_date_from') if is_ret_range_search else None
            explicit_ret_date_to = context.user_data.get('return_date_to') if is_ret_range_search else None
            ret_date_for_offset_search = single_ret_date_str if not is_ret_range_search else None
        # --- Конец новой логики для дат ---

        logger.info(
            "Запуск launch_flight_search. Параметры: price_pref=%s, user_max_price=%s, dep_iata=%s, arr_iata=%s, "
            "single_dep_date=%s, is_dep_range=%s, dep_range_from=%s, dep_range_to=%s, "
            "single_ret_date=%s, is_ret_range=%s, ret_range_from=%s, ret_range_to=%s, "
            "one_way=%s, current_flow=%s",
            price_preference, user_max_price, dep_iata, arr_iata, 
            single_dep_date_str, is_dep_range_search, explicit_dep_date_from, explicit_dep_date_to,
            single_ret_date_str, is_ret_range_search, explicit_ret_date_from, explicit_ret_date_to,
            is_one_way, current_flow
        )

        if not dep_iata: # Минимальная валидация
            msg = "Ошибка: Аэропорт вылета не был указан для запуска поиска. Начните заново: /start"
            # ... (существующая логика отправки сообщения об ошибке) ...
            return ConversationHandler.END
        
        if effective_chat_id: # Отправляем сообщение о начале поиска
            await context.bot.send_message(chat_id=effective_chat_id, text=config.MSG_SEARCHING_FLIGHTS)

        all_flights_data: Dict[str, list] = await flight_api.find_flights_with_fallback(
            departure_airport_iata=dep_iata,
            arrival_airport_iata=arr_iata,
            departure_date_str=dep_date_for_offset_or_year_search, # Для +/- offset или годового поиска
            max_price=user_max_price,
            return_date_str=ret_date_for_offset_search, # Для +/- offset
            is_one_way=is_one_way,
            # Новые параметры для явного диапазона
            explicit_departure_date_from=explicit_dep_date_from,
            explicit_departure_date_to=explicit_dep_date_to,
            explicit_return_date_from=explicit_ret_date_from,
            explicit_return_date_to=explicit_ret_date_to
        )

        logger.info(f"API flight_api.find_flights_with_fallback вернул: {'Данные есть (ключи: ' + str(list(all_flights_data.keys())) + ')' if isinstance(all_flights_data, dict) and all_flights_data else 'Пустой результат или не словарь'}")
        if not isinstance(all_flights_data, dict):
             logger.warning(f"find_flights_with_fallback вернул не словарь: {type(all_flights_data)}")
             all_flights_data = {}

        final_flights_to_show: Dict[str, list]
        if price_preference == config.CALLBACK_PRICE_LOWEST and all_flights_data:
            final_flights_to_show = helpers.filter_cheapest_flights(all_flights_data)
            logger.info(f"После filter_cheapest_flights для 'lowest': {'Данные есть' if final_flights_to_show else 'Пусто'}")
        else: 
            final_flights_to_show = all_flights_data
            logger.info(f"Для '{price_preference}': используются все полученные рейсы ({'Данные есть' if final_flights_to_show else 'Пусто'})")

        return await process_and_send_flights(update, context, final_flights_to_show)

    except Exception as e:
        logger.error(f"Критическая ошибка в launch_flight_search: {e}", exc_info=True)
        error_msg = config.MSG_ERROR_OCCURRED + " (launch_fs). Пожалуйста, попробуйте /start."
        # ... (ваша существующая логика обработки ошибок и отправки сообщения пользователю) ...
        return ConversationHandler.END

# bot/handlers.py
# ... (после launch_flight_search) ...

async def process_and_send_flights(update: Update, context: ContextTypes.DEFAULT_TYPE, flights_by_date: Dict[str, list]) -> int:
    chat_id = update.effective_chat.id if update.effective_chat else None
    if not chat_id and update.callback_query and update.callback_query.message:
        chat_id = update.callback_query.message.chat_id
    
    if not chat_id:
        logger.error("process_and_send_flights: Не удалось определить chat_id.")
        return ConversationHandler.END # Или другая обработка ошибки

    # context.user_data.pop('remaining_flights_to_show', None) # Если у вас была такая переменная

    if not flights_by_date or not any(flights_by_date.values()): # Если словарь пуст или все списки в нем пусты
        await context.bot.send_message(chat_id=chat_id, text=config.MSG_NO_FLIGHTS_FOUND)
        
        # Проверка возможности поиска из других аэропортов
        dep_country = context.user_data.get('departure_country')
        dep_airport_iata = context.user_data.get('departure_airport_iata')
        
        if dep_country and dep_airport_iata and \
           config.COUNTRIES_DATA.get(dep_country) and \
           len(config.COUNTRIES_DATA[dep_country]) > 1 and \
           not context.user_data.get("_already_searched_alternatives", False):
            
            text_ask_other_airports = f"Хотите поискать вылеты из других аэропортов в стране {dep_country} по этому же направлению и датам?"
            await context.bot.send_message(
                chat_id=chat_id,
                text=text_ask_other_airports,
                reply_markup=keyboards.get_search_other_airports_keyboard(dep_country)
            )
            return config.ASK_SEARCH_OTHER_AIRPORTS # <--- ИЗМЕНЕНИЕ: переход к вопросу о других аэропортах
        else:
            # Если альтернативный поиск не предлагается, сразу переходим к вопросу о сохранении
            await context.bot.send_message(
                chat_id=chat_id,
                text=config.MSG_ASK_SAVE_SEARCH,
                reply_markup=keyboards.get_save_search_keyboard()
            )
            return config.ASK_SAVE_SEARCH_PREFERENCES # <--- ИЗМЕНЕНИЕ: Новый стейт
    else: # Рейсы найдены
        await context.bot.send_message(chat_id=chat_id, text=config.MSG_FLIGHTS_FOUND_SEE_BELOW)
        
        # ВАША СУЩЕСТВУЮЩАЯ ЛОГИКА ФОРМАТИРОВАНИЯ И ОТПРАВКИ НАЙДЕННЫХ РЕЙСОВ
        all_flights_with_original_date = []
        for date_str, flights_list_item in flights_by_date.items(): # Изменил имя переменной, чтобы не конфликтовать
            for flight_obj in flights_list_item:
                all_flights_with_original_date.append({'original_date_str': date_str, 'flight': flight_obj})

        globally_sorted_flights_with_date = sorted(all_flights_with_original_date, key=lambda x: helpers.get_flight_price(x['flight']))

        flights_message_parts = []
        last_printed_date_str = None
        departure_city_name_for_weather = context.user_data.get('departure_city_name')
        arrival_city_name_for_weather = context.user_data.get('arrival_city_name')

        for item in globally_sorted_flights_with_date:
            flight = item['flight']
            original_date_str = item['original_date_str']
            if original_date_str != last_printed_date_str:
                try:
                    date_obj = datetime.strptime(original_date_str, "%Y-%m-%d")
                    formatted_date_header = f"\n--- 📅 {date_obj.strftime('%d %B %Y (%A)')} ---\n"
                    flights_message_parts.append(formatted_date_header)
                    last_printed_date_str = original_date_str
                except ValueError:
                    formatted_date_header = f"\n--- 📅 {original_date_str} ---\n"
                    flights_message_parts.append(formatted_date_header)
                    last_printed_date_str = original_date_str
            
            formatted_flight_msg = await message_formatter.format_flight_details(
                flight,
                departure_city_name=departure_city_name_for_weather,
                arrival_city_name=arrival_city_name_for_weather
            )
            flights_message_parts.append(formatted_flight_msg)
        
        if flights_message_parts:
            full_text = "".join(flights_message_parts)
            if not full_text.strip(): # Если после форматирования ничего не осталось
                await context.bot.send_message(chat_id=chat_id, text=config.MSG_NO_FLIGHTS_FOUND) 
            else:
                max_telegram_message_length = 4096
                for i in range(0, len(full_text), max_telegram_message_length):
                    chunk = full_text[i:i + max_telegram_message_length]
                    try:
                        await context.bot.send_message(chat_id=chat_id, text=chunk, parse_mode="HTML", disable_web_page_preview=True)
                    except Exception as e_send_chunk:
                        logger.error(f"Не удалось отправить чанк рейсов: {e_send_chunk}")
                        if i == 0: 
                             await context.bot.send_message(chat_id=chat_id, text="Произошла ошибка при отображении части результатов.")
        else: # Если flights_message_parts пуст (маловероятно, если flights_by_date не пуст)
            await context.bot.send_message(chat_id=chat_id, text=config.MSG_NO_FLIGHTS_FOUND)

        # После отображения результатов - предлагаем сохранить поиск
        await context.bot.send_message(
            chat_id=chat_id,
            text=config.MSG_ASK_SAVE_SEARCH,
            reply_markup=keyboards.get_save_search_keyboard()
        )
        return config.ASK_SAVE_SEARCH_PREFERENCES # <--- ИЗМЕНЕНИЕ: Новый стейт

async def prompt_new_search_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query: 
        logger.warning("prompt_new_search_type_callback вызван без query")
        return
    await query.answer()
    context.user_data.clear()

    user_id = update.effective_user.id
    has_searches = await user_history.has_saved_searches(user_id) # <--- await
    main_menu_kbd = keyboards.get_main_menu_keyboard(has_saved_searches=has_searches)

    target_chat_id = query.message.chat_id if query.message else (update.effective_chat.id if update.effective_chat else None)

    if target_chat_id:
        if query.message: 
            try:
                await query.edit_message_text(text=config.MSG_WELCOME, reply_markup=main_menu_kbd)
            except Exception as e: 
                logger.warning(f"Не удалось отредактировать сообщение в prompt_new_search_type_callback: {e}")
                # Если редактирование не удалось, отправляем новое сообщение
                await context.bot.send_message(chat_id=target_chat_id, text=config.MSG_WELCOME, reply_markup=main_menu_kbd)
        else: # Если query.message нет (например, сообщение было удалено), отправляем новое
            await context.bot.send_message(chat_id=target_chat_id, text=config.MSG_WELCOME, reply_markup=main_menu_kbd)
    else:
        logger.warning("prompt_new_search_type_callback: не удалось определить чат для ответа.")


async def end_search_session_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    context.user_data.clear()

    donate_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("💸 Донат в USDT (TRC-20)", url="https://tronscan.org/#/address/TZ6rTYbF5Go94Q4f9uZwcVZ4g3oAnzwDHN")],
        [InlineKeyboardButton("⚡ Донат в TON", url="https://tonviewer.com/UQB0W1KEAR7RFQ03AIA872jw-2G2ntydiXlyhfTN8rAb2KN5")],
        [InlineKeyboardButton("✉️ Связаться с автором", url="https://t.me/Criptonius")]
    ])

    final_text = (
        "Поиск завершён. Если понадоблюсь — вы знаете, где меня найти! /start\n\n"
        "☕ Понравился бот? Поддержи проект донатом:"
    )

    if query.message:
        await query.edit_message_text(text=final_text, reply_markup=donate_keyboard, parse_mode="HTML")
    elif update.effective_chat:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=final_text, reply_markup=donate_keyboard, parse_mode="HTML")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    user_id = update.effective_user.id
    has_searches = await user_history.has_saved_searches(user_id) # <--- await
    main_menu_keyboard = keyboards.get_main_menu_keyboard(has_saved_searches=has_searches)
    chat_id = update.effective_chat.id if update.effective_chat else None
    
    image_sent_successfully = False
    welcome_image_path = getattr(config, 'WELCOME_IMAGE_PATH', None)

    if chat_id and welcome_image_path and os.path.exists(welcome_image_path):
        try:
            with open(welcome_image_path, 'rb') as photo_file:
                await context.bot.send_photo(chat_id=chat_id, photo=photo_file)
            image_sent_successfully = True
        except Exception as e:
            logger.error(f"Ошибка при отправке приветственного изображения: {e}")

    if not chat_id: # Если chat_id не удалось определить
        logger.warning("start_command: не удалось определить chat_id для ответа.")
        # Можно попытаться извлечь из update.message или update.callback_query, если они есть
        if update.message: chat_id = update.message.chat_id
        elif update.callback_query and update.callback_query.message: chat_id = update.callback_query.message.chat_id
        if not chat_id: return # Если все еще нет, выходим

    if update.message:
        await update.message.reply_text(config.MSG_WELCOME, reply_markup=main_menu_keyboard)
    elif update.callback_query:
        await update.callback_query.answer()
        target_chat_id_cb = update.callback_query.message.chat_id if update.callback_query.message else chat_id # Используем chat_id из сообщения callback'а или ранее определенный
        if target_chat_id_cb: # Убедимся, что chat_id есть
            if update.callback_query.message: # Если есть сообщение для редактирования/удаления
                if image_sent_successfully:
                    await context.bot.send_message(chat_id=target_chat_id_cb, text=config.MSG_WELCOME, reply_markup=main_menu_keyboard)
                    try:
                        await update.callback_query.message.delete()
                    except Exception as e:
                        logger.warning(f"Не удалось удалить предыдущее сообщение (callback): {e}")
                else:
                    try:
                        await update.callback_query.edit_message_text(config.MSG_WELCOME, reply_markup=main_menu_keyboard)
                    except Exception as e:
                        logger.warning(f"Не удалось отредактировать сообщение в start_command (callback): {e}. Отправка нового.")
                        await context.bot.send_message(chat_id=target_chat_id_cb, text=config.MSG_WELCOME, reply_markup=main_menu_keyboard)
            else: # Если у callback_query нет message, просто отправляем новое
                await context.bot.send_message(chat_id=target_chat_id_cb, text=config.MSG_WELCOME, reply_markup=main_menu_keyboard)
        else:
            logger.warning("start_command (callback): не удалось определить chat_id для ответа.")


async def start_search_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    # Проверка, что query существует, добавлена для надежности
    if not query: 
        logger.warning("start_search_callback вызван без query.")
        return ConversationHandler.END
        
    await query.answer()
    context.user_data.clear() # Очищаем данные предыдущей сессии

    chat_id_to_send = update.effective_chat.id if update.effective_chat else None
    if query.message and not chat_id_to_send: # Дополнительное получение chat_id если основной не сработал
        chat_id_to_send = query.message.chat_id
    
    if not chat_id_to_send:
        logger.error("start_search_callback: не удалось определить chat_id для ответа.")
        return ConversationHandler.END

    if query.message:
        try:
            if query.data == "start_standard_search": 
                await query.edit_message_text(text="Выбран стандартный поиск.")
            elif query.data == "start_flex_search": 
                await query.edit_message_text(text="Выбран гибкий поиск.")
        except Exception as e: 
            logger.warning(f"Не удалось отредактировать сообщение в start_search_callback: {e}")
            # Если редактирование не удалось, все равно продолжаем, отправив новое сообщение ниже

    if query.data == "start_standard_search":
        context.user_data['current_search_flow'] = config.FLOW_STANDARD # <--- УСТАНАВЛИВАЕМ ТИП ПОТОКА
        await context.bot.send_message(
            chat_id=chat_id_to_send, 
            text=config.MSG_FLIGHT_TYPE_PROMPT, 
            reply_markup=keyboards.get_flight_type_reply_keyboard()
        )
        return config.S_SELECTING_FLIGHT_TYPE
    elif query.data == "start_flex_search":
        context.user_data['current_search_flow'] = config.FLOW_FLEX # <--- УСТАНАВЛИВАЕМ ТИП ПОТОКА
        await context.bot.send_message(
            chat_id=chat_id_to_send, 
            text=config.MSG_FLIGHT_TYPE_PROMPT, 
            reply_markup=keyboards.get_flight_type_reply_keyboard()
        )
        return config.SELECTING_FLEX_FLIGHT_TYPE
    elif query.data == "start_flex_anywhere":
        # current_search_flow устанавливается внутри start_flex_anywhere_callback
        return await start_flex_anywhere_callback(update, context) # type: ignore
        
    logger.warning(f"start_search_callback: неизвестные данные query.data: {query.data}")
    return ConversationHandler.END

async def start_flex_anywhere_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id_to_send = update.effective_chat.id if update.effective_chat else None
    edited_successfully = False
    if update.callback_query:
        query = update.callback_query
        if query.message:
            chat_id_to_send = query.message.chat_id
            try: 
                await query.edit_message_text(text="Выбран поиск \"Куда угодно\".")
                edited_successfully = True
            except Exception as e: logger.warning(f"Не удалось отредактировать сообщение в start_flex_anywhere_callback: {e}")
    
    if not chat_id_to_send:
        logger.error("start_flex_anywhere_callback: не удалось определить chat_id.")
        return ConversationHandler.END

    if not edited_successfully and not update.callback_query :
         await context.bot.send_message(chat_id=chat_id_to_send, text="Выбран поиск \"Куда угодно\".")

    context.user_data.clear()
    context.user_data['arrival_airport_iata'] = None
    context.user_data['departure_date'] = None
    context.user_data['return_date'] = None
    context.user_data['current_search_flow'] = config.FLOW_FLEX
    await context.bot.send_message(
        chat_id=chat_id_to_send,
        text=config.MSG_FLIGHT_TYPE_PROMPT,
        reply_markup=keyboards.get_flight_type_reply_keyboard()
    )
    return config.SELECTING_FLEX_FLIGHT_TYPE

# --- ВСЕ ВАШИ СУЩЕСТВУЮЩИЕ ОБРАБОТЧИКИ СОСТОЯНИЙ И "НАЗАД" ДОЛЖНЫ БЫТЬ ЗДЕСЬ ---
# (standard_flight_type, ..., flex_return_date_selected, back_std_..., back_flex_...)
# Это тот самый большой блок из ~60-70 функций из вашего файла от 1 июня.
# Я НЕ МОГУ ИХ ЗДЕСЬ ПОВТОРИТЬ ИЗ-ЗА ОГРАНИЧЕНИЯ ДЛИНЫ.
# Убедитесь, что они все скопированы сюда из вашего оригинального файла handlers.py.

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

# bot/handlers.py
async def back_price_to_std_ret_date_twoway_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        logger.warning("back_price_to_std_ret_date_twoway_handler вызван без query")
        return ConversationHandler.END
    await query.answer()

    # Очищаем данные о выборе цены
    context.user_data.pop('price_preference_choice', None)
    context.user_data.pop('max_price', None)

    return_year = context.user_data.get('return_year')
    return_month = context.user_data.get('return_month')

    start_day: int | None = None
    end_day: int | None = None

    # Пытаемся получить start_day и end_day для диапазона дат возврата
    if context.user_data.get('is_return_range_search', False):
        # Если был выбран весь диапазон через handle_entire_range_selected
        date_from_str = context.user_data.get('return_date_from')
        date_to_str = context.user_data.get('return_date_to')
        if date_from_str and date_to_str:
            try:
                start_day = int(date_from_str.split('-')[2])
                end_day = int(date_to_str.split('-')[2])
            except (IndexError, ValueError, TypeError):
                logger.error(f"Ошибка парсинга дней из return_date_from/to: {date_from_str}, {date_to_str}")
    else:
        # Если пользователь выбирал диапазон (1-10, 11-20 и т.д.) перед выбором конкретной даты
        range_str = context.user_data.get('return_date_range_str')
        if range_str:
            try:
                start_day_parsed, end_day_parsed = map(int, range_str.split('-'))
                start_day = start_day_parsed
                end_day = end_day_parsed
            except ValueError:
                logger.error(f"Ошибка парсинга return_date_range_str: '{range_str}'")

    # Получаем дату вылета для сравнения (min_allowed_date для возврата)
    departure_date_to_compare_str: str | None = None
    if context.user_data.get('is_departure_range_search', False):
        departure_date_to_compare_str = context.user_data.get('departure_date_from')
    else:
        departure_date_to_compare_str = context.user_data.get('departure_date')
    
    departure_date_obj: datetime | None = None
    if departure_date_to_compare_str:
        departure_date_obj = helpers.validate_date_format(departure_date_to_compare_str)

    # Проверяем наличие всех необходимых данных для вызова ask_specific_date
    if not all([return_year, return_month, start_day is not None, end_day is not None, departure_date_obj]):
        missing_parts = []
        if not return_year: missing_parts.append("год возврата")
        if not return_month: missing_parts.append("месяц возврата")
        if start_day is None or end_day is None: missing_parts.append("диапазон дней возврата")
        if not departure_date_obj: missing_parts.append("дата вылета")
        
        logger.error(
            f"back_price_to_std_ret_date_twoway_handler: Не хватает данных для возврата к выбору даты. Отсутствуют: {', '.join(missing_parts)}. "
            f"UserData: {context.user_data}"
        )
        await query.edit_message_text(
            "Ошибка: не хватает данных для возврата к выбору даты. Пожалуйста, начните поиск заново: /start"
        )
        return ConversationHandler.END

    # Формируем сообщение и вызываем ask_specific_date
    month_name_rus = config.RUSSIAN_MONTHS.get(return_month, str(return_month))
    message_text_for_ask = f"Диапазон: {start_day:02d}-{end_day:02d} {month_name_rus} {return_year}. 🗓️ Выберите дату обратного вылета:"

    # Сначала редактируем сообщение, с которого пришла кнопка "Назад" (сообщение о выборе цены)
    try:
        await query.edit_message_text(
            text=f"Возврат к выбору даты возврата ({month_name_rus} {return_year}, диапазон {start_day:02d}-{end_day:02d})."
        )
    except Exception as e_edit:
        logger.warning(f"Не удалось отредактировать сообщение в back_price_to_std_ret_date_twoway_handler: {e_edit}")
        # Если редактирование не удалось, все равно пытаемся отправить новую клавиатуру

    # Затем отправляем новую клавиатуру для выбора конкретной даты (это может быть новое сообщение или часть ask_specific_date)
    await ask_specific_date(
        source_update_or_query=query, # query содержит message для edit_message_text в ask_specific_date
        context=context,
        year=return_year,
        month=return_month,
        range_start=start_day, # Используем полученные start_day
        range_end=end_day,     # и end_day
        message_text=message_text_for_ask,
        callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_date_",
        min_allowed_date_for_comparison=departure_date_obj, # Минимальная дата для возврата - это дата вылета
        keyboard_back_callback=config.CB_BACK_STD_RET_DATE_TO_RANGE, # Назад к выбору под-диапазона (1-10, 11-20 и т.д.)
        range_selection_type="ret"
    )
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

# bot/handlers.py
async def back_flex_ask_arr_to_dep_city_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        logger.warning("back_flex_ask_arr_to_dep_city_handler вызван без query")
        return ConversationHandler.END
    await query.answer()

    # --- НАЧАЛО ИСПРАВЛЕНИЙ ---
    # Очищаем ранее выбранный город вылета и его IATA код
    context.user_data.pop('departure_city_name', None)
    context.user_data.pop('departure_airport_iata', None)
    logger.info("Очищены данные о городе вылета при возврате к его выбору.")
    # --- КОНЕЦ ИСПРАВЛЕНИЙ ---

    country = context.user_data.get('departure_country')
    if not country:
        logger.error("back_flex_ask_arr_to_dep_city_handler: departure_country не найден в user_data.")
        if query.message:
            try:
                await query.edit_message_text("Критическая ошибка: страна вылета не определена. Пожалуйста, начните заново: /start")
            except Exception as e_edit:
                logger.error(f"Ошибка редактирования сообщения (страна не найдена): {e_edit}")
        return ConversationHandler.END

    # Удаляем сообщение, с которого была нажата кнопка "Назад" (например, "Указать аэропорт прилёта?")
    if query.message:
        try:
            await query.delete_message()
        except Exception as e_delete:
            logger.warning(f"Не удалось удалить сообщение в back_flex_ask_arr_to_dep_city_handler: {e_delete}. Попытка редактирования...")
            try:
                await query.edit_message_text("Возврат к выбору города вылета...")
            except Exception as e_edit_fallback:
                logger.warning(f"Не удалось отредактировать сообщение как fallback: {e_edit_fallback}")
                # Если и это не удалось, просто продолжаем, пользователь увидит новый запрос ниже

    # Отправляем новый запрос на выбор города с ReplyKeyboardMarkup
    # Это сообщение появится после предыдущего подтверждения "Город вылета: Berlin.", если оно не было удалено/отредактировано.
    chat_id_to_send = query.message.chat_id if query.message else update.effective_chat.id
    if chat_id_to_send:
        await context.bot.send_message(
            chat_id=chat_id_to_send,
            text="🏙️ Выберите город вылета:", # Запрос дублируется визуально, но состояние должно быть сброшено
            reply_markup=keyboards.get_city_reply_keyboard(country)
        )
    else:
        logger.error("back_flex_ask_arr_to_dep_city_handler: Не удалось определить chat_id для отправки сообщения.")
        # Можно рассмотреть возврат ConversationHandler.END, если chat_id критичен
        # и его не удалось получить (хотя из query.message он обычно доступен)

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
                            keyboard_back_callback=config.CB_BACK_STD_DEP_DATE_TO_RANGE,
                            range_selection_type="dep")
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
                                        keyboard_back_callback=config.CB_BACK_STD_DEP_DATE_TO_RANGE,
                                        range_selection_type="dep")
                return config.S_SELECTING_DEPARTURE_DATE
            except ValueError: pass # Ошибка в range_str, провалится ниже
        await query.edit_message_text("Ошибка даты. Начните /start.")
        return ConversationHandler.END


    context.user_data['departure_date'] = selected_date_str
    # ОЧИСТКА ДАННЫХ ДИАПАЗОНА
    context.user_data.pop('departure_date_from', None)
    context.user_data.pop('departure_date_to', None)
    context.user_data.pop('is_departure_range_search', None)
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
        dep_year_comp = context.user_data.get('departure_year') # Используется для обратного вызова ask_month
        dep_month_comp = context.user_data.get('departure_month') # Используется для обратного вызова ask_month
        if year:
            await ask_month(update, context, year, f"Год обратного вылета: {year}. Выберите месяц:",
                            config.CALLBACK_PREFIX_STANDARD + "ret_month_",
                            # Эти параметры для departure_year/month_for_comparison в ask_month
                            # относятся к тому, чтобы не дать выбрать месяц возврата раньше месяца вылета, если год тот же.
                            departure_year_for_comparison=dep_year_comp if year == dep_year_comp else None, 
                            departure_month_for_comparison=dep_month_comp if year == dep_year_comp else None,
                            keyboard_back_callback=config.CB_BACK_STD_RET_MONTH_TO_YEAR)
            return config.S_SELECTING_RETURN_MONTH
        return ConversationHandler.END

    context.user_data['return_date_range_str'] = selected_range_str
    year = context.user_data['return_year']
    month = context.user_data['return_month']

    # --- ИЗМЕНЕНИЕ ЛОГИКИ ПОЛУЧЕНИЯ ДАТЫ ВЫЛЕТА ---
    departure_date_to_compare_str: str | None = None
    if context.user_data.get('is_departure_range_search', False):
        # Если для вылета был выбран диапазон, используем его начальную дату для сравнения
        departure_date_to_compare_str = context.user_data.get('departure_date_from')
    else:
        # Иначе используем одиночную дату вылета
        departure_date_to_compare_str = context.user_data.get('departure_date')

    if not departure_date_to_compare_str: # Если даты вылета все еще нет (не должно быть на этом этапе)
        await query.edit_message_text("Ошибка: дата вылета не найдена для сравнения. Начните поиск заново /start.")
        logger.error("standard_return_date_range_selected: Отсутствует дата вылета (departure_date или departure_date_from).")
        return ConversationHandler.END
        
    departure_date_obj = helpers.validate_date_format(departure_date_to_compare_str)
    # --- КОНЕЦ ИЗМЕНЕНИЯ ЛОГИКИ ---

    if not departure_date_obj: # Если дата вылета невалидна (не должно быть, если логика до этого верна)
        await query.edit_message_text("Ошибка: дата вылета некорректна. Начните поиск заново /start.")
        logger.error(f"standard_return_date_range_selected: Не удалось валидировать дату вылета: {departure_date_to_compare_str}")
        return ConversationHandler.END

    await ask_specific_date(update, context, year, month, start_day, end_day,
                            f"Диапазон: {selected_range_str}. Выберите дату возврата:",
                            callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_date_",
                            min_allowed_date_for_comparison=departure_date_obj, # Минимальная дата для возврата - это дата вылета
                            keyboard_back_callback=config.CB_BACK_STD_RET_DATE_TO_RANGE,
                            range_selection_type="ret")
    return config.S_SELECTING_RETURN_DATE

async def standard_return_date_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    selected_date_str = query.data.replace(config.CALLBACK_PREFIX_STANDARD + "ret_date_", "")
    return_date_obj = helpers.validate_date_format(selected_date_str)

    # --- ИЗМЕНЕНИЕ ЛОГИКИ ПОЛУЧЕНИЯ ДАТЫ ВЫЛЕТА ---
    departure_date_to_compare_str: str | None = None
    if context.user_data.get('is_departure_range_search', False):
        departure_date_to_compare_str = context.user_data.get('departure_date_from')
    else:
        departure_date_to_compare_str = context.user_data.get('departure_date')

    if not departure_date_to_compare_str:
        await query.edit_message_text("Ошибка: дата вылета не найдена для сравнения. Начните поиск заново /start.")
        logger.error("standard_return_date_selected: Отсутствует дата вылета (departure_date или departure_date_from).")
        return ConversationHandler.END

    departure_date_obj = helpers.validate_date_format(departure_date_to_compare_str)
    # --- КОНЕЦ ИЗМЕНЕНИЯ ЛОГИКИ ---
    
    if not departure_date_obj:
        await query.edit_message_text("Ошибка: дата вылета некорректна. Начните поиск заново /start.")
        logger.error(f"standard_return_date_selected: Не удалось валидировать дату вылета: {departure_date_to_compare_str}")
        return ConversationHandler.END

    if not return_date_obj or return_date_obj < departure_date_obj: # Проверка, что дата возврата не раньше даты вылета
        year = context.user_data.get('return_year')
        month = context.user_data.get('return_month')
        range_str = context.user_data.get('return_date_range_str') # Диапазон, из которого выбирали
        if year and month and range_str: # Убедимся, что эти данные есть
             try:
                 start_day, end_day = map(int, range_str.split('-'))
                 await query.edit_message_text("Некорректная дата или раньше даты вылета. Попробуйте снова.")
                 await ask_specific_date(update, context, year, month, start_day, end_day,
                                        f"Диапазон: {range_str}. Выберите дату возврата:",
                                        callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_date_",
                                        min_allowed_date_for_comparison=departure_date_obj,
                                        keyboard_back_callback=config.CB_BACK_STD_RET_DATE_TO_RANGE,
                                        range_selection_type="ret")
                 return config.S_SELECTING_RETURN_DATE
             except ValueError as e:
                 logger.error(f"Ошибка парсинга return_date_range_str ('{range_str}') в standard_return_date_selected: {e}")
                 # Если range_str не удалось распарсить, то переход к ask_specific_date не сработает корректно
        
        # Если не удалось вернуться к выбору конкретной даты (например, нет range_str)
        await query.edit_message_text("Ошибка даты возврата. Пожалуйста, начните поиск заново /start.")
        return ConversationHandler.END


    context.user_data['return_date'] = selected_date_str
    # Очистка данных диапазона, так как выбрана одиночная дата
    context.user_data.pop('return_date_from', None)
    context.user_data.pop('return_date_to', None)
    context.user_data.pop('is_return_range_search', None)

    await query.edit_message_text(text=f"Дата обратного вылета: {return_date_obj.strftime('%d-%m-%Y')}")
    context.user_data['current_search_flow'] = config.FLOW_STANDARD # Это уже устанавливается ранее, но для надежности
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
# bot/handlers.py
async def flex_departure_year_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    try:
        selected_year = int(query.data.replace(config.CALLBACK_PREFIX_FLEX + "dep_year_", ""))
    except ValueError:
        logger.warning("flex_departure_year_selected: ValueError parsing year.")
        # ... (обработка ошибки, возможно, возврат к ask_year)
        await query.edit_message_text("❗Ошибка формата года. Пожалуйста, начните заново /start.") # Редактируем с ошибкой
        return ConversationHandler.END # или предыдущее состояние
    context.user_data['departure_year'] = selected_year

    if query.message:
        try:
            # Просто убираем клавиатуру с предыдущего сообщения, текст не меняем или ставим нейтральный
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception as e:
            logger.warning(f"Не удалось убрать клавиатуру в flex_departure_year_selected: {e}")
    
    # ask_month теперь должна отправить НОВОЕ сообщение с запросом месяца,
    # так как редактировать предыдущее (с которого только что убрали клавиатуру) для добавления новой 
    # может быть не лучшим UX, если текст там уже нерелевантен.
    # Либо ask_month должна уметь принимать решение: редактировать (если текст подходит) или слать новое.

    # Чтобы ask_month отправила новое сообщение, можно передать ей не query, а update.
    # Или модифицировать ask_month, чтобы она всегда отправляла новое, если ей не передать query.message для редактирования.
    # Ваша ask_month уже имеет логику отправки нового сообщения, если actual_query_object не найден или не имеет .message

    # Давайте сделаем так, чтобы ask_month отредактировала сообщение, которое пришло с query,
    # но теперь с новым текстом и новой клавиатурой.
    await ask_month(
        message_or_update_or_query=query, # Передаем query, чтобы ask_month попыталась отредактировать query.message
        context=context,
        year_for_months=selected_year,
        message_text=f"Год вылета: {selected_year}. 🗓️ Выберите месяц:", # ask_month установит этот текст
        callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_month_",
        keyboard_back_callback=config.CB_BACK_FLEX_DEP_MONTH_TO_YEAR
    )
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
                            keyboard_back_callback=config.CB_BACK_FLEX_DEP_DATE_TO_RANGE,
                            range_selection_type="dep")
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
                                        keyboard_back_callback=config.CB_BACK_FLEX_DEP_DATE_TO_RANGE,
                                        range_selection_type="dep")
                return config.SELECTING_FLEX_DEPARTURE_DATE
            except ValueError: pass
        await query.edit_message_text("🚫 Ошибка даты. Начните /start.")
        return ConversationHandler.END

    context.user_data['departure_date'] = selected_date_str
    # ОЧИСТКА ДАННЫХ ДИАПАЗОНА
    context.user_data.pop('departure_date_from', None)
    context.user_data.pop('departure_date_to', None)
    context.user_data.pop('is_departure_range_search', None)
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

    # --- ИЗМЕНЕНИЕ ЛОГИКИ ПОЛУЧЕНИЯ ДАТЫ ВЫЛЕТА ---
    departure_date_to_compare_str: str | None = None
    if context.user_data.get('is_departure_range_search', False):
        departure_date_to_compare_str = context.user_data.get('departure_date_from')
    else:
        departure_date_to_compare_str = context.user_data.get('departure_date')

    if not departure_date_to_compare_str:
        await query.edit_message_text("🚫 Ошибка: дата вылета не найдена для сравнения. Начните /start.")
        logger.error("flex_return_year_selected: Отсутствует дата вылета (departure_date или departure_date_from).")
        return ConversationHandler.END
        
    departure_date_obj = helpers.validate_date_format(departure_date_to_compare_str)
    # --- КОНЕЦ ИЗМЕНЕНИЯ ЛОГИКИ ---

    if not departure_date_obj: # Проверка на None после validate_date_format
        await query.edit_message_text("🚫 Ошибка: дата вылета некорректна. Начните /start.")
        logger.error(f"flex_return_year_selected: Не удалось валидировать дату вылета: {departure_date_to_compare_str}")
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
                  departure_year_for_comparison=departure_date_obj.year, # Для сравнения в ask_month
                  departure_month_for_comparison=min_ret_month_for_comp, # Для сравнения в ask_month
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
        # Возврат к выбору года возврата
        await ask_year(query, context, "🗓️ Выберите год обратного вылета:",
                       callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_year_",
                       keyboard_back_callback=config.CB_BACK_FLEX_RET_YEAR_TO_DEP_DATE)
        return config.SELECTING_FLEX_RETURN_YEAR

    return_year = context.user_data.get('return_year') # Год возврата, который только что выбрали или подтвердили

    # --- ИЗМЕНЕНИЕ ЛОГИКИ ПОЛУЧЕНИЯ ДАТЫ ВЫЛЕТА ---
    departure_date_to_compare_str: str | None = None
    if context.user_data.get('is_departure_range_search', False):
        departure_date_to_compare_str = context.user_data.get('departure_date_from')
    else:
        departure_date_to_compare_str = context.user_data.get('departure_date')

    if not departure_date_to_compare_str:
        await query.edit_message_text("🚫 Ошибка: дата вылета не найдена для сравнения. Начните /start.")
        logger.error("flex_return_month_selected: Отсутствует дата вылета (departure_date или departure_date_from).")
        return ConversationHandler.END
        
    departure_date_obj = helpers.validate_date_format(departure_date_to_compare_str)
    # --- КОНЕЦ ИЗМЕНЕНИЯ ЛОГИКИ ---

    if not return_year or not departure_date_obj: # Проверка на None после validate_date_format
        await query.edit_message_text("🚫 Ошибка данных о датах (год возврата или дата вылета не определены). /start")
        logger.error(f"flex_return_month_selected: return_year={return_year}, departure_date_obj={departure_date_obj}")
        return ConversationHandler.END

    if return_year == departure_date_obj.year and selected_return_month < departure_date_obj.month:
        await query.edit_message_text("🗓️ Месяц возврата не может быть раньше месяца вылета в том же году.")
        min_ret_month_for_comp = departure_date_obj.month # Гарантированно тот же год
        await ask_month(update, context, return_year,
                        f"🗓️ Год обратного вылета: {return_year}. Выберите месяц:",
                        config.CALLBACK_PREFIX_FLEX + "ret_month_",
                        departure_year_for_comparison=departure_date_obj.year, 
                        departure_month_for_comparison=min_ret_month_for_comp,
                        keyboard_back_callback=config.CB_BACK_FLEX_RET_MONTH_TO_YEAR)
        return config.SELECTING_FLEX_RETURN_MONTH

    context.user_data['return_month'] = selected_return_month
    month_name = config.RUSSIAN_MONTHS.get(selected_return_month, str(selected_return_month))
    await ask_date_range(update, context, return_year, selected_return_month, # update содержит query
                         f"Выбран: {month_name} {return_year}. 📏 Выберите диапазон дат для возврата:",
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
        # Возврат к выбору месяца возврата
        year = context.user_data.get('return_year')
        # Для ask_month нужны данные о дате вылета для сравнения
        departure_date_to_compare_str_fallback: str | None = None
        if context.user_data.get('is_departure_range_search', False):
            departure_date_to_compare_str_fallback = context.user_data.get('departure_date_from')
        else:
            departure_date_to_compare_str_fallback = context.user_data.get('departure_date')
        
        dep_date_obj_fallback = helpers.validate_date_format(departure_date_to_compare_str_fallback) if departure_date_to_compare_str_fallback else None

        min_ret_month_for_comp = 1
        dep_year_for_comp = None
        if dep_date_obj_fallback and year == dep_date_obj_fallback.year: # Год возврата совпадает с годом вылета
            min_ret_month_for_comp = dep_date_obj_fallback.month
            dep_year_for_comp = dep_date_obj_fallback.year


        if year: # Год возврата должен быть известен
            await ask_month(update, context, year, f"🗓️ Год обратного вылета: {year}. Выберите месяц:",
                            config.CALLBACK_PREFIX_FLEX + "ret_month_",
                            departure_year_for_comparison=dep_year_for_comp, 
                            departure_month_for_comparison=min_ret_month_for_comp,
                            keyboard_back_callback=config.CB_BACK_FLEX_RET_MONTH_TO_YEAR)
            return config.SELECTING_FLEX_RETURN_MONTH
        return ConversationHandler.END # Если года нет, что-то пошло не так

    context.user_data['return_date_range_str'] = selected_range_str
    year = context.user_data['return_year'] # Год возврата
    month = context.user_data['return_month'] # Месяц возврата

    # --- ИЗМЕНЕНИЕ ЛОГИКИ ПОЛУЧЕНИЯ ДАТЫ ВЫЛЕТА ---
    departure_date_to_compare_str: str | None = None
    if context.user_data.get('is_departure_range_search', False):
        departure_date_to_compare_str = context.user_data.get('departure_date_from')
    else:
        departure_date_to_compare_str = context.user_data.get('departure_date')

    if not departure_date_to_compare_str:
        await query.edit_message_text("❗Ошибка: дата вылета не найдена для сравнения. /start")
        logger.error("flex_return_date_range_selected: Отсутствует дата вылета (departure_date или departure_date_from).")
        return ConversationHandler.END
        
    departure_date_obj = helpers.validate_date_format(departure_date_to_compare_str)
    # --- КОНЕЦ ИЗМЕНЕНИЯ ЛОГИКИ ---

    if not departure_date_obj: # Проверка на None после validate_date_format
        await query.edit_message_text("❗Ошибка: дата вылета некорректна. /start")
        logger.error(f"flex_return_date_range_selected: Не удалось валидировать дату вылета: {departure_date_to_compare_str}")
        return ConversationHandler.END

    min_allowed_return_date = departure_date_obj # Минимальная дата для возврата - это дата вылета

    temp_start_day_for_buttons = start_day
    # Корректируем начальный день для кнопок, если он раньше даты вылета в том же месяце/году
    if year == departure_date_obj.year and month == departure_date_obj.month:
        temp_start_day_for_buttons = max(start_day, departure_date_obj.day)
    
    if temp_start_day_for_buttons > end_day:
        await query.edit_message_text("🚫 В этом диапазоне нет доступных дат после учета даты вылета. Пожалуйста, выберите другой диапазон или месяц.")
        min_ret_month_fallback = departure_date_obj.month if year == departure_date_obj.year else 1
        dep_year_fallback = departure_date_obj.year
        await ask_month(update, context, year,
                        f"🗓️ Год обратного вылета: {year}. Выберите месяц:",
                        config.CALLBACK_PREFIX_FLEX + "ret_month_",
                        departure_year_for_comparison=dep_year_fallback, 
                        departure_month_for_comparison=min_ret_month_fallback,
                        keyboard_back_callback=config.CB_BACK_FLEX_RET_MONTH_TO_YEAR)
        return config.SELECTING_FLEX_RETURN_MONTH

    month_name_rus = config.RUSSIAN_MONTHS.get(month, str(month))
    await ask_specific_date(update, context, year, month, temp_start_day_for_buttons, end_day,
                            f"Диапазон: {start_day}-{end_day} {month_name_rus}. 🗓️ Выберите дату возврата:",
                            callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_date_",
                            min_allowed_date_for_comparison=min_allowed_return_date,
                            keyboard_back_callback=config.CB_BACK_FLEX_RET_DATE_TO_RANGE,
                            range_selection_type="ret")
    return config.SELECTING_FLEX_RETURN_DATE

async def flex_return_date_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    selected_date_str = query.data.replace(config.CALLBACK_PREFIX_FLEX + "ret_date_", "")
    return_date_obj = helpers.validate_date_format(selected_date_str)

    # --- ИЗМЕНЕНИЕ ЛОГИКИ ПОЛУЧЕНИЯ ДАТЫ ВЫЛЕТА ---
    departure_date_to_compare_str: str | None = None
    if context.user_data.get('is_departure_range_search', False):
        departure_date_to_compare_str = context.user_data.get('departure_date_from')
    else:
        departure_date_to_compare_str = context.user_data.get('departure_date')

    if not departure_date_to_compare_str:
        await query.edit_message_text("❗Ошибка: дата вылета не найдена для сравнения. Начните /start.")
        logger.error("flex_return_date_selected: Отсутствует дата вылета (departure_date или departure_date_from).")
        return ConversationHandler.END
        
    departure_date_obj = helpers.validate_date_format(departure_date_to_compare_str)
    # --- КОНЕЦ ИЗМЕНЕНИЯ ЛОГИКИ ---

    if not departure_date_obj: # Проверка на None после validate_date_format
        await query.edit_message_text("❗Ошибка: дата вылета некорректна. Начните /start.")
        logger.error(f"flex_return_date_selected: Не удалось валидировать дату вылета: {departure_date_to_compare_str}")
        return ConversationHandler.END

    if not return_date_obj or return_date_obj < departure_date_obj:
        year = context.user_data.get('return_year')
        month = context.user_data.get('return_month')
        range_str = context.user_data.get('return_date_range_str') # Диапазон, из которого выбирали
        
        if year and month and range_str: # Убедимся, что эти данные есть
             try:
                 start_day_orig, end_day_orig = map(int, range_str.split('-'))
                 # Корректируем start_day для кнопок, как это делалось в flex_return_date_range_selected
                 start_day_buttons = start_day_orig
                 if year == departure_date_obj.year and month == departure_date_obj.month: # Если тот же год и месяц, что и дата вылета
                     start_day_buttons = max(start_day_orig, departure_date_obj.day)

                 month_name_rus = config.RUSSIAN_MONTHS.get(month, str(month))
                 await query.edit_message_text("🚫 Некорректная дата возврата (раньше даты вылета или в прошлом). Попробуйте снова.")
                 await ask_specific_date(update, context, year, month, start_day_buttons, end_day_orig,
                                        f"📏 Диапазон: {start_day_orig}-{end_day_orig} {month_name_rus}. 🗓️ Выберите дату возврата:",
                                        callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_date_",
                                        min_allowed_date_for_comparison=departure_date_obj,
                                        keyboard_back_callback=config.CB_BACK_FLEX_RET_DATE_TO_RANGE,
                                        range_selection_type="ret")
                 return config.SELECTING_FLEX_RETURN_DATE
             except ValueError as e:
                 logger.error(f"Ошибка парсинга return_date_range_str ('{range_str}') в flex_return_date_selected: {e}")

        # Если не удалось вернуться к выбору конкретной даты
        await query.edit_message_text("❗Ошибка даты возврата. Пожалуйста, начните поиск заново /start.")
        return ConversationHandler.END

    context.user_data['return_date'] = selected_date_str
    # Очистка данных диапазона, так как выбрана одиночная дата
    context.user_data.pop('return_date_from', None)
    context.user_data.pop('return_date_to', None)
    context.user_data.pop('is_return_range_search', None)

    if query.message:
        try: 
            await query.edit_message_text(text=f"🗓️ Дата обратного вылета: {return_date_obj.strftime('%d-%m-%Y')}")
        except Exception as e: 
            logger.warning(f"flex_return_date_selected: edit_message_text failed: {e}")
            # Если не удалось отредактировать, все равно продолжаем и запускаем поиск
    
    # Все данные для гибкого поиска туда-обратно собраны
    if not context.user_data.get('departure_airport_iata'): # Нужен аэропорт вылета
            await context.bot.send_message(
                chat_id=query.message.chat_id if query.message else update.effective_chat.id, 
                text="Не указан аэропорт вылета для гибкого поиска. /start"
            )
            return ConversationHandler.END
    return await launch_flight_search(update, context)


# --- ГИБКИЙ ПОИСК - ОБРАБОТЧИКИ "НАЗАД" ДЛЯ ДАТ ---

# bot/handlers.py
async def back_flex_dep_year_to_ask_dates_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        logger.warning("back_flex_dep_year_to_ask_dates_handler вызван без query.")
        return ConversationHandler.END
    await query.answer()

    # Очищаем данные шага, с которого уходим (выбор года вылета и последующих месяцев/дат)
    context.user_data.pop('departure_year', None)
    context.user_data.pop('departure_month', None)
    context.user_data.pop('departure_date_range_str', None)
    context.user_data.pop('departure_date', None)
    context.user_data.pop('departure_date_from', None)
    context.user_data.pop('departure_date_to', None)
    context.user_data.pop('is_departure_range_search', None)

    # 1. Проверка базовых данных не так критична здесь, так как мы возвращаемся к общему вопросу о датах,
    # но если current_search_flow не FLEX, это все равно странно.
    if not context.user_data.get('current_search_flow') == config.FLOW_FLEX:
        logger.warning(f"back_flex_dep_year_to_ask_dates_handler: Неверный current_search_flow. Callback: {query.data}")
        # Можно просто завершить или перенаправить на /start
        if query.message:
            try: await query.edit_message_text("Произошла ошибка потока диалога. Пожалуйста, /start", reply_markup=None)
            except Exception as e: logger.error(f"Ошибка редактирования: {e}")
        return ConversationHandler.END


    # 2. Возвращаемся к вопросу "Указать конкретные даты?"
    # Определяем правильную кнопку "Назад" для следующего шага (ASK_FLEX_DATES)
    back_cb_for_ask_dates = config.CB_BACK_FLEX_ASK_DATES_TO_DEP_CITY_NO_ARR # По умолчанию
    # Если аэропорт прилета уже был выбран, кнопка "Назад" должна вести к нему
    if context.user_data.get('arrival_airport_iata') and context.user_data.get('arrival_city_name'):
        back_cb_for_ask_dates = config.CB_BACK_FLEX_ASK_DATES_TO_ARR_CITY
    # Если аэропорт прилета не выбран, но город вылета есть (это стандартный случай перед ASK_FLEX_DATES, если прилет не указан)
    elif context.user_data.get('departure_city_name') and context.user_data.get('arrival_airport_iata') is None:
        back_cb_for_ask_dates = config.CB_BACK_FLEX_ASK_DATES_TO_DEP_CITY_NO_ARR
    # Можно добавить еще условия, если есть другие пути к ASK_FLEX_DATES с разными кнопками "Назад"

    if query.message:
        try:
            await query.edit_message_text(
                text="🗓️ Указать конкретные даты вылета?",
                reply_markup=keyboards.get_skip_dates_keyboard(
                    callback_select_dates=config.CALLBACK_PREFIX_FLEX + "ask_dates_yes",
                    back_callback_data=back_cb_for_ask_dates
                )
            )
        except Exception as e_edit:
            logger.error(f"Ошибка редактирования в back_flex_dep_year_to_ask_dates_handler: {e_edit}")
            # Если редактирование не удалось, пытаемся отправить новое сообщение
            if query.message and query.message.chat_id:
                 await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="🗓️ Указать конкретные даты вылета?",
                    reply_markup=keyboards.get_skip_dates_keyboard(
                        callback_select_dates=config.CALLBACK_PREFIX_FLEX + "ask_dates_yes",
                        back_callback_data=back_cb_for_ask_dates
                    )
                )
    else: # Если query.message нет, это неожиданно для CallbackQueryHandler
        logger.error("back_flex_dep_year_to_ask_dates_handler: query.message отсутствует.")
        # Попытка отправить сообщение, если есть chat_id
        effective_chat_id = update.effective_chat.id
        if effective_chat_id:
            await context.bot.send_message(
                chat_id=effective_chat_id,
                text="🗓️ Указать конкретные даты вылета?",
                reply_markup=keyboards.get_skip_dates_keyboard(
                    callback_select_dates=config.CALLBACK_PREFIX_FLEX + "ask_dates_yes",
                    back_callback_data=back_cb_for_ask_dates
                )
            )
        else: # Крайний случай, если и chat_id не найти
            return ConversationHandler.END


    return config.ASK_FLEX_DATES

# bot/handlers.py
async def back_flex_dep_month_to_year_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        logger.warning("back_flex_dep_month_to_year_handler вызван без query.")
        return ConversationHandler.END
    await query.answer()

    # Очищаем данные шага, с которого уходим (выбор месяца вылета и последующих дат/диапазонов)
    context.user_data.pop('departure_month', None)
    context.user_data.pop('departure_date_range_str', None)
    context.user_data.pop('departure_date', None)
    context.user_data.pop('departure_date_from', None)
    context.user_data.pop('departure_date_to', None)
    context.user_data.pop('is_departure_range_search', None)

    # 1. Проверка базовых данных (аэропорт вылета и тип потока)
    # Хотя для выбора года вылета они не строго нужны, но если их нет,
    # это указывает на более глубокую проблему в потоке.
    if not context.user_data.get('departure_airport_iata') or \
       not context.user_data.get('current_search_flow') == config.FLOW_FLEX:
        logger.warning(f"back_flex_dep_month_to_year_handler: Отсутствуют базовые данные. Callback: {query.data}")
        if query.message:
            try:
                await query.edit_message_text(
                    "Произошла небольшая путаница. Давайте начнем с выбора дат вылета. ✈️",
                    reply_markup=None
                )
            except Exception as e_edit:
                logger.error(f"Ошибка редактирования (нет базовых данных) в back_flex_dep_month_to_year_handler: {e_edit}")

        back_cb_ask_dates = config.CB_BACK_FLEX_ASK_DATES_TO_ARR_CITY \
                            if context.user_data.get('arrival_airport_iata') \
                            else config.CB_BACK_FLEX_ASK_DATES_TO_DEP_CITY_NO_ARR
        if query.message and query.message.chat_id:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="🗓️ Указать конкретные даты вылета?",
                reply_markup=keyboards.get_skip_dates_keyboard(
                    callback_select_dates=config.CALLBACK_PREFIX_FLEX + "ask_dates_yes",
                    back_callback_data=back_cb_ask_dates
                )
            )
        return config.ASK_FLEX_DATES

    # 2. Возвращаемся к выбору года вылета
    # `departure_year` будет очищен или не установлен, ask_year запросит его.
    await ask_year(
        message_or_update_or_query=query,
        context=context,
        message_text="🗓️ Выберите год вылета:",
        callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_year_",
        keyboard_back_callback=config.CB_BACK_FLEX_DEP_YEAR_TO_ASK_DATES # Назад к вопросу "Указать даты?"
    )
    return config.SELECTING_FLEX_DEPARTURE_YEAR

# bot/handlers.py
async def back_flex_dep_range_to_month_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        logger.warning("back_flex_dep_range_to_month_handler вызван без query.")
        return ConversationHandler.END
    await query.answer()

    # Очищаем данные шага, с которого уходим (выбор диапазона дней вылета и последующей даты)
    context.user_data.pop('departure_date_range_str', None)
    context.user_data.pop('departure_date', None)
    context.user_data.pop('departure_date_from', None) # Также очищаем, если был установлен диапазон
    context.user_data.pop('departure_date_to', None)
    context.user_data.pop('is_departure_range_search', None) # И флаг, если был установлен

    # 1. Проверка базовых данных (аэропорт вылета и тип потока)
    if not context.user_data.get('departure_airport_iata') or \
       not context.user_data.get('current_search_flow') == config.FLOW_FLEX:
        logger.warning(f"back_flex_dep_range_to_month_handler: Отсутствуют базовые данные. Callback: {query.data}")
        if query.message:
            try:
                await query.edit_message_text(
                    "Произошла небольшая путаница. Давайте начнем с выбора дат вылета. ✈️",
                    reply_markup=None
                )
            except Exception as e_edit:
                logger.error(f"Ошибка редактирования (нет базовых данных) в back_flex_dep_range_to_month_handler: {e_edit}")
        
        back_cb_ask_dates = config.CB_BACK_FLEX_ASK_DATES_TO_ARR_CITY \
                            if context.user_data.get('arrival_airport_iata') \
                            else config.CB_BACK_FLEX_ASK_DATES_TO_DEP_CITY_NO_ARR
        if query.message and query.message.chat_id:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="🗓️ Указать конкретные даты вылета?",
                reply_markup=keyboards.get_skip_dates_keyboard(
                    callback_select_dates=config.CALLBACK_PREFIX_FLEX + "ask_dates_yes",
                    back_callback_data=back_cb_ask_dates
                )
            )
        return config.ASK_FLEX_DATES

    # 2. Получаем год вылета, который должен был быть установлен ранее
    year = context.user_data.get('departure_year')

    if not year:
        logger.warning("back_flex_dep_range_to_month_handler: Не найден год вылета (departure_year).")
        if query.message:
            try:
                await query.edit_message_text(
                    "Не удалось вернуться к выбору месяца, т.к. не определен год вылета. Давайте выберем год вылета. 📅",
                    reply_markup=None
                )
            except Exception as e_edit:
                logger.error(f"Ошибка редактирования (нет года вылета) в back_flex_dep_range_to_month_handler: {e_edit}")
        
        # Переводим на шаг выбора года вылета
        await ask_year(query, context, "🗓️ Выберите год вылета:",
                       callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_year_",
                       keyboard_back_callback=config.CB_BACK_FLEX_DEP_YEAR_TO_ASK_DATES)
        return config.SELECTING_FLEX_DEPARTURE_YEAR

    # 3. Если год есть, возвращаемся к выбору месяца вылета
    await ask_month(
        message_or_update_or_query=query,
        context=context,
        year_for_months=year,
        message_text=f"Год вылета: {year}. 🗓️ Выберите месяц:",
        callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_month_",
        # departure_year/month_for_comparison здесь не нужны, т.к. мы выбираем месяц вылета, а не возврата
        keyboard_back_callback=config.CB_BACK_FLEX_DEP_MONTH_TO_YEAR # Назад к выбору года вылета
    )
    return config.SELECTING_FLEX_DEPARTURE_MONTH

# bot/handlers.py
async def back_flex_dep_date_to_range_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        logger.warning("back_flex_dep_date_to_range_handler вызван без query.")
        return ConversationHandler.END
    await query.answer()

    # Очищаем данные шага, с которого уходим (выбор конкретной даты вылета)
    context.user_data.pop('departure_date', None)
    context.user_data.pop('departure_date_from', None) # Также очищаем, если был установлен диапазон
    context.user_data.pop('departure_date_to', None)
    context.user_data.pop('is_departure_range_search', None)

    # 1. Проверка наличия базовых данных для гибкого поиска
    if not context.user_data.get('departure_airport_iata') or \
       not context.user_data.get('current_search_flow') == config.FLOW_FLEX:
        logger.warning(f"back_flex_dep_date_to_range_handler: Отсутствуют базовые данные. Callback: {query.data}")
        if query.message:
            try:
                await query.edit_message_text(
                    "Произошла небольшая путаница. Давайте начнем с выбора дат вылета. ✈️",
                    reply_markup=None
                )
            except Exception as e_edit:
                logger.error(f"Ошибка редактирования (нет базовых данных): {e_edit}")
        
        back_cb_ask_dates = config.CB_BACK_FLEX_ASK_DATES_TO_ARR_CITY \
                            if context.user_data.get('arrival_airport_iata') \
                            else config.CB_BACK_FLEX_ASK_DATES_TO_DEP_CITY_NO_ARR
        if query.message and query.message.chat_id:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="🗓️ Указать конкретные даты вылета?",
                reply_markup=keyboards.get_skip_dates_keyboard(
                    callback_select_dates=config.CALLBACK_PREFIX_FLEX + "ask_dates_yes",
                    back_callback_data=back_cb_ask_dates
                )
            )
        return config.ASK_FLEX_DATES

    # 2. Получаем год и месяц вылета, которые должны были быть установлены ранее
    year = context.user_data.get('departure_year')
    month = context.user_data.get('departure_month')

    if not year or not month:
        logger.warning(f"back_flex_dep_date_to_range_handler: Не найден год ({year}) или месяц ({month}) вылета.")
        if query.message:
            try:
                await query.edit_message_text(
                    "Не удалось вернуться к выбору диапазона дат вылета, т.к. не определен месяц/год. Давайте выберем год вылета. 📅",
                    reply_markup=None
                )
            except Exception as e_edit: logger.error(f"Ошибка редактирования (нет года/месяца вылета): {e_edit}")
        
        # Переводим на шаг выбора года вылета
        await ask_year(query, context, "🗓️ Выберите год вылета:",
                       callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_year_",
                       keyboard_back_callback=config.CB_BACK_FLEX_DEP_YEAR_TO_ASK_DATES)
        return config.SELECTING_FLEX_DEPARTURE_YEAR

    # 3. Если год и месяц есть, возвращаемся к выбору диапазона дней вылета
    month_name = config.RUSSIAN_MONTHS.get(month, str(month))
    await ask_date_range(
        source_update_or_query=query,
        context=context,
        year=year,
        month=month,
        message_text=f"Выбран: {month_name} {year}. 📏 Выберите диапазон дней для вылета:",
        callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_range_",
        keyboard_back_callback=config.CB_BACK_FLEX_DEP_RANGE_TO_MONTH # Назад к выбору месяца вылета
    )
    return config.SELECTING_FLEX_DEPARTURE_DATE_RANGE

# bot/handlers.py
async def back_flex_ret_year_to_dep_date_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        logger.warning("back_flex_ret_year_to_dep_date_handler вызван без query.")
        return ConversationHandler.END
    await query.answer()

    # Очищаем данные, связанные с выбором дат возврата, так как мы уходим с этого этапа
    context.user_data.pop('return_year', None)
    context.user_data.pop('return_month', None)
    context.user_data.pop('return_date_range_str', None)
    context.user_data.pop('return_date', None)
    context.user_data.pop('return_date_from', None)
    context.user_data.pop('return_date_to', None)
    context.user_data.pop('is_return_range_search', None)

    # Пытаемся получить данные, необходимые для возврата к выбору конкретной даты вылета
    dep_year = context.user_data.get('departure_year')
    dep_month = context.user_data.get('departure_month')
    dep_range_str = context.user_data.get('departure_date_range_str')

    if dep_year and dep_month and dep_range_str:
        # Если все данные для выбора конкретной даты вылета есть, действуем как раньше
        try:
            start_day, end_day = map(int, dep_range_str.split('-'))
        except ValueError:
            logger.error(f"Ошибка парсинга departure_date_range_str ('{dep_range_str}') в back_flex_ret_year_to_dep_date_handler")
            await query.edit_message_text("❗Произошла ошибка с данными о диапазоне дат вылета. Пожалуйста, начните заново: /start")
            return ConversationHandler.END

        min_date_for_dep = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        month_name_rus = config.RUSSIAN_MONTHS.get(dep_month, str(dep_month))
        
        await query.edit_message_text( # Редактируем текущее сообщение (от кнопки "Назад")
            text=f"Возврат к выбору даты вылета. Диапазон: {start_day}-{end_day} {month_name_rus} {dep_year}."
        )
        await ask_specific_date( # Отправляем новую клавиатуру для выбора конкретной даты
            source_update_or_query=query, # query содержит message для edit_message_text в ask_specific_date
            context=context, 
            year=dep_year, 
            month=dep_month, 
            range_start=start_day, 
            range_end=end_day,
            message_text=f"Диапазон: {start_day}-{end_day} {month_name_rus} {dep_year}. 🗓️ Выберите дату вылета:",
            callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_date_",
            min_allowed_date_for_comparison=min_date_for_dep,
            keyboard_back_callback=config.CB_BACK_FLEX_DEP_DATE_TO_RANGE, # Назад к выбору диапазона дней вылета
            range_selection_type="dep"
        )
        return config.SELECTING_FLEX_DEPARTURE_DATE
    else:
        # Если данных для возврата к выбору конкретной даты вылета нет,
        # это значит, что пользователь, вероятно, еще не дошел до этапа выбора дат вылета вообще.
        # Перенаправляем его на самый первый шаг выбора дат вылета - вопрос "Указать конкретные даты?".
        logger.warning(
            f"back_flex_ret_year_to_dep_date_handler: Отсутствуют данные для восстановления шага выбора даты вылета "
            f"(dep_year: {dep_year}, dep_month: {dep_month}, dep_range_str: {dep_range_str}). "
            f"Callback: {query.data}. UserData: {context.user_data}"
        )
        
        try:
            await query.edit_message_text(
                "Произошла небольшая путаница. Давайте определимся с датами вылета. ✈️",
                reply_markup=None # Убираем старую клавиатуру
            )
        except Exception as e_edit:
            logger.error(f"Ошибка редактирования сообщения в back_flex_ret_year_to_dep_date_handler (нет данных о дате вылета): {e_edit}")

        # Определяем правильную кнопку "Назад" для шага ASK_FLEX_DATES
        # Это нужно, чтобы кнопка "Назад" на следующем шаге была корректной
        back_cb_ask_dates = config.CB_BACK_FLEX_ASK_DATES_TO_ARR_CITY \
                            if context.user_data.get('arrival_airport_iata') \
                            else config.CB_BACK_FLEX_ASK_DATES_TO_DEP_CITY_NO_ARR
        
        # Убедимся, что query.message существует для chat_id
        if query.message and query.message.chat_id:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="🗓️ Указать конкретные даты вылета?", # Сообщение для ASK_FLEX_DATES
                reply_markup=keyboards.get_skip_dates_keyboard(
                    callback_select_dates=config.CALLBACK_PREFIX_FLEX + "ask_dates_yes",
                    back_callback_data=back_cb_ask_dates
                )
            )
        return config.ASK_FLEX_DATES # Возвращаем на самый ранний этап запроса дат вылета

# bot/handlers.py
async def back_flex_ret_month_to_year_handler(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        logger.warning("back_flex_ret_month_to_year_handler: вызван без query.")
        return ConversationHandler.END
    await query.answer()

    # Очищаем данные шага, с которого уходим, и всех последующих этапов выбора дат возврата
    context.user_data.pop('return_month', None)
    context.user_data.pop('return_date_range_str', None)
    context.user_data.pop('return_date', None)
    context.user_data.pop('return_date_from', None)
    context.user_data.pop('return_date_to', None)
    context.user_data.pop('is_return_range_search', None)

    # Определяем строку с датой вылета (одиночная или начало диапазона)
    departure_date_str: str | None
    if context.user_data.get('is_departure_range_search', False):
        departure_date_str = context.user_data.get('departure_date_from')
    else:
        departure_date_str = context.user_data.get('departure_date')

    departure_date_obj = helpers.validate_date_format(departure_date_str)

    if not departure_date_obj:
        logger.warning(f"back_flex_ret_month_to_year_handler: Дата вылета не найдена или некорректна ('{departure_date_str}'). Перенаправление на выбор года вылета.")
        # Редактируем исходное сообщение (от кнопки "Назад")
        if query.message:
            try:
                await query.edit_message_text(
                    text="Для выбора дат возврата, пожалуйста, сначала определитесь с датой вылета. ✈️",
                    reply_markup=None # Убираем старую клавиатуру
                )
            except Exception as e_edit:
                logger.error(f"Ошибка редактирования сообщения в back_flex_ret_month_to_year_handler (нет даты вылета): {e_edit}")
        
        # Отправляем новую клавиатуру для выбора года ВЫЛЕТА
        await ask_year(
            message_or_update_or_query=query, # query, чтобы ask_year мог попробовать отредактировать (хотя мы уже сделали) или отправить новое
            context=context,
            message_text="🗓️ Пожалуйста, выберите год вылета:",
            callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_year_",
            keyboard_back_callback=config.CB_BACK_FLEX_DEP_YEAR_TO_ASK_DATES
        )
        return config.SELECTING_FLEX_DEPARTURE_YEAR # Переход к выбору года ВЫЛЕТА

    # Если дата вылета есть, продолжаем и возвращаемся к выбору года ВОЗВРАТА
    if query.message: # Отредактируем сообщение перед показом клавиатуры выбора года возврата
        try:
            await query.edit_message_text(
                text="Возврат к выбору года обратного вылета.",
                reply_markup=None
            )
        except Exception as e_edit:
            logger.warning(f"Не удалось отредактировать сообщение при возврате к году возврата: {e_edit}")

    await ask_year(
        message_or_update_or_query=query, # query для ask_year
        context=context,
        message_text="🗓️ Выберите год обратного вылета:",
        callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_year_",
        keyboard_back_callback=config.CB_BACK_FLEX_RET_YEAR_TO_DEP_DATE # Кнопка "Назад" отсюда ведет к дате вылета
    )
    return config.SELECTING_FLEX_RETURN_YEAR

# bot/handlers.py
async def back_flex_ret_range_to_month_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    if not query:
        logger.warning("back_flex_ret_range_to_month_handler вызван без query.")
        # Если query нет, то и query.message нет, надо найти другой способ ответить, если это вообще возможно
        # или просто завершить. Для простоты завершаем.
        return ConversationHandler.END
    await query.answer()

    # Проверяем наличие ключевых данных, необходимых ДО выбора дат вылета
    # Эти данные должны быть установлены до того, как пользователь дойдет до выбора дат возврата
    if not context.user_data.get('departure_airport_iata') or \
       not context.user_data.get('current_search_flow') == config.FLOW_FLEX:
        logger.warning(f"back_flex_ret_range_to_month_handler: Отсутствуют базовые данные для гибкого поиска (аэропорт вылета или тип потока). Callback: {query.data}. UserData: {context.user_data}")
        try:
            await query.edit_message_text(
                "Произошла небольшая путаница в диалоге. Давайте начнем с выбора дат вылета. ✈️",
                reply_markup=None # Убираем старую клавиатуру
            )
        except Exception as e_edit:
            logger.error(f"Ошибка редактирования сообщения в back_flex_ret_range_to_month_handler (нет базовых данных): {e_edit}")
            # Если редактирование не удалось, пытаемся отправить новое сообщение
            if query.message and query.message.chat_id:
                await context.bot.send_message(chat_id=query.message.chat_id, text="Произошла небольшая путаница в диалоге. Давайте начнем с выбора дат вылета. ✈️")


        # Переводим на шаг выбора дат вылета (вопрос "Указать конкретные даты?")
        # Это должно быть безопасно, так как этот шаг не требует предзаполненных дат вылета
        # и является логическим предшественником выбора конкретных дат вылета.
        # Убедимся, что query.message существует для chat_id
        if query.message and query.message.chat_id:
            # Определяем правильную кнопку "Назад" для шага ASK_FLEX_DATES
            back_cb_ask_dates = config.CB_BACK_FLEX_ASK_DATES_TO_ARR_CITY \
                                if context.user_data.get('arrival_airport_iata') \
                                else config.CB_BACK_FLEX_ASK_DATES_TO_DEP_CITY_NO_ARR

            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="🗓️ Указать конкретные даты вылета?", # Сообщение для ASK_FLEX_DATES
                reply_markup=keyboards.get_skip_dates_keyboard(
                    callback_select_dates=config.CALLBACK_PREFIX_FLEX + "ask_dates_yes",
                    back_callback_data=back_cb_ask_dates
                )
            )
        return config.ASK_FLEX_DATES # Возвращаем на этап запроса дат вылета

    year = context.user_data.get("return_year") # Год возврата

    # Очищаем данные, связанные с выбором диапазона дат возврата и конкретной датой возврата
    context.user_data.pop("return_date_range_str", None)
    context.user_data.pop("return_date", None)
    context.user_data.pop("return_date_from", None)
    context.user_data.pop("return_date_to", None)
    context.user_data.pop("is_return_range_search", None)

    if not year:
        logger.warning(
            "back_flex_ret_range_to_month_handler: return_year не найден в user_data."
        )
        await query.edit_message_text("❗Ошибка: год возврата не найден. Пожалуйста, начните поиск заново: /start")
        return ConversationHandler.END

    # --- Безопасное получение и валидация даты вылета для сравнения ---
    dep_date_str_for_validation: str | None = None
    if context.user_data.get("is_departure_range_search", False):
        dep_date_str_for_validation = context.user_data.get("departure_date_from")
    else:
        dep_date_str_for_validation = context.user_data.get("departure_date")

    if not dep_date_str_for_validation:
        logger.warning(
            "back_flex_ret_range_to_month_handler: Не найдена строка даты вылета (departure_date или departure_date_from), хотя базовые данные поиска есть."
        )
        await query.edit_message_text(
            "Похоже, мы пропустили выбор даты вылета. Давайте вернемся к этому шагу. 🛫",
            reply_markup=None
        )
        await ask_year(query, context, "🗓️ Выберите год вылета:", # Переводим на выбор года вылета
                       callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_year_",
                       keyboard_back_callback=config.CB_BACK_FLEX_DEP_YEAR_TO_ASK_DATES)
        return config.SELECTING_FLEX_DEPARTURE_YEAR

    departure_date_obj_for_comparison = helpers.validate_date_format(
        dep_date_str_for_validation
    )

    if not departure_date_obj_for_comparison:
        logger.warning(
            f"back_flex_ret_range_to_month_handler: Не удалось валидировать дату вылета: {dep_date_str_for_validation}."
        )
        await query.edit_message_text("❗Ошибка: дата вылета некорректна. Пожалуйста, укажите ее снова.")
        await ask_year(query, context, "🗓️ Выберите год вылета:", # Переводим на выбор года вылета
                       callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_year_",
                       keyboard_back_callback=config.CB_BACK_FLEX_DEP_YEAR_TO_ASK_DATES)
        return config.SELECTING_FLEX_DEPARTURE_YEAR
    # --- Конец безопасного получения и валидации даты вылета ---

    min_return_month_for_comparison = (
        departure_date_obj_for_comparison.month
        if year == departure_date_obj_for_comparison.year
        else 1
    )

    await ask_month(
        message_or_update_or_query=query,
        context=context,
        year_for_months=year,
        message_text=f"Год обратного вылета: {year}. 🗓️ Выберите месяц:",
        callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_month_",
        departure_year_for_comparison=departure_date_obj_for_comparison.year,
        departure_month_for_comparison=min_return_month_for_comparison,
        keyboard_back_callback=config.CB_BACK_FLEX_RET_MONTH_TO_YEAR,
    )
    return config.SELECTING_FLEX_RETURN_MONTH

# bot/handlers.py
async def back_flex_ret_date_to_range_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        logger.warning("back_flex_ret_date_to_range_handler вызван без query.")
        return ConversationHandler.END
    await query.answer()

    # Очищаем данные шага, с которого уходим (выбор конкретной даты возврата)
    # и связанные с выбором всего диапазона, если он был
    context.user_data.pop('return_date', None)
    context.user_data.pop('return_date_from', None)
    context.user_data.pop('return_date_to', None)
    context.user_data.pop('is_return_range_search', None)

    # 1. Проверка наличия базовых данных для гибкого поиска (аэропорт вылета)
    if not context.user_data.get('departure_airport_iata') or \
       not context.user_data.get('current_search_flow') == config.FLOW_FLEX:
        logger.warning(f"back_flex_ret_date_to_range_handler: Отсутствуют базовые данные. Callback: {query.data}")
        if query.message:
            try:
                await query.edit_message_text(
                    "Произошла небольшая путаница. Давайте начнем с выбора дат вылета. ✈️",
                    reply_markup=None
                )
            except Exception as e_edit:
                logger.error(f"Ошибка редактирования (нет базовых данных) в back_flex_ret_date_to_range_handler: {e_edit}")
        
        back_cb_ask_dates = config.CB_BACK_FLEX_ASK_DATES_TO_ARR_CITY \
                            if context.user_data.get('arrival_airport_iata') \
                            else config.CB_BACK_FLEX_ASK_DATES_TO_DEP_CITY_NO_ARR
        if query.message and query.message.chat_id:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="🗓️ Указать конкретные даты вылета?",
                reply_markup=keyboards.get_skip_dates_keyboard(
                    callback_select_dates=config.CALLBACK_PREFIX_FLEX + "ask_dates_yes",
                    back_callback_data=back_cb_ask_dates
                )
            )
        return config.ASK_FLEX_DATES

    # 2. Получаем год и месяц возврата (должны быть установлены)
    return_year = context.user_data.get('return_year')
    return_month = context.user_data.get('return_month')

    if not return_year or not return_month:
        logger.warning(f"back_flex_ret_date_to_range_handler: Не найден год ({return_year}) или месяц ({return_month}) возврата.")
        if query.message:
            try:
                await query.edit_message_text(
                    "Не удалось вернуться к выбору диапазона дат, т.к. не определен месяц/год возврата. Давайте выберем год возврата. 📅",
                    reply_markup=None
                )
            except Exception as e_edit: logger.error(f"Ошибка редактирования (нет года/месяца возврата): {e_edit}")
        
        # Переводим на шаг выбора года возврата
        # Нужна дата вылета для кнопки "Назад" в ask_year
        dep_date_str_for_bk_btn: str | None = None
        if context.user_data.get("is_departure_range_search", False):
            dep_date_str_for_bk_btn = context.user_data.get("departure_date_from")
        else:
            dep_date_str_for_bk_btn = context.user_data.get("departure_date")
        
        # Если dep_date_str_for_bk_btn все еще None, кнопка "Назад" в ask_year может быть не совсем корректной,
        # но ask_year должен сам обработать ситуацию.
        # CB_BACK_FLEX_RET_YEAR_TO_DEP_DATE - это кнопка назад от выбора года возврата к выбору даты вылета.
        # Это подходящий колбэк, если мы хотим вернуться к выбору года возврата.
        await ask_year(query, context, "🗓️ Выберите год обратного вылета:",
                       callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_year_",
                       keyboard_back_callback=config.CB_BACK_FLEX_RET_YEAR_TO_DEP_DATE)
        return config.SELECTING_FLEX_RETURN_YEAR

    # 3. Получаем дату вылета для передачи в ask_specific_date (хотя ask_date_range её не использует напрямую)
    # Это больше для консистентности и если бы ask_date_range её требовал для каких-то внутренних проверок.
    # На самом деле, для ask_date_range дата вылета не нужна для генерации кнопок 1-10, 11-20 и т.д.
    # Она понадобится на следующем шаге (ask_specific_date).
    # Здесь важно, чтобы она просто была, чтобы последующие шаги не сломались.
    dep_date_str_for_validation: str | None = None
    if context.user_data.get("is_departure_range_search", False):
        dep_date_str_for_validation = context.user_data.get("departure_date_from")
    else:
        dep_date_str_for_validation = context.user_data.get("departure_date")

    if not dep_date_str_for_validation:
        logger.warning("back_flex_ret_date_to_range_handler: Не найдена дата вылета, необходимая для последующих шагов.")
        if query.message:
            try:
                await query.edit_message_text(
                    "Похоже, мы пропустили выбор даты вылета. Давайте вернемся к этому шагу. 🛫",
                    reply_markup=None
                )
            except Exception as e_edit: logger.error(f"Ошибка редактирования (нет даты вылета): {e_edit}")
        
        await ask_year(query, context, "🗓️ Выберите год вылета:",
                       callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_year_",
                       keyboard_back_callback=config.CB_BACK_FLEX_DEP_YEAR_TO_ASK_DATES)
        return config.SELECTING_FLEX_DEPARTURE_YEAR
        
    departure_date_obj_check = helpers.validate_date_format(dep_date_str_for_validation)
    if not departure_date_obj_check:
        logger.warning(f"back_flex_ret_date_to_range_handler: Невалидная дата вылета: {dep_date_str_for_validation}")
        if query.message:
            try:
                await query.edit_message_text("Дата вылета указана некорректно. Пожалуйста, выберите ее заново.", reply_markup=None)
            except Exception as e_edit: logger.error(f"Ошибка редактирования (невалидная дата вылета): {e_edit}")
        
        await ask_year(query, context, "🗓️ Выберите год вылета:",
                       callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_year_",
                       keyboard_back_callback=config.CB_BACK_FLEX_DEP_YEAR_TO_ASK_DATES)
        return config.SELECTING_FLEX_DEPARTURE_YEAR

    # 4. Если все необходимые данные есть, возвращаемся к выбору диапазона дней для возврата
    month_name = config.RUSSIAN_MONTHS.get(return_month, str(return_month))
    await ask_date_range(
        source_update_or_query=query,
        context=context,
        year=return_year,
        month=return_month,
        message_text=f"Выбран: {month_name} {return_year}. 📏 Выберите диапазон дней для возврата:",
        callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_range_",
        keyboard_back_callback=config.CB_BACK_FLEX_RET_RANGE_TO_MONTH # Назад к выбору месяца возврата
    )
    return config.SELECTING_FLEX_RETURN_DATE_RANGE

# --- УНИВЕРСАЛЬНЫЕ ОБРАБОТЧИКИ ДЛЯ ЦЕНЫ (ОБНОВЛЕННЫЕ) ---
async def handle_price_option_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (код этой функции, как в Части 3 предыдущего ответа) ...
    # Убедитесь, что все проверки на None для chat_id и message сделаны
    query = update.callback_query
    if not query: return ConversationHandler.END
    await query.answer()
    choice: PriceChoice = query.data # type: ignore 
    context.user_data['price_preference_choice'] = choice
    current_flow = context.user_data.get('current_search_flow', config.FLOW_STANDARD)
    effective_chat_id = update.effective_chat.id if update.effective_chat else (query.message.chat_id if query.message else None)
    if not effective_chat_id:
        logger.error("handle_price_option_selected: effective_chat_id не определен.")
        return ConversationHandler.END

    if choice == config.CALLBACK_PRICE_CUSTOM:
        reply_markup_custom = InlineKeyboardMarkup([[InlineKeyboardButton(config.MSG_BACK, callback_data=config.CB_BACK_PRICE_TO_ENTERING_CUSTOM)]])
        if query.message:
            try: await query.edit_message_text(text=config.MSG_MAX_PRICE_PROMPT, reply_markup=reply_markup_custom)
            except Exception: await context.bot.send_message(effective_chat_id, config.MSG_MAX_PRICE_PROMPT, reply_markup=reply_markup_custom)
        else: await context.bot.send_message(effective_chat_id, config.MSG_MAX_PRICE_PROMPT, reply_markup=reply_markup_custom)
        return config.ENTERING_CUSTOM_PRICE
    elif choice == config.CALLBACK_PRICE_LOWEST or choice == config.CALLBACK_PRICE_ALL:
        context.user_data['max_price'] = None
        next_step_msg = ""
        if current_flow == config.FLOW_STANDARD:
            next_step_msg = config.MSG_PRICE_CHOICE_LOWEST_STANDARD if choice == config.CALLBACK_PRICE_LOWEST else config.MSG_PRICE_CHOICE_ALL_STANDARD
            if query.message:
                try: await query.edit_message_text(text=next_step_msg)
                except Exception as e: logger.warning(f"Не удалось изменить сообщение: {e}"); await context.bot.send_message(effective_chat_id, next_step_msg)
            else: await context.bot.send_message(effective_chat_id, next_step_msg)
            return await launch_flight_search(update, context)
        else: # FLOW_FLEX
            next_step_msg = config.MSG_PRICE_CHOICE_SAVED_FLEX
            if query.message:
                try: await query.edit_message_text(text=next_step_msg)
                except Exception as e: logger.warning(f"Не удалось изменить сообщение: {e}"); await context.bot.send_message(effective_chat_id, next_step_msg)
            else: await context.bot.send_message(effective_chat_id, next_step_msg)
            back_cb_for_ask_dep = config.CB_BACK_FLEX_ASK_DEP_TO_PRICE
            await context.bot.send_message(
                chat_id=effective_chat_id,
                text=config.MSG_ASK_FLEX_DEPARTURE_AIRPORT_PROMPT,
                reply_markup=keyboards.get_yes_no_keyboard(
                    yes_callback=config.CALLBACK_PREFIX_FLEX + "ask_dep_yes",
                    no_callback=config.CALLBACK_PREFIX_FLEX + "ask_dep_no",
                    back_callback_data=back_cb_for_ask_dep))
            return config.ASK_FLEX_DEPARTURE_AIRPORT
    else:
        logger.warning(f"Неизвестный выбор опции цены: {choice}")
        if query.message:
            try: await query.edit_message_text("Неизвестный выбор. Попробуйте снова.")
            except Exception: pass
        return ConversationHandler.END


async def enter_custom_price_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (код этой функции, как в Части 3 предыдущего ответа) ...
    # Убедитесь, что все проверки на None для chat_id и message сделаны
    if not update.message or not update.message.text:
        if update.message:
             await update.message.reply_text(config.MSG_INVALID_PRICE_INPUT, 
                                            reply_markup=keyboards.get_price_options_keyboard())
        return config.SELECTING_PRICE_OPTION 
    user_input = update.message.text
    price = helpers.validate_price(user_input)
    current_flow = context.user_data.get('current_search_flow', config.FLOW_STANDARD)
    if price is None:
        back_cb_for_price_options = None
        if current_flow == config.FLOW_STANDARD:
            back_cb_for_price_options = config.CB_BACK_PRICE_TO_STD_ARR_CITY_ONEWAY if context.user_data.get('flight_type_one_way') else config.CB_BACK_PRICE_TO_STD_RET_DATE_TWOWAY
        elif current_flow == config.FLOW_FLEX:
            back_cb_for_price_options = config.CB_BACK_PRICE_TO_FLEX_FLIGHT_TYPE
        await update.message.reply_text(
            config.MSG_INVALID_PRICE_INPUT,
            reply_markup=keyboards.get_price_options_keyboard(back_callback_data=back_cb_for_price_options))
        return config.SELECTING_PRICE_OPTION
    context.user_data['max_price'] = price
    context.user_data['price_preference_choice'] = config.CALLBACK_PRICE_CUSTOM
    await update.message.reply_text(config.MSG_MAX_PRICE_SET_INFO.format(price=price))
    if current_flow == config.FLOW_STANDARD:
        return await launch_flight_search(update, context)
    else: # FLOW_FLEX
        back_cb_for_ask_dep = config.CB_BACK_FLEX_ASK_DEP_TO_PRICE
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=config.MSG_ASK_FLEX_DEPARTURE_AIRPORT_PROMPT,
            reply_markup=keyboards.get_yes_no_keyboard(
                yes_callback=config.CALLBACK_PREFIX_FLEX + "ask_dep_yes",
                no_callback=config.CALLBACK_PREFIX_FLEX + "ask_dep_no",
                back_callback_data=back_cb_for_ask_dep))
        return config.ASK_FLEX_DEPARTURE_AIRPORT

# ... (handle_search_other_airports_decision, cancel_handler, error_handler_conv, handle_invalid_price_choice_fallback БЕЗ ИЗМЕНЕНИЙ) ...
# bot/handlers.py
# ... (после process_and_send_flights) ...

async def handle_search_other_airports_decision(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        logger.warning("handle_search_other_airports_decision вызван без query.")
        chat_id_fallback = update.effective_chat.id if update.effective_chat else None
        if chat_id_fallback: # Попытка отправить сообщение об ошибке, если есть куда
             await context.bot.send_message(chat_id_fallback, config.MSG_ERROR_OCCURRED + " (internal_hsoad).")
        return ConversationHandler.END # Завершаем, если нет query

    await query.answer()
    effective_chat_id = update.effective_chat.id if update.effective_chat else (query.message.chat_id if query.message else None)

    if not effective_chat_id: # Еще одна проверка на chat_id
        logger.error("handle_search_other_airports_decision: не удалось определить effective_chat_id.")
        return ConversationHandler.END

    if query.data == config.CALLBACK_YES_OTHER_AIRPORTS:
        departure_country = context.user_data.get('departure_country')
        original_departure_iata = context.user_data.get('departure_airport_iata')
        # original_arrival_city_name_for_weather уже получаем ниже, перед циклом

        # --- НАЧАЛО ИЗМЕНЕНИЙ: Получение всех параметров дат ---
        # Эти параметры должны быть уже в context.user_data после первоначального выбора пользователя
        user_max_price: Union[Decimal, None] = context.user_data.get('max_price')
        price_preference: Union[config.PriceChoice, None] = context.user_data.get('price_preference_choice')
        is_one_way: bool = context.user_data.get('flight_type_one_way', True)

        # Даты вылета из user_data (аналогично как в launch_flight_search)
        single_dep_date_str: Union[str, None] = context.user_data.get('departure_date')
        is_dep_range_search: bool = context.user_data.get('is_departure_range_search', False)
        explicit_dep_date_from_orig: Union[str, None] = context.user_data.get('departure_date_from')
        explicit_dep_date_to_orig: Union[str, None] = context.user_data.get('departure_date_to')

        # Определяем, какие параметры дат вылета передавать в find_flights_with_fallback
        dep_date_for_offset_or_year_search_alt = single_dep_date_str if not is_dep_range_search else None
        explicit_dep_date_from_alt = explicit_dep_date_from_orig if is_dep_range_search else None
        explicit_dep_date_to_alt = explicit_dep_date_to_orig if is_dep_range_search else None

        # Даты возврата из user_data (аналогично как в launch_flight_search)
        single_ret_date_str: Union[str, None] = None
        is_ret_range_search: bool = False
        explicit_ret_date_from_orig: Union[str, None] = None
        explicit_ret_date_to_orig: Union[str, None] = None
        ret_date_for_offset_search_alt = None

        if not is_one_way:
            single_ret_date_str = context.user_data.get('return_date')
            is_ret_range_search = context.user_data.get('is_return_range_search', False)
            explicit_ret_date_from_orig = context.user_data.get('return_date_from')
            explicit_ret_date_to_orig = context.user_data.get('return_date_to')
            ret_date_for_offset_search_alt = single_ret_date_str if not is_ret_range_search else None
        
        # Определяем, какие параметры дат возврата передавать
        explicit_ret_date_from_alt = explicit_ret_date_from_orig if not is_one_way and is_ret_range_search else None
        explicit_ret_date_to_alt = explicit_ret_date_to_orig if not is_one_way and is_ret_range_search else None
        # --- КОНЕЦ ИЗМЕНЕНИЙ: Получение всех параметров дат ---

        if not departure_country or not original_departure_iata:
            msg_no_data = "🤷 Не удалось получить данные для поиска по другим аэропортам. Начните новый поиск."
            if query.message:
                try: await query.edit_message_text(text=msg_no_data)
                except Exception: await context.bot.send_message(effective_chat_id, msg_no_data)
            else: await context.bot.send_message(effective_chat_id, msg_no_data)
            
            await context.bot.send_message(
                chat_id=effective_chat_id,
                text=config.MSG_ASK_SAVE_SEARCH,
                reply_markup=keyboards.get_save_search_keyboard()
            )
            return config.ASK_SAVE_SEARCH_PREFERENCES

        text_searching_alt = f"⏳ Ищу рейсы из других аэропортов в {departure_country}..."
        if query.message:
            try: await query.edit_message_text(text=text_searching_alt)
            except Exception: await context.bot.send_message(effective_chat_id, text=text_searching_alt)
        else: await context.bot.send_message(effective_chat_id, text=text_searching_alt)
        
        context.user_data["_already_searched_alternatives"] = True # Флаг, что уже искали

        all_airports_in_country = config.COUNTRIES_DATA.get(departure_country, {})
        alternative_airports = {
            city: iata for city, iata in all_airports_in_country.items() if iata != original_departure_iata
        }

        if not alternative_airports:
            no_alt_airports_msg = f"🤷 В стране {departure_country} нет других аэропортов для поиска."
            await context.bot.send_message(chat_id=effective_chat_id, text=no_alt_airports_msg)
            # Переход к сохранению будет ниже, вне этого else
        else:
            # Используем defaultdict(dict), если flights_from_alt_by_date это Dict[str, list]
            # и мы хотим хранить {airport_key: {date_key: [flights]}}
            # В вашем коде found_alternative_flights_data[key] = processed_for_this_airport,
            # где processed_for_this_airport это Dict[str, list]. Значит тип правильный.
            found_alternative_flights_data: Dict[str, Dict[str, list]] = defaultdict(dict)
            found_any = False
            original_arrival_city_name_for_weather = context.user_data.get('arrival_city_name') # Для погоды

            for current_alternative_city_name, iata_code in alternative_airports.items():
                logger.info(f"Поиск из альтернативного аэропорта: {current_alternative_city_name} ({iata_code})")
                text_checking_alt = f"⏳ Проверяю вылеты из {current_alternative_city_name} ({iata_code})..."
                await context.bot.send_message(chat_id=effective_chat_id, text=text_checking_alt)

                # --- ИЗМЕНЕННЫЙ ВЫЗОВ find_flights_with_fallback ---
                flights_from_alt_by_date: Dict[str, list] = await flight_api.find_flights_with_fallback(
                    departure_airport_iata=iata_code, # Новый аэропорт вылета
                    arrival_airport_iata=context.user_data.get('arrival_airport_iata'), # Оригинальный аэропорт прилета
                    
                    # Параметры для +/- offset или годового поиска (будут None если был явный диапазон)
                    departure_date_str=dep_date_for_offset_or_year_search_alt,
                    return_date_str=ret_date_for_offset_search_alt,
                    
                    max_price=user_max_price,
                    is_one_way=is_one_way,
                    
                    # Параметры для явного диапазона дат
                    explicit_departure_date_from=explicit_dep_date_from_alt,
                    explicit_departure_date_to=explicit_dep_date_to_alt,
                    explicit_return_date_from=explicit_ret_date_from_alt,
                    explicit_return_date_to=explicit_ret_date_to_alt
                    # search_days_offset можно оставить по умолчанию, если не нужно менять
                )
                # --- КОНЕЦ ИЗМЕНЕННОГО ВЫЗОВА ---
                
                if flights_from_alt_by_date: 
                    processed_for_this_airport: Dict[str, list]
                    if price_preference == config.CALLBACK_PRICE_LOWEST:
                        processed_for_this_airport = helpers.filter_cheapest_flights(flights_from_alt_by_date)
                    else: 
                        processed_for_this_airport = flights_from_alt_by_date
                    
                    if processed_for_this_airport: 
                        found_any = True
                        # Ключ - информация об аэропорте, значение - словарь {дата: [рейсы]}
                        found_alternative_flights_data[f"{current_alternative_city_name} ({iata_code})"] = processed_for_this_airport
            
            # Оригинальная логика отображения найденных альтернативных рейсов
            if found_any:
                alt_flights_final_message_parts = [f"✈️✨ Найдены рейсы из других аэропортов в {departure_country}:\n"]
                for source_airport_info, flights_by_sub_date_dict_item in found_alternative_flights_data.items():
                    if not flights_by_sub_date_dict_item: continue
                    
                    city_name_for_current_dep_weather = source_airport_info.split('(')[0].strip()
                    alt_flights_final_message_parts.append(f"\n✈️ --- Из аэропорта: {source_airport_info} ---\n")
                    
                    # Сортируем даты для каждого аэропорта
                    sorted_dates_for_airport = sorted(flights_by_sub_date_dict_item.items())
                    for date_key, flights_on_this_date in sorted_dates_for_airport:
                        try:
                            date_obj_alt = datetime.strptime(date_key, "%Y-%m-%d")
                            alt_flights_final_message_parts.append(f"\n--- 📅 {date_obj_alt.strftime('%d %B %Y (%A)')} ---\n")
                        except ValueError:
                            alt_flights_final_message_parts.append(f"\n--- 📅 {date_key} ---\n")
                        
                        for flight_alt in flights_on_this_date:
                            formatted_flight_msg = await message_formatter.format_flight_details(
                                flight_alt,
                                departure_city_name=city_name_for_current_dep_weather, # Используем текущий альтернативный город вылета
                                arrival_city_name=original_arrival_city_name_for_weather # Оригинальный город прилета
                            )
                            alt_flights_final_message_parts.append(formatted_flight_msg)
                        alt_flights_final_message_parts.append("\n") # Добавляем пустую строку после рейсов на одну дату
                
                full_alt_message = "".join(alt_flights_final_message_parts)
                if len(full_alt_message.strip()) > len(f"✈️✨ Найдены рейсы из других аэропортов в {departure_country}:\n".strip()):
                    for i_alt_msg in range(0, len(full_alt_message), 4096): # 4096 - лимит длины сообщения Telegram
                        chunk_alt = full_alt_message[i_alt_msg:i_alt_msg + 4096]
                        try:
                            await context.bot.send_message(chat_id=effective_chat_id, text=chunk_alt, parse_mode="HTML", disable_web_page_preview=True)
                        except Exception as e_send_alt_chunk:
                            logger.error(f"Не удалось отправить чанк альтернативных рейсов: {e_send_alt_chunk}")
                            if i_alt_msg == 0: # Если это первый чанк и он не отправился
                                await context.bot.send_message(chat_id=effective_chat_id, text="Произошла ошибка при отображении части альтернативных результатов.")
                else: 
                     no_alt_flights_msg = f"🤷 Из других аэропортов в {departure_country} рейсов по вашим критериям не найдено (после форматирования)."
                     await context.bot.send_message(chat_id=effective_chat_id, text=no_alt_flights_msg)
            else: # not found_any
                no_alt_flights_msg = f"🤷 Из других аэропортов в {departure_country} рейсов по вашим критериям не найдено."
                await context.bot.send_message(chat_id=effective_chat_id, text=no_alt_flights_msg)

    elif query.data == config.CALLBACK_NO_OTHER_AIRPORTS:
        msg_cancel_alt_search = "🛑 Понял. Поиск из других аэропортов отменен."
        if query.message: 
            try: await query.edit_message_text(text=msg_cancel_alt_search)
            except Exception: await context.bot.send_message(effective_chat_id, msg_cancel_alt_search)
        else: await context.bot.send_message(effective_chat_id, msg_cancel_alt_search)
    
    # Вне зависимости от выбора и результатов, предлагаем сохранить исходный поиск
    await context.bot.send_message(
        chat_id=effective_chat_id,
        text=config.MSG_ASK_SAVE_SEARCH,
        reply_markup=keyboards.get_save_search_keyboard()
    )
    return config.ASK_SAVE_SEARCH_PREFERENCES


async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message_to_send = config.MSG_CANCELLED
    reply_markup_to_send = ReplyKeyboardRemove()
    chat_id_to_send = update.effective_chat.id if update.effective_chat else None
    if update.callback_query:
        await update.callback_query.answer()
        target_chat_id_cb = update.callback_query.message.chat_id if update.callback_query.message else chat_id_to_send
        if target_chat_id_cb:
            if update.callback_query.message:
                try: await update.callback_query.edit_message_text(text=message_to_send)
                except Exception: await context.bot.send_message(chat_id=target_chat_id_cb, text=message_to_send, reply_markup=reply_markup_to_send)
            else: await context.bot.send_message(chat_id=target_chat_id_cb, text=message_to_send, reply_markup=reply_markup_to_send)
    elif update.message and chat_id_to_send:
        await update.message.reply_text(message_to_send, reply_markup=reply_markup_to_send)
    elif chat_id_to_send:
        await context.bot.send_message(chat_id=chat_id_to_send, text=message_to_send, reply_markup=reply_markup_to_send)
    context.user_data.clear()
    return ConversationHandler.END

async def error_handler_conv(update: Union[Update, None], context: ContextTypes.DEFAULT_TYPE) -> Union[int, None]:
    logger.error(f"Ошибка в ConversationHandler: {context.error}", exc_info=context.error)
    chat_id_to_send_error = None
    if update and isinstance(update, Update) and update.effective_chat:
        chat_id_to_send_error = update.effective_chat.id
    elif update and isinstance(update, CallbackQuery) and update.message:
        chat_id_to_send_error = update.message.chat_id
    if chat_id_to_send_error:
        try:
            await context.bot.send_message(
                chat_id=chat_id_to_send_error,
                text=config.MSG_ERROR_OCCURRED + " 🙏 Пожалуйста, попробуйте начать заново с /start.",
                reply_markup=ReplyKeyboardRemove())
        except Exception as e: logger.error(f"Не удалось отправить сообщение об ошибке пользователю: {e}")
    if context.user_data: context.user_data.clear()
    return ConversationHandler.END

async def handle_invalid_price_choice_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query:
        await query.answer(config.MSG_INVALID_PRICE_CHOICE_FALLBACK, show_alert=True)
        user_identifier = query.from_user.id if query.from_user else "unknown_user"
        message_identifier = query.message.message_id if query.message else "unknown_message"
        logger.warning(
            f"Пользователь {user_identifier} нажал кнопку цены '{query.data}' на сообщении "
            f"{message_identifier} в несоответствующем состоянии диалога.")
        
# НОВЫЙ МЕТОД
async def handle_entire_range_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает выбор всего диапазона дат (кнопка "Выбрать весь диапазон ДД-ДД").
    """
    query = update.callback_query
    if not query or not query.data:
        logger.warning("handle_entire_range_selected вызван без query или query.data")
        return ConversationHandler.END
    
    await query.answer()

    # Callback data формат: config.CALLBACK_ENTIRE_RANGE_SELECTED + "dep_YYYY-MM-DDstart-DDend"
    # или config.CALLBACK_ENTIRE_RANGE_SELECTED + "ret_YYYY-MM-DDstart-DDend"
    try:
        # Убираем префикс
        payload = query.data.replace(config.CALLBACK_ENTIRE_RANGE_SELECTED, "")
        # Разделяем тип (dep/ret) и строку с датами
        range_type, date_info_str = payload.split("_", 1) # "dep", "YYYY-MM-DDstart-DDend"
        
        # Парсим год, месяц, день начала, день конца
        year_str, month_str, start_day_str, end_day_str = date_info_str.split('-')
        year = int(year_str)
        month = int(month_str)
        start_day = int(start_day_str)
        end_day = int(end_day_str)
    except (ValueError, IndexError) as e:
        logger.error(f"Ошибка парсинга callback_data в handle_entire_range_selected: {query.data}, {e}")
        await query.edit_message_text("Произошла ошибка при обработке вашего выбора. Пожалуйста, /start")
        return ConversationHandler.END

    date_from_str = f"{year}-{month:02d}-{start_day:02d}"
    date_to_str = f"{year}-{month:02d}-{end_day:02d}"
    
    # Валидация дат (минимальная)
    try:
        datetime.strptime(date_from_str, "%Y-%m-%d")
        datetime.strptime(date_to_str, "%Y-%m-%d")
    except ValueError:
        logger.error(f"Некорректный формат дат после парсинга в handle_entire_range_selected: from={date_from_str}, to={date_to_str}")
        await query.edit_message_text("Произошла ошибка (неверный формат даты). Пожалуйста, /start")
        return ConversationHandler.END

    current_flow = context.user_data.get('current_search_flow')
    month_name_rus = config.RUSSIAN_MONTHS.get(month, str(month))
    selected_range_text = f"{start_day:02d}-{end_day:02d} {month_name_rus} {year}"

    if range_type == "dep":
        context.user_data['departure_date_from'] = date_from_str
        context.user_data['departure_date_to'] = date_to_str
        context.user_data.pop('departure_date', None) # Очищаем одиночную дату
        context.user_data['is_departure_range_search'] = True
        
        # Очищаем данные о конкретном диапазоне для выбора одиночной даты, если они были
        context.user_data.pop('departure_date_range_str', None) 

        await query.edit_message_text(text=f"✈️ Диапазон дат вылета: {selected_range_text}")

        if current_flow == config.FLOW_STANDARD:
            # Переход к выбору страны прилета
            await context.bot.send_message(
                chat_id=query.message.chat_id, # Используем chat_id из query.message
                text="🌍 Выберите страну прилёта:", 
                reply_markup=keyboards.get_country_reply_keyboard()
            )
            return config.S_SELECTING_ARRIVAL_COUNTRY
        elif current_flow == config.FLOW_FLEX:
            if context.user_data.get('flight_type_one_way', True):
                # Если это гибкий поиск в одну сторону, и даты вылета (диапазон) заданы,
                # то можно запускать поиск. (Предполагается, что аэропорт вылета уже задан)
                if not context.user_data.get('departure_airport_iata'):
                    await context.bot.send_message(chat_id=query.message.chat_id, text="Не указан аэропорт вылета для гибкого поиска. /start")
                    return ConversationHandler.END
                return await launch_flight_search(update, context)
            else: # Гибкий поиск туда-обратно, нужны даты возврата
                # Переход к выбору года возврата
                # query здесь - это CallbackQuery от выбора диапазона дат вылета,
                # ask_year ожидает Update или CallbackQuery.
                await ask_year(query, context, "🗓️ Выберите год обратного вылета:",
                               callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_year_",
                               # CB_BACK_FLEX_RET_YEAR_TO_DEP_DATE должен вести обратно к выбору ДАТЫ вылета,
                               # но мы выбрали ДИАПАЗОН. Это "назад" может потребовать доработки или
                               # можно решить, что после выбора диапазона "назад" на этом шаге не будет столь явным.
                               # Пока оставим как есть, но это потенциальное место для улучшения UX кнопки "Назад".
                               keyboard_back_callback=config.CB_BACK_FLEX_RET_YEAR_TO_DEP_DATE) 
                return config.SELECTING_FLEX_RETURN_YEAR
        else: # Неизвестный current_flow
            logger.error(f"Неизвестный current_search_flow: {current_flow} в handle_entire_range_selected для 'dep'")
            await context.bot.send_message(chat_id=query.message.chat_id, text="Произошла системная ошибка. /start")
            return ConversationHandler.END
            
    elif range_type == "ret":
        # Проверка, что дата возврата (начало диапазона) не раньше даты вылета
        departure_date_final_str = context.user_data.get('departure_date')
        departure_date_from_range_str = context.user_data.get('departure_date_from')

        if departure_date_final_str: # Если была выбрана одиночная дата вылета
            dep_dt_obj = helpers.validate_date_format(departure_date_final_str)
        elif departure_date_from_range_str: # Если был выбран диапазон дат вылета, берем его начало
            dep_dt_obj = helpers.validate_date_format(departure_date_from_range_str)
        else: # Даты вылета нет - ошибка
            await query.edit_message_text("Ошибка: не найдена дата вылета для сравнения. /start")
            return ConversationHandler.END

        current_return_range_start_obj = helpers.validate_date_format(date_from_str)
        if not dep_dt_obj or not current_return_range_start_obj or current_return_range_start_obj < dep_dt_obj:
            await query.edit_message_text(f"🚫 Диапазон возврата ({selected_range_text}) не может начинаться раньше даты вылета ({dep_dt_obj.strftime('%d-%m-%Y') if dep_dt_obj else 'N/A'}). Пожалуйста, выберите корректный диапазон для возврата.")
            # Чтобы пользователь мог выбрать заново, нужно вернуть его на шаг выбора диапазона возврата.
            # Это требует сохранения year, month, range_start, range_end из предыдущего шага (выбора диапазона возврата).
            # Для простоты, пока отправим его выбирать год возврата снова.
            # Либо, если данные есть в user_data (return_year, return_month), можно попытаться переспросить диапазон.
            # Этот блок лучше вызывать в соответствующем хендлере выбора диапазона дат возврата (например, flex_return_date_range_selected).
            # Но так как это уже выбор "всего диапазона", то эта проверка здесь уместна.
            # Возвращаем на предыдущий шаг - выбор диапазона дат возврата (если возможно) или месяца/года.
            # TODO: Улучшить возврат на предыдущий шаг. Пока просто ошибка и /start.
            # Этого не должно происходить, если клавиатура генерируется правильно с min_allowed_date
            logger.warning(f"Попытка выбрать диапазон возврата раньше даты вылета. Dep: {dep_dt_obj}, RetFrom: {current_return_range_start_obj}")
            # Попытка вернуть к выбору диапазона дат возврата (самый близкий шаг)
            ret_year = context.user_data.get('return_year')
            ret_month = context.user_data.get('return_month')
            if ret_year and ret_month:
                month_name_ret = config.RUSSIAN_MONTHS.get(ret_month, str(ret_month))
                cb_prefix_ret = config.CALLBACK_PREFIX_STANDARD if current_flow == config.FLOW_STANDARD else config.CALLBACK_PREFIX_FLEX
                cb_back_ret = config.CB_BACK_STD_RET_RANGE_TO_MONTH if current_flow == config.FLOW_STANDARD else config.CB_BACK_FLEX_RET_RANGE_TO_MONTH

                await ask_date_range(query, context, ret_year, ret_month,
                                   f"Выбран: {month_name_ret} {ret_year}. 📏 Выберите диапазон дат для возврата:",
                                   callback_prefix=cb_prefix_ret + "ret_range_",
                                   keyboard_back_callback=cb_back_ret)
                if current_flow == config.FLOW_STANDARD: return config.S_SELECTING_RETURN_DATE_RANGE
                if current_flow == config.FLOW_FLEX: return config.SELECTING_FLEX_RETURN_DATE_RANGE
            
            await query.edit_message_text("Ошибка в дате возврата. Попробуйте /start") # Fallback
            return ConversationHandler.END


        context.user_data['return_date_from'] = date_from_str
        context.user_data['return_date_to'] = date_to_str
        context.user_data.pop('return_date', None) # Очищаем одиночную дату
        context.user_data['is_return_range_search'] = True
        
        context.user_data.pop('return_date_range_str', None)

        await query.edit_message_text(text=f"✈️ Диапазон дат возврата: {selected_range_text}")

        if current_flow == config.FLOW_STANDARD:
            # Переход к выбору опции цены
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=config.MSG_PRICE_OPTION_PROMPT,
                reply_markup=keyboards.get_price_options_keyboard(back_callback_data=config.CB_BACK_PRICE_TO_STD_RET_DATE_TWOWAY)
            )
            return config.SELECTING_PRICE_OPTION
        elif current_flow == config.FLOW_FLEX:
            # Все данные для гибкого поиска туда-обратно собраны
            if not context.user_data.get('departure_airport_iata'): # Нужен аэропорт вылета
                 await context.bot.send_message(chat_id=query.message.chat_id, text="Не указан аэропорт вылета для гибкого поиска. /start")
                 return ConversationHandler.END
            return await launch_flight_search(update, context)
        else: # Неизвестный current_flow
            logger.error(f"Неизвестный current_search_flow: {current_flow} в handle_entire_range_selected для 'ret'")
            await context.bot.send_message(chat_id=query.message.chat_id, text="Произошла системная ошибка. /start")
            return ConversationHandler.END
    else:
        logger.error(f"Неизвестный range_type: {range_type} в handle_entire_range_selected")
        await query.edit_message_text("Произошла ошибка при обработке типа диапазона. Пожалуйста, /start")
        return ConversationHandler.END

    # Этот return не должен достигаться, если все ветки обработаны
    return ConversationHandler.END        

# ИМПОРТ handlers_saved_search (ПОСЛЕ ВСЕХ ФУНКЦИЙ ЭТОГО ФАЙЛА, ПЕРЕД create_conversation_handler)
from . import handlers_saved_search

# --- СОЗДАНИЕ CONVERSATIONHANDLER ---
def create_conversation_handler() -> ConversationHandler:
    # Обертки
    async def _handle_save_search_preference_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        return await handlers_saved_search.handle_save_search_preference_callback(update, context, launch_flight_search_func=launch_flight_search)

    async def _start_last_saved_search_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        return await handlers_saved_search.start_last_saved_search_callback(update, context, launch_flight_search_func=launch_flight_search)

    price_option_pattern = f"^({config.CALLBACK_PRICE_CUSTOM}|{config.CALLBACK_PRICE_LOWEST}|{config.CALLBACK_PRICE_ALL})$"
    price_fallback_pattern = r"^price_.*$"

    # Паттерн для выбора всего диапазона дат
    # Он должен соответствовать формату, который вы генерируете в keyboards.py:
    # f"{CALLBACK_ENTIRE_RANGE_SELECTED}{range_selection_type}_YYYY-MM-DDstart-DDend"
    entire_range_pattern_dep = f"^{config.CALLBACK_ENTIRE_RANGE_SELECTED}dep_"
    entire_range_pattern_ret = f"^{config.CALLBACK_ENTIRE_RANGE_SELECTED}ret_"


    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start_command),
            CallbackQueryHandler(start_search_callback, pattern='^(start_standard_search|start_flex_search)$'),
            CallbackQueryHandler(start_flex_anywhere_callback, pattern='^start_flex_anywhere$'),
            CallbackQueryHandler(_start_last_saved_search_wrapper, pattern=f"^{config.CALLBACK_START_LAST_SAVED_SEARCH}$")
        ],
        states={
            # --- Стандартный поиск ---
            config.S_SELECTING_FLIGHT_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, standard_flight_type)],
            config.S_SELECTING_DEPARTURE_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, standard_departure_country)],
            config.S_SELECTING_DEPARTURE_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, standard_departure_city)],
            config.S_SELECTING_DEPARTURE_YEAR: [
                CallbackQueryHandler(standard_departure_year_selected, pattern=f"^{config.CALLBACK_PREFIX_STANDARD}dep_year_"),
                CallbackQueryHandler(back_std_dep_year_to_city_handler, pattern=f"^{config.CB_BACK_STD_DEP_YEAR_TO_CITY}$")
            ],
            config.S_SELECTING_DEPARTURE_MONTH: [
                CallbackQueryHandler(standard_departure_month_selected, pattern=f"^{config.CALLBACK_PREFIX_STANDARD}dep_month_"),
                CallbackQueryHandler(back_std_dep_month_to_year_handler, pattern=f"^{config.CB_BACK_STD_DEP_MONTH_TO_YEAR}$")
            ],
            config.S_SELECTING_DEPARTURE_DATE_RANGE: [
                CallbackQueryHandler(standard_departure_date_range_selected, pattern=f"^{config.CALLBACK_PREFIX_STANDARD}dep_range_"),
                CallbackQueryHandler(back_std_dep_range_to_month_handler, pattern=f"^{config.CB_BACK_STD_DEP_RANGE_TO_MONTH}$")
            ],
            config.S_SELECTING_DEPARTURE_DATE: [ # Состояние выбора конкретной даты вылета
                CallbackQueryHandler(standard_departure_date_selected, pattern=f"^{config.CALLBACK_PREFIX_STANDARD}dep_date_"), # Выбор одиночной даты
                CallbackQueryHandler(handle_entire_range_selected, pattern=entire_range_pattern_dep), # Выбор всего диапазона для вылета
                CallbackQueryHandler(back_std_dep_date_to_range_handler, pattern=f"^{config.CB_BACK_STD_DEP_DATE_TO_RANGE}$")
            ],
            config.S_SELECTING_ARRIVAL_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, standard_arrival_country)],
            config.S_SELECTING_ARRIVAL_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, standard_arrival_city)],
            config.S_SELECTING_RETURN_YEAR: [
                CallbackQueryHandler(standard_return_year_selected, pattern=f"^{config.CALLBACK_PREFIX_STANDARD}ret_year_"),
                CallbackQueryHandler(back_std_ret_year_to_arr_city_handler, pattern=f"^{config.CB_BACK_STD_RET_YEAR_TO_ARR_CITY}$")
            ],
            config.S_SELECTING_RETURN_MONTH: [
                CallbackQueryHandler(standard_return_month_selected, pattern=f"^{config.CALLBACK_PREFIX_STANDARD}ret_month_"),
                CallbackQueryHandler(back_std_ret_month_to_year_handler, pattern=f"^{config.CB_BACK_STD_RET_MONTH_TO_YEAR}$")
            ],
            config.S_SELECTING_RETURN_DATE_RANGE: [
                CallbackQueryHandler(standard_return_date_range_selected, pattern=f"^{config.CALLBACK_PREFIX_STANDARD}ret_range_"),
                CallbackQueryHandler(back_std_ret_range_to_month_handler, pattern=f"^{config.CB_BACK_STD_RET_RANGE_TO_MONTH}$")
            ],
            config.S_SELECTING_RETURN_DATE: [ # Состояние выбора конкретной даты возврата
                CallbackQueryHandler(standard_return_date_selected, pattern=f"^{config.CALLBACK_PREFIX_STANDARD}ret_date_"), # Выбор одиночной даты
                CallbackQueryHandler(handle_entire_range_selected, pattern=entire_range_pattern_ret), # Выбор всего диапазона для возврата
                CallbackQueryHandler(back_std_ret_date_to_range_handler, pattern=f"^{config.CB_BACK_STD_RET_DATE_TO_RANGE}$")
            ],

            # --- Гибкий поиск ---
            config.SELECTING_FLEX_FLIGHT_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, flex_flight_type)],
            config.ASK_FLEX_DEPARTURE_AIRPORT: [
                CallbackQueryHandler(flex_ask_departure_airport, pattern=f"^{config.CALLBACK_PREFIX_FLEX}ask_dep_"),
                CallbackQueryHandler(back_flex_ask_dep_to_price_handler, pattern=f"^{config.CB_BACK_FLEX_ASK_DEP_TO_PRICE}$")
            ],
            config.SELECTING_FLEX_DEPARTURE_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, flex_departure_country)],
            config.SELECTING_FLEX_DEPARTURE_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, flex_departure_city)],
            config.ASK_FLEX_ARRIVAL_AIRPORT: [
                CallbackQueryHandler(flex_ask_arrival_airport, pattern=f"^{config.CALLBACK_PREFIX_FLEX}ask_arr_"),
                CallbackQueryHandler(back_flex_ask_arr_to_dep_city_handler, pattern=f"^{config.CB_BACK_FLEX_ASK_ARR_TO_DEP_CITY}$")
            ],
            config.SELECTING_FLEX_ARRIVAL_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, flex_arrival_country)],
            config.SELECTING_FLEX_ARRIVAL_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, flex_arrival_city)],
            config.ASK_FLEX_DATES: [
                CallbackQueryHandler(flex_ask_dates, pattern=f"^(?:{config.CALLBACK_PREFIX_FLEX}ask_dates_yes|{config.CALLBACK_NO_SPECIFIC_DATES})$"),
                CallbackQueryHandler(back_flex_ask_dates_to_location_handler, pattern=f"^{config.CB_BACK_FLEX_ASK_DATES_TO_ARR_CITY}$"),
                CallbackQueryHandler(back_flex_ask_dates_to_location_handler, pattern=f"^{config.CB_BACK_FLEX_ASK_DATES_TO_DEP_CITY_NO_ARR}$")
            ],
            config.SELECTING_FLEX_DEPARTURE_YEAR: [
                CallbackQueryHandler(flex_departure_year_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}dep_year_"),
                CallbackQueryHandler(back_flex_dep_year_to_ask_dates_handler, pattern=f"^{config.CB_BACK_FLEX_DEP_YEAR_TO_ASK_DATES}$")
            ],
            config.SELECTING_FLEX_DEPARTURE_MONTH: [
                CallbackQueryHandler(flex_departure_month_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}dep_month_"),
                CallbackQueryHandler(back_flex_dep_month_to_year_handler, pattern=f"^{config.CB_BACK_FLEX_DEP_MONTH_TO_YEAR}$")
            ],
            config.SELECTING_FLEX_DEPARTURE_DATE_RANGE: [
                CallbackQueryHandler(flex_departure_date_range_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}dep_range_"),
                CallbackQueryHandler(back_flex_dep_range_to_month_handler, pattern=f"^{config.CB_BACK_FLEX_DEP_RANGE_TO_MONTH}$")
            ],
            config.SELECTING_FLEX_DEPARTURE_DATE: [ # Состояние выбора конкретной даты вылета (гибкий)
                CallbackQueryHandler(flex_departure_date_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}dep_date_"), # Выбор одиночной даты
                CallbackQueryHandler(handle_entire_range_selected, pattern=entire_range_pattern_dep), # Выбор всего диапазона для вылета
                CallbackQueryHandler(back_flex_dep_date_to_range_handler, pattern=f"^{config.CB_BACK_FLEX_DEP_DATE_TO_RANGE}$")
            ],
            config.SELECTING_FLEX_RETURN_YEAR: [
                CallbackQueryHandler(flex_return_year_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}ret_year_"),
                CallbackQueryHandler(back_flex_ret_year_to_dep_date_handler, pattern=f"^{config.CB_BACK_FLEX_RET_YEAR_TO_DEP_DATE}$")
            ],
            config.SELECTING_FLEX_RETURN_MONTH: [
                CallbackQueryHandler(flex_return_month_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}ret_month_"),
                CallbackQueryHandler(back_flex_ret_month_to_year_handler, pattern=f"^{config.CB_BACK_FLEX_RET_MONTH_TO_YEAR}$")
            ],
            config.SELECTING_FLEX_RETURN_DATE_RANGE: [
                CallbackQueryHandler(flex_return_date_range_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}ret_range_"),
                CallbackQueryHandler(back_flex_ret_range_to_month_handler, pattern=f"^{config.CB_BACK_FLEX_RET_RANGE_TO_MONTH}$")
            ],
            config.SELECTING_FLEX_RETURN_DATE: [ # Состояние выбора конкретной даты возврата (гибкий)
                CallbackQueryHandler(flex_return_date_selected, pattern=f"^{config.CALLBACK_PREFIX_FLEX}ret_date_"), # Выбор одиночной даты
                CallbackQueryHandler(handle_entire_range_selected, pattern=entire_range_pattern_ret), # Выбор всего диапазона для возврата
                CallbackQueryHandler(back_flex_ret_date_to_range_handler, pattern=f"^{config.CB_BACK_FLEX_RET_DATE_TO_RANGE}$")
            ],

            # --- ОБЩИЕ СОСТОЯНИЯ ДЛЯ ЦЕНЫ ---
            config.SELECTING_PRICE_OPTION: [
                CallbackQueryHandler(handle_price_option_selected, pattern=price_option_pattern),
                CallbackQueryHandler(back_price_to_std_arr_city_oneway_handler, pattern=f"^{config.CB_BACK_PRICE_TO_STD_ARR_CITY_ONEWAY}$"),
                CallbackQueryHandler(back_price_to_std_ret_date_twoway_handler, pattern=f"^{config.CB_BACK_PRICE_TO_STD_RET_DATE_TWOWAY}$"),
                CallbackQueryHandler(back_price_to_flex_flight_type_handler, pattern=f"^{config.CB_BACK_PRICE_TO_FLEX_FLIGHT_TYPE}$"),
                CallbackQueryHandler(back_price_to_entering_custom_handler, pattern=f"^{config.CB_BACK_PRICE_TO_ENTERING_CUSTOM}$")
            ],
            config.ENTERING_CUSTOM_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_custom_price_handler),
                # Если пользователь нажимает инлайн-кнопку "Назад" на сообщении "Введите цену"
                CallbackQueryHandler(back_price_to_entering_custom_handler, pattern=f"^{config.CB_BACK_PRICE_TO_ENTERING_CUSTOM}$")
            ],
            config.ASK_SEARCH_OTHER_AIRPORTS: [
                CallbackQueryHandler(handle_search_other_airports_decision, pattern=f"^{config.CALLBACK_YES_OTHER_AIRPORTS}$|^{config.CALLBACK_NO_OTHER_AIRPORTS}$")
            ],

            config.ASK_SAVE_SEARCH_PREFERENCES: [
                CallbackQueryHandler(_handle_save_search_preference_wrapper, pattern=f"^{config.CALLBACK_SAVE_SEARCH_YES}$|^{config.CALLBACK_SAVE_SEARCH_NO}$")
            ],
        },
        fallbacks=[
            CommandHandler('cancel', cancel_handler),
            CallbackQueryHandler(handle_invalid_price_choice_fallback, pattern=price_fallback_pattern),
            CallbackQueryHandler(lambda u, c: u.callback_query.answer("Нет доступных опций (ошибка валидности месяца).", show_alert=True) if u.callback_query else None, pattern="^no_valid_months_error$"),
            CallbackQueryHandler(lambda u, c: u.callback_query.answer("Нет доступных опций (ошибка валидности дат).", show_alert=True) if u.callback_query else None, pattern="^no_valid_dates_error$"),
            CallbackQueryHandler(lambda u, c: u.callback_query.answer("Нет доступных опций (нет дат в этом диапазоне).", show_alert=True) if u.callback_query else None, pattern="^no_specific_dates_in_range_error$"),
            CallbackQueryHandler(lambda u, c: u.callback_query.answer("Нет доступных опций (ошибка валидности диапазона).", show_alert=True) if u.callback_query else None, pattern="^no_valid_date_ranges_error$"),
            CallbackQueryHandler(lambda u, c: u.callback_query.answer("Нет доступных опций (нет дат).", show_alert=True) if u.callback_query else None, pattern="^no_dates$"),
            # Можно добавить общий обработчик для непредвиденных callback'ов внутри диалога
            CallbackQueryHandler(error_handler_conv) # Этот обработчик должен быть последним в fallbacks или очень общим
        ],
        map_to_parent={},
        per_message=False, 
        allow_reentry=True, # Важно для возможности возврата к предыдущим шагам
        # persistent=True, name="my_ryanair_conversation" # Для сохранения состояния между перезапусками (требует настройки persistence)
    )
    # Добавление обработчика ошибок в сам ConversationHandler
    # conv_handler.error_handler = error_handler_conv # Если хотите специфичный для диалога обработчик ошибок (но у вас уже есть глобальный)
    return conv_handler