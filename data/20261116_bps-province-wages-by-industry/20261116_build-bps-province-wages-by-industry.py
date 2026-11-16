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

# Raw inputs: the BPS province list and the WebAPI responses for var 2475 (2024-2025)
RAW_PROVINCES = ROOT / "raw/province-codes/20261102_bps-province-codes-2025-s1.json"
RAW_API = ROOT / "raw/labour/20261116_bps-webapi-wages-by-province-and-industry.jsonl"

# Output; the metadata JSON is written beside it with a -metadata suffix
OUT_CSV = HERE / "20261116_bps-province-wages-by-industry.csv"

KEYS = ["province_code", "indicator", "sector", "period"]

# How the table writes its values, read from opening the responses: whole rupiah, no thousands separator,
# Indonesia as region 9999; an empty cell means BPS suppressed the estimate (RSE of 50% or more)
READ_CONTEXT = {
    "title": "Rata-Rata Upah/Gaji Bersih Sebulan Buruh/Karyawan/Pegawai menurut Provinsi dan Lapangan Usaha di 17 Sektor",
    "unit": "Rupiah", "decimals": 0, "national_label": "RATA-RATA",
    "note_text": "Data yang kosong menandakan bahwa nilai RSE ≥ 50%, sehingga data tidak ditampilkan",
    "turvar": {"A Pertanian, Kehutanan dan Perikanan": "A", "B Pertambangan dan Penggalian": "B", "C Industri Pengolahan": "C",
               "D Pengadaan Listrik dan Gas": "D", "E Pengadaan Air, Pengelolaan Sampah, Limbah dan Daur Ulang": "E",
               "F Konstruksi": "F", "G Perdagangan Besar dan Eceran, Reparasi Mobil dan Sepeda Motor": "G",
               "H Transportasi dan Pergudangan": "H", "I Penyediaan Akomodasi dan Makan Minum": "I", "J Informasi dan Komunikasi": "J",
               "K Jasa Keuangan dan Asuransi": "K", "L Real Estate": "L", "M,N Jasa Perusahaan": "MN",
               "O Administrasi Pemerintahan, Pertahanan dan Jaminan Sosial Wajib": "O", "P Jasa Pendidikan": "P",
               "Q Jasa Kesehatan dan Kegiatan Sosial": "Q", "R,S,T,U Jasa Lainnya": "RSTU", "Total": "TOTAL"},
    "turtahun": {"Februari": "wage_monthly_february", "Agustus": "wage_monthly_august", "Tahunan": None},
}

SECTORS = {code: label for label, code in READ_CONTEXT["turvar"].items()}
INDICATORS = {
    "wage_monthly_february": {"name": "Rata-rata upah/gaji bersih sebulan buruh/karyawan/pegawai, Sakernas Februari (average net monthly wage of employees, February survey)",
                              "unit": "Rp per month", "multiplier": 1, "source": "BPS WebAPI var 2475"},
    "wage_monthly_august": {"name": "Rata-rata upah/gaji bersih sebulan buruh/karyawan/pegawai, Sakernas Agustus (average net monthly wage of employees, August survey)",
                            "unit": "Rp per month", "multiplier": 1, "source": "BPS WebAPI var 2475"},
}
YEARS = ["2024", "2025"]

# Plausibility: wages in Rp per month, and mining wage relative to the all-industry average
PLAUSIBLE = {"wage": (500_000, 20_000_000), "mining_relative_wage": (0.5, 4.0)}

# Functions

def read_table(record, lookup):
    """Read one WebAPI response into long rows; empty cells (suppressed) give no row."""
    c = READ_CONTEXT
    table = record["response"]
    v = table["var"][0]
    where = f"var {record['var']} {record['year']}"
    cleaning.require_text(v["label"], c["title"], where)
    assert v["unit"] == c["unit"] and int(v["decimal"]) == c["decimals"], (where, v["unit"], v["decimal"])
    cleaning.require_text(cleaning.html_to_text(v["note"]), c["note_text"], where)
    assert {cleaning.html_to_text(t["label"]).strip() for t in table["turvar"]} == set(c["turvar"]), where
    out = []
    for code, tv, tt, year, text in cleaning.bps_api_province_cells(table, lookup, national_label=c["national_label"]):
        indicator = c["turtahun"][tt]
        assert indicator is not None, (where, "annual wage column now filled")
        value = cleaning.parse_number(text, ".", None, decimals=c["decimals"])
        out.append({"province_code": code, "indicator": indicator, "sector": c["turvar"][tv], "period": year, "status": "", "value": value})
    return out


def plausibility_flags(df):
    """Layer 5: wages outside their range, and mining wages far from the provincial average."""
    flags = cleaning.flag_outside([{"province_code": r.province_code, "indicator": r.indicator, "sector": r.sector, "period": r.period, "value": r.value}
                                   for r in df.itertuples()], "wage", *PLAUSIBLE["wage"])
    wide = df.pivot_table(index=["province_code", "indicator", "period"], columns="sector", values="value")
    rel = (wide["B"] / wide["TOTAL"]).dropna()
    flags += cleaning.flag_outside([{"province_code": c, "indicator": i, "period": p, "value": x} for (c, i, p), x in rel.items()],
                                   "mining_relative_wage", *PLAUSIBLE["mining_relative_wage"])
    return flags

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
assert sorted({r["period"] for r in rows}) == YEARS

# Every province and Indonesia must have an all-industry average in each August round, which the
# location matrix uses; other cells, including February averages (Kalimantan Barat 2025), may be suppressed
df = pd.DataFrame(rows)
for (indicator, period), g in df[(df["sector"] == "TOTAL") & (df["indicator"] == "wage_monthly_august")].groupby(["indicator", "period"]):
    assert set(g["province_code"]) == set(provinces), (indicator, period)
suppressed = sorted({(p, i, s, y) for p in provinces for i in INDICATORS for s in SECTORS for y in YEARS}
                    - {(r["province_code"], r["indicator"], r["sector"], r["period"]) for r in rows})

# Layer 5: plausibility only flags
flags = plausibility_flags(df)

# Describe the dataset
meta = {
    "title": "BPS average net monthly wage of employees by province and 17 industries, Sakernas February and August, 2024-2025, Indonesia",
    "columns": {
        "province_code": "BPS province code (kode_bps); 00 = Indonesia. Names and Kemendagri codes in 'provinces'.",
        "indicator": "Wage by survey round; definitions in 'indicators'.",
        "sector": "Industry (KBLI 2020 categories); names in 'sectors'. TOTAL is all industries.",
        "period": "YYYY.",
        "status": "Empty: the WebAPI table does not mark which values have an RSE of 25-50% (its note says some do).",
        "value": "Rupiah per month, as published.",
    },
    "provinces": provinces,
    "sectors": SECTORS,
    "indicators": INDICATORS,
    "source_tables": {"webapi 2475": {"title": READ_CONTEXT["title"], "unit": "Rupiah", "responses": tables}},
    "gaps": {"meaning": "BPS leaves the cell empty because the estimate's relative standard error is 50% or more", "cells": [list(k) for k in suppressed]},
    "notes": [
        "Wages are for employees (buruh/karyawan/pegawai) only, net of deductions, from the main job.",
        "Some published values have a relative standard error of 25-50% (BPS table note); the WebAPI does not say which.",
        "The annual (Tahunan) column of the table is empty.",
    ],
    "checks": {"passed": [], "plausible_ranges": PLAUSIBLE, "flags": flags},
}

# Layers 1, 2 and 6: every province, industry, round and year is present except the suppressed cells
expected = {(p, i, s, y) for p in provinces for i in INDICATORS for s in SECTORS for y in YEARS} - set(suppressed)
out = cleaning.write_dataset(
    rows, KEYS,
    allowed={"province_code": provinces, "indicator": list(INDICATORS), "sector": list(SECTORS)},
    expected=expected,
    csv_path=OUT_CSV, meta=meta, raw_files=[RAW_PROVINCES, RAW_API],
    sort_orders={"sector": list(SECTORS)},
)

# Report what was written
print(f"{OUT_CSV.name}: {len(out)} rows, {len(suppressed)} suppressed cells, {len(flags)} plausibility flags")
miss_b = [k for k in suppressed if k[1] == "wage_monthly_august" and k[2] == "B" and k[3] == "2025"]
print("  mining wage suppressed, August 2025:", [k[0] for k in miss_b])
for f in flags:
    print("  flag:", f)
