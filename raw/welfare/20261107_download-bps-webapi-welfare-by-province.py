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
API = "https://webapi.bps.go.id/v1/api/list/model/{model}/lang/ind/domain/0000/var/{var}{extra}/key/{key}/"
KEY = re.search(r"^BPS_WEBAPI_KEY=(\w+)$", (ROOT / ".env").read_text(), re.M).group(1)

# National tables covering every province
TABLES = {
    416: "[Metode Baru] Pengeluaran per Kapita Disesuaikan",
    192: "Persentase Penduduk Miskin (P0) Menurut Provinsi dan Daerah",
}

YEARS = range(2020, 2027)

OUT = HERE / "20261107_bps-webapi-welfare-by-province.jsonl"

PAUSE = 0.4

# Functions

def get(model, var, extra=""):
    """Call the WebAPI and return the parsed response and the request address without the key."""
    url = API.format(model=model, var=var, extra=extra, key=KEY)
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

# Steps

# Fetch each table's year list, then each wanted year, writing one response per line as received
lines = 0
with open(OUT, "w", encoding="utf-8") as f:
    for var, title in TABLES.items():
        body, _ = get("th", var)
        ids = {int(r["th"]): r["th_id"] for r in body["data"][1]}
        for year in [y for y in YEARS if y in ids]:
            body, url = get("data", var, f"/th/{ids[year]}")
            # Skip years BPS lists but has not filled yet, and stop on a different table
            if body.get("data-availability") != "available" or not body.get("datacontent"):
                print(f"{title}: {year} listed but empty")
                continue
            assert str(body["var"][0]["val"]) == str(var), var
            f.write(json.dumps({"var": var, "year": year, "request": url, "response": body}, ensure_ascii=False) + "\n")
            lines += 1
        print(f"{title}: {sorted(y for y in YEARS if y in ids)}")
print(f"{OUT.name}: {lines} responses")
