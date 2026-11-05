# socioeconpractice

This README sets the layout and rules of the repository, and CLAUDE.md makes every Claude session follow this README.

## Layout

```
socioeconpractice/
├── README.md                    layout and rules
├── CLAUDE.md                    tells every Claude session to follow README.md
├── requirements.txt             pinned packages for .venv
├── .gitignore                   excludes .venv, .env, caches and Office lock files
├── .gitattributes               keeps every file in raw/ byte for byte as received, and text files in data/ and analysis/ with LF line endings
├── .env                         local keys such as BPS_API_KEY, never committed
├── .venv/                       built on each machine, never committed
├── tools/
│   ├── cleaning.py              shared cleaning and checks, imported by every build script
│   └── charts.py                shared chart code, imported by analysis scripts that draw charts
├── .inbox/                      drop folder, emptied by Claude
├── .outbox/
│   └── YYYYMMDD_<delivery>/     one folder per delivery
├── reference/                   papers, reports, method notes
├── raw/
│   └── <topic>/                 one folder per topic
│       ├── YYYYMMDD_<source>.xlsx
│       └── YYYYMMDD_<download>.py
├── data/
│   └── YYYYMMDD_<dataset>/
│       ├── YYYYMMDD_<build>.py
│       ├── YYYYMMDD_<dataset>.csv
│       └── YYYYMMDD_<dataset>-metadata.json
└── analysis/
    └── YYYYMMDD_<analysis>/
        ├── YYYYMMDD_<analysis>.py
        ├── YYYYMMDD_<figure>.png
        └── YYYYMMDD_<table>.csv
```

| Folder | Holds | Scripts |
|---|---|---|
| `tools/` | Shared modules, without date prefixes | `cleaning.py` holds the cleaning and checking that every build script uses, and `charts.py` holds the chart code that analysis scripts share |
| `reference/` | Papers, reports and method notes | None |
| `raw/<topic>/` | Source files as received, never edited | A download script sits beside the files it fetched |
| `data/YYYYMMDD_<dataset>/` | Cleaned datasets and their metadata | The build script sits beside its output, reads `raw/` or other `data/` folders, and follows Cleaning and checking |
| `analysis/YYYYMMDD_<analysis>/` | Figures and tables | The script sits beside its outputs and reads `data/` only |

## Naming

- Every work file and work folder starts with `YYYYMMDD` and an underscore, then lowercase words joined by hyphens, as in `20261102_gdp-per-capita.csv`.
- The date is the Jakarta date (UTC+7) on which the item was created or filed.
- The date in a name stays fixed after later edits, and git records those edits.
- Sorting folders like `raw/<topic>/`, control files like `README.md` and shared modules in `tools/` have no date prefix, and topic folder names use lowercase words joined by hyphens.

## Scripts

- Every `.py` file sits in the folder of the data it writes, and every script finds other files by paths relative to its own location.
- An `import` statement cannot load a `.py` file whose name starts with a digit, so each script defines its own parameters and functions at the top, and code shared between scripts lives in `tools/`.
- Every build script in `data/` imports `tools/cleaning.py` and writes its output through `cleaning.write_dataset`, which checks the data and writes nothing if a check fails.
- A cleaning function that a second dataset needs moves into `tools/cleaning.py`, and every build script in `data/` is rerun after `tools/cleaning.py` changes.
- Files in `raw/` are never edited, and a cleaned version of a raw file goes to a new folder in `data/`.
- An analysis script in `analysis/` never reads a file in `raw/`. It reads only datasets in `data/`, so a raw value an analysis needs is first built into a `data/` dataset, where it passes the checks in Cleaning and checking.
- A download script never overwrites a saved file, and a revised release is fetched by a copy of the script under a new date.
- A script that calls the BPS WebAPI reads `BPS_API_KEY` from `.env` at run time, and never prints the key or writes it to a file.
- Every script starts from the header below, and every step in a script carries a comment that states its purpose.

```python
from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# Parameters

# Functions

# Steps
```

A build script in `data/` adds the shared module right after that header.

```python
# Load the shared cleaning module from tools/
import sys
sys.path.insert(0, str(ROOT / "tools"))
import cleaning
```

An analysis script that draws charts adds the shared chart module right after that header.

```python
# Load the shared chart module from tools/
import sys
sys.path.insert(0, str(ROOT / "tools"))
import charts
```

## Cleaning and checking

Every build script in `data/` turns raw files into one long CSV and one metadata JSON, and it writes neither file unless every check passes. `tools/cleaning.py` implements the rules below, so a build script only declares how its raw files are written and parses them; `data/20261102_bps-province-grdp-population/` is the worked example.

| Step | `tools/cleaning.py` provides |
|---|---|
| Read numbers | `parse_number` (declared decimal mark, thousands separator and decimals), `parse_cell`, `read_csv_rows`, `require_text` |
| Read BPS website pages | `bps_flight_text`, `bps_find_object`, `bps_resolve`, `html_to_text` |
| Read BPS static tables | `excel_grid` (an Excel-made HTML table laid out on a grid, with inline markup in a cell only where the build allows it), `excel_own_texts`, `excel_number_formats` |
| Read BPS WebAPI responses | `read_webapi_table` (dynamic tables, every datacontent key decoded, and on request the cells left under turvar codes a table no longer lists set aside for the build to declare), `read_simdasi_table` (SIMDASI yearbook tables, checked for year, area and values), `parse_status_note` (revision status by year from a table note) |
| Match regions | `load_bps_provinces`, `province_code`, `normalise_name`, `webapi_region_code` (WebAPI vervar values to BPS codes) |
| Combine sources | `merge_sources` (priority order, repeated values must match exactly), `compare_sources` (every difference between two sources, within a stated tolerance) |
| Check | `check_sum`, `flag_outside`, and inside `write_dataset`: structure and completeness |
| Write | `write_dataset` (CSV in the shared format, metadata with format, status codes and raw file hashes) |

### Reading the source

- Each build script declares, for every raw file, its encoding, field separator, decimal mark, thousands separator, missing-value markers and unit text, in a `READ_CONTEXT` parameter.
- The declarations come from opening the raw file, because BPS files mix conventions: some CSVs start with a byte-order mark, Indonesian-format files write `1.234,5` for 1234.5, and units sit in headers as words such as Ribu (thousand), Juta (million) and Milyar (billion).
- The script parses every number as text against the declared format and stops on any value that does not match, so a thousands separator never becomes a decimal point.
- The script checks that each header still carries its declared unit text, so a source that changes units stops the build.
- Header rows, footnotes and notes rows are read on purpose: footnotes go to the metadata, and data rows are matched by name, never by line number alone.

### Writing the dataset

- The CSV is UTF-8 without a byte-order mark, comma-separated, with `.` as the decimal mark and no thousands separator.
- The CSV has one value per row, with key columns first, then `status`, then a single `value` column last, as in `province_code, indicator, sector, period, status, value`.
- `status` carries the source's revision marker, such as BPS `*` (preliminary), `**` and `***`, and is empty for final values; the metadata gives each marker's meaning.
- When several raw files hold the same value, the build reads them in a stated priority order (BPS pages and downloads before compiled workbooks), and the lower-priority copies serve as checks.
- Values keep the precision and unit BPS published; the metadata gives each indicator's unit, its multiplier to base units and its source.
- A value BPS does not publish has no row, and markers such as `-`, `...` and `NA` are never written as 0.
- Derived values such as per-capita figures and growth rates belong in `analysis/`, and the metadata gives the formula.
- Codes, not names, identify regions, sectors and indicators, and the metadata maps every code to its name.
- Periods are written `YYYY` for years, `YYYYQn` for quarters and `YYYYSn` for half-yearly survey rounds, such as `2025S1` for the March Susenas and `2025S2` for the September one.

### Regions

- Province names map to BPS province codes (`kode_bps`) through the BPS list in `raw/province-codes/`, never through a list typed by hand.
- Names are normalised before matching (upper case, `KEP.` spelled out as `KEPULAUAN`, `D I` written as `DI`, single spaces), and a name with no match stops the build.
- BPS and Kemendagri codes differ for the six Papua provinces, so the metadata keeps both and a join with another dataset uses the code system that dataset uses.
- Papua Barat Daya, Papua Selatan, Papua Tengah and Papua Pegunungan have values from 2023 in the annual GRDP tables (WebAPI vars 286, 288, 291 and 296) and from 2024 in the sector GRDP tables (vars 2267 and 2268), the expenditure GRDP tables (vars 534 and 542), the population tables and the social tables. Before those years, Papua and Papua Barat values cover the pre-split areas.
- Kalimantan Utara has its own values from 2010 in the sector and expenditure GRDP tables, from 2013 in the annual GRDP tables and from 2015 or 2016 in the population and social tables; before that, Kalimantan Timur includes it.

### Checks

| Layer | Check | On failure |
|---|---|---|
| 1. Structure | Exact columns, numeric values, unique keys, every code in the metadata lookups | Stop |
| 2. Completeness | Every expected region, indicator, sector and period is present, and the only gaps are those the metadata explains | Stop |
| 3. Identities | Parts sum to totals (sectors to TOTAL, quarters to year, shares to 100, provinces to Indonesia) within a stated rounding tolerance | Stop |
| 4. Cross-source | Values that appear in more than one source match exactly or within a tolerance the build states, and the metadata lists every difference | Stop |
| 5. Plausibility | Values and year-on-year changes stay inside stated ranges | List in the metadata `checks.flags` |
| 6. Provenance | The SHA-256 hash of every raw file read is recorded in the metadata | Recorded |

- A flag is reviewed by a person and stays in the metadata whether it reflects a real event or a source error.
- Rebuilding a dataset from unchanged raw files produces byte-identical output, so `git diff --exit-code data/` after a rebuild shows whether anything changed.
- A revised BPS release is filed as a new dated raw file beside the old one, and the build script is pointed at it, so the git diff of the CSV shows each revised value.

### Reference sources

| Need | Source | In this repository |
|---|---|---|
| Province codes and names, BPS and Kemendagri | BPS region bridging service, `https://sig.bps.go.id/rest-bridging/getwilayah?level=provinsi&periode_merge=2025_1.2025`, where the default period without `periode_merge` returns the old 34 provinces | `raw/province-codes/` |
| Province area and official names | Keputusan Menteri Dalam Negeri on Kode dan Data Wilayah Administrasi Pemerintahan (BPS cites Nomor 100.1.1-6117 Tahun 2022) | Not yet filed |
| BPS tables, one year per page | bps.go.id statistics-table pages saved as received; population pages take `?year=YYYY`, while GRDP pages serve only the latest year | `raw/population/`, `raw/grdp/` |
| BPS tables for any year by script | BPS WebAPI, `https://webapi.bps.go.id`, with a free key registered at that site and kept in `.env` as `BPS_API_KEY`; one request covers at most 3 years, and provincial yearbook tables such as GRDP by detailed industry come through its SIMDASI service | `raw/grdp/`, `raw/grdp-detailed-industry/`, `raw/population/`, `raw/inequality/`, `raw/poverty/`, `raw/household-spending/`, `raw/labour/`, `raw/education/` |

## .inbox and .outbox

- You drop files into `.inbox` from a clone on your PC or through the Upload files page on github.com.
- Claude moves each file to `reference/` or a `raw/<topic>/` folder and adds the date prefix to its name.
- Claude creates each topic folder in `raw/` when the first file on that topic arrives.
- The commit message records each original filename, and git keeps that original filename in the file's history.
- Claude checks `.inbox` at the start of each session and asks you about any file whose topic is unclear.
- Each delivery goes in a new `.outbox/YYYYMMDD_<name>/` folder, and Claude pushes that folder to GitHub.

## Environment

`.venv` sits at the repository root, and each machine builds its own `.venv` from `requirements.txt`. The pinned numpy and scipy versions require Python 3.12 or later.

### Windows PowerShell

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Linux or macOS

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Scripts run with the `.venv` Python, as in `.venv\Scripts\python.exe data\YYYYMMDD_<dataset>\YYYYMMDD_<build>.py` on Windows.
