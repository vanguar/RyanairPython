# bot/message_formatter.py
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from telegram.helpers import escape_markdown

logger = logging.getLogger(__name__)

def format_flight_details(flight: any) -> str:
    """
    Форматирует информацию о рейсе для вывода пользователю.
    Используется разделитель '────────✈️────────'.
    """
    # Ваш предпочтительный разделитель
    custom_separator = "────────✈️────────\n"

    try:
        if hasattr(flight, 'price') and flight.price is not None:  # Рейс в одну сторону
            departure_time_dt = flight.departureTime
            if isinstance(departure_time_dt, str):
                try:
                    departure_time_dt = datetime.fromisoformat(departure_time_dt.replace("Z", "+00:00"))
                except ValueError:
                    logger.warning(f"Could not parse date string: {flight.departureTime}")
            
            departure_time_str = departure_time_dt.strftime("%Y-%m-%d %H:%M") if isinstance(departure_time_dt, datetime) else str(flight.departureTime)
            
            flight_number = _get_escaped_attr(flight, 'flightNumber')
            origin_full = _get_escaped_attr(flight, 'originFull')
            destination_full = _get_escaped_attr(flight, 'destinationFull')
            
            try:
                price_val = Decimal(str(flight.price)).quantize(Decimal('0.01'))
                price_str = str(price_val)
            except InvalidOperation:
                price_str = "N/A"
            
            currency = _get_escaped_attr(flight, 'currency')

            return (
                f"✈️ Рейс: {flight_number}\n"
                f"🗺️ Маршрут: {origin_full} → {destination_full}\n"
                f"🛫 Вылет: {escape_markdown(departure_time_str, version=2)}\n" 
                f"💶 Цена: {escape_markdown(price_str, version=2)} {currency}\n"
                f"{custom_separator}" # Используем ваш разделитель
            )
            
        elif hasattr(flight, 'outbound') and flight.outbound and hasattr(flight.outbound, 'price') and \
             hasattr(flight, 'inbound') and flight.inbound and hasattr(flight.inbound, 'price'):  # Рейс туда и обратно
            
            outbound = flight.outbound
            inbound = flight.inbound

            # ... (код для получения и форматирования дат вылета outbound и inbound остается прежним) ...
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


            out_flight_number = _get_escaped_attr(outbound, 'flightNumber')
            out_origin_full = _get_escaped_attr(outbound, 'originFull')
            out_destination_full = _get_escaped_attr(outbound, 'destinationFull')
            out_currency = _get_escaped_attr(outbound, 'currency')
            
            try:
                out_price_val = Decimal(str(outbound.price)).quantize(Decimal('0.01'))
                out_price_str = str(out_price_val)
            except InvalidOperation:
                out_price_str = "N/A"
                out_price_val = None

            in_flight_number = _get_escaped_attr(inbound, 'flightNumber')
            in_origin_full = _get_escaped_attr(inbound, 'originFull')
            in_destination_full = _get_escaped_attr(inbound, 'destinationFull')
            
            try:
                in_price_val = Decimal(str(inbound.price)).quantize(Decimal('0.01'))
                in_price_str = str(in_price_val)
            except InvalidOperation:
                in_price_str = "N/A"
                in_price_val = None
            
            total_price_str = "N/A"
            if isinstance(out_price_val, Decimal) and isinstance(in_price_val, Decimal):
                total_price_val = (out_price_val + in_price_val).quantize(Decimal('0.01'))
                total_price_str = str(total_price_val)

            return (
                f"🔄 Рейс туда и обратно\n\n"
                f"➡️ Вылет туда:\n"
                f"  ✈️ Рейс: {out_flight_number}\n"
                f"  🗺️ Маршрут: {out_origin_full} → {out_destination_full}\n"
                f"  🛫 Вылет: {escape_markdown(out_departure_time_str, version=2)}\n"
                f"  💶 Цена: {escape_markdown(out_price_str, version=2)} {out_currency}\n\n"
                f"⬅️ Вылет обратно:\n"
                f"  ✈️ Рейс: {in_flight_number}\n"
                f"  🗺️ Маршрут: {in_origin_full} → {in_destination_full}\n"
                f"  🛫 Вылет: {escape_markdown(in_departure_time_str, version=2)}\n"
                f"  💶 Цена: {escape_markdown(in_price_str, version=2)} {out_currency}\n\n"
                f"💵 Общая цена: {escape_markdown(total_price_str, version=2)} {out_currency}\n"
                f"{custom_separator}" # Используем ваш разделитель
            )
        else:
            logger.warning(f"Не удалось отформатировать рейс, неизвестная структура: {flight}")
            return escape_markdown("Не удалось отобразить информацию о рейсе.", version=2) + "\n"
    except Exception as e:
        logger.error(f"Ошибка при форматировании деталей рейса: {e}. Данные рейса: {flight}", exc_info=True)
        return escape_markdown("Ошибка отображения информации о рейсе.", version=2) + "\n"