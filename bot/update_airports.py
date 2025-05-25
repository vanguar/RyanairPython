#!/usr/bin/env python3
"""
update_airports.py

Downloads the latest airports.json and generates countries_data.json in the data/ directory.
Creates a backup of the old countries_data.json.
No translations – original names are preserved.
"""

import json
import pathlib
import requests
import sys

# URL to fetch the latest airport definitions
URL = "https://raw.githubusercontent.com/pcjedi/ryanair/master/airports.json"

# Paths relative to project root
ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RAW = DATA_DIR / "airports_raw.json"
OUT = DATA_DIR / "countries_data.json"
BACKUP = DATA_DIR / "countries_data.backup.json"


def main():
    # ensure data/ exists
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 1) Download latest airports.json
    try:
        response = requests.get(URL, timeout=30)
        response.raise_for_status()
        RAW.write_bytes(response.content)
        print(f"[download] saved {RAW.relative_to(ROOT)}")
    except Exception as e:
        print(f"[error] failed to download {URL}: {e}", file=sys.stderr)
        sys.exit(1)

    # 2) Parse JSON
    try:
        airports = json.loads(RAW.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[error] failed to read {RAW}: {e}", file=sys.stderr)
        sys.exit(1)

    # 3) Build mapping: { country: { city: IATA } }
    result: dict[str, dict[str, str]] = {}
    for airport in airports:
        country = airport["country"]["name"]
        city = airport["city"]["name"]
        code = airport["code"]
        result.setdefault(country, {})[city] = code

    # 4) Backup old file
    if OUT.exists():
        BACKUP.write_text(OUT.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"[backup] created {BACKUP.relative_to(ROOT)}")

    # 5) Write new file
    try:
        OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        total = sum(len(cities) for cities in result.values())
        print(f"[update] wrote {OUT.relative_to(ROOT)}: {total} airports")
    except Exception as e:
        print(f"[error] failed to write {OUT}: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()