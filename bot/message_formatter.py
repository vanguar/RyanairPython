# bot/message_formatter.py
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from bot import weather_api

logger = logging.getLogger(__name__)

def _get_simple_attr(obj: any, attr_name: str, default: str = 'N/A') -> str:
    val = getattr(obj, attr_name, default)
    return str(val)

async def format_flight_details(flight: any, 
                                departure_city_name: str | None = None, 
                                arrival_city_name: str | None = None) -> str:
    flight_info_parts = []
    custom_separator = "────────✈️────────\n"
    weather_separator = "--------------------\n"

    logger.debug(f"Начало форматирования для объекта flight: {type(flight)}")
    if flight is None:
        logger.error("format_flight_details вызван с flight=None")
        return "Ошибка: переданы неверные данные для форматирования рейса.\n"

    try:
        # Погода ДО основного блока
        dep_city_for_weather = departure_city_name
        arr_city_for_weather = arrival_city_name

        if not dep_city_for_weather:
            origin_source = None
            if hasattr(flight, 'outbound') and flight.outbound: origin_source = flight.outbound
            elif hasattr(flight, 'origin'): origin_source = flight
            if origin_source:
                origin_val = _get_simple_attr(origin_source, 'origin', '')
                dep_city_for_weather = origin_val.split(',')[0].strip() if ',' in origin_val else origin_val

        if not arr_city_for_weather:
            destination_source = None
            if hasattr(flight, 'outbound') and flight.outbound: destination_source = flight.outbound
            elif hasattr(flight, 'inbound') and flight.inbound: destination_source = flight.inbound
            elif hasattr(flight, 'destination'): destination_source = flight
            if destination_source:
                dest_val = _get_simple_attr(destination_source, 'destination', '')
                arr_city_for_weather = dest_val.split(',')[0].strip() if ',' in dest_val else dest_val

        weather_text_parts = []
        attempted_dep_weather = False
        attempted_arr_weather = False

        if dep_city_for_weather and dep_city_for_weather != 'N/A':
            attempted_dep_weather = True
            logger.debug(f"Запрос погоды для города вылета: {dep_city_for_weather}")
            dep_weather = await weather_api.get_weather_forecast(dep_city_for_weather)
            if dep_weather:
                weather_text_parts.append(f"  В г. {dep_weather['city']}: {dep_weather['temperature']}°C {dep_weather['emoji']}")
            else:
                logger.info(f"Прогноз погоды для города вылета {dep_city_for_weather} не получен.")

        if arr_city_for_weather and arr_city_for_weather != 'N/A':
            attempted_arr_weather = True
            logger.debug(f"Запрос погоды для города прилета: {arr_city_for_weather}")
            arr_weather = await weather_api.get_weather_forecast(arr_city_for_weather)
            if arr_weather:
                weather_text_parts.append(f"  В г. {arr_weather['city']}: {arr_weather['temperature']}°C {arr_weather['emoji']}")
            else:
                logger.info(f"Прогноз погоды для города прилета {arr_city_for_weather} не получен.")

        if attempted_dep_weather or attempted_arr_weather:
            flight_info_parts.append(f"{weather_separator}🌬️ Прогноз погоды:\n")
            if weather_text_parts:
                flight_info_parts.append("\n".join(weather_text_parts) + "\n")
            else:
                flight_info_parts.append("  В данный момент прогноз погоды недоступен.\n")

        # Основной блок
        if hasattr(flight, 'price') and flight.price is not None:
            departure_time_val = getattr(flight, 'departureTime', None)
            departure_time_str = str(departure_time_val)
            if isinstance(departure_time_val, str):
                try:
                    dt_obj = datetime.fromisoformat(departure_time_val.replace("Z", "+00:00"))
                    departure_time_str = dt_obj.strftime("%Y-%m-%d %H:%M")
                except ValueError:
                    logger.warning(f"Could not parse date string: {departure_time_val}")
            elif isinstance(departure_time_val, datetime):
                departure_time_str = departure_time_val.strftime("%Y-%m-%d %H:%M")

            flight_number_val = _get_simple_attr(flight, 'flightNumber')
            origin_full_val = _get_simple_attr(flight, 'originFull')
            destination_full_val = _get_simple_attr(flight, 'destinationFull')

            price_attr = getattr(flight, 'price', None)
            price_str = "N/A"
            if price_attr is not None:
                try:
                    price_val_decimal = Decimal(str(price_attr)).quantize(Decimal('0.01'))
                    price_str = str(price_val_decimal)
                except (InvalidOperation, ValueError) as e_price:
                    logger.warning(f"Invalid price format for one-way: {price_attr}, error: {e_price}")
            currency_val = _get_simple_attr(flight, 'currency', 'EUR')

            flight_info_parts.append(f"✈️ Рейс: {flight_number_val}\n")
            flight_info_parts.append(f"🗺️ Маршрут: {origin_full_val} → {destination_full_val}\n")
            flight_info_parts.append(f"🛫 Вылет: {departure_time_str}\n")
            flight_info_parts.append(f"💶 Цена: {price_str} {currency_val}\n")

        elif hasattr(flight, 'outbound') and flight.outbound and hasattr(flight, 'inbound') and flight.inbound:
            outbound = flight.outbound
            inbound = flight.inbound

            out_departure_time_val = getattr(outbound, 'departureTime', None)
            out_departure_time_str = str(out_departure_time_val)
            if isinstance(out_departure_time_val, str):
                try:
                    dt_obj = datetime.fromisoformat(out_departure_time_val.replace("Z", "+00:00"))
                    out_departure_time_str = dt_obj.strftime("%Y-%m-%d %H:%M")
                except ValueError:
                    logger.warning(f"Could not parse outbound date string: {out_departure_time_val}")
            elif isinstance(out_departure_time_val, datetime):
                out_departure_time_str = out_departure_time_val.strftime("%Y-%m-%d %H:%M")

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
                except (InvalidOperation, ValueError) as e_price:
                    logger.warning(f"Invalid price format for outbound: {out_price_attr}, error: {e_price}")

            in_departure_time_val = getattr(inbound, 'departureTime', None)
            in_departure_time_str = str(in_departure_time_val)
            if isinstance(in_departure_time_val, str):
                try:
                    dt_obj = datetime.fromisoformat(in_departure_time_val.replace("Z", "+00:00"))
                    in_departure_time_str = dt_obj.strftime("%Y-%m-%d %H:%M")
                except ValueError:
                    logger.warning(f"Could not parse inbound date string: {in_departure_time_val}")
            elif isinstance(in_departure_time_val, datetime):
                in_departure_time_str = in_departure_time_val.strftime("%Y-%m-%d %H:%M")

            in_flight_number_val = _get_simple_attr(inbound, 'flightNumber')
            in_origin_full_val = _get_simple_attr(inbound, 'originFull')
            in_destination_full_val = _get_simple_attr(inbound, 'destinationFull')

            in_price_attr = getattr(inbound, 'price', None)
            in_price_str = "N/A"; in_price_val_decimal = None
            if in_price_attr is not None:
                try:
                    in_price_val_decimal = Decimal(str(in_price_attr)).quantize(Decimal('0.01'))
                    in_price_str = str(in_price_val_decimal)
                except (InvalidOperation, ValueError) as e_price:
                    logger.warning(f"Invalid price format for inbound: {in_price_attr}, error: {e_price}")

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
            logger.warning(f"Не удалось отформатировать рейс (основная часть), неизвестная структура: {flight}.")
            flight_info_parts.append("Не удалось отобразить информацию о рейсе (неизвестная структура).\n")

        if flight_info_parts and flight_info_parts[-1] != "Не удалось отобразить информацию о рейсе (неизвестная структура).\n":
            flight_info_parts.append(f"\n{custom_separator}")

        return "".join(flight_info_parts)

    except Exception as e:
        logger.error(f"Критическая ошибка при форматировании деталей рейса (вкл. погоду): {e}. Данные рейса: {type(flight)}", exc_info=True)
        return "Произошла ошибка при отображении информации о рейсе (вкл. погоду).\n"