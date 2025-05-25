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
from datetime import datetime, timedelta 
from collections import defaultdict
from telegram.helpers import escape_markdown # <--- ДОБАВЛЕН ИМПОРТ
from telegram import ReplyKeyboardRemove

from . import config, keyboards, helpers, flight_api

logger = logging.getLogger(__name__)

# --- Вспомогательные функции для обработчиков ---
async def ask_departure_country(update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str):
    # (без изменений)
    if hasattr(update, 'message') and update.message:
        await update.message.reply_text(message_text, reply_markup=keyboards.get_country_reply_keyboard())
    elif hasattr(update, 'callback_query') and update.callback_query and update.effective_chat:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=message_text, reply_markup=keyboards.get_country_reply_keyboard())
    else:
        logger.warning("ask_departure_country: Не удалось определить, как отправить сообщение.")

async def ask_departure_city(update: Update, context: ContextTypes.DEFAULT_TYPE, country_name: str):
    # (без изменений)
    if hasattr(update, 'message') and update.message:
        await update.message.reply_text("Выберите город вылета:", reply_markup=keyboards.get_city_reply_keyboard(country_name))
    elif hasattr(update, 'callback_query') and update.callback_query and update.effective_chat:
         await context.bot.send_message(chat_id=update.effective_chat.id, text="Выберите город вылета:", reply_markup=keyboards.get_city_reply_keyboard(country_name))

async def ask_arrival_country(update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str):
    # (без изменений)
    if hasattr(update, 'message') and update.message:
        await update.message.reply_text(message_text, reply_markup=keyboards.get_country_reply_keyboard())
    elif hasattr(update, 'callback_query') and update.callback_query and update.effective_chat:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=message_text, reply_markup=keyboards.get_country_reply_keyboard())

async def ask_arrival_city(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    country_name: str,
) -> int:
    """
    Шаг «Выбор города (аэропорта) прилёта».

    • Убираем из списка тот IATA, что уже выбран на вылете.
    • Если после фильтрации вариантов не остаётся, возвращаем
      пользователя к шагу выбора страны прилёта.
    """
    chat_id = update.effective_chat.id
    dep_iata = context.user_data.get("departure_airport_iata")

    # --- готовим список городов / IATA в выбранной стране ---
    all_cities = config.COUNTRIES_DATA.get(country_name, {})
    available_cities = {
        city: iata for city, iata in all_cities.items() if iata != dep_iata
    }

    # --- нет ни одного альтернативного аэропорта -----------------
    if not available_cities:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"В стране «{country_name}» нет других аэропортов, отличных от "
                "выбранного для вылета.\n"
                "Выберите другую страну прилёта."
            ),
        )
        # отправляем пользователя на повторный выбор страны прилёта
        await ask_arrival_country(update, context, "Выберите страну прилёта:")
        return config.SELECTING_ARRIVAL_COUNTRY

    # --- показываем клавиатуру городов ---------------------------
    keyboard = keyboards.get_city_reply_keyboard(
        country_name, override_cities=available_cities
    )

        # ➊ сначала убираем старую клавиатуру
    if getattr(update, "message", None):
        await update.message.reply_text("Ок, убираю клавиатуру…", reply_markup=ReplyKeyboardRemove())
    else:
        await context.bot.send_message(chat_id=chat_id, text="Ок, убираю клавиатуру…", reply_markup=ReplyKeyboardRemove())

    # ➋ теперь отправляем новое сообщение с клавиатурой городов
    await context.bot.send_message(
        chat_id=chat_id,
        text="Выберите город прилёта:",
        reply_markup=keyboard
    )


    # сохраняем доступные варианты, если потом понадобятся
    context.user_data["arrival_city_options"] = available_cities

    return config.SELECTING_ARRIVAL_CITY


async def ask_year(message_or_update: Update | object, context: ContextTypes.DEFAULT_TYPE, message_text: str, callback_prefix: str = ""):
    # (без изменений, если он корректно работает с ReplyKeyboardRemove перед ним)
    # Важно: если ask_year вызывается после сообщения с ReplyKeyboardRemove, 
    # оно должно отправлять новое сообщение, а не пытаться редактировать то, у которого клавиатура была убрана.
    # Текущая логика ask_year вроде бы это обрабатывает, отправляя новое сообщение, если нет callback_query.
    target_message_object = None
    if hasattr(message_or_update, 'callback_query') and message_or_update.callback_query:
        await message_or_update.callback_query.edit_message_text(
            text=message_text,
            reply_markup=keyboards.generate_year_buttons(callback_prefix)
        )
        return
    elif hasattr(message_or_update, 'message') and message_or_update.message: # Это сообщение пользователя с городом
        # Если мы здесь после ReplyKeyboardRemove, то reply_text на ЭТО сообщение отправит новое.
        target_message_object = message_or_update.message
    elif hasattr(message_or_update, 'reply_text'): # Это может быть объект сообщения, которому можно ответить
        target_message_object = message_or_update

    if target_message_object and hasattr(target_message_object, 'reply_text'):
        await target_message_object.reply_text( # Отправит новое сообщение
            message_text,
            reply_markup=keyboards.generate_year_buttons(callback_prefix)
        )
    elif hasattr(message_or_update, 'effective_chat') and message_or_update.effective_chat: # Фоллбэк на send_message
         await context.bot.send_message(
            chat_id=message_or_update.effective_chat.id,
            text=message_text,
            reply_markup=keyboards.generate_year_buttons(callback_prefix)
        )
    else:
        logger.warning("ask_year: не удалось определить объект для ответа.")


async def ask_month(update: Update, context: ContextTypes.DEFAULT_TYPE,
                    year_for_months: int, message_text: str, callback_prefix: str = "",
                    departure_year_for_comparison: int = None,
                    departure_month_for_comparison: int = None):
    # (без изменений, но убедитесь, что keyboards.generate_month_buttons актуален)
    logger.info(f"ask_month: Вызов клавиатуры месяцев. Год: {year_for_months}, Префикс: {callback_prefix}")
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
        logger.info("ask_month: Клавиатура месяцев успешно отображена.")
    except TypeError as e:
        logger.error(f"ask_month: TypeError при вызове generate_month_buttons: {e}")
        await update.callback_query.edit_message_text("Произошла ошибка при отображении месяцев. Попробуйте /start")
    except Exception as e:
        logger.error(f"ask_month: Непредвиденная ошибка: {e}")
        await update.callback_query.edit_message_text("Произошла внутренняя ошибка. Попробуйте /start")


async def ask_date_range(update: Update, context: ContextTypes.DEFAULT_TYPE, year: int, month: int, message_text: str, callback_prefix: str = "", min_allowed_date: datetime | None = None): # <--- Добавлен min_allowed_date
    # (изменен для передачи min_allowed_date, если keyboards.generate_date_range_buttons его принимает)
    # Если keyboards.generate_date_range_buttons использует только today.date() внутри, этот параметр можно не передавать.
    # Последняя версия keyboards.generate_date_range_buttons от ChatGPT использовала today внутри.
    # Но для общности (например, для дат возврата) передача min_allowed_date - хорошая практика.
    # Пока оставим как было в вашем файле, если generate_date_range_buttons не меняли на прием этого параметра.
    # Однако, последняя версия generate_date_range_buttons от ChatGPT (с `today = datetime.now().date()`) 
    # НЕ принимает min_allowed_date. Если вы используете именно ее, то здесь параметр не нужен.
    # Я оставлю вызов как в вашем последнем файле, предполагая, что generate_date_range_buttons не изменился для приема min_allowed_date.
    # Если вы обновили generate_date_range_buttons на версию, принимающую min_allowed_date, раскомментируйте и передайте его.
    await update.callback_query.edit_message_text(
        text=message_text,
        reply_markup=keyboards.generate_date_range_buttons(year, month, callback_prefix) #, min_allowed_date=min_allowed_date)
    )

async def ask_specific_date(update: Update, context: ContextTypes.DEFAULT_TYPE,
                            year: int, month: int, range_start: int, range_end: int,
                            message_text: str, callback_prefix: str = "",
                            min_allowed_date_for_comparison: datetime = None):
    # (без изменений, но убедитесь, что keyboards.generate_specific_date_buttons актуален)
    await update.callback_query.edit_message_text(
        text=message_text,
        reply_markup=keyboards.generate_specific_date_buttons(
            year, month, range_start, range_end,
            callback_prefix=callback_prefix,
            min_allowed_date=min_allowed_date_for_comparison
        )
    )

# bot/handlers.py
# ... (импорты, включая from telegram.helpers import escape_markdown) ...

async def process_and_send_flights(update: Update, context: ContextTypes.DEFAULT_TYPE, flights_by_date: dict):
    chat_id = update.effective_chat.id
    context.user_data.pop('remaining_flights_to_show', None)

    if not flights_by_date:
        await context.bot.send_message(chat_id=chat_id, text=config.MSG_NO_FLIGHTS_FOUND)
        dep_country = context.user_data.get('departure_country')
        dep_airport_iata = context.user_data.get('departure_airport_iata')

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
        flights_message_parts.append("\n")

    if flights_message_parts:
        full_text = "".join(flights_message_parts)

        # Сначала экранируем весь текст, потом режем
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
            except Exception as e:
                logger.exception(f"Ошибка при отправке чанка рейсов с MarkdownV2: {e}. Попытка отправить как простой текст.")
                try:
                    # Отправляем УЖЕ ЭКРАНИРОВАННЫЙ чанк, но без parse_mode.
                    # Пользователь увидит экранирующие символы, но бот не упадет.
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


async def show_all_remaining_flights_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # (без изменений)
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text="Эта функция отображения оставшихся рейсов обновляется.")

async def prompt_new_search_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # (без изменений)
    query = update.callback_query
    await query.answer()
    context.user_data.clear() # Очищаем данные перед новым поиском
    if query.message:
      await query.edit_message_text(text=config.MSG_WELCOME, reply_markup=keyboards.get_main_menu_keyboard())
    elif update.effective_chat: # Если исходное сообщение было удалено или это новый вызов
      await context.bot.send_message(chat_id=update.effective_chat.id, text=config.MSG_WELCOME, reply_markup=keyboards.get_main_menu_keyboard())


async def end_search_session_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # (без изменений)
    query = update.callback_query
    await query.answer()
    context.user_data.clear() # Очищаем данные при завершении сессии
    if query.message:
      await query.edit_message_text(text="Поиск завершен. Если понадоблюсь, вы знаете, как меня найти! /start")
    elif update.effective_chat:
      await context.bot.send_message(chat_id=update.effective_chat.id, text="Поиск завершен. Если понадоблюсь, вы знаете, как меня найти! /start")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает /start, выводит приветствие и главное меню."""

    # сбрасываем возможное состояние предыдущих диалогов
    context.user_data.clear()

    # экранируем спец-символы Markdown V2 ( ! . ( ) _ * и т.д. )
    welcome = escape_markdown(config.MSG_WELCOME, version=2)

    if update.message:                                        # обычная команда /start
        await update.message.reply_text(
            welcome,
            reply_markup=keyboards.get_main_menu_keyboard()
        )

    elif update.callback_query:                               # редкий случай /start из inline-кнопки
        await update.callback_query.answer()

        if update.callback_query.message:                     # редактируем то же сообщение
            await update.callback_query.edit_message_text(
                welcome,
                reply_markup=keyboards.get_main_menu_keyboard()
            )
        else:                                                 # если оригинального сообщения нет
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=welcome,
                reply_markup=keyboards.get_main_menu_keyboard()
            )

async def start_search_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # (без изменений)
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
    elif query.data == "start_flex_anywhere":
        return await start_flex_anywhere_callback(update, context) # Передаем update, context
    return ConversationHandler.END

async def start_flex_anywhere_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # (без изменений)
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        if query.message:
            await query.edit_message_text(text="Выбран поиск \"Куда угодно\".")
    else: 
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Выбран поиск \"Куда угодно\".")

    context.user_data.clear()
    context.user_data['arrival_airport_iata'] = None # Ключевой флаг для "Куда угодно"
    context.user_data['departure_date'] = None     # Даты не указаны
    context.user_data['return_date'] = None        # Даты не указаны

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=config.MSG_FLIGHT_TYPE_PROMPT,
        reply_markup=keyboards.get_flight_type_reply_keyboard()
    )
    return config.SELECTING_FLEX_FLIGHT_TYPE


# --- СТАНДАРТНЫЙ ПОИСК ---
async def standard_flight_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # (без изменений)
    user_input = update.message.text
    if user_input not in ['1', '2']:
        await update.message.reply_text("Пожалуйста, выберите 1 или 2.", reply_markup=keyboards.get_flight_type_reply_keyboard())
        return config.SELECTING_FLIGHT_TYPE
    context.user_data['flight_type_one_way'] = (user_input == '1')
    await ask_departure_country(update, context, "Выберите страну вылета:")
    return config.SELECTING_DEPARTURE_COUNTRY

async def standard_departure_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # (без изменений)
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
    
    # ---> ИЗМЕНЕНИЕ: Убираем ReplyKeyboard <---
    await update.message.reply_text(f"Город вылета: {city}.", reply_markup=ReplyKeyboardRemove())
    
    # Отправляем новое сообщение для выбора года, так как предыдущее было для ReplyKeyboardRemove
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Выберите год вылета:",
        reply_markup=keyboards.generate_year_buttons(config.CALLBACK_PREFIX_STANDARD + "dep_year_")
    )
    return config.SELECTING_DEPARTURE_YEAR

# ... (standard_departure_year_selected и далее без изменений до flex_flight_type, если они не затрагивают передачу min_allowed_date в ask_date_range)
# Важно: Убедитесь, что в standard_departure_month_selected при вызове ask_date_range передается min_allowed_date, если вы обновили generate_date_range_buttons в keyboards.py для его приема.
# Примерно так (если generate_date_range_buttons принимает min_allowed_date):
# async def standard_departure_month_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
#     # ...
#     min_date_for_ranges = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
#     await ask_date_range(update, context, year, selected_month,
#                        f"Выбран: {month_name} {year}. Выберите диапазон дат:",
#                        callback_prefix=config.CALLBACK_PREFIX_STANDARD + "dep_range_",
#                        min_allowed_date=min_date_for_ranges) # <--- ПЕРЕДАЧА ПАРАМЕТРА
#     return config.SELECTING_DEPARTURE_DATE_RANGE
# Если generate_date_range_buttons НЕ БЫЛ изменен для приема min_allowed_date (и использует today внутри),
# то вызов ask_date_range остается без этого параметра. Я оставлю без него, как в вашем последнем файле handlers.py,
# так как последняя версия generate_date_range_buttons от ChatGPT не требовала этот параметр извне.

async def standard_departure_year_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selected_year = int(query.data.replace(config.CALLBACK_PREFIX_STANDARD + "dep_year_", "")) 
    context.user_data['departure_year'] = selected_year
    
    # Для ask_month передаем departure_year_for_comparison и departure_month_for_comparison (сейчас None для вылета)
    await ask_month(update, context,
                  year_for_months=selected_year,
                  message_text=f"Год вылета: {selected_year}. Выберите месяц:",
                  callback_prefix=config.CALLBACK_PREFIX_STANDARD + "dep_month_",
                  departure_year_for_comparison=None, # Для вылета эти параметры не нужны для фильтрации "до"
                  departure_month_for_comparison=None) 
    logger.info(f"standard_departure_year_selected: Переход в SELECTING_DEPARTURE_MONTH = {config.SELECTING_DEPARTURE_MONTH}")
    return config.SELECTING_DEPARTURE_MONTH

async def standard_departure_month_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    logger.info(f"standard_departure_month_selected: Получен callback: {query.data}")
    try:
        await query.answer()
    except Exception as e:
        logger.error(f"standard_departure_month_selected: Ошибка при вызове query.answer(): {e}")
        return ConversationHandler.END 

    try:
        selected_month_str = query.data.replace(config.CALLBACK_PREFIX_STANDARD + "dep_month_", "")
        selected_month = int(selected_month_str)
    except ValueError:
        logger.error(f"standard_departure_month_selected: Не удалось извлечь номер месяца из query.data: {query.data}")
        await query.edit_message_text("Ошибка: неверный формат данных месяца. Пожалуйста, попробуйте еще раз или начните заново /start.")
        return config.SELECTING_DEPARTURE_YEAR 

    try:
        year = int(context.user_data['departure_year'])
    except KeyError: # ... (обработка ошибок года)
        logger.error("standard_departure_month_selected: Ключ 'departure_year' не найден.")
        await query.edit_message_text("Ошибка: год вылета не сохранен. Начните /start.")
        return ConversationHandler.END
    except ValueError:
        logger.error(f"standard_departure_month_selected: 'departure_year' некорректен: {context.user_data.get('departure_year')}")
        await query.edit_message_text("Ошибка: некорректный год. Начните /start.")
        return ConversationHandler.END

    server_now_datetime = datetime.now()
    current_month_start_on_server = server_now_datetime.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    selected_month_start_by_user = datetime(year, selected_month, 1)
    logger.info(
        f"standard_departure_month_selected: Данные для проверки месяца: "
        f"selected={selected_month_start_by_user.strftime('%Y-%m-%d')}, "
        f"current_server_month_start={current_month_start_on_server.strftime('%Y-%m-%d')}"
    )
    if selected_month_start_by_user < current_month_start_on_server:
        month_name_rus = config.RUSSIAN_MONTHS.get(selected_month, str(selected_month))
        logger.warning(f"standard_departure_month_selected: Выбран прошедший месяц ({month_name_rus} {year}).")
        await query.edit_message_text(text=f"Выбран прошедший месяц ({month_name_rus}). Пожалуйста, выберите корректный месяц.")
        await ask_month(update, context,
                      year_for_months=year,
                      message_text=f"Год вылета: {year}. Выберите месяц:",
                      callback_prefix=config.CALLBACK_PREFIX_STANDARD + "dep_month_",
                      departure_year_for_comparison=None, 
                      departure_month_for_comparison=None)
        return config.SELECTING_DEPARTURE_MONTH

    context.user_data['departure_month'] = selected_month
    month_name = config.RUSSIAN_MONTHS.get(selected_month, str(selected_month))
    context.user_data['departure_month_name'] = month_name
    logger.info(f"standard_departure_month_selected: Месяц {month_name} {year} выбран. Переход к выбору диапазона дат.")
    
    # Для ask_date_range передаем min_allowed_date, если generate_date_range_buttons его использует.
    # Если generate_date_range_buttons от ChatGPT используется (с today внутри), то этот параметр не нужен.
    # Я оставляю вызов без min_allowed_date, как в вашем последнем файле handlers.py,
    # так как последняя версия generate_date_range_buttons от ChatGPT не требовала этот параметр извне.
    await ask_date_range(update, context, year, selected_month,
                       f"Выбран: {month_name} {year}. Выберите диапазон дат:",
                       callback_prefix=config.CALLBACK_PREFIX_STANDARD + "dep_range_")
                       # min_allowed_date=current_month_start_on_server) # <--- если generate_date_range_buttons изменен
    return config.SELECTING_DEPARTURE_DATE_RANGE

# ... (standard_departure_date_range_selected и далее без изменений, если не считать передачу min_allowed_date)
async def standard_departure_date_range_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selected_range_str = query.data.replace(config.CALLBACK_PREFIX_STANDARD + "dep_range_", "")
    try:
        start_day, end_day = map(int, selected_range_str.split('-'))
        context.user_data['departure_date_range_str'] = selected_range_str
    except ValueError: # ... (обработка ошибки) ...
        await query.edit_message_text("Некорректный диапазон. Выберите снова.")
        # ... (код для повторного вызова ask_date_range)
        year = context.user_data['departure_year']
        month = context.user_data['departure_month']
        month_name = config.RUSSIAN_MONTHS.get(month, "")
        await ask_date_range(update, context, year, month, 
                             f"Выбран: {month_name} {year}. Выберите диапазон дат:", 
                             callback_prefix=config.CALLBACK_PREFIX_STANDARD + "dep_range_")
        return config.SELECTING_DEPARTURE_DATE_RANGE


    year = context.user_data['departure_year']
    month = context.user_data['departure_month']
    min_date_for_dep = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    await ask_specific_date(update, context, year, month, start_day, end_day,
                            f"Диапазон: {selected_range_str}. Выберите дату:",
                            callback_prefix=config.CALLBACK_PREFIX_STANDARD + "dep_date_",
                            min_allowed_date_for_comparison=min_date_for_dep)
    return config.SELECTING_DEPARTURE_DATE

async def standard_departure_date_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # (без изменений)
    query = update.callback_query
    await query.answer()
    selected_date_str = query.data.replace(config.CALLBACK_PREFIX_STANDARD + "dep_date_", "")
    date_obj = helpers.validate_date_format(selected_date_str)
    min_allowed_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    if not date_obj or date_obj < min_allowed_date :
        await query.edit_message_text("Некорректная дата или дата в прошлом. Попробуйте снова.")
        year = context.user_data['departure_year']
        month = context.user_data['departure_month']
        selected_range_str = context.user_data.get('departure_date_range_str', "1-10")
        try: start_day, end_day = map(int, selected_range_str.split('-'))
        except ValueError: start_day, end_day = 1, 10
        await ask_specific_date(update, context, year, month, start_day, end_day,
                                f"Диапазон: {selected_range_str}. Выберите дату:",
                                callback_prefix=config.CALLBACK_PREFIX_STANDARD + "dep_date_",
                                min_allowed_date_for_comparison=min_allowed_date)
        return config.SELECTING_DEPARTURE_DATE

    context.user_data['departure_date'] = selected_date_str 
    formatted_date = date_obj.strftime('%d-%m-%Y')
    await query.edit_message_text(text=f"Дата вылета: {formatted_date}")
    await ask_arrival_country(update, context, "Выберите страну прилёта:")
    return config.SELECTING_ARRIVAL_COUNTRY

async def standard_arrival_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # (без изменений)
    country = update.message.text
    if country not in config.COUNTRIES_DATA:
        await update.message.reply_text("Страна не найдена! Пожалуйста, выберите из списка.")
        await ask_arrival_country(update, context, "Выберите страну прилёта:")
        return config.SELECTING_ARRIVAL_COUNTRY
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
    # (без изменений - ReplyKeyboardRemove уже есть, если это конечный текстовый ввод перед ценой/годом возврата)
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
    
    # ---> ИЗМЕНЕНИЕ: Убираем ReplyKeyboard перед запросом цены или года возврата <---
    # Это уже было в вашем коде для случая "в одну сторону". Убедимся, что для "туда-обратно" тоже происходит.
    # ask_year будет вызван с update.message, поэтому он отправит новое сообщение с инлайн клавиатурой.
    # Явный ReplyKeyboardRemove перед ask_year не нужен, если ask_year отправляет новое сообщение.
    # Но для цены - нужен.
    
    if context.user_data.get('flight_type_one_way', True):
        await update.message.reply_text(f"Город прилёта: {city}.", reply_markup=ReplyKeyboardRemove()) # Подтверждение и удаление
        await context.bot.send_message(chat_id=update.effective_chat.id, text=config.MSG_MAX_PRICE_PROMPT) # Новый запрос цены
        return config.SELECTING_MAX_PRICE
    else:
        await update.message.reply_text(f"Город прилёта: {city}.", reply_markup=ReplyKeyboardRemove()) # Подтверждение и удаление
        # ask_year отправит новое сообщение с инлайн клавиатурой
        await ask_year(update, context, "Выберите год обратного вылета:", callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_year_")
        return config.SELECTING_RETURN_YEAR

async def standard_return_year_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # (аналогично standard_departure_year_selected, передаем параметры для ask_month)
    query = update.callback_query
    await query.answer()
    selected_return_year = int(query.data.replace(config.CALLBACK_PREFIX_STANDARD + "ret_year_", ""))
    departure_year = context.user_data.get('departure_year')
    if selected_return_year < departure_year:
        await query.edit_message_text(text=f"Год возврата ({selected_return_year}) не может быть раньше года вылета ({departure_year}).")
        await ask_year(query, context, "Выберите корректный год обратного вылета:", callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_year_")
        return config.SELECTING_RETURN_YEAR

    context.user_data['return_year'] = selected_return_year
    departure_month = context.user_data.get('departure_month')
    departure_date_obj = helpers.validate_date_format(context.user_data.get('departure_date')) # Для более точной фильтрации min_month
    
    min_return_month = departure_month
    if not departure_date_obj or selected_return_year > departure_year : # Если год возврата > года вылета, то любой месяц ок
        min_return_month = 1 # Или None, если generate_month_buttons обработает None как "без ограничений снизу"
                           # Но для нашей логики min_departure_month, если год отличается, то месяц не важен
                           # Поэтому передаем departure_month, а generate_month_buttons сравнивает и год
    
    await ask_month(update, context,
                  year_for_months=selected_return_year,
                  message_text=f"Год обратного вылета: {selected_return_year}. Выберите месяц:",
                  callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_month_",
                  departure_year_for_comparison=departure_year, # Год вылета для сравнения
                  departure_month_for_comparison=min_return_month) # Месяц вылета для сравнения
    return config.SELECTING_RETURN_MONTH

async def standard_return_month_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # (аналогично standard_departure_month_selected, с учетом даты вылета)
    query = update.callback_query
    await query.answer()
    selected_return_month = int(query.data.replace(config.CALLBACK_PREFIX_STANDARD + "ret_month_", ""))
    return_year = context.user_data['return_year']
    departure_year = context.user_data['departure_year']
    departure_month = context.user_data['departure_month']

    # Более строгое сравнение: выбранная дата возврата не может быть раньше даты вылета.
    # На этапе месяца мы можем отсечь только если год тот же, а месяц раньше.
    if return_year == departure_year and selected_return_month < departure_month:
        month_name_rus = config.RUSSIAN_MONTHS.get(selected_return_month, "")
        dep_month_name_rus = config.RUSSIAN_MONTHS.get(departure_month, "")
        await query.edit_message_text(text=f"Месяц возврата ({month_name_rus}) не может быть раньше месяца вылета ({dep_month_name_rus} {departure_year}).")
        await ask_month(update, context,
                      year_for_months=return_year,
                      message_text=f"Год обратного вылета: {return_year}. Выберите месяц:",
                      callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_month_",
                      departure_year_for_comparison=departure_year,
                      departure_month_for_comparison=departure_month)
        return config.SELECTING_RETURN_MONTH

    context.user_data['return_month'] = selected_return_month
    month_name = config.RUSSIAN_MONTHS.get(selected_return_month, "")
    context.user_data['return_month_name'] = month_name
    
    departure_date_obj = helpers.validate_date_format(context.user_data.get('departure_date'))
    # min_allowed_date для диапазонов дат возврата - это дата вылета + 1 день (или тот же день, если API позволяет)
    # Пока передадим None, если generate_date_range_buttons использует today. Если нет, то нужна дата вылета.
    await ask_date_range(update, context, return_year, selected_return_month, 
                         f"Выбран: {month_name} {return_year}. Выберите диапазон дат:", 
                         callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_range_")
                         # min_allowed_date=departure_date_obj) # <--- если generate_date_range_buttons изменен
    return config.SELECTING_RETURN_DATE_RANGE

async def standard_return_date_range_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # (аналогично standard_departure_date_range_selected, с учетом даты вылета для min_allowed_date_for_comparison)
    query = update.callback_query
    await query.answer()
    selected_range_str = query.data.replace(config.CALLBACK_PREFIX_STANDARD + "ret_range_", "")
    try:
        start_day, end_day = map(int, selected_range_str.split('-'))
        context.user_data['return_date_range_str'] = selected_range_str
    except ValueError: # ... (обработка ошибки) ...
        await query.edit_message_text("Некорректный диапазон. Выберите снова.")
        # ... (код для повторного вызова ask_return_month)
        year = context.user_data['return_year']
        departure_year = context.user_data.get('departure_year')
        departure_month = context.user_data.get('departure_month')
        await ask_month(update, context,
                        year_for_months=year,
                        message_text=f"Год обратного вылета: {year}. Выберите месяц:",
                        callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_month_",
                        departure_year_for_comparison=departure_year,
                        departure_month_for_comparison=departure_month)
        return config.SELECTING_RETURN_MONTH

    year = context.user_data['return_year']
    month = context.user_data['return_month']
    
    departure_date_obj = helpers.validate_date_format(context.user_data.get('departure_date'))
    if not departure_date_obj: # Должна быть всегда на этом этапе
        logger.error("standard_return_date_range_selected: Не найдена дата вылета для сравнения.")
        await query.edit_message_text("Ошибка: не найдена дата вылета. Начните /start.")
        return ConversationHandler.END

    await ask_specific_date(update, context, year, month, start_day, end_day,
                            f"Диапазон: {selected_range_str}. Выберите дату:",
                            callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_date_",
                            min_allowed_date_for_comparison=departure_date_obj) # Передаем дату вылета как минимальную
    return config.SELECTING_RETURN_DATE

async def standard_return_date_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # (без изменений)
    query = update.callback_query
    await query.answer()
    selected_date_str = query.data.replace(config.CALLBACK_PREFIX_STANDARD + "ret_date_", "")
    return_date_obj = helpers.validate_date_format(selected_date_str)
    departure_date_obj = helpers.validate_date_format(context.user_data.get('departure_date'))

    if not return_date_obj or not departure_date_obj or return_date_obj < departure_date_obj:
        await query.edit_message_text("Некорректная дата возвращения или она раньше даты вылета. Попробуйте снова.")
        year = context.user_data['return_year']
        month = context.user_data['return_month']
        selected_range_str = context.user_data.get('return_date_range_str', "1-10")
        try: start_day, end_day = map(int, selected_range_str.split('-'))
        except ValueError: start_day, end_day = 1, 10
        await ask_specific_date(update, context, year, month, start_day, end_day,
                                f"Диапазон: {selected_range_str}. Выберите дату:",
                                callback_prefix=config.CALLBACK_PREFIX_STANDARD + "ret_date_",
                                min_allowed_date_for_comparison=departure_date_obj)
        return config.SELECTING_RETURN_DATE

    context.user_data['return_date'] = selected_date_str
    formatted_date = return_date_obj.strftime('%d-%m-%Y')
    
    # ---> ИЗМЕНЕНИЕ: Явное удаление ReplyKeyboard перед запросом цены <---
    # query.message - это сообщение с инлайн-клавиатурой. reply_text к нему не применим.
    # Нужно отправить новое сообщение или использовать context.bot.send_message
    await query.edit_message_text(text=f"Дата обратного вылета: {formatted_date}")
    await context.bot.send_message(chat_id=update.effective_chat.id, text=config.MSG_MAX_PRICE_PROMPT, reply_markup=ReplyKeyboardRemove())
    return config.SELECTING_MAX_PRICE

async def standard_max_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # (без изменений - ReplyKeyboardRemove уже был при запросе цены)
    price = helpers.validate_price(update.message.text)
    if price is None:
        await update.message.reply_text("Некорректная цена. Введите положительное число, например, 50:")
        return config.SELECTING_MAX_PRICE
    context.user_data['max_price'] = price
    await update.message.reply_text(config.MSG_SEARCHING_FLIGHTS) # ReplyKeyboardRemove уже был отправлен
    
    flights_by_date = await flight_api.find_flights_with_fallback(
        departure_airport_iata=context.user_data['departure_airport_iata'],
        arrival_airport_iata=context.user_data['arrival_airport_iata'],
        departure_date_str=context.user_data['departure_date'],
        max_price=context.user_data['max_price'],
        return_date_str=context.user_data.get('return_date'),
        is_one_way=context.user_data.get('flight_type_one_way', True)
    )
    return await process_and_send_flights(update, context, flights_by_date)


# --- ГИБКИЙ ПОИСК ---

async def flex_flight_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # (без изменений - ReplyKeyboardRemove уже есть при запросе цены)
    user_input = update.message.text
    if user_input not in ['1', '2']:
        await update.message.reply_text("Пожалуйста, выберите 1 или 2.", reply_markup=keyboards.get_flight_type_reply_keyboard())
        return config.SELECTING_FLEX_FLIGHT_TYPE
    context.user_data['flight_type_one_way'] = (user_input == '1')
    await update.message.reply_text(config.MSG_MAX_PRICE_PROMPT, reply_markup=ReplyKeyboardRemove())
    return config.SELECTING_FLEX_MAX_PRICE

async def flex_max_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # (без изменений)
    price = helpers.validate_price(update.message.text)
    if price is None:
        await update.message.reply_text("Некорректная цена. Введите положительное число, например, 50:")
        return config.SELECTING_FLEX_MAX_PRICE
    context.user_data['max_price'] = price
    
    # Спрашиваем про аэропорт вылета (новое сообщение с инлайн клавиатурой)
    # ReplyKeyboardRemove был на предыдущем шаге
    await update.message.reply_text(
        "Указать аэропорт вылета?",
        reply_markup=keyboards.get_yes_no_keyboard(
            yes_callback=config.CALLBACK_PREFIX_FLEX + "ask_dep_yes",
            no_callback=config.CALLBACK_PREFIX_FLEX + "ask_dep_no"
        )
    )
    return config.ASK_FLEX_DEPARTURE_AIRPORT

async def flex_ask_departure_airport(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Шаг гибкого поиска: спрашиваем, будет ли указан конкретный аэропорт вылета.
    Если пользователь ответил «нет» – сразу прерываем сценарий, т.к. Ryanair API
    без departure_airport не работает.
    """
    query = update.callback_query
    await query.answer()

    # --- пользователь согласен указать аэропорт вылета ---
    if query.data == config.CALLBACK_PREFIX_FLEX + "ask_dep_yes":
        if query.message:
            # убираем inline-кнопки «да/нет» и просим выбрать страну
            await query.edit_message_text(
                text="Хорошо, выберите страну вылета:",
                reply_markup=None
            )

        # дальше – стандартный выбор страны
        await ask_departure_country(update, context, "Выберите страну вылета:")
        return config.SELECTING_FLEX_DEPARTURE_COUNTRY

    # --- пользователь ответил «нет» ---
    logger.info(
        "Гибкий поиск: пользователь попытался пропустить аэропорт вылета – сценарий остановлен."
    )

    warn_text = (
        "⚠️ Для поиска рейсов Ryanair нужно указать конкретный аэропорт вылета.\n\n"
        "Нажмите /start и начните новый поиск, указав аэропорт."
    )

    if query.message:
        # заменяем сообщение c кнопками на предупреждение
        await query.edit_message_text(text=warn_text, reply_markup=None)
    else:
        # fallback (на всякий случай)
        await context.bot.send_message(chat_id=update.effective_chat.id, text=warn_text)

    # чистим только ключи текущего гибкого поиска
    for k in (
        'departure_airport_iata', 'arrival_airport_iata',
        'flight_type_one_way', 'max_price',
        'departure_country', 'departure_city_name',
        'arrival_country', 'arrival_city_name',
    ):
        context.user_data.pop(k, None)

    return ConversationHandler.END



async def flex_departure_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # (без изменений)
    country = update.message.text
    if country not in config.COUNTRIES_DATA:
        await update.message.reply_text("Страна не найдена! Пожалуйста, выберите из списка.")
        await ask_departure_country(update, context, "Выберите страну вылета:")
        return config.SELECTING_FLEX_DEPARTURE_COUNTRY
    context.user_data['departure_country'] = country
    await ask_departure_city(update, context, country)
    return config.SELECTING_FLEX_DEPARTURE_CITY

async def flex_departure_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    city = update.message.text
    country = context.user_data.get('departure_country')
    iata_code = helpers.get_airport_iata(country, city)
    if not iata_code:
        await update.message.reply_text("Город не найден или неверная страна! Пожалуйста, выберите из списка.")
        await ask_departure_city(update, context, country)
        return config.SELECTING_FLEX_DEPARTURE_CITY
        
    context.user_data['departure_airport_iata'] = iata_code
    context.user_data['departure_city_name'] = city

    # ---> ИЗМЕНЕНИЕ: Убираем ReplyKeyboard и всегда спрашиваем про аэропорт прилета <---
    await update.message.reply_text(f"Город вылета: {city}.", reply_markup=ReplyKeyboardRemove())
    
    # Отправляем новое сообщение с вопросом об аэропорте прилета
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Указать аэропорт прилёта?",
        reply_markup=keyboards.get_yes_no_keyboard(
            yes_callback=config.CALLBACK_PREFIX_FLEX + "ask_arr_yes",
            no_callback=config.CALLBACK_PREFIX_FLEX + "ask_arr_no"
        )
    )
    return config.ASK_FLEX_ARRIVAL_AIRPORT

async def flex_ask_arrival_airport(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # (без изменений в основной логике, кроме edit_message_text)
    query = update.callback_query
    await query.answer()

    # Если это поток "Куда угодно" ИЛИ если пользователь явно пропустил аэропорт вылета,
    # И теперь отвечает на вопрос про аэропорт прилета
    if query.data == config.CALLBACK_PREFIX_FLEX + "ask_arr_yes":
        if query.message: await query.edit_message_text(text="Аэропорт прилёта: ДА")
        # ask_arrival_country отправит новое сообщение с ReplyKeyboard
        await ask_arrival_country(update, context, "Выберите страну прилёта:")
        return config.SELECTING_FLEX_ARRIVAL_COUNTRY
    else: # ask_arr_no (пользователь пропускает аэропорт прилета)
        if query.message: await query.edit_message_text(text="Аэропорт прилёта: НЕТ (любой доступный).")
        context.user_data['arrival_airport_iata'] = None # Явно указываем
        
        # Если не указан ни аэропорт вылета, ни аэропорт прилета - это ошибка для поиска по датам
        # (Для "Куда угодно" departure_airport_iata может быть None, arrival_airport_iata тоже None)
        # Этот кейс (оба None) должен вести к поиску без дат или с датами, но API должен это поддерживать.
        # Ryanair API требует хотя бы аэропорт вылета.

        if context.user_data.get('departure_airport_iata') is None: # Если и вылет не указан
             msg = "Ошибка: Для поиска 'в любом направлении' нужно указать хотя бы аэропорт вылета. Начните /start заново."
             # query.message может быть None, если это сообщение было удалено или это первый вход
             if query.message: await query.edit_message_text(text=msg) # Убираем клавиатуру
             else: await context.bot.send_message(chat_id=update.effective_chat.id, text=msg, reply_markup=ReplyKeyboardRemove())
             context.user_data.clear()
             return ConversationHandler.END
        
        # Если аэропорт вылета указан, а прилета - нет, переходим к датам
        # Отправляем новое сообщение
        await context.bot.send_message(chat_id=update.effective_chat.id,
            text="Указать конкретные даты?",
            reply_markup=keyboards.get_skip_dates_keyboard(
                callback_select_dates=config.CALLBACK_PREFIX_FLEX + "ask_dates_yes"
            ))
        return config.ASK_FLEX_DATES

async def flex_arrival_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # (без изменений)
    country = update.message.text
    if country not in config.COUNTRIES_DATA:
        await update.message.reply_text("Страна не найдена! Пожалуйста, выберите из списка.")
        return config.SELECTING_FLEX_ARRIVAL_COUNTRY
    context.user_data['arrival_country'] = country
    await ask_arrival_city(update, context, country)
    return config.SELECTING_FLEX_ARRIVAL_CITY


async def flex_arrival_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # (без изменений, кроме ReplyKeyboardRemove перед запросом дат)
    city = update.message.text 
    country = context.user_data.get('arrival_country')
    iata_code = helpers.get_airport_iata(country, city)
    if not iata_code:
        await update.message.reply_text("Город не найден! Пожалуйста, выберите из списка.")
        return config.SELECTING_FLEX_ARRIVAL_CITY
    if context.user_data.get('departure_airport_iata') and iata_code == context.user_data['departure_airport_iata']:
        await update.message.reply_text("Аэропорт прилёта не может совпадать с аэропортом вылета. Выберите другой город.")
        return config.SELECTING_FLEX_ARRIVAL_CITY
        
    context.user_data['arrival_airport_iata'] = iata_code
    context.user_data['arrival_city_name'] = city

    # ---> ИЗМЕНЕНИЕ: Убираем ReplyKeyboard перед запросом дат <---
    await update.message.reply_text(f"Город прилёта: {city}.", reply_markup=ReplyKeyboardRemove())

    # Отправляем новое сообщение для запроса дат
    await context.bot.send_message(chat_id=update.effective_chat.id,
        text="Указать конкретные даты?",
        reply_markup=keyboards.get_skip_dates_keyboard(
            callback_select_dates=config.CALLBACK_PREFIX_FLEX + "ask_dates_yes"
        ))
    return config.ASK_FLEX_DATES

async def flex_ask_dates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # (без изменений в основной логике)
    query = update.callback_query
    await query.answer()
    # departure_airport_is_set = context.user_data.get('departure_airport_iata') is not None # Для проверки позже

    if query.data == config.CALLBACK_PREFIX_FLEX + "ask_dates_yes":
        if query.message: await query.edit_message_text(text="Даты: ДА, указать конкретные.")
        # ask_year будет редактировать текущее сообщение (бывшее с кнопками "указать даты?")
        await ask_year(query, context, "Выберите год вылета:", callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_year_")
        return config.SELECTING_FLEX_DEPARTURE_YEAR
    elif query.data == config.CALLBACK_NO_SPECIFIC_DATES:
        if query.message: await query.edit_message_text(text="Даты: НЕТ, искать на ближайший год.")
        context.user_data['departure_date'] = None # Явное указание для find_flights_with_fallback
        context.user_data['return_date'] = None  # Явное указание

        # Проверка, указан ли хотя бы один аэропорт (вылета или прилета)
        # Ryanair API требует хотя бы аэропорт вылета для поиска "куда угодно по датам"
        # или хотя бы аэропорт вылета для поиска "в любой город без дат".
        # Если оба None (поток "куда угодно" без указания аэропорта вылета) - это нужно обработать.
        # Текущая flight_api.find_flights_with_fallback ожидает departure_airport_iata.
        
        if context.user_data.get('departure_airport_iata') is None and \
           context.user_data.get('arrival_airport_iata') is None:
            msg_text = ("Ошибка: Для поиска без дат 'куда угодно' необходимо сначала указать аэропорт вылета "
                        "через опцию 'Указать аэропорт вылета?' в начале гибкого поиска. Начните поиск заново /start.")
            # query.message - это сообщение с инлайн-кнопками, его можно редактировать
            await query.edit_message_text(text=msg_text, reply_markup=None)
            context.user_data.clear()
            return ConversationHandler.END
        
        # Отправляем новое сообщение перед поиском
        await context.bot.send_message(chat_id=update.effective_chat.id, text=config.MSG_SEARCHING_FLIGHTS, reply_markup=ReplyKeyboardRemove())
        
        flights_by_date = await flight_api.find_flights_with_fallback(
            departure_airport_iata=context.user_data.get('departure_airport_iata'), # Может быть None, если так задумано и API позволяет
            arrival_airport_iata=context.user_data.get('arrival_airport_iata'),   # Может быть None
            departure_date_str=None, # Ключевой параметр для поиска "без дат"
            max_price=context.user_data['max_price'],
            return_date_str=None, # Ключевой параметр для поиска "без дат"
            is_one_way=context.user_data.get('flight_type_one_way', True)
        )
        return await process_and_send_flights(update, context, flights_by_date)
    
    # Если callback не соответствует ни одному из ожидаемых (не должно произойти с текущими кнопками)
    return config.ASK_FLEX_DATES


# --- Гибкий поиск дат (flex_departure_year_selected и т.д.) ---
# В этих функциях также нужно учесть передачу min_allowed_date / departure_date_obj
# в ask_date_range и ask_specific_date, если вы обновили keyboards.py
# для приема этих параметров в соответствующих функциях генерации клавиатур.
# Я оставлю их как в вашем последнем файле, если не было явных инструкций по их изменению
# в контексте min_allowed_date для generate_date_range_buttons.

async def flex_departure_year_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selected_year = int(query.data.replace(config.CALLBACK_PREFIX_FLEX + "dep_year_", ""))
    context.user_data['departure_year'] = selected_year
    await ask_month(update, context,
                  year_for_months=selected_year,
                  message_text=f"Год вылета: {selected_year}. Выберите месяц:",
                  callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_month_",
                  departure_year_for_comparison=None, 
                  departure_month_for_comparison=None)
    return config.SELECTING_FLEX_DEPARTURE_MONTH

async def flex_departure_month_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selected_month = int(query.data.replace(config.CALLBACK_PREFIX_FLEX + "dep_month_", ""))
    year = context.user_data['departure_year']
    
    server_now_datetime = datetime.now()
    current_month_start_on_server = server_now_datetime.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    selected_month_start_by_user = datetime(year, selected_month, 1)

    if selected_month_start_by_user < current_month_start_on_server:
        month_name_rus = config.RUSSIAN_MONTHS.get(selected_month, str(selected_month))
        await query.edit_message_text(text=f"Выбран прошедший месяц ({month_name_rus}). Пожалуйста, выберите корректный месяц.")
        await ask_month(update, context, 
                        year_for_months=year, 
                        message_text=f"Год вылета: {year}. Выберите месяц:", 
                        callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_month_",
                        departure_year_for_comparison=None, 
                        departure_month_for_comparison=None)
        return config.SELECTING_FLEX_DEPARTURE_MONTH
        
    context.user_data['departure_month'] = selected_month
    month_name = config.RUSSIAN_MONTHS.get(selected_month, "")
    context.user_data['departure_month_name'] = month_name
    
    await ask_date_range(update, context, year, selected_month, 
                         f"Выбран: {month_name} {year}. Выберите диапазон дат:", 
                         callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_range_")
                         # min_allowed_date=current_month_start_on_server) # <--- если generate_date_range_buttons изменен
    return config.SELECTING_FLEX_DEPARTURE_DATE_RANGE

async def flex_departure_date_range_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selected_range_str = query.data.replace(config.CALLBACK_PREFIX_FLEX + "dep_range_", "")
    try: 
        start_day, end_day = map(int, selected_range_str.split('-'))
    except ValueError: 
        await query.edit_message_text("Неверный диапазон")
        # ... (код для повторного вызова ask_date_range для flex)
        year = context.user_data['departure_year']
        month = context.user_data['departure_month']
        month_name = config.RUSSIAN_MONTHS.get(month, "")
        await ask_date_range(update, context, year, month, 
                             f"Выбран: {month_name} {year}. Выберите диапазон дат:", 
                             callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_range_")
        return config.SELECTING_FLEX_DEPARTURE_DATE_RANGE
        
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
    await query.answer()
    selected_date_str = query.data.replace(config.CALLBACK_PREFIX_FLEX + "dep_date_", "")
    date_obj = helpers.validate_date_format(selected_date_str)
    min_allowed_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    if not date_obj or date_obj < min_allowed_date :
        await query.edit_message_text("Некорректная дата или дата в прошлом. Попробуйте снова.")
        year, month = context.user_data['departure_year'], context.user_data['departure_month']
        s_range = context.user_data.get('departure_date_range_str', "1-10")
        try: start_day, end_day = map(int, s_range.split('-'))
        except: start_day, end_day = 1,10
        await ask_specific_date(update, context, year, month, start_day, end_day, 
                                f"Диапазон: {s_range}. Выберите дату:", # Используем s_range для текста
                                callback_prefix=config.CALLBACK_PREFIX_FLEX + "dep_date_",
                                min_allowed_date_for_comparison=min_allowed_date)
        return config.SELECTING_FLEX_DEPARTURE_DATE
        
    context.user_data['departure_date'] = selected_date_str
    formatted_date = date_obj.strftime('%d-%m-%Y')
    
    if query.message: # Убедимся, что query.message существует перед редактированием
      await query.edit_message_text(text=f"Дата вылета: {formatted_date}")
    
    # Отправляем новое сообщение перед поиском
    await context.bot.send_message(chat_id=update.effective_chat.id, text=config.MSG_SEARCHING_FLIGHTS, reply_markup=ReplyKeyboardRemove())
    
    if context.user_data.get('flight_type_one_way', True):
        flights_by_date = await flight_api.find_flights_with_fallback(
            departure_airport_iata=context.user_data.get('departure_airport_iata'),
            arrival_airport_iata=context.user_data.get('arrival_airport_iata'),
            departure_date_str=context.user_data['departure_date'],
            max_price=context.user_data['max_price'], 
            is_one_way=True
        )
        return await process_and_send_flights(update, context, flights_by_date)
    else: # Нужен обратный рейс
        # query.message здесь уже было использовано для edit_message_text, используем context.bot.send_message или ask_year должен корректно создать новое сообщение
        # ask_year при вызове с query (CallbackQuery) будет редактировать сообщение.
        # Это сообщение уже было отредактировано текстом "Дата вылета: ...".
        # Поэтому для запроса года возврата лучше отправить новое сообщение или убедиться, что ask_year это сделает.
        # Текущий ask_year редактирует, если есть query.callback_query.
        
        # Отправим новое сообщение для года возврата
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Выберите год обратного вылета:",
            reply_markup=keyboards.generate_year_buttons(config.CALLBACK_PREFIX_FLEX + "ret_year_")
        )
        return config.SELECTING_FLEX_RETURN_YEAR

async def flex_return_year_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # (аналогично standard_return_year_selected)
    query = update.callback_query
    await query.answer()
    selected_return_year = int(query.data.replace(config.CALLBACK_PREFIX_FLEX + "ret_year_", ""))
    departure_year = context.user_data.get('departure_year')
    if selected_return_year < departure_year:
        await query.edit_message_text(f"Год возврата ({selected_return_year}) не может быть раньше года вылета ({departure_year}).")
        await ask_year(query, context, "Выберите корректный год обратного вылета:", callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_year_")
        return config.SELECTING_FLEX_RETURN_YEAR

    context.user_data['return_year'] = selected_return_year
    departure_month = context.user_data.get('departure_month')
    departure_date_obj = helpers.validate_date_format(context.user_data.get('departure_date'))
    
    min_return_month = departure_month
    if not departure_date_obj or selected_return_year > departure_year:
        min_return_month = 1
        
    await ask_month(update, context, 
                  year_for_months=selected_return_year, 
                  message_text=f"Год обратного вылета: {selected_return_year}. Выберите месяц:",
                  callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_month_",
                  departure_year_for_comparison=departure_year,
                  departure_month_for_comparison=min_return_month)
    return config.SELECTING_FLEX_RETURN_MONTH

async def flex_return_month_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # (аналогично standard_return_month_selected)
    query = update.callback_query
    await query.answer()
    selected_return_month = int(query.data.replace(config.CALLBACK_PREFIX_FLEX + "ret_month_", ""))
    return_year, dep_year, dep_month = context.user_data['return_year'], context.user_data['departure_year'], context.user_data['departure_month']
    
    if return_year == dep_year and selected_return_month < dep_month:
        # ... (сообщение об ошибке и повторный запрос месяца) ...
        month_name_rus = config.RUSSIAN_MONTHS.get(selected_return_month, "")
        dep_month_name_rus = config.RUSSIAN_MONTHS.get(dep_month, "")
        await query.edit_message_text(text=f"Месяц возврата ({month_name_rus}) не может быть раньше месяца вылета ({dep_month_name_rus} {dep_year}).")
        await ask_month(update, context, return_year, 
                        message_text=f"Год обратного вылета: {return_year}. Выберите месяц:", 
                        callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_month_",
                        departure_year_for_comparison=dep_year, 
                        departure_month_for_comparison=dep_month)
        return config.SELECTING_FLEX_RETURN_MONTH
        
    context.user_data['return_month'] = selected_return_month
    month_name = config.RUSSIAN_MONTHS.get(selected_return_month, "")
    context.user_data['return_month_name'] = month_name
    
    departure_date_obj = helpers.validate_date_format(context.user_data.get('departure_date'))
    await ask_date_range(update, context, return_year, selected_return_month, 
                         f"Выбран: {month_name} {return_year}. Выберите диапазон дат:", 
                         callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_range_")
                         # min_allowed_date=departure_date_obj) # <--- если generate_date_range_buttons изменен
    return config.SELECTING_FLEX_RETURN_DATE_RANGE


async def flex_return_date_range_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # (аналогично standard_return_date_range_selected)
    query = update.callback_query
    await query.answer()
    selected_range_str = query.data.replace(config.CALLBACK_PREFIX_FLEX + "ret_range_", "")
    try: 
        start_day, end_day = map(int, selected_range_str.split('-'))
    except ValueError: 
        await query.edit_message_text("Неверный диапазон")
        # ... (код для повторного вызова ask_return_month для flex)
        year = context.user_data['return_year']
        dep_year = context.user_data.get('departure_year')
        dep_month = context.user_data.get('departure_month')
        await ask_month(update, context, year,
                        message_text=f"Год обратного вылета: {year}. Выберите месяц:",
                        callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_month_",
                        departure_year_for_comparison=dep_year,
                        departure_month_for_comparison=dep_month)
        return config.SELECTING_FLEX_RETURN_MONTH
        
    context.user_data['return_date_range_str'] = selected_range_str
    year, month = context.user_data['return_year'], context.user_data['return_month']
    departure_date_obj = helpers.validate_date_format(context.user_data.get('departure_date'))
    if not departure_date_obj:
        logger.error("flex_return_date_range_selected: Не найдена дата вылета для сравнения.")
        await query.edit_message_text("Ошибка: не найдена дата вылета. Начните /start.")
        return ConversationHandler.END
        
    await ask_specific_date(update, context, year, month, start_day, end_day,
                            f"Диапазон: {selected_range_str}. Выберите дату:",
                            callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_date_",
                            min_allowed_date_for_comparison=departure_date_obj)
    return config.SELECTING_FLEX_RETURN_DATE

async def flex_return_date_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # (аналогично standard_return_date_selected)
    query = update.callback_query
    await query.answer()
    selected_date_str = query.data.replace(config.CALLBACK_PREFIX_FLEX + "ret_date_", "")
    return_date_obj = helpers.validate_date_format(selected_date_str)
    departure_date_obj = helpers.validate_date_format(context.user_data.get('departure_date'))
    
    if not return_date_obj or not departure_date_obj or return_date_obj < departure_date_obj:
        await query.edit_message_text("Некорректная дата возвращения или она раньше даты вылета. Попробуйте снова.")
        year, month = context.user_data['return_year'], context.user_data['return_month']
        s_range = context.user_data.get('return_date_range_str', "1-10")
        try: start_day, end_day = map(int, s_range.split('-'))
        except: start_day, end_day = 1,10
        await ask_specific_date(update, context, year, month, start_day, end_day, 
                                f"Диапазон: {s_range}. Выберите дату:",
                                callback_prefix=config.CALLBACK_PREFIX_FLEX + "ret_date_",
                                min_allowed_date_for_comparison=departure_date_obj)
        return config.SELECTING_FLEX_RETURN_DATE
        
    context.user_data['return_date'] = selected_date_str
    formatted_date = return_date_obj.strftime('%d-%m-%Y')
    
    if query.message: # Убедимся, что query.message существует
        await query.edit_message_text(text=f"Дата обратного вылета: {formatted_date}")
    
    await context.bot.send_message(chat_id=update.effective_chat.id, text=config.MSG_SEARCHING_FLIGHTS, reply_markup=ReplyKeyboardRemove())
    
    flights_by_date = await flight_api.find_flights_with_fallback(
        departure_airport_iata=context.user_data.get('departure_airport_iata'),
        arrival_airport_iata=context.user_data.get('arrival_airport_iata'),
        departure_date_str=context.user_data['departure_date'],
        max_price=context.user_data['max_price'],
        return_date_str=context.user_data['return_date'], 
        is_one_way=False # Это рейс туда-обратно на этом шаге
    )
    return await process_and_send_flights(update, context, flights_by_date)

# --- Обработка поиска из других аэропортов ---
async def handle_search_other_airports_decision(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    if query.data == config.CALLBACK_YES_OTHER_AIRPORTS:
        departure_country = context.user_data.get('departure_country')
        original_departure_iata = context.user_data.get('departure_airport_iata')

        if not departure_country or not original_departure_iata:
            await query.edit_message_text(text="Не удалось получить данные для поиска. Начните новый поиск.")
            return ConversationHandler.END
        
        await query.edit_message_text(text=f"Ищу рейсы из других аэропортов в {departure_country}...")
        context.user_data["_already_searched_alternatives"] = True # Ставим флаг

        all_airports_in_country = config.COUNTRIES_DATA.get(departure_country, {})
        alternative_airports = { 
            city: iata for city, iata in all_airports_in_country.items() if iata != original_departure_iata 
        }

        if not alternative_airports:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"В стране {departure_country} нет других аэропортов для поиска.")
            # Предлагаем новый поиск или завершение (как в process_and_send_flights)
            await context.bot.send_message(
                chat_id=update.effective_chat.id, text="Что дальше?",
                reply_markup=keyboards.get_yes_no_keyboard(
                    yes_callback="prompt_new_search_type", no_callback="end_search_session",
                    yes_text="✅ Начать новый поиск", no_text="❌ Закончить"
                ))
            # context.user_data.clear() # Очищать здесь или в колбэках
            return ConversationHandler.END # Завершаем, т.к. альтернатив нет

        found_alternative_flights = False
        all_alternative_flights_by_date_and_source = defaultdict(dict) # Изменено для лучшей группировки

        original_search_params = {
            "arrival_airport_iata": context.user_data.get('arrival_airport_iata'),
            "departure_date_str": context.user_data.get('departure_date'), # Может быть None для гибкого поиска
            "max_price": context.user_data['max_price'],
            "return_date_str": context.user_data.get('return_date'), # Может быть None
            "is_one_way": context.user_data.get('flight_type_one_way', True)
        }

        for city, iata_code in alternative_airports.items():
            logger.info(f"Поиск из альтернативного аэропорта: {city} ({iata_code})")
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Проверяю вылеты из {city} ({iata_code})...")
            
            flights_from_alt_by_date = await flight_api.find_flights_with_fallback(
                departure_airport_iata=iata_code,
                **original_search_params
            )
            if flights_from_alt_by_date:
                found_alternative_flights = True
                # Группируем по аэропорту вылета, затем по дате
                for date_str, flights_list in flights_from_alt_by_date.items():
                    # Ключ будет, например, "Берлин (BER) -> 2025-07-20"
                    # Или просто "Берлин (BER)" если группировка по датам уже есть внутри flights_list
                    # find_flights_with_fallback возвращает {дата_строка: [рейсы]}
                    # Мы хотим добавить информацию об источнике
                    source_key = f"{city} ({iata_code})"
                    all_alternative_flights_by_date_and_source[source_key]\
                        .setdefault(date_str, [])\
                        .extend(flights_list)

        
        if found_alternative_flights:
            # Формируем сообщение для альтернативных рейсов
            alt_flights_final_message_parts = [f"Найдены рейсы из других аэропортов в {departure_country}:\n"]
            for source_airport_info, flights_by_sub_date in all_alternative_flights_by_date_and_source.items():
                alt_flights_final_message_parts.append(f"\n✈️ --- *Из аэропорта: {source_airport_info}* ---\n")
                for date_key, flights_on_this_date in sorted(flights_by_sub_date.items()):
                    try:
                        date_obj_alt = datetime.strptime(date_key, "%Y-%m-%d")
                        alt_flights_final_message_parts.append(f"\n--- 📅 *{date_obj_alt.strftime('%d %B %Y (%A)')}* ---\n")
                    except ValueError:
                        alt_flights_final_message_parts.append(f"\n--- 📅 *{date_key}* ---\n")
                    
                    for i_alt, flight_alt in enumerate(flights_on_this_date):
                        # Можно ввести отдельный CHUNK_SIZE для альтернативных, или использовать тот же
                        alt_flights_final_message_parts.append(helpers.format_flight_details(flight_alt))
                        # Здесь нет ограничения по FLIGHTS_CHUNK_SIZE, чтобы показать все найденные альтернативы
                    alt_flights_final_message_parts.append("\n")

            full_alt_message = "".join(alt_flights_final_message_parts)
            if len(full_alt_message) > len(f"Найдены рейсы из других аэропортов в {departure_country}:\n") + 20 : # Проверка, что есть что-то кроме заголовка
                max_len_alt = 4096
                for i_alt_msg in range(0, len(full_alt_message), max_len_alt):
                    chunk_alt = full_alt_message[i_alt_msg:i_alt_msg + max_len_alt]
                    try:
                        escaped_alt_chunk = escape_markdown(chunk_alt, version=2)
                        await context.bot.send_message(chat_id=update.effective_chat.id, text=escaped_alt_chunk, parse_mode='MarkdownV2')
                    except Exception: # Фоллбэк на простой текст
                        await context.bot.send_message(chat_id=update.effective_chat.id, text=chunk_alt)
            else: # Если вдруг found_alternative_flights было True, но сообщение пустое
                 await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Из других аэропортов в {departure_country} рейсов по вашим критериям не найдено.")

        else: # not found_alternative_flights
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Из других аэропортов в {departure_country} рейсов по вашим критериям не найдено.")

        # Кнопки "Что дальше?" после поиска по альтернативным
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text="Что дальше?",
            reply_markup=keyboards.get_yes_no_keyboard(
                yes_callback="prompt_new_search_type", no_callback="end_search_session",
                yes_text="✅ Начать новый поиск", no_text="❌ Закончить"
            ))
        # context.user_data.clear() # Очищаем после этого специфического поиска
        return ConversationHandler.END

    elif query.data == config.CALLBACK_NO_OTHER_AIRPORTS:
        await query.edit_message_text(text="Понял. Поиск из других аэропортов отменен.")
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text="Что дальше?",
            reply_markup=keyboards.get_yes_no_keyboard(
                yes_callback="prompt_new_search_type", no_callback="end_search_session",
                yes_text="✅ Начать новый поиск", no_text="❌ Закончить"
            ))
        # context.user_data.clear()
        return ConversationHandler.END
    
    # Если callback не распознан (не должно быть)
    return config.ASK_SEARCH_OTHER_AIRPORTS


# --- Отмена и обработка ошибок ---
async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # (без изменений)
    message_to_send = config.MSG_CANCELLED 
    reply_markup_to_send = ReplyKeyboardRemove()
    chat_id_to_send = update.effective_chat.id
    if update.callback_query:
        await update.callback_query.answer()
        if update.callback_query.message:
            try: await update.callback_query.edit_message_text(text=message_to_send)
            except Exception: # Если сообщение уже удалено или не может быть отредактировано
                if chat_id_to_send: await context.bot.send_message(chat_id=chat_id_to_send, text=message_to_send, reply_markup=reply_markup_to_send)
        elif chat_id_to_send: await context.bot.send_message(chat_id=chat_id_to_send, text=message_to_send, reply_markup=reply_markup_to_send)
    elif update.message and chat_id_to_send:
        await update.message.reply_text(message_to_send, reply_markup=reply_markup_to_send)
    context.user_data.clear()
    return ConversationHandler.END

async def error_handler_conv(update: Update | None, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    # (без изменений)
    logger.error(f"Ошибка в ConversationHandler: {context.error}", exc_info=context.error)
    chat_id_to_send_error = None
    if update and hasattr(update, 'effective_chat') and update.effective_chat:
        chat_id_to_send_error = update.effective_chat.id
    
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
    # (без изменений в структуре, если только паттерны колбэков не менялись)
    std_dep_year_pattern = f"^{config.CALLBACK_PREFIX_STANDARD}dep_year_" 
    flex_dep_year_pattern = f"^{config.CALLBACK_PREFIX_FLEX}dep_year_" 
    flex_ret_year_pattern = f"^{config.CALLBACK_PREFIX_FLEX}ret_year_" 
    flex_ret_date_pattern = f"^{config.CALLBACK_PREFIX_FLEX}ret_date_" 

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start_command),
            CallbackQueryHandler(start_search_callback, pattern='^start_standard_search$|^start_flex_search$'),
            CallbackQueryHandler(start_flex_anywhere_callback, pattern='^start_flex_anywhere$')
        ],
        states={
            config.SELECTING_FLIGHT_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, standard_flight_type)],
            config.SELECTING_DEPARTURE_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, standard_departure_country)],
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

            config.SELECTING_FLEX_FLIGHT_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, flex_flight_type)],
            config.SELECTING_FLEX_MAX_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, flex_max_price)],
            config.ASK_FLEX_DEPARTURE_AIRPORT: [CallbackQueryHandler(flex_ask_departure_airport, pattern=f"^{config.CALLBACK_PREFIX_FLEX}ask_dep_")],
            config.SELECTING_FLEX_DEPARTURE_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, flex_departure_country)],
            config.SELECTING_FLEX_DEPARTURE_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, flex_departure_city)], # Переход изменен
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
            
            config.ASK_SEARCH_OTHER_AIRPORTS: [
                CallbackQueryHandler(handle_search_other_airports_decision, pattern=f"^{config.CALLBACK_YES_OTHER_AIRPORTS}$|^{config.CALLBACK_NO_OTHER_AIRPORTS}$")
            ],
        },
        fallbacks=[
            CommandHandler('cancel', cancel_handler),
            # Добавлены обработчики для плейсхолдеров с клавиатур
            CallbackQueryHandler(lambda u, c: u.callback_query.answer("Нет доступных опций.", show_alert=True), pattern="^no_valid_months_error$"),
            CallbackQueryHandler(lambda u, c: u.callback_query.answer("Нет доступных опций.", show_alert=True), pattern="^no_valid_dates_error$"), # Общий для диапазонов и спец. дат
            CallbackQueryHandler(lambda u, c: u.callback_query.answer("Нет доступных опций.", show_alert=True), pattern="^no_specific_dates_in_range_error$"), # Если нужен отдельный
            CallbackQueryHandler(lambda u, c: u.callback_query.answer("Нет доступных опций.", show_alert=True), pattern="^no_valid_date_ranges_error$"), # Для generate_date_range_buttons (если callback_data="no_dates" не используется)
            CallbackQueryHandler(lambda u, c: u.callback_query.answer("Нет доступных опций.", show_alert=True), pattern="^no_dates$"), # Для generate_date_range_buttons от ChatGPT

            # Старые обработчики (если они еще актуальны, или их можно совместить/удалить)
            # CallbackQueryHandler(lambda u, c: u.callback_query.answer("Этот месяц уже прошёл или недоступен для выбора.", show_alert=True), pattern="^ignore_past_month$"),
            # CallbackQueryHandler(lambda u, c: u.callback_query.answer("Эта дата уже прошла или недоступна для выбора.", show_alert=True), pattern="^ignore_past_day$"),
        ],
        map_to_parent={},
        per_message=False, 
        allow_reentry=True, # Рассмотрите возможность разрешить повторный вход для /start, чтобы прерывать диалог
    )
    
    return conv_handler