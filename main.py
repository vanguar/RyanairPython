# main.py
import logging
import asyncio # Для post_init, если будете использовать asyncio.run для main
from telegram import Update # Добавлен импорт Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from datetime import time
from bot import config
from bot import fx_rates
# Убедитесь, что handlers.py и его функции доступны для create_conversation_handler
from bot.handlers import (
    create_conversation_handler,
    prompt_new_search_type_callback, # Глобальный обработчик
    end_search_session_callback # Глобальный обработчик
)
from bot import user_history # Для init_db
# >>>>> ДОБАВЬ ЭТИ ИМПОРТЫ <<<<<
from bot import user_stats
from bot.admin_handlers import stats_command, stats_callback_handler, daily_report_job
# >>>>> КОНЕЦ <<<<<

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log", mode='a', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Уменьшаем уровень логгирования для слишком "болтливых" библиотек
logging.getLogger("httpx").setLevel(logging.WARNING)
# logging.getLogger("telegram.ext").setLevel(logging.INFO) # Можно оставить INFO или поднять до WARNING

async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Логирует ошибки, вызванные Update."""
    logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)
    
    if isinstance(update, Update) and update.effective_chat: # Проверяем, что update - это Update
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Произошла непредвиденная ошибка. Попробуйте выполнить команду /start или свяжитесь с администратором, если проблема повторяется."
            )
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение об ошибке пользователю: {e}")

async def post_init(application: Application) -> None:
    """Выполняется после инициализации приложения, но до начала поллинга."""
    await user_history.init_db()
    # >>>>> ДОБАВЬ ИНИЦИАЛИЗАЦИЮ ТАБЛИЦЫ СТАТИСТИКИ <<<<<
    await user_stats.init_db()
    await fx_rates.init_db()
    # >>>>> КОНЕЦ <<<<<
    logger.info("База данных инициализирована через post_init.")

# <<< НОВАЯ ФУНКЦИЯ-ОБЁРТКА >>>
# Она принимает аргумент `application`, как того требует PTB, и вызывает нашу функцию.
async def on_shutdown(application: Application) -> None:
    logger.info("Выполняется остановка бота, закрытие HTTP-клиента...")
    await fx_rates.close_client()    

def main() -> None:
    """Запускает бота."""
    if not config.TELEGRAM_BOT_TOKEN:
        logger.critical("Токен Telegram-бота не найден. Завершение работы.")
        return

    logger.info("Запуск бота...")

    # Создание экземпляра Application с post_init хуком
    application = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(on_shutdown)  # <-- РЕГИСТРИРУЕМ ОБЁРТКУ ЗДЕСЬ
        .build()
    )

    # ДОБАВЬТЕ ЭТУ СТРОКУ после создания application и перед application.add_handler
    # Этот хук корректно закроет HTTP-клиент при остановке бота.
    application.post_shutdown.append(fx_rates.close_client)
    # >>>>> ДОБАВЬ ЕЖЕДНЕВНУЮ ЗАДАЧУ (JOB QUEUE) <<<<<
    # Убедись, что ADMIN_TELEGRAM_ID задан в .env, иначе задача будет падать с ошибкой в логах
    if config.ADMIN_TELEGRAM_ID:
        # Запускаем каждый день в 21:00 по времени сервера
        application.job_queue.run_daily(daily_report_job, time(hour=21, minute=0))
        logger.info("Ежедневная задача для отправки отчета по статистике настроена.")
    else:
        logger.warning("ADMIN_TELEGRAM_ID не установлен. Ежедневный отчет по статистике не будет отправляться.")
    # >>>>> КОНЕЦ <<<<<

    # Получение ConversationHandler
    conv_handler = create_conversation_handler() # Убедитесь, что все зависимости для него (launch_flight_search) разрешены
    application.add_handler(conv_handler)
    # >>>>> ДОБАВЬ ОБРАБОТЧИКИ ДЛЯ АДМИН-ПАНЕЛИ <<<<<
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CallbackQueryHandler(stats_callback_handler, pattern="^stats_"))
    # >>>>> КОНЕЦ <<<<<

    # Глобальные обработчики для кнопок "Что дальше?"
    application.add_handler(CallbackQueryHandler(prompt_new_search_type_callback, pattern="^prompt_new_search_type$"))
    application.add_handler(CallbackQueryHandler(end_search_session_callback, pattern="^end_search_session$"))

    # Глобальный обработчик ошибок
    application.add_error_handler(global_error_handler)

    logger.info("Бот настроен и готов к работе. Запуск поллинга...")
    application.run_polling()

if __name__ == '__main__':
    main()