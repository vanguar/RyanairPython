# bot/message_formatter.py
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from telegram.helpers import escape_markdown

logger = logging.getLogger(__name__)

def _get_escaped_attr(obj: any, attr_name: str, default: str = 'N/A') -> str:
    """
    Вспомогательная функция для безопасного получения значения атрибута объекта 
    и его экранирования для MarkdownV2, если это строка.
    """
    val = getattr(obj, attr_name, default)
    if val is default and default == 'N/A': # Если значение по умолчанию и это 'N/A'
        return 'N/A' # Возвращаем как есть, без экранирования 'N/A'
    if isinstance(val, str):
        return escape_markdown(val, version=2)
    return escape_markdown(str(val), version=2) # Экранируем и другие типы после приведения к строке

def format_flight_details(flight: any) -> str:
    """
    Форматирует информацию о рейсе для вывода пользователю.
    Используется разделитель '────────✈️────────'.
    Менее строгая проверка атрибутов цены, как в оригинальной логике.
    """
    custom_separator = "────────✈️────────\n"

    try:
        # Проверяем сначала на рейс "туда-обратно", так как он имеет более специфичную структуру
        if hasattr(flight, 'outbound') and flight.outbound and hasattr(flight, 'inbound') and flight.inbound:
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
            out_currency_val = getattr(outbound, 'currency', 'EUR') # По умолчанию EUR, если не указано

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
            # Валюта для inbound обычно та же, что и для outbound
            
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
            
            # Используем _get_escaped_attr для значений, которые уже извлечены
            return (
                f"🔄 Рейс туда и обратно\n\n"
                f"➡️ Вылет туда:\n"
                f"  ✈️ Рейс: {_get_escaped_attr(None, '', default=out_flight_number_val)}\n"
                f"  🗺️ Маршрут: {_get_escaped_attr(None, '', default=out_origin_full_val)} → {_get_escaped_attr(None, '', default=out_destination_full_val)}\n"
                f"  🛫 Вылет: {escape_markdown(out_departure_time_str, version=2)}\n"
                f"  💶 Цена: {escape_markdown(out_price_str, version=2)} {_get_escaped_attr(None, '', default=out_currency_val)}\n\n"
                f"⬅️ Вылет обратно:\n"
                f"  ✈️ Рейс: {_get_escaped_attr(None, '', default=in_flight_number_val)}\n"
                f"  🗺️ Маршрут: {_get_escaped_attr(None, '', default=in_origin_full_val)} → {_get_escaped_attr(None, '', default=in_destination_full_val)}\n"
                f"  🛫 Вылет: {escape_markdown(in_departure_time_str, version=2)}\n"
                f"  💶 Цена: {escape_markdown(in_price_str, version=2)} {_get_escaped_attr(None, '', default=out_currency_val)}\n\n" # Используем валюту от outbound
                f"💵 Общая цена: {escape_markdown(total_price_str, version=2)} {_get_escaped_attr(None, '', default=out_currency_val)}\n"
                f"{custom_separator}"
            )

        # Проверяем на рейс "в одну сторону"
        elif hasattr(flight, 'price') and flight.price is not None:
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
            
            price_attr = getattr(flight, 'price', None) # Уже проверено, что не None
            price_str = "N/A"
            if price_attr is not None: # Дополнительная проверка для спокойствия
                try:
                    price_val = Decimal(str(price_attr)).quantize(Decimal('0.01'))
                    price_str = str(price_val)
                except InvalidOperation:
                    logger.warning(f"Invalid price format for one-way: {price_attr}")

            currency_val = getattr(flight, 'currency', 'EUR')

            return (
                f"✈️ Рейс: {_get_escaped_attr(None, '', default=flight_number_val)}\n"
                f"🗺️ Маршрут: {_get_escaped_attr(None, '', default=origin_full_val)} → {_get_escaped_attr(None, '', default=destination_full_val)}\n"
                f"🛫 Вылет: {escape_markdown(departure_time_str, version=2)}\n" 
                f"💶 Цена: {escape_markdown(price_str, version=2)} {_get_escaped_attr(None, '', default=currency_val)}\n"
                f"{custom_separator}"
            )
        else: # Если ни одно из условий не выполнилось (неизвестная структура)
            logger.warning(f"Не удалось отформатировать рейс, неизвестная структура или отсутствуют ключевые поля (price/outbound): {flight}")
            # Выводим больше информации об объекте flight для отладки
            flight_attrs = {attr: getattr(flight, attr, 'N/A') for attr in dir(flight) if not callable(getattr(flight, attr)) and not attr.startswith("__")}
            logger.debug(f"Атрибуты объекта flight, вызвавшего ошибку форматирования: {flight_attrs}")
            return escape_markdown("Не удалось отобразить информацию о рейсе (неизвестная структура).", version=2) + "\n"

    except Exception as e:
        logger.error(f"Критическая ошибка при форматировании деталей рейса: {e}. Данные рейса: {flight}", exc_info=True)
        # Выводим больше информации об объекте flight для отладки
        flight_attrs = {attr: getattr(flight, attr, 'N/A') for attr in dir(flight) if not callable(getattr(flight, attr)) and not attr.startswith("__")}
        logger.debug(f"Атрибуты объекта flight, вызвавшего критическую ошибку: {flight_attrs}")
        return escape_markdown("Произошла ошибка при отображении информации о рейсе.", version=2) + "\n"