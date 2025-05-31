# bot/message_formatter.py
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from bot import weather_api # Импортируем модуль погоды

logger = logging.getLogger(__name__)

def _get_simple_attr(obj: any, attr_name: str, default: str = 'N/A') -> str:
    """
    Вспомогательная функция для безопасного получения значения атрибута объекта как строки.
    """
    val = getattr(obj, attr_name, default)
    return str(val)

async def format_flight_details(flight: any, 
                                departure_city_name: str | None = None, 
                                arrival_city_name: str | None = None) -> str:
    """
    Форматирует информацию о рейсе и добавляет прогноз погоды.
    Если прогноз недоступен, выводит соответствующее сообщение.
    """
    flight_info_parts = []
    custom_separator = "────────✈️────────\n"
    weather_separator = "--------------------\n"

    try:
        # Блок 1: Формирование основной информации о рейсе
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
            flight_attrs = {attr: getattr(flight, attr, 'N/A') for attr in dir(flight) if not callable(getattr(flight, attr)) and not attr.startswith("__")}
            logger.debug(f"Атрибуты объекта flight (основная часть): {flight_attrs}")
            flight_info_parts.append("Не удалось отобразить информацию о рейсе (неизвестная структура).\n")

        if flight_info_parts and flight_info_parts[-1] != "Не удалось отобразить информацию о рейсе (неизвестная структура).\n":
            flight_info_parts.append(f"\n{custom_separator}")

        # Блок 2: Формирование информации о погоде
        dep_city_for_weather = departure_city_name
        arr_city_for_weather = arrival_city_name

        if not dep_city_for_weather: # Пытаемся извлечь, если не передано
            origin_source = None
            if hasattr(flight, 'outbound') and flight.outbound: origin_source = flight.outbound
            elif hasattr(flight, 'origin'): origin_source = flight
            
            if origin_source:
                origin_val = _get_simple_attr(origin_source, 'origin', '')
                dep_city_for_weather = origin_val.split(',')[0].strip() if ',' in origin_val else origin_val
        
        if not arr_city_for_weather: # Пытаемся извлечь, если не передано
            destination_source = None
            if hasattr(flight, 'outbound') and flight.outbound: destination_source = flight.outbound # Для round-trip берем из плеча "туда"
            elif hasattr(flight, 'inbound') and flight.inbound: destination_source = flight.inbound # Если вдруг outbound нет, но есть inbound (маловероятно)
            elif hasattr(flight, 'destination'): destination_source = flight # Для one-way
            
            if destination_source:
                dest_val = _get_simple_attr(destination_source, 'destination', '')
                arr_city_for_weather = dest_val.split(',')[0].strip() if ',' in dest_val else dest_val
        
        weather_text_parts = []
        attempted_dep_weather = False
        attempted_arr_weather = False

        if dep_city_for_weather and dep_city_for_weather != 'N/A':
            attempted_dep_weather = True
            dep_weather = await weather_api.get_weather_forecast(dep_city_for_weather)
            if dep_weather:
                weather_text_parts.append(f"  В г. {dep_weather['city']}: {dep_weather['temperature']}°C {dep_weather['emoji']}")
        
        # Запрашиваем погоду для города прилета, только если он отличается от города вылета 
        # (и если мы его смогли определить)
        if arr_city_for_weather and arr_city_for_weather != 'N/A' and \
           (not dep_city_for_weather or dep_city_for_weather.lower() != arr_city_for_weather.lower()):
            attempted_arr_weather = True
            arr_weather = await weather_api.get_weather_forecast(arr_city_for_weather)
            if arr_weather:
                weather_text_parts.append(f"  В г. {arr_weather['city']}: {arr_weather['temperature']}°C {arr_weather['emoji']}")
        elif arr_city_for_weather and arr_city_for_weather != 'N/A' and dep_city_for_weather and dep_city_for_weather.lower() == arr_city_for_weather.lower() and weather_text_parts:
            # Если города совпадают и погода для города вылета уже есть, не дублируем, но считаем, что попытка была
            attempted_arr_weather = True 


        # Добавляем блок погоды, если мы пытались получить погоду хотя бы для одного города
        if attempted_dep_weather or attempted_arr_weather:
            flight_info_parts.append(f"{weather_separator}🌬️ Прогноз погоды:\n")
            if weather_text_parts: # Если есть хотя бы один успешный прогноз
                flight_info_parts.append("\n".join(weather_text_parts) + "\n")
            else: # Если пытались, но не получили ни одного прогноза
                flight_info_parts.append("  В данный момент прогноз погоды недоступен.\n")
        
        return "".join(flight_info_parts)

    except Exception as e:
        logger.error(f"Критическая ошибка при форматировании деталей рейса (вкл. погоду): {e}. Данные рейса: {flight}", exc_info=True)
        flight_attrs = {attr: getattr(flight, attr, 'N/A') for attr in dir(flight) if not callable(getattr(flight, attr)) and not attr.startswith("__")}
        logger.debug(f"Атрибуты объекта flight (критическая ошибка): {flight_attrs}")
        return "Произошла ошибка при отображении информации о рейсе (вкл. погоду).\n"