# main.py
import logging
import asyncio
from telegram import Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from datetime import time
from bot import config
from bot import fx_rates
from bot.handlers import (
    create_conversation_handler,
    prompt_new_search_type_callback,
    end_search_session_callback
)
from bot import user_history
from bot import user_stats
from bot.admin_handlers import stats_command, stats_callback_handler, daily_report_job

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log", mode='a', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

logging.getLogger("httpx").setLevel(logging.WARNING)

async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)
    if isinstance(update, Update) and update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Произошла непредвиденная ошибка. Попробуйте выполнить команду /start."
            )
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение об ошибке пользователю: {e}")

async def post_init(application: Application) -> None:
    await user_history.init_db()
    await user_stats.init_db()
    await fx_rates.init_db()
    logger.info("Все базы данных инициализированы через post_init.")

async def on_shutdown(application: Application) -> None:
    logger.info("Выполняется остановка бота, закрытие HTTP-клиента...")
    await fx_rates.close_client()

def main() -> None:
    if not config.TELEGRAM_BOT_TOKEN:
        logger.critical("Токен Telegram-бота не найден. Завершение работы.")
        return
    logger.info("Запуск бота...")

    application = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(on_shutdown)
        .build()
    )

    if config.ADMIN_TELEGRAM_ID:
        application.job_queue.run_daily(daily_report_job, time(hour=21, minute=0))
        logger.info("Ежедневная задача для отправки отчета по статистике настроена.")
    else:
        logger.warning("ADMIN_TELEGRAM_ID не установлен. Ежедневный отчет не будет отправляться.")

    conv_handler = create_conversation_handler()
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CallbackQueryHandler(stats_callback_handler, pattern="^stats_"))
    application.add_handler(CallbackQueryHandler(prompt_new_search_type_callback, pattern="^prompt_new_search_type$"))
    application.add_handler(CallbackQueryHandler(end_search_session_callback, pattern="^end_search_session$"))
    application.add_error_handler(global_error_handler)

    logger.info("Бот настроен и готов к работе. Запуск поллинга...")
    application.run_polling()

if __name__ == '__main__':
    main()