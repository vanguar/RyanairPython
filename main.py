# main.py
import logging
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, Application # MODIFIED: Defaults убран, если не используется явно
from telegram import Update

# Импортируем конфигурацию и обработчики
from bot import config
from bot.handlers import (
    create_conversation_handler,
    # show_all_remaining_flights_callback, # УДАЛЕНО, так как функция удалена из handlers.py
    prompt_new_search_type_callback,
    end_search_session_callback,
)

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

# Отключаем излишне подробные логи от httpx и telegram.ext, если они мешают
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.INFO)


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
    
    # Очистка user_data в случае ошибки в диалоге может быть полезной,
    # но должна делаться осторожно и только для определенных типов ошибок,
    # чтобы не потерять данные пользователя безвозвратно при временных сбоях.
    # Пример:
    # if context.user_data and isinstance(context.error, SpecificConversationError):
    #     logger.info(f"Очистка user_data для chat_id {update.effective_chat.id} из-за ошибки в диалоге.")
    #     context.user_data.clear()


def main() -> None:
    """Запускает бота."""
    if not config.TELEGRAM_BOT_TOKEN:
        logger.critical("Токен Telegram-бота не найден. Завершение работы.")
        return

    logger.info("Запуск бота...")

    # Создание экземпляра Application
    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    # Получение ConversationHandler
    conv_handler = create_conversation_handler()
    application.add_handler(conv_handler)

    # Добавляем обработчики для кнопок, работающих вне основного диалога ConversationHandler
    # Эти callback'и (prompt_new_search_type, end_search_session) вызываются кнопками,
    # которые отправляются в конце успешного поиска или при отмене.
    application.add_handler(CallbackQueryHandler(prompt_new_search_type_callback, pattern="^prompt_new_search_type$"))
    application.add_handler(CallbackQueryHandler(end_search_session_callback, pattern="^end_search_session$"))

    # Глобальный обработчик ошибок
    application.add_error_handler(global_error_handler)

    logger.info("Бот запущен и готов к работе.")
    application.run_polling()

if __name__ == '__main__':
    main()