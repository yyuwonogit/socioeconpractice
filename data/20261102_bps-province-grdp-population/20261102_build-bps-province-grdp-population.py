from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

import csv
import hashlib
import json
import re

import openpyxl
import pandas as pd

# Parameters

# Raw inputs, as filed from .inbox on 20261102
RAW_PROVINCES = ROOT / "raw/province-codes/20261102_bps-province-codes-2025-s1.json"
RAW_GRDP_INDUSTRY = ROOT / "raw/grdp/20261102_grdp-quarterly-current-prices-by-industry-by-province-2025.csv"
RAW_GRDP_TOTAL = ROOT / "raw/grdp/20261102_bps-grdp-current-prices-by-province-2025-total.csv"
RAW_POPULATION = ROOT / "raw/population/20261102_population-growth-share-density-sex-ratio-by-province-2025.csv"
RAW_SERIES = ROOT / "raw/grdp-population/20261102_bps-province-grdp-population-2020-2025.xlsx"
RAW_COMBINED = ROOT / "raw/grdp-population/20261102_bps-province-grdp-population-2025.xlsx"

# Outputs
OUT_CSV = HERE / "20261102_bps-province-grdp-population.csv"
OUT_META = HERE / "20261102_bps-province-grdp-population-metadata.json"

# How each raw file is written, read from inspecting the files: encoding, field separator,
# decimal mark, thousands separator, missing-value markers, and the unit text its header must carry
READ_CONTEXT = {
    RAW_GRDP_INDUSTRY: {"encoding": "utf-8-sig", "delimiter": ",", "decimal": ".", "thousands": None,
                        "missing": [], "unit_text": "(Milyar Rupiah)"},
    RAW_GRDP_TOTAL: {"encoding": "utf-8", "delimiter": ",", "decimal": ".", "thousands": None,
                     "missing": [], "unit_text": "(Milyar Rp)"},
    RAW_POPULATION: {"encoding": "utf-8-sig", "delimiter": ",", "decimal": ".", "thousands": None,
                     "missing": [], "unit_text": "(Ribu)"},
    RAW_SERIES: {"decimal": "native", "missing": ["-"], "unit_text": {"GRDP ADHB 2020-2025": "Rp billion",
                                                                      "Population 2020-2025": "Thousand people"}},
    RAW_COMBINED: {"decimal": "native", "missing": [], "unit_text": "(Rp billion)"},
}

# A published number: optional minus, digits, optional decimal point and digits, no thousands separator
NUMBER = re.compile(r"^-?\d+(\.\d+)?$")

# Indonesia has no code in the BPS province list, so it gets "00"
NATIONAL = {"00": "INDONESIA"}

# Provinces created in the 2022 Papua split, and the first year the raw tables report them
NEW_PROVINCES = {"92", "95", "96", "97"}
SPLIT_PARENTS = {"91", "94"}
FIRST_SPLIT_YEAR = 2024

# GRDP sector codes, from the BPS KBLI letter groups in the industry table header
SECTORS = {
    "A": "Pertanian, Kehutanan dan Perikanan",
    "B": "Pertambangan dan Penggalian",
    "C": "Industri Pengolahan",
    "D": "Pengadaan Listrik dan Gas",
    "E": "Pengadaan Air, Pengelolaan Sampah, Limbah dan Daur Ulang",
    "F": "Konstruksi",
    "G": "Perdagangan Besar dan Eceran, Reparasi Mobil dan Sepeda Motor",
    "H": "Transportasi dan Pergudangan",
    "I": "Penyediaan Akomodasi dan Makan Minum",
    "J": "Informasi dan Komunikasi",
    "K": "Jasa Keuangan dan Asuransi",
    "L": "Real Estate",
    "MN": "Jasa Perusahaan",
    "O": "Administrasi Pemerintahan, Pertahanan dan Jaminan Sosial Wajib",
    "P": "Jasa Pendidikan",
    "Q": "Jasa Kesehatan dan Kegiatan Sosial",
    "RSTU": "Jasa Lainnya",
    "TOTAL": "Produk Domestik Regional Bruto",
}
PERIODS = {"Triwulan I": "Q1", "Triwulan II": "Q2", "Triwulan III": "Q3", "Triwulan IV": "Q4", "Tahunan": ""}

# Population table columns mapped to indicator codes
POP_COLUMNS = {
    "Jumlah Penduduk (Ribu)": "population",
    "Laju Pertumbuhan Penduduk per Tahun": "population_growth",
    "Persentase Penduduk": "population_share",
    "Kepadatan Penduduk per km persegi (Km2)": "population_density",
    "Rasio Jenis Kelamin Penduduk": "sex_ratio",
}

# Tolerances for accounting identities, set by the rounding in the BPS tables
TOL_GRDP_SUM = 0.05        # Rp billion, sectors vs TOTAL and quarters vs year
TOL_SHARE_SUM = 0.1        # percentage points, population shares vs 100
TOL_NATIONAL_REL = 1e-4    # relative, provinces vs Indonesia population

# Plausibility ranges; a value outside its range is flagged, not dropped
PLAUSIBLE = {
    "grdp_growth_pct": (-20, 40),
    "population_growth_pct": (0, 4),
    "sex_ratio": (90, 120),
    "population_density": (1, 20000),
}

URL_PROVINCES = "https://sig.bps.go.id/rest-bridging/getwilayah?level=provinsi&periode_merge=2025_1.2025"
URL_GRDP = "https://www.bps.go.id/id/statistics-table/2/MjI2OCMy/-seri-2010--pdrb-triwulanan-atas-dasar-harga-berlaku-menurut-lapangan-usaha-di-provinsi-seluruh-indonesia--milyar-rupiah-.html"
URL_POP = "https://www.bps.go.id/id/statistics-table/3/V1ZSbFRUY3lTbFpEYTNsVWNGcDZjek53YkhsNFFUMDkjMyMwMDAw/jumlah-penduduk--laju-pertumbuhan-penduduk--distribusi-persentase-penduduk--kepadatan-penduduk--rasio-jenis-kelamin-penduduk-menurut-provinsi.html"


# Functions

def normalise(name):
    """Return a province name in the BPS reference spelling: upper case, KEP. spelled out, single spaces."""
    name = " ".join(name.upper().split())
    return re.sub(r"^KEP\. ", "KEPULAUAN ", name)


def load_provinces(path):
    """Read the BPS province list and return code -> record and normalised name -> code."""
    records = json.loads(path.read_text(encoding="utf-8"))
    provinces = {r["kode_bps"]: {"name": r["nama_bps"], "kode_dagri": r["kode_dagri"]} for r in records}
    provinces.update({code: {"name": name, "kode_dagri": None} for code, name in NATIONAL.items()})
    lookup = {normalise(p["name"]): code for code, p in provinces.items()}
    return provinces, lookup


def parse_number(text, context):
    """Turn a published number string into a float, stopping on any format the context did not declare."""
    text = text.strip()
    assert context["thousands"] is None and context["decimal"] == ".", context
    assert NUMBER.match(text), f"unexpected number format: {text!r}"
    return float(text)


def parse_cell(value, context):
    """Turn an Excel cell into a float, or None for a declared missing marker."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    assert value in context["missing"], f"unexpected cell: {value!r}"
    return None


def read_csv_rows(path):
    """Read a raw CSV with its declared encoding and separator."""
    context = READ_CONTEXT[path]
    with open(path, encoding=context["encoding"], newline="") as f:
        return list(csv.reader(f, delimiter=context["delimiter"]))


def read_grdp_industry(path, lookup):
    """Read the BPS quarterly GRDP-by-industry CSV into long rows."""
    context = READ_CONTEXT[path]
    rows = read_csv_rows(path)
    # Row 1 carries the unit, row 2 names each sector over five columns, row 4 names the period
    assert context["unit_text"] in rows[1][1], rows[1][1]
    sector_row, period_row = rows[2], rows[4]
    sector_codes = list(SECTORS)
    labels = [c for c in sector_row[1:] if c]
    assert len(labels) == len(sector_codes) and len(period_row) == 1 + 5 * len(sector_codes)
    for code, label in zip(sector_codes, labels):
        assert label.endswith(SECTORS[code]), (code, label)
    out = []
    for row in rows[5:]:
        if not row or not row[0].strip():
            continue
        for i in range(1, len(period_row)):
            out.append({
                "province_code": lookup[normalise(row[0])],
                "indicator": "grdp_current",
                "sector": sector_codes[(i - 1) // 5],
                "period": "2025" + PERIODS[period_row[i].strip()],
                "value": parse_number(row[i], context),
            })
    return out


def read_population(path, lookup):
    """Read the BPS 2025 population CSV into long rows and its footnotes."""
    context = READ_CONTEXT[path]
    rows = read_csv_rows(path)
    header = rows[0]
    assert context["unit_text"] in header[1], header[1]
    out, notes = [], []
    for row in rows[1:]:
        name = row[0].strip()
        if normalise(name) in lookup:
            for col, indicator in POP_COLUMNS.items():
                out.append({
                    "province_code": lookup[normalise(name)],
                    "indicator": indicator,
                    "sector": "",
                    "period": "2025",
                    "value": parse_number(row[header.index(col)], context),
                })
        elif name and name != "Keterangan":
            notes.append(" ".join(name.split()))
    return out, notes


def read_series_sheet(ws, indicator, sector, lookup):
    """Read one 2020-2025 annual sheet of the series workbook into long rows."""
    context = READ_CONTEXT[RAW_SERIES]
    assert context["unit_text"][ws.title] in ws["A2"].value, ws["A2"].value
    years = [str(c.value) for c in ws[4][1:]]
    out = []
    for row in ws.iter_rows(min_row=5, values_only=True):
        if row[0] is None:
            continue
        for year, cell in zip(years, row[1:]):
            value = parse_cell(cell, context)
            # A missing marker means the province did not exist yet, so no row is written
            if value is None:
                continue
            out.append({
                "province_code": lookup[normalise(row[0])],
                "indicator": indicator,
                "sector": sector,
                "period": year,
                "value": value,
            })
    return out


def key(r):
    """Return the identifying fields of a long row."""
    return (r["province_code"], r["indicator"], r["sector"], r["period"])


def sha256(path):
    """Return the SHA-256 hash of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_structure(df, provinces):
    """Layer 1: exact columns, types, unique keys and known codes."""
    assert list(df.columns) == ["province_code", "indicator", "sector", "period", "value"]
    assert not df.duplicated(["province_code", "indicator", "sector", "period"]).any()
    assert df["value"].notna().all()
    assert set(df["province_code"]) <= set(provinces)
    assert set(df["sector"]) <= set(SECTORS) | {""}
    assert df["period"].str.fullmatch(r"\d{4}(Q[1-4])?").all()


def expected_keys(provinces):
    """Layer 2: every row the raw tables should yield, with the Papua split as the only gap."""
    provs = [c for c in provinces if c not in NATIONAL]

    def existing(year):
        return [c for c in provs if year >= FIRST_SPLIT_YEAR or c not in NEW_PROVINCES]

    keys = set()
    for c in provs:
        for s in SECTORS:
            for p in ["2025Q1", "2025Q2", "2025Q3", "2025Q4", "2025"]:
                keys.add((c, "grdp_current", s, p))
    for year in range(2020, 2025):
        for c in existing(year):
            keys.add((c, "grdp_current", "TOTAL", str(year)))
    for year in range(2020, 2026):
        for c in existing(year) + list(NATIONAL):
            keys.add((c, "population", "", str(year)))
    for indicator in list(POP_COLUMNS.values())[1:]:
        for c in provs + list(NATIONAL):
            keys.add((c, indicator, "", "2025"))
    return keys


def check_identities(df):
    """Layer 3: sectors sum to TOTAL, quarters to the year, shares to 100, provinces to Indonesia."""
    g = df[(df["indicator"] == "grdp_current") & df["period"].str.startswith("2025")]
    sectors = g[g["sector"] != "TOTAL"].groupby(["province_code", "period"])["value"].sum()
    total = g[g["sector"] == "TOTAL"].set_index(["province_code", "period"])["value"]
    assert (sectors - total).abs().max() <= TOL_GRDP_SUM
    quarters = g[g["period"].str.contains("Q")].groupby(["province_code", "sector"])["value"].sum()
    year = g[g["period"] == "2025"].set_index(["province_code", "sector"])["value"]
    assert (quarters - year).abs().max() <= TOL_GRDP_SUM
    share = df[(df["indicator"] == "population_share") & (df["province_code"] != "00")]["value"].sum()
    assert abs(share - 100) <= TOL_SHARE_SUM, share
    pop = df[df["indicator"] == "population"]
    provinces = pop[pop["province_code"] != "00"].groupby("period")["value"].sum()
    national = pop[pop["province_code"] == "00"].set_index("period")["value"]
    assert ((provinces - national).abs() / national).max() <= TOL_NATIONAL_REL


def plausibility_flags(df):
    """Layer 5: list values outside their plausible range, skipping changes across the Papua split."""
    flags = []

    def flag(row, check, value):
        lo, hi = PLAUSIBLE[check]
        if not lo <= value <= hi:
            flags.append({"province_code": row.province_code, "check": check, "period": row.period,
                          "value": round(value, 4), "range": [lo, hi]})

    for indicator, check in [("grdp_current", "grdp_growth_pct"), ("population", "population_growth_pct")]:
        s = df[(df["indicator"] == indicator) & (df["sector"].isin(["TOTAL", ""])) & ~df["period"].str.contains("Q")]
        s = s.sort_values(["province_code", "period"])
        s = s.assign(change=s.groupby("province_code")["value"].pct_change() * 100)
        for row in s.dropna(subset=["change"]).itertuples():
            if row.province_code in SPLIT_PARENTS and int(row.period) == FIRST_SPLIT_YEAR:
                continue
            flag(row, check, row.change)
    for indicator in ["sex_ratio", "population_density"]:
        for row in df[df["indicator"] == indicator].itertuples():
            flag(row, indicator, row.value)
    for row in df[(df["indicator"] == "grdp_current") & (df["value"] < 0)].itertuples():
        flags.append({"province_code": row.province_code, "check": "negative_grdp", "period": row.period,
                      "sector": row.sector, "value": row.value})
    return flags


# Steps

# Read the BPS province list that every province name is matched against
provinces, lookup = load_provinces(RAW_PROVINCES)

# Read the full 2025 GRDP table and the 2025 population table
grdp = read_grdp_industry(RAW_GRDP_INDUSTRY, lookup)
population, pop_notes = read_population(RAW_POPULATION, lookup)

# Read the 2020-2025 annual series for GRDP total and population
wb = openpyxl.load_workbook(RAW_SERIES)
series = (read_series_sheet(wb["GRDP ADHB 2020-2025"], "grdp_current", "TOTAL", lookup)
          + read_series_sheet(wb["Population 2020-2025"], "population", "", lookup))

# Layer 4: merge sources, keeping BPS table values and checking any overlap matches exactly
records = {}
for r in grdp + population + series:
    k = key(r)
    if k in records:
        assert records[k]["value"] == r["value"], (k, records[k]["value"], r["value"])
    else:
        records[k] = r

# Layer 4: check the 2025 GRDP total CSV repeats the industry table's total columns
total_rows = read_csv_rows(RAW_GRDP_TOTAL)
assert all(READ_CONTEXT[RAW_GRDP_TOTAL]["unit_text"] in h for h in total_rows[0][1:])
for row in total_rows[1:]:
    for cell, period in zip(row[1:], ["2025Q1", "2025Q2", "2025Q3", "2025Q4", "2025"]):
        value = parse_number(cell, READ_CONTEXT[RAW_GRDP_TOTAL])
        assert records[(lookup[normalise(row[0])], "grdp_current", "TOTAL", period)]["value"] == value

# Layer 4: check the 2025 combined workbook repeats the same GRDP and population values
ws = openpyxl.load_workbook(RAW_COMBINED)["Combined 2025"]
assert READ_CONTEXT[RAW_COMBINED]["unit_text"] in ws["B3"].value
for name, grdp_2025, pop_2025, _ in ws.iter_rows(min_row=4, max_row=41, values_only=True):
    assert records[(lookup[normalise(name)], "grdp_current", "TOTAL", "2025")]["value"] == grdp_2025
    assert records[(lookup[normalise(name)], "population", "", "2025")]["value"] == pop_2025

# Build the long table sorted by indicator, province, sector and period
df = pd.DataFrame(records.values())
df["sector_order"] = df["sector"].map({c: i for i, c in enumerate(SECTORS)}).fillna(-1)
df = df.sort_values(["indicator", "province_code", "sector_order", "period"]).drop(columns="sector_order")
df = df.reset_index(drop=True)

# Layers 1-3: stop before writing if structure, completeness or identities fail
check_structure(df, provinces)
found = {key(r) for r in df.to_dict("records")}
expected = expected_keys(provinces)
assert found == expected, {"missing": sorted(expected - found)[:10], "extra": sorted(found - expected)[:10]}
check_identities(df)

# Layer 5: collect plausibility flags for the metadata
flags = plausibility_flags(df)

# Write the long table
df.to_csv(OUT_CSV, index=False, float_format="%.10g", lineterminator="\n")

# Layer 6: write the metadata, with raw file hashes for provenance
raw_files = [RAW_PROVINCES, RAW_GRDP_INDUSTRY, RAW_GRDP_TOTAL, RAW_POPULATION, RAW_SERIES, RAW_COMBINED]
meta = {
    "title": "BPS provincial GRDP (current prices) and population, Indonesia",
    "file": OUT_CSV.name,
    "format": {
        "encoding": "UTF-8, no byte-order mark",
        "delimiter": ",",
        "decimal": ".",
        "thousands_separator": None,
        "missing": "a missing row means BPS has no value; no placeholder values are written",
        "layout": "one value per row",
    },
    "columns": {
        "province_code": "BPS province code (kode_bps); 00 = Indonesia. Names and Kemendagri codes in 'provinces'.",
        "indicator": "Indicator code; definitions in 'indicators'.",
        "sector": "GRDP sector code (KBLI letter groups) or TOTAL; empty for population indicators.",
        "period": "YYYY = annual, YYYYQn = quarter n.",
        "value": "Number in the indicator's unit, as published by BPS (not rounded or rescaled). Multiply by 'multiplier' for base units.",
    },
    "provinces": provinces,
    "province_source": {
        "url": URL_PROVINCES,
        "note": "BPS and Kemendagri codes differ for the six Papua provinces; join other datasets on the code system they use.",
    },
    "sectors": SECTORS,
    "indicators": {
        "grdp_current": {
            "name": "PDRB atas dasar harga berlaku (GRDP at current prices), Seri 2010",
            "unit": "Rp billion (Milyar Rupiah)",
            "multiplier": 1e9,
            "base_unit": "Rp",
            "periods": "2025Q1-2025Q4 and 2025 by sector; 2020-2024 annual TOTAL only",
            "source": URL_GRDP,
            "notes": [
                "2025 values come from the BPS table '[Seri 2010] PDRB Triwulanan Atas Dasar Harga Berlaku Menurut Lapangan Usaha di Provinsi Seluruh Indonesia', last updated 5 Aug 2026.",
                "2020-2024 annual totals come from the same BPS table for earlier years, compiled in raw/grdp-population/20261102_bps-province-grdp-population-2020-2025.xlsx.",
                "Recent years (2024-2025 in particular) are likely preliminary and subject to revision.",
                "BPS publishes no Indonesia row in this table; the sum of provincial GRDP is not national GDP, which BPS does not reconcile with it.",
                f"Sectors may differ from TOTAL, and quarters from the year, by up to {TOL_GRDP_SUM} because of rounding in the BPS table.",
            ],
        },
        "population": {
            "name": "Jumlah penduduk (population)",
            "unit": "thousand people (Ribu)",
            "multiplier": 1e3,
            "base_unit": "people",
            "periods": "2020-2025 annual",
            "source": URL_POP + "?year=YYYY",
            "notes": [
                "2020 = Sensus Penduduk 2020 (September 2020).",
                "2021-2025 = Proyeksi Penduduk Indonesia 2020-2050 hasil SP2020, mid-year (June).",
                "The 2025 table was last updated 2 May 2025.",
            ],
        },
        "population_growth": {
            "name": "Laju pertumbuhan penduduk per tahun (annual population growth rate)",
            "unit": "percent per year",
            "multiplier": 1,
            "periods": "2025",
            "source": URL_POP + "?year=2025",
            "notes": ["Growth from the September 2020 census to the June 2025 projection; 2020 base population is the sum of the forming regencies and municipalities."],
        },
        "population_share": {
            "name": "Distribusi persentase penduduk (share of national population)",
            "unit": "percent",
            "multiplier": 1,
            "periods": "2025",
            "source": URL_POP + "?year=2025",
        },
        "population_density": {
            "name": "Kepadatan penduduk (population density)",
            "unit": "people per km2",
            "multiplier": 1,
            "periods": "2025",
            "source": URL_POP + "?year=2025",
            "notes": ["Province area per Kepmendagri Nomor 100.1.1-6117 Tahun 2022 (9 November 2022)."],
        },
        "sex_ratio": {
            "name": "Rasio jenis kelamin penduduk (sex ratio)",
            "unit": "males per 100 females",
            "multiplier": 1,
            "periods": "2025",
            "source": URL_POP + "?year=2025",
        },
    },
    "notes": [
        "Papua split: Papua Barat Daya (92), Papua Selatan (95), Papua Tengah (96) and Papua Pegunungan (97) have values from 2024. For 2020-2023, Papua (94) and Papua Barat (91) are the pre-split provinces and are not comparable with 2024-2025.",
        "For a consistent series: Papua (old) = 94 + 95 + 96 + 97; Papua Barat (old) = 91 + 92.",
        "GRDP per capita (Rp million per person) = grdp_current (Rp billion) / population (thousand); it is not stored because it is derived, and it may differ slightly from BPS's own PDRB per kapita.",
    ],
    "bps_population_footnotes": pop_notes,
    "checks": {
        "passed": [
            "structure: columns, types, unique keys, known codes",
            "completeness: every expected province, indicator, sector and period is present; only the Papua split leaves gaps",
            f"identities: sectors vs TOTAL and quarters vs year within {TOL_GRDP_SUM}; population shares sum to 100 within {TOL_SHARE_SUM}; provinces sum to Indonesia population within {TOL_NATIONAL_REL:.0e} relative",
            "cross-source: values repeated across raw files match exactly",
        ],
        "plausible_ranges": PLAUSIBLE,
        "flags": flags,
    },
    "raw_files": {str(p.relative_to(ROOT)): {"sha256": sha256(p)} for p in raw_files},
}
OUT_META.write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

# Report what was written
print(f"{OUT_CSV.name}: {len(df)} rows, {len(flags)} plausibility flags")
for f in flags:
    print("  flag:", f)
