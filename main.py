# main.py
import logging
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler

# Импортируем конфигурацию и обработчики
from bot import config
from bot.handlers import (
    create_conversation_handler,
    # error_handler_conv, # Раскомментируй, если будешь использовать глобальный обработчик ошибок
    show_all_remaining_flights_callback,
    prompt_new_search_type_callback,
    end_search_session_callback,
    # start_command # start_command уже обрабатывается через ConversationHandler entry_points
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

# Отключаем излишне подробные логи от httpx, если они мешают
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram.ext.Application").setLevel(logging.INFO) # Можно оставить INFO или поднять до WARNING


def main() -> None:
    """Запускает бота."""
    if not config.TELEGRAM_BOT_TOKEN:
        logger.critical("Токен Telegram-бота не найден. Завершение работы.")
        return

    logger.info("Запуск бота...")

    # Создание экземпляра Application
    application = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).build()

    # Получение ConversationHandler
    conv_handler = create_conversation_handler()
    application.add_handler(conv_handler)

    # Добавляем обработчики для кнопок, работающих вне основного диалога ConversationHandler
    application.add_handler(CallbackQueryHandler(show_all_remaining_flights_callback, pattern="^show_all_remaining_flights$"))
    application.add_handler(CallbackQueryHandler(prompt_new_search_type_callback, pattern="^prompt_new_search_type$"))
    application.add_handler(CallbackQueryHandler(end_search_session_callback, pattern="^end_search_session$"))

    # Глобальный обработчик ошибок (если нужен).
    # error_handler_conv из handlers.py был предназначен для fallbacks в ConversationHandler.
    # Для глобального обработчика можно создать отдельную функцию или адаптировать его.
    # Например:
    # async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    #     logger.error(f"Необработанная ошибка: {context.error}", exc_info=context.error)
    #     if isinstance(update, Update) and update.effective_chat:
    #         await context.bot.send_message(
    #             chat_id=update.effective_chat.id,
    #             text="Произошла непредвиденная ошибка. Попробуйте позже."
    #         )
    # application.add_error_handler(global_error_handler)

    logger.info("Бот запущен и готов к работе.")
    application.run_polling()

if __name__ == '__main__':
    main()