from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# Load the shared cleaning module from tools/
import sys
sys.path.insert(0, str(ROOT / "tools"))
import cleaning

# Modules for reading the table note clause by clause: html for its entities, re for its tags
import html
import re

# Parameters

# Raw inputs: the BPS province list, and the BPS WebAPI dynamic table of domain 0000, var 2211 (Angka Partisipasi
# Sekolah (APS) Menurut Provinsi dan Kelompok Umur), saved by the download script in the year ranges it requested, at
# most three years per request. var 2211 gives every value in the CSV
RAW_PROVINCES = ROOT / "raw/province-codes/20261102_bps-province-codes-2025-s1.json"
RAW_DIR = ROOT / "raw/education"
RAW_DOWNLOAD_SCRIPT = "raw/education/20261104_download-bps-school-participation-by-province.py"
VAR = 2211
YEAR_RANGES = [(2015, 2017), (2018, 2020), (2021, 2023), (2024, 2025)]
RAW_WEBAPI = {span: RAW_DIR / f"20261104_bps-api-var{VAR}-school-participation-by-province-and-age-{span[0]}-"
                              f"{span[1]}.json" for span in YEAR_RANGES}

# Output; the metadata JSON is written beside it with a -metadata suffix
OUT_CSV = HERE / "20261104_bps-province-school-participation.csv"

# How each raw file is written, read from opening all five files. The province list is UTF-8 JSON without a byte-order
# mark: 38 records whose four fields (kode_bps, nama_bps, kode_dagri, nama_dagri) are all text, so it holds no numbers,
# units or missing values. The four WebAPI files are UTF-8 JSON without a byte-order mark. Every value is a JSON number
# with a decimal point and no thousands separator, trailing zeros dropped (82 for 82.00, 99.9 for 99.90). The unit
# field reads 'Tidak Ada Satuan' (no unit) and the decimal field 2. A value BPS does not publish is a key absent from
# datacontent (the four new Papua provinces before 2024); the files hold no missing-value markers
UNIT = "Tidak Ada Satuan"
DECIMALS = 2
READ_CONTEXT = {
    RAW_PROVINCES: {"encoding": "utf-8", "numbers": "none: every code and name is a JSON string",
                    "missing": "none: every record carries kode_bps, nama_bps, kode_dagri and nama_dagri",
                    "unit": None},
    **{path: {"encoding": "utf-8", "numbers": "JSON numbers, decimal point, no thousands separator",
              "missing": "key absent from datacontent", "var": VAR, "unit": UNIT, "decimals": DECIMALS}
       for path in RAW_WEBAPI.values()},
}

# The one number format and missing-value convention cleaning.read_webapi_table reads: each value a JSON number, and
# a key absent from datacontent for a value BPS does not publish; a WebAPI file declared otherwise stops the build
WEBAPI_READS = {"numbers": "JSON numbers, decimal point, no thousands separator",
                "missing": "key absent from datacontent"}

# What the table must still be, read from opening the files, so that a different table under the same number stops the
# build: its label, the subject BPS files it under, and the collection its var record names
VAR_LABEL = "Angka Partisipasi Sekolah (APS) Menurut Provinsi dan Kelompok Umur"
SUBJECT = [{"val": 521, "label": "Pendidikan"}]
COLLECTION = "Pendidikan"

# The table's breakdown (turvar): four age groups in years, each with its BPS label and the code this dataset writes
AGE_GROUPS = {2001: ("7-12", "7-12"), 2002: ("13-15", "13-15"), 2003: ("16-18", "16-18"), 2004: ("19-23", "19-23")}
AGE_CODE = {turvar: code for turvar, (_, code) in AGE_GROUPS.items()}
AGE_NAMES = {"7-12": "Ages 7-12 (primary school age, SD)", "13-15": "Ages 13-15 (junior secondary age, SMP)",
             "16-18": "Ages 16-18 (senior secondary age, SMA/SMK)", "19-23": "Ages 19-23 (higher education age)"}

# The table's one sub-period (turtahun 'Tahun', year), the name of its region list, and the row BPS lists after the 38
# provinces, Indonesia
TURTAHUN = [(0, "Tahun")]
LABEL_VERVAR = "38 Provinsi"
NATIONAL_ROW = (9999, "INDONESIA")

# The table's note, clause by clause; the build stops if it changes. It names the source, BPS Susenas, and gives a
# definition that describes another indicator: the gap in school participation between people aged 7-17 with and
# without disabilities, not school participation by age group. The definition field is empty, and the note states no
# revision status and no Susenas round
NOTE_CLAUSES = ["Sumber : BPS, Susenas",
                "Definisi : Angka yang menggambarkan ketimpangan partisipasi sekolah antara penduduk berusia 7-17 "
                "tahun dengan disabilitas dan tanpa disabilitas"]

# Output indicator, with its name, unit and multiplier to base units
INDICATOR = "school_participation_rate"
INDICATOR_INFO = {"name": "Angka Partisipasi Sekolah, APS (school participation rate), by age group",
                  "unit": "percent of the age group", "multiplier": 0.01, "base_unit": "fraction of the age group"}

# Years held: every year the download requested, which its comments give as every year BPS lists for the var
YEARS = range(2015, 2026)
PERIODS = [str(year) for year in YEARS]

# Coverage, read from opening the files: the four provinces split from Papua Barat and Papua in 2022 have values from
# 2024, and every other province, Kalimantan Utara (65) included, and Indonesia have values in every year
FIRST_YEAR = {"92": 2024, "95": 2024, "96": 2024, "97": 2024}
PARENT = {"92": "91", "95": "94", "96": "94", "97": "94"}

# Provinces whose area changes, keyed by the first year on the new borders, with the provinces split off; a change of
# such a province from the year before compares different areas, so no change check reads it
BORDER_CHANGES = {("91", 2024): ["92"], ("94", 2024): ["95", "96", "97"]}

# A rate written per 100 lies between 0 and 100; a value outside means the values are not percentages, so the unit this
# script declares is wrong and the build stops
PERCENT_BOUNDS = (0, 100)

# Plausibility ranges (layer 5) by age group, in percent, and for the change from the year before, in percentage points;
# a value or change outside its range is flagged for review, not dropped
PLAUSIBLE = {"7-12": (90, 100), "13-15": (75, 100), "16-18": (45, 100), "19-23": (8, 75)}
CHANGE_RANGE = (-6, 6)
PLAUSIBLE_MEASURE = ("Every value, percent of the age group, against its age group's range: nearly every child of "
                     "primary age is in school, fewer at each later stage, and fewest at higher-education age. A "
                     "value outside its group's range lies far from Indonesia's in every year (checks.identities), so "
                     "it is flagged for review.")
CHANGE_MEASURE = ("Change from the same region's value for the same age group the year before, in percentage points. "
                  "School participation moves slowly, so a move of more than 6 points in one year is flagged for "
                  "review.")

# Source addresses for the metadata; the WebAPI request is given without its key
URL_PROVINCES = "https://sig.bps.go.id/rest-bridging/getwilayah?level=provinsi&periode_merge=2025_1.2025"
URL_WEBAPI = f"https://webapi.bps.go.id/v1/api/list/model/data/domain/0000/var/{VAR}/th/{{th}}/key/{{key}}"

# Key columns of this dataset
KEYS = ["province_code", "indicator", "age_group", "period"]


# Functions

def posix(path):
    """Return a path relative to the repository root with forward slashes, for the metadata fields that name files."""
    return Path(path).resolve().relative_to(ROOT).as_posix()


def and_list(items):
    """Return items joined for a sentence: 'a', 'a and b', or 'a, b and c'."""
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def read_webapi(path):
    """Read one saved WebAPI table with the encoding, var, unit and decimals READ_CONTEXT declares for it."""
    c = READ_CONTEXT[path]

    # read_webapi_table reads values only as JSON numbers and treats an absent key as no value, so a file declared
    # with another number format or missing-value convention stops the build
    if {k: c.get(k) for k in WEBAPI_READS} != WEBAPI_READS:
        raise ValueError(f"{path.name}: READ_CONTEXT declares {c}, but read_webapi_table reads only {WEBAPI_READS}")
    return cleaning.read_webapi_table(path, var=c["var"], unit=c["unit"], decimals=c["decimals"],
                                      encoding=c["encoding"])


def check_form(table, name):
    """Stop unless the file holds the declared table: its label, subject and collection, an empty definition, the four
    age groups and the one sub-period."""
    v = table["var"][0]
    if v["label"] != VAR_LABEL or table["subject"] != SUBJECT or v["subj"] != COLLECTION:
        raise ValueError(f"{name}: label {v['label']!r}, subject {table['subject']}, collection {v['subj']!r}")

    # The metadata states that the table defines nothing in its definition field, so one that appears must be read
    # into the metadata first
    if v["def"] != "":
        raise ValueError(f"{name}: the definition field now reads {v['def']!r}; read it into the metadata")
    if [(t["val"], t["label"]) for t in table["turvar"]] != [(k, label) for k, (label, _) in AGE_GROUPS.items()]:
        raise ValueError(f"{name}: turvar {table['turvar']}, expected the declared age groups")
    if [(t["val"], t["label"]) for t in table["turtahun"]] != TURTAHUN:
        raise ValueError(f"{name}: turtahun {table['turtahun']}, expected {TURTAHUN}")


def check_regions(table, lookup, codes, name):
    """Stop unless the file lists the 38 provinces in BPS order under their BPS names and codes, then Indonesia."""
    rows = [(v["val"], v["label"]) for v in table["vervar"]]
    if table["labelvervar"] != LABEL_VERVAR or rows[-1] != NATIONAL_ROW:
        raise ValueError(f"{name}: region list {table['labelvervar']!r} ending {rows[-1]}")
    found = [cleaning.webapi_region_code(val, label, lookup) for val, label in rows]
    if found != codes + [cleaning.NATIONAL_CODE]:
        raise ValueError(f"{name}: regions {found}, expected the 38 provinces in BPS order, then Indonesia")


def note_clauses(note):
    """Return a WebAPI note as its clauses: each list item, paragraph or line as plain text, without the empty ones."""
    text = html.unescape(html.unescape(note or ""))
    parts = re.split(r"<\s*/?\s*(?:li|ul|ol|p|br|div)\b[^>]*>|[\r\n]", text, flags=re.I)
    return [clause for clause in (" ".join(re.sub(r"<[^>]+>", " ", p).split()) for p in parts) if clause]


def read_files(lookup, codes):
    """Read every WebAPI file; return the description they share and {(code, age group, period): value}."""
    tables, values = [], {}
    for (first, last), path in RAW_WEBAPI.items():
        table, records = read_webapi(path)

        # The file must hold the declared table, the years the download asked for, and the 38 provinces and Indonesia
        check_form(table, path.name)
        years = [int(t["label"]) for t in table["tahun"]]
        if years != list(range(first, last + 1)):
            raise ValueError(f"{path.name}: years {years}, expected {first}-{last}")
        check_regions(table, lookup, codes, path.name)
        tables.append(table)

        # Each value goes to its region code (checked against the BPS list by name), age group and year, once
        for r in records:
            code = cleaning.webapi_region_code(r["vervar"], r["vervar_label"], lookup)
            key = (code, AGE_CODE[r["turvar"]], str(r["year"]))
            if key in values:
                raise ValueError(f"{path.name}: {key} read twice")
            values[key] = r["value"]

    # All files must come from one release of the table, note, unit and decimals included
    for table in tables[1:]:
        for field in ("var", "turvar", "turtahun", "vervar", "labelvervar", "subject", "last_update"):
            if table[field] != tables[0][field]:
                raise ValueError(f"var {VAR}: files differ in {field}")
    return tables[0], values


def regions_in(year, codes):
    """Return Indonesia and the provinces with their own values in a year."""
    return [code for code in [cleaning.NATIONAL_CODE] + codes if year >= FIRST_YEAR.get(code, YEARS[0])]


def expected_keys(codes):
    """Every key the table should yield: each age group in each year for Indonesia and every province with its own
    values that year; the four new Papua provinces before 2024 are the only gaps."""
    return {(code, INDICATOR, age, str(year)) for year in YEARS for code in regions_in(year, codes)
            for age in AGE_CODE.values()}


def coverage(codes):
    """Describe each run of years with the same provinces: how many have values and which are absent."""
    runs = []
    for year in YEARS:
        absent = [code for code in codes if code not in regions_in(year, codes)]
        if runs and runs[-1]["absent"] == absent:
            runs[-1]["last"] = year
        else:
            runs.append({"first": year, "last": year, "absent": absent})
    return {f"{r['first']}-{r['last']}": {"provinces": len(codes) - len(r["absent"]), "absent": r["absent"]}
            for r in runs}


def check_percent(values):
    """Stop unless every value lies within PERCENT_BOUNDS, as a rate written per 100 must, and return the check for the
    metadata."""
    low, high = PERCENT_BOUNDS
    outside = sorted((k, v) for k, v in values.items() if not low <= v <= high)
    if outside:
        raise ValueError(f"{len(outside)} values outside {low}-{high}, such as {outside[:3]}; the values are not "
                         f"percentages, so the declared unit is wrong")
    return {"check": f"every value lies between {low} and {high}, as a rate written per 100 must; the unit field reads "
                     f"'{UNIT}', so this is what declares the values percentages",
            "compared": len(values), "lowest": min(values.values()), "highest": max(values.values())}


def national_within_provinces(values):
    """Layer 3: in every age group and year, Indonesia's rate lies between the lowest and the highest province rate.
    A national rate over the same age group is a population-weighted mean of the provinces' rates, and rounding to the
    published decimals keeps that order, so the check needs no tolerance; the table gives no weights for a closer
    provinces-to-Indonesia identity."""
    detail = {}
    for age in AGE_CODE.values():
        for year in YEARS:
            period = str(year)
            provinces = {c: v for (c, a, p), v in values.items()
                         if a == age and p == period and c != cleaning.NATIONAL_CODE}
            national = values[(cleaning.NATIONAL_CODE, age, period)]
            low, high = min(provinces, key=provinces.get), max(provinces, key=provinces.get)
            if not provinces[low] <= national <= provinces[high]:
                raise ValueError(f"{age} {period}: Indonesia's {national} lies outside the provinces' "
                                 f"{provinces[low]} ({low}) to {provinces[high]} ({high})")
            detail[f"{age} {period}"] = {"indonesia": national, "lowest": [low, provinces[low]],
                                         "highest": [high, provinces[high]], "provinces": len(provinces)}
    return {"check": "Indonesia (00) lies between the lowest and the highest province rate, every age group and year",
            "compared": len(detail), "tolerance": 0,
            "tolerance_reason": "rounding to the published decimals cannot move a weighted mean outside the rounded "
                                "lowest and highest values", "groups": detail}


def plausibility(values):
    """Layer 5: every value, and every change from the same region's value the year before, inside its stated range.
    Returns the flags, the values each check read, and the changes left out at a border change."""
    read = {**{age: [] for age in PLAUSIBLE}, "change": []}
    skipped = []
    for (code, age, period), value in sorted(values.items()):
        read[age].append({"province_code": code, "age_group": age, "period": period, "value": value})
        before = values.get((code, age, str(int(period) - 1)))
        if before is None:
            continue

        # A change across a border change compares different areas, so it is listed and left out
        if (code, int(period)) in BORDER_CHANGES:
            split = BORDER_CHANGES[(code, int(period))]
            own = "has its" if len(split) == 1 else "have their"
            skipped.append({"province_code": code, "age_group": age, "period": period,
                            "reason": f"{code} in {int(period) - 1} includes {and_list(split)}, which {own} own values "
                                      f"from {period}, so the change compares different areas"})
            continue
        read["change"].append({"province_code": code, "age_group": age, "period": period,
                               "from_period": str(int(period) - 1),
                               "values": {str(int(period) - 1): before, period: value},
                               "value": round(value - before, 2)})
    ranges = {**PLAUSIBLE, "change": CHANGE_RANGE}
    flags = [f for check, (low, high) in ranges.items()
             for f in cleaning.flag_outside(read[check], check if check == "change" else f"rate_{check}", low, high)]
    return flags, read, skipped


def observed(read):
    """Return the lowest and highest value each plausibility check read, with region and period, for the metadata."""
    out = {}
    for check, items in read.items():
        low, high = min(items, key=lambda r: r["value"]), max(items, key=lambda r: r["value"])
        out[check] = {"read": len(items),
                      **{end: {"province_code": r["province_code"], "period": r["period"],
                               "value": round(r["value"], 4)} for end, r in (("lowest", low), ("highest", high))}}
    return out


# Steps

# Print in UTF-8 so BPS labels show on any console
sys.stdout.reconfigure(encoding="utf-8")

# Read the BPS province list that every region name and code is matched against; load_bps_provinces reads UTF-8
# JSON, so a list declared in another encoding stops the build
if READ_CONTEXT[RAW_PROVINCES]["encoding"] != "utf-8":
    raise ValueError(f"{RAW_PROVINCES.name}: READ_CONTEXT declares {READ_CONTEXT[RAW_PROVINCES]}, but "
                     f"load_bps_provinces reads UTF-8")
provinces, lookup = cleaning.load_bps_provinces(RAW_PROVINCES)
codes = [c for c in provinces if c != cleaning.NATIONAL_CODE]

# Stop unless the download script the metadata names is in the repository, and raw/education holds exactly the
# declared files of the var
if not (ROOT / RAW_DOWNLOAD_SCRIPT).is_file():
    raise FileNotFoundError(f"download script {RAW_DOWNLOAD_SCRIPT} not found")
found = sorted(RAW_DIR.glob(f"20261104_bps-api-var{VAR}-*.json"))
if found != sorted(RAW_WEBAPI.values()):
    raise ValueError(f"var {VAR}: raw/education holds {[p.name for p in found]}, expected the declared files")

# Read every file into one description and one value map
table, values = read_files(lookup, codes)

# The note must still read clause for clause as declared and state no revision status, so every row is final (empty)
note = table["var"][0]["note"]
if note_clauses(note) != NOTE_CLAUSES:
    raise ValueError(f"var {VAR} note now reads {note_clauses(note)}, the script declares {NOTE_CLAUSES}")
if cleaning.parse_status_note(note):
    raise ValueError(f"var {VAR} note now states revision statuses {cleaning.parse_status_note(note)}")
rows = [{"province_code": c, "indicator": INDICATOR, "age_group": a, "period": p, "status": "", "value": v}
        for (c, a, p), v in values.items()]

# Unit (layer 1): every rate lies between 0 and 100, which is what declares it a percentage; stops on failure
unit_check = check_percent(values)

# Layer 3: Indonesia lies between the lowest and highest province in every age group and year; stops on failure
identity = national_within_provinces(values)

# Layer 5: every value and every change from the year before inside its stated range; outliers are only flagged
flags, read, skipped = plausibility(values)
seen = observed(read)

# Statements for the metadata, written from the declarations so that they cannot go stale
new_codes = and_list(list(FIRST_YEAR))
first_new = min(FIRST_YEAR.values())
v = table["var"][0]

# Describe the dataset
meta = {
    "title": f"BPS school participation rate (APS) by province and age group, {YEARS[0]}-{YEARS[-1]}, Indonesia",
    "columns": {
        "province_code": "BPS province code (kode_bps); 00 = Indonesia. Names and Kemendagri codes in 'provinces'.",
        "indicator": "Indicator code; definition in 'indicators'.",
        "age_group": "Age group in years, as BPS labels it; names in 'age_groups'.",
        "period": "YYYY, the year BPS gives the value for. The table labels its one sub-period 'Tahun' (year), and its "
                  "note names the source only as 'BPS, Susenas', without the Susenas round (March or September), so "
                  "periods are written YYYY, not YYYYS1 or YYYYS2.",
        "status": "Revision marker; the table note states none, so every row is empty (final).",
        "value": "Percent of the age group, 2 decimals, as published by BPS. Multiply by 'multiplier' for base units.",
    },
    "provinces": provinces,
    "province_source": {"url": URL_PROVINCES, "file": posix(RAW_PROVINCES),
                        "note": "BPS and Kemendagri codes differ for the six Papua provinces; join other datasets on "
                                "the code system they use. Every region label in the table matches the BPS list "
                                "after cleaning.normalise_name, so no alias is declared."},
    "indicators": {
        INDICATOR: {
            **INDICATOR_INFO,
            "decimals": v["decimal"],
            "periods": f"{YEARS[0]}-{YEARS[-1]}, yearly",
            "unit_reading": f"The table's unit field reads '{UNIT}' (no unit). Every value lies between "
                            f"{PERCENT_BOUNDS[0]} and {PERCENT_BOUNDS[1]} with at most 2 decimals (checks.unit, which "
                            f"stops the build otherwise), so the values are read as percent of the age group.",
            "definition": "The raw files do not define the rate: the definition field is empty, and the note's "
                          "definition ('Angka yang menggambarkan ketimpangan partisipasi sekolah antara penduduk "
                          "berusia 7-17 tahun dengan disabilitas dan tanpa disabilitas') describes another indicator, "
                          "the gap in school participation between people aged 7-17 with and without disabilities. "
                          "The label names the rate as Angka Partisipasi Sekolah (APS) by age group.",
            "source": f"BPS WebAPI var {VAR} '{VAR_LABEL}', from Susenas; see 'source_table'",
            "download_script": RAW_DOWNLOAD_SCRIPT,
        },
    },
    "age_groups": {code: {"name": AGE_NAMES[code], "bps_label": label, "turvar": turvar}
                   for turvar, (label, code) in AGE_GROUPS.items()},
    "periods": {"held": PERIODS,
                "survey_round": "The table does not state its Susenas round: its one sub-period is 'Tahun' (year) and "
                                "its note names only 'BPS, Susenas'. Each value is BPS's figure for the year, written "
                                "YYYY."},
    "coverage": {
        "years": coverage(codes),
        "first_year": {code: {"year": year, "reason": f"{provinces[code]['name']} became a province in 2022; the "
                                                      f"table gives it its own values from {year}, and "
                                                      f"{PARENT[code]} covers it before"}
                       for code, year in FIRST_YEAR.items()},
        "indonesia": f"The table lists Indonesia (row {NATIONAL_ROW[0]} '{NATIONAL_ROW[1]}') after the 38 provinces, "
                     f"with a value in every age group and year; it is written as code {cleaning.NATIONAL_CODE}.",
    },
    "borders": [
        f"65 (Kalimantan Utara) has its own values from {YEARS[0]}, the first year held, so 64 (Kalimantan Timur) "
        f"excludes it in every year held.",
        f"91 (Papua Barat) and 94 (Papua) up to {first_new - 1} cover the areas before the 2022 split: the table gives "
        f"{new_codes} no value before {first_new}. From {first_new}, 91 and 94 cover the provinces after the split.",
        "Rates do not add across provinces. A rate for an area of several provinces, such as Papua Barat before the "
        "split (91 + 92), needs each province's population in the age group, which this table does not give.",
        f"A change of 91 or 94 from {first_new - 1} to {first_new} compares different areas; the change check leaves "
        f"those changes out (checks.change_not_compared).",
    ],
    "source_table": {
        "role": "gives every value in the CSV",
        "label": v["label"],
        "subject": table["subject"],
        "collection": v["subj"],
        "unit": v["unit"],
        "decimals": v["decimal"],
        "definition": "none: the table's definition field ('def') is empty; the note's definition describes another "
                      "indicator (see 'indicators')",
        "turvar": {str(t["val"]): t["label"] for t in table["turvar"]},
        "turtahun": {str(t["val"]): t["label"] for t in table["turtahun"]},
        "regions": table["labelvervar"],
        "years": f"{YEAR_RANGES[0][0]}-{YEAR_RANGES[-1][1]}",
        "last_update": table["last_update"],
        "note": cleaning.html_to_text(v["note"]),
        "note_clauses": NOTE_CLAUSES,
        "request": URL_WEBAPI + f" (th = first:last year minus 1900, such as {YEAR_RANGES[0][0] - 1900}:"
                                f"{YEAR_RANGES[0][1] - 1900} for {YEAR_RANGES[0][0]}-{YEAR_RANGES[0][1]}; the key "
                                f"is not stored)",
        "download_script": RAW_DOWNLOAD_SCRIPT,
        "files": [posix(p) for p in RAW_WEBAPI.values()],
    },
    "notes": [
        "No other raw file in the repository holds these rates, so there is no cross-source check (layer 4).",
        "Indonesia's value is BPS's own national figure, not computed here. It lies between the lowest and the highest "
        "province in every age group and year (checks.identities), as a national rate over the same age group must.",
        "Derived values are not stored. Change in a rate (percentage points) = rate in t - rate in t-1.",
        "checks.flags lists every value or change outside its range in checks.plausible_ranges for a person to review, "
        "with the two values each change compares; a flag stays whether it reflects a real event or a source error.",
    ],
    "checks": {
        "passed": ["unit", "identities", "plausibility checked (layer 5, flags listed)"],
        "unit": unit_check,
        "identities": identity,
        "cross_source": "Not applicable (layer 4): no other raw file holds these values; see 'notes'.",
        "plausible_ranges": {**{f"rate_{age}": {"range": list(r), "measure": PLAUSIBLE_MEASURE}
                                for age, r in PLAUSIBLE.items()},
                             "change": {"range": list(CHANGE_RANGE), "measure": CHANGE_MEASURE}},
        "plausibility_observed": seen,
        "change_not_compared": skipped,
        "flags": flags,
    },
}

# Layers 1, 2 and 6: check structure and completeness against the declared coverage, then write the CSV and metadata
raw_files = [RAW_PROVINCES] + list(RAW_WEBAPI.values())
out = cleaning.write_dataset(
    rows, KEYS,
    allowed={"province_code": [cleaning.NATIONAL_CODE] + codes, "indicator": [INDICATOR],
             "age_group": list(AGE_CODE.values()), "period": PERIODS},
    expected=expected_keys(codes),
    csv_path=OUT_CSV, meta=meta, raw_files=raw_files,
    sort_orders={"age_group": list(AGE_CODE.values()), "period": PERIODS},
)

# Report what was written, every check result and every plausibility flag
print(f"{OUT_CSV.name}: {len(out)} rows, {len(flags)} plausibility flags")
print("  unit:", {k: v for k, v in unit_check.items() if k != "check"})
print("  identity:", identity["check"], "-", identity["compared"], "age group-years")
print("  plausibility observed:", {k: (v["lowest"]["value"], v["highest"]["value"]) for k, v in seen.items()})
for s in skipped:
    print("  change not compared:", s["province_code"], s["age_group"], s["period"])
for f in flags:
    print("  flag:", f)
