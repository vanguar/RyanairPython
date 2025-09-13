"""
bot/donate_stars.py
Витрина «подарков» через Telegram Stars (XTR) для PTB v20.

Апгрейды:
- /donate и кнопка "✨ Поддержать звёздами" показывают витрину.
- По нажатию на подарок: отправляется инвойс (Stars), ВИТРИНА автоматически сворачивается.
- После оплаты: кастомное "спасибо", лог в консоль, опциональное уведомление админу.

Подключение в main.py (у тебя уже сделано):
    from bot.donate_stars import get_handlers as donate_get_handlers
    for h in donate_get_handlers():
        application.add_handler(h)
"""

from __future__ import annotations

import time
import logging
from dataclasses import dataclass
from typing import List, Optional

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
)
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
)

log = logging.getLogger(__name__)

# ---- Конфиг/провайдер ----
try:
    from . import config  # bot.config
    PROVIDER_TOKEN = getattr(config, "TELEGRAM_STARS_PROVIDER_TOKEN", "STARS")
    ADMIN_ID: Optional[int] = getattr(config, "ADMIN_TELEGRAM_ID", None)
except Exception:
    PROVIDER_TOKEN = "STARS"
    ADMIN_ID = None

CURRENCY = "XTR"
# ⚠️ Для текущего поведения Stars множитель = 1 (1⭐ = 1 минимальная единица).
STARS_MULTIPLIER = 1

# ---- Модель подарка ----
@dataclass(frozen=True)
class Gift:
    emoji: str
    title: str
    price_stars: int
    description: str

# ---- Каталог «подарков» (максимально похоже на канал) ----
GIFTS: List[Gift] = [
    Gift("💖", "Сердце",             15,  "Спасибо за поддержку!"),
    Gift("🧸", "Плюшевый медведь",    15,  "Милота и забота."),
    Gift("🎁", "Подарок",             25,  "Тёплый сюрприз!"),
    Gift("🌹", "Роза",                25,  "Классический знак внимания."),
    Gift("🎂", "Торт",                50,  "За твои старания!"),
    Gift("💐", "Букет",               50,  "Охапка благодарности."),
    Gift("🚀", "Ракета",              50,  "Взлетаем!"),
    Gift("🏆", "Кубок",              100,  "Топовый бот — топовая награда."),
    Gift("💍", "Кольцо",             100,  "Ого. Это серьёзно!"),
]

# ---- Текст благодарности (можешь кастомизировать как хочешь) ----
THANK_YOU_TEXT_TEMPLATE = (
    "{gift} Спасибо за поддержку, {name}! "
    "Ты задонатил(а) {stars}⭐ — это мотивирует развивать бота. "
    "Если хочешь — подпишись и расскажи друзьям 😉"
)

# Если включить True — после выбора подарка удаляем «витрину», чтобы чат был чище
DELETE_CATALOG_ON_INVOICE = True

# ---- Клавиатуры ----
def _build_gifts_keyboard() -> InlineKeyboardMarkup:
    buttons: List[List[InlineKeyboardButton]] = []
    row: List[InlineKeyboardButton] = []

    for idx, g in enumerate(GIFTS):
        text = f"{g.emoji} {g.title} ({g.price_stars}⭐)"
        row.append(InlineKeyboardButton(text, callback_data=f"gift_pick:{idx}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data="donate_menu_back_to_menu")])
    return InlineKeyboardMarkup(buttons)

# ---- Entry-пойнты ----
async def donate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    await context.bot.send_message(
        chat_id=chat_id,
        text="✨ Выберите подарок, чтобы поддержать автора:",
        reply_markup=_build_gifts_keyboard()
    )

async def donate_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        "✨ Выберите подарок, чтобы поддержать автора:",
        reply_markup=_build_gifts_keyboard()
    )

async def donate_menu_back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer("Назад")
    await q.edit_message_text("Вы вернулись в меню. Нажмите /start, чтобы продолжить.")

# ---- Выставление инвойса ----
def _gift_to_price(g: Gift) -> List[LabeledPrice]:
    amount = int(g.price_stars * STARS_MULTIPLIER)
    return [LabeledPrice(label=f"{g.title} {g.emoji}", amount=amount)]

async def _send_invoice_for_gift(update: Update, context: ContextTypes.DEFAULT_TYPE, gift_id: int) -> None:
    chat_id = update.effective_chat.id
    g = GIFTS[gift_id]
    payload = f"gift:{gift_id}:{int(time.time())}:{chat_id}"

    await context.bot.send_invoice(
        chat_id=chat_id,
        title=f"{g.emoji} {g.title}",
        description=g.description,
        payload=payload,
        provider_token=PROVIDER_TOKEN,
        currency=CURRENCY,
        prices=_gift_to_price(g),
    )

# ---- Обработчики выбора подарка ----
async def gift_pick_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    try:
        _, idx_str = q.data.split(":")
        gift_id = int(idx_str)
    except Exception:
        await q.answer("Ошибка выбора подарка", show_alert=True)
        return

    # 1) Отправляем инвойс
    await _send_invoice_for_gift(update, context, gift_id)

    # 2) Сворачиваем витрину (чтобы не засорять чат)
    try:
        if DELETE_CATALOG_ON_INVOICE:
            await q.delete_message()
        else:
            g = GIFTS[gift_id]
            await q.edit_message_text(
                f"Вы выбрали: {g.emoji} {g.title} — {g.price_stars}⭐\n"
                f"Теперь подтвердите оплату в появившемся окне ниже.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("⬅️ Выбрать другой подарок", callback_data="donate_menu")]]
                )
            )
    except Exception as e:
        log.debug("Не удалось свернуть/отредактировать витрину: %s", e)

# ---- PreCheckout: обязательно ответить ok=True ----
async def precheckout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.pre_checkout_query
    await query.answer(ok=True)

# ---- Успешная оплата ----
async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sp = update.message.successful_payment
    total = sp.total_amount  # в минимальных единицах XTR
    stars = total // STARS_MULTIPLIER if STARS_MULTIPLIER else total
    payload = sp.invoice_payload or ""
    user = update.effective_user
    name = user.first_name or (user.username and f"@{user.username}") or "друг"

    gift_emoji = "✨"
    gift_title = "Подарок"

    # Пытаемся вытащить id подарка из payload
    try:
        parts = payload.split(":")
        if len(parts) >= 2 and parts[0] == "gift":
            gift_id = int(parts[1])
            if 0 <= gift_id < len(GIFTS):
                gift_emoji = GIFTS[gift_id].emoji
                gift_title = GIFTS[gift_id].title
    except Exception:
        pass

    # 1) Тёплое «спасибо»
    thank_text = THANK_YOU_TEXT_TEMPLATE.format(gift=gift_emoji, name=name, stars=stars)
    try:
        await update.message.reply_text(thank_text)
    except Exception as e:
        log.warning("Не смогли отправить спасибо: %s", e)

    # 2) Лог в консоль
    log.info("⭐ DONATION: user_id=%s username=%s gift=%s stars=%s payload=%s",
             user.id, user.username, gift_title, stars, payload)

    # 3) Уведомление админу (если указан)
    if ADMIN_ID:
        try:
            await context.bot.send_message(
                chat_id=int(ADMIN_ID),
                text=(f"⭐ Донат получен\n"
                      f"Пользователь: @{user.username or user.id}\n"
                      f"Подарок: {gift_emoji} {gift_title}\n"
                      f"Сумма: {stars} ⭐")
            )
        except Exception as e:
            log.debug("Не удалось отправить уведомление админу: %s", e)

# ---- Экспорт набора хендлеров для main.py ----
def get_handlers():
    return [
        CommandHandler("donate", donate_command),
        CallbackQueryHandler(donate_menu_callback, pattern="^donate_menu$"),
        CallbackQueryHandler(donate_menu_back_to_menu, pattern="^donate_menu_back_to_menu$"),
        CallbackQueryHandler(gift_pick_handler, pattern="^gift_pick:\\d+$"),
        PreCheckoutQueryHandler(precheckout_handler),
        MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler),
    ]
