# bot/message_formatter.py
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
# Убираем from telegram.helpers import escape_markdown, если он больше нигде не нужен в этом файле

logger = logging.getLogger(__name__)

def _get_escaped_attr(obj: any, attr_name: str, default: str = 'N/A') -> str:
    """
    Вспомогательная функция для безопасного получения значения атрибута объекта.
    Экранирование удалено.
    """
    val = getattr(obj, attr_name, default)
    return str(val) # Просто приводим к строке

def format_flight_details(flight: any) -> str:
    """
    Форматирует информацию о рейсе для вывода пользователю.
    Экранирование Markdown удалено.
    Используется разделитель '────────✈️────────'.
    """
    custom_separator = "────────✈️────────\n"

    try:
        if hasattr(flight, 'price') and flight.price is not None:  # Рейс в одну сторону
            departure_time_dt = getattr(flight, 'departureTime', None)
            if isinstance(departure_time_dt, str):
                try:
                    departure_time_dt = datetime.fromisoformat(departure_time_dt.replace("Z", "+00:00"))
                except ValueError:
                    logger.warning(f"Could not parse date string: {getattr(flight, 'departureTime', 'N/A')}")
            
            departure_time_str = departure_time_dt.strftime("%Y-%m-%d %H:%M") if isinstance(departure_time_dt, datetime) else str(getattr(flight, 'departureTime', 'N/A'))
            
            flight_number_val = getattr(flight, 'flightNumber', 'N/A')
            origin_full_val = getattr(flight, 'originFull', 'N/A')
            destination_full_val = getattr(flight, 'destinationFull', 'N/A')
            
            price_attr = getattr(flight, 'price', None)
            price_str = "N/A"
            if price_attr is not None:
                try:
                    price_val = Decimal(str(price_attr)).quantize(Decimal('0.01'))
                    price_str = str(price_val)
                except InvalidOperation:
                    logger.warning(f"Invalid price format for one-way: {price_attr}")

            currency_val = getattr(flight, 'currency', 'EUR')

            return (
                f"✈️ Рейс: {flight_number_val}\n"
                f"🗺️ Маршрут: {origin_full_val} → {destination_full_val}\n"
                f"🛫 Вылет: {departure_time_str}\n" 
                f"💶 Цена: {price_str} {currency_val}\n"
                f"{custom_separator}"
            )
            
        elif hasattr(flight, 'outbound') and flight.outbound and hasattr(flight, 'inbound') and flight.inbound:
            outbound = flight.outbound
            inbound = flight.inbound

            out_departure_time_dt = getattr(outbound, 'departureTime', None)
            if isinstance(out_departure_time_dt, str):
                try: 
                    out_departure_time_dt = datetime.fromisoformat(out_departure_time_dt.replace("Z", "+00:00"))
                except ValueError: 
                    logger.warning(f"Could not parse outbound date string: {getattr(outbound, 'departureTime', 'N/A')}")
            out_departure_time_str = out_departure_time_dt.strftime("%Y-%m-%d %H:%M") if isinstance(out_departure_time_dt, datetime) else str(getattr(outbound, 'departureTime', 'N/A'))

            in_departure_time_dt = getattr(inbound, 'departureTime', None)
            if isinstance(in_departure_time_dt, str):
                try: 
                    in_departure_time_dt = datetime.fromisoformat(in_departure_time_dt.replace("Z", "+00:00"))
                except ValueError: 
                    logger.warning(f"Could not parse inbound date string: {getattr(inbound, 'departureTime', 'N/A')}")
            in_departure_time_str = in_departure_time_dt.strftime("%Y-%m-%d %H:%M") if isinstance(in_departure_time_dt, datetime) else str(getattr(inbound, 'departureTime', 'N/A'))

            out_flight_number_val = getattr(outbound, 'flightNumber', 'N/A')
            out_origin_full_val = getattr(outbound, 'originFull', 'N/A')
            out_destination_full_val = getattr(outbound, 'destinationFull', 'N/A')
            out_currency_val = getattr(outbound, 'currency', 'EUR') 

            out_price_attr = getattr(outbound, 'price', None)
            out_price_str = "N/A"
            out_price_val_decimal = None
            if out_price_attr is not None:
                try:
                    out_price_val_decimal = Decimal(str(out_price_attr)).quantize(Decimal('0.01'))
                    out_price_str = str(out_price_val_decimal)
                except InvalidOperation:
                    logger.warning(f"Invalid price format for outbound: {out_price_attr}")

            in_flight_number_val = getattr(inbound, 'flightNumber', 'N/A')
            in_origin_full_val = getattr(inbound, 'originFull', 'N/A')
            in_destination_full_val = getattr(inbound, 'destinationFull', 'N/A')
            
            in_price_attr = getattr(inbound, 'price', None)
            in_price_str = "N/A"
            in_price_val_decimal = None
            if in_price_attr is not None:
                try:
                    in_price_val_decimal = Decimal(str(in_price_attr)).quantize(Decimal('0.01'))
                    in_price_str = str(in_price_val_decimal)
                except InvalidOperation:
                    logger.warning(f"Invalid price format for inbound: {in_price_attr}")
            
            total_price_str = "N/A"
            if isinstance(out_price_val_decimal, Decimal) and isinstance(in_price_val_decimal, Decimal):
                total_price_val = (out_price_val_decimal + in_price_val_decimal).quantize(Decimal('0.01'))
                total_price_str = str(total_price_val)
            
            return (
                f"🔄 Рейс туда и обратно\n\n"
                f"➡️ Вылет туда:\n"
                f"  ✈️ Рейс: {out_flight_number_val}\n"
                f"  🗺️ Маршрут: {out_origin_full_val} → {out_destination_full_val}\n"
                f"  🛫 Вылет: {out_departure_time_str}\n"
                f"  💶 Цена: {out_price_str} {out_currency_val}\n\n"
                f"⬅️ Вылет обратно:\n"
                f"  ✈️ Рейс: {in_flight_number_val}\n"
                f"  🗺️ Маршрут: {in_origin_full_val} → {in_destination_full_val}\n"
                f"  🛫 Вылет: {in_departure_time_str}\n"
                f"  💶 Цена: {in_price_str} {out_currency_val}\n\n" # Используем валюту от outbound
                f"💵 Общая цена: {total_price_str} {out_currency_val}\n"
                f"{custom_separator}"
            )
        else: 
            logger.warning(f"Не удалось отформатировать рейс, неизвестная структура или отсутствуют ключевые поля (price/outbound): {flight}")
            flight_attrs = {attr: getattr(flight, attr, 'N/A') for attr in dir(flight) if not callable(getattr(flight, attr)) and not attr.startswith("__")}
            logger.debug(f"Атрибуты объекта flight, вызвавшего ошибку форматирования: {flight_attrs}")
            return "Не удалось отобразить информацию о рейсе (неизвестная структура).\n" # Убрал escape_markdown

    except Exception as e:
        logger.error(f"Критическая ошибка при форматировании деталей рейса: {e}. Данные рейса: {flight}", exc_info=True)
        flight_attrs = {attr: getattr(flight, attr, 'N/A') for attr in dir(flight) if not callable(getattr(flight, attr)) and not attr.startswith("__")}
        logger.debug(f"Атрибуты объекта flight, вызвавшего критическую ошибку: {flight_attrs}")
        return "Произошла ошибка при отображении информации о рейсе.\n" # Убрал escape_markdown