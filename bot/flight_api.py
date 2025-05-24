# bot/flight_api.py
import logging
from datetime import datetime, timedelta
from ryanair import Ryanair #
from decimal import Decimal
from collections import defaultdict #MODIFIED: added defaultdict

logger = logging.getLogger(__name__)

# Инициализация API клиента один раз
try:
    ryanair_api = Ryanair() # Использует EUR по умолчанию #
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
            flights = ryanair_api.get_cheapest_return_flights( #
                source_airport=departure_airport_iata,
                date_from=date_from_str,
                date_to=date_to_str,
                destination_airport=arrival_airport_iata, # None если не указан
                return_date_from=return_date_from_str,
                return_date_to=return_date_to_str,
                max_price=float(max_price) if max_price is not None else None,
            )
        else:
            flights = ryanair_api.get_cheapest_flights( #
                airport=departure_airport_iata,
                date_from=date_from_str,
                date_to=date_to_str,
                destination_airport=arrival_airport_iata, # None если не указан #
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

# MODIFIED: Логика find_flights_with_fallback изменена для сбора рейсов по датам
async def find_flights_with_fallback(
    departure_airport_iata: str,
    arrival_airport_iata: str | None,
    departure_date_str: str | None, # Может быть None для гибкого поиска
    max_price: Decimal,
    return_date_str: str | None = None, # Может быть None
    is_one_way: bool = True,
    search_days_offset: int = 3 # MODIFIED: Уменьшил дефолтный offset для примера, можно вернуть 7
):
    """
    Основная логика поиска рейсов.
    Если departure_date_str указан, ищет на эту дату и +/- search_days_offset.
    Если departure_date_str is None, ищет на ближайший год (в диапазоне).
    Возвращает словарь {дата_строка: [список_рейсов]} или пустой словарь.
    """
    all_flights_by_date = defaultdict(list)

    if departure_date_str:
        base_departure_dt = datetime.strptime(departure_date_str, "%Y-%m-%d")
        base_return_dt = datetime.strptime(return_date_str, "%Y-%m-%d") if return_date_str and not is_one_way else None
        
        dates_to_check = []
        # Добавляем основную дату
        dates_to_check.append((
            base_departure_dt,
            base_return_dt
        ))
        # Добавляем даты со смещением
        for offset in range(1, search_days_offset + 1):
            # Даты ранее
            prev_dep_dt = base_departure_dt - timedelta(days=offset)
            if prev_dep_dt >= datetime.now(): # Не ищем в прошлом
                dates_to_check.append((
                    prev_dep_dt,
                    (base_return_dt - timedelta(days=offset)) if base_return_dt else None
                ))
            # Даты позднее
            next_dep_dt = base_departure_dt + timedelta(days=offset)
            dates_to_check.append((
                next_dep_dt,
                (base_return_dt + timedelta(days=offset)) if base_return_dt else None
            ))
        
        # Сортируем даты для последовательного запроса (опционально, но логично)
        dates_to_check.sort(key=lambda x: x[0])

        for dep_dt, ret_dt in dates_to_check:
            current_dep_date_str = dep_dt.strftime("%Y-%m-%d")
            current_ret_date_str = ret_dt.strftime("%Y-%m-%d") if ret_dt and not is_one_way else None

            logger.info(f"Поиск на дату: {current_dep_date_str} (возврат: {current_ret_date_str})")
            flights_on_date = await find_flights_api(
                departure_airport_iata=departure_airport_iata,
                arrival_airport_iata=arrival_airport_iata,
                date_from_str=current_dep_date_str,
                date_to_str=current_dep_date_str, # Ищем на конкретный день
                max_price=max_price,
                return_date_from_str=current_ret_date_str,
                return_date_to_str=current_ret_date_str # Ищем на конкретный день
            )
            if flights_on_date:
                all_flights_by_date[current_dep_date_str].extend(flights_on_date)
        
        return dict(all_flights_by_date)

    else: # Поиск без указания дат (на ближайший год)
        logger.info("Поиск без указания конкретных дат (на ближайший год).")
        # Для поиска на год Ryanair API может потребовать date_to быть значительно позже date_from
        date_from_year_search = datetime.now().strftime("%Y-%m-%d")
        date_to_year_search = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d")
        
        return_date_from_year_search = None
        return_date_to_year_search = None
        if not is_one_way:
            return_date_from_year_search = date_from_year_search 
            return_date_to_year_search = date_to_year_search

        # API может вернуть много рейсов, если диапазон большой.
        # Результат будет одним списком, а не сгруппированным по датам,
        # так как мы не итерируем по дням здесь.
        # Для консистентности вернем также в формате {дата: [рейсы]}
        # но здесь дата будет "период" или первая дата диапазона.
        # Либо, нужно будет обработать результат и сгруппировать его.
        # Пока упростим: для годового поиска вернем как есть, сгруппировав по дате вылета из ответа API.
        
        flights_for_year = await find_flights_api(
            departure_airport_iata=departure_airport_iata,
            arrival_airport_iata=arrival_airport_iata,
            date_from_str=date_from_year_search,
            date_to_str=date_to_year_search,
            max_price=max_price,
            return_date_from_str=return_date_from_year_search,
            return_date_to_str=return_date_to_year_search
        )
        
        if flights_for_year:
            for flight in flights_for_year:
                try:
                    # Пытаемся получить дату вылета из объекта рейса
                    # Для one-way это flight.departureTime, для round-trip это flight.outbound.departureTime
                    departure_time = None
                    if hasattr(flight, 'departureTime') and flight.departureTime:
                        departure_time = flight.departureTime
                    elif hasattr(flight, 'outbound') and flight.outbound and hasattr(flight.outbound, 'departureTime'):
                        departure_time = flight.outbound.departureTime
                    
                    if departure_time:
                        if isinstance(departure_time, str):
                            dep_date_key = datetime.fromisoformat(departure_time.replace("Z", "+00:00")).strftime("%Y-%m-%d")
                        elif isinstance(departure_time, datetime):
                            dep_date_key = departure_time.strftime("%Y-%m-%d")
                        else:
                            dep_date_key = "unknown_date" # fallback
                        all_flights_by_date[dep_date_key].append(flight)
                    else:
                        all_flights_by_date["unknown_date"].append(flight)
                except Exception as e:
                    logger.warning(f"Не удалось извлечь дату из рейса при годовом поиске: {e}")
                    all_flights_by_date["processing_error_date"].append(flight)
            return dict(all_flights_by_date)
        return {}