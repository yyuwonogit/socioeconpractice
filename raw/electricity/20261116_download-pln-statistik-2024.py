from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

import http.client
import time
import urllib.request

# Parameters

# PLN statistical report listed as "2024" on the PLN statistical reports page:
# https://www.pln.co.id/investor-relations-en/investor-publications-en/statistical-reports-en
# The page also lists a "2025" edition (Statistik-2025-2907.pdf, 76 MB), but the server closes each
# connection after about 50 seconds and ignores Range requests, so that file cannot be fetched from here.
URL = "https://www.pln.co.id/webapi/media/file/webkorp/asset/Statistik2024.pdf"

OUT = HERE / "20261116_pln-statistik-2024.pdf"

ATTEMPTS = 5

# Functions

def fetch(url):
    """Return the body of a URL, retrying when the server drops the connection."""
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(1, ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                size = int(response.headers["Content-Length"])
                body = response.read()
            if len(body) == size:
                return body
        except (OSError, http.client.IncompleteRead):
            if attempt == ATTEMPTS:
                raise
        time.sleep(5 * attempt)
    raise RuntimeError(f"incomplete download after {ATTEMPTS} attempts")

# Steps

# Download the PDF as received and check it is a PDF
pdf = fetch(URL)
assert pdf[:5] == b"%PDF-", pdf[:20]
OUT.write_bytes(pdf)
print(f"{OUT.name}: {len(pdf):,} bytes from {URL}")
