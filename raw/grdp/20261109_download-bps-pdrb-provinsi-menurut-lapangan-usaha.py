from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

import hashlib
import json
import re
import urllib.request

# Parameters

# BPS WebAPI; the key is read from the git-ignored .env file and never written to disk elsewhere
API = "https://webapi.bps.go.id/v1/api/view/model/publication/lang/ind/domain/0000/id/{pub_id}/key/{key}/"
KEY = re.search(r"^BPS_WEBAPI_KEY=(\w+)$", (ROOT / ".env").read_text(), re.M).group(1)

# Publication: Produk Domestik Regional Bruto Provinsi-Provinsi di Indonesia Menurut Lapangan Usaha 2021-2025,
# catalogue 9302001, released 2026-04-13, page:
# https://www.bps.go.id/id/publication/2026/04/13/71d97fa95c70c5049deecbab/produk-domestik-regional-bruto-provinsi-provinsi-di-indonesia-menurut-lapangan-usaha-2021-2025.html
PUB_ID = "71d97fa95c70c5049deecbab"
TITLE = "Produk Domestik Regional Bruto Provinsi-Provinsi di Indonesia Menurut Lapangan Usaha 2021-2025"

OUT = HERE / "20261109_bps-pdrb-provinsi-provinsi-menurut-lapangan-usaha-2021-2025.pdf"

# Functions

def fetch(url, timeout=300):
    """Download a URL with a browser user agent and return its body as bytes."""
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()

# Steps

# Ask the WebAPI for the publication record, which carries a fresh PDF download link
record = json.loads(fetch(API.format(pub_id=PUB_ID, key=KEY)))["data"]
assert record["title"].strip() == TITLE, record["title"]

# Download the PDF as received and stop unless it is a PDF
body = fetch(record["pdf"])
assert body[:5] == b"%PDF-", body[:20]
OUT.write_bytes(body)
print(f"{OUT.name}: {len(body):,} bytes, released {record.get('rl_date')}, sha256 {hashlib.sha256(body).hexdigest()}")
