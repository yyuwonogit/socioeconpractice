from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

import time
import urllib.request

# Parameters

# BPS table page: population, growth, share, density and sex ratio by province, one year per page
URL = ("https://www.bps.go.id/id/statistics-table/3/V1ZSbFRUY3lTbFpEYTNsVWNGcDZjek53YkhsNFFUMDkjMyMwMDAw/"
       "jumlah-penduduk--laju-pertumbuhan-penduduk--distribusi-persentase-penduduk--kepadatan-penduduk--"
       "rasio-jenis-kelamin-penduduk-menurut-provinsi.html?year={year}")

# 2020 is the census year that starts the SP2020-based series; earlier years use the SP2010 base
YEARS = range(2020, 2027)

OUT = HERE / "20261102_bps-population-by-province-{year}.html"

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

# Steps

# Download each year's page and save it exactly as received
for year in YEARS:
    body = fetch(URL.format(year=year))
    # Stop if BPS served a different year than requested
    assert f'\\"tahun_data\\":{year}' in body, f"page for {year} does not carry tahun_data {year}"
    OUT.with_name(OUT.name.format(year=year)).write_text(body, encoding="utf-8")
    print(f"{year}: {len(body)} characters")
    time.sleep(PAUSE)
