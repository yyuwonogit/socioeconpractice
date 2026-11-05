from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# Load the shared cleaning module from tools/
import sys
sys.path.insert(0, str(ROOT / "tools"))
import cleaning

# Modules for the raw JSON fields read_simdasi_table does not return, footnote markers and the identity sums
import json
import re

import pandas as pd

# Parameters

# Raw inputs. BPS static table 945 holds every year from 2011 to 2025 in one HTML table and gives every value in the
# CSV. The BPS statistics table of the same series (tablestatistic), one file per year from 2017 to 2025, repeats
# those years and is read only as the lower-priority copy
RAW_PROVINCES = ROOT / "raw/province-codes/20261102_bps-province-codes-2025-s1.json"
RAW_DIR = ROOT / "raw/household-spending"
RAW_STATIC = RAW_DIR / "20261103_bps-per-capita-expenditure-by-province-2011-2025-static-table.json"
YEARS = list(range(2011, 2026))
YEARLY_YEARS = list(range(2017, 2026))
RAW_YEARLY = {year: RAW_DIR / f"20261103_bps-per-capita-expenditure-by-province-{year}.json" for year in YEARLY_YEARS}
DOWNLOAD_SCRIPT = "raw/household-spending/20261103_download-bps-per-capita-expenditure-by-province.py"

# Output; the metadata JSON is written beside it with a -metadata suffix
OUT_CSV = HERE / "20261103_bps-province-household-spending.csv"

# Excel writes padding as a span with this style holding one no-break space, before or after some numbers;
# cleaning.excel_grid reads the static table's HTML and keeps that padding apart from the digits
PADDING_STYLE = cleaning.EXCEL_PADDING_STYLE

# How each raw file is written, read from opening the files; all eleven are UTF-8 JSON without a byte-order mark.
# The province list is 38 records whose fields are all text. In the static table, data.table is an HTML page that
# Excel wrote (Publish as Web Page): its meta tag names windows-1252, but the page arrives as a JSON string already
# decoded from UTF-8, so no second decoding applies. Each value cell shows whole rupiah in the number format
# "#\ ###\ ##0", a space (U+0020) between digit groups and no decimals, under a style whose displayed decimal mark is
# '.'; Excel pads some numbers with a no-break space in a padding span, before or after the digits; an empty cell
# holds &nbsp;; a cell without a value holds '-'; the unit sits in the title as '(rupiah)'; and a region name may
# end in a footnote marker such as ' 1)'. The yearly tables write each value as Indonesian text (1.053.803,48) with
# the 2 decimals each column declares, a row without values carries '...' for each column, and the title carries
# '(rupiah)' in every year except 2019, whose title names no unit; 2019 is read without a unit check, and its values
# equal the static table's rupiah values exactly (checks.cross_source)
STATIC_FORMAT = {"encoding": "utf-8", "decimal": ".", "thousands": " ", "decimals": 0, "number_format": '"#\\ ###\\ ##0"',
                 "padding": PADDING_STYLE, "empty": "&nbsp; or nothing", "missing": ["-"], "unit_text": "(rupiah)",
                 "footnote_marker": r"(.*?)\s+(\d+\))"}
YEARLY_FORMAT = {"encoding": "utf-8", "decimal": ",", "thousands": ".", "decimals": 2, "unit_text": "(rupiah)",
                 "missing": ["..."]}
YEARLY_NO_UNIT = {2019: "the 2019 title names no unit"}
READ_CONTEXT = {
    RAW_PROVINCES: {"encoding": "utf-8"},
    RAW_STATIC: STATIC_FORMAT,
    **{path: {**YEARLY_FORMAT, "unit_text": None if year in YEARLY_NO_UNIT else YEARLY_FORMAT["unit_text"]}
       for year, path in RAW_YEARLY.items()},
}

# Key columns and the one indicator
KEYS = ["province_code", "indicator", "item", "period"]
INDICATOR = "spending_per_capita_month"

# Item code of each static table header and of each yearly table column, in output order
ITEMS = {"Makanan": "food", "Bukan makanan": "non_food", "Jumlah": "total"}
ITEM_ORDER = list(ITEMS.values())
YEARLY_COLUMNS = {
    "Rata-rata Pengeluaran per Kapita Sebulan di Perkotaan dan Perdesaan - Makanan": "food",
    "Rata-rata Pengeluaran per Kapita Sebulan di Perkotaan dan Perdesaan - Bukan Makanan": "non_food",
    "Rata-rata Pengeluaran per Kapita Sebulan di Perkotaan dan Perdesaan - Jumlah": "total",
}
ITEM_NAMES = {"food": "Makanan (food)", "non_food": "Bukan makanan (non-food)",
              "total": "Jumlah (food and non-food together)"}

# Text the tables must still carry, so that another table under the same address stops the build
STATIC_ID = 945
STATIC_TITLE_TEXT = ("Pengeluaran per Kapita Sebulan Untuk Makanan dan Bukan Makanan di Daerah Perkotaan dan Perdesaan "
                     "Menurut Provinsi")
STATIC_PERIOD_TEXT = "2011-2025"
STATIC_HEADER = "Provinsi"
STATIC_SOURCE_PREFIX = "Sumber"
YEARLY_TITLE_TEXT = ("Rata-rata Pengeluaran per Kapita Sebulan Makanan dan Bukan Makanan di Daerah Perkotaan dan "
                     "Perdesaan Menurut Provinsi")
YEARLY_AREA = "Indonesia"

# First year with a value of each region whose series starts after 2011, read from opening the static table; every
# earlier cell of these rows is printed '-'. Every other region, Indonesia included, has all three items in every year
FIRST_YEAR = {"65": 2015, "92": 2024, "95": 2024, "96": 2024, "97": 2024}
SPLIT_NOTE = "the 2023 yearly table's note says its 2023 figures still follow those of"
FIRST_YEAR_REASON = {
    "65": "Kalimantan Utara became a province in 2012; the static table prints '-' for 2011-2014 under its footnote "
          "1), 'Data masih bergabung dengan Provinsi Kalimantan Timur' (data still combined with Kalimantan Timur)",
    "92": f"Papua Barat Daya became a province in 2022; the static table prints '-' for 2011-2023, and {SPLIT_NOTE} "
          f"Papua Barat",
    "95": f"Papua Selatan became a province in 2022; the static table prints '-' for 2011-2023, and {SPLIT_NOTE} Papua",
    "96": f"Papua Tengah became a province in 2022; the static table prints '-' for 2011-2023, and {SPLIT_NOTE} Papua",
    "97": f"Papua Pegunungan became a province in 2022; the static table prints '-' for 2011-2023, and {SPLIT_NOTE} "
          f"Papua",
}

# Years in which a province's area changes, so that its change from the year before compares different areas
BORDER_CHANGES = {
    ("64", "2015"): "Kalimantan Timur: 2014 includes Kalimantan Utara, 2015 does not",
    ("91", "2024"): "Papua Barat: 2023 includes Papua Barat Daya, 2024 does not",
    ("94", "2024"): "Papua: 2023 includes Papua Selatan, Papua Tengah and Papua Pegunungan, 2024 does not",
}

# Food + non_food - total, in rupiah, where the static table's three values do not add up within rounding: Nusa
# Tenggara Barat in 2012 prints 291 176 + 234 901 = 526 077 against a total of 484 661. No other raw file holds 2012,
# so which value is wrong cannot be told here; all three are kept as published, the gap is declared exactly, the
# build stops if it changes, and checks.flags lists it for review
IDENTITY_BREAKS = {("52", "2012"): 41416}
IDENTITY_BREAK_REASON = ("BPS's own inconsistency inside static table 945, read correctly: the row's food, non_food and "
                         "total cells sit in their columns and parse cleanly, and every other region and year adds up "
                         "within 1 rupiah. No other raw file holds 2012, so the three values are kept as published")

# The year whose static totals are the static food plus the static non_food, each already rounded, so that a total
# can differ from the yearly table's total, rounded on its own, by up to 1 rupiah
ROUNDED_PARTS_YEAR = "2018"

# Tolerances, in rupiah
TOL_SUM = 1      # food, non_food and total are each rounded to whole rupiah, so food + non_food - total is -1, 0 or 1
TOL_CROSS = 1    # the static table's whole rupiah against the yearly tables' 2 decimals; see ROUNDED_PARTS_YEAR
HALF = 0.5       # the largest gap that rounding one value to whole rupiah leaves

# Plausibility ranges; a value outside its range is flagged, not dropped
PLAUSIBLE = {
    "spending_rupiah": (100_000, 5_000_000),                 # every value, rupiah per person per month
    "spending_change_pct": (-10, 25),                        # value in year t / value in year t-1 x 100 - 100
    "food_plus_non_food_minus_total": (-TOL_SUM, TOL_SUM),   # rupiah, every region and year
}

# Where the raw files come from; each WebAPI request ends in /key/ and a registered key, which is not stored
URL_PROVINCES = "https://sig.bps.go.id/rest-bridging/getwilayah?level=provinsi&periode_merge=2025_1.2025"
URL_STATIC = "https://webapi.bps.go.id/v1/api/view/domain/0000/model/statictable/lang/ind/id/945/key/<key>/"
URL_YEARLY = ("https://webapi.bps.go.id/v1/api/view/domain/0000/model/tablestatistic/id/"
              "V1ZKMWVrSTNOek5ZZUZOcVZEZGFValJvV0hWalFUMDkjMyMwMDAw/lang/ind/key/<key>/?year=<year>")


# Functions

def read_static(path, lookup):
    """Read static table 945: its description, one value per region, item and year, and the cells printed '-'.

    Rows are matched by what they say: the title row by the title, the header by 'Provinsi', the year row under it,
    the data rows by region name until the first empty row, and the notes after them. Every value cell must parse as
    READ_CONTEXT declares or carry a declared missing marker, and every row outside these must be empty.
    """
    context = READ_CONTEXT[path]
    reply = json.loads(path.read_text(encoding=context["encoding"]))
    data = reply.get("data") or {}
    if reply.get("status") != "OK" or reply.get("data-availability") != "available" or data.get("table_id") != STATIC_ID:
        raise ValueError(f"{path.name}: not static table {STATIC_ID} ({reply.get('status')}, {data.get('table_id')})")

    # The title must still name the series, its unit and its years
    title = cleaning.HTML_SPACE.sub(" ", data["title"]).strip()
    for text in (STATIC_TITLE_TEXT, context["unit_text"], STATIC_PERIOD_TEXT):
        cleaning.require_text(title, text, f"{path.name} title")

    # The style must declare the decimal mark READ_CONTEXT gives, and each value cell's class the declared format
    page = data["table"]
    cleaning.require_text(page, f'mso-displayed-decimal-separator:"{context["decimal"]}"', f"{path.name} style")
    formats = cleaning.excel_number_formats(page)
    grid = cleaning.excel_grid(page)

    # The title row is the first row with text, and the table's own title is its only text
    filled = [i for i, row in enumerate(grid) if cleaning.excel_own_texts(row)]
    title_row = filled[0]
    first_row = cleaning.excel_own_texts(grid[title_row])
    if first_row != [title]:
        raise ValueError(f"{path.name}: first row {first_row} is not the title {title!r}")

    # The header row starts with 'Provinsi', spanning the item row and the year row under it
    header = next((i for i, row in enumerate(grid) if row[0][0] == STATIC_HEADER and row[0][2]), None)
    if (header is None or grid[header][0][1]["rowspan"] != 2
            or any(cleaning.excel_own_texts(r) for r in grid[title_row + 1:header])):
        raise ValueError(f"{path.name}: no '{STATIC_HEADER}' header two rows high after the title and empty rows")
    columns = {}
    for j in range(1, len(grid[header])):
        item_text, year_text, year_own = grid[header][j][0], grid[header + 1][j][0], grid[header + 1][j][2]
        if item_text not in ITEMS or not year_own or not re.fullmatch(r"\d{4}", year_text):
            raise ValueError(f"{path.name}: column {j} is headed {item_text!r} / {year_text!r}")
        columns[j] = (ITEMS[item_text], year_text)
    expected = sorted((item, str(year)) for item in ITEM_ORDER for year in YEARS)
    if sorted(columns.values()) != expected:
        raise ValueError(f"{path.name}: the columns hold {sorted(columns.values())}, expected {expected}")

    # Data rows: every row after the year row whose first cell names a region, up to the first empty row
    values, dashes, names, markers = {}, [], {}, {}
    i = header + 2
    while i < len(grid) and grid[i][0][0]:
        row = grid[i]
        if any(not own or cell["colspan"] != 1 or cell["rowspan"] != 1 for _, cell, own in row):
            raise ValueError(f"{path.name}: data row {row[0][0]!r} has a merged cell")

        # The region is matched by name, after taking off a footnote marker such as ' 1)'
        marked = re.fullmatch(context["footnote_marker"], row[0][0])
        name = marked.group(1) if marked else row[0][0]
        code = cleaning.province_code(name, lookup)
        if code in names:
            raise ValueError(f"{path.name}: {name!r} and {names[code]!r} both map to {code}")
        names[code] = name
        if marked:
            markers.setdefault(marked.group(2), []).append(code)

        # Each cell is a number in the declared format, or the declared marker of a cell without a value
        for j, (item, period) in columns.items():
            text, cell, _ = row[j]
            key = (code, item, period)
            if formats.get(cell["class"]) != context["number_format"]:
                raise ValueError(f"{path.name}: {name} {item} {period} has number format {formats.get(cell['class'])}")
            if text in context["missing"]:
                dashes.append(key)
                continue
            # Padding belongs in a padding span; a no-break space outside one is not the declared format
            if text != text.strip():
                raise ValueError(f"{path.name}: {name} {item} {period}: white space outside a padding span in {text!r}")
            try:
                values[key] = cleaning.parse_number(text, context["decimal"], context["thousands"], context["decimals"])
            except ValueError as e:
                raise ValueError(f"{path.name}: {name} {item} {period}: {e}") from None
        i += 1

    # Every region of the BPS list and Indonesia must have its row
    if set(names) != set(lookup.values()):
        raise ValueError(f"{path.name}: rows for {sorted(names)}, expected {sorted(lookup.values())}")

    # Notes after the data rows, each in the first cell of its row: notes, footnotes and the source line
    notes, footnotes = [], {}
    for row in grid[i:]:
        texts = cleaning.excel_own_texts(row)
        if not texts:
            continue
        if texts != [row[0][0]]:
            raise ValueError(f"{path.name}: a note row has text outside its first cell: {texts}")
        notes.append(texts[0])
        footnote = re.fullmatch(r"(\d+\))\s+(.*)", texts[0])
        if footnote:
            footnotes[footnote.group(1)] = footnote.group(2)
    sources = [n for n in notes if n.startswith(STATIC_SOURCE_PREFIX)]
    if len(sources) != 1:
        raise ValueError(f"{path.name}: {len(sources)} source lines in the notes {notes}")
    if set(markers) != set(footnotes):
        raise ValueError(f"{path.name}: row markers {sorted(markers)} but footnotes {sorted(footnotes)}")

    # The notes must give no revision status, so every value is final
    if cleaning.parse_status_note("\n".join(notes)) != {}:
        raise ValueError(f"{path.name}: the notes now give revision statuses: {notes}")

    info = {"title": data["title"], "table_id": data["table_id"], "subject": data.get("subcsa"),
            "created": data.get("cr_date"), "updated": data.get("updt_date"), "notes": notes,
            "footnotes": {m: {"text": footnotes[m], "rows": markers[m]} for m in sorted(footnotes)},
            "source_line": sources[0]}
    return info, values, dashes


def simdasi_region(kode_wilayah, where):
    """Return the BPS province code of a SIMDASI kode_wilayah, such as 1100000 for 11 and '0000000' for Indonesia."""
    digits = f"{int(kode_wilayah):07d}"
    if digits[2:] != "00000":
        raise ValueError(f"{where}: kode_wilayah {kode_wilayah!r} is not a province or Indonesia")
    return cleaning.NATIONAL_CODE if digits == "0000000" else digits[:2]


def read_yearly(year, path, lookup):
    """Read one year of the statistics table: its description, its values and the cells it marks as missing."""
    context = READ_CONTEXT[path]
    table, records = cleaning.read_simdasi_table(path, year, YEARLY_AREA, **context)

    # The title must still name the series and its year; 2019 alone carries no unit text (READ_CONTEXT)
    title = " ".join(table["title"].split())
    cleaning.require_text(title, YEARLY_TITLE_TEXT, f"{path.name} title")
    if not title.endswith(f", {year}"):
        raise ValueError(f"{path.name}: title {title!r} does not end with the year")

    # Each column must be one of the three items, and the three items must all be there
    columns = {}
    for key, column in table["columns"].items():
        if column["name"] not in YEARLY_COLUMNS:
            raise ValueError(f"{path.name}: column {column['name']!r} is not one of the three items")
        columns[key] = YEARLY_COLUMNS[column["name"]]
    if sorted(columns.values()) != sorted(ITEM_ORDER):
        raise ValueError(f"{path.name}: columns give {sorted(columns.values())}")

    # Each row is matched by name, and its kode_wilayah must give the same code; a value carries no marker
    values, missing = {}, []
    for r in records:
        code = cleaning.province_code(r["label"], lookup, simdasi_region(r["kode_wilayah"], path.name))
        key = (code, columns[r["column"]], str(year))
        if key in values or key in missing:
            raise ValueError(f"{path.name}: two cells for {key}")
        if r["value"] is None:
            missing.append(key)
        elif r["value_code"]:
            raise ValueError(f"{path.name}: {key} carries marker {r['value_code']!r}")
        else:
            values[key] = r["value"]

    # Fields read_simdasi_table does not return: the years the table offers, its version and when it was made
    raw = json.loads(path.read_text(encoding=context["encoding"]))["data"][1]
    if sorted(raw["list_tahun_data"]) != YEARLY_YEARS:
        raise ValueError(f"{path.name}: the table offers {sorted(raw['list_tahun_data'])}, the folder holds {YEARLY_YEARS}")

    # The note must give no revision status
    if cleaning.parse_status_note(table["notes"]) != {}:
        raise ValueError(f"{path.name}: the note gives revision statuses: {table['notes']!r}")
    info = {"file": path.relative_to(ROOT).as_posix(), "title": table["title"], "source": table["source"],
            "notes": table["notes"], "version": raw.get("versi"), "created": raw.get("table_created"),
            "change_log": table["change_log"], "legend": table["legend"]}
    return info, values, missing


def identity_check(values):
    """Layer 3: food + non_food = total within TOL_SUM for every region and year except the declared breaks, each of
    which must keep exactly its declared gap. Returns the check and every gap, for the flags."""
    gaps = []
    for (code, item, period), total in values.items():
        if item != "total":
            continue
        food, non_food = values[(code, "food", period)], values[(code, "non_food", period)]
        gaps.append({"province_code": code, "period": period,
                     "rupiah": {"food": food, "non_food": non_food, "total": total}, "value": food + non_food - total})

    # Every key outside the declared breaks must add up within the rounding tolerance
    kept = [g for g in gaps if (g["province_code"], g["period"]) not in IDENTITY_BREAKS]
    index = pd.MultiIndex.from_tuples([(g["province_code"], g["period"]) for g in kept])
    parts = pd.Series([g["rupiah"]["food"] + g["rupiah"]["non_food"] for g in kept], index=index)
    totals = pd.Series([g["rupiah"]["total"] for g in kept], index=index)
    check = cleaning.check_sum(parts, totals, TOL_SUM,
                               f"food + non_food = total, rupiah, every region and year except declared_breaks")

    # Each declared break must still have exactly its declared gap
    found = {(g["province_code"], g["period"]): g for g in gaps}
    breaks = []
    for key, declared in IDENTITY_BREAKS.items():
        if key not in found or found[key]["value"] != declared:
            raise ValueError(f"{key}: food + non_food - total is {found.get(key, {}).get('value')}, declared {declared}")
        breaks.append({"province_code": key[0], "period": key[1], **found[key]["rupiah"],
                       "food_plus_non_food_minus_total": found[key]["value"], "declared": float(declared),
                       "reason": IDENTITY_BREAK_REASON})
    check["declared_breaks"] = breaks
    return check, gaps


def cross_check(static, yearly, missing):
    """Layer 4: every static value of 2017-2025 against its lower-priority copy in the yearly tables, within TOL_CROSS.

    Both sources must hold the same keys, the yearly tables' '...' cells must be cells the static table prints '-',
    and every gap beyond HALF must be a total of ROUNDED_PARTS_YEAR that equals the static food plus non_food.
    """
    # Compare in the CSV's order (region, item, year), so that the differences list reads like the CSV
    first = {k: static[k] for k in sorted(static, key=lambda k: (k[0], ITEM_ORDER.index(k[1]), k[2]))
             if int(k[2]) in YEARLY_YEARS}
    if set(first) != set(yearly):
        raise ValueError(f"static and yearly keys differ: {sorted(set(first) ^ set(yearly))[:10]}")
    result = cleaning.compare_sources(first, yearly, TOL_CROSS,
                                      "static table 945 = yearly statistics tables, 2017-2025, rupiah")

    # A gap beyond half a rupiah is a total the static table formed from its own rounded parts
    beyond = [d for d in result["differences"] if d["gap"] > HALF]
    for d in beyond:
        code, item, period = d["key"]
        if not (item == "total" and period == ROUNDED_PARTS_YEAR
                and static[(code, "food", period)] + static[(code, "non_food", period)] == static[(code, "total", period)]):
            raise ValueError(f"{d}: a gap beyond {HALF} that is not a {ROUNDED_PARTS_YEAR} total of rounded parts")
    result.update({
        "first": f"static table {STATIC_ID}, whole rupiah",
        "second": "statistics table, one file per year, 2 decimals (written ,00 in 2019 and 2023-2025)",
        "key": "[province_code, item, period]",
        "tolerance_reason": (f"The static table rounds to whole rupiah, so a copy with 2 decimals differs by up to {HALF} "
                             f"rupiah; its {ROUNDED_PARTS_YEAR} totals are its rounded food plus its rounded non_food, "
                             f"which differ from the total rounded on its own by up to 1"),
        "within_half_rupiah": len(result["differences"]) - len(beyond),
        "beyond_half_rupiah": {"keys": [d["key"] for d in beyond],
                               "reason": f"{ROUNDED_PARTS_YEAR} totals: the static total equals the static food plus "
                                         f"the static non_food, both already rounded (checked for each key)"},
        "exact_by_year": {str(y): sum(1 for k in first if k[2] == str(y) and first[k] == yearly[k]) for y in YEARLY_YEARS},
        "compared_by_year": {str(y): sum(1 for k in first if k[2] == str(y)) for y in YEARLY_YEARS},
    })

    # The yearly tables' '...' cells must be cells the static table has no value for
    if set(missing) & set(static):
        raise ValueError(f"yearly '...' cells hold static values: {sorted(set(missing) & set(static))}")
    result["not_compared"] = {"yearly '...' cells, '-' in the static table": [list(k) for k in sorted(missing)],
                              "static table only": f"{YEARS[0]}-{YEARLY_YEARS[0] - 1}"}
    return result


def change_rows(values):
    """Return the change (%) from the year before of every region and item with a value in both years, apart from the
    changes across a border change, which compare different areas and are listed with their reason instead."""
    changes, crossed = [], set()
    for (code, item, period), now in sorted(values.items(), key=lambda kv: (kv[0][0], ITEM_ORDER.index(kv[0][1]), kv[0][2])):
        before = values.get((code, item, str(int(period) - 1)))
        if before is None:
            continue
        if (code, period) in BORDER_CHANGES:
            crossed.add((code, period))
            continue
        changes.append({"province_code": code, "item": item, "period": period, "from_period": str(int(period) - 1),
                        "rupiah": {str(int(period) - 1): before, period: now}, "value": 100 * (now / before - 1)})

    # Every declared border change must be a change that the values hold
    if crossed != set(BORDER_CHANGES):
        raise ValueError(f"border changes declared but not in the values: {sorted(set(BORDER_CHANGES) - crossed)}")
    skipped = [{"province_code": c, "period": p, "reason": BORDER_CHANGES[(c, p)]} for c, p in sorted(BORDER_CHANGES)]
    return changes, skipped


def plausibility(rows, values, gaps):
    """Layer 5: every value, every change from the year before and every identity gap against its stated range.
    Returns the flags, how many values each check read, and the changes left out at border changes."""
    changes, skipped = change_rows(values)
    read = {
        "spending_rupiah": [{k: r[k] for k in KEYS + ["value"]} for r in rows],
        "spending_change_pct": changes,
        "food_plus_non_food_minus_total": gaps,
    }
    flags = [f for check, checked in read.items() for f in cleaning.flag_outside(checked, check, *PLAUSIBLE[check])]
    return flags, {check: len(checked) for check, checked in read.items()}, skipped


def year_span(first, last):
    """Return a span of years as text: '2011' or '2011-2014'."""
    return str(first) if first == last else f"{first}-{last}"


# Steps

# Print in UTF-8 so BPS labels and markers show on any console
sys.stdout.reconfigure(encoding="utf-8")

# Read the BPS province list that every region name is matched against; load_bps_provinces reads UTF-8, so a list
# declared in another encoding stops the build
if READ_CONTEXT[RAW_PROVINCES]["encoding"] != "utf-8":
    raise ValueError(f"{RAW_PROVINCES.name} is declared {READ_CONTEXT[RAW_PROVINCES]}, but is read as UTF-8")
provinces, lookup = cleaning.load_bps_provinces(RAW_PROVINCES)

# Stop unless the download script the metadata names is in the repository
if not (ROOT / DOWNLOAD_SCRIPT).is_file():
    raise FileNotFoundError(f"download script {DOWNLOAD_SCRIPT} not found")

# Stop unless the folder holds exactly the declared raw files
found = sorted(RAW_DIR.glob("20261103_bps-per-capita-expenditure-by-province-*.json"))
if found != sorted([RAW_STATIC, *RAW_YEARLY.values()]):
    raise ValueError(f"raw files {[p.name for p in found]} differ from the declared ones")

# Read the static table, which gives every value: one row per published cell, all final
static_info, static, dashes = read_static(RAW_STATIC, lookup)
rows = [{"province_code": c, "indicator": INDICATOR, "item": item, "period": p, "status": "", "value": v}
        for (c, item, p), v in static.items()]

# Read the yearly tables, the lower-priority copy of 2017-2025
yearly_info, yearly, yearly_missing = {}, {}, []
for year, path in RAW_YEARLY.items():
    yearly_info[str(year)], values, missing = read_yearly(year, path, lookup)
    yearly.update(values)
    yearly_missing += missing

# Stop unless every yearly table carries the same marker legend, which the metadata keeps once
legends = [info.pop("legend") for info in yearly_info.values()]
if any(other != legends[0] for other in legends):
    raise ValueError("the yearly tables carry different marker legends")
legend = legends[0]

# Layer 3: food + non_food = total within rounding, apart from the declared break; stops on failure
identities, gaps = identity_check(static)

# Layer 4: the static table against the yearly tables for 2017-2025, within TOL_CROSS; stops on failure
cross = cross_check(static, yearly, yearly_missing)

# Layer 5: plausibility of every value, every change from the year before and every identity gap; only flagged
flags, plausibility_compared, change_not_compared = plausibility(rows, static, gaps)

# Coverage for the metadata: each late-starting region's first year and the years printed '-' before it
coverage = {
    "first_year": {code: {"year": str(year), "reason": FIRST_YEAR_REASON[code]} for code, year in FIRST_YEAR.items()},
    "not_published": {
        "marker": "-",
        "meaning": "no value for the region in that year; the cell is left out, never written as 0",
        "cells": len(dashes),
        "years_by_region": {code: year_span(YEARS[0], year - 1) for code, year in FIRST_YEAR.items()},
    },
    "gaps": "none: every other region, Indonesia included, has food, non_food and total in every year 2011-2025",
}

# Describe the dataset
footnote = static_info["footnotes"]["1)"]["text"]
meta = {
    "title": "BPS average monthly spending per capita on food and non-food by province, Indonesia, 2011-2025",
    "columns": {
        "province_code": "BPS province code (kode_bps); 00 = Indonesia. Names and Kemendagri codes in 'provinces'.",
        "indicator": "Indicator code; definition in 'indicators'.",
        "item": "Spending group; BPS names in 'items'. total is food and non_food together.",
        "period": "YYYY = survey year of the Susenas round (see 'periods').",
        "status": "Revision marker; neither source gives one, so every row is empty (final).",
        "value": "Rupiah per person per month at current prices, whole rupiah as BPS static table 945 publishes it.",
    },
    "provinces": provinces,
    "province_source": {"url": URL_PROVINCES, "file": RAW_PROVINCES.relative_to(ROOT).as_posix(),
                        "note": "BPS and Kemendagri codes differ for the six Papua provinces; join other datasets on "
                                "the code system they use."},
    "indicators": {INDICATOR: {
        "name": "Rata-rata pengeluaran per kapita sebulan (average monthly spending per capita), urban and rural "
                "areas together (daerah perkotaan dan perdesaan)",
        "unit": "rupiah per person per month, current prices", "multiplier": 1,
        "base_unit": "Rp per person per month", "decimals": STATIC_FORMAT["decimals"],
        "periods": f"{YEARS[0]}-{YEARS[-1]}, annual",
        "source": f"BPS WebAPI static table {STATIC_ID}, {URL_STATIC} (key not stored), from Susenas (Survei Sosial "
                  f"Ekonomi Nasional)",
        "download_script": DOWNLOAD_SCRIPT,
        "table": static_info["title"],
        "notes": [
            f"Static table {STATIC_ID} publishes whole rupiah (Excel number format #\\ ###\\ ##0); the CSV keeps them.",
            "Per capita values do not add across provinces; 00 is BPS's national figure from the same survey.",
        ],
    }},
    "items": ITEM_NAMES,
    "periods": {
        "held": [str(y) for y in YEARS],
        "note": "One value per year. The static table's notes name Susenas Triwulan I (the first-quarter round) for "
                "2012-2014, and the yearly tables' source lines name Susenas Maret (March) for 2017-2025; no raw file "
                "names the round for 2011, 2015 or 2016.",
    },
    "coverage": coverage,
    "borders": [
        f"64 (Kalimantan Timur) in 2011-2014 includes Kalimantan Utara, as the static table's footnote 1) states "
        f"('{footnote}'); 65 (Kalimantan Utara) has its own values from 2015.",
        "91 (Papua Barat) and 94 (Papua) in 2011-2023 cover the pre-split provinces: the 2023 yearly table's note says "
        "Papua Barat Daya still follows the Papua Barat figures, and Papua Selatan, Papua Tengah and Papua Pegunungan "
        "the Papua figures. From 2024, 91 and 94 cover the post-split areas, and 92, 95, 96 and 97 start.",
        "A per capita value of a pre-split area cannot be rebuilt from the post-split provinces without their "
        "populations, and a change from the year before across a border change compares different areas: 64 in 2015, "
        "91 and 94 in 2024 (checks.change_not_compared).",
    ],
    "source_priority": [
        {"source": f"static table {STATIC_ID}", "years": year_span(YEARS[0], YEARS[-1]), "use": "every value in the CSV"},
        {"source": "statistics table (tablestatistic), one file per year", "years": year_span(YEARLY_YEARS[0], YEARLY_YEARS[-1]),
         "use": "lower-priority copy, compared in checks.cross_source and never written"},
    ],
    "source_tables": {
        f"static_table_{STATIC_ID}": {
            "file": RAW_STATIC.relative_to(ROOT).as_posix(), "url": URL_STATIC, "download_script": DOWNLOAD_SCRIPT,
            **{k: static_info[k] for k in ("title", "subject", "created", "updated", "source_line", "footnotes")},
            "notes_as_published": static_info["notes"],
        },
        "statistics_table": {
            "url": URL_YEARLY, "download_script": DOWNLOAD_SCRIPT,
            "legend": {"note": "The marker legend (keterangan_data) of the yearly tables, as published; all nine "
                               "carry the same legend.", "markers": legend},
            "years": yearly_info,
        },
    },
    "notes": [
        f"Every value comes from static table {STATIC_ID}, the one raw file that holds all {len(YEARS)} years, so the "
        f"series has one source and one precision throughout. The yearly statistics tables repeat 2017-2025, with 2 "
        f"decimals in 2017, 2018 and 2020-2022 and whole rupiah in 2019 and 2023-2025; every shared value agrees "
        f"within {TOL_CROSS} rupiah, and every difference is listed under checks.cross_source.",
        f"The static table rounds food, non_food and total to whole rupiah one by one, so food + non_food differs from "
        f"total by up to {TOL_SUM} rupiah. In {ROUNDED_PARTS_YEAR} its totals are its rounded food plus its rounded "
        f"non_food, which is why {len(cross['beyond_half_rupiah']['keys'])} totals of {ROUNDED_PARTS_YEAR} differ "
        f"from the yearly table by more than {HALF} rupiah.",
        "Nusa Tenggara Barat (52) in 2012: the static table prints food 291 176, non_food 234 901 and total 484 661, "
        "so food + non_food exceeds total by 41 416 rupiah. The three values are kept as published; one of them is a "
        "BPS error, and no raw file here can tell which (checks.identities, declared_breaks; checks.flags).",
        f"The {YEARLY_YEARS[-1]} yearly table is version {yearly_info[str(YEARLY_YEARS[-1])]['version']}, whose change "
        f"log records a correction of all province figures; static table {STATIC_ID} (updated "
        f"{static_info['updated'][:10]}) matches it in all {cross['compared_by_year'][str(YEARLY_YEARS[-1])]} values "
        f"of {YEARLY_YEARS[-1]}.",
        "Derived values are not stored: food share (%) = food / total x 100, and the change from the year before (%) "
        "= value in year t / value in year t-1 x 100 - 100, at current prices; the change is computed here only for "
        "the plausibility flags.",
        "checks.flags lists every value, change and identity gap outside its range in checks.plausible_ranges for a "
        "person to review; a change flag gives the two values it compares under rupiah. A flag stays whether it "
        "reflects a real event or a source error.",
    ],
    "checks": {
        "passed": ["identities", "cross-source"],
        "identities": [identities],
        "cross_source": [cross, {"check": "status: no cell of either source carries a revision marker, and no note "
                                          "gives a status, so every row is final"}],
        "plausible_ranges": PLAUSIBLE,
        "plausibility_compared": plausibility_compared,
        "change_not_compared": change_not_compared,
        "flags": flags,
    },
}

# Layers 1, 2 and 6: every region, item and year from its first year must be present, and nothing else; write the
# CSV and metadata
regions = list(provinces)
expected = {(code, INDICATOR, item, str(year)) for code in regions for year in YEARS
            if year >= FIRST_YEAR.get(code, YEARS[0]) for item in ITEM_ORDER}
out = cleaning.write_dataset(
    rows, KEYS,
    allowed={"province_code": regions, "indicator": [INDICATOR], "item": ITEM_ORDER, "period": [str(y) for y in YEARS]},
    expected=expected, csv_path=OUT_CSV, meta=meta, raw_files=[RAW_PROVINCES, RAW_STATIC, *RAW_YEARLY.values()],
    sort_orders={"item": ITEM_ORDER},
)

# Report what was written and every check
print(f"{OUT_CSV.name}: {len(out)} rows, {len(dashes)} cells printed '-', {len(flags)} plausibility flags")
print(out.groupby("item").size().to_string())
print(f"  identity: {identities['compared']} compared, largest gap {identities['largest_gap']}, declared breaks "
      f"{[(b['province_code'], b['period'], b['food_plus_non_food_minus_total']) for b in identities['declared_breaks']]}")
print(f"  cross-source: {cross['compared']} compared, {len(cross['differences'])} differ, largest gap "
      f"{cross['largest_gap']}, beyond {HALF}: {cross['beyond_half_rupiah']['keys']}")
print(f"  plausibility: values read {plausibility_compared}")
for f in flags:
    print("  flag:", f)
