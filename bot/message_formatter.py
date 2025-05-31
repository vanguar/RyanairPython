# bot/message_formatter.py
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from bot import weather_api # Убедитесь, что этот импорт есть

logger = logging.getLogger(__name__)

def _get_simple_attr(obj: any, attr_name: str, default: str = 'N/A') -> str:
    val = getattr(obj, attr_name, default)
    return str(val)

async def format_flight_details(flight: any, 
                                departure_city_name: str | None = None, 
                                arrival_city_name: str | None = None) -> str:
    flight_info_parts = []
    custom_separator = "────────✈️────────\n"
    weather_separator = "--------------------\n" # Разделитель для блока погоды

    try:
        # Блок 1: Формирование основной информации о рейсе
        # (Этот блок кода остается таким же, как в вашей последней рабочей версии,
        #  которая корректно отображала рейсы без погоды. Я не буду его здесь повторять,
        #  чтобы не загромождать ответ. Просто убедитесь, что он на месте и работает.)
        # --- Начало вашего рабочего кода для информации о рейсе ---
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
            flight_info_parts.append("Не удалось отобразить информацию о рейсе (неизвестная структура).\n")

        # Добавляем основной разделитель, если информация о рейсе была и это не сообщение об ошибке
        if flight_info_parts and flight_info_parts[-1] != "Не удалось отобразить информацию о рейсе (неизвестная структура).\n":
            flight_info_parts.append(f"\n{custom_separator}")
        # --- Конец вашего рабочего кода для информации о рейсе ---

        # Блок 2: Формирование информации о погоде
        weather_text_parts = []
        attempted_weather_fetch = False # Флаг, что мы пытались получить погоду хотя бы для одного релевантного города

        if departure_city_name and departure_city_name != 'N/A':
            attempted_weather_fetch = True
            logger.debug(f"Запрос погоды для города вылета: {departure_city_name}")
            dep_weather = await weather_api.get_weather_forecast(departure_city_name)
            if dep_weather:
                weather_text_parts.append(f"  В г. {dep_weather['city']}: {dep_weather['temperature']}°C {dep_weather['emoji']}")
            else:
                logger.info(f"Прогноз погоды для города вылета {departure_city_name} не получен.")
        
        # Запрашиваем погоду для города прилета, только если он указан и отличается от города вылета
        if arrival_city_name and arrival_city_name != 'N/A' and \
           (not departure_city_name or departure_city_name.lower() != arrival_city_name.lower()):
            attempted_weather_fetch = True
            logger.debug(f"Запрос погоды для города прилета: {arrival_city_name}")
            arr_weather = await weather_api.get_weather_forecast(arrival_city_name)
            if arr_weather:
                weather_text_parts.append(f"  В г. {arr_weather['city']}: {arr_weather['temperature']}°C {arr_weather['emoji']}")
            else:
                 logger.info(f"Прогноз погоды для города прилета {arrival_city_name} не получен.")
        elif arrival_city_name and arrival_city_name != 'N/A' and \
             departure_city_name and departure_city_name.lower() == arrival_city_name.lower() and weather_text_parts:
            # Если города совпадают и погода для вылета уже есть, считаем, что попытка была, но не дублируем
            attempted_weather_fetch = True


        if attempted_weather_fetch:
            flight_info_parts.append(f"{weather_separator}🌬️ Прогноз погоды:\n")
            if weather_text_parts:
                flight_info_parts.append("\n".join(weather_text_parts) + "\n")
            else:
                flight_info_parts.append("  В данный момент прогноз погоды недоступен.\n")
        
        return "".join(flight_info_parts)

    except Exception as e:
        logger.error(f"Критическая ошибка при форматировании деталей рейса (вкл. погоду): {e}. Данные рейса: {flight}", exc_info=True)
        return "Произошла ошибка при отображении информации о рейсе (вкл. погоду).\n"