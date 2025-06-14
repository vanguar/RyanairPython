# bot/admin_handlers.py

import logging
import io
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, error as telegram_error
from telegram.ext import ContextTypes
from telegram.error import BadRequest

from . import config
from . import user_stats

logger = logging.getLogger(__name__)


# --- КЛАВИАТУРА АДМИН-ПАНЕЛИ (без изменений) ---
def get_stats_keyboard() -> InlineKeyboardMarkup:
    """Возвращает клавиатуру для админ-панели статистики."""
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
            InlineKeyboardButton("📥 Скачать отчет", callback_data="stats_download"),
        ]
    ])

# --- ПРОВЕРКА АДМИНА (без изменений) ---
def is_admin(user_id: int) -> bool:
    admin_id_str = config.ADMIN_TELEGRAM_ID
    return admin_id_str and str(user_id) == admin_id_str

# --- КОМАНДА /stats (без изменений) ---
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        logger.warning(f"Попытка доступа к /stats от пользователя {update.effective_user.id}")
        return

    await update.message.reply_text(
        "📊 *Статистика новых пользователей*\nВыберите период:",
        reply_markup=get_stats_keyboard(),
        parse_mode="Markdown"
    )


# --- ОБРАБОТЧИК КНОПОК СТАТИСТИКИ (ИЗМЕНЁН) ---
async def stats_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия кнопок, включая скачивание отчета с username."""
    query = update.callback_query
    try:
        await query.answer()
    except BadRequest as e:
        if "Query is too old" in str(e):
            logger.warning(f"Нажата устаревшая кнопка в админ-панели: {e}")
            return
        else:
            logger.error(f"Ошибка BadRequest в админ-панели: {e}", exc_info=True)
            return
    except Exception as e:
        logger.warning(f"Не удалось выполнить query.answer() в админ-панели: {e}")

    if not is_admin(query.from_user.id):
        return

    period = query.data.split('_')[1]

    if period == "download":
        await query.message.reply_chat_action('upload_document')
        
        # 1. Параллельно получаем числовую статистику
        day_count, week_count, month_count, total_count, all_users = await asyncio.gather(
            user_stats.count_new_users("day"),
            user_stats.count_new_users("week"),
            user_stats.count_new_users("month"),
            user_stats.count_new_users("total"),
            user_stats.get_all_users() # 2. И список всех пользователей
        )
        
        report_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 3. Формируем первую часть отчета
        report_text = (
            f"Статистика пользователей бота на {report_date}\n"
            f"-----------------------------------------\n"
            f"Новых за сегодня: {day_count}\n"
            f"Новых за неделю: {week_count}\n"
            f"Новых за месяц: {month_count}\n"
            f"Всего пользователей: {total_count}\n"
        )
        
        # 4. Добавляем вторую часть отчета со списком пользователей
        report_text += "\n\n-----------------------------------------"
        report_text += "\nID и username всех пользователей:\n-----------------------------------------\n"
        for uid, uname in all_users:
            report_text += f"{uid:>12}  —  {uname or '-'}\n"
        
        # 5. Отправляем готовый файл
        report_file = io.BytesIO(report_text.encode('utf-8'))
        filename = f"ryanair_bot_stats_{datetime.now().strftime('%Y-%m-%d')}.txt"
        await context.bot.send_document(
            chat_id=query.message.chat_id,
            document=report_file,
            filename=filename
        )
        return

    try:
        if period == "refresh":
            await query.edit_message_text(
                "📊 Статистика новых пользователей\nВыберите период:",
                reply_markup=get_stats_keyboard(),
                parse_mode="Markdown"
            )
        else:
            count = await user_stats.count_new_users(period)
            period_rus_map = {
                'day': 'сегодня', 'week': 'неделю', 'month': 'месяц', 'total': 'всё время'
            }
            period_rus = period_rus_map.get(period, '')
            message_text = f"👤 *Новых пользователей за {period_rus}:* {count}"
            
            await query.edit_message_text(
                text=message_text,
                reply_markup=get_stats_keyboard(),
                parse_mode="Markdown"
            )
            
    except telegram_error.BadRequest as e:
        if "Message is not modified" in str(e):
            pass # Не логируем эту ошибку, т.к. она означает, что сообщение не изменилось
        else:
            logger.error(f"Ошибка BadRequest в stats_callback_handler: {e}", exc_info=True)


# --- ЕЖЕДНЕВНЫЙ ОТЧЁТ (без изменений) ---
async def daily_report_job(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Запуск ежедневной задачи: отправка отчета по статистике.")
    admin_id = config.ADMIN_TELEGRAM_ID
    if not admin_id:
        logger.warning("Не могу отправить ежедневный отчет: ADMIN_TELEGRAM_ID не установлен.")
        return

    counts = {p: await user_stats.count_new_users(p) for p in ("day", "week", "month", "total")}
    
    text = (
        f"📈 *Ежедневная сводка по пользователям*\n\n"
        f"Новых за сегодня: {counts['day']}\n"
        f"Новых за неделю: {counts['week']}\n"
        f"Всего пользователей: {counts['total']}"
    )
    
    await context.bot.send_message(chat_id=admin_id, text=text, parse_mode="Markdown")