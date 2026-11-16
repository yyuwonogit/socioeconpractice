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

# Raw inputs: the BPS province list, the August 2025 labour force report, and the national
# WebAPI table whose August totals check the report's Indonesia row
RAW_PROVINCES = ROOT / "raw/province-codes/20261102_bps-province-codes-2025-s1.json"
RAW_PDF = ROOT / "raw/labour/20261116_bps-keadaan-angkatan-kerja-agustus-2025.pdf"
RAW_API = ROOT / "raw/labour/20261116_bps-webapi-workers-by-status-and-education.jsonl"

# Output; the metadata JSON is written beside it with a -metadata suffix
OUT_CSV = HERE / "20261116_bps-province-workers-by-education.csv"

KEYS = ["province_code", "indicator", "education", "period"]
PERIOD = "2025"

# How the report writes Table 107, read from opening the PDF. Values are whole persons with "." as the
# thousands separator. A 6.5-point superscript 1 after a value marks a relative standard error of
# 25-50%. The pages carry a rotated www.bps.go.id watermark and a white heading left over from the
# February edition ("Februari 2025"); pdf_visible_lines drops both. The visible heading says
# Agustus 2025, and the Indonesia row matches the WebAPI August totals exactly (layer 4).
READ_CONTEXT = {
    "pdf": {
        "pages": [211, 212],
        "page_text": {211: ["Tabel 107 Penduduk Berumur 15 Tahun ke Atas yang Bekerja Selama Seminggu Terakhir Menurut Provinsi dan Pendidikan",
                            "Table Tertinggi yang Ditamatkan di Indonesia, Agustus 2025"],
                      212: ["Lanjutan Tabel/Continued Table 107",
                            "Kesalahan Baku Relatif 25% ≤ RSE ≤ 50%/Relative standard error 25% ≤ RSE ≤ 50%"]},
        "header_text": ["Primary School", "and Below", "Junior High", "Senior High", "Vocational High", "Bachelor, Master,", "or Doctoral Degree"],
        "decimal": ",", "thousands": ".", "unit": "persons (orang)",
        "marker": {"text": "1", "max_size": 7.5, "status": "rse25-50"},
        "national_row": "Jumlah",
    },
    "api": {"title": "Penduduk Berumur 15 Tahun Ke Atas yang Bekerja Selama Seminggu yang Lalu Menurut Status Pekerjaan Utama dan Pendidikan Tertinggi yang Ditamatkan",
            "unit": "Orang", "decimals": 0, "total_row": "Total", "month": "Agustus"},
}

# Report columns, left to right
EDUCATION = {
    "primary_or_less": "Sekolah Dasar ke Bawah (no schooling, primary not completed, or primary school)",
    "junior_secondary": "Sekolah Menengah Pertama, SMP (junior secondary school)",
    "senior_secondary_general": "Sekolah Menengah Atas, SMA (general senior secondary school)",
    "senior_secondary_vocational": "Sekolah Menengah Kejuruan, SMK (vocational senior secondary school)",
    "diploma": "Diploma I/II/III",
    "university": "Diploma IV, S1, S2, S3 (bachelor, master or doctoral degree)",
    "TOTAL": "Jumlah (all education levels)",
}
PARTS = [e for e in EDUCATION if e != "TOTAL"]

# WebAPI education columns as sums of report columns
API_COLUMNS = {
    "primary_or_less": ["Tidak Punya", "SD"],
    "junior_secondary": ["SMP"],
    "senior_secondary_general+senior_secondary_vocational": ["SMA"],
    "diploma": ["D1-D3"],
    "university": ["S1 ke atas"],
    "TOTAL": ["Total"],
}

INDICATORS = {
    "employed_persons_august": {"name": "Penduduk berumur 15 tahun ke atas yang bekerja selama seminggu terakhir, Sakernas Agustus (employed persons aged 15 and over, August survey), by highest education completed",
                                "unit": "persons", "multiplier": 1,
                                "source": "BPS, Keadaan Angkatan Kerja di Indonesia Agustus 2025, Tabel 107"},
}

# Sum checks: education parts to the total in each row, provinces to Indonesia in each column (whole persons)
TOLERANCE = 2

# Plausibility: share of workers with junior secondary schooling or less, in percent
PLAUSIBLE = {"low_education_share_pct": (20, 85)}

NUMBER = re.compile(r"^\d{1,3}(?:\.\d{3})*$")

# Functions

def row(code, education, value, status=""):
    """Return one long row."""
    return {"province_code": code, "indicator": "employed_persons_august", "education": education,
            "period": PERIOD, "status": status, "value": value}


def read_pdf_rows(pdf, lookup):
    """Read Table 107 from its two pages into long rows of provinces and Indonesia."""
    c = READ_CONTEXT["pdf"]
    for number in c["pages"]:
        lines = cleaning.pdf_visible_lines(pdf.pages[number - 1])
        text = "\n".join(" ".join(w["text"] for w in line) for line in lines)
        # Check the page still carries its title, column labels and footnote
        for needle in c["page_text"][number] + c["header_text"]:
            cleaning.require_text(text, needle, f"page {number}")
    # Read the province rows and the Indonesia row (Jumlah above its numbers, Total below)
    cells, gaps = cleaning.bps_report_province_table(
        pdf, {number: list(EDUCATION) for number in c["pages"]}, lookup,
        marker_status=c["marker"]["status"], marker_text=c["marker"]["text"], decimal=c["decimal"],
        thousands=c["thousands"], national_label=c["national_row"], max_marker_size=c["marker"]["max_size"])
    assert not gaps, gaps
    return [row(x["province_code"], x["column"], x["value"], x["status"]) for x in cells]


def read_api_totals(record):
    """Return the WebAPI August national totals by its education columns."""
    c = READ_CONTEXT["api"]
    table = record["response"]
    v = table["var"][0]
    cleaning.require_text(v["label"], c["title"], "var 1126")
    assert v["unit"] == c["unit"] and int(v["decimal"]) == c["decimals"], (v["unit"], v["decimal"])
    totals = {}
    for r, tv, th, tt, text in cleaning.bps_api_cells(table):
        if cleaning.html_to_text(r["label"]) == c["total_row"] and tt["label"] == c["month"]:
            totals[tv["label"]] = cleaning.parse_number(text, ".", None, decimals=0)
    return totals


def cross_check(df, totals):
    """Layer 4: the report's Indonesia row equals the WebAPI August totals, column group by column group."""
    national = df[df["province_code"] == cleaning.NATIONAL_CODE].set_index("education")["value"]
    compared = 0
    for ours, theirs in API_COLUMNS.items():
        a = sum(national[e] for e in ours.split("+"))
        b = sum(totals[t] for t in theirs)
        if a != b:
            raise ValueError(f"Indonesia {ours}: report {a}, WebAPI {b}")
        compared += 1
    return {"report Tabel 107 Indonesia row = WebAPI var 1126 Agustus 2025 total row": compared}


def identity_checks(df):
    """Layer 3: education parts sum to each row's total, and provinces sum to Indonesia in each column."""
    wide = df.pivot(index="province_code", columns="education", values="value")
    checks = [cleaning.check_sum(wide[PARTS].sum(axis=1), wide["TOTAL"], TOLERANCE, "education levels to TOTAL")]
    provinces = wide.drop(index=cleaning.NATIONAL_CODE)
    checks.append(cleaning.check_sum(provinces.sum(), wide.loc[cleaning.NATIONAL_CODE], TOLERANCE, "provinces to Indonesia"))
    return checks


def plausibility_flags(df):
    """Layer 5: share of workers with junior secondary schooling or less outside its range."""
    wide = df.pivot(index="province_code", columns="education", values="value")
    share = (wide["primary_or_less"] + wide["junior_secondary"]) / wide["TOTAL"] * 100
    return cleaning.flag_outside([{"province_code": c, "period": PERIOD, "value": v} for c, v in share.items()],
                                 "low_education_share_pct", *PLAUSIBLE["low_education_share_pct"])


# Steps

# Read the BPS province list that every region name and code is matched against
provinces, lookup = cleaning.load_bps_provinces(RAW_PROVINCES)

# Read Table 107 from the report
with pdfplumber.open(RAW_PDF) as pdf:
    rows = read_pdf_rows(pdf, lookup)

# Read the WebAPI national totals that check the Indonesia row
[record] = cleaning.read_jsonl(RAW_API)
assert record["year"] == PERIOD, record["year"]
totals = read_api_totals(record)

# Layers 3 and 4: sums and the cross-source check stop the build on failure
df = pd.DataFrame(rows)
sums = identity_checks(df)
overlaps = cross_check(df, totals)

# Layer 5: plausibility only flags
flags = plausibility_flags(df)

# Describe the dataset
meta = {
    "title": "BPS employed persons by highest education completed, by province, Sakernas August 2025, Indonesia",
    "columns": {
        "province_code": "BPS province code (kode_bps); 00 = Indonesia. Names and Kemendagri codes in 'provinces'.",
        "indicator": "Indicator code; definitions in 'indicators'.",
        "education": "Highest education completed; names in 'education'. TOTAL is all levels.",
        "period": "YYYY; the survey month (August) is in the indicator code.",
        "status": "BPS precision marker: rse25-50 where the report marks a relative standard error of 25-50%.",
        "value": "Persons, as published by BPS.",
    },
    "provinces": provinces,
    "education": EDUCATION,
    "indicators": INDICATORS,
    "source_tables": {
        "report": {"title": "Keadaan Angkatan Kerja di Indonesia Agustus 2025, Tabel 107: Penduduk Berumur 15 Tahun ke Atas yang Bekerja Selama Seminggu Terakhir Menurut Provinsi dan Pendidikan Tertinggi yang Ditamatkan di Indonesia, Agustus 2025",
                   "pages": "PDF pages 211-212 (printed pages 153-154)", "file": str(RAW_PDF.relative_to(ROOT)),
                   "publication": "raw/labour/20261116_bps-keadaan-angkatan-kerja-agustus-2025-publication.json"},
        "webapi 1126": {"title": READ_CONTEXT["api"]["title"], "request": record["request"],
                        "last_update": record["response"].get("last_update"), "use": "check only: national August totals"},
    },
    "notes": [
        "Table 107 pages carry hidden white text from the February 2025 edition ('Februari 2025'). It is not read; the visible heading says Agustus 2025 and the Indonesia row equals the WebAPI August 2025 totals exactly, not the February ones.",
        "Values marked rse25-50 have a relative standard error of 25-50% (BPS footnote): Papua Selatan diploma, Papua Pegunungan SMK and diploma.",
        "The share of workers with junior secondary schooling or less is (primary_or_less + junior_secondary) / TOTAL; it is derived in analysis/, not stored here.",
    ],
    "checks": {
        "passed": ["identities", "cross-source"],
        "identities": sums,
        "cross_source_overlaps": overlaps,
        "plausible_ranges": PLAUSIBLE,
        "flags": flags,
    },
}

# Layers 1, 2 and 6: check structure and completeness, then write the CSV and metadata
expected = {(c, "employed_persons_august", e, PERIOD) for c in provinces for e in EDUCATION}
out = cleaning.write_dataset(
    rows, KEYS,
    allowed={"province_code": provinces, "indicator": list(INDICATORS), "education": list(EDUCATION)},
    expected=expected,
    csv_path=OUT_CSV, meta=meta, raw_files=[RAW_PROVINCES, RAW_PDF, RAW_API],
    sort_orders={"education": list(EDUCATION)},
)

# Report what was written
print(f"{OUT_CSV.name}: {len(out)} rows, {len(flags)} plausibility flags, overlaps {overlaps}")
print(sums)
print(out[out["status"] != ""].to_string(index=False))
for f in flags:
    print("  flag:", f)
