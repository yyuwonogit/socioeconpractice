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

# Raw inputs, in priority order: the saved BPS pages (2026) first, then the WebAPI responses (2020-2026)
RAW_PROVINCES = ROOT / "raw/province-codes/20261102_bps-province-codes-2025-s1.json"
RAW_PAGES = {
    "416": ROOT / "raw/welfare/20261107_bps-adjusted-per-capita-expenditure-by-province-2026.html",
    "192": ROOT / "raw/welfare/20261107_bps-poverty-rate-by-province-2026.html",
}
RAW_API = ROOT / "raw/welfare/20261107_bps-webapi-welfare-by-province.jsonl"

# Output; the metadata JSON is written beside it with a -metadata suffix
OUT_CSV = HERE / "20261108_bps-province-welfare.csv"

KEYS = ["province_code", "indicator", "area", "period"]

# How each BPS table writes its values, read from opening the pages and responses
READ_CONTEXT = {
    "416": {"title": "[Metode Baru] Pengeluaran per Kapita Disesuaikan", "unit": "Ribu Rupiah/Orang/Tahun", "decimals": 0,
            # Province rows are bold and coded PP00; the other rows are regencies and cities, which are not read
            "rows": "bold province rows and INDONESIA", "turvar": {"Tidak ada": ""},
            "turtahun": {"Tahun": "expenditure_per_capita_adjusted"}},
    "192": {"title": "Persentase Penduduk Miskin (P0) Menurut Provinsi dan Daerah", "unit": "Persen", "decimals": 2,
            "rows": "38 provinces and INDONESIA", "turvar": {"Perkotaan": "urban", "Perdesaan": "rural", "Jumlah": "total"},
            "turtahun": {"Semester 1 (Maret)": "poverty_rate_march", "Semester 2 (September)": "poverty_rate_september",
                         "Tahunan": "poverty_rate_annual"},
            "note_text": "Angka Provinsi Papua Barat dan Papua sebelum tahun 2024 merupakan angka provinsi sebelum mengalami pemekaran"},
}

# BPS writes Indonesia as region 9999
NATIONAL_SOURCE_CODE = "9999"

INDICATORS = {
    "expenditure_per_capita_adjusted": {"name": "Pengeluaran per kapita disesuaikan, metode baru (adjusted per capita household expenditure, HDI method)",
                                        "unit": "thousand Rp per person per year, at constant 2012 prices (PPP-adjusted)", "multiplier": 1e3, "base_unit": "Rp per person per year"},
    "poverty_rate_march": {"name": "Persentase penduduk miskin P0, Susenas Maret (poverty headcount, March survey)", "unit": "percent of population", "multiplier": 1},
    "poverty_rate_september": {"name": "Persentase penduduk miskin P0, Susenas September (poverty headcount, September survey)", "unit": "percent of population", "multiplier": 1},
}
AREAS = {"": "not split by area", "urban": "Perkotaan", "rural": "Perdesaan", "total": "Jumlah (urban + rural)"}

# Years each indicator should cover; BPS ran no September survey in 2023 and has not yet published September 2026
YEARS = {
    "expenditure_per_capita_adjusted": range(2020, 2027),
    "poverty_rate_march": range(2020, 2027),
    "poverty_rate_september": [2020, 2021, 2022, 2024, 2025],
}

# Papua split: new BPS codes and the first year with separate values
NEW_PROVINCES = {"92", "95", "96", "97"}
FIRST_SPLIT_YEAR = 2024

# DKI Jakarta has no rural area, so BPS publishes no rural poverty rate for it
NO_RURAL = {"31"}

# Plausibility ranges; a value outside its range is flagged, not dropped
PLAUSIBLE = {
    "poverty_rate": (0, 45),
    "expenditure_change_pct": (-8, 12),
}

URL_PAGES = {
    "416": "https://www.bps.go.id/id/statistics-table/2/NDE2IzI=/-metode-baru--pengeluaran-per-kapita",
    "192": "https://www.bps.go.id/id/statistics-table/2/MTkyIzI=/persentase-penduduk-miskin--maret-2026.html",
}

# Functions

def row(code, indicator, area, period, value, status=""):
    """Return one long row."""
    return {"province_code": code, "indicator": indicator, "area": area, "period": period, "status": status, "value": value}


def read_table(table, lookup, where):
    """Read one BPS table (page or WebAPI response) for one year into long rows of provinces and Indonesia."""
    var = str(table["var"][0]["val"])
    c = READ_CONTEXT[var]
    v = table["var"][0]
    # Check the table still has its title, unit, decimals and column labels
    cleaning.require_text(v["label"], c["title"], where)
    cleaning.require_text(v["unit"], c["unit"], where)
    assert int(v["decimal"]) == c["decimals"], (where, v["decimal"])
    assert {t["label"] for t in table["turvar"]} == set(c["turvar"]), where
    assert {t["label"] for t in table["turtahun"]} <= set(c["turtahun"]), where
    if "note_text" in c:
        cleaning.require_text(cleaning.html_to_text(v["note"]), c["note_text"], where)
    [year] = [str(t["label"]) for t in table["tahun"]]
    if var == "416":
        # Bold rows are provinces and Indonesia; their codes must end in 00 or be 9999
        bold = {str(r["val"]) for r in table["vervar"] if "<b>" in r["label"]}
        assert all(x.endswith("00") or x == NATIONAL_SOURCE_CODE for x in bold), where
    out = []
    for r, tv, th, tt, text in cleaning.bps_api_cells(table):
        source_code = str(r["val"])
        if var == "416" and source_code not in bold:
            continue
        name = cleaning.html_to_text(r["label"])
        code = cleaning.province_code(name, lookup, cleaning.NATIONAL_CODE if source_code == NATIONAL_SOURCE_CODE else source_code[:2])
        indicator = c["turtahun"][tt["label"]]
        value = cleaning.parse_number(text, ".", None, max_decimals=c["decimals"])
        out.append(row(code, indicator, c["turvar"][tv["label"]], year, value))
    info = {"title": v["label"], "unit": v["unit"], "last_update": table.get("last_update"),
            "note": cleaning.html_to_text(v["note"])}
    return out, info


def existing(provinces, year):
    """Return the codes with separate values in a year: provinces (Papua split from 2024) and Indonesia."""
    return [c for c in provinces if year >= FIRST_SPLIT_YEAR or c not in NEW_PROVINCES]


def expected_keys(provinces):
    """Every key the tables should yield; the Papua split, the missing survey rounds and rural Jakarta are the only gaps."""
    keys = set()
    for indicator, years in YEARS.items():
        for year in years:
            for c in existing(provinces, year):
                if indicator == "expenditure_per_capita_adjusted":
                    keys.add((c, indicator, "", str(year)))
                else:
                    keys |= {(c, indicator, a, str(year)) for a in ["urban", "rural", "total"] if not (a == "rural" and c in NO_RURAL)}
    return keys


def plausibility_flags(df):
    """Layer 5: poverty rates and year-on-year changes in expenditure outside their ranges."""
    flags = []
    pov = df[df["indicator"].str.startswith("poverty_rate")]
    flags += cleaning.flag_outside([{"province_code": r.province_code, "indicator": r.indicator, "area": r.area, "period": r.period, "value": r.value}
                                    for r in pov.itertuples()], "poverty_rate", *PLAUSIBLE["poverty_rate"])
    e = df[df["indicator"] == "expenditure_per_capita_adjusted"].sort_values(["province_code", "period"])
    e = e.assign(change=e.groupby("province_code")["value"].pct_change() * 100).dropna(subset=["change"])
    # Changes across the Papua split compare different areas, so they are skipped
    e = e[~(e["province_code"].isin(["91", "94"]) & (e["period"] == str(FIRST_SPLIT_YEAR)))]
    flags += cleaning.flag_outside([{"province_code": r.province_code, "period": r.period, "value": r.change}
                                    for r in e.itertuples()], "expenditure_change_pct", *PLAUSIBLE["expenditure_change_pct"])
    return flags


# Steps

# Read the BPS province list that every region name and code is matched against
provinces, lookup = cleaning.load_bps_provinces(RAW_PROVINCES)

# Read the saved BPS pages (2026)
page_rows, tables = [], {}
for var, path in RAW_PAGES.items():
    text = cleaning.bps_flight_text(path)
    table = cleaning.bps_find_object(text, ["datacontent", "vervar", "turvar", "tahun", "turtahun", "var"])
    out, info = read_table(table, lookup, path.name)
    page_rows += out
    tables[f"page {var}"] = {**info, "url": URL_PAGES[var], "file": str(path.relative_to(ROOT))}

# Read the WebAPI responses (2020-2026), one table and year per line
api_rows = []
for record in cleaning.read_jsonl(RAW_API):
    assert record["response"]["data-availability"] == "available", (record["var"], record["year"])
    out, info = read_table(record["response"], lookup, f"var {record['var']} {record['year']}")
    assert {r["period"] for r in out} == {record["year"]}, (record["var"], record["year"])
    api_rows += out
    tables[f"webapi {record['var']}"] = {**info, "request": record["request"]}

# Layer 4: merge in priority order; every value repeated across sources must match exactly
rows, overlaps = cleaning.merge_sources([("BPS pages 2026", page_rows), ("BPS WebAPI 2020-2026", api_rows)], KEYS)

# Layer 5: plausibility only flags
df = pd.DataFrame(rows)
flags = plausibility_flags(df)

# Describe the dataset
meta = {
    "title": "BPS provincial adjusted per capita expenditure and poverty rate, Indonesia",
    "columns": {
        "province_code": "BPS province code (kode_bps); 00 = Indonesia. Names and Kemendagri codes in 'provinces'.",
        "indicator": "Indicator code; definitions in 'indicators'.",
        "area": "urban, rural or total for poverty rates; empty for expenditure. Names in 'areas'.",
        "period": "YYYY. For poverty rates the survey month is in the indicator code.",
        "status": "BPS revision marker; these tables carry none.",
        "value": "Number in the indicator's unit, as published by BPS.",
    },
    "provinces": provinces,
    "areas": AREAS,
    "indicators": INDICATORS,
    "source_tables": tables,
    "notes": [
        "Papua split: Papua Barat Daya (92), Papua Selatan (95), Papua Tengah (96) and Papua Pegunungan (97) have values from 2024. For 2020-2023, Papua (94) and Papua Barat (91) are the pre-split provinces (BPS table note).",
        "BPS ran no September Susenas poverty round in 2023; September 2026 is not yet published. The 'Tahunan' column of the poverty table is empty for every year.",
        "DKI Jakarta has no rural poverty rate because it has no rural area.",
        "Adjusted per capita expenditure is the HDI expenditure component: real (constant 2012 prices), purchasing-power adjusted. It is not comparable with GRDP per capita in rupiah terms; compare levels across provinces, or ratios.",
        "Expenditure rows for regencies and cities in the same BPS table are not read.",
    ],
    "checks": {
        "passed": ["cross-source"],
        "cross_source_overlaps": overlaps,
        "plausible_ranges": PLAUSIBLE,
        "flags": flags,
    },
}

# Layers 1, 2 and 6: check structure and completeness, then write the CSV and metadata
out = cleaning.write_dataset(
    rows, KEYS,
    allowed={"province_code": provinces, "indicator": list(INDICATORS), "area": list(AREAS)},
    expected=expected_keys(provinces),
    csv_path=OUT_CSV, meta=meta, raw_files=[RAW_PROVINCES, *RAW_PAGES.values(), RAW_API],
    sort_orders={"area": list(AREAS)},
)

# Report what was written
print(f"{OUT_CSV.name}: {len(out)} rows, {len(flags)} plausibility flags, overlaps {overlaps}")
print(out.groupby(["indicator", "area"]).size().to_string())
for f in flags:
    print("  flag:", f)
