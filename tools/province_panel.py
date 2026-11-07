"""The harmonised province panel and its estimators, for every analysis script in analysis/ that uses the panel.

An analysis script adds tools/ to sys.path and imports this module, as it imports charts.py:

    sys.path.insert(0, str(ROOT / "tools"))
    import province_panel

build() reads the ten datasets the panel draws on from data/, runs every check, and returns the panel, one row per
unit-year from 2010 to 2025, as a PanelBuild with what was read and derived on the way. A unit is a province on fixed
borders, or a province split inside those years kept on its pre-split area until the last dataset reports the new
provinces apart. The module also holds the panel's parameters, the functions that read the datasets and rebuild each
series on the units' borders, and the estimators the tests run: two-way fixed effects with standard errors clustered
by unit, and Spearman (or partial rank) correlations of unit averages and of long differences. It reads data/ only and
writes nothing.
"""

from dataclasses import dataclass
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

# Province display names come from the shared chart module, which sits beside this one in tools/
import charts

# Locate the repository root, one level above tools/
ROOT = Path(__file__).resolve().parents[1]

# The ten datasets read, each a long CSV in the shared format beside its metadata in data/<name>/
DATASETS = {
    # GRDP and GRDP per capita at current and constant 2010 prices, BPS WebAPI vars 286 and 288
    "grdp": "20261103_bps-province-grdp-2010-2025",
    # GRDP by the 17 KBLI categories and TOTAL at current and constant 2010 prices, vars 2267 and 2268
    "industry": "20261103_bps-province-grdp-by-industry-2010-2025",
    # Gini ratio of household spending per capita by area, Susenas March and September rounds, var 98
    "gini": "20261103_bps-province-gini",
    # GRDP by the 17 categories, their sub-categories and items (62 sectors) at current and constant 2010 prices,
    # BPS SIMDASI yearbook tables 13.1.1 and 13.1.2
    "detailed": "20261103_bps-province-grdp-detailed-industry-2010-2025",
    # GRDP by expenditure at current prices: household consumption (PKRT), the five other components and PDRB, var 534
    "expenditure": "20261104_bps-province-grdp-by-expenditure-2010-2025",
    # Informal share of employment (var 2153, 2018-2025) and average hourly wage (var 1172, 2015-2025), Sakernas, yearly
    "work": "20261104_bps-province-informal-work-and-hourly-wage",
    # Provincial minimum wage (UMP), BPS var 220 to 2020 and Kemnaker for 2017 and 2021-2025
    "minimum_wage": "20261104_bps-kemnaker-province-minimum-wage",
    # Employed persons by status in the main job, Sakernas Februari and Agustus rounds, var 2335
    "employment": "20261104_bps-province-employment-by-status",
    # Average net monthly wage of employees, Sakernas Agustus round, BPS static tables and var 583
    "monthly_wage": "20261104_bps-province-monthly-wage",
    # School participation rate (APS) by age group, Susenas, var 2211
    "school": "20261104_bps-province-school-participation",
}

# Unit of each indicator read, as its metadata states it; a dataset whose unit changes stops the script
UNITS = {
    "grdp": {"grdp_current": "Rp billion (Milyar Rupiah)", "grdp_constant_2010": "Rp billion (Milyar Rupiah)",
             "grdp_per_capita_current": "Rp thousand per person (Ribu Rupiah)",
             "grdp_per_capita_constant_2010": "Rp thousand per person (Ribu Rupiah)"},
    "industry": {"grdp_current": "Rp billion (Milyar Rupiah)", "grdp_constant_2010": "Rp billion (Milyar Rupiah)"},
    "gini": {"gini_ratio": "ratio, no unit (Tidak Ada Satuan)"},
    "detailed": {"grdp_current": "Rp billion (miliar rupiah)", "grdp_constant_2010": "Rp billion (miliar rupiah)"},
    "expenditure": {"grdp_current": "Rp billion (Milyar Rupiah)"},
    "work": {"informal_employment_share": "percent of employment", "hourly_wage": "Rupiah per hour (Rupiah/Jam)"},
    "minimum_wage": {"minimum_wage": "rupiah per month (BPS unit 'Rupiah'; Kemnaker '(Rp)', and 'upah bulanan' in its "
                                     "definition)"},
    "employment": {"employed_persons": "persons (Orang)"},
    "monthly_wage": {"employee_net_wage_month": "rupiah per employee per month, current prices"},
    "school": {"school_participation_rate": "percent of the age group"},
}

# Panel years: 2010, the first year of the 2010-base GRDP series, which every dataset of T1 and T3 covers, to 2025, the
# last year of GRDP
FIRST_YEAR, LAST_YEAR = 2010, 2025
YEARS = list(range(FIRST_YEAR, LAST_YEAR + 1))
# BPS's national row, which is not a panel unit
NATIONAL = "00"

# Gini comes from the March Susenas round (BPS Semester 1, periods YYYYS1); GRDP and the labour series are yearly.
# T5's employee counts and monthly wages come from the Agustus Sakernas round (periods YYYYS2), the one round both hold
MARCH = "S1"
AUGUST = "S2"
# DKI Jakarta has no rural area, so BPS publishes no rural Gini ratio for it
NO_RURAL = ["31"]

# Provinces split inside the panel years: the parent's BPS code and the codes of the provinces carved out of it.
# Kalimantan Utara came out of Kalimantan Timur; Papua Barat Daya out of Papua Barat; Papua Selatan, Papua Tengah and
# Papua Pegunungan out of Papua
SPLITS = {"64": ["65"], "91": ["92"], "94": ["95", "96", "97"]}
# First year each dataset reports the carved-out provinces on their own; before it the parent's code covers the
# pre-split area. Each is checked against the rows the dataset holds
SEPARATE_FROM = {
    # Vars 286 and 288: Kalimantan Utara from 2013, the new Papua provinces from 2023
    "grdp": {"64": 2013, "91": 2023, "94": 2023},
    # Vars 2267 and 2268: Kalimantan Utara from 2010, their first year, the new Papua provinces from 2024
    "industry": {"64": 2010, "91": 2024, "94": 2024},
    # The Gini table: Kalimantan Utara from 2015 (March 2015), the new Papua provinces from 2024 (March 2024)
    "gini": {"64": 2015, "91": 2024, "94": 2024},
    # The yearbook tables: 64 leaves Kalimantan Utara out in every year, and the new Papua provinces have tables from
    # 2023, when 91 and 94 cover the post-split areas
    "detailed": {"64": 2010, "91": 2023, "94": 2023},
    # Var 534: Kalimantan Utara from 2010, its first year, the new Papua provinces from 2024
    "expenditure": {"64": 2010, "91": 2024, "94": 2024},
}
# Datasets whose values add across provinces (Rp billion), so a pre-split area can be rebuilt from its parts. The
# others hold rates and per capita values, which cannot be added, so the panel units follow their borders: a
# province-year enters only on borders every series describes
ADDITIVE = ["grdp", "industry", "detailed", "expenditure"]
# First year each border province has a yearbook table at current prices, as the detailed dataset's coverage states
# and checked against its rows: Kalimantan Utara (65) has tables from 2014, so the pre-split Kalimantan Timur has
# detail in 2014 only; 91 and 94 from 2015; the new Papua provinces from 2023
DETAILED_FIRST_YEARS = {"64": 2010, "65": 2014, "91": 2015, "92": 2023, "94": 2015, "95": 2023, "96": 2023,
                        "97": 2023}
# Names of the pre-split areas as panel units
PRE_SPLIT_NAMES = {"64": "Kalimantan Timur (pre-split)", "91": "Papua Barat (pre-split)", "94": "Papua (pre-split)"}
# Each carved-out province's parent
PARENT_OF = {c: p for p, kids in SPLITS.items() for c in kids}
# Each unit splits in the year the last dataset of T1 and T3 reports its new provinces apart: the Gini table. T2's
# labour datasets, read only from SHARP_FIRST_YEAR, are checked against these borders by labour_series
UNIT_SPLIT = {p: max(SEPARATE_FROM[k][p] for k in SEPARATE_FROM) for p in SPLITS}

# var 286 GRDP and the industry TOTAL (vars 2267 and 2268) must agree on every unit-year within 0.05 Rp billion, five
# rounding steps of 0.01, at both prices. This catches a unit rebuilt on the wrong borders. The one exception is BPS's
# own gap for pre-split Papua Barat in 2023, industry minus var 286, which the 2010-2025 build declares; it must hold
# to the cent
BORDER_TOL = 0.05
BORDER_GAPS = {("91+92", 2023, "grdp_current"): -5.10, ("91+92", 2023, "grdp_constant_2010"): -11.00}
# The population implied by current and by constant prices (GRDP / GRDP per capita) must agree within this relative
# gap: BPS divides both by one population, and per capita has 2 decimals in Rp thousand
POP_TOL = 1e-5
# The detailed tables rebuilt on each unit's borders must match the other datasets within this gap per yearbook table
# summed (Rp billion): TOTAL against var 286 GRDP, and B1-B4 against the industry B (vars 2267 and 2268). Rounding
# leaves gaps of a few hundredths, the largest in the 2014 tables BPS rounded to 0.1 before printing, while a unit on
# the wrong borders misses by thousands
DETAILED_TOL = 0.1

# T2's labour series, yearly, read only in the years of its samples (from SHARP_FIRST_YEAR): each panel column with
# its dataset and indicator. They hold rates and per-person values, which cannot be added, so a unit takes its own
# code's value, and a pre-split unit its parent's while the dataset still reports the pre-split area there;
# labour_series stops if a dataset reports a unit's provinces on other borders
LABOUR = {
    "informal_share_pct": ("work", "informal_employment_share"),
    "hourly_wage_rp": ("work", "hourly_wage"),
    "minimum_wage_rp": ("minimum_wage", "minimum_wage"),
}
# Unit-years of T2's years without a labour value, each with its reason from the dataset's metadata; any other gap
# stops the script. The informal share starts in 2018 (INFORMAL_FIRST_YEAR), so its earlier years are absent for every
# unit and are not listed
LABOUR_GAPS = {
    ("minimum_wage_rp", code, 2016): "BPS var 220 has no 2016 value for the province and Kemnaker dataset 36 prints '-'"
    for code in ["33", "34", "35"]
}
# T2 tests the informal share in percentage points and each wage in logs, so that a slope reads as a proportional change
T2_OUTCOMES = ["informal_share_pct", "ln_hourly_wage", "ln_minimum_wage"]
# The first year of the informal share (BPS var 2153), checked against its rows. T2 asks whether informal work is part
# of why extraction lowers the household share by rerunning T1's within-province test from this year with and without
# the informal share held equal, on the same unit-years
INFORMAL_FIRST_YEAR = 2018

# T1, first definition of the extractive sectors: B (mining and quarrying) only, kept beside the sharpened one below
EXTRACTIVE_SECTORS = ["B"]
EXTRACTIVE_NAME = "mining and quarrying"
# The sharpened extractive definition (the user's): industries that extract material intensively from land, raw
# production plus first processing, as a share of GRDP at current prices. Each group lists its sectors of the detailed
# dataset with the BPS name each must carry in its metadata; an en-dash cell (none or zero) counts as 0
EXTRACTIVE_GROUPS = {
    "fossil": {
        # B1, oil, gas and geothermal extraction
        "B1": "Pertambangan Minyak, Gas, dan Panas Bumi",
        # B2, coal and lignite mining
        "B2": "Pertambangan Batubara dan Lignit",
        # C1, coal products and oil and gas refining, LNG included
        "C1": "Industri Batubara dan Pengilangan Migas",
    },
    "metals": {
        # B3, metal ore mining
        "B3": "Pertambangan Bijih Logam",
        # C11, basic metals: the smelters
        "C11": "Industri Logam Dasar",
    },
    "plantation": {
        # A1c, estate crops: palm oil, rubber, coffee, cocoa
        "A1c": "Tanaman Perkebunan",
        # C2, food and beverage manufacturing, which holds the palm oil mills; counted only in unit-years where A1c is
        # at least ESTATE_MIN_SHARE of GRDP
        "C2": "Industri Makanan dan Minuman",
    },
    "forest": {
        # A2, forestry and logging
        "A2": "Kehutanan dan Penebangan Kayu",
        # C6, wood, cork, bamboo and rattan products
        "C6": "Industri Kayu, Barang dari Kayu dan Gabus; dan Barang Anyaman dari Bambu, Rotan, dan Sejenisnya",
        # C7, paper and pulp, with printing and recorded media in the same BPS sector
        "C7": "Industri Kertas dan Barang dari Kertas; Percetakan dan Reproduksi Media Rekaman",
    },
    "quarrying": {
        # B4, other mining and quarrying: stone, sand, clay
        "B4": "Pertambangan dan Penggalian Lainnya",
        # C10, non-metallic mineral products, cement included
        "C10": "Industri Barang Galian bukan Logam",
    },
}
# The plantation group's food and beverage sector (C2) enters only where estate crops (A1c) are at least this share
# of the unit-year's GRDP, in percent; on a merged unit the share is that of the merged area
MILLS_SECTOR, ESTATE_SECTOR, ESTATE_MIN_SHARE = "C2", "A1c", 10
SHARP_NAME = "fossil, metals, plantation, forest, quarrying"
# Tests on the sharpened share use the years from 2015, the first year every panel unit has it: in 2014 only 17 of
# the 34 longer units have it, and from 2015 every long difference starts in the same year
SHARP_FIRST_YEAR = 2015
# T1's outcome, BPS's household consumption (PKRT) as a share of GRDP on the expenditure side (%) = PKRT / PDRB x 100,
# both from var 534 at current prices and summed over each unit's area; for a single province this is the share BPS
# publishes as var 542, within 0.006 points
# T4's outcomes, the other five expenditure components as shares of the same GRDP, computed the same way: non-profits'
# consumption (PKLNPRT), government consumption (PKP), gross fixed capital formation (PMTB), change in inventories (PI)
# and net exports to other provinces and abroad (NETEKSPOR). The six shares add to 100, so in one sample and design the
# five components' slopes on extraction add to minus T1's slope: T4 shows where the household share's loss goes
T4_COMPONENTS = {"PKLNPRT": "non-profits' consumption", "PKP": "government consumption", "PMTB": "investment (PMTB)",
                 "PI": "change in inventories", "NETEKSPOR": "net exports"}
EXPENDITURE_COMPONENTS = ["PKRT", *T4_COMPONENTS, "TOTAL"]
T4_OUTCOMES = [f"{code.lower()}_share_pct" for code in T4_COMPONENTS]
# The six shares add to 100 within six half-units of their last decimal (DERIVED_DECIMALS), plus the gap BPS's own
# rounding leaves between the six published components and PDRB (within 0.035 Rp billion, which the expenditure build
# checks), as a share of each row's PDRB
SHARE_SUM_TOL = 6 * 0.5 * 10 ** -6

# T5's series, from the Agustus Sakernas round, from WAGE_FIRST_YEAR, the first year of the employee counts (BPS var
# 2335): each panel column with its dataset and the key columns that pick its rows. Both datasets report the new Papua
# provinces apart from 2024, the year the panel units split, so each unit takes its own code's value (labour_series)
T5_SERIES = {
    "employees_persons": ("employment", {"indicator": "employed_persons", "work_status": "employee"}),
    "employed_persons": ("employment", {"indicator": "employed_persons", "work_status": "TOTAL"}),
    "employee_wage_month_rp": ("monthly_wage", {"indicator": "employee_net_wage_month"}),
}
WAGE_FIRST_YEAR = 2017
# T5's outcome, the employee wage bill as a share of GRDP (%) = employees x average net monthly wage x 12 / GRDP at
# current prices (var 286, Rp billion x 10^9) x 100: what a province's employees take home in a year from its output,
# at the Agustus count and wage. The wage covers employees only (buruh/karyawan/pegawai), not casual or own-account work
MONTHS, RP_PER_BN = 12, 1e9
# T5 then splits the wage share in logs into three parts, so that their slopes on extraction add to its slope:
# ln(wage share) = ln(employee share of employment) + ln(monthly wage) - ln(GRDP per worker, Rp thousand) + ln(12/1000).
# A lower wage share can come from fewer employees among workers, lower wages, or more output per worker than wages
# follow. Each part with its sign in the sum, and the gap the saved values' rounding may leave in the identity
T5_PARTS = {"ln_employee_share": +1, "ln_employee_wage": +1, "ln_grdp_per_worker": -1}
T5_SPLIT_TOL = 1e-5
# T6's outcomes, BPS's school participation rate (APS, %) at ages 16-18 (senior secondary) and 19-23 (higher
# education), yearly; rates are read on each unit's own borders (labour_series)
T6_SERIES = {"aps_16_18_pct": "16-18", "aps_19_23_pct": "19-23"}

# Decimals of each derived panel column, kept in the CSV and used by the tests, so the tests run on the saved values
DERIVED_DECIMALS = 6

# Two-way fixed effects: unit and year effects removed by alternating demeaning (by unit, then by year) until no value
# moves more than DEMEAN_TOL; the slope must then equal the dummy-variable OLS slope within LSDV_TOL (relative)
DEMEAN_TOL, DEMEAN_MAX_ITER, LSDV_TOL = 1e-12, 10_000, 1e-8
# Standard errors cluster by panel unit (the column named here), with the small-sample factor G/(G-1) x (N-1)/(N-K),
# where K counts the slopes, the year effects but one and the constant, as Stata's xtreg, fe vce(cluster) counts year
# dummies; the unit effects are nested in the clusters and not counted. p-values come from a t distribution with
# G - 1 degrees of freedom, G the number of clusters, reported as provinces
CLUSTER = "unit"

# A unit enters the between-province and long-difference comparisons only with at least this many years in the test's
# sample. This leaves out Kalimantan Timur (pre-split, 2010-2014) and the six Papua provinces of 2024-2025, whose
# areas the longer units already cover, so each place counts once and no difference spans one year
CROSS_SECTION_MIN_YEARS = 5

# Samples, by the name the results give them: the panel's unit-years from the first year given, which is every panel
# year, the years of the sharpened share, the years of the informal share, or the years of T5's employee counts
SAMPLES = {"all_years": FIRST_YEAR, "sharp_years": SHARP_FIRST_YEAR, "informal_years": INFORMAL_FIRST_YEAR,
           "wage_years": WAGE_FIRST_YEAR}
# The control of T1, T2 and T3: log real GRDP per capita
INCOME = "ln_grdp_pc_real"
# The sharpened share and each group's share, as panel columns
SHARP_SHARE = "extractive_sharp_share_pct"
GROUP_SHARES = [f"{group}_share_pct" for group in EXTRACTIVE_GROUPS]


def read_dataset(key):
    """Read a dataset's CSV and metadata, with codes, periods and statuses as text and every value parsed as a number.

    The metadata must declare the shared format and each indicator read must carry its declared unit.
    """
    name = DATASETS[key]
    folder = ROOT / "data" / name
    meta = json.loads((folder / f"{name}-metadata.json").read_text(encoding="utf-8"))
    fmt = meta["format"]
    assert fmt["encoding"].startswith("UTF-8") and fmt["delimiter"] == "," and fmt["decimal"] == "." \
        and fmt["thousands_separator"] is None, f"{name}: not the shared CSV format"
    for indicator, unit in UNITS[key].items():
        assert meta["indicators"][indicator]["unit"] == unit, f"{name}: unit of {indicator} changed"
    df = pd.read_csv(folder / f"{name}.csv", dtype=str, keep_default_na=False, encoding="utf-8")
    # Every value must parse as a number; a text value stops the script
    df["value"] = pd.to_numeric(df["value"], errors="raise").astype(float)
    return df, meta


def yearly(df, **keys):
    """Return the rows of yearly periods (YYYY) in the panel years matching the key columns, with the year as int."""
    rows = df[df["period"].str.fullmatch(r"\d{4}")]
    for column, value in keys.items():
        rows = rows[rows[column] == value]
    rows = rows.assign(year=rows["period"].astype(int))
    return rows[rows["year"].between(FIRST_YEAR, LAST_YEAR)]


def survey_round(df, half, **keys):
    """Return the rows of one survey round (YYYYS1 or YYYYS2, as half gives it) in the panel years matching the key
    columns, with the year as int."""
    rows = df[df["period"].str.fullmatch(r"\d{4}" + half)]
    for column, value in keys.items():
        rows = rows[rows[column] == value]
    rows = rows.assign(year=rows["period"].str[:4].astype(int))
    return rows[rows["year"].between(FIRST_YEAR, LAST_YEAR)]


def series(rows, column="value"):
    """Return one value per (province code, year), stopping on a repeated key."""
    assert not rows.duplicated(["province_code", "year"]).any(), "repeated province-year"
    return rows.set_index(["province_code", "year"])[column]


def check_borders(key, keys, years=YEARS):
    """Check that a dataset reports every parent in each of the years, and each carved-out province from its declared
    year only."""
    for parent, kids in SPLITS.items():
        start = SEPARATE_FROM[key][parent]
        for year in years:
            assert (parent, year) in keys, f"{key}: no row for {parent} in {year}"
            present = {k for k in kids if (k, year) in keys}
            expected = set(kids) if year >= start else set()
            assert present == expected, f"{key}: {sorted(present)} in {year}, expected {sorted(expected)}"


def panel_units(names):
    """Return the panel units as {unit: (name, codes covered, first year, last year)}.

    A split province is one unit on its pre-split area (code 'parent+children') until the last dataset reports the
    new provinces apart, and from then on the parent and each new province are units of their own.
    """
    children = {c for kids in SPLITS.values() for c in kids}
    units = {}
    for code in sorted(names):
        if code in SPLITS:
            split = UNIT_SPLIT[code]
            codes = [code] + SPLITS[code]
            units["+".join(codes)] = (PRE_SPLIT_NAMES[code], codes, FIRST_YEAR, split - 1)
            units[code] = (charts.display_name(names[code]), [code], split, LAST_YEAR)
        elif code in children:
            units[code] = (charts.display_name(names[code]), [code], UNIT_SPLIT[PARENT_OF[code]], LAST_YEAR)
        else:
            units[code] = (charts.display_name(names[code]), [code], FIRST_YEAR, LAST_YEAR)
    return units


def area_codes(key, codes, year):
    """Return the codes whose rows make up a unit's area in one dataset and year.

    A pre-split area is its parent's row until the dataset reports the new provinces apart, and the sum of the parent
    and its new provinces after; only additive datasets may be summed. A post-split province must already be reported
    on its own borders.
    """
    head = codes[0]
    if len(codes) > 1:
        if year < SEPARATE_FROM[key][head]:
            return [head]
        assert key in ADDITIVE, f"{key} would need its rates added to rebuild {'+'.join(codes)} in {year}"
        return codes
    parent = PARENT_OF.get(head, head)
    if parent in SPLITS:
        assert year >= SEPARATE_FROM[key][parent], f"{key} reports {head} on pre-split borders in {year}"
    return codes


def gather(key, table, units, columns):
    """Return a unit-year table of a dataset's columns, summed over the codes of each unit's area, and the unit-years
    that were summed from more than one code. Every code needed must have a row."""
    out, summed = {}, []
    for unit, (_, codes, first, last) in units.items():
        for year in range(first, last + 1):
            parts = area_codes(key, codes, year)
            missing = [c for c in parts if (c, year) not in table.index]
            assert not missing, f"{key}: no row for {missing} in {year}, needed for {unit}"
            out[(unit, year)] = table.loc[[(c, year) for c in parts], columns].sum()
            if len(parts) > 1:
                summed.append((unit, year))
    frame = pd.DataFrame.from_dict(out, orient="index")
    frame.index = pd.MultiIndex.from_tuples(frame.index, names=["unit", "year"])
    return frame, summed


def single(key, values, units):
    """Return a unit-year series of a dataset's rates or per capita values, taken from the one code of each unit's
    area."""
    out = {}
    for unit, (_, codes, first, last) in units.items():
        for year in range(first, last + 1):
            parts = area_codes(key, codes, year)
            assert len(parts) == 1
            if (parts[0], year) in values.index:
                out[(unit, year)] = values.loc[(parts[0], year)]
    result = pd.Series(out, dtype=float)
    result.index = pd.MultiIndex.from_tuples(result.index, names=["unit", "year"])
    return result


def labour_series(values, units, first_year, column):
    """Return a unit-year series of a labour value from first_year on, and the unit-years without one.

    A unit takes its own code's value; a pre-split unit takes its parent's, which covers the pre-split area while the
    dataset does not yet report the new provinces apart. A rate cannot be added up to another area, so the read stops if
    the dataset reports a pre-split unit's new provinces apart in one of its years, or a new province before its unit
    starts.
    """
    out, gaps = {}, []
    for unit, (_, codes, first, last) in units.items():
        for year in range(max(first, first_year), last + 1):
            apart = [c for c in codes[1:] if (c, year) in values.index]
            assert not apart, f"{column}: {apart} reported apart in {year}, inside the pre-split unit {unit}"
            if (codes[0], year) in values.index:
                out[(unit, year)] = values.loc[(codes[0], year)]
            else:
                gaps.append((unit, year))
    for code, parent in PARENT_OF.items():
        early = sorted(y for c, y in values.index if c == code and first_year <= y < UNIT_SPLIT[parent])
        assert not early, f"{column}: {code} reported apart in {early}, before its unit starts"
    result = pd.Series(out, dtype=float)
    result.index = pd.MultiIndex.from_tuples(result.index, names=["unit", "year"])
    return result, gaps


def parse_years(text):
    """Return the years of a span text such as '2014, 2016-2025', as the metadata writes them."""
    years = []
    for part in text.split(","):
        first, _, last = part.strip().partition("-")
        years += range(int(first), int(last or first) + 1)
    return years


def detailed_table(df, dataset_meta, sectors, prices="current"):
    """Return the detailed dataset's values at one price basis in the panel years as a table with one row per
    (province code, year) that has a yearbook table and one column per sector, and the count of en-dash cells set to 0.

    prices: "current" (yearbook table 13.1.1, indicator grdp_current) or "constant_2010" (table 13.1.2, indicator
        grdp_constant_2010).
    An en-dash cell (none or zero) has no row in the CSV and becomes 0 when the metadata lists it under
    none_or_zero_cells; any other cell without a row, unpublished or excluded, stays missing, and so does an en-dash
    cell the metadata also lists under small_values, a small value BPS did not print rather than a zero.
    """
    indicator = f"grdp_{prices}"
    assert indicator in dataset_meta["indicators"], f"the detailed dataset has no tables at {prices} prices"
    rows = yearly(df, indicator=indicator)
    assert not rows.duplicated(["province_code", "year", "sector"]).any(), "repeated detailed key"
    table = rows.pivot(index=["province_code", "year"], columns="sector", values="value").reindex(columns=sectors)
    # The small values hidden under en dashes at this price basis, which stay missing
    small = {(c["province_code"], c["sector"], int(c["period"]))
             for c in dataset_meta["none_or_zero_cells"]["small_values"]["cells"] if c["indicator"] == indicator}
    zeros = 0
    for code, cells in dataset_meta["none_or_zero_cells"]["cells"][indicator].items():
        for sector, years in cells.items():
            for year in parse_years(years):
                if sector in sectors and (code, year) in table.index and (code, sector, year) not in small:
                    assert pd.isna(table.loc[(code, year), sector]), f"en dash with a row: {code} {sector} {year}"
                    table.loc[(code, year), sector] = 0.0
                    zeros += 1
    return table, zeros


def gather_detailed(table, units, columns):
    """Return a unit-year table of the detailed columns summed over the codes of each unit's area, the unit-years
    summed from more than one code, and the reason each other unit-year has no values: a code of its area without
    a yearbook table, or a needed cell that is unpublished or excluded."""
    out, summed, gaps = {}, [], {}
    for unit, (_, codes, first, last) in units.items():
        for year in range(first, last + 1):
            parts = area_codes("detailed", codes, year)
            absent = [c for c in parts if (c, year) not in table.index]
            if absent:
                gaps[(unit, year)] = f"no yearbook table for {' '.join(absent)}"
                continue
            block = table.loc[[(c, year) for c in parts], columns]
            unknown = [column for column in columns if block[column].isna().any()]
            if unknown:
                gaps[(unit, year)] = f"no value for {' '.join(unknown)}"
                continue
            out[(unit, year)] = block.sum()
            if len(parts) > 1:
                summed.append((unit, year))
    frame = pd.DataFrame.from_dict(out, orient="index")
    frame.index = pd.MultiIndex.from_tuples(frame.index, names=["unit", "year"])
    return frame, summed, gaps


def year_span(years):
    """Return compact text for a list of years, such as '2011-2014' or '2013-2014, 2023'."""
    years = sorted(set(years))
    if not years:
        return ""
    runs, start = [], years[0]
    for a, b in zip(years, years[1:] + [None]):
        if b != a + 1:
            runs.append(f"{start}-{a}" if a != start else f"{a}")
            start = b
    return ", ".join(runs)


def demean(values, unit_idx, year_idx):
    """Remove unit and year means by alternating demeaning until no value moves more than DEMEAN_TOL.

    On an unbalanced panel this converges to the residual of a regression on unit and year dummies.
    """
    v = values.astype(float).copy()
    n_units, n_years = unit_idx.max() + 1, year_idx.max() + 1
    unit_n, year_n = np.bincount(unit_idx, minlength=n_units), np.bincount(year_idx, minlength=n_years)
    for _ in range(DEMEAN_MAX_ITER):
        before = v.copy()
        v = v - (np.bincount(unit_idx, weights=v, minlength=n_units) / unit_n)[unit_idx]
        v = v - (np.bincount(year_idx, weights=v, minlength=n_years) / year_n)[year_idx]
        if np.max(np.abs(v - before)) < DEMEAN_TOL:
            return v
    raise RuntimeError("alternating demeaning did not converge")


def twfe(df, outcome, predictors):
    """Two-way fixed effects OLS of an outcome on predictors, with standard errors clustered by unit.

    Returns the slopes, their clustered standard errors and p-values, and the sample's size, units and years.
    """
    d = df.dropna(subset=[outcome] + predictors).sort_values(["unit", "year"])
    # A unit with one year has no within-unit variation; none is expected
    assert (d.groupby("unit")["year"].transform("size") > 1).all(), f"{outcome}: a unit with one year"
    units, unit_idx = np.unique(d["unit"].to_numpy(), return_inverse=True)
    years, year_idx = np.unique(d["year"].to_numpy(), return_inverse=True)
    y = demean(d[outcome].to_numpy(), unit_idx, year_idx)
    x = np.column_stack([demean(d[p].to_numpy(), unit_idx, year_idx) for p in predictors])
    xtx_inv = np.linalg.inv(x.T @ x)
    slopes = xtx_inv @ (x.T @ y)
    resid = y - x @ slopes
    # The slopes equal those of OLS with a dummy for every unit and every year but one
    dummies = np.column_stack([d[p].to_numpy(float) for p in predictors]
                              + [(unit_idx == g).astype(float) for g in range(len(units))]
                              + [(year_idx == t).astype(float) for t in range(1, len(years))])
    lsdv = np.linalg.lstsq(dummies, d[outcome].to_numpy(float), rcond=None)[0][:len(predictors)]
    gap = np.max(np.abs(lsdv - slopes) / np.maximum(1.0, np.abs(slopes)))
    assert gap < LSDV_TOL, f"{outcome}: demeaned slopes differ from dummy-variable OLS by {gap}"
    # Cluster-robust (sandwich) variance with the CR1 small-sample factor
    clusters, cluster_idx = np.unique(d[CLUSTER].to_numpy(), return_inverse=True)
    n, g, k = len(d), len(clusters), len(predictors) + (len(years) - 1) + 1
    scores = np.zeros((g, len(predictors)))
    np.add.at(scores, cluster_idx, x * resid[:, None])
    variance = (g / (g - 1)) * ((n - 1) / (n - k)) * xtx_inv @ (scores.T @ scores) @ xtx_inv
    se = np.sqrt(np.diag(variance))
    p = 2 * stats.t.sf(np.abs(slopes / se), g - 1)
    return {"slopes": slopes, "se": se, "p": p, "n": n, "units": g, "years": (int(years[0]), int(years[-1]))}


def cross_section(df, outcome, columns):
    """Return the test's sample, the unit-years with the outcome and the columns, restricted to units with at least
    CROSS_SECTION_MIN_YEARS years."""
    d = df.dropna(subset=[outcome, *columns])
    return d[d.groupby("unit")["year"].transform("size") >= CROSS_SECTION_MIN_YEARS].sort_values(["unit", "year"])


def partial_spearman(x, y, controls):
    """Partial rank correlation of x and y controlling for the controls, with its p-value.

    The Pearson correlation of the ranks of x and of y after each is regressed on a constant and the ranks of the
    controls; the p-value comes from a t distribution with n - 2 - (number of controls) degrees of freedom. With one
    control it must equal the textbook formula on the three Spearman correlations.
    """
    rx, ry = stats.rankdata(x), stats.rankdata(y)
    z = np.column_stack([np.ones(len(rx))] + [stats.rankdata(c) for c in controls])
    ex = rx - z @ np.linalg.lstsq(z, rx, rcond=None)[0]
    ey = ry - z @ np.linalg.lstsq(z, ry, rcond=None)[0]
    r = float(ex @ ey / math.sqrt((ex @ ex) * (ey @ ey)))
    if len(controls) == 1:
        rxy, rxz, ryz = (float(stats.spearmanr(a, b).statistic) for a, b in
                         [(x, y), (x, controls[0]), (y, controls[0])])
        formula = (rxy - rxz * ryz) / math.sqrt((1 - rxz ** 2) * (1 - ryz ** 2))
        assert abs(r - formula) < 1e-12, f"partial rank correlation {r} differs from the formula's {formula}"
    dof = len(rx) - 2 - len(controls)
    t = r * math.sqrt(dof / (1 - r ** 2))
    return r, float(2 * stats.t.sf(abs(t), dof))


def between(df, outcome, predictor, controls=()):
    """Spearman rank correlation of unit averages over their years; with controls, the partial rank correlation that
    controls for the controls' unit averages."""
    d = cross_section(df, outcome, [predictor, *controls])
    means = d.groupby("unit")[[predictor, outcome, *controls]].mean()
    if controls:
        rho, p = partial_spearman(means[predictor], means[outcome], [means[c] for c in controls])
    else:
        r = stats.spearmanr(means[predictor], means[outcome])
        rho, p = float(r.statistic), float(r.pvalue)
    return {"rho": rho, "p": p, "n": len(means), "units": len(means),
            "years": (int(d["year"].min()), int(d["year"].max()))}


def long_differences(df, outcome, predictor, controls=()):
    """Return each unit's change from its first to its last year in the test's sample, with both years: d_x for the
    predictor, d_y for the outcome and d_<control> for each control."""
    d = cross_section(df, outcome, [predictor, *controls])
    first = d.loc[d.groupby("unit")["year"].idxmin()].set_index("unit")
    last = d.loc[d.groupby("unit")["year"].idxmax()].set_index("unit")
    return pd.DataFrame({"d_x": last[predictor] - first[predictor], "d_y": last[outcome] - first[outcome],
                         **{f"d_{c}": last[c] - first[c] for c in controls},
                         "first": first["year"], "last": last["year"]})


def long_difference(df, outcome, predictor, controls=()):
    """Spearman rank correlation of the changes from each unit's first to its last year; with controls, the partial
    rank correlation that controls for the controls' changes."""
    ld = long_differences(df, outcome, predictor, controls)
    if controls:
        rho, p = partial_spearman(ld["d_x"], ld["d_y"], [ld[f"d_{c}"] for c in controls])
    else:
        r = stats.spearmanr(ld["d_x"], ld["d_y"])
        rho, p = float(r.statistic), float(r.pvalue)
    return {"rho": rho, "p": p, "n": len(ld), "units": len(ld),
            "years": (int(ld["first"].min()), int(ld["last"].max()))}


def num(value, digits=6):
    """Format a number with a fixed count of significant digits, or empty text for None."""
    return "" if value is None else f"{value:.{digits}g}"


def above_median(values):
    """Return a boolean Series, True where a value lies strictly above the median of the values given.

    values: a Series, whose index the result keeps, or any sequence of numbers. A missing value is False and does not
    count toward the median.
    """
    values = pd.Series(values)
    return values > values.median()


@dataclass
class PanelBuild:
    """The harmonised panel that build() returns, with what was read and derived on the way to it.

    panel: one row per unit-year, sorted by unit and year with a fresh index; the panel script saves it as
        20261103_harmonised-panel.csv.
    units: {unit: (name, BPS codes covered, first year, last year)} in build order, as panel_units returns them; a
        pre-split unit's key joins its codes with '+', as in '94+95+96+97'.
    names: {BPS province code: BPS name} of the 38 provinces, from the GRDP metadata.
    data, meta: {dataset key of DATASETS: the CSV as read_dataset returns it} and {key: its metadata}.
    grdp_units: var 286 GRDP rebuilt on each unit's borders, indexed by (unit, year): grdp_current and
        grdp_constant_2010 (Rp billion), pop_current and pop_constant_2010 (GRDP over BPS's per capita value), and
        grdp_per_capita_current and grdp_per_capita_constant_2010 (Rp thousand per person), unrounded.
    industry_units: vars 2267 and 2268 on each unit's borders, indexed by (unit, year): B and TOTAL at current prices,
        TOTAL_constant at constant 2010 prices (Rp billion), unrounded.
    expenditure_units, expenditure_summed: var 534 on each unit's borders, indexed by (unit, year), one column per code
        of EXPENDITURE_COMPONENTS at current prices (Rp billion), unrounded; and the unit-years summed from several
        codes.
    detailed_sectors: the yearbook sectors read, those of EXTRACTIVE_GROUPS and then TOTAL.
    mining_sectors: B's sub-categories in the yearbook tables, B1 to B4.
    detailed: detailed_table's current-price table of detailed_sectors by (province code, year), en-dash cells as 0.
    detailed_units, detailed_summed, detailed_gaps: gather_detailed's result on that table: the sectors summed on each
        unit's borders for the unit-years with every value, indexed by (unit, year); the unit-years summed from several
        codes; and {(unit, year): reason} for the unit-years without the detail.
    sharp: the sharpened definition on detailed_units' index, as the panel holds it: detailed_total_current_bn,
        estate_crops_current_bn, <group>_current_bn for each group, extractive_sharp_current_bn, plantation_includes_c2,
        estate_crops_share_pct, SHARP_SHARE and GROUP_SHARES.
    mills: boolean Series on detailed_units' index, True where the plantation group counts C2 (estate crops at least
        ESTATE_MIN_SHARE of the unit-year's GRDP at current prices).
    checks: the figures the checks found, as the panel script prints them: pop_gap, border_checks, dash_zeros,
        detail_checks, detail_worst ({check: largest gap}), expenditure_checks, expenditure_worst, pkrt_above (the
        panel rows, in build order, whose PKRT share passes 100%), part_gap, share_gap and split_gap.
    """
    panel: pd.DataFrame
    units: dict
    names: dict
    data: dict
    meta: dict
    grdp_units: pd.DataFrame
    industry_units: pd.DataFrame
    expenditure_units: pd.DataFrame
    expenditure_summed: list
    detailed_sectors: list
    mining_sectors: list
    detailed: pd.DataFrame
    detailed_units: pd.DataFrame
    detailed_summed: list
    detailed_gaps: dict
    sharp: pd.DataFrame
    mills: pd.Series
    checks: dict


def build():
    """Read the panel's datasets from data/, check them, and return the harmonised panel as a PanelBuild.

    Runs every check of the panel: the shared format and declared units, the provinces listed, each dataset's
    borders, the rebuilt unit borders against var 286 GRDP, the yearbook detail, the expenditure identity, the
    declared gaps and the identity of T5's parts. A failed check stops it with an AssertionError. It prints nothing and
    writes nothing.
    """
    # Read the ten datasets, checking their format and units
    data, meta = {}, {}
    for key in DATASETS:
        data[key], meta[key] = read_dataset(key)

    # Province names come from the GRDP metadata, which lists the 38 provinces with their BPS names; every dataset must
    # list the same 38
    names = {c: p["name"] for c, p in meta["grdp"]["provinces"].items() if c != NATIONAL}
    for key in DATASETS:
        assert {c for c in meta[key]["provinces"] if c != NATIONAL} == set(names), f"{key}: other provinces"

    # Pick the series each test needs: GRDP and per capita by year; the industry's current-price sectors and both TOTALs
    # by year; Gini (total, urban, rural) from the March round; the labour series by year
    grdp = {ind: series(yearly(data["grdp"], indicator=ind, sector="TOTAL")) for ind in UNITS["grdp"]}
    grdp_status = series(yearly(data["grdp"], indicator="grdp_current", sector="TOTAL"), "status")
    sectors = sorted(set(EXTRACTIVE_SECTORS + ["TOTAL"]))
    industry = {s: series(yearly(data["industry"], indicator="grdp_current", sector=s)) for s in sectors}
    industry["TOTAL_constant"] = series(yearly(data["industry"], indicator="grdp_constant_2010", sector="TOTAL"))
    gini = {area: series(survey_round(data["gini"], MARCH, indicator="gini_ratio", area=area))
            for area in ["total", "urban", "rural"]}
    labour = {column: series(yearly(data[key], indicator=indicator)) for column, (key, indicator) in LABOUR.items()}
    # PKRT and PDRB on the expenditure side by year, at current prices
    expenditure = {c: series(yearly(data["expenditure"], indicator="grdp_current", component=c))
                   for c in EXPENDITURE_COMPONENTS}
    # T5's employee counts, employment and monthly wages from the Agustus round; T6's school participation by year
    t5_values = {column: series(survey_round(data[key], AUGUST, **keys)) for column, (key, keys) in T5_SERIES.items()}
    t6_values = {column: series(yearly(data["school"], indicator="school_participation_rate", age_group=age))
                 for column, age in T6_SERIES.items()}

    # The four GRDP indicators hold the same province-years, as do the industry series, the expenditure series, and the
    # Gini total and urban series, so the border checks below on one series of each hold for the others
    for name, group in [("GRDP", grdp), ("industry", industry), ("expenditure", expenditure)]:
        keys = {frozenset(s.index) for s in group.values()}
        assert len(keys) == 1, f"{name} series hold different province-years"
    assert set(gini["total"].index) == set(gini["urban"].index), "Gini total and urban differ in coverage"

    # Check each dataset's borders against the declared first years of the new provinces
    check_borders("grdp", set(grdp["grdp_current"].drop(NATIONAL, level=0).index))
    check_borders("industry", set(industry["TOTAL"].index))
    check_borders("gini", set(gini["total"].index))
    check_borders("expenditure", set(expenditure["TOTAL"].index))
    # The informal share starts in its declared first year
    assert min(y for _, y in labour["informal_share_pct"].index) == INFORMAL_FIRST_YEAR, \
        "the informal share's first year"

    # The sectors of the sharpened definition carry their declared BPS names; each is a sub-category or an item, and
    # none lies under another, so no value counts twice. B1-B4 are all of B, so the definition holds all of mining
    sector_meta = meta["detailed"]["sectors"]
    sharp_sectors = [code for codes in EXTRACTIVE_GROUPS.values() for code in codes]
    assert len(set(sharp_sectors)) == len(sharp_sectors), "a sector sits in two groups"
    for codes in EXTRACTIVE_GROUPS.values():
        for code, bps_name in codes.items():
            assert sector_meta[code]["name"] == bps_name, f"{code} is now {sector_meta[code]['name']!r}"
            assert sector_meta[code]["level"] in ("subcategory", "item"), f"{code} is a {sector_meta[code]['level']}"
    for code in sharp_sectors:
        parent = sector_meta[code]["parent"]
        while parent is not None:
            assert parent not in sharp_sectors, f"{code} lies under {parent}, and both are in the definition"
            parent = sector_meta[parent]["parent"]
    assert {MILLS_SECTOR, ESTATE_SECTOR} <= set(EXTRACTIVE_GROUPS["plantation"]), "the mills rule names other sectors"
    mining_sectors = [code for code, s in sector_meta.items() if s["parent"] == "B"]
    assert mining_sectors == ["B1", "B2", "B3", "B4"] and set(mining_sectors) <= set(sharp_sectors), \
        f"B's sub-categories are now {mining_sectors}"
    # An en dash at current prices is a true none or zero: the small values that hide under en dashes all lie in the
    # constant-price tables
    hidden = {c["indicator"] for c in meta["detailed"]["none_or_zero_cells"]["small_values"]["cells"]}
    assert hidden == {"grdp_constant_2010"}, f"small values hide under en dashes in {sorted(hidden)}"

    # Read the sharpened sectors and TOTAL at current prices from the yearbook tables, each en-dash cell as 0
    detailed_sectors = sharp_sectors + ["TOTAL"]
    detailed, dash_zeros = detailed_table(data["detailed"], meta["detailed"], detailed_sectors)
    # Each border province has a yearbook table from its declared first year on, and in no year before
    for code, start in DETAILED_FIRST_YEARS.items():
        held = {y for c, y in detailed.index if c == code}
        assert held == set(range(max(start, FIRST_YEAR), LAST_YEAR + 1)), \
            f"detailed: tables of {code} in {year_span(held)}"

    # Panel units follow the borders of the datasets that hold rates, which cannot be added up to a pre-split area:
    # each must report the new provinces apart from the year its unit splits (UNIT_SPLIT)
    for key in SEPARATE_FROM:
        if key not in ADDITIVE:
            assert SEPARATE_FROM[key] == UNIT_SPLIT, f"{key} holds rates on borders the panel units do not follow"
    units = panel_units(names)

    # Rebuild GRDP on each unit's borders: GRDP sums over the area's codes, and each per capita value is the summed GRDP
    # over the summed population implied by BPS's per capita (GRDP / per capita), at its own prices
    grdp_table = pd.DataFrame(grdp)
    for prices in ["current", "constant_2010"]:
        grdp_table[f"pop_{prices}"] = grdp_table[f"grdp_{prices}"] / grdp_table[f"grdp_per_capita_{prices}"]
    pop_gap = (grdp_table["pop_current"] / grdp_table["pop_constant_2010"] - 1).abs().max()
    assert pop_gap < POP_TOL, f"implied populations differ by {pop_gap} between the price bases"
    g_units, g_summed = gather("grdp", grdp_table, units, ["grdp_current", "grdp_constant_2010", "pop_current",
                                                           "pop_constant_2010"])
    for prices in ["current", "constant_2010"]:
        g_units[f"grdp_per_capita_{prices}"] = g_units[f"grdp_{prices}"] / g_units[f"pop_{prices}"]

    # The GRDP status (BPS revision marker) is the year's, the same for every code of an area
    status = {}
    for unit, (_, codes, first, last) in units.items():
        for year in range(first, last + 1):
            marks = {grdp_status.loc[(c, year)] for c in area_codes("grdp", codes, year)}
            assert len(marks) == 1, f"statuses differ inside {unit} {year}"
            status[(unit, year)] = marks.pop()

    # Rebuild the industry sectors on each unit's borders by summing the area's codes
    i_units, i_summed = gather("industry", pd.DataFrame(industry), units, list(industry))

    # Check the rebuilt borders: var 286 GRDP equals the industry TOTAL on every unit-year, at both prices, within the
    # rounding tolerance or at BPS's declared gap
    border_checks = 0
    for (unit, year) in g_units.index:
        for indicator, column in [("grdp_current", "TOTAL"), ("grdp_constant_2010", "TOTAL_constant")]:
            gap = round(i_units.loc[(unit, year), column] - g_units.loc[(unit, year), indicator], 2)
            declared = BORDER_GAPS.get((unit, year, indicator))
            assert (gap == declared) if declared is not None else abs(gap) <= BORDER_TOL, \
                f"{unit} {year} {indicator}: industry TOTAL differs from var 286 by {gap}"
            border_checks += 1

    # Rebuild PKRT and PDRB on the expenditure side on each unit's borders by summing the area's codes, and check the
    # rebuilt borders: PDRB on the expenditure side equals var 286 GRDP on every unit-year within the rounding tolerance
    e_units, e_summed = gather("expenditure", pd.DataFrame(expenditure), units, list(expenditure))
    assert set(e_units.index) == set(g_units.index), "the expenditure units cover other unit-years"
    expenditure_checks, expenditure_worst = 0, 0.0
    for (unit, year) in g_units.index:
        gap = round(e_units.loc[(unit, year), "TOTAL"] - g_units.loc[(unit, year), "grdp_current"], 2)
        assert abs(gap) <= BORDER_TOL, f"{unit} {year}: expenditure-side PDRB differs from var 286 by {gap}"
        expenditure_checks += 1
        expenditure_worst = max(expenditure_worst, abs(gap))

    # Rebuild the yearbook sectors on each unit's borders by summing the area's codes; a unit-year whose area lacks a
    # table or a needed value has none
    d_units, d_summed, d_gaps = gather_detailed(detailed, units, detailed_sectors)

    # Check the rebuilt yearbook borders on every unit-year with the detail: TOTAL equals var 286 GRDP, and B1-B4 sum to
    # the industry B, within DETAILED_TOL per table summed
    detail_checks, detail_worst = 0, {"TOTAL against var 286": 0.0, "B1-B4 against the industry B": 0.0}
    for (unit, year), row in d_units.iterrows():
        tol = DETAILED_TOL * len(area_codes("detailed", units[unit][1], year))
        for check, gap in [("TOTAL against var 286", row["TOTAL"] - g_units.loc[(unit, year), "grdp_current"]),
                           ("B1-B4 against the industry B",
                            row[mining_sectors].sum() - i_units.loc[(unit, year), "B"])]:
            gap = round(gap, 2)
            assert abs(gap) <= tol, f"{unit} {year}: yearbook {check} differs by {gap}"
            detail_checks += 1
            detail_worst[check] = max(detail_worst[check], abs(gap))

    # Derive the sharpened definition on each unit's borders at the published precision: each group's value, with C2 in
    # the plantation group only where estate crops (A1c) reach ESTATE_MIN_SHARE of the area's GRDP, and the shares of
    # GRDP
    sharp = pd.DataFrame(index=d_units.index)
    sharp["detailed_total_current_bn"] = d_units["TOTAL"].round(2)
    sharp["estate_crops_current_bn"] = d_units[ESTATE_SECTOR].round(2)
    estate_share = (sharp["estate_crops_current_bn"] / sharp["detailed_total_current_bn"] * 100).round(DERIVED_DECIMALS)
    mills = estate_share >= ESTATE_MIN_SHARE
    for group, codes in EXTRACTIVE_GROUPS.items():
        value = d_units[[c for c in codes if c != MILLS_SECTOR]].sum(axis=1)
        if MILLS_SECTOR in codes:
            value = value + d_units[MILLS_SECTOR].where(mills, 0.0)
        sharp[f"{group}_current_bn"] = value.round(2)
    sharp["extractive_sharp_current_bn"] = sharp[[f"{g}_current_bn" for g in EXTRACTIVE_GROUPS]].sum(axis=1).round(2)
    sharp["plantation_includes_c2"] = np.where(mills, "yes", "no")
    sharp["estate_crops_share_pct"] = estate_share
    for column, value in [(SHARP_SHARE, "extractive_sharp_current_bn")] + [
            (share, f"{g}_current_bn") for g, share in zip(EXTRACTIVE_GROUPS, GROUP_SHARES)]:
        sharp[column] = (sharp[value] / sharp["detailed_total_current_bn"] * 100).round(DERIVED_DECIMALS)
    # The group shares add up to the sharpened share, and every share lies between 0 and 100
    assert (sharp[GROUP_SHARES].sum(axis=1) - sharp[SHARP_SHARE]).abs().max() < 1e-5, "group shares do not add up"
    for column in ["estate_crops_share_pct", SHARP_SHARE, *GROUP_SHARES]:
        assert sharp[column].between(0, 100).all(), f"{column} outside 0-100"
    # On a merged unit-year the mills rule gives the same answer for the merged area as for each of its provinces, so
    # applying it after summing changes nothing; a unit-year where they differ stops the script for a decision
    for unit, year in d_summed:
        parts = area_codes("detailed", units[unit][1], year)
        own = {bool(detailed.loc[(c, year), ESTATE_SECTOR] / detailed.loc[(c, year), "TOTAL"] * 100 >= ESTATE_MIN_SHARE)
               for c in parts}
        assert own == {bool(mills[(unit, year)])}, f"{unit} {year}: the mills rule differs between its provinces"

    # Take the Gini ratios from the one code of each unit's area
    social = {"gini_total": single("gini", gini["total"], units), "gini_urban": single("gini", gini["urban"], units),
              "gini_rural": single("gini", gini["rural"], units)}

    # Assemble the panel, one row per unit-year, with each base series at its published precision
    rows = []
    for unit, (name, codes, first, last) in units.items():
        for year in range(first, last + 1):
            g, i = g_units.loc[(unit, year)], i_units.loc[(unit, year)]
            rows.append({"unit": unit, "unit_name": name, "bps_codes": " ".join(codes), "unit_first": first,
                         "unit_last": last, "year": year,
                         "grdp_rule": "summed" if (unit, year) in g_summed else "as published",
                         "industry_rule": "summed" if (unit, year) in i_summed else "as published",
                         "grdp_status": status[(unit, year)],
                         "grdp_current_bn": round(g["grdp_current"], 2),
                         "grdp_constant_2010_bn": round(g["grdp_constant_2010"], 2),
                         "grdp_pc_current_k": round(g["grdp_per_capita_current"], 2),
                         "grdp_pc_constant_2010_k": round(g["grdp_per_capita_constant_2010"], 2),
                         "industry_total_current_bn": round(i["TOTAL"], 2),
                         "extractive_current_bn": round(sum(i[s] for s in EXTRACTIVE_SECTORS), 2),
                         **{k: s.get((unit, year), np.nan) for k, s in social.items()}})
    panel = pd.DataFrame(rows)

    # Every unit-year has every Gini ratio except the declared gap: no rural Gini ratio for Jakarta
    for column in social:
        gaps = panel[panel[column].isna()]
        allowed = gaps["unit"].isin(NO_RURAL) & (column == "gini_rural")
        assert allowed.all(), f"{column} missing for {gaps.loc[~allowed, ['unit', 'year']].values.tolist()}"

    # Derive the test variables: the share of GRDP of mining and quarrying (B, current prices) and the log of real GRDP
    # per capita
    panel["extractive_share_pct"] = panel["extractive_current_bn"] / panel["industry_total_current_bn"] * 100
    panel["ln_grdp_pc_real"] = np.log(panel["grdp_pc_constant_2010_k"])
    derived = ["extractive_share_pct", "ln_grdp_pc_real"]
    panel[derived] = panel[derived].round(DERIVED_DECIMALS)

    # The share must lie between 0 and 100
    assert panel["extractive_share_pct"].between(0, 100).all(), "extractive_share_pct outside 0-100"

    # Add the sharpened definition after the existing columns: how the yearbook values were taken, the values and the
    # shares; a unit-year without the detail leaves them empty
    key = pd.MultiIndex.from_frame(panel[["unit", "year"]])
    summed_keys, sharp_keys = set(d_summed), set(sharp.index)
    panel["detailed_rule"] = ["summed" if k in summed_keys else "as published" if k in sharp_keys else "" for k in key]
    for column in sharp.columns:
        panel[column] = sharp[column].reindex(key).to_numpy()
    # From SHARP_FIRST_YEAR every unit-year has the sharpened share, so its tests keep every unit of the panel
    missing = panel[(panel["year"] >= SHARP_FIRST_YEAR) & panel[SHARP_SHARE].isna()]
    assert missing.empty, f"no sharpened share for {missing[['unit', 'year']].values.tolist()}"

    # Add BPS's household consumption after the existing columns: how its values were taken, PKRT and PDRB on the
    # expenditure side at their published precision, and PKRT's share of that PDRB, which every unit-year has
    e_summed_keys = set(e_summed)
    panel["expenditure_rule"] = ["summed" if k in e_summed_keys else "as published" for k in key]
    panel["pkrt_current_bn"] = e_units["PKRT"].reindex(key).round(2).to_numpy()
    panel["expenditure_total_current_bn"] = e_units["TOTAL"].reindex(key).round(2).to_numpy()
    panel["pkrt_share_pct"] = (panel["pkrt_current_bn"] / panel["expenditure_total_current_bn"] * 100).round(
        DERIVED_DECIMALS)
    assert panel["pkrt_share_pct"].notna().all() and (panel["pkrt_share_pct"] > 0).all(), \
        "PKRT share missing or not positive"
    pkrt_above = panel[panel["pkrt_share_pct"] > 100]

    # Add T2's labour series after the existing columns, each from SHARP_FIRST_YEAR on its unit's borders and as
    # published, and the logs of the two wages. Every unit-year of those years has each series, except the informal
    # share before INFORMAL_FIRST_YEAR and the declared gaps
    labour_gaps = {}
    for column, values in labour.items():
        unit_values, labour_gaps[column] = labour_series(values, units, SHARP_FIRST_YEAR, column)
        panel[column] = unit_values.reindex(key).to_numpy()
    found = {(column, unit.split("+")[0], year) for column, gaps in labour_gaps.items() for unit, year in gaps
             if not (column == "informal_share_pct" and year < INFORMAL_FIRST_YEAR)}
    assert found == set(LABOUR_GAPS), f"labour gaps {sorted(found ^ set(LABOUR_GAPS))} differ from the declared ones"
    for column in ["hourly_wage", "minimum_wage"]:
        panel[f"ln_{column}"] = np.log(panel[f"{column}_rp"]).round(DERIVED_DECIMALS)
    assert panel["informal_share_pct"].dropna().between(0, 100).all(), "informal share outside 0-100"

    # Add T4's five other expenditure components after the existing columns, each at its published precision and as a
    # share of the same expenditure-side PDRB; the six shares add to 100
    for code in T4_COMPONENTS:
        panel[f"{code.lower()}_current_bn"] = e_units[code].reindex(key).round(2).to_numpy()
        panel[f"{code.lower()}_share_pct"] = (panel[f"{code.lower()}_current_bn"]
                                              / panel["expenditure_total_current_bn"] * 100).round(DERIVED_DECIMALS)
    # The six components add to PDRB at their published precision, and the six shares to 100 within that gap and the
    # shares' rounding, row by row
    part_gaps = (panel[[f"{c.lower()}_current_bn" for c in ["PKRT", *T4_COMPONENTS]]].sum(axis=1)
                 - panel["expenditure_total_current_bn"]).abs()
    share_gaps = (panel[["pkrt_share_pct", *T4_OUTCOMES]].sum(axis=1) - 100).abs()
    allowed = SHARE_SUM_TOL + 100 * part_gaps / panel["expenditure_total_current_bn"] + 1e-9
    assert part_gaps.max() <= 0.035 + 1e-9, f"the components miss PDRB by {part_gaps.max():.2f} Rp billion"
    assert (share_gaps <= allowed).all(), f"the six expenditure shares miss 100 by {share_gaps.max()}"
    part_gap, share_gap = part_gaps.max(), share_gaps.max()

    # Add T5's series after the existing columns, each from WAGE_FIRST_YEAR on its unit's borders and as published, and
    # T6's school participation rates from SHARP_FIRST_YEAR; every unit-year of those years has each series
    for first_year, values_by_column in [(WAGE_FIRST_YEAR, t5_values), (SHARP_FIRST_YEAR, t6_values)]:
        for column, values in values_by_column.items():
            unit_values, gaps = labour_series(values, units, first_year, column)
            assert not gaps, f"{column}: no value for {gaps}"
            panel[column] = unit_values.reindex(key).to_numpy()

    # Derive T5's outcome and its parts: the employee wage bill (Rp billion) and its share of GRDP, the employee share
    # of employment, GRDP per worker (Rp thousand), and the logs of the share and its three parts
    panel["wage_bill_current_bn"] = (panel["employees_persons"] * panel["employee_wage_month_rp"] * MONTHS
                                     / RP_PER_BN).round(DERIVED_DECIMALS)
    panel["wage_share_pct"] = (panel["wage_bill_current_bn"] / panel["grdp_current_bn"] * 100).round(DERIVED_DECIMALS)
    panel["employee_share_pct"] = (panel["employees_persons"] / panel["employed_persons"] * 100).round(DERIVED_DECIMALS)
    panel["grdp_per_worker_k"] = (panel["grdp_current_bn"] * RP_PER_BN / 1000 / panel["employed_persons"]).round(2)
    for column, source in [("ln_wage_share", "wage_share_pct"), ("ln_employee_share", "employee_share_pct"),
                           ("ln_employee_wage", "employee_wage_month_rp"), ("ln_grdp_per_worker", "grdp_per_worker_k")]:
        panel[column] = np.log(panel[source]).round(DERIVED_DECIMALS)
    # The shares lie between 0 and 100, and the log of the wage share equals its parts' sum on every unit-year, so the
    # parts' slopes add to its slope
    for column in ["wage_share_pct", "employee_share_pct"]:
        assert panel[column].dropna().between(0, 100).all(), f"{column} outside 0-100"
    split_gap = (panel["ln_wage_share"] - math.log(MONTHS / 1000)
                 - sum(sign * panel[part] for part, sign in T5_PARTS.items())).abs().max()
    assert split_gap < T5_SPLIT_TOL, f"the log wage share misses its parts by {split_gap}"

    # Sort the panel by unit and year with a fresh index, as the panel script saves it
    panel = panel.sort_values(["unit", "year"]).reset_index(drop=True)
    return PanelBuild(
        panel=panel, units=units, names=names, data=data, meta=meta, grdp_units=g_units, industry_units=i_units,
        expenditure_units=e_units, expenditure_summed=e_summed, detailed_sectors=detailed_sectors,
        mining_sectors=mining_sectors, detailed=detailed, detailed_units=d_units, detailed_summed=d_summed,
        detailed_gaps=d_gaps, sharp=sharp, mills=mills,
        checks={"pop_gap": pop_gap, "border_checks": border_checks, "dash_zeros": dash_zeros,
                "detail_checks": detail_checks, "detail_worst": detail_worst,
                "expenditure_checks": expenditure_checks, "expenditure_worst": expenditure_worst,
                "pkrt_above": pkrt_above, "part_gap": part_gap, "share_gap": share_gap, "split_gap": split_gap})
