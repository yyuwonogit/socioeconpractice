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

# National workers by status and education (Indonesia only, no province split); its August totals
# by education check the Indonesia row of Table 107 in the Keadaan Angkatan Kerja Agustus 2025 report
VAR = 1126
YEARS = [2025]

OUT = HERE / "20261116_bps-webapi-workers-by-status-and-education.jsonl"

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

# Fetch the year list, then each wanted year, writing one response per line as received
body, _ = get("th", VAR)
ids = {int(r["th"]): r["th_id"] for r in body["data"][1]}
with open(OUT, "w", encoding="utf-8") as f:
    for year in YEARS:
        body, url = get("data", VAR, f"/th/{ids[year]}")
        assert body.get("data-availability") == "available" and body.get("datacontent"), year
        assert str(body["var"][0]["val"]) == str(VAR)
        f.write(json.dumps({"var": VAR, "year": year, "request": url, "response": body}, ensure_ascii=False) + "\n")
print(f"{OUT.name}: {len(YEARS)} responses")
