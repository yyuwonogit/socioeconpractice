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

# BPS WebAPI dynamic table 98, Gini Ratio Menurut Provinsi dan Daerah, saved in blocks of up to three years
RAW_DIR = ROOT / "raw/inequality"
BLOCKS = ["2002-2005", "2007-2009", "2010-2012", "2013-2015", "2016-2018", "2019-2021", "2022-2024", "2025-2026"]
RAW_GINI = [RAW_DIR / f"20261103_bps-gini-ratio-by-province-{b}.json" for b in BLOCKS]
DOWNLOAD_SCRIPT = "raw/inequality/20261103_download-bps-gini-ratio-by-province.py"
VAR = 98
URL_GINI = "https://webapi.bps.go.id/v1/api/list/model/data/domain/0000/var/98/th/{th}"

# How each raw file is written, read from opening the files: the province list is UTF-8 JSON; each WebAPI file is
# UTF-8 JSON whose values are JSON numbers with a decimal point and no thousands separator, 3 decimals, no unit
# ('Tidak Ada Satuan'), and a cell BPS does not publish is a key absent from datacontent
JSON_NUMBERS = "JSON numbers, decimal point, no thousands separator"
ABSENT_KEY = "key absent from datacontent"
READ_CONTEXT = {RAW_PROVINCES: {"encoding": "utf-8"}}
READ_CONTEXT.update({p: {"encoding": "utf-8", "var": VAR, "unit": "Tidak Ada Satuan", "decimals": 3,
                         "numbers": JSON_NUMBERS, "missing": ABSENT_KEY} for p in RAW_GINI})

OUT_CSV = HERE / "20261103_bps-province-gini.csv"

# Indicator code and the area code for each of BPS's area labels (turvar)
INDICATOR = "gini_ratio"
AREAS = {"Perkotaan+Perdesaan": "total", "Perkotaan": "urban", "Perdesaan": "rural"}

# Period suffix for each of BPS's sub-period labels (turtahun): the March and September Susenas rounds, or a yearly
# figure for the early years
SUBPERIODS = {"Semester 1 (Maret)": "S1", "Semester 2 (September)": "S2", "Tahunan": ""}

# Periods the table holds, read from opening the files: yearly figures for 2002-2008 (none for 2003, 2004 or 2006),
# March only for 2009, 2010, 2023 and 2026, and March and September otherwise
PERIODS = (["2002", "2005", "2007", "2008", "2009S1", "2010S1"]
           + [f"{y}{s}" for y in range(2011, 2023) for s in ("S1", "S2")]
           + ["2023S1", "2024S1", "2024S2", "2025S1", "2025S2", "2026S1"])

# First period of each region whose series starts after the table's first period, with the reason
FIRST_PERIOD = {
    "21": ("2005", "Kepulauan Riau became a province in 2002; the table starts it in 2005"),
    "76": ("2007", "Sulawesi Barat became a province in 2004; the table's 2005 cells are 0.000 placeholders"),
    "91": ("2007", "Papua Barat (Irian Jaya Barat until 2007) became a province in 2003; the table starts it in 2007"),
    "65": ("2015S1", "Kalimantan Utara became a province in 2012; the table starts it in March 2015"),
    "92": ("2024S1", "Papua Barat Daya became a province in 2022; the table starts it in March 2024"),
    "95": ("2024S1", "Papua Selatan became a province in 2022; the table starts it in March 2024"),
    "96": ("2024S1", "Papua Tengah became a province in 2022; the table starts it in March 2024"),
    "97": ("2024S1", "Papua Pegunungan became a province in 2022; the table starts it in March 2024"),
}

# Regions absent from one period although their series has started
GAPS = {("11", "2002"): "BPS publishes no 2002 value for Aceh",
        ("81", "2002"): "BPS publishes no 2002 value for Maluku",
        ("82", "2002"): "BPS publishes no 2002 value for Maluku Utara",
        ("94", "2002"): "BPS publishes no 2002 value for Papua"}

# DKI Jakarta has no rural area, so the table has no rural cell for it in any period
NO_RURAL = {"31": "DKI Jakarta has no rural area, so BPS publishes no rural Gini ratio for it"}

# Cells BPS publishes as 0.000, which is not a Gini ratio: Sulawesi Barat in 2005, the year after it became a
# province. They are dropped, and the build stops if the set of zero cells changes
ZERO_PLACEHOLDERS = {("76", area, "2005") for area in AREAS.values()}

# Periods where a province's borders change, so its change from the previous period compares different areas: the
# Papua split, which the table applies from March 2024, and Kalimantan Utara's first period in March 2015
BORDER_CHANGES = {("91", "2024S1"): "Papua Barat loses Papua Barat Daya", ("94", "2024S1"): "Papua loses Papua "
                  "Selatan, Papua Tengah and Papua Pegunungan", ("64", "2015S1"): "Kalimantan Timur loses Kalimantan Utara"}

# Plausibility ranges (layer 5): every Gini ratio, and the change in the total ratio between consecutive periods
PLAUSIBLE = {"gini_ratio": (0.15, 0.55), "gini_change": (-0.05, 0.05)}

# Functions

def read_table(path):
    """Read one saved WebAPI table with its READ_CONTEXT, after checking the declarations read_webapi_table assumes."""
    context = dict(READ_CONTEXT[path])
    assert context.pop("numbers") == JSON_NUMBERS and context.pop("missing") == ABSENT_KEY, path.name
    return cleaning.read_webapi_table(path, **context)


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


def change_flags(rows):
    """Layer 5: flag a total ratio that moves more than the stated range from the region's previous period."""
    series = {}
    for r in rows:
        if r["area"] == "total":
            series.setdefault(r["province_code"], []).append((PERIODS.index(r["period"]), r["period"], r["value"]))
    changes, skipped = [], []
    for code, points in series.items():
        points.sort()
        for (_, before, a), (_, after, b) in zip(points, points[1:]):
            if (code, after) in BORDER_CHANGES:
                skipped.append({"province_code": code, "period": after, "reason": BORDER_CHANGES[(code, after)]})
                continue
            changes.append({"province_code": code, "indicator": "gini_change", "area": "total",
                            "period": after, "from_period": before, "value": round(b - a, 3)})
    return cleaning.flag_outside(changes, "gini_change", *PLAUSIBLE["gini_change"]), skipped

# Steps

# Read the BPS province list, which load_bps_provinces reads as UTF-8, the encoding declared for it
assert READ_CONTEXT[RAW_PROVINCES]["encoding"] == "utf-8"
provinces, lookup = cleaning.load_bps_provinces(RAW_PROVINCES)

# Stop unless the folder holds exactly the declared blocks
found = sorted(RAW_DIR.glob("20261103_bps-gini-ratio-by-province-*.json"))
assert found == sorted(RAW_GINI), [p.name for p in found]

# Read every block, check it is the same table throughout, and turn each cell into a row
rows, zeros, notes, meta_tables = [], set(), set(), {}
for path in RAW_GINI:
    table, records = read_table(path)
    first, last = (int(y) for y in path.stem.rsplit("-", 2)[-2:])
    assert {r["year"] for r in records} <= set(range(first, last + 1)), path.name
    assert {t["label"] for t in table["turvar"]} == set(AREAS), path.name
    notes.add(table["var"][0]["note"])
    meta_tables[path.name] = {"last_update": table.get("last_update"), "label": table["var"][0]["label"],
                              "subject": table["var"][0].get("subj")}
    for r in records:
        code = cleaning.webapi_region_code(r["vervar"], r["vervar_label"], lookup)
        key = (code, AREAS[r["turvar_label"]], f"{r['year']}{SUBPERIODS[r['turtahun_label']]}")
        # Drop BPS's 0.000 placeholders, which are not Gini ratios, and keep every other value as published
        if r["value"] == 0:
            zeros.add(key)
            continue
        rows.append({"province_code": code, "indicator": INDICATOR, "area": key[1], "period": key[2],
                     "status": "", "value": r["value"]})

# Stop unless every block carries the same note, and that note gives no revision status
assert len(notes) == 1, "the blocks carry different notes"
note = notes.pop()
assert cleaning.parse_status_note(note) == {}, "the note now gives revision statuses"

# Stop unless the zero cells are exactly the declared placeholders
assert zeros == ZERO_PLACEHOLDERS, f"zero cells changed: {sorted(zeros ^ ZERO_PLACEHOLDERS)}"

# Stop unless the table holds exactly the declared periods
assert sorted({r["period"] for r in rows}, key=PERIODS.index) == PERIODS, sorted({r["period"] for r in rows})

# Plausibility (layer 5): every ratio inside its range, and every change in the total ratio inside its range
flags = cleaning.flag_outside(rows, "gini_ratio", *PLAUSIBLE["gini_ratio"])
moves, skipped = change_flags(rows)
flags += moves

# Metadata: codes, sources, coverage rules, dropped cells, borders and checks
meta = {
    "title": "BPS Gini ratio by province and area, Indonesia, 2002-2026",
    "columns": {
        "province_code": "BPS province code (kode_bps); 00 = Indonesia. Names and Kemendagri codes in 'provinces'.",
        "indicator": "Indicator code; definition in 'indicators'.",
        "area": "Area code; BPS labels in 'areas'.",
        "period": "YYYY for a yearly figure (2002-2008), YYYYS1 for the March Susenas round and YYYYS2 for the "
                  "September round.",
        "status": "Revision marker; the table gives none, so every row is empty (final).",
        "value": "Gini ratio as published by BPS, 3 decimals: 0 means every household spends the same, 1 that one "
                 "household spends everything.",
    },
    "provinces": provinces,
    "province_source": {"url": URL_PROVINCES, "file": RAW_PROVINCES.relative_to(ROOT).as_posix()},
    "indicators": {INDICATOR: {
        "name": "Gini Ratio Menurut Provinsi dan Daerah (Gini ratio of household per capita expenditure)",
        "unit": "ratio, no unit (Tidak Ada Satuan)", "multiplier": 1, "decimals": 3,
        "source": f"BPS WebAPI dynamic table {VAR}, {URL_GINI} (key omitted), from Susenas",
        "download_script": DOWNLOAD_SCRIPT,
        "note_as_published": note,
    }},
    "areas": {code: label for label, code in AREAS.items()},
    "periods": {"held": PERIODS, "note": "The table holds no value for 2003, 2004 or 2006, and no September value "
                "for 2009, 2010, 2023 or 2026. 2002-2008 are yearly figures from the survey rounds the note names."},
    "coverage": {
        "first_period": {code: {"period": p, "reason": why} for code, (p, why) in FIRST_PERIOD.items()},
        "gaps": [{"province_code": c, "period": p, "reason": why} for (c, p), why in GAPS.items()],
        "no_rural": NO_RURAL,
    },
    "dropped_cells": {"cells": [{"province_code": c, "area": a, "period": p} for c, a, p in sorted(ZERO_PLACEHOLDERS)],
                      "reason": "BPS publishes these as 0.000, which is not a Gini ratio; they are left out rather "
                                "than written as values."},
    "borders": ["91 (Papua Barat) and 94 (Papua) before March 2024 cover the areas before the 2022 split, as the "
                "table's note says; 92, 95, 96 and 97 start in March 2024.",
                "64 (Kalimantan Timur) before March 2015 includes Kalimantan Utara, which starts in March 2015."],
    "source_tables": meta_tables,
    "checks": {
        "passed": ["plausibility checked (layer 5, flags listed)"],
        "plausible_ranges": {k: list(v) for k, v in PLAUSIBLE.items()},
        "change_not_compared": skipped,
        "flags": flags,
    },
    "notes": ["No other raw file holds these values, so there is no cross-source check (layer 4).",
              "Area 'total' is BPS's Perkotaan+Perdesaan, computed by BPS from all households, not an average of the "
              "urban and rural ratios."],
}

# Check structure and completeness against the declared coverage, then write the CSV and the metadata
regions = sorted(provinces)
cleaning.write_dataset(
    rows, ["province_code", "indicator", "area", "period"],
    allowed={"province_code": regions, "indicator": [INDICATOR], "area": list(AREAS.values()), "period": PERIODS},
    expected=expected_keys(regions), csv_path=OUT_CSV, meta=meta, raw_files=[RAW_PROVINCES] + RAW_GINI,
    sort_orders={"area": list(AREAS.values()), "period": PERIODS},
)

# Report the size of the dataset and every plausibility flag
print(f"{len(rows)} rows, {len(PERIODS)} periods, {len(flags)} plausibility flags")
for f in flags:
    print("  flag:", f)
