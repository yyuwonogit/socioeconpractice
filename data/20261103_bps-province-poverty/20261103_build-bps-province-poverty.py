from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# Load the shared cleaning module from tools/
import sys
sys.path.insert(0, str(ROOT / "tools"))
import cleaning

# Parameters

# BPS province list that every region name in the table is matched against
RAW_PROVINCES = ROOT / "raw/province-codes/20261102_bps-province-codes-2025-s1.json"
URL_PROVINCES = "https://sig.bps.go.id/rest-bridging/getwilayah?level=provinsi&periode_merge=2025_1.2025"

# BPS WebAPI dynamic table 192, Persentase Penduduk Miskin (P0) Menurut Provinsi dan Daerah, saved in blocks of up
# to three years
RAW_DIR = ROOT / "raw/poverty"
BLOCKS = ["2007-2009", "2010-2012", "2013-2015", "2016-2018", "2019-2021", "2022-2024", "2025-2026"]
RAW_POVERTY = [RAW_DIR / f"20261103_bps-poverty-rate-p0-by-province-{b}.json" for b in BLOCKS]
DOWNLOAD_SCRIPT = "raw/poverty/20261103_download-bps-poverty-rate-p0-by-province.py"
VAR = 192
LABEL = "Persentase Penduduk Miskin (P0) Menurut Provinsi dan Daerah"
URL_POVERTY = "https://webapi.bps.go.id/v1/api/list/model/data/domain/0000/var/192/th/{th}"

# How each raw file is written, read from opening the files: the province list is UTF-8 JSON; each WebAPI file is
# UTF-8 JSON without a byte-order mark whose values are JSON numbers with a decimal point and no thousands separator,
# 2 decimals at most (a trailing zero is dropped, so 26.30 is written 26.3 and 23.00 is written 23), unit 'Persen',
# and a cell BPS does not publish is a key absent from datacontent
JSON_NUMBERS = "JSON numbers, decimal point, no thousands separator"
ABSENT_KEY = "key absent from datacontent"
READ_CONTEXT = {RAW_PROVINCES: {"encoding": "utf-8"}}
READ_CONTEXT.update({p: {"encoding": "utf-8", "var": VAR, "unit": "Persen", "decimals": 2,
                         "numbers": JSON_NUMBERS, "missing": ABSENT_KEY} for p in RAW_POVERTY})

# The table's note, item by item as published: it sets the Kalimantan Utara and Papua coverage below and gives no
# revision status, so the build stops if it changes
NOTE_ITEMS = [
    "Data Provinsi Kalimantan Utara pada tahun 2013 dan 2014 masih bergabung dengan Provinsi Kalimantan Timur",
    "Angka Provinsi Papua Barat dan Papua sebelum tahun 2024 merupakan angka provinsi sebelum mengalami pemekaran "
    "Daerah Otonom Baru (DOB)",
]

OUT_CSV = HERE / "20261103_bps-province-poverty.csv"

# Indicator code and the area code for each of BPS's area labels (turvar)
INDICATOR = "poverty_rate"
AREAS = {"Jumlah": "total", "Perkotaan": "urban", "Perdesaan": "rural"}

# Period suffix for each of BPS's sub-period labels (turtahun): the March and September rounds, or a yearly figure
SUBPERIODS = {"Semester 1 (Maret)": "S1", "Semester 2 (September)": "S2", "Tahunan": ""}

# Periods the table holds, read from opening the files: yearly figures for 2007-2011, March and September for
# 2012-2022, 2024 and 2025, and March only for 2023 and 2026
PERIODS = ([str(y) for y in range(2007, 2012)]
           + [f"{y}{s}" for y in range(2012, 2023) for s in ("S1", "S2")]
           + ["2023S1", "2024S1", "2024S2", "2025S1", "2025S2", "2026S1"])

# First period of each region whose series starts after the table's first period, with the reason; every other
# region, the provinces formed before 2007 among them, has a value in every period from 2007
FIRST_PERIOD = {
    "65": ("2015S1", "Kalimantan Utara became a province in 2012; the table's note says its 2013 and 2014 data are "
                     "still part of Kalimantan Timur, and the table starts it in March 2015"),
    "92": ("2024S1", "Papua Barat Daya became a province in 2022; the table starts it in March 2024"),
    "95": ("2024S1", "Papua Selatan became a province in 2022; the table starts it in March 2024"),
    "96": ("2024S1", "Papua Tengah became a province in 2022; the table starts it in March 2024"),
    "97": ("2024S1", "Papua Pegunungan became a province in 2022; the table starts it in March 2024"),
}

# Regions absent from a period although their series has started: none in this table
GAPS = {}

# DKI Jakarta has no rural area, so the table has no rural rate for it in any period
NO_RURAL = {"31": "DKI Jakarta has no rural area, so BPS publishes no rural poverty rate for it"}

# Cells BPS publishes as 0.00, which is not a poverty rate: DKI Jakarta's rural cell in September 2012 and September
# 2016, the only periods in which the table fills it. They are dropped, and the build stops if the set of zero cells
# changes
ZERO_PLACEHOLDERS = {("31", "rural", "2012S2"), ("31", "rural", "2016S2")}

# Periods where a province's borders change, so its change from the previous period compares different areas: the
# Papua split, which the table applies from March 2024, and Kalimantan Utara's first period in March 2015
BORDER_CHANGES = {("91", "2024S1"): "Papua Barat loses Papua Barat Daya",
                  ("94", "2024S1"): "Papua loses Papua Selatan, Papua Tengah and Papua Pegunungan",
                  ("64", "2015S1"): "Kalimantan Timur loses Kalimantan Utara"}

# Consecutive periods about a year apart rather than a half-year: the yearly figures of 2007-2011, the 2011 yearly
# figure to March 2012, and March 2023 to March 2024, as the table holds no September 2023 value
YEAR_STEPS = [("2007", "2008"), ("2008", "2009"), ("2009", "2010"), ("2010", "2011"), ("2011", "2012S1"),
              ("2023S1", "2024S1")]

# Plausibility ranges (layer 5), in percent and percentage points: every rate, and the change in a rate from the
# region's previous period in the same area; urban and rural rates come from smaller samples than the total and get
# a wider range, and a step of about a year gets 1.5 times the half-year range
PLAUSIBLE = {
    "poverty_rate": (1.0, 50.0),
    "poverty_rate_change": {
        "half_year": {"total": (-2.0, 2.0), "urban": (-3.0, 3.0), "rural": (-3.0, 3.0)},
        "year": {"total": (-3.0, 3.0), "urban": (-4.5, 4.5), "rural": (-4.5, 4.5)},
    },
}

# Layer 3 tolerance, in percentage points: the total rate is the population-weighted average of the urban and rural
# rates, so it lies between them, within one unit in the last published decimal because BPS rounds each rate on its
# own; where there is no rural rate the total is the urban rate itself, so they must match exactly
TOL_BETWEEN = 0.01
TOL_NO_RURAL = 0

# Functions

def read_table(path):
    """Read one saved WebAPI table with its READ_CONTEXT, after checking the declarations read_webapi_table assumes."""
    context = dict(READ_CONTEXT[path])
    assert context.pop("numbers") == JSON_NUMBERS and context.pop("missing") == ABSENT_KEY, path.name
    return cleaning.read_webapi_table(path, **context)


def note_items(note):
    """Return the text of each list item of a BPS note, and stop if the note holds text outside its list items."""
    items = [cleaning.html_to_text(part.split("</li>")[0]) for part in note.split("<li>")[1:]]
    assert cleaning.html_to_text(note) == " ".join(items), "the note holds text outside its list items"
    return items


def expected_keys(regions):
    """Return every (region, indicator, area, period) the table must hold, from the declared coverage rules."""
    keys = set()
    for code in regions:
        start = FIRST_PERIOD.get(code, (PERIODS[0], ""))[0]
        for period in PERIODS[PERIODS.index(start):]:
            if (code, period) in GAPS:
                continue
            for area in AREAS.values():
                if area == "rural" and code in NO_RURAL:
                    continue
                keys.add((code, INDICATOR, area, period))
    return keys


def identity_checks(rows):
    """Layer 3: each total rate lies between the region's urban and rural rates, and equals the urban rate where BPS
    publishes no rural rate. Stops on any gap beyond its tolerance, and returns a summary of each check."""
    value = {(r["province_code"], r["area"], r["period"]): r["value"] for r in rows}
    between, no_rural = [], []
    for (code, area, period), total in value.items():
        if area != "total":
            continue
        if (code, "urban", period) not in value:
            raise ValueError(f"{code} {period}: a total rate without an urban rate")
        urban, rural = value[(code, "urban", period)], value.get((code, "rural", period))
        if rural is None:
            if code not in NO_RURAL:
                raise ValueError(f"{code} {period}: no rural rate, and {code} is not declared in NO_RURAL")
            no_rural.append(((code, period), round(abs(total - urban), 2)))
        else:
            low, high = min(urban, rural), max(urban, rural)
            between.append(((code, period), round(max(0.0, low - total, total - high), 2)))
    results = []
    for label, gaps, tolerance in (
            (f"{INDICATOR}: total lies between urban and rural, every region and period with both", between,
             TOL_BETWEEN),
            (f"{INDICATOR}: total equals urban where BPS publishes no rural rate ({', '.join(sorted(NO_RURAL))})",
             no_rural, TOL_NO_RURAL)):
        over = sorted((k, g) for k, g in gaps if g > tolerance)
        if not gaps or over:
            raise ValueError(f"{label}: {len(gaps)} compared, {len(over)} beyond {tolerance}, such as {over[:5]}")
        results.append({"check": label, "compared": len(gaps), "tolerance": tolerance,
                        "largest_gap": max(g for _, g in gaps)})
    return results


def step_of(before, after):
    """Return 'half_year' or 'year' for two consecutive periods, and stop on a step the build does not declare."""
    if (before, after) in YEAR_STEPS:
        return "year"
    year = int(before[:4])
    if (before[4:], after) in (("S1", f"{year}S2"), ("S2", f"{year + 1}S1")):
        return "half_year"
    raise ValueError(f"{before} to {after} is neither a half-year nor a declared year step")


def change_flags(rows):
    """Layer 5: flag a rate that moves more than its stated range from the region's previous period in the same area,
    skipping the periods where the region's borders change. Returns the flags, the skipped steps and the count
    compared."""
    order = list(AREAS.values())
    series = {}
    for r in rows:
        series.setdefault((r["province_code"], r["area"]), []).append(
            (PERIODS.index(r["period"]), r["period"], r["value"]))
    flags, skipped, compared = [], [], 0
    for (code, area), points in sorted(series.items(), key=lambda s: (s[0][0], order.index(s[0][1]))):
        points.sort()
        for (_, before, a), (_, after, b) in zip(points, points[1:]):
            if (code, after) in BORDER_CHANGES:
                skipped.append({"province_code": code, "area": area, "period": after, "from_period": before,
                                "reason": BORDER_CHANGES[(code, after)]})
                continue
            step = step_of(before, after)
            change = {"province_code": code, "indicator": "poverty_rate_change", "area": area, "period": after,
                      "from_period": before, "step": step, "value": round(b - a, 2)}
            flags += cleaning.flag_outside([change], "poverty_rate_change",
                                           *PLAUSIBLE["poverty_rate_change"][step][area])
            compared += 1
    return flags, skipped, compared


def equal_area_flags(rows):
    """Layer 5: flag a region and period whose urban and rural rates are equal, which two populations rarely give."""
    value = {(r["province_code"], r["area"], r["period"]): r["value"] for r in rows}
    keys = sorted((k for k in value if k[1] == "urban"), key=lambda k: (k[0], PERIODS.index(k[2])))
    return [{"check": "urban_equals_rural", "province_code": code, "indicator": INDICATOR, "period": period,
             "urban": value[(code, "urban", period)], "rural": value[(code, "rural", period)],
             "total": value[(code, "total", period)]}
            for code, _, period in keys if value.get((code, "rural", period)) == value[(code, "urban", period)]]

# Steps

# Read the BPS province list, which load_bps_provinces reads as UTF-8, the encoding declared for it
assert READ_CONTEXT[RAW_PROVINCES]["encoding"] == "utf-8"
provinces, lookup = cleaning.load_bps_provinces(RAW_PROVINCES)

# Stop unless the folder holds exactly the declared blocks
found = sorted(RAW_DIR.glob("20261103_bps-poverty-rate-p0-by-province-*.json"))
assert found == sorted(RAW_POVERTY), [p.name for p in found]

# Read every block, check it is the same table throughout and holds exactly its years, and turn each cell into a row
rows, zeros, notes, meta_tables = [], set(), set(), {}
for path in RAW_POVERTY:
    table, records = read_table(path)
    first, last = (int(y) for y in path.stem.rsplit("-", 2)[-2:])
    assert [t["label"] for t in table["tahun"]] == [str(y) for y in range(first, last + 1)], path.name
    assert table["var"][0]["label"] == LABEL, (path.name, table["var"][0]["label"])
    assert {t["label"] for t in table["turvar"]} == set(AREAS), path.name
    assert {t["label"] for t in table["turtahun"]} == set(SUBPERIODS), path.name
    notes.add(table["var"][0]["note"])
    meta_tables[path.name] = {"last_update": table.get("last_update"), "label": table["var"][0]["label"],
                              "subject": table["var"][0].get("subj")}
    for r in records:
        code = cleaning.webapi_region_code(r["vervar"], r["vervar_label"], lookup)
        key = (code, AREAS[r["turvar_label"]], f"{r['year']}{SUBPERIODS[r['turtahun_label']]}")
        # Drop BPS's 0.00 placeholders, which are not poverty rates, and keep every other value as published
        if r["value"] == 0:
            zeros.add(key)
            continue
        rows.append({"province_code": code, "indicator": INDICATOR, "area": key[1], "period": key[2],
                     "status": "", "value": r["value"]})

# Stop unless every block carries the same note, the note still says what the build declares, and it gives no
# revision status
assert len(notes) == 1, "the blocks carry different notes"
note = notes.pop()
assert note_items(note) == NOTE_ITEMS, f"the note changed: {note_items(note)}"
assert cleaning.parse_status_note(note) == {}, "the note now gives revision statuses"

# Stop unless the zero cells are exactly the declared placeholders
assert zeros == ZERO_PLACEHOLDERS, f"zero cells changed: {sorted(zeros ^ ZERO_PLACEHOLDERS)}"

# Stop unless the table holds exactly the declared periods
held = {r["period"] for r in rows}
assert held == set(PERIODS), f"periods held differ from the declared ones: {sorted(held ^ set(PERIODS))}"

# Stop unless the rows hold exactly the declared coverage, before the identity and change checks rely on it
regions = sorted(provinces)
expected = expected_keys(regions)
keys = {(r["province_code"], r["indicator"], r["area"], r["period"]) for r in rows}
assert keys == expected, (f"coverage: {len(expected - keys)} missing {sorted(expected - keys)[:5]}, "
                          f"{len(keys - expected)} extra {sorted(keys - expected)[:5]}")

# Identities (layer 3): every total between its urban and rural rates, and equal to the urban rate without a rural one
identities = identity_checks(rows)

# Plausibility (layer 5): every rate inside its range, every change from the previous period inside its range, and
# every pair of urban and rural rates that are equal
area_order = list(AREAS.values())
ordered = sorted(rows, key=lambda r: (r["province_code"], area_order.index(r["area"]), PERIODS.index(r["period"])))
flags = cleaning.flag_outside(ordered, INDICATOR, *PLAUSIBLE["poverty_rate"])
moves, skipped, compared = change_flags(ordered)
flags += moves + equal_area_flags(ordered)

# Metadata: codes, sources, coverage rules, dropped cells, borders and checks
meta = {
    "title": "BPS poverty rate (P0) by province and area, Indonesia, 2007-2026",
    "columns": {
        "province_code": "BPS province code (kode_bps); 00 = Indonesia. Names and Kemendagri codes in 'provinces'.",
        "indicator": "Indicator code; definition in 'indicators'.",
        "area": "Area code; BPS labels in 'areas'.",
        "period": "YYYY for a yearly figure (2007-2011), YYYYS1 for the March round (BPS Semester 1) and YYYYS2 for "
                  "the September round (BPS Semester 2).",
        "status": "Revision marker; the table gives none, so every row is empty (final).",
        "value": "Percentage of the population below the poverty line, as published by BPS: percent, 2 decimals.",
    },
    "provinces": provinces,
    "province_source": {"url": URL_PROVINCES, "file": RAW_PROVINCES.relative_to(ROOT).as_posix()},
    "indicators": {INDICATOR: {
        "name": f"{LABEL} (poverty headcount index P0: the percentage of people whose monthly per capita expenditure "
                "is below the poverty line)",
        "unit": "percent of the population (Persen)", "multiplier": 1, "decimals": 2,
        "source": f"BPS WebAPI dynamic table {VAR}, {URL_POVERTY} (key omitted; th lists up to three years, each "
                  "minus 1900, joined by ';'), subject Kemiskinan dan Ketimpangan",
        "download_script": DOWNLOAD_SCRIPT,
        "note_as_published": note,
    }},
    "areas": {code: label for label, code in AREAS.items()},
    "periods": {"held": PERIODS, "note": "The table gives yearly figures (BPS 'Tahunan') for 2007-2011, the March and "
                "September rounds for 2012-2022, 2024 and 2025, and March only for 2023 and 2026: it holds no "
                "September 2023 value. Its note names no survey round for the yearly figures, so they are written "
                "YYYY, not YYYYS1."},
    "coverage": {
        "first_period": {code: {"period": p, "reason": why} for code, (p, why) in FIRST_PERIOD.items()},
        "other_regions": f"Every other region has a value in every period from {PERIODS[0]}, the table's first.",
        "gaps": [{"province_code": c, "period": p, "reason": why} for (c, p), why in GAPS.items()],
        "no_rural": NO_RURAL,
    },
    "dropped_cells": {"cells": [{"province_code": c, "area": a, "period": p} for c, a, p in sorted(ZERO_PLACEHOLDERS)],
                      "reason": "BPS publishes these as 0.00, which is not a poverty rate: DKI Jakarta has no rural "
                                "area, the table has no rural cell for it in its other 31 periods, and its total rate "
                                "equals its urban rate in every period, these two included. They are left out rather "
                                "than written as values."},
    "borders": ["91 (Papua Barat) and 94 (Papua) before March 2024 cover the areas before the 2022 split, as the "
                "table's note says; 92, 95, 96 and 97 start in March 2024.",
                "64 (Kalimantan Timur) before March 2015 includes Kalimantan Utara, which the table's note says is "
                "still part of it in 2013 and 2014; 65 starts in March 2015."],
    "source_tables": meta_tables,
    "checks": {
        "passed": ["identities", "plausibility checked (layer 5, flags listed)"],
        "identities": identities,
        "plausible_ranges": {
            "poverty_rate": list(PLAUSIBLE["poverty_rate"]),
            "poverty_rate_change": {step: {area: list(r) for area, r in ranges.items()}
                                    for step, ranges in PLAUSIBLE["poverty_rate_change"].items()},
        },
        "plausible_ranges_reason": "Rates in percent, changes in percentage points from the region's previous "
                                   "period in the same area. Urban and rural rates come from smaller samples than the "
                                   "total, so their change range is wider, and a step of about a year gets 1.5 times "
                                   "the half-year range.",
        "change_steps": {"half_year": "S1 to S2 of the same year, or S2 to S1 of the next year",
                         "year": [f"{b} to {a}" for b, a in YEAR_STEPS],
                         "year_reason": "the yearly figures of 2007-2011 are a year apart, the 2011 yearly figure is "
                                        "followed by March 2012, and the table holds no September 2023 value"},
        "change_compared": compared,
        "change_not_compared": skipped,
        "change_not_compared_note": "A region's first period has no earlier value, so it has no change to compare.",
        "plausibility_rules": {"urban_equals_rural": "an urban rate equal to the rural rate of the same region and "
                               "period, which two different populations rarely give; listed for a person to compare "
                               "with the BPS release"},
        "flags": flags,
    },
    "notes": ["No other raw file holds these values, so there is no cross-source check (layer 4).",
              "Area 'total' is BPS's Jumlah, the rate over everyone in the region: the population-weighted average "
              "of the urban and rural rates, which checks.identities tests."],
}

# Check structure and completeness against the declared coverage, then write the CSV and the metadata
cleaning.write_dataset(
    rows, ["province_code", "indicator", "area", "period"],
    allowed={"province_code": regions, "indicator": [INDICATOR], "area": list(AREAS.values()), "period": PERIODS},
    expected=expected, csv_path=OUT_CSV, meta=meta, raw_files=[RAW_PROVINCES] + RAW_POVERTY,
    sort_orders={"area": list(AREAS.values()), "period": PERIODS},
)

# Report the size of the dataset, the identity checks and every plausibility flag
print(f"{len(rows)} rows, {len(PERIODS)} periods, {compared} changes compared, {len(flags)} plausibility flags")
for check in identities:
    print("  identity:", check)
for f in flags:
    print("  flag:", f)
