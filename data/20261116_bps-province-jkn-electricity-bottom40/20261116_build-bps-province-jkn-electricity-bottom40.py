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

# Raw inputs: the BPS province list and the WebAPI responses for var 2279 (2022-2025) and var 1575 (2015-2019)
RAW_PROVINCES = ROOT / "raw/province-codes/20261102_bps-province-codes-2025-s1.json"
RAW_API = ROOT / "raw/welfare/20261116_bps-webapi-jkn-and-bottom40-electricity-by-province.jsonl"

# Output; the metadata JSON is written beside it with a -metadata suffix
OUT_CSV = HERE / "20261116_bps-province-jkn-electricity-bottom40.csv"

KEYS = ["province_code", "indicator", "period"]

# How each table writes its values, read from opening the responses: percent with two decimals, "." as the
# decimal mark, Indonesia as region 9999, one value per province and year
READ_CONTEXT = {
    "2279": {"title": "Persentase Penduduk yang Memiliki Jaminan Kesehatan Nasional (JKN) Menurut Provinsi", "unit": "Persen", "decimals": 2,
             "note_text": "Kepemilikan JKN adalah jika memiliki BPJS PBI, BPJS Non PBI, atau Jamkesda", "indicator": "jkn_coverage"},
    "1575": {"title": "Persentase Rumah Tangga Yang Menggunakan Penerangan Dengan Sumber Listrik (40% Ke Bawah), Menurut Provinsi", "unit": "Persen", "decimals": 2,
             "note_text": "Sumber: Susenas (diolah)", "indicator": "electric_lighting_bottom40"},
}

INDICATORS = {
    "jkn_coverage": {"name": "Persentase penduduk yang memiliki Jaminan Kesehatan Nasional (share of the population with national health insurance: BPJS PBI, BPJS non-PBI or Jamkesda), Susenas Maret",
                     "unit": "percent of population", "multiplier": 1, "source": "BPS WebAPI var 2279"},
    "electric_lighting_bottom40": {"name": "Persentase rumah tangga 40% terbawah yang menggunakan penerangan dengan sumber listrik (share of households in the bottom 40% of expenditure whose lighting is electric), Susenas",
                                   "unit": "percent of households", "multiplier": 1, "source": "BPS WebAPI var 1575 (SDG indicator 7.1.1, first edition; BPS stopped it after 2019)"},
}
YEARS = {"jkn_coverage": range(2022, 2026), "electric_lighting_bottom40": range(2015, 2020)}

# Papua split: the four new provinces have values from this year in each table (never in var 1575)
NEW_PROVINCES = {"92", "95", "96", "97"}
FIRST_SPLIT_YEAR = {"jkn_coverage": 2023, "electric_lighting_bottom40": 9999}

PLAUSIBLE = {"percent": (30, 100)}

# Functions

def read_table(record, lookup):
    """Read one WebAPI response into long rows."""
    var = str(record["var"])
    c = READ_CONTEXT[var]
    table = record["response"]
    v = table["var"][0]
    where = f"var {var} {record['year']}"
    cleaning.require_text(v["label"], c["title"], where)
    assert v["unit"] == c["unit"] and int(v["decimal"]) == c["decimals"], (where, v["unit"], v["decimal"])
    cleaning.require_text(cleaning.html_to_text(v["note"]), c["note_text"], where)
    out = []
    for code, tv, tt, year, text in cleaning.bps_api_province_cells(table, lookup):
        value = cleaning.parse_number(text, ".", None, max_decimals=c["decimals"])
        out.append({"province_code": code, "indicator": c["indicator"], "period": year, "status": "", "value": value})
    return out

# Steps

# Read the BPS province list that every region name and code is matched against
provinces, lookup = cleaning.load_bps_provinces(RAW_PROVINCES)

# Read every response, one table and year per line
rows, tables = [], {}
for record in cleaning.read_jsonl(RAW_API):
    out = read_table(record, lookup)
    assert {r["period"] for r in out} == {record["year"]}
    rows += out
    tables[f"webapi {record['var']} {record['year']}"] = {"request": record["request"], "last_update": record["response"].get("last_update")}

# Layer 5: plausibility only flags
flags = cleaning.flag_outside([{k: r[k] for k in KEYS} | {"value": r["value"]} for r in rows], "percent", *PLAUSIBLE["percent"])

# Describe the dataset
meta = {
    "title": "BPS provincial JKN health-insurance coverage (2022-2025) and electric lighting among the poorest 40% of households (2015-2019), Indonesia",
    "columns": {
        "province_code": "BPS province code (kode_bps); 00 = Indonesia. Names and Kemendagri codes in 'provinces'.",
        "indicator": "Indicator code; definitions in 'indicators'.",
        "period": "YYYY.",
        "status": "BPS revision marker; these tables carry none.",
        "value": "Percent, as published by BPS.",
    },
    "provinces": provinces,
    "indicators": INDICATORS,
    "source_tables": tables,
    "notes": [
        "JKN coverage counts BPJS PBI (state-paid), BPJS non-PBI and Jamkesda (regional schemes). It is health insurance, not BPJS Ketenagakerjaan (employment social security), for which BPS publishes no provincial table.",
        "The four new Papua provinces have JKN values from 2023; for 2022, Papua (94) and Papua Barat (91) cover the pre-split areas.",
        "Electric lighting among the poorest 40% (var 1575) stops in 2019 and covers the 34 pre-2022 provinces; Papua (94) and Papua Barat (91) are the pre-split areas, and the four new Papua provinces have no value.",
    ],
    "checks": {"passed": [], "plausible_ranges": PLAUSIBLE, "flags": flags},
}

# Layers 1, 2 and 6: every province and year is present except the Papua split
expected = {(p, i, str(y)) for i, years in YEARS.items() for y in years for p in provinces
            if p not in NEW_PROVINCES or y >= FIRST_SPLIT_YEAR[i]}
out = cleaning.write_dataset(
    rows, KEYS,
    allowed={"province_code": provinces, "indicator": list(INDICATORS)},
    expected=expected,
    csv_path=OUT_CSV, meta=meta, raw_files=[RAW_PROVINCES, RAW_API],
)

# Report what was written
print(f"{OUT_CSV.name}: {len(out)} rows, {len(flags)} plausibility flags")
for f in flags:
    print("  flag:", f)
