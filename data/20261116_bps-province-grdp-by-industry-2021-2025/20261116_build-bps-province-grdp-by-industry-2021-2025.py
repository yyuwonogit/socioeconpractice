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

# Raw inputs: the BPS province list and the BPS publication of provincial GRDP by industry, 2021-2025
RAW_PROVINCES = ROOT / "raw/province-codes/20261102_bps-province-codes-2025-s1.json"
RAW_PDF = ROOT / "raw/grdp/20261109_bps-pdrb-provinsi-provinsi-menurut-lapangan-usaha-2021-2025.pdf"

# Existing dataset whose provincial GRDP totals (current prices) check this one
CHECK_TOTALS = ROOT / "data/20261102_bps-province-grdp-population/20261102_bps-province-grdp-population.csv"

# Provincial offices' subsector tables (WebAPI, 26 provinces, earlier vintages), compared for the record only
REVISION_CHECK = ROOT / "data/20261108_bps-province-grdp-subsector/20261108_bps-province-grdp-subsector.csv"

# Output; the metadata JSON is written beside it with a -metadata suffix
OUT_CSV = HERE / "20261116_bps-province-grdp-by-industry-2021-2025.csv"

KEYS = ["province_code", "indicator", "sector", "period"]

# How the publication writes its tables, read from opening the PDF: tables 9-84 on PDF pages 53-128,
# one province and price basis per page, five year columns 2021-2025 (2024* preliminary, 2025** very
# preliminary), whole billions of rupiah with "." as the thousands separator, "–" for nil and "~0"
# for less than half a unit. Row labels are Indonesian/English and may wrap onto lines without numbers.
READ_CONTEXT = {
    "pages": range(53, 129),
    "title": re.compile(r"^PDRB (?P<name>.+) Atas Dasar Harga (?P<basis>Berlaku|Konstan 2010) Menurut Lapangan Usaha \(miliar rupiah\), 2021–2025$"),
    "unit_text": "(miliar rupiah)",
    "years": {"2021": "", "2022": "", "2023": "", "2024*": "*", "2025**": "**"},
    "decimal": ",", "thousands": ".", "decimals": 0,
    "no_value": {"–": "nil (no activity)", "~0": "less than half a unit (under Rp 0.5 billion)"},
    "basis": {"Berlaku": "grdp_current", "Konstan 2010": "grdp_constant"},
}

# Rows read, matched by name in this order (patterns apply to the label without its outline code)
SECTORS = {
    "A": r"^Pertanian, Kehutanan,? dan Perikanan/",
    "B": r"^Pertambangan dan Penggalian/Mining",
    "B1": r"^1 ?Pertambangan Minyak",
    "B2": r"^2 ?Pertambangan Batubara",
    "B3": r"^3 ?Pertambangan Bijih Logam",
    "B4": r"^4 ?Pertambangan dan Penggalian Lainnya",
    "C": r"^Industri Pengolahan/Manufacturing",
    "D": r"^Pengadaan Listrik dan Gas/",
    "E": r"^Pengadaan Air",
    "F": r"^Konstruksi/",
    "G": r"^Perdagangan Besar dan Eceran;",
    "H": r"^Transportasi dan Pergudangan/",
    "I": r"^Penyediaan Akomodasi dan Makan Minum/",
    "J": r"^Informasi dan Komunikasi/",
    "K": r"^Jasa Keuangan dan Asuransi/",
    "L": r"^Real Estat/",
    "MN": r"^Jasa Perusahaan/",
    "O": r"^Administrasi Pemerintahan",
    "P": r"^Jasa Pendidikan/",
    "Q": r"^Jasa Kesehatan dan Kegiatan Sosial/",
    "RSTU": r"^Jasa lainnya/",
    "TOTAL": r"^PRODUK DOMESTIK REGIONAL BRUTO/Gross",
    "NONOIL": r"^PRODUK DOMESTIK REGIONAL BRUTO TANPA MIGAS",
}
SECTOR_NAMES = {
    "A": "Pertanian, Kehutanan, dan Perikanan (agriculture, forestry and fishing)",
    "B": "Pertambangan dan Penggalian (mining and quarrying)",
    "B1": "Pertambangan Minyak, Gas dan Panas Bumi (crude oil, natural gas and geothermal)",
    "B2": "Pertambangan Batubara dan Lignit (coal and lignite mining)",
    "B3": "Pertambangan Bijih Logam (metal ore mining)",
    "B4": "Pertambangan dan Penggalian Lainnya (other mining and quarrying)",
    "C": "Industri Pengolahan (manufacturing)", "D": "Pengadaan Listrik dan Gas (electricity and gas)",
    "E": "Pengadaan Air, Pengelolaan Sampah, Limbah dan Daur Ulang (water supply and waste)",
    "F": "Konstruksi (construction)", "G": "Perdagangan Besar dan Eceran; Reparasi Mobil dan Sepeda Motor (trade)",
    "H": "Transportasi dan Pergudangan (transport and storage)", "I": "Penyediaan Akomodasi dan Makan Minum (accommodation and food)",
    "J": "Informasi dan Komunikasi (information and communication)", "K": "Jasa Keuangan dan Asuransi (finance and insurance)",
    "L": "Real Estat (real estate)", "MN": "Jasa Perusahaan (business services, M and N)",
    "O": "Administrasi Pemerintahan, Pertahanan dan Jaminan Sosial Wajib (public administration)",
    "P": "Jasa Pendidikan (education)", "Q": "Jasa Kesehatan dan Kegiatan Sosial (health and social work)",
    "RSTU": "Jasa Lainnya (other services, R to U)",
    "TOTAL": "Produk Domestik Regional Bruto (GRDP)", "NONOIL": "PDRB tanpa migas (GRDP excluding oil and gas)",
}
TOP = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "MN", "O", "P", "Q", "RSTU"]
MINING = ["B1", "B2", "B3", "B4"]

INDICATORS = {
    "grdp_current": {"name": "PDRB atas dasar harga berlaku (GRDP at current prices), Seri 2010", "unit": "Rp billion (miliar rupiah)",
                     "multiplier": 1e9, "base_unit": "Rp", "source": "BPS, PDRB Provinsi-Provinsi di Indonesia Menurut Lapangan Usaha 2021-2025"},
    "grdp_constant": {"name": "PDRB atas dasar harga konstan 2010 (GRDP at constant 2010 prices), Seri 2010", "unit": "Rp billion (miliar rupiah)",
                      "multiplier": 1e9, "base_unit": "Rp", "source": "BPS, PDRB Provinsi-Provinsi di Indonesia Menurut Lapangan Usaha 2021-2025"},
}

# Source errors: in Tabel 77 (Papua, current prices) the 2023 cells of A, B (with B1-B4) and C repeat the
# 2022 values, which cover pre-split Papua, while every other 2023 cell and the 2023 GRDP cover the
# post-split province, so the 17 industries exceed GRDP by Rp 117,902 billion. These cells are not
# written; the build checks each still equals its 2022 cell, and the identity check skips that row
SOURCE_ERRORS = {("94", "grdp_current", "2023"): {"sectors": ["A", "B", "B1", "B2", "B3", "B4", "C"], "repeats": "2022"}}

# The four new Papua provinces have no values before 2023 in this publication
NEW_PROVINCES = {"92", "95", "96", "97"}
FIRST_SPLIT_YEAR = 2023

# Sum checks on whole-billion rounded values: half a billion per part
TOLERANCE_TOP = 0.5 * len(TOP) + 0.5
TOLERANCE_MINING = 0.5 * len(MINING) + 0.5

# Cross-check against the existing dataset's current-price totals: same BPS series, rounded here to whole billions
CHECK_TOLERANCE = 0.5

# Province-years left out of the cross-check: the existing dataset's 2023 Papua and Papua Barat cover the
# pre-split areas, while this publication gives post-split values from 2023
CHECK_SKIP = {("91", "2023"): "pre-split area in the existing dataset", ("94", "2023"): "pre-split area in the existing dataset"}

# Plausibility: coal share of GRDP, percent
PLAUSIBLE = {"coal_share_pct": (0, 60)}

NUMBER = re.compile(r"^(?:\d{1,3}(?:\.\d{3})*|–|~0)$")

# Functions

def read_page(page, lookup, number):
    """Read one table page into long rows, and the cells the table leaves without a value."""
    c = READ_CONTEXT
    lines = cleaning.pdf_visible_lines(page)
    texts = [" ".join(w["text"] for w in line) for line in lines]
    [title] = [t for t in texts if c["title"].match(t)]
    m = c["title"].match(title)
    code = cleaning.province_code(m.group("name"), lookup)
    indicator = c["basis"][m.group("basis")]
    # Check the year header and its revision markers
    [years] = [t for t in texts if t.startswith("Lapangan Usaha/Industry")]
    assert years.split()[-5:] == list(c["years"]), (number, years)
    # Rows with numbers: the label is every word before the last five, which are the year cells
    labels, cells = [], []
    for line in lines:
        words = [w["text"] for w in line]
        if len(words) > 5 and all(NUMBER.match(x) for x in words[-5:]) and not NUMBER.match(words[-6]):
            labels.append(" ".join(words[:-5]))
            cells.append(words[-5:])
    index = cleaning.match_rows(labels, SECTORS, where=f"page {number}")
    rows, gaps = [], []
    for sector, i in index.items():
        for (year, status), text in zip(c["years"].items(), cells[i]):
            period = year.rstrip("*")
            if text in c["no_value"]:
                gaps.append({"province_code": code, "indicator": indicator, "sector": sector, "period": period, "marker": text})
                continue
            value = cleaning.parse_number(text, c["decimal"], c["thousands"], decimals=c["decimals"])
            rows.append({"province_code": code, "indicator": indicator, "sector": sector, "period": period, "status": status, "value": value})
    return code, indicator, rows, gaps


def drop_source_errors(rows):
    """Remove the declared source-error cells, checking each still repeats its earlier-year cell."""
    value = {(r["province_code"], r["indicator"], r["sector"], r["period"]): r["value"] for r in rows}
    dropped = []
    for (code, indicator, period), e in SOURCE_ERRORS.items():
        for sector in e["sectors"]:
            key = (code, indicator, sector, period)
            if key not in value:
                continue
            if value[key] != value[(code, indicator, sector, e["repeats"])]:
                raise ValueError(f"{key}: declared source error no longer repeats {e['repeats']}")
            dropped.append({"province_code": code, "indicator": indicator, "sector": sector, "period": period,
                            "marker": f"source error: repeats the {e['repeats']} value {value[key]:g}"})
    keys = {(d["province_code"], d["indicator"], d["sector"], d["period"]) for d in dropped}
    return [r for r in rows if (r["province_code"], r["indicator"], r["sector"], r["period"]) not in keys], dropped


def identity_checks(df):
    """Layer 3: the 17 industries sum to GRDP, and the four mining sub-industries sum to mining."""
    wide = df.pivot_table(index=["province_code", "indicator", "period"], columns="sector", values="value")
    wide = wide.drop(index=list(SOURCE_ERRORS))
    return [cleaning.check_sum(wide[TOP].sum(axis=1, min_count=1), wide["TOTAL"], TOLERANCE_TOP, "industries A-U to TOTAL"),
            cleaning.check_sum(wide[MINING].sum(axis=1, min_count=1).fillna(0), wide["B"].fillna(0), TOLERANCE_MINING, "B1-B4 to B")]


def cross_check(df):
    """Layer 4: current-price provincial totals equal the existing dataset's, rounded to whole billions."""
    other = pd.read_csv(CHECK_TOTALS, dtype={"province_code": str, "sector": str, "period": str, "status": str}, keep_default_na=False)
    other = other[(other["indicator"] == "grdp_current") & (other["sector"] == "TOTAL")].set_index(["province_code", "period"])["value"]
    ours = df[(df["indicator"] == "grdp_current") & (df["sector"] == "TOTAL")].set_index(["province_code", "period"])["value"]
    both = ours.index.intersection(other.index).difference(list(CHECK_SKIP))
    gap = (ours[both] - other[both]).abs()
    if gap.max() > CHECK_TOLERANCE:
        raise ValueError(f"totals differ from {CHECK_TOTALS.name}: largest {gap.max()} at {gap.idxmax()}")
    return {f"TOTAL grdp_current = {CHECK_TOTALS.parent.name} (rounded to Rp 1 billion)": int(len(both)),
            "skipped": {f"{c} {p}": why for (c, p), why in CHECK_SKIP.items()}}


def revision_comparison(df):
    """Compare B, B2 and TOTAL with the provincial offices' WebAPI tables (older vintages); recorded, not a stop."""
    other = pd.read_csv(REVISION_CHECK, dtype={"province_code": str, "sector": str, "period": str, "status": str}, keep_default_na=False)
    m = df.merge(other, on=KEYS, suffixes=("", "_offices"))
    m = m[m["sector"].isin(["B", "B2", "TOTAL"])]
    m["gap"] = (m["value"] - m["value_offices"].round()).abs()
    differ = m[m["gap"] > CHECK_TOLERANCE].sort_values("gap", ascending=False)
    return {"against": REVISION_CHECK.parent.name, "compared": int(len(m)), "agree_to_Rp_0.5_billion": int(len(m) - len(differ)),
            "differ": [{k: r[k] for k in KEYS} | {"this": float(r["value"]), "offices": float(r["value_offices"])} for _, r in differ.iterrows()]}


def plausibility_flags(df):
    """Layer 5: coal share of current-price GRDP outside its range."""
    wide = df[df["indicator"] == "grdp_current"].pivot_table(index=["province_code", "period"], columns="sector", values="value")
    share = (wide["B2"] / wide["TOTAL"] * 100).dropna()
    return cleaning.flag_outside([{"province_code": c, "period": p, "value": v} for (c, p), v in share.items()],
                                 "coal_share_pct", *PLAUSIBLE["coal_share_pct"])

# Steps

# Read the BPS province list that every region name and code is matched against
provinces, lookup = cleaning.load_bps_provinces(RAW_PROVINCES)
regions = [c for c in provinces if c != cleaning.NATIONAL_CODE]

# Read every table page; each province must appear once at current and once at constant prices
rows, gaps, seen = [], [], set()
with pdfplumber.open(RAW_PDF) as pdf:
    for number in READ_CONTEXT["pages"]:
        code, indicator, page_rows, page_gaps = read_page(pdf.pages[number - 1], lookup, number)
        assert (code, indicator) not in seen, (code, indicator)
        seen.add((code, indicator))
        rows += page_rows
        gaps += page_gaps
assert seen == {(c, i) for c in regions for i in INDICATORS}, "tables missing"

# Remove the declared source errors; they join the gaps the metadata explains
rows, errors = drop_source_errors(rows)
gaps += errors

# The only whole-column gaps allowed are the four new Papua provinces before their first year
df = pd.DataFrame(rows)
totals_gap = [g for g in gaps if g["sector"] == "TOTAL"]
assert all(g["province_code"] in NEW_PROVINCES and int(g["period"]) < FIRST_SPLIT_YEAR for g in totals_gap), totals_gap

# Layers 3 and 4 stop the build on failure
sums = identity_checks(df)
overlaps = cross_check(df)

# Layer 5: plausibility only flags; the comparison with older provincial-office tables is recorded
flags = plausibility_flags(df)
revisions = revision_comparison(df)

# Describe the dataset
meta = {
    "title": "BPS provincial GRDP by industry, current and constant 2010 prices, 2021-2025, Indonesia (38 provinces)",
    "columns": {
        "province_code": "BPS province code (kode_bps). Names and Kemendagri codes in 'provinces'.",
        "indicator": "grdp_current or grdp_constant; definitions in 'indicators'.",
        "sector": "Industry code; names in 'sectors'. TOTAL is GRDP, NONOIL is GRDP excluding oil and gas.",
        "period": "YYYY.",
        "status": "BPS revision marker: * preliminary (2024), ** very preliminary (2025).",
        "value": "Rp billion, rounded to whole billions as published.",
    },
    "provinces": {k: v for k, v in provinces.items() if k != cleaning.NATIONAL_CODE},
    "sectors": SECTOR_NAMES,
    "indicators": INDICATORS,
    "source_tables": {"pdf": {"title": "Produk Domestik Regional Bruto Provinsi-Provinsi di Indonesia Menurut Lapangan Usaha 2021-2025, Tabel 9-84",
                              "pages": "PDF pages 53-128", "file": str(RAW_PDF.relative_to(ROOT))}},
    "gaps": {"meaning": READ_CONTEXT["no_value"], "cells": gaps},
    "notes": [
        "Source error: Tabel 77 (Papua, current prices) repeats the 2022 values in its 2023 cells for A, B (B1-B4) and C, while its other 2023 cells and its 2023 GRDP cover the post-split province. Those cells are not written (listed in 'gaps' with marker 'source error') and the industries-to-GRDP check skips Papua current 2023.",
        "A cell marked '–' (nil) or '~0' (under Rp 0.5 billion) has no row; 'gaps' lists every such cell. Where coal mining (B2) has no row, the province has no coal mining output, or under Rp 0.5 billion.",
        "Papua Barat Daya (92), Papua Selatan (95), Papua Tengah (96) and Papua Pegunungan (97) have values from 2023; Papua (94) and Papua Barat (91) cover the post-split areas in this publication.",
        "Only the 17 main industries, the four mining sub-industries and the two totals are read; other sub-industries in the tables are not.",
        "Shares and growth rates are derived in analysis/.",
        "Compared with the provincial offices' subsector tables in data/20261108_bps-province-grdp-subsector (earlier vintages), some B, B2 and TOTAL values differ ('checks.revision_comparison'); this April 2026 national publication is the later release and is the one used.",
    ],
    "checks": {
        "passed": ["identities", "cross-source"],
        "identities": sums,
        "cross_source_overlaps": overlaps,
        "revision_comparison": revisions,
        "plausible_ranges": PLAUSIBLE,
        "flags": flags,
    },
}

# Layers 1, 2 and 6: every sector, province and year is present except the listed gaps
gap_keys = {(g["province_code"], g["indicator"], g["sector"], g["period"]) for g in gaps}
expected = {(c, i, s, str(y)) for c in regions for i in INDICATORS for s in SECTORS for y in range(2021, 2026)} - gap_keys
out = cleaning.write_dataset(
    rows, KEYS,
    allowed={"province_code": regions, "indicator": list(INDICATORS), "sector": list(SECTORS)},
    expected=expected,
    csv_path=OUT_CSV, meta=meta, raw_files=[RAW_PROVINCES, RAW_PDF],
    sort_orders={"sector": list(SECTORS)},
)

# Report what was written
print(f"{OUT_CSV.name}: {len(out)} rows, {len(gaps)} gap cells, {len(flags)} plausibility flags, overlaps {overlaps}")
for s in sums:
    print(" ", s)
for f in flags:
    print("  flag:", f)
