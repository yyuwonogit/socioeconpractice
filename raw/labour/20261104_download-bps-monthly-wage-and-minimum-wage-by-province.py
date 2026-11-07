from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

import http.client
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

# Parameters

# BPS WebAPI; every path below ends in the key, which is read from ROOT / ".env" at run time
BASE = "https://webapi.bps.go.id/v1/api/"

# Static tables of the average net monthly wage of employees (Rata-rata Upah/Gaji Bersih Sebulan
# Buruh/Karyawan/Pegawai) by province, one table per release, as listed by the WebAPI statictable search on
# 4 November 2026. The tables by main occupation (Jenis Pekerjaan Utama) give the provincial wage; the tables by main
# industry (Lapangan Pekerjaan Utama) repeat each province's total and serve as checks. Keys are the period the title
# names
STATIC_PATH = "view/domain/0000/model/statictable/lang/ind/id/{id}/key/{key}/"
STATIC_TABLES = {
    "occupation": {"2016": 1948, "2017": 1988, "2018": 2048, "2019": 2070, "2020": 2096, "2021": 2131,
                   "2022-2023": 2190, "2023": 2233, "2024": 2255},
    "industry": {"2017": 1987, "2018": 2049, "2019": 2071, "2020": 2097, "2021": 2130, "2022": 2189, "2023": 2231,
                 "2024": 2253},
}
# Words every static table title must carry, compared as lower-case letters and digits only, since BPS writes
# 'Upah/Gaji' and 'UpahGaji' in different years
STATIC_TITLE_WORDS = {"occupation": ["upahgajibersihsebulan", "menurutprovinsidanjenispekerjaanutama"],
                      "industry": ["upahgajibersihsebulan", "menurutprovinsidanlapanganpekerjaanutama"]}

# Dynamic tables (WebAPI model data): var 583 is the same wage by province and main occupation for 2016 and 2024-2026,
# and var 220 is the provincial minimum wage (Upah Minimum Regional/Propinsi), which BPS publishes for 1997-2016 and
# 2018-2020. th lists years as offsets from 1900, at most three per request, separated by semicolons
DATA_PATH = "list/model/data/domain/0000/var/{var}/th/{th}/key/{key}"
DYNAMIC = {
    583: {"what": "monthly-wage-by-province-and-occupation",
          "title": "Upah/Gaji Bersih Sebulan Buruh/Karyawan/Pegawai Menurut Provinsi dan Jenis Pekerjaan Utama",
          "blocks": [[2016], [2024, 2025]]},
    220: {"what": "minimum-wage-by-province",
          "title": "Upah Minimum Regional/Propinsi",
          "blocks": [[1997, 1998, 1999], [2000, 2001, 2002], [2003, 2004, 2005], [2006, 2007, 2008],
                     [2009, 2010, 2011], [2012, 2013, 2014], [2015, 2016], [2018, 2019, 2020]]},
}

OUT_STATIC = "20261104_bps-static-table-{id}-monthly-wage-by-province-and-{kind}-{period}.json"
OUT_DYNAMIC = "20261104_bps-api-var{var}-{what}-{first}-{last}.json"

# Pause after each request and attempts per request, to keep the load on the WebAPI light
PAUSE = 1.5
ATTEMPTS = 4

# Functions

def read_key():
    """Return the BPS WebAPI key from the BPS_API_KEY line of ROOT / '.env'."""
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        name, _, value = line.partition("=")
        if name.strip() == "BPS_API_KEY":
            return value.strip().strip('"').strip("'")
    raise SystemExit("no BPS_API_KEY line in .env")


def fetch(path, key):
    """GET a WebAPI path, where {key} marks the key, and return the body bytes, retrying on network and server errors.

    Messages show the path with {key} in place of the key, so the key never reaches the screen.
    """
    url = BASE + path.replace("{key}", urllib.parse.quote(key, safe=""))
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    for attempt in range(1, ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                body = response.read()
            time.sleep(PAUSE)
            return body
        except urllib.error.HTTPError as error:
            if error.code != 429 and error.code < 500:
                raise SystemExit(f"HTTP {error.code} for {path}") from None
            problem = f"HTTP {error.code}"
        except (OSError, http.client.HTTPException) as error:
            problem = type(error).__name__
        if attempt == ATTEMPTS:
            raise SystemExit(f"{problem} for {path} after {ATTEMPTS} attempts") from None
        time.sleep(PAUSE * 4 * attempt)


def parse(body, key):
    """Stop if a response body contains the key, otherwise return it parsed as JSON."""
    text = body.decode("utf-8")
    if key in text or urllib.parse.quote(key, safe="") in text:
        raise SystemExit("a response contains the API key, so it was not saved")
    return json.loads(text)


def letters(text):
    """Keep only the lower-case letters and digits of a title, since BPS titles vary in spaces and stray characters."""
    return re.sub(r"[^0-9a-z]", "", (text or "").lower())


def save(path, body):
    """Write a response body byte for byte as received, never over a file already saved."""
    # A file in raw/ is never replaced; a revised release goes under a new date, from a copy of this script
    if path.exists():
        print(f"{path.name}: exists, kept")
        return False
    path.write_bytes(body)
    return True

# Steps

# Read the key once; it stays in memory and is never printed or saved
key = read_key()
sent = 0

# Download each static table, stop unless BPS served that table under the expected title, and save it as received
for kind, tables in STATIC_TABLES.items():
    for period, table_id in tables.items():
        out = HERE / OUT_STATIC.format(id=table_id, kind=kind, period=period)
        if out.exists():
            print(f"{out.name}: exists, kept")
            continue
        body = fetch(STATIC_PATH.format(id=table_id, key="{key}"), key)
        sent += 1
        reply = parse(body, key)
        assert reply.get("status") == "OK" and reply["data"]["table_id"] == table_id, f"static table {table_id} not served"
        title = letters(reply["data"]["title"])
        assert all(word in title for word in STATIC_TITLE_WORDS[kind]), f"{table_id}: title {reply['data']['title']!r}"
        assert period.split("-")[-1] in reply["data"]["title"], f"{table_id}: title {reply['data']['title']!r}"
        save(out, body)
        print(f"{out.name}: {len(body)} bytes, '{' '.join(reply['data']['title'].split())}'")

# Download each block of years of the two dynamic tables, stop unless it holds that variable, title and those years
for var, spec in DYNAMIC.items():
    for years in spec["blocks"]:
        out = HERE / OUT_DYNAMIC.format(var=var, what=spec["what"], first=years[0], last=years[-1])
        if out.exists():
            print(f"{out.name}: exists, kept")
            continue
        th = ";".join(str(year - 1900) for year in years)
        body = fetch(DATA_PATH.format(var=var, th=th, key="{key}"), key)
        sent += 1
        reply = parse(body, key)
        assert reply.get("status") == "OK" and reply.get("data-availability") == "available", f"var {var} {years}: {reply}"
        assert reply["var"][0]["val"] == var, f"var {var}: response is for var {reply['var'][0]['val']}"
        assert spec["title"] in " ".join(reply["var"][0]["label"].split()), f"var {var}: title {reply['var'][0]['label']!r}"
        held = sorted(int(t["label"]) for t in reply["tahun"])
        assert held == years, f"var {var}: asked for {years}, got {held}"
        save(out, body)
        print(f"{out.name}: {len(body)} bytes, {len(reply.get('datacontent') or {})} values, "
              f"BPS last_update {reply.get('last_update')}")

# Report how many requests the run sent
print(f"{sent} requests sent")
