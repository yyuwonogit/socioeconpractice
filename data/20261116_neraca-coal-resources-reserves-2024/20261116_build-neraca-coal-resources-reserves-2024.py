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

# Raw inputs: the BPS province list, the screenshot of Tabel 33 the user sent (the Neraca PDF filed in raw/mining
# ends at Tabel 32, so the screenshot comes from another edition or file), and that Neraca PDF, whose Tabel 31
# national totals check the screenshot's TOTAL INDONESIA row
RAW_PROVINCES = ROOT / "raw/province-codes/20261102_bps-province-codes-2025-s1.json"
RAW_SCREENSHOT = ROOT / "raw/mining/20261116_neraca-tabel-33-coal-resources-reserves-by-province-screenshot.png"
RAW_NERACA = ROOT / "raw/mining/20261116_neraca-sumber-daya-dan-cadangan-mineral-dan-batubara-indonesia-2025.pdf"

# Output; the metadata JSON is written beside it with a -metadata suffix
OUT_CSV = HERE / "20261116_neraca-coal-resources-reserves-2024.csv"

KEYS = ["province_code", "indicator", "period"]
PERIOD = "2024"

# Tabel 33 "Sumber Daya dan Cadangan Batubara Indonesia per Provinsi Tahun 2024", typed from the screenshot
# (an image, so no text can be read from it). Million tonnes, as printed; the image writes "." for thousands
# and "," for decimals, though a few cells mix them ("1,417,40", "12,376,75", "36,268.91", "5,155,77"); the
# values below are the numbers those cells show. Columns, left to right:
COLUMNS = ["exploration_target", "inventory_total", "resource_inferred", "resource_indicated", "resource_measured",
           "resource_total", "resource_verified", "reserve_probable", "reserve_proven", "reserve_total", "reserve_verified"]
TABLE = {
    "Banten":             [5.47, 52.2, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00],
    "Jawa Tengah":        [0.00, 0.80, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00],
    "Jawa Timur":         [0.00, 0.10, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00],
    "Aceh":               [1.16, 20.9, 314.58, 401.94, 362.23, 1042.75, 791.28, 313.70, 193.36, 507.05, 409.40],
    "Sumatra Utara":      [0.00, 14.6, 10.24, 8.48, 7.55, 26.26, 0.00, 0.00, 7.12, 7.12, 0.00],
    "Riau":               [36.92, 525.9, 271.52, 282.00, 303.27, 856.76, 854.76, 185.52, 173.75, 359.27, 358.75],
    "Sumatra Barat":      [1.19, 363.0, 26.30, 19.54, 33.09, 78.94, 28.51, 11.09, 18.11, 29.20, 12.37],
    "Jambi":              [142.37, 1309.1, 1042.78, 1140.65, 1995.48, 4178.90, 3455.55, 632.01, 1068.29, 1700.30, 1574.20],
    "Bengkulu":           [42.75, 211.9, 137.74, 106.06, 171.33, 415.12, 367.59, 42.20, 67.86, 110.06, 93.76],
    "Sumatra Selatan":    [4885.39, 10732.2, 7541.71, 9795.50, 8325.82, 25663.02, 22257.11, 4586.90, 4348.17, 8935.07, 8556.31],
    "Lampung":            [0.00, 107.0, 10.25, 24.28, 60.32, 94.85, 0.00, 60.32, 0.00, 60.32, 0.00],
    "Kalimantan Barat":   [2.26, 463.4, 19.28, 13.15, 38.55, 70.98, 0.00, 3.31, 7.91, 11.22, 0.00],
    "Kalimantan Tengah":  [35.39, 2936.2, 3853.66, 3138.08, 3050.54, 10042.28, 8793.99, 1532.57, 1417.40, 2949.97, 2473.34],
    "Kalimantan Selatan": [7.83, 1846.3, 3481.90, 3414.04, 6635.73, 13531.67, 12376.75, 1310.69, 2756.26, 4066.94, 3644.19],
    "Kalimantan Timur":   [890.55, 14115.8, 8377.75, 13055.48, 17892.13, 39325.36, 36268.91, 5155.77, 7101.24, 12257.02, 11177.66],
    "Kalimantan Utara":   [25.79, 379.8, 857.89, 826.56, 927.34, 2611.79, 2554.54, 580.70, 377.17, 957.87, 941.01],
    "Sulawesi Selatan":   [13.79, 31.3, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00],
    "Sulawesi Barat":     [11.47, 26.3, 1.30, 1.00, 0.85, 3.15, 3.15, 0.00, 0.00, 0.00, 0.00],
    "Sulawesi Tengah":    [0.52, 2.0, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00],
    "Sulawesi Tenggara":  [0.64, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00],
    "Maluku Utara":       [8.22, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00],
    "Papua Barat":        [93.66, 32.8, 6.00, 5.70, 7.20, 19.90, 18.90, 4.09, 0.00, 4.09, 4.09],
    "Papua":              [7.20, 31.4, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00],
}
TOTAL_INDONESIA = [6212.57, 33202.95, 25952.90, 32232.44, 39775.43, 97960.76, 87771.04, 14418.86, 17536.63, 31955.50, 29245.08]

# The table spells Sumatera "Sumatra"
NAME_FIXES = {"Sumatra": "Sumatera"}

# Tabel 31 of the filed Neraca PDF (page 174): national resources and reserves, million tonnes
NERACA_TABLE_31 = {"resource_inferred": 25952.90, "resource_indicated": 32232.44, "resource_measured": 39775.43, "resource_total": 97960.76,
                   "reserve_probable": 14418.87, "reserve_proven": 17536.63, "reserve_total": 31955.50}

# Rounding to two decimals: three parts and a total, each off by up to 0.005, may miss by up to 0.035 (Riau 0.03);
# 23 provinces by up to 0.12
TOLERANCE_ROW = 0.035
TOLERANCE_COLUMN = 0.12

# Cells printed wrongly, with the value the table's own totals require: (province, column) -> (printed, corrected).
# Aceh terukur is printed 362,23; with 326,23 (two digits swapped) both the Aceh row (1.042,75) and the terukur
# column (39.775,43) add up exactly, and with 362,23 both miss by exactly 36
# Papua Barat total resources is printed 19,90; its parts and its verified total give 18,90, and the total column then
# adds up to 97.960,76
CELL_FIXES = {("Aceh", "resource_measured"): (362.23, 326.23), ("Papua Barat", "resource_total"): (19.90, 18.90)}

# Rows whose printed total does not equal the sum of its printed parts, kept as printed (the totals are used)
SOURCE_INCONSISTENCIES = {
}

INDICATORS = {c: {"name": n, "unit": "million tonnes", "multiplier": 1e6, "base_unit": "tonnes",
                  "source": "Badan Geologi ESDM, Neraca Sumber Daya dan Cadangan Mineral dan Batubara Indonesia, Tabel 33 (status December 2024)"}
              for c, n in zip(COLUMNS, ["Target eksplorasi (exploration target)", "Total inventori (total inventory)",
                                        "Sumber daya tereka (inferred resources)", "Sumber daya tertunjuk (indicated resources)",
                                        "Sumber daya terukur (measured resources)", "Sumber daya total (total resources)",
                                        "Sumber daya total terverifikasi (verified total resources)", "Cadangan terkira (probable reserves)",
                                        "Cadangan terbukti (proven reserves)", "Cadangan total (total reserves)",
                                        "Cadangan total terverifikasi (verified total reserves)"])}

# Functions

def check_rows(df):
    """Layer 3: resource classes sum to total resources, reserve classes to total reserves, in every row."""
    out, exceptions = [], []
    for whole, parts in [("resource_total", ["resource_inferred", "resource_indicated", "resource_measured"]),
                         ("reserve_total", ["reserve_probable", "reserve_proven"])]:
        gap = (df[parts].sum(axis=1) - df[whole]).abs()
        bad = [n for n in gap.index if gap[n] > TOLERANCE_ROW]
        declared = {n for (n, c) in SOURCE_INCONSISTENCIES if c == whole}
        if set(bad) != declared:
            raise ValueError(f"{whole}: rows that do not add up {bad}, declared {sorted(declared)}")
        exceptions += bad
        ok = gap.drop(index=bad)
        out.append({"check": f"{' + '.join(parts)} = {whole}", "compared": int(len(ok)), "largest_gap": float(round(ok.max(), 4)), "tolerance": TOLERANCE_ROW})
    return out, exceptions

# Steps

# Read the BPS province list that every province name is matched against
provinces, lookup = cleaning.load_bps_provinces(RAW_PROVINCES)
regions = [c for c in provinces if c != cleaning.NATIONAL_CODE]

# Put the typed table in a frame indexed by province name, then apply the declared cell fixes
df = pd.DataFrame.from_dict(TABLE, orient="index", columns=COLUMNS)
for (name, col), (printed, corrected) in CELL_FIXES.items():
    assert df.loc[name, col] == printed, (name, col, df.loc[name, col])
    df.loc[name, col] = corrected
total = pd.Series(TOTAL_INDONESIA, index=COLUMNS)

# Layer 3: rows add up (except declared source inconsistencies) and provinces add up to TOTAL INDONESIA in every column
sums, exceptions = check_rows(df)
sums.append(cleaning.check_sum(df.sum(), total, TOLERANCE_COLUMN, "provinces = TOTAL INDONESIA"))

# Layer 4: the national row equals the filed Neraca PDF's Tabel 31
for c, v in NERACA_TABLE_31.items():
    assert abs(total[c] - v) <= 0.011, (c, total[c], v)

# Long rows by BPS code; provinces not in the table get no row (no coal data in the Neraca)
rows = []
for name, values in TABLE.items():
    bps_name = " ".join(NAME_FIXES.get(w, w) for w in name.split())
    code = cleaning.province_code(bps_name, lookup)
    rows += [{"province_code": code, "indicator": c, "period": PERIOD, "status": "", "value": float(df.loc[name, c])} for c in COLUMNS]

# Describe the dataset
meta = {
    "title": "Coal resources and reserves by province, status December 2024 (Neraca Sumber Daya dan Cadangan Batubara, Tabel 33)",
    "columns": {
        "province_code": "BPS province code (kode_bps). Names and Kemendagri codes in 'provinces'.",
        "indicator": "Column of Tabel 33; definitions in 'indicators'.",
        "period": "YYYY, status year (December).",
        "status": "Empty.",
        "value": "Million tonnes, as printed.",
    },
    "provinces": {k: v for k, v in provinces.items() if k != cleaning.NATIONAL_CODE},
    "indicators": INDICATORS,
    "source_tables": {"screenshot": {"file": str(RAW_SCREENSHOT.relative_to(ROOT)),
                                     "note": "Screenshot of Tabel 33 sent by the user on 2026-11-16; values typed from it. The filed Neraca PDF ends at Tabel 32, so the original document should be filed when available."},
                      "check": {"file": str(RAW_NERACA.relative_to(ROOT)), "table": "Tabel 31 (national totals), PDF page 174", "use": "check only"}},
    "notes": [
        "Values were typed from an image; every row is checked against its printed totals and every column against TOTAL INDONESIA, and the national row against Tabel 31 of the Neraca PDF.",
        "Provinces not in the table (15 of 38) have no coal resource or reserve data in the Neraca; they have no row here.",
        "Reserves are a stock in the ground, not annual production; the Neraca gives national production only (836.12 million tonnes, Tabel 31, from Pusdatin ESDM December 2023).",
        "The image mixes separators in a few cells ('1,417,40', '12,376,75', '36,268.91', '5,155,77'); they are read as the numbers shown.",
    ] + [f"Corrected cell, {n} {c}: printed {a}, corrected to {b} (the row total and the column total both require it)" for (n, c), (a, b) in CELL_FIXES.items()]
      + [f"Source inconsistency, {n} {c}: {why}" for (n, c), why in SOURCE_INCONSISTENCIES.items()],
    "checks": {"passed": ["identities", "cross-source"], "identities": sums, "row_exceptions": exceptions,
               "cross_source": "TOTAL INDONESIA equals Neraca PDF Tabel 31 for resources (inferred, indicated, measured, total) and reserves (probable, proven, total)",
               "flags": []},
}

# Layers 1, 2 and 6: every listed province has every column
out = cleaning.write_dataset(
    rows, KEYS,
    allowed={"province_code": regions, "indicator": COLUMNS},
    expected={(r["province_code"], r["indicator"], PERIOD) for r in rows},
    csv_path=OUT_CSV, meta=meta, raw_files=[RAW_PROVINCES, RAW_SCREENSHOT, RAW_NERACA],
    sort_orders={"indicator": COLUMNS},
)

# Report what was written
print(f"{OUT_CSV.name}: {len(out)} rows, {len(TABLE)} provinces; {sums}; exceptions {exceptions}")
