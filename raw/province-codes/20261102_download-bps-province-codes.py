from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

import json
import urllib.request

# Parameters

# BPS region bridging service: BPS and Kemendagri codes and names for each province
URL = "https://sig.bps.go.id/rest-bridging/getwilayah?level=provinsi&periode_merge={period}"

# Semester 1 of 2025 is the first period with all 38 provinces after the 2022 Papua split
PERIOD = "2025_1.2025"

OUT = HERE / "20261102_bps-province-codes-2025-s1.json"

# Functions

def fetch(url):
    """Download a URL and return its body as text."""
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read().decode("utf-8")

# Steps

# Download the province list for the chosen period
body = fetch(URL.format(period=PERIOD))

# Stop if the service returned something other than the 38 provinces
provinces = json.loads(body)
assert len(provinces) == 38, f"expected 38 provinces, got {len(provinces)}"

# Save the response exactly as received
OUT.write_text(body, encoding="utf-8")
print(f"{OUT.name}: {len(provinces)} provinces")
