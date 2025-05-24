# bot/helpers.py
import logging
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from telegram import Update
from .config import COUNTRIES_DATA

logger = logging.getLogger(__name__)

def format_flight_details(flight) -> str:
    """Форматирует информацию о рейсе для вывода пользователю."""
    try:
        if hasattr(flight, 'price') and flight.price is not None: # Рейс в одну сторону
            departure_time_dt = flight.departureTime
            if isinstance(departure_time_dt, str):
                try:
                    departure_time_dt = datetime.fromisoformat(departure_time_dt.replace("Z", "+00:00"))
                except ValueError:
                    logger.warning(f"Could not parse date string: {flight.departureTime}")
                    # Keep original string if parsing fails
            
            departure_time_str = departure_time_dt.strftime("%Y-%m-%d %H:%M") if isinstance(departure_time_dt, datetime) else str(flight.departureTime)

            return (
                f"✈️  Рейс : {getattr(flight, 'flightNumber', 'N/A')}\n"
                f"📍  Маршрут : {getattr(flight, 'originFull', 'N/A')} -> {getattr(flight, 'destinationFull', 'N/A')}\n"
                f"🕒  Вылет : {departure_time_str}\n"
                f"💰  Цена : {Decimal(str(flight.price)).quantize(Decimal('0.01'))} {getattr(flight, 'currency', 'N/A')}\n"
            ) + "\n--------------------------\n"
        elif hasattr(flight, 'outbound') and flight.outbound and hasattr(flight.outbound, 'price') and \
             hasattr(flight, 'inbound') and flight.inbound and hasattr(flight.inbound, 'price'): # Рейс туда и обратно
            
            outbound = flight.outbound
            inbound = flight.inbound

            out_departure_time_dt = outbound.departureTime
            if isinstance(out_departure_time_dt, str):
                try:
                    out_departure_time_dt = datetime.fromisoformat(out_departure_time_dt.replace("Z", "+00:00"))
                except ValueError:
                     logger.warning(f"Could not parse outbound date string: {outbound.departureTime}")

            out_departure_time_str = out_departure_time_dt.strftime("%Y-%m-%d %H:%M") if isinstance(out_departure_time_dt, datetime) else str(outbound.departureTime)

            in_departure_time_dt = inbound.departureTime
            if isinstance(in_departure_time_dt, str):
                try:
                    in_departure_time_dt = datetime.fromisoformat(in_departure_time_dt.replace("Z", "+00:00"))
                except ValueError:
                    logger.warning(f"Could not parse inbound date string: {inbound.departureTime}")
            
            in_departure_time_str = in_departure_time_dt.strftime("%Y-%m-%d %H:%M") if isinstance(in_departure_time_dt, datetime) else str(inbound.departureTime)

            total_price = Decimal(str(outbound.price)) + Decimal(str(inbound.price))
            return (
                f"🔄  Рейс туда и обратно \n\n"
                f"➡️  Вылет туда :\n"
                f"  -  Рейс : {getattr(outbound, 'flightNumber', 'N/A')}\n"
                f"  -  Маршрут : {getattr(outbound, 'originFull', 'N/A')} -> {getattr(outbound, 'destinationFull', 'N/A')}\n"
                f"  -  Вылет : {out_departure_time_str}\n"
                f"  -  Цена : {Decimal(str(outbound.price)).quantize(Decimal('0.01'))} {getattr(outbound, 'currency', 'N/A')}\n\n"
                f"⬅️  Вылет обратно :\n"
                f"  -  Рейс : {getattr(inbound, 'flightNumber', 'N/A')}\n"
                f"  -  Маршрут : {getattr(inbound, 'originFull', 'N/A')} -> {getattr(inbound, 'destinationFull', 'N/A')}\n"
                f"  -  Вылет : {in_departure_time_str}\n"
                f"  -  Цена : {Decimal(str(inbound.price)).quantize(Decimal('0.01'))} {getattr(inbound, 'currency', 'N/A')}\n\n"
                f"💵  Общая цена : {total_price.quantize(Decimal('0.01'))} {getattr(outbound, 'currency', 'N/A')}\n"
            ) + "\n--------------------------\n"
        else:
            logger.warning(f"Не удалось отформатировать рейс, неизвестная структура: {flight}")
            return "Не удалось отобразить информацию о рейсе."
    except Exception as e:
        logger.error(f"Ошибка при форматировании деталей рейса: {e}. Данные рейса: {flight}")
        return "Ошибка отображения информации о рейсе."

def validate_date_format(date_str: str) -> datetime | None:
    """Проверяет, что строка даты соответствует формату YYYY-MM-DD и возвращает datetime объект."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return None

def validate_price(price_str: str) -> Decimal | None:
    """Проверяет, что строка является корректной ценой (положительное Decimal)."""
    try:
        price = Decimal(price_str).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        if price > 0:
            return price
        return None
    except InvalidOperation: # Ошибка преобразования в Decimal
        return None

async def clear_chat_keyboards(update: Update, context, num_messages=5):
    """Пытается удалить последние несколько сообщений бота, чтобы убрать старые клавиатуры."""
    if update.effective_chat and update.effective_message:
        chat_id = update.effective_chat.id
        message_id = update.effective_message.message_id
        for i in range(num_messages):
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=message_id - i)
            except Exception:
                # logger.debug(f"Не удалось удалить сообщение {message_id - i}: {e}")
                pass # Игнорируем ошибки, если сообщение уже удалено или не существует

def get_airport_iata(country_name: str, city_name: str) -> str | None:
    """Возвращает IATA код аэропорта по стране и городу."""
    return COUNTRIES_DATA.get(country_name, {}).get(city_name)