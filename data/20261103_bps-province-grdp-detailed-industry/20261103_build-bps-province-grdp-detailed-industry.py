from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# Load the shared cleaning module from tools/
import sys
sys.path.insert(0, str(ROOT / "tools"))
import cleaning

# Modules for the checks: math for a range open above, pandas for the identity sums
import math

import pandas as pd

# Parameters

# Raw inputs. Every value comes from the SIMDASI yearbook tables, one per province and year, which are the
# only source of the 62 industry rows; the WebAPI quarterly GRDP by industry (var 2268) holds the same 17
# categories and total for both years and serves as the cross-check
RAW_PROVINCES = ROOT / "raw/province-codes/20261102_bps-province-codes-2025-s1.json"
RAW_TABLE_DIR = ROOT / "raw/grdp-detailed-industry"
RAW_TABLE_NAME = "20261103_bps-grdp-current-prices-detailed-industry-{code}-{year}.json"
# The years this dataset holds; the folder also holds the 2010-2023 tables, which
# data/20261103_bps-province-grdp-detailed-industry-2010-2025 reads, so only these years' tables are taken
YEARS = [2024, 2025]
RAW_TABLES = sorted(p for year in YEARS for p in RAW_TABLE_DIR.glob(RAW_TABLE_NAME.format(code="??", year=year)))
RAW_2268 = ROOT / "raw/grdp/20261103_bps-api-var2268-grdp-quarterly-current-prices-by-industry-by-province-2024-2025.json"

# The scripts that downloaded the SIMDASI tables and var 2268, named in the metadata
DOWNLOAD_SCRIPT = "raw/grdp-detailed-industry/20261103_download-bps-grdp-detailed-industry.py"
DOWNLOAD_SCRIPT_2268 = "raw/grdp/20261103_download-bps-api-grdp-2010-2025.py"

# Output; the metadata JSON is written beside it with a -metadata suffix
OUT_CSV = HERE / "20261103_bps-province-grdp-detailed-industry.csv"

# The en dash BPS prints, with no value, for 'Tidak ada atau nol' (none or zero)
NONE_OR_ZERO = "–"

# How each raw file is written, read from opening the files: all are UTF-8 JSON without a byte-order mark.
# The BPS province list is 38 records whose codes and names are all text, so it declares no number format.
# The SIMDASI tables write each value as Indonesian text (75.317,96) with the 2 decimals each column
# declares, carry the unit in the title, and leave a cell without a value only under the en dash.
# Var 2268 writes JSON numbers in Milyar Rupiah with 2 decimals.
SIMDASI_FORMAT = {"encoding": "utf-8", "decimal": ",", "thousands": ".", "decimals": 2,
                  "unit_text": "(miliar rupiah)", "missing": [NONE_OR_ZERO]}
READ_CONTEXT = {
    RAW_PROVINCES: {"encoding": "utf-8"},
    **{path: SIMDASI_FORMAT for path in RAW_TABLES},
    RAW_2268: {"encoding": "utf-8", "var": 2268, "unit": "Milyar Rupiah", "decimals": 2},
}

KEYS = ["province_code", "indicator", "sector", "period"]
INDICATOR = "grdp_current"

# Each table's title and its one column must still name GRDP at current prices by industry
TITLE_TEXT = "Produk Domestik Regional Bruto Atas Dasar Harga Berlaku Menurut Lapangan Usaha"
COLUMN_TEXT = "Atas Dasar Harga Berlaku"

# The 17 KBLI categories, coded as in data/20261102_bps-province-grdp-population, each with the code
# that the SIMDASI rows and the var 2268 industry labels print
GROUPS = {"A": "A", "B": "B", "C": "C", "D": "D", "E": "E", "F": "F", "G": "G", "H": "H", "I": "I", "J": "J",
          "K": "K", "L": "L", "MN": "M,N", "O": "O", "P": "P", "Q": "Q", "RSTU": "R,S,T,U"}

# Numbered sub-categories of each category that has them, and lettered items of each sub-category that
# has them, as the table prints them; a sub-category code appends its number to its category (B2), and
# an item code appends its letter to its sub-category (A1a)
SUBCATEGORIES = {"A": 3, "B": 4, "C": 16, "D": 2, "G": 2, "H": 6, "I": 2, "K": 4}
ITEMS = {"A1": "abcde"}

# The province total, matched by its label: the last SIMDASI row and the last var 2268 industry. The SIMDASI
# row's label_raw reads 'Produk Domestik Bruto' though its HTML label reads 'Produk Domestik Regional Bruto',
# so the metadata names TOTAL as var 2268 labels it and keeps the SIMDASI text in label_raw
TOTAL = "TOTAL"
TOTAL_LABELS = {"simdasi": "Produk Domestik Bruto", "var 2268": "Produk Domestik Regional Bruto"}

# Coal and lignite mining, which the coal-share check reads; the row must still carry this label
COAL = "B2"
COAL_LABEL = "Pertambangan Batubara dan Lignit"

# Revision status of each year, which every value cell's marker and the var 2268 note must both give
STATUS_BY_YEAR = {2024: "*", 2025: "**"}

# Cells BPS prints as 0,00 with no marker, written as 0 with an empty status: (province, sector, year)
NO_MARKER_CELLS = {("81", "C13", 2024), ("81", "C13", 2025)}

# Cells BPS prints as an en dash, read from opening the 76 tables: sector -> provinces, the same 172 cells in
# 2024 and in 2025. These are the only keys the CSV leaves out, and the build stops if a table prints an en
# dash in any other cell or a value in any of these
NONE_OR_ZERO_CELLS = {
    "A1c": ["31"],
    "A2": ["31"],
    "B1": ["13", "17", "34", "51", "52", "53", "61", "74", "75", "76", "82", "94", "95", "96", "97"],
    "B2": ["12", "18", "19", "21", "31", "32", "33", "34", "35", "51", "52", "53", "71", "72", "74", "75", "81",
           "82", "91", "94", "95", "96", "97"],
    "B3": ["16", "31", "33", "34", "51", "95", "97"],
    "C1": ["12", "17", "19", "21", "34", "51", "52", "53", "61", "62", "63", "71", "73", "74", "75", "76", "81",
           "82", "94", "95", "96", "97"],
    "C3": ["14", "19", "31", "61", "62", "63", "64", "65", "71", "75", "76", "81", "82", "91", "92", "94", "95",
           "96", "97"],
    "C5": ["14", "18", "19", "52", "53", "62", "63", "74", "75", "76", "81", "82", "97"],
    "C9": ["82", "97"],
    "C11": ["11", "13", "14", "15", "34", "51", "53", "62", "63", "65", "75", "76", "91", "92", "94", "95", "96",
            "97"],
    "C13": ["13", "14", "17", "19", "52", "53", "71", "72", "73", "74", "76", "82", "91", "92", "94", "95", "96",
            "97"],
    "C14": ["53", "97"],
    "H1": ["14", "15", "17", "19", "21", "51", "52", "53", "61", "62", "63", "64", "65", "71", "72", "73", "74",
           "75", "76", "81", "82", "91", "92", "94", "95", "96", "97"],
    "H3": ["34", "97"],
    "H4": ["34"],
    "K4": ["97"],
}

# Keys (province, sector, year) whose SIMDASI value, kept here, differs from the var 2268 value, each with the
# sibling datasets whose CSVs hold the WebAPI value for it under the same indicator code. The build stops
# unless these are exactly the keys at which SIMDASI and var 2268 differ, so the note naming them holds
WEBAPI_VALUE_IN = {
    ("12", "TOTAL", "2024"): ["data/20261102_bps-province-grdp-population",
                              "data/20261103_bps-province-grdp-2010-2025"],
    ("13", "A", "2025"): ["data/20261102_bps-province-grdp-population"],
}

# The var 2268 period that holds the annual value
ANNUAL = "Tahunan"

# Tolerances: identities within the rounding of 2-decimal values, and one unit in the last decimal
# between SIMDASI and var 2268, which BPS rounds table by table
TOL_SUM = 0.05     # Rp billion
TOL_CROSS = 0.01   # Rp billion

# Plausibility ranges; a value outside its range is flagged, not dropped, and a range ending in None is open above
PLAUSIBLE = {
    "coal_share_pct": (0, 40),            # B2 / TOTAL x 100
    "grdp_growth_pct": (-20, 40),         # TOTAL 2025 / TOTAL 2024 x 100 - 100, current prices
    "sector_growth_pct": (-50, 100),      # 2025 / 2024 x 100 - 100 of every sector, TOTAL included, current prices
    "sector_growth_from_zero": (0, 0),    # the 2025 value, Rp billion, of a sector whose 2024 value is 0
    "value_nonnegative": (0, None),       # every value, Rp billion
}

# Where the raw files come from; each WebAPI request also ends in /key/ and a registered key, left out here
URL_PROVINCES = "https://sig.bps.go.id/rest-bridging/getwilayah?level=provinsi&periode_merge=2025_1.2025"
URL_TABLE = ("https://webapi.bps.go.id/v1/api/interoperabilitas/datasource/simdasi/id/25/wilayah/<kode_bps>00000"
             "/tahun/<year>/id_tabel/S1RMUWRYb0NWc0Y5L05QQkxzcWw3Zz09")
URL_2268 = "https://webapi.bps.go.id/v1/api/list/model/data/domain/0000/var/2268/th/124:125"


# Functions

def sector_list():
    """Return the 62 sector codes in table order, each mapped to (level, parent code)."""
    sectors = {}
    for group in GROUPS:
        sectors[group] = ("category", TOTAL)
        for n in range(1, SUBCATEGORIES.get(group, 0) + 1):
            sub = f"{group}{n}"
            sectors[sub] = ("subcategory", group)
            for letter in ITEMS.get(sub, ""):
                sectors[sub + letter] = ("item", sub)
    sectors[TOTAL] = ("total", None)
    return sectors


def group_code(printed, where):
    """Return the dataset code of a category from the code a table prints, such as MN for 'M,N'."""
    codes = {p: code for code, p in GROUPS.items()}
    if printed not in codes:
        raise ValueError(f"{where}: category {printed!r} is not one of the 17 groups")
    return codes[printed]


def sector_code(record, where):
    """Return a SIMDASI row's sector code from its category, sub-category number and item letter."""
    # The one row outside the hierarchy is the province total, matched by its label
    if record["category"] is None:
        if record["label"] != TOTAL_LABELS["simdasi"]:
            raise ValueError(f"{where}: row {record['label']!r} has no category and is not the total row")
        return TOTAL
    return group_code(record["category"], where) + (record["subcategory"] or "") + (record["item"] or "")


def sector_name(sector, level, label):
    """Return a sector's name: its label_raw without the code a category prints, and for TOTAL the var 2268 label."""
    if level == "total":
        return TOTAL_LABELS["var 2268"]
    if level != "category":
        return label
    # A category's label_raw starts with the code it prints and a space, as in 'M,N Jasa Perusahaan'
    printed = GROUPS[sector] + " "
    if not label.startswith(printed):
        raise ValueError(f"category {sector} is {label!r}, expected it to start with {printed!r}")
    return label[len(printed):]


def read_table(path, code, name, year, lookup, sectors):
    """Read one SIMDASI table into its description and its cells by sector code, in table order."""
    table, records = cleaning.read_simdasi_table(path, year, name, **READ_CONTEXT[path])
    # Map the table's area name to a BPS code through the province list; it must be the file's code
    cleaning.province_code(table["area"], lookup, code)
    # The title and the one column must still name GRDP at current prices by industry
    cleaning.require_text(table["title"], TITLE_TEXT, f"{path.name} title")
    if len(table["columns"]) != 1:
        raise ValueError(f"{path.name}: {len(table['columns'])} columns, expected 1")
    cleaning.require_text(next(iter(table["columns"].values()))["name"], COLUMN_TEXT, f"{path.name} column")
    # Every row maps to its own sector code, and the codes run in the expected table order
    cells = {}
    for r in records:
        sector = sector_code(r, path.name)
        if sector in cells:
            raise ValueError(f"{path.name}: two rows map to sector {sector}")
        cells[sector] = r
    if list(cells) != list(sectors):
        raise ValueError(f"{path.name}: rows map to {list(cells)}, expected {list(sectors)}")
    return table, cells


def read_2268(path, lookup):
    """Read var 2268's annual values of the 17 categories and TOTAL, and the status its note gives each year."""
    table, records = cleaning.read_webapi_table(path, **READ_CONTEXT[path])
    values = {}
    for r in records:
        # Keep the annual values; the quarters are not part of this dataset
        if r["turtahun_label"] != ANNUAL:
            continue
        # Match the province by its vervar value and label, and the industry by its label
        code = cleaning.webapi_region_code(r["vervar"], r["vervar_label"], lookup)
        label = r["turvar_label"]
        sector = TOTAL if label == TOTAL_LABELS["var 2268"] else group_code(label.split(" ", 1)[0], path.name)
        key = (code, sector, str(r["year"]))
        if key in values:
            raise ValueError(f"{path.name}: two annual values for {key}")
        values[key] = r["value"]
    return values, cleaning.parse_status_note(table["var"][0]["note"]), table


def identity_checks(rows, none_or_zero, sectors):
    """Layer 3: each level sums to its parent, counting the en-dash cells as zero."""
    cells = pd.DataFrame([{k: r[k] for k in ("province_code", "sector", "period", "value")} for r in rows]
                         + [{**c, "value": 0.0} for c in none_or_zero])
    cells["level"] = cells["sector"].map(lambda s: sectors[s][0])
    cells["parent"] = cells["sector"].map(lambda s: sectors[s][1])
    # Every cell, indexed so that a parent's own value lines up with the sum of its parts
    totals = cells.set_index(["province_code", "period", "sector"])["value"].rename_axis(["province_code", "period", "parent"])
    results = []
    for level, label in [("category", "17 categories sum to TOTAL"),
                         ("subcategory", "numbered sub-categories sum to their category"),
                         ("item", "lettered items A1a-A1e sum to A1")]:
        parts = cells[cells["level"] == level].groupby(["province_code", "period", "parent"])["value"].sum()
        results.append(cleaning.check_sum(parts, totals.reindex(parts.index), TOL_SUM,
                                          f"{label}, en-dash cells counted as zero"))
    return results


def year_on_year(values, codes, sectors):
    """Return the change (%) from the year before of every province and sector with a value in both years, and
    apart from them the later values of those whose earlier value is 0, which have no growth rate."""
    growth, from_zero = [], []
    for c in codes:
        for s in sectors:
            for y in YEARS[1:]:
                now, before = values.get((c, s, str(y))), values.get((c, s, str(y - 1)))
                if now is None or before is None:
                    continue
                # Each row keeps both values it compares, so a flag shows them
                row = {"province_code": c, "sector": s, "period": str(y),
                       "rp_billion": {str(y - 1): before, str(y): now}}
                if before == 0:
                    from_zero.append({**row, "value": now})
                else:
                    growth.append({**row, "value": 100 * (now / before - 1)})
    return growth, from_zero


def flag_range(rows, check):
    """Layer 5: flag the rows whose value lies outside the check's stated range, which None leaves open above."""
    low, high = PLAUSIBLE[check]
    flags = cleaning.flag_outside(rows, check, low, math.inf if high is None else high)
    # Each flag states the range as declared, since JSON has no infinity
    return [{**f, "range": [low, high]} for f in flags]


def plausibility_flags(rows, values, codes, sectors):
    """Layer 5: the coal share of GRDP, the growth of TOTAL and of every sector, and every value, against their
    stated ranges. Returns the flags and how many values each check read."""
    share = [{"province_code": c, "period": p, "value": 100 * v / values[(c, TOTAL, p)]}
             for (c, s, p), v in values.items() if s == COAL]
    growth, from_zero = year_on_year(values, codes, sectors)
    read = {
        "coal_share_pct": share,
        "grdp_growth_pct": [g for g in growth if g["sector"] == TOTAL],
        "sector_growth_pct": growth,
        "sector_growth_from_zero": from_zero,
        "value_nonnegative": [{k: r[k] for k in ("province_code", "sector", "period", "value")} for r in rows],
    }
    flags = [f for check, checked in read.items() for f in flag_range(checked, check)]
    return flags, {check: len(checked) for check, checked in read.items()}


def general_title(title, area, year):
    """Return a table title with its province and year replaced by placeholders and spaces collapsed."""
    return " ".join(title.replace(area, "<province>").replace(str(year), "<year>").split())


# Steps

# Print in UTF-8 so BPS labels and markers show on any console
sys.stdout.reconfigure(encoding="utf-8")

# Read the BPS province list that every province name and code is matched against; load_bps_provinces
# reads UTF-8, so a list declared in another encoding stops the build
if READ_CONTEXT[RAW_PROVINCES]["encoding"] != "utf-8":
    raise ValueError(f"{RAW_PROVINCES.name} is declared {READ_CONTEXT[RAW_PROVINCES]}, but is read as UTF-8")
provinces, lookup = cleaning.load_bps_provinces(RAW_PROVINCES)
codes = [c for c in provinces if c != cleaning.NATIONAL_CODE]

# Stop unless both download scripts the metadata names are in the repository
for script in (DOWNLOAD_SCRIPT, DOWNLOAD_SCRIPT_2268):
    if not (ROOT / script).is_file():
        raise FileNotFoundError(f"download script {script} not found")

# Stop unless the folder holds exactly one table for every province and year
paths = {(c, y): RAW_TABLE_DIR / RAW_TABLE_NAME.format(code=c, year=y) for c in codes for y in YEARS}
if set(paths.values()) != set(RAW_TABLES):
    missing = sorted(p.name for p in set(paths.values()) - set(RAW_TABLES))
    extra = sorted(p.name for p in set(RAW_TABLES) - set(paths.values()))
    raise ValueError(f"SIMDASI tables missing {missing}, unexpected {extra}")

# Build the 62 sector codes in table order, with their levels and parents
sectors = sector_list()

# Read every table: a value becomes a row, and an en-dash cell is listed for the metadata
labels, tables, rows, none_or_zero, unmarked = {}, {}, [], [], set()
for (code, year), path in paths.items():
    table, cells = read_table(path, code, provinces[code]["name"], year, lookup, sectors)
    tables[(code, year)] = table
    for sector, r in cells.items():
        # Every table must give a sector the same label
        if labels.setdefault(sector, r["label"]) != r["label"]:
            raise ValueError(f"{path.name}: {sector} is {r['label']!r}, other tables say {labels[sector]!r}")
        # An en-dash cell has no value, so it gets no row
        if r["value"] is None:
            none_or_zero.append({"province_code": code, "sector": sector, "period": str(year)})
            continue
        # A value carries its year's marker, except the cells declared as a 0,00 printed without one
        if (code, sector, year) in NO_MARKER_CELLS:
            if r["value_code"] or r["value"] != 0:
                raise ValueError(f"{path.name}: {sector} was declared 0,00 without a marker, "
                                 f"but holds {r['value']} [{r['value_code']}]")
            unmarked.add((code, sector, year))
        elif r["value_code"] != STATUS_BY_YEAR[year]:
            raise ValueError(f"{path.name}: {sector} carries marker {r['value_code']!r}, "
                             f"expected {STATUS_BY_YEAR[year]!r} for {year}")
        rows.append({"province_code": code, "indicator": INDICATOR, "sector": sector, "period": str(year),
                     "status": r["value_code"], "value": r["value"]})

# Stop unless every declared cell without a marker was found as such
if unmarked != NO_MARKER_CELLS:
    raise ValueError(f"cells declared without a marker but not found so: {sorted(NO_MARKER_CELLS - unmarked)}")

# Stop unless the en-dash cells the tables print are exactly the declared ones, in every year
declared = {(c, s, str(y)) for s, cs in NONE_OR_ZERO_CELLS.items() for c in cs for y in YEARS}
found = {(c["province_code"], c["sector"], c["period"]) for c in none_or_zero}
if found != declared:
    raise ValueError(f"en-dash cells differ from NONE_OR_ZERO_CELLS: printed but not declared "
                     f"{sorted(found - declared)}, declared but not printed {sorted(declared - found)}")

# Stop unless the coal row still carries the coal and lignite mining label
if labels[COAL] != COAL_LABEL:
    raise ValueError(f"{COAL} is {labels[COAL]!r}, expected {COAL_LABEL!r}")

# Stop unless every table has the same marker legend, note and source line, which the metadata keeps once
first = tables[next(iter(tables))]
for (code, year), table in tables.items():
    for field in ("legend", "notes", "source"):
        if table[field] != first[field]:
            raise ValueError(f"{code} {year}: table {field} {table[field]!r} differs from {first[field]!r}")

# List the en-dash cells in the CSV's order: province, then sector in table order, then period
order = {s: i for i, s in enumerate(sectors)}
none_or_zero.sort(key=lambda c: (c["province_code"], order[c["sector"]], c["period"]))

# Read var 2268's annual values for the 17 categories and TOTAL, and the status its note gives each year
annual_2268, status_2268, table_2268 = read_2268(RAW_2268, lookup)

# Layer 4: the 17 categories and TOTAL must be in both sources and agree within the stated tolerance
values = {(r["province_code"], r["sector"], r["period"]): r["value"] for r in rows}
groups_simdasi = {k: v for k, v in values.items() if sectors[k[1]][0] in ("category", "total")}
if set(groups_simdasi) != set(annual_2268):
    raise ValueError(f"var 2268 annual keys differ: {sorted(set(groups_simdasi) ^ set(annual_2268))[:10]}")
cross = cleaning.compare_sources(groups_simdasi, annual_2268, TOL_CROSS,
                                 "SIMDASI 17 categories and TOTAL = var 2268 annual (Tahunan)")
cross["note"] = ("BPS rounds each table separately, so the two may differ by 0.01 in the last decimal; "
                 "the CSV keeps the SIMDASI value. Keys are [province_code, sector, period].")

# Stop unless SIMDASI and var 2268 differ at exactly the keys that the note on the sibling datasets names
differing = {tuple(d["key"]) for d in cross["differences"]}
if differing != set(WEBAPI_VALUE_IN):
    raise ValueError(f"SIMDASI and var 2268 differ at {sorted(differing)}, but WEBAPI_VALUE_IN names "
                     f"{sorted(WEBAPI_VALUE_IN)}; compare the sibling datasets and update it")

# Name each key whose value here differs from the WebAPI value that the sibling datasets carry
sibling_note = (
    f"Keys whose value here differs from the sibling datasets under the same indicator code {INDICATOR}: "
    + "; ".join(f"({c}, {INDICATOR}, {s}, {p}) is {values[(c, s, p)]:.10g} here but "
                f"{annual_2268[(c, s, p)]:.10g} in {' and '.join(datasets)}"
                for (c, s, p), datasets in WEBAPI_VALUE_IN.items())
    + ". The sibling datasets carry the WebAPI value, which var 2268 gives here as well, while this dataset "
      "keeps the SIMDASI value, so an analysis that joins them chooses one source on purpose.")

# Layer 4: the var 2268 note must give each year the status that the SIMDASI cells carry
note_status = {year: status_2268.get(year) for year in YEARS}
if note_status != STATUS_BY_YEAR:
    raise ValueError(f"var 2268 note gives {note_status}, SIMDASI cells carry {STATUS_BY_YEAR}")
status_check = {"check": "status by year: SIMDASI cell markers = var 2268 note",
                "status": {str(y): s for y, s in STATUS_BY_YEAR.items()}}

# Layers 3 and 5: identities stop the build; plausibility only flags
identities = identity_checks(rows, none_or_zero, sectors)
flags, plausibility_compared = plausibility_flags(rows, values, codes, sectors)

# Name each sector: its label_raw without the code a category prints, and TOTAL as var 2268 labels it
names = {s: sector_name(s, level, labels[s]) for s, (level, _) in sectors.items()}

# Describe the dataset
meta = {
    "title": "BPS provincial GRDP at current prices by detailed industry, Indonesia, 2024-2025",
    "columns": {
        "province_code": "BPS province code (kode_bps) of the 38 provinces; there is no Indonesia row. Names and Kemendagri codes in 'provinces'.",
        "indicator": "Indicator code; definition in 'indicators'.",
        "sector": "Industry code: the 17 KBLI categories, their numbered sub-categories and lettered items, and TOTAL. Names, levels and parents in 'sectors'.",
        "period": "YYYY = annual.",
        "status": "BPS revision marker of each cell; meanings in 'status'.",
        "value": "Rp billion at current prices, as published by BPS. Multiply by 'multiplier' for rupiah.",
    },
    "provinces": {c: provinces[c] for c in codes},
    "province_source": {"url": URL_PROVINCES, "file": RAW_PROVINCES.relative_to(ROOT).as_posix(),
                        "note": "BPS and Kemendagri codes differ for the six Papua provinces; join other datasets on the code system they use."},
    "sectors": {s: {"name": names[s], "label_raw": labels[s], "level": level, "parent": parent}
                for s, (level, parent) in sectors.items()},
    "sector_notes": [
        f"The 17 KBLI categories use the codes of data/20261102_bps-province-grdp-population, where MN and RSTU are the "
        f"categories BPS prints as M,N and R,S,T,U. A numbered sub-category appends its number to its category "
        f"({COAL} = {names[COAL]}, coal and lignite mining), and a lettered item appends its letter to its sub-category "
        f"(A1a = {names['A1a']}). TOTAL is the province's GRDP, the table's last row.",
        f"'label_raw' is each row's label_raw as BPS publishes it, and 'name' is the same text without the code a "
        f"category prints ('{labels['MN']}' is named '{names['MN']}'). TOTAL's label_raw reads '{labels[TOTAL]}', so "
        f"TOTAL is named '{names[TOTAL]}', as var 2268 labels the same row.",
        "Each level sums to its parent: the 17 categories to TOTAL, the numbered sub-categories to their category, and "
        "A1a-A1e to A1. Summing every row under A (A1, A1a-A1e, A2 and A3) would double count A1's items, so add up "
        "one level at a time.",
        f"Categories {', '.join(g for g in GROUPS if g not in SUBCATEGORIES)} have no sub-categories.",
    ],
    "indicators": {
        INDICATOR: {
            "name": "Produk Domestik Regional Bruto atas dasar harga berlaku menurut lapangan usaha (GRDP at current prices by industry)",
            "unit": "Rp billion (miliar rupiah)", "multiplier": 1e9, "base_unit": "Rp",
            "decimals": SIMDASI_FORMAT["decimals"],
            "periods": "2024 and 2025, annual",
            "source": URL_TABLE,
            "download_script": DOWNLOAD_SCRIPT,
            "table": general_title(first["title"], first["area"], first["year"]),
            "table_en": general_title(first["title_en"], first["area"], first["year"]),
            "column": next(iter(first["columns"].values()))["name"],
            "notes": [
                f"BPS table note: {first['notes']}",
                f"BPS source line: {first['source']}",
                "BPS publishes no Indonesia row in these tables; the sum of provincial GRDP is not national GDP.",
                f"BPS publishes every value with {SIMDASI_FORMAT['decimals']} decimals, which the build checks; the "
                "CSV writes each value without trailing zeros, so a value BPS prints as 1.234,50 is written 1234.5.",
            ],
        },
    },
    "legend": {"note": "The marker legend (keterangan_data) of the SIMDASI tables, as published; all 76 tables carry the same legend.",
               "markers": first["legend"]},
    "none_or_zero_cells": {
        "marker": NONE_OR_ZERO,
        "meaning": f"{first['legend'][NONE_OR_ZERO]} (none or zero)",
        "rule": "BPS prints these cells as an en dash with no value. They have no row in the CSV; an analysis may "
                "treat each listed cell as 0 Rp billion, as the identity checks do. Every other cell has a row.",
        "count": len(none_or_zero),
        "cells": none_or_zero,
    },
    "source_tables": {c: {str(y): {"table_updated": tables[(c, y)]["table_updated"],
                                   "change_log": tables[(c, y)]["change_log"]} for y in YEARS} for c in codes},
    "cross_check_source": {
        "url": URL_2268, "file": RAW_2268.relative_to(ROOT).as_posix(),
        "download_script": DOWNLOAD_SCRIPT_2268,
        "table": table_2268["var"][0]["label"], "last_update": table_2268["last_update"],
        "note": cleaning.html_to_text(table_2268["var"][0]["note"]),
        "use": "Annual (Tahunan) values of the 17 categories and TOTAL, compared with the SIMDASI values; its quarterly values are not used.",
    },
    "notes": [
        "Every value comes from the SIMDASI yearbook table of its province and year, the only source of the 62 rows, so "
        "all rows of a province and year come from one table and its sums hold. Var 2268 gives the same 17 categories "
        "and TOTAL; they match within 0.01 Rp billion, and every difference is listed under checks.cross_source.",
        "Status is each cell's marker: * (Angka sementara) for 2024 and ** (Angka sangat sementara) for 2025. The var "
        "2268 note gives the same status for each year.",
        f"Maluku (81) C13 {names['C13']} is printed as 0,00 with no status marker in 2024 and in 2025, unlike every "
        "other value cell. It is written as 0 with an empty status: it is a published zero, not an en-dash cell.",
        "Each table's change_log under source_tables is BPS's revision history of that yearbook table, kept as "
        "published; the status column follows each cell's marker, not the change log.",
        "All 38 provinces, including Papua Barat Daya (92), Papua Selatan (95), Papua Tengah (96) and Papua "
        "Pegunungan (97), have their own table for 2024 and 2025, so the Papua split leaves no gap.",
        sibling_note,
        "Coal share of GRDP (%) = B2 / TOTAL x 100, GRDP growth (%) = TOTAL 2025 / TOTAL 2024 x 100 - 100 and "
        "sector growth (%) = sector 2025 / sector 2024 x 100 - 100, all at current prices; none is stored because "
        "all are derived. A sector whose 2024 value is 0 has no growth rate and is checked under "
        "sector_growth_from_zero instead.",
        "checks.flags lists every value or change outside its range in checks.plausible_ranges for a person to "
        "review, and a growth flag gives the two values it compares under rp_billion; a flag stays whether it "
        "reflects a real event or a source error.",
    ],
    "checks": {
        "passed": ["identities", "cross-source"],
        "identities": identities,
        "cross_source": [cross, status_check],
        "none_or_zero_declared": {
            "check": "en-dash cells the tables print = NONE_OR_ZERO_CELLS declared in the build, the same in every "
                     "year; completeness expects every other key of the full grid of provinces, sectors and years",
            "per_year": {str(y): sum(1 for c in none_or_zero if c["period"] == str(y)) for y in YEARS},
        },
        "plausible_ranges": PLAUSIBLE,
        "plausibility_compared": plausibility_compared,
        "flags": flags,
    },
}

# Layers 1, 2 and 6: every key of the full grid except the declared en-dash cells must be present; write the
# CSV and metadata
expected = {(c, INDICATOR, s, str(y)) for c in codes for s in sectors for y in YEARS}
expected -= {(c, INDICATOR, s, p) for c, s, p in declared}
out = cleaning.write_dataset(
    rows, KEYS,
    allowed={"province_code": codes, "indicator": [INDICATOR], "sector": list(sectors)},
    expected=expected,
    csv_path=OUT_CSV, meta=meta, raw_files=[RAW_PROVINCES, *paths.values(), RAW_2268],
    sort_orders={"sector": list(sectors)},
)

# Report what was written
print(f"{OUT_CSV.name}: {len(out)} rows, {len(none_or_zero)} en-dash cells listed, {len(flags)} plausibility flags")
print(out.groupby(["period", "status"]).size().to_string())
for check in identities:
    print("  identity:", check)
print(f"  cross-source: {cross['compared']} compared, differences {cross['differences']}")
print(f"  plausibility: values compared {plausibility_compared}")
for f in flags:
    print("  flag:", f)
