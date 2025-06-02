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
# ПОЛНОСТЬЮ ИСПРАВЛЕННЫЙ МЕТОД find_flights_with_fallback
async def find_flights_with_fallback(
    departure_airport_iata: str,
    arrival_airport_iata: str | None,
    departure_date_str: str | None, # Используется для +/- offset ИЛИ если None -> годовой поиск
    max_price: Decimal | None,      # Изменено на Decimal | None для консистентности
    return_date_str: str | None = None, # Используется для +/- offset для обратного рейса
    is_one_way: bool = True,
    search_days_offset: int = 3,
    # НОВЫЕ ПАРАМЕТРЫ для явного указания диапазона
    explicit_departure_date_from: str | None = None,
    explicit_departure_date_to: str | None = None,
    explicit_return_date_from: str | None = None,
    explicit_return_date_to: str | None = None
):
    """
    Основная логика поиска рейсов.
    1. Если explicit_departure_date_from/_to указаны, ищет в этом точном диапазоне.
    2. Если departure_date_str указан (и explicit НЕТ), ищет на эту дату и +/- search_days_offset.
    3. Если departure_date_str is None (и explicit НЕТ), ищет на ближайший год.
    Возвращает словарь {дата_строка: [список_рейсов]} или пустой словарь.
    """
    all_flights_by_date = defaultdict(list)

    # --- Сценарий 1: Явный диапазон дат ---
    if explicit_departure_date_from and explicit_departure_date_to:
        logger.info(
            f"Поиск по ЯВНОМУ диапазону дат: {departure_airport_iata} -> {arrival_airport_iata or 'Любой'}, "
            f"Вылет: {explicit_departure_date_from} до {explicit_departure_date_to}"
        )
        
        api_call_return_date_from = None
        api_call_return_date_to = None
        if not is_one_way:
            if explicit_return_date_from and explicit_return_date_to:
                api_call_return_date_from = explicit_return_date_from
                api_call_return_date_to = explicit_return_date_to
                logger.info(f"Обратный рейс в диапазоне: {api_call_return_date_from} до {api_call_return_date_to}")
            else:
                # Если это рейс туда-обратно, но диапазон возврата не указан явно,
                # это может быть ошибкой в логике вызова или дизайном.
                # Ryanair API для get_cheapest_return_flights требует return_date_from/to.
                # Можно либо выбросить ошибку, либо установить широкий диапазон по умолчанию,
                # либо предположить, что это поиск только "туда" если return диапазон не задан.
                # Пока что, если is_one_way=False, но нет явного диапазона возврата, поиск будет как для "в одну сторону".
                # Это поведение должно быть согласовано с тем, как формируются параметры в launch_flight_search.
                # Если is_one_way=False, launch_flight_search должен был предоставить explicit_return_date_from/to.
                # Если нет, то это может быть недоработкой на вызывающей стороне.
                # Для безопасности, если is_one_way=False, но нет explicit_return_date_from/to,
                # лучше не вызывать get_cheapest_return_flights или указать на ошибку.
                # Однако, find_flights_api сам решает, какой метод Ryanair API вызывать.
                logger.warning(
                    "Для рейса туда-обратно с явным диапазоном вылета, диапазон возврата также должен быть указан. "
                    "Если explicit_return_date_from/to не заданы, поиск будет как для рейса в одну сторону или может завершиться ошибкой в find_flights_api."
                )


        flights_in_range = await find_flights_api(
            departure_airport_iata=departure_airport_iata,
            arrival_airport_iata=arrival_airport_iata,
            date_from_str=explicit_departure_date_from,
            date_to_str=explicit_departure_date_to,
            max_price=max_price,
            return_date_from_str=api_call_return_date_from, # Будет None если не указан или is_one_way
            return_date_to_str=api_call_return_date_to     # Будет None если не указан или is_one_way
        )
        
        if flights_in_range:
            logger.info(f"API (явный диапазон) вернул {len(flights_in_range)} рейсов. Группировка по датам...")
            for flight in flights_in_range:
                try:
                    departure_time_obj = None
                    if hasattr(flight, 'departureTime') and flight.departureTime: # one-way
                        departure_time_obj = flight.departureTime
                    elif hasattr(flight, 'outbound') and flight.outbound and hasattr(flight.outbound, 'departureTime'): # round-trip
                        departure_time_obj = flight.outbound.departureTime
                    
                    if departure_time_obj:
                        if isinstance(departure_time_obj, str):
                            # Убедимся, что строка корректно парсится в datetime
                            dt_parsed = datetime.fromisoformat(departure_time_obj.replace("Z", "+00:00"))
                            dep_date_key = dt_parsed.strftime("%Y-%m-%d")
                        elif isinstance(departure_time_obj, datetime):
                            dep_date_key = departure_time_obj.strftime("%Y-%m-%d")
                        else:
                            dep_date_key = "unknown_date_explicit_range"
                        all_flights_by_date[dep_date_key].append(flight)
                    else:
                        all_flights_by_date["unknown_time_explicit_range"].append(flight)
                except Exception as e_group:
                    logger.warning(f"Не удалось извлечь/сгруппировать дату из рейса при явном поиске по диапазону: {e_group}, рейс: {flight}")
                    all_flights_by_date["error_grouping_explicit_range"].append(flight)
        return dict(all_flights_by_date)

    # --- Сценарий 2: Указана одна дата вылета (для +/- search_days_offset) ---
    elif departure_date_str: # departure_date_str есть, а explicit_departure_date_from/to - нет
        logger.info(f"Поиск по одной дате (+/- {search_days_offset} дней): {departure_date_str}")
        base_departure_dt = datetime.strptime(departure_date_str, "%Y-%m-%d")
        base_return_dt = datetime.strptime(return_date_str, "%Y-%m-%d") if return_date_str and not is_one_way else None
        
        dates_to_check = []
        dates_to_check.append((base_departure_dt, base_return_dt)) # Основная дата
        
        for offset in range(1, search_days_offset + 1):
            # Даты ранее
            prev_dep_dt = base_departure_dt - timedelta(days=offset)
            if prev_dep_dt >= datetime.now().replace(hour=0, minute=0, second=0, microsecond=0): # Не ищем в прошлом
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
        
        dates_to_check.sort(key=lambda x: x[0] if x[0] else datetime.max) # Сортировка, учитывая None

        for dep_dt, ret_dt in dates_to_check:
            if not dep_dt: continue # Пропускаем, если дата вылета некорректна (маловероятно здесь)

            current_dep_date_str = dep_dt.strftime("%Y-%m-%d")
            current_ret_date_str = None
            if ret_dt and not is_one_way:
                 # Убедимся, что дата возврата не раньше даты вылета для этого конкретного запроса
                if dep_dt > ret_dt:
                    logger.warning(f"Для offset-поиска дата возврата {ret_dt} раньше даты вылета {dep_dt}. Пропуск этой пары.")
                    continue
                current_ret_date_str = ret_dt.strftime("%Y-%m-%d")

            logger.info(f"Поиск на дату (offset): {current_dep_date_str} (возврат: {current_ret_date_str or 'N/A'})")
            flights_on_date = await find_flights_api(
                departure_airport_iata=departure_airport_iata,
                arrival_airport_iata=arrival_airport_iata,
                date_from_str=current_dep_date_str, # Ищем на конкретный день
                date_to_str=current_dep_date_str,   # Ищем на конкретный день
                max_price=max_price,
                return_date_from_str=current_ret_date_str, # Ищем на конкретный день
                return_date_to_str=current_ret_date_str    # Ищем на конкретный день
            )
            if flights_on_date:
                all_flights_by_date[current_dep_date_str].extend(flights_on_date)
        
        return dict(all_flights_by_date)

    # --- Сценарий 3: Даты не указаны (поиск на год вперед) ---
    else: # departure_date_str is None, и explicit_departure_date_from/to также None
        logger.info("Поиск без указания конкретных дат (на ближайший год).")
        date_from_year_search = datetime.now().strftime("%Y-%m-%d")
        date_to_year_search = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d")
        
        return_date_from_year_search = None
        return_date_to_year_search = None
        if not is_one_way:
            # Для годового поиска туда-обратно, Ryanair API ожидает, что return_date_from/to
            # также будут определять окно для обратного рейса.
            # Можно сделать их такими же, как и для вылета, или немного сместить.
            # Для простоты, сделаем их такими же.
            return_date_from_year_search = date_from_year_search 
            return_date_to_year_search = date_to_year_search
            logger.info(f"Годовой поиск (туда-обратно): даты возврата также {return_date_from_year_search} - {return_date_to_year_search}")

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
            logger.info(f"API (годовой поиск) вернул {len(flights_for_year)} рейсов. Группировка по датам...")
            for flight in flights_for_year:
                try:
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
                            dep_date_key = "unknown_date_year_search"
                        all_flights_by_date[dep_date_key].append(flight)
                    else:
                        all_flights_by_date["unknown_time_year_search"].append(flight)
                except Exception as e:
                    logger.warning(f"Не удалось извлечь/сгруппировать дату из рейса при годовом поиске: {e}, рейс: {flight}")
                    all_flights_by_date["error_grouping_year_search"].append(flight)
            return dict(all_flights_by_date)
        return {} # Если flights_for_year пуст