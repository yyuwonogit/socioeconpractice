from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

import re
import time
import urllib.error
import urllib.request

# Parameters

# BPS table page: population, growth, share, density and sex ratio by province, one year per page
URL = ("https://www.bps.go.id/id/statistics-table/3/V1ZSbFRUY3lTbFpEYTNsVWNGcDZjek53YkhsNFFUMDkjMyMwMDAw/"
       "jumlah-penduduk--laju-pertumbuhan-penduduk--distribusi-persentase-penduduk--kepadatan-penduduk--"
       "rasio-jenis-kelamin-penduduk-menurut-provinsi.html?year={year}")

# Years before 2020; 20261102_download-bps-population-by-province.py saves 2020 onward
YEARS = range(2010, 2020)

OUT = HERE / "20261103_bps-population-by-province-{year}.html"

# Pause between requests to the BPS site, in seconds
PAUSE = 2

# Markers in the page's embedded data, written with the backslash escapes the saved page carries
YEAR_MARK = '\\"tahun_data\\":{year}'
ANY_YEAR_MARK = '\\"tahun_data\\":'
ERROR_MARK = '\\"errorMessage\\":'
LIST_MARK = re.compile(r'\\"list_tahun_data\\":\[([0-9,]+)\]')

# Functions

def fetch(url, attempts=4):
    """Download a URL with a browser user agent and return its HTTP status and body bytes.

    Network errors and server errors are retried with a growing pause; a 404 is returned at once.
    """
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return 404, error.read()
            if attempt == attempts:
                raise
        except OSError:
            if attempt == attempts:
                raise
        time.sleep(PAUSE * 5 * attempt)


def listed_years(text):
    """Return the years the page's table names in its list_tahun_data."""
    match = LIST_MARK.search(text)
    assert match, "a page with a table has no list_tahun_data"
    return {int(y) for y in match.group(1).split(",")}

# Steps

# Keep the years served, the years not served, and the years the table's own list names
served, not_served, listed = [], [], set()
for year in YEARS:
    # Download one year's page
    status, body = fetch(URL.format(year=year))
    text = body.decode("utf-8")
    if status == 200 and YEAR_MARK.format(year=year) in text:
        # Save a page that carries the requested year's table, byte for byte, never over a saved file
        page_file = OUT.with_name(OUT.name.format(year=year))
        if page_file.exists():
            raise SystemExit(f"{page_file.name} already exists; copy this script under a new date to file a new release")
        page_file.write_bytes(body)
        served.append(year)
        listed |= listed_years(text)
        print(f"{year}: HTTP {status}, {len(body)} bytes, table for {year}, saved")
    else:
        # Stop if BPS served another year's table instead of saying it holds none
        assert ANY_YEAR_MARK not in text, f"page for {year} carries a table for another year"
        # Stop unless the page is BPS's answer for a year it does not hold: HTTP 404, or the page shell with its error component
        assert status == 404 or ERROR_MARK in text, f"page for {year} has neither a table nor the error component"
        not_served.append(year)
        print(f"{year}: HTTP {status}, {len(body)} bytes, no table for {year}, not saved")
    time.sleep(PAUSE)

# Stop unless the years served are exactly the years before 2020 that the table's own year list names
assert served, "no year was served"
assert set(served) == {y for y in listed if y < YEARS.stop}, (served, sorted(listed))

# Stop if the table names a year earlier than this script asks for
assert min(listed) >= YEARS.start, sorted(listed)
print(f"saved {served}; not served {not_served}; table year list {sorted(listed)}")
