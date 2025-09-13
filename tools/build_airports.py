# tools/build_airports.py
import json, pathlib

# читаем сырой JSON, сохранённый из браузера в data/airports_raw.json
src = pathlib.Path("data/airports_raw.json")
raw = json.load(open(src, encoding="utf-8"))

# ответ может быть списком или {"airports": [...]}
airports = raw.get("airports") if isinstance(raw, dict) else raw

by_code, countries = {}, {}

for a in airports:
    code = (a.get("iataCode") or a.get("code") or "").strip().upper()
    city = (
        a.get("cityName")
        or (a.get("city") or {}).get("name")
        or a.get("city")
        or (a.get("macCity") or {}).get("name")
    )
    country = (
        a.get("countryName")
        or (a.get("country") or {}).get("name")
        or a.get("country")
    )
    if code and city:
        by_code[code] = {"city": {"name": city}}
    if code and city and country:
        countries.setdefault(country, {})[city] = code

# пишем файлы в тех местах/форматах, где их ждёт бот
pathlib.Path("bot").mkdir(parents=True, exist_ok=True)
json.dump(by_code, open("bot/airports_raw.json","w",encoding="utf-8"), ensure_ascii=False, indent=2)
pathlib.Path("data").mkdir(parents=True, exist_ok=True)
json.dump(countries, open("data/countries_data.json","w",encoding="utf-8"), ensure_ascii=False, indent=2)

print(f"OK: {len(by_code)} airports; {len(countries)} countries")
