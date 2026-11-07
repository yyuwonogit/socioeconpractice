from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

import http.client
import json
import time
import urllib.error
import urllib.request

# Parameters

# BPS WebAPI; the key sits in the URL path and is read from the repository .env file at run time
BASE = "https://webapi.bps.go.id/v1/api/"
ENV_FILE = ROOT / ".env"

# Dynamic tables of the open unemployment rate (Tingkat Pengangguran Terbuka, percent) by province:
# var 543 holds the Februari and Agustus Sakernas rounds and the earlier Tahunan (annual) round;
# var 2562 is the quarterly Sakernas series (Februari, Mei, Agustus, November) that starts in 2025
SERIES = {
    543: ("Tingkat Pengangguran Terbuka Menurut Provinsi",
          "20261103_bps-unemployment-rate-by-province-{years}.json"),
    2562: ("Tingkat Pengangguran Terbuka menurut Provinsi (Triwulanan)",
           "20261103_bps-unemployment-rate-by-province-quarterly-{years}.json"),
}
PERIODS_PATH = "list/model/th/domain/0000/key/{key}/"
DATA_PATH = "list/model/data/domain/0000/var/{var}/th/{th}/key/{key}/"

# The data endpoint refuses more than 3 years per request
YEARS_PER_REQUEST = 3

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


def list_periods(var, key):
    """Return {th id: year label} for every period a dynamic table offers, following every page of the list."""
    periods, page, pages = {}, 1, 1
    while page <= pages:
        response = parse(fetch(PERIODS_PATH, key, f"var={var}&page={page}"), key)
        assert response["status"] == "OK", f"period list of var {var} not served"
        info, rows = response["data"]
        pages = info["pages"]
        for row in rows:
            assert row["var_id"] == var, f"period list of var {var} returned var {row['var_id']}"
            periods[int(row["th_id"])] = row["th"]
        page += 1
    assert len(periods) == info["total"], f"var {var}: listed {len(periods)} periods, total says {info['total']}"
    return periods


def chunks(ids, size):
    """Split sorted period ids into runs of consecutive ids, each cut into pieces of at most size ids."""
    runs, run = [], []
    for i in ids:
        if run and (i != run[-1] + 1 or len(run) == size):
            runs.append(run)
            run = []
        run.append(i)
    return runs + [run] if run else runs

# Steps

# Read the WebAPI key from .env
key = read_key()

# Download each unemployment table in turn: list its years, then fetch them in blocks of three
for var, (title, name) in SERIES.items():
    # List every year the table offers
    periods = list_periods(var, key)
    print(f"var {var}: {len(periods)} years offered, {min(periods.values())}-{max(periods.values())}")

    # Download the offered years in requests of at most three consecutive years
    for chunk in chunks(sorted(periods), YEARS_PER_REQUEST):
        body = fetch(DATA_PATH.replace("{var}", str(var)).replace("{th}", ";".join(map(str, chunk))), key)
        response = parse(body, key)

        # Stop if BPS served an error, another table or other years than requested
        assert response["status"] == "OK" and response["data-availability"] == "available", f"var {var} {chunk}: no data"
        assert response["var"][0]["val"] == var and response["var"][0]["label"].strip() == title, "table title changed"
        assert sorted(t["val"] for t in response["tahun"]) == chunk, f"var {var}: asked for {chunk}, got {response['tahun']}"

        # Save the response exactly as received, named by the years it holds
        first, last = periods[chunk[0]], periods[chunk[-1]]
        save(HERE / name.format(years=first if first == last else f"{first}-{last}"), body)
