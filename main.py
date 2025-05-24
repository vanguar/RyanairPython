# main.py
import logging
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, Application # MODIFIED: Added Application, ContextTypes
from telegram import Update # MODIFIED: Added Update

# Импортируем конфигурацию и обработчики
from bot import config # [cite: 1]
from bot.handlers import (
    create_conversation_handler,
    show_all_remaining_flights_callback, # MODIFIED: May be deprecated by new flight display
    prompt_new_search_type_callback,
    end_search_session_callback,
    # NEW: Обработчик для кнопок поиска из других аэропортов, если он не в ConversationHandler
    # handle_search_other_airports_decision - он теперь часть ConversationHandler
)
# from bot.handlers import error_handler_conv # Глобальный error handler для ConversationHandler уже в нем

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log", mode='a', encoding='utf-8'), # Логи в файл
        logging.StreamHandler() # Логи в консоль
    ]
)
logger = logging.getLogger(__name__)

# Отключаем излишне подробные логи от httpx, если они мешают
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.INFO) # Общие логи библиотеки PTB


async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Логирует ошибки, вызванные Update."""
    logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)
    
    # Попытка уведомить пользователя, если это возможно
    if isinstance(update, Update) and update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Произошла непредвиденная ошибка. Попробуйте выполнить команду /start или свяжитесь с администратором, если проблема повторяется."
            )
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение об ошибке пользователю: {e}")
    
    # Очистка user_data в случае ошибки в диалоге, если это безопасно
    # if context.user_data and isinstance(context.error, YourSpecificDialogError):
    # context.user_data.clear()


def main() -> None:
    """Запускает бота."""
    if not config.TELEGRAM_BOT_TOKEN: # [cite: 1]
        logger.critical("Токен Telegram-бота не найден. Завершение работы.")
        return

    logger.info("Запуск бота...")

    # Создание экземпляра Application
    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build() # [cite: 1]

    # Получение ConversationHandler
    conv_handler = create_conversation_handler() #
    application.add_handler(conv_handler)

    # Добавляем обработчики для кнопок, работающих вне основного диалога ConversationHandler
    # show_all_remaining_flights_callback может быть не нужен с новым отображением
    # application.add_handler(CallbackQueryHandler(show_all_remaining_flights_callback, pattern="^show_all_remaining_flights$"))
    application.add_handler(CallbackQueryHandler(prompt_new_search_type_callback, pattern="^prompt_new_search_type$"))
    application.add_handler(CallbackQueryHandler(end_search_session_callback, pattern="^end_search_session$"))

    # NEW: Callback-обработчик для кнопок ДА/НЕТ при поиске из других аэропортов,
    # если он НЕ является частью ConversationHandler.
    # В текущей реализации handle_search_other_airports_decision добавлен в ConversationHandler.
    # Если бы он был отдельным, то:
    # application.add_handler(CallbackQueryHandler(handle_search_other_airports_decision, pattern=f"^{config.CALLBACK_YES_OTHER_AIRPORTS}$|^{config.CALLBACK_NO_OTHER_AIRPORTS}$"))

    # Глобальный обработчик ошибок
    application.add_error_handler(global_error_handler)

    logger.info("Бот запущен и готов к работе.")
    application.run_polling()

if __name__ == '__main__':
    main()