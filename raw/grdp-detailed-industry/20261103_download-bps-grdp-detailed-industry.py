from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

import json
import sys
import time
import urllib.error
import urllib.request

# Parameters

# BPS WebAPI; every path below ends in /key/<key>, and the key is read from ROOT/.env at run time
BASE = "https://webapi.bps.go.id/v1/api/"

# SIMDASI (Yearbook Dataset) services: 26 lists the 7-digit MFD province codes, 23 lists the
# yearbook tables of one area, and 25 returns one table for one area and one year
PROVINCE_LIST = "interoperabilitas/datasource/simdasi/id/26"
TABLE_LIST = "interoperabilitas/datasource/simdasi/id/23/wilayah/{wilayah}"
TABLE = "interoperabilitas/datasource/simdasi/id/25/wilayah/{wilayah}/tahun/{year}/id_tabel/{table}"

# Yearbook table 13.1.1, "Produk Domestik Regional Bruto Atas Dasar Harga Berlaku Menurut Lapangan
# Usaha di Provinsi <X> (miliar rupiah)": 17 categories with sub-categories, including
# "Pertambangan Batubara dan Lignit" under B; every province publishes it under this one id
TABLE_ID = "S1RMUWRYb0NWc0Y5L05QQkxzcWw3Zz09"
YEARS = [2025, 2024]

# Province whose table list is saved to show where the table id comes from (Kalimantan Timur)
LIST_PROVINCE = "64"

# The 38 provinces and their BPS codes
PROVINCES = ROOT / "raw" / "province-codes" / "20261102_bps-province-codes-2025-s1.json"

# Seconds to wait after each request, and attempts per request for network or server errors
PAUSE = 1.5
ATTEMPTS = 4

# Output files, saved beside this script
OUT_PROVINCES = HERE / "20261103_bps-simdasi-province-codes.json"
OUT_TABLES = HERE / f"20261103_bps-simdasi-tables-{LIST_PROVINCE}.json"
OUT_TABLE = "20261103_bps-grdp-current-prices-detailed-industry-{code}-{year}.json"

# Functions

def read_key():
    """Return the BPS WebAPI key from the BPS_API_KEY line of ROOT/.env."""
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("BPS_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("no BPS_API_KEY line in .env")


def fetch(path, key):
    """Download one WebAPI path and return (HTTP status, body bytes).

    Network errors, HTTP 429 and HTTP 5xx are retried with a growing wait; other HTTP errors
    are returned with their body. Messages name the path only, never the URL with the key.
    """
    request = urllib.request.Request(f"{BASE}{path}/key/{key}", headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(1, ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                result = (response.status, response.read())
        except urllib.error.HTTPError as error:
            result = (error.code, error.read())
            if error.code != 429 and error.code < 500:
                break
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            result = None
            print(f"  {path}: attempt {attempt} failed ({type(error).__name__})")
        else:
            break
        # Wait longer after each failed attempt before trying again
        if attempt < ATTEMPTS:
            time.sleep(PAUSE * 2 ** attempt)
    # Keep the load on the server light
    time.sleep(PAUSE)
    if result is None:
        raise SystemExit(f"{path}: no response after {ATTEMPTS} attempts")
    return result


def save(body, out, key):
    """Write a response exactly as received, unless it contains the key or the file already exists."""
    # A file in raw/ is never replaced; a revised release goes under a new date, from a copy of this script
    if out.exists():
        raise SystemExit(f"{out.name} already exists; copy this script under a new date to file a new release")
    if key.encode("utf-8") in body:
        print(f"  {out.name}: response contains the API key, so it was not saved")
        return False
    out.write_bytes(body)
    return True


def table_problem(status, body, year):
    """Return why a response is not a usable table for the year, or None when it is one."""
    if status != 200:
        return f"HTTP {status}"
    try:
        reply = json.loads(body.decode("utf-8"))
        table = reply["data"][1]
        rows = table["data"]
    except (ValueError, KeyError, IndexError, TypeError):
        # A missing year answers status OK with an error object inside data[1]
        return "no table in the response"
    if reply.get("status") != "OK" or not isinstance(rows, list):
        return "no table in the response"
    if table.get("tahun_data") != year:
        return f"tahun_data is {table.get('tahun_data')}"
    # An empty shell lists the row labels with no values
    if not any(row.get("variables") for row in rows):
        return "an empty table shell"
    return None


def describe(body, year):
    """Return a one-line note on a table response: area, year, row count and the coal row."""
    try:
        reply = json.loads(body.decode("utf-8"))
        table = reply["data"][1]
        rows = table["data"]
        assert isinstance(rows, list)
    except (ValueError, KeyError, IndexError, TypeError, AssertionError):
        # A year without the table still answers status OK, with the error inside data[1]
        return "no table: " + body[:300].decode("utf-8", "replace")
    coal = [row for row in rows
            if (row.get("label_raw") or "").lower().startswith("pertambangan batu")]
    # An empty table shell has the row labels but an empty list in place of each row's values
    cells = [next(iter(row["variables"].values())) for row in coal if row.get("variables")]
    if len(coal) != 1:
        coal_note = f"{len(coal)} coal rows"
    elif not cells:
        coal_note = "coal row without a value"
    else:
        coal_note = f"coal {cells[0].get('value_raw')} [{cells[0].get('value_code')}]"
    year_note = "" if table.get("tahun_data") == year else f" (tahun_data {table.get('tahun_data')})"
    return f"{table.get('wilayah')} {table.get('tahun_data')}{year_note}, {len(rows)} rows, {coal_note}"


# Steps

# Print in UTF-8 so BPS markers such as the en dash show on any console
sys.stdout.reconfigure(encoding="utf-8")

# Read the key; it is used only inside fetch() and is never printed or written
key = read_key()

# Load the 38 provinces and their BPS codes
provinces = json.loads(PROVINCES.read_text(encoding="utf-8"))
assert len(provinces) == 38, f"expected 38 provinces, got {len(provinces)}"
sent = 0

# Download the SIMDASI province list and save it as received
status, body = fetch(PROVINCE_LIST, key)
sent += 1
save(body, OUT_PROVINCES, key)

# Stop unless every province has the MFD code <BPS code>00000 used below
mfd = {row["kode"] for row in json.loads(body.decode("utf-8"))["data"][1]["data"]}
missing = [p["kode_bps"] for p in provinces if p["kode_bps"] + "00000" not in mfd]
assert not missing, f"no MFD code for provinces {missing}"
print(f"{OUT_PROVINCES.name}: HTTP {status}, {len(body)} bytes, {len(mfd)} areas")

# Download one province's table list and save it as received
status, body = fetch(TABLE_LIST.format(wilayah=LIST_PROVINCE + "00000"), key)
sent += 1
save(body, OUT_TABLES, key)

# Stop unless that list holds the table id, and show its title and years
listed = [row for row in json.loads(body.decode("utf-8"))["data"][1]["data"] if row["id_tabel"] == TABLE_ID]
assert len(listed) == 1, f"table {TABLE_ID} not in the list for {LIST_PROVINCE}"
print(f"{OUT_TABLES.name}: HTTP {status}, {len(body)} bytes, table {listed[0]['kode_tabel']} "
      f"'{listed[0]['judul']}', years {listed[0]['ketersediaan_tahun']}")

# Download the table for every province and year, and save each response as received
for province in provinces:
    code = province["kode_bps"]
    for year in YEARS:
        status, body = fetch(TABLE.format(wilayah=code + "00000", year=year, table=TABLE_ID), key)
        sent += 1
        out = HERE / OUT_TABLE.format(code=code, year=year)
        # Stop before saving anything that is not a filled table for this province and year
        problem = table_problem(status, body, year)
        if problem:
            raise SystemExit(f"{code} {year}: {problem}; nothing saved")
        # Report what each saved response carries, so gaps show at once
        if save(body, out, key):
            print(f"{out.name}: HTTP {status}, {len(body)} bytes, {describe(body, year)}")

# Report the number of requests sent
print(f"{sent} requests sent")
