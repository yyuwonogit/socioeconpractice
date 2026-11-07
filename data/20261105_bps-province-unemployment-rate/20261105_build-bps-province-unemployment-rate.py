from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# Load the shared cleaning module from tools/
import sys
sys.path.insert(0, str(ROOT / "tools"))
import cleaning

# Parameters

# Raw files: the BPS province list that every region code is matched against, and BPS WebAPI var 543 (open
# unemployment rate by province, Sakernas February and August rounds) for 2023-2025, the years this dataset covers
RAW_PROVINCES = ROOT / "raw/province-codes/20261102_bps-province-codes-2025-s1.json"
RAW_TPT = ROOT / "raw/labour/20261103_bps-unemployment-rate-by-province-2023-2025.json"

# How each raw file is written, declared after opening it
READ_CONTEXT = {
    RAW_PROVINCES: {"encoding": "utf-8", "numbers": "none: every code and name is a JSON string",
                    "missing": "none: every record carries kode_bps, nama_bps, kode_dagri and nama_dagri",
                    "unit": None},
    RAW_TPT: {"encoding": "utf-8", "numbers": "JSON numbers, decimal point, no thousands separator",
              "missing": "key absent from datacontent", "var": 543, "unit": "Persen", "decimals": 2},
}

# Survey rounds kept, by the table's turtahun label: Sakernas February (S1) and August (S2). The table's third column,
# 'Tahunan' (yearly), is left out so each value appears once
ROUNDS = {"Februari": "S1", "Agustus": "S2"}
YEARS = [2023, 2024, 2025]

# The four Papua provinces formed in 2022 that this table reports apart only from 2024; in 2023 their areas sit inside
# Papua Barat (91) and Papua (94)
NEW_PAPUA = {"92": "91", "95": "94", "96": "94", "97": "94"}
NEW_PAPUA_FROM = 2024

# Indicator code, its unit and multiplier to base units, and the plausible range in percent (values outside are
# flagged in the metadata)
INDICATOR = "open_unemployment_rate"
UNIT = "percent of the labour force (Persen)"
PLAUSIBLE = (0, 25)

# Output beside this script; the metadata JSON is written next to it by cleaning.write_dataset
OUT_CSV = HERE / "20261105_bps-province-unemployment-rate.csv"

# Steps

# Read the BPS province list that every region code is matched against
provinces, lookup = cleaning.load_bps_provinces(RAW_PROVINCES)

# Read the WebAPI table with the variable, unit and decimals READ_CONTEXT declares; every datacontent key must decode
c = READ_CONTEXT[RAW_TPT]
table, records = cleaning.read_webapi_table(RAW_TPT, var=c["var"], unit=c["unit"], decimals=c["decimals"],
                                            encoding=c["encoding"])

# Keep the February and August rounds, one row per province, round and value, each region matched to its BPS code
rows = []
for r in records:
    if r["turtahun_label"] not in ROUNDS:
        continue
    rows.append({"province_code": cleaning.webapi_region_code(r["vervar"], r["vervar_label"], lookup),
                 "indicator": INDICATOR, "period": f"{r['year']}{ROUNDS[r['turtahun_label']]}", "status": "",
                 "value": r["value"]})

# The expected rows: Indonesia and every province in every round, except the new Papua provinces before 2024
periods = [f"{y}{s}" for y in YEARS for s in ROUNDS.values()]
codes = sorted(provinces) + [cleaning.NATIONAL_CODE]
expected = {(code, INDICATOR, p) for code in codes for p in periods
            if not (code in NEW_PAPUA and int(p[:4]) < NEW_PAPUA_FROM)}

# Flag any rate outside the plausible range (layer 5)
flags = cleaning.flag_outside(rows, f"{INDICATOR} within {PLAUSIBLE[0]}-{PLAUSIBLE[1]}%", *PLAUSIBLE)

# The metadata: source, indicator, rounds, region codes, the declared gap and the checks
meta = {
    "title": "Open unemployment rate by province, Sakernas February and August rounds, 2023-2025",
    "source": "BPS WebAPI var 543 'Tingkat Pengangguran Terbuka Menurut Provinsi' (Sakernas)",
    "last_update": table.get("last_update"),
    "bps_note": table["var"][0].get("note", ""),
    "provinces": provinces,
    "national_code": cleaning.NATIONAL_CODE,
    "indicators": {INDICATOR: {"unit": UNIT, "multiplier_to_base": 1,
                               "definition": "unemployed persons as a percentage of the labour force",
                               "source": "BPS WebAPI var 543", "periods": f"{periods[0]}-{periods[-1]}"}},
    "periods": {"S1": "Sakernas February round", "S2": "Sakernas August round"},
    "gaps": {code: f"no value before {NEW_PAPUA_FROM}: the table reports this province apart from {NEW_PAPUA_FROM}; "
                   f"in 2023 its area is inside {NEW_PAPUA[code]}" for code in NEW_PAPUA},
    "read_context": {Path(p).relative_to(ROOT).as_posix(): v for p, v in READ_CONTEXT.items()},
    "checks": {"passed": ["plausibility"] if not flags else [], "flags": flags},
}

# Check and write the CSV and its metadata; nothing is written if a check fails
allowed = {"province_code": set(codes), "indicator": {INDICATOR}, "period": set(periods)}
cleaning.write_dataset(rows, ["province_code", "indicator", "period"], allowed, expected, OUT_CSV, meta,
                       [RAW_PROVINCES, RAW_TPT])
print(f"Wrote {len(rows)} rows for {len(periods)} rounds; flags: {len(flags)}")
