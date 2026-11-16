from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# Load the shared cleaning module from tools/
import sys
sys.path.insert(0, str(ROOT / "tools"))
import cleaning

import openpyxl

# Parameters

# Raw inputs: the BPS province list, and the location matrix as the user saved it on 2026-11-16 15:28 after typing
# operating / planned renewable-energy capacity into sheet FB1, column C (rows 2-39, English province names in B)
RAW_PROVINCES = ROOT / "raw/province-codes/20261102_bps-province-codes-2025-s1.json"
RAW_ENTRY = ROOT / "raw/renewable-energy/20261116_location-selection-matrix-with-re-capacity-entered.xlsx"

# Output; the metadata JSON is written beside it with a -metadata suffix
OUT_CSV = HERE / "20261116_province-re-capacity-entered.csv"

KEYS = ["province_code", "indicator"]

# Where the values sit, read from opening the workbook: numbers (no text), one per province row
READ_CONTEXT = {
    "sheet": "FB1 RE Exposure Index",
    "header": {"B1": "Province", "C1": "Operating / Planned RE Capacity in the Region"},
    "rows": range(2, 40), "name_column": "B", "value_column": "C",
}

INDICATORS = {
    "re_capacity_operating_planned": {"name": "Operating / planned renewable-energy capacity in the region, as entered by the user",
                                      "unit": "not stated by the user (MW assumed until confirmed)", "multiplier": 1,
                                      "source": "Typed into the location matrix by the user; original source and year to be confirmed"},
}

# Functions

def read_entry(lookup):
    """Read FB1 column C by province name, checking headers and that every value is a number."""
    c = READ_CONTEXT
    ws = openpyxl.load_workbook(RAW_ENTRY, data_only=True)[c["sheet"]]
    for cell, text in c["header"].items():
        assert str(ws[cell].value).strip() == text, (cell, ws[cell].value)
    rows = []
    for r in c["rows"]:
        name, value = ws[f"{c['name_column']}{r}"].value, ws[f"{c['value_column']}{r}"].value
        assert isinstance(value, (int, float)) and not isinstance(value, bool), (r, name, value)
        code = cleaning.province_code(cleaning.english_to_bps_name(name), lookup)
        rows.append({"province_code": code, "indicator": "re_capacity_operating_planned", "status": "", "value": float(value)})
    return rows

# Steps

# Read the BPS province list that every province name is matched against
provinces, lookup = cleaning.load_bps_provinces(RAW_PROVINCES)
regions = [c for c in provinces if c != cleaning.NATIONAL_CODE]

# Read the user's entries
rows = read_entry(lookup)

# Describe the dataset
meta = {
    "title": "Operating / planned renewable-energy capacity by province, as entered by the user in the location matrix",
    "columns": {
        "province_code": "BPS province code (kode_bps). Names and Kemendagri codes in 'provinces'.",
        "indicator": "Indicator code; definition in 'indicators'.",
        "status": "Empty.",
        "value": "As typed by the user, unchanged.",
    },
    "provinces": {k: v for k, v in provinces.items() if k != cleaning.NATIONAL_CODE},
    "indicators": INDICATORS,
    "source_tables": {"entry": {"file": str(RAW_ENTRY.relative_to(ROOT)), "sheet": READ_CONTEXT["sheet"], "column": "C",
                                "note": "The user typed these values into the delivered workbook; that workbook is kept as received."}},
    "notes": ["Unit, year and original source were not stated when the values were entered; confirm them with the user before use in an index."],
    "checks": {"passed": [], "flags": []},
}

# Layers 1, 2 and 6: every province has one value
out = cleaning.write_dataset(
    rows, KEYS,
    allowed={"province_code": regions, "indicator": list(INDICATORS)},
    expected={(c, "re_capacity_operating_planned") for c in regions},
    csv_path=OUT_CSV, meta=meta, raw_files=[RAW_PROVINCES, RAW_ENTRY],
)

# Report what was written
print(f"{OUT_CSV.name}: {len(out)} rows")
