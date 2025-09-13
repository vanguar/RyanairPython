"""
bot/donate_stars.py
Витрина «подарков» через Telegram Stars (XTR) для PTB v20.

Фичи:
- /donate и кнопка "✨ Поддержать звёздами" показывают витрину.
- Предустановленные «подарки» (как в канале) + кнопка «🔢 Своя сумма».
- Конструктор суммы: шаги -10/-5/-1/+1/+5/+10, подтверждение «Оплатить ⭐ N» и «Отмена».
- По нажатию создаём инвойс (sendInvoice, currency='XTR', provider='STARS').
- После оплаты — кастомное «спасибо», лог и (опционально) уведомление админу.

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
STARS_MULTIPLIER = 1  # 1⭐ = 1 минимальная единица (сейчас так корректно)

# ---- Конструктор суммы ----
CUSTOM_MIN = 1
CUSTOM_MAX = 10000
CUSTOM_DEFAULT = 10
USER_KEY_AMOUNT = "donate_custom_amount"

# Если True — после отправки инвойса удаляем сообщение с витриной/конструктором
DELETE_MESSAGE_ON_INVOICE = True

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

# ---- Текст благодарности ----
THANK_YOU_TEXT_TEMPLATE = (
    "{gift} Спасибо за поддержку, {name}! "
    "Ты задонатил(а) {stars}⭐ — это мотивирует развивать бота. "
    "Если хочешь — поделись ссылкой на бота с друзьями 😉"
)

# ---- Вспомогательные клавиатуры ----
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

    # Своя сумма отдельной строкой
    buttons.append([InlineKeyboardButton("🔢 Своя сумма", callback_data="donate_custom")])
    # Назад
    buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data="donate_menu_back_to_menu")])
    return InlineKeyboardMarkup(buttons)

def _clamp_amount(n: int) -> int:
    return max(CUSTOM_MIN, min(CUSTOM_MAX, n))

def _build_amount_keyboard(amount: int) -> InlineKeyboardMarkup:
    amount = _clamp_amount(amount)
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("−10", callback_data="amount_step:-10"),
            InlineKeyboardButton("−5",  callback_data="amount_step:-5"),
            InlineKeyboardButton("−1",  callback_data="amount_step:-1"),
            InlineKeyboardButton("+1",  callback_data="amount_step:+1"),
            InlineKeyboardButton("+5",  callback_data="amount_step:+5"),
            InlineKeyboardButton("+10", callback_data="amount_step:+10"),
        ],
        [InlineKeyboardButton(f"Оплатить ⭐ {amount}", callback_data="amount_pay")],
        [InlineKeyboardButton("⬅️ Отмена", callback_data="amount_cancel")],
    ])

# ---- Общие помощники ----
def _gift_to_price(g: Gift) -> List[LabeledPrice]:
    amount = int(g.price_stars * STARS_MULTIPLIER)
    return [LabeledPrice(label=f"{g.title} {g.emoji}", amount=amount)]

def _custom_to_price(stars: int) -> List[LabeledPrice]:
    amount = int(_clamp_amount(stars) * STARS_MULTIPLIER)
    return [LabeledPrice(label=f"Поддержка ⭐ {stars}", amount=amount)]

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

# ---- Предустановленные подарки → инвойс ----
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

    # По желанию сворачиваем витрину
    if DELETE_MESSAGE_ON_INVOICE:
        try:
            await q.delete_message()
        except Exception:
            pass

# ---- Конструктор «Своя сумма» ----
async def donate_custom_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    context.user_data[USER_KEY_AMOUNT] = CUSTOM_DEFAULT
    await q.edit_message_text(
        f"🔢 Укажи сумму поддержки (⭐): текущее значение — {CUSTOM_DEFAULT}\n"
        f"Диапазон {CUSTOM_MIN}…{CUSTOM_MAX}⭐",
        reply_markup=_build_amount_keyboard(CUSTOM_DEFAULT),
    )

async def amount_step_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    delta_str = q.data.split(":")[1]
    try:
        delta = int(delta_str)
    except Exception:
        return

    current = int(context.user_data.get(USER_KEY_AMOUNT, CUSTOM_DEFAULT))
    new_amount = _clamp_amount(current + delta)
    context.user_data[USER_KEY_AMOUNT] = new_amount

    try:
        await q.edit_message_text(
            f"🔢 Укажи сумму поддержки (⭐): текущее значение — {new_amount}\n"
            f"Диапазон {CUSTOM_MIN}…{CUSTOM_MAX}⭐",
            reply_markup=_build_amount_keyboard(new_amount),
        )
    except Exception:
        pass

async def amount_cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer("Отменено")
    await q.edit_message_text(
        "✨ Выберите подарок, чтобы поддержать автора:",
        reply_markup=_build_gifts_keyboard()
    )

async def amount_pay_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    amount = int(context.user_data.get(USER_KEY_AMOUNT, CUSTOM_DEFAULT))
    amount = _clamp_amount(amount)
    chat_id = update.effective_chat.id
    payload = f"custom:{amount}:{int(time.time())}:{chat_id}"

    await context.bot.send_invoice(
        chat_id=chat_id,
        title=f"⭐ Поддержка ({amount})",
        description="Свободная сумма поддержки",
        payload=payload,
        provider_token=PROVIDER_TOKEN,
        currency=CURRENCY,
        prices=_custom_to_price(amount),
    )

    if DELETE_MESSAGE_ON_INVOICE:
        try:
            await q.delete_message()
        except Exception:
            pass

# ---- PreCheckout обязательно ok=True ----
async def precheckout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.pre_checkout_query
    await query.answer(ok=True)

# ---- Успешная оплата ----
async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sp = update.message.successful_payment
    total = sp.total_amount
    stars = total // STARS_MULTIPLIER if STARS_MULTIPLIER else total
    payload = sp.invoice_payload or ""
    user = update.effective_user
    name = user.first_name or (user.username and f"@{user.username}") or "друг"

    gift_emoji = "✨"
    gift_title = "Подарка/поддержка"

    # Пытаемся разобрать payload
    try:
        parts = payload.split(":")
        if parts and parts[0] == "gift":
            gift_id = int(parts[1])
            if 0 <= gift_id < len(GIFTS):
                gift_emoji = GIFTS[gift_id].emoji
                gift_title = GIFTS[gift_id].title
        elif parts and parts[0] == "custom":
            gift_emoji = "⭐"
            gift_title = f"Своя сумма ({parts[1]}⭐)"
    except Exception:
        pass

    # Спасибо
    thank_text = THANK_YOU_TEXT_TEMPLATE.format(gift=gift_emoji, name=name, stars=stars)
    try:
        await update.message.reply_text(thank_text)
    except Exception as e:
        log.warning("Не смогли отправить спасибо: %s", e)

    # Лог
    log.info("⭐ DONATION: user_id=%s username=%s type=%s stars=%s payload=%s",
             user.id, user.username, gift_title, stars, payload)

    # Уведомление админу
    if ADMIN_ID:
        try:
            await context.bot.send_message(
                chat_id=int(ADMIN_ID),
                text=(f"⭐ Донат получен\n"
                      f"Пользователь: @{user.username or user.id}\n"
                      f"Тип: {gift_emoji} {gift_title}\n"
                      f"Сумма: {stars} ⭐")
            )
        except Exception as e:
            log.debug("Не удалось отправить уведомление админу: %s", e)

# ---- Экспорт хендлеров ----
def get_handlers():
    return [
        CommandHandler("donate", donate_command),
        # витрина
        CallbackQueryHandler(donate_menu_callback, pattern="^donate_menu$"),
        CallbackQueryHandler(donate_menu_back_to_menu, pattern="^donate_menu_back_to_menu$"),
        CallbackQueryHandler(gift_pick_handler, pattern="^gift_pick:\\d+$"),
        # своя сумма
        CallbackQueryHandler(donate_custom_start, pattern="^donate_custom$"),
        CallbackQueryHandler(amount_step_handler, pattern="^amount_step:(?:\\+|-)?\\d+$"),
        CallbackQueryHandler(amount_cancel_handler, pattern="^amount_cancel$"),
        CallbackQueryHandler(amount_pay_handler, pattern="^amount_pay$"),
        # платежи
        PreCheckoutQueryHandler(precheckout_handler),
        MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler),
    ]
