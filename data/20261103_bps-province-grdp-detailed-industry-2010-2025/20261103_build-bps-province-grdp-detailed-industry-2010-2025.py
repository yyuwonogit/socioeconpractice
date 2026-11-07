from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# Load the shared cleaning module from tools/
import sys
sys.path.insert(0, str(ROOT / "tools"))
import cleaning

# Modules for the checks: collections for counts, json for the table lists, the raw table notes and the check datasets'
# metadata, math for ranges open above, re for file names, pandas for the identity sums
import collections
import json
import math
import re

import pandas as pd

# Parameters

# Raw inputs: the BPS province list, each province's SIMDASI table list (which gives the years BPS lists for each
# table), and the SIMDASI yearbook tables 13.1.1 (GRDP at current prices by industry) and 13.1.2 (GRDP at constant
# 2010 prices by industry), one file per province and year. These tables are the only source of the 62 industry rows,
# so every value in the CSV comes from them
RAW_PROVINCES = ROOT / "raw/province-codes/20261102_bps-province-codes-2025-s1.json"
RAW_DIR = ROOT / "raw/grdp-detailed-industry"
RAW_LIST_NAME = "20261103_bps-simdasi-tables-{code}.json"
RAW_LISTS = sorted(RAW_DIR.glob(RAW_LIST_NAME.format(code="??")))
KIND = {"current": "grdp_current", "constant": "grdp_constant_2010"}
TABLE_FILE = re.compile(r"20261103_bps-grdp-(current|constant)-prices-detailed-industry-(\d{2})-(\d{4})\.json")
TABLE_NAME = {"grdp_current": "20261103_bps-grdp-current-prices-detailed-industry-{code}-{year}.json",
              "grdp_constant_2010": "20261103_bps-grdp-constant-prices-detailed-industry-{code}-{year}.json"}
RAW_TABLES = {(KIND[m.group(1)], m.group(2), int(m.group(3))): p
              for p in sorted(RAW_DIR.glob("20261103_bps-grdp-*.json")) if (m := TABLE_FILE.fullmatch(p.name))}

# The scripts that saved the raw files, named in the metadata: the first saved 13.1.1 for 2024 and 2025 and the table
# list of 64, the second the other 37 table lists, 13.1.1 for 2010-2023 and 13.1.2 for 2010-2025
DOWNLOAD_SCRIPTS = {
    "raw/grdp-detailed-industry/20261103_download-bps-grdp-detailed-industry.py":
        "13.1.1 for 2024 and 2025, and the table list of 64",
    "raw/grdp-detailed-industry/20261103_download-bps-grdp-detailed-industry-2010-2025.py":
        "13.1.1 for 2010-2023, 13.1.2 for 2010-2025, and the table lists of the other 37 provinces",
}

# Output; the metadata JSON is written beside it with a -metadata suffix
OUT_CSV = HERE / "20261103_bps-province-grdp-detailed-industry-2010-2025.csv"

# Markers a cell without a value carries, as each table's legend (keterangan_data) defines them: the en dash for
# 'Tidak ada atau nol' (none or zero), '...' for 'Data tidak tersedia' (data not available) and 'NA' for 'Data tidak
# dapat ditampilkan' (data cannot be shown). Opening all 853 tables found no other marker on a cell without a value
EN_DASH = "–"
UNPUBLISHED_MARKERS = ["...", "NA"]

# The one unit text a title carries: the tables of 2020-2025, and the one 2016 table listed, print '(miliar rupiah)'
# in their title; every other title prints no unit at all (the build stops if one names rupiah), so their unit is
# established by comparing them with the WebAPI values in Rp billion (checks.cross_source)
UNIT_TEXT = "(miliar rupiah)"
UNIT_TEXT_YEARS = range(2020, 2026)
UNIT_TEXT_ALSO = {("grdp_current", "36", 2016)}
UNIT_TEXT_EN = "(billion rupiahs)"

# Tables whose values are in Rp million (juta rupiah), 1000 times the Rp billion the series uses: the two tables of 11
# in 2014 say so in their note ('Data dalam juta rupiah'); the others print no unit, and their 17 categories and
# TOTAL are 1000 times the WebAPI values. Rp million is not the Rp billion of the series, so these tables are left out
# (excluded.tables) and their 17 categories and TOTAL are checked against data/20261103_bps-province-grdp-by-industry-
# 2010-2025 scaled by 1000 (checks.exclusions)
MILLION_TABLES = {("grdp_current", "11", 2014), ("grdp_constant_2010", "11", 2014),
                  *(("grdp_current", "17", year) for year in range(2010, 2015)),
                  ("grdp_current", "19", 2014), ("grdp_constant_2010", "19", 2014),
                  ("grdp_current", "72", 2014), ("grdp_constant_2010", "72", 2014)}
MILLION_NOTE = "Data dalam juta rupiah"
MILLION_NOTE_TABLES = {("grdp_current", "11", 2014), ("grdp_constant_2010", "11", 2014)}

# A million-rupiah table whose TOTAL is not the sum of its categories: 19 at current prices in 2014 prints 55.873.812,
# while its 17 categories sum to 56.373.615 and the WebAPI TOTAL is 56.373,62 Rp billion
MISPRINTED_TOTAL = {("grdp_current", "19", 2014)}

# How each raw file is written, read from opening all of them. Every file is UTF-8 JSON without a byte-order mark. The
# province list is 38 records whose codes and names are text. A table list gives each table's years as JSON integers.
# A SIMDASI table writes each value as Indonesian text (75.317,96) with the 2 decimals its one column declares, and a
# cell without a value carries one of the markers above. Most tables print every value to 0.01; the tables listed in
# PRINTED_STEP print theirs rounded to a coarser step, still with 2 decimals (54.108,00)
SIMDASI_FORMAT = {"encoding": "utf-8", "decimal": ",", "thousands": ".", "decimals": 2,
                  "missing": [EN_DASH, *UNPUBLISHED_MARKERS]}
PRINTED_STEP = {
    **{(indicator, code, 2014): 0.1 for indicator, code in [
        ("grdp_current", "21"), ("grdp_current", "35"), ("grdp_constant_2010", "35"), ("grdp_current", "53"),
        ("grdp_constant_2010", "53"), ("grdp_current", "62"), ("grdp_constant_2010", "62"), ("grdp_current", "65"),
        ("grdp_constant_2010", "65")]},
    **{(indicator, code, 2014): 1.0 for indicator in KIND.values() for code in ("19", "31", "72")},
}
STEP = 0.01
READ_CONTEXT = {
    RAW_PROVINCES: {"encoding": "utf-8", "numbers": "none: every code and name is a JSON string"},
    **{path: {"encoding": "utf-8", "numbers": "ketersediaan_tahun: years as JSON integers"} for path in RAW_LISTS},
    **{path: {**SIMDASI_FORMAT,
              "unit_text": UNIT_TEXT if year in UNIT_TEXT_YEARS or (indicator, code, year) in UNIT_TEXT_ALSO else None,
              "unit": "Rp million" if (indicator, code, year) in MILLION_TABLES else "Rp billion",
              "step": PRINTED_STEP.get((indicator, code, year), STEP)}
       for (indicator, code, year), path in RAW_TABLES.items()},
}

# The two indicators, each with its yearbook table as the table lists give it (kode_tabel and id_tabel), the text its
# title and its one column must still carry, and its name
INDICATORS = {
    "grdp_current": {
        "kode_tabel": "13.1.1", "id_tabel": "S1RMUWRYb0NWc0Y5L05QQkxzcWw3Zz09",
        "title": "Produk Domestik Regional Bruto Atas Dasar Harga Berlaku Menurut Lapangan Usaha",
        "column": "Produk Domestik Bruto/Produk Domestik Regional Bruto Atas Dasar Harga Berlaku",
        "name": "Produk Domestik Regional Bruto atas dasar harga berlaku menurut lapangan usaha (GRDP at current "
                "prices by industry)",
    },
    "grdp_constant_2010": {
        "kode_tabel": "13.1.2", "id_tabel": "UklLSnFZZnMzMlJiSWpMOExJODIrQT09",
        "title": "Produk Domestik Regional Bruto Atas Dasar Harga Konstan 2010 Menurut Lapangan Usaha",
        "column": "Produk Domestik Bruto/Produk Domestik Regional Bruto Atas Dasar Harga Konstan 2010",
        "name": "Produk Domestik Regional Bruto atas dasar harga konstan 2010 menurut lapangan usaha (GRDP at constant "
                "2010 prices by industry)",
    },
}
KEYS = ["province_code", "indicator", "sector", "period"]
YEARS = range(2010, 2026)

# Years each table list gives (ketersediaan_tahun), read from the 38 lists: every province from 2014 to 2025 at both
# prices, except the first years listed here
FIRST_LISTED_DEFAULT = 2014
FIRST_LISTED = {
    "grdp_current": {"17": 2010, "19": 2010, "64": 2010, "81": 2015, "91": 2015, "94": 2015,
                     "92": 2020, "95": 2020, "96": 2020, "97": 2020},
    "grdp_constant_2010": {"17": 2015, "19": 2010, "64": 2010, "81": 2015, "91": 2015, "94": 2015,
                           "92": 2020, "95": 2020, "96": 2020, "97": 2020},
}

# Years the table lists give but BPS serves as empty shells (the row labels with no values) at both prices, so the
# download script saved no file: the four provinces split from Papua and Papua Barat in 2022, before 2023
EMPTY_SHELLS = {code: [2020, 2021, 2022] for code in ("92", "95", "96", "97")}

# The 17 KBLI categories, coded as in data/20261102_bps-province-grdp-population, each with the code the SIMDASI rows
# print; the numbered sub-categories of each category that has them, and the lettered items of each sub-category that
# has them, as the tables print them: a sub-category code appends its number to its category (B2), an item code its
# letter to its sub-category (A1a)
GROUPS = {"A": "A", "B": "B", "C": "C", "D": "D", "E": "E", "F": "F", "G": "G", "H": "H", "I": "I", "J": "J",
          "K": "K", "L": "L", "MN": "M,N", "O": "O", "P": "P", "Q": "Q", "RSTU": "R,S,T,U"}
SUBCATEGORIES = {"A": 3, "B": 4, "C": 16, "D": 2, "G": 2, "H": 6, "I": 2, "K": 4}
ITEMS = {"A1": "abcde"}

# The province total, the last row of every table, matched by its label_raw; it is named as its HTML label and the
# sibling datasets name it
TOTAL = "TOTAL"
TOTAL_LABEL = "Produk Domestik Bruto"
TOTAL_NAME = "Produk Domestik Regional Bruto"

# Coal and lignite mining, which the coal-share check reads; the row must still carry this label
COAL = "B2"
COAL_LABEL = "Pertambangan Batubara dan Lignit"

# Revision status of each year, which every value cell's marker must give: 2024 preliminary, 2025 very preliminary,
# and no marker on the cells of 2010-2023
STATUS_BY_YEAR = {2024: "*", 2025: "**"}

# Cells printed without the marker of their year, each with the value it prints; written with an empty status, as the
# cell has no marker: (indicator, province, sector, year)
NO_MARKER_CELLS = {("grdp_current", "81", "C13", 2024): 0.0, ("grdp_current", "81", "C13", 2025): 0.0,
                   ("grdp_constant_2010", "81", "C13", 2024): 0.0, ("grdp_constant_2010", "81", "C13", 2025): 0.0,
                   ("grdp_constant_2010", "17", "C3", 2025): 0.01}

# Statuses the table notes state, by the year of the table: the notes of the 2018 and 2019 tables state 2021 and 2022,
# years those tables do not hold; every other note states none
NOTE_STATUSES = {2018: {2021: "*", 2022: "**"}, 2019: {2021: "*", 2022: "**"}}

# Cells printed as an en dash, read from opening every table: indicator -> province -> sector -> years. The build
# stops unless the tables print an en dash in exactly these cells, leaving aside the excluded tables and cells. The
# tables of 2015 print no en dash: they print 0,00 where the tables of other years print one
NONE_OR_ZERO_CELLS = {
    "grdp_current": {
        "11": {"C11": "2016-2025", "H1": "2016-2022"},
        "12": {"B2": "2014, 2016-2025", "C1": "2018-2025"},
        "13": {"B1": "2016-2025", "C3": "2016", "C11": "2016-2025", "C13": "2016-2025"},
        "14": {"C3": "2014, 2016-2025", "C5": "2014, 2016-2025", "C11": "2014, 2016-2025", "C13": "2014, 2016-2025",
               "H1": "2014, 2016-2025"},
        "15": {"C11": "2016-2025", "H1": "2016-2025"},
        "16": {"B3": "2016-2025"},
        "17": {"B1": "2016-2025", "C1": "2016-2025", "C3": "2016-2022", "C13": "2016-2025", "H1": "2016-2025"},
        "18": {"B2": "2016-2025", "C5": "2016-2025"},
        "19": {"B2": "2010-2013, 2016-2025", "C1": "2010-2013, 2016-2025", "C3": "2010-2013, 2016-2025",
               "C5": "2010-2013, 2016-2025", "C13": "2010-2013, 2016-2025", "H1": "2010-2013, 2016-2025"},
        "21": {"B2": "2016-2025", "C1": "2018-2025", "H1": "2016-2025"},
        "31": {"A1c": "2016-2025", "A2": "2016-2025", "B2": "2016-2025", "B3": "2016-2025", "C3": "2016-2025"},
        "32": {"B2": "2016-2025"},
        "33": {"B2": "2016-2025", "B3": "2016-2025"},
        "34": {"B1": "2016-2025", "B2": "2016-2025", "B3": "2016-2025", "C1": "2016-2025", "C11": "2016-2025",
               "H3": "2016-2025", "H4": "2016-2025"},
        "35": {"B2": "2014, 2016-2025"},
        "51": {"B1": "2014, 2016-2025", "B2": "2014, 2016-2025", "B3": "2014, 2016-2025", "C1": "2014, 2016-2025",
               "C11": "2014, 2016-2025", "H1": "2014, 2016-2025"},
        "52": {"B1": "2014, 2016-2025", "B2": "2014, 2016-2025", "C1": "2014, 2016-2025", "C5": "2014, 2016-2025",
               "C13": "2014, 2016-2025", "H1": "2014, 2016-2025"},
        "53": {"B1": "2016-2025", "B2": "2016-2025", "C1": "2016-2025", "C5": "2016-2025", "C11": "2016-2025",
               "C13": "2016-2025", "C14": "2016-2025", "H1": "2016-2025"},
        "61": {"B1": "2014, 2016-2025", "C1": "2014, 2016-2025", "C3": "2014, 2016-2025", "H1": "2016-2025"},
        "62": {"C1": "2016-2025", "C3": "2016-2025", "C5": "2016-2025", "C11": "2016-2025", "H1": "2016-2025"},
        "63": {"C1": "2016-2025", "C3": "2016-2025", "C5": "2016-2025", "C11": "2016-2025", "H1": "2016-2025"},
        "64": {"C3": "2010-2014, 2016-2025", "C11": "2010-2014, 2016-2023", "H1": "2010-2014, 2016-2025"},
        "65": {"C1": "2016-2022", "C3": "2016-2025", "C11": "2014, 2016-2025", "H1": "2016-2025"},
        "71": {"B2": "2016-2025", "C1": "2016-2025", "C3": "2016-2025", "C13": "2016-2025", "H1": "2016-2025"},
        "72": {"B2": "2016-2025", "C13": "2016-2025", "H1": "2016-2025"},
        "73": {"B2": "2016-2017", "C1": "2016-2025", "C13": "2016-2025", "H1": "2016-2025"},
        "74": {"B1": "2014, 2016-2025", "B2": "2014, 2016-2025", "C1": "2014, 2016-2025", "C5": "2014, 2016-2025",
               "C13": "2014, 2016-2025", "H1": "2014, 2016-2025"},
        "75": {"B1": "2014, 2016-2025", "B2": "2014, 2016-2025", "C1": "2014, 2016-2025", "C3": "2014, 2016-2025",
               "C5": "2014, 2016-2025", "C11": "2014, 2016-2025", "H1": "2014, 2016-2025"},
        "76": {"B1": "2014, 2016-2025", "B2": "2014, 2016-2022", "B3": "2014, 2016-2022", "C1": "2014, 2016-2025",
               "C3": "2014, 2016-2025", "C5": "2014, 2016-2025", "C11": "2014, 2016-2025", "C13": "2014, 2016-2025",
               "H1": "2014, 2016-2025"},
        "81": {"B2": "2016-2025", "C1": "2016-2025", "C3": "2016-2025", "C5": "2016-2025", "C13": "2016",
               "H1": "2016-2025"},
        "82": {"B1": "2016-2025", "B2": "2016-2025", "C1": "2016-2025", "C3": "2016-2025", "C5": "2016-2025",
               "C9": "2016-2025", "C13": "2016-2025", "H1": "2016-2025"},
        "91": {"B2": "2016-2017, 2020, 2023-2025", "B3": "2017", "C3": "2016-2025", "C11": "2016-2025",
               "C13": "2016-2025", "H1": "2016-2025"},
        "92": {"C3": "2023-2025", "C11": "2023-2025", "C13": "2023-2025", "H1": "2023-2025"},
        "94": {"B1": "2016-2025", "B2": "2016-2025", "C1": "2016-2025", "C3": "2016-2025", "C11": "2016-2025",
               "C13": "2016-2025", "H1": "2016-2025"},
        "95": {"B1": "2023-2025", "B2": "2023-2025", "B3": "2023-2025", "C1": "2023-2025", "C3": "2023-2025",
               "C11": "2023-2025", "C13": "2023-2025", "H1": "2023-2025"},
        "96": {"B1": "2023-2025", "B2": "2023-2025", "C1": "2023-2025", "C3": "2023-2025", "C11": "2023-2025",
               "C13": "2023-2025", "H1": "2023-2025"},
        "97": {"B1": "2023-2025", "B2": "2023-2025", "B3": "2023-2025", "C1": "2023-2025", "C3": "2023-2025",
               "C5": "2023-2025", "C9": "2023-2025", "C11": "2023-2025", "C13": "2023-2025", "C14": "2023-2025",
               "H1": "2023-2025", "H3": "2023-2025", "K4": "2023-2025"},
    },
    "grdp_constant_2010": {
        "11": {"C11": "2016-2025", "H1": "2016-2022", "K4": "2016-2017"},
        "12": {"B2": "2014, 2016-2025", "C1": "2018-2025"},
        "13": {"B1": "2014, 2016-2025", "B3": "2016-2017", "C1": "2016-2017", "C3": "2014, 2016", "C11": "2014, 2016-2025",
               "C13": "2014, 2016-2025", "D2": "2016-2017"},
        "14": {"C3": "2016-2025", "C5": "2016-2025", "C11": "2016-2025", "C13": "2016-2025", "H1": "2016-2025"},
        "15": {"C3": "2016-2017", "C5": "2016-2017", "C11": "2016-2025", "H1": "2016-2025"},
        "16": {"B3": "2016-2025"},
        "17": {"B1": "2016-2025", "C1": "2016-2025", "C3": "2016-2022", "C5": "2016-2017", "C8": "2016-2017",
               "C11": "2016-2017", "C13": "2016-2025", "C14": "2016-2017", "D2": "2016-2017", "H1": "2016-2025",
               "K4": "2016-2017"},
        "18": {"B2": "2016-2025", "C5": "2016-2025"},
        "19": {"B2": "2010-2013, 2016-2025", "C1": "2010-2013, 2016-2025", "C3": "2010-2013, 2016-2025",
               "C5": "2010-2013, 2016-2025", "C13": "2010-2013, 2016-2025", "H1": "2010-2013, 2016-2025"},
        "21": {"B2": "2016-2025", "C1": "2018-2025", "H1": "2016-2025"},
        "31": {"A1c": "2016-2025", "A2": "2016-2025", "B2": "2016-2025", "B3": "2016-2025", "C3": "2016-2025"},
        "32": {"B2": "2016-2025", "H4": "2016-2017"},
        "33": {"B2": "2016-2025", "B3": "2016-2025"},
        "34": {"B1": "2016-2025", "B2": "2016-2025", "B3": "2016-2025", "C1": "2016-2025", "C11": "2016-2025",
               "D2": "2016-2017", "H3": "2016-2025", "H4": "2016-2025"},
        "35": {"B2": "2014, 2016-2025"},
        "36": {"C3": "2016-2017", "K4": "2016-2017"},
        "51": {"B1": "2014, 2016-2025", "B2": "2014, 2016-2025", "B3": "2014, 2016-2025", "C1": "2014, 2016-2025",
               "C11": "2014, 2016-2025", "H1": "2014, 2016-2025"},
        "52": {"B1": "2014, 2016-2025", "B2": "2014, 2016-2025", "C1": "2014, 2016-2025", "C5": "2014, 2016-2025",
               "C13": "2014, 2016-2025", "D2": "2016-2017", "H1": "2014, 2016-2025"},
        "53": {"B1": "2016-2025", "B2": "2016-2025", "C1": "2016-2025", "C3": "2016-2017", "C5": "2016-2025",
               "C9": "2016-2017", "C11": "2016-2025", "C13": "2016-2025", "C14": "2016-2025", "D2": "2016-2017",
               "H1": "2016-2025"},
        "61": {"B1": "2014, 2016-2025", "C1": "2014, 2016-2025", "C3": "2014, 2016-2025", "H1": "2016-2025"},
        "62": {"C1": "2016-2025", "C3": "2016-2025", "C5": "2016-2025", "C11": "2016-2025", "H1": "2016-2025"},
        "63": {"C1": "2016-2025", "C3": "2016-2025", "C5": "2016-2025", "C11": "2016-2025", "H1": "2016-2025"},
        "64": {"C3": "2010-2014, 2016-2025", "C11": "2010-2014, 2016-2023", "H1": "2010-2014, 2016-2025",
               "K4": "2016-2017"},
        "65": {"C1": "2014, 2016-2022", "C3": "2014, 2016-2025", "C11": "2014, 2016-2025", "D2": "2016",
               "H1": "2014, 2016-2025", "K4": "2016-2017"},
        "71": {"B2": "2016-2025", "C1": "2016-2025", "C3": "2016-2025", "C13": "2016-2025", "H1": "2016-2025"},
        "72": {"B2": "2016-2025", "C13": "2016-2025", "D2": "2016-2017", "H1": "2016-2025"},
        "73": {"B2": "2016-2017", "C1": "2016-2025", "C13": "2016-2025", "H1": "2016-2025"},
        "74": {"B1": "2014, 2016-2025", "B2": "2014, 2016-2025", "C1": "2014, 2016-2025", "C3": "2016-2017",
               "C5": "2014, 2016-2025", "C8": "2016-2017", "C13": "2014, 2016-2025", "D2": "2016-2017",
               "H1": "2014, 2016-2025"},
        "75": {"B1": "2014, 2016-2025", "B2": "2014, 2016-2025", "C1": "2014, 2016-2025", "C3": "2014, 2016-2025",
               "C5": "2014, 2016-2025", "C8": "2016-2017", "C11": "2014, 2016-2025", "C13": "2016-2017",
               "D2": "2016-2017", "H1": "2014, 2016-2025"},
        "76": {"B1": "2014, 2016-2025", "B2": "2014, 2016-2022", "B3": "2014, 2016-2022", "C1": "2014, 2016-2025",
               "C3": "2014, 2016-2025", "C5": "2014, 2016-2025", "C11": "2014, 2016-2025", "C13": "2014, 2016-2025",
               "H1": "2014, 2016-2025", "K4": "2016-2017"},
        "81": {"B2": "2016-2025", "C1": "2016-2025", "C3": "2016-2025", "C5": "2016-2025", "C8": "2016",
               "C11": "2016-2017", "C12": "2016-2017", "C13": "2016-2017", "D2": "2016-2017", "H1": "2016-2025"},
        "82": {"B1": "2016-2025", "B2": "2016-2025", "C1": "2016-2025", "C3": "2016-2025", "C5": "2016-2025",
               "C8": "2016-2017", "C9": "2016-2025", "C12": "2016-2017", "C13": "2016-2025", "H1": "2016-2025"},
        "91": {"B2": "2016-2017, 2020, 2023-2025", "B3": "2017", "C3": "2016-2025", "C9": "2016-2017",
               "C11": "2016-2025", "C13": "2016-2025", "D2": "2016-2017", "H1": "2016-2025"},
        "92": {"C3": "2023-2025", "C11": "2023-2025", "C13": "2023-2025", "H1": "2023-2025"},
        "94": {"B1": "2016-2025", "B2": "2016-2025", "C1": "2016-2025", "C3": "2016-2025", "C11": "2016-2025",
               "C13": "2016-2025", "H1": "2016-2025", "K4": "2016-2017"},
        "95": {"B1": "2023-2025", "B2": "2023-2025", "B3": "2023-2025", "C1": "2023-2025", "C3": "2023-2025",
               "C11": "2023-2025", "C13": "2023-2025", "H1": "2023-2025"},
        "96": {"B1": "2023-2025", "B2": "2023-2025", "C1": "2023-2025", "C3": "2023-2025", "C11": "2023-2025",
               "C13": "2023-2025", "H1": "2023-2025"},
        "97": {"B1": "2023-2025", "B2": "2023-2025", "B3": "2023-2025", "C1": "2023-2025", "C3": "2023-2025",
               "C5": "2023-2025", "C9": "2023-2025", "C11": "2023-2025", "C13": "2023-2025", "C14": "2023-2025",
               "H1": "2023-2025", "H3": "2023-2025", "K4": "2023-2025"},
    },
}

# Tables whose en dash also covers small values: in the constant-price tables of 2016 and 2017, some cells printed as an
# en dash hold a value at current prices (0.01 to 1.49 Rp billion), and the category above them includes it, so their
# sub-categories sum to less than the category. These cells are small values BPS did not print, not zeros; the build
# stops if a cell printed as an en dash at one price holds a value at the other price in any other table
SMALL_VALUES_AS_EN_DASH = {("grdp_constant_2010", 2016), ("grdp_constant_2010", 2017)}

# Cells printed with '...' (data not available) or 'NA' (data cannot be shown), read from opening every table outside
# the excluded ones: (indicator, province, year) -> (marker, rows), where rows is 'all' (the 62 rows), 'subsectors'
# (every sub-category and item: the 17 categories and TOTAL keep their values), 'subsectors except C6' or a list
UNPUBLISHED_CELLS = {
    ("grdp_current", "18", 2014): ("...", ["B2", "C5"]),
    ("grdp_constant_2010", "18", 2014): ("...", ["B2", "C5"]),
    **{("grdp_constant_2010", "19", year): ("...", [TOTAL]) for year in range(2010, 2014)},
    ("grdp_current", "31", 2014): ("...", "subsectors except C6"),
    ("grdp_constant_2010", "31", 2014): ("...", "subsectors"),
    ("grdp_current", "32", 2014): ("...", "all"),
    ("grdp_constant_2010", "32", 2014): ("...", "all"),
    ("grdp_current", "34", 2014): ("NA", "subsectors"),
    ("grdp_constant_2010", "34", 2014): ("NA", "subsectors"),
    ("grdp_current", "62", 2014): ("...", "subsectors"),
    ("grdp_constant_2010", "62", 2014): ("...", "subsectors"),
    ("grdp_current", "63", 2014): ("...", [TOTAL]),
    ("grdp_constant_2010", "65", 2014): ("...", ["K4"]),
    ("grdp_current", "71", 2014): ("...", "subsectors"),
    ("grdp_constant_2010", "71", 2014): ("...", "subsectors"),
    ("grdp_current", "82", 2014): ("...", "all"),
    ("grdp_constant_2010", "82", 2014): ("...", "all"),
}

# A table left out because its rows from this one through TOTAL repeat the current-price table of the same province
# and year: 14 (Riau) in 2014 prints current prices from C9 on, so its categories D-RSTU and TOTAL equal the current
# prices of var 2268, while A, B and C equal the constant prices of var 2267
CURRENT_IN_CONSTANT = {("grdp_constant_2010", "14", 2014): "C9"}

# Sub-categories left out at both prices because they are the same in the two tables and sum to neither table's
# category: (province, year) -> categories whose sub-categories are left out
SUBCATEGORIES_SUM_TO_NEITHER = {("61", 2014): ["G", "H", "I", "K"]}

# Items left out because they do not sum to their sub-category, which agrees with the rest of the table: Jawa Timur
# (35) at current prices in 2014 prints A1d 13.340,3 and A1e 24.239,8, whose ratios to the constant-price cells
# (0.45 and 13.5) lie far outside those of every other row of the table
ITEMS_NOT_SUMMING = {("grdp_current", "35", 2014): ("A1", ["A1d", "A1e"])}

# Areas the tables cover. Kalimantan Timur (64) never includes Kalimantan Utara (65), whose own tables start in 2014.
# Papua Barat (91) and Papua (94) cover the pre-split areas in their tables of 2015-2022 and the post-split areas from
# 2023, when the tables of the four new provinces start (read from the numbers: checks.borders)
PRE_SPLIT_YEARS = {"91": range(2015, 2023), "94": range(2015, 2023)}
SPLIT_YEAR = 2023
NEW_PROVINCES = {"92": "91", "95": "94", "96": "94", "97": "94"}
BORDER_CHANGES = {("91", SPLIT_YEAR), ("94", SPLIT_YEAR)}
KALTIM, KALTARA = "64", "65"

# Datasets this build checks against, written in the shared CSV format, with the units the checks expect. This build
# reads their CSVs and metadata and records their hashes, so all three must be rebuilt before this dataset
CHECK_INDUSTRY = ROOT / "data/20261103_bps-province-grdp-by-industry-2010-2025/20261103_bps-province-grdp-by-industry-2010-2025.csv"
CHECK_286 = ROOT / "data/20261103_bps-province-grdp-2010-2025/20261103_bps-province-grdp-2010-2025.csv"
CHECK_DETAILED = ROOT / "data/20261103_bps-province-grdp-detailed-industry/20261103_bps-province-grdp-detailed-industry.csv"
CHECK_UNITS = {
    CHECK_INDUSTRY: {"grdp_current": "Rp billion (Milyar Rupiah)", "grdp_constant_2010": "Rp billion (Milyar Rupiah)"},
    CHECK_286: {"grdp_current": "Rp billion (Milyar Rupiah)", "grdp_constant_2010": "Rp billion (Milyar Rupiah)"},
    CHECK_DETAILED: {"grdp_current": "Rp billion (miliar rupiah)"},
}
CHECK_CONTEXT = {path: {"encoding": "utf-8", "delimiter": ",", "decimal": ".", "thousands": None, "units": units}
                 for path, units in CHECK_UNITS.items()}

# Tolerances in Rp billion. Each value BPS rounds to its printed step (0.01 in most tables) is off by at most half a
# step, so parts and their total can differ by up to half a step per value; the WebAPI tables round to 0.01
TOL_WEBAPI = 0.005       # half a unit in the last decimal of the WebAPI values
TOL_VAR_286 = 0.04       # var 286 and vars 2267/2268 are rounded apart and differ by up to 0.03 (by-industry dataset)
TOL_BASE_YEAR = 0.01     # one unit in the last decimal: the two price tables are rounded apart
TOL_SAME_RELEASE = 0     # data/20261103_bps-province-grdp-detailed-industry reads the same raw files: exactly
TOL_MILLION = 0.01       # one unit in the WebAPI's last decimal, against a factor of 1000 in Rp billion
TOLERANCE_REASONS = {
    "identity": "(number of parts + 1) x half the table's printed step: each part and the total is rounded to that "
                "step, so 0.09 for the 17 categories and TOTAL of a table printed to 0.01",
    "webapi": f"half the table's printed step plus {TOL_WEBAPI}, half a unit of the WebAPI's 2 decimals: 0.01 for a "
              f"table printed to 0.01",
    "var_286": f"the WebAPI tolerance plus {TOL_VAR_286}: var 286 and vars 2267/2268 are rounded apart and differ by up "
               f"to 0.03 (data/20261103_bps-province-grdp-by-industry-2010-2025, checks.cross_source)",
    "base_year": f"one unit in the last decimal ({TOL_BASE_YEAR}): the current-price and constant-price tables are "
                 f"rounded apart",
    "million": f"{TOL_MILLION}, one unit in the WebAPI's last decimal: each value divided by 1000 lands on the WebAPI "
               f"value in Rp billion, where a table in Rp billion would be 1000 times larger (19 in 2014 differs by up "
               f"to 0.007, an earlier revision in whole Rp million)",
}

# Tables whose 17 categories or TOTAL differ from the WebAPI values (vars 2267/2268, and var 286 for TOTAL) by more
# than rounding, each with its largest gap in Rp billion and the reason. The build stops if any other table differs by
# more than rounding, if one of these exceeds its gap, or if one no longer differs from vars 2267/2268 by more than
# rounding. Every other yearbook table, old or new, carries the values of vars 2267/2268 within its rounding
REVISION_GAPS = {
    ("grdp_current", "31", 2014): (0.91, "printed in whole Rp billion from an earlier revision: every category is within "
                                         "1 Rp billion of var 2268, beyond the 0.5 that rounding explains"),
    ("grdp_constant_2010", "31", 2014): (0.89, "printed in whole Rp billion from an earlier revision: every category is "
                                               "within 1 Rp billion of var 2267, beyond the 0.5 that rounding explains"),
    ("grdp_current", "76", 2022): (5.4, "A is 5.40 Rp billion lower and C 5.40 higher than in var 2268, TOTAL equal: "
                                        "the two releases split A and C differently"),
    ("grdp_constant_2010", "76", 2022): (5.4, "A is 5.40 Rp billion lower and C 5.40 higher than in var 2267, TOTAL "
                                              "equal: the two releases split A and C differently"),
    ("grdp_constant_2010", "76", 2023): (0.37, "A, C and TOTAL are 0.35, 0.03 and 0.37 Rp billion higher than in vars "
                                               "2267 and 286; the change log records 'Revisi Provinsi Sulawesi Barat'"),
    ("grdp_constant_2010", "76", 2024): (1.32, "A, C, K and TOTAL are 1.29, 0.02, 0.02 and 1.32 Rp billion higher than "
                                               "in vars 2267 and 286"),
}

# In 2023, on the pre-split borders, the categories and TOTAL of Papua Barat (91 + 92) that differ from var 2268's or
# var 2267's 91 by more than rounding, each with its gap (Rp billion); 94 + 95 + 96 + 97 equals their 94 within rounding
OLD_BORDER_GAPS = {("grdp_current", "A"): 5.0, ("grdp_current", "D"): 0.1, ("grdp_current", TOTAL): 5.1,
                   ("grdp_constant_2010", "A"): 11.0, ("grdp_constant_2010", TOTAL): 11.0}

# Plausibility ranges (layer 5); a value outside its range is flagged, not dropped, and a range ending in None is open
# above. Growth compares each year with the year before, shares use current prices
PLAUSIBLE = {
    "value_nonnegative": (0, None),
    "grdp_growth_pct": (-20, 40),
    "grdp_real_growth_pct": (-15, 25),
    "sector_growth_pct": (-50, 100),
    "sector_real_growth_pct": (-50, 100),
    "sector_growth_from_zero": (0, 0),
    "sector_share_pct": (0, 50),
    "coal_share_pct": (0, 40),
}
PLAUSIBLE_MEASURES = {
    "value_nonnegative": "every value, Rp billion",
    "grdp_growth_pct": "TOTAL at current prices: (grdp_current in year t / grdp_current in year t-1 - 1) x 100; the range "
                       "of data/20261103_bps-province-grdp-detailed-industry",
    "grdp_real_growth_pct": "TOTAL at constant 2010 prices, the same formula on grdp_constant_2010; the range of "
                            "data/20261103_bps-province-grdp-by-industry-2010-2025",
    "sector_growth_pct": "every sector except TOTAL at current prices, the same formula; the range of "
                         "data/20261103_bps-province-grdp-detailed-industry",
    "sector_real_growth_pct": "every sector except TOTAL at constant 2010 prices, the same formula; the range of "
                              "data/20261103_bps-province-grdp-by-industry-2010-2025",
    "sector_growth_from_zero": "the value, Rp billion, of a sector whose value the year before is 0, at either price; "
                               "it has no growth rate",
    "sector_share_pct": "each of the 17 categories as a share of TOTAL at current prices: grdp_current of the category / "
                        "grdp_current of TOTAL x 100",
    "coal_share_pct": f"{COAL} / TOTAL x 100 at current prices; the range of "
                      f"data/20261103_bps-province-grdp-detailed-industry",
}

# Where the raw files come from; each WebAPI request also ends in /key/ and a registered key, left out here
URL_PROVINCES = "https://sig.bps.go.id/rest-bridging/getwilayah?level=provinsi&periode_merge=2025_1.2025"
URL_LIST = "https://webapi.bps.go.id/v1/api/interoperabilitas/datasource/simdasi/id/23/wilayah/<kode_bps>00000"
URL_TABLE = ("https://webapi.bps.go.id/v1/api/interoperabilitas/datasource/simdasi/id/25/wilayah/<kode_bps>00000"
             "/tahun/<year>/id_tabel/{id_tabel}")


# Functions

def posix(path):
    """Return a path relative to the repository root with forward slashes."""
    return Path(path).resolve().relative_to(ROOT).as_posix()


def and_list(items):
    """Return items joined for a sentence: 'a', 'a and b', or 'a, b and c'."""
    items = [str(i) for i in items]
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def parse_years(text):
    """Return the years a declaration such as '2014, 2016-2025' names."""
    years = set()
    for part in text.split(","):
        first, _, last = part.strip().partition("-")
        years.update(range(int(first), int(last or first) + 1))
    return years


def year_runs(years):
    """Return years written as runs, such as '2014, 2016-2025'."""
    years, runs = sorted(set(years)), []
    for year in years:
        if runs and year == runs[-1][1] + 1:
            runs[-1][1] = year
        else:
            runs.append([year, year])
    return ", ".join(str(a) if a == b else f"{a}-{b}" for a, b in runs)


def sector_list():
    """Return the 62 sector codes in table order, each mapped to (level, parent code)."""
    sectors = {}
    for group in GROUPS:
        sectors[group] = ("category", TOTAL)
        for n in range(1, SUBCATEGORIES.get(group, 0) + 1):
            sub = f"{group}{n}"
            sectors[sub] = ("subcategory", group)
            for letter in ITEMS.get(sub, ""):
                sectors[sub + letter] = ("item", sub)
    sectors[TOTAL] = ("total", None)
    return sectors


def sector_code(record, where):
    """Return a SIMDASI row's sector code from its category, sub-category number and item letter."""
    # The one row outside the hierarchy is the province total, matched by its label
    if record["category"] is None:
        if record["label"] != TOTAL_LABEL:
            raise ValueError(f"{where}: row {record['label']!r} has no category and is not the total row")
        return TOTAL
    codes = {printed: code for code, printed in GROUPS.items()}
    if record["category"] not in codes:
        raise ValueError(f"{where}: category {record['category']!r} is not one of the 17 groups")
    return codes[record["category"]] + (record["subcategory"] or "") + (record["item"] or "")


def sector_name(sector, level, label):
    """Return a sector's name: its label_raw without the code a category prints, and TOTAL_NAME for the total."""
    if level == "total":
        return TOTAL_NAME
    if level != "category":
        return label
    # A category's label_raw starts with the code it prints and a space, as in 'M,N Jasa Perusahaan'
    printed = GROUPS[sector] + " "
    if not label.startswith(printed):
        raise ValueError(f"category {sector} is {label!r}, expected it to start with {printed!r}")
    return label[len(printed):]


def listed_years(indicator, code):
    """Return the years the table list should give a province's table: from its first listed year to 2025."""
    return list(range(FIRST_LISTED[indicator].get(code, FIRST_LISTED_DEFAULT), YEARS[-1] + 1))


def read_table_list(path, code):
    """Read one province's SIMDASI table list and return {indicator: its entry for the indicator's table}."""
    reply = json.loads(path.read_text(encoding=READ_CONTEXT[path]["encoding"]))
    listing = reply["data"][1]["data"]
    entries = {}
    for indicator, spec in INDICATORS.items():
        # The table id must appear once, still as the declared kode_tabel and title
        found = [row for row in listing if row.get("id_tabel") == spec["id_tabel"]]
        if len(found) != 1:
            raise ValueError(f"{path.name}: table {spec['id_tabel']} appears {len(found)} times")
        entry = found[0]
        if entry["kode_tabel"] != spec["kode_tabel"]:
            raise ValueError(f"{path.name}: {spec['id_tabel']} is now table {entry['kode_tabel']}")
        cleaning.require_text(" ".join(entry["judul"].split()), spec["title"], f"{path.name} {spec['kode_tabel']}")
        # The years BPS lists must be the declared ones
        if sorted(entry["ketersediaan_tahun"]) != listed_years(indicator, code):
            raise ValueError(f"{path.name}: {spec['kode_tabel']} lists {sorted(entry['ketersediaan_tahun'])}, "
                             f"declared {listed_years(indicator, code)}")
        entries[indicator] = entry
    return entries


def raw_table_fields(path):
    """Return the fields of a saved SIMDASI table that read_simdasi_table does not return: the note as published
    (HTML, which parse_status_note reads clause by clause), the table version and its creation time."""
    table = json.loads(path.read_text(encoding=READ_CONTEXT[path]["encoding"]))["data"][1]
    return {"note_html": table.get("catatan"), "versi": table.get("versi"), "table_created": table.get("table_created")}


def read_table(key, path, name, lookup, sectors):
    """Read one SIMDASI table with its declared format; check its area, title, unit text and column; return its
    description and its cells by sector code, in table order."""
    indicator, code, year = key
    c = READ_CONTEXT[path]
    table, records = cleaning.read_simdasi_table(path, year, name, decimals=c["decimals"], unit_text=c["unit_text"],
                                                 decimal=c["decimal"], thousands=c["thousands"], missing=c["missing"],
                                                 encoding=c["encoding"])
    # The table's area name must map to the file's province code through the BPS list
    cleaning.province_code(table["area"], lookup, code)

    # The title must still name the indicator's table; a title without the declared unit text names no unit at all,
    # and no English title names another unit than Rp billion
    title, title_en = " ".join(table["title"].split()), " ".join((table["title_en"] or "").split())
    cleaning.require_text(title, INDICATORS[indicator]["title"], f"{path.name} title")
    if c["unit_text"] is None and "rupiah" in title.lower():
        raise ValueError(f"{path.name}: title {title!r} names a unit the build does not declare")
    if c["unit_text"] is not None:
        cleaning.require_text(title_en, UNIT_TEXT_EN, f"{path.name} English title")
    if "million" in title_en.lower() or "juta" in title.lower():
        raise ValueError(f"{path.name}: title names Rp million")

    # The one column must still name the indicator
    if len(table["columns"]) != 1:
        raise ValueError(f"{path.name}: {len(table['columns'])} columns, expected 1")
    column = next(iter(table["columns"].values()))["name"]
    if column != INDICATORS[indicator]["column"]:
        raise ValueError(f"{path.name}: column {column!r}, expected {INDICATORS[indicator]['column']!r}")

    # Every row maps to its own sector code, and the codes run in the expected table order
    cells = {}
    for r in records:
        sector = sector_code(r, path.name)
        if sector in cells:
            raise ValueError(f"{path.name}: two rows map to sector {sector}")
        cells[sector] = r
    if list(cells) != list(sectors):
        raise ValueError(f"{path.name}: rows map to {list(cells)}, expected {list(sectors)}")
    return table, cells


def unpublished_rows(spec, sectors):
    """Return the sectors an UNPUBLISHED_CELLS entry names."""
    subsectors = [s for s, (level, _) in sectors.items() if level in ("subcategory", "item")]
    if spec == "all":
        return list(sectors)
    if spec == "subsectors":
        return subsectors
    if spec == "subsectors except C6":
        return [s for s in subsectors if s != "C6"]
    return list(spec)


def excluded_cells(sectors):
    """Return every excluded cell (indicator, province, year, sector) with its reason, leaving aside whole tables."""
    out = {}
    for (code, year), groups in SUBCATEGORIES_SUM_TO_NEITHER.items():
        for indicator in INDICATORS:
            for s, (level, parent) in sectors.items():
                if level == "subcategory" and parent in groups:
                    out[(indicator, code, year, s)] = "subcategories_sum_to_neither"
    for (indicator, code, year), (_, items) in ITEMS_NOT_SUMMING.items():
        for s in items:
            out[(indicator, code, year, s)] = "items_not_summing"
    return out


def excluded_tables():
    """Return every excluded table (indicator, province, year) with its reason."""
    return {**{k: "million_rupiah" for k in MILLION_TABLES}, **{k: "current_in_constant" for k in CURRENT_IN_CONSTANT}}


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


def table_step(key):
    """Return the step a table prints its values to, in its own unit."""
    return PRINTED_STEP.get(key, STEP)


def identity_checks(values, cell_state, tables_kept, sectors):
    """Layer 3: in every kept table, the 17 categories sum to TOTAL, the numbered sub-categories to their category and
    A1a-A1e to A1, within (parts + 1) x half the printed step, an en dash counting as zero. A parent whose parts
    include an en dash hiding a small value (SMALL_VALUES_AS_EN_DASH) must exceed its printed parts by no more than the
    current-price values of those cells divided by the table's smallest price ratio; a parent with an unpublished part
    must be no smaller than its printed parts; a parent or part that is unpublished or excluded is otherwise not
    checked."""
    parts_of = collections.defaultdict(list)
    for s, (level, parent) in sectors.items():
        if parent is not None:
            parts_of[parent].append(s)
    full = collections.defaultdict(dict)
    bounded, one_sided, not_checked = [], [], collections.Counter()
    for key in tables_kept:
        indicator, code, year = key
        step = table_step(key)
        for parent, parts in parts_of.items():
            tol = round((len(parts) + 1) * step / 2, 6)
            parent_value = values.get((code, indicator, parent, str(year)))
            if parent_value is None:
                not_checked[f"parent {cell_state[key + (parent,)]}"] += 1
                continue
            states = [cell_state[key + (s,)] for s in parts]
            printed = round(sum(values.get((code, indicator, s, str(year)), 0.0) for s in parts), 6)
            where = {"indicator": indicator, "province_code": code, "period": str(year), "sector": parent}
            if "excluded" in states:
                not_checked["a part excluded"] += 1
            elif "unpublished" in states:
                # Printed parts can only fall short of the parent
                one_sided.append({**where, "printed_parts": round(printed, 6), "parent": parent_value, "tolerance": tol})
                if printed > parent_value + tol:
                    raise ValueError(f"identity: {where} printed parts {printed} exceed the parent {parent_value}")
            elif "small value" in states:
                # The parent includes the small values the en dash hides. Their current-price cells, divided by the
                # smallest ratio of current to constant prices among the table's rows of at least 1 Rp billion, bound
                # them: a hidden row's prices are assumed to have risen no less than those of every such row
                hidden = [s for s, st in zip(parts, states) if st == "small value"]
                hidden_current = sum(values[(code, "grdp_current", s, str(year))] for s in hidden)
                ratio = min(values[(code, "grdp_current", s, str(year))] / values[(code, indicator, s, str(year))]
                            for s in sectors if min(values.get((code, "grdp_current", s, str(year)), 0),
                                                    values.get((code, indicator, s, str(year)), 0)) >= 1)
                bound = hidden_current / ratio
                gap = parent_value - printed
                bounded.append({**where, "gap": round(gap, 6), "hidden": hidden,
                                "hidden_current": round(hidden_current, 6), "smallest_price_ratio": round(ratio, 4),
                                "bound": round(bound, 6), "tolerance": tol})
                if not -tol <= gap <= bound + tol:
                    raise ValueError(f"identity: {where} gap {gap} outside [-{tol}, {bound} + {tol}]")
            else:
                full[(parent, step)][(indicator, code, str(year))] = (printed, parent_value)

    # One check_sum per parent and printed step, each with its own rounding tolerance
    results = []
    for (parent, step), cells in sorted(full.items(), key=lambda kv: (list(sectors).index(kv[0][0]), kv[0][1])):
        n = len(parts_of[parent])
        tol = round((n + 1) * step / 2, 6)
        index = pd.MultiIndex.from_tuples(list(cells), names=["indicator", "province_code", "period"])
        sums = pd.Series([v[0] for v in cells.values()], index=index)
        totals = pd.Series([v[1] for v in cells.values()], index=index)
        level = {"total": "the 17 categories", "category": "its numbered sub-categories",
                 "subcategory": "its lettered items"}[sectors[parent][0]]
        result = cleaning.check_sum(sums, totals, tol, f"{level} sum to {parent}, tables printed to {step:g}, "
                                                        f"en-dash cells counted as zero, Rp billion")
        results.append({**result, "tolerance_reason": TOLERANCE_REASONS["identity"]})
    worst_bounded = max(bounded, key=lambda b: b["gap"] / b["bound"])
    results.append({
        "check": "a parent with a part printed as an en dash that hides a small value exceeds its printed parts by at "
                 "least minus the rounding tolerance and at most bound plus it, where bound = the current-price values "
                 "of those parts / the smallest ratio of current to constant prices among the rows of at least 1 Rp "
                 "billion in the same province and year",
        "compared": len(bounded),
        "largest_gap": max(b["gap"] for b in bounded),
        "largest_gap_to_bound": round(worst_bounded["gap"] / worst_bounded["bound"], 4),
        "cells": bounded,
    })
    results.append({
        "check": "a parent with an unpublished part ('...' or 'NA') is no smaller than its printed parts",
        "compared": len(one_sided),
        "largest_excess": round(max((o["printed_parts"] - o["parent"] for o in one_sided), default=0.0), 6),
    })
    results.append({"check": "parents not checked", "counts": dict(sorted(not_checked.items()))})
    return results


def step_tolerance(step, extra=0.0):
    """Return the cross-source tolerance for a printed step: half the step plus the WebAPI's half unit, plus extra."""
    return round(step / 2 + TOL_WEBAPI + extra, 6)


def rounding_tolerance(key, extra=0.0):
    """Return the cross-source tolerance of a table from its printed step."""
    return step_tolerance(table_step(key), extra)


def compare_tables(ours, theirs, extra, label, reason):
    """Layer 4: compare values keyed (indicator, code, sector, year) table by table: each table within its rounding
    tolerance (plus extra), unless REVISION_GAPS declares a larger gap for it. Stops if a table beyond rounding is not
    declared. Returns one compare_sources result per printed step and per declared table, and the tables beyond
    rounding."""
    groups = collections.defaultdict(dict)
    beyond = set()
    for k, v in ours.items():
        if k not in theirs:
            continue
        table = (k[0], k[1], k[3])
        if abs(v - theirs[k]) > rounding_tolerance(table, extra) + 1e-9:
            beyond.add(table)
        group = (1, table) if table in REVISION_GAPS else (0, table_step(table))
        groups[group][k] = v
    undeclared = beyond - set(REVISION_GAPS)
    if undeclared:
        raise ValueError(f"{label}: tables beyond rounding that REVISION_GAPS does not declare: {sorted(undeclared)}")
    results = []
    for (declared, what), first in sorted(groups.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
        if declared:
            tol = REVISION_GAPS[what][0]
            text = f"{' '.join(str(x) for x in what)}, declared in REVISION_GAPS: {REVISION_GAPS[what][1]}"
        else:
            tol = step_tolerance(what, extra)
            text = f"tables printed to {what:g}"
        result = cleaning.compare_sources(first, {k: theirs[k] for k in first}, tol, f"{label}: {text}")
        result["keys"] = "[indicator, province_code, sector, year]; first = this dataset, second = the check dataset"
        result["tolerance_reason"] = "the stated largest gap" if declared else reason
        results.append(result)
    return results, beyond


def year_on_year(values, indicator, wanted, codes_order, sector_order):
    """Return the change (%) from the year before of every province and sector in wanted with a value in both years,
    leaving out a change across a border change, and apart from them the later values of those whose earlier value
    is 0, which have no growth rate."""
    growth, from_zero = [], []
    for (code, ind, sector, period), now in sorted(values.items(), key=lambda kv: (codes_order[kv[0][0]],
                                                                                  sector_order[kv[0][2]], kv[0][3])):
        if ind != indicator or sector not in wanted:
            continue
        year = int(period)
        before = values.get((code, ind, sector, str(year - 1)))
        if before is None or (code, year) in BORDER_CHANGES:
            continue
        # Each row keeps both values it compares, so a flag shows them
        row = {"province_code": code, "indicator": ind, "sector": sector, "period": period,
               "rp_billion": {str(year - 1): before, period: now}}
        if before == 0:
            from_zero.append({**row, "value": now})
        else:
            growth.append({**row, "value": 100 * (now / before - 1)})
    return growth, from_zero


def flag_range(rows, check):
    """Layer 5: flag the rows whose value lies outside the check's stated range, which None leaves open above."""
    low, high = PLAUSIBLE[check]
    flags = cleaning.flag_outside(rows, check, low, math.inf if high is None else high)
    # Each flag states the range as declared, since JSON has no infinity
    return [{**f, "range": [low, high]} for f in flags]


def general_title(title, area, year):
    """Return a table title with its province and year replaced by placeholders and spaces collapsed."""
    return " ".join(title.replace(area, "<province>").replace(f", {year}", ", <year>").split())


# Steps

# Print in UTF-8 so BPS labels and markers show on any console
sys.stdout.reconfigure(encoding="utf-8")

# Read the BPS province list that every province name and code is matched against; load_bps_provinces reads UTF-8,
# so a list declared in another encoding stops the build
if READ_CONTEXT[RAW_PROVINCES]["encoding"] != "utf-8":
    raise ValueError(f"{RAW_PROVINCES.name} is declared {READ_CONTEXT[RAW_PROVINCES]}, but is read as UTF-8")
provinces, lookup = cleaning.load_bps_provinces(RAW_PROVINCES)
codes = [c for c in provinces if c != cleaning.NATIONAL_CODE]
codes_order = {c: i for i, c in enumerate(codes)}

# Stop unless both download scripts the metadata names are in the repository
for script in DOWNLOAD_SCRIPTS:
    if not (ROOT / script).is_file():
        raise FileNotFoundError(f"download script {script} not found")

# Stop unless every table-like file in the folder has a declared name, and the folder holds one table list per
# province
odd = [p.name for p in RAW_DIR.glob("20261103_bps-grdp-*") if not TABLE_FILE.fullmatch(p.name)]
if odd:
    raise ValueError(f"files in {posix(RAW_DIR)} with no declared name pattern: {odd}")
if RAW_LISTS != [RAW_DIR / RAW_LIST_NAME.format(code=c) for c in codes]:
    raise ValueError(f"table lists {[p.name for p in RAW_LISTS]}, expected one per province")

# Read every table list: the table ids, codes and titles must hold, and the years BPS lists must be the declared ones
listings = {code: read_table_list(RAW_DIR / RAW_LIST_NAME.format(code=code), code) for code in codes}

# Stop unless the folder holds exactly one table for every listed year that is not an empty shell
expected_tables = {(indicator, code, year) for indicator in INDICATORS for code in codes
                   for year in listed_years(indicator, code) if year not in EMPTY_SHELLS.get(code, [])}
if set(RAW_TABLES) != expected_tables:
    raise ValueError(f"tables missing {sorted(expected_tables - set(RAW_TABLES))[:10]}, "
                     f"unexpected {sorted(set(RAW_TABLES) - expected_tables)[:10]}")
paths = {k: RAW_TABLES[k] for k in sorted(RAW_TABLES, key=lambda k: (list(INDICATORS).index(k[0]), codes_order[k[1]], k[2]))}

# Build the 62 sector codes in table order, with their levels and parents
sectors = sector_list()
sector_order = {s: i for i, s in enumerate(sectors)}

# Read every table: its description, its cells by sector, and the fields read_simdasi_table leaves out
tables, cells, extra, labels = {}, {}, {}, {}
for key, path in paths.items():
    tables[key], cells[key] = read_table(key, path, provinces[key[1]]["name"], lookup, sectors)
    extra[key] = raw_table_fields(path)
    # Every table must give a sector the same label
    for sector, r in cells[key].items():
        if labels.setdefault(sector, r["label"]) != r["label"]:
            raise ValueError(f"{path.name}: {sector} is {r['label']!r}, other tables say {labels[sector]!r}")

# Stop unless the coal row still carries the coal and lignite mining label
if labels[COAL] != COAL_LABEL:
    raise ValueError(f"{COAL} is {labels[COAL]!r}, expected {COAL_LABEL!r}")

# Stop unless every table has the same marker legend, which the metadata keeps once
first = tables[next(iter(tables))]
for key, table in tables.items():
    if table["legend"] != first["legend"]:
        raise ValueError(f"{key}: legend {table['legend']} differs from {first['legend']}")
    for marker in [EN_DASH, *UNPUBLISHED_MARKERS]:
        if marker not in table["legend"]:
            raise ValueError(f"{key}: the legend no longer defines {marker!r}")

# Every table note must state the declared statuses only, for years other than the table's own
for key, fields in extra.items():
    stated = cleaning.parse_status_note(fields["note_html"])
    if stated != NOTE_STATUSES.get(key[2], {}):
        raise ValueError(f"{key}: note states {stated}, declared {NOTE_STATUSES.get(key[2], {})}")
    if key[2] in stated:
        raise ValueError(f"{key}: note states a status for the table's own year")

# The million-rupiah note must be in exactly the declared tables
million_noted = {k for k, t in tables.items() if MILLION_NOTE in t["notes"]}
if million_noted != MILLION_NOTE_TABLES:
    raise ValueError(f"tables noting {MILLION_NOTE!r}: {sorted(million_noted)}, declared {sorted(MILLION_NOTE_TABLES)}")

# Each table's printed step must hold: every value of a declared coarse table is a multiple of its step, and every other
# table with values prints at least one value that is not a multiple of 0.1
for key, table_cells in cells.items():
    printed = [r["value"] for r in table_cells.values() if r["value"] is not None]
    if not printed:
        continue
    cents = [round(v * 100) for v in printed]
    if key in PRINTED_STEP:
        unit = round(PRINTED_STEP[key] * 100)
        if any(c % unit for c in cents):
            raise ValueError(f"{key}: declared printed to {PRINTED_STEP[key]}, but prints finer values")
    elif all(c % 10 == 0 for c in cents):
        raise ValueError(f"{key}: prints no value finer than 0.1; declare its step in PRINTED_STEP")

# Sort every cell: a cell of an excluded table or an excluded cell is left out with its reason, an en dash or an
# unpublished marker is a gap with no row, and a value becomes a row with its cell's marker as status
tables_out = excluded_tables()
cells_out = excluded_cells(sectors)
for key in tables_out:
    if key not in cells:
        raise ValueError(f"excluded table {key} is not among the tables read")
values, statuses, cell_state = {}, {}, {}
en_dash, unpublished, unmarked = set(), {}, set()
for key, table_cells in cells.items():
    indicator, code, year = key
    for sector, r in table_cells.items():
        cell = key + (sector,)
        if key in tables_out or cell in cells_out:
            cell_state[cell] = "excluded"
            continue
        if r["value"] is None:
            if r["value_code"] == EN_DASH:
                en_dash.add(cell)
                cell_state[cell] = "en dash"
            else:
                unpublished[cell] = r["value_code"]
                cell_state[cell] = "unpublished"
            continue
        # A value carries its year's marker, except the cells declared as printed without one
        if (indicator, code, sector, year) in NO_MARKER_CELLS:
            if r["value_code"] or r["value"] != NO_MARKER_CELLS[(indicator, code, sector, year)]:
                raise ValueError(f"{cell}: declared without a marker, but holds {r['value']} [{r['value_code']}]")
            unmarked.add((indicator, code, sector, year))
        elif r["value_code"] != STATUS_BY_YEAR.get(year, ""):
            raise ValueError(f"{cell}: marker {r['value_code']!r}, expected {STATUS_BY_YEAR.get(year, '')!r}")
        k = (code, indicator, sector, str(year))
        values[k], statuses[k] = r["value"], r["value_code"]
        cell_state[cell] = "value"

# Stop unless every declared cell without a marker was found as such
if unmarked != set(NO_MARKER_CELLS):
    raise ValueError(f"cells declared without a marker but not found so: {sorted(set(NO_MARKER_CELLS) - unmarked)}")

# Stop unless the en-dash cells are exactly the declared ones
declared_dash = {(indicator, code, year, sector) for indicator, by_code in NONE_OR_ZERO_CELLS.items()
                 for code, by_sector in by_code.items() for sector, years in by_sector.items()
                 for year in parse_years(years)}
if en_dash != declared_dash:
    raise ValueError(f"en-dash cells differ from NONE_OR_ZERO_CELLS: printed but not declared "
                     f"{sorted(en_dash - declared_dash)[:10]}, declared but not printed "
                     f"{sorted(declared_dash - en_dash)[:10]}")

# Stop unless the unpublished cells are exactly the declared ones, each with its declared marker
declared_unpublished = {key + (s,): marker for key, (marker, spec) in UNPUBLISHED_CELLS.items()
                        for s in unpublished_rows(spec, sectors)}
if unpublished != declared_unpublished:
    differ = set(unpublished.items()) ^ set(declared_unpublished.items())
    raise ValueError(f"unpublished cells differ from UNPUBLISHED_CELLS: {sorted(differ)[:10]}")

# Sort the en-dash cells by what the other price prints: an en dash, a zero, a value, or no table. A value at the
# other price means the en dash hides a small value, allowed only in the declared tables
small_values = {}
for cell in sorted(en_dash):
    indicator, code, year, sector = cell
    other = "grdp_current" if indicator == "grdp_constant_2010" else "grdp_constant_2010"
    v = values.get((code, other, sector, str(year)))
    if v:
        if (indicator, year) not in SMALL_VALUES_AS_EN_DASH:
            raise ValueError(f"{cell}: printed as an en dash, but {other} holds {v}")
        small_values[cell] = v
        cell_state[cell] = "small value"
for indicator, year in SMALL_VALUES_AS_EN_DASH:
    if not any(c[0] == indicator and c[2] == year for c in small_values):
        raise ValueError(f"{indicator} {year}: declared to hide small values under the en dash, but hides none")

# Read the three check datasets; the sectors here must be those of data/20261103_bps-province-grdp-detailed-industry
check_industry, meta_industry = read_check_dataset(CHECK_INDUSTRY)
check_286, meta_286 = read_check_dataset(CHECK_286)
check_detailed, meta_detailed = read_check_dataset(CHECK_DETAILED)
names = {s: sector_name(s, level, labels[s]) for s, (level, _) in sectors.items()}
sector_meta = {s: {"name": names[s], "label_raw": labels[s], "level": level, "parent": parent}
               for s, (level, parent) in sectors.items()}
if meta_detailed["sectors"] != sector_meta:
    raise ValueError(f"{CHECK_DETAILED.name} describes its sectors differently from these tables")
industry = {(i, c, s, int(p)): v for (c, i, s, p), (v, _) in check_industry.items() if p.isdigit()}
industry_status = {(i, c, s, int(p)): m for (c, i, s, p), (_, m) in check_industry.items() if p.isdigit()}
var286 = {(i, c, s, int(p)): v for (c, i, s, p), (v, _) in check_286.items()}

# Verify each exclusion against the numbers: a million-rupiah table is 1000 times the WebAPI values in its 17
# categories and TOTAL (the misprinted TOTAL aside, whose categories sum to the WebAPI TOTAL)
categories = [s for s, (level, _) in sectors.items() if level == "category"]
group_keys = categories + [TOTAL]
exclusions = []
scaled, webapi = {}, {}
for key in sorted(MILLION_TABLES):
    indicator, code, year = key
    for s in group_keys:
        r = cells[key][s]
        if s == TOTAL and key in MISPRINTED_TOTAL:
            total_of_categories = sum(cells[key][c]["value"] for c in categories)
            if abs(total_of_categories - r["value"]) <= 9:
                raise ValueError(f"{key}: TOTAL was declared misprinted, but equals the sum of its categories")
            scaled[(indicator, code, "sum of categories", year)] = round(total_of_categories / 1000, 6)
            webapi[(indicator, code, "sum of categories", year)] = industry[(indicator, code, TOTAL, year)]
            continue
        # Values in Rp million with 2 decimals are exact at 5 decimals in Rp billion; rounding drops float noise
        scaled[(indicator, code, s, year)] = round(r["value"] / 1000, 6)
        webapi[(indicator, code, s, year)] = industry[(indicator, code, s, year)]
million_check = cleaning.compare_sources(scaled, webapi, TOL_MILLION,
                                         "million-rupiah tables: 17 categories and TOTAL / 1000 = "
                                         "data/20261103_bps-province-grdp-by-industry-2010-2025, Rp billion")
million_check["tolerance_reason"] = TOLERANCE_REASONS["million"]
million_check["keys"] = "[indicator, province_code, sector, year]; first = the table / 1000, second = vars 2267/2268"
# These values are not in the CSV, so the count of differences is kept rather than each one
million_check["differences"] = len(million_check["differences"])
million_check["misprinted_total"] = [
    {"indicator": i, "province_code": c, "period": str(y), "printed_rp_million": cells[(i, c, y)][TOTAL]["value"],
     "sum_of_categories_rp_million": round(sum(cells[(i, c, y)][s]["value"] for s in categories), 2)}
    for (i, c, y) in sorted(MISPRINTED_TOTAL)]
exclusions.append(million_check)

# A constant-price table with current prices from a row on: every cell from that row through TOTAL equals the
# current-price table, its categories after that row equal var 2268, and its first categories equal var 2267
for key, first_row in CURRENT_IN_CONSTANT.items():
    indicator, code, year = key
    current_key = ("grdp_current", code, year)
    rows_after = list(sectors)[list(sectors).index(first_row):]
    same = [s for s in rows_after if (cells[key][s]["value"], cells[key][s]["value_code"])
            == (cells[current_key][s]["value"], cells[current_key][s]["value_code"])]
    if same != rows_after:
        raise ValueError(f"{key}: rows {sorted(set(rows_after) - set(same))} differ from the current-price table")
    before = [s for s in categories if sector_order[s] < sector_order[first_row]]
    after = [s for s in group_keys if sector_order[s] >= sector_order[first_row]]
    as_constant = cleaning.compare_sources({(indicator, code, s, year): cells[key][s]["value"] for s in before},
                                           {(indicator, code, s, year): industry[(indicator, code, s, year)]
                                            for s in before}, rounding_tolerance(key),
                                           f"{code} {year} constant-price table, categories before {first_row} = var 2267")
    as_current = cleaning.compare_sources({(indicator, code, s, year): cells[key][s]["value"] for s in after},
                                          {(indicator, code, s, year): industry[("grdp_current", code, s, year)]
                                           for s in after}, rounding_tolerance(key),
                                          f"{code} {year} constant-price table, categories from {first_row} and TOTAL "
                                          f"= var 2268 (current prices)")
    exclusions.append({"check": f"{indicator} {code} {year}: every cell from {first_row} through TOTAL equals the "
                                f"current-price table of the same province and year",
                       "cells_equal": len(same), "parts": [as_constant, as_current]})

# Sub-categories the same in both tables that sum to neither table's category
for (code, year), groups in SUBCATEGORIES_SUM_TO_NEITHER.items():
    detail = []
    for group in groups:
        parts = [s for s, (level, parent) in sectors.items() if level == "subcategory" and parent == group]
        pair = [(cells[(i, code, year)][s]["value"], cells[(i, code, year)][s]["value_code"]) for i in INDICATORS
                for s in parts]
        if pair[:len(parts)] != pair[len(parts):]:
            raise ValueError(f"{code} {year} {group}: sub-categories differ between the two tables")
        tol = (len(parts) + 1) * table_step(("grdp_current", code, year)) / 2
        for indicator in INDICATORS:
            printed = sum(cells[(indicator, code, year)][s]["value"] or 0.0 for s in parts)
            total = cells[(indicator, code, year)][group]["value"]
            if abs(printed - total) <= 100 * tol:
                raise ValueError(f"{indicator} {code} {year} {group}: sub-categories sum to their category")
            detail.append({"indicator": indicator, "sector": group, "category": total,
                           "sum_of_subcategories": round(printed, 2)})
    exclusions.append({"check": f"{code} {year}: the sub-categories of {and_list(groups)} are the same at current and "
                                f"constant prices and sum to neither table's category", "cells": detail})

# Items that do not sum to their sub-category, which agrees with the categories above it, and whose ratio to the
# constant-price cells lies outside the ratios of every other row of the table
for key, (sub, items) in ITEMS_NOT_SUMMING.items():
    indicator, code, year = key
    constant_key = ("grdp_constant_2010", code, year)
    item_codes = [s for s, (level, parent) in sectors.items() if parent == sub]
    printed = sum(cells[key][s]["value"] for s in item_codes)
    tol = (len(item_codes) + 1) * table_step(key) / 2
    group = sectors[sub][1]
    group_parts = [s for s, (level, parent) in sectors.items() if parent == group]
    group_gap = abs(sum(cells[key][s]["value"] for s in group_parts) - cells[key][group]["value"])
    ratios = {s: cells[key][s]["value"] / cells[constant_key][s]["value"] for s in sectors
              if cells[key][s]["value"] and cells[constant_key][s]["value"]}
    others = [r for s, r in ratios.items() if s not in items]
    if abs(printed - cells[key][sub]["value"]) <= tol or group_gap > (len(group_parts) + 1) * table_step(key) / 2:
        raise ValueError(f"{key}: the items no longer fail, or {group} no longer sums")
    if any(min(others) <= ratios[s] <= max(others) for s in items):
        raise ValueError(f"{key}: an excluded item's price ratio lies inside the table's range")
    exclusions.append({"check": f"{indicator} {code} {year}: {and_list(item_codes)} sum to {round(printed, 2)}, not to "
                                f"{sub} = {cells[key][sub]['value']}, while the sub-categories of {group} sum to "
                                f"{group} within rounding",
                       "ratio_to_constant_prices": {s: round(ratios[s], 4) for s in items},
                       "ratio_range_of_every_other_row": [round(min(others), 4), round(max(others), 4)]})

# The kept tables, in the CSV's order
tables_kept = [k for k in cells if k not in tables_out]

# Layer 3: identities within each kept table; stops on failure
identities = identity_checks(values, cell_state, tables_kept, sectors)

# Layer 4: the 17 categories and TOTAL against vars 2267/2268 (data/20261103_bps-province-grdp-by-industry-2010-2025)
# on the same borders, which leaves out 91 and 94 in 2023 (post-split here, pre-split there)
ours_groups = {(i, c, s, int(p)): v for (c, i, s, p), v in values.items() if s in group_keys}
same_borders = {k: v for k, v in ours_groups.items() if (k[1], k[3]) not in BORDER_CHANGES}
cross_industry, beyond_industry = compare_tables(same_borders, industry, 0.0, "17 categories and TOTAL = vars "
                                                 "2267/2268 in data/20261103_bps-province-grdp-by-industry-2010-2025, "
                                                 "same borders, Rp billion", TOLERANCE_REASONS["webapi"])

# Every table REVISION_GAPS declares must differ from vars 2267/2268 by more than rounding, so the list stays current
stale = set(REVISION_GAPS) - beyond_industry
if stale:
    raise ValueError(f"REVISION_GAPS declares tables within rounding of vars 2267/2268: {sorted(stale)}")
status_differ = [k for k in same_borders if k in industry and statuses[(k[1], k[0], k[2], str(k[3]))]
                 != industry_status[k]]
if status_differ:
    raise ValueError(f"statuses differ from vars 2267/2268 at {status_differ[:5]}")

# Every category or TOTAL key here that the comparison leaves out must have a declared reason, and so must every key
# vars 2267/2268 hold that is not here
not_compared_here = collections.Counter()
for k in ours_groups:
    if k in same_borders and k in industry:
        continue
    if (k[1], k[3]) in BORDER_CHANGES:
        not_compared_here[f"91 and 94 in {SPLIT_YEAR}: post-split here, pre-split in vars 2267/2268 "
                          f"(checks.borders compares the old areas)"] += 1
    elif k[1] in NEW_PROVINCES and k[3] == SPLIT_YEAR:
        not_compared_here[f"92, 95, 96 and 97 in {SPLIT_YEAR}: vars 2267/2268 hold them inside 91 and 94 until "
                          f"2024"] += 1
    else:
        raise ValueError(f"{k} is here but not in vars 2267/2268, for no declared reason")
not_compared_there = collections.Counter()
for k in industry:
    if k in same_borders or (k[1], k[3]) in BORDER_CHANGES or k[3] not in YEARS:
        continue
    table = (k[0], k[1], k[3])
    if table not in cells:
        not_compared_there["no SIMDASI table for the province and year"] += 1
    elif table in tables_out:
        not_compared_there[f"SIMDASI table excluded ({tables_out[table]})"] += 1
    elif cell_state.get(table + (k[2],)) == "unpublished":
        not_compared_there["SIMDASI cell unpublished ('...' or 'NA')"] += 1
    else:
        raise ValueError(f"{k} is in vars 2267/2268 but not here, for no declared reason")
cross_industry_summary = {"check": "17 categories and TOTAL = vars 2267/2268, same borders",
                          "parts": cross_industry, "statuses_equal": sum(1 for k in same_borders if k in industry),
                          "tables_beyond_rounding": [" ".join(str(x) for x in t) for t in sorted(beyond_industry)],
                          "not_compared": {"here only": dict(not_compared_here),
                                           "there only": dict(not_compared_there)}}

# Layer 4: where a table prints no TOTAL, its 17 categories must sum to the WebAPI TOTAL
missing_total = {k[:3]: k for k, m in unpublished.items() if k[3] == TOTAL}
sums_here, sums_there = {}, {}
for (indicator, code, year) in sorted(missing_total):
    printed = [values.get((code, indicator, s, str(year))) for s in categories]
    if None in printed:
        continue
    sums_here[(indicator, code, year)] = round(sum(printed), 6)
    sums_there[(indicator, code, year)] = industry[(indicator, code, TOTAL, year)]
cross_missing_total = cleaning.compare_sources(sums_here, sums_there, round(18 * TOL_WEBAPI, 6),
                                               "tables printing no TOTAL: the sum of the 17 categories = the TOTAL of "
                                               "vars 2267/2268, Rp billion")
cross_missing_total["tolerance_reason"] = "18 values each rounded to 0.01: 18 x 0.005"

# Layer 4: TOTAL against var 286 (data/20261103_bps-province-grdp-2010-2025) on the same borders, which leaves out 64
# in 2010-2012 (var 286 holds Kalimantan Utara inside it until 2012)
ours_total = {k: v for k, v in ours_groups.items() if k[2] == TOTAL}
kaltim_split = {(i, KALTIM, TOTAL, y) for i in INDICATORS for y in YEARS if (i, KALTARA, TOTAL, y) not in var286
                and (i, KALTIM, TOTAL, y) in var286}
missing_286 = sorted(k for k in ours_total if k not in var286)
if missing_286:
    raise ValueError(f"TOTAL keys here that var 286 does not hold: {missing_286[:5]}")
cross_286, beyond_286 = compare_tables({k: v for k, v in ours_total.items() if k not in kaltim_split}, var286,
                                       TOL_VAR_286, "TOTAL = var 286 in data/20261103_bps-province-grdp-2010-2025, "
                                       "same borders, Rp billion", TOLERANCE_REASONS["var_286"])

# Every TOTAL compared with var 286 must carry the status var 286 gives its year
status_286 = {(i, c, s, int(p)): m for (c, i, s, p), (_, m) in check_286.items()}
compared_286 = [k for k in ours_total if k not in kaltim_split]
status_differ_286 = [k for k in compared_286 if statuses[(k[1], k[0], k[2], str(k[3]))] != status_286[k]]
if status_differ_286:
    raise ValueError(f"statuses differ from var 286 at {status_differ_286[:5]}")

# Layer 4 and borders: Kalimantan Timur. In 2010-2013 its tables equal vars 2267/2268's 64, which leaves out
# Kalimantan Utara, and var 286's 64 of 2010-2012 equals this 64 plus vars 2267/2268's 65
kaltim_here = {(i, y): round(values[(KALTIM, i, TOTAL, str(y))] + industry[(i, KALTARA, TOTAL, y)], 6)
               for (i, _, _, y) in sorted(kaltim_split) if (KALTIM, i, TOTAL, str(y)) in values}
kaltim_286 = {(i, y): var286[(i, KALTIM, TOTAL, y)] for (i, y) in kaltim_here}
cross_kaltim = cleaning.compare_sources(kaltim_here, kaltim_286, round(3 * TOL_WEBAPI + TOL_VAR_286, 6),
                                        "64 here + 65 of vars 2267/2268 = var 286's 64 (which includes Kalimantan "
                                        "Utara), 2010-2012, Rp billion")
cross_kaltim["keys"] = "[indicator, year]"

# Borders of Papua Barat (91) and Papua (94): in each year, TOTAL against vars 2267/2268 (pre-split through 2023) and
# var 286 (pre-split through 2022, post-split from 2023); the declared years must match the pre-split areas, and 2023
# the post-split ones
border_rows = []
for code in sorted(PRE_SPLIT_YEARS):
    for indicator in INDICATORS:
        for year in range(min(PRE_SPLIT_YEARS[code]), YEARS[-1] + 1):
            here = values.get((code, indicator, TOTAL, str(year)))
            pre = industry.get((indicator, code, TOTAL, year))
            post = var286.get((indicator, code, TOTAL, year))
            tol = rounding_tolerance((indicator, code, year), TOL_VAR_286)
            pre_split_area = year in PRE_SPLIT_YEARS[code]
            matches_industry = pre is not None and abs(here - pre) <= tol
            matches_286 = post is not None and abs(here - post) <= tol
            # Pre-split years must match both (both are pre-split then); 2023 must match var 286 and not vars 2267/2268
            if pre_split_area and not (matches_industry and matches_286):
                raise ValueError(f"{code} {indicator} {year}: TOTAL {here} does not match the pre-split values")
            if year == SPLIT_YEAR and not (matches_286 and not matches_industry):
                raise ValueError(f"{code} {indicator} {year}: TOTAL {here} does not match the post-split value only")
            # After the split year both sources are post-split, so both must match
            if year > SPLIT_YEAR and not (matches_industry and matches_286):
                raise ValueError(f"{code} {indicator} {year}: TOTAL {here} does not match the post-split values")
            border_rows.append({"province_code": code, "indicator": indicator, "period": str(year), "total": here,
                                "vars_2267_2268": pre, "var_286": post,
                                "borders": "pre-split" if pre_split_area else "post-split"})

# On the pre-split borders of 2023, the old provinces' sums of the 17 categories and TOTAL against vars 2267/2268
old_area_groups = {"91": ["91", "92"], "94": ["94", "95", "96", "97"]}
old_sums, old_there, declared_gaps = {}, {}, []
for code, members in old_area_groups.items():
    for indicator in INDICATORS:
        for s in group_keys:
            total = round(sum(values[(m, indicator, s, str(SPLIT_YEAR))] for m in members), 6)
            there = industry[(indicator, code, s, SPLIT_YEAR)]
            tol = round((len(members) + 1) * TOL_WEBAPI, 6)
            gap = round(total - there, 6)
            if code == "91" and (indicator, s) in OLD_BORDER_GAPS:
                if abs(gap - OLD_BORDER_GAPS[(indicator, s)]) > tol:
                    raise ValueError(f"{code} {indicator} {s}: old-border gap {gap}, declared "
                                     f"{OLD_BORDER_GAPS[(indicator, s)]}")
                declared_gaps.append({"area": "+".join(members), "indicator": indicator, "sector": s,
                                      "sum": round(total, 2), "vars_2267_2268": there, "gap": round(gap, 2)})
                continue
            old_sums[(code, indicator, s)] = (total, tol)
            old_there[(code, indicator, s)] = there
cross_old_borders = []
for tol in sorted({t for _, t in old_sums.values()}):
    keys = [k for k, (_, t) in old_sums.items() if t == tol]
    result = cleaning.compare_sources({k: old_sums[k][0] for k in keys}, {k: old_there[k] for k in keys}, tol,
                                      f"{SPLIT_YEAR}, pre-split borders: the sum of the provinces of each old area = "
                                      f"vars 2267/2268's old province, 17 categories and TOTAL, Rp billion")
    result["keys"] = "[old province, indicator, sector]"
    result["tolerance_reason"] = "(provinces + 1) values each rounded to 0.01"
    cross_old_borders.append(result)

# Layer 4: 2024-2025 at current prices against data/20261103_bps-province-grdp-detailed-industry, which reads the same
# raw files: every value, status and en-dash cell exactly
detailed_here = {k: v for k, v in values.items() if k[1] == "grdp_current" and int(k[3]) >= 2024}
detailed_there = {k: v for k, (v, _) in check_detailed.items()}
if set(detailed_here) != set(detailed_there):
    raise ValueError(f"keys differ from {CHECK_DETAILED.name}: {sorted(set(detailed_here) ^ set(detailed_there))[:5]}")
cross_detailed = cleaning.compare_sources(detailed_here, detailed_there, TOL_SAME_RELEASE,
                                          f"grdp_current 2024-2025, all 62 sectors, = {CHECK_DETAILED.name}, exactly")
cross_detailed["tolerance_reason"] = "the same raw files, so the same values"
detailed_status_differ = [k for k in detailed_here if statuses[k] != check_detailed[k][1]]
dash_there = {(c["province_code"], c["sector"], c["period"]) for c in meta_detailed["none_or_zero_cells"]["cells"]}
dash_here = {(c, s, str(y)) for (i, c, y, s) in en_dash if i == "grdp_current" and y >= 2024}
if detailed_status_differ or dash_here != dash_there:
    raise ValueError(f"statuses or en-dash cells differ from {CHECK_DETAILED.name}")
cross_detailed["statuses_equal"] = len(detailed_here)
cross_detailed["en_dash_cells_equal"] = len(dash_here)
cross_detailed["sectors_equal"] = len(sector_meta)

# Layer 4: in the base year 2010, every value at constant 2010 prices equals the value at current prices
base = {k: v for k, v in values.items() if k[3] == str(YEARS[0])}
base_current = {(c, s): v for (c, i, s, p), v in base.items() if i == "grdp_current"}
base_constant = {(c, s): v for (c, i, s, p), v in base.items() if i == "grdp_constant_2010"}
base_check = cleaning.compare_sources(base_current, base_constant, TOL_BASE_YEAR,
                                      f"grdp_constant_2010 = grdp_current in the base year {YEARS[0]}, every province "
                                      f"and sector with both, Rp billion")
base_check["keys"] = "[province_code, sector]; first = grdp_current, second = grdp_constant_2010"
base_check["tolerance_reason"] = TOLERANCE_REASONS["base_year"]
base_check["one_price_only"] = sorted(f"{c} {s}" for c, s in set(base_current) ^ set(base_constant))
base_check["provinces"] = sorted({c for c, _ in base_current} | {c for c, _ in base_constant})

# Layer 5: plausibility; every value nonnegative, growth of TOTAL and of every sector at both prices, the shares of
# the 17 categories and of coal at current prices, against their stated ranges
read = {"value_nonnegative": [{"province_code": c, "indicator": i, "sector": s, "period": p, "value": v}
                              for (c, i, s, p), v in sorted(values.items())]}
read["grdp_growth_pct"], zero_current_total = year_on_year(values, "grdp_current", {TOTAL}, codes_order, sector_order)
read["grdp_real_growth_pct"], zero_constant_total = year_on_year(values, "grdp_constant_2010", {TOTAL}, codes_order,
                                                                 sector_order)
others = set(sectors) - {TOTAL}
read["sector_growth_pct"], zero_current = year_on_year(values, "grdp_current", others, codes_order, sector_order)
read["sector_real_growth_pct"], zero_constant = year_on_year(values, "grdp_constant_2010", others, codes_order,
                                                             sector_order)
read["sector_growth_from_zero"] = zero_current_total + zero_constant_total + zero_current + zero_constant
read["sector_share_pct"] = [
    {"province_code": c, "sector": s, "period": p, "rp_billion": {s: v, TOTAL: values[(c, i, TOTAL, p)]},
     "value": 100 * v / values[(c, i, TOTAL, p)]}
    for (c, i, s, p), v in sorted(values.items(), key=lambda kv: (codes_order[kv[0][0]], sector_order[kv[0][2]],
                                                                   kv[0][3]))
    if i == "grdp_current" and s in categories and (c, i, TOTAL, p) in values]
read["coal_share_pct"] = [
    {"province_code": c, "period": p, "rp_billion": {COAL: v, TOTAL: values[(c, i, TOTAL, p)]},
     "value": 100 * v / values[(c, i, TOTAL, p)]}
    for (c, i, s, p), v in sorted(values.items()) if i == "grdp_current" and s == COAL and (c, i, TOTAL, p) in values]
flags = [f for check in PLAUSIBLE for f in flag_range(read[check], check)]
plausibility_compared = {check: len(read[check]) for check in PLAUSIBLE}

# Coverage: the years each province has rows in, by indicator, and the tables behind them
def years_with_rows(indicator, code):
    """Return the years in which a province has at least one row of the indicator."""
    return sorted({int(p) for (c, i, s, p) in values if c == code and i == indicator})


coverage = {indicator: {code: year_runs(years_with_rows(indicator, code)) for code in codes}
            for indicator in INDICATORS}
table_counts = {indicator: {"listed_by_bps": sum(len(listed_years(indicator, c)) for c in codes),
                            "empty_shells": sum(len(y) for y in EMPTY_SHELLS.values()),
                            "saved": sum(1 for k in cells if k[0] == indicator),
                            "excluded": sum(1 for k in tables_out if k[0] == indicator),
                            "all_cells_unpublished": sum(1 for k, (_, spec) in UNPUBLISHED_CELLS.items()
                                                         if k[0] == indicator and spec == "all")}
                for indicator in INDICATORS}

# Summaries of the table notes, source lines and change logs, by indicator and year
def by_indicator_year(field):
    """Return {text: {indicator: {year: number of tables}}} for a text field of the tables."""
    out = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    for (indicator, code, year), table in tables.items():
        out[table[field]][indicator][str(year)] += 1
    return [{"text": text, "tables": {i: dict(sorted(c.items())) for i, c in by.items()}} for text, by in out.items()]


source_tables = {}
for indicator in INDICATORS:
    source_tables[indicator] = {}
    for year in YEARS:
        keys = [k for k in tables if k[0] == indicator and k[2] == year]
        if not keys:
            continue
        logs = collections.Counter(c["change"] for k in keys for c in tables[k]["change_log"])
        stamps = [tables[k]["table_updated"] or extra[k]["table_created"] for k in keys]
        source_tables[indicator][str(year)] = {
            "tables": len(keys),
            "table_updated": [min(stamps), max(stamps)],
            "versions": sorted({extra[k]["versi"] for k in keys}),
            "change_log": dict(sorted(logs.items())),
        }

# The en-dash cells as written in NONE_OR_ZERO_CELLS, from the cells found, and the small values among them
dash_map = collections.defaultdict(lambda: collections.defaultdict(lambda: collections.defaultdict(set)))
for indicator, code, year, sector in en_dash:
    dash_map[indicator][code][sector].add(year)
dash_listing = {i: {c: {s: year_runs(dash_map[i][c][s]) for s in sorted(dash_map[i][c], key=sector_order.get)}
                    for c in sorted(dash_map[i], key=codes_order.get)} for i in INDICATORS}
small_listing = [{"indicator": i, "province_code": c, "sector": s, "period": str(y), "grdp_current": v}
                 for (i, c, y, s), v in sorted(small_values.items(), key=lambda kv: (kv[0][2], codes_order[kv[0][1]],
                                                                                     sector_order[kv[0][3]]))]

# The unpublished cells and the excluded tables and cells, for the metadata
unpublished_listing = [{"indicator": i, "province_code": c, "period": str(y), "marker": marker,
                        "meaning": first["legend"][marker],
                        "sectors": spec if isinstance(spec, str) else list(spec),
                        "cells": len(unpublished_rows(spec, sectors))}
                       for (i, c, y), (marker, spec) in UNPUBLISHED_CELLS.items()]
excluded_listing = {
    "tables": [{"indicator": i, "province_code": c, "period": str(y), "reason": tables_out[(i, c, y)],
                "detail": ("note: 'Data dalam juta rupiah' (Data in million rupiahs)" if (i, c, y) in MILLION_NOTE_TABLES
                           else "no unit printed; the 17 categories and TOTAL are 1000 times vars 2267/2268"
                           if tables_out[(i, c, y)] == "million_rupiah"
                           else f"every cell from {CURRENT_IN_CONSTANT[(i, c, y)]} through TOTAL equals the "
                                f"current-price table") + ("; its TOTAL is misprinted (55.873.812 against categories "
                                                           "summing to 56.373.615)" if (i, c, y) in MISPRINTED_TOTAL
                                                           else "")}
               for (i, c, y) in sorted(tables_out, key=lambda k: (list(INDICATORS).index(k[0]), codes_order[k[1]], k[2]))],
    "cells": [{"indicator": i, "province_code": c, "period": str(y), "sectors": sorted(
                   [s for (ii, cc, yy, s) in cells_out if (ii, cc, yy) == (i, c, y)], key=sector_order.get),
               "reason": reason}
              for (i, c, y), reason in sorted({k[:3]: v for k, v in cells_out.items()}.items(),
                                              key=lambda kv: (list(INDICATORS).index(kv[0][0]), codes_order[kv[0][1]],
                                                              kv[0][2]))],
}

# Counts for the metadata and the report
n_dash = len(en_dash)
n_unpublished = len(unpublished)

# Describe the dataset
meta = {
    "title": "BPS provincial GRDP by detailed industry at current and constant 2010 prices, Indonesia, 2010-2025",
    "columns": {
        "province_code": "BPS province code (kode_bps) of the 38 provinces; there is no Indonesia row. Names and "
                         "Kemendagri codes in 'provinces'.",
        "indicator": "Indicator code; definitions in 'indicators'.",
        "sector": "Industry code: the 17 KBLI categories, their numbered sub-categories and lettered items, and TOTAL. "
                  "Names, levels and parents in 'sectors'.",
        "period": "YYYY = annual.",
        "status": "BPS revision marker of each cell; meanings in 'status'.",
        "value": "Rp billion, as published by BPS. Multiply by 'multiplier' for rupiah.",
    },
    "provinces": {c: provinces[c] for c in codes},
    "province_source": {"url": URL_PROVINCES, "file": posix(RAW_PROVINCES),
                        "note": "BPS and Kemendagri codes differ for the six Papua provinces; join other datasets on "
                                "the code system they use."},
    "sectors": sector_meta,
    "sector_notes": [
        f"The 17 KBLI categories use the codes of data/20261102_bps-province-grdp-population, where MN and RSTU are "
        f"the categories BPS prints as M,N and R,S,T,U. A numbered sub-category appends its number to its category "
        f"({COAL} = {names[COAL]}, coal and lignite mining), and a lettered item appends its letter to its "
        f"sub-category (A1a = {names['A1a']}). TOTAL is the province's GRDP, the table's last row. The sectors are "
        f"those of data/20261103_bps-province-grdp-detailed-industry.",
        f"'label_raw' is each row's label_raw as BPS publishes it, the same in all {len(tables)} tables, and 'name' is "
        f"the same text without the code a category prints. TOTAL's label_raw reads '{labels[TOTAL]}', so TOTAL is "
        f"named '{TOTAL_NAME}', as its HTML label and the sibling datasets name it.",
        "Each level sums to its parent: the 17 categories to TOTAL, the numbered sub-categories to their category, and "
        "A1a-A1e to A1. Summing every row under A (A1, A1a-A1e, A2 and A3) would double count A1's items, so add up "
        "one level at a time.",
    ],
    "indicators": {
        indicator: {
            "name": spec["name"],
            "unit": "Rp billion (miliar rupiah)", "multiplier": 1e9, "base_unit": "Rp",
            "decimals": SIMDASI_FORMAT["decimals"],
            "periods": f"{YEARS[0]}-{YEARS[-1]}, annual; see 'coverage'",
            "source": URL_TABLE.format(id_tabel=spec["id_tabel"]),
            "kode_tabel": spec["kode_tabel"],
            "download_scripts": list(DOWNLOAD_SCRIPTS),
            "table": general_title(tables[(indicator, "11", 2025)]["title"], tables[(indicator, "11", 2025)]["area"],
                                   2025),
            "table_en": general_title(tables[(indicator, "11", 2025)]["title_en"],
                                      tables[(indicator, "11", 2025)]["area"], 2025),
            "column": spec["column"],
            "notes": [
                f"The titles of 2020-2025 carry '{UNIT_TEXT}'; those of 2010-2019 print no unit, except one 2016 "
                f"current-price table (36), and their unit is shown by their values, which equal vars 2267/2268 in "
                f"Rp billion (checks.cross_source).",
                "BPS publishes every value with 2 decimals; the CSV writes each value without trailing zeros, so a "
                "value BPS prints as 1.234,50 is written 1234.5. Some 2014 tables round their values to 0.1 or to whole "
                "Rp billion before printing them with 2 decimals (table_formats.printed_step).",
                "BPS publishes no Indonesia row in these tables; the sum of provincial GRDP is not national GDP.",
            ],
        }
        for indicator, spec in INDICATORS.items()
    },
    "coverage": {
        "years_with_rows": coverage,
        "tables": table_counts,
        "notes": [
            "Each table list (ketersediaan_tahun) gives the years BPS publishes the table for: 2014-2025 for most "
            "provinces; 2010-2025 for 19 (Kepulauan Bangka Belitung) and 64 (Kalimantan Timur) at both prices and for 17 "
            "(Bengkulu) at current prices, whose constant-price table starts in 2015; 2015-2025 for 81 (Maluku), 91 "
            "(Papua Barat) and 94 (Papua); 2020-2025 for 92, 95, 96 and 97.",
            "BPS serves 92, 95, 96 and 97 for 2020-2022 as empty shells (the row labels without values), so they have "
            "tables from 2023.",
            "Excluded tables (excluded.tables) leave these years without rows: 17 at current prices in 2010-2014, 11, "
            "19 and 72 in 2014 at both prices, and 14 at constant prices in 2014. 32 and 82 print '...' in every cell "
            "of their 2014 tables (unpublished_cells). So 11, 17, 32, 72 and 82 have rows from 2015, 14 has rows from "
            "2014 at current prices and from 2015 at constant prices, and 19 has none for 2014.",
            "Kalimantan Utara (65) has tables from 2014 only, and 64's tables leave it out in every year, so its values "
            "for 2010-2013 are in no table here (borders).",
            f"A province with a kept table in a year has a row for each of its 62 sectors except the cells listed in "
            f"none_or_zero_cells, unpublished_cells and excluded.cells; completeness expects exactly this grid.",
        ],
    },
    "borders": [
        "64 (Kalimantan Timur) excludes Kalimantan Utara in every year: its 2010-2013 tables equal vars 2267/2268's 64, "
        "which leave Kalimantan Utara out, and var 286's 64 of 2010-2012 equals this 64 plus vars 2267/2268's 65 "
        "(checks.cross_source). 65 (Kalimantan Utara) has its own tables from 2014.",
        f"91 (Papua Barat) and 94 (Papua) cover the pre-split provinces in their tables of 2015-2022: TOTAL equals vars "
        f"2267/2268 and var 286, both pre-split then. Their {SPLIT_YEAR}-2025 tables cover the post-split areas: TOTAL "
        f"of {SPLIT_YEAR} equals var 286's post-split 91 and 94 and differs from vars 2267/2268, which keep the pre-split "
        f"areas in {SPLIT_YEAR}. 92 (Papua Barat Daya), 95 (Papua Selatan), 96 (Papua Tengah) and 97 (Papua Pegunungan) "
        f"have tables from {SPLIT_YEAR}. checks.borders lists each year's TOTAL against both.",
        f"On the pre-split borders of {SPLIT_YEAR}, 94 + 95 + 96 + 97 equals vars 2267/2268's 94 within rounding in "
        f"every category and TOTAL; 91 + 92 equals their 91 within rounding except A and D at current prices (+5.00 "
        f"and +0.10, TOTAL +5.10 Rp billion) and A at constant prices (+11.00, TOTAL +11.00), the gaps "
        f"data/20261103_bps-province-grdp-2010-2025 finds between var 286's 91 + 92 and var 2268's 91.",
        f"A change of 91 or 94 from 2022 to {SPLIT_YEAR} compares different areas; the growth checks leave those "
        f"changes out (checks.growth_not_compared). On fixed borders: Papua Barat (pre-{SPLIT_YEAR} area) = 91 + 92 "
        f"and Papua (pre-{SPLIT_YEAR} area) = 94 + 95 + 96 + 97 from {SPLIT_YEAR}.",
        "These tables split Papua in 2023, as var 286 (data/20261103_bps-province-grdp-2010-2025) does, one year before "
        "vars 2267/2268 (data/20261103_bps-province-grdp-by-industry-2010-2025).",
    ],
    "table_formats": {
        "encoding": "UTF-8 JSON without a byte-order mark",
        "numbers": "Indonesian text: '.' thousands separator, ',' decimal mark, 2 decimals as each column declares",
        "unit_text": {"text": UNIT_TEXT, "years": f"{UNIT_TEXT_YEARS[0]}-{UNIT_TEXT_YEARS[-1]}",
                      "also": [f"{i} {c} {y}" for i, c, y in sorted(UNIT_TEXT_ALSO)],
                      "other_titles": "no unit"},
        "printed_step": [{"indicator": i, "province_code": c, "period": str(y), "step": s,
                          "unit": READ_CONTEXT[RAW_TABLES[(i, c, y)]]["unit"]}
                         for (i, c, y), s in sorted(PRINTED_STEP.items())],
        "status_markers": {str(y): m for y, m in STATUS_BY_YEAR.items()},
        "cells_without_their_years_marker": [{"indicator": i, "province_code": c, "sector": s, "period": str(y),
                                              "value": v} for (i, c, s, y), v in sorted(NO_MARKER_CELLS.items())],
    },
    "legend": {"note": f"The marker legend (keterangan_data) of the SIMDASI tables, as published; all {len(tables)} "
                       f"tables carry the same legend.", "markers": first["legend"]},
    "table_notes": by_indicator_year("notes"),
    "table_source_lines": by_indicator_year("source"),
    "none_or_zero_cells": {
        "marker": EN_DASH,
        "meaning": f"{first['legend'][EN_DASH]} (none or zero)",
        "rule": "BPS prints these cells as an en dash with no value. They have no row in the CSV. An analysis may treat "
                "a listed cell as 0 Rp billion, as the identity checks do, except the cells under small_values. The "
                "tables of 2015 print 0,00 where the tables of other years print an en dash, and those zeros have rows.",
        "count": n_dash,
        "cells": dash_listing,
        "small_values": {
            "rule": "In the constant-price tables of 2016 and 2017 these cells are printed as an en dash, but the "
                    "current-price cell holds a value and the category above includes it: they are small values BPS "
                    "did not print, not zeros (checks.identities bounds each).",
            "count": len(small_values),
            "cells": small_listing,
        },
    },
    "unpublished_cells": {
        "rule": "Cells BPS prints with '...' (Data tidak tersedia, data not available) or 'NA' (Data tidak dapat "
                "ditampilkan, data cannot be shown). They have no row in the CSV and are not zeros. In 2014 '...' also "
                "stands in some tables where later tables print the en dash (18: B2 and C5).",
        "count": n_unpublished,
        "tables": unpublished_listing,
    },
    "excluded": {
        "rule": "Cells BPS publishes that this dataset leaves out, because they are not GRDP in Rp billion at the "
                "table's price basis or do not add up within their own table; the build verifies each reason "
                "(checks.exclusions). The 17 categories and TOTAL of the excluded tables are in "
                "data/20261103_bps-province-grdp-by-industry-2010-2025.",
        "tables": excluded_listing["tables"],
        "cells": excluded_listing["cells"],
        "reasons": {
            "million_rupiah": "values in Rp million (juta rupiah), 1000 times the Rp billion of the series",
            "current_in_constant": "a constant-price table that prints current prices from a row through TOTAL",
            "subcategories_sum_to_neither": "sub-categories that are the same in the current-price and constant-price "
                                            "tables and sum to neither table's category",
            "items_not_summing": "items that do not sum to their sub-category, whose ratio to the constant-price cells "
                                 "lies far outside every other row of the table",
        },
    },
    "source_tables": {
        "list_url": URL_LIST,
        "lists": [posix(p) for p in RAW_LISTS],
        "note": "Each yearbook table's update times, versions (versi) and change logs (BPS's revision history), by "
                "indicator and year, as published; the status column follows each cell's marker, not the change log.",
        "by_year": source_tables,
    },
    "notes": [
        "Every value comes from the SIMDASI yearbook table of its province, year and price basis, so all rows of a "
        "table come from one table and its sums hold (checks.identities).",
        f"{len(tables_out)} tables and {len(cells_out)} cells BPS publishes are left out (excluded): "
        f"{len(MILLION_TABLES)} tables in Rp million (17 at current prices in 2010-2014, and 11, 19 and 72 in 2014 at "
        f"both prices), the constant-price table of 14 in 2014, which prints current prices from C9 on, the "
        f"sub-categories of G, H, I and K of 61 in 2014 at both prices, and A1d and A1e of 35 at current prices in "
        f"2014. The 17 categories and TOTAL of the excluded tables are in "
        f"data/20261103_bps-province-grdp-by-industry-2010-2025.",
        f"An en dash means none or zero, except {len(small_values)} cells of the constant-price tables of 2016 and "
        f"2017 whose current-price cell holds a value (none_or_zero_cells.small_values): there the en dash hides a "
        f"small value, so their sub-categories sum to up to "
        f"{next(r['largest_gap'] for r in identities if 'cells' in r)} Rp billion less than the category.",
        "Status is each cell's marker: * (Angka sementara) for 2024 and ** (Angka sangat sementara) for 2025; the cells "
        "of 2010-2023 carry no marker. Five cells carry no marker in 2024 or 2025 (table_formats."
        "cells_without_their_years_marker) and are written with an empty status. The notes of the 2018 and 2019 "
        "tables state statuses for 2021 and 2022, years those tables do not hold.",
        f"The 17 categories and TOTAL equal vars 2267/2268 (data/20261103_bps-province-grdp-by-industry-2010-2025) within "
        f"the rounding of each table on the same borders, except the tables in checks.cross_source declared under "
        f"REVISION_GAPS: 31 in 2014 (whole Rp billion, an earlier revision, up to 0.91) and 76 (Sulawesi Barat) in "
        f"2022 at both prices (A and C split differently, 5.40) and in 2023 and 2024 at constant prices (0.37 and 1.32 "
        f"at TOTAL). checks.cross_source lists every difference.",
        "Derived values are not stored. Sector share (%) = grdp_current of the sector / grdp_current of TOTAL x 100; "
        "real growth (%) = (grdp_constant_2010 in year t / grdp_constant_2010 in year t-1 - 1) x 100; implicit price "
        "deflator (2010 = 100) = grdp_current / grdp_constant_2010 x 100.",
        "checks.flags lists every value or change outside its range in checks.plausible_ranges for a person to review, "
        "and a growth or share flag gives the two values it compares under rp_billion; a flag stays whether it reflects "
        "a real event or a source error.",
    ],
    "check_datasets": {
        "build_order": "data/20261103_bps-province-grdp-by-industry-2010-2025/, "
                       "data/20261103_bps-province-grdp-2010-2025/ and data/20261103_bps-province-grdp-detailed-industry/ "
                       "must be rebuilt before this dataset: this build reads their CSVs and metadata as checks and "
                       "records their hashes as they are when it runs",
        "files": {posix(p): {"sha256": cleaning.sha256(p)}
                  for csv in (CHECK_INDUSTRY, CHECK_286, CHECK_DETAILED)
                  for p in (csv, csv.with_name(csv.stem + "-metadata.json"))},
    },
    "checks": {
        "passed": ["identities", "cross-source", "exclusions", "borders"],
        "identities": identities,
        "cross_source": [cross_industry_summary, cross_missing_total,
                         {"check": "TOTAL = var 286, same borders", "parts": cross_286,
                          "statuses_equal": len(compared_286),
                          "tables_beyond_rounding": [" ".join(str(x) for x in t) for t in sorted(beyond_286)],
                          "not_compared": [f"64 in {year_runs([k[3] for k in kaltim_split])}: var 286's 64 includes "
                                           f"Kalimantan Utara (compared in the next check)"]},
                         cross_kaltim, cross_detailed, base_check],
        "revision_gaps": {f"{i} {c} {y}": {"largest_gap": gap, "reason": reason}
                          for (i, c, y), (gap, reason) in REVISION_GAPS.items()},
        "exclusions": exclusions,
        "borders": {"papua_totals": border_rows, "old_borders_2023": cross_old_borders,
                    "old_borders_2023_declared_gaps": declared_gaps},
        "plausible_ranges": {check: {"range": list(PLAUSIBLE[check]), "measure": PLAUSIBLE_MEASURES[check]}
                             for check in PLAUSIBLE},
        "plausibility_compared": plausibility_compared,
        "growth_not_compared": [{"province_code": c, "period": str(y),
                                 "reason": f"{c} in {y - 1} covers the pre-split area, in {y} the post-split one"}
                                for c, y in sorted(BORDER_CHANGES)],
        "flags": flags,
    },
}

# Layers 1, 2 and 6: every key of the kept tables except the declared gaps must be present; write the CSV and metadata
rows = [{"province_code": c, "indicator": i, "sector": s, "period": p, "status": statuses[(c, i, s, p)], "value": v}
        for (c, i, s, p), v in values.items()]
expected = {(code, indicator, s, str(year)) for (indicator, code, year) in tables_kept for s in sectors
            if cell_state[(indicator, code, year, s)] == "value"}
expected_grid = {(code, indicator, s, str(year)) for (indicator, code, year) in tables_kept for s in sectors} - {
    (c, i, s, str(y)) for (i, c, y, s) in set(en_dash) | set(unpublished) | set(cells_out)}
if expected != expected_grid:
    raise ValueError("the kept cells and the grid minus the declared gaps differ")
raw_files = [RAW_PROVINCES, *RAW_LISTS, *paths.values()]
out = cleaning.write_dataset(
    rows, KEYS,
    allowed={"province_code": codes, "indicator": list(INDICATORS), "sector": list(sectors),
             "period": [str(y) for y in YEARS]},
    expected=expected_grid,
    csv_path=OUT_CSV, meta=meta, raw_files=raw_files,
    sort_orders={"indicator": list(INDICATORS), "sector": list(sectors)},
)

# Report what was written, every check result and every plausibility flag
print(f"{OUT_CSV.name}: {len(out)} rows, {n_dash} en-dash cells ({len(small_values)} small values), "
      f"{n_unpublished} unpublished cells, {len(tables_out)} excluded tables, {len(cells_out)} excluded cells, "
      f"{len(flags)} plausibility flags")
print(out.groupby(["indicator", "period", "status"]).size().unstack("status", fill_value=0).to_string())
for check in identities:
    print("  identity:", {k: v for k, v in check.items() if k != "cells"})
for part in cross_industry + cross_286:
    print("  cross-source:", {k: part[k] for k in ("check", "compared", "tolerance", "largest_gap")},
          f"{len(part['differences'])} differences")
for check in (cross_missing_total, cross_kaltim, cross_detailed, base_check, *cross_old_borders, million_check):
    count = check["differences"] if isinstance(check["differences"], int) else len(check["differences"])
    print("  check:", {k: check[k] for k in ("check", "compared", "tolerance", "largest_gap")}, f"{count} differences")
print("  old-border declared gaps:", declared_gaps)
print(f"  plausibility: values read {plausibility_compared}")
for f in flags:
    print("  flag:", f)
