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
    arrival_airport_iata: str | None,
    date_from_str: str, # YYYY-MM-DD
    date_to_str: str,   # YYYY-MM-DD
    max_price: Decimal | None,
    return_date_from_str: str | None = None, # YYYY-MM-DD, для рейсов туда-обратно
    return_date_to_str: str | None = None    # YYYY-MM-DD, для рейсов туда-обратно
):
    """
    Ищет рейсы через API Ryanair и затем фильтрует их строго по заданным диапазонам дат.
    Возвращает список найденных и отфильтрованных рейсов или пустой список.
    """
    if not ryanair_api:
        logger.error("Ryanair API клиент не инициализирован.")
        return []

    raw_flights = [] # Список для "сырых" результатов от API
    try:
        logger.info(
            f"Запрос к API Ryanair: {departure_airport_iata} -> {arrival_airport_iata or 'Любой'}, "
            f"Даты вылета: {date_from_str}-{date_to_str}, Макс.цена: {max_price}"
        )
        if return_date_from_str and return_date_to_str:
            logger.info(f"Даты возврата для API: {return_date_from_str}-{return_date_to_str}")
            # Запрос рейсов туда-обратно
            raw_flights = ryanair_api.get_cheapest_return_flights(
                source_airport=departure_airport_iata,
                date_from=date_from_str,
                date_to=date_to_str,
                destination_airport=arrival_airport_iata,
                return_date_from=return_date_from_str,
                return_date_to=return_date_to_str,
                max_price=float(max_price) if max_price is not None else None,
            )
        else:
            # Запрос рейсов в одну сторону
            raw_flights = ryanair_api.get_cheapest_flights(
                airport=departure_airport_iata,
                date_from=date_from_str,
                date_to=date_to_str,
                destination_airport=arrival_airport_iata,
                max_price=float(max_price) if max_price is not None else None,
            )
        
        logger.info(f"API Ryanair вернул {len(raw_flights) if raw_flights else 0} рейсов (до внутренней фильтрации).")

    except Exception as e:
        logger.error(f"Ошибка при запросе к Ryanair API: {e}", exc_info=True) # Добавлено exc_info=True для полного стека ошибки
        logger.error(
            f"Параметры запроса: dep={departure_airport_iata}, arr={arrival_airport_iata}, "
            f"date_from={date_from_str}, date_to={date_to_str}, ret_from={return_date_from_str}, "
            f"ret_to={return_date_to_str}, price={max_price}"
        )
        return []

    # --- НАЧАЛО БЛОКА ПОСТ-ФИЛЬТРАЦИИ РЕЙСОВ ПО ДАТАМ ---
    if not raw_flights: # Если API ничего не вернул или список пуст
        return []

    try:
        # Преобразуем строки дат окна вылета в объекты date для сравнения
        dep_window_start_date = datetime.strptime(date_from_str, "%Y-%m-%d").date()
        dep_window_end_date = datetime.strptime(date_to_str, "%Y-%m-%d").date()
    except ValueError:
        logger.error(f"Некорректный формат дат для окна вылета при фильтрации: {date_from_str} - {date_to_str}")
        return [] # Не можем фильтровать, если даты окна некорректны

    ret_window_start_date = None
    ret_window_end_date = None
    # Проверяем, был ли это поиск туда-обратно (для которого нужны даты возврата)
    is_round_trip_search_intended = bool(return_date_from_str and return_date_to_str)
    
    if is_round_trip_search_intended:
        try:
            # Преобразуем строки дат окна возврата в объекты date
            ret_window_start_date = datetime.strptime(return_date_from_str, "%Y-%m-%d").date()
            ret_window_end_date = datetime.strptime(return_date_to_str, "%Y-%m-%d").date()
        except ValueError:
            logger.error(f"Некорректный формат дат для окна возврата при фильтрации: {return_date_from_str} - {return_date_to_str}")
            return [] # Не можем фильтровать, если даты окна возврата некорректны

    filtered_flights = []
    for flight_obj in raw_flights:
        try:
            outbound_flight_part = None
            # Определяем, какая часть объекта рейса содержит информацию о вылете "туда"
            # Это зависит от того, возвращает ли API для round-trip один объект с 'outbound'/'inbound'
            # или это всегда объекты типа one-way flight.
            # Предполагаем, что flight_obj может быть либо one-way, либо round-trip с полями outbound/inbound.
            if hasattr(flight_obj, 'outbound') and flight_obj.outbound and hasattr(flight_obj.outbound, 'departureTime'):
                outbound_flight_part = flight_obj.outbound
            elif hasattr(flight_obj, 'departureTime'): # Для рейсов в одну сторону или если get_cheapest_return_flights возвращает список отдельных рейсов
                outbound_flight_part = flight_obj
            
            if not outbound_flight_part:
                logger.warning(f"Не удалось извлечь информацию о вылете (туда) из объекта рейса: {type(flight_obj)}")
                continue

            out_dep_time_attr = outbound_flight_part.departureTime
            out_actual_departure_date = None # Фактическая дата вылета "туда"

            if isinstance(out_dep_time_attr, str):
                out_actual_departure_date = datetime.fromisoformat(out_dep_time_attr.replace("Z", "+00:00")).date()
            elif isinstance(out_dep_time_attr, datetime):
                out_actual_departure_date = out_dep_time_attr.date()
            else:
                logger.warning(f"Неизвестный тип времени вылета (туда) '{type(out_dep_time_attr)}' у рейса.")
                continue
            
            # Фильтруем по дате вылета "туда"
            if not (dep_window_start_date <= out_actual_departure_date <= dep_window_end_date):
                # logger.debug(f"Рейс отфильтрован (туда): {out_actual_departure_date} не в [{dep_window_start_date}, {dep_window_end_date}]")
                continue 

            # Если это поиск туда-обратно, проверяем и фильтруем дату вылета "обратно"
            if is_round_trip_search_intended:
                # Убедимся, что данные для обратного рейса существуют и корректны
                if not (hasattr(flight_obj, 'inbound') and flight_obj.inbound and hasattr(flight_obj.inbound, 'departureTime')):
                    logger.warning(f"Поиск туда-обратно, но отсутствуют или неполны данные о рейсе обратно в объекте: {type(flight_obj)}")
                    continue # Пропускаем этот рейс, так как он неполный для туда-обратно

                inbound_flight_part = flight_obj.inbound
                in_dep_time_attr = inbound_flight_part.departureTime
                in_actual_departure_date = None # Фактическая дата вылета "обратно"

                if isinstance(in_dep_time_attr, str):
                    in_actual_departure_date = datetime.fromisoformat(in_dep_time_attr.replace("Z", "+00:00")).date()
                elif isinstance(in_dep_time_attr, datetime):
                    in_actual_departure_date = in_dep_time_attr.date()
                else:
                    logger.warning(f"Неизвестный тип времени вылета (обратно) '{type(in_dep_time_attr)}' у рейса.")
                    continue
                
                # Фильтруем по дате вылета "обратно"
                # ret_window_start_date и ret_window_end_date должны быть определены, если is_round_trip_search_intended is True
                if not (ret_window_start_date and ret_window_end_date and \
                        ret_window_start_date <= in_actual_departure_date <= ret_window_end_date):
                    # logger.debug(f"Рейс отфильтрован (обратно): {in_actual_departure_date} не в [{ret_window_start_date}, {ret_window_end_date}]")
                    continue
            
            # Если все проверки пройдены, добавляем рейс в отфильтрованный список
            filtered_flights.append(flight_obj)

        except Exception as filter_exc:
            logger.warning(f"Ошибка при фильтрации отдельного рейса: {filter_exc}. Рейс: {flight_obj}", exc_info=True)
            continue # Пропускаем рейс, который не удалось обработать

    final_count = len(filtered_flights)
    if len(raw_flights) != final_count:
        logger.info(f"Внутренняя фильтрация дат API: Исходно {len(raw_flights)} рейсов, после фильтрации {final_count} рейсов (Dep: {date_from_str}-{date_to_str}, Ret: {return_date_from_str or 'N/A'}-{return_date_to_str or 'N/A'})")
    
    return filtered_flights
    # --- КОНЕЦ БЛОКА ПОСТ-ФИЛЬТРАЦИИ РЕЙСОВ ПО ДАТАМ ---

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
    
# ---------------------------------------------------------------------------
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ TOP-3
# ---------------------------------------------------------------------------

def find_country_by_airport(airport_iata: str) -> str:
    """Возвращает название страны по IATA-коду аэропорта (или '' если не найден)."""
    for country, cities in config.COUNTRIES_DATA.items():
        if airport_iata in cities.values():
            return country
    return ""

# ---------------------------------------------------------------------------
# TOP-3
# ---------------------------------------------------------------------------
async def get_cheapest_flights_top3(search_params: dict, limit: int = 3) -> list[dict]:
    """
    Возвращает list из 'limit' самых дешёвых рейсов.
    Берём пул через find_flights_with_fallback() → плоский список → сортируем.
    """
    flights_by_date = await find_flights_with_fallback(
        departure_airport_iata = search_params.get("departure_airport_iata"),
        arrival_airport_iata   = search_params.get("arrival_airport_iata"),
        departure_date_str     = search_params.get("departure_date_str"),
        return_date_str        = search_params.get("return_date_str"),
        is_one_way             = search_params.get("is_one_way", True),
        max_price              = search_params.get("max_price"),
        search_days_offset     = search_params.get("search_days_offset", 3),
    )

    if not flights_by_date:
        return []

    flat = []
    for flights in flights_by_date.values():
        for f in flights:
            price = helpers.get_flight_price(f)
            if price is not None:
                flat.append((price, f))

    if not flat:
        return []

    flat.sort(key=lambda x: x[0])
    top = flat[:limit]

    res = []
    for price, flight in top:
        dep_iata = getattr(flight, "origin", "")[-3:]
        arr_iata = getattr(flight, "destination", "")[-3:]
        res.append({
            "price": price,
            "flight": flight,
            "departure_country": find_country_by_airport(dep_iata),
            "arrival_country":   find_country_by_airport(arr_iata),
            # остальные поля handlers_top3 использует по желанию
        })
    return res

# ---------------------------------------------------------------------------
# TOP-3: агрегируем рейсы из пула аэропортов и берём общую тройку
# ---------------------------------------------------------------------------
from decimal import Decimal
from . import helpers, config

async def get_cheapest_flights_top3(search_params: dict, limit: int = 3) -> list[dict]:
    """
    • Если указан departure_airport_iata – ищем из него.
    • Если None и в user_data есть 'airport_pool' – перебираем первые 5 аэропортов этого пула.
    • Иначе берём список config.POPULAR_DEPARTURE_AIRPORTS.

    Возвращаем список словарей:
        {"price": Decimal, "flight": FlightObj,
         "departure_country": str, "arrival_country": str}
    """
    dep_iata = search_params.get("departure_airport_iata")
    airport_pool = ([dep_iata] if dep_iata
                    else search_params.get("airport_pool",
                                           config.POPULAR_DEPARTURE_AIRPORTS)[:5])

    flat: list[tuple[Decimal, object, str]] = []

    for dep in airport_pool:
        try:
            flights_by_date = await find_flights_with_fallback(
                departure_airport_iata = dep,
                arrival_airport_iata   = search_params.get("arrival_airport_iata"),
                departure_date_str     = search_params.get("departure_date_str"),
                return_date_str        = search_params.get("return_date_str"),
                is_one_way             = search_params.get("is_one_way", True),
                max_price              = search_params.get("max_price"),
                search_days_offset     = search_params.get("search_days_offset", 3),
            )
        except Exception as e:
            logger.warning(f"Ryanair API error for {dep}: {e}")
            continue

        for flights in flights_by_date.values():
            for fl in flights:
                price = helpers.get_flight_price(fl)
                if price is not None and price != Decimal('inf'):
                    flat.append((price, fl, dep))

    if not flat:
        return []

    # сортируем и берём TOP-N
    flat.sort(key=lambda x: x[0])
    top = flat[:limit]

    res = []
    for price, fl, dep in top:
        arr_iata = getattr(fl, "destination", "")[-3:]
        res.append({
            "price": price,                 # ← ключ, который потом используется в handlers_top3
            "flight": fl,
            "departure_country": find_country_by_airport(dep),
            "arrival_country":   find_country_by_airport(arr_iata),
        })
    return res



