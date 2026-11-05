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

# Satu Data Kemnaker (Ministry of Manpower data portal) public API: POST {"id": n} to detail_data returns a dataset's
# title, abstract, dates and the address of its file. No key is needed
DETAIL_URL = "https://satudata.kemnaker.go.id/api/v1/data/detail_data"

# The portal's datasets of the provincial minimum wage (Upah Minimum Provinsi, UMP) by province, as listed by its
# list_data search on 4 November 2026, each with title wording its detail must carry and the years it names. Dataset
# 36 repeats 2016-2020, which BPS WebAPI var 220 holds except 2017, and dataset 473 repeats 2018-2020, so both serve
# as checks on BPS and fill 2017 and 2021-2022; datasets 942, 1611 and 2252 hold 2023, 2024 and 2025
DATASETS = {
    36: {"title": "UMP Nasional Tahun 2016-2020", "years": "2016-2020"},
    473: {"title": "Nilai Upah Minimum Provinsi (UMP) di Indonesia Tahun 2018 sampai dengan Tahun 2022",
          "years": "2018-2022"},
    942: {"title": "Upah Minimum Provinsi (UMP) Tahun 2023", "years": "2023"},
    1611: {"title": "Upah Minimum Provinsi (UMP) Tahun 2024", "years": "2024"},
    2252: {"title": "Upah Minimum Provinsi (UMP) Tahun 2025", "years": "2025"},
}

# Each dataset's detail (the API answer, which records the file address, abstract and dates) and its file, saved as
# received
OUT_DETAIL = "20261104_kemnaker-dataset-{id}-minimum-wage-by-province-{years}-detail.json"
OUT_FILE = "20261104_kemnaker-dataset-{id}-minimum-wage-by-province-{years}.xlsx"

# An xlsx file is a zip archive, so it starts with these bytes
XLSX_START = b"PK\x03\x04"

# Pause after each request and attempts per request, to keep the load on the portal light
PAUSE = 1.5
ATTEMPTS = 4

# Functions

def request(url, body=None):
    """Return the bytes of a GET, or of a POST of a JSON body, retrying on network and server errors."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"User-Agent": "Mozilla/5.0"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    for attempt in range(1, ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers), timeout=90) as response:
                content = response.read()
            time.sleep(PAUSE)
            return content
        except urllib.error.HTTPError as error:
            if error.code != 429 and error.code < 500:
                raise SystemExit(f"HTTP {error.code} for {url}") from None
            problem = f"HTTP {error.code}"
        except (OSError, http.client.HTTPException) as error:
            problem = type(error).__name__
        if attempt == ATTEMPTS:
            raise SystemExit(f"{problem} for {url} after {ATTEMPTS} attempts") from None
        time.sleep(PAUSE * 4 * attempt)


def save(path, content):
    """Write bytes exactly as received, never over a file already saved."""
    # A file in raw/ is never replaced; a revised release goes under a new date, from a copy of this script
    if path.exists():
        print(f"{path.name}: exists, kept")
        return
    path.write_bytes(content)
    print(f"{path.name}: {len(content)} bytes")

# Steps

for dataset_id, spec in DATASETS.items():
    detail_path = HERE / OUT_DETAIL.format(id=dataset_id, years=spec["years"])
    file_path = HERE / OUT_FILE.format(id=dataset_id, years=spec["years"])

    # Read the dataset's detail and stop unless it is the dataset this script names
    detail_bytes = detail_path.read_bytes() if detail_path.exists() else request(DETAIL_URL, {"id": dataset_id})
    detail = json.loads(detail_bytes)
    assert detail.get("status") == 200, f"dataset {dataset_id}: status {detail.get('status')}"
    title = " ".join(str(detail["data"]["judul"]).split())
    assert title == spec["title"], f"dataset {dataset_id} is now titled {title!r}"
    save(detail_path, detail_bytes)

    # Download the dataset's file from the address its detail gives, and stop unless it is an xlsx file
    if file_path.exists():
        print(f"{file_path.name}: exists, kept")
        continue
    content = request(detail["data"]["file"])
    assert content.startswith(XLSX_START), f"dataset {dataset_id}: the file is not an xlsx file"
    save(file_path, content)
