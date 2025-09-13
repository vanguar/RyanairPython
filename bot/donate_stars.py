"""
bot/donate_stars.py
Витрина «подарков» через Telegram Stars (XTR) для PTB v20.

Что делает:
- Кнопка "✨ Поддержать звёздами" (callback_data="donate_menu") и команда /donate показывают витрину подарков.
- По нажатию на «подарок» бот выставляет инвойс (sendInvoice) с currency='XTR'.
- Обрабатывает PreCheckoutQuery и SuccessfulPayment, шлёт благодарность.

Подключение в main.py:
    from bot.donate_stars import get_handlers as donate_get_handlers
    for h in donate_get_handlers():
        application.add_handler(h)

Важно:
- Для Stars используем currency='XTR' и provider_token='STARS' (или из ENV).
- Сумма указывается в «минимальных единицах». Сейчас берём множитель 100:
  1 ⭐ = 100 минимальных единиц. Если у тебя покажет «неправильное» число —
  поменяй STARS_MULTIPLIER на 1.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List

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

# ---- Конфиг/провайдер ----
try:
    from . import config  # bot.config
    PROVIDER_TOKEN = getattr(config, "TELEGRAM_STARS_PROVIDER_TOKEN", "STARS")
except Exception:
    PROVIDER_TOKEN = "STARS"

CURRENCY = "XTR"
STARS_MULTIPLIER = 1  # 1 ⭐ = 100 минимальных единиц (если что — поменяешь на 1)

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
    # Здесь можно перерисовать твоё главное меню. Чтобы не тянуть зависимости:
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
    await _send_invoice_for_gift(update, context, gift_id)

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
    gift_emoji = "✨"

    try:
        parts = payload.split(":")
        if len(parts) >= 2 and parts[0] == "gift":
            gift_id = int(parts[1])
            if 0 <= gift_id < len(GIFTS):
                gift_emoji = GIFTS[gift_id].emoji
    except Exception:
        pass

    await update.message.reply_text(
        f"{gift_emoji} Спасибо! Оплата прошла успешно — {stars}⭐"
    )

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
