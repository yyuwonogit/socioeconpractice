from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# Load the shared cleaning module from tools/
import sys
sys.path.insert(0, str(ROOT / "tools"))
import cleaning

import pdfplumber

# Parameters

# Raw inputs: the BPS province list and PLN's statistical report for 2024
RAW_PROVINCES = ROOT / "raw/province-codes/20261102_bps-province-codes-2025-s1.json"
RAW_PDF = ROOT / "raw/electricity/20261116_pln-statistik-2024.pdf"

# Output; the metadata JSON is written beside it with a -metadata suffix
OUT_CSV = HERE / "20261116_pln-unit-saidi-saifi-2024.csv"

KEYS = ["unit", "indicator", "period"]
PERIOD = "2024"

# How the report writes Tabel 16, read from opening the PDF: PDF page 46, one line per PLN unit with
# SAIDI (hours per customer) and SAIFI (times per customer), "," as the decimal mark and two decimals
READ_CONTEXT = {
    "page": 46,
    "page_text": ["Tabel/Table 16 : SAIDI dan SAIFI / SAIDI and SAIFI 2024", "Unit PLN / PLN Units SAIDI SAIFI",
                  "Jam/Pelanggan/ Kali/Pelanggan/", "Hours/Customer Times/Customer"],
    "decimal": ",", "thousands": None, "decimals": 2,
}

# PLN units as printed, with a short code and the provinces each serves. The provinces come from the unit's
# own name; abbreviated parts are spelled out ("Sulawesi Utara, Tengah dan Gorontalo" is Sulawesi Utara,
# Sulawesi Tengah and Gorontalo). PLN units predate the 2022 Papua split, so "Papua dan Papua Barat" covers all
# six Papua provinces. PT PLN Batam serves Batam, part of Kepulauan Riau, which the Riau unit also serves.
UNITS = {
    "UID Aceh": ("ACEH", ["ACEH"]),
    "UID Sumatera Utara": ("SUMUT", ["SUMATERA UTARA"]),
    "UID Sumatera Barat": ("SUMBAR", ["SUMATERA BARAT"]),
    "UID Riau dan Kepulauan Riau": ("RIAU_KEPRI", ["RIAU", "KEPULAUAN RIAU"]),
    "UID Sumatera Selatan, Jambi dan Bengkulu": ("S2JB", ["SUMATERA SELATAN", "JAMBI", "BENGKULU"]),
    "UIW Bangka Belitung": ("BABEL", ["KEPULAUAN BANGKA BELITUNG"]),
    "UID Lampung": ("LAMPUNG", ["LAMPUNG"]),
    "UID Kalimantan Barat": ("KALBAR", ["KALIMANTAN BARAT"]),
    "UID Kalimantan Selatan dan Tengah": ("KALSELTENG", ["KALIMANTAN SELATAN", "KALIMANTAN TENGAH"]),
    "UID Kalimantan Timur dan Utara": ("KALTIMRA", ["KALIMANTAN TIMUR", "KALIMANTAN UTARA"]),
    "UID Sulawesi Utara,Tengah dan Gorontalo": ("SULUTTENGGO", ["SULAWESI UTARA", "SULAWESI TENGAH", "GORONTALO"]),
    "UID Sulawesi Selatan, Tenggara dan Barat": ("SULSELRABAR", ["SULAWESI SELATAN", "SULAWESI TENGGARA", "SULAWESI BARAT"]),
    "UIW Maluku dan Maluku Utara": ("MALUKU_MALUT", ["MALUKU", "MALUKU UTARA"]),
    "UIW Papua dan Papua Barat": ("PAPUA_PABAR", ["PAPUA", "PAPUA BARAT", "PAPUA BARAT DAYA", "PAPUA SELATAN", "PAPUA TENGAH", "PAPUA PEGUNUNGAN"]),
    "UID Bali": ("BALI", ["BALI"]),
    "UIW Nusa Tenggara Barat": ("NTB", ["NUSA TENGGARA BARAT"]),
    "UIW Nusa Tenggara Timur": ("NTT", ["NUSA TENGGARA TIMUR"]),
    "PT PLN Batam": ("BATAM", ["KEPULAUAN RIAU"]),
    "Luar Jawa": ("OUTSIDE_JAVA", []),
    "UID Jawa Timur": ("JATIM", ["JAWA TIMUR"]),
    "UID Jawa Tengah dan Yogyakarta": ("JATENG_DIY", ["JAWA TENGAH", "DI YOGYAKARTA"]),
    "UID Jawa Barat": ("JABAR", ["JAWA BARAT"]),
    "UID Banten": ("BANTEN", ["BANTEN"]),
    "UID Jakarta Raya": ("JAKARTA", ["DKI JAKARTA"]),
    "Jawa": ("JAVA", []),
    "Indonesia": ("INDONESIA", []),
}
AGGREGATES = {"OUTSIDE_JAVA", "JAVA", "INDONESIA"}

# For a province served by two units, the unit whose value the province takes
PRIMARY = {"KEPULAUAN RIAU": "RIAU_KEPRI"}

INDICATORS = {
    "saidi": {"name": "System Average Interruption Duration Index (SAIDI): average outage hours per customer in the year",
              "unit": "hours per customer", "multiplier": 1, "source": "PLN, Statistik PLN 2024, Tabel 16"},
    "saifi": {"name": "System Average Interruption Frequency Index (SAIFI): average number of outages per customer in the year",
              "unit": "times per customer", "multiplier": 1, "source": "PLN, Statistik PLN 2024, Tabel 16"},
}

PLAUSIBLE = {"saidi": (0, 50), "saifi": (0, 20)}

# Functions

def read_table(pdf):
    """Read every unit line of Tabel 16 into long rows, by unit name."""
    c = READ_CONTEXT
    lines = cleaning.pdf_visible_lines(pdf.pages[c["page"] - 1])
    text = "\n".join(" ".join(w["text"] for w in line) for line in lines)
    for needle in c["page_text"]:
        cleaning.require_text(text, needle, f"page {c['page']}")
    rows, found = [], []
    for line in lines:
        words = [w["text"] for w in line]
        name = " ".join(words[:-2])
        if name in UNITS:
            unit = UNITS[name][0]
            for indicator, cell in zip(INDICATORS, words[-2:]):
                value = cleaning.parse_number(cell, c["decimal"], c["thousands"], decimals=c["decimals"])
                rows.append({"unit": unit, "indicator": indicator, "period": PERIOD, "status": "", "value": value})
            found.append(name)
    if sorted(found) != sorted(UNITS):
        raise ValueError(f"units not found once each: missing {set(UNITS) - set(found)}, repeated {[n for n in found if found.count(n) > 1]}")
    return rows


def coverage(lookup):
    """Return unit -> BPS province codes it serves, and province -> the unit whose value it takes."""
    served = {code: [cleaning.province_code(n, lookup) for n in names] for code, names in UNITS.values()}
    provinces = {}
    for unit, codes in served.items():
        for p in codes:
            provinces.setdefault(p, []).append(unit)
    primary = {cleaning.province_code(n, lookup): u for n, u in PRIMARY.items()}
    assign = {}
    for p, units in provinces.items():
        if len(units) > 1:
            assert p in primary and primary[p] in units, (p, units)
            assign[p] = primary[p]
        else:
            assign[p] = units[0]
    return served, assign

# Steps

# Read the BPS province list that every province name is matched against
provinces, lookup = cleaning.load_bps_provinces(RAW_PROVINCES)
regions = [c for c in provinces if c != cleaning.NATIONAL_CODE]

# Read Tabel 16
with pdfplumber.open(RAW_PDF) as pdf:
    rows = read_table(pdf)

# Every province is served by a unit; a province served by two units takes its declared primary unit
served, assign = coverage(lookup)
assert sorted(assign) == sorted(regions), set(regions) - set(assign)

# Layer 5: plausibility only flags
flags = []
for indicator, (low, high) in PLAUSIBLE.items():
    flags += cleaning.flag_outside([{"unit": r["unit"], "period": r["period"], "value": r["value"]} for r in rows if r["indicator"] == indicator], indicator, low, high)

# Describe the dataset
units_meta = {code: {"name": name, "provinces": served[code], "aggregate": code in AGGREGATES} for name, (code, _) in UNITS.items()}
meta = {
    "title": "PLN SAIDI and SAIFI by PLN distribution unit, 2024, with the provinces each unit serves",
    "columns": {
        "unit": "PLN unit code; names and the BPS province codes each serves in 'units'.",
        "indicator": "saidi or saifi; definitions in 'indicators'.",
        "period": "YYYY.",
        "status": "Empty; the table carries no markers.",
        "value": "As published by PLN.",
    },
    "units": units_meta,
    "province_unit": {p: {"unit": u, "name": provinces[p]["name"]} for p, u in sorted(assign.items())},
    "provinces": {k: v for k, v in provinces.items() if k != cleaning.NATIONAL_CODE},
    "indicators": INDICATORS,
    "source_tables": {"pdf": {"title": "Statistik PLN 2024, Tabel 16: SAIDI dan SAIFI 2024", "page": "PDF page 46 (printed page 30)",
                              "file": str(RAW_PDF.relative_to(ROOT)),
                              "url": "https://www.pln.co.id/webapi/media/file/webkorp/asset/Statistik2024.pdf"}},
    "notes": [
        "PLN reports reliability by distribution unit (UID/UIW), not by province. A province takes the value of the unit that serves it, so provinces served by one unit share a value.",
        "Units serving several provinces: Riau dan Kepulauan Riau; Sumatera Selatan, Jambi dan Bengkulu; Kalimantan Selatan dan Tengah; Kalimantan Timur dan Utara; Sulawesi Utara, Tengah dan Gorontalo; Sulawesi Selatan, Tenggara dan Barat; Maluku dan Maluku Utara; Jawa Tengah dan Yogyakarta; Papua dan Papua Barat (all six Papua provinces).",
        "Kepulauan Riau is served by UID Riau dan Kepulauan Riau and by PT PLN Batam (Batam city); it takes the UID Riau dan Kepulauan Riau value (see 'province_unit').",
        "SAIDI and SAIFI cover PLN customers only; off-grid households and captive power are outside them.",
    ],
    "checks": {"passed": [], "plausible_ranges": PLAUSIBLE, "flags": flags},
}

# Layers 1, 2 and 6: every unit has both indicators
unit_codes = [code for code, _ in UNITS.values()]
out = cleaning.write_dataset(
    rows, KEYS,
    allowed={"unit": unit_codes, "indicator": list(INDICATORS)},
    expected={(u, i, PERIOD) for u in unit_codes for i in INDICATORS},
    csv_path=OUT_CSV, meta=meta, raw_files=[RAW_PROVINCES, RAW_PDF],
    sort_orders={"unit": unit_codes},
)

# Report what was written
print(f"{OUT_CSV.name}: {len(out)} rows, {len(UNITS)} units, {len(flags)} plausibility flags")
for f in flags:
    print("  flag:", f)
