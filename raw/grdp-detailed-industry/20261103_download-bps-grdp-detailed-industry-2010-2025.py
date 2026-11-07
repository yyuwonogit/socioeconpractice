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

# SIMDASI (Yearbook Dataset) services: 23 lists the yearbook tables of one area with the years each
# table holds (ketersediaan_tahun), and 25 returns one table for one area and one year
TABLE_LIST = "interoperabilitas/datasource/simdasi/id/23/wilayah/{wilayah}"
TABLE = "interoperabilitas/datasource/simdasi/id/25/wilayah/{wilayah}/tahun/{year}/id_tabel/{table}"

# The two yearbook tables of provincial GRDP by detailed industry (62 rows: 17 categories with their
# sub-categories), each with its id, its kode_tabel and title wording as a check, the years to fetch,
# and the name of each saved file. 13.1.1 for 2024 and 2025 was saved by
# 20261103_download-bps-grdp-detailed-industry.py, so this script fetches 2010-2023 of it
TABLES = {
    "current": {"id": "S1RMUWRYb0NWc0Y5L05QQkxzcWw3Zz09", "kode": "13.1.1",
                "title": "Atas Dasar Harga Berlaku Menurut Lapangan Usaha", "years": range(2010, 2024),
                "out": "20261103_bps-grdp-current-prices-detailed-industry-{code}-{year}.json"},
    "constant": {"id": "UklLSnFZZnMzMlJiSWpMOExJODIrQT09", "kode": "13.1.2",
                 "title": "Atas Dasar Harga Konstan 2010 Menurut Lapangan Usaha", "years": range(2010, 2026),
                 "out": "20261103_bps-grdp-constant-prices-detailed-industry-{code}-{year}.json"},
}

# The 38 provinces and their BPS codes; each province's SIMDASI area code is <BPS code>00000
PROVINCES = ROOT / "raw" / "province-codes" / "20261102_bps-province-codes-2025-s1.json"

# Each province's table list is saved beside this script; one was saved for 64 by the first script
OUT_LIST = "20261103_bps-simdasi-tables-{code}.json"

# Seconds to wait after each request, and attempts per request for network or server errors
PAUSE = 1.5
ATTEMPTS = 4

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


def table_entry(listing, spec):
    """Return the one entry of a table list that is this table: its id, kode_tabel and title wording."""
    found = [row for row in listing if row.get("id_tabel") == spec["id"]]
    if len(found) != 1:
        return None
    row = found[0]
    # The id must still be the table it was chosen as
    if row.get("kode_tabel") != spec["kode"] or spec["title"] not in " ".join((row.get("judul") or "").split()):
        raise SystemExit(f"table {spec['id']} is now {row.get('kode_tabel')} '{row.get('judul')}'")
    return row

# Steps

# Print in UTF-8 so BPS markers such as the en dash show on any console
sys.stdout.reconfigure(encoding="utf-8")

# Read the key; it is used only inside fetch() and is never printed or written
key = read_key()

# Load the 38 provinces and their BPS codes
provinces = json.loads(PROVINCES.read_text(encoding="utf-8"))
assert len(provinces) == 38, f"expected 38 provinces, got {len(provinces)}"
sent, saved, skipped, problems = 0, 0, 0, []

for province in provinces:
    code = province["kode_bps"]
    wilayah = code + "00000"

    # Read the province's table list, from the saved file when one exists, otherwise download and save it
    list_file = HERE / OUT_LIST.format(code=code)
    if list_file.exists():
        body = list_file.read_bytes()
    else:
        status, body = fetch(TABLE_LIST.format(wilayah=wilayah), key)
        sent += 1
        if status != 200:
            problems.append(f"{code} table list: HTTP {status}")
            continue
        save(body, list_file, key)
    listing = json.loads(body.decode("utf-8"))["data"][1]["data"]

    for name, spec in TABLES.items():
        # Fetch only the years BPS lists for this province's table, inside the years wanted
        entry = table_entry(listing, spec)
        if entry is None:
            problems.append(f"{code} {spec['kode']}: not in the province's table list")
            continue
        listed = sorted(set(entry.get("ketersediaan_tahun") or []) & set(spec["years"]))
        print(f"{code} {spec['kode']} {name}: BPS lists {entry.get('ketersediaan_tahun')}; fetching {listed}")
        for year in listed:
            out = HERE / spec["out"].format(code=code, year=year)
            # A table saved by an earlier run stays as it is, so the script can resume
            if out.exists():
                skipped += 1
                continue
            status, body = fetch(TABLE.format(wilayah=wilayah, year=year, table=spec["id"]), key)
            sent += 1
            # Save nothing that is not a filled table for this province and year, and note why
            problem = table_problem(status, body, year)
            if problem:
                problems.append(f"{code} {spec['kode']} {year}: {problem}")
                continue
            if save(body, out, key):
                saved += 1

# Report the requests, the tables saved and skipped, and every problem
print(f"{sent} requests sent, {saved} tables saved, {skipped} already saved")
for problem in problems:
    print("PROBLEM:", problem)
if problems:
    raise SystemExit(f"{len(problems)} problems; see above")
