# main.py
import logging
from datetime import time

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

from bot import config
from bot import fx_rates
from bot import user_history
from bot import user_stats

# Handlers
from bot.handlers import (
    create_conversation_handler,
    prompt_new_search_type_callback,   # глобальный обработчик
    end_search_session_callback,       # глобальный обработчик
)
from bot.handlers import create_top3_conversation_handler  # фабрика топ-3

# Админ-панель и ежедневный отчёт
from bot.admin_handlers import stats_command, stats_callback_handler, daily_report_job

# Звёзды (Telegram Stars)
from bot.donate_stars import get_handlers as donate_get_handlers


# ---------- Базовая настройка логов ----------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log", mode="a", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
# logging.getLogger("telegram.ext").setLevel(logging.INFO)

# ---------- Глобальный обработчик ошибок ----------
async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Логирует ошибки, вызванные Update, и шлёт юзеру вежливое сообщение."""
    logger.exception("Произошла необработанная ошибка во время обработки апдейта")
    if isinstance(update, Update) and update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=(
                    "Произошла непредвиденная ошибка. Попробуйте выполнить команду /start "
                    "или свяжитесь с администратором, если проблема повторяется."
                ),
            )
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение об ошибке пользователю: {e}")

# ---------- Хуки жизненного цикла ----------
async def _log_bot_identity(app: Application) -> None:
    """Логируем, под каким ботом поднялось приложение (удобно для проверки токена)."""
    me = await app.bot.get_me()
    logging.getLogger(__name__).info(
        "Running as @%s (id=%s, name=%s %s)",
        me.username,
        me.id,
        me.first_name or "",
        me.last_name or "",
    )

async def _post_init_all(application: Application) -> None:
    """Единый post_init: сначала инициализируем БД/кеши, затем логируем identity."""
    await user_history.init_db()
    await user_stats.init_db()
    await fx_rates.init_db()
    logger.info("База данных инициализирована через post_init.")
    await _log_bot_identity(application)

async def on_shutdown(application: Application) -> None:
    """Чистое завершение: закрываем HTTP-клиент курсов валют и пр."""
    logger.info("Выполняется остановка бота, закрытие HTTP-клиента...")
    await fx_rates.close_client()


def main() -> None:
    """Точка входа бота."""
    if not config.TELEGRAM_BOT_TOKEN:
        logger.critical("Токен Telegram-бота не найден. Завершение работы.")
        return

    logger.info("Запуск бота...")

    # Создание Application с корректными хуками
    application = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .post_init(_post_init_all)   # ← единый post_init (инициализация БД + лог identity)
        .post_shutdown(on_shutdown)
        .build()
    )

    # Ежедневная задача (если указан админ)
    if config.ADMIN_TELEGRAM_ID:
        # Запуск каждый день в 21:00 по времени сервера
        application.job_queue.run_daily(daily_report_job, time(hour=21, minute=0))
        logger.info("Ежедневная задача для отправки отчета по статистике настроена.")
    else:
        logger.warning(
            "ADMIN_TELEGRAM_ID не установлен. Ежедневный отчет по статистике не будет отправляться."
        )

    # Основные ConversationHandler'ы
    conv_handler = create_conversation_handler()
    top3_handler = create_top3_conversation_handler()
    application.add_handler(conv_handler)
    application.add_handler(top3_handler)

    # Админ-панель
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CallbackQueryHandler(stats_callback_handler, pattern="^stats_"))

    # Глобальные обработчики «что дальше?»
    application.add_handler(
        CallbackQueryHandler(prompt_new_search_type_callback, pattern="^prompt_new_search_type$")
    )
    application.add_handler(
        CallbackQueryHandler(end_search_session_callback, pattern="^end_search_session$")
    )

    # Донаты звёздами (Stars)
    for h in donate_get_handlers():
        application.add_handler(h)

    # Глобальный обработчик ошибок
    application.add_error_handler(global_error_handler)

    logger.info("Бот настроен и готов к работе. Запуск поллинга...")
    application.run_polling()


if __name__ == "__main__":
    main()
