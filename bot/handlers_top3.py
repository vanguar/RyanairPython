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

    flights = await flight_api.get_cheapest_flights_top3(context.user_data, limit=3)
    if not flights:
        await context.bot.send_message(chat_id, "😔 Ничего не нашёл, попробуйте позже.")
        return ConversationHandler.END

    from_text = "отовсюду" if context.user_data.get("top3_from_anywhere") else context.user_data.get("departure_city_name", "—")

    await context.bot.send_message(chat_id,
        f"🔥 <b>Топ-3 самых дешёвых направлений</b>\nИз: {from_text}\n",
        parse_mode="HTML"
    )

    for idx, item in enumerate(flights, 1):
        formatted = await message_formatter.format_flight_details(item["flight"])
        await context.bot.send_message(chat_id,
            f"🏆 <b>#{idx}</b>\n{formatted}",
            parse_mode="HTML",
            disable_web_page_preview=True
        )

    # спросить о сохранении
    kb = keyboards.get_yes_no_keyboard(
        yes_callback=config.CALLBACK_TOP3_SAVE_YES,
        no_callback=config.CALLBACK_TOP3_SAVE_NO,
        yes_text="💾 Сохранить",
        no_text="❌ Не сохранять"
    )
    await context.bot.send_message(chat_id,
        "💾 Сохранить эти параметры и предлагать их при следующем нажатии «Топ-3»?",
        reply_markup=kb
    )
    return config.TOP3_ASK_SAVE

async def handle_save_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    if q.data == config.CALLBACK_TOP3_SAVE_YES:
        await user_history.save_search_parameters(update.effective_user.id, context.user_data)
        await q.edit_message_text(config.MSG_TOP3_SAVED)
    else:
        await q.edit_message_text(config.MSG_TOP3_NOT_SAVED)

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
