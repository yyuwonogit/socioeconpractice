from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# Load the shared cleaning module from tools/
import sys
sys.path.insert(0, str(ROOT / "tools"))
import cleaning

import json
from decimal import Decimal

import pandas as pd

# Parameters

# Raw inputs: the BPS province list, and the BPS WebAPI downloads of six vars, each in the six year ranges the
# download script requested. var 286 (GRDP) and var 288 (GRDP per capita) give every value in the CSV. The other four
# are read only as checks and never written: var 291 (real GRDP growth), var 296 (real growth of GRDP per capita), and
# vars 2267 and 2268 (BPS quarterly GRDP by industry, at constant 2010 and at current prices), whose annual value of
# the total row repeats var 286's annual totals as a lower-priority copy
RAW_PROVINCES = ROOT / "raw/province-codes/20261102_bps-province-codes-2025-s1.json"
RAW_DOWNLOAD_SCRIPT = "raw/grdp/20261103_download-bps-api-grdp-2010-2025.py"
YEAR_RANGES = [(2010, 2012), (2013, 2015), (2016, 2018), (2019, 2021), (2022, 2023), (2024, 2025)]
RAW_NAMES = {286: "grdp-by-province", 288: "grdp-per-capita-by-province", 291: "grdp-growth-by-province",
             296: "grdp-per-capita-growth-by-province",
             2267: "grdp-quarterly-constant-prices-by-industry-by-province",
             2268: "grdp-quarterly-current-prices-by-industry-by-province"}
RAW_WEBAPI = {var: {span: ROOT / f"raw/grdp/20261103_bps-api-var{var}-{name}-{span[0]}-{span[1]}.json" for span in YEAR_RANGES}
              for var, name in RAW_NAMES.items()}

# The annual tables by province, read in full, and the quarterly tables by industry and province, of which only the
# annual value of the total row is read
ANNUAL_VARS = [286, 288, 291, 296]
QUARTERLY_VARS = [2267, 2268]

# The dataset that 2020-2025 GRDP and population are checked against, written in the shared CSV format. This build
# reads its CSV and metadata and records their hashes, so data/20261102_bps-province-grdp-population/ must be rebuilt
# before this dataset
CHECK_CSV = ROOT / "data/20261102_bps-province-grdp-population/20261102_bps-province-grdp-population.csv"
CHECK_META = CHECK_CSV.with_name(CHECK_CSV.stem + "-metadata.json")
CHECK_CONTEXT = {"encoding": "utf-8", "delimiter": ",", "decimal": ".", "thousands": None,
                 "units": {"grdp_current": "Rp billion (Milyar Rupiah)", "population": "thousand people (ribu)"}}
CHECK_YEARS = range(2020, 2026)

# Output; the metadata JSON is written beside it with a -metadata suffix
OUT_CSV = HERE / "20261103_bps-province-grdp-2010-2025.csv"

# How each raw file is written, read from opening all 37 files. The province list is UTF-8 JSON without a byte-order
# mark: a list of 38 records whose four fields (kode_bps, nama_bps, kode_dagri, nama_dagri) are all text, so it holds
# no numbers, units or missing values. The 36 WebAPI files are UTF-8 JSON without a byte-order mark: values are JSON
# numbers, a value BPS does not publish is a key absent from datacontent (no markers), the unit sits in each var's
# unit field, and every var declares two decimals
UNITS = {286: "Milyar Rupiah", 288: "Ribu Rupiah", 291: "Persen", 296: "Persen", 2267: "Milyar Rupiah",
         2268: "Milyar Rupiah"}
READ_CONTEXT = {
    RAW_PROVINCES: {"encoding": "utf-8", "numbers": "none: every code and name is a JSON string",
                    "missing": "none: every record carries kode_bps, nama_bps, kode_dagri and nama_dagri",
                    "unit": None},
    **{path: {"encoding": "utf-8", "numbers": "JSON numbers, decimal point, no thousands separator",
              "missing": "key absent from datacontent", "var": var, "unit": UNITS[var], "decimals": 2}
       for var, files in RAW_WEBAPI.items() for path in files.values()},
}

# The one number format and missing-value convention cleaning.read_webapi_table reads: each value a JSON number, and
# a key absent from datacontent for a value BPS does not publish; a WebAPI file declared otherwise stops the build
WEBAPI_READS = {"numbers": "JSON numbers, decimal point, no thousands separator",
                "missing": "key absent from datacontent"}

# Text each var's label must still carry, so that a different table under the same number stops the build
VAR_LABELS = {
    286: "[Seri 2010] Produk Domestik Regional Bruto",
    288: "[Seri 2010] Produk Domestik Regional Bruto Per Kapita",
    291: "[Seri 2010] Laju Pertumbuhan Produk Domestik Regional Bruto Atas Dasar Harga Konstan 2010",
    296: "[Seri 2010] Laju Pertumbuhan Produk Domestik Regional Bruto Per Kapita Atas Dasar Harga Konstan 2010",
    2267: "[Seri 2010] PDRB Triwulanan Atas Dasar Harga Konstan Menurut Lapangan Usaha di Provinsi",
    2268: "[Seri 2010] PDRB Triwulanan Atas Dasar Harga Berlaku Menurut Lapangan Usaha di Provinsi",
}

# Breakdowns each annual table must hold: two price bases (turvar) in the level tables, the single 'Tidak ada'
# (none) turvar in the growth tables, and one annual period (turtahun) in all four
TURVARS = {286: [(530, "Harga Berlaku"), (531, "Harga Konstan 2010")],
           288: [(530, "Harga Berlaku"), (531, "Harga Konstan 2010")],
           291: [("0", "Tidak ada")],
           296: [("0", "Tidak ada")]}
TURTAHUN = [(0, "Tahun")]

# Breakdowns each quarterly table must hold: 18 turvars, the 17 industry categories followed by the total row this
# build reads, and five periods, the four quarters followed by the year ('Tahunan') this build reads
QUARTERLY_TURVAR_COUNT = 18
QUARTERLY_TOTAL = (2022, "Produk Domestik Regional Bruto")
QUARTERLY_TURTAHUN = [(31, "Triwulan I"), (32, "Triwulan II"), (33, "Triwulan III"), (34, "Triwulan IV"),
                      (35, "Tahunan")]
QUARTERLY_ANNUAL = QUARTERLY_TURTAHUN[-1]

# First year each var's files list: the first year of each range, except in var 296, whose first file lists only 2011
# and 2012 because growth needs the year before and the series starts in 2010 (var 291's first file lists 2010 with
# no values)
LISTED_FROM = {296: 2011}

# Output indicators, by var and turvar, in output order
INDICATORS = {
    (286, 530): "grdp_current",
    (286, 531): "grdp_constant_2010",
    (288, 530): "grdp_per_capita_current",
    (288, 531): "grdp_per_capita_constant_2010",
}

# Name, unit and multiplier to base units of each indicator
INDICATOR_INFO = {
    "grdp_current": {"name": "PDRB atas dasar harga berlaku (GRDP at current prices), Seri 2010",
                     "unit": "Rp billion (Milyar Rupiah)", "multiplier": 1e9, "base_unit": "Rp"},
    "grdp_constant_2010": {"name": "PDRB atas dasar harga konstan 2010 (GRDP at constant 2010 prices), Seri 2010",
                           "unit": "Rp billion (Milyar Rupiah)", "multiplier": 1e9, "base_unit": "Rp"},
    "grdp_per_capita_current": {"name": "PDRB per kapita atas dasar harga berlaku (GRDP per capita at current prices), Seri 2010",
                                "unit": "Rp thousand per person (Ribu Rupiah)", "multiplier": 1e3, "base_unit": "Rp per person"},
    "grdp_per_capita_constant_2010": {"name": "PDRB per kapita atas dasar harga konstan 2010 (GRDP per capita at constant 2010 prices), Seri 2010",
                                      "unit": "Rp thousand per person (Ribu Rupiah)", "multiplier": 1e3, "base_unit": "Rp per person"},
}

# The vars that publish each indicator's annual values, in priority order: the first gives every value in the CSV,
# and a later one is a lower-priority copy, the annual value of a quarterly table's total row, read only as a check
SOURCE_PRIORITY = {"grdp_current": [286, 2268], "grdp_constant_2010": [286, 2267],
                   "grdp_per_capita_current": [288], "grdp_per_capita_constant_2010": [288]}

# What each var gives this dataset, for the metadata
ROLES = {
    286: "gives every grdp_current and grdp_constant_2010 value in the CSV, first in source_priority",
    288: "gives every grdp_per_capita_current and grdp_per_capita_constant_2010 value in the CSV",
    291: "check only: real GRDP growth, against the growth computed from grdp_constant_2010",
    296: "check only: real growth of GRDP per capita, against the growth computed from grdp_per_capita_constant_2010",
    2267: "check only: lower-priority copy of grdp_constant_2010 in the annual value of its total row",
    2268: "check only: lower-priority copy of grdp_current in the annual value of its total row",
}

# Key columns, the one sector code every row carries, and the years every indicator covers
KEYS = ["province_code", "indicator", "sector", "period"]
SECTORS = {"TOTAL": "Produk Domestik Regional Bruto (all industries, lapangan usaha basis)"}
YEARS = range(2010, 2026)

# Revision status by year that each var's note states; the build stops if a note changes. var 288's note is one
# release behind its own values (it names 2023 and 2024, though the table holds 2025), so var 286's statuses apply to
# every indicator; var 296's note, on the growth of the per capita series, must give var 286's statuses, which
# confirms them for the per capita rows. The quarterly tables' notes also name 2026, whose quarters these files do
# not hold
NOTE_STATUS = {286: {2024: "*", 2025: "**"}, 288: {2023: "*", 2024: "**"}, 291: {2024: "*", 2025: "**"},
               296: {2024: "*", 2025: "**"}, 2267: {2024: "*", 2025: "**", 2026: "***"},
               2268: {2024: "*", 2025: "**", 2026: "***"}}
STATUS_VAR = 286
PER_CAPITA_STATUS_VAR = 296

# First year with separate values in these annual tables: Kalimantan Utara (65) from 2013, the four new Papua
# provinces from 2023; every other province and Indonesia have values from 2010
FIRST_YEAR = {"65": 2013, "92": 2023, "95": 2023, "96": 2023, "97": 2023}

# Provinces whose area changed, keyed by the first year on the new borders, with the codes that together cover the
# area the province had the year before, and why the growth tables (vars 291 and 296) differ there from the computed
# growth; old_area_reproduces says whether the growth of that old area gives the table's value, and the build stops
# if it no longer does as declared. In each reason, {table} is the growth table and {levels} its level table
BORDER_CHANGES = {
    ("64", "2013"): {"old_area": ["64", "65"], "old_area_reproduces": True,
                     "reason": "64 in 2012 includes Kalimantan Utara and in 2013 does not, so the computed growth compares "
                               "different areas; {table} gives the growth of the 2012 area, which old_area_growth (64 + 65 in "
                               "2013 over 64 in 2012) reproduces"},
    ("91", "2023"): {"old_area": ["91", "92"], "old_area_reproduces": False,
                     "reason": "91 in 2022 includes Papua Barat Daya and in 2023 does not, so the computed growth compares "
                               "different areas; {table} matches neither that nor old_area_growth, so it rests on 2022 values "
                               "for the post-split area, which {levels} does not publish ({table} also gives 2023 growth for 92)"},
    ("94", "2023"): {"old_area": ["94", "95", "96", "97"], "old_area_reproduces": False,
                     "reason": "94 in 2022 includes Papua Selatan, Papua Tengah and Papua Pegunungan and in 2023 does not, so "
                               "the computed growth compares different areas; {table} matches neither that nor old_area_growth, "
                               "so it rests on 2022 values for the post-split area, which {levels} does not publish ({table} "
                               "also gives 2023 growth for 95, 96 and 97)"},
}

# Keys that var 286 and the quarterly tables (vars 2267 and 2268) hold on different borders, each compared on the
# area both cover, as (var 286's codes, the quarterly table's codes): the quarterly tables carry Kalimantan Utara (65)
# from 2010, three years before var 286, and split Papua only from 2024, one year after it, so their 2023 values for
# 91 and 94 cover the pre-split areas
QUARTERLY_BORDERS = {
    **{("64", str(year)): (["64"], ["64", "65"]) for year in range(YEARS[0], FIRST_YEAR["65"])},
    ("91", "2023"): (["91", "92"], ["91"]),
    ("94", "2023"): (["94", "95", "96", "97"], ["94"]),
}

# The one border-mapped gap beyond rounding, as the quarterly table's value minus var 286's, in Rp billion: in 2023 the
# quarterly tables' pre-split Papua Barat (91) is not var 286's 91 + 92, at current prices (var 2268: 97675.84 against
# 97680.94) or at constant 2010 prices (var 2267: 64964.02 against 64975.02). This is BPS's own inconsistency between
# two of its tables, both of which give 2023 as final; each gap is declared exactly, and the build stops if it changes
KNOWN_GAPS = {(2268, "91", "2023"): Decimal("-5.10"), (2267, "91", "2023"): Decimal("-11.00")}
KNOWN_GAP_REASON = ("BPS's own inconsistency between two of its tables, both of which give 2023 as final, not a reading "
                    "error: the quarterly table's pre-split Papua Barat (91) is not the sum of Papua Barat (91) and Papua "
                    "Barat Daya (92) in var 286, while every other area in border_areas agrees within the tolerance. The "
                    "build declares this gap exactly and stops if it changes")

# Indonesia's row (00) changes basis between 2014 and 2015: in 2010-2014 it tracks the provincial sum (equal within
# TOL_NATIONAL_SUM in 2010-2012, within TOL_NATIONAL_TRACK_PCT in 2013-2014), and in 2015-2025 it is national GDP. var
# 291 publishes no 00 growth for 2015, var 296's 00 per capita growth for 2015 implies GDP growth of about 4.87%
# against 4.38% from the 00 levels, and the provincial sum minus 00 steps from -0.025% in 2013-2014 to +0.56% in 2015 at
# constant prices. The 2015 year-on-year change of 00 therefore compares different bases, and the growth comparisons
# list it apart
NATIONAL_SUM_YEARS = range(2010, 2013)
NATIONAL_TRACK_YEARS = range(2013, 2015)
NATIONAL_GDP_YEARS = range(2015, 2026)
BASIS_CHANGES = {(cleaning.NATIONAL_CODE, str(NATIONAL_GDP_YEARS[0])):
                 "00 in 2014 tracks the provincial sum and in 2015 is national GDP, so the computed growth compares "
                 "different bases"}

# What var 296 shows at the basis change, added to its reason there; var 291 publishes no value for it
BASIS_DETAIL = {296: "var 296 differs: with the population growth var 286 and var 288 imply (population_growth_implied) "
                     "it gives GDP growth of gdp_growth_implied_by_var_296, not gdp_growth_computed, so it likely rests "
                     "on one basis in both years"}

# Per capita growth of 00 in which var 296 differs beyond rounding from the growth computed from var 288, though 00's
# GDP growth matches var 291 (2020: computed -3.26 against var 296's -3.03; 2021: 2.76 against 2.52). With the
# population growth var 286 and var 288 imply, var 296 gives a GDP growth var 291 does not, so the two pairs of tables
# likely use different population series; these keys are listed apart in the comparison with var 296
PER_CAPITA_APART = {(cleaning.NATIONAL_CODE, year): (
    "00's GDP growth matches var 291 (gdp_growth_computed), but var 296, with the population growth var 286 and var 288 "
    "imply (population_growth_implied), gives another GDP growth (gdp_growth_implied_by_var_296), so var 296 likely "
    "divides by a different population series") for year in ["2020", "2021"]}

# The check dataset holds 2023 on the pre-split Papua borders, so 91 and 94 in 2023 are not compared one to one
CHECK_PRE_SPLIT = [("91", "2023"), ("94", "2023")]

# Tolerances for identities and comparisons
TOL_NATIONAL_SUM = 0.17        # Rp billion: 33 provinces and the total, each rounded to 0.01, differ by at most 34 x 0.005
TOL_NATIONAL_TRACK_PCT = 0.17  # percent: the largest gap between 00 and the provincial sum in 2013-2014 is 0.169% (2014, current prices)
TOL_GROWTH = 0.01              # percentage points: one unit in the last decimal vars 291 and 296 publish
TOL_QUARTERLY = 0.05           # Rp billion: BPS rounds var 286 and the quarterly tables' annual value separately; the largest gap found is 0.03
TOL_QUARTERLY_REASON = ("BPS rounds the annual table (var 286) and the quarterly table's annual value separately, so the "
                        "two can differ by a few units in the last decimal")

# Plausibility ranges; a value outside its range is flagged, not dropped. In 2023-2025 the population table and
# BPS's per capita GRDP use the same population, so the implied population should match to the rounding of the
# population figures (about 0.01% for the smallest province); in 2020-2022 they use different population series
PLAUSIBLE = {
    "real_growth_pct": (-15, 25),
    "implied_population_gap_pct_2020_2022": (-3, 3),
    "implied_population_gap_pct_2023_2025": (-0.05, 0.05),
}
IMPLIED_POPULATION_YEARS = {"implied_population_gap_pct_2020_2022": range(2020, 2023),
                            "implied_population_gap_pct_2023_2025": range(2023, 2026)}

# Source addresses for the metadata; the WebAPI request is given without its key
URL_PROVINCES = "https://sig.bps.go.id/rest-bridging/getwilayah?level=provinsi&periode_merge=2025_1.2025"
URL_WEBAPI = "https://webapi.bps.go.id/v1/api/list/model/data/domain/0000/var/{var}/th/{{th}}/key/{{key}}"


# Functions

def row(code, indicator, period, value, status):
    """Return one long row; every value in this dataset is a total over all industries."""
    return {"province_code": code, "indicator": indicator, "sector": "TOTAL", "period": period,
            "status": status, "value": value}


def and_list(items):
    """Return items joined for a sentence: 'a', 'a and b', or 'a, b and c'."""
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def posix(path):
    """Return a path relative to the repository root with forward slashes, for the metadata fields that name files
    (write_dataset writes the raw_files keys the same way itself)."""
    return Path(path).resolve().relative_to(ROOT).as_posix()


def read_webapi(path):
    """Read one saved WebAPI table with the encoding, var, unit and decimals that READ_CONTEXT declares for it."""
    c = READ_CONTEXT[path]

    # read_webapi_table reads values only as JSON numbers and treats an absent key as no value, so a file declared
    # with another number format or missing-value convention stops the build
    if {k: c.get(k) for k in WEBAPI_READS} != WEBAPI_READS:
        raise ValueError(f"{path.name}: READ_CONTEXT declares {c}, but read_webapi_table reads only {WEBAPI_READS}")
    return cleaning.read_webapi_table(path, var=c["var"], unit=c["unit"], decimals=c["decimals"], encoding=c["encoding"])


def read_files(var):
    """Read the six files of one var; return the description they share and each file's records."""
    tables, files = [], []
    for (first, last), path in RAW_WEBAPI[var].items():
        table, records = read_webapi(path)

        # The file must hold the table and years the download asked for
        cleaning.require_text(table["var"][0]["label"], VAR_LABELS[var], path.name)
        years = list(range(max(first, LISTED_FROM.get(var, first)), last + 1))
        if [int(t["label"]) for t in table["tahun"]] != years:
            raise ValueError(f"{path.name}: years {[t['label'] for t in table['tahun']]}, expected {years}")
        tables.append(table)
        files.append((path, records))

    # All six files must come from one release of the table
    for table in tables[1:]:
        for field in ("var", "turvar", "turtahun", "vervar", "labelvervar", "subject", "last_update"):
            if table[field] != tables[0][field]:
                raise ValueError(f"var {var}: files differ in {field}")
    return tables[0], files


def region_key(record, lookup):
    """Return (code, period) of a record: the region code its vervar gives, checked against the BPS list by name."""
    return cleaning.webapi_region_code(record["vervar"], record["vervar_label"], lookup), str(record["year"])


def read_var(var, lookup):
    """Read the six files of one annual table; return its description and {turvar: {(code, period): value}}."""
    table, files = read_files(var)

    # The table must hold the breakdowns this build declares for it
    if [(t["val"], t["label"]) for t in table["turvar"]] != TURVARS[var]:
        raise ValueError(f"var {var}: turvar {table['turvar']}, expected {TURVARS[var]}")
    if [(t["val"], t["label"]) for t in table["turtahun"]] != TURTAHUN:
        raise ValueError(f"var {var}: turtahun {table['turtahun']}, expected {TURTAHUN}")

    # Each value goes to its region code and year, once
    values = {}
    for path, records in files:
        for r in records:
            key, cells = region_key(r, lookup), values.setdefault(r["turvar"], {})
            if key in cells:
                raise ValueError(f"{path.name}: {key} turvar {r['turvar']} read twice")
            cells[key] = r["value"]
    return table, values


def read_quarterly(var, lookup):
    """Read the six files of one quarterly table; return its description and {(code, period): value} of the annual
    value of its total row, which repeats var 286's annual total."""
    table, files = read_files(var)

    # The table must hold 17 industry categories followed by the total row, and four quarters followed by the year
    turvars = [(t["val"], t["label"]) for t in table["turvar"]]
    if (len(turvars) != QUARTERLY_TURVAR_COUNT or turvars[-1] != QUARTERLY_TOTAL
            or [t for t in turvars if t[1] == QUARTERLY_TOTAL[1]] != [QUARTERLY_TOTAL]):
        raise ValueError(f"var {var}: turvar {turvars}, expected {QUARTERLY_TURVAR_COUNT} ending in {QUARTERLY_TOTAL}")
    if [(t["val"], t["label"]) for t in table["turtahun"]] != QUARTERLY_TURTAHUN:
        raise ValueError(f"var {var}: turtahun {table['turtahun']}, expected {QUARTERLY_TURTAHUN}")

    # Keep the annual value of the total row, once for each region code and year
    values = {}
    for path, records in files:
        for r in records:
            if (r["turvar"], r["turvar_label"]) != QUARTERLY_TOTAL or (r["turtahun"], r["turtahun_label"]) != QUARTERLY_ANNUAL:
                continue
            key = region_key(r, lookup)
            if key in values:
                raise ValueError(f"{path.name}: {key} read twice")
            values[key] = r["value"]
    return table, values


def regions_in(year, provinces):
    """Return the codes with their own values in a year: every province that existed, and Indonesia."""
    return [code for code in provinces if year >= FIRST_YEAR.get(code, YEARS[0])]


def expected_keys(provinces):
    """Every key the tables should yield; provinces that did not yet exist in these tables are the only gaps."""
    return {(code, indicator, "TOTAL", str(year)) for year in YEARS for code in regions_in(year, provinces)
            for indicator in INDICATORS.values()}


def coverage(provinces):
    """Describe each run of years with the same regions: how many provinces have values and which codes are absent."""
    runs = []
    for year in YEARS:
        absent = [code for code in provinces if code not in regions_in(year, provinces)]
        if runs and runs[-1]["absent"] == absent:
            runs[-1]["last"] = year
        else:
            runs.append({"first": year, "last": year, "absent": absent})
    return {f"{r['first']}-{r['last']}": {"provinces": len(provinces) - 1 - len(r["absent"]), "indonesia_00": True,
                                          "absent": r["absent"]} for r in runs}


def provincial_sums(values):
    """Return the sum over provinces and BPS's Indonesia value, each as a Series by period."""
    s = pd.Series(values)
    s.index.names = ["province_code", "period"]
    national = s.xs(cleaning.NATIONAL_CODE, level="province_code")
    parts = s.drop(cleaning.NATIONAL_CODE, level="province_code").groupby(level="period").sum()
    return parts, national


def identity_checks(levels):
    """Layer 3: constant equals current prices in the base year 2010, and provinces sum to Indonesia in 2010-2012."""
    results = []

    # In the base year constant 2010 prices are current prices, for GRDP and for GRDP per capita, exactly
    for current, constant in [("grdp_current", "grdp_constant_2010"),
                              ("grdp_per_capita_current", "grdp_per_capita_constant_2010")]:
        base = {k: v for k, v in levels[current].items() if k[1] == "2010"}
        same = {k: v for k, v in levels[constant].items() if k[1] == "2010"}
        if base.keys() != same.keys():
            raise ValueError(f"{current} and {constant} cover different regions in 2010")
        results.append(cleaning.compare_sources(base, same, 0, f"{constant} equals {current} in 2010, every region"))

    # BPS's Indonesia row equals the sum of the provinces in 2010-2012, within rounding
    years = [str(y) for y in NATIONAL_SUM_YEARS]
    for indicator in ["grdp_current", "grdp_constant_2010"]:
        parts, national = provincial_sums(levels[indicator])
        results.append(cleaning.check_sum(parts[years], national[years], TOL_NATIONAL_SUM,
                                          f"{indicator}: provinces sum to Indonesia (00), {years[0]}-{years[-1]}"))
    return results


def national_vs_provinces(levels):
    """Information on BPS's Indonesia row from 2013, when it stops being the provincial sum: the gap each year and the
    basis of 00 that year. Stops if 00 no longer tracks the provincial sum within TOL_NATIONAL_TRACK_PCT in 2013-2014,
    as the indicator notes state."""
    out = {}
    for indicator in ["grdp_current", "grdp_constant_2010"]:
        parts, national = provincial_sums(levels[indicator])
        out[indicator] = {}
        for p in national.index:
            if int(p) in NATIONAL_SUM_YEARS:
                continue

            # Each year from 2013 has one declared basis, and in 2013-2014 the gap must stay within the stated bound
            tracks = int(p) in NATIONAL_TRACK_YEARS
            if not tracks and int(p) not in NATIONAL_GDP_YEARS:
                raise ValueError(f"{indicator}: 00 in {p} has no declared basis")
            gap_pct = float((parts[p] / national[p] - 1) * 100)
            if tracks and abs(gap_pct) > TOL_NATIONAL_TRACK_PCT:
                raise ValueError(f"{indicator} {p}: the provincial sum differs from 00 by {gap_pct:.3f}%, beyond "
                                 f"{TOL_NATIONAL_TRACK_PCT}%, so 00 no longer tracks it")
            out[indicator][p] = {"provinces_sum": round(float(parts[p]), 2), "indonesia": float(national[p]),
                                 "gap": round(float(parts[p] - national[p]), 2), "gap_pct": round(gap_pct, 3),
                                 "basis": "tracks the provincial sum" if tracks else "national GDP"}
    return out


def exact_sum(cells, codes, period):
    """Return the sum of several codes' values in one period, added as decimals so that float rounding never enters."""
    return float(sum(Decimal(str(cells[(code, period)])) for code in codes))


def compare_quarterly(var, ours, copy, indicator):
    """Layer 4: var 286's annual totals of one indicator against the annual value of the total row of a quarterly
    table, their lower-priority copy. Same-border keys and border-mapped areas must agree within TOL_QUARTERLY, each
    declared known gap must stay exactly as declared, and every key left out must have a known reason."""
    label = f"{indicator} (var {STATUS_VAR}) against the annual total of var {var}, Rp billion"
    result = {"check": f"{indicator} (var {STATUS_VAR}, first in source_priority) equals its lower-priority copy in var "
                       f"{var}, Rp billion",
              "first": f"var {STATUS_VAR}",
              "second": f"var {var}: the year (turtahun {QUARTERLY_ANNUAL[0]} '{QUARTERLY_ANNUAL[1]}') of the total row "
                        f"(turvar {QUARTERLY_TOTAL[0]} '{QUARTERLY_TOTAL[1]}')"}

    # The copy's note must give every year the status var 286's note gives it, so that compared values share a status
    differ = [y for y in YEARS if NOTE_STATUS[var].get(y, "") != NOTE_STATUS[STATUS_VAR].get(y, "")]
    if differ:
        raise ValueError(f"var {var} and var {STATUS_VAR} give different statuses for {differ}")
    marked = and_list([f"{y} '{m}'" for y, m in NOTE_STATUS[STATUS_VAR].items()])
    result["statuses_equal"] = f"both notes give {marked}, and every other year of {YEARS[0]}-{YEARS[-1]} is final in both"

    # Keys both sources hold on the same borders, compared one to one within TOL_QUARTERLY
    same = {k: v for k, v in ours.items() if k in copy and k not in QUARTERLY_BORDERS}
    result["same_borders"] = cleaning.compare_sources(same, {k: copy[k] for k in same}, TOL_QUARTERLY,
                                                      f"{label}, same borders")

    # Keys on different borders, compared on the area both sources cover: a declared known gap must stay exactly as
    # declared, and every other area must agree within TOL_QUARTERLY
    result["border_areas"] = [{"key": list(k), "first": "+".join(a), "second": "+".join(b)}
                              for k, (a, b) in QUARTERLY_BORDERS.items()]
    first, second, known = {}, {}, []
    for key, (codes_ours, codes_copy) in QUARTERLY_BORDERS.items():
        a, b = exact_sum(ours, codes_ours, key[1]), exact_sum(copy, codes_copy, key[1])
        declared = KNOWN_GAPS.get((var,) + key)
        if declared is None:
            first[key], second[key] = a, b
            continue
        found = Decimal(str(b)) - Decimal(str(a))
        if found != declared:
            raise ValueError(f"var {var} {key}: {'+'.join(codes_copy)} minus var {STATUS_VAR}'s {'+'.join(codes_ours)} "
                             f"is {found}, but the build declares {declared}")
        known.append({"key": list(key), "first_codes": "+".join(codes_ours), "first": a,
                      "second_codes": "+".join(codes_copy), "second": b, "second_minus_first": float(found),
                      "declared": float(declared), "reason": KNOWN_GAP_REASON})
    result["border_mapped"] = cleaning.compare_sources(first, second, TOL_QUARTERLY, f"{label}, on the area both cover")
    result["known_differences"] = known

    # Every key only one source holds must be Indonesia, which the copy lacks, or lie inside a border-mapped area
    inside = {(code, k[1]) for k, (a, b) in QUARTERLY_BORDERS.items() for code in a + b}
    national, inside_ours, inside_copy = [], [], []
    for key in sorted(k for k in ours if k not in copy):
        if key[0] == cleaning.NATIONAL_CODE:
            national.append(list(key))
        elif key in inside:
            inside_ours.append(list(key))
        else:
            raise ValueError(f"var {var} lacks {key} for no known reason")
    for key in sorted(k for k in copy if k not in ours):
        if key not in inside:
            raise ValueError(f"var {var} holds {key}, which var {STATUS_VAR} lacks, for no known reason")
        inside_copy.append(list(key))
    result["not_compared"] = {
        f"Indonesia (00): var {var} has no Indonesia row": national,
        f"in var {STATUS_VAR} only, compared inside border_areas: var {var} holds 92 inside 91, and 95, 96 and 97 inside "
        f"94, until 2024": inside_ours,
        f"in var {var} only, compared inside border_areas: var {STATUS_VAR} holds 65 inside 64 until 2013": inside_copy,
        "in both on different borders, compared on the area both cover (border_mapped, known_differences)":
            [list(k) for k in QUARTERLY_BORDERS],
    }
    return result


def real_growth(levels):
    """Return real growth in percent from a constant-price level table, for every region with a value the year before."""
    out = {}
    for code, period in sorted(levels):
        before = levels.get((code, str(int(period) - 1)))
        if before is not None:
            out[(code, period)] = (levels[(code, period)] / before - 1) * 100
    return out


def old_area_grdp(levels):
    """Return a function giving the GRDP at constant 2010 prices of the area several codes cover together."""
    grdp = levels["grdp_constant_2010"]
    return lambda codes, period: sum(grdp[(c, period)] for c in codes)


def old_area_per_capita(levels):
    """Return a function giving the GRDP per capita at constant 2010 prices of the area several codes cover together:
    their GRDP over their population, each code's population being its GRDP over its GRDP per capita."""
    grdp, per_capita = levels["grdp_constant_2010"], levels["grdp_per_capita_constant_2010"]
    return lambda codes, period: (sum(grdp[(c, period)] for c in codes)
                                  / sum(grdp[(c, period)] / per_capita[(c, period)] for c in codes))


def national_evidence(levels, gdp_growth, var_291, var_296):
    """Return a function giving, for a 00 key listed apart in the per capita comparison, the figures behind its
    reason: 00's GDP growth computed and as var 291 publishes it, the population growth var 286 and var 288 imply, and
    the GDP growth that var 296 gives with that population growth."""
    grdp, per_capita = levels["grdp_constant_2010"], levels["grdp_per_capita_constant_2010"]

    def evidence(key):
        code, period = key
        if code != cleaning.NATIONAL_CODE:
            return {}
        people = [grdp[(code, p)] / per_capita[(code, p)] for p in (str(int(period) - 1), period)]
        population = (people[1] / people[0] - 1) * 100
        implied = ((1 + var_296[key] / 100) * (1 + population / 100) - 1) * 100
        return {"gdp_growth_computed": round(gdp_growth[key], 4), "var_291": var_291.get(key),
                "population_growth_implied": round(population, 4), "gdp_growth_implied_by_var_296": round(implied, 4)}
    return evidence


def within(computed, published, decimals):
    """Return whether a computed growth, rounded as the growth table publishes it, lies within TOL_GROWTH of the
    published value, compared as decimals."""
    return abs(Decimal(str(round(computed, decimals))) - Decimal(str(published))) <= Decimal(str(TOL_GROWTH))


def compare_growth(var, levels_var, indicator, levels, growth, published, decimals, old_area_level, old_area_formula,
                   apart, evidence):
    """Layer 4: growth computed from a level table, rounded as growth table var publishes it, against that table within
    TOL_GROWTH. Border changes, the basis change of 00 and the keys in apart are listed apart with their reasons, and
    the build stops if one of them no longer behaves as its reason states."""
    table, source = f"var {var}", f"var {levels_var}"

    # Keys across a border or basis change, and the keys in apart, are listed apart below
    listed = set(BORDER_CHANGES) | set(BASIS_CHANGES) | set(apart)
    first = {k: round(v, decimals) for k, v in growth.items() if k not in listed}
    second = {k: v for k, v in published.items() if k not in listed}
    result = cleaning.compare_sources(first, second, TOL_GROWTH,
                                      f"real growth computed from {indicator} equals {table} (percent)")
    result["computed_rounded_to_decimals"] = decimals
    result["largest_gap_before_rounding"] = round(max(abs(growth[k] - second[k]) for k in first if k in second), 6)

    # Keys that only one side has are listed, not compared
    result["not_compared"] = {
        f"computed, but {table} has no value": [list(k) for k in sorted(first) if k not in second],
        f"in {table}, but {source} has no value the year before": [list(k) for k in sorted(second) if k not in first],
    }

    # Each border change: the computed growth, the published value, and the growth of the area the province had the
    # year before, which must give the published value exactly when the declared reason says so
    result["old_area_growth_formula"] = old_area_formula
    result["border_changes"] = []
    for key, change in BORDER_CHANGES.items():
        code, period = key
        old_growth = (old_area_level(change["old_area"], period) / levels[(code, str(int(period) - 1))] - 1) * 100
        if (within(old_growth, published[key], decimals) != change["old_area_reproduces"]
                or within(growth[key], published[key], decimals)):
            raise ValueError(f"{table} {key}: {published[key]} against computed {growth[key]:.4f} and old_area_growth "
                             f"{old_growth:.4f}; the declared reason no longer holds")
        result["border_changes"].append({
            "province_code": code, "period": period, "computed": round(growth[key], 4), f"var_{var}": published[key],
            "old_area": "+".join(change["old_area"]), "old_area_growth": round(old_growth, 4),
            "reason": change["reason"].format(table=table, levels=source)})

    # The basis change of 00 and the other keys listed apart: a published value must still differ from the computed
    # growth beyond TOL_GROWTH, so that a key that agrees again is compared again
    for name, reasons in [("basis_changes", BASIS_CHANGES), ("listed_apart", apart)]:
        if not reasons:
            continue
        result[name] = []
        for key, reason in reasons.items():
            value = published.get(key)
            if value is not None and within(growth[key], value, decimals):
                raise ValueError(f"{table} {key}: {value} now matches the computed {growth[key]:.4f}; compare it again")
            detail = (f"{table} publishes no value for it" if value is None
                      else BASIS_DETAIL.get(var) if key in BASIS_CHANGES else None)
            result[name].append({"province_code": key[0], "period": key[1], "computed": round(growth[key], 4),
                                 f"var_{var}": value, **evidence(key),
                                 "reason": reason + (f"; {detail}" if detail else "")})
    return result


def read_check_dataset():
    """Read the 2020-2025 GRDP totals, their statuses and the population of the check dataset."""
    c = CHECK_CONTEXT

    # The check dataset must still be in the shared format and in the units this script expects
    meta = json.loads(CHECK_META.read_text(encoding=c["encoding"]))
    if meta["format"] != cleaning.CSV_FORMAT:
        raise ValueError(f"{CHECK_META.name}: format {meta['format']}")
    for indicator, unit in c["units"].items():
        if meta["indicators"][indicator]["unit"] != unit:
            raise ValueError(f"{CHECK_META.name}: {indicator} unit {meta['indicators'][indicator]['unit']!r}, expected {unit!r}")

    # Parse every value used as text against the shared format
    rows = cleaning.read_csv_rows(CHECK_CSV, c["encoding"], c["delimiter"])
    if rows[0] != KEYS + ["status", "value"]:
        raise ValueError(f"{CHECK_CSV.name}: header {rows[0]}")
    grdp, marks, population = {}, {}, {}
    for code, indicator, sector, period, status, value in rows[1:]:
        if not (period.isdigit() and int(period) in CHECK_YEARS):
            continue
        if indicator == "grdp_current" and sector == "TOTAL":
            grdp[(code, period)] = cleaning.parse_number(value, c["decimal"], c["thousands"])
            marks[(code, period)] = status
        elif indicator == "population":
            population[(code, period)] = cleaning.parse_number(value, c["decimal"], c["thousands"])
    return grdp, marks, population


def compare_check_dataset(levels, statuses, grdp, marks, pre_split):
    """Layer 4: grdp_current 2020-2025 against the check dataset, exactly, with the output rows' statuses equal."""
    ours = {k: levels[k] for k in sorted(levels) if int(k[1]) in CHECK_YEARS}

    # 91 and 94 in 2023 are on different borders in the two datasets, so they are listed apart below
    first = {k: v for k, v in ours.items() if k not in CHECK_PRE_SPLIT}
    second = {k: v for k, v in grdp.items() if k not in CHECK_PRE_SPLIT}
    result = cleaning.compare_sources(first, second, 0, f"grdp_current 2020-2025 equals TOTAL in {CHECK_CSV.name}")

    # The check dataset must hold nothing this dataset lacks, and every compared value must carry the same status
    extra = [k for k in second if k not in first]
    if extra:
        raise ValueError(f"{CHECK_CSV.name} has keys this dataset lacks: {extra[:5]}")
    differ = [k for k in first if k in second and statuses[k] != marks[k]]
    if differ:
        raise ValueError(f"statuses differ from {CHECK_CSV.name} at {differ[:5]}")
    result["statuses_equal"] = result["compared"]

    # Every key the check dataset lacks must have a known reason: it has no Indonesia GRDP row, and it holds the
    # new Papua provinces inside 91 and 94 in 2023
    inside_pre_split = {(c, period) for code, period in CHECK_PRE_SPLIT
                        for c in BORDER_CHANGES[(code, period)]["old_area"] if c != code}
    no_national, not_split = [], []
    for code, period in (k for k in first if k not in second):
        if code == cleaning.NATIONAL_CODE:
            no_national.append([code, period])
        elif (code, period) in inside_pre_split:
            not_split.append([code, period])
        else:
            raise ValueError(f"{CHECK_CSV.name} lacks {(code, period)} for no known reason")
    result["not_compared"] = {
        f"Indonesia (00): {CHECK_CSV.name} has no national GRDP row": no_national,
        f"new Papua provinces in 2023: {CHECK_CSV.name} holds them inside 91 and 94 until 2024": not_split}

    # The 2023 Papua values: this dataset's post-split value, the check dataset's pre-split value, the sum of the
    # post-split codes that cover the pre-split area, and the pre-split value BPS publishes in var 2268
    result["pre_split_2023"] = []
    for code, period in CHECK_PRE_SPLIT:
        codes = BORDER_CHANGES[(code, period)]["old_area"]
        old_area = round(sum(levels[(c, period)] for c in codes), 2)
        result["pre_split_2023"].append({
            "province_code": code, "period": period, "this_dataset_post_split": levels[(code, period)],
            "check_dataset_pre_split": grdp[(code, period)], "old_area": "+".join(codes),
            "old_area_sum_this_dataset": old_area, "check_minus_old_area_sum": round(grdp[(code, period)] - old_area, 2),
            "var_2268_pre_split": pre_split[(code, period)]})
    return result


def implied_population_check(levels, population):
    """Layer 5: the population implied by GRDP and GRDP per capita against the check dataset's population."""
    # Thousand people = 1000 x Rp billion / Rp thousand per person
    implied = {k: 1000 * v / levels["grdp_per_capita_current"][k]
               for k, v in levels["grdp_current"].items() if int(k[1]) in CHECK_YEARS}

    # Compare one to one, except the 2023 Papua values, which the check dataset holds on the pre-split borders
    comparisons = []
    for (code, period), people in population.items():
        codes = BORDER_CHANGES[(code, period)]["old_area"] if (code, period) in CHECK_PRE_SPLIT else [code]
        value = sum(implied[(c, period)] for c in codes)
        comparisons.append({"province_code": code, "period": period, "codes": codes, "implied": value,
                            "population": people, "gap_pct": (value / people - 1) * 100})

    # Every implied value must enter one comparison
    covered = sorted((c, r["period"]) for r in comparisons for c in r["codes"])
    if covered != sorted(implied):
        raise ValueError("implied population and the check dataset's population cover different keys")

    # Flag gaps outside each year group's range
    flags = []
    for check, years in IMPLIED_POPULATION_YEARS.items():
        flags += cleaning.flag_outside(
            [{"province_code": r["province_code"], "period": r["period"],
              **({"area": "+".join(r["codes"])} if len(r["codes"]) > 1 else {}), "value": r["gap_pct"]}
             for r in comparisons if int(r["period"]) in years], check, *PLAUSIBLE[check])

    # Summarise the largest gap in each year, and give the pre-split comparisons in full
    summary = {"formula": "implied population (thousand) = 1000 x grdp_current / grdp_per_capita_current; "
                          "gap_pct = (implied / population - 1) x 100",
               "by_year": {}, "pre_split_2023": []}
    for year in CHECK_YEARS:
        group = [r for r in comparisons if r["period"] == str(year)]
        worst = max(group, key=lambda r: abs(r["gap_pct"]))
        summary["by_year"][str(year)] = {"compared": len(group), "largest_abs_gap_pct": round(abs(worst["gap_pct"]), 4),
                                         "at": "+".join(worst["codes"])}
    for r in comparisons:
        if len(r["codes"]) > 1:
            summary["pre_split_2023"].append({"province_code": r["province_code"], "period": r["period"],
                                              "old_area": "+".join(r["codes"]), "implied": round(r["implied"], 3),
                                              "population": r["population"], "gap_pct": round(r["gap_pct"], 4)})
    return flags, summary


def growth_flags(growth):
    """Layer 5: real growth outside its plausible range; years across a border or basis change compare different
    areas or bases and are skipped."""
    return cleaning.flag_outside([{"province_code": c, "period": p, "value": v} for (c, p), v in growth.items()
                                  if (c, p) not in BORDER_CHANGES and (c, p) not in BASIS_CHANGES],
                                 "real_growth_pct", *PLAUSIBLE["real_growth_pct"])


def basis_evidence(basis_291, basis_296):
    """Return, for the notes, what vars 291 and 296 give for 00 in the first year on the national GDP basis: var 291's
    growth (or that it publishes none), and the GDP growth var 296's per capita growth gives with the population growth
    var 286 and var 288 imply, against the growth of the 00 levels."""
    year = NATIONAL_GDP_YEARS[0]
    gdp = "publishes no 00 growth" if basis_291 is None else f"gives 00 growth of {basis_291}%"
    return (f"var 291 {gdp} for {year}, and var 296's 00 per capita growth for {year}, {basis_296['var_296']}%, gives GDP "
            f"growth of {round(basis_296['gdp_growth_implied_by_var_296'], 2)}% with the population growth var 286 and "
            f"var 288 imply ({round(basis_296['population_growth_implied'], 2)}%), against "
            f"{round(basis_296['gdp_growth_computed'], 2)}% from the 00 levels")


def national_note(gaps, evidence):
    """Return the note on 00 for a var 286 indicator, written from the declared years, the indicator's gaps between
    the provincial sum and 00 by year, and the evidence of the basis change."""
    track_year, basis_year = str(NATIONAL_TRACK_YEARS[-1]), str(NATIONAL_GDP_YEARS[0])
    national_gdp = [gaps[str(y)]["gap_pct"] for y in NATIONAL_GDP_YEARS]
    return (f"00 = Indonesia: the national row BPS publishes in the same table (vervar 9999 INDONESIA), whose basis "
            f"changes between {track_year} and {basis_year}. In {NATIONAL_SUM_YEARS[0]}-{track_year} it tracks the "
            f"provincial sum: exactly, to rounding, in {NATIONAL_SUM_YEARS[0]}-{NATIONAL_SUM_YEARS[-1]} "
            f"(checks.identities), and within {TOL_NATIONAL_TRACK_PCT}% in {NATIONAL_TRACK_YEARS[0]}-{track_year}. In "
            f"{basis_year}-{NATIONAL_GDP_YEARS[-1]} it is national GDP, from which the provincial sum differs by "
            f"{min(national_gdp)}% to {max(national_gdp)}% (BPS note: statistical discrepancy); the gap steps from "
            f"{gaps[track_year]['gap_pct']}% in {track_year} to {gaps[basis_year]['gap_pct']}% in {basis_year}. The "
            f"{basis_year} year-on-year change of 00 therefore compares different bases, and the growth comparisons in "
            f"checks.cross_source list it apart (basis_changes): {evidence}. Gaps by year, with the basis of each, in "
            f"checks.national_vs_provinces.")


def per_capita_note(basis):
    """Return the note on 00 for a var 288 indicator, written from the declared years and var 296's entry for the
    basis change of 00."""
    track_year, basis_year = NATIONAL_TRACK_YEARS[-1], NATIONAL_GDP_YEARS[0]
    return (f"00 = Indonesia: GDP per capita, var 286's 00 over BPS's population, so it changes basis with var 286's 00 "
            f"between {track_year} and {basis_year}, and its {basis_year} year-on-year change compares different bases. "
            f"At constant 2010 prices the computed growth is {round(basis['computed'], 2)}% against var 296's "
            f"{basis['var_296']}%, listed apart in checks.cross_source (basis_changes), while the population var 286 and "
            f"var 288 imply grows {round(basis['population_growth_implied'], 2)}% in {basis_year}.")


def describe_var(var, table):
    """Describe one WebAPI table for the metadata: role, label, unit, breakdowns, release, note and files."""
    v = table["var"][0]
    return {
        "role": ROLES[var],
        **({"read": f"turvar {QUARTERLY_TOTAL[0]} '{QUARTERLY_TOTAL[1]}' (the total row) in turtahun "
                    f"{QUARTERLY_ANNUAL[0]} '{QUARTERLY_ANNUAL[1]}' (the year); the 17 industry categories and the "
                    f"quarters are not read"} if var in QUARTERLY_VARS else {}),
        "label": v["label"].strip(),
        "subject": v["subj"],
        "unit": v["unit"],
        "decimals": v["decimal"],
        "turvar": {str(t["val"]): t["label"] for t in table["turvar"]},
        "regions": table["labelvervar"],
        "last_update": table["last_update"],
        "note": cleaning.html_to_text(v["note"]),
        "note_statuses": NOTE_STATUS[var],
        "request": URL_WEBAPI.format(var=var) + " (th = first:last year minus 1900, such as 110:112 for 2010-2012; "
                                                "the key is not stored)",
        "download_script": RAW_DOWNLOAD_SCRIPT,
        "files": [posix(p) for p in RAW_WEBAPI[var].values()],
    }


# Steps

# Read the BPS province list that every region name and code is matched against; load_bps_provinces reads UTF-8
# JSON, so a list declared in another encoding stops the build
if READ_CONTEXT[RAW_PROVINCES]["encoding"] != "utf-8":
    raise ValueError(f"{RAW_PROVINCES.name}: READ_CONTEXT declares {READ_CONTEXT[RAW_PROVINCES]}, but "
                     f"load_bps_provinces reads UTF-8")
provinces, lookup = cleaning.load_bps_provinces(RAW_PROVINCES)

# The priority order must name first the var whose values the CSV holds; the later vars are the quarterly copies
written = {indicator: var for (var, _), indicator in INDICATORS.items()}
if {indicator: sources[0] for indicator, sources in SOURCE_PRIORITY.items()} != written:
    raise ValueError(f"SOURCE_PRIORITY {SOURCE_PRIORITY} does not start with the vars the CSV holds, {written}")
copies = {var: indicator for indicator, sources in SOURCE_PRIORITY.items() for var in sources[1:]}
if sorted(copies) != sorted(QUARTERLY_VARS):
    raise ValueError(f"the lower-priority copies {sorted(copies)} are not the quarterly tables {QUARTERLY_VARS}")

# Read the annual tables (vars 286, 288, 291 and 296) and the annual total of the quarterly tables (vars 2267 and
# 2268), six files each, into one description and one value map per var
tables, values = {}, {}
for var in ANNUAL_VARS:
    tables[var], values[var] = read_var(var, lookup)
for var in QUARTERLY_VARS:
    tables[var], values[var] = read_quarterly(var, lookup)

# Each var's note must still state the statuses this script declares; var 286's statuses apply to every row, and
# var 296's note must give the same, which confirms them for the per capita rows
for var, table in tables.items():
    found = cleaning.parse_status_note(table["var"][0]["note"])
    if found != NOTE_STATUS[var]:
        raise ValueError(f"var {var} note gives {found}, the script declares {NOTE_STATUS[var]}")
if NOTE_STATUS[PER_CAPITA_STATUS_VAR] != NOTE_STATUS[STATUS_VAR]:
    raise ValueError(f"var {PER_CAPITA_STATUS_VAR}'s note no longer confirms var {STATUS_VAR}'s statuses for the "
                     f"per capita rows")
status_by_year = {str(year): mark for year, mark in NOTE_STATUS[STATUS_VAR].items()}

# Name each level table by its indicator, and turn it into long rows with the status of their year
levels = {indicator: values[var][turvar] for (var, turvar), indicator in INDICATORS.items()}
rows = [row(code, indicator, period, value, status_by_year.get(period, ""))
        for indicator, cells in levels.items() for (code, period), value in cells.items()]

# Layer 3: constant equals current prices in 2010, and provinces sum to Indonesia in 2010-2012; stops on failure
identities = identity_checks(levels)

# Layer 4: var 286's annual totals against their lower-priority copies, the annual total of vars 2268 and 2267, on the
# same borders and on the areas both cover; stops on any gap beyond TOL_QUARTERLY that is not declared exactly
quarterly_checks = [compare_quarterly(var, levels[indicator], values[var], indicator) for var, indicator in copies.items()]

# State why both quarterly comparisons share one tolerance, with the largest gap found in either
largest = max(c[part]["largest_gap"] for c in quarterly_checks for part in ("same_borders", "border_mapped"))
for check in quarterly_checks:
    check["tolerance_reason"] = (f"{TOL_QUARTERLY_REASON}; one tolerance of {TOL_QUARTERLY} serves both quarterly "
                                 f"tables, and the largest gap found in either is {largest}")

# Layer 4: real growth computed from grdp_constant_2010 against var 291, within TOL_GROWTH; stops on failure
growth = real_growth(levels["grdp_constant_2010"])
growth_check = compare_growth(
    291, 286, "grdp_constant_2010", levels["grdp_constant_2010"], growth, values[291]["0"],
    tables[291]["var"][0]["decimal"], old_area_grdp(levels),
    "(GRDP of old_area in year t / GRDP of the province in year t-1 - 1) x 100, at constant 2010 prices",
    {}, lambda key: {})

# Layer 4: real growth of GRDP per capita computed from grdp_per_capita_constant_2010 against var 296, within
# TOL_GROWTH; stops on failure
per_capita_check = compare_growth(
    296, 288, "grdp_per_capita_constant_2010", levels["grdp_per_capita_constant_2010"],
    real_growth(levels["grdp_per_capita_constant_2010"]), values[296]["0"], tables[296]["var"][0]["decimal"],
    old_area_per_capita(levels),
    "(GRDP per capita of old_area in year t / GRDP per capita of the province in year t-1 - 1) x 100, at constant 2010 "
    "prices; the GRDP per capita of old_area is its GRDP over its population, each code's population being its GRDP "
    "over its GRDP per capita",
    PER_CAPITA_APART, national_evidence(levels, growth, values[291]["0"], values[296]["0"]))

# Layer 4: grdp_current 2020-2025 against the check dataset, exactly and with equal statuses; stops on failure
check_grdp, check_marks, check_population = read_check_dataset()
row_status = {(r["province_code"], r["period"]): r["status"] for r in rows if r["indicator"] == "grdp_current"}
dataset_check = compare_check_dataset(levels["grdp_current"], row_status, check_grdp, check_marks, values[2268])

# Layer 5: real growth and the implied population inside their plausible ranges; outliers are only flagged
flags = growth_flags(growth)
population_flags, population_summary = implied_population_check(levels, check_population)
flags += population_flags

# Information for the metadata: BPS's Indonesia row against the provincial sum from 2013, with its basis each year;
# stops if 00 no longer tracks the provincial sum in 2013-2014 as the notes state
national = national_vs_provinces(levels)

# Evidence of the basis change of 00 for the notes, written from what vars 291 and 296 give for 00 in 2015, so that it
# cannot go stale
basis_key = (cleaning.NATIONAL_CODE, str(NATIONAL_GDP_YEARS[0]))
basis_296 = next(e for e in per_capita_check["basis_changes"] if (e["province_code"], e["period"]) == basis_key)
basis_text = basis_evidence(values[291]["0"].get(basis_key), basis_296)

# Status statements for the metadata, written from the declared note statuses so that they cannot go stale
status_text = " and ".join(f"{year} '{mark}'" for year, mark in status_by_year.items())
stale_text = " and ".join(f"{year} '{mark}'" for year, mark in NOTE_STATUS[288].items())
confirm_text = " and ".join(f"{year} '{mark}'" for year, mark in NOTE_STATUS[PER_CAPITA_STATUS_VAR].items())
final_by_override = [str(y) for y in NOTE_STATUS[288] if str(y) not in status_by_year]
check_folder = posix(CHECK_CSV.parent) + "/"
copy_text = {indicator: " and ".join(f"var {v}" for v in sources[1:]) for indicator, sources in SOURCE_PRIORITY.items()}
growth_apart = and_list(sorted({p for _, p in BASIS_CHANGES}))
per_capita_apart = and_list(sorted({p for _, p in BASIS_CHANGES} | {p for _, p in PER_CAPITA_APART}))

# Describe the dataset
meta = {
    "title": "BPS provincial GRDP at current and constant 2010 prices, and GRDP per capita, Indonesia, 2010-2025",
    "columns": {
        "province_code": "BPS province code (kode_bps); 00 = Indonesia, whose basis changes between 2014 and 2015 "
                         "(see the notes of each indicator). Names and Kemendagri codes in 'provinces'.",
        "indicator": "Indicator code; definitions in 'indicators'.",
        "sector": "TOTAL for every row: GRDP over all industries.",
        "period": "YYYY = calendar year.",
        "status": "BPS revision marker; meanings in 'status'.",
        "value": "Number in the indicator's unit, as published by BPS. Multiply by 'multiplier' for base units.",
    },
    "provinces": provinces,
    "province_source": {"url": URL_PROVINCES, "file": posix(RAW_PROVINCES),
                        "note": "BPS and Kemendagri codes differ for the six Papua provinces; join other datasets on the code system they use."},
    "sectors": SECTORS,
    "indicators": {
        indicator: {
            **INDICATOR_INFO[indicator],
            "periods": f"{YEARS[0]}-{YEARS[-1]} annual",
            "source": f"BPS WebAPI var {var} '{tables[var]['var'][0]['label'].strip()}', turvar {turvar} "
                      f"'{dict(TURVARS[var])[turvar]}'"
                      + (f"; {copy_text[indicator]} repeats it as a lower-priority copy, read only as a check"
                         if copy_text[indicator] else "") + "; see 'source_priority' and 'source_tables'",
            "notes": ([national_note(national[indicator], basis_text)]
                      if var == STATUS_VAR else
                      ["Published by BPS (var 288), not derived here: BPS divides GRDP by its own population estimate for the "
                       "year.",
                       per_capita_note(basis_296),
                       f"1000 x grdp_current / grdp_per_capita_current gives that population in thousands; "
                       f"checks.implied_population compares it with the population in {check_folder}."]),
        }
        for (var, turvar), indicator in INDICATORS.items()
    },
    "source_priority": {indicator: [f"var {v}" for v in sources] for indicator, sources in SOURCE_PRIORITY.items()},
    "coverage": coverage(provinces),
    "borders": [
        "64 (Kalimantan Timur) in 2010-2012 includes Kalimantan Utara; 65 (Kalimantan Utara) has its own values from 2013.",
        "91 (Papua Barat) and 94 (Papua) in 2010-2022 cover the pre-split provinces: Papua Barat then included Papua Barat "
        "Daya, and Papua included Papua Selatan, Papua Tengah and Papua Pegunungan. From 2023, 91 and 94 cover the "
        "post-split areas, and 92 (Papua Barat Daya), 95 (Papua Selatan), 96 (Papua Tengah) and 97 (Papua Pegunungan) start.",
        "On fixed borders: Kalimantan Timur (pre-2013 area) = 64 + 65 from 2013; Papua Barat (pre-2023 area) = 91 + 92 and "
        "Papua (pre-2023 area) = 94 + 95 + 96 + 97 from 2023.",
        "A year-on-year change across a border change compares different areas: 64 in 2013, 91 and 94 in 2023.",
        f"These annual tables split Papua from 2023, one year before the sector GRDP tables (vars 2267 and 2268), the "
        f"population tables and {check_folder}, which keep 91 and 94 on the pre-split borders in 2023; join 2023 "
        f"with those on the sums 91 + 92 and 94 + 95 + 96 + 97. Kalimantan Utara has its own values from 2010 in the "
        f"sector GRDP tables but from 2013 here.",
        "checks.cross_source compares var 286 with vars 2267 and 2268 on the area both cover (border_areas): var 286's 64 "
        "in 2010-2012 against their 64 + 65, and their pre-split 91 and 94 in 2023 against var 286's 91 + 92 and 94 + 95 + "
        "96 + 97. Vars 2267 and 2268 are the source of these pre-split check values.",
    ],
    "source_tables": {str(var): describe_var(var, table) for var, table in tables.items()},
    "notes": [
        f"status: var {STATUS_VAR}'s note gives {status_text}; every row of those years carries that status, in every "
        f"indicator, and other years are final. The WebAPI gives no status per cell.",
        f"var 288's own note gives {stale_text}, one release behind its values: the table holds "
        f"{max(int(p) for _, p in levels['grdp_per_capita_current'])} and was last updated {tables[288]['last_update']} "
        f"(var {STATUS_VAR}: {tables[STATUS_VAR]['last_update']}). var {STATUS_VAR}'s year statuses are therefore applied "
        f"to the per capita rows, so {', '.join(final_by_override)} is final there as well. var {PER_CAPITA_STATUS_VAR}'s "
        f"note, on the growth of the same per capita series (last updated {tables[PER_CAPITA_STATUS_VAR]['last_update']}), "
        f"gives {confirm_text}, which confirms these statuses for the per capita rows independently of var 288.",
        f"The statuses equal those of grdp_current in {check_folder}, which come from the BPS quarterly GRDP "
        f"table note; checked for every compared value. They also equal the statuses the notes of "
        f"{and_list([f'var {v}' for v in copies])} give each year (checks.cross_source, statuses_equal).",
        f"Values in two raw files: source_priority lists the vars that publish each indicator, in priority order. var "
        f"{STATUS_VAR} gives every grdp_current and grdp_constant_2010 value; {copy_text['grdp_current']} and "
        f"{copy_text['grdp_constant_2010']} (BPS quarterly GRDP by industry, at current and at constant 2010 prices) "
        f"repeat them as the annual value ('{QUARTERLY_ANNUAL[1]}') of their total row ('{QUARTERLY_TOTAL[1]}') and are "
        f"read only as lower-priority copies: compared in checks.cross_source, never written to the CSV. They are also "
        f"the source of the pre-split check values there: 64 + 65 (Kalimantan Timur with Kalimantan Utara) in 2010-2012, "
        f"and 91 (Papua Barat) and 94 (Papua) on their pre-split borders in 2023. Within each var, the six files cover "
        f"disjoint years.",
        "vars 291 and 296 (real growth of GRDP and of GRDP per capita) are read only as checks and are not in the CSV.",
        f"Derived values are not stored. Real growth (%) = (grdp_constant_2010 in year t / grdp_constant_2010 in year "
        f"t-1 - 1) x 100, which equals var 291 within {TOL_GROWTH} percentage points except across a border change and "
        f"for 00 in {growth_apart}. Real growth of GRDP per capita (%) is the same formula on "
        f"grdp_per_capita_constant_2010, which equals var 296 within {TOL_GROWTH} percentage points except across a "
        f"border change and for 00 in {per_capita_apart}. GRDP per capita is published by BPS, not derived.",
    ],
    "check_datasets": {
        "build_order": f"{check_folder} must be rebuilt before this dataset: this build reads its CSV and metadata as "
                       f"checks and records their hashes as they are when it runs",
        "files": {posix(p): {"sha256": cleaning.sha256(p)} for p in [CHECK_CSV, CHECK_META]},
    },
    "checks": {
        "passed": ["identities", "cross-source"],
        "identities": identities,
        "cross_source": [*quarterly_checks, growth_check, per_capita_check, dataset_check],
        "national_vs_provinces": national,
        "implied_population": population_summary,
        "plausible_ranges": PLAUSIBLE,
        "flags": flags,
    },
}

# Layers 1, 2 and 6: check structure and completeness, then write the CSV and metadata
raw_files = [RAW_PROVINCES] + [p for files in RAW_WEBAPI.values() for p in files.values()]
out = cleaning.write_dataset(
    rows, KEYS,
    allowed={"province_code": provinces, "indicator": list(INDICATORS.values()), "sector": list(SECTORS)},
    expected=expected_keys(provinces),
    csv_path=OUT_CSV, meta=meta, raw_files=raw_files,
    sort_orders={"indicator": list(INDICATORS.values())},
)

# Report what was written
print(f"{OUT_CSV.name}: {len(out)} rows, {len(flags)} plausibility flags")
print(out.groupby(["indicator", "status"]).size().to_string())
for f in flags:
    print("  flag:", f)
