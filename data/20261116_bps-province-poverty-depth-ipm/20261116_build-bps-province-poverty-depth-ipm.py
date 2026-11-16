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

# Raw inputs: the BPS province list and the WebAPI responses (2020-2026), one table and year per line
RAW_PROVINCES = ROOT / "raw/province-codes/20261102_bps-province-codes-2025-s1.json"
RAW_API = ROOT / "raw/welfare/20261116_bps-webapi-p1-and-ipm-by-province.jsonl"

# Output; the metadata JSON is written beside it with a -metadata suffix
OUT_CSV = HERE / "20261116_bps-province-poverty-depth-ipm.csv"

KEYS = ["province_code", "indicator", "area", "period"]

# How each BPS table writes its values, read from opening the responses: numbers use "." as the
# decimal mark with no thousands separator, every published cell is a number, and Indonesia is 9999
READ_CONTEXT = {
    "503": {"title": "Indeks Kedalaman Kemiskinan (P1) Menurut Provinsi dan Daerah", "unit": "Persen", "decimals": 2,
            "turvar": {"Perkotaan": "urban", "Perdesaan": "rural", "Perkotaan+Perdesaan": "total"},
            "turtahun": {"Semester 1 (Maret)": "poverty_depth_march", "Semester 2 (September)": "poverty_depth_september",
                         "Tahunan": "poverty_depth_annual"},
            "note_text": "Angka Provinsi Papua Barat dan Papua sebelum tahun 2024 merupakan angka provinsi sebelum mengalami pemekaran"},
    "2207": {"title": "[Metode Baru] Indeks Pembangunan Manusia (IPM) menurut Provinsi (Umur Harapan Hidup Hasil Long Form SP2020)",
             "unit": None, "decimals": 2, "turvar": {"Tidak ada": ""}, "turtahun": {"Tahun": "ipm"},
             "note_text": "Umur Harapan Hidup (UHH) menggunakan hasil Long Form Sensus Penduduk 2020 (SP2020)"},
}

# BPS writes Indonesia as region 9999
NATIONAL_SOURCE_CODE = "9999"

INDICATORS = {
    "poverty_depth_march": {"name": "Indeks Kedalaman Kemiskinan P1, Susenas Maret (poverty gap index, March survey)",
                            "unit": "index (percent of the poverty line, averaged over the whole population)", "multiplier": 1,
                            "definition": "Average shortfall of the poor's expenditure below the poverty line, as a percent of the line, with the non-poor counted as zero. Higher means poverty is deeper.",
                            "source": "BPS WebAPI var 503"},
    "poverty_depth_september": {"name": "Indeks Kedalaman Kemiskinan P1, Susenas September (poverty gap index, September survey)",
                                "unit": "index (percent of the poverty line, averaged over the whole population)", "multiplier": 1,
                                "source": "BPS WebAPI var 503"},
    "ipm": {"name": "Indeks Pembangunan Manusia, metode baru, UHH hasil Long Form SP2020 (Human Development Index)",
            "unit": "index, 0-100", "multiplier": 1,
            "definition": "Geometric mean of three dimension indices: health (life expectancy at birth, UHH), education (mean of the expected years of schooling index, HLS, and the mean years of schooling index, RLS) and standard of living (adjusted per capita expenditure).",
            "source": "BPS WebAPI var 2207"},
}
AREAS = {"": "not split by area", "urban": "Perkotaan", "rural": "Perdesaan", "total": "Perkotaan+Perdesaan (urban + rural)"}

# Years each indicator should cover; BPS ran no September survey in 2023 and has not yet published September 2026
YEARS = {
    "poverty_depth_march": range(2020, 2027),
    "poverty_depth_september": [2020, 2021, 2022, 2024, 2025],
    "ipm": range(2020, 2027),
}

# Papua split: new BPS codes and the first year with separate values in each table
NEW_PROVINCES = {"92", "95", "96", "97"}
FIRST_SPLIT_YEAR = {"poverty_depth_march": 2024, "poverty_depth_september": 2024, "ipm": 2022}

# DKI Jakarta has no rural area, so BPS publishes no rural poverty figure for it
NO_RURAL = {"31"}

# Plausibility ranges; a value outside its range is flagged, not dropped
PLAUSIBLE = {
    "poverty_depth": (0, 10),
    "ipm": (55, 85),
    "ipm_change": (-1.5, 2.5),
}

# Functions

def row(code, indicator, area, period, value, status=""):
    """Return one long row."""
    return {"province_code": code, "indicator": indicator, "area": area, "period": period, "status": status, "value": value}


def read_table(table, lookup, where):
    """Read one WebAPI response (one table, one year) into long rows of provinces and Indonesia."""
    var = str(table["var"][0]["val"])
    c = READ_CONTEXT[var]
    v = table["var"][0]
    # Check the table still has its title, unit, decimals, column labels and note
    cleaning.require_text(v["label"], c["title"], where)
    assert v["unit"] == c["unit"], (where, v["unit"])
    assert int(v["decimal"]) == c["decimals"], (where, v["decimal"])
    assert {t["label"] for t in table["turvar"]} == set(c["turvar"]), where
    assert {t["label"] for t in table["turtahun"]} <= set(c["turtahun"]), where
    cleaning.require_text(cleaning.html_to_text(v["note"]), c["note_text"], where)
    [year] = [str(t["label"]) for t in table["tahun"]]
    out = []
    for r, tv, th, tt, text in cleaning.bps_api_cells(table):
        source_code = str(r["val"])
        name = cleaning.html_to_text(r["label"])
        code = cleaning.province_code(name, lookup, cleaning.NATIONAL_CODE if source_code == NATIONAL_SOURCE_CODE else source_code[:2])
        value = cleaning.parse_number(text, ".", None, max_decimals=c["decimals"])
        out.append(row(code, c["turtahun"][tt["label"]], c["turvar"][tv["label"]], year, value))
    info = {"title": v["label"], "unit": v["unit"], "last_update": table.get("last_update"),
            "note": cleaning.html_to_text(v["note"])}
    return out, info


def existing(provinces, indicator, year):
    """Return the codes with separate values in a year: provinces (Papua split by table) and Indonesia."""
    return [c for c in provinces if year >= FIRST_SPLIT_YEAR[indicator] or c not in NEW_PROVINCES]


def expected_keys(provinces):
    """Every key the tables should yield; the Papua split, the missing survey rounds and rural Jakarta are the only gaps."""
    keys = set()
    for indicator, years in YEARS.items():
        for year in years:
            for c in existing(provinces, indicator, year):
                if indicator == "ipm":
                    keys.add((c, indicator, "", str(year)))
                else:
                    keys |= {(c, indicator, a, str(year)) for a in ["urban", "rural", "total"] if not (a == "rural" and c in NO_RURAL)}
    return keys


def plausibility_flags(df):
    """Layer 5: P1 and IPM levels, and year-on-year IPM changes, outside their ranges."""
    flags = []
    p1 = df[df["indicator"].str.startswith("poverty_depth")]
    flags += cleaning.flag_outside([{"province_code": r.province_code, "indicator": r.indicator, "area": r.area, "period": r.period, "value": r.value}
                                    for r in p1.itertuples()], "poverty_depth", *PLAUSIBLE["poverty_depth"])
    ipm = df[df["indicator"] == "ipm"].sort_values(["province_code", "period"])
    flags += cleaning.flag_outside([{"province_code": r.province_code, "period": r.period, "value": r.value}
                                    for r in ipm.itertuples()], "ipm", *PLAUSIBLE["ipm"])
    ipm = ipm.assign(change=ipm.groupby("province_code")["value"].diff()).dropna(subset=["change"])
    # Changes across the Papua split compare different areas, so they are skipped
    ipm = ipm[~(ipm["province_code"].isin(["91", "94"]) & (ipm["period"] == str(FIRST_SPLIT_YEAR["ipm"])))]
    flags += cleaning.flag_outside([{"province_code": r.province_code, "period": r.period, "value": r.change}
                                    for r in ipm.itertuples()], "ipm_change", *PLAUSIBLE["ipm_change"])
    return flags


# Steps

# Read the BPS province list that every region name and code is matched against
provinces, lookup = cleaning.load_bps_provinces(RAW_PROVINCES)

# Read the WebAPI responses, one table and year per line
rows, tables = [], {}
for record in cleaning.read_jsonl(RAW_API):
    assert record["response"]["data-availability"] == "available", (record["var"], record["year"])
    out, info = read_table(record["response"], lookup, f"var {record['var']} {record['year']}")
    assert {r["period"] for r in out} == {record["year"]}, (record["var"], record["year"])
    rows += out
    tables[f"webapi {record['var']}"] = {**info, "request": record["request"]}

# BPS leaves the annual P1 column empty; stop if it starts filling it, so the indicator gets defined first
assert not any(r["indicator"] == "poverty_depth_annual" for r in rows), "annual P1 now published"

# Layer 5: plausibility only flags
df = pd.DataFrame(rows)
flags = plausibility_flags(df)

# Describe the dataset
meta = {
    "title": "BPS provincial poverty depth index (P1) and Human Development Index (IPM), Indonesia, 2020-2026",
    "columns": {
        "province_code": "BPS province code (kode_bps); 00 = Indonesia. Names and Kemendagri codes in 'provinces'.",
        "indicator": "Indicator code; definitions in 'indicators'.",
        "area": "urban, rural or total for P1; empty for IPM. Names in 'areas'.",
        "period": "YYYY. For P1 the survey month is in the indicator code.",
        "status": "BPS revision marker; these tables carry none.",
        "value": "Number in the indicator's unit, as published by BPS.",
    },
    "provinces": provinces,
    "areas": AREAS,
    "indicators": INDICATORS,
    "source_tables": tables,
    "notes": [
        "P1 Papua split: Papua Barat Daya (92), Papua Selatan (95), Papua Tengah (96) and Papua Pegunungan (97) have values from 2024; for 2020-2023, Papua (94) and Papua Barat (91) are the pre-split provinces (BPS table note).",
        "IPM Papua split: the four new provinces have IPM values from 2022, so IPM for Papua (94) and Papua Barat (91) covers the post-split areas from 2022 and the pre-split areas in 2020-2021.",
        "BPS ran no September Susenas poverty round in 2023; September 2026 is not yet published. The 'Tahunan' column of the P1 table is empty for every year.",
        "DKI Jakarta has no rural P1 because it has no rural area.",
        "IPM is var 2207, which uses life expectancy from the SP2020 Long Form and is the series BPS currently updates. The older IPM table (var 494) stops at 2024 and is not read; its values differ because of the life-expectancy basis.",
    ],
    "checks": {
        "passed": [],
        "plausible_ranges": PLAUSIBLE,
        "flags": flags,
    },
}

# Layers 1, 2 and 6: check structure and completeness, then write the CSV and metadata
out = cleaning.write_dataset(
    rows, KEYS,
    allowed={"province_code": provinces, "indicator": list(INDICATORS), "area": list(AREAS)},
    expected=expected_keys(provinces),
    csv_path=OUT_CSV, meta=meta, raw_files=[RAW_PROVINCES, RAW_API],
    sort_orders={"area": list(AREAS)},
)

# Report what was written
print(f"{OUT_CSV.name}: {len(out)} rows, {len(flags)} plausibility flags")
print(out.groupby(["indicator", "area"]).size().to_string())
for f in flags:
    print("  flag:", f)
