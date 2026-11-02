from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

import csv
import json

import openpyxl
import pandas as pd

# Parameters

# Raw inputs, as filed from .inbox on 20261102
RAW_GRDP_INDUSTRY = ROOT / "raw/grdp/20261102_grdp-quarterly-current-prices-by-industry-by-province-2025.csv"
RAW_GRDP_TOTAL = ROOT / "raw/grdp/20261102_bps-grdp-current-prices-by-province-2025-total.csv"
RAW_POPULATION = ROOT / "raw/population/20261102_population-growth-share-density-sex-ratio-by-province-2025.csv"
RAW_SERIES = ROOT / "raw/grdp-population/20261102_bps-province-grdp-population-2020-2025.xlsx"
RAW_COMBINED = ROOT / "raw/grdp-population/20261102_bps-province-grdp-population-2025.xlsx"

# Outputs
OUT_CSV = HERE / "20261102_bps-province-grdp-population.csv"
OUT_META = HERE / "20261102_bps-province-grdp-population-metadata.json"

# BPS province codes (Kode Wilayah, Kepmendagri 2022), with "00" for Indonesia
PROVINCES = {
    "11": "Aceh", "12": "Sumatera Utara", "13": "Sumatera Barat", "14": "Riau",
    "15": "Jambi", "16": "Sumatera Selatan", "17": "Bengkulu", "18": "Lampung",
    "19": "Kepulauan Bangka Belitung", "21": "Kepulauan Riau", "31": "DKI Jakarta",
    "32": "Jawa Barat", "33": "Jawa Tengah", "34": "DI Yogyakarta", "35": "Jawa Timur",
    "36": "Banten", "51": "Bali", "52": "Nusa Tenggara Barat", "53": "Nusa Tenggara Timur",
    "61": "Kalimantan Barat", "62": "Kalimantan Tengah", "63": "Kalimantan Selatan",
    "64": "Kalimantan Timur", "65": "Kalimantan Utara", "71": "Sulawesi Utara",
    "72": "Sulawesi Tengah", "73": "Sulawesi Selatan", "74": "Sulawesi Tenggara",
    "75": "Gorontalo", "76": "Sulawesi Barat", "81": "Maluku", "82": "Maluku Utara",
    "91": "Papua Barat", "92": "Papua Tengah", "93": "Papua Selatan", "94": "Papua",
    "95": "Papua Pegunungan", "96": "Papua Barat Daya", "00": "Indonesia",
}
NAME_TO_CODE = {name: code for code, name in PROVINCES.items()}
NAME_TO_CODE.update({"Kep. Bangka Belitung": "19", "Kep. Riau": "21"})

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

URL_GRDP = "https://www.bps.go.id/id/statistics-table/2/MjI2OCMy/-seri-2010--pdrb-triwulanan-atas-dasar-harga-berlaku-menurut-lapangan-usaha-di-provinsi-seluruh-indonesia--milyar-rupiah-.html"
URL_POP = "https://www.bps.go.id/id/statistics-table/3/V1ZSbFRUY3lTbFpEYTNsVWNGcDZjek53YkhsNFFUMDkjMyMwMDAw/jumlah-penduduk--laju-pertumbuhan-penduduk--distribusi-persentase-penduduk--kepadatan-penduduk--rasio-jenis-kelamin-penduduk-menurut-provinsi.html"


# Functions

def code_of(name):
    """Return the BPS province code for a province name as written in a raw file."""
    return NAME_TO_CODE[name.strip()]


def read_grdp_industry(path):
    """Read the BPS quarterly GRDP-by-industry CSV into long rows."""
    rows = list(csv.reader(open(path, encoding="utf-8-sig")))
    # Row 2 names each sector over five columns (four quarters and the year), row 4 names the period
    sector_row, period_row = rows[2], rows[4]
    sector_codes = list(SECTORS)
    out = []
    for row in rows[5:]:
        if not row or not row[0].strip():
            continue
        for i in range(1, len(period_row)):
            sector = sector_codes[(i - 1) // 5]
            out.append({
                "province_code": code_of(row[0]),
                "indicator": "grdp_current",
                "sector": sector,
                "period": "2025" + PERIODS[period_row[i].strip()],
                "value": float(row[i]),
            })
    # Check the header text agrees with the sector order assumed above
    labels = [c for c in sector_row[1:] if c]
    for code, label in zip(sector_codes, labels):
        assert label.endswith(SECTORS[code]), (code, label)
    return out


def read_population(path):
    """Read the BPS 2025 population CSV into long rows and its footnotes."""
    rows = list(csv.reader(open(path, encoding="utf-8-sig")))
    header = rows[0]
    out, notes = [], []
    for row in rows[1:]:
        name = row[0].strip()
        if name in NAME_TO_CODE:
            for col, indicator in POP_COLUMNS.items():
                out.append({
                    "province_code": code_of(name),
                    "indicator": indicator,
                    "sector": "",
                    "period": "2025",
                    "value": float(row[header.index(col)]),
                })
        elif name and name != "Keterangan":
            notes.append(" ".join(name.split()))
    return out, notes


def read_series_sheet(ws, indicator, sector):
    """Read one 2020-2025 annual sheet of the series workbook into long rows."""
    years = [str(c.value) for c in ws[4][1:]]
    out = []
    for row in ws.iter_rows(min_row=5, values_only=True):
        if row[0] is None:
            continue
        for year, value in zip(years, row[1:]):
            # "-" marks a province that did not exist yet, so no row is written
            if value == "-" or value is None:
                continue
            out.append({
                "province_code": code_of(row[0]),
                "indicator": indicator,
                "sector": sector,
                "period": year,
                "value": float(value),
            })
    return out


def key(r):
    """Return the identifying fields of a long row."""
    return (r["province_code"], r["indicator"], r["sector"], r["period"])


# Steps

# Read the full 2025 GRDP table and the 2025 population table
grdp = read_grdp_industry(RAW_GRDP_INDUSTRY)
population, pop_notes = read_population(RAW_POPULATION)

# Read the 2020-2025 annual series for GRDP total and population
wb = openpyxl.load_workbook(RAW_SERIES, data_only=False)
series = (read_series_sheet(wb["GRDP ADHB 2020-2025"], "grdp_current", "TOTAL")
          + read_series_sheet(wb["Population 2020-2025"], "population", ""))

# Merge sources, keeping BPS table values and checking any overlap matches exactly
records = {}
for r in grdp + population + series:
    k = key(r)
    if k in records:
        assert abs(records[k]["value"] - r["value"]) < 1e-9, (k, records[k]["value"], r["value"])
    else:
        records[k] = r

# Check the 2025 GRDP total CSV repeats the industry table's total columns
total = pd.read_csv(RAW_GRDP_TOTAL)
for _, row in total.iterrows():
    for col, period in zip(total.columns[1:], ["2025Q1", "2025Q2", "2025Q3", "2025Q4", "2025"]):
        assert records[(code_of(row["Provinsi"]), "grdp_current", "TOTAL", period)]["value"] == row[col]

# Check the 2025 combined workbook repeats the same GRDP and population values
ws = openpyxl.load_workbook(RAW_COMBINED)["Combined 2025"]
for name, grdp_2025, pop_2025, _ in ws.iter_rows(min_row=4, max_row=41, values_only=True):
    assert records[(code_of(name), "grdp_current", "TOTAL", "2025")]["value"] == grdp_2025
    assert records[(code_of(name), "population", "", "2025")]["value"] == pop_2025

# Write the long table sorted by indicator, province, sector and period
df = pd.DataFrame(records.values())
df["sector_order"] = df["sector"].map({c: i for i, c in enumerate(SECTORS)}).fillna(-1)
df = df.sort_values(["indicator", "province_code", "sector_order", "period"]).drop(columns="sector_order")
df.to_csv(OUT_CSV, index=False, float_format="%.10g", lineterminator="\n")

# Write the metadata that the CSV codes refer to
meta = {
    "title": "BPS provincial GRDP (current prices) and population, Indonesia",
    "file": OUT_CSV.name,
    "format": "CSV, UTF-8, comma-separated, one value per row; a missing row means BPS has no value",
    "columns": {
        "province_code": "BPS two-digit province code; 00 = Indonesia. Names in 'provinces'.",
        "indicator": "Indicator code; definitions in 'indicators'.",
        "sector": "GRDP sector code (KBLI letter groups) or TOTAL; empty for population indicators.",
        "period": "YYYY = annual, YYYYQn = quarter n.",
        "value": "Number in the indicator's unit, as published by BPS (not rounded or rescaled).",
    },
    "provinces": PROVINCES,
    "sectors": SECTORS,
    "indicators": {
        "grdp_current": {
            "name": "PDRB atas dasar harga berlaku (GRDP at current prices), Seri 2010",
            "unit": "Rp billion (Milyar Rupiah)",
            "periods": "2025Q1-2025Q4 and 2025 by sector; 2020-2024 annual TOTAL only",
            "source": URL_GRDP,
            "notes": [
                "2025 values come from the BPS table '[Seri 2010] PDRB Triwulanan Atas Dasar Harga Berlaku Menurut Lapangan Usaha di Provinsi Seluruh Indonesia', last updated 5 Aug 2026.",
                "2020-2024 annual totals come from the same BPS table for earlier years, compiled in raw/grdp-population/20261102_bps-province-grdp-population-2020-2025.xlsx.",
                "Recent years (2024-2025 in particular) are likely preliminary and subject to revision.",
                "BPS publishes no Indonesia row in this table; the sum of provincial GRDP is not national GDP, which BPS does not reconcile with it.",
                "Sectors may differ from TOTAL, and quarters from the year, by up to 0.04 because of rounding in the BPS table.",
            ],
        },
        "population": {
            "name": "Jumlah penduduk (population)",
            "unit": "thousand people",
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
            "periods": "2025",
            "source": URL_POP + "?year=2025",
            "notes": ["Growth from the September 2020 census to the June 2025 projection; 2020 base population is the sum of the forming regencies and municipalities."],
        },
        "population_share": {
            "name": "Distribusi persentase penduduk (share of national population)",
            "unit": "percent",
            "periods": "2025",
            "source": URL_POP + "?year=2025",
        },
        "population_density": {
            "name": "Kepadatan penduduk (population density)",
            "unit": "people per km2",
            "periods": "2025",
            "source": URL_POP + "?year=2025",
            "notes": ["Province area per Kepmendagri Nomor 100.1.1-6117 Tahun 2022 (9 November 2022)."],
        },
        "sex_ratio": {
            "name": "Rasio jenis kelamin penduduk (sex ratio)",
            "unit": "males per 100 females",
            "periods": "2025",
            "source": URL_POP + "?year=2025",
        },
    },
    "notes": [
        "Papua split: Papua Barat Daya (96), Papua Selatan (93), Papua Tengah (92) and Papua Pegunungan (95) have values from 2024. For 2020-2023, Papua (94) and Papua Barat (91) are the pre-split provinces and are not comparable with 2024-2025.",
        "For a consistent series: Papua (old) = 94 + 93 + 92 + 95; Papua Barat (old) = 91 + 96.",
        "GRDP per capita (Rp million per person) = grdp_current (Rp billion) / population (thousand); it is not stored because it is derived, and it may differ slightly from BPS's own PDRB per kapita.",
    ],
    "bps_population_footnotes": pop_notes,
    "raw_files": [str(p.relative_to(ROOT)) for p in
                  [RAW_GRDP_INDUSTRY, RAW_GRDP_TOTAL, RAW_POPULATION, RAW_SERIES, RAW_COMBINED]],
}
OUT_META.write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

# Report what was written
print(f"{OUT_CSV.name}: {len(df)} rows")
print(df.groupby("indicator").size().to_string())
