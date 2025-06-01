# bot/handlers_saved_search.py
import logging
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from . import config, keyboards, user_history

logger = logging.getLogger(__name__)

async def handle_save_search_preference_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, launch_flight_search_func) -> int:
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if query.data == config.CALLBACK_SAVE_SEARCH_YES:
        if context.user_data and context.user_data.get('current_search_flow'):
            await user_history.save_search_parameters(user_id, context.user_data)
            if query.message:
                try:
                    await query.edit_message_text(text=config.MSG_SEARCH_SAVED)
                except Exception as e:
                    logger.warning(f"Не удалось отредактировать сообщение ({config.MSG_SEARCH_SAVED}): {e}. Отправка нового.")
                    await context.bot.send_message(chat_id=chat_id, text=config.MSG_SEARCH_SAVED)
            else:
                await context.bot.send_message(chat_id=chat_id, text=config.MSG_SEARCH_SAVED)
        else:
            no_data_msg = "Нечего сохранять. Параметры поиска неполные."
            if query.message:
                try:
                    await query.edit_message_text(text=no_data_msg)
                except Exception as e:
                    logger.warning(f"Не удалось отредактировать сообщение ({no_data_msg}): {e}. Отправка нового.")
                    await context.bot.send_message(chat_id=chat_id, text=no_data_msg)
            else:
                await context.bot.send_message(chat_id=chat_id, text=no_data_msg)

    elif query.data == config.CALLBACK_SAVE_SEARCH_NO:
        if query.message:
            try:
                await query.edit_message_text(text=config.MSG_SEARCH_NOT_SAVED)
            except Exception as e:
                logger.warning(f"Не удалось отредактировать сообщение ({config.MSG_SEARCH_NOT_SAVED}): {e}. Отправка нового.")
                await context.bot.send_message(chat_id=chat_id, text=config.MSG_SEARCH_NOT_SAVED)
        else:
            await context.bot.send_message(chat_id=chat_id, text=config.MSG_SEARCH_NOT_SAVED)

    await context.bot.send_message(
        chat_id=chat_id, text="Что дальше?",
        reply_markup=keyboards.get_yes_no_keyboard(
            yes_callback="prompt_new_search_type", no_callback="end_search_session",
            yes_text="✅ Начать новый поиск", no_text="❌ Закончить"
        )
    )
    return ConversationHandler.END


async def start_last_saved_search_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, launch_flight_search_func) -> int:
    query = update.callback_query
    if not query:
        return ConversationHandler.END
    
    await query.answer()
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    saved_params = await user_history.get_last_saved_search(user_id)

    if saved_params:
        context.user_data.clear()
        for key, value in saved_params.items():
            context.user_data[key] = value
        
        load_message = config.MSG_LOADED_SAVED_SEARCH
        if query.message:
            try:
                await query.edit_message_text(text=load_message)
            except Exception:
                await context.bot.send_message(chat_id=chat_id, text=load_message)
        else:
            await context.bot.send_message(chat_id=chat_id, text=load_message)
        
        return await launch_flight_search_func(update, context)
    else:
        has_any_saved = await user_history.has_saved_searches(user_id)
        msg_to_send = config.MSG_ERROR_LOADING_SAVED_SEARCH if has_any_saved else config.MSG_NO_SAVED_SEARCHES_ON_START

        main_menu_kbd = keyboards.get_main_menu_keyboard(has_saved_searches=has_any_saved)
        if query.message:
            try:
                await query.edit_message_text(text=msg_to_send, reply_markup=main_menu_kbd)
            except Exception:
                await context.bot.send_message(chat_id=chat_id, text=msg_to_send, reply_markup=main_menu_kbd)
        else:
             await context.bot.send_message(chat_id=chat_id, text=msg_to_send, reply_markup=main_menu_kbd)
        return ConversationHandler.END