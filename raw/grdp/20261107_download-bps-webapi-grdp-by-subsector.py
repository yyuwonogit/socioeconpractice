from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

import json
import re
import time
import urllib.request

# Parameters

# BPS WebAPI; the key is read from the git-ignored .env file and never written to disk elsewhere
API = "https://webapi.bps.go.id/v1/api/list/model/{model}/lang/ind/domain/{domain}/var/{var}{extra}/key/{key}/"
KEY = re.search(r"^BPS_WEBAPI_KEY=(\w+)$", (ROOT / ".env").read_text(), re.M).group(1)

# Provincial GRDP tables that split mining and manufacturing into subsectors (coal, metal ores, basic metals).
# Found on 2026-11-07 by keyword search of each provincial domain and checked for those rows.
# domain -> (province, current-price var, constant-price var); one var means it holds both price bases.
TABLES = {
    "1200": ("Sumatera Utara", 778, 780),
    "1300": ("Sumatera Barat", 153, None),
    "1400": ("Riau", 419, 418),
    "1500": ("Jambi", 1976, 1977),
    "1600": ("Sumatera Selatan", 741, None),
    "1800": ("Lampung", 893, None),
    "1900": ("Kepulauan Bangka Belitung", 8, 32),
    "2100": ("Kepulauan Riau", 265, 268),
    "3200": ("Jawa Barat", 111, 113),
    "3300": ("Jawa Tengah", 2280, 2278),
    "3400": ("DI Yogyakarta", 268, None),
    "3500": ("Jawa Timur", 483, 473),
    "3600": ("Banten", 342, 343),
    "5100": ("Bali", 363, 365),
    "5200": ("Nusa Tenggara Barat", 352, 353),
    "6200": ("Kalimantan Tengah", 38, 437),
    "6300": ("Kalimantan Selatan", 322, None),
    "6400": ("Kalimantan Timur", 238, 239),
    "6500": ("Kalimantan Utara", 119, 120),
    "7100": ("Sulawesi Utara", 206, 1877),
    "7300": ("Sulawesi Selatan", 1744, None),
    "7400": ("Sulawesi Tenggara", 422, None),
    "7500": ("Gorontalo", 240, 241),
    "7600": ("Sulawesi Barat", 459, 456),
    "8200": ("Maluku Utara", 294, None),
    "9100": ("Papua Barat", 177, None),
    "9100b": ("Papua Barat Daya", 310, None),
}

# Years to fetch when the table has them
YEARS = range(2020, 2026)

OUT = HERE / "20261107_bps-webapi-grdp-by-subsector.jsonl"

# Pause between requests, in seconds
PAUSE = 0.4

# Functions

def get(model, domain, var, extra=""):
    """Call the WebAPI and return the parsed response and the request address without the key."""
    url = API.format(model=model, domain=domain, var=var, extra=extra, key=KEY)
    for attempt in range(1, 5):
        try:
            with urllib.request.urlopen(url, timeout=90) as response:
                body = json.loads(response.read())
            time.sleep(PAUSE)
            return body, url.replace(KEY, "KEY")
        except OSError:
            if attempt == 4:
                raise
            time.sleep(3 * attempt)


def year_ids(domain, var):
    """Return {year: th_id} for the years the table lists."""
    body, _ = get("th", domain, var)
    if body.get("data-availability") != "available":
        return {}
    return {int(r["th"]): r["th_id"] for r in body["data"][1]}

# Steps

# Fetch each table's year list and its data for each wanted year, writing one response per line as received
lines = 0
with open(OUT, "w", encoding="utf-8") as f:
    for key, (province, *vars_) in TABLES.items():
        domain = key[:4]
        for var in [v for v in vars_ if v]:
            ids = year_ids(domain, var)
            for year in [y for y in YEARS if y in ids]:
                body, url = get("data", domain, var, f"/th/{ids[year]}")
                # Stop if BPS returned a different table or year than requested
                assert body.get("data-availability") == "available", (province, var, year)
                assert str(body["var"][0]["val"]) == str(var), (province, var)
                f.write(json.dumps({"domain": domain, "province": province, "var": var, "year": year,
                                    "request": url, "response": body}, ensure_ascii=False) + "\n")
                lines += 1
            print(f"{province} var {var}: {sorted(y for y in YEARS if y in ids)}")
print(f"{OUT.name}: {lines} responses")
