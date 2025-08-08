# bot/handlers_top3.py
import logging
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, CommandHandler, filters
from telegram.error import BadRequest

from . import config, keyboards, flight_api, message_formatter, user_history, helpers

logger = logging.getLogger(__name__)

# ---------- entry-point ----------

async def start_top3(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Старт кнопки «🔥 Топ-3 направления»."""
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    try:
        await query.answer("🔥", cache_time=1)
    except BadRequest:
        return ConversationHandler.END

    context.user_data.clear()
    context.user_data["current_search_flow"] = config.FLOW_TOP3

    # проверяем — есть ли сохранённые настройки именно для top3
    saved = await user_history.get_last_saved_search(update.effective_user.id)
    if saved and saved.get("current_search_flow") == config.FLOW_TOP3:
        kb = keyboards.get_yes_no_keyboard(
            yes_callback="top3_use_saved",
            no_callback="top3_new_search",
            yes_text="💾 Использовать сохранённые",
            no_text="🆕 Новый поиск"
        )
        await query.edit_message_text(
            f"{config.MSG_TOP3_WELCOME}\n\nУ вас уже есть сохранённые параметры.",
            reply_markup=kb
        )
        return config.TOP3_ASK_SCOPE

    # иначе сразу спрашиваем «отовсюду / из города»
    return await ask_scope(update, context)

# ---------- шаг 1: «отовсюду / город» ----------

async def ask_scope(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    kb = keyboards.get_yes_no_keyboard(
        yes_callback=config.CALLBACK_TOP3_SPECIFIC_CITY,
        no_callback=config.CALLBACK_TOP3_FROM_ANYWHERE,
        yes_text="🏙️ Конкретный город",
        no_text="🌍 Отовсюду"
    )
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=config.MSG_TOP3_SCOPE,
        reply_markup=kb
    )
    return config.TOP3_ASK_SCOPE

async def handle_scope_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()

    if q.data == "top3_use_saved":        # загрузка сохранённых
        saved = await user_history.get_last_saved_search(update.effective_user.id)
        context.user_data.update(saved)
        await q.edit_message_text("💾 Использую сохранённые настройки…")
        return await execute_search(update, context)

    if q.data == "top3_new_search":
        return await ask_scope(update, context)

    if q.data == config.CALLBACK_TOP3_FROM_ANYWHERE:
        context.user_data["top3_from_anywhere"] = True
        context.user_data["airport_pool"]       = config.POPULAR_DEPARTURE_AIRPORTS.copy()

        await q.edit_message_text(
            "🌍 Ищу лучшие направления из популярных европейских хабов…"
        )
        return await execute_search(update, context)

    if q.data == config.CALLBACK_TOP3_SPECIFIC_CITY:
        context.user_data["top3_from_anywhere"] = False
        await q.edit_message_text("🌍 Выберите страну вылета:")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="🌍 Страна:",
            reply_markup=keyboards.get_country_reply_keyboard()
        )
        return config.TOP3_ASK_COUNTRY

    return ConversationHandler.END

# ---------- шаг 2: страна / город ----------

async def handle_country_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    country = update.message.text
    if country not in config.COUNTRIES_DATA:
        await update.message.reply_text("Не могу найти такую страну, выберите из списка.")
        return config.TOP3_ASK_COUNTRY

    context.user_data["departure_country"] = country
    await update.message.reply_text(
        f"🏙️ Город в {country}:",
        reply_markup=keyboards.get_city_reply_keyboard(country)
    )
    return config.TOP3_ASK_CITY

async def handle_city_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    country = context.user_data["departure_country"]
    city    = update.message.text
    iata    = helpers.get_airport_iata(country, city)
    if not iata:
        await update.message.reply_text("Город не найден, попробуйте ещё раз.")
        return config.TOP3_ASK_CITY

    context.user_data.update({
        "departure_airport_iata": iata,
        "departure_city_name": city
    })
    await update.message.reply_text(f"✅ Выбран {city} ({iata})", reply_markup=ReplyKeyboardRemove())
    return await execute_search(update, context)

# ---------- поиск и вывод ----------

async def execute_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = update.effective_chat.id
    await context.bot.send_message(chat_id, "🔍 Ищу топ-3…")

    # определяем, один аэропорт или пул
    airport_pool = context.user_data.get("airport_pool")
    all_flights: list[dict] = []

    if airport_pool:
        # перебираем первые N хабов (чтобы не делать десятки запросов)
        for dep_iata in airport_pool[:5]:
            tmp_params          = context.user_data.copy()
            tmp_params["departure_airport_iata"] = dep_iata
            flights             = await flight_api.get_cheapest_flights_top3(tmp_params, limit=10)
            if flights:
                all_flights.extend(flights)
    else:
        flights = await flight_api.get_cheapest_flights_top3(context.user_data, limit=3)
        all_flights.extend(flights)

    if not all_flights:
        await context.bot.send_message(chat_id, "😔 Ничего дешёвого не нашёл, попробуйте позже.")
        return ConversationHandler.END

    # сортируем агрегированный пул по цене
    all_flights.sort(key=lambda x: x["price"])
    top3 = all_flights[:3]

    from_text = "популярных европейских хабов" if airport_pool else context.user_data.get(
        "departure_city_name", "—")

    await context.bot.send_message(
        chat_id,
        f"🔥 <b>Топ-3 самых дешёвых направлений</b>\nИз: {from_text}\n",
        parse_mode="HTML"
    )

    for idx, item in enumerate(top3, 1):
        formatted = await message_formatter.format_flight_details(item["flight"])
        await context.bot.send_message(
            chat_id,
            f"🏆 <b>#{idx}</b>\n{formatted}",
            parse_mode="HTML",
            disable_web_page_preview=True
        )

    # спрашиваем о сохранении
    kb = keyboards.get_yes_no_keyboard(
        yes_callback=config.CALLBACK_TOP3_SAVE_YES,
        no_callback=config.CALLBACK_TOP3_SAVE_NO,
        yes_text="💾 Сохранить",
        no_text="❌ Не сохранять"
    )
    await context.bot.send_message(
        chat_id,
        "💾 Сохранить эти параметры и предлагать их при следующем нажатии «Топ-3»?",
        reply_markup=kb
    )
    return config.TOP3_ASK_SAVE


async def handle_save_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Жмём «Сохранить / Не сохранять» после выдачи Top-3"""
    q = update.callback_query
    await q.answer()

    user_id = update.effective_user.id

    if q.data == config.CALLBACK_TOP3_SAVE_YES:
        await user_history.save_search_parameters(user_id, context.user_data)
        await q.edit_message_text(config.MSG_TOP3_SAVED)
    else:                                 # CALLBACK_TOP3_SAVE_NO
        await q.edit_message_text(config.MSG_TOP3_NOT_SAVED)

    # есть ли вообще какие-то сохранённые поиски у пользователя
    has_saved = await user_history.has_saved_searches(user_id)

    # показываем главное меню сразу, чтобы диалог не «завис»
    main_kb = keyboards.get_main_menu_keyboard(has_saved_searches=has_saved)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="👇 Выберите, что делаем дальше:",
        reply_markup=main_kb,
    )

    context.user_data.clear()
    return ConversationHandler.END





async def cancel_top3(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("🛑 Поиск Top-3 отменён.")
    else:
        await update.message.reply_text("🛑 Поиск Top-3 отменён.", reply_markup=ReplyKeyboardRemove())
    context.user_data.clear()
    return ConversationHandler.END


