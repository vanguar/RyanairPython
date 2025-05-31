# bot/message_formatter.py
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
# from bot import weather_api # Пока отключаем, если не используется больше нигде

logger = logging.getLogger(__name__)

def _get_simple_attr(obj: any, attr_name: str, default: str = 'N/A') -> str:
    val = getattr(obj, attr_name, default)
    return str(val)

# Убираем async и параметры departure_city_name, arrival_city_name из сигнатуры
def format_flight_details(flight: any) -> str:
    flight_info_parts = []
    custom_separator = "────────✈️────────\n"
    # weather_separator = "--------------------\n" # Пока не нужен

    try:
        # Блок 1: Формирование основной информации о рейсе (ваш рабочий код)
        if hasattr(flight, 'price') and flight.price is not None:  # Рейс в одну сторону
            departure_time_dt = getattr(flight, 'departureTime', None)
            if isinstance(departure_time_dt, str):
                try:
                    departure_time_dt = datetime.fromisoformat(departure_time_dt.replace("Z", "+00:00"))
                except ValueError:
                    logger.warning(f"Could not parse date string: {getattr(flight, 'departureTime', 'N/A')}")
            departure_time_str = departure_time_dt.strftime("%Y-%m-%d %H:%M") if isinstance(departure_time_dt, datetime) else str(getattr(flight, 'departureTime', 'N/A'))
            
            flight_number_val = _get_simple_attr(flight, 'flightNumber')
            origin_full_val = _get_simple_attr(flight, 'originFull')
            destination_full_val = _get_simple_attr(flight, 'destinationFull')
            
            price_attr = getattr(flight, 'price', None)
            price_str = "N/A"
            if price_attr is not None:
                try:
                    price_val_decimal = Decimal(str(price_attr)).quantize(Decimal('0.01'))
                    price_str = str(price_val_decimal)
                except InvalidOperation:
                    logger.warning(f"Invalid price format for one-way: {price_attr}")
            currency_val = _get_simple_attr(flight, 'currency', 'EUR')

            flight_info_parts.append(f"✈️ Рейс: {flight_number_val}\n")
            flight_info_parts.append(f"🗺️ Маршрут: {origin_full_val} → {destination_full_val}\n")
            flight_info_parts.append(f"🛫 Вылет: {departure_time_str}\n")
            flight_info_parts.append(f"💶 Цена: {price_str} {currency_val}\n")
        
        elif hasattr(flight, 'outbound') and flight.outbound and hasattr(flight, 'inbound') and flight.inbound:
            # ... (ваш существующий и работающий код для рейса "туда-обратно" без изменений) ...
            # Я скопирую его из вашего предыдущего рабочего варианта для полноты
            outbound = flight.outbound
            inbound = flight.inbound

            out_departure_time_dt = getattr(outbound, 'departureTime', None)
            if isinstance(out_departure_time_dt, str):
                try: out_departure_time_dt = datetime.fromisoformat(out_departure_time_dt.replace("Z", "+00:00"))
                except ValueError: logger.warning(f"Could not parse outbound date string: {getattr(outbound, 'departureTime', 'N/A')}")
            out_departure_time_str = out_departure_time_dt.strftime("%Y-%m-%d %H:%M") if isinstance(out_departure_time_dt, datetime) else str(getattr(outbound, 'departureTime', 'N/A'))

            in_departure_time_dt = getattr(inbound, 'departureTime', None)
            if isinstance(in_departure_time_dt, str):
                try: in_departure_time_dt = datetime.fromisoformat(in_departure_time_dt.replace("Z", "+00:00"))
                except ValueError: logger.warning(f"Could not parse inbound date string: {getattr(inbound, 'departureTime', 'N/A')}")
            in_departure_time_str = in_departure_time_dt.strftime("%Y-%m-%d %H:%M") if isinstance(in_departure_time_dt, datetime) else str(getattr(inbound, 'departureTime', 'N/A'))

            out_flight_number_val = _get_simple_attr(outbound, 'flightNumber')
            out_origin_full_val = _get_simple_attr(outbound, 'originFull') 
            out_destination_full_val = _get_simple_attr(outbound, 'destinationFull') 
            out_currency_val = _get_simple_attr(outbound, 'currency', 'EUR') 

            out_price_attr = getattr(outbound, 'price', None)
            out_price_str = "N/A"; out_price_val_decimal = None
            if out_price_attr is not None:
                try:
                    out_price_val_decimal = Decimal(str(out_price_attr)).quantize(Decimal('0.01'))
                    out_price_str = str(out_price_val_decimal)
                except InvalidOperation: logger.warning(f"Invalid price format for outbound: {out_price_attr}")

            in_flight_number_val = _get_simple_attr(inbound, 'flightNumber')
            in_origin_full_val = _get_simple_attr(inbound, 'originFull')
            in_destination_full_val = _get_simple_attr(inbound, 'destinationFull')
            
            in_price_attr = getattr(inbound, 'price', None)
            in_price_str = "N/A"; in_price_val_decimal = None
            if in_price_attr is not None:
                try:
                    in_price_val_decimal = Decimal(str(in_price_attr)).quantize(Decimal('0.01'))
                    in_price_str = str(in_price_val_decimal)
                except InvalidOperation: logger.warning(f"Invalid price format for inbound: {in_price_attr}")
            
            total_price_str = "N/A"
            if isinstance(out_price_val_decimal, Decimal) and isinstance(in_price_val_decimal, Decimal):
                total_price_val = (out_price_val_decimal + in_price_val_decimal).quantize(Decimal('0.01'))
                total_price_str = str(total_price_val)
            
            flight_info_parts.append(f"🔄 Рейс туда и обратно\n\n")
            flight_info_parts.append(f"➡️ Вылет туда:\n")
            flight_info_parts.append(f"  ✈️ Рейс: {out_flight_number_val}\n")
            flight_info_parts.append(f"  🗺️ Маршрут: {out_origin_full_val} → {out_destination_full_val}\n")
            flight_info_parts.append(f"  🛫 Вылет: {out_departure_time_str}\n")
            flight_info_parts.append(f"  💶 Цена: {out_price_str} {out_currency_val}\n\n")
            flight_info_parts.append(f"⬅️ Вылет обратно:\n")
            flight_info_parts.append(f"  ✈️ Рейс: {in_flight_number_val}\n")
            flight_info_parts.append(f"  🗺️ Маршрут: {in_origin_full_val} → {in_destination_full_val}\n")
            flight_info_parts.append(f"  🛫 Вылет: {in_departure_time_str}\n")
            flight_info_parts.append(f"  💶 Цена: {in_price_str} {out_currency_val}\n\n")
            flight_info_parts.append(f"💵 Общая цена: {total_price_str} {out_currency_val}\n")
        else: 
            logger.warning(f"Не удалось отформатировать рейс (основная часть), неизвестная структура: {flight}")
            # flight_attrs = {attr: getattr(flight, attr, 'N/A') for attr in dir(flight) if not callable(getattr(flight, attr)) and not attr.startswith("__")}
            # logger.debug(f"Атрибуты объекта flight (основная часть): {flight_attrs}")
            flight_info_parts.append("Не удалось отобразить информацию о рейсе (неизвестная структура).\n")

        # Добавляем основной разделитель, если информация о рейсе была
        if flight_info_parts and flight_info_parts[-1] != "Не удалось отобразить информацию о рейсе (неизвестная структура).\n":
            flight_info_parts.append(f"\n{custom_separator}")

        # ----- БЛОК ПОГОДЫ ПОКА ПОЛНОСТЬЮ ОТКЛЮЧЕН -----
        # weather_text_parts = []
        # attempted_dep_weather = False
        # attempted_arr_weather = False
        # ... (весь код, связанный с attempted_dep_weather, attempted_arr_weather, dep_weather, arr_weather, и вызовом weather_api.get_weather_forecast)
        # if attempted_dep_weather or attempted_arr_weather:
        #     flight_info_parts.append(f"{weather_separator}🌬️ Прогноз погоды:\n")
        #     if weather_text_parts: 
        #         flight_info_parts.append("\n".join(weather_text_parts) + "\n")
        #     else: 
        #         flight_info_parts.append("  В данный момент прогноз погоды недоступен.\n")
        
        return "".join(flight_info_parts)

    except Exception as e:
        logger.error(f"Критическая ошибка при форматировании деталей рейса: {e}. Данные рейса: {flight}", exc_info=True)
        # flight_attrs = {attr: getattr(flight, attr, 'N/A') for attr in dir(flight) if not callable(getattr(flight, attr)) and not attr.startswith("__")}
        # logger.debug(f"Атрибуты объекта flight (критическая ошибка): {flight_attrs}")
        return "Произошла ошибка при отображении информации о рейсе.\n" # Убрал "(вкл. погоду)"