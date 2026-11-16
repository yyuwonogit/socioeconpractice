from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# Load the shared cleaning module from tools/
import sys
sys.path.insert(0, str(ROOT / "tools"))
import cleaning

import pandas as pd

# Parameters

# Raw inputs: the BPS province list and the WebAPI responses for var 1840 (2019-2023)
RAW_PROVINCES = ROOT / "raw/province-codes/20261102_bps-province-codes-2025-s1.json"
RAW_API = ROOT / "raw/investment/20261116_bps-webapi-foreign-investment-by-province.jsonl"

# Output; the metadata JSON is written beside it with a -metadata suffix
OUT_CSV = HERE / "20261116_bps-province-foreign-investment.csv"

KEYS = ["province_code", "indicator", "period"]

# How the table writes its values, read from opening the responses: "." as the decimal mark, one decimal for
# value, whole numbers for projects, Indonesia as region 9999
READ_CONTEXT = {
    "title": "Realisasi Investasi Penanaman Modal Luar Negeri Menurut Provinsi", "unit": "Juta US$", "decimals": 1,
    "note_text": "Tidak termasuk Sektor Minyak Bumi dan Gas",
    "turvar": {"Proyek": "fdi_projects", "Investasi": "fdi_value"},
}
INDICATORS = {
    "fdi_projects": {"name": "Realisasi PMA: jumlah proyek (realised foreign direct investment, number of projects)", "unit": "projects", "multiplier": 1,
                     "source": "BPS WebAPI var 1840 (from Kementerian Investasi/BKPM)"},
    "fdi_value": {"name": "Realisasi PMA: nilai investasi (realised foreign direct investment, value)", "unit": "million US$", "multiplier": 1e6,
                  "base_unit": "US$", "source": "BPS WebAPI var 1840 (from Kementerian Investasi/BKPM)"},
}
YEARS = range(2019, 2024)

# Papua split: the four new provinces have values from 2023
NEW_PROVINCES = {"92", "95", "96", "97"}
FIRST_SPLIT_YEAR = 2023

# Provinces sum to Indonesia within rounding (one decimal per province), recorded rather than stopped on,
# because realisations not assigned to a province would also make them differ
SUM_TOLERANCE = {"fdi_value": 2.0, "fdi_projects": 0}

# Functions

def read_table(record, lookup):
    """Read one WebAPI response into long rows."""
    c = READ_CONTEXT
    table = record["response"]
    v = table["var"][0]
    where = f"var {record['var']} {record['year']}"
    cleaning.require_text(v["label"], c["title"], where)
    assert v["unit"] == c["unit"] and int(v["decimal"]) == c["decimals"], (where, v["unit"], v["decimal"])
    cleaning.require_text(cleaning.html_to_text(v["note"]), c["note_text"], where)
    out = []
    for code, tv, tt, year, text in cleaning.bps_api_province_cells(table, lookup):
        value = cleaning.parse_number(text, ".", None, max_decimals=c["decimals"])
        out.append({"province_code": code, "indicator": c["turvar"][tv], "period": year, "status": "", "value": value})
    return out

# Steps

# Read the BPS province list that every region name and code is matched against
provinces, lookup = cleaning.load_bps_provinces(RAW_PROVINCES)

# Read every response, one year per line
rows, tables = [], {}
for record in cleaning.read_jsonl(RAW_API):
    out = read_table(record, lookup)
    assert {r["period"] for r in out} == {record["year"]}
    rows += out
    tables[f"webapi {record['var']} {record['year']}"] = {"request": record["request"], "last_update": record["response"].get("last_update")}

# Layer 3 (recorded): provinces against Indonesia by year
df = pd.DataFrame(rows)
sums = {}
for ind in INDICATORS:
    w = df[df["indicator"] == ind].pivot(index="province_code", columns="period", values="value")
    gap = (w.drop(index=cleaning.NATIONAL_CODE).sum() - w.loc[cleaning.NATIONAL_CODE]).round(2)
    sums[ind] = {"provinces_minus_indonesia_by_year": gap.to_dict(), "within_tolerance": bool((gap.abs() <= SUM_TOLERANCE[ind]).all())}

# Describe the dataset
meta = {
    "title": "BPS realised foreign direct investment (PMA) by province, 2019-2023, Indonesia",
    "columns": {
        "province_code": "BPS province code (kode_bps); 00 = Indonesia. Names and Kemendagri codes in 'provinces'.",
        "indicator": "Indicator code; definitions in 'indicators'.",
        "period": "YYYY.",
        "status": "BPS revision marker; this table carries none.",
        "value": "As published by BPS.",
    },
    "provinces": provinces,
    "indicators": INDICATORS,
    "source_tables": tables,
    "notes": [
        "All sectors combined, excluding oil and gas, banking and other finance, insurance, leasing, investment licensed by technical ministries, portfolio investment and households (BPS note). Not specific to nickel or batteries.",
        "Foreign investment only (PMA); BPS publishes no provincial table of domestic investment (PMDN).",
        "The four new Papua provinces have values from 2023; earlier, Papua (94) and Papua Barat (91) cover the pre-split areas.",
    ],
    "checks": {"passed": [], "provinces_vs_indonesia": sums, "flags": []},
}

# Layers 1, 2 and 6: every province, indicator and year is present except the Papua split
expected = {(p, i, str(y)) for p in provinces for i in INDICATORS for y in YEARS if p not in NEW_PROVINCES or y >= FIRST_SPLIT_YEAR}
out = cleaning.write_dataset(
    rows, KEYS,
    allowed={"province_code": provinces, "indicator": list(INDICATORS)},
    expected=expected,
    csv_path=OUT_CSV, meta=meta, raw_files=[RAW_PROVINCES, RAW_API],
)

# Report what was written
print(f"{OUT_CSV.name}: {len(out)} rows; {sums}")
