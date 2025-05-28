# bot/helpers.py
import logging
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Dict, List, Any, Union # Добавляем Union для PriceChoice в user_data, если он будет здесь использоваться
from collections import defaultdict

from .config import COUNTRIES_DATA # Загрузка COUNTRIES_DATA если она тут используется

logger = logging.getLogger(__name__)

def format_flight_details(flight: Any) -> str: #
    """Форматирует информацию о рейсе для вывода пользователю."""
    try:
        if hasattr(flight, 'price') and flight.price is not None: # Рейс в одну сторону #
            departure_time_dt = flight.departureTime #
            if isinstance(departure_time_dt, str): #
                try:
                    departure_time_dt = datetime.fromisoformat(departure_time_dt.replace("Z", "+00:00")) #
                except ValueError: #
                    logger.warning(f"Could not parse date string: {flight.departureTime}") #
            
            departure_time_str = departure_time_dt.strftime("%Y-%m-%d %H:%M") if isinstance(departure_time_dt, datetime) else str(flight.departureTime) #

            return ( #
                f"✈️ *Рейс*: {getattr(flight, 'flightNumber', 'N/A')}\n"
                f"📍 *Маршрут*: {getattr(flight, 'originFull', 'N/A')} -> {getattr(flight, 'destinationFull', 'N/A')}\n"
                f"🕒 *Вылет*: {departure_time_str}\n"
                f"💰 *Цена*: {Decimal(str(flight.price)).quantize(Decimal('0.01'))} {getattr(flight, 'currency', 'N/A')}\n" #
            ) + "\n──────── ✈️ ────────\n"
        elif hasattr(flight, 'outbound') and flight.outbound and hasattr(flight.outbound, 'price') and \
             hasattr(flight, 'inbound') and flight.inbound and hasattr(flight.inbound, 'price'): # Рейс туда и обратно #
            
            outbound = flight.outbound #
            inbound = flight.inbound #

            out_departure_time_dt = outbound.departureTime #
            if isinstance(out_departure_time_dt, str): #
                try:
                    out_departure_time_dt = datetime.fromisoformat(out_departure_time_dt.replace("Z", "+00:00")) #
                except ValueError: #
                     logger.warning(f"Could not parse outbound date string: {outbound.departureTime}") #

            out_departure_time_str = out_departure_time_dt.strftime("%Y-%m-%d %H:%M") if isinstance(out_departure_time_dt, datetime) else str(outbound.departureTime) #

            in_departure_time_dt = inbound.departureTime #
            if isinstance(in_departure_time_dt, str): #
                try:
                    in_departure_time_dt = datetime.fromisoformat(in_departure_time_dt.replace("Z", "+00:00")) #
                except ValueError: #
                    logger.warning(f"Could not parse inbound date string: {inbound.departureTime}") #
            
            in_departure_time_str = in_departure_time_dt.strftime("%Y-%m-%d %H:%M") if isinstance(in_departure_time_dt, datetime) else str(inbound.departureTime) #

            total_price = Decimal(str(outbound.price)) + Decimal(str(inbound.price)) #
            return ( #
                f"🔄 *Рейс туда и обратно*\n\n"
                f"➡️ *Вылет туда*:\n"
                f"  - *Рейс*: {getattr(outbound, 'flightNumber', 'N/A')}\n"
                f"  - *Маршрут*: {getattr(outbound, 'originFull', 'N/A')} -> {getattr(outbound, 'destinationFull', 'N/A')}\n"
                f"  - *Вылет*: {out_departure_time_str}\n"
                f"  - *Цена*: {Decimal(str(outbound.price)).quantize(Decimal('0.01'))} {getattr(outbound, 'currency', 'N/A')}\n\n" #
                f"⬅️ *Вылет обратно*:\n"
                f"  - *Рейс*: {getattr(inbound, 'flightNumber', 'N/A')}\n"
                f"  - *Маршрут*: {getattr(inbound, 'originFull', 'N/A')} -> {getattr(inbound, 'destinationFull', 'N/A')}\n"
                f"  - *Вылет*: {in_departure_time_str}\n"
                f"  - *Цена*: {Decimal(str(inbound.price)).quantize(Decimal('0.01'))} {getattr(inbound, 'currency', 'N/A')}\n\n" #
                f"💵 *Общая цена*: {total_price.quantize(Decimal('0.01'))} {getattr(outbound, 'currency', 'N/A')}\n" #
            ) + "\n──────── ✈️ ────────\n"
        else:
            logger.warning(f"Не удалось отформатировать рейс, неизвестная структура: {flight}") #
            return "Не удалось отобразить информацию о рейсе." #
    except Exception as e:
        logger.error(f"Ошибка при форматировании деталей рейса: {e}. Данные рейса: {flight}") #
        return "Ошибка отображения информации о рейсе." #

def validate_date_format(date_str: str) -> Union[datetime, None]: #
    """Проверяет, что строка даты соответствует формату YYYY-MM-DD и возвращает datetime объект."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d") #
    except ValueError: #
        return None #

def validate_price(price_str: str) -> Union[Decimal, None]: #
    """Проверяет, что строка является корректной ценой (положительное Decimal)."""
    try:
        price = Decimal(price_str).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) #
        if price > 0: #
            return price #
        return None #
    except InvalidOperation: # Ошибка преобразования в Decimal #
        return None #

def get_airport_iata(country_name: str, city_name: str) -> Union[str, None]: #
    """Возвращает IATA код аэропорта по стране и городу."""
    return COUNTRIES_DATA.get(country_name, {}).get(city_name) #

# НОВАЯ ФУНКЦИЯ
def filter_cheapest_flights(all_flights_data: Dict[str, List[Any]]) -> Dict[str, List[Any]]:
    """
    Фильтрует словарь рейсов, оставляя только те, что имеют минимальную цену.

    Args:
        all_flights_data: Словарь, где ключи - строки с датами ('YYYY-MM-DD'),
                          а значения - списки объектов рейсов.
                          Объекты рейсов должны иметь атрибут 'price' (для one-way)
                          или 'outbound.price' и 'inbound.price' (для round-trip).

    Returns:
        Словарь того же формата, содержащий только рейсы с минимальной найденной ценой.
        Возвращает пустой словарь, если входной словарь пуст или не найдено рейсов с валидной ценой.
    """
    if not all_flights_data:
        return {}

    min_overall_price = Decimal('inf')

    # Первый проход: найти абсолютную минимальную цену
    for flights_on_date in all_flights_data.values():
        for flight in flights_on_date:
            current_flight_price = Decimal('inf')
            if hasattr(flight, 'price') and flight.price is not None:
                try: current_flight_price = Decimal(str(flight.price))
                except InvalidOperation: continue
            elif hasattr(flight, 'outbound') and flight.outbound and hasattr(flight.outbound, 'price'):
                try:
                    current_flight_price = Decimal(str(flight.outbound.price))
                    if hasattr(flight, 'inbound') and flight.inbound and hasattr(flight.inbound, 'price'):
                        current_flight_price += Decimal(str(flight.inbound.price))
                except InvalidOperation: continue
            
            if current_flight_price < min_overall_price:
                min_overall_price = current_flight_price
    
    if min_overall_price == Decimal('inf'):
        return {}

    cheapest_flights_result: Dict[str, List[Any]] = defaultdict(list)
    # Второй проход: собрать все рейсы, соответствующие этой минимальной цене
    for date_str, flights_on_date in all_flights_data.items():
        for flight in flights_on_date:
            current_flight_price = Decimal('inf')
            if hasattr(flight, 'price') and flight.price is not None:
                try: current_flight_price = Decimal(str(flight.price))
                except InvalidOperation: continue
            elif hasattr(flight, 'outbound') and flight.outbound and hasattr(flight.outbound, 'price'):
                try:
                    current_flight_price = Decimal(str(flight.outbound.price))
                    if hasattr(flight, 'inbound') and flight.inbound and hasattr(flight.inbound, 'price'):
                        current_flight_price += Decimal(str(flight.inbound.price))
                except InvalidOperation: continue

            if current_flight_price == min_overall_price:
                cheapest_flights_result[date_str].append(flight)
                
    return dict(cheapest_flights_result)

def get_flight_price(flight: Any) -> Decimal:
    """
    Извлекает общую цену из объекта рейса для сравнения.
    Возвращает Decimal('inf'), если цена не может быть определена.
    """
    price_str = None
    if hasattr(flight, 'price') and getattr(flight, 'price') is not None: # В одну сторону
        price_str = getattr(flight, 'price')
    elif hasattr(flight, 'outbound') and getattr(flight, 'outbound') and \
         hasattr(flight.outbound, 'price') and getattr(flight.outbound, 'price') is not None: # Туда-обратно
        
        outbound_price_str = getattr(flight.outbound, 'price')
        try:
            current_total_price = Decimal(str(outbound_price_str))
            if hasattr(flight, 'inbound') and getattr(flight, 'inbound') and \
               hasattr(flight.inbound, 'price') and getattr(flight.inbound, 'price') is not None:
                inbound_price_str = getattr(flight.inbound, 'price')
                current_total_price += Decimal(str(inbound_price_str))
            return current_total_price
        except InvalidOperation:
            logger.warning(f"Не удалось преобразовать цену рейса в Decimal: outbound='{outbound_price_str}', inbound='{getattr(flight.inbound, 'price', None)}'")
            return Decimal('inf')
    
    if price_str is not None:
        try:
            return Decimal(str(price_str))
        except InvalidOperation:
            logger.warning(f"Не удалось преобразовать цену рейса в Decimal: '{price_str}'")
            return Decimal('inf')
            
    logger.warning(f"Не удалось извлечь цену из объекта рейса: {flight}")
    return Decimal('inf')