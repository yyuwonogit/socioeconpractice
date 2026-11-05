from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# Load the shared cleaning module from tools/
import sys
sys.path.insert(0, str(ROOT / "tools"))
import cleaning

# Modules for the checks: json for the check datasets' metadata, math for a range open above, Decimal for the declared
# gap, pandas for the sums
import json
import math
from decimal import Decimal

import pandas as pd

# Parameters

# Raw inputs: the BPS province list, and the BPS WebAPI downloads of var 534 (GRDP by expenditure at current prices,
# Rp billion) and var 542 (each component's share of that GRDP, percent), each in the six year ranges the download
# script requested. var 534 gives every grdp_current value in the CSV and var 542 every grdp_distribution_current value
RAW_PROVINCES = ROOT / "raw/province-codes/20261102_bps-province-codes-2025-s1.json"
RAW_DOWNLOAD_SCRIPT = "raw/grdp/20261104_download-bps-api-grdp-by-expenditure-2010-2025.py"
YEAR_RANGES = [(2010, 2012), (2013, 2015), (2016, 2018), (2019, 2021), (2022, 2023), (2024, 2025)]
RAW_NAMES = {534: "grdp-by-expenditure-by-province", 542: "grdp-distribution-by-expenditure-by-province"}
RAW_WEBAPI = {var: {span: ROOT / f"raw/grdp/20261104_bps-api-var{var}-{name}-{span[0]}-{span[1]}.json"
                    for span in YEAR_RANGES} for var, name in RAW_NAMES.items()}

# Output; the metadata JSON is written beside it with a -metadata suffix
OUT_CSV = HERE / "20261104_bps-province-grdp-by-expenditure-2010-2025.csv"

# Cells the 2019-2021 files hold under turvar codes the tables' turvar lists do not name, read from opening the files:
# in var 534 codes 686-690, 693 and 694 for 2019 (the year and its quarters) and 2020 Q1-Q2, and in var 542 the same
# codes for 2020 Q1-Q2, each for the 34 provinces of those years. read_webapi_table sets them aside, the build stops
# unless they are exactly these, and none is written
UNLISTED_CODES = [686, 687, 688, 689, 690, 693, 694]
UNLISTED = {
    (534, (2019, 2021)): ["2019", "2019Q1", "2019Q2", "2019Q3", "2019Q4", "2020Q1", "2020Q2"],
    (542, (2019, 2021)): ["2020Q1", "2020Q2"],
}
# The listed component each unlisted code lies nearest, found by value when the files were opened, and the factor
# that puts the unlisted values on the listed unit: var 534's unlisted values are about 1000 times the listed ones (Rp
# million rather than Rp billion), and var 542's are percentages like the listed ones. The build stops unless every
# code still lies nearest its declared component
UNLISTED_NEAREST = {686: "PKRT", 687: "PKLNPRT", 688: "PKP", 689: "PMTB", 690: "PI", 693: "NETEKSPOR", 694: "TOTAL"}
UNLISTED_SCALE = {534: 1000, 542: 1}

# How each raw file is written, read from opening all 13 files. The province list is UTF-8 JSON without a byte-order
# mark: 38 records whose four fields (kode_bps, nama_bps, kode_dagri, nama_dagri) are all text, so it holds no numbers,
# units or missing values. The 12 WebAPI files are UTF-8 JSON without a byte-order mark: values are JSON numbers with a
# decimal point and no thousands separator, var 534's unit field reads 'Milyar Rupiah' and var 542's 'Persen', each
# var's decimal field is 2, a value BPS does not publish is a key absent from datacontent (the four new Papua provinces
# before 2024, and the TOTAL row in every year; no markers), and the two 2019-2021 files also hold the unlisted cells
UNITS = {534: "Milyar Rupiah", 542: "Persen"}
READ_CONTEXT = {
    RAW_PROVINCES: {"encoding": "utf-8", "numbers": "none: every code and name is a JSON string",
                    "missing": "none: every record carries kode_bps, nama_bps, kode_dagri and nama_dagri",
                    "unit": None},
    **{path: {"encoding": "utf-8", "numbers": "JSON numbers, decimal point, no thousands separator",
              "missing": "key absent from datacontent", "var": var, "unit": UNITS[var], "decimals": 2,
              "unlisted_turvar": (var, span) in UNLISTED}
       for var, files in RAW_WEBAPI.items() for span, path in files.items()},
}

# The one number format and missing-value convention cleaning.read_webapi_table reads: each value a JSON number, and
# a key absent from datacontent for a value BPS does not publish; a WebAPI file declared otherwise stops the build
WEBAPI_READS = {"numbers": "JSON numbers, decimal point, no thousands separator",
                "missing": "key absent from datacontent"}

# Text each var's label must still carry, so that a different table under the same number stops the build, and the
# text of the region list each file must name
VAR_LABELS = {534: "[SERI 2010] 1. PDRB Atas Dasar Harga Berlaku Menurut Pengeluaran",
              542: "[SERI 2010] 3. Distribusi PDRB Atas Dasar Harga Berlaku Menurut Pengeluaran"}
LABEL_VERVAR = "Provinsi (PDRB)"

# The row BPS lists after the 38 provinces, which holds no value in any file, so the dataset has no Indonesia row
EMPTY_ROW = (9999, "TOTAL")

# Output indicator of each var, in output order, with its name, unit and multiplier to base units; grdp_current uses
# the code and unit of data/20261103_bps-province-grdp-2010-2025 and data/20261103_bps-province-grdp-by-industry-2010-2025
INDICATORS = {534: "grdp_current", 542: "grdp_distribution_current"}
VAR_OF = {indicator: var for var, indicator in INDICATORS.items()}
INDICATOR_INFO = {
    "grdp_current": {"name": "PDRB atas dasar harga berlaku menurut pengeluaran (GRDP by expenditure at current "
                             "prices), Seri 2010",
                     "unit": "Rp billion (Milyar Rupiah)", "multiplier": 1e9, "base_unit": "Rp"},
    "grdp_distribution_current": {"name": "Distribusi PDRB atas dasar harga berlaku menurut pengeluaran (each "
                                          "component's share of GRDP at current prices), Seri 2010",
                                  "unit": "percent of TOTAL (Persen)", "multiplier": 0.01,
                                  "base_unit": "fraction of TOTAL"},
}

# The six expenditure components and PDRB, each with its turvar value, the label BPS gives it and an English name;
# the tables hold exactly these seven turvars in this order
COMPONENTS = {
    "PKRT": (1544, "Pengeluaran Konsumsi Rumah Tangga", "household final consumption expenditure"),
    "PKLNPRT": (1545, "Pengeluaran Konsumsi LNPRT", "final consumption expenditure of non-profit institutions serving "
                                                    "households (lembaga nonprofit yang melayani rumah tangga)"),
    "PKP": (1546, "Pengeluaran Konsumsi Pemerintah", "government final consumption expenditure"),
    "PMTB": (1547, "Pembentukan Modal Tetap Bruto", "gross fixed capital formation"),
    "PI": (1548, "Perubahan Inventori", "change in inventories"),
    "NETEKSPOR": (1549, "Net Ekspor", "net exports"),
    "TOTAL": (1550, "PDRB", "GRDP (Produk Domestik Regional Bruto), the sum of the six components"),
}
TOTAL = "TOTAL"
PARTS = [c for c in COMPONENTS if c != TOTAL]
# Components whose value can be negative; every other value must be positive (checks.flags)
SIGNED = ["PI", "NETEKSPOR"]

# The tables' sub-periods (turtahun), in table order, each with its period suffix: four quarters, then the year
SUB_PERIODS = {31: ("Triwulan I", "Q1"), 32: ("Triwulan II", "Q2"), 33: ("Triwulan III", "Q3"),
               34: ("Triwulan IV", "Q4"), 35: ("Tahunan", "")}

# Years the files hold, and every period in output order: each year, then its four quarters
YEARS = range(2010, 2026)
PERIODS = [f"{year}{suffix}" for year in YEARS for suffix in ["", "Q1", "Q2", "Q3", "Q4"]]

# Revision status by year that each var's note states, every period of the year carrying it; the build stops if a note
# changes. The 2026 statement covers quarters these files do not hold. Each note also states that the new autonomous
# regions (Daerah Otonom Baru) have data from 2024
NOTE_STATUS = {534: {2024: "*", 2025: "**", 2026: "***"}, 542: {2024: "*", 2025: "**", 2026: "***"}}
NOTE_NEW_REGIONS = "Data Daerah Otonom Baru (DOB) mulai dirilis tahun 2024"

# Coverage, read from opening the files: every province has values from 2010, including Kalimantan Utara (65), except
# the four provinces split from Papua and Papua Barat in 2022, which these tables give their own values from 2024. A
# province with values in a year has all seven components in the year and its four quarters, in both tables
FIRST_YEAR = {"92": 2024, "95": 2024, "96": 2024, "97": 2024}
PARENT = {"92": "91", "95": "94", "96": "94", "97": "94"}

# Provinces whose area changes, keyed by the first year on the new borders, with the codes that together cover the
# area the province had the year before; a change of such a province from that year before compares different areas
BORDER_CHANGES = {("91", 2024): ["91", "92"], ("94", 2024): ["94", "95", "96", "97"]}

# Datasets this build checks against, written in the shared CSV format, with the units the checks expect. This build
# reads their CSVs and metadata and records their hashes, so both must be rebuilt before this dataset
CHECK_2268 = ROOT / "data/20261103_bps-province-grdp-by-industry-2010-2025/20261103_bps-province-grdp-by-industry-2010-2025.csv"
CHECK_286 = ROOT / "data/20261103_bps-province-grdp-2010-2025/20261103_bps-province-grdp-2010-2025.csv"
CHECK_CONTEXT = {path: {"encoding": "utf-8", "delimiter": ",", "decimal": ".", "thousands": None,
                        "units": {"grdp_current": "Rp billion (Milyar Rupiah)"}} for path in (CHECK_2268, CHECK_286)}
CHECK_KEYS = ["province_code", "indicator", "sector", "period"]

# The one gap beyond rounding between PDRB here and the industry TOTAL of var 2268, as var 2268's value minus var
# 534's, in Rp billion: pre-split Papua Barat (91) in 2023 and its first quarter. Here 91 in 2023 is 97680.94, var
# 286's 91 + 92; var 2268 has 97675.84, the gap its own build declares against var 286. This is BPS's own inconsistency
# between two of its tables, declared exactly, and the build stops if it changes
KNOWN_GAPS_2268 = {("91", "2023"): Decimal("-5.10"), ("91", "2023Q1"): Decimal("-5.09")}

# Keys that var 286 (data/20261103_bps-province-grdp-2010-2025) holds on other borders, each compared on the area both
# cover, as (this dataset's codes, var 286's codes): var 286 holds Kalimantan Utara inside 64 until 2012 and splits
# Papua from 2023, one year before these tables
BORDERS_286 = {
    **{("64", str(y)): (["64", "65"], ["64"]) for y in range(2010, 2013)},
    ("91", "2023"): (["91"], ["91", "92"]),
    ("94", "2023"): (["94"], ["94", "95", "96", "97"]),
}

# Tolerances, each set by the rounding of values BPS publishes with 2 decimals
TOL_COMPONENT_SUM = 0.035  # six components and PDRB, each rounded to 0.01, differ by at most 7 x 0.005
TOL_QUARTER_SUM = 0.025    # four quarters and the year, each rounded to 0.01, differ by at most 5 x 0.005
TOL_SHARE_SUM = 0.03       # six shares rounded to 0.01 against an exact 100 differ by at most 6 x 0.005
TOL_SHARE_LEVELS = 0.006   # a share rounded to 0.01 (0.005), and the rounding of the two levels it divides (under 0.001)
TOL_2268 = 0.01            # one unit in the last decimal: BPS rounds var 534 and var 2268 separately
TOL_286 = 0.05             # BPS rounds var 286 separately, and a border area sums up to five rounded values
TOLERANCE_REASONS = {
    "component_sum": f"six components and PDRB, each rounded to 0.01, can differ by up to 7 x 0.005 = "
                     f"{TOL_COMPONENT_SUM}",
    "quarter_sum": f"four quarters and the year, each rounded to 0.01, can differ by up to 5 x 0.005 = {TOL_QUARTER_SUM}",
    "share_sum": f"six shares, each rounded to 0.01, can differ from 100 by up to 6 x 0.005 = {TOL_SHARE_SUM}",
    "share_levels": f"the published share is rounded to 0.01 (up to 0.005), and the two levels the share is recomputed "
                    f"from are rounded to 0.01 Rp billion, which moves it by under 0.001 point; tolerance "
                    f"{TOL_SHARE_LEVELS}",
    "var_2268": f"one unit in the last decimal ({TOL_2268}): BPS rounds var 534 and var 2268 separately",
    "var_286": f"BPS rounds var 286 separately, and a border area sums up to five values rounded to 0.01; tolerance "
               f"{TOL_286}",
}

# Plausibility ranges (layer 5); a value outside its range is flagged, not dropped, and a range ending in None is open
# above
PLAUSIBLE = {
    "value_positive": (0.01, None),
    "pkrt_share_pct": (15, 85),
    "nominal_growth_pct": (-10, 30),
}
PLAUSIBLE_MEASURES = {
    "value_positive": f"every value of the components other than {' and '.join(SIGNED)}, in both indicators; 0.01 is "
                      f"the smallest positive value with 2 decimals",
    "pkrt_share_pct": "PKRT's share of PDRB in each year, as var 542 publishes it (grdp_distribution_current of PKRT); "
                      "below 15 households consume less than a seventh of the province's GRDP, above 85 nearly all of it",
    "nominal_growth_pct": "PKRT and PDRB at current prices, each year against the year before: (grdp_current in year t "
                          "/ grdp_current in year t-1 - 1) x 100",
}

# Source addresses for the metadata; the WebAPI request is given without its key
URL_PROVINCES = "https://sig.bps.go.id/rest-bridging/getwilayah?level=provinsi&periode_merge=2025_1.2025"
URL_WEBAPI = "https://webapi.bps.go.id/v1/api/list/model/data/domain/0000/var/{var}/th/{{th}}/key/{{key}}"

# Key columns of this dataset
KEYS = ["province_code", "indicator", "component", "period"]


# Functions

def posix(path):
    """Return a path relative to the repository root with forward slashes, for the metadata fields that name files."""
    return Path(path).resolve().relative_to(ROOT).as_posix()


def and_list(items):
    """Return items joined for a sentence: 'a', 'a and b', or 'a, b and c'."""
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def period_of(year, turtahun):
    """Return the period text of a year and a turtahun value: YYYY for the year, YYYYQn for a quarter."""
    return f"{year}{SUB_PERIODS[turtahun][1]}"


def read_webapi(path):
    """Read one saved WebAPI table with the encoding, var, unit, decimals and unlisted-cell setting READ_CONTEXT
    declares for it."""
    c = READ_CONTEXT[path]

    # read_webapi_table reads values only as JSON numbers and treats an absent key as no value, so a file declared
    # with another number format or missing-value convention stops the build
    if {k: c.get(k) for k in WEBAPI_READS} != WEBAPI_READS:
        raise ValueError(f"{path.name}: READ_CONTEXT declares {c}, but read_webapi_table reads only {WEBAPI_READS}")
    return cleaning.read_webapi_table(path, var=c["var"], unit=c["unit"], decimals=c["decimals"],
                                      encoding=c["encoding"], unlisted_turvar=c["unlisted_turvar"])


def check_regions(table, lookup, name):
    """Stop unless the file lists the 38 provinces under their BPS names and codes, then the empty TOTAL row."""
    rows = [(v["val"], v["label"]) for v in table["vervar"]]
    if rows[-1] != EMPTY_ROW or len(rows) != 39:
        raise ValueError(f"{name}: region list {rows[:2]} ... {rows[-2:]}")
    for val, label in rows[:-1]:
        cleaning.webapi_region_code(val, label, lookup)
    if table["labelvervar"] != LABEL_VERVAR:
        raise ValueError(f"{name}: region list named {table['labelvervar']!r}")


def read_var(var, lookup):
    """Read the six files of one var; return the description they share, {(code, indicator, component, period): value}
    and the cells each file holds under unlisted turvar codes."""
    turvars = [(val, label) for val, label, _ in COMPONENTS.values()]
    component_of = {val: code for code, (val, _, _) in COMPONENTS.items()}
    turtahun = [(val, label) for val, (label, _) in SUB_PERIODS.items()]
    tables, values, unlisted = [], {}, {}
    for (first, last), path in RAW_WEBAPI[var].items():
        table, records = read_webapi(path)

        # The file must hold the table, the years the download asked for, the 38 provinces, the seven components and
        # the five periods
        cleaning.require_text(table["var"][0]["label"], VAR_LABELS[var], path.name)
        years = [int(t["label"]) for t in table["tahun"]]
        if years != list(range(first, last + 1)):
            raise ValueError(f"{path.name}: years {years}, expected {first}-{last}")
        check_regions(table, lookup, path.name)
        if [(t["val"], t["label"]) for t in table["turvar"]] != turvars:
            raise ValueError(f"{path.name}: turvar {table['turvar']}, expected {turvars}")
        if [(t["val"], t["label"]) for t in table["turtahun"]] != turtahun:
            raise ValueError(f"{path.name}: turtahun {table['turtahun']}, expected {turtahun}")
        unlisted[(first, last)] = table.pop("unlisted_turvar", [])
        tables.append(table)

        # Each value goes to its region code (checked against the BPS list by name), component and period, once
        for r in records:
            code = cleaning.webapi_region_code(r["vervar"], r["vervar_label"], lookup)
            key = (code, INDICATORS[var], component_of[r["turvar"]], period_of(r["year"], r["turtahun"]))
            if key in values:
                raise ValueError(f"{path.name}: {key} read twice")
            values[key] = r["value"]

    # All six files must come from one release of the table
    for table in tables[1:]:
        for field in ("var", "turvar", "turtahun", "vervar", "labelvervar", "subject", "last_update"):
            if table[field] != tables[0][field]:
                raise ValueError(f"var {var}: files differ in {field}")
    return tables[0], values, unlisted


def regions_in(year, codes):
    """Return the codes with their own values in a year: every province that these tables had split off by then."""
    return [code for code in codes if year >= FIRST_YEAR.get(code, YEARS[0])]


def expected_keys(codes):
    """Every key the tables should yield: the full grid of indicators, components and periods for each province with
    its own values that year; the four new Papua provinces before 2024 are the only gaps."""
    return {(code, indicator, component, f"{year}{suffix}") for year in YEARS for code in regions_in(year, codes)
            for indicator in INDICATORS.values() for component in COMPONENTS for _, suffix in SUB_PERIODS.values()}


def coverage(codes):
    """Describe each run of years with the same provinces: how many have values and which codes are absent."""
    runs = []
    for year in YEARS:
        absent = [code for code in codes if code not in regions_in(year, codes)]
        if runs and runs[-1]["absent"] == absent:
            runs[-1]["last"] = year
        else:
            runs.append({"first": year, "last": year, "absent": absent})
    return {f"{r['first']}-{r['last']}": {"provinces": len(codes) - len(r["absent"]), "absent": r["absent"]}
            for r in runs}


def describe_unlisted(var, span, cells, values, codes, lookup):
    """Check the cells a file holds under unlisted turvar codes against the declaration, and describe them: each code's
    count and the listed component its values lie nearest once put on the listed unit. Stops unless the cells are
    exactly the declared codes and periods for every province of those periods, and each code lies nearest its
    declared component."""
    periods = UNLISTED.get((var, span), [])
    found = {(c["turvar"], period_of(c["year"], c["turtahun"]),
              cleaning.webapi_region_code(c["vervar"], c["vervar_label"], lookup)): c["value"] for c in cells}
    expected = {(t, p, code) for t in UNLISTED_CODES for p in periods for code in regions_in(int(p[:4]), codes)}
    if len(found) != len(cells) or set(found) != expected:
        raise ValueError(f"var {var} {span}: {len(cells)} unlisted cells, not the declared codes and periods")
    if not cells:
        return None

    # Put each unlisted value on the listed unit and find the listed component it lies nearest, on average
    indicator, scale = INDICATORS[var], UNLISTED_SCALE[var]
    nearest = {}
    for t in UNLISTED_CODES:
        mine = {(p, code): v / scale for (tt, p, code), v in found.items() if tt == t}
        gaps = {comp: sum(abs(v - values[(code, indicator, comp, p)]) for (p, code), v in mine.items()) / len(mine)
                for comp in COMPONENTS}
        ranked = sorted(gaps, key=gaps.get)
        if ranked[0] != UNLISTED_NEAREST[t]:
            raise ValueError(f"var {var}: unlisted turvar {t} lies nearest {ranked[0]}, declared {UNLISTED_NEAREST[t]}")
        nearest[str(t)] = {"cells": len(mine), "nearest_component": ranked[0],
                           "mean_abs_gap": round(gaps[ranked[0]], 4), "next_nearest": ranked[1],
                           "next_mean_abs_gap": round(gaps[ranked[1]], 4)}
    unit = "Rp billion" if var == 534 else "percentage points"
    put = (f"Divided by {scale}, as values in Rp million would need to be, each code's values lie"
           if scale != 1 else "Each code's values lie")
    return {
        "file": posix(RAW_WEBAPI[var][span]),
        "cells": len(cells),
        "turvars": UNLISTED_CODES,
        "periods": periods,
        "provinces_per_period": len(regions_in(int(periods[0][:4]), codes)),
        "scale": scale,
        "by_turvar": nearest,
        "reason": f"BPS left these cells in datacontent under turvar codes that the table's turvar list no longer names. "
                  f"{put} nearest one listed component (by_turvar, mean absolute gap in {unit}) but not on it, as an "
                  f"earlier release of the table would. None is written: every value in the CSV comes from the listed "
                  f"turvars.",
    }


def frame(values):
    """Return the values as a DataFrame with one column per key, for the identity sums."""
    return pd.DataFrame([{"province_code": c, "indicator": i, "component": m, "period": p, "value": v}
                         for (c, i, m, p), v in values.items()])


def checked_sum(parts, total, tolerance, label):
    """Layer 3: check_sum, after checking that every sum has its published total and every total its parts."""
    if set(parts.index) != set(total.index):
        raise ValueError(f"{label}: {len(set(parts.index) ^ set(total.index))} sums or totals lack their counterpart")
    return cleaning.check_sum(parts, total.reindex(parts.index), tolerance, label)


def identity_checks(values):
    """Layer 3: the six components sum to PDRB and the four quarters to the year at current prices; PDRB is 100 and the
    six shares sum to 100 in var 542; and each published share is the component over PDRB in var 534."""
    df = frame(values)
    df["year"] = df["period"].str[:4]
    df["quarter"] = df["period"].str.len() > 4
    level = df[df["indicator"] == "grdp_current"]
    share = df[df["indicator"] == "grdp_distribution_current"]
    results = []

    # The six components sum to PDRB, every province, year and quarter
    parts = level[level["component"] != TOTAL].groupby(["province_code", "period"])["value"]
    if (parts.size() != len(PARTS)).any():
        raise ValueError("a province and period lacks some of the six components")
    total = level[level["component"] == TOTAL].set_index(["province_code", "period"])["value"]
    results.append({**checked_sum(parts.sum(), total, TOL_COMPONENT_SUM, "grdp_current: the six components sum to "
                                  "TOTAL (PDRB), every province, year and quarter, Rp billion"),
                    "tolerance_reason": TOLERANCE_REASONS["component_sum"]})

    # The four quarters sum to the year, every province and component, TOTAL included
    quarters = level[level["quarter"]].groupby(["province_code", "component", "year"])["value"]
    if (quarters.size() != 4).any():
        raise ValueError("a province, component and year lacks some of its four quarters")
    year = level[~level["quarter"]].set_index(["province_code", "component", "year"])["value"]
    results.append({**checked_sum(quarters.sum(), year, TOL_QUARTER_SUM, "grdp_current: the four quarters sum to the "
                                  "year, every province and component, TOTAL included, Rp billion"),
                    "tolerance_reason": TOLERANCE_REASONS["quarter_sum"]})

    # var 542 gives PDRB as 100 exactly, and the six shares sum to it
    hundred = share[share["component"] == TOTAL]
    if not (hundred["value"] == 100).all():
        raise ValueError(f"grdp_distribution_current of TOTAL is not 100 at {hundred[hundred['value'] != 100].head()}")
    shares = share[share["component"] != TOTAL].groupby(["province_code", "period"])["value"].sum()
    results.append({**checked_sum(shares, hundred.set_index(["province_code", "period"])["value"], TOL_SHARE_SUM,
                                  "grdp_distribution_current: the six shares sum to 100, every province, year and "
                                  "quarter, percent"),
                    "tolerance_reason": TOLERANCE_REASONS["share_sum"],
                    "total_is_100": f"TOTAL is exactly 100 in all {len(hundred)} cells"})

    # Each published share equals the component over PDRB in var 534, x 100; every share has both levels
    lv = level.set_index(["province_code", "component", "period"])["value"]
    sh = share[share["component"] != TOTAL].set_index(["province_code", "component", "period"])["value"]
    pdrb = level[level["component"] == TOTAL].set_index(["province_code", "period"])["value"]
    numerator = lv.reindex(sh.index).to_numpy()
    denominator = pdrb.reindex(pd.MultiIndex.from_arrays([sh.index.get_level_values(0),
                                                          sh.index.get_level_values(2)])).to_numpy()
    if pd.isna(numerator).any() or pd.isna(denominator).any():
        raise ValueError("a published share has no level to recompute it from")
    recomputed = pd.Series(100 * numerator / denominator, index=sh.index)
    results.append({**checked_sum(recomputed, sh, TOL_SHARE_LEVELS, "grdp_distribution_current (var 542) equals 100 x "
                                  "the component's grdp_current over TOTAL's (var 534), every province, component, "
                                  "year and quarter, percentage points"),
                    "tolerance_reason": TOLERANCE_REASONS["share_levels"],
                    "rounded_differ": int((recomputed.round(2) != sh.reindex(recomputed.index)).sum())})
    return results


def read_check_dataset(path):
    """Read a dataset in data/ that this build checks against: its metadata, and {(code, indicator, sector, period):
    (value, status)} for the declared indicators, every value parsed as text against the shared format."""
    c = CHECK_CONTEXT[path]

    # The check dataset must still be in the shared format and in the units this script expects
    meta_path = path.with_name(path.stem + "-metadata.json")
    meta = json.loads(meta_path.read_text(encoding=c["encoding"]))
    if meta["format"] != cleaning.CSV_FORMAT:
        raise ValueError(f"{meta_path.name}: format {meta['format']}")
    for indicator, unit in c["units"].items():
        if meta["indicators"][indicator]["unit"] != unit:
            raise ValueError(f"{meta_path.name}: {indicator} unit {meta['indicators'][indicator]['unit']!r}, "
                             f"expected {unit!r}")

    # Parse every value of the declared indicators as text against the shared format
    rows = cleaning.read_csv_rows(path, c["encoding"], c["delimiter"])
    if rows[0] != CHECK_KEYS + ["status", "value"]:
        raise ValueError(f"{path.name}: header {rows[0]}")
    cells = {}
    for code, indicator, sector, period, status, value in rows[1:]:
        if indicator in c["units"]:
            cells[(code, indicator, sector, period)] = (cleaning.parse_number(value, c["decimal"], c["thousands"]),
                                                        status)
    return cells, meta


def equal_statuses(keys, ours, theirs, name):
    """Stop unless every compared key carries the same status in both datasets; return how many were compared."""
    differ = [k for k in keys if ours[k] != theirs[k]]
    if differ:
        raise ValueError(f"statuses differ from {name} at {differ[:5]}")
    return len(keys)


def compare_2268(values, statuses, check):
    """Layer 4: PDRB in every year and quarter against the industry TOTAL of var 2268 in
    data/20261103_bps-province-grdp-by-industry-2010-2025, which holds the same provinces on the same borders, within
    TOL_2268; the declared gaps must hold to the cent."""
    name = CHECK_2268.name
    ours = {(c, p): v for (c, i, m, p), v in values.items() if i == "grdp_current" and m == TOTAL}
    theirs = {(c, p): v for (c, i, s, p), (v, _) in check.items() if i == "grdp_current" and s == "TOTAL"}
    if set(ours) != set(theirs):
        raise ValueError(f"{name} holds other keys: {sorted(set(ours) ^ set(theirs))[:5]}")

    # Every key but the declared gaps within the tolerance, and each declared gap exactly
    first = {k: v for k, v in ours.items() if k not in KNOWN_GAPS_2268}
    result = cleaning.compare_sources(first, {k: theirs[k] for k in first}, TOL_2268,
                                      f"grdp_current TOTAL (var 534) equals the industry TOTAL (var 2268) in {name}, "
                                      f"every province, year and quarter, Rp billion")
    result["keys"] = "[province_code, period]; first = this dataset (var 534), second = var 2268"
    result["tolerance_reason"] = TOLERANCE_REASONS["var_2268"]
    declared = []
    for key, gap in KNOWN_GAPS_2268.items():
        found = Decimal(str(theirs[key])) - Decimal(str(ours[key]))
        if found != gap:
            raise ValueError(f"{key}: var 2268 minus var 534 is {found}, declared {gap}")
        declared.append({"key": list(key), "var_534": ours[key], "var_2268": theirs[key], "gap": float(gap)})
    result["declared_gaps"] = {"gaps": declared, "reason": "BPS's own inconsistency between two of its tables: here "
                               "pre-split Papua Barat (91) in 2023 is var 286's 91 + 92 (97680.94), and var 2268's 91 "
                               "is 5.10 lower in the year and 5.09 lower in the first quarter, the gap "
                               "data/20261103_bps-province-grdp-by-industry-2010-2025 declares against var 286. "
                               "Declared exactly; the build stops if it changes"}

    # Every compared value must carry the same status in both
    their_status = {(c, p): m for (c, i, s, p), (_, m) in check.items() if i == "grdp_current" and s == "TOTAL"}
    our_status = {k: statuses[(k[0], "grdp_current", TOTAL, k[1])] for k in ours}
    result["statuses_equal"] = equal_statuses(list(ours), our_status, their_status, name)
    return result


def compare_286(values, statuses, check):
    """Layer 4: annual PDRB against var 286 in data/20261103_bps-province-grdp-2010-2025, within TOL_286, on the same
    borders or on the area both cover; every other key needs a declared reason."""
    name = CHECK_286.name
    ours = {(c, p): v for (c, i, m, p), v in values.items() if i == "grdp_current" and m == TOTAL and p.isdigit()}
    theirs = {(c, p): v for (c, i, s, p), (v, _) in check.items() if i == "grdp_current" and s == "TOTAL"}

    # Each border key is the sum of the codes that cover one area in each dataset, and the codes that only enter such a
    # sum are not compared on their own; every other key both hold is compared on the same borders
    inside = {(c, p) for (_, p), (mine, other) in BORDERS_286.items() for c in mine + other} - set(BORDERS_286)
    first, second = {}, {}
    for (code, period), value in ours.items():
        if (code, period) in BORDERS_286:
            mine, other = BORDERS_286[(code, period)]
            first[(code, period)] = round(sum(ours[(c, period)] for c in mine), 2)
            second[(code, period)] = round(sum(theirs[(c, period)] for c in other), 2)
        elif (code, period) in theirs and (code, period) not in inside:
            first[(code, period)], second[(code, period)] = value, theirs[(code, period)]
    result = cleaning.compare_sources(first, second, TOL_286,
                                      f"annual grdp_current TOTAL (var 534) equals var 286 in {name}, on the same "
                                      f"borders or summed over the area both cover, Rp billion")
    result["keys"] = "[province_code, period]; first = this dataset (var 534), second = var 286"
    result["tolerance_reason"] = TOLERANCE_REASONS["var_286"]
    result["border_areas"] = {f"{code} {period}": {"this_dataset": "+".join(mine), "var_286": "+".join(other)}
                              for (code, period), (mine, other) in BORDERS_286.items()}

    # Every compared value must carry the same status in both
    their_status = {(c, p): m for (c, i, s, p), (_, m) in check.items() if i == "grdp_current" and s == "TOTAL"}
    our_status = {k: statuses[(k[0], "grdp_current", TOTAL, k[1])] for k in first}
    result["statuses_equal"] = equal_statuses(list(first), our_status, their_status, name)

    # Every key left out must have a declared reason
    reasons = {"inside a border area's sum": sorted([list(k) for k in inside]),
               "Indonesia (00): var 534 publishes no value in its TOTAL row": []}
    for key in sorted(set(ours) | set(theirs)):
        if key in first or key in inside:
            continue
        if key not in ours and key[0] == cleaning.NATIONAL_CODE:
            reasons["Indonesia (00): var 534 publishes no value in its TOTAL row"].append(list(key))
        else:
            raise ValueError(f"{key} is in {'this dataset' if key in ours else name} only, for no declared reason")
    result["not_compared"] = reasons
    return result


def flag_range(rows, check):
    """Layer 5: flag the rows whose value lies outside the check's stated range, which None leaves open above."""
    low, high = PLAUSIBLE[check]
    flags = cleaning.flag_outside(rows, check, low, math.inf if high is None else high)
    # Each flag states the range as declared, since JSON has no infinity
    return [{**f, "range": [low, high]} for f in flags]


def plausibility(values):
    """Layer 5: unsigned values positive, PKRT's share of PDRB and the nominal growth of PKRT and PDRB inside their
    stated ranges. Returns the flags and how many values each check read."""
    read = {"value_positive": [{"province_code": c, "indicator": i, "component": m, "period": p, "value": v}
                               for (c, i, m, p), v in sorted(values.items()) if m not in SIGNED],
            "pkrt_share_pct": [{"province_code": c, "period": p, "value": v} for (c, i, m, p), v in sorted(values.items())
                               if i == "grdp_distribution_current" and m == "PKRT" and p.isdigit()],
            "nominal_growth_pct": []}
    current = {(c, m, p): v for (c, i, m, p), v in values.items() if i == "grdp_current" and p.isdigit()}
    for (code, component, period), value in sorted(current.items()):
        before = current.get((code, component, str(int(period) - 1)))
        # A change across a border change compares different areas, and a change from a value that is not positive has
        # no growth rate (value_positive flags that value)
        if component not in ("PKRT", TOTAL) or before is None or (code, int(period)) in BORDER_CHANGES or before <= 0:
            continue
        read["nominal_growth_pct"].append({"province_code": code, "component": component, "period": period,
                                           "rp_billion": {str(int(period) - 1): before, period: value},
                                           "value": (value / before - 1) * 100})
    flags = [f for check in PLAUSIBLE for f in flag_range(read[check], check)]
    return flags, {check: len(read[check]) for check in PLAUSIBLE}


def growth_not_compared():
    """List the provinces whose change from the year before their border change compares different areas."""
    out = []
    for (code, year), old_area in BORDER_CHANGES.items():
        others = and_list(old_area[1:])
        own = "has its" if len(old_area) == 2 else "have their"
        out.append({"province_code": code, "period": str(year), "old_area": "+".join(old_area),
                    "reason": f"{code} in {year - 1} includes {others}, which {own} own values from {year}, so the "
                              f"change of {code} from {year - 1} compares different areas; no growth check reads it"})
    return out


def describe_var(var, table):
    """Describe one WebAPI table for the metadata: role, label, unit, breakdowns, release, note and files."""
    v = table["var"][0]
    return {
        "role": f"gives every {INDICATORS[var]} value in the CSV",
        "label": v["label"].strip(),
        "subject": v["subj"],
        "unit": v["unit"],
        "decimals": v["decimal"],
        "turvar": {str(t["val"]): t["label"] for t in table["turvar"]},
        "turtahun": {str(t["val"]): t["label"] for t in table["turtahun"]},
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

# Print in UTF-8 so BPS labels and markers show on any console
sys.stdout.reconfigure(encoding="utf-8")

# Read the BPS province list that every region name and code is matched against; load_bps_provinces reads UTF-8
# JSON, so a list declared in another encoding stops the build
if READ_CONTEXT[RAW_PROVINCES]["encoding"] != "utf-8":
    raise ValueError(f"{RAW_PROVINCES.name}: READ_CONTEXT declares {READ_CONTEXT[RAW_PROVINCES]}, but "
                     f"load_bps_provinces reads UTF-8")
provinces, lookup = cleaning.load_bps_provinces(RAW_PROVINCES)
codes = [c for c in provinces if c != cleaning.NATIONAL_CODE]

# Stop unless the download script the metadata names is in the repository, and raw/grdp holds exactly the declared
# files of each var
if not (ROOT / RAW_DOWNLOAD_SCRIPT).is_file():
    raise FileNotFoundError(f"download script {RAW_DOWNLOAD_SCRIPT} not found")
for var, files in RAW_WEBAPI.items():
    found = sorted((ROOT / "raw/grdp").glob(f"20261104_bps-api-var{var}-*.json"))
    if found != sorted(files.values()):
        raise ValueError(f"var {var}: raw/grdp holds {[p.name for p in found]}, expected the six declared files")

# Read both vars, six files each, into one description and one value map per var, setting aside the unlisted cells
tables, values, unlisted = {}, {}, {}
for var in INDICATORS:
    tables[var], cells, unlisted[var] = read_var(var, lookup)
    values.update(cells)

# The unlisted cells must be exactly the declared ones, and each code must lie nearest its declared component
unlisted_cells = [d for var in INDICATORS for span in YEAR_RANGES
                  if (d := describe_unlisted(var, span, unlisted[var][span], values, codes, lookup)) is not None]

# Each var's note must still state the statuses and the first year of the new regions this script declares, and every
# row takes the status its var's note gives its year (2010-2023 final)
for var, table in tables.items():
    found = cleaning.parse_status_note(table["var"][0]["note"])
    if found != NOTE_STATUS[var]:
        raise ValueError(f"var {var} note gives {found}, the script declares {NOTE_STATUS[var]}")
    cleaning.require_text(cleaning.html_to_text(table["var"][0]["note"]), NOTE_NEW_REGIONS, f"var {var} note")
status_by_year = {var: {str(year): mark for year, mark in NOTE_STATUS[var].items()} for var in INDICATORS}
statuses = {k: status_by_year[VAR_OF[k[1]]].get(k[3][:4], "") for k in values}
rows = [{"province_code": c, "indicator": i, "component": m, "period": p, "status": statuses[(c, i, m, p)], "value": v}
        for (c, i, m, p), v in values.items()]

# Layer 3: components sum to PDRB, quarters sum to the year, shares sum to 100 and equal the levels' ratio; stops on
# failure
identities = identity_checks(values)

# Layer 4: PDRB against the industry TOTAL of var 2268 in every period, and against var 286 in every year; stops on any
# gap beyond the stated tolerance or any key left out for no declared reason
check_2268, _ = read_check_dataset(CHECK_2268)
check_286, _ = read_check_dataset(CHECK_286)
cross_2268 = compare_2268(values, statuses, check_2268)
cross_286 = compare_286(values, statuses, check_286)

# Layer 5: unsigned values positive, PKRT's share and nominal growth inside their stated ranges; outliers are only
# flagged
flags, compared = plausibility(values)

# Statements for the metadata, written from the declared statuses and the check results so that they cannot go stale
if NOTE_STATUS[534] != NOTE_STATUS[542]:
    raise ValueError("the two notes give different statuses; restate the status note")
marked = and_list([f"{year} '{mark}'" for year, mark in NOTE_STATUS[534].items()])
marked_years = and_list([str(year) for year in NOTE_STATUS[534] if year in YEARS])
unused = [str(year) for year in NOTE_STATUS[534] if year not in YEARS]
final_years = f"{YEARS[0]}-{min(NOTE_STATUS[534]) - 1}"
check_folders = [posix(CHECK_286.parent) + "/", posix(CHECK_2268.parent) + "/"]
component_gap = identities[0]["largest_gap"]
quarter_gap = identities[1]["largest_gap"]
levels_gap = identities[3]["largest_gap"]

# Describe the dataset
meta = {
    "title": "BPS provincial GRDP by expenditure, quarterly and annual, at current prices, with each component's "
             "share, Indonesia, 2010-2025",
    "columns": {
        "province_code": "BPS province code (kode_bps) of the 38 provinces; these tables publish no Indonesia value. "
                         "Names and Kemendagri codes in 'provinces'.",
        "indicator": "Indicator code; definitions in 'indicators'.",
        "component": "Expenditure component code: the six components and TOTAL (PDRB); BPS labels in 'components'.",
        "period": "YYYY = year (BPS 'Tahunan'); YYYYQn = quarter n (BPS 'Triwulan I' to 'Triwulan IV').",
        "status": "BPS revision marker from the table note; meanings in 'status'.",
        "value": "grdp_current: Rp billion; grdp_distribution_current: percent of TOTAL; both as published by BPS "
                 "with 2 decimals. Multiply by 'multiplier' for base units.",
    },
    "provinces": {c: provinces[c] for c in codes},
    "province_source": {"url": URL_PROVINCES, "file": posix(RAW_PROVINCES),
                        "note": "BPS and Kemendagri codes differ for the six Papua provinces; join other datasets on "
                                "the code system they use."},
    "components": {code: {"label": label, "name": name, "turvar": val}
                   for code, (val, label, name) in COMPONENTS.items()},
    "component_notes": [
        f"TOTAL is BPS's row 'PDRB', published by BPS, not summed here. The six components sum to it within "
        f"{component_gap} Rp billion and the four quarters to the year within {quarter_gap} Rp billion, inside the "
        f"rounding tolerances of {TOL_COMPONENT_SUM} and {TOL_QUARTER_SUM} (checks.identities).",
        f"{' and '.join(SIGNED)} can be negative; every other component is positive in every cell (checks.flags lists "
        f"any that is not).",
    ],
    "indicators": {
        indicator: {
            **INDICATOR_INFO[indicator],
            "decimals": tables[var]["var"][0]["decimal"],
            "periods": f"{YEARS[0]}-{YEARS[-1]}: each year and its four quarters",
            "source": f"BPS WebAPI var {var} '{tables[var]['var'][0]['label'].strip()}'; see 'source_tables'",
            "download_script": RAW_DOWNLOAD_SCRIPT,
            "notes": [f"BPS table note (last updated {tables[var]['last_update']}): "
                      f"{cleaning.html_to_text(tables[var]['var'][0]['note'])}"],
        }
        for var, indicator in INDICATORS.items()
    },
    "coverage": {
        "years": coverage(codes),
        "first_year": {code: {"year": year, "reason": f"{provinces[code]['name']} became a province in 2022; these "
                                                      f"tables give it its own values from {year}, as their note "
                                                      f"states ('{NOTE_NEW_REGIONS}'), and {PARENT[code]} covers it "
                                                      f"before"}
                       for code, year in FIRST_YEAR.items()},
        "cells": "A province with values in a year has all seven components in the year and in each of its four "
                 "quarters, in both indicators; completeness expects exactly this grid.",
        "no_indonesia_row": f"Both tables list a row {EMPTY_ROW[0]} '{EMPTY_ROW[1]}' after the 38 provinces, which "
                            f"holds no value in any file, so the dataset has no Indonesia (00) row; the sum of the "
                            f"provinces is not national GDP.",
    },
    "borders": [
        "65 (Kalimantan Utara) has its own values from 2010 in these tables, so 64 (Kalimantan Timur) excludes it in "
        "every year, as in the industry tables vars 2267 and 2268; the annual table var 286 "
        "(data/20261103_bps-province-grdp-2010-2025) holds it inside 64 until 2012.",
        f"91 (Papua Barat) and 94 (Papua) in {YEARS[0]}-2023 cover the pre-split provinces: Papua Barat then included "
        f"Papua Barat Daya, and Papua included Papua Selatan, Papua Tengah and Papua Pegunungan. From 2024, 91 and 94 "
        f"cover the post-split areas, and {and_list(list(FIRST_YEAR))} start.",
        "On fixed borders: Papua Barat (pre-2024 area) = 91 + 92 and Papua (pre-2024 area) = 94 + 95 + 96 + 97 from "
        "2024. grdp_current adds across provinces; a share of a combined area is the combined component over the "
        "combined TOTAL x 100, never a sum or average of the provinces' shares.",
        "A change of 91 or 94 from 2023 to 2024 compares different areas; the growth checks leave those changes out "
        "(checks.growth_not_compared).",
    ],
    "source_tables": {str(var): describe_var(var, table) for var, table in tables.items()},
    "unlisted_cells": unlisted_cells,
    "notes": [
        f"status: both notes give {marked}; every row of {marked_years} carries the status of its year, in the year "
        f"and its four quarters and in both indicators, and {final_years} are final. {and_list(unused)} is after the "
        f"last year these files hold, so its status applies to no row. The WebAPI gives no status per cell.",
        f"grdp_distribution_current is BPS's own share, var 542, kept as published. It equals 100 x the component's "
        f"grdp_current over TOTAL's within {levels_gap} percentage points (checks.identities), so a share of an area "
        f"made of several provinces can be rebuilt from grdp_current.",
        f"PDRB (TOTAL) is the GRDP of the production side: it equals the industry TOTAL of var 2268 in "
        f"{check_folders[1]} within {TOL_2268} Rp billion in every year and quarter except BPS's declared gap for "
        f"pre-split Papua Barat in 2023, and var 286 in {check_folders[0]} within {cross_286['largest_gap']} Rp "
        f"billion in every year (checks.cross_source).",
        "Derived values are not stored. A component's share (%) of an area = sum of the component's grdp_current / sum "
        "of TOTAL's grdp_current x 100; nominal growth (%) = (grdp_current in year t / grdp_current in year t-1 - 1) "
        "x 100.",
        "checks.flags lists every value or change outside its range in checks.plausible_ranges for a person to review, "
        "with the two values each growth compares under rp_billion; a flag stays whether it reflects a real event or "
        "a source error.",
    ],
    "check_datasets": {
        "build_order": f"{and_list(check_folders)} must be rebuilt before this dataset: this build reads their CSVs "
                       f"and metadata as checks and records their hashes as they are when it runs",
        "files": {posix(p): {"sha256": cleaning.sha256(p)}
                  for csv in (CHECK_286, CHECK_2268) for p in (csv, csv.with_name(csv.stem + "-metadata.json"))},
    },
    "checks": {
        "passed": ["identities", "cross-source"],
        "identities": identities,
        "cross_source": [cross_2268, cross_286],
        "plausible_ranges": {check: {"range": list(PLAUSIBLE[check]), "measure": PLAUSIBLE_MEASURES[check]}
                             for check in PLAUSIBLE},
        "plausibility_compared": compared,
        "growth_not_compared": growth_not_compared(),
        "flags": flags,
    },
}

# Layers 1, 2 and 6: check structure and completeness against the declared coverage, then write the CSV and metadata
raw_files = [RAW_PROVINCES] + [p for files in RAW_WEBAPI.values() for p in files.values()]
out = cleaning.write_dataset(
    rows, KEYS,
    allowed={"province_code": codes, "indicator": list(INDICATORS.values()), "component": list(COMPONENTS),
             "period": PERIODS},
    expected=expected_keys(codes),
    csv_path=OUT_CSV, meta=meta, raw_files=raw_files,
    sort_orders={"indicator": list(INDICATORS.values()), "component": list(COMPONENTS), "period": PERIODS},
)

# Report what was written, every check result and every plausibility flag
print(f"{OUT_CSV.name}: {len(out)} rows, {len(flags)} plausibility flags")
print(out.groupby(["indicator", "status"]).size().to_string())
for check in identities:
    print("  identity:", {k: v for k, v in check.items() if k != "differences"})
for cross in (cross_2268, cross_286):
    print("  cross-source:", {k: cross[k] for k in ("check", "compared", "tolerance", "largest_gap", "statuses_equal")},
          f"{len(cross['differences'])} differences")
for cell in unlisted_cells:
    print("  unlisted:", cell["file"], cell["cells"], "cells;",
          {t: (d["nearest_component"], d["mean_abs_gap"], d["next_mean_abs_gap"]) for t, d in cell["by_turvar"].items()})
print(f"  plausibility: values read {compared}")
for f in flags:
    print("  flag:", f)
