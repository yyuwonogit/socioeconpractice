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

# BPS WebAPI dynamic table 416, [Metode Baru] Pengeluaran per Kapita Disesuaikan, saved in blocks of up to three years
RAW_DIR = ROOT / "raw/household-spending"
BLOCKS = ["2010-2012", "2013-2015", "2016-2018", "2019-2021", "2022-2024", "2025-2025"]
RAW_SPENDING = [RAW_DIR / f"20261104_bps-real-spending-per-capita-by-province-{b}.json" for b in BLOCKS]
DOWNLOAD_SCRIPT = "raw/household-spending/20261104_download-bps-real-spending-per-capita-by-province.py"
VAR = 416
UNIT = "Ribu Rupiah/Orang/Tahun"
URL_SPENDING = "https://webapi.bps.go.id/v1/api/list/model/data/domain/0000/var/416/th/{th}"

# How each raw file is written, read from opening the files: the province list is UTF-8 JSON; each WebAPI file is
# UTF-8 JSON with no byte-order mark whose values are JSON integers (no decimal point, no thousands separator),
# 0 decimals, in thousand rupiah per person per year, and a cell BPS does not publish is a key absent from datacontent
JSON_NUMBERS = "JSON numbers, decimal point, no thousands separator"
ABSENT_KEY = "key absent from datacontent"
READ_CONTEXT = {RAW_PROVINCES: {"encoding": "utf-8"}}
READ_CONTEXT.update({p: {"encoding": "utf-8", "var": VAR, "unit": UNIT, "decimals": 0,
                         "numbers": JSON_NUMBERS, "missing": ABSENT_KEY} for p in RAW_SPENDING})

OUT_CSV = HERE / "20261104_bps-province-real-spending.csv"

# Indicator code
INDICATOR = "real_spending_per_capita"

# Years the table holds, read from opening the files
PERIODS = [str(y) for y in range(2010, 2026)]

# First year of each region whose series starts after 2010, with the reason, read from opening the files
FIRST_PERIOD = {
    "65": ("2013", "Kalimantan Utara became a province in 2012; the table starts it in 2013"),
    "92": ("2024", "Papua Barat Daya became a province in 2022; the table starts it in 2024"),
    "95": ("2024", "Papua Selatan became a province in 2022; the table starts it in 2024"),
    "96": ("2024", "Papua Tengah became a province in 2022; the table starts it in 2024"),
    "97": ("2024", "Papua Pegunungan became a province in 2022; the table starts it in 2024"),
}

# Years where a province's borders change, so its change from the previous year compares different areas: the Papua
# split, which the table applies from 2024, and Kalimantan Utara's first year, 2013
BORDER_CHANGES = {("91", "2024"): "Papua Barat loses Papua Barat Daya",
                  ("94", "2024"): "Papua loses Papua Selatan, Papua Tengah and Papua Pegunungan",
                  ("64", "2013"): "Kalimantan Timur loses Kalimantan Utara"}

# Plausibility ranges (layer 5): every value in thousand rupiah per person per year, and the change from the previous
# year as a fraction of the previous year's value
PLAUSIBLE = {"real_spending_per_capita": (3000, 30000), "real_spending_change": (-0.08, 0.10)}

# Functions

def read_table(path):
    """Read one saved WebAPI table with its READ_CONTEXT, after checking the declarations read_webapi_table assumes."""
    context = dict(READ_CONTEXT[path])
    assert context.pop("numbers") == JSON_NUMBERS and context.pop("missing") == ABSENT_KEY, path.name
    return cleaning.read_webapi_table(path, **context)


def is_province_row(vervar):
    """Return True for a province or Indonesia row; the table's other rows are regencies and cities."""
    return vervar == 9999 or (vervar % 100 == 0 and 1100 <= vervar <= 9900)


def expected_keys(regions):
    """Return every (region, indicator, period) the table must hold, from the declared coverage rules."""
    keys = set()
    for code in regions:
        start = FIRST_PERIOD.get(code, (PERIODS[0], ""))[0]
        for period in PERIODS[PERIODS.index(start):]:
            keys.add((code, INDICATOR, period))
    return keys


def change_flags(rows):
    """Layer 5: flag a value that moves more than the stated range from the region's previous year."""
    series = {}
    for r in rows:
        series.setdefault(r["province_code"], []).append((r["period"], r["value"]))
    changes, skipped = [], []
    for code, points in series.items():
        points.sort()
        for (before, a), (after, b) in zip(points, points[1:]):
            if (code, after) in BORDER_CHANGES:
                skipped.append({"province_code": code, "period": after, "reason": BORDER_CHANGES[(code, after)]})
                continue
            changes.append({"province_code": code, "indicator": "real_spending_change", "period": after,
                            "from_period": before, "value": round(b / a - 1, 4)})
    return cleaning.flag_outside(changes, "real_spending_change", *PLAUSIBLE["real_spending_change"]), skipped

# Steps

# Read the BPS province list, which load_bps_provinces reads as UTF-8, the encoding declared for it
assert READ_CONTEXT[RAW_PROVINCES]["encoding"] == "utf-8"
provinces, lookup = cleaning.load_bps_provinces(RAW_PROVINCES)

# Stop unless the folder holds exactly the declared blocks
found = sorted(RAW_DIR.glob("20261104_bps-real-spending-per-capita-by-province-*.json"))
assert found == sorted(RAW_SPENDING), [p.name for p in found]

# Read every block, check it is the same table throughout, and turn each province or Indonesia cell into a row
rows, notes, meta_tables, local_values = [], set(), {}, 0
for path in RAW_SPENDING:
    table, records = read_table(path)
    first, last = (int(y) for y in path.stem.rsplit("-", 2)[-2:])
    assert {r["year"] for r in records} <= set(range(first, last + 1)), path.name
    assert [t["label"] for t in table["turvar"]] == ["Tidak ada"], path.name
    assert [t["label"] for t in table["turtahun"]] == ["Tahun"], path.name
    notes.add(table["var"][0]["note"])
    meta_tables[path.name] = {"last_update": table.get("last_update"), "label": table["var"][0]["label"],
                              "subject": table["var"][0].get("subj")}

    # BPS writes province and Indonesia labels in bold and regency and city labels without, so stop if the two marks
    # of a province row ever disagree
    for v in table["vervar"]:
        assert is_province_row(v["val"]) == v["label"].startswith("<b>"), f"{path.name}: {v}"
    for r in records:
        if not is_province_row(r["vervar"]):
            local_values += 1
            continue
        code = cleaning.webapi_region_code(r["vervar"], cleaning.html_to_text(r["vervar_label"]), lookup)
        rows.append({"province_code": code, "indicator": INDICATOR, "period": str(r["year"]),
                     "status": "", "value": r["value"]})

# Stop unless every block carries the same note, and that note gives no revision status
assert len(notes) == 1, "the blocks carry different notes"
note = notes.pop()
assert cleaning.parse_status_note(note) == {}, "the note now gives revision statuses"

# Stop unless the table holds exactly the declared years
assert sorted({r["period"] for r in rows}) == PERIODS, sorted({r["period"] for r in rows})

# Plausibility (layer 5): every value inside its range, and every change from the previous year inside its range
flags = cleaning.flag_outside(rows, INDICATOR, *PLAUSIBLE[INDICATOR])
moves, skipped = change_flags(rows)
flags += moves

# Metadata: codes, sources, coverage rules, borders and checks
meta = {
    "title": "BPS real spending per person by province (new-method HDI), Indonesia, 2010-2025",
    "columns": {
        "province_code": "BPS province code (kode_bps); 00 = Indonesia. Names and Kemendagri codes in 'provinces'.",
        "indicator": "Indicator code; definition in 'indicators'.",
        "period": "YYYY, the year of the March Susenas round the value comes from.",
        "status": "Revision marker; the table gives none, so every row is empty (final).",
        "value": "Thousand rupiah per person per year at constant 2012 prices, adjusted for regional price "
                 "differences, as published by BPS (0 decimals).",
    },
    "provinces": provinces,
    "province_source": {"url": URL_PROVINCES, "file": RAW_PROVINCES.relative_to(ROOT).as_posix()},
    "indicators": {INDICATOR: {
        "name": "[Metode Baru] Pengeluaran per Kapita Disesuaikan (adjusted real spending per person, the spending "
                "part of BPS's new-method Human Development Index)",
        "unit": f"thousand rupiah per person per year, constant 2012 prices ({UNIT})", "multiplier": 1000,
        "decimals": 0,
        "source": f"BPS WebAPI dynamic table {VAR}, {URL_SPENDING} (key omitted), from Susenas",
        "download_script": DOWNLOAD_SCRIPT,
        "note_as_published": note,
    }},
    "periods": {"held": PERIODS},
    "coverage": {
        "first_period": {code: {"period": p, "reason": why} for code, (p, why) in FIRST_PERIOD.items()},
        "local_rows_left_out": {"values": local_values,
                                "reason": "The table also holds every regency and city; this dataset keeps the "
                                          "provinces and Indonesia, which BPS labels in bold."},
    },
    "borders": ["91 (Papua Barat) and 94 (Papua) up to 2023 cover the areas before the 2022 split; from 2024 they "
                "cover the provinces after it, and 92, 95, 96 and 97 start in 2024.",
                "64 (Kalimantan Timur) before 2013 includes Kalimantan Utara, which starts in 2013."],
    "source_tables": meta_tables,
    "checks": {
        "passed": ["plausibility checked (layer 5, flags listed)"],
        "plausible_ranges": {k: list(v) for k, v in PLAUSIBLE.items()},
        "change_not_compared": skipped,
        "flags": flags,
    },
    "notes": ["No other raw file holds these values, so there is no cross-source check (layer 4).",
              "Indonesia's value is BPS's own national figure, not a sum or average of the provinces, so there is "
              "no provinces-to-Indonesia identity (layer 3)."],
}

# Check structure and completeness against the declared coverage, then write the CSV and the metadata
regions = sorted(provinces)
cleaning.write_dataset(
    rows, ["province_code", "indicator", "period"],
    allowed={"province_code": regions, "indicator": [INDICATOR], "period": PERIODS},
    expected=expected_keys(regions), csv_path=OUT_CSV, meta=meta, raw_files=[RAW_PROVINCES] + RAW_SPENDING,
    sort_orders={"period": PERIODS},
)

# Report the size of the dataset and every plausibility flag
print(f"{len(rows)} rows, {len(PERIODS)} periods, {len(flags)} plausibility flags")
for f in flags:
    print("  flag:", f)
