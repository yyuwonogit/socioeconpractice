from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

import json
import time
import urllib.error
import urllib.parse
import urllib.request

# Parameters

# BPS WebAPI, national domain; the key is read from ROOT/.env at run time and is never printed or saved
BASE = "https://webapi.bps.go.id/v1/api/"
DOMAIN = "0000"
ENV_FILE = ROOT / ".env"
ENV_NAME = "BPS_API_KEY"

# Dynamic table 98, Gini Ratio Menurut Provinsi dan Daerah (subject 23, Kemiskinan dan Ketimpangan),
# found with list/model/var?keyword=gini; columns are Perkotaan, Perdesaan and Perkotaan+Perdesaan,
# sub-periods are Semester 1 (Maret), Semester 2 (September) and Tahunan
VAR = 98

# Years per request: the WebAPI accepts at most 3 years in th, and BPS lists 2002, 2005 and 2007-2026
# for this table, with no 2003, 2004 or 2006
BLOCKS = [
    (2002, 2005),
    (2007, 2008, 2009),
    (2010, 2011, 2012),
    (2013, 2014, 2015),
    (2016, 2017, 2018),
    (2019, 2020, 2021),
    (2022, 2023, 2024),
    (2025, 2026),
]

OUT = HERE / "20261103_bps-gini-ratio-by-province-{first}-{last}.json"

# Pause between requests and number of tries per request
PAUSE = 1.5
ATTEMPTS = 4

# Functions

def read_key(path, name):
    """Return the value of the NAME=value line in the .env file."""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith(name + "="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit(f"{path.name} has no {name} line")


def fetch(path, key):
    """GET one WebAPI path with {key} filled in and return the body as bytes.

    Network errors, HTTP 429 and HTTP 5xx are retried with a growing pause. Any error is raised
    with the key replaced by {key}, and a body that carries the key stops the script unprinted,
    so the key never reaches the screen or a saved file.
    """
    url = BASE + path.replace("{key}", urllib.parse.quote(key, safe=""))
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(1, ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read()
            if key.encode() in body:
                raise SystemExit("the response carries the API key, so nothing is saved")
            return body
        except urllib.error.HTTPError as error:
            message = f"HTTP {error.code}: {error.read()[:300]!r}"
            if error.code != 429 and error.code < 500:
                raise RuntimeError(message.replace(key, "{key}")) from None
        except OSError as error:
            message = f"{type(error).__name__}: {error}"
        if attempt == ATTEMPTS:
            raise RuntimeError(message.replace(key, "{key}")) from None
        time.sleep(PAUSE * 4 * attempt)


def list_years(var, key):
    """Return the sorted years BPS lists for one dynamic table, reading every page of list/model/th."""
    years, page, pages = [], 1, 1
    while page <= pages:
        doc = json.loads(fetch(f"list/model/th/domain/{DOMAIN}/key/{{key}}?var={var}&lang=ind&page={page}", key))
        assert doc.get("status") == "OK", f"period list page {page}: {doc}"
        pages = doc["data"][0]["pages"]
        years += [int(row["th"]) for row in doc["data"][1]]
        page += 1
        time.sleep(PAUSE)
    return sorted(years)

# Steps

# Read the key from the repository's .env file
key = read_key(ENV_FILE, ENV_NAME)

# Stop unless the blocks request exactly the years BPS lists for this table
offered = list_years(VAR, key)
requested = sorted(year for block in BLOCKS for year in block)
assert requested == offered, f"BPS lists {offered}, the blocks request {requested}"

# Download each block of years and save the response exactly as received
for block in BLOCKS:
    th = ";".join(str(year - 1900) for year in block)
    body = fetch(f"list/model/data/domain/{DOMAIN}/var/{VAR}/th/{th}/key/{{key}}?lang=ind", key)
    doc = json.loads(body)

    # Stop if the response is an error, another table or other years
    assert doc.get("status") == "OK" and doc.get("data-availability") == "available", f"{block}: {doc}"
    assert doc["var"][0]["val"] == VAR, f"{block}: response is var {doc['var'][0]['val']}"
    assert [row["label"] for row in doc["tahun"]] == [str(year) for year in block], f"{block}: years differ"

    # Save the body byte for byte, never over a saved file (a revised release goes under a new date)
    out = OUT.with_name(OUT.name.format(first=block[0], last=block[-1]))
    if out.exists():
        raise SystemExit(f"{out.name} already exists; copy this script under a new date to file a new release")
    out.write_bytes(body)
    print(f"{out.name}: {len(body)} bytes, {len(doc['vervar'])} rows, {len(doc['datacontent'])} values")
    time.sleep(PAUSE)
