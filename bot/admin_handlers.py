# bot/admin_handlers.py
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from . import config
from . import user_stats  # Импортируем наш новый модуль

logger = logging.getLogger(__name__)

# Клавиатура для выбора периода статистики
def get_stats_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("За сегодня", callback_data="stats_day"),
            InlineKeyboardButton("За неделю", callback_data="stats_week"),
        ],
        [
            InlineKeyboardButton("За месяц", callback_data="stats_month"),
            InlineKeyboardButton("За всё время", callback_data="stats_total"),
        ],
        [
            InlineKeyboardButton("🔄 Обновить", callback_data="stats_refresh"),
        ]
    ])

def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь админом."""
    admin_id_str = config.ADMIN_TELEGRAM_ID
    return admin_id_str and str(user_id) == admin_id_str


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет меню статистики, если команду вызвал админ."""
    if not is_admin(update.effective_user.id):
        logger.warning(f"Попытка доступа к /stats от пользователя {update.effective_user.id}")
        return

    await update.message.reply_text(
        "📊 *Статистика новых пользователей*\nВыберите период:",
        reply_markup=get_stats_keyboard(),
        parse_mode="Markdown"
    )

async def stats_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия кнопок в меню статистики."""
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    # 'stats_day' -> 'day'
    period = query.data.split('_')[1]
    
    if period == "refresh":
        await query.edit_message_text(
            "📊 *Статистика новых пользователей*\nВыберите период:",
            reply_markup=get_stats_keyboard(),
            parse_mode="Markdown"
        )
        return

    count = await user_stats.count_new_users(period)
    
    period_rus_map = {
        'day': 'сегодня', 'week': 'неделю', 'month': 'месяц', 'total': 'всё время'
    }
    period_rus = period_rus_map.get(period, '')

    message_text = f"👤 Новых пользователей за {period_rus}: *{count}*"
    
    # Редактируем сообщение, добавляя результат и оставляя клавиатуру для других запросов
    await query.edit_message_text(
        text=message_text,
        reply_markup=get_stats_keyboard(),
        parse_mode="Markdown"
    )

async def daily_report_job(context: ContextTypes.DEFAULT_TYPE):
    """Задача, которая отправляет ежедневный отчет админу."""
    logger.info("Запуск ежедневной задачи: отправка отчета по статистике.")
    admin_id = config.ADMIN_TELEGRAM_ID
    if not admin_id:
        logger.warning("Не могу отправить ежедневный отчет: ADMIN_TELEGRAM_ID не установлен.")
        return

    counts = {p: await user_stats.count_new_users(p) for p in ("day", "week", "month", "total")}
    
    text = (
        f"📈 *Ежедневная сводка по пользователям*\n\n"
        f"Новых за сегодня: *{counts['day']}*\n"
        f"Новых за неделю: *{counts['week']}*\n"

        f"Всего пользователей: *{counts['total']}*"
    )
    
    await context.bot.send_message(chat_id=admin_id, text=text, parse_mode="Markdown")