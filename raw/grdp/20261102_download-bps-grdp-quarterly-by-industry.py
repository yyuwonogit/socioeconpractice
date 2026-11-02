from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

import urllib.request

# Parameters

# BPS table page: quarterly GRDP at current prices by industry and province (var 2268)
URL = ("https://www.bps.go.id/id/statistics-table/2/MjI2OCMy/-seri-2010--pdrb-triwulanan-atas-dasar-harga-"
       "berlaku-menurut-lapangan-usaha-di-provinsi-seluruh-indonesia--milyar-rupiah-.html")

# The page serves only its latest year; earlier years need the BPS WebAPI and a key
YEAR = 2026

OUT = HERE / f"20261102_bps-grdp-quarterly-by-industry-{YEAR}.html"

# Functions

def fetch(url):
    """Download a URL with a browser user agent and return its body as text."""
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8")

# Steps

# Download the page
body = fetch(URL)

# Stop if the page now serves a year other than the one this file is named for
assert f'\\"tahun\\":[{{\\"val\\":{YEAR - 1900},\\"label\\":\\"{YEAR}\\"}}]' in body, "page serves a different year"

# Save the page exactly as received
OUT.write_text(body, encoding="utf-8")
print(f"{OUT.name}: {len(body)} characters")
