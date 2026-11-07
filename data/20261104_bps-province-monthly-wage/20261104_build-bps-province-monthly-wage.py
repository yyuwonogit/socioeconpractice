from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# Load the shared cleaning module from tools/
import sys
sys.path.insert(0, str(ROOT / "tools"))
import cleaning

# Modules for the raw JSON and for the page text: json reads the saved responses, re matches labels and notes
import json
import re

# Parameters

# Raw inputs, all saved by DOWNLOAD_SCRIPT. The BPS static tables of the average net monthly wage of employees by
# province and main occupation (Jenis Pekerjaan Utama), one per release, give every value of 2016-2024; WebAPI var 583,
# the same table, gives 2025 and repeats 2016 and 2024; the static tables by province and main industry (Lapangan
# Pekerjaan Utama) repeat each province's total and are read only as checks
RAW_PROVINCES = ROOT / "raw/province-codes/20261102_bps-province-codes-2025-s1.json"
RAW_DIR = ROOT / "raw/labour"
DOWNLOAD_SCRIPT = "raw/labour/20261104_download-bps-monthly-wage-and-minimum-wage-by-province.py"
STATIC_FILE = "20261104_bps-static-table-{id}-monthly-wage-by-province-and-{kind}-{period}.json"
API_FILE = "20261104_bps-api-var583-monthly-wage-by-province-and-occupation-{span}.json"

# Output; the metadata JSON is written beside it with a -metadata suffix
OUT_CSV = HERE / "20261104_bps-province-monthly-wage.csv"

# Key columns and the one indicator
KEYS = ["province_code", "indicator", "period"]
INDICATOR = "employee_net_wage_month"

# Sakernas rounds as the tables label them, each with its period suffix: Februari is the year's first round (S1) and
# Agustus its second (S2)
ROUNDS = {"Februari": "S1", "Agustus": "S2"}
ROUND_LABEL = re.compile(r"(Februari|Agustus) (\d{4})")

# The dataset keeps one round per year. Every year 2016-2025 has both rounds in the raw files, so either runs through
# the whole series; this build keeps Agustus (S2) in every year. The Februari values are read and cross-checked, never
# written; setting WRITTEN_ROUND to "S1" writes Februari instead
WRITTEN_ROUND = "S2"
YEARS = list(range(2016, 2026))
PERIODS = [f"{year}{WRITTEN_ROUND}" for year in YEARS]

# Codes of the parts each static table splits its total into, in column order, as its code row and its footnote 1)
# give them: eight main-occupation groups; nine main-industry sectors in 2017; 17 main-industry sectors, numbered in
# 2018-2019 and lettered from 2020
OCCUPATIONS = ["0/1", "2", "3", "4", "5", "6", "7/8/9", "X/00"]
SECTORS_9 = [str(n) for n in range(1, 10)]
SECTORS_17 = [str(n) for n in range(1, 18)]
SECTORS_17_LETTERED = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M,N", "O", "P", "Q", "R,S,T,U"]

# Number formats (mso-number-format) of the value cells, as the page styles write them
SPACED_1 = r'"#\ ###\ ##0"'
SPACED_2 = r'"###\ ###\ ##0"'
SPACED_3 = r'"###\ ###\ ###"'
SPACED_4 = r'"# ### ##0"'
SPACED_5 = r'"### ### ###"'
GROUPED_1 = r'"#,##0"'
GROUPED_2 = r'"#,###,##0"'
GROUPED_3 = r'"###,###,###"'
GROUPED_4 = r'"\#\#\#\,\#\#\#\,\#\#0"'
GROUPED_5 = r'"\#\#\#\,\#\#\#\,\#\#\#"'

# Every static table as opened: the breakdown of its parts, the period its file name and titles name, how many copies
# of one Excel page its data.table holds, the decimal and thousands separators its page style displays, and each round
# it holds, in column order, with the thousands separator its values are written with and the number formats of its
# value cells. No value has decimals. The space-grouped formats write literal spaces between digit groups, so a page
# whose style displays '.' still prints '2 225 539'; table 2190 displays ' ' as its thousands separator, so its "#,##0"
# cells print spaces too
STATIC = {
    1948: {"kind": "occupation", "period": "2016", "parts": OCCUPATIONS, "copies": 1, "style": (",", "."),
           "rounds": {"2016S1": (" ", {SPACED_2}), "2016S2": (" ", {SPACED_3})}},
    1988: {"kind": "occupation", "period": "2017", "parts": OCCUPATIONS, "copies": 1, "style": (",", "."),
           "rounds": {"2017S1": (" ", {SPACED_1}), "2017S2": (" ", {SPACED_1})}},
    2048: {"kind": "occupation", "period": "2018", "parts": OCCUPATIONS, "copies": 1, "style": (",", "."),
           "rounds": {"2018S1": (" ", {SPACED_1}), "2018S2": (" ", {SPACED_1})}},
    2070: {"kind": "occupation", "period": "2019", "parts": OCCUPATIONS, "copies": 1, "style": (",", "."),
           "rounds": {"2019S1": (" ", {SPACED_1}), "2019S2": (" ", {SPACED_1})}},
    2096: {"kind": "occupation", "period": "2020", "parts": OCCUPATIONS, "copies": 1, "style": (",", "."),
           "rounds": {"2020S1": (" ", {SPACED_1}), "2020S2": (" ", {SPACED_1, SPACED_2})}},
    2131: {"kind": "occupation", "period": "2021", "parts": OCCUPATIONS, "copies": 1, "style": (",", "."),
           "rounds": {"2021S1": (" ", {SPACED_1}), "2021S2": (" ", {SPACED_1})}},
    2190: {"kind": "occupation", "period": "2022-2023", "parts": OCCUPATIONS, "copies": 1, "style": (".", " "),
           "rounds": {"2022S1": (" ", {SPACED_1}), "2022S2": (" ", {SPACED_1}), "2023S1": (" ", {GROUPED_1})}},
    2233: {"kind": "occupation", "period": "2023", "parts": OCCUPATIONS, "copies": 1, "style": (",", "."),
           "rounds": {"2023S1": (" ", {SPACED_4, SPACED_5}), "2023S2": (".", {GROUPED_3})}},
    2255: {"kind": "occupation", "period": "2024", "parts": OCCUPATIONS, "copies": 2, "style": (",", "."),
           "rounds": {"2024S1": (".", {GROUPED_5}), "2024S2": (".", {GROUPED_5})}},
    1987: {"kind": "industry", "period": "2017", "parts": SECTORS_9, "copies": 1, "style": (",", "."),
           "rounds": {"2017S1": (" ", {SPACED_4}), "2017S2": (" ", {SPACED_4})}},
    2049: {"kind": "industry", "period": "2018", "parts": SECTORS_17, "copies": 1, "style": (",", "."),
           "rounds": {"2018S1": (" ", {SPACED_1}), "2018S2": (" ", {SPACED_1})}},
    2071: {"kind": "industry", "period": "2019", "parts": SECTORS_17, "copies": 1, "style": (",", "."),
           "rounds": {"2019S1": (" ", {SPACED_1}), "2019S2": (" ", {SPACED_1})}},
    2097: {"kind": "industry", "period": "2020", "parts": SECTORS_17_LETTERED, "copies": 1, "style": (",", "."),
           "rounds": {"2020S1": (" ", {SPACED_1}), "2020S2": (" ", {SPACED_1})}},
    2130: {"kind": "industry", "period": "2021", "parts": SECTORS_17_LETTERED, "copies": 1, "style": (",", "."),
           "rounds": {"2021S1": (" ", {SPACED_1}), "2021S2": (" ", {SPACED_1})}},
    2189: {"kind": "industry", "period": "2022", "parts": SECTORS_17_LETTERED, "copies": 1, "style": (",", "."),
           "rounds": {"2022S1": (" ", {SPACED_1}), "2022S2": (" ", {SPACED_1})}},
    2231: {"kind": "industry", "period": "2023", "parts": SECTORS_17_LETTERED, "copies": 1, "style": (",", "."),
           "rounds": {"2023S1": (" ", {SPACED_1, "0"}), "2023S2": (".", {GROUPED_2})}},
    2253: {"kind": "industry", "period": "2024", "parts": SECTORS_17_LETTERED, "copies": 1, "style": (",", "."),
           "rounds": {"2024S1": (".", {GROUPED_4}), "2024S2": (".", {GROUPED_4})}},
}
INDUSTRY_TABLES = [t for t, spec in STATIC.items() if spec["kind"] == "industry"]

# The occupation table that gives each year's values: the one whose title names that year alone, apart from 2022,
# whose table 2190 is titled 2022-2023 and adds Februari 2023 (table 2233, titled 2023, holds both rounds of 2023)
PRIMARY_TABLE = {2016: 1948, 2017: 1988, 2018: 2048, 2019: 2070, 2020: 2096, 2021: 2131, 2022: 2190, 2023: 2233,
                 2024: 2255}

# Text every static table must carry, compared as lower-case letters and digits only, since BPS writes 'Upah/Gaji'
# and 'UpahGaji' in different years: the series and breakdown in both titles, the workers covered, and the unit in the
# page title. The page title of table 1948 names 'Pekerja Formal' (formal workers) where its catalogue title and every
# other table name 'Buruh/Karyawan/Pegawai' (employees); checks.cross_source shows var 583, titled for employees,
# repeats all its cells
TITLE_WORDS = {"occupation": ["upahgajibersihsebulan", "menurutprovinsidanjenispekerjaanutama"],
               "industry": ["upahgajibersihsebulan", "menurutprovinsidanlapanganpekerjaanutama"]}
WORKERS = "buruhkaryawanpegawai"
PAGE_WORKERS = {1948: "pekerjaformal"}
UNIT_TEXT = "(rupiah)"

# Labels of the table layout: the rows above the header name the area and sex covered (urban and rural areas, men and
# women together); the header row starts with 'Provinsi', each round's parts end in its 'Jumlah' (total) column, the
# row under the round labels names the breakdown, and the notes start with 'Catatan:'
AREA_TEXT = "Perkotaan+Perdesaan"
SEX_TEXT = "Laki-laki+Perempuan"
HEADER_TEXT = "Provinsi"
TOTAL_TEXT = "Jumlah"
BREAKDOWN_TEXT = {"occupation": "Jenis Pekerjaan Utama 1)", "industry": "Lapangan Pekerjaan Utama 1)"}
NOTES_TEXT = "Catatan:"

# Markers a part cell may carry instead of a number, with the meaning the tables' legends give: 'NA' is 'data tidak
# dapat ditampilkan' (cannot be shown; table 2131's legend says 'Not applicable', and table 1948 uses it without a
# legend line) and '-' is 'Tidak ada atau nol' (none or zero). No total (Jumlah) cell carries a marker in any table
MARKERS = {"NA": "data tidak dapat ditampilkan (cannot be shown)", "-": "Tidak ada atau nol (none or zero)"}

# Note lines: a footnote 1) line gives a part code and its name, the first carrying the marker '1)'; a legend line
# gives a marker and its meaning
FOOTNOTE_LINE = re.compile(r"(?P<marker>1\)\s*)?(?P<code>X/00|\d+(?:/\d+)*|[A-Z](?:,[A-Z])*)\.?\s+(?P<name>\S.*)")
LEGEND_LINE = re.compile(r"(?P<marker>NA|-):?\s+(?P<meaning>\S.*)")

# Text in note rows outside the notes, each in a cell of its own, kept out of the notes as published: table 2130 writes
# '&nbspnbsp;' in a cell of its first footnote row, and table 2255 writes 'hb' beside footnote 3
STRAY = {2130: ["\xa0nbsp;"], 2255: ["hb"]}

# Tags allowed inside cells: a named anchor around the title, rich-text font runs and superscript footnote markers in
# header and note cells. Excel also wraps text that overflows into a filled neighbour cell in a hidden span, which
# cleaning.excel_grid reads as part of its cell's text when given HIDDEN_STYLE. A value or region cell may hold none
# of them
INLINE = {"a": {"name"}, "font": {"class"}, "sup": set()}
HIDDEN_STYLE = "display:none"

# Padding spans may hold HTML white space beside no-break spaces (cleaning.excel_grid's padding_space): Excel wraps long
# source lines inside padding spans, and tables 2096, 2097, 2130, 2131, 2189 and 2231 pad with spaces where the others
# use no-break spaces
PADDING_SPACE = True

# WebAPI var 583 as opened: its label, unit, region list, the eight occupation turvars with the footnote 1) code each
# label names (checked by name), the total turvar, and the sub-periods (turtahun), of which Tahunan holds no value
API_VAR = 583
API_SPANS = {"2016-2016": [2016], "2024-2025": [2024, 2025]}
API_LABEL = "Rata-rata Upah/Gaji Bersih Sebulan Buruh/Karyawan/Pegawai Menurut Provinsi dan Jenis Pekerjaan Utama"
API_UNIT = "Rupiah"
API_REGIONS = "Provinsi dg Rata2"
API_PARTS = {744: "0/1", 745: "2", 746: "3", 747: "4", 748: "5", 749: "6", 750: "7/8/9", 751: "X/00"}
API_TOTAL = (752, "Jumlah")
API_SUB_PERIODS = {189: "Februari", 190: "Agustus", 191: "Tahunan"}

# Region names the BPS province list lacks: the last row of every table holds the national average, labelled
# 'Rata-rata' (average) in the static tables and 'RATA-RATA' under vervar 9999 (the WebAPI code for Indonesia) in var
# 583, whose region list is named 'Provinsi dg Rata2' (provinces with the average)
NAME_ALIASES = {"RATA-RATA": cleaning.NATIONAL_CODE}

# First year of each province whose own values start after 2016, read from opening the files: the four provinces split
# from Papua Barat (91) and Papua (94) in 2022 have rows from 2024 in tables 2253 and 2255 and values from 2024 in var
# 583, whose 2016 file lists them without values. Kalimantan Utara (65) has its own row in every table from 2016
FIRST_YEAR = {"92": 2024, "95": 2024, "96": 2024, "97": 2024}
PARENT = {"92": "91", "95": "94", "96": "94", "97": "94"}

# Changes from the year before that compare different areas, which the change checks leave out
BORDER_CHANGES = {
    ("91", "2024"): "Papua Barat: 2023 includes Papua Barat Daya, 2024 does not",
    ("94", "2024"): "Papua: 2023 includes Papua Selatan, Papua Tengah and Papua Pegunungan, 2024 does not",
}

# Tolerance of every cross-source comparison, in rupiah: the copies are the same published whole-rupiah figures
TOL_CROSS = 0

# Plausibility ranges; a value outside its range is flagged, not dropped
PLAUSIBLE = {
    "wage_rupiah": (1_000_000, 8_000_000),   # every value, rupiah per employee per month
    "wage_change_pct": (-10, 20),            # value in year t / value in year t-1 x 100 - 100, same round
}
PLAUSIBLE_MEASURES = {
    "wage_rupiah": "every value in the CSV, rupiah per month",
    "wage_change_pct": "each value against the same round of the year before, (value t / value t-1 - 1) x 100, apart "
                       "from the changes across a border change (checks.change_not_compared)",
}

# A further plausibility check, read over every source and both rounds: two survey rounds that give one region the same
# average to the rupiah while the averages of its parts differ point to a cell copied from the other round
REPEAT_CHECK = "total_same_in_both_rounds"
REPEAT_MEASURE = ("in each source, every region and year with both rounds: the Februari and Agustus totals (Jumlah) "
                  "are equal to the rupiah; each flag counts the parts whose values differ between the two rounds")

# Where the raw files come from; each WebAPI request ends in /key/ and a registered key, which is not stored
URL_PROVINCES = "https://sig.bps.go.id/rest-bridging/getwilayah?level=provinsi&periode_merge=2025_1.2025"
URL_STATIC = "https://webapi.bps.go.id/v1/api/view/domain/0000/model/statictable/lang/ind/id/{id}/key/<key>/"
URL_API = ("https://webapi.bps.go.id/v1/api/list/model/data/domain/0000/var/583/th/{th}/key/<key> (th = years minus "
           "1900, separated by ';')")

# Paths of the raw files
STATIC_PATHS = {t: RAW_DIR / STATIC_FILE.format(id=t, kind=s["kind"], period=s["period"]) for t, s in STATIC.items()}
API_PATHS = {span: RAW_DIR / API_FILE.format(span=span) for span in API_SPANS}

# How each raw file is written, read from opening all 20 files. The province list is UTF-8 JSON of 38 records whose
# fields are all text. Each static table is UTF-8 JSON without a byte-order mark whose data.table is an Excel-made HTML
# page (Publish as Web Page; table 2255 holds the page twice, identical): its style displays the decimal and thousands
# separators STATIC gives, every value is a whole number of rupiah written as text with its round's thousands separator,
# a part cell without a value holds a MARKERS marker, the unit is '(rupiah)' in the page title, and cells may carry
# INLINE markup and hidden overflow spans. Each var 583 file is UTF-8 JSON without a byte-order mark whose values are
# JSON integers, whose decimal field is null, and in which a value BPS does not show is a key absent from datacontent
READ_CONTEXT = {
    RAW_PROVINCES: {"encoding": "utf-8", "numbers": "none: every code and name is a JSON string"},
    **{STATIC_PATHS[t]: {
        "encoding": "utf-8",
        "layout": f"JSON; data.table holds {s['copies']} identical cop{'y' if s['copies'] == 1 else 'ies'} of an "
                  f"Excel-made HTML page",
        "decimal": s["style"][0],
        "style_thousands": s["style"][1],
        "decimals": 0,
        "thousands": {period: sep for period, (sep, _) in s["rounds"].items()},
        "number_formats": {period: sorted(formats) for period, (_, formats) in s["rounds"].items()},
        "missing": MARKERS,
        "unit_text": UNIT_TEXT,
        "inline": {tag: sorted(attrs) for tag, attrs in INLINE.items()},
        "hidden": HIDDEN_STYLE,
    } for t, s in STATIC.items()},
    **{API_PATHS[span]: {
        "encoding": "utf-8", "var": API_VAR, "unit": API_UNIT, "decimals": None,
        "numbers": "JSON integers: no decimal point, no thousands separator",
        "missing": "key absent from datacontent",
    } for span in API_SPANS},
}


# Functions

def letters(text):
    """Keep only the lower-case letters and digits of a title, since BPS titles vary in spaces and punctuation."""
    return re.sub(r"[^0-9a-z]", "", (text or "").lower())


def posix(path):
    """Return a path relative to the repository root with forward slashes, for the metadata fields that name files."""
    return Path(path).resolve().relative_to(ROOT).as_posix()


def regions_in(year, codes):
    """Return the codes with their own values in a year: Indonesia and every province split off by then."""
    return [code for code in codes if year >= FIRST_YEAR.get(code, YEARS[0])]


def page_copies(page, name):
    """Split a data.table string into the Excel pages it holds, each from its <html> tag (with a doctype before it),
    and stop if anything comes before the first page."""
    starts = [m.start() for m in re.finditer(r"(?:<!DOCTYPE[^>]*>\s*)?<html\b", page, re.I)]
    if not starts or page[:starts[0]].strip():
        raise ValueError(f"{name}: data.table does not start with an HTML page")
    return [page[a:b] for a, b in zip(starts, starts[1:] + [len(page)])]


def style_separators(page, name):
    """Return the (decimal, thousands) separators an Excel page's style displays, without Excel's escaping."""
    found = {kind: [v.replace("\\", "") for v in values] for kind in ("decimal", "thousand")
             for values in [re.findall(rf'mso-displayed-{kind}-separator:"([^"]*)";', page)]}
    if any(len(set(v)) != 1 for v in found.values()):
        raise ValueError(f"{name}: the style displays separators {found}")
    return found["decimal"][0], found["thousand"][0]


def check_title(title, spec, workers, where):
    """Stop unless a title names the series, the breakdown, the workers it covers and, at its end, the file's period."""
    flat = letters(title)
    for word in TITLE_WORDS[spec["kind"]] + [workers]:
        if word not in flat:
            raise ValueError(f"{where}: {title!r} does not name {word!r}")
    if not flat.endswith(letters(spec["period"])):
        raise ValueError(f"{where}: {title!r} does not end with the period {spec['period']}")


def header_blocks(grid, header, spec, name):
    """Read the round blocks of a static table's header: each round label starts a block of part columns that runs up
    to its 'Jumlah' column, as the code row under it confirms. Returns {period: (part columns, total column)} in column
    order, and the empty columns outside every block.

    A slot inside a block is covered by its round label or left empty (table 2049 spans 'Agustus 2018' over 9 of its
    17 columns); the classification row names the breakdown over each block; the code row gives the declared part
    codes; and the column-number row holds only numbers in brackets.
    """
    row = grid[header]
    blocks, spacers, current = {}, [], None
    for j in range(1, len(row)):
        text, cell, own = row[j]
        if j == 1 and text == HEADER_TEXT and not own:
            continue
        label = ROUND_LABEL.fullmatch(text) if own else None
        if label:
            if current is not None:
                raise ValueError(f"{name}: round {text!r} starts inside the block of {current[0]}")
            current = (f"{label.group(2)}{ROUNDS[label.group(1)]}", j)
        elif own and text == TOTAL_TEXT:
            if current is None or cell["rowspan"] != 3:
                raise ValueError(f"{name}: a 'Jumlah' column at {j} closes no round or is not three rows high")
            period, start = current
            blocks[period] = (list(range(start, j)), j)
            current = None
        elif text and not (current and not own and row[current[1]][1] is cell):
            raise ValueError(f"{name}: header column {j} holds {text!r}")
        elif not text and current is None:
            spacers.append(j)
    if current is not None or list(blocks) != list(spec["rounds"]):
        raise ValueError(f"{name}: the header holds rounds {list(blocks)}, expected {list(spec['rounds'])}")

    # Under each block: the breakdown label, the part codes, and the column numbers
    breakdown, codes, numbers = grid[header + 1], grid[header + 2], grid[header + 3]
    for period, (parts, total) in blocks.items():
        if breakdown[parts[0]][0] != BREAKDOWN_TEXT[spec["kind"]] or any(
                breakdown[j][0] not in ("", BREAKDOWN_TEXT[spec["kind"]]) for j in parts):
            raise ValueError(f"{name}: {period} is not headed {BREAKDOWN_TEXT[spec['kind']]!r}")
        if [codes[j][0] for j in parts] != spec["parts"] or not all(codes[j][2] for j in parts):
            raise ValueError(f"{name}: {period} has codes {[codes[j][0] for j in parts]}, expected {spec['parts']}")
        if any(grid[header + k][total][1] is not row[total][1] for k in (1, 2)):
            raise ValueError(f"{name}: the 'Jumlah' column of {period} does not span the three header rows")
    if not all(re.fullmatch(r"\(\d+\)", t) for t in cleaning.excel_own_texts(numbers)):
        raise ValueError(f"{name}: the column-number row holds {cleaning.excel_own_texts(numbers)}")

    # Columns outside every block must be empty in the three rows under the header
    for j in spacers:
        if any(grid[header + k][j][0] for k in (1, 2, 3)):
            raise ValueError(f"{name}: column {j} lies outside every round but holds text")
    return blocks, spacers


def read_value(text, cell, formats, context, period, where, markers):
    """Parse one value cell: a whole number of rupiah in its round's declared format, or, when markers is given, one
    of those markers. Returns the number or the marker."""
    if not text or cell["inline"] or cell["colspan"] != 1 or cell["rowspan"] != 1:
        raise ValueError(f"{where}: an empty, merged or marked-up value cell {text!r} ({cell['inline']})")
    if formats.get(cell["class"]) not in context["number_formats"][period]:
        raise ValueError(f"{where}: number format {formats.get(cell['class'])!r} is not declared for {period}")
    if markers and text in markers:
        return text
    # Padding belongs in a padding span; white space outside one is not the declared format
    if text != text.strip(" \xa0"):
        raise ValueError(f"{where}: white space outside a padding span in {text!r}")
    try:
        return cleaning.parse_number(text, context["decimal"], context["thousands"][period], context["decimals"])
    except ValueError as e:
        raise ValueError(f"{where}: {e}") from None


def read_notes(grid, start, table_id, spec, name):
    """Read a static table's notes, from the 'Catatan:' row to the end of the page: the note lines as published, the
    footnote 1) list of part codes and names, the legend of markers, and the declared stray texts left out of them.

    Every line after 'Catatan:' must be a footnote line or a legend line, the footnote codes must be the header's part
    codes in order, and each declared stray text must sit alone in a cell exactly once.
    """
    stray, found, lines = STRAY.get(table_id, []), [], []
    for row in grid[start:]:
        texts = cleaning.excel_own_texts(row)
        found += [t for t in texts if t in stray]
        texts = [t for t in texts if t not in stray]
        if texts:
            lines.append(" ".join(texts))
    if sorted(found) != sorted(stray):
        raise ValueError(f"{name}: stray texts {found}, declared {stray}")
    if lines[0] != NOTES_TEXT:
        raise ValueError(f"{name}: the notes start with {lines[0]!r}")

    # Footnote 1) lines first, the first carrying the marker, then the legend lines
    classification, legend = {}, {}
    for line in lines[1:]:
        footnote, marker = FOOTNOTE_LINE.fullmatch(line), LEGEND_LINE.fullmatch(line)
        if footnote and not legend and (classification or footnote.group("marker")):
            classification[footnote.group("code")] = footnote.group("name")
        elif marker:
            legend[marker.group("marker")] = marker.group("meaning")
        else:
            raise ValueError(f"{name}: note line {line!r} is neither a footnote 1) line nor a legend line")
    if list(classification) != spec["parts"]:
        raise ValueError(f"{name}: footnote 1) lists {list(classification)}, the header {spec['parts']}")

    # The notes must give no revision status, so every value is final
    if cleaning.parse_status_note("\n".join(lines)) != {}:
        raise ValueError(f"{name}: the notes now give revision statuses: {lines}")
    return {"notes_as_published": lines, "footnote_1": classification, "legend": legend, "stray_texts": found}


def read_static(table_id, lookup, codes):
    """Read one static table: its description, the total (Jumlah) of every region and round, and the parts of each.

    Rows are matched by what they say: the title row by the title, the area and sex rows by their labels, the header
    by 'Provinsi', the data rows by region name up to 'Catatan:', and the notes after it. Returns (info, totals, parts):
    totals maps (code, period) to rupiah, and parts maps (code, period) to {part code: rupiah or marker}.
    """
    spec, path = STATIC[table_id], STATIC_PATHS[table_id]
    context = READ_CONTEXT[path]
    reply = json.loads(path.read_text(encoding=context["encoding"]))
    data = reply.get("data") or {}
    if reply.get("status") != "OK" or reply.get("data-availability") != "available" or data.get("table_id") != table_id:
        raise ValueError(f"{path.name}: not static table {table_id} ({reply.get('status')}, {data.get('table_id')})")

    # The catalogue title must name the series, the breakdown, employees and the period
    title = " ".join(data["title"].split())
    check_title(title, spec, WORKERS, f"{path.name} title")

    # data.table must hold the declared copies of one Excel page, all identical; the first is read
    copies = page_copies(data["table"], path.name)
    if len(copies) != spec["copies"] or any(c != copies[0] for c in copies):
        raise ValueError(f"{path.name}: {len(copies)} pages, expected {spec['copies']} identical ones")
    page = copies[0]

    # The style must display the declared separators, and each value cell's class must set a declared number format
    style = style_separators(page, path.name)
    if style != spec["style"]:
        raise ValueError(f"{path.name}: the style displays {style}, declared {spec['style']}")
    formats = cleaning.excel_number_formats(page)
    grid = cleaning.excel_grid(page, INLINE, hidden=HIDDEN_STYLE, padding_space=PADDING_SPACE)

    # The first row with text holds only the page title, which must name the series, the workers, the unit and period
    filled = [i for i, row in enumerate(grid) if cleaning.excel_own_texts(row)]
    title_row = filled[0]
    page_title = cleaning.excel_own_texts(grid[title_row])
    if len(page_title) != 1:
        raise ValueError(f"{path.name}: the first row holds {page_title}")
    page_title = page_title[0]
    check_title(page_title, spec, PAGE_WORKERS.get(table_id, WORKERS), f"{path.name} page title")
    cleaning.require_text(page_title.lower(), context["unit_text"], f"{path.name} page title")

    # The header row starts with 'Provinsi' three rows high, and the rows above it name the area and sex covered
    header = next((i for i, row in enumerate(grid) if row[0][0] == HEADER_TEXT and row[0][2]), None)
    if header is None or grid[header][0][1]["rowspan"] != 3:
        raise ValueError(f"{path.name}: no '{HEADER_TEXT}' header three rows high")
    above = [t for row in grid[title_row + 1:header] for t in cleaning.excel_own_texts(row)]
    if sorted(above) != sorted([AREA_TEXT, SEX_TEXT]):
        raise ValueError(f"{path.name}: the rows above the header hold {above}")
    blocks, spacers = header_blocks(grid, header, spec, path.name)

    # The notes start at the first 'Catatan:' row after the header
    notes_row = next((i for i in range(header + 4, len(grid)) if grid[i][0][0] == NOTES_TEXT and grid[i][0][2]), None)
    if notes_row is None:
        raise ValueError(f"{path.name}: no '{NOTES_TEXT}' row")

    # Data rows: every row with text between the header and the notes names a region in its first cell
    totals, parts, names, markers = {}, {}, {}, {}
    value_columns = {j for cols, total in blocks.values() for j in cols + [total]}
    for i in range(header + 4, notes_row):
        row = grid[i]
        if not cleaning.excel_own_texts(row):
            continue
        name_text, name_cell, name_own = row[0]
        if not name_own or name_cell["inline"] or not name_text:
            raise ValueError(f"{path.name}: row {i} does not start with a region name: {row[0][0]!r}")
        code = cleaning.province_code(name_text, lookup)
        if code in names:
            raise ValueError(f"{path.name}: {name_text!r} and {names[code]!r} both map to {code}")
        names[code] = name_text

        # Nothing may sit outside the region cell and the value columns
        stray = [(j, t) for j, (t, c, own) in enumerate(row)
                 if own and t and j not in value_columns and c is not name_cell]
        if stray:
            raise ValueError(f"{path.name}: {name_text} has text outside the value columns: {stray}")

        # Each round's parts are numbers or markers, and its total is a number, in the round's declared format
        for period, (columns, total) in blocks.items():
            where = f"{path.name} {name_text} {period}"
            text, cell, _ = row[total]
            totals[(code, period)] = read_value(text, cell, formats, context, period, f"{where} Jumlah", None)
            parts[(code, period)] = {}
            for part, j in zip(spec["parts"], columns):
                text, cell, _ = row[j]
                value = read_value(text, cell, formats, context, period, f"{where} {part}", context["missing"])
                parts[(code, period)][part] = value
                if isinstance(value, str):
                    markers[value] = markers.get(value, 0) + 1

    # Every region with its own values in each round's year must have its row, and no other region
    expected = {frozenset(regions_in(int(period[:4]), codes)) for period in blocks}
    if len(expected) != 1 or set(names) != set(expected.pop()):
        raise ValueError(f"{path.name}: rows for {sorted(names)}, expected the regions of {list(blocks)}")

    # The notes, read on purpose: footnote 1) names the parts, the legend the markers
    notes = read_notes(grid, notes_row, table_id, spec, path.name)
    info = {
        "file": posix(path), "url": URL_STATIC.format(id=table_id), "kind": spec["kind"],
        "title": title, "page_title": page_title, "subject": data.get("subcsa"), "created": data.get("cr_date"),
        "updated": data.get("updt_date"), "rounds": list(blocks), "regions": len(names),
        "copies_of_the_page": spec["copies"], "area_and_sex": [AREA_TEXT, SEX_TEXT], **notes,
        "markers_in_part_cells": dict(sorted(markers.items())),
        "hidden_overflow_cells": sum(1 for row in grid for _, c, own in row if own and "span" in c["inline"]),
        "empty_columns_between_rounds": spacers,
    }
    return info, totals, parts


def read_api(span, lookup, codes):
    """Read one var 583 file: its description and {(code, period, turvar): rupiah}, after checking it is the declared
    table, years, regions, turvars and sub-periods, and that every value is a JSON integer."""
    path, context = API_PATHS[span], READ_CONTEXT[API_PATHS[span]]

    # read_webapi_table reads JSON numbers and treats an absent key as no value, the conventions declared for var 583
    table, records = cleaning.read_webapi_table(path, var=context["var"], unit=context["unit"],
                                                decimals=context["decimals"], encoding=context["encoding"])
    raw = json.loads(path.read_text(encoding=context["encoding"]))["datacontent"]
    if any(type(v) is not int for v in raw.values()):
        raise ValueError(f"{path.name}: a datacontent value is not a JSON integer")

    # The file must hold the declared table, years, regions, turvars and sub-periods
    var = table["var"][0]
    if " ".join(var["label"].split()) != API_LABEL or table["labelvervar"] != API_REGIONS:
        raise ValueError(f"{path.name}: var label {var['label']!r}, region list {table['labelvervar']!r}")
    if [int(t["label"]) for t in table["tahun"]] != API_SPANS[span]:
        raise ValueError(f"{path.name}: years {[t['label'] for t in table['tahun']]}, expected {API_SPANS[span]}")
    turvars = {t["val"]: t["label"] for t in table["turvar"]}
    if sorted(turvars) != sorted(list(API_PARTS) + [API_TOTAL[0]]) or turvars[API_TOTAL[0]] != API_TOTAL[1]:
        raise ValueError(f"{path.name}: turvars {turvars}")
    if {t["val"]: t["label"] for t in table["turtahun"]} != API_SUB_PERIODS:
        raise ValueError(f"{path.name}: sub-periods {table['turtahun']}")
    listed = [cleaning.webapi_region_code(v["val"], v["label"], lookup) for v in table["vervar"]]
    if sorted(listed) != sorted(codes):
        raise ValueError(f"{path.name}: regions {listed}")

    # One value per region, round and turvar; Tahunan holds no value
    values = {}
    for r in records:
        sub = API_SUB_PERIODS[r["turtahun"]]
        if sub not in ROUNDS:
            raise ValueError(f"{path.name}: {sub} now holds a value ({r})")
        code = cleaning.webapi_region_code(r["vervar"], r["vervar_label"], lookup)
        values[(code, f"{r['year']}{ROUNDS[sub]}", r["turvar"])] = r["value"]

    # Every region with its own values that year has a total in both rounds, and no other region has a value
    for year in API_SPANS[span]:
        for suffix in ROUNDS.values():
            held = {c for (c, p, t) in values if p == f"{year}{suffix}" and t == API_TOTAL[0]}
            other = {c for (c, p, t) in values if p == f"{year}{suffix}"}
            if held != set(regions_in(year, codes)) or other != held:
                raise ValueError(f"{path.name}: {year}{suffix} totals for {sorted(held)}")
    return table, values


def within_parts(totals, parts, source, label):
    """Layer 3: a total is the average over all its parts' employees, so it must lie between the lowest and highest
    part average. Where every part is published, or shown as '-' (none), the bound is exact and a total outside it
    stops the build; where a part is not shown ('NA', or absent from var 583), the hidden part could pull the total
    outside the published range, so such a total outside it is flagged instead."""
    exact = partial = 0
    flags = []
    for key, total in sorted(totals.items()):
        published = [v for v in parts[key].values() if not isinstance(v, str)]
        hidden = sum(1 for v in parts[key].values() if v == "NA")
        if not published:
            raise ValueError(f"{label}: {key} has no published part to bound its total")
        low, high = min(published), max(published)
        if hidden:
            partial += 1
        else:
            exact += 1
        if not low <= total <= high:
            if not hidden:
                raise ValueError(f"{label}: total {total} at {key} lies outside its parts' range {low}-{high}")
            flags.append({"check": "total_within_parts", "source": source, "province_code": key[0],
                          "period": key[1], "value": total, "range": [low, high], "parts_not_shown": hidden})
    return {"check": label, "compared": exact + partial, "exact_bound": exact, "some_parts_not_shown": partial,
            "flagged": len(flags)}, flags


def compare(first, second, label, first_name, second_name):
    """Layer 4: two sources must hold the same keys and the same values within TOL_CROSS; returns the summary with
    every difference."""
    if set(first) != set(second):
        raise ValueError(f"{label}: keys differ: {sorted(set(first) ^ set(second))[:10]}")
    ordered = {k: first[k] for k in sorted(first)}
    result = cleaning.compare_sources(ordered, second, TOL_CROSS, label)
    result.update({"first": first_name, "second": second_name, "keys": "[province_code, period]"})
    return result


def compare_cells(table_id, parts, totals, api, part_names, turvar_names):
    """Layer 4: every cell of a static table against var 583, parts and total alike. A number must equal var 583's
    value exactly, and a part shown 'NA' must be a key var 583 leaves out (its note: an empty cell has RSE of 50% or
    more). The part codes are matched to turvars by name, which must agree with API_PARTS."""
    by_name = {letters(name): turvar for turvar, name in turvar_names.items()}
    matched = {code: by_name.get(letters(name)) for code, name in part_names.items()}
    if matched != {code: turvar for turvar, code in API_PARTS.items()}:
        raise ValueError(f"table {table_id}: footnote 1) names match var 583 turvars as {matched}")
    equal = absent = 0
    for (code, period), cells in sorted(parts.items()):
        for part, value in [*cells.items(), (API_TOTAL[1], totals[(code, period)])]:
            turvar = matched.get(part, API_TOTAL[0])
            other = api.get((code, period, turvar))
            if value == "NA" and other is None:
                absent += 1
            elif isinstance(value, float) and other == value:
                equal += 1
            else:
                raise ValueError(f"table {table_id} {code} {period} {part}: {value!r}, var 583 {other!r}")
    held = {(c, p, t) for (c, p, t) in api if p in {p for _, p in parts}}
    if len(held) != equal:
        raise ValueError(f"table {table_id}: var 583 holds {len(held)} cells of its rounds, {equal} matched")
    return {"check": f"every cell of static table {table_id} (eight occupations and Jumlah, both rounds) equals var "
                     f"{API_VAR}", "cells": equal + absent, "equal": equal, "na_cells_absent_from_var_583": absent,
            "differences": [], "part_turvars": {code: turvar for code, turvar in matched.items()}}


def change_rows(values):
    """Return the change (%) from the same round of the year before for every region with both values, apart from the
    changes across a border change, which compare different areas and are listed with their reason instead."""
    changes, skipped = [], []
    for (code, period), now in sorted(values.items()):
        before_period = f"{int(period[:4]) - 1}{period[4:]}"
        before = values.get((code, before_period))
        if before is None:
            continue
        if (code, period[:4]) in BORDER_CHANGES:
            skipped.append({"province_code": code, "period": period, "reason": BORDER_CHANGES[(code, period[:4])]})
            continue
        changes.append({"province_code": code, "period": period, "from_period": before_period,
                        "rupiah": {before_period: before, period: now}, "value": 100 * (now / before - 1)})
    if len(skipped) != len(BORDER_CHANGES):
        raise ValueError(f"border changes declared but not in the values: {skipped}")
    return changes, skipped


def plausibility(values):
    """Layer 5: every value and every change from the year before against its stated range. Returns the flags, how
    many values each check read, and the changes left out at border changes."""
    changes, skipped = change_rows(values)
    read = {"wage_rupiah": [{"province_code": c, "period": p, "value": v} for (c, p), v in sorted(values.items())],
            "wage_change_pct": changes}
    flags = [f for check, rows in read.items() for f in cleaning.flag_outside(rows, check, *PLAUSIBLE[check])]
    return flags, {check: len(rows) for check, rows in read.items()}, skipped


def repeated_totals(sources):
    """Layer 5: flag every region and year whose Februari and Agustus totals are equal to the rupiah in one source,
    with how many of its parts differ between the two rounds. Returns the flags and how many pairs were compared."""
    flags, compared = [], 0
    for name, totals, parts in sources:
        for (code, period), total in sorted(totals.items()):
            other = (code, f"{period[:4]}{ROUNDS['Februari']}")
            if not period.endswith(ROUNDS["Agustus"]) or other not in totals:
                continue
            compared += 1
            if totals[other] == total:
                mine, theirs = parts[(code, period)], parts[other]
                flags.append({"check": REPEAT_CHECK, "source": name, "province_code": code, "period": period,
                              "other_period": other[1], "value": total, "parts": len(mine),
                              "parts_differing": sum(1 for p in mine if mine[p] != theirs[p])})
    return flags, compared


def repeat_note(flag, values, provinces, source_of_period):
    """Describe one total repeated across the two rounds of a year for the metadata notes, saying whether the CSV
    holds it."""
    code, period = flag["province_code"], flag["period"]
    written = values.get((code, period)) == flag["value"] and source_of_period.get(period) == flag["source"]
    return (f"{code} ({provinces[code]['name']}) {period[:4]} in {flag['source']}: the Februari and Agustus totals are "
            f"both {flag['value']:,.0f} rupiah while {flag['parts_differing']} of its {flag['parts']} parts differ "
            f"between the rounds, which points to a cell copied from one round to the other. "
            f"{'The CSV holds it as ' + period if written else 'The CSV does not hold it'}; it is kept as published "
            f"and flagged (checks.flags).")


def describe_api(table, span):
    """Describe one var 583 file for the metadata."""
    var = table["var"][0]
    return {"file": posix(API_PATHS[span]), "years": API_SPANS[span], "label": " ".join(var["label"].split()),
            "subject": var.get("subj"), "unit": var["unit"], "decimal": var["decimal"],
            "regions": table["labelvervar"], "turvar": {str(t["val"]): t["label"] for t in table["turvar"]},
            "turtahun": {str(t["val"]): t["label"] for t in table["turtahun"]}, "last_update": table["last_update"]}


# Steps

# Print in UTF-8 so BPS labels and markers show on any console
sys.stdout.reconfigure(encoding="utf-8")

# Read the BPS province list that every region name is matched against; load_bps_provinces reads UTF-8, so a list
# declared in another encoding stops the build. The national-average label is added as a declared alias
if READ_CONTEXT[RAW_PROVINCES]["encoding"] != "utf-8":
    raise ValueError(f"{RAW_PROVINCES.name} is declared {READ_CONTEXT[RAW_PROVINCES]}, but is read as UTF-8")
provinces, lookup = cleaning.load_bps_provinces(RAW_PROVINCES)
lookup = {**lookup, **NAME_ALIASES}
codes = list(provinces)

# Stop unless the download script the metadata names is in the repository, and raw/labour holds exactly the declared
# wage tables
if not (ROOT / DOWNLOAD_SCRIPT).is_file():
    raise FileNotFoundError(f"download script {DOWNLOAD_SCRIPT} not found")
for pattern, declared in (("20261104_bps-static-table-*-monthly-wage-*.json", STATIC_PATHS.values()),
                          ("20261104_bps-api-var583-*.json", API_PATHS.values())):
    found = sorted(RAW_DIR.glob(pattern))
    if found != sorted(declared):
        raise ValueError(f"raw/labour holds {[p.name for p in found]}, declared {[p.name for p in declared]}")

# Read every static table: its description, each region's total in each round, and the parts of each total
static_info, static_totals, static_parts = {}, {}, {}
for table_id in STATIC:
    static_info[table_id], static_totals[table_id], static_parts[table_id] = read_static(table_id, lookup, codes)

# Read var 583: its two files must come from one release with one note, which gives no revision status
api_tables, api = {}, {}
for span in API_SPANS:
    api_tables[span], cells = read_api(span, lookup, codes)
    api.update(cells)
api_first, api_second = api_tables.values()
if api_first["var"] != api_second["var"] or api_first["last_update"] != api_second["last_update"]:
    raise ValueError("the two var 583 files differ in their description or release")
api_note = cleaning.html_to_text(api_first["var"][0]["note"])
if cleaning.parse_status_note(api_first["var"][0]["note"]) != {}:
    raise ValueError("the var 583 note now gives revision statuses")
api_totals = {(c, p): v for (c, p, t), v in api.items() if t == API_TOTAL[0]}
api_parts = {}
for (c, p, t), v in api.items():
    api_parts.setdefault((c, p), {code: "NA" for code in API_PARTS.values()})
    if t != API_TOTAL[0]:
        api_parts[(c, p)][API_PARTS[t]] = v

# The values written: each year's Agustus total from its occupation table, and 2025's from var 583
values = {}
for year in YEARS:
    period = f"{year}{WRITTEN_ROUND}"
    source = static_totals[PRIMARY_TABLE[year]] if year in PRIMARY_TABLE else api_totals
    values.update({key: v for key, v in source.items() if key[1] == period})
rows = [{"province_code": c, "indicator": INDICATOR, "period": p, "status": "", "value": v}
        for (c, p), v in sorted(values.items())]

# Layer 3: every total, of every table and round, lies within its parts' range; stops where the bound is exact
identities, range_flags = [], []
for table_id in STATIC:
    check, flags = within_parts(static_totals[table_id], static_parts[table_id], f"static table {table_id}",
                                f"static table {table_id}: Jumlah lies within its parts' range, every region and round")
    identities.append(check)
    range_flags += flags
for span in API_SPANS:
    held = {k: v for k, v in api_totals.items() if int(k[1][:4]) in API_SPANS[span]}
    check, flags = within_parts(held, api_parts, f"var {API_VAR}", f"var {API_VAR} {span}: Jumlah (turvar "
                                f"{API_TOTAL[0]}) lies within its parts' range, every region and round")
    identities.append(check)
    range_flags += flags

# Layer 4: each industry table's totals against the occupation table of the same year, in both rounds
cross = []
for table_id in INDUSTRY_TABLES:
    year = int(STATIC[table_id]["period"])
    occupation = PRIMARY_TABLE[year]
    theirs = static_totals[table_id]
    mine = {k: v for k, v in static_totals[occupation].items() if k[1] in STATIC[table_id]["rounds"]}
    cross.append(compare(mine, theirs, f"occupation table {occupation} = industry table {table_id}, Jumlah, "
                                       f"{' and '.join(STATIC[table_id]['rounds'])}, rupiah",
                         f"static table {occupation}", f"static table {table_id}"))

# Layer 4: Februari 2023, which table 2190 adds to 2022, against table 2233
feb_2023 = "2023S1"
cross.append(compare({k: v for k, v in static_totals[2233].items() if k[1] == feb_2023},
                     {k: v for k, v in static_totals[2190].items() if k[1] == feb_2023},
                     f"occupation table 2233 = occupation table 2190, Jumlah, {feb_2023}, rupiah",
                     "static table 2233", "static table 2190"))

# Layer 4: var 583's totals of 2016 and 2024 against the occupation tables, then every cell of those tables
api_cells = []
for table_id in (PRIMARY_TABLE[2016], PRIMARY_TABLE[2024]):
    rounds = STATIC[table_id]["rounds"]
    cross.append(compare(static_totals[table_id], {k: v for k, v in api_totals.items() if k[1] in rounds},
                         f"occupation table {table_id} = var {API_VAR}, Jumlah, {' and '.join(rounds)}, rupiah",
                         f"static table {table_id}", f"var {API_VAR}"))
    turvar_names = {t["val"]: t["label"] for t in api_first["turvar"] if t["val"] in API_PARTS}
    api_cells.append(compare_cells(table_id, static_parts[table_id], static_totals[table_id], api,
                                   static_info[table_id]["footnote_1"], turvar_names))

# Layer 5: plausibility of every value and every change from the year before, and totals repeated across the two
# rounds of a year in any source; only flagged
flags, plausibility_compared, change_not_compared = plausibility(values)
repeat_flags, plausibility_compared[REPEAT_CHECK] = repeated_totals(
    [(f"static table {t}", static_totals[t], static_parts[t]) for t in STATIC]
    + [(f"var {API_VAR}", api_totals, api_parts)])
flags = range_flags + flags + repeat_flags

# Statements for the metadata, written from the values read so that they cannot go stale
rounds_by_table = {str(t): ", ".join(info["rounds"]) for t, info in static_info.items()}
source_of_period = {f"{year}{WRITTEN_ROUND}": (f"static table {PRIMARY_TABLE[year]}" if year in PRIMARY_TABLE
                                               else f"var {API_VAR}") for year in YEARS}
compared_values = sum(c["compared"] for c in cross)
equal_cells = sum(c["equal"] for c in api_cells)
national = {p: values[(cleaning.NATIONAL_CODE, p)] for p in PERIODS}
repeats = [repeat_note(f, values, provinces, source_of_period) for f in repeat_flags]

# Describe the dataset
meta = {
    "title": "BPS average net monthly wage of employees by province, Indonesia, Sakernas August, 2016-2025",
    "columns": {
        "province_code": "BPS province code (kode_bps); 00 = Indonesia (the tables' 'Rata-rata' row). Names and "
                         "Kemendagri codes in 'provinces'.",
        "indicator": "Indicator code; definition in 'indicators'.",
        "period": "YYYYS2 = the Agustus (August) round of Sakernas in year YYYY (see 'periods').",
        "status": "Revision marker; no source gives one, so every row is empty (final).",
        "value": "Rupiah per employee per month at current prices, whole rupiah as BPS publishes it; all main "
                 "occupations and industries together (the tables' Jumlah column).",
    },
    "provinces": provinces,
    "province_source": {"url": URL_PROVINCES, "file": posix(RAW_PROVINCES),
                        "aliases": {name: {"code": code, "reason": "the national average row: 'Rata-rata' in the "
                                                                   "static tables, 'RATA-RATA' under vervar 9999 in "
                                                                   "var 583 ('Provinsi dg Rata2')"}
                                    for name, code in NAME_ALIASES.items()},
                        "note": "BPS and Kemendagri codes differ for the six Papua provinces; join other datasets on "
                                "the code system they use."},
    "indicators": {INDICATOR: {
        "name": "Rata-rata upah/gaji bersih sebulan buruh/karyawan/pegawai (average net monthly wage or salary of "
                "employees), urban and rural areas, men and women together, all main occupations and industries",
        "definition": "From the var 583 note: upah/gaji bersih is what an employee received in the past month from "
                      "the main job, basic wage or salary and allowances, in cash or in kind, paid by the firm, office "
                      "or employer. Buruh/karyawan/pegawai are people who work for another person or an institution "
                      "with a fixed employer for a wage or salary; casual workers (pekerja bebas) are not included.",
        "unit": "rupiah per employee per month, current prices", "multiplier": 1, "base_unit": "Rp per month",
        "decimals": 0, "periods": f"{PERIODS[0]}-{PERIODS[-1]}, one value per year (the Agustus round)",
        "source": "BPS Sakernas (Survei Angkatan Kerja Nasional), as the var 583 note names it; BPS static tables "
                  "by province and main occupation for 2016-2024 and WebAPI var 583 for 2025 (see source_priority)",
        "download_script": DOWNLOAD_SCRIPT,
        "notes": [
            "The value is each table's Jumlah (total) column: every main occupation and industry together. No single "
            "occupation's or industry's value is written; the parts are read only for the checks.",
            "The var 583 note says some figures have a relative standard error (RSE) of 25-50%, and that an empty "
            "cell has an RSE of 50% or more and is not shown; no total is empty in any source.",
            "Averages do not add across provinces; 00 is BPS's national figure from the same survey round.",
        ],
    }},
    "periods": {
        "held": PERIODS,
        "round": f"Agustus (August), written {WRITTEN_ROUND}, in every year",
        "rounds_in_the_raw_files": rounds_by_table,
        "var_583_rounds": "Februari and Agustus of 2016, 2024 and 2025 (turtahun 189 and 190); its sub-period "
                          "Tahunan (191) holds no value",
        "how_the_round_is_known": "No static table has a source line or a note naming the round: each column block is "
                                  "headed 'Februari YYYY' or 'Agustus YYYY', and var 583 labels its sub-periods the "
                                  "same way. The survey is named only in the var 583 note (Sakernas).",
        "choice": "Every table holds both rounds of its year, and table 2190 adds Februari 2023, so either round runs "
                  "through 2016-2025. This build keeps Agustus in every year, one round per year as the dataset "
                  "asks, so that every year compares the same point in the year; Agustus is the round BPS uses for "
                  "its annual labour-force figures (this build's reason; no raw file names a preferred round). The "
                  "Februari values are read and cross-checked but not written; WRITTEN_ROUND = 'S1' writes them "
                  "instead.",
    },
    "coverage": {
        "first_period": {code: {"period": f"{year}{WRITTEN_ROUND}",
                                "reason": f"{provinces[code]['name']} became a province in 2022; tables 2253 and 2255 "
                                          f"give it its own row from 2024 and var 583 its own values from 2024 (its "
                                          f"2016 file lists it without values), and {PARENT[code]} covers it before"}
                         for code, year in FIRST_YEAR.items()},
        "gaps": "none: every other province and Indonesia has a value in every period; no total is 'NA' or '-' in any "
                "source.",
        "kalimantan_utara": "65 (Kalimantan Utara) has its own row in every table from 2016, so 64 (Kalimantan Timur) "
                            "excludes it in every period.",
    },
    "borders": [
        "91 (Papua Barat) and 94 (Papua) in 2016-2023 cover the pre-split provinces: the tables of those years have 34 "
        "provinces, with Papua Barat Daya inside 91 and Papua Selatan, Papua Tengah and Papua Pegunungan inside 94. "
        "From 2024, 91 and 94 cover the post-split areas, and 92, 95, 96 and 97 start.",
        "An average of a pre-split area cannot be rebuilt from the post-split provinces without their numbers of "
        "employees, and a change from the year before across a border change compares different areas: 91 and 94 in "
        "2024 (checks.change_not_compared).",
    ],
    "workers_covered": {
        "finding": "Every table covers employees (buruh/karyawan/pegawai), including 2016.",
        "evidence": f"The page title of static table 1948 (2016) reads 'Pekerja Formal' (formal workers), but its "
                    f"catalogue title reads 'Buruh/Karyawan/Pegawai', as do all other tables and var {API_VAR}. Var "
                    f"{API_VAR}, defined in its note for employees, repeats every cell of table 1948: "
                    f"{api_cells[0]['equal']} values equal and its {api_cells[0]['na_cells_absent_from_var_583']} "
                    f"'NA' cells are the keys var "
                    f"{API_VAR} leaves out (checks.cross_source). No raw file defines 'Pekerja Formal' or gives a "
                    f"different 2016 figure, so the build treats 2016 as covering the same employees as the other "
                    f"years.",
    },
    "part_markers": {"markers": MARKERS,
                     "note": "Markers appear only in the part (occupation or industry) cells, which are read for the "
                             "checks and never written; no total carries one."},
    "source_priority": [
        {"source": "static tables by province and main occupation", "periods": f"{PERIODS[0]}-{PERIODS[-2]}",
         "use": "every value of its year, from the table whose title names that year (2190 for 2022, titled "
                "2022-2023)", "by_period": {p: s for p, s in source_of_period.items() if s != f"var {API_VAR}"}},
        {"source": f"WebAPI var {API_VAR}", "periods": PERIODS[-1],
         "use": f"the {YEARS[-1]} values, which no static table holds; its 2016 and 2024 values are lower-priority "
                f"copies, compared in checks.cross_source"},
        {"source": "static tables by province and main industry", "periods": "2017-2024",
         "use": "lower-priority copies of each total, compared in checks.cross_source and never written"},
    ],
    "source_tables": {
        **{f"static_table_{t}": {**static_info[t], "download_script": DOWNLOAD_SCRIPT,
                                 "role": ("gives the values of its year" if t in PRIMARY_TABLE.values() else
                                          "lower-priority copy of each total, read as a check"),
                                 "read_as": {"decimal_displayed": STATIC[t]["style"][0],
                                             "thousands_displayed": STATIC[t]["style"][1],
                                             "thousands_written": READ_CONTEXT[STATIC_PATHS[t]]["thousands"],
                                             "decimals": 0}}
           for t in STATIC},
        f"var_{API_VAR}": {"files": {span: describe_api(api_tables[span], span) for span in API_SPANS},
                           "request": URL_API, "download_script": DOWNLOAD_SCRIPT, "note_as_published": api_note},
    },
    "table_2190": f"Static table 2190 is titled 2022-2023 and holds Februari 2022, Agustus 2022 and Februari 2023 "
                  f"(created {static_info[2190]['created'][:10]}, updated {static_info[2190]['updated'][:10]}). Its "
                  f"2022 totals equal industry table 2189 in both rounds, and its Februari 2023 totals equal table "
                  f"2233 (2023, both rounds); it gives the 2022 value, and its Februari 2023 is a check.",
    "notes": [
        f"Each value is the Agustus Jumlah of its year's occupation table (2016-2024) or of var {API_VAR} (2025). All "
        f"{compared_values} comparisons of a total that two sources share agree exactly, in both rounds, and so do all "
        f"{equal_cells} cells var {API_VAR} shares with tables 1948 and 2255 (checks.cross_source).",
        "National average (00), rupiah per month: " + ", ".join(f"{p} {v:,.0f}" for p, v in national.items()) + ".",
        *repeats,
        "Derived values are not stored: the change from the year before (%) = value in year t / value in year t-1 x "
        "100 - 100, the same round in both years; it is computed here only for the plausibility flags. A real wage "
        "needs a price index, and a ratio to the minimum wage needs that dataset, both in analysis/.",
        "checks.flags lists, for a person to review, every value and change outside its range in "
        "checks.plausible_ranges, every total outside its published parts' range where a part is not shown, and every "
        "total that one source repeats in both rounds of a year (checks.repeat_check); a change flag gives the two "
        "values it compares under rupiah. A flag stays whether it reflects a real event or a source error.",
    ],
    "checks": {
        "passed": ["identities", "cross-source"],
        "identities": identities,
        "identity_reason": "A total (Jumlah) is the average over every employee of the province and round, so it lies "
                           "between the lowest and highest average of its parts (occupations or industries): exactly "
                           "where every part is published or '-', and only as a flag where a part is not shown.",
        "cross_source": cross + api_cells,
        "cross_source_tolerance": f"{TOL_CROSS} rupiah: every copy is the same published whole-rupiah figure",
        "plausible_ranges": {check: {"range": list(PLAUSIBLE[check]), "measure": PLAUSIBLE_MEASURES[check]}
                             for check in PLAUSIBLE},
        "repeat_check": {"check": REPEAT_CHECK, "measure": REPEAT_MEASURE},
        "plausibility_compared": plausibility_compared,
        "change_not_compared": change_not_compared,
        "flags": flags,
    },
}

# Layers 1, 2 and 6: every region from its first year must have a value in every period, and nothing else; write the
# CSV and metadata
expected = {(code, INDICATOR, f"{year}{WRITTEN_ROUND}") for year in YEARS for code in regions_in(year, codes)}
raw_files = [RAW_PROVINCES, *STATIC_PATHS.values(), *API_PATHS.values()]
out = cleaning.write_dataset(
    rows, KEYS, allowed={"province_code": codes, "indicator": [INDICATOR], "period": PERIODS},
    expected=expected, csv_path=OUT_CSV, meta=meta, raw_files=raw_files, sort_orders={"period": PERIODS},
)

# Report what was written and every check
print(f"{OUT_CSV.name}: {len(out)} rows, {len(flags)} flags")
print(out.groupby("period").size().to_string())
for check in identities:
    print("  identity:", {k: check[k] for k in ("check", "compared", "exact_bound", "some_parts_not_shown")})
for check in cross:
    print(f"  cross-source: {check['check']}: {check['compared']} compared, {len(check['differences'])} differ")
for check in api_cells:
    print(f"  cross-source: {check['check']}: {check['equal']} equal, "
          f"{check['na_cells_absent_from_var_583']} NA absent")
print(f"  plausibility: values read {plausibility_compared}")
for f in flags:
    print("  flag:", f)
