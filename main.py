# main.py
import logging
from telegram.ext import ApplicationBuilder, CommandHandler

# Импортируем конфигурацию и обработчики
from bot import config
from bot.handlers import create_conversation_handler, error_handler_conv # Убедитесь, что error_handler_conv определен

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

    # Добавление глобального обработчика ошибок для ConversationHandler
    # (Если он не обрабатывается внутри fallbacks самого ConversationHandler)
    # application.add_error_handler(error_handler_conv) # Раскомментируйте, если нужен глобальный обработчик ошибок для всего приложения

    logger.info("Бот запущен и готов к работе.")
    application.run_polling()

if __name__ == '__main__':
    main()