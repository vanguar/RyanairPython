# bot/admin_handlers.py

import logging
import io  # <-- ДОБАВЛЯЕМ ДЛЯ РАБОТЫ С ФАЙЛАМИ В ПАМЯТИ
import asyncio  # <-- ДОБАВЛЯЕМ ДЛЯ ПАРАЛЛЕЛЬНОГО СБОРА СТАТИСТИКИ
from datetime import datetime  # <-- ДОБАВЛЯЕМ ДЛЯ ДАТЫ В ИМЕНИ ФАЙЛА
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from . import config
from . import user_stats

logger = logging.getLogger(__name__)


# --- ИЗМЕНЕНИЕ 1: ДОБАВЛЯЕМ НОВУЮ КНОПКУ В КЛАВИАТУРУ ---
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
            # Вот она, новая кнопка:
            InlineKeyboardButton("📥 Скачать отчет", callback_data="stats_download"),
        ]
    ])

# Функция is_admin остается без изменений
def is_admin(user_id: int) -> bool:
    admin_id_str = config.ADMIN_TELEGRAM_ID
    return admin_id_str and str(user_id) == admin_id_str

# Функция stats_command остается без изменений
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        logger.warning(f"Попытка доступа к /stats от пользователя {update.effective_user.id}")
        return

    await update.message.reply_text(
        "📊 *Статистика новых пользователей*\nВыберите период:",
        reply_markup=get_stats_keyboard(),
        parse_mode="Markdown"
    )


# --- ИЗМЕНЕНИЕ 2: ДОРАБАТЫВАЕМ ОБРАБОТЧИК КНОПОК ---
async def stats_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия кнопок, включая скачивание отчета."""
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    period = query.data.split('_')[1]

    # Обработка кнопки "Скачать"
    if period == "download":
        await query.message.reply_chat_action('upload_document') # Показываем статус "отправка файла"

        # Собираем все данные параллельно для скорости
        day_count, week_count, month_count, total_count = await asyncio.gather(
            user_stats.count_new_users("day"),
            user_stats.count_new_users("week"),
            user_stats.count_new_users("month"),
            user_stats.count_new_users("total")
        )

        # Формируем текст для файла
        report_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        report_text = (
            f"Статистика пользователей бота на {report_date}\n"
            f"-----------------------------------------\n"
            f"Новых за сегодня: {day_count}\n"
            f"Новых за неделю: {week_count}\n"
            f"Новых за месяц: {month_count}\n"
            f"Всего пользователей: {total_count}\n"
        )
        
        # Создаем текстовый файл в памяти
        report_file = io.BytesIO(report_text.encode('utf-8'))
        
        # Генерируем имя файла с текущей датой
        filename = f"ryanair_bot_stats_{datetime.now().strftime('%Y-%m-%d')}.txt"
        
        # Отправляем файл как документ
        await context.bot.send_document(
            chat_id=query.message.chat_id,
            document=report_file,
            filename=filename
        )
        return # Завершаем выполнение, так как мы отправили новый документ

    # Обработка кнопки "Обновить"
    elif period == "refresh":
        await query.edit_message_text(
            "📊 *Статистика новых пользователей*\nВыберите период:",
            reply_markup=get_stats_keyboard(),
            parse_mode="Markdown"
        )
        return

    # Логика для остальных кнопок (сегодня, неделя, месяц, всего)
    else:
        count = await user_stats.count_new_users(period)
        period_rus_map = {
            'day': 'сегодня', 'week': 'неделю', 'month': 'месяц', 'total': 'всё время'
        }
        period_rus = period_rus_map.get(period, '')
        message_text = f"👤 Новых пользователей за {period_rus}: *{count}*"
        
        await query.edit_message_text(
            text=message_text,
            reply_markup=get_stats_keyboard(),
            parse_mode="Markdown"
        )

# Функция daily_report_job остается без изменений
async def daily_report_job(context: ContextTypes.DEFAULT_TYPE):
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