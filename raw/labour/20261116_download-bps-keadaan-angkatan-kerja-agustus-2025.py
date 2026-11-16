from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

import http.client
import json
import re
import time
import urllib.request

# Parameters

# BPS WebAPI publication detail; the key is read from the git-ignored .env file and never written to disk elsewhere
API = "https://webapi.bps.go.id/v1/api/view/model/publication/lang/ind/domain/0000/id/{pub_id}/key/{key}/"
KEY = re.search(r"^BPS_WEBAPI_KEY=(\w+)$", (ROOT / ".env").read_text(), re.M).group(1)

# Keadaan Angkatan Kerja di Indonesia Agustus 2025 (Sakernas August 2025), released 2025-12-19
PUB_ID = "42a75ee61332755586fdfcdd"
TITLE = "Keadaan Angkatan Kerja di Indonesia Agustus 2025"

OUT_PDF = HERE / "20261116_bps-keadaan-angkatan-kerja-agustus-2025.pdf"
OUT_META = HERE / "20261116_bps-keadaan-angkatan-kerja-agustus-2025-publication.json"

# Functions

def fetch(url, attempts=5):
    """Return the body of a URL, retrying when the server drops the connection mid-transfer."""
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                return response.read()
        except (OSError, http.client.IncompleteRead):
            if attempt == attempts:
                raise
            time.sleep(5 * attempt)

# Steps

# Read the publication record and check it is the expected report
url = API.format(pub_id=PUB_ID, key=KEY)
record = json.loads(fetch(url))
data = record["data"]
assert data["title"].strip() == TITLE, data["title"]

# Download the PDF as received and check it is a PDF
pdf = fetch(data["pdf"])
assert pdf[:5] == b"%PDF-", pdf[:20]
OUT_PDF.write_bytes(pdf)

# Save the publication record, without the key in the request address
OUT_META.write_text(json.dumps({"request": url.replace(KEY, "KEY"), "response": record}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(f"{OUT_PDF.name}: {len(pdf):,} bytes; {data['title']}, released {data.get('rl_date')}")
