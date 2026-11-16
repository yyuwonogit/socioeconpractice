from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

import json

import pandas as pd

# Parameters

# Datasets read; analysis scripts read data/ only
WELFARE = ROOT / "data/20261108_bps-province-welfare/20261108_bps-province-welfare.csv"
DEPTH_IPM = ROOT / "data/20261116_bps-province-poverty-depth-ipm/20261116_bps-province-poverty-depth-ipm.csv"
DEPTH_IPM_META = ROOT / "data/20261116_bps-province-poverty-depth-ipm/20261116_bps-province-poverty-depth-ipm-metadata.json"

OUT_VALUES = HERE / "20261116_cross-cutting-indicator-values.csv"
OUT_COLUMNS = HERE / "20261116_cross-cutting-indicator-columns.csv"

# Use this year where every province has a value, otherwise the latest such year
REFERENCE_YEAR = "2025"

# Template sheets, exactly as named in reference/20261116_location-selection-matrix.xlsx
CC3 = "CC3 Fiscal & Service Sens. Inde"
CC4 = "CC4 Poverty & Resilience Index"
CC5 = "CC5 Adapt. Capacity Defisit Ind"
CC6 = "CC6 Inclusion & Ener. Jus.Index"

# Each filled template column: the dataset, indicator and area it takes, and how to describe it
FILLED = [
    {"sheet": CC4, "column": "C", "dataset": WELFARE, "indicator": "poverty_rate_march", "area": "total",
     "label": "Poverty headcount rate P0, March (Persentase Penduduk Miskin)",
     "definition": "Share of the population whose monthly per capita expenditure is below the provincial poverty line, urban and rural combined.",
     "unit": "percent of population", "source": "BPS, Susenas March, WebAPI var 192; repo dataset data/20261108_bps-province-welfare"},
    {"sheet": CC4, "column": "D", "dataset": DEPTH_IPM, "indicator": "poverty_depth_march", "area": "total",
     "label": "Poverty depth index P1, March (Indeks Kedalaman Kemiskinan)",
     "definition": "Average gap between the poor's expenditure and the poverty line, as a percent of the line, with the non-poor counted as zero; urban and rural combined. Higher means deeper poverty.",
     "unit": "index", "source": "BPS, Susenas March, WebAPI var 503; repo dataset data/20261116_bps-province-poverty-depth-ipm"},
    {"sheet": CC5, "column": "C", "dataset": DEPTH_IPM, "indicator": "ipm", "area": "",
     "label": "Human Development Index, IPM (Indeks Pembangunan Manusia)",
     "definition": "Geometric mean of health (life expectancy, UHH), education (expected and mean years of schooling, HLS and RLS) and standard of living (adjusted per capita expenditure). Life expectancy from the SP2020 Long Form. Higher means more capacity, so a deficit index would invert it.",
     "unit": "index, 0-100", "source": "BPS, WebAPI var 2207; repo dataset data/20261116_bps-province-poverty-depth-ipm"},
]

# Template columns not filled in this version, with the reason
NOT_FILLED = [
    {"sheet": CC3, "column": "C", "label": "DBH Minerba / total regional revenue (Pendapatan Daerah), province government",
     "status": "pending: DJPK 2024 DBH allocation is filed (raw/fiscal); 2024 APBD revenue still to be fetched from DJPK"},
    {"sheet": CC3, "column": "D", "label": "DBH Minerba / own-source revenue (PAD), province government",
     "status": "pending: needs 2024 APBD PAD from DJPK"},
    {"sheet": CC3, "column": "E", "label": "Fiscal & Service Sensitivity Index", "status": "blank on request: index method to be set by the team"},
    {"sheet": CC4, "column": "E", "label": "Poverty & Resilience Index", "status": "blank on request: index method to be set by the team"},
    {"sheet": CC5, "column": "D", "label": "Share of workers with junior secondary schooling (SMP) or less",
     "status": "pending: BPS Keadaan Angkatan Kerja Agustus 2025 publication still to be fetched"},
    {"sheet": CC5, "column": "E", "label": "Adaptive Capacity Deficit Index", "status": "blank on request: index method to be set by the team"},
    {"sheet": CC6, "column": "C", "label": "Electricity reliability", "status": "blank on request: indicator to be set by the team"},
    {"sheet": CC6, "column": "D", "label": "TBD", "status": "blank on request: indicator to be set by the team"},
    {"sheet": CC6, "column": "E", "label": "Inclusion & Energy Justice Index", "status": "blank on request: index method to be set by the team"},
]

# Functions

def read(path):
    """Read a long dataset with codes and periods kept as text."""
    return pd.read_csv(path, dtype={"province_code": str, "area": str, "period": str, "status": str}, keep_default_na=False)


def pick_year(df, provinces):
    """Return REFERENCE_YEAR if every province has a value in it, otherwise the latest year where all do."""
    complete = sorted(p for p, g in df.groupby("period") if set(g["province_code"]) >= provinces)
    if not complete:
        raise ValueError("no year covers every province")
    return REFERENCE_YEAR if REFERENCE_YEAR in complete else complete[-1]

# Steps

# The 38 provinces (Indonesia, code 00, is not a template row)
provinces = set(json.loads(DEPTH_IPM_META.read_text(encoding="utf-8"))["provinces"]) - {"00"}
assert len(provinces) == 38, len(provinces)

# Take each filled column's values for its year, one row per province
values, columns = [], []
for spec in FILLED:
    df = read(spec["dataset"])
    df = df[(df["indicator"] == spec["indicator"]) & (df["area"] == spec["area"]) & df["province_code"].isin(provinces)]
    year = pick_year(df, provinces)
    df = df[df["period"] == year]
    assert set(df["province_code"]) == provinces and len(df) == 38, (spec["sheet"], spec["column"])
    values += [{"sheet": spec["sheet"], "column": spec["column"], "province_code": r.province_code, "indicator": spec["indicator"],
                "period": year, "value": r.value} for r in df.itertuples()]
    columns.append({"sheet": spec["sheet"], "column": spec["column"], "label": spec["label"], "definition": spec["definition"],
                    "unit": spec["unit"], "period": year, "source": spec["source"], "status": "filled"})

# Describe the columns left empty
columns += [{**c, "definition": "", "unit": "", "period": "", "source": ""} for c in NOT_FILLED]

# Write both tables
pd.DataFrame(values).sort_values(["sheet", "column", "province_code"]).to_csv(OUT_VALUES, index=False, lineterminator="\n", float_format="%.10g")
cols = pd.DataFrame(columns)[["sheet", "column", "label", "definition", "unit", "period", "source", "status"]]
cols.sort_values(["sheet", "column"]).to_csv(OUT_COLUMNS, index=False, lineterminator="\n")
print(f"{OUT_VALUES.name}: {len(values)} values; {OUT_COLUMNS.name}: {len(cols)} columns")
print(cols[["sheet", "column", "period", "status"]].to_string(index=False))
