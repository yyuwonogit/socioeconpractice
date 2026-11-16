from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# Load the shared cleaning module from tools/
import sys
sys.path.insert(0, str(ROOT / "tools"))
import cleaning

import re

import pandas as pd
import pdfplumber

# Parameters

# Raw inputs: the BPS province list and the DJPK 2024 general transfer allocation table (PDF, uploaded by the user)
RAW_PROVINCES = ROOT / "raw/province-codes/20261102_bps-province-codes-2025-s1.json"
RAW_PDF = ROOT / "raw/fiscal/20261116_rincian-alokasi-dau-dbh-ta-2024.pdf"

# Output; the metadata JSON is written beside it with a -metadata suffix
OUT_CSV = HERE / "20261116_djpk-province-dbh-2024.csv"

KEYS = ["province_code", "indicator", "period"]
PERIOD = "2024"

# How the PDF writes the table, read from opening it: an Excel export, 6 pages, one row per local
# government (province governments as "Provinsi X", then regencies and cities), numbered in column 1,
# values in thousand rupiah with "." as the thousands separator and no decimals, "-" for no allocation,
# and a JUMLAH row at the end. Each page repeats a row of column numbers (1, 2, 3, ...) that fixes the
# column positions. Column words are joined before parsing because some cells print as two words.
READ_CONTEXT = {
    "pages": 6,
    "title_text": ["RINCIAN DANA TRANSFER UMUM", "TAHUN ANGGARAN 2024", "MENURUT PROVINSI/KABUPATEN/KOTA"],
    "unit_text": "(dalam ribuan rupiah)",
    "header_text": ["PPH", "PBB", "CHT", "IIUPH/PSDH", "DR", "MIGAS", "MINERBA", "PERIKANAN", "PANAS", "BUMI", "SAWIT"],
    "decimal": ",", "thousands": ".", "decimals": 0,
    # A dash is a nil allocation: the totals in columns 6, 13 and 15 equal the sum of their parts only
    # when a dash counts as zero (checked below), so a dash is read as 0 here, not as a missing value
    "nil": "-",
    "province_prefix": "Provinsi ",
    "total_row": "JUMLAH",
    "label_fixes": {"Bangka Belitung": "KEPULAUAN BANGKA BELITUNG"},
}

# Columns 3-15 (the DBH block), by the column number printed in the table; columns 16-23 (DAU) are not read
COLUMNS = {
    3: "dbh_pph", 4: "dbh_pbb", 5: "dbh_cht", 6: "dbh_tax_total",
    7: "dbh_forestry_iiuph_psdh", 8: "dbh_forestry_dr", 9: "dbh_oil_gas", 10: "dbh_minerba",
    11: "dbh_fisheries", 12: "dbh_geothermal", 13: "dbh_sda_total", 14: "dbh_palm_oil", 15: "dbh_total",
}
LAST_COLUMN = 23

INDICATORS = {
    "dbh_pph": "DBH Pajak: Pajak Penghasilan (PPh, income tax)",
    "dbh_pbb": "DBH Pajak: Pajak Bumi dan Bangunan (PBB, land and building tax)",
    "dbh_cht": "DBH Pajak: Cukai Hasil Tembakau (CHT, tobacco excise)",
    "dbh_tax_total": "Total DBH Pajak (tax revenue sharing) = PPh + PBB + CHT",
    "dbh_forestry_iiuph_psdh": "DBH SDA Kehutanan: IIUPH/PSDH (forestry licence fees and resource provision)",
    "dbh_forestry_dr": "DBH SDA Kehutanan: Dana Reboisasi (DR, reforestation fund)",
    "dbh_oil_gas": "DBH SDA Minyak dan Gas Bumi (MIGAS, oil and gas)",
    "dbh_minerba": "DBH SDA Mineral dan Batubara (MINERBA, minerals and coal; DJPK does not split coal from other minerals)",
    "dbh_fisheries": "DBH SDA Perikanan (fisheries)",
    "dbh_geothermal": "DBH SDA Panas Bumi (geothermal)",
    "dbh_sda_total": "Total DBH SDA (natural resource revenue sharing) = IIUPH/PSDH + DR + MIGAS + MINERBA + PERIKANAN + PANAS BUMI",
    "dbh_palm_oil": "DBH Lainnya: Sawit (palm oil)",
    "dbh_total": "Total DBH = DBH Pajak + DBH SDA + DBH Sawit",
}

# Identities the table prints in its column headers
IDENTITIES = {
    "dbh_tax_total": ["dbh_pph", "dbh_pbb", "dbh_cht"],
    "dbh_sda_total": ["dbh_forestry_iiuph_psdh", "dbh_forestry_dr", "dbh_oil_gas", "dbh_minerba", "dbh_fisheries", "dbh_geothermal"],
    "dbh_total": ["dbh_tax_total", "dbh_sda_total", "dbh_palm_oil"],
}

# The table is in thousand rupiah; parts and totals are whole numbers, so they must agree exactly
TOLERANCE = 0

# Plausibility: DBH Minerba of a province government, thousand rupiah (0 to Rp 10 trillion)
PLAUSIBLE = {"dbh_minerba": (0, 10_000_000_000)}

NUMBER = re.compile(r"^[\d.]+$|^-$")

# Largest gap (points) between two pieces of one printed number; separate cells are 10+ points apart
JOIN_GAP = 1.0

# Functions

def column_bounds(line):
    """Return column number -> (left, right) x bounds from the row of printed column numbers.

    Values are right-aligned and end between the centre of their own column number and the centre
    of the next one, so a word's right edge (x1) places it; the bounds apply to x1.
    """
    centres = {}
    for w in line:
        m = re.match(r"^(\d+)=?$", w["text"])
        if m and int(m.group(1)) not in centres and int(m.group(1)) == len(centres) + 1:
            centres[int(m.group(1))] = (w["x0"] + w["x1"]) / 2
    assert list(centres) == list(range(1, LAST_COLUMN + 1)), sorted(centres)
    xs = [centres[k] for k in range(1, LAST_COLUMN + 1)] + [1e9]
    return {k: (xs[k - 1], xs[k]) for k in range(1, LAST_COLUMN + 1)}


def cells(line, bounds):
    """Group a line's words into column number -> joined text.

    Names are left-aligned and start under the NO column's number, so every word left of column 3
    is the row number (a first word of digits) followed by the name. Long names run past column 3's
    left edge, so a word with letters in it always belongs to the name.
    """
    # Some cells print as two words with no gap ("8" + "4.326.031.897"); join touching number words
    joined = []
    for w in line:
        if joined and NUMBER.match(w["text"]) and NUMBER.match(joined[-1]["text"]) and w["x0"] - joined[-1]["x1"] < JOIN_GAP:
            joined[-1] = {**joined[-1], "text": joined[-1]["text"] + w["text"], "x1": w["x1"]}
        else:
            joined.append(w)
    out = {}
    for w in joined:
        if re.search(r"[A-Za-z]", w["text"]):
            k = 2
        elif w["x1"] <= bounds[3][0]:
            k = 1 if not out and re.fullmatch(r"\d+", w["text"]) else 2
        else:
            k = next(k for k, (lo, hi) in bounds.items() if lo < w["x1"] <= hi)
        out.setdefault(k, []).append(w["text"])
    return {k: (" " if k == 2 else "").join(v) for k, v in out.items()}


def number(text, where):
    """Parse one DBH cell: thousand rupiah, a dash for nil."""
    c = READ_CONTEXT
    if text == c["nil"]:
        return 0.0
    return cleaning.parse_number(text, c["decimal"], c["thousands"], decimals=c["decimals"])


def read_table(pdf):
    """Read every local-government row and the JUMLAH row of the DBH block."""
    c = READ_CONTEXT
    assert len(pdf.pages) == c["pages"], len(pdf.pages)
    rows, total = [], None
    for p, page in enumerate(pdf.pages, start=1):
        lines = cleaning.pdf_visible_lines(page)
        text = "\n".join(" ".join(w["text"] for w in line) for line in lines)
        # Check the page still carries its column labels; the first also carries the title and unit
        for needle in c["header_text"] + (c["title_text"] + [c["unit_text"]] if p == 1 else []):
            cleaning.require_text(text, needle, f"page {p}")
        [header] = [i for i, line in enumerate(lines) if [w["text"] for w in line[:3]] == ["1", "2", "3"]]
        bounds = column_bounds(lines[header])
        for line in lines[header + 1:]:
            cell = cells(line, bounds)
            if cell.get(2) == c["total_row"] or cell.get(1) == c["total_row"]:
                total = {name: number(cell[k], f"{c['total_row']} column {k}") for k, name in COLUMNS.items()}
                continue
            if not re.fullmatch(r"\d+", cell.get(1, "")):
                continue
            assert all(NUMBER.match(cell.get(k, "")) for k in COLUMNS), (p, cell)
            rows.append({"no": int(cell[1]), "name": cell[2],
                         **{name: number(cell[k], f"row {cell[1]} column {k}") for k, name in COLUMNS.items()}})
    assert total is not None, "no JUMLAH row"
    return rows, total


def province_rows(rows, lookup):
    """Return the 38 province-government rows with their BPS codes."""
    c = READ_CONTEXT
    fixes = dict(c["label_fixes"])
    out = {}
    for r in rows:
        if not r["name"].startswith(c["province_prefix"]):
            continue
        name = r["name"][len(c["province_prefix"]):]
        code = cleaning.province_code(fixes.pop(name, name), lookup)
        assert code not in out, (code, r["name"])
        out[code] = r
    assert not fixes, f"label fixes not used: {fixes}"
    return out


def identity_checks(rows, total):
    """Layer 3: printed totals equal their parts in every row, and the rows sum to JUMLAH in every column."""
    df = pd.DataFrame(rows)
    checks = [cleaning.check_sum(df[parts].sum(axis=1), df[whole], TOLERANCE, f"{whole} = {' + '.join(parts)}")
              for whole, parts in IDENTITIES.items()]
    checks.append(cleaning.check_sum(df[list(COLUMNS.values())].sum(), pd.Series(total), TOLERANCE, "all local governments to JUMLAH"))
    return checks

# Steps

# Read the BPS province list that every region name and code is matched against
provinces, lookup = cleaning.load_bps_provinces(RAW_PROVINCES)

# Read the table: every local government and the JUMLAH row
with pdfplumber.open(RAW_PDF) as pdf:
    all_rows, total = read_table(pdf)

# Every row number from 1 to the last appears once, so no row was skipped
numbers = [r["no"] for r in all_rows]
assert numbers == list(range(1, len(numbers) + 1)), "row numbers have gaps or repeats"

# Layer 3: identities and the JUMLAH row stop the build on failure
sums = identity_checks(all_rows, total)

# Keep the 38 province governments; regencies and cities are checked above but not written
by_code = province_rows(all_rows, lookup)
rows = [{"province_code": code, "indicator": name, "period": PERIOD, "status": "", "value": r[name]}
        for code, r in by_code.items() for name in COLUMNS.values()]

# Layer 5: plausibility only flags
flags = cleaning.flag_outside([{"province_code": code, "indicator": "dbh_minerba", "period": PERIOD, "value": r["dbh_minerba"]}
                               for code, r in by_code.items()], "dbh_minerba", *PLAUSIBLE["dbh_minerba"])

# Describe the dataset
meta = {
    "title": "DJPK general transfer allocation 2024: Dana Bagi Hasil (DBH) by type, province governments, Indonesia",
    "columns": {
        "province_code": "BPS province code (kode_bps) of the province government (pemerintah provinsi). Names and Kemendagri codes in 'provinces'.",
        "indicator": "DBH type; definitions in 'indicators'.",
        "period": "YYYY, budget year (tahun anggaran).",
        "status": "Empty; the table carries no markers.",
        "value": "Thousand rupiah, as published.",
    },
    "provinces": {k: v for k, v in provinces.items() if k != cleaning.NATIONAL_CODE},
    "indicators": {k: {"name": v, "unit": "thousand Rp", "multiplier": 1e3, "base_unit": "Rp",
                       "source": "DJPK Kemenkeu, Rincian Dana Transfer Umum TA 2024"} for k, v in INDICATORS.items()},
    "source_tables": {"pdf": {"title": "Rincian Dana Transfer Umum Tahun Anggaran 2024 Menurut Provinsi/Kabupaten/Kota (DAU dan DBH)",
                              "publisher": "Direktorat Jenderal Perimbangan Keuangan (DJPK), Kementerian Keuangan",
                              "file": str(RAW_PDF.relative_to(ROOT)),
                              "received": "uploaded by the user to .inbox on 2026-11-16; the user describes it as the 2024 allocation (pagu alokasi)"}},
    "notes": [
        "Values are budget allocations (pagu) for 2024, not realised transfers (realisasi).",
        "Province-government rows only. The table's regency and city rows are read so that every column can be checked against JUMLAH, but are not written.",
        "A dash in the table is a nil allocation and is written as 0: the table's own totals (columns 6, 13 and 15) and the JUMLAH row hold exactly only with dashes counted as zero.",
        "DAU columns (16-23) are not read.",
        "DBH Minerba covers coal and other minerals together; DJPK publishes no coal-only split.",
        "The table names Kepulauan Bangka Belitung 'Bangka Belitung'; that label is matched by a declared fix.",
    ],
    "checks": {
        "passed": ["identities"],
        "identities": sums,
        "rows_read": {"local_governments": len(all_rows), "province_governments": len(by_code)},
        "plausible_ranges": PLAUSIBLE,
        "flags": flags,
    },
}

# Layers 1, 2 and 6: check structure and completeness, then write the CSV and metadata
expected = {(c, name, PERIOD) for c in provinces if c != cleaning.NATIONAL_CODE for name in COLUMNS.values()}
out = cleaning.write_dataset(
    rows, KEYS,
    allowed={"province_code": [c for c in provinces if c != cleaning.NATIONAL_CODE], "indicator": list(INDICATORS)},
    expected=expected,
    csv_path=OUT_CSV, meta=meta, raw_files=[RAW_PROVINCES, RAW_PDF],
    sort_orders={"indicator": list(INDICATORS)},
)

# Report what was written
print(f"{OUT_CSV.name}: {len(out)} rows from {len(all_rows)} local governments, {len(flags)} plausibility flags")
for s in sums:
    print(" ", s)
print(out[out["indicator"] == "dbh_minerba"].sort_values("value", ascending=False).head(10).to_string(index=False))
