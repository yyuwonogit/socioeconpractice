from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# Load the shared cleaning module from tools/
import sys
sys.path.insert(0, str(ROOT / "tools"))
import cleaning

# Modules for the reads and checks: json for the Kemnaker detail files, math for a range open above, re for the
# workbook formulas and the BPS note items, statistics for the yearly median change, Decimal for exact gaps and
# decimal places, openpyxl for the workbooks
import json
import math
import re
import statistics
from decimal import Decimal

import openpyxl
from openpyxl.utils import get_column_letter

# Parameters

# BPS province list that every province name is matched against
RAW_PROVINCES = ROOT / "raw/province-codes/20261102_bps-province-codes-2025-s1.json"
URL_PROVINCES = "https://sig.bps.go.id/rest-bridging/getwilayah?level=provinsi&periode_merge=2025_1.2025"

# Folder of the raw files, and the two scripts that downloaded them
RAW_DIR = ROOT / "raw/labour"
BPS_DOWNLOAD = "raw/labour/20261104_download-bps-monthly-wage-and-minimum-wage-by-province.py"
KEMNAKER_DOWNLOAD = "raw/labour/20261104_download-kemnaker-minimum-wage-by-province.py"

# BPS WebAPI var 220 'Upah Minimum Regional/Propinsi', saved in the blocks of years the download script asked for; BPS
# publishes no 2017 and nothing after 2020
BPS_VAR = 220
BPS_LABEL = "Upah Minimum Regional/Propinsi"
BPS_SPANS = [(1997, 1999), (2000, 2002), (2003, 2005), (2006, 2008), (2009, 2011), (2012, 2014), (2015, 2016),
             (2018, 2020)]
RAW_BPS = {span: RAW_DIR / f"20261104_bps-api-var220-minimum-wage-by-province-{span[0]}-{span[1]}.json"
           for span in BPS_SPANS}
BPS_YEARS = [year for first, last in BPS_SPANS for year in range(first, last + 1)]
URL_BPS ="https://webapi.bps.go.id/v1/api/list/model/data/domain/0000/var/220/th/{th}/key/{key}"

# What every var 220 file says about itself, read from opening the files: its subject, region list, single turvar and
# turtahun, and its note, item by item (Kemnaker is BPS's source, Kalimantan Utara's 2013 figure is still inside
# Kalimantan Timur, and the data are quoted from the publication Statistik Indonesia)
BPS_SUBJECT = "Upah Buruh"
BPS_REGIONS = "38 Provinsi"
BPS_TURVAR = [("0", "Tidak ada")]
BPS_TURTAHUN = [(0, "Tahun")]
BPS_NOTE_ITEMS = ["Sumber: Kementerian Ketenagakerjaan",
                  "Data Kalimantan Utara tahun 2013 masih bergabung dengan Kalimantan Timur",
                  "Data dikutip dari Publikasi Statistik Indonesia"]

# Kemnaker Satu Data portal datasets: id -> the years their file names carry and the title each detail must carry
KEMNAKER = {
    36: ("2016-2020", "UMP Nasional Tahun 2016-2020"),
    473: ("2018-2022", "Nilai Upah Minimum Provinsi (UMP) di Indonesia Tahun 2018 sampai dengan Tahun 2022"),
    942: ("2023", "Upah Minimum Provinsi (UMP) Tahun 2023"),
    1611: ("2024", "Upah Minimum Provinsi (UMP) Tahun 2024"),
    2252: ("2025", "Upah Minimum Provinsi (UMP) Tahun 2025"),
}
RAW_XLSX = {d: RAW_DIR / f"20261104_kemnaker-dataset-{d}-minimum-wage-by-province-{years}.xlsx"
            for d, (years, _) in KEMNAKER.items()}
RAW_DETAIL = {d: RAW_DIR / f"20261104_kemnaker-dataset-{d}-minimum-wage-by-province-{years}-detail.json"
              for d, (years, _) in KEMNAKER.items()}
URL_DETAIL = 'https://satudata.kemnaker.go.id/api/v1/data/detail_data, POST {"id": <dataset>}'

# How each raw file is written, read from opening all 19 files. The province list is UTF-8 JSON whose 38 records hold
# only text. The 8 var 220 files are UTF-8 JSON without a byte-order mark: values are JSON integers (no decimal point,
# no thousands separator) whose unit field reads 'Rupiah'; the var's decimal field is null, so whole rupiah is checked
# value by value; a value BPS does not publish is a key absent from datacontent (no markers). The 5 detail files are
# UTF-8 JSON without a byte-order mark whose abstracts (HTML) write figures as Indonesian-format text, '.' for
# thousands and ',' before 2 decimals ('Rp 1.967.572,00'). The 5 workbooks are xlsx files opened with openpyxl in
# read-only mode: each value is an Excel numeric cell (no text to parse) shown with the number format #,##0.00, and
# each data sheet is laid out as declared below: title lines above a header row named by its 'Provinsi' cell, the
# label over each value column, where the unit text stands, the average row after the provinces, the lines below it,
# and the cells that hold a single space
BPS_NUMBERS = "JSON integers: no decimal point, no thousands separator"
ABSENT_KEY = "key absent from datacontent"
XLSX = {"reader": "openpyxl, read-only", "numbers": "Excel numeric cells, no text to parse",
        "number_format": "#,##0.00", "name_label": "Provinsi", "stray_text": " "}
READ_CONTEXT = {
    RAW_PROVINCES: {"encoding": "utf-8", "numbers": "none: every field is a JSON string", "missing": "none"},
    **{path: {"encoding": "utf-8", "numbers": BPS_NUMBERS, "missing": ABSENT_KEY, "var": BPS_VAR, "unit": "Rupiah",
              "decimals": None} for path in RAW_BPS.values()},
    **{path: {"encoding": "utf-8", "decimal": ",", "thousands": ".", "decimals": 2} for path in RAW_DETAIL.values()},
    RAW_XLSX[36]: {**XLSX, "sheets": ["Sheet4"], "sheet": "Sheet4",
                   "titles": ["Upah Minimum Provinsi Menurut Provinsi", "Tahun 2016 – 2020"],
                   "number_label": None, "columns": {f"Tahun {y}": y for y in range(2016, 2021)},
                   "unit_text": "(Rp)", "unit_place": "row below the header", "decimals": 3, "missing": ["-"],
                   "average_label": "Rata-Rata", "average": "values",
                   "after": ["Sumber: Ditjend. PHI dan JSK, diolah oleh Pusdatinaker",
                             "Sesuai PP No.78 Tahun 2015 tentang Pengupahan dengan Pentahapan Pencapaian KHL ",
                             "Tidak sesuai dengan PP 78 Tahun 2015 yaitu Bengkulu, Bali dan Papua Barat"],
                   "block": "Standar Data", "stray": 0},
    RAW_XLSX[473]: {**XLSX, "sheets": ["ump"], "sheet": "ump",
                    "titles": ["Upah Minimum Provinsi Di Indonesia", "Tahun 2018-2022"],
                    "number_label": "No.", "columns": {2018: 2018, 2019: 2019, 2020: 2020, 2021: 2021, "2022*": 2022},
                    "unit_text": None, "unit_place": None, "decimals": 3, "missing": [],
                    "average_label": "Rata-Rata", "average": "formulas",
                    "after": ["Sumber : Ditjend. PHI dan JSK, Kemnaker RI", "Note: *) data per 8 Februari 2022"],
                    "block": None, "stray": 0},
    RAW_XLSX[942]: {**XLSX, "sheets": ["data", "standar data", "metadata"], "sheet": "data",
                    "titles": ["Upah Minimum Provinsi ", "Tahun 2023"],
                    "number_label": None, "columns": {"UMP": 2023},
                    "unit_text": "(Rp)", "unit_place": "row below the header", "decimals": 2, "missing": [],
                    "average_label": "Rata-rata", "average": "formulas",
                    "after": ["Sumber: Ditjend. PHI dan JSK"], "block": None, "stray": 1},
    RAW_XLSX[1611]: {**XLSX, "sheets": ["data", "standar data", "metadata"], "sheet": "data",
                     "titles": ["Upah Minimum Provinsi di Indonesia", "Tahun 2024"],
                     "number_label": "No", "columns": {"Upah Minimum (Rp)": 2024},
                     "unit_text": "(Rp)", "unit_place": "header", "decimals": 2, "missing": [],
                     "average_label": "Rata-rata", "average": "formulas",
                     "after": ["Sumber: Kemnaker RI"], "block": None, "stray": 1},
    RAW_XLSX[2252]: {**XLSX, "sheets": ["data", "standar data", "metadata"], "sheet": "data",
                     "titles": ["Upah Minimum Provinsi di Indonesia", "Tahun 2025"],
                     "number_label": "No", "columns": {"Upah Minimum (Rp)": 2025},
                     "unit_text": "(Rp)", "unit_place": "header", "decimals": 2, "missing": [],
                     "average_label": "Rata-Rata", "average": "formulas",
                     "after": ["Sumber: Kemnaker RI"], "block": None, "stray": 1},
}

# Kemnaker spellings the BPS list lacks, each mapped to the BPS name it means, with the reason
NAME_ALIASES = {
    "BANGKA BELITUNG": ("KEPULAUAN BANGKA BELITUNG", "Kemnaker writes the province without 'Kepulauan'"),
    "DI. YOGYAKARTA": ("DI YOGYAKARTA", "Kemnaker writes 'DI.' with a full stop, which normalise_name keeps"),
}

# Provinces each Kemnaker dataset lists: all 38 in 1611 and 2252, and the 34 without the four new Papua provinces in 36,
# 473 and 942
NEW_PAPUA = ["92", "95", "96", "97"]
LISTS_NEW_PAPUA = {36: False, 473: False, 942: False, 1611: True, 2252: True}

# Dataset 36 fills some 2020 cells with a colour, and two lines below its table give each colour's meaning, each line
# beside a cell of its colour: light yellow for UMPs set under PP 78/2015 with the phased approach to decent living
# needs (KHL), orange for UMPs not set under PP 78/2015, which the line names. The build stops unless the filled cells
# and the named provinces are exactly these
LEGEND_36 = {
    "FFFFE699": {"note": "Sesuai PP No.78 Tahun 2015 tentang Pengupahan dengan Pentahapan Pencapaian KHL ",
                 "english": "set in line with Government Regulation (PP) 78/2015 on Wages, with the phased approach "
                            "to decent living needs (Kebutuhan Hidup Layak, KHL)",
                 "cells": [("53", 2020), ("62", 2020), ("75", 2020), ("76", 2020)], "named": None},
    "FFFFC000": {"note": "Tidak sesuai dengan PP 78 Tahun 2015 yaitu Bengkulu, Bali dan Papua Barat",
                 "english": "not in line with PP 78/2015, namely Bengkulu, Bali and Papua Barat",
                 "cells": [("17", 2020), ("51", 2020), ("91", 2020)], "named": ["Bengkulu", "Bali", "Papua Barat"]},
}

# Dataset 473 heads its 2022 column '2022*', and the line below its table gives the marker's meaning: the 2022 values
# are as recorded on 8 February 2022. That is a date of record, not a revision status in cleaning.BPS_STATUS, so the
# rows keep an empty status and the metadata keeps the marker
MARKER_473 = {"header": "2022*", "year": 2022, "marker": "*", "note": "Note: *) data per 8 Februari 2022"}

# Forms that describe the data, read by their labels: in dataset 36 a block below the table headed 'Standar Data' with
# labels down column A and values in column C, then an indicator table; in 942, 1611 and 2252 the sheets 'standar
# data' and 'metadata', each a header row of labels over a row of values. The field each file gives the unit in must
# read 'Rupiah' in both forms
STANDARD_LABELS = ["Konsep", "Definisi", "Klasifikasi", "Ukuran", "Satuan", "Dasar Rujukan"]
INDICATOR_LABELS = ["Nama Indikator", "Konsep", "Definisi", "Interpretasi", "Ukuran", "Satuan", "Level Estimasi"]
FORMS = {
    36: {"standard": None, "indicator": ("Sheet4", "Rata-Rata Upah Minimum Provinsi"), "unit_field": "Ukuran"},
    942: {"standard": "standar data", "indicator": ("metadata", "Upah Minimum Provinsi (UMP)"), "unit_field": "Satuan"},
    1611: {"standard": "standar data", "indicator": ("metadata", "Upah Minimum Provinsi (UMP)"),
           "unit_field": "Satuan"},
    2252: {"standard": "standar data", "indicator": ("metadata", "Upah Minimum Provinsi (UMP)"),
           "unit_field": "Satuan"},
}

# Average rows: formulas of the form =SUM(C5:C42)/38 or =AVERAGE(E6:E39) over the province rows of their own column
SUM_OVER_N = re.compile(r"=SUM\(([A-Z]+)(\d+):([A-Z]+)(\d+)\)/(\d+)")
AVERAGE_OF = re.compile(r"=AVERAGE\(([A-Z]+)(\d+):([A-Z]+)(\d+)\)")

# Figures the Kemnaker abstracts state, each checked against the dataset's own values: (text in the abstract,
# statistic, year, (dataset, year) a change starts from). The statistics are over the provinces with a value: the mean,
# the lowest, the highest, and the change of the mean in rupiah or percent
ABSTRACT_FIGURES = {
    36: [("Rp 1.967.572,00", "mean", 2016, None), ("Rp 2.672.370,77", "mean", 2020, None),
         ("Rp 704.798,77", "mean_change", 2020, (36, 2016)), ("35,82 persen", "mean_change_pct", 2020, (36, 2016)),
         ("Rp 1.312.355,00", "lowest", 2016, None), ("Rp 3.100.000,00", "highest", 2016, None),
         ("Rp 1.704.608,25", "lowest", 2020, None), ("Rp 4.276.349,91", "highest", 2020, None)],
    942: [("Rp 2.923.309,40", "mean", 2023, None), ("7,26%", "mean_change_pct", 2023, (473, 2022))],
    1611: [("Rp3.113.359,85", "mean", 2024, None)],
}
FIGURE_TEXT = re.compile(r"^(?:Rp\s*)?([\d.,]+)(?:\s*persen|%)?$")

# Texts the abstracts must still carry because the metadata relies on them: the 2021 freeze (473) and the minimum wage
# of the new provinces from 2024 (1611)
FREEZE_TEXT = "SE Menaker Nomor M/11/HK.04/X/2020"
NEW_PROVINCES_TEXT = "termasuk upah minimum bagi provinsi baru di Indonesia"
FREEZE_YEAR = 2021

# Sources in priority order. BPS var 220 gives every year it holds and Kemnaker the years BPS lacks; the Kemnaker
# datasets repeat only 2018-2020 (36 and 473), all BPS years, and 473, the later release, ranks above 36. Each year
# takes all its values from the first source that holds the year, and the lower-priority copies serve as checks
PRIORITY = ["bps", 473, 36, 942, 1611, 2252]
SOURCE_CODE = {"bps": "bps_var220", 36: "kemnaker_36", 473: "kemnaker_473", 942: "kemnaker_942", 1611: "kemnaker_1611",
               2252: "kemnaker_2252"}
SOURCE_NAME = {"bps": "BPS WebAPI var 220", **{d: f"Kemnaker Satu Data dataset {d}" for d in KEMNAKER}}

# Tolerances of the cross-source checks (layer 4): BPS publishes whole rupiah and Kemnaker up to 3 decimals, so rounding
# a Kemnaker value to whole rupiah moves it by at most 0.5; the two Kemnaker releases must match exactly
TOL_BPS = 0.5
TOL_KEMNAKER = 0
TOLERANCE_REASONS = {
    "bps": "BPS publishes whole rupiah and Kemnaker up to 3 decimals; rounding to whole rupiah moves a value by at "
           "most 0.5 rupiah",
    "kemnaker": "two releases of the same Kemnaker figures must match exactly",
}

# Differences beyond the tolerance, each declared exactly with the reason read from the files; the build stops if one
# changes. Jawa Barat 2016: BPS's value is its own 2016 value for Sulawesi Selatan (SAME_AS), and dataset 36's abstract
# names Kemnaker's value as the lowest UMP of 2016. Banten 2019: BPS dropped the decimals instead of rounding them
DECLARED = {
    ("32", 2016): {"bps": 2250000, 36: 1312355,
                   "reason": "BPS's 2,250,000 equals BPS's own 2016 value for Sulawesi Selatan (73); Kemnaker "
                             "dataset 36 gives 1,312,355, which its abstract names as the lowest UMP of 2016 "
                             "(checks.abstract_figures). The CSV keeps BPS's value by the stated priority, and "
                             "checks.flags lists the changes into and out of 2016 for a person to decide"},
    ("36", 2019): {"bps": 2267990, 36: 2267990.55, 473: 2267990.55,
                   "reason": "BPS writes 2,267,990 where both Kemnaker releases give 2,267,990.55: BPS dropped the "
                             "decimals instead of rounding them to 2,267,991, a gap of under 1 rupiah"},
}
SAME_AS = {("32", 2016): ("73", 2016)}

# BPS's INDONESIA row (vervar 9999), which BPS does not describe. Read from opening the files, it is the unweighted mean
# of the provinces var 220 lists that year, rounded to the nearest 100 rupiah in 1997-2004 and written in whole rupiah,
# within 1 rupiah, from 2005; except that the mean leaves out Papua Barat (91) in 2006-2008 and the four provinces
# 32-35 in 2015, and 2014 is no such mean (its gap to the mean of all 33 provinces declared to the cent)
NATIONAL_ROUNDED_TO = {year: 100 for year in range(1997, 2005)}
NATIONAL_LEFT_OUT = {2006: ["91"], 2007: ["91"], 2008: ["91"], 2015: ["32", "33", "34", "35"]}
NATIONAL_UNMATCHED = {2014: Decimal("73926.82")}
TOL_NATIONAL = 1
TOL_AVERAGE = 0.005

# Years and periods of the dataset, its indicator and its key columns
YEARS = list(range(1997, 2026))
PERIODS = [str(y) for y in YEARS]
INDICATOR = "minimum_wage"
KEYS = ["province_code", "indicator", "period"]

# Coverage, read from opening the files: the first year of each province whose values start after 1997, and the years
# without a value after a province's first year, with the reasons
FIRST_YEAR = {"19": 1998, "36": 1998, "75": 1998, "82": 1998, "76": 2006, "91": 2006, "65": 2015,
              "92": 2024, "95": 2024, "96": 2024, "97": 2024}
GAP_KEPRI = ("BPS var 220 holds no value for Kepulauan Riau in 2002-2004, between its values for 1997-2001 and from "
             "2005, and no Kemnaker file covers those years")
GAP_JAVA = "neither source gives a 2016 value: BPS var 220 has no key, and Kemnaker dataset 36 prints '-'"
GAPS = {("21", 2002): GAP_KEPRI, ("21", 2003): GAP_KEPRI, ("21", 2004): GAP_KEPRI,
        ("33", 2016): GAP_JAVA, ("34", 2016): GAP_JAVA, ("35", 2016): GAP_JAVA}

# The province each later province was formed from, whose value its first years equal (coverage.same_as_parent), and
# the year each was formed: general knowledge, not read from these files (README gives 65 and the new Papua provinces)
PARENT = {"19": "16", "21": "14", "36": "32", "75": "71", "76": "73", "82": "81", "91": "94", "65": "64",
          "92": "91", "95": "94", "96": "94", "97": "94"}
FORMED = {"82": 1999, "36": 2000, "19": 2000, "75": 2000, "21": 2002, "91": 2003, "76": 2004, "65": 2012,
          "92": 2022, "95": 2022, "96": 2022, "97": 2022}

# Facts about the values that justify the plausibility ranges, checked by the build: the lowest and the highest UMP in
# the files, and the largest median change across provinces in any year, in percent, with their years
PLAUSIBLE_BASIS = {"lowest": (106_000, 1997), "highest": (5_396_761, 2025), "largest_median_change_pct": (32.4, 2001)}

# Plausibility ranges (layer 5); a value outside its range is flagged, not dropped, and a range ending in None is open
# above
PLAUSIBLE = {
    "minimum_wage_rupiah": (100_000, 6_000_000),
    "minimum_wage_change_pct": (-0.001, 50),
    "unchanged_from_previous_year_rupiah": (1, None),
}
PLAUSIBLE_MEASURES = {
    "minimum_wage_rupiah": "every value, rupiah per month. The UMPs in these files run from 106,000 (1997) to "
                           "5,396,761 (2025), so a value below 100,000 or above 6,000,000 is a unit or digit error "
                           "rather than a minimum wage",
    "minimum_wage_change_pct": "(value in year t / value in year t-1 - 1) x 100. Below -0.001: the UMP fell (one "
                               "rupiah of rounding where the series switches between BPS's whole rupiah and "
                               "Kemnaker's decimals is under 0.001% of any UMP here). Above 50: a rise of more than "
                               "half in one year, beyond the largest median rise across provinces in these files "
                               "(32.4%, 2001)",
    "unchanged_from_previous_year_rupiah": "|value in year t - value in year t-1|, rupiah. Below 1 rupiah the UMP did "
                                           "not change (allowing for the rounding at a switch of source); 2021 is not "
                                           "read, since dataset 473's abstract states the 2021 freeze",
}

# Output; the metadata JSON is written beside it with a -metadata suffix
OUT_CSV = HERE / "20261104_bps-kemnaker-province-minimum-wage.csv"


# Functions

def posix(path):
    """Return a path relative to the repository root with forward slashes, for the metadata."""
    return Path(path).resolve().relative_to(ROOT).as_posix()


def and_list(items):
    """Return items joined for a sentence: 'a', 'a and b', or 'a, b and c'."""
    items = [str(i) for i in items]
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def spans(years):
    """Return years as runs of consecutive years for a sentence: [1997, 1998, 2000] -> '1997-1998 and 2000', or ''
    for no years."""
    runs = []
    for year in sorted(years):
        if runs and year == runs[-1][1] + 1:
            runs[-1][1] = year
        else:
            runs.append([year, year])
    return and_list([str(a) if a == b else f"{a}-{b}" for a, b in runs]) if runs else ""


def decimals_of(value):
    """Return the decimal places of a number as stored, such as 2 for 1961354.69 and 0 for 2700000.0."""
    return max(0, -Decimal(repr(float(value))).normalize().as_tuple().exponent)


def read_bps(lookup):
    """Read the eight var 220 files: {(code, year): rupiah} for the provinces, {year: rupiah} for the INDONESIA row, and
    the description all eight share."""
    values, national, tables = {}, {}, []
    for (first, last), path in RAW_BPS.items():
        c = READ_CONTEXT[path]

        # read_webapi_table reads JSON numbers and treats an absent key as no value, which is how these files are
        # declared; the var declares decimal null, so its decimals are checked here, value by value
        if c["numbers"] != BPS_NUMBERS or c["missing"] != ABSENT_KEY:
            raise ValueError(f"{path.name}: READ_CONTEXT declares {c}, which read_webapi_table does not read")
        table, records = cleaning.read_webapi_table(path, var=c["var"], unit=c["unit"], encoding=c["encoding"])
        v = table["var"][0]
        if v["decimal"] is not c["decimals"]:
            raise ValueError(f"{path.name}: var declares decimal {v['decimal']!r}, expected {c['decimals']!r}")

        # The file must hold the table, the years the download asked for, and the declared breakdowns and note
        years = [int(t["label"]) for t in table["tahun"]]
        if years != list(range(first, last + 1)):
            raise ValueError(f"{path.name}: years {years}, expected {first}-{last}")
        cleaning.require_text(v["label"], BPS_LABEL, path.name)
        if (v["subj"], table["labelvervar"]) != (BPS_SUBJECT, BPS_REGIONS):
            raise ValueError(f"{path.name}: subject {v['subj']!r}, regions {table['labelvervar']!r}")
        if ([(t["val"], t["label"]) for t in table["turvar"]] != BPS_TURVAR
                or [(t["val"], t["label"]) for t in table["turtahun"]] != BPS_TURTAHUN):
            raise ValueError(f"{path.name}: turvar {table['turvar']}, turtahun {table['turtahun']}")
        items = [" ".join(i.split()) for i in re.findall(r"<li>(.*?)</li>", v["note"], re.S)]
        if items != BPS_NOTE_ITEMS or cleaning.parse_status_note(v["note"]) != {}:
            raise ValueError(f"{path.name}: note items {items}, or the note now gives revision statuses")

        # The region list is the 38 provinces under their BPS names and codes, then INDONESIA
        regions = [cleaning.webapi_region_code(r["val"], r["label"], lookup) for r in table["vervar"]]
        if regions[-1] != cleaning.NATIONAL_CODE or len(set(regions[:-1])) != 38:
            raise ValueError(f"{path.name}: region list {regions}")

        # Each value is whole rupiah and goes to its province (checked against the BPS list by name) and year, once
        for r in records:
            if not r["value"].is_integer():
                raise ValueError(f"{path.name}: {r['vervar']} {r['year']} = {r['value']} is not whole rupiah")
            code = cleaning.webapi_region_code(r["vervar"], r["vervar_label"], lookup)
            target = national if code == cleaning.NATIONAL_CODE else values
            key = r["year"] if code == cleaning.NATIONAL_CODE else (code, r["year"])
            if key in target:
                raise ValueError(f"{path.name}: {key} read twice")
            target[key] = r["value"]
        tables.append(table)

    # All eight files must come from one release of the table
    for table in tables[1:]:
        for field in ("var", "subject", "turvar", "turtahun", "vervar", "labelvervar", "last_update"):
            if table[field] != tables[0][field]:
                raise ValueError(f"var 220 files differ in {field}")
    return values, national, tables[0]


def kemnaker_code(name, lookup, used):
    """Return the BPS code of a Kemnaker province name, through a declared alias where the BPS list lacks the
    spelling."""
    key = cleaning.normalise_name(name)
    if key in NAME_ALIASES:
        used.add(key)
        key = NAME_ALIASES[key][0]
    return cleaning.province_code(key, lookup)


def sheet_cells(path, sheet, data_only=False):
    """Open a workbook read-only; return its sheet names and every cell of one sheet that holds a value or a fill, as
    {(row, column): {"value", "type", "format", "fill"}}, with formulas as text or, when data_only, their saved
    results."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=data_only)
    try:
        cells = {}
        for row in wb[sheet].iter_rows():
            for c in row:
                # Empty cells carry no position; a fill is kept by its colour
                if not hasattr(c, "row"):
                    continue
                fill = None
                if c.fill is not None and c.fill.fill_type is not None:
                    rgb = c.fill.fgColor.rgb
                    fill = rgb if isinstance(rgb, str) else f"theme {c.fill.fgColor.theme}"
                if c.value is not None or fill is not None:
                    cells[(c.row, c.column)] = {"value": c.value, "type": c.data_type, "format": c.number_format,
                                                "fill": fill}
        return wb.sheetnames, cells
    finally:
        wb.close()


def clean(text):
    """Return a workbook text with its white space collapsed, for the metadata and for matching labels."""
    return " ".join(str(text).split())


def form_fields(cells, labels, key=None):
    """Return {label: text} from a form laid out as one header row of labels over a row of values: the row below the
    header, or, when key gives (label, text), the row below it whose cell under that label holds that text."""
    texts = {k: clean(c["value"]) for k, c in cells.items() if c["value"] is not None}
    rows = {}
    for (r, col), text in texts.items():
        rows.setdefault(r, {})[text] = col
    header = [r for r, found in rows.items() if all(label in found for label in labels)]
    if len(header) != 1:
        raise ValueError(f"form: {len(header)} rows hold all of {labels}")
    columns = {label: rows[header[0]][label] for label in labels}
    if key is None:
        value_row = header[0] + 1
    else:
        found = [r for (r, col), text in texts.items() if r > header[0] and col == columns[key[0]] and text == key[1]]
        if len(found) != 1:
            raise ValueError(f"form: {len(found)} rows hold {key[1]!r} under {key[0]!r}")
        value_row = found[0]
    return {label: texts.get((value_row, col)) for label, col in columns.items()}


def label_fields(cells, labels, first_row, label_col=1, value_col=3):
    """Return {label: text} from a form laid out as labels down one column with values in another, from first_row."""
    fields = {}
    for label in labels:
        found = [r for (r, col), c in cells.items() if r >= first_row and col == label_col and c["value"] is not None
                 and clean(c["value"]) == label]
        if len(found) != 1:
            raise ValueError(f"block: label {label!r} found {len(found)} times")
        value = cells.get((found[0], value_col), {}).get("value")
        fields[label] = clean(value) if value is not None else None
    return fields


def check_formula(text, column, first, last, count, where):
    """Stop unless an average formula is SUM over the province rows of its own column divided by their number, or
    AVERAGE over them."""
    m = SUM_OVER_N.fullmatch(text) or AVERAGE_OF.fullmatch(text)
    letter = get_column_letter(column)
    if m is None or (m.group(1), int(m.group(2)), m.group(3), int(m.group(4))) != (letter, first, letter, last):
        raise ValueError(f"{where}: average formula {text!r} is not over {letter}{first}:{letter}{last}")
    if m.re is SUM_OVER_N and int(m.group(5)) != count:
        raise ValueError(f"{where}: {text!r} divides by {m.group(5)}, not by the {count} provinces")


def read_detail(dataset):
    """Read one Kemnaker detail file: its title, abstract as text, file address and dates."""
    path = RAW_DETAIL[dataset]
    reply = json.loads(path.read_text(encoding=READ_CONTEXT[path]["encoding"]))
    data = reply.get("data") or {}
    if reply.get("status") != 200 or data.get("id") != dataset:
        raise ValueError(f"{path.name}: status {reply.get('status')}, dataset {data.get('id')}")
    title = clean(data["judul"])
    if title != KEMNAKER[dataset][1]:
        raise ValueError(f"{path.name}: titled {title!r}")
    return {"title": title, "abstract": cleaning.html_to_text(data["abstraksi"]), "file_address": data["file"],
            "created_at": data["created_at"], "updated_at": data["updated_at"]}


def read_kemnaker(dataset, lookup, used):
    """Read one Kemnaker workbook's data sheet as declared in READ_CONTEXT, and its forms. Returns {(code, year):
    rupiah}, the cells printed with a missing marker, and a description that holds the average row against the mean
    of the provinces."""
    path = RAW_XLSX[dataset]
    c = READ_CONTEXT[path]
    names, cells = sheet_cells(path, c["sheet"])
    _, saved = sheet_cells(path, c["sheet"], data_only=True)
    if names != c["sheets"]:
        raise ValueError(f"{path.name}: sheets {names}, expected {c['sheets']}")
    texts = {k: cell["value"] for k, cell in cells.items() if cell["value"] is not None}
    seen = set()

    # The header row holds the topmost 'Provinsi' cell (dataset 36's forms block below the table repeats the word, which
    # is checked once the block is found), and the title lines are every text above it
    labelled = sorted(k for k, v in texts.items() if v == c["name_label"])
    if not labelled:
        raise ValueError(f"{path.name}: no cell reads {c['name_label']!r}")
    header, name_col = labelled[0]
    above = [k for k in sorted(texts) if k[0] < header]
    if [texts[k] for k in above] != c["titles"]:
        raise ValueError(f"{path.name}: titles {[texts[k] for k in above]}")
    seen |= set(above)

    # Each other header cell is the number label or the label of one value column, which gives the column's year
    number_col, year_col = None, {}
    for (r, col), text in sorted(texts.items()):
        if r != header or col == name_col:
            continue
        if c["number_label"] is not None and text == c["number_label"]:
            number_col = col
        elif text in c["columns"]:
            year_col[c["columns"][text]] = col
        else:
            raise ValueError(f"{path.name}: header cell {text!r} is not declared")
    if sorted(year_col) != sorted(c["columns"].values()) or (c["number_label"] is not None) != (number_col is not None):
        raise ValueError(f"{path.name}: header columns {year_col}, number column {number_col}")
    seen |= {k for k in texts if k[0] == header}

    # A single-year file names its year in a title line
    if len(year_col) == 1:
        cleaning.require_text(" ".join(c["titles"]), f"Tahun {list(year_col)[0]}", f"{path.name} title")

    # The unit text stands in each value column's header, or alone in the row below the header, or nowhere
    first = header + 1
    if c["unit_place"] == "header":
        for text in c["columns"]:
            cleaning.require_text(text, c["unit_text"], f"{path.name} header")
    elif c["unit_place"] == "row below the header":
        row = {col: v for (r, col), v in texts.items() if r == first}
        if row != {col: c["unit_text"] for col in year_col.values()}:
            raise ValueError(f"{path.name}: unit row {row}")
        seen |= {(first, col) for col in row}
        first += 1
    elif c["unit_place"] is not None or c["unit_text"] is not None:
        raise ValueError(f"{path.name}: unit place {c['unit_place']!r}")

    # The average row is the one row labelled with the average label, in the name or number column
    found = [k for k, v in texts.items() if v == c["average_label"]]
    if len(found) != 1 or found[0][1] not in (name_col, number_col) or found[0][0] <= first:
        raise ValueError(f"{path.name}: average label found at {found}")
    average_row, average_col = found[0]

    # Every row between the header and the average row is a province, matched by name: a consecutive number where the
    # file numbers its rows, then a number in the declared format or a declared marker in each value column, and nothing
    # else but cells holding a single space
    values, markers, fills, codes, stray = {}, [], {}, [], 0
    for n, r in enumerate(range(first, average_row), start=1):
        row = {col: cell for (rr, col), cell in cells.items() if rr == r}
        name = row.get(name_col, {}).get("value")
        if not isinstance(name, str):
            raise ValueError(f"{path.name}: row {r} has no province name")
        code = kemnaker_code(name, lookup, used)
        codes.append(code)
        if number_col is not None and row.get(number_col, {}).get("value") != n:
            raise ValueError(f"{path.name}: {name} numbered {row.get(number_col, {}).get('value')}, expected {n}")
        for year, col in year_col.items():
            cell = row.get(col, {})
            value = cleaning.parse_cell(cell.get("value"), c["missing"])
            if value is None:
                markers.append({"province_code": code, "period": str(year), "marker": cell["value"]})
            elif cell["type"] != "n" or cell["format"] != c["number_format"] or decimals_of(value) > c["decimals"]:
                raise ValueError(f"{path.name}: {name} {year} is {cell}, not a number in the declared format")
            else:
                values[(code, year)] = value
            if cell.get("fill") is not None:
                fills[(code, year)] = cell["fill"]
        for col, cell in row.items():
            if col in (name_col, number_col, *year_col.values()) or cell["value"] is None:
                continue
            if cell["value"] != c["stray_text"]:
                raise ValueError(f"{path.name}: row {r} holds {cell['value']!r} outside the table")
            stray += 1
        seen |= {(r, col) for col in row}
    if len(set(codes)) != len(codes):
        raise ValueError(f"{path.name}: a province is listed twice")
    expected = {code for code in lookup.values() if code != cleaning.NATIONAL_CODE
                and (LISTS_NEW_PAPUA[dataset] or code not in NEW_PAPUA)}
    if set(codes) != expected:
        raise ValueError(f"{path.name}: provinces differ from the declared list: {sorted(set(codes) ^ expected)}")
    if stray != c["stray"]:
        raise ValueError(f"{path.name}: {stray} cells hold a single space, declared {c['stray']}")

    # The average row holds, in each value column, the mean of that column's provinces: a saved formula over the
    # province rows, or a value (dataset 36); the label and these cells are all it holds
    row = {col: cell for (r, col), cell in cells.items() if r == average_row and cell["value"] is not None}
    if set(row) != {average_col, *year_col.values()}:
        raise ValueError(f"{path.name}: average row holds cells in columns {sorted(row)}")
    averages = {}
    for year, col in year_col.items():
        own = [v for (code, y), v in values.items() if y == year]
        mean = sum(own) / len(own)
        if c["average"] == "formulas":
            check_formula(row[col]["value"], col, first, average_row - 1, len(own), f"{path.name} {year}")
            shown, cell_text = saved[(average_row, col)]["value"], row[col]["value"]
        else:
            if row[col]["type"] != "n" or row[col]["format"] != c["number_format"]:
                raise ValueError(f"{path.name}: average {year} is {row[col]}")
            shown, cell_text = row[col]["value"], "a value, not a formula"
        if not isinstance(shown, (int, float)) or abs(shown - mean) > TOL_AVERAGE:
            raise ValueError(f"{path.name}: average {year} {shown!r} is not the mean {mean} of its provinces")
        averages[str(year)] = {"label": c["average_label"], "cell": cell_text, "value": round(float(shown), 6),
                               "provinces": len(own), "mean_of_provinces": round(mean, 6)}
    seen |= {(average_row, col) for col in row}

    # Below the average row come the declared lines, then, in dataset 36, the block of forms from its heading down
    block_row = None
    if c["block"] is not None:
        found = [r for (r, col), v in texts.items() if r > average_row and col == 1 and v == c["block"]]
        if len(found) != 1:
            raise ValueError(f"{path.name}: block heading {c['block']!r} found {len(found)} times")
        block_row = found[0]
    if any(k[0] < (block_row or math.inf) for k in labelled[1:]):
        raise ValueError(f"{path.name}: {c['name_label']!r} stands outside the header at {labelled[1:]}")
    below = [k for k in sorted(texts) if k[0] > average_row and (block_row is None or k[0] < block_row)]
    if [texts[k] for k in below] != c["after"]:
        raise ValueError(f"{path.name}: lines below the table {[texts[k] for k in below]}")
    seen |= set(below)
    if block_row is not None:
        seen |= {k for k in texts if k[0] >= block_row}
    if set(texts) - seen:
        raise ValueError(f"{path.name}: cells not read: {sorted(set(texts) - seen)[:5]}")

    # Dataset 36's colour legend: each legend line beside a cell of its colour, and the filled value cells exactly the
    # declared ones; no other file fills a value cell
    legend = []
    declared_fills = {}
    if dataset == 36:
        for colour, entry in LEGEND_36.items():
            where = [k for k in below if texts[k] == entry["note"]]
            swatch = cells.get((where[0][0], where[0][1] - 1), {}).get("fill") if len(where) == 1 else None
            if swatch != colour:
                raise ValueError(f"{path.name}: legend line {entry['note']!r} stands beside fill {swatch}")
            if entry["named"] is not None:
                named = sorted(kemnaker_code(name, lookup, used) for name in entry["named"])
                cleaning.require_text(entry["note"], " dan ".join([", ".join(entry["named"][:-1]),
                                                                   entry["named"][-1]]), f"{path.name} legend")
                if named != sorted(code for code, _ in entry["cells"]):
                    raise ValueError(f"{path.name}: legend names {named}, cells {entry['cells']}")
            declared_fills.update({cell: colour for cell in entry["cells"]})
            legend.append({"fill": colour, "note": clean(entry["note"]), "english": entry["english"],
                           "cells": [[code, str(year)] for code, year in entry["cells"]]})
    if fills != declared_fills:
        raise ValueError(f"{path.name}: filled value cells {fills}, declared {declared_fills}")

    # Dataset 473's 2022 marker: the header label carries it and a line below the table explains it
    marker = None
    if dataset == 473:
        if MARKER_473["header"] not in c["columns"] or MARKER_473["note"] not in c["after"]:
            raise ValueError(f"{path.name}: the 2022 marker or its note is gone")
        marker = {"column": MARKER_473["header"], "year": str(MARKER_473["year"]), "marker": MARKER_473["marker"],
                  "note": MARKER_473["note"], "english": "the 2022 values are as recorded on 8 February 2022",
                  "use": "a date of record, not a revision status, so the 2022 rows keep an empty status"}

    # The forms, read by their labels; the field that gives the unit must read 'Rupiah' in both
    forms = {}
    if dataset in FORMS:
        spec = FORMS[dataset]
        if spec["standard"] is None:
            forms["standard_data"] = label_fields(cells, STANDARD_LABELS, block_row)
        else:
            forms["standard_data"] = form_fields(sheet_cells(path, spec["standard"])[1], STANDARD_LABELS)
        sheet, name = spec["indicator"]
        source = cells if sheet == c["sheet"] else sheet_cells(path, sheet)[1]
        forms["indicator_metadata"] = form_fields(source, INDICATOR_LABELS, ("Nama Indikator", name))
        for form in forms.values():
            if form[spec["unit_field"]] != "Rupiah":
                raise ValueError(f"{path.name}: unit field {spec['unit_field']!r} reads {form[spec['unit_field']]!r}")

    info = {"sheet": c["sheet"], "titles": [clean(t) for t in c["titles"]],
            "columns": {str(label): str(year) for label, year in c["columns"].items()},
            "unit_text": c["unit_text"], "unit_place": c["unit_place"] or "nowhere: the file states no unit",
            "provinces": len(codes), "number_format": c["number_format"],
            "max_decimals": max(decimals_of(v) for v in values.values()),
            "lines_below_table": [clean(t) for t in c["after"]], "cells_holding_one_space": stray,
            "missing_markers": markers, "average_row": averages, "cell_notes": legend, "column_marker": marker,
            **forms}
    return values, markers, info


def compare_pair(first, second, sources):
    """Layer 4: compare two sources value by value over the years both hold, within the tolerance; each declared
    difference must hold exactly instead. Stops unless both hold the same provinces in those years."""
    a_all, b_all = sources[first], sources[second]
    years = sorted({y for _, y in a_all} & {y for _, y in b_all})
    a = {k: v for k, v in sorted(a_all.items()) if k[1] in years}
    b = {k: v for k, v in sorted(b_all.items()) if k[1] in years}
    if set(a) != set(b):
        raise ValueError(f"{first} and {second} hold different provinces: {sorted(set(a) ^ set(b))}")
    # A declaration applies to a pair of sources whose declared values differ; sources it gives the same value are
    # compared as usual
    declared = {k: d for k, d in DECLARED.items() if first in d and second in d and d[first] != d[second]}
    for k, d in declared.items():
        if (a[k], b[k]) != (d[first], d[second]):
            raise ValueError(f"{k}: {first} {a[k]}, {second} {b[k]}; declared {d[first]}, {d[second]}")
    tolerance = TOL_BPS if first == "bps" else TOL_KEMNAKER
    label = (f"{SOURCE_NAME[first]} = {SOURCE_NAME[second]}, {spans(years)}, every province, rupiah per month, "
             f"except the declared differences")
    result = cleaning.compare_sources({(c, str(y)): v for (c, y), v in a.items() if (c, y) not in declared},
                                      {(c, str(y)): v for (c, y), v in b.items() if (c, y) not in declared},
                                      tolerance, label)
    result["keys"] = f"[province_code, period]; first = {SOURCE_CODE[first]}, second = {SOURCE_CODE[second]}"
    result["tolerance_reason"] = TOLERANCE_REASONS["bps" if first == "bps" else "kemnaker"]
    result["declared_differences"] = [{"key": [k[0], str(k[1])], "first": d[first], "second": d[second],
                                       "gap": float(abs(Decimal(str(d[first])) - Decimal(str(d[second])))),
                                       "reason": d["reason"]} for k, d in declared.items()]
    return result


def abstract_checks(kem, details):
    """Check every figure the Kemnaker abstracts state against the dataset's own values, each parsed as text in the
    detail file's declared Indonesian format."""
    out = []
    for dataset, figures in ABSTRACT_FIGURES.items():
        c = READ_CONTEXT[RAW_DETAIL[dataset]]
        for text, statistic, year, base in figures:
            cleaning.require_text(details[dataset]["abstract"], text, f"dataset {dataset} abstract")
            stated = cleaning.parse_number(FIGURE_TEXT.fullmatch(text).group(1), c["decimal"], c["thousands"],
                                           c["decimals"])
            own = [v for (_, y), v in kem[dataset].items() if y == year]
            mean = sum(own) / len(own)
            if statistic == "mean":
                found = mean
            elif statistic == "lowest":
                found = min(own)
            elif statistic == "highest":
                found = max(own)
            else:
                # A change of the mean starts from the declared dataset and year, which every change figure must give
                start = [v for (_, y), v in kem[base[0]].items() if y == base[1]]
                start = sum(start) / len(start)
                found = {"mean_change": mean - start, "mean_change_pct": (mean / start - 1) * 100}[statistic]
            if abs(found - stated) > TOL_AVERAGE:
                raise ValueError(f"dataset {dataset} abstract states {text!r}; the file gives {found}")
            out.append({"dataset": dataset, "text": text, "statistic": statistic, "year": str(year),
                        "from": None if base is None else f"dataset {base[0]}, {base[1]}", "stated": stated,
                        "from_the_file": round(found, 4)})
    return {"check": "every figure a Kemnaker abstract states equals the statistic of the dataset's own values, to 2 "
                     "decimals", "figures": out}


def national_rows(bps_values, national):
    """Layer 3: BPS's INDONESIA row against the unweighted mean of the provinces var 220 lists in the same year, as
    NATIONAL_ROUNDED_TO, NATIONAL_LEFT_OUT and NATIONAL_UNMATCHED declare; stops on any other gap."""
    years = {}
    for year, published in sorted(national.items()):
        left = NATIONAL_LEFT_OUT.get(year, [])
        kept = [v for (code, y), v in bps_values.items() if y == year and code not in left]
        mean = sum(kept) / len(kept)
        step = NATIONAL_ROUNDED_TO.get(year, 1)
        if year in NATIONAL_UNMATCHED:
            gap = Decimal(str(published - mean)).quantize(Decimal("0.01"))
            if gap != NATIONAL_UNMATCHED[year]:
                raise ValueError(f"INDONESIA {year}: gap to the mean is {gap}, declared {NATIONAL_UNMATCHED[year]}")
        elif step == 100 and not (published % 100 == 0 and abs(published - mean) <= 50):
            raise ValueError(f"INDONESIA {year}: {published} is not the mean {mean} rounded to the nearest 100")
        elif step == 1 and abs(published - mean) >= TOL_NATIONAL:
            raise ValueError(f"INDONESIA {year}: {published} differs from the mean {mean} by 1 rupiah or more")
        years[str(year)] = {"published": published, "provinces_averaged": len(kept), "left_out": left,
                            "mean_of_provinces": round(mean, 3), "rounded_to": step,
                            "gap": round(published - mean, 3), "matches": year not in NATIONAL_UNMATCHED}
    return {"check": "BPS var 220's INDONESIA row equals the unweighted mean of the provinces the file lists that "
                     "year, with the declared exceptions; written to the metadata only", "years": years}


def merge(sources):
    """Take each year's values from the first source in PRIORITY that holds the year; stop if a lower-priority source
    holds a province that year that the chosen source lacks. Returns values, the source of each, and of each year."""
    values, origin, by_year = {}, {}, {}
    for year in YEARS:
        holders = [s for s in PRIORITY if any(y == year for _, y in sources[s])]
        if not holders:
            raise ValueError(f"no source holds {year}")
        mine = {k: v for k, v in sources[holders[0]].items() if k[1] == year}
        for other in holders[1:]:
            extra = {k for k in sources[other] if k[1] == year} - set(mine)
            if extra:
                raise ValueError(f"{other} holds {sorted(extra)} that {holders[0]} lacks in {year}")
        values.update(mine)
        origin.update({k: holders[0] for k in mine})
        by_year[year] = holders[0]
    return values, origin, by_year


def coverage_runs(values, codes):
    """Describe each run of years with the same provinces: how many have values and which codes are absent."""
    runs = []
    for year in YEARS:
        absent = [code for code in codes if (code, year) not in values]
        if runs and runs[-1]["absent"] == absent:
            runs[-1]["last"] = year
        else:
            runs.append({"first": year, "last": year, "absent": absent})
    return {spans(range(r["first"], r["last"] + 1)): {"provinces": len(codes) - len(r["absent"]), "absent": r["absent"]}
            for r in runs}


def border_changes(values):
    """Return {(province, year): reason} for each province whose change from the year before compares different areas:
    a province formed from it gains or loses its own value that year."""
    out = {}
    for parent in sorted(set(PARENT.values())):
        children = [c for c, p in PARENT.items() if p == parent]
        for year in YEARS[1:]:
            if (parent, year) not in values or (parent, year - 1) not in values:
                continue
            before = {c for c in children if (c, year - 1) in values}
            now = {c for c in children if (c, year) in values}
            if before != now:
                # Say which provinces formed from it start or stop having a value that year
                parts = []
                for found, one, many in ((now - before, f"has its own value from {year}",
                                          f"have their own values from {year}"),
                                         (before - now, f"has no value in {year}", f"have no value in {year}")):
                    if found:
                        parts.append(f"{and_list(sorted(found))} {one if len(found) == 1 else many}")
                out[(parent, year)] = (f"{'; '.join(parts)} (formed from {parent}), so the provinces listed for "
                                       f"{parent}'s former area change from {year - 1} to {year}; no change check "
                                       f"reads {parent}'s change")
    return out


def flag_range(rows, check):
    """Layer 5: flag the rows whose value lies outside the check's stated range, which None leaves open above."""
    low, high = PLAUSIBLE[check]
    flags = cleaning.flag_outside(rows, check, low, math.inf if high is None else high)
    # Each flag states the range as declared, since JSON has no infinity
    return [{**f, "range": [low, high]} for f in flags]


def plausibility(values, origin):
    """Layer 5: every value inside its range, every change from the year before inside its range, and no value left
    unchanged outside the 2021 freeze; changes across a border change are left out. Returns the flags, the number of
    values each check read and the changes left out."""
    skip = border_changes(values)
    read = {check: [] for check in PLAUSIBLE}
    for (code, year), now in sorted(values.items()):
        read["minimum_wage_rupiah"].append({"province_code": code, "period": str(year),
                                            "source": SOURCE_CODE[origin[(code, year)]], "value": now})
        before = values.get((code, year - 1))
        if before is None or (code, year) in skip:
            continue
        common = {"province_code": code, "period": str(year), "from_period": str(year - 1),
                  "rupiah": {str(year - 1): before, str(year): now},
                  "sources": {str(year - 1): SOURCE_CODE[origin[(code, year - 1)]],
                              str(year): SOURCE_CODE[origin[(code, year)]]}}
        read["minimum_wage_change_pct"].append({**common, "value": (now / before - 1) * 100})
        if year != FREEZE_YEAR:
            read["unchanged_from_previous_year_rupiah"].append({**common, "value": abs(now - before)})
    flags = [f for check in PLAUSIBLE for f in flag_range(read[check], check)]
    not_compared = [{"province_code": code, "period": str(year), "reason": reason}
                    for (code, year), reason in sorted(skip.items())]

    # The facts the ranges are justified by must still hold: the lowest and highest value, and the largest median
    # change across provinces in a year
    lowest, highest = min(values.items(), key=lambda kv: kv[1]), max(values.items(), key=lambda kv: kv[1])
    by_year = {}
    for r in read["minimum_wage_change_pct"]:
        by_year.setdefault(int(r["period"]), []).append(r["value"])
    medians = {year: statistics.median(changes) for year, changes in by_year.items()}
    top = max(medians, key=medians.get)
    found = {"lowest": (lowest[1], lowest[0][1]), "highest": (highest[1], highest[0][1]),
             "largest_median_change_pct": (round(medians[top], 1), top)}
    if found != PLAUSIBLE_BASIS:
        raise ValueError(f"the values give {found}, but the plausibility ranges are justified by {PLAUSIBLE_BASIS}")
    return flags, {check: len(rows) for check, rows in read.items()}, not_compared


def same_as_parent(values, provinces):
    """Return, for each later province, the years its value equals that of the province it was formed from."""
    out = {}
    for child, parent in PARENT.items():
        years = [y for y in YEARS if (child, y) in values and values.get((parent, y)) == values[(child, y)]]
        out[child] = {"name": provinces[child]["name"], "formed_from": parent, "formed": FORMED[child],
                      "first_year": FIRST_YEAR.get(child, YEARS[0]), "years_equal_to_parent": spans(years) or None}
    return out


# Steps

# Print in UTF-8 so source labels show on any console
sys.stdout.reconfigure(encoding="utf-8")

# Read the BPS province list that every name and code is matched against; load_bps_provinces reads UTF-8 JSON, so a
# list declared in another encoding stops the build
if READ_CONTEXT[RAW_PROVINCES]["encoding"] != "utf-8":
    raise ValueError(f"{RAW_PROVINCES.name}: declared {READ_CONTEXT[RAW_PROVINCES]}, but read as UTF-8")
provinces, lookup = cleaning.load_bps_provinces(RAW_PROVINCES)
codes = [c for c in provinces if c != cleaning.NATIONAL_CODE]

# Stop unless both download scripts are in the repository and raw/labour holds exactly the declared files of each source
for script in (BPS_DOWNLOAD, KEMNAKER_DOWNLOAD):
    if not (ROOT / script).is_file():
        raise FileNotFoundError(f"download script {script} not found")
if sorted(RAW_DIR.glob("20261104_bps-api-var220-*.json")) != sorted(RAW_BPS.values()):
    raise ValueError("raw/labour holds other var 220 files than the declared ones")
if sorted(RAW_DIR.glob("20261104_kemnaker-dataset-*")) != sorted([*RAW_XLSX.values(), *RAW_DETAIL.values()]):
    raise ValueError("raw/labour holds other Kemnaker files than the declared ones")

# Read BPS var 220: the provinces' values, the INDONESIA row and the table's description
bps, bps_national, bps_table = read_bps(lookup)

# Read each Kemnaker dataset: its detail and its workbook, with every province matched by name
used_aliases = set()
details = {d: read_detail(d) for d in KEMNAKER}
kem, kem_markers, kem_info = {}, {}, {}
for d in KEMNAKER:
    kem[d], kem_markers[d], kem_info[d] = read_kemnaker(d, lookup, used_aliases)
if used_aliases != set(NAME_ALIASES):
    raise ValueError(f"aliases declared but not used: {sorted(set(NAME_ALIASES) - used_aliases)}")
sources = {"bps": bps, **kem}

# The abstracts must still state the 2021 freeze and the new provinces' minimum wage, on which the metadata relies
cleaning.require_text(details[473]["abstract"], FREEZE_TEXT, "dataset 473 abstract")
cleaning.require_text(details[1611]["abstract"], NEW_PROVINCES_TEXT, "dataset 1611 abstract")

# Layer 4: BPS against both Kemnaker releases, and the two Kemnaker releases against each other, value by value over
# the years both hold; the declared differences must hold exactly, and BPS's Jawa Barat 2016 must still be its own
# Sulawesi Selatan 2016 value
cross = [compare_pair("bps", 36, sources), compare_pair("bps", 473, sources), compare_pair(473, 36, sources)]
for key, other in SAME_AS.items():
    if bps[key] != bps[other]:
        raise ValueError(f"BPS {key} is {bps[key]}, no longer its value for {other} ({bps[other]})")

# Every figure the Kemnaker abstracts state must match the dataset's own values
abstracts = abstract_checks(kem, details)

# Layer 3: BPS's INDONESIA row against the mean of its provinces; each Kemnaker average row was checked as it was read
national = national_rows(bps, bps_national)

# Take each year from the first source in priority order that holds it
values, origin, by_year = merge(sources)

# Coverage: every province from its declared first year, the declared gaps and nothing else, which completeness
# enforces; each gap's reason must still hold in the files
for (code, year), _ in GAPS.items():
    if year in BPS_YEARS and (code, year) in bps:
        raise ValueError(f"BPS now holds {code} {year}, declared a gap")
java_markers = {(m["province_code"], int(m["period"])) for m in kem_markers[36] if m["marker"] == "-"}
if java_markers != {k for k, reason in GAPS.items() if reason == GAP_JAVA}:
    raise ValueError(f"dataset 36 prints '-' at {sorted(java_markers)}, not at the declared 2016 gaps")
if any(int(y) <= 2004 for d in KEMNAKER for y in KEMNAKER[d][0].split("-")):
    raise ValueError("a Kemnaker file now covers the Kepulauan Riau gap of 2002-2004")
first_found = {code: min(y for c, y in values if c == code) for code in codes}
if first_found != {code: FIRST_YEAR.get(code, YEARS[0]) for code in codes}:
    raise ValueError(f"first years in the files {first_found} differ from FIRST_YEAR")
expected = {(code, INDICATOR, str(year)) for code in codes for year in YEARS
            if year >= FIRST_YEAR.get(code, YEARS[0]) and (code, year) not in GAPS}

# Rows of the CSV: one value per province and year, every status empty (no source gives a revision status)
rows = [{"province_code": c, "indicator": INDICATOR, "period": str(y), "status": "", "value": v}
        for (c, y), v in sorted(values.items())]

# The CSV writes values with 10 significant digits, so stop unless every value reads back exactly
for r in rows:
    if float(f"{r['value']:.10g}") != r["value"]:
        raise ValueError(f"{r}: the value does not survive the CSV's number format")

# Layer 5: values, changes and unchanged values against their stated ranges; outliers are only flagged
flags, compared, change_not_compared = plausibility(values, origin)

# Statements for the metadata, written from the merge, the checks and the declarations so that they cannot go stale
kemnaker_years = [y for y in YEARS if by_year[y] != "bps"]
source_by_year = {}
for year in YEARS:
    source_by_year.setdefault(by_year[year], []).append(year)
by_year_text = {spans(years): SOURCE_NAME[s] for s, years in sorted(source_by_year.items(), key=lambda x: x[1][0])}
rows_by_source = {SOURCE_CODE[s]: sum(1 for k in values if origin[k] == s) for s in PRIORITY}
jabar = DECLARED[("32", 2016)]
average_gaps = [abs(a["value"] - a["mean_of_provinces"]) for d in KEMNAKER for a in kem_info[d]["average_row"].values()]

# Describe each source table for the metadata
bps_v = bps_table["var"][0]
source_tables = {
    "bps_var220": {
        "role": f"gives every value of {spans(BPS_YEARS)}",
        "label": bps_v["label"], "subject": [bps_v["subj"], bps_table["subject"][0]["label"]],
        "unit": bps_v["unit"],
        "decimals": "the var declares decimal null; every value is a JSON integer (whole rupiah)",
        "regions": bps_table["labelvervar"], "turvar": BPS_TURVAR[0][1], "turtahun": BPS_TURTAHUN[0][1],
        "last_update": bps_table["last_update"], "note_items": BPS_NOTE_ITEMS,
        "note_english": ["Source: Ministry of Manpower (Kementerian Ketenagakerjaan)",
                         "Kalimantan Utara's 2013 figure is still combined with Kalimantan Timur",
                         "The data are quoted from the publication Statistik Indonesia"],
        "request": URL_BPS + " (th = years minus 1900 joined by ';', such as 97;98;99; the key is not stored)",
        "download_script": BPS_DOWNLOAD, "files": [posix(p) for p in RAW_BPS.values()],
    },
    **{SOURCE_CODE[d]: {
        "role": (f"gives every value of {spans([y for y in YEARS if by_year[y] == d])}"
                 if any(by_year[y] == d for y in YEARS) else "a check only: every year it holds comes from BPS")
                + (f"; checks {spans(sorted({y for _, y in kem[d]} & set(BPS_YEARS)))} against BPS"
                   if {y for _, y in kem[d]} & set(BPS_YEARS) else ""),
        **details[d], **{k: v for k, v in kem_info[d].items() if k != "average_row"},
        "average_row": "national_rows.kemnaker_rata_rata",
        "detail_request": URL_DETAIL, "download_script": KEMNAKER_DOWNLOAD,
        "files": [posix(RAW_DETAIL[d]), posix(RAW_XLSX[d])],
    } for d in KEMNAKER},
}

# Describe the dataset
meta = {
    "title": "Provincial minimum wage (Upah Minimum Provinsi, UMP) by province, Indonesia, 1997-2025: BPS figures, "
             "with Ministry of Manpower (Kemnaker) figures for the years BPS does not publish",
    "columns": {
        "province_code": "BPS province code (kode_bps) of the 38 provinces; there is no Indonesia row (see "
                         "'national_rows'). Names and Kemendagri codes in 'provinces'.",
        "indicator": "Indicator code; definition in 'indicators'.",
        "period": "YYYY, the year the minimum wage is set for; a UMP applies to the whole calendar year from 1 "
                  "January.",
        "status": "Revision marker; no source gives one, so every row is empty (see notes on dataset 473's '2022*').",
        "value": "Rupiah per month: whole rupiah in the years from BPS, and up to 2 decimals, as Kemnaker stores them, "
                 "in the years from Kemnaker (see 'sources').",
    },
    "provinces": {c: provinces[c] for c in codes},
    "province_source": {"url": URL_PROVINCES, "file": posix(RAW_PROVINCES),
                        "note": "BPS and Kemendagri codes differ for the six Papua provinces; join other datasets on "
                                "the code system they use."},
    "indicators": {INDICATOR: {
        "name": "Upah Minimum Provinsi (UMP), provincial minimum wage; BPS labels it 'Upah Minimum Regional/Propinsi', "
                "naming the older term UMR beside UMP",
        "definition": kem_info[36]["standard_data"]["Definisi"],
        "definition_english": "The minimum wage is the lowest monthly wage, being the wage without allowances or the "
                              "basic wage including fixed allowances, set by the governor as a safety net. The UMP is "
                              "the minimum wage that applies to every regency and city within one province.",
        "unit": "rupiah per month (BPS unit 'Rupiah'; Kemnaker '(Rp)', and 'upah bulanan' in its definition)",
        "multiplier": 1, "base_unit": "Rp per month",
        "decimals": "0 in the BPS years; up to 2 in the Kemnaker years, shown by Kemnaker with the format #,##0.00",
        "periods": f"{YEARS[0]}-{YEARS[-1]}, annual",
        "source": "see 'sources': BPS WebAPI var 220 where BPS publishes the year, Kemnaker Satu Data otherwise",
    }},
    "sources": {
        "statement": f"Every value of {spans(BPS_YEARS)} is BPS's (WebAPI var 220). The values of "
                     f"{spans(kemnaker_years)} are not BPS figures: BPS publishes none for those years, so they come "
                     f"from the Ministry of Manpower (Kementerian Ketenagakerjaan, Kemnaker) Satu Data portal. This "
                     f"departs from the project's practice of using BPS numbers only, by the user's choice. BPS's own "
                     f"note names Kemnaker as its source ('{BPS_NOTE_ITEMS[0]}').",
        "by_year": by_year_text,
        "rows_by_source": rows_by_source,
        "priority": [{"rank": i + 1, "source": SOURCE_CODE[s], "name": SOURCE_NAME[s],
                      "years_held": spans(sorted({y for _, y in sources[s]}))} for i, s in enumerate(PRIORITY)],
        "rule": "Each year takes all its values from the first source in this order that holds the year; the "
                "lower-priority copies serve as checks (checks.cross_source). Kemnaker's datasets repeat only "
                "2018-2020 (36 and 473), all BPS years, and 473, the later release, ranks above 36.",
    },
    "source_tables": source_tables,
    "periods": {
        "held": PERIODS,
        "note": "One value per province and year: the year the UMP is set for, as BPS's tahun and Kemnaker's titles "
                "and year columns name it. A UMP is set by the governor before the year starts and applies from 1 "
                "January.",
    },
    "coverage": {
        "years": coverage_runs(values, codes),
        "first_year": {code: {"year": year, "source": SOURCE_CODE[origin[(code, year)]]}
                       for code, year in sorted(FIRST_YEAR.items())},
        "gaps": {f"{code} {year}": reason for (code, year), reason in sorted(GAPS.items())},
        "same_as_parent": same_as_parent(values, provinces),
        "formed_note": "'formed' gives the year each later province was formed, which is general knowledge, not read "
                       "from these files. BPS var 220 lists several of them from 1997 or 1998, before they were "
                       "formed, mostly with the value of the province they were formed from ('years_equal_to_parent'); "
                       "the values are kept as BPS publishes them.",
        "kalimantan_utara": f"BPS var 220 starts Kalimantan Utara (65) in 2015, with Kalimantan Timur's value; its "
                            f"note says the 2013 figure is still combined with Kalimantan Timur "
                            f"('{BPS_NOTE_ITEMS[1]}'), and the files give no 2014 value either.",
        "new_papua_provinces": f"Kemnaker dataset 1611 (2024) is the first file to list Papua Barat Daya (92), Papua "
                               f"Selatan (95), Papua Tengah (96) and Papua Pegunungan (97), as its abstract says "
                               f"('{NEW_PROVINCES_TEXT}'); dataset 942 (2023) lists only Papua Barat (91) and "
                               f"Papua (94).",
    },
    "borders": [
        "A UMP is a rate set for a province, not a total over its area, so a value does not change because the "
        "province's area changes; still, a change of a province from the year before is left out of the change "
        "checks when a province formed from it gains or loses its own value that year (checks.change_not_compared).",
        "91 (Papua Barat) and 94 (Papua) up to 2023 are the UMPs of the pre-split provinces; the four new Papua "
        "provinces have their own values from 2024.",
    ],
    "national_rows": {
        "decision": "The dataset has no Indonesia (00) row. Indonesia has no national minimum wage: each source's "
                    "national row is an average of the provincial UMPs, a derived value that belongs in analysis/. "
                    "Kemnaker labels its row 'Rata-rata' (average) and computes it as the unweighted mean of the "
                    "provinces it lists; BPS's INDONESIA row is not described by BPS and, in every year but "
                    f"{and_list(sorted(NATIONAL_UNMATCHED))}, is such a mean over a set of provinces that changes "
                    "from year to year (checks.identities).",
        "formula": "unweighted mean (Rp per month) = sum of minimum_wage over the provinces with a value that year / "
                   "the number of those provinces",
        "bps_var220_indonesia": {str(y): v for y, v in sorted(bps_national.items())},
        "kemnaker_rata_rata": {SOURCE_CODE[d]: kem_info[d]["average_row"] for d in KEMNAKER},
    },
    "notes": [
        f"Sources by year: {'; '.join(f'{k}: {v}' for k, v in by_year_text.items())}. Every value of "
        f"{spans(kemnaker_years)} is a Kemnaker figure, not a BPS figure.",
        f"Where BPS and Kemnaker hold the same year (2016, 2018-2020), BPS's whole-rupiah values equal Kemnaker's "
        f"rounded to whole rupiah, within {TOL_BPS} rupiah, except Jawa Barat 2016 and Banten 2019 "
        f"(checks.cross_source, declared_differences). The two Kemnaker releases 36 and 473 agree exactly in "
        f"2018-2020.",
        f"Jawa Barat (32) 2016: BPS publishes {jabar['bps']:,.0f}, Kemnaker dataset 36 {jabar[36]:,.0f}. BPS's figure "
        f"equals its own 2016 value for Sulawesi Selatan (73), and Kemnaker's abstract names {jabar[36]:,.0f} as the "
        f"lowest UMP of 2016, so BPS's figure looks like an error; the CSV keeps it by the stated priority, and "
        f"checks.flags lists the rise into 2016 and the fall into 2017 for a person to decide.",
        "Jawa Barat, Jawa Tengah, DI Yogyakarta and Jawa Timur (32-35) have the same value in 2015 as in 2014 in BPS "
        "var 220, and BPS's own 2015 INDONESIA mean leaves these four out (checks.identities); neither source gives "
        "them a 2016 value (coverage.gaps). checks.flags lists the four unchanged 2015 values.",
        f"2021: dataset 473's abstract says most provinces set the same UMP as in 2020, under {FREEZE_TEXT}, so 2021 "
        f"values equal to 2020's are expected and the unchanged check does not read 2021.",
        "Dataset 473 heads its 2022 column '2022*' with the note '*) data per 8 Februari 2022': the 2022 values are as "
        "Kemnaker recorded them on 8 February 2022. This is a date of record, not a BPS revision status, so the 2022 "
        "rows keep an empty status (source_tables.kemnaker_473.column_marker).",
        "The series switches between BPS's whole rupiah and Kemnaker's decimals at 2016/2017, 2017/2018 and "
        "2020/2021, so a change across a switch includes up to 0.5 rupiah of BPS's rounding: an unchanged 2021 UMP can "
        "show as a change of a few tenths of a rupiah.",
        "Dataset 36 fills 2020 cells with two colours that its legend explains (source_tables.kemnaker_36.cell_notes): "
        "Nusa Tenggara Timur, Kalimantan Tengah, Gorontalo and Sulawesi Barat set their 2020 UMP under PP 78/2015 with "
        "the phased approach to decent living needs (KHL), and Bengkulu, Bali and Papua Barat not under PP 78/2015.",
        "Derived values are not stored: change from the year before (%) = (value in year t / value in year t-1 - 1) x "
        "100; the national mean is in 'national_rows'.",
        "checks.flags lists every value, change and unchanged value outside its range in checks.plausible_ranges for a "
        "person to review, with the two values and their sources each change compares; a flag stays whether it "
        "reflects a real event or a source error.",
    ],
    "checks": {
        "passed": ["identities", "cross-source", "plausibility checked (layer 5, flags listed)"],
        "identities": [national, {"check": "each Kemnaker average row (Rata-rata) equals the unweighted mean of the "
                                           "provinces its dataset lists, within 0.005 rupiah, and each average formula "
                                           "covers exactly the province rows of its column",
                                  "compared": len(average_gaps), "tolerance": TOL_AVERAGE,
                                  "largest_gap": round(max(average_gaps), 6),
                                  "values": "national_rows.kemnaker_rata_rata"}],
        "cross_source": cross,
        "abstract_figures": abstracts,
        "name_aliases": {alias: {"bps_name": name, "reason": why} for alias, (name, why) in NAME_ALIASES.items()},
        "plausible_ranges": {check: {"range": list(PLAUSIBLE[check]), "measure": PLAUSIBLE_MEASURES[check]}
                             for check in PLAUSIBLE},
        "plausibility_compared": compared,
        "change_not_compared": change_not_compared,
        "flags": flags,
    },
}

# Layers 1, 2 and 6: check structure and completeness against the declared coverage, then write the CSV and metadata
raw_files = [RAW_PROVINCES, *RAW_BPS.values(), *[p for d in KEMNAKER for p in (RAW_DETAIL[d], RAW_XLSX[d])]]
out = cleaning.write_dataset(
    rows, KEYS, allowed={"province_code": codes, "indicator": [INDICATOR], "period": PERIODS},
    expected=expected, csv_path=OUT_CSV, meta=meta, raw_files=raw_files,
)

# Report what was written, every check result and every plausibility flag
print(f"{OUT_CSV.name}: {len(out)} rows, {len(flags)} plausibility flags")
print("  rows by source:", rows_by_source)
print("  years by source:", by_year_text)
for check in cross:
    print("  cross-source:", {k: check[k] for k in ("check", "compared", "tolerance", "largest_gap")},
          f"{len(check['differences'])} differences, declared {[d['key'] for d in check['declared_differences']]}")
print(f"  abstract figures: {len(abstracts['figures'])} checked")
print("  INDONESIA rows:", {y: (d["gap"], d["left_out"]) for y, d in national["years"].items()
                            if d["left_out"] or not d["matches"]})
print(f"  plausibility: values read {compared}")
for f in flags:
    print("  flag:", f)
