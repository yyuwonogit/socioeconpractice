from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

import json
import sys

# Load the shared chart module from tools/ for province display names
sys.path.insert(0, str(ROOT / "tools"))
import charts

import pandas as pd

# Parameters

# Datasets read; analysis scripts read data/ only
DATA = ROOT / "data"
POPULATION = DATA / "20261102_bps-province-grdp-population/20261102_bps-province-grdp-population.csv"
COAL_RESERVES = DATA / "20261116_neraca-coal-resources-reserves-2024/20261116_neraca-coal-resources-reserves-2024.csv"
RUPTL = DATA / "20261116_ruptl-province-plants-grid-2025-2034/20261116_ruptl-province-plants-grid-2025-2034.csv"
RUPTL_META = DATA / "20261116_ruptl-province-plants-grid-2025-2034/20261116_ruptl-province-plants-grid-2025-2034-metadata.json"
FDI = DATA / "20261116_bps-province-foreign-investment/20261116_bps-province-foreign-investment.csv"
HOUSEHOLD_ENERGY = DATA / "20261116_bps-province-household-energy/20261116_bps-province-household-energy.csv"
RE_CAPACITY = DATA / "20261116_province-re-capacity-entered/20261116_province-re-capacity-entered.csv"
WELFARE = DATA / "20261108_bps-province-welfare/20261108_bps-province-welfare.csv"
DEPTH_IPM = DATA / "20261116_bps-province-poverty-depth-ipm/20261116_bps-province-poverty-depth-ipm.csv"
DEPTH_IPM_META = DATA / "20261116_bps-province-poverty-depth-ipm/20261116_bps-province-poverty-depth-ipm-metadata.json"
WORKERS_EDUCATION = DATA / "20261116_bps-province-workers-by-education/20261116_bps-province-workers-by-education.csv"
WORKERS_INDUSTRY = DATA / "20261116_bps-province-workers-by-industry/20261116_bps-province-workers-by-industry.csv"
WAGES = DATA / "20261116_bps-province-wages-by-industry/20261116_bps-province-wages-by-industry.csv"
JKN_ELECTRICITY = DATA / "20261116_bps-province-jkn-electricity-bottom40/20261116_bps-province-jkn-electricity-bottom40.csv"
GRDP_INDUSTRY = DATA / "20261116_bps-province-grdp-by-industry-2021-2025/20261116_bps-province-grdp-by-industry-2021-2025.csv"
PLN = DATA / "20261116_pln-unit-saidi-saifi-2024/20261116_pln-unit-saidi-saifi-2024.csv"
PLN_META = DATA / "20261116_pln-unit-saidi-saifi-2024/20261116_pln-unit-saidi-saifi-2024-metadata.json"
DBH = DATA / "20261116_djpk-province-dbh-2024/20261116_djpk-province-dbh-2024.csv"
APBD = DATA / "20261116_djpk-province-apbd-2024/20261116_djpk-province-apbd-2024.csv"

# Provinces whose APBD export is still to come; the others without one were not downloaded (DBH Minerba under Rp 50 billion)
APBD_PENDING = {}

OUT_VALUES = HERE / "20261116_cross-cutting-indicator-values.csv"
OUT_COLUMNS = HERE / "20261116_cross-cutting-indicator-columns.csv"
OUT_PLN = HERE / "20261116_pln-units-and-provinces.csv"
OUT_DBH = HERE / "20261116_dbh-2024-by-province.csv"
OUT_RUPTL = HERE / "20261116_ruptl-chapters-and-provinces.csv"

# DBH columns shown for CC3, from the DJPK 2024 allocation (thousand rupiah)
DBH_COLUMNS = ["dbh_sda_total", "dbh_minerba", "dbh_oil_gas", "dbh_total"]

# Template sheets, exactly as named in reference/20261116_location-selection-matrix.xlsx
FA1 = "FA1 Coal Mining Exposure Index"
FA2 = "FA2 Coal Power Exposure Index"
FB1 = "FB1 RE Exposure Index"
FB2 = "FB2 Grid-Transm. Exp. Index"
FB3 = "FB3 Crit Min & Bat SC Index"
FB4 = "FB4 Energy Access Index"
CC1 = "CC1 Labor Market Sensit. Index"
CC2 = "CC2 Econ. Depend. & Diver Index"
CC3 = "CC3 Fiscal & Service Sens. Inde"
CC4 = "CC4 Poverty & Resilience Index"
CC5 = "CC5 Adapt. Capacity Defisit Ind"
CC6 = "CC6 Inclusion & Ener. Jus.Index"

# Education levels counted as junior secondary schooling or less
LOW_EDUCATION = ["primary_or_less", "junior_secondary"]

# Template columns not filled in this version, with the reason
NOT_FILLED = [
    {"sheet": CC1, "column": "F", "label": "Labor Market Sensitivity Index", "status": "blank on request: index method to be set by the team"},
    {"sheet": CC2, "column": "E", "label": "Economic Dependence & Diversification Index", "status": "blank on request: index method to be set by the team"},
    {"sheet": CC3, "column": "E", "label": "Fiscal & Service Sensitivity Index", "status": "blank on request: index method to be set by the team"},
    {"sheet": CC4, "column": "E", "label": "Poverty & Resilience Index", "status": "blank on request: index method to be set by the team"},
    {"sheet": CC5, "column": "E", "label": "Adaptive Capacity Deficit Index", "status": "blank on request: index method to be set by the team"},
    {"sheet": CC6, "column": "E", "label": "Inclusion & Energy Justice Index", "status": "blank on request: index method to be set by the team"},
]

# Functions

def read(path):
    """Read a long dataset with codes and periods kept as text."""
    return pd.read_csv(path, dtype={"province_code": str, "area": str, "period": str, "status": str, "sector": str,
                                    "education": str, "unit": str}, keep_default_na=False)


def wide(path, column, **where):
    """Return one indicator and period of a dataset as province rows by sector or education column."""
    df = read(path)
    for k, v in where.items():
        df = df[df[k] == v]
    return df.pivot(index="province_code", columns=column, values="value")


def coal_reserves():
    """FA1 C: total coal reserves (cadangan), million tonnes, status December 2024; 0 where the Neraca records none."""
    df = read(COAL_RESERVES)
    s = df[df["indicator"] == "reserve_total"].set_index("province_code")["value"]
    return s.reindex(list(PROVINCE_NAMES)).fillna(0.0), "Dec 2024", {}


def ruptl_by_province(indicator):
    """A RUPTL chapter value for each province; chapters covering several provinces give blanks, unless the value is 0."""
    meta = json.loads(RUPTL_META.read_text(encoding="utf-8"))
    df = read(RUPTL)
    value = df[df["indicator"] == indicator].set_index("region")["value"]
    out, blank = {}, {}
    for region, r in meta["regions"].items():
        v = value[region]
        for p in r["provinces"]:
            if len(r["provinces"]) == 1 or v == 0:
                out[p] = v
            else:
                blank[p] = f"RUPTL chapter {region} reports {len(r['provinces'])} provinces together ({v:g} for the group; see sheet 'RUPTL by chapter')"
    return pd.Series(out), blank


def coal_capacity():
    """FA2 C: existing on-grid coal (PLTU) capacity, MW, from RUPTL."""
    s, blank = ruptl_by_province("coal_capacity_mw")
    return s, "2024", blank


def coal_capacity_per_resident():
    """FA2 D: coal capacity per resident, watts per person (MW x 1e6 / people)."""
    s, blank = ruptl_by_province("coal_capacity_mw")
    pop = read(POPULATION)
    pop = pop[(pop["indicator"] == "population") & (pop["period"] == "2025")].set_index("province_code")["value"] * 1000
    return (s * 1e6 / pop[s.index]), "2024 / pop 2025", blank


def transmission_plan():
    """FB2 C: planned new transmission 2025-2034, kms, RE Base, from RUPTL."""
    s, blank = ruptl_by_province("transmission_plan_2025_2034_kms")
    return s, "2025-2034", blank


def fdi_value():
    """FB3 D: realised foreign direct investment, million US$, 2023."""
    df = read(FDI)
    return df[(df["indicator"] == "fdi_value") & (df["period"] == "2023")].set_index("province_code")["value"], "2023", {}


def metal_ore_share():
    """FB3 C (proxy): metal ore mining (B3) share of GRDP at current prices, 2025; 0 where BPS shows none."""
    w = wide(GRDP_INDUSTRY, "sector", indicator="grdp_current", period="2025")
    return w["B3"].fillna(0) / w["TOTAL"] * 100, "2025", {}


def electric_lighting():
    """FB4 C: households whose main lighting is electric, 2025."""
    df = read(HOUSEHOLD_ENERGY)
    return df[(df["indicator"] == "electric_lighting") & (df["period"] == "2025")].set_index("province_code")["value"], "2025", {}


def clean_cooking():
    """FB4 D: households cooking mainly with electricity or gas/LPG, 2025."""
    df = read(HOUSEHOLD_ENERGY)
    df = df[(df["indicator"] == "cooking_fuel") & (df["period"] == "2025")]
    w = df.pivot(index="province_code", columns="fuel", values="value")
    return w["electricity"] + w["gas_lpg"], "2025", {}


def re_capacity():
    """FB1 C: operating / planned RE capacity, as entered by the user."""
    df = read(RE_CAPACITY)
    return df.set_index("province_code")["value"], "as entered", {}


def population():
    """FB2 D (inserted column): population, 2025, thousand people."""
    df = read(POPULATION)
    return df[(df["indicator"] == "population") & (df["period"] == "2025")].set_index("province_code")["value"], "2025", {}


def poverty_rate():
    """CC4 C: P0, March, urban and rural combined, 2025."""
    df = read(WELFARE)
    s = df[(df["indicator"] == "poverty_rate_march") & (df["area"] == "total") & (df["period"] == "2025")].set_index("province_code")["value"]
    return s, "2025", {}


def poverty_depth():
    """CC4 D: P1, March, urban and rural combined, 2025."""
    df = read(DEPTH_IPM)
    s = df[(df["indicator"] == "poverty_depth_march") & (df["area"] == "total") & (df["period"] == "2025")].set_index("province_code")["value"]
    return s, "2025", {}


def ipm():
    """CC5 C: Human Development Index, 2025."""
    df = read(DEPTH_IPM)
    return df[(df["indicator"] == "ipm") & (df["period"] == "2025")].set_index("province_code")["value"], "2025", {}


def low_education_share():
    """CC5 D: workers with junior secondary schooling or less, percent of all workers, August 2025."""
    w = wide(WORKERS_EDUCATION, "education", period="2025")
    return w[LOW_EDUCATION].sum(axis=1) / w["TOTAL"] * 100, "Aug 2025", {}


def mining_employment_share():
    """CC1 C: mining and quarrying workers, percent of all workers, August 2025."""
    w = wide(WORKERS_INDUSTRY, "sector", period="2025")
    blank = {c: "BPS publishes no estimate (NA) for mining employment" for c in w.index[w["B"].isna()]}
    return (w["B"] / w["TOTAL"] * 100).dropna(), "Aug 2025", blank


def mining_relative_wage():
    """CC1 D: mining employees' average monthly wage divided by all employees' average in the province, August 2025."""
    w = wide(WAGES, "sector", indicator="wage_monthly_august", period="2025")
    blank = {c: "BPS suppresses the mining wage (relative standard error 50% or more)" for c in w.index[w["B"].isna()]}
    return (w["B"] / w["TOTAL"]).dropna(), "Aug 2025", blank


def jkn():
    """CC1 E: share of the population with JKN health insurance, 2025."""
    df = read(JKN_ELECTRICITY)
    return df[(df["indicator"] == "jkn_coverage") & (df["period"] == "2025")].set_index("province_code")["value"], "2025", {}


def coal_share():
    """CC2 C: coal mining (B2) share of GRDP at current prices, 2025; 0 where BPS shows no coal output."""
    w = wide(GRDP_INDUSTRY, "sector", indicator="grdp_current", period="2025")
    return w["B2"].fillna(0) / w["TOTAL"] * 100, "2025", {}


def coal_growth():
    """CC2 D: average annual real growth (CAGR) of coal mining (B2) at constant 2010 prices, 2021 to 2025, percent."""
    a = wide(GRDP_INDUSTRY, "sector", indicator="grdp_constant", period="2021")["B2"]
    b = wide(GRDP_INDUSTRY, "sector", indicator="grdp_constant", period="2025")["B2"]
    growth = (((b / a) ** (1 / 4) - 1) * 100).dropna()
    blank = {c: "no coal mining output in 2021 or 2025 (BPS shows – or under Rp 0.5 billion), or no 2021 table for the province"
             for c in PROVINCE_NAMES if c not in growth.index}
    return growth, "2021-2025", blank


def saidi():
    """CC6 C: SAIDI 2024 of the PLN unit serving each province (shared within multi-province units)."""
    meta = json.loads(PLN_META.read_text(encoding="utf-8"))
    df = read(PLN)
    value = df[df["indicator"] == "saidi"].set_index("unit")["value"]
    return pd.Series({p: value[x["unit"]] for p, x in meta["province_unit"].items()}), "2024", {}


def dbh_minerba_ratio(denominator):
    """DBH Minerba allocation 2024 divided by a 2024 APBD budget account of the province government, percent."""
    dbh = read(DBH)
    minerba = dbh[dbh["indicator"] == "dbh_minerba"].set_index("province_code")["value"] * 1e3
    apbd = read(APBD)
    base = apbd[apbd["indicator"] == denominator].set_index("province_code")["value"]
    ratio = (minerba[base.index] / base * 100)
    blank = {c: APBD_PENDING.get(c, "APBD not downloaded: DBH Minerba under Rp 50 billion, so the ratio is near zero")
             for c in minerba.index if c not in base.index}
    return ratio, "2024", blank


def dbh_minerba_revenue():
    """CC3 C: DBH Minerba / total revenue (Pendapatan Daerah, APBD murni budget), province government, 2024."""
    return dbh_minerba_ratio("revenue_budget")


def dbh_minerba_pad():
    """CC3 D: DBH Minerba / own-source revenue (PAD, APBD murni budget), province government, 2024."""
    return dbh_minerba_ratio("pad_budget")


def electric_lighting_bottom40():
    """CC6 D: poorest 40% of households with electric lighting, 2019 (latest BPS year)."""
    df = read(JKN_ELECTRICITY)
    s = df[(df["indicator"] == "electric_lighting_bottom40") & (df["period"] == "2019")].set_index("province_code")["value"]
    blank = {c: "BPS stopped this table in 2019, before the province had separate figures" for c in ["92", "95", "96", "97"]}
    return s, "2019", blank


# Each filled column: how its values are made, and how the sheet and Notes describe it
FILLED = [
    {"sheet": FB1, "column": "C", "make": re_capacity,
     "label": "Operating / planned RE capacity (entered by you)", "unit": "MW? (unit and source to confirm)", "short_source": "your entry, 16 Nov 2026",
     "definition": "Values you typed into this column on 16 Nov 2026, kept unchanged. Unit, year and source still to be confirmed.",
     "source": "User entry, kept as received in raw/renewable-energy/20261116_location-selection-matrix-with-re-capacity-entered.xlsx; repo dataset data/20261116_province-re-capacity-entered"},
    {"sheet": FB2, "column": "D", "make": population,
     "label": "Population", "unit": "thousand people", "short_source": "BPS population projection",
     "definition": "Mid-year (June) population of the province, from BPS's Proyeksi Penduduk Indonesia 2020-2050. Put in the template's (TBD) column on request.",
     "source": "BPS, population by province (Proyeksi Penduduk Indonesia 2020-2050); repo dataset data/20261102_bps-province-grdp-population"},
    {"sheet": FB1, "column": "D", "make": population,
     "label": "Population", "unit": "thousand people", "short_source": "BPS population projection",
     "definition": "Mid-year (June) population of the province, from BPS's Proyeksi Penduduk Indonesia 2020-2050. Filled in place of the template's 'Share of Coal Sector in the GRDP' header, on request.",
     "source": "BPS, population by province (Proyeksi Penduduk Indonesia 2020-2050); repo dataset data/20261102_bps-province-grdp-population"},
    {"sheet": FA1, "column": "C", "make": coal_reserves,
     "label": "Coal reserves (cadangan), million tonnes — reserves, not production", "unit": "million tonnes", "short_source": "ESDM Neraca SD & Cadangan, Tabel 33",
     "definition": "Total coal reserves (probable + proven), status December 2024. Reserves are coal in the ground that can be mined economically, not annual production; the Neraca gives production for Indonesia only. 0 = no coal resources recorded in the Neraca for the province. Two printed errors in Tabel 33 are corrected (Aceh measured resources, Papua Barat total resources); reserves are not affected.",
     "source": "Badan Geologi ESDM, Neraca Sumber Daya dan Cadangan Mineral dan Batubara, Tabel 33 (from your screenshot, checked against the table's own totals and the Neraca PDF's Tabel 31); repo dataset data/20261116_neraca-coal-resources-reserves-2024"},
    {"sheet": FA2, "column": "C", "make": coal_capacity,
     "label": "Coal power plant (PLTU) capacity ON-GRID, MW — captive plants NOT included", "unit": "MW", "short_source": "RUPTL 2025-2034",
     "definition": "Installed capacity of existing coal power plants (PLTU, incl. mine-mouth) on the PLN system: PLN, IPP, rented and excess power. Captive plants (e.g. in nickel industrial parks in Sulawesi and Maluku Utara) are NOT included, so those provinces are understated. Kepulauan Riau excludes Batam. Bengkulu shows 0 because RUPTL's table omits PLTU Teluk Sepang (2 x 100 MW).",
     "source": "PLN, RUPTL 2025-2034, Lampiran A-C, existing-plant tables; repo dataset data/20261116_ruptl-province-plants-grid-2025-2034"},
    {"sheet": FA2, "column": "D", "make": coal_capacity_per_resident,
     "label": "On-grid coal capacity per resident, watts per person", "unit": "W per person", "short_source": "RUPTL 2025-2034 & BPS population",
     "definition": "Column C (MW) x 1,000,000 divided by 2025 population (persons). Same limits as column C.",
     "source": "RUPTL 2025-2034 (data/20261116_ruptl-province-plants-grid-2025-2034) and BPS population (data/20261102_bps-province-grdp-population)"},
    {"sheet": FB2, "column": "C", "make": transmission_plan,
     "label": "Planned new transmission lines 2025-2034, kms (RE Base)", "unit": "kms (circuit km)", "short_source": "RUPTL 2025-2034",
     "definition": "Total planned new transmission lines over 2025-2034 in RUPTL's RE Base scenario (Rekapitulasi table, Jumlah). Planned substation capacity (MVA) is in sheet 'RUPTL by chapter'. Some lengths are estimates until routes are fixed (RUPTL footnote).",
     "source": "PLN, RUPTL 2025-2034, Lampiran A-C; repo dataset data/20261116_ruptl-province-plants-grid-2025-2034"},
    {"sheet": FB3, "column": "D", "make": fdi_value,
     "label": "Realised foreign direct investment (PMA), million US$ — all sectors", "unit": "million US$", "short_source": "BPS var 1840 (BKPM)",
     "definition": "Realised foreign direct investment in 2023, all sectors combined (excluding oil and gas, finance and portfolio investment). Not specific to nickel or batteries; domestic investment (PMDN) is not included.",
     "source": "BPS WebAPI var 1840 (Kementerian Investasi/BKPM); repo dataset data/20261116_bps-province-foreign-investment"},
    {"sheet": FA1, "column": "D", "make": coal_share,
     "label": "Coal mining (B2) share of GRDP, %", "unit": "% of GRDP, current prices", "short_source": "BPS PDRB Provinsi 2021-2025",
     "definition": "GRDP of coal and lignite mining (B2) divided by total GRDP, current prices, times 100; same as CC2 C. 0 where BPS shows no coal mining output. 2025 is very preliminary.",
     "source": "BPS, PDRB Provinsi-Provinsi di Indonesia Menurut Lapangan Usaha 2021-2025; repo dataset data/20261116_bps-province-grdp-by-industry-2021-2025"},
    {"sheet": FB3, "column": "C", "make": metal_ore_share,
     "label": "PROXY for nickel/battery-mineral mines: metal-ore mining (B3) share of GRDP, %", "unit": "% of GRDP, current prices", "short_source": "BPS PDRB Provinsi 2021-2025",
     "definition": "Proxy for nickel and battery-mineral mining: GRDP of metal ore mining (B3: nickel, copper, gold, tin, bauxite and others) divided by total GRDP, current prices, times 100. It does not count mines or smelters and mixes battery minerals with copper and gold (e.g. Papua Tengah is copper-gold). 0 where BPS shows none.",
     "source": "BPS, PDRB Provinsi-Provinsi di Indonesia Menurut Lapangan Usaha 2021-2025; repo dataset data/20261116_bps-province-grdp-by-industry-2021-2025"},
    {"sheet": FB4, "column": "C", "make": electric_lighting,
     "label": "PROXY for electrification ratio: households with electric lighting, % (BPS, not the ESDM ratio)", "unit": "% of households", "short_source": "BPS Susenas, var 772",
     "definition": "Share of households whose main lighting source is electricity (PLN or non-PLN), Susenas March. A household-based measure of electrification; ESDM's official electrification ratio is computed differently.",
     "source": "BPS WebAPI var 772; repo dataset data/20261116_bps-province-household-energy"},
    {"sheet": FB4, "column": "D", "make": clean_cooking,
     "label": "Households cooking with electricity or gas/LPG, %", "unit": "% of households", "short_source": "BPS Susenas, var 150",
     "definition": "Share of households whose main cooking fuel is electricity or gas/LPG (clean fuels in the SDG 7.1.2 sense). The rest use kerosene, charcoal, firewood or other fuels, or do not cook.",
     "source": "BPS WebAPI var 150; repo dataset data/20261116_bps-province-household-energy"},
    {"sheet": CC1, "column": "C", "make": mining_employment_share,
     "label": "Mining & quarrying (B) workers, % of all workers", "unit": "% of employed persons", "short_source": "BPS Sakernas, Tabel 112",
     "definition": "Employed persons aged 15+ whose main job is in mining and quarrying (KBLI category B), divided by all employed persons aged 15+, times 100. BPS does not split coal from other mining at province level, so this is the closest available measure of the coal-linked workforce.",
     "source": "BPS, Keadaan Angkatan Kerja di Indonesia Agustus 2025, Tabel 112; repo dataset data/20261116_bps-province-workers-by-industry"},
    {"sheet": CC1, "column": "D", "make": mining_relative_wage,
     "label": "Mining wage ÷ provincial average wage", "unit": "ratio (1 = provincial all-industry average)", "short_source": "BPS Sakernas, var 2475",
     "definition": "Average net monthly wage of employees in mining and quarrying divided by the average net monthly wage of all employees in the same province. Above 1 means mining jobs pay more than the provincial average, so their loss costs more income.",
     "source": "BPS WebAPI var 2475 (Sakernas August); repo dataset data/20261116_bps-province-wages-by-industry"},
    {"sheet": CC1, "column": "E", "make": jkn,
     "label": "Population with JKN health insurance (BPJS Kesehatan), %", "unit": "% of population", "short_source": "BPS Susenas, var 2279",
     "definition": "Share of the population with national health insurance: BPJS PBI (state-paid), BPJS non-PBI or Jamkesda. BPJS Ketenagakerjaan (employment social security) is not included; BPS publishes no provincial table for it.",
     "source": "BPS WebAPI var 2279 (Susenas March); repo dataset data/20261116_bps-province-jkn-electricity-bottom40"},
    {"sheet": CC2, "column": "C", "make": coal_share,
     "label": "Coal mining (B2) share of GRDP, %", "unit": "% of GRDP, current prices", "short_source": "BPS PDRB Provinsi 2021-2025",
     "definition": "GRDP of coal and lignite mining (B2) divided by total GRDP, current prices, times 100. 0 where BPS shows no coal mining output. 2025 values are very preliminary (BPS **).",
     "source": "BPS, PDRB Provinsi-Provinsi di Indonesia Menurut Lapangan Usaha 2021-2025; repo dataset data/20261116_bps-province-grdp-by-industry-2021-2025"},
    {"sheet": CC2, "column": "D", "make": coal_growth,
     "label": "Coal mining (B2) real growth, average per year 2021-2025 (CAGR), %", "unit": "% per year, constant 2010 prices", "short_source": "BPS PDRB Provinsi 2021-2025",
     "definition": "Compound average annual growth of coal and lignite mining GRDP at constant 2010 prices from 2021 to 2025: ((2025 / 2021) ^ (1/4) - 1) x 100. Compares the coal sector with itself, not with total GRDP. Values are rounded to whole Rp billions, so provinces with very small coal output can show large swings (West Kalimantan: Rp 15 billion to Rp 1 billion). 2024 is preliminary and 2025 very preliminary. Quadrant chart with CC2 C: analysis/20261117_cc2-coal-share-growth-quadrant.",
     "source": "BPS, PDRB Provinsi-Provinsi di Indonesia Menurut Lapangan Usaha 2021-2025; repo dataset data/20261116_bps-province-grdp-by-industry-2021-2025"},
    {"sheet": CC3, "column": "C", "make": dbh_minerba_revenue,
     "label": "DBH Minerba ÷ total revenue (Pendapatan Daerah), %", "unit": "% of budgeted revenue", "short_source": "DJPK TKD 2024 & APBD 2024",
     "definition": "2024 DBH Minerba allocation to the province government divided by its 2024 APBD murni revenue budget (Pendapatan Daerah), times 100. Province government only, not its regencies and cities. DBH Minerba covers coal and other minerals together.",
     "source": "DJPK, Rincian Dana Transfer Umum TA 2024 (data/20261116_djpk-province-dbh-2024) and DJPK APBD portal data for 2024: your 16 exports plus your compiled 38-province workbook, which match exactly where they overlap (data/20261116_djpk-province-apbd-2024)"},
    {"sheet": CC3, "column": "D", "make": dbh_minerba_pad,
     "label": "DBH Minerba ÷ own-source revenue (PAD), %", "unit": "% of budgeted PAD", "short_source": "DJPK TKD 2024 & APBD 2024",
     "definition": "2024 DBH Minerba allocation to the province government divided by its 2024 APBD murni own-source revenue budget (PAD), times 100. Above 100 means the mining transfer at risk is larger than everything the province raises itself.",
     "source": "DJPK, Rincian Dana Transfer Umum TA 2024 (data/20261116_djpk-province-dbh-2024) and DJPK APBD portal data for 2024: your 16 exports plus your compiled 38-province workbook, which match exactly where they overlap (data/20261116_djpk-province-apbd-2024)"},
    {"sheet": CC4, "column": "C", "make": poverty_rate,
     "label": "Poverty rate P0, March, %", "unit": "% of population", "short_source": "BPS Susenas, var 192",
     "definition": "Share of the population whose monthly per capita expenditure is below the provincial poverty line, urban and rural combined.",
     "source": "BPS, Susenas March, WebAPI var 192; repo dataset data/20261108_bps-province-welfare"},
    {"sheet": CC4, "column": "D", "make": poverty_depth,
     "label": "Poverty depth index P1, March", "unit": "index", "short_source": "BPS Susenas, var 503",
     "definition": "Average gap between the poor's expenditure and the poverty line, as a percent of the line, with the non-poor counted as zero; urban and rural combined. Higher means deeper poverty.",
     "source": "BPS, Susenas March, WebAPI var 503; repo dataset data/20261116_bps-province-poverty-depth-ipm"},
    {"sheet": CC5, "column": "C", "make": ipm,
     "label": "Human Development Index (IPM)", "unit": "index, 0-100", "short_source": "BPS, var 2207",
     "definition": "Geometric mean of health (life expectancy, UHH), education (expected and mean years of schooling, HLS and RLS) and standard of living (adjusted per capita expenditure). Life expectancy from the SP2020 Long Form. Higher means more capacity, so a deficit index would invert it.",
     "source": "BPS, WebAPI var 2207; repo dataset data/20261116_bps-province-poverty-depth-ipm"},
    {"sheet": CC5, "column": "D", "make": low_education_share,
     "label": "Workers with junior secondary (SMP) or less, %", "unit": "% of employed persons", "short_source": "BPS Sakernas, Tabel 107",
     "definition": "Employed persons aged 15+ whose highest completed education is primary school or less (including no schooling) or junior secondary (SMP), divided by all employed persons aged 15+, times 100.",
     "source": "BPS, Keadaan Angkatan Kerja di Indonesia Agustus 2025, Tabel 107; repo dataset data/20261116_bps-province-workers-by-education"},
    {"sheet": CC6, "column": "C", "make": saidi,
     "label": "SAIDI: outage hours per customer (PLN unit value, ILLUSTRATIVE)", "unit": "hours per customer per year", "short_source": "PLN Statistik 2024, Tabel 16",
     "definition": "System Average Interruption Duration Index of the PLN distribution unit serving the province. PLN reports by unit, not province, so provinces in one unit share its value (see sheet 'CC6 PLN units'). For illustration while the team decides how to regroup.",
     "source": "PLN, Statistik PLN 2024, Tabel 16; repo dataset data/20261116_pln-unit-saidi-saifi-2024"},
    {"sheet": CC6, "column": "D", "make": electric_lighting_bottom40,
     "label": "Poorest 40% of households with electric lighting, %", "unit": "% of households in the bottom 40%", "short_source": "BPS Susenas, var 1575",
     "definition": "Share of households in the bottom 40% of the expenditure distribution whose main lighting is electric (PLN or non-PLN). BPS stopped this table after 2019, so it is old and covers the 34 provinces of that time; Papua and Papua Barat values are for the pre-split areas.",
     "source": "BPS WebAPI var 1575 (Susenas); repo dataset data/20261116_bps-province-jkn-electricity-bottom40"},
]

# Steps

# The 38 provinces and their BPS names (Indonesia, code 00, is not a template row)
meta = json.loads(DEPTH_IPM_META.read_text(encoding="utf-8"))
names = {c: p["name"] for c, p in meta["provinces"].items() if c != "00"}
PROVINCE_NAMES = names
assert len(names) == 38

# Make each filled column: values for the provinces that have one, and a reason for each blank province
values, columns = [], []
for spec in FILLED:
    s, period, blank = spec["make"]()
    s = s[s.index.isin(names)]
    missing = set(names) - set(s.index)
    assert missing == set(blank), (spec["sheet"], spec["column"], missing, set(blank))
    values += [{"sheet": spec["sheet"], "column": spec["column"], "province_code": c, "indicator": spec["make"].__name__,
                "period": period, "value": v} for c, v in s.items()]
    reasons = {}
    for c, why in sorted(blank.items()):
        reasons.setdefault(why, []).append(charts.display_name(names[c]))
    blanks = "; ".join(f"Blank for {', '.join(ps)} ({why})" for why, ps in reasons.items())
    columns.append({"sheet": spec["sheet"], "column": spec["column"], "label": spec["label"], "definition": spec["definition"],
                    "unit": spec["unit"], "period": period, "source": spec["source"], "status": "filled",
                    "header_label": f"Data: {spec['label']} | {spec['unit']} | {period} | {spec['short_source']}",
                    "blank_cells": blanks})

# Describe the columns left empty
columns += [{**c, "definition": "", "unit": "", "period": "", "source": "", "header_label": f"Data: {c['status']}", "blank_cells": ""} for c in NOT_FILLED]

# PLN units for the CC6 illustration: each unit's SAIDI, SAIFI and the provinces it serves
pln_meta = json.loads(PLN_META.read_text(encoding="utf-8"))
pln = read(PLN).pivot(index="unit", columns="indicator", values="value")
units = pd.DataFrame([{"unit": u, "unit_name": x["name"], "saidi": pln.loc[u, "saidi"], "saifi": pln.loc[u, "saifi"],
                       "province_codes": " ".join(x["provinces"]), "provinces": len(x["provinces"]), "aggregate": x["aggregate"]}
                      for u, x in pln_meta["units"].items()])

# DBH allocations by province for the CC3 sheet, in thousand rupiah as published
dbh = read(DBH)
dbh = dbh[dbh["indicator"].isin(DBH_COLUMNS)].pivot(index="province_code", columns="indicator", values="value")[DBH_COLUMNS]
assert len(dbh) == 38

# Write the four tables
pd.DataFrame(values).sort_values(["sheet", "column", "province_code"]).to_csv(OUT_VALUES, index=False, lineterminator="\n", float_format="%.10g")
cols = pd.DataFrame(columns)[["sheet", "column", "label", "definition", "unit", "period", "source", "status", "header_label", "blank_cells"]]
cols.sort_values(["sheet", "column"]).to_csv(OUT_COLUMNS, index=False, lineterminator="\n")
units.to_csv(OUT_PLN, index=False, lineterminator="\n", float_format="%.10g")
dbh.reset_index().to_csv(OUT_DBH, index=False, lineterminator="\n", float_format="%.10g")
ruptl_meta = json.loads(RUPTL_META.read_text(encoding="utf-8"))
ruptl = read(RUPTL).pivot(index="region", columns="indicator", values="value")
pd.DataFrame([{"chapter": c, "province_codes": " ".join(r["provinces"]), **ruptl.loc[c].to_dict()} for c, r in ruptl_meta["regions"].items()]).to_csv(OUT_RUPTL, index=False, lineterminator="\n", float_format="%.10g")
print(f"{OUT_VALUES.name}: {len(values)} values; {OUT_COLUMNS.name}: {len(cols)} columns; {OUT_PLN.name}: {len(units)} units")
print(cols.sort_values(["sheet", "column"])[["sheet", "column", "period", "status", "blank_cells"]].to_string(index=False, max_colwidth=70))
