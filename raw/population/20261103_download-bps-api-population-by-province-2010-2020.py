from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

import json
import time
import urllib.error
import urllib.request

# Parameters

# BPS WebAPI; the key is read from ROOT/.env at run time and never printed or saved
BASE = "https://webapi.bps.go.id/v1/api/"
ENV_FILE = ROOT / ".env"
KEY_NAME = "BPS_API_KEY"

# Years wanted; the WebAPI has no provincial population table with annual values for 2011-2014
YEARS = range(2010, 2021)

# Dynamic table 1886: population projection by province and sex (thousand), Proyeksi Penduduk Indonesia 2015-2045 hasil SUPAS 2015
VAR = 1886
PERIODS_PATH = "list/model/th/domain/0000/key/{key}/?var={var}&lang=ind"
DATA_PATH = "list/model/data/domain/0000/var/{var}/th/{th}/key/{key}/?lang=ind"

# The WebAPI refuses a th range of more than three years with HTTP 400
MAX_YEARS_PER_REQUEST = 3

# Static tables by id: 1274 is the SP2010-based projection by province for 2010, 2015, ... 2035 (thousand);
# 1267 is census and SUPAS counts by province for 1971-2010 (people)
STATIC_PATH = "view/domain/0000/model/statictable/lang/ind/id/{id}/key/{key}/"
STATIC_TABLES = {
    1274: "20261103_bps-api-static-table-1274-population-projection-by-province-2010-2035.json",
    1267: "20261103_bps-api-static-table-1267-population-census-by-province-1971-2010.json",
}

OUT_PERIODS = HERE / f"20261103_bps-api-var-{VAR}-periods.json"
OUT_DATA = HERE / f"20261103_bps-api-var-{VAR}-population-projection-by-province-{{first}}-{{last}}.json"

# Pause between requests to the WebAPI, in seconds
PAUSE = 1.5

# Functions

def read_key(path, name):
    """Return the value of name=value from the .env file."""
    for line in path.read_text(encoding="utf-8").splitlines():
        field, sep, value = line.partition("=")
        if sep and field.strip() == name:
            return value.strip()
    raise SystemExit(f"{name} is missing from {path.name}")


def fetch(path, key, attempts=4):
    """GET one WebAPI path and return the body bytes, retrying network and server errors with backoff.

    Error messages show the path with {key}, never the key itself.
    """
    url = BASE + path.replace("{key}", key)
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            # A client error such as 400 or 404 will not change on a retry
            if error.code < 500 or attempt == attempts:
                raise RuntimeError(f"HTTP {error.code} for {BASE + path}") from None
        except Exception as error:
            if attempt == attempts:
                raise RuntimeError(f"{type(error).__name__} for {BASE + path}") from None
        time.sleep(PAUSE * 4 * attempt)


def save(body, out, key):
    """Save a response byte for byte as received, unless it carries the key or the file already exists."""
    # A file in raw/ is never replaced; a revised release goes under a new date, from a copy of this script
    if out.exists():
        raise SystemExit(f"{out.name} already exists; copy this script under a new date to file a new release")
    # Never save a response that carries the key
    if key.encode("utf-8") in body:
        raise SystemExit(f"{out.name}: the response carries the key, so it is not saved")
    out.write_bytes(body)
    print(f"{out.name}: {len(body)} bytes")


def chunks(years, size):
    """Split a sorted list of years into runs of at most size consecutive years."""
    runs, run = [], []
    for year in years:
        if run and (year != run[-1] + 1 or len(run) == size):
            runs.append(run)
            run = []
        run.append(year)
    return runs + ([run] if run else [])

# Steps

# Read the key from the repository's .env file
key = read_key(ENV_FILE, KEY_NAME)

# Download the list of years that table 1886 holds
body = fetch(PERIODS_PATH.format(var=VAR, key="{key}"), key)
periods = json.loads(body)

# Stop unless the list came back complete on one page, then save it as received
assert periods["status"] == "OK", periods.get("status")
assert periods["data"][0]["pages"] == 1, "the period list runs to more than one page"
save(body, OUT_PERIODS, key)
held = {int(p["th"]): p["th_id"] for p in periods["data"][1]}

# Stop if a period id does not follow the WebAPI rule th = year - 1900
assert all(th == year - 1900 for year, th in held.items()), held

# Keep the years held inside the wanted range
wanted = sorted(y for y in held if y in YEARS)
print(f"var {VAR} holds {sorted(held)}; downloading {wanted}")
time.sleep(PAUSE)

# Download the wanted years in runs of at most three, and save each response as received
for run in chunks(wanted, MAX_YEARS_PER_REQUEST):
    th = f"{held[run[0]]}:{held[run[-1]]}" if len(run) > 1 else str(held[run[0]])
    body = fetch(DATA_PATH.format(var=VAR, th=th, key="{key}"), key)
    data = json.loads(body)
    # Stop unless the response is table 1886 and carries values for exactly the years asked for
    assert data["status"] == "OK" and data["var"][0]["val"] == VAR, data.get("status")
    assert [int(t["label"]) for t in data["tahun"]] == run, data["tahun"]
    assert len(data["datacontent"]) > 0, f"no values for {run}"
    save(body, OUT_DATA.with_name(OUT_DATA.name.format(first=run[0], last=run[-1])), key)
    time.sleep(PAUSE)

# Download the two static tables and save each response as received
for table_id, name in STATIC_TABLES.items():
    body = fetch(STATIC_PATH.format(id=table_id, key="{key}"), key)
    table = json.loads(body)
    # Stop unless the response is the requested table with an HTML table in it
    assert table["status"] == "OK" and table["data"]["table_id"] == table_id, table.get("status")
    assert "<table" in table["data"]["table"].lower(), f"static table {table_id} has no HTML table"
    save(body, HERE / name, key)
    time.sleep(PAUSE)
