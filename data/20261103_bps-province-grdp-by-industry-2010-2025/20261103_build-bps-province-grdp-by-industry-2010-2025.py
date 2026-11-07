from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# Load the shared cleaning module from tools/
import sys
sys.path.insert(0, str(ROOT / "tools"))
import cleaning

# Modules for the checks: json for the check datasets' metadata, math for a range open above, pandas for the sums
import json
import math

import pandas as pd

# Parameters

# Raw inputs: the BPS province list, and the BPS WebAPI downloads of var 2267 (quarterly GRDP by industry at constant
# 2010 prices) and var 2268 (the same at current prices), each in the six year ranges the download script requested.
# They are the only raw files with GRDP by industry for every quarter of 2010-2025, so every value in the CSV comes
# from them
RAW_PROVINCES = ROOT / "raw/province-codes/20261102_bps-province-codes-2025-s1.json"
RAW_DOWNLOAD_SCRIPT = "raw/grdp/20261103_download-bps-api-grdp-2010-2025.py"
YEAR_RANGES = [(2010, 2012), (2013, 2015), (2016, 2018), (2019, 2021), (2022, 2023), (2024, 2025)]
RAW_NAMES = {2267: "grdp-quarterly-constant-prices-by-industry-by-province",
             2268: "grdp-quarterly-current-prices-by-industry-by-province"}
RAW_WEBAPI = {var: {span: ROOT / f"raw/grdp/20261103_bps-api-var{var}-{name}-{span[0]}-{span[1]}.json"
                    for span in YEAR_RANGES} for var, name in RAW_NAMES.items()}

# Output; the metadata JSON is written beside it with a -metadata suffix
OUT_CSV = HERE / "20261103_bps-province-grdp-by-industry-2010-2025.csv"

# How each raw file is written, read from opening all 13 files. The province list is UTF-8 JSON without a byte-order
# mark: 38 records whose four fields (kode_bps, nama_bps, kode_dagri, nama_dagri) are all text, so it holds no numbers,
# units or missing values. The 12 WebAPI files are UTF-8 JSON without a byte-order mark: values are JSON numbers with a
# decimal point and no thousands separator, each var's unit field reads 'Milyar Rupiah' and its decimal field 2, and a
# value BPS does not publish is a key absent from datacontent (the four new Papua provinces before 2024; no markers)
READ_CONTEXT = {
    RAW_PROVINCES: {"encoding": "utf-8", "numbers": "none: every code and name is a JSON string",
                    "missing": "none: every record carries kode_bps, nama_bps, kode_dagri and nama_dagri",
                    "unit": None},
    **{path: {"encoding": "utf-8", "numbers": "JSON numbers, decimal point, no thousands separator",
              "missing": "key absent from datacontent", "var": var, "unit": "Milyar Rupiah", "decimals": 2}
       for var, files in RAW_WEBAPI.items() for path in files.values()},
}

# The one number format and missing-value convention cleaning.read_webapi_table reads: each value a JSON number, and
# a key absent from datacontent for a value BPS does not publish; a WebAPI file declared otherwise stops the build
WEBAPI_READS = {"numbers": "JSON numbers, decimal point, no thousands separator",
                "missing": "key absent from datacontent"}

# Text each var's label must still carry, so that a different table under the same number stops the build
VAR_LABELS = {2267: "[Seri 2010] PDRB Triwulanan Atas Dasar Harga Konstan Menurut Lapangan Usaha di Provinsi",
              2268: "[Seri 2010] PDRB Triwulanan Atas Dasar Harga Berlaku Menurut Lapangan Usaha di Provinsi"}

# Output indicator of each var, in output order, with its name, unit and multiplier to base units; the codes and units
# are those of data/20261103_bps-province-grdp-2010-2025 and data/20261102_bps-province-grdp-population
INDICATORS = {2267: "grdp_constant_2010", 2268: "grdp_current"}
VAR_OF = {indicator: var for var, indicator in INDICATORS.items()}
INDICATOR_INFO = {
    "grdp_constant_2010": {"name": "PDRB triwulanan atas dasar harga konstan 2010 menurut lapangan usaha (GRDP by "
                                   "industry at constant 2010 prices), Seri 2010",
                           "unit": "Rp billion (Milyar Rupiah)", "multiplier": 1e9, "base_unit": "Rp"},
    "grdp_current": {"name": "PDRB triwulanan atas dasar harga berlaku menurut lapangan usaha (GRDP by industry at "
                             "current prices), Seri 2010",
                     "unit": "Rp billion (Milyar Rupiah)", "multiplier": 1e9, "base_unit": "Rp"},
}

# The 17 KBLI categories and the total, with the codes and names data/20261102_bps-province-grdp-population uses (the
# build stops unless that dataset's metadata still gives the same), each with its turvar value and the code its label
# prints: a category's label is that code, a space and the name, as in 'M,N Jasa Perusahaan', and the total's label is
# its name. The tables hold exactly these 18 turvars in this order
SECTORS = {
    "A": (2005, "A", "Pertanian, Kehutanan dan Perikanan"),
    "B": (2006, "B", "Pertambangan dan Penggalian"),
    "C": (2007, "C", "Industri Pengolahan"),
    "D": (2008, "D", "Pengadaan Listrik dan Gas"),
    "E": (2009, "E", "Pengadaan Air, Pengelolaan Sampah, Limbah dan Daur Ulang"),
    "F": (2010, "F", "Konstruksi"),
    "G": (2011, "G", "Perdagangan Besar dan Eceran, Reparasi Mobil dan Sepeda Motor"),
    "H": (2012, "H", "Transportasi dan Pergudangan"),
    "I": (2013, "I", "Penyediaan Akomodasi dan Makan Minum"),
    "J": (2014, "J", "Informasi dan Komunikasi"),
    "K": (2015, "K", "Jasa Keuangan dan Asuransi"),
    "L": (2016, "L", "Real Estate"),
    "MN": (2017, "M,N", "Jasa Perusahaan"),
    "O": (2018, "O", "Administrasi Pemerintahan, Pertahanan dan Jaminan Sosial Wajib"),
    "P": (2019, "P", "Jasa Pendidikan"),
    "Q": (2020, "Q", "Jasa Kesehatan dan Kegiatan Sosial"),
    "RSTU": (2021, "R,S,T,U", "Jasa Lainnya"),
    "TOTAL": (2022, None, "Produk Domestik Regional Bruto"),
}
TOTAL = "TOTAL"
CATEGORIES = [s for s in SECTORS if s != TOTAL]

# The tables' sub-periods (turtahun), in table order, each with its period suffix: four quarters, then the year
SUB_PERIODS = {31: ("Triwulan I", "Q1"), 32: ("Triwulan II", "Q2"), 33: ("Triwulan III", "Q3"),
               34: ("Triwulan IV", "Q4"), 35: ("Tahunan", "")}

# Years the files hold, and every period in output order: each year, then its four quarters
YEARS = range(2010, 2026)
PERIODS = [f"{year}{suffix}" for year in YEARS for suffix in ["", "Q1", "Q2", "Q3", "Q4"]]

# Revision status by year that each var's note states; the build stops if a note changes. Each statement covers the
# four quarters and the year ('Triwulan I–IV 2024 dan Tahun 2024: Angka sementara'), so every period of a year carries
# its status. The 2026 statement covers quarters these files do not hold
NOTE_STATUS = {2267: {2024: "*", 2025: "**", 2026: "***"},
               2268: {2024: "*", 2025: "**", 2026: "***"}}

# Coverage, read from opening the files: every province has values from 2010, including Kalimantan Utara (65), except
# the four provinces split from Papua and Papua Barat in 2022, which these tables give their own values from 2024. A
# province with values in a year has all 17 categories and TOTAL in the year and its four quarters, at both prices
FIRST_YEAR = {"92": 2024, "95": 2024, "96": 2024, "97": 2024}
PARENT = {"92": "91", "95": "94", "96": "94", "97": "94"}

# Provinces whose area changes, keyed by the first year on the new borders, with the codes that together cover the
# area the province had the year before; a change of such a province from that year before compares different areas
BORDER_CHANGES = {("91", 2024): ["91", "92"], ("94", 2024): ["94", "95", "96", "97"]}

# Datasets this build checks against, written in the shared CSV format, with the units the checks expect. This build
# reads their CSVs and metadata and records their hashes, so both must be rebuilt before this dataset
CHECK_286 = ROOT / "data/20261103_bps-province-grdp-2010-2025/20261103_bps-province-grdp-2010-2025.csv"
CHECK_POP = ROOT / "data/20261102_bps-province-grdp-population/20261102_bps-province-grdp-population.csv"
CHECK_CONTEXT = {
    CHECK_286: {"encoding": "utf-8", "delimiter": ",", "decimal": ".", "thousands": None,
                "units": {"grdp_current": "Rp billion (Milyar Rupiah)",
                          "grdp_constant_2010": "Rp billion (Milyar Rupiah)"}},
    CHECK_POP: {"encoding": "utf-8", "delimiter": ",", "decimal": ".", "thousands": None,
                "units": {"grdp_current": "Rp billion (Milyar Rupiah)"}},
}

# Keys (province, year) that data/20261103_bps-province-grdp-2010-2025 (var 286) holds on other borders, which the
# annual TOTAL comparison leaves out, and keys only one of the two datasets holds, each with its reason
BORDERS_286 = {
    **{("64", str(y)): "var 286's 64 includes Kalimantan Utara, which these tables give its own values (65)"
       for y in range(2010, 2013)},
    ("91", "2023"): "var 286's 91 excludes Papua Barat Daya (92) from 2023, these tables' 91 only from 2024",
    ("94", "2023"): "var 286's 94 excludes Papua Selatan, Papua Tengah and Papua Pegunungan (95, 96, 97) from 2023, "
                    "these tables' 94 only from 2024",
}
ONLY_HERE_286 = {("65", str(y)) for y in range(2010, 2013)}
ONLY_THERE_286 = {(code, "2023") for code in ("92", "95", "96", "97")}

# Tolerances, each set by the rounding of values BPS publishes with 2 decimals (Rp billion)
TOL_SECTOR_SUM = 0.09    # 17 categories and TOTAL, each rounded to 0.01, differ by at most 18 x 0.005
TOL_QUARTER_SUM = 0.025  # four quarters and the year, each rounded to 0.01, differ by at most 5 x 0.005
TOL_BASE_YEAR = 0.01     # one unit in the last decimal: BPS rounds vars 2267 and 2268 separately
TOL_VAR_286 = 0.05       # BPS rounds var 286 and the annual value of vars 2267 and 2268 separately
TOL_SAME_RELEASE = 0     # one table in one release: the same value, exactly
TOLERANCE_REASONS = {
    "sector_sum": f"17 categories and TOTAL, each rounded to 0.01, can differ by up to 18 x 0.005 = {TOL_SECTOR_SUM}",
    "quarter_sum": f"four quarters and the year, each rounded to 0.01, can differ by up to 5 x 0.005 = {TOL_QUARTER_SUM}",
    "base_year": f"one unit in the last decimal ({TOL_BASE_YEAR}): BPS rounds var 2267 and var 2268 separately",
    "var_286": f"BPS rounds the annual table (var 286) and the annual value of the quarterly tables separately, so the "
               f"two can differ by a few units in the last decimal; tolerance {TOL_VAR_286}",
}

# Plausibility ranges (layer 5); a value outside its range is flagged, not dropped, and a range ending in None is open
# above. Real growth uses constant 2010 prices and shares current prices
PLAUSIBLE = {
    "value_positive": (0.01, None),
    "real_growth_pct": (-15, 25),
    "real_growth_quarter_pct": (-15, 25),
    "sector_real_growth_pct": (-50, 100),
    "sector_share_pct": (0, 50),
}
PLAUSIBLE_MEASURES = {
    "value_positive": "every value, Rp billion; 0.01 is the smallest positive value with 2 decimals",
    "real_growth_pct": "TOTAL, each year against the year before: (grdp_constant_2010 in year t / grdp_constant_2010 "
                       "in year t-1 - 1) x 100; the range of data/20261103_bps-province-grdp-2010-2025",
    "real_growth_quarter_pct": "TOTAL, each quarter against the same quarter a year before, the same formula on "
                               "quarters",
    "sector_real_growth_pct": "each of the 17 categories, each year against the year before, the same formula; the "
                              "range data/20261103_bps-province-grdp-detailed-industry uses for sector growth",
    "sector_share_pct": "each of the 17 categories as a share of TOTAL in each year, at current prices: grdp_current "
                        "of the category / grdp_current of TOTAL x 100; above 50 one industry is more than half of "
                        "the province's GRDP",
}

# Source addresses for the metadata; the WebAPI request is given without its key
URL_PROVINCES = "https://sig.bps.go.id/rest-bridging/getwilayah?level=provinsi&periode_merge=2025_1.2025"
URL_WEBAPI = "https://webapi.bps.go.id/v1/api/list/model/data/domain/0000/var/{var}/th/{{th}}/key/{{key}}"

# Key columns of this dataset and of both check datasets
KEYS = ["province_code", "indicator", "sector", "period"]


# Functions

def posix(path):
    """Return a path relative to the repository root with forward slashes, for the metadata fields that name files
    (write_dataset writes the raw_files keys the same way itself)."""
    return Path(path).resolve().relative_to(ROOT).as_posix()


def and_list(items):
    """Return items joined for a sentence: 'a', 'a and b', or 'a, b and c'."""
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def turvar_label(sector):
    """Return the label BPS gives a sector's turvar: the printed code, a space and the name, or the total's name."""
    _, printed, name = SECTORS[sector]
    return f"{printed} {name}" if printed else name


def read_webapi(path):
    """Read one saved WebAPI table with the encoding, var, unit and decimals that READ_CONTEXT declares for it."""
    c = READ_CONTEXT[path]

    # read_webapi_table reads values only as JSON numbers and treats an absent key as no value, so a file declared
    # with another number format or missing-value convention stops the build
    if {k: c.get(k) for k in WEBAPI_READS} != WEBAPI_READS:
        raise ValueError(f"{path.name}: READ_CONTEXT declares {c}, but read_webapi_table reads only {WEBAPI_READS}")
    return cleaning.read_webapi_table(path, var=c["var"], unit=c["unit"], decimals=c["decimals"], encoding=c["encoding"])


def read_var(var, lookup):
    """Read the six files of one var; return the description they share and {(code, indicator, sector, period): value}."""
    turvars = [(val, turvar_label(sector)) for sector, (val, _, _) in SECTORS.items()]
    sector_of = {val: sector for sector, (val, _, _) in SECTORS.items()}
    turtahun = [(val, label) for val, (label, _) in SUB_PERIODS.items()]
    tables, values = [], {}
    for (first, last), path in RAW_WEBAPI[var].items():
        table, records = read_webapi(path)

        # The file must hold the table, the years the download asked for, the 18 industry rows and the five periods
        cleaning.require_text(table["var"][0]["label"], VAR_LABELS[var], path.name)
        years = [int(t["label"]) for t in table["tahun"]]
        if years != list(range(first, last + 1)):
            raise ValueError(f"{path.name}: years {years}, expected {first}-{last}")
        if [(t["val"], t["label"]) for t in table["turvar"]] != turvars:
            raise ValueError(f"{path.name}: turvar {table['turvar']}, expected {turvars}")
        if [(t["val"], t["label"]) for t in table["turtahun"]] != turtahun:
            raise ValueError(f"{path.name}: turtahun {table['turtahun']}, expected {turtahun}")
        tables.append(table)

        # Each value goes to its region code (checked against the BPS list by name), sector and period, once
        for r in records:
            code = cleaning.webapi_region_code(r["vervar"], r["vervar_label"], lookup)
            key = (code, INDICATORS[var], sector_of[r["turvar"]], f"{r['year']}{SUB_PERIODS[r['turtahun']][1]}")
            if key in values:
                raise ValueError(f"{path.name}: {key} read twice")
            values[key] = r["value"]

    # All six files must come from one release of the table
    for table in tables[1:]:
        for field in ("var", "turvar", "turtahun", "vervar", "labelvervar", "subject", "last_update"):
            if table[field] != tables[0][field]:
                raise ValueError(f"var {var}: files differ in {field}")
    return tables[0], values


def regions_in(year, codes):
    """Return the codes with their own values in a year: every province that these tables had split off by then."""
    return [code for code in codes if year >= FIRST_YEAR.get(code, YEARS[0])]


def expected_keys(codes):
    """Every key the tables should yield: the full grid of indicators, sectors and periods for each province with its
    own values that year; the four new Papua provinces before 2024 are the only gaps."""
    return {(code, indicator, sector, f"{year}{suffix}") for year in YEARS for code in regions_in(year, codes)
            for indicator in INDICATORS.values() for sector in SECTORS for _, suffix in SUB_PERIODS.values()}


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


def frame(values):
    """Return the values as a DataFrame with one column per key, for the identity sums."""
    return pd.DataFrame([{"province_code": c, "indicator": i, "sector": s, "period": p, "value": v}
                         for (c, i, s, p), v in values.items()])


def checked_sum(parts, total, tolerance, label):
    """Layer 3: check_sum, after checking that every sum has its published total and every total its parts."""
    if set(parts.index) != set(total.index):
        raise ValueError(f"{label}: {len(set(parts.index) ^ set(total.index))} sums or totals lack their counterpart")
    return cleaning.check_sum(parts, total.reindex(parts.index), tolerance, label)


def identity_checks(values):
    """Layer 3: the 17 categories sum to TOTAL in every period, the four quarters sum to the year in every sector, and
    in the base year 2010 constant prices equal current prices in every annual value."""
    df = frame(values)
    df["year"] = df["period"].str[:4]
    df["quarter"] = df["period"].str.len() > 4
    results = []
    for indicator in INDICATORS.values():
        d = df[df["indicator"] == indicator]

        # The 17 categories sum to TOTAL, every province, year and quarter
        parts = d[d["sector"] != TOTAL].groupby(["province_code", "period"])["value"].sum()
        total = d[d["sector"] == TOTAL].set_index(["province_code", "period"])["value"]
        if (d[d["sector"] != TOTAL].groupby(["province_code", "period"]).size() != len(CATEGORIES)).any():
            raise ValueError(f"{indicator}: a province and period lacks some of the 17 categories")
        results.append({**checked_sum(parts, total, TOL_SECTOR_SUM, f"{indicator}: the 17 categories sum to TOTAL, "
                                      f"every province, year and quarter, Rp billion"),
                        "tolerance_reason": TOLERANCE_REASONS["sector_sum"]})

        # The four quarters sum to the year, every province and sector, TOTAL included
        quarters = d[d["quarter"]].groupby(["province_code", "sector", "year"])["value"]
        if (quarters.size() != 4).any():
            raise ValueError(f"{indicator}: a province, sector and year lacks some of its four quarters")
        year = d[~d["quarter"]].set_index(["province_code", "sector", "year"])["value"]
        results.append({**checked_sum(quarters.sum(), year, TOL_QUARTER_SUM, f"{indicator}: the four quarters sum to "
                                      f"the year, every province and sector, TOTAL included, Rp billion"),
                        "tolerance_reason": TOLERANCE_REASONS["quarter_sum"]})

    # In the base year the annual value at constant 2010 prices is the annual value at current prices; the quarters of
    # 2010 differ, so only the year is compared
    base = str(YEARS[0])
    current = {(c, s): v for (c, i, s, p), v in values.items() if i == "grdp_current" and p == base}
    constant = {(c, s): v for (c, i, s, p), v in values.items() if i == "grdp_constant_2010" and p == base}
    if current.keys() != constant.keys():
        raise ValueError(f"grdp_current and grdp_constant_2010 cover different keys in {base}")
    base_check = cleaning.compare_sources(current, constant, TOL_BASE_YEAR, f"grdp_constant_2010 equals grdp_current "
                                          f"in the base year {base} (annual), every province and sector, Rp billion")
    base_check["keys"] = "[province_code, sector]; first = grdp_current, second = grdp_constant_2010"
    base_check["tolerance_reason"] = TOLERANCE_REASONS["base_year"]
    quarters_differ = sum(1 for (c, i, s, p), v in values.items()
                          if i == "grdp_current" and p.startswith(base) and p != base
                          and v != values[(c, "grdp_constant_2010", s, p)])
    base_check["quarters_not_compared"] = (f"{quarters_differ} of the {4 * len(current)} quarterly values of {base} "
                                           f"differ between the two prices: constant 2010 prices are those of the year "
                                           f"{base} as a whole, so only its annual values coincide")
    results.append(base_check)
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
    if rows[0] != KEYS + ["status", "value"]:
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


def compare_var_286(values, statuses, check):
    """Layer 4: the annual TOTAL of both indicators against data/20261103_bps-province-grdp-2010-2025 (var 286),
    within TOL_VAR_286, on the keys both hold on the same borders; every other key needs a declared reason."""
    name = CHECK_286.name
    ours = {(c, i, p): v for (c, i, s, p), v in values.items() if s == TOTAL and p.isdigit()}
    theirs = {(c, i, p): v for (c, i, s, p), (v, _) in check.items() if s == TOTAL and p.isdigit()}

    # Keys both hold on the same borders, compared one to one; the border keys must be in both
    border = {(c, i, p) for (c, p) in BORDERS_286 for i in INDICATORS.values()}
    if not border <= set(ours) & set(theirs):
        raise ValueError(f"border keys missing from one dataset: {sorted(border - (set(ours) & set(theirs)))}")
    first = {k: v for k, v in ours.items() if k in theirs and k not in border}
    result = cleaning.compare_sources(first, {k: theirs[k] for k in first}, TOL_VAR_286,
                                      f"annual TOTAL of grdp_constant_2010 (var 2267) and grdp_current (var 2268) "
                                      f"equals var 286 in {name}, same borders, Rp billion")
    result["keys"] = "[province_code, indicator, period]; first = this dataset, second = var 286"
    result["tolerance_reason"] = TOLERANCE_REASONS["var_286"]

    # Every compared value must carry the same status in both
    their_status = {(c, i, p): m for (c, i, s, p), (_, m) in check.items()}
    our_status = {(c, i, p): statuses[(c, i, TOTAL, p)] for (c, i, p) in first}
    result["statuses_equal"] = equal_statuses(list(first), our_status, their_status, name)

    # Every key left out must have a declared reason
    reasons = {
        "different borders": [],
        "65 in 2010-2012: var 286 holds Kalimantan Utara inside 64 until 2012": [],
        "92, 95, 96 and 97 in 2023: these tables hold them inside 91 and 94 until 2024": [],
        "Indonesia (00): vars 2267 and 2268 have no Indonesia row": [],
    }
    labels = list(reasons)
    for key in sorted(set(ours) | set(theirs)):
        code, _, period = key
        if key in first:
            continue
        if key in border:
            reasons[labels[0]].append({"key": list(key), "reason": BORDERS_286[(code, period)]})
        elif key not in theirs and (code, period) in ONLY_HERE_286:
            reasons[labels[1]].append(list(key))
        elif key not in ours and (code, period) in ONLY_THERE_286:
            reasons[labels[2]].append(list(key))
        elif key not in ours and code == cleaning.NATIONAL_CODE:
            reasons[labels[3]].append(list(key))
        else:
            raise ValueError(f"{key} is in {'this dataset' if key in ours else name} only, for no declared reason")
    result["not_compared"] = reasons
    return result


def compare_grdp_population(values, statuses, check, release):
    """Layer 4: grdp_current 2020-2025 against data/20261102_bps-province-grdp-population, every key it holds in those
    years: exactly in 2025, which it reads from var 2268 in the release these files hold, and within TOL_VAR_286 in
    2020-2024, whose annual totals it takes from a compiled workbook."""
    name = CHECK_POP.name
    ours = {(c, s, p): v for (c, i, s, p), v in values.items() if i == "grdp_current"}
    theirs = {(c, s, p): v for (c, i, s, p), (v, _) in check.items()}

    # Every key the check dataset holds in this dataset's years must be here, and its other keys must come after them
    later = sorted(k for k in theirs if int(k[2][:4]) > YEARS[-1])
    shared = [k for k in theirs if int(k[2][:4]) <= YEARS[-1]]
    missing = [k for k in shared if k not in ours]
    if missing:
        raise ValueError(f"{name} holds keys this dataset lacks: {missing[:5]}")

    # 2025: one table in one release, so the values must be the same exactly
    last = str(YEARS[-1])
    same = {k: ours[k] for k in shared if k[2][:4] == last}
    exact = cleaning.compare_sources(same, {k: theirs[k] for k in same}, TOL_SAME_RELEASE,
                                     f"grdp_current {last}, the 17 categories and TOTAL in the four quarters and the "
                                     f"year, equals {name}, exactly")
    exact["tolerance_reason"] = (f"{name} reads {last} from var 2268 as the BPS website served it in the release these "
                                 f"files hold (last updated {release}), so the values must be the same")

    # Earlier years: the annual totals the check dataset takes from a compiled workbook, not from var 2268
    earlier = {k: ours[k] for k in shared if k[2][:4] != last}
    workbook = cleaning.compare_sources(earlier, {k: theirs[k] for k in earlier}, TOL_VAR_286,
                                        f"grdp_current, annual TOTAL {min(k[2] for k in earlier)}-"
                                        f"{max(k[2] for k in earlier)}, equals {name}, Rp billion")
    workbook["tolerance_reason"] = (f"{name} takes these annual totals from a compiled workbook, not from var 2268, so "
                                    f"they may carry another table's rounding: {TOLERANCE_REASONS['var_286']}")

    # Every compared value must carry the same status in both
    their_status = {(c, s, p): m for (c, i, s, p), (_, m) in check.items()}
    our_status = {(c, s, p): statuses[(c, "grdp_current", s, p)] for (c, s, p) in shared}
    first_year = min(int(k[2][:4]) for k in shared)
    left_here = sum(1 for k in ours if first_year <= int(k[2][:4]) <= YEARS[-1] and k not in theirs)
    return {
        "check": f"grdp_current {first_year}-{last} equals {name}",
        "years": f"{first_year}-{last}",
        "keys": "[province_code, sector, period]; first = this dataset (var 2268), second = the check dataset",
        "parts": [exact, workbook],
        "statuses_equal": equal_statuses(shared, our_status, their_status, name),
        "not_compared": {
            f"in this dataset only: the 17 categories and the quarters of {first_year}-{int(last) - 1}, where {name} "
            f"holds only the annual TOTAL": left_here,
            f"in {name} only: {and_list(sorted({k[2] for k in later}))}, after {last}, the last year these files "
            f"hold": len(later),
        },
    }


def growth(values):
    """Return the real growth rows of each growth check, at constant 2010 prices: each year of TOTAL and of every
    category against the year before, and each quarter of TOTAL against the same quarter a year before. A change
    across a border change compares different areas and is left out, and a change from a value that is not positive
    has no growth rate (value_positive flags that value)."""
    constant = {(c, s, p): v for (c, i, s, p), v in values.items() if i == "grdp_constant_2010"}
    checks = {"real_growth_pct": [], "real_growth_quarter_pct": [], "sector_real_growth_pct": []}
    for (code, sector, period), value in sorted(constant.items()):
        year, suffix = int(period[:4]), period[4:]
        if sector == TOTAL:
            check = "real_growth_quarter_pct" if suffix else "real_growth_pct"
        elif not suffix:
            check = "sector_real_growth_pct"
        else:
            continue
        earlier = f"{year - 1}{suffix}"
        before = constant.get((code, sector, earlier))
        if before is None or (code, year) in BORDER_CHANGES or before <= 0:
            continue
        checks[check].append({"province_code": code, "sector": sector, "period": period,
                              "rp_billion": {earlier: before, period: value}, "value": (value / before - 1) * 100})
    return checks


def shares(values):
    """Return each category's share of TOTAL (%) in each year at current prices; a TOTAL that is not positive gives no
    share (value_positive flags it)."""
    current = {(c, s, p): v for (c, i, s, p), v in values.items() if i == "grdp_current" and p.isdigit()}
    out = []
    for (code, sector, period), value in sorted(current.items()):
        total = current[(code, TOTAL, period)]
        if sector == TOTAL or total <= 0:
            continue
        out.append({"province_code": code, "sector": sector, "period": period,
                    "rp_billion": {sector: value, TOTAL: total}, "value": 100 * value / total})
    return out


def flag_range(rows, check):
    """Layer 5: flag the rows whose value lies outside the check's stated range, which None leaves open above."""
    low, high = PLAUSIBLE[check]
    flags = cleaning.flag_outside(rows, check, low, math.inf if high is None else high)
    # Each flag states the range as declared, since JSON has no infinity
    return [{**f, "range": [low, high]} for f in flags]


def plausibility(values):
    """Layer 5: every value positive, real growth and sector shares inside their stated ranges. Returns the flags and
    how many values each check read."""
    read = {"value_positive": [{"province_code": c, "indicator": i, "sector": s, "period": p, "value": v}
                               for (c, i, s, p), v in sorted(values.items())],
            **growth(values),
            "sector_share_pct": shares(values)}
    flags = [f for check in PLAUSIBLE for f in flag_range(read[check], check)]
    return flags, {check: len(read[check]) for check in PLAUSIBLE}


def growth_not_compared():
    """List the provinces whose change from the year before their border change compares different areas."""
    out = []
    for (code, year), old_area in BORDER_CHANGES.items():
        others = and_list(old_area[1:])
        own = "has its" if len(old_area) == 2 else "have their"
        out.append({"province_code": code, "periods": [f"{year}{s}" for s in ["", "Q1", "Q2", "Q3", "Q4"]],
                    "old_area": "+".join(old_area),
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
    found = sorted((ROOT / "raw/grdp").glob(f"20261103_bps-api-var{var}-*.json"))
    if found != sorted(files.values()):
        raise ValueError(f"var {var}: raw/grdp holds {[p.name for p in found]}, expected the six declared files")

# Read both vars, six files each, into one description and one value map per var
tables, values = {}, {}
for var in INDICATORS:
    tables[var], cells = read_var(var, lookup)
    values.update(cells)

# Each var's note must still state the statuses this script declares, and every row takes the status its var's note
# gives its year (2010-2023 final)
for var, table in tables.items():
    found = cleaning.parse_status_note(table["var"][0]["note"])
    if found != NOTE_STATUS[var]:
        raise ValueError(f"var {var} note gives {found}, the script declares {NOTE_STATUS[var]}")
status_by_year = {var: {str(year): mark for year, mark in NOTE_STATUS[var].items()} for var in INDICATORS}
statuses = {k: status_by_year[VAR_OF[k[1]]].get(k[3][:4], "") for k in values}
rows = [{"province_code": c, "indicator": i, "sector": s, "period": p, "status": statuses[(c, i, s, p)], "value": v}
        for (c, i, s, p), v in values.items()]

# Layer 3: categories sum to TOTAL, quarters sum to the year, and constant equals current prices in 2010; stops on
# failure
identities = identity_checks(values)

# Read both check datasets; the sector codes and names must be those of data/20261102_bps-province-grdp-population
check_286, _ = read_check_dataset(CHECK_286)
check_pop, meta_pop = read_check_dataset(CHECK_POP)
names = {sector: name for sector, (_, _, name) in SECTORS.items()}
if meta_pop["sectors"] != names:
    raise ValueError(f"{CHECK_POP.name} names its sectors {meta_pop['sectors']}, this build {names}")

# The check dataset's 2025 values must come from the release of var 2268 these files hold, as its note on the BPS
# page states, for the exact comparison to apply
release = tables[2268]["last_update"]
if not any(f"last updated {release}" in note for note in meta_pop["indicators"]["grdp_current"].get("notes", [])):
    raise ValueError(f"{CHECK_POP.name} no longer names var 2268's release {release}; restate the 2025 tolerance")

# Layer 4: annual TOTAL against var 286 on the same borders, and grdp_current 2020-2025 against the population and
# GRDP dataset; stops on any gap beyond the stated tolerance or any key left out for no declared reason
cross_286 = compare_var_286(values, statuses, check_286)
cross_pop = compare_grdp_population(values, statuses, check_pop, release)

# Layer 5: every value positive, real growth and sector shares inside their stated ranges; outliers are only flagged
flags, compared = plausibility(values)

# Statements for the metadata, written from the declared statuses and the check results so that they cannot go stale
if NOTE_STATUS[2267] != NOTE_STATUS[2268]:
    raise ValueError("the two notes give different statuses; restate the status note")
marked = and_list([f"{year} '{mark}'" for year, mark in NOTE_STATUS[2267].items()])
marked_years = and_list([str(year) for year in NOTE_STATUS[2267] if year in YEARS])
unused = [str(year) for year in NOTE_STATUS[2267] if year not in YEARS]
final_years = f"{YEARS[0]}-{min(NOTE_STATUS[2267]) - 1}"
gaps_286 = cross_286["differences"]
gaps_pop = [d for part in cross_pop["parts"] for d in part["differences"]]
pop_years = cross_pop["years"]
check_folders = [posix(CHECK_POP.parent) + "/", posix(CHECK_286.parent) + "/"]
new_papua = [c for c in FIRST_YEAR]
sector_gap = max(r["largest_gap"] for r in identities if "sum to TOTAL" in r["check"])
quarter_gap = max(r["largest_gap"] for r in identities if "sum to the year" in r["check"])
pop_text = ("equal this dataset's at every key" if not gaps_pop else
            f"differ from this dataset's at {len(gaps_pop)} keys, by at most "
            f"{max(d['gap'] for d in gaps_pop)} Rp billion")

# Describe the dataset
meta = {
    "title": "BPS provincial GRDP by industry, quarterly and annual, at constant 2010 and current prices, Indonesia, "
             "2010-2025",
    "columns": {
        "province_code": "BPS province code (kode_bps) of the 38 provinces; these tables have no Indonesia row. Names "
                         "and Kemendagri codes in 'provinces'.",
        "indicator": "Indicator code; definitions in 'indicators'.",
        "sector": "Industry code: the 17 KBLI categories (lapangan usaha) and TOTAL; names and BPS labels in "
                  "'sectors'.",
        "period": "YYYY = year (BPS 'Tahunan'); YYYYQn = quarter n (BPS 'Triwulan I' to 'Triwulan IV').",
        "status": "BPS revision marker from the table note; meanings in 'status'.",
        "value": "Rp billion, as published by BPS with 2 decimals. Multiply by 'multiplier' for rupiah.",
    },
    "provinces": {c: provinces[c] for c in codes},
    "province_source": {"url": URL_PROVINCES, "file": posix(RAW_PROVINCES),
                        "note": "BPS and Kemendagri codes differ for the six Papua provinces; join other datasets on "
                                "the code system they use."},
    "sectors": {sector: {"name": name, "label": turvar_label(sector), "turvar": val}
                for sector, (val, _, name) in SECTORS.items()},
    "sector_notes": [
        "The 17 KBLI categories use the codes of data/20261102_bps-province-grdp-population, where MN and RSTU are the "
        "categories BPS prints as M,N and R,S,T,U; 'label' is the turvar label as BPS publishes it.",
        f"TOTAL is BPS's row '{SECTORS[TOTAL][2]}', published by BPS, not summed here. The 17 categories sum to it "
        f"within {sector_gap} Rp billion and the four quarters sum to the year within {quarter_gap} Rp billion, inside "
        f"the rounding tolerances of {TOL_SECTOR_SUM} and {TOL_QUARTER_SUM} (checks.identities).",
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
                                                      f"tables give it its own values from {year}, and {PARENT[code]} "
                                                      f"covers it before"}
                       for code, year in FIRST_YEAR.items()},
        "cells": "A province with values in a year has all 17 categories and TOTAL in the year and in each of its four "
                 "quarters, at constant 2010 and at current prices; completeness expects exactly this grid.",
    },
    "borders": [
        "65 (Kalimantan Utara) has its own values from 2010 in these tables, so 64 (Kalimantan Timur) excludes it in "
        "every year; the annual table var 286 (data/20261103_bps-province-grdp-2010-2025) holds it inside 64 until "
        "2012.",
        f"91 (Papua Barat) and 94 (Papua) in {YEARS[0]}-2023 cover the pre-split provinces: Papua Barat then included "
        f"Papua Barat Daya, and Papua included Papua Selatan, Papua Tengah and Papua Pegunungan. From 2024, 91 and 94 "
        f"cover the post-split areas, and {and_list(new_papua)} start.",
        "On fixed borders: Papua Barat (pre-2024 area) = 91 + 92 and Papua (pre-2024 area) = 94 + 95 + 96 + 97 from "
        "2024.",
        "A change of 91 or 94 from 2023 to 2024, in the year or in a quarter, compares different areas; the growth "
        "checks leave those changes out (checks.growth_not_compared).",
        "These tables split Papua in 2024, one year after var 286, which splits it from 2023; join 2023 with "
        "data/20261103_bps-province-grdp-2010-2025 on that dataset's 91 + 92 and 94 + 95 + 96 + 97.",
    ],
    "source_tables": {str(var): describe_var(var, table) for var, table in tables.items()},
    "notes": [
        f"status: both notes give {marked}; every row of {marked_years} carries the status of its year, in the year "
        f"and its four quarters and in both indicators, and {final_years} are final. {and_list(unused)} is after the "
        f"last year these files hold, so its status applies to no row. The WebAPI gives no status per cell.",
        "These tables have no Indonesia row, and the sum of the provinces is not national GDP: the BPS note gives "
        "statistical discrepancy as one reason the two differ.",
        f"Every value comes from var 2267 or var 2268, so the categories and quarters of a province and period come "
        f"from one table and its sums hold. The annual TOTAL repeats var 286 in {check_folders[1]}, which differs from "
        f"it at {len(gaps_286)} of {cross_286['compared']} keys on the same borders, by at most "
        f"{cross_286['largest_gap']} Rp billion (checks.cross_source lists each); an analysis that joins the two "
        f"chooses one source on purpose.",
        f"The current-price values of {check_folders[0]} in {pop_years} (its annual TOTAL in the earlier years, every "
        f"category and quarter in {YEARS[-1]}) {pop_text} (checks.cross_source).",
        f"In {YEARS[0]} the annual values at constant 2010 prices equal those at current prices within "
        f"{TOL_BASE_YEAR} Rp billion (checks.identities); the quarters of {YEARS[0]} differ between the two, since "
        f"constant 2010 prices are the prices of {YEARS[0]} as a whole.",
        "Derived values are not stored. Real growth (%) = (grdp_constant_2010 in period t / grdp_constant_2010 in the "
        "same period a year before - 1) x 100; sector share (%) = grdp_current of the category / grdp_current of TOTAL "
        "x 100; implicit price deflator (2010 = 100) = grdp_current / grdp_constant_2010 x 100.",
        "checks.flags lists every value or change outside its range in checks.plausible_ranges for a person to review, "
        "with the two values each growth or share compares under rp_billion; a flag stays whether it reflects a real "
        "event or a source error.",
    ],
    "check_datasets": {
        "build_order": f"{and_list(check_folders)} must be rebuilt, in that order, before this dataset: this build "
                       f"reads their CSVs and metadata as checks and records their hashes as they are when it runs",
        "files": {posix(p): {"sha256": cleaning.sha256(p)}
                  for csv in (CHECK_POP, CHECK_286) for p in (csv, csv.with_name(csv.stem + "-metadata.json"))},
    },
    "checks": {
        "passed": ["identities", "cross-source"],
        "identities": identities,
        "cross_source": [cross_286, cross_pop],
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
    allowed={"province_code": codes, "indicator": list(INDICATORS.values()), "sector": list(SECTORS),
             "period": PERIODS},
    expected=expected_keys(codes),
    csv_path=OUT_CSV, meta=meta, raw_files=raw_files,
    sort_orders={"indicator": list(INDICATORS.values()), "sector": list(SECTORS), "period": PERIODS},
)

# Report what was written, every check result and every plausibility flag
print(f"{OUT_CSV.name}: {len(out)} rows, {len(flags)} plausibility flags")
print(out.groupby(["indicator", "status"]).size().to_string())
for check in identities:
    print("  identity:", {k: v for k, v in check.items() if k != "differences"},
          "differences:", check.get("differences", "n/a"))
print("  cross-source var 286:", {k: cross_286[k] for k in ("compared", "tolerance", "largest_gap", "statuses_equal")},
      f"{len(gaps_286)} differences")
for part in cross_pop["parts"]:
    print("  cross-source grdp-population:", {k: part[k] for k in ("check", "compared", "tolerance", "largest_gap")},
          f"{len(part['differences'])} differences")
print(f"  plausibility: values read {compared}")
for f in flags:
    print("  flag:", f)
