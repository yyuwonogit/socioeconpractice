from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# Load the shared cleaning module from tools/
import sys
sys.path.insert(0, str(ROOT / "tools"))
import cleaning

import pandas as pd
import pdfplumber

# Parameters

# Raw inputs: the BPS province list and the August 2025 labour force report
RAW_PROVINCES = ROOT / "raw/province-codes/20261102_bps-province-codes-2025-s1.json"
RAW_PDF = ROOT / "raw/labour/20261116_bps-keadaan-angkatan-kerja-agustus-2025.pdf"

# Dataset whose provincial totals (Tabel 107, same survey round) check this table's totals
CHECK_TOTALS = ROOT / "data/20261116_bps-province-workers-by-education/20261116_bps-province-workers-by-education.csv"

# Output; the metadata JSON is written beside it with a -metadata suffix
OUT_CSV = HERE / "20261116_bps-province-workers-by-industry.csv"

KEYS = ["province_code", "indicator", "sector", "period"]
PERIOD = "2025"

# How the report writes Table 112, read from opening the PDF: PDF pages 221-222 hold industries A-I and
# pages 223-224 hold J to R,S,T,U and the total, for the same province rows; whole persons with "." as the
# thousands separator; NA where BPS publishes no estimate; a 6.5-point superscript 2 after a value marks a
# relative standard error of 25-50%. The watermark is dropped by pdf_visible_lines.
READ_CONTEXT = {
    "pages": {221: ["A", "B", "C", "D", "E", "F", "G", "H", "I"], 222: ["A", "B", "C", "D", "E", "F", "G", "H", "I"],
              223: ["J", "K", "L", "MN", "O", "P", "Q", "RSTU", "TOTAL"], 224: ["J", "K", "L", "MN", "O", "P", "Q", "RSTU", "TOTAL"]},
    "page_text": {221: ["Tabel 112 Penduduk Berumur 15 Tahun ke Atas yang Bekerja Selama Seminggu Terakhir Menurut Provinsi dan Lapangan",
                        "Pekerjaan Utama di Indonesia, Agustus 2025", "Province A B C D E F G H I"],
                  222: ["Lanjutan Tabel/Continued Table 112", "Province A B C D E F G H I"],
                  223: ["Lanjutan Tabel/Continued Table 112", "Province J K L M,N O P Q R,S,T,U Total"],
                  224: ["Lanjutan Tabel/Continued Table 112", "Province J K L M,N O P Q R,S,T,U Total",
                        "B. Pertambangan dan Penggalian/Mining and Quarrying",
                        "2 Kesalahan Baku Relatif 25%≤RSE≤50%/Relative standard error 25%≤RSE≤50%"]},
    "decimal": ",", "thousands": ".", "no_value": ("NA",),
    "marker": {"text": "2", "status": "rse25-50"},
    # Jawa Tengah mining is printed without its thousands separator; the row total holds with 111.071
    "cell_fixes": {("Jawa Tengah", "B"): ("111071", "111.071")},
}

SECTORS = {
    "A": "Pertanian, Kehutanan, dan Perikanan (agriculture, forestry and fishing)",
    "B": "Pertambangan dan Penggalian (mining and quarrying)",
    "C": "Industri Pengolahan (manufacturing)",
    "D": "Pengadaan Listrik, Gas, Uap/Air Panas, dan Udara Dingin (electricity, gas, steam and air conditioning)",
    "E": "Treatment Air, Air Limbah, Sampah dan Remediasi (water supply, sewerage and waste)",
    "F": "Konstruksi (construction)",
    "G": "Perdagangan Besar dan Eceran, Reparasi Mobil dan Sepeda Motor (trade and vehicle repair)",
    "H": "Pengangkutan dan Pergudangan (transport and storage)",
    "I": "Penyediaan Akomodasi dan Makan Minum (accommodation and food)",
    "J": "Informasi dan Komunikasi (information and communication)",
    "K": "Aktivitas Keuangan dan Asuransi (finance and insurance)",
    "L": "Real Estat (real estate)",
    "MN": "Aktivitas Profesional dan Perusahaan (professional, administrative and support, M and N)",
    "O": "Administrasi Pemerintahan, Pertahanan, dan Jaminan Sosial Wajib (public administration)",
    "P": "Pendidikan (education)",
    "Q": "Aktivitas Kesehatan dan Aktivitas Sosial (health and social work)",
    "RSTU": "Aktivitas Jasa Lainnya (other services, R to U)",
    "TOTAL": "Jumlah (all industries)",
}
PARTS = [s for s in SECTORS if s != "TOTAL"]

INDICATORS = {
    "employed_persons_august": {"name": "Penduduk berumur 15 tahun ke atas yang bekerja selama seminggu terakhir, Sakernas Agustus (employed persons aged 15 and over, August survey), by main industry",
                                "unit": "persons", "multiplier": 1,
                                "source": "BPS, Keadaan Angkatan Kerja di Indonesia Agustus 2025, Tabel 112"},
}

# Sum checks in whole persons, on rows and columns with no NA cell
TOLERANCE = 2

# Plausibility: mining share of employment, percent
PLAUSIBLE = {"mining_share_pct": (0, 15)}

# Functions

def identity_checks(df, gaps):
    """Layer 3: industries sum to TOTAL in rows without NA, and provinces sum to Indonesia in columns without NA."""
    wide = df.pivot(index="province_code", columns="sector", values="value")
    na_rows = {g["province_code"] for g in gaps}
    na_columns = {g["column"] for g in gaps}
    full = wide.drop(index=[c for c in na_rows if c in wide.index])
    checks = [cleaning.check_sum(full[PARTS].sum(axis=1), full["TOTAL"], TOLERANCE, "industries to TOTAL (rows without NA)")]
    columns = [s for s in SECTORS if s not in na_columns]
    provinces = wide.drop(index=cleaning.NATIONAL_CODE)[columns]
    checks.append(cleaning.check_sum(provinces.sum(), wide.loc[cleaning.NATIONAL_CODE, columns], TOLERANCE, "provinces to Indonesia (columns without NA)"))
    checks.append({"rows_with_na": sorted(na_rows), "columns_with_na": sorted(na_columns)})
    return checks


def cross_check(df):
    """Layer 4: each province's total equals Tabel 107's total for the same survey round."""
    other = pd.read_csv(CHECK_TOTALS, dtype={"province_code": str, "period": str, "status": str}, keep_default_na=False)
    other = other[other["education"] == "TOTAL"].set_index("province_code")["value"]
    ours = df[df["sector"] == "TOTAL"].set_index("province_code")["value"]
    assert set(ours.index) == set(other.index)
    differ = ours[ours != other[ours.index]]
    if len(differ):
        raise ValueError(f"totals differ from Tabel 107: {differ.to_dict()}")
    return {"TOTAL = Tabel 107 TOTAL (data/20261116_bps-province-workers-by-education)": int(len(ours))}


def plausibility_flags(df):
    """Layer 5: mining share of employment outside its range."""
    wide = df.pivot(index="province_code", columns="sector", values="value")
    share = (wide["B"] / wide["TOTAL"] * 100).dropna()
    return cleaning.flag_outside([{"province_code": c, "period": PERIOD, "value": v} for c, v in share.items()],
                                 "mining_share_pct", *PLAUSIBLE["mining_share_pct"])

# Steps

# Read the BPS province list that every region name and code is matched against
provinces, lookup = cleaning.load_bps_provinces(RAW_PROVINCES)

# Read Table 112, checking each page still carries its title, column headers and footnotes
c = READ_CONTEXT
with pdfplumber.open(RAW_PDF) as pdf:
    for number, needles in c["page_text"].items():
        text = "\n".join(" ".join(w["text"] for w in line) for line in cleaning.pdf_visible_lines(pdf.pages[number - 1]))
        for needle in needles:
            cleaning.require_text(text, needle, f"page {number}")
    cells, gaps = cleaning.bps_report_province_table(
        pdf, c["pages"], lookup, marker_status=c["marker"]["status"], marker_text=c["marker"]["text"],
        no_value=c["no_value"], cell_fixes=c["cell_fixes"], decimal=c["decimal"], thousands=c["thousands"])
rows = [{"province_code": x["province_code"], "indicator": "employed_persons_august", "sector": x["column"],
         "period": PERIOD, "status": x["status"], "value": x["value"]} for x in cells]

# Layers 3 and 4 stop the build on failure
df = pd.DataFrame(rows)
sums = identity_checks(df, gaps)
overlaps = cross_check(df)

# Layer 5: plausibility only flags
flags = plausibility_flags(df)

# Describe the dataset
meta = {
    "title": "BPS employed persons by main industry, by province, Sakernas August 2025, Indonesia",
    "columns": {
        "province_code": "BPS province code (kode_bps); 00 = Indonesia. Names and Kemendagri codes in 'provinces'.",
        "indicator": "Indicator code; definitions in 'indicators'.",
        "sector": "Main industry (KBLI 2020 categories); names in 'sectors'. TOTAL is all industries.",
        "period": "YYYY; the survey month (August) is in the indicator code.",
        "status": "BPS precision marker: rse25-50 where the report marks a relative standard error of 25-50%.",
        "value": "Persons, as published by BPS.",
    },
    "provinces": provinces,
    "sectors": SECTORS,
    "indicators": INDICATORS,
    "source_tables": {"report": {"title": "Keadaan Angkatan Kerja di Indonesia Agustus 2025, Tabel 112: Penduduk Berumur 15 Tahun ke Atas yang Bekerja Selama Seminggu Terakhir Menurut Provinsi dan Lapangan Pekerjaan Utama di Indonesia, Agustus 2025",
                                 "pages": "PDF pages 221-224 (printed pages 163-166)", "file": str(RAW_PDF.relative_to(ROOT))}},
    "gaps": {"meaning": {"NA": "BPS publishes no estimate for the cell"}, "cells": gaps},
    "notes": [
        "BPS does not split mining and quarrying (B) into coal and other mining in this table.",
        "Jawa Tengah mining (B) is printed '111071' without its thousands separator; it is read as 111,071, and Jawa Tengah's industries then sum to its total.",
        "Rows and columns containing NA cells are left out of the sum checks, because NA cells are estimates BPS does not publish.",
        "Shares are derived in analysis/.",
    ],
    "checks": {
        "passed": ["identities", "cross-source"],
        "identities": sums,
        "cross_source_overlaps": overlaps,
        "plausible_ranges": PLAUSIBLE,
        "flags": flags,
    },
}

# Layers 1, 2 and 6: every province and industry is present except the NA cells
gap_keys = {(g["province_code"], "employed_persons_august", g["column"], PERIOD) for g in gaps}
expected = {(p, "employed_persons_august", s, PERIOD) for p in provinces for s in SECTORS} - gap_keys
out = cleaning.write_dataset(
    rows, KEYS,
    allowed={"province_code": provinces, "indicator": list(INDICATORS), "sector": list(SECTORS)},
    expected=expected,
    csv_path=OUT_CSV, meta=meta, raw_files=[RAW_PROVINCES, RAW_PDF],
    sort_orders={"sector": list(SECTORS)},
)

# Report what was written
print(f"{OUT_CSV.name}: {len(out)} rows, {len(gaps)} NA cells, {len(flags)} plausibility flags, overlaps {overlaps}")
for s in sums:
    print(" ", s)
for f in flags:
    print("  flag:", f)
