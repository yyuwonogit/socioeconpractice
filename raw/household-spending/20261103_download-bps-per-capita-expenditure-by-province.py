from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

import http.client
import json
import re
import time
import urllib.error
import urllib.request

# Parameters

# BPS WebAPI; the key sits in the URL path and is read from the repository .env file at run time
BASE = "https://webapi.bps.go.id/v1/api/"
ENV_FILE = ROOT / ".env"

# Static table 945: average monthly expenditure per capita on food, non-food and both (Jumlah), urban and
# rural combined, by province, in rupiah; one HTML table holds every year from 2011 to 2025
STATIC_PATH = "view/domain/0000/model/statictable/lang/ind/id/945/key/{key}/"
STATIC_ID = 945
STATIC_TITLE_END = "di Daerah Perkotaan dan Perdesaan Menurut Provinsi (rupiah), 2011-2025"

# The same series as a BPS statistics table (tablestatistic, type 3) that serves one year per request
# and names the Susenas round in its source line
TABLE3_PATH = ("view/domain/0000/model/tablestatistic/id/"
               "V1ZKMWVrSTNOek5ZZUZOcVZEZGFValJvV0hWalFUMDkjMyMwMDAw/lang/ind/key/{key}/")
TABLE3_TITLE = ("Rata-rata Pengeluaran per Kapita Sebulan Makanan dan Bukan Makanan di Daerah Perkotaan "
                "dan Perdesaan Menurut Provinsi")

# The table needs a year; this one exists, and its response lists every year the table offers
TABLE3_FIRST_YEAR = 2025

OUT_STATIC = HERE / "20261103_bps-per-capita-expenditure-by-province-2011-2025-static-table.json"
OUT_YEAR = HERE / "20261103_bps-per-capita-expenditure-by-province-{year}.json"

# Pause after each request and attempts per request, to keep the load on the WebAPI light
PAUSE = 1.5
ATTEMPTS = 4

# Functions

def read_key():
    """Return the WebAPI key from the BPS_API_KEY line of the repository .env file."""
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("BPS_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit(f"no BPS_API_KEY line in {ENV_FILE}")


def fetch(path, key, query=""):
    """GET a WebAPI path, where {key} marks the key, and return the body bytes, retrying on network errors.

    Messages show the path with {key} in place of the key, so the key never reaches the screen.
    """
    shown = path + (f"?{query}" if query else "")
    request = urllib.request.Request(BASE + shown.replace("{key}", key),
                                     headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    for attempt in range(1, ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                body = response.read()
            time.sleep(PAUSE)
            return body
        except urllib.error.HTTPError as error:
            if error.code != 429 and error.code < 500:
                raise SystemExit(f"HTTP {error.code} for {shown}") from None
            problem = f"HTTP {error.code}"
        except (OSError, http.client.HTTPException) as error:
            problem = type(error).__name__
        if attempt == ATTEMPTS:
            raise SystemExit(f"{problem} for {shown} after {ATTEMPTS} attempts") from None
        time.sleep(PAUSE * 4 * attempt)


def parse(body, key):
    """Stop if a response body contains the key, otherwise return it parsed as JSON."""
    text = body.decode("utf-8")
    if key in text:
        raise SystemExit("a response contains the API key, so it was not saved")
    return json.loads(text)


def save(path, body):
    """Write a response body byte for byte as received, never over a file already saved."""
    # A file in raw/ is never replaced; a revised release goes under a new date, from a copy of this script
    if path.exists():
        raise SystemExit(f"{path.name} already exists; copy this script under a new date to file a new release")
    path.write_bytes(body)
    print(f"{path.name}: {len(body)} bytes")


def letters(text):
    """Keep only the lower-case letters and digits of a title, since BPS titles vary in spaces and stray characters."""
    return re.sub(r"[^0-9a-z]", "", text.lower())


def table3(year, key):
    """Download one year of the statistics table, stop unless BPS served that year of that table, and return it."""
    body = fetch(TABLE3_PATH, key, f"year={year}")
    response = parse(body, key)
    assert response["status"] == "OK", f"statistics table not served for {year}"
    table = response["data"][1]
    assert table["tahun_data"] == year, f"asked for {year}, got {table['tahun_data']}"
    assert letters(table["judul_tabel"]).startswith(letters(TABLE3_TITLE)), "title changed: " + table["judul_tabel"]
    return body, table

# Steps

# Read the WebAPI key from .env
key = read_key()

# Download static table 945 with every year from 2011 to 2025
body = fetch(STATIC_PATH, key)
static = parse(body, key)

# Stop if BPS served an error or a table other than the one this file is named for
assert static["status"] == "OK" and static["data"]["table_id"] == STATIC_ID, "static table 945 not served"
assert static["data"]["title"].endswith(STATIC_TITLE_END), "static table title changed: " + static["data"]["title"]

# Save the static table exactly as received
save(OUT_STATIC, body)

# Download the first year of the statistics table, whose list_tahun_data names every year offered
first_body, first = table3(TABLE3_FIRST_YEAR, key)
years = sorted(first["list_tahun_data"])
print(f"statistics table years offered: {years}")

# Download every other offered year and save each year's response exactly as received
for year in years:
    body = first_body if year == TABLE3_FIRST_YEAR else table3(year, key)[0]
    save(OUT_YEAR.with_name(OUT_YEAR.name.format(year=year)), body)
