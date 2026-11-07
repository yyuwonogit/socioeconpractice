from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

import re
import time
import urllib.request

# Parameters

# BPS national tables covering every province; each page serves only its latest year
PAGES = {
    "adjusted-per-capita-expenditure": "https://www.bps.go.id/id/statistics-table/2/NDE2IzI=/-metode-baru--pengeluaran-per-kapita",
    "poverty-rate": "https://www.bps.go.id/id/statistics-table/2/MTkyIzI=/persentase-penduduk-miskin--maret-2026.html",
}

OUT = HERE / "20261107_bps-{name}-by-province-{year}.html"

# Pause between requests to the BPS site, in seconds
PAUSE = 2

# Functions

def fetch(url, attempts=4):
    """Download a URL with a browser user agent and return its body as text, retrying on network errors."""
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read().decode("utf-8")
        except OSError:
            if attempt == attempts:
                raise
            time.sleep(PAUSE * 5 * attempt)


def served_year(body):
    """Return the year a BPS dynamic-table page serves, read from its tahun list."""
    years = re.findall(r'\\"tahun\\":\[\{\\"val\\":\d+,\\"label\\":\\"(\d{4})\\"', body)
    assert len(set(years)) == 1, f"expected one served year, found {set(years)}"
    return years[0]

# Steps

# Download each page, name it by the year it serves, and save it exactly as received
for name, url in PAGES.items():
    body = fetch(url)
    year = served_year(body)
    path = OUT.with_name(OUT.name.format(name=name, year=year))
    path.write_text(body, encoding="utf-8")
    print(f"{path.name}: {len(body)} characters")
    time.sleep(PAUSE)
