# bot/flight_api.py
import logging
from datetime import datetime, timedelta
from ryanair import Ryanair
from decimal import Decimal

logger = logging.getLogger(__name__)

# Инициализация API клиента один раз
try:
    ryanair_api = Ryanair() # Использует EUR по умолчанию
except Exception as e:
    logger.critical(f"Не удалось инициализировать Ryanair API: {e}")
    ryanair_api = None # Устанавливаем в None, чтобы проверки ниже сработали

async def find_flights_api(
    departure_airport_iata: str,
    arrival_airport_iata: str | None, # Может быть None для поиска "в любом направлении"
    date_from_str: str, # YYYY-MM-DD
    date_to_str: str,   # YYYY-MM-DD
    max_price: Decimal | None,
    return_date_from_str: str | None = None, # YYYY-MM-DD, для рейсов туда-обратно
    return_date_to_str: str | None = None    # YYYY-MM-DD, для рейсов туда-обратно
):
    """
    Ищет рейсы через API Ryanair.
    Возвращает список найденных рейсов или пустой список в случае ошибки/отсутствия рейсов.
    """
    if not ryanair_api:
        logger.error("Ryanair API клиент не инициализирован.")
        return []

    try:
        logger.info(
            f"Поиск API: {departure_airport_iata} -> {arrival_airport_iata or 'Любой'}, "
            f"Даты: {date_from_str}-{date_to_str}, Макс.цена: {max_price}"
        )
        if return_date_from_str and return_date_to_str:
            logger.info(f"Обратные даты: {return_date_from_str}-{return_date_to_str}")
            flights = ryanair_api.get_cheapest_return_flights(
                source_airport=departure_airport_iata,
                date_from=date_from_str,
                date_to=date_to_str,
                destination_airport=arrival_airport_iata, # None если не указан
                return_date_from=return_date_from_str,
                return_date_to=return_date_to_str,
                max_price=float(max_price) if max_price is not None else None,
                # custom_params={'market': 'ru-ru'} # Пример для локализации, если API поддерживает
            )
        else:
            flights = ryanair_api.get_cheapest_flights(
                airport=departure_airport_iata,
                date_from=date_from_str,
                date_to=date_to_str,
                destination_airport=arrival_airport_iata, # None если не указан
                max_price=float(max_price) if max_price is not None else None,
            )
        
        logger.info(f"API вернул {len(flights) if flights else 0} рейсов.")
        return flights if flights else []
    
    except Exception as e:
        logger.error(f"Ошибка при запросе к Ryanair API: {e}")
        logger.error(
            f"Параметры запроса: dep={departure_airport_iata}, arr={arrival_airport_iata}, "
            f"date_from={date_from_str}, date_to={date_to_str}, ret_from={return_date_from_str}, "
            f"ret_to={return_date_to_str}, price={max_price}"
        )
        return []

async def find_flights_with_fallback(
    departure_airport_iata: str,
    arrival_airport_iata: str | None,
    departure_date_str: str | None, # Может быть None для гибкого поиска
    max_price: Decimal,
    return_date_str: str | None = None, # Может быть None
    is_one_way: bool = True,
    search_days_offset: int = 7 # Для поиска +/- N дней
):
    """
    Основная логика поиска рейсов, включая поиск на ближайшие даты, если на точную дату ничего нет.
    Если departure_date_str is None, ищет на ближайший год.
    """
    flights_found = []

    # 1. Поиск на указанную дату (если она есть)
    if departure_date_str:
        current_departure_date_from = departure_date_str
        current_departure_date_to = departure_date_str
        current_return_date_from = return_date_str if return_date_str and not is_one_way else None
        current_return_date_to = return_date_str if return_date_str and not is_one_way else None

        logger.info(f"Первичный поиск на дату: {current_departure_date_from} (возврат: {current_return_date_from})")
        flights_found = await find_flights_api(
            departure_airport_iata=departure_airport_iata,
            arrival_airport_iata=arrival_airport_iata,
            date_from_str=current_departure_date_from,
            date_to_str=current_departure_date_to,
            max_price=max_price,
            return_date_from_str=current_return_date_from,
            return_date_to_str=current_return_date_to
        )
        if flights_found:
            return flights_found

        # 2. Поиск на +/- N дней (если на точную дату не найдено и дата была указана)
        logger.info(f"Рейсы на {departure_date_str} не найдены. Поиск на +/- {search_days_offset} дней.")
        base_departure_dt = datetime.strptime(departure_date_str, "%Y-%m-%d")
        base_return_dt = datetime.strptime(return_date_str, "%Y-%m-%d") if return_date_str and not is_one_way else None

        for offset in range(1, search_days_offset + 1):
            # Даты ранее
            prev_dep_dt = base_departure_dt - timedelta(days=offset)
            if prev_dep_dt >= datetime.now(): # Не ищем в прошлом
                prev_dep_str = prev_dep_dt.strftime("%Y-%m-%d")
                prev_ret_str = (base_return_dt - timedelta(days=offset)).strftime("%Y-%m-%d") if base_return_dt else None
                
                logger.debug(f"Поиск со смещением -{offset}: {prev_dep_str} (возврат: {prev_ret_str})")
                flights_found = await find_flights_api(departure_airport_iata, arrival_airport_iata, prev_dep_str, prev_dep_str, max_price, prev_ret_str, prev_ret_str)
                if flights_found: return flights_found

            # Даты позднее
            next_dep_dt = base_departure_dt + timedelta(days=offset)
            next_dep_str = next_dep_dt.strftime("%Y-%m-%d")
            next_ret_str = (base_return_dt + timedelta(days=offset)).strftime("%Y-%m-%d") if base_return_dt else None

            logger.debug(f"Поиск со смещением +{offset}: {next_dep_str} (возврат: {next_ret_str})")
            flights_found = await find_flights_api(departure_airport_iata, arrival_airport_iata, next_dep_str, next_dep_str, max_price, next_ret_str, next_ret_str)
            if flights_found: return flights_found
        
        logger.info(f"Рейсы на +/- {search_days_offset} дней не найдены.")
        return [] # Возвращаем пустой список, если и на ближайшие даты ничего нет

    # 3. Поиск без указания дат (на ближайший год)
    else:
        logger.info("Поиск без указания конкретных дат (на ближайший год).")
        date_from_year_search = datetime.now().strftime("%Y-%m-%d")
        date_to_year_search = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d")
        
        return_date_from_year_search = None
        return_date_to_year_search = None
        if not is_one_way:
            # Для обратных рейсов также ищем в течение года, начиная с сегодняшнего дня
            # Ryanair API может потребовать, чтобы return_date_from был не раньше date_from
            return_date_from_year_search = date_from_year_search 
            return_date_to_year_search = date_to_year_search

        flights_found = await find_flights_api(
            departure_airport_iata=departure_airport_iata,
            arrival_airport_iata=arrival_airport_iata,
            date_from_str=date_from_year_search,
            date_to_str=date_to_year_search, # API может искать по всему диапазону
            max_price=max_price,
            return_date_from_str=return_date_from_year_search,
            return_date_to_str=return_date_to_year_search
        )
        return flights_found