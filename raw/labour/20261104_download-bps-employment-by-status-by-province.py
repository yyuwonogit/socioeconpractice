from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

import http.client
import json
import time
import urllib.error
import urllib.parse
import urllib.request

# Parameters

# BPS WebAPI dynamic-table endpoint; th is the year minus 1900, and the key is read from ROOT / ".env" at run time
URL = "https://webapi.bps.go.id/v1/api/list/model/data/domain/{domain}/var/{var}/th/{th}/key/{key}"

# National domain, which serves the tables by province
DOMAIN = "0000"

# Variable to download, with the description used in its file names, the title wording its response must carry (so a
# reused var id that now holds another table stops the run) and its year ranges: the API accepts at most 3 years in
# th, and the var is fetched over every year BPS lists for it (2017-2026; 2026 holds the Februari round only)
VARIABLES = {
    # Penduduk Berumur 15 Tahun Keatas yang Bekerja Selama Seminggu Terakhir Menurut Provinsi dan Status Pekerjaan
    # Utama (Sakernas, Februari and Agustus rounds), persons employed by status in their main job
    2335: {"what": "employment-by-status-by-province",
           "title": "yang Bekerja Selama Seminggu Terakhir Menurut Provinsi dan Status Pekerjaan Utama",
           "ranges": [(2017, 2019), (2020, 2022), (2023, 2025), (2026, 2026)]},
}

OUT_NAME = "20261104_bps-api-var{var}-{what}-{start}-{end}.json"

# Pause between requests, retries with doubling waits, and a timeout, to keep the load on BPS light
PAUSE_SECONDS = 1.5
RETRIES = 4
TIMEOUT_SECONDS = 120

# Functions

def read_key():
    """Return the BPS WebAPI key from the BPS_API_KEY line of ROOT / '.env'."""
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        name, _, value = line.partition("=")
        if name.strip() == "BPS_API_KEY":
            return value.strip().strip('"').strip("'")
    raise SystemExit("no BPS_API_KEY line in .env")


def hide(text, key):
    """Replace the key, plain or URL-quoted, with {key} so that messages never show it."""
    return text.replace(urllib.parse.quote(key, safe=""), "{key}").replace(key, "{key}")


def fetch(url, key):
    """Download a URL with retries and return the body as bytes, stopping at once on client errors."""
    for attempt in range(1, RETRIES + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            # A client error other than rate limiting gets the same answer on a retry
            if error.code < 500 and error.code != 429:
                detail = error.read()[:300].decode("utf-8", "replace")
                raise SystemExit(hide(f"HTTP {error.code} for {url}: {detail}", key))
            problem = f"HTTP {error.code}"
        except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException) as error:
            problem = type(error).__name__
        print(hide(f"attempt {attempt} of {RETRIES} failed ({problem}) for {url}", key))
        if attempt < RETRIES:
            time.sleep(2 ** attempt)
    raise SystemExit(hide(f"gave up on {url}", key))


def check(body, key, var, spec, start, end):
    """Return the parsed response and its years, stopping unless it is an OK answer for this variable, its title
    and every year of the range, without the key."""
    text = body.decode("utf-8")
    if key in text:
        raise SystemExit(f"var {var} {start}-{end}: the response contains the key, so it is not saved")
    data = json.loads(text)
    if data.get("status") != "OK" or data.get("data-availability") != "available":
        raise SystemExit(f"var {var} {start}-{end}: {text[:300]}")
    if data["var"][0]["val"] != var:
        raise SystemExit(f"var {var} {start}-{end}: response is for var {data['var'][0]['val']}")
    if spec["title"] not in " ".join(data["var"][0]["label"].split()):
        raise SystemExit(f"var {var} {start}-{end}: title is now '{data['var'][0]['label']}'")
    years = sorted(int(item["label"]) for item in data["tahun"])
    if years != list(range(start, end + 1)):
        raise SystemExit(f"var {var} {start}-{end}: response holds years {years}")
    return data, years

# Steps

# Read the key once; it stays in memory and is never printed or saved
key = read_key()

# Download the variable in each year range
sent = 0
for var, spec in VARIABLES.items():
    for start, end in spec["ranges"]:
        out = HERE / OUT_NAME.format(var=var, what=spec["what"], start=start, end=end)

        # Keep a file that already exists, because files in raw/ are never edited
        if out.exists():
            print(f"{out.name}: exists, kept")
            continue

        # Build the request; th takes the first and last year as offsets from 1900
        th = f"{start - 1900}:{end - 1900}"
        url = URL.format(domain=DOMAIN, var=var, th=th, key=urllib.parse.quote(key, safe=""))

        # Pause before every request after the first
        if sent:
            time.sleep(PAUSE_SECONDS)
        body = fetch(url, key)
        sent += 1

        # Check the response, then save it exactly as received
        data, years = check(body, key, var, spec, start, end)
        out.write_bytes(body)
        values = len(data.get("datacontent") or {})
        print(f"{out.name}: {len(body)} bytes, years {years[0]}-{years[-1]}, {values} values, "
              f"BPS last_update {data.get('last_update')}")

# Report how many requests the run sent
print(f"{sent} requests sent")
