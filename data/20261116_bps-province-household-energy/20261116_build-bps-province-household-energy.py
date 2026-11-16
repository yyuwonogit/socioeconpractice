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

# Raw inputs: the BPS province list and the WebAPI responses for var 772 (2020-2025) and var 150 (2021-2025)
RAW_PROVINCES = ROOT / "raw/province-codes/20261102_bps-province-codes-2025-s1.json"
RAW_API = ROOT / "raw/electricity/20261116_bps-webapi-household-lighting-and-cooking-fuel-by-province.jsonl"

# Output; the metadata JSON is written beside it with a -metadata suffix
OUT_CSV = HERE / "20261116_bps-province-household-energy.csv"

KEYS = ["province_code", "indicator", "fuel", "period"]

# How each table writes its values, read from opening the responses: percent with two decimals, "." as the
# decimal mark, Indonesia as region 9999; var 150 has one column per cooking fuel and a Jumlah (100) column
READ_CONTEXT = {
    "772": {"title": "Persentase Rumah Tangga menurut Provinsi dan Sumber Penerangan Utama dari Listrik", "unit": "Persen", "decimals": 2,
            "note_text": "Sumber: Susenas Maret", "indicator": "electric_lighting", "turvar": {"Tidak ada": ""}},
    "150": {"title": "Persentase Rumah Tangga Menurut Provinsi dan Bahan Bakar Utama untuk Memasak", "unit": "Persen", "decimals": 2,
            "note_text": "(1) Termasuk rumah tangga yang tidak memasak", "indicator": "cooking_fuel",
            "turvar": {"Listrik": "electricity", "Gas/Elpiji": "gas_lpg", "Minyak Tanah": "kerosene", "Arang/Briket": "charcoal",
                       "Kayu": "firewood", "Lainnya(1)": "other", "Jumlah": "TOTAL"}},
}

FUELS = {"": "not split by fuel", "electricity": "Listrik", "gas_lpg": "Gas/Elpiji (LPG and piped gas)", "kerosene": "Minyak tanah",
         "charcoal": "Arang/briket", "firewood": "Kayu", "other": "Lainnya, including households that do not cook", "TOTAL": "Jumlah (100)"}
INDICATORS = {
    "electric_lighting": {"name": "Persentase rumah tangga dengan sumber penerangan utama listrik (households whose main lighting is electric, PLN or non-PLN), Susenas Maret",
                          "unit": "percent of households", "multiplier": 1, "source": "BPS WebAPI var 772"},
    "cooking_fuel": {"name": "Persentase rumah tangga menurut bahan bakar utama untuk memasak (households by main cooking fuel), Susenas",
                     "unit": "percent of households", "multiplier": 1, "source": "BPS WebAPI var 150"},
}
YEARS = {"electric_lighting": range(2020, 2026), "cooking_fuel": range(2021, 2026)}

# Papua split: the four new provinces have values from 2024 in both tables
NEW_PROVINCES = {"92", "95", "96", "97"}
FIRST_SPLIT_YEAR = 2024

# Fuel shares are rounded to two decimals, so seven parts can miss 100 by a few hundredths
TOLERANCE_PT = 0.05

PLAUSIBLE = {"electric_lighting": (60, 100)}

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
        out.append({"province_code": code, "indicator": c["indicator"], "fuel": c["turvar"][tv], "period": year, "status": "", "value": value})
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

# Layer 3: cooking fuels sum to the total (100) for every province and year
df = pd.DataFrame(rows)
cook = df[df["indicator"] == "cooking_fuel"].pivot_table(index=["province_code", "period"], columns="fuel", values="value")
parts = [f for f in READ_CONTEXT["150"]["turvar"].values() if f != "TOTAL"]
# Rows with an empty fuel cell (DKI Jakarta 2021) cannot add up and are left out of the check
full = cook[cook[parts].notna().all(axis=1)]
sums = [cleaning.check_sum(full[parts].sum(axis=1), full["TOTAL"], TOLERANCE_PT, "cooking fuels to Jumlah (rows without empty cells)"),
        {"rows_with_empty_cells": [list(i) for i in cook.index.difference(full.index)]}]

# Completeness: every province and year (Papua split aside); fuel cells BPS leaves empty are listed as gaps
expected_cells = set()
for indicator, years in YEARS.items():
    fuels = [""] if indicator == "electric_lighting" else list(READ_CONTEXT["150"]["turvar"].values())
    for y in years:
        for p in provinces:
            if p in NEW_PROVINCES and y < FIRST_SPLIT_YEAR:
                continue
            expected_cells |= {(p, indicator, f, str(y)) for f in fuels}
found = {(r["province_code"], r["indicator"], r["fuel"], r["period"]) for r in rows}
gaps = sorted(expected_cells - found)
assert all(g[1] == "cooking_fuel" and g[2] not in ("TOTAL", "electricity", "gas_lpg") for g in gaps), gaps

# Layer 5: plausibility only flags
flags = cleaning.flag_outside([{k: r[k] for k in KEYS} | {"value": r["value"]} for r in rows if r["indicator"] == "electric_lighting"],
                              "electric_lighting", *PLAUSIBLE["electric_lighting"])

# Describe the dataset
meta = {
    "title": "BPS provincial household electric lighting (2020-2025) and main cooking fuel (2021-2025), Indonesia",
    "columns": {
        "province_code": "BPS province code (kode_bps); 00 = Indonesia. Names and Kemendagri codes in 'provinces'.",
        "indicator": "Indicator code; definitions in 'indicators'.",
        "fuel": "Cooking fuel for cooking_fuel; empty for electric_lighting. Names in 'fuels'.",
        "period": "YYYY.",
        "status": "BPS revision marker; these tables carry none.",
        "value": "Percent of households, as published by BPS.",
    },
    "provinces": provinces,
    "fuels": FUELS,
    "indicators": INDICATORS,
    "source_tables": tables,
    "gaps": {"meaning": "BPS leaves the fuel cell empty (no value published)", "cells": [list(g) for g in gaps]},
    "notes": [
        "The four new Papua provinces have values from 2024; for earlier years Papua (94) and Papua Barat (91) cover the pre-split areas.",
        "Cooking fuel 'other' includes households that do not cook (BPS note). Clean cooking in the SDG 7.1.2 sense (electricity, LPG/gas) is derived in analysis/.",
        "Electric lighting counts PLN and non-PLN electricity.",
    ],
    "checks": {"passed": ["identities"], "identities": sums, "plausible_ranges": PLAUSIBLE, "flags": flags},
}

# Layers 1, 2 and 6: every expected cell is present except the listed gaps
out = cleaning.write_dataset(
    rows, KEYS,
    allowed={"province_code": provinces, "indicator": list(INDICATORS), "fuel": list(FUELS)},
    expected=expected_cells - set(gaps),
    csv_path=OUT_CSV, meta=meta, raw_files=[RAW_PROVINCES, RAW_API],
    sort_orders={"fuel": list(FUELS)},
)

# Report what was written
print(f"{OUT_CSV.name}: {len(out)} rows, {len(gaps)} empty fuel cells, {len(flags)} plausibility flags; {sums}")
for f in flags:
    print("  flag:", f)
