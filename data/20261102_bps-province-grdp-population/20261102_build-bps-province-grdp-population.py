from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# Load the shared cleaning module from tools/
import sys
sys.path.insert(0, str(ROOT / "tools"))
import cleaning

import openpyxl
import pandas as pd

# Parameters

# Raw inputs, in priority order: BPS pages first, then BPS CSV downloads, then the compiled workbooks
RAW_PROVINCES = ROOT / "raw/province-codes/20261102_bps-province-codes-2025-s1.json"
RAW_POP_PAGES = {year: ROOT / f"raw/population/20261102_bps-population-by-province-{year}.html" for year in range(2020, 2027)}
RAW_GRDP_PAGE = ROOT / "raw/grdp/20261102_bps-grdp-quarterly-by-industry-2026.html"
RAW_GRDP_INDUSTRY = ROOT / "raw/grdp/20261102_grdp-quarterly-current-prices-by-industry-by-province-2025.csv"
RAW_GRDP_TOTAL = ROOT / "raw/grdp/20261102_bps-grdp-current-prices-by-province-2025-total.csv"
RAW_POPULATION = ROOT / "raw/population/20261102_population-growth-share-density-sex-ratio-by-province-2025.csv"
RAW_SERIES = ROOT / "raw/grdp-population/20261102_bps-province-grdp-population-2020-2025.xlsx"
RAW_COMBINED = ROOT / "raw/grdp-population/20261102_bps-province-grdp-population-2025.xlsx"

# Output; the metadata JSON is written beside it with a -metadata suffix
OUT_CSV = HERE / "20261102_bps-province-grdp-population.csv"

# How each raw file writes numbers, read from opening the files
READ_CONTEXT = {
    RAW_PROVINCES: {"encoding": "utf-8"},
    "pop_pages": {"decimal": ",", "thousands": "."},
    "grdp_page": {"unit": "Milyar Rupiah", "decimals": 2, "var": 2268},
    RAW_GRDP_INDUSTRY: {"encoding": "utf-8-sig", "delimiter": ",", "decimal": ".", "thousands": None, "unit_text": "(Milyar Rupiah)"},
    RAW_GRDP_TOTAL: {"encoding": "utf-8", "delimiter": ",", "decimal": ".", "thousands": None, "unit_text": "(Milyar Rp)"},
    RAW_POPULATION: {"encoding": "utf-8-sig", "delimiter": ",", "decimal": ".", "thousands": None, "unit_text": "(Ribu)"},
    RAW_SERIES: {"missing": ["-"], "unit_text": {"GRDP ADHB 2020-2025": "Rp billion", "Population 2020-2025": "Thousand people"}},
    RAW_COMBINED: {"missing": [], "unit_text": "(Rp billion)"},
}

KEYS = ["province_code", "indicator", "sector", "period"]

# BPS population page variables: id -> (indicator, decimals, unit multiplier as a power of ten)
POP_VARIABLES = {
    "nzudy5elv7": ("population", 1, 3),
    "d8efayjxld": ("population_growth", 2, None),
    "efg2cjrdn2": ("population_share", 2, None),
    "xauol4vjpj": ("population_density", 0, None),
    "ztxhjlhyqd": ("sex_ratio", 1, None),
}

# Population CSV columns mapped to indicator codes
POP_COLUMNS = {
    "Jumlah Penduduk (Ribu)": "population",
    "Laju Pertumbuhan Penduduk per Tahun": "population_growth",
    "Persentase Penduduk": "population_share",
    "Kepadatan Penduduk per km persegi (Km2)": "population_density",
    "Rasio Jenis Kelamin Penduduk": "sex_ratio",
}

# GRDP sector codes, in the order of the BPS KBLI letter groups
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

# GRDP revision status by year, as the BPS table note states it; the note must still carry each phrase
GRDP_STATUS = {
    2024: ("*", "Triwulan I–IV 2024 dan Tahun 2024: Angka sementara"),
    2025: ("**", "Triwulan I–IV 2025 dan Tahun 2025: Angka sangat sementara"),
    2026: ("***", "Triwulan I–II 2026 : Angka sangat sangat sementara"),
}

# Papua split: new BPS codes, their parents, and the first year with separate values
NEW_PROVINCES = {"92", "95", "96", "97"}
SPLIT_PARENTS = {"91", "94"}
FIRST_SPLIT_YEAR = 2024

# Periods each indicator should cover
POP_YEARS = range(2020, 2027)
GRDP_TOTAL_YEARS = range(2020, 2025)
GRDP_SECTOR_PERIODS = ["2025Q1", "2025Q2", "2025Q3", "2025Q4", "2025", "2026Q1", "2026Q2"]

# Tolerances for accounting identities, set by the rounding in the BPS tables
TOL_GRDP_SUM = 0.05        # Rp billion
TOL_SHARE_SUM = 0.1        # percentage points
TOL_NATIONAL_REL = 1e-4    # relative

# Plausibility ranges; a value outside its range is flagged, not dropped
PLAUSIBLE = {
    "grdp_growth_pct": (-20, 40),
    "population_change_pct": (0, 4),
    "sex_ratio": (90, 120),
    "population_density": (1, 20000),
}

URL_PROVINCES = "https://sig.bps.go.id/rest-bridging/getwilayah?level=provinsi&periode_merge=2025_1.2025"
URL_GRDP = "https://www.bps.go.id/id/statistics-table/2/MjI2OCMy/-seri-2010--pdrb-triwulanan-atas-dasar-harga-berlaku-menurut-lapangan-usaha-di-provinsi-seluruh-indonesia--milyar-rupiah-.html"
URL_POP = "https://www.bps.go.id/id/statistics-table/3/V1ZSbFRUY3lTbFpEYTNsVWNGcDZjek53YkhsNFFUMDkjMyMwMDAw/jumlah-penduduk--laju-pertumbuhan-penduduk--distribusi-persentase-penduduk--kepadatan-penduduk--rasio-jenis-kelamin-penduduk-menurut-provinsi.html?year={year}"


# Functions

def row(code, indicator, sector, period, value, status=""):
    """Return one long row."""
    return {"province_code": code, "indicator": indicator, "sector": sector, "period": period,
            "status": status, "value": value}


def read_population_page(path, year, lookup):
    """Read one year's BPS population page into long rows and a description of the table."""
    text = cleaning.bps_flight_text(path)
    table = cleaning.bps_find_object(text, ["tahun_data", "kolom", "data"])
    assert table["tahun_data"] == year, (path, table["tahun_data"])
    # Check each variable still has the decimals and multiplier this script expects
    for vid, (indicator, decimals, multiplier) in POP_VARIABLES.items():
        assert table["kolom"][vid]["angka_desimal_dibelakang_koma"] == decimals, (year, vid)
        assert table["kolom"][vid].get("unit_multiplier") == multiplier, (year, vid)
    context = READ_CONTEXT["pop_pages"]
    out = []
    for r in table["data"]:
        # BPS writes region codes as seven digits; the first two are the province
        code = cleaning.province_code(r["label"], lookup, str(r["kode_wilayah"]).zfill(7)[:2])
        for vid, (indicator, decimals, _) in POP_VARIABLES.items():
            cell = r["variables"][vid]
            status = cell["value_code"] or ""
            if status in cleaning.BPS_NO_VALUE:
                assert cell["value_raw"] is None, (year, r["label"], cell)
                continue
            value = cleaning.parse_number(cell["value_raw"], context["decimal"], context["thousands"], decimals)
            out.append(row(code, indicator, "", str(year), value, status))
    info = {
        "title": table["judul_tabel_en"],
        "url": URL_POP.format(year=year),
        "table_updated": table.get("table_updated"),
        "source": cleaning.html_to_text(table["sumber"]),
        "notes": cleaning.html_to_text(cleaning.bps_resolve(text, table["catatan"])),
    }
    return out, info


def read_grdp_page(path, lookup):
    """Read the BPS GRDP-by-industry page (latest year) into long rows and the table note."""
    text = cleaning.bps_flight_text(path)
    t = cleaning.bps_find_object(text, ["datacontent", "vervar", "turvar", "tahun", "turtahun", "var"])
    context = READ_CONTEXT["grdp_page"]
    var = t["var"][0]
    assert var["val"] == context["var"] and var["unit"] == context["unit"] and var["decimal"] == context["decimals"], var
    labels = [x["label"] for x in t["turvar"]]
    assert len(labels) == len(SECTORS) and all(l.endswith(s) for l, s in zip(labels, SECTORS.values())), labels
    note = cleaning.html_to_text(var["note"])
    out, used = [], set()
    for v in t["vervar"]:
        code = cleaning.province_code(v["label"], lookup, f"{v['val']:02d}")
        for sector, tv in zip(SECTORS, t["turvar"]):
            for th in t["tahun"]:
                for tt in t["turtahun"]:
                    k = f"{v['val']}{var['val']}{tv['val']}{th['val']}{tt['val']}"
                    if k not in t["datacontent"]:
                        continue
                    value = float(t["datacontent"][k])
                    # Values must carry no more decimals than the table declares
                    assert round(value, context["decimals"]) == value, (k, value)
                    out.append(row(code, "grdp_current", sector, th["label"] + PERIODS[tt["label"]], value))
                    used.add(k)
    # Every published value must have been read
    assert used == set(t["datacontent"]), len(set(t["datacontent"]) - used)
    return out, note, t["last_update"]


def read_grdp_industry(path, lookup):
    """Read the BPS quarterly GRDP-by-industry CSV (2025) into long rows."""
    c = READ_CONTEXT[path]
    rows = cleaning.read_csv_rows(path, c["encoding"], c["delimiter"])
    # Row 1 carries the unit, row 2 names each sector over five columns, row 4 names the period
    cleaning.require_text(rows[1][1], c["unit_text"], path.name)
    sector_row, period_row = rows[2], rows[4]
    labels = [x for x in sector_row[1:] if x]
    assert len(labels) == len(SECTORS) and len(period_row) == 1 + 5 * len(SECTORS)
    assert all(l.endswith(s) for l, s in zip(labels, SECTORS.values())), labels
    out = []
    for r in rows[5:]:
        if not r or not r[0].strip():
            continue
        code = cleaning.province_code(r[0], lookup)
        for i in range(1, len(period_row)):
            value = cleaning.parse_number(r[i], c["decimal"], c["thousands"])
            out.append(row(code, "grdp_current", list(SECTORS)[(i - 1) // 5], "2025" + PERIODS[period_row[i].strip()], value))
    return out


def read_population_csv(path, lookup):
    """Read the BPS 2025 population CSV into long rows."""
    c = READ_CONTEXT[path]
    rows = cleaning.read_csv_rows(path, c["encoding"], c["delimiter"])
    header = rows[0]
    cleaning.require_text(header[1], c["unit_text"], path.name)
    out = []
    for r in rows[1:]:
        if cleaning.normalise_name(r[0]) not in lookup:
            continue
        for col, indicator in POP_COLUMNS.items():
            value = cleaning.parse_number(r[header.index(col)], c["decimal"], c["thousands"])
            out.append(row(cleaning.province_code(r[0], lookup), indicator, "", "2025", value))
    return out


def read_grdp_total_csv(path, lookup):
    """Read the 2025 GRDP total CSV, an extract of the industry table, into long rows."""
    c = READ_CONTEXT[path]
    rows = cleaning.read_csv_rows(path, c["encoding"], c["delimiter"])
    for h in rows[0][1:]:
        cleaning.require_text(h, c["unit_text"], path.name)
    out = []
    for r in rows[1:]:
        for cell, period in zip(r[1:], ["2025Q1", "2025Q2", "2025Q3", "2025Q4", "2025"]):
            value = cleaning.parse_number(cell, c["decimal"], c["thousands"])
            out.append(row(cleaning.province_code(r[0], lookup), "grdp_current", "TOTAL", period, value))
    return out


def read_series_sheet(ws, indicator, sector, lookup):
    """Read one 2020-2025 annual sheet of the compiled series workbook into long rows."""
    c = READ_CONTEXT[RAW_SERIES]
    cleaning.require_text(ws["A2"].value, c["unit_text"][ws.title], ws.title)
    years = [str(x.value) for x in ws[4][1:]]
    out = []
    for r in ws.iter_rows(min_row=5, values_only=True):
        if r[0] is None:
            continue
        for year, cell in zip(years, r[1:]):
            value = cleaning.parse_cell(cell, c["missing"])
            # A missing marker means the province did not exist yet, so no row is written
            if value is not None:
                out.append(row(cleaning.province_code(r[0], lookup), indicator, sector, year, value))
    return out


def read_combined(path, lookup):
    """Read the 2025 combined workbook's GRDP and population columns into long rows."""
    ws = openpyxl.load_workbook(path)["Combined 2025"]
    cleaning.require_text(ws["B3"].value, READ_CONTEXT[path]["unit_text"], path.name)
    out = []
    for name, grdp, pop, _ in ws.iter_rows(min_row=4, max_row=41, values_only=True):
        code = cleaning.province_code(name, lookup)
        out += [row(code, "grdp_current", "TOTAL", "2025", float(grdp)), row(code, "population", "", "2025", float(pop))]
    return out


def existing(provinces, year):
    """Return the province codes that have separate values in a given year."""
    return [c for c in provinces if c != cleaning.NATIONAL_CODE and (year >= FIRST_SPLIT_YEAR or c not in NEW_PROVINCES)]


def expected_keys(provinces):
    """Every key the sources should yield; the Papua split is the only gap."""
    keys = set()
    for period in GRDP_SECTOR_PERIODS:
        for c in existing(provinces, int(period[:4])):
            keys |= {(c, "grdp_current", s, period) for s in SECTORS}
    for year in GRDP_TOTAL_YEARS:
        keys |= {(c, "grdp_current", "TOTAL", str(year)) for c in existing(provinces, year)}
    for year in POP_YEARS:
        for c in existing(provinces, year) + [cleaning.NATIONAL_CODE]:
            keys |= {(c, ind, "", str(year)) for ind, _, _ in POP_VARIABLES.values()}
    return keys


def identity_checks(df):
    """Layer 3: sectors to TOTAL, quarters to year, shares to 100, provinces to Indonesia."""
    results = []
    g = df[(df["indicator"] == "grdp_current") & df["period"].isin(GRDP_SECTOR_PERIODS)]
    parts = g[g["sector"] != "TOTAL"].groupby(["province_code", "period"])["value"].sum()
    total = g[g["sector"] == "TOTAL"].set_index(["province_code", "period"])["value"]
    results.append(cleaning.check_sum(parts, total, TOL_GRDP_SUM, "GRDP sectors sum to TOTAL"))
    q = g[g["period"].str.startswith("2025Q")].groupby(["province_code", "sector"])["value"].sum()
    y = g[g["period"] == "2025"].set_index(["province_code", "sector"])["value"]
    results.append(cleaning.check_sum(q, y, TOL_GRDP_SUM, "GRDP 2025 quarters sum to year"))
    p = df[df["indicator"].isin(["population", "population_share"])]
    provs, nat = p[p["province_code"] != "00"], p[p["province_code"] == "00"]
    share = provs[provs["indicator"] == "population_share"].groupby("period")["value"].sum()
    results.append(cleaning.check_sum(share, pd.Series(100.0, index=share.index), TOL_SHARE_SUM, "population shares sum to 100"))
    pop = provs[provs["indicator"] == "population"].groupby("period")["value"].sum()
    natpop = nat[nat["indicator"] == "population"].set_index("period")["value"]
    results.append(cleaning.check_sum(pop, natpop, TOL_NATIONAL_REL, "provinces sum to Indonesia population", relative=True))
    return results


def plausibility_flags(df):
    """Layer 5: year-on-year changes and levels outside their plausible range."""
    flags = []
    for indicator, check in [("grdp_current", "grdp_growth_pct"), ("population", "population_change_pct")]:
        s = df[(df["indicator"] == indicator) & df["sector"].isin(["TOTAL", ""]) & ~df["period"].str.contains("Q")]
        s = s.sort_values(["province_code", "period"])
        s = s.assign(change=s.groupby("province_code")["value"].pct_change() * 100).dropna(subset=["change"])
        # Changes across the Papua split compare different areas, so they are skipped
        s = s[~(s["province_code"].isin(SPLIT_PARENTS) & (s["period"].astype(int) == FIRST_SPLIT_YEAR))]
        flags += cleaning.flag_outside([{"province_code": r.province_code, "period": r.period, "value": r.change}
                                        for r in s.itertuples()], check, *PLAUSIBLE[check])
    for indicator in ["sex_ratio", "population_density"]:
        s = df[df["indicator"] == indicator]
        flags += cleaning.flag_outside([{"province_code": r.province_code, "period": r.period, "value": r.value}
                                        for r in s.itertuples()], indicator, *PLAUSIBLE[indicator])
    return flags


# Steps

# Read the BPS province list that every province name and code is matched against;
# load_bps_provinces reads UTF-8, so a list declared in another encoding stops the build
assert READ_CONTEXT[RAW_PROVINCES]["encoding"] == "utf-8", READ_CONTEXT[RAW_PROVINCES]
provinces, lookup = cleaning.load_bps_provinces(RAW_PROVINCES)

# Read the BPS population pages, 2020-2026
pop_pages, pop_tables = [], {}
for year, path in RAW_POP_PAGES.items():
    rows, pop_tables[str(year)] = read_population_page(path, year, lookup)
    pop_pages += rows

# Read the BPS GRDP page (2026) and check its note still states the revision status of each year
grdp_page, grdp_note, grdp_updated = read_grdp_page(RAW_GRDP_PAGE, lookup)
for year, (_, phrase) in GRDP_STATUS.items():
    cleaning.require_text(grdp_note, phrase, "GRDP table note")

# Read the CSV downloads and the compiled workbooks
grdp_industry = read_grdp_industry(RAW_GRDP_INDUSTRY, lookup)
pop_csv = read_population_csv(RAW_POPULATION, lookup)
grdp_total_csv = read_grdp_total_csv(RAW_GRDP_TOTAL, lookup)
wb = openpyxl.load_workbook(RAW_SERIES)
series_grdp = read_series_sheet(wb["GRDP ADHB 2020-2025"], "grdp_current", "TOTAL", lookup)
series_pop = read_series_sheet(wb["Population 2020-2025"], "population", "", lookup)
combined = read_combined(RAW_COMBINED, lookup)

# Layer 4: merge in priority order; every value repeated across sources must match exactly
rows, overlaps = cleaning.merge_sources([
    ("BPS population pages", pop_pages),
    ("BPS GRDP page 2026", grdp_page),
    ("BPS GRDP industry CSV 2025", grdp_industry),
    ("BPS population CSV 2025", pop_csv),
    ("GRDP total CSV 2025", grdp_total_csv),
    ("series workbook GRDP", series_grdp),
    ("series workbook population", series_pop),
    ("combined workbook 2025", combined),
], KEYS)

# Mark GRDP values with the revision status the BPS note gives their year
status_by_year = {str(y): s for y, (s, _) in GRDP_STATUS.items()}
for r in rows:
    if r["indicator"] == "grdp_current":
        r["status"] = status_by_year.get(r["period"][:4], "")

# Layers 3 and 5: identities stop the build; plausibility only flags
df = pd.DataFrame(rows)
identities = identity_checks(df)
flags = plausibility_flags(df)

# Describe the dataset
meta = {
    "title": "BPS provincial GRDP (current prices) and population, Indonesia",
    "columns": {
        "province_code": "BPS province code (kode_bps); 00 = Indonesia. Names and Kemendagri codes in 'provinces'.",
        "indicator": "Indicator code; definitions in 'indicators'.",
        "sector": "GRDP sector code (KBLI letter groups) or TOTAL; empty for population indicators.",
        "period": "YYYY = annual, YYYYQn = quarter n.",
        "status": "BPS revision marker; meanings in 'status'.",
        "value": "Number in the indicator's unit, as published by BPS. Multiply by 'multiplier' for base units.",
    },
    "provinces": provinces,
    "province_source": {"url": URL_PROVINCES, "file": RAW_PROVINCES.relative_to(ROOT).as_posix(),
                        "note": "BPS and Kemendagri codes differ for the six Papua provinces; join other datasets on the code system they use."},
    "sectors": SECTORS,
    "indicators": {
        "grdp_current": {
            "name": "PDRB atas dasar harga berlaku (GRDP at current prices), Seri 2010",
            "unit": "Rp billion (Milyar Rupiah)", "multiplier": 1e9, "base_unit": "Rp",
            "periods": "by sector: 2025Q1-2025Q4, 2025, 2026Q1-2026Q2; TOTAL only: 2020-2024 annual",
            "source": URL_GRDP,
            "notes": [
                f"BPS table note (page last updated {grdp_updated}): {grdp_note}",
                "2020-2024 annual totals come from the compiled workbook raw/grdp-population/20261102_bps-province-grdp-population-2020-2025.xlsx, not yet from a BPS page; quarterly and sector values for those years need the BPS WebAPI.",
                "BPS publishes no Indonesia row in this table; the sum of provincial GRDP is not national GDP.",
            ],
        },
        "population": {"name": "Jumlah penduduk (population)", "unit": "thousand people (ribu)", "multiplier": 1e3, "base_unit": "people",
                       "periods": "2020-2026 annual", "notes": ["2020 = Sensus Penduduk 2020 (September); 2021-2022 = Proyeksi Penduduk Interim 2020-2023; 2023 onward = Proyeksi Penduduk Indonesia 2020-2050; all mid-year (June). See 'source_tables' for each year.",
                                 "The change from the interim to the 2020-2050 projection between 2022 and 2023 can show as a population fall in 2023 that is not a real decline."]},
        "population_growth": {"name": "Laju pertumbuhan penduduk per tahun (annual population growth rate)", "unit": "percent per year", "multiplier": 1,
                              "periods": "2020-2026 annual", "notes": ["The base period differs by year (2020: 2010-2020; later years: from SP2020). See 'source_tables' for each year."]},
        "population_share": {"name": "Distribusi persentase penduduk (share of national population)", "unit": "percent", "multiplier": 1, "periods": "2020-2026 annual"},
        "population_density": {"name": "Kepadatan penduduk (population density)", "unit": "people per km2", "multiplier": 1, "periods": "2020-2026 annual",
                               "notes": ["The area basis differs by year (Permendagri 72/2019, later Kepmendagri 2022). See 'source_tables'."]},
        "sex_ratio": {"name": "Rasio jenis kelamin penduduk (sex ratio)", "unit": "males per 100 females", "multiplier": 1, "periods": "2020-2026 annual"},
    },
    "source_tables": {"population": pop_tables},
    "notes": [
        "Papua split: Papua Barat Daya (92), Papua Selatan (95), Papua Tengah (96) and Papua Pegunungan (97) have values from 2024. For 2020-2023, Papua (94) and Papua Barat (91) are the pre-split provinces and are not comparable with 2024 onward.",
        "For a consistent series: Papua (old) = 94 + 95 + 96 + 97; Papua Barat (old) = 91 + 92.",
        "GRDP per capita (Rp million per person) = grdp_current (Rp billion) / population (thousand); not stored because it is derived.",
    ],
    "checks": {
        "passed": ["identities", "cross-source"],
        "identities": identities,
        "cross_source_overlaps": overlaps,
        "plausible_ranges": PLAUSIBLE,
        "flags": flags,
    },
}

# Layers 1, 2 and 6: check structure and completeness, then write the CSV and metadata
raw_files = [RAW_PROVINCES, *RAW_POP_PAGES.values(), RAW_GRDP_PAGE, RAW_GRDP_INDUSTRY, RAW_GRDP_TOTAL,
             RAW_POPULATION, RAW_SERIES, RAW_COMBINED]
out = cleaning.write_dataset(
    rows, KEYS,
    allowed={"province_code": provinces, "sector": [""] + list(SECTORS),
             "indicator": [ind for ind, _, _ in POP_VARIABLES.values()] + ["grdp_current"]},
    expected=expected_keys(provinces),
    csv_path=OUT_CSV, meta=meta, raw_files=raw_files,
    sort_orders={"sector": [""] + list(SECTORS)},
)

# Report what was written
print(f"{OUT_CSV.name}: {len(out)} rows, {len(flags)} plausibility flags")
print(out.groupby(["indicator", "status"]).size().to_string())
for f in flags:
    print("  flag:", f)
