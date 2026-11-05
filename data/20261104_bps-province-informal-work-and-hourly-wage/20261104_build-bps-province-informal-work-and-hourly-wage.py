from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# Load the shared cleaning module from tools/
import sys
sys.path.insert(0, str(ROOT / "tools"))
import cleaning

# Modules for reading the table notes clause by clause: html for their entities, re for their tags and statements
import html
import re

# Parameters

# Raw inputs: the BPS province list, and two BPS WebAPI dynamic tables of domain 0000, var 2153 (Proporsi Lapangan Kerja
# Informal Menurut Provinsi) and var 1172 (Upah Rata - Rata Per Jam Pekerja Menurut Provinsi), each saved by the
# download script in the year ranges it requested, at most three years per request. var 2153 gives every
# informal_employment_share value in the CSV and var 1172 every hourly_wage value
RAW_PROVINCES = ROOT / "raw/province-codes/20261102_bps-province-codes-2025-s1.json"
RAW_DIR = ROOT / "raw/labour"
RAW_DOWNLOAD_SCRIPT = "raw/labour/20261104_download-bps-informal-work-and-hourly-wage-by-province.py"
RAW_NAMES = {2153: "informal-employment-share-by-province", 1172: "hourly-wage-by-province"}
YEAR_RANGES = {2153: [(2018, 2020), (2021, 2023), (2024, 2025)],
               1172: [(2015, 2017), (2018, 2020), (2021, 2023), (2024, 2025)]}
RAW_WEBAPI = {var: {span: RAW_DIR / f"20261104_bps-api-var{var}-{name}-{span[0]}-{span[1]}.json"
                    for span in YEAR_RANGES[var]} for var, name in RAW_NAMES.items()}

# Output; the metadata JSON is written beside it with a -metadata suffix
OUT_CSV = HERE / "20261104_bps-province-informal-work-and-hourly-wage.csv"

# How each raw file is written, read from opening all eight files. The province list is UTF-8 JSON without a byte-order
# mark: 38 records whose four fields (kode_bps, nama_bps, kode_dagri, nama_dagri) are all text, so it holds no numbers,
# units or missing values. The seven WebAPI files are UTF-8 JSON without a byte-order mark. Every value is a JSON number
# with a decimal point and no thousands separator, trailing zeros dropped (var 2153 writes 55 for 55.00 and 50.2 for
# 50.20). var 2153's unit field reads 'Tidak Ada Satuan' (no unit) and its decimal field 2; var 1172's unit field reads
# 'Rupiah/Jam' and its decimal field 0. A value BPS does not publish is a key absent from datacontent (the four new
# Papua provinces before 2024); the files hold no missing-value markers
UNITS = {2153: "Tidak Ada Satuan", 1172: "Rupiah/Jam"}
DECIMALS = {2153: 2, 1172: 0}
READ_CONTEXT = {
    RAW_PROVINCES: {"encoding": "utf-8", "numbers": "none: every code and name is a JSON string",
                    "missing": "none: every record carries kode_bps, nama_bps, kode_dagri and nama_dagri",
                    "unit": None},
    **{path: {"encoding": "utf-8", "numbers": "JSON numbers, decimal point, no thousands separator",
              "missing": "key absent from datacontent", "var": var, "unit": UNITS[var], "decimals": DECIMALS[var]}
       for var, files in RAW_WEBAPI.items() for path in files.values()},
}

# The one number format and missing-value convention cleaning.read_webapi_table reads: each value a JSON number, and
# a key absent from datacontent for a value BPS does not publish; a WebAPI file declared otherwise stops the build
WEBAPI_READS = {"numbers": "JSON numbers, decimal point, no thousands separator",
                "missing": "key absent from datacontent"}

# What each table must still be, read from opening the files, so that a different table under the same number stops the
# build: its label, the subject BPS files it under, and the SDG collection both tables belong to. The SDG indicator
# numbers come from the download script's comments; the raw files name only the collection
VAR_LABELS = {2153: "Proporsi Lapangan Kerja Informal Menurut Provinsi",
              1172: "Upah Rata - Rata Per Jam Pekerja Menurut Provinsi"}
SUBJECTS = {2153: [{"val": 520, "label": "Tenaga Kerja"}], 1172: [{"val": 537, "label": "Biaya Tenaga Kerja"}]}
SDG_COLLECTION = "Tujuan Pembangunan Berkelanjutan Edisi I"
SDG_INDICATORS = {2153: "8.3.1", 1172: "8.5.1"}

# Each table's one breakdown (turvar 'Tidak ada', none) and one sub-period (turtahun 'Tahun', year), the name of its
# region list, and the row BPS lists after the 38 provinces, Indonesia
TURVAR = [("0", "Tidak ada")]
TURTAHUN = [(0, "Tahun")]
LABEL_VERVAR = "38 Provinsi"
NATIONAL_ROW = (9999, "INDONESIA")

# Each table's note, clause by clause (list items and paragraphs as published, empty ones dropped); the build stops if a
# note changes. Both name the survey; var 1172's also states that 2015-2019 are revised figures because of a change of
# survey weights (penimbang). No note, label or sub-period names the Sakernas round (February or August), and both
# tables' definition fields are empty
NOTE_CLAUSES = {2153: ["Sumber: Sakernas, BPS"],
                1172: ["Sumber: Sakernas, BPS", "Tahun 2015-2019 angka revisi karena perubahan penimbang"]}

# A note clause that states revised figures (angka revisi) for a year or a run of years, as 'Tahun 2015-2019 angka
# revisi karena perubahan penimbang', and the BPS_STATUS marker of revised figures, 'r' (Angka diperbaiki, revised),
# which every year of the run carries; cleaning.parse_status_note does not read this form
REVISION_CLAUSE = re.compile(r"Tahun ((?:19|20)\d{2})(?:\s*[-–]\s*((?:19|20)\d{2}))? angka revisi\b.*", re.I)
REVISED = "r"

# Revision status by year that each note states; every row of a stated year carries it, and the build stops if a note
# states other statuses
NOTE_STATUS = {2153: {}, 1172: {year: REVISED for year in range(2015, 2020)}}

# Output indicator of each var, in output order, with its name, unit and multiplier to base units
INDICATORS = {2153: "informal_employment_share", 1172: "hourly_wage"}
VAR_OF = {indicator: var for var, indicator in INDICATORS.items()}
SHARE, WAGE = INDICATORS[2153], INDICATORS[1172]
INDICATOR_INFO = {
    SHARE: {"name": "Proporsi lapangan kerja informal (informal employment as a share of employment)",
            "unit": "percent of employment", "multiplier": 0.01, "base_unit": "fraction of employment"},
    WAGE: {"name": "Upah rata-rata per jam pekerja (average hourly wage of workers)",
           "unit": "Rupiah per hour (Rupiah/Jam)", "multiplier": 1, "base_unit": "Rupiah per hour"},
}

# Years each indicator holds: the years the download script requested, which its comments give as every year BPS lists
# for the var; and every period in output order
YEARS = {SHARE: range(2018, 2026), WAGE: range(2015, 2026)}
PERIODS = [str(year) for year in range(2015, 2026)]

# Coverage, read from opening the files: the four provinces split from Papua Barat and Papua in 2022 have values from
# 2024 in both tables, and every other province, Kalimantan Utara (65) included, and Indonesia have values in every
# year of each table
FIRST_YEAR = {"92": 2024, "95": 2024, "96": 2024, "97": 2024}
PARENT = {"92": "91", "95": "94", "96": "94", "97": "94"}

# Provinces whose area changes, keyed by the first year on the new borders, with the provinces split off; a change of
# such a province from the year before compares different areas, so no change check reads it
BORDER_CHANGES = {("91", 2024): ["92"], ("94", 2024): ["95", "96", "97"]}

# A share written per 100 lies between 0 and 100; a var 2153 value outside means its values are not percentages, so the
# unit this script declares for it is wrong and the build stops
PERCENT_BOUNDS = (0, 100)

# Plausibility ranges (layer 5); a value or change outside its range is flagged for review, not dropped
PLAUSIBLE = {
    SHARE: (20, 95),
    f"{SHARE}_change": (-8, 8),
    WAGE: (5000, 50000),
    f"{WAGE}_change_pct": (-15, 30),
}
PLAUSIBLE_MEASURES = {
    SHARE: "Every value, percent of employment. Below 20, more than four jobs in five would be formal; above 95, fewer "
           "than one in twenty. Either lies far from Indonesia's share in every year (checks.identities), so it is "
           "flagged for review.",
    f"{SHARE}_change": "Change from the same region's value the year before, in percentage points (share in t - share "
                       "in t-1). Informality is a share of all employment and shifts slowly, so a move of more than 8 "
                       "points in one year is flagged for review.",
    WAGE: f"Every value, Rupiah per hour as published. The range reaches well beyond the published values on both "
          f"sides (checks.plausibility_observed), so a value below 5,000 or above 50,000 Rupiah per hour in "
          f"{YEARS[WAGE][0]}-{YEARS[WAGE][-1]} would point to a unit or entry error, and is flagged for review.",
    f"{WAGE}_change_pct": "Change from the same region's value the year before, in percent ((hourly_wage in t / "
                          "hourly_wage in t-1 - 1) x 100). An average wage seldom falls by more than 15 percent or "
                          "rises by more than 30 percent in one year, so such a move is flagged for review.",
}

# Source addresses for the metadata; the WebAPI request is given without its key
URL_PROVINCES = "https://sig.bps.go.id/rest-bridging/getwilayah?level=provinsi&periode_merge=2025_1.2025"
URL_WEBAPI = "https://webapi.bps.go.id/v1/api/list/model/data/domain/0000/var/{var}/th/{{th}}/key/{{key}}"

# Key columns of this dataset
KEYS = ["province_code", "indicator", "period"]


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


def check_form(var, table, name):
    """Stop unless the file holds the declared table: its label, subject and SDG collection, an empty definition, and
    the one breakdown and one sub-period."""
    v = table["var"][0]
    if v["label"] != VAR_LABELS[var] or table["subject"] != SUBJECTS[var] or v["subj"] != SDG_COLLECTION:
        raise ValueError(f"{name}: label {v['label']!r}, subject {table['subject']}, collection {v['subj']!r}")

    # The metadata states that the table defines nothing, so a definition that appears must be read into it first
    if v["def"] != "":
        raise ValueError(f"{name}: the definition field now reads {v['def']!r}; read it into the metadata")
    if [(t["val"], t["label"]) for t in table["turvar"]] != TURVAR:
        raise ValueError(f"{name}: turvar {table['turvar']}, expected {TURVAR}")
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


def read_var(var, lookup, codes):
    """Read the files of one var; return the description they share and {(code, indicator, period): value}."""
    tables, values = [], {}
    for (first, last), path in RAW_WEBAPI[var].items():
        table, records = read_webapi(path)

        # The file must hold the declared table, the years the download asked for, and the 38 provinces and Indonesia
        check_form(var, table, path.name)
        years = [int(t["label"]) for t in table["tahun"]]
        if years != list(range(first, last + 1)):
            raise ValueError(f"{path.name}: years {years}, expected {first}-{last}")
        check_regions(table, lookup, codes, path.name)
        tables.append(table)

        # Each value goes to its region code (checked against the BPS list by name) and year, once
        for r in records:
            code = cleaning.webapi_region_code(r["vervar"], r["vervar_label"], lookup)
            key = (code, INDICATORS[var], str(r["year"]))
            if key in values:
                raise ValueError(f"{path.name}: {key} read twice")
            values[key] = r["value"]

    # All files of the var must come from one release of the table, note, unit and decimals included
    for table in tables[1:]:
        for field in ("var", "turvar", "turtahun", "vervar", "labelvervar", "subject", "last_update"):
            if table[field] != tables[0][field]:
                raise ValueError(f"var {var}: files differ in {field}")
    return tables[0], values


def note_clauses(note):
    """Return a WebAPI note as its clauses: each list item, paragraph or line as plain text, without the empty ones."""
    text = html.unescape(html.unescape(note or ""))
    parts = re.split(r"<\s*/?\s*(?:li|ul|ol|p|br|div)\b[^>]*>|[\r\n]", text, flags=re.I)
    return [clause for clause in (" ".join(re.sub(r"<[^>]+>", " ", p).split()) for p in parts) if clause]


def note_statuses(note):
    """Return {year: status} that a note states: the statements cleaning.parse_status_note reads, and each clause
    stating revised figures for a year or a run of years (REVISION_CLAUSE), which gives every year of the run REVISED.
    Stops on a run that ends before it starts, on a year given two statuses, and on any other clause naming a
    revision."""
    status = cleaning.parse_status_note(note)
    for clause in note_clauses(note):
        found = REVISION_CLAUSE.fullmatch(clause)
        if found:
            first, last = int(found.group(1)), int(found.group(2) or found.group(1))
            if last < first:
                raise ValueError(f"note clause {clause!r}: the run of years ends before it starts")
            for year in range(first, last + 1):
                if status.setdefault(year, REVISED) != REVISED:
                    raise ValueError(f"note gives {year} both {status[year]!r} and {REVISED!r}")
        elif "revisi" in clause.lower():
            raise ValueError(f"note clause {clause!r} names a revision in a form this build does not read")
    return status


def regions_in(indicator, year, codes):
    """Return Indonesia and the provinces with their own values in a year of an indicator."""
    return [code for code in [cleaning.NATIONAL_CODE] + codes if year >= FIRST_YEAR.get(code, YEARS[indicator][0])]


def expected_keys(codes):
    """Every key the tables should yield: each indicator's years for Indonesia and every province with its own values
    that year; the four new Papua provinces before 2024 are the only gaps."""
    return {(code, indicator, str(year)) for indicator, years in YEARS.items() for year in years
            for code in regions_in(indicator, year, codes)}


def coverage(codes):
    """Describe, per indicator, each run of years with the same provinces: how many have values and which are absent."""
    out = {}
    for indicator, years in YEARS.items():
        runs = []
        for year in years:
            absent = [code for code in codes if code not in regions_in(indicator, year, codes)]
            if runs and runs[-1]["absent"] == absent:
                runs[-1]["last"] = year
            else:
                runs.append({"first": year, "last": year, "absent": absent})
        out[indicator] = {f"{r['first']}-{r['last']}": {"provinces": len(codes) - len(r["absent"]),
                                                        "absent": r["absent"]} for r in runs}
    return out


def check_percent(values):
    """Stop unless every informal_employment_share value lies within PERCENT_BOUNDS, as a share written per 100 must,
    and return the check for the metadata."""
    low, high = PERCENT_BOUNDS
    shares = {k: v for k, v in values.items() if k[1] == SHARE}
    outside = sorted((k, v) for k, v in shares.items() if not low <= v <= high)
    if outside:
        raise ValueError(f"{SHARE}: {len(outside)} values outside {low}-{high}, such as {outside[:3]}; the values are "
                         f"not percentages, so the declared unit is wrong")
    return {"check": f"{SHARE} lies between {low} and {high} in every row, as a share written per 100 must; the unit "
                     f"field reads '{UNITS[2153]}', so this is what declares the values percentages",
            "compared": len(shares), "lowest": min(shares.values()), "highest": max(shares.values())}


def national_within_provinces(values):
    """Layer 3: in every indicator and year, Indonesia's value lies between the lowest and the highest province value.
    A national share or average over the same workers is a weighted mean of the provinces' values, and rounding to the
    published decimals keeps that order, so the check needs no tolerance; the tables give no weights for a closer
    provinces-to-Indonesia identity."""
    results = []
    for indicator, years in YEARS.items():
        detail = {}
        for year in years:
            period = str(year)
            provinces = {c: v for (c, i, p), v in values.items()
                         if i == indicator and p == period and c != cleaning.NATIONAL_CODE}
            national = values[(cleaning.NATIONAL_CODE, indicator, period)]
            low, high = min(provinces, key=provinces.get), max(provinces, key=provinces.get)
            if not provinces[low] <= national <= provinces[high]:
                raise ValueError(f"{indicator} {period}: Indonesia's {national} lies outside the provinces' "
                                 f"{provinces[low]} ({low}) to {provinces[high]} ({high})")
            detail[period] = {"indonesia": national, "lowest": [low, provinces[low]],
                              "highest": [high, provinces[high]], "provinces": len(provinces)}
        results.append({"check": f"{indicator}: Indonesia (00) lies between the lowest and the highest province value, "
                                 f"every year", "compared": len(detail), "tolerance": 0,
                        "tolerance_reason": "rounding to the published decimals cannot move a weighted mean outside "
                                            "the rounded lowest and highest values", "years": detail})
    return results


def plausibility(values):
    """Layer 5: every value, and every change from the same region's value the year before, inside its stated range.
    Returns the flags, the values each check read, and the changes left out at a border change."""
    read = {check: [] for check in PLAUSIBLE}
    skipped = []
    for (code, indicator, period), value in sorted(values.items()):
        read[indicator].append({"province_code": code, "indicator": indicator, "period": period, "value": value})
        before = values.get((code, indicator, str(int(period) - 1)))
        if before is None:
            continue

        # A change across a border change compares different areas, so it is listed and left out
        if (code, int(period)) in BORDER_CHANGES:
            split = BORDER_CHANGES[(code, int(period))]
            own = "has its" if len(split) == 1 else "have their"
            skipped.append({"province_code": code, "indicator": indicator, "period": period,
                            "reason": f"{code} in {int(period) - 1} includes {and_list(split)}, which {own} own values "
                                      f"from {period}, so the change compares different areas"})
            continue
        pair = {"from_period": str(int(period) - 1), "values": {str(int(period) - 1): before, period: value}}
        if indicator == SHARE:
            read[f"{SHARE}_change"].append({"province_code": code, "indicator": indicator, "period": period, **pair,
                                            "value": round(value - before, 2)})
        elif before > 0:
            # A change from a wage that is not positive has no rate; the value range flags that wage
            read[f"{WAGE}_change_pct"].append({"province_code": code, "indicator": indicator, "period": period, **pair,
                                               "value": (value / before - 1) * 100})
    flags = [f for check, (low, high) in PLAUSIBLE.items()
             for f in cleaning.flag_outside(read[check], check, low, high)]
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


def describe_var(var, table):
    """Describe one WebAPI table for the metadata: role, label, subject, unit, breakdowns, release, note and files."""
    v = table["var"][0]
    first, last = YEAR_RANGES[var][0][0], YEAR_RANGES[var][-1][1]
    return {
        "role": f"gives every {INDICATORS[var]} value in the CSV",
        "label": v["label"],
        "subject": table["subject"],
        "collection": v["subj"],
        "sdg_indicator": f"{SDG_INDICATORS[var]}, as the download script's comments name it; the raw files name only "
                         f"the collection '{v['subj']}'",
        "unit": v["unit"],
        "decimals": v["decimal"],
        "definition": "none: the table's definition field ('def') is empty",
        "turvar": {str(t["val"]): t["label"] for t in table["turvar"]},
        "turtahun": {str(t["val"]): t["label"] for t in table["turtahun"]},
        "regions": table["labelvervar"],
        "years": f"{first}-{last}",
        "last_update": table["last_update"],
        "note": cleaning.html_to_text(v["note"]),
        "note_clauses": NOTE_CLAUSES[var],
        "note_statuses": {str(year): mark for year, mark in NOTE_STATUS[var].items()},
        "request": URL_WEBAPI.format(var=var) + f" (th = first:last year minus 1900, such as "
                                                f"{YEAR_RANGES[var][0][0] - 1900}:{YEAR_RANGES[var][0][1] - 1900} for "
                                                f"{YEAR_RANGES[var][0][0]}-{YEAR_RANGES[var][0][1]}; the key is not "
                                                f"stored)",
        "download_script": RAW_DOWNLOAD_SCRIPT,
        "files": [posix(p) for p in RAW_WEBAPI[var].values()],
    }


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

# Stop unless the download script the metadata names is in the repository, and raw/labour holds exactly the declared
# files of each var
if not (ROOT / RAW_DOWNLOAD_SCRIPT).is_file():
    raise FileNotFoundError(f"download script {RAW_DOWNLOAD_SCRIPT} not found")
for var, files in RAW_WEBAPI.items():
    found = sorted(RAW_DIR.glob(f"20261104_bps-api-var{var}-*.json"))
    if found != sorted(files.values()):
        raise ValueError(f"var {var}: raw/labour holds {[p.name for p in found]}, expected the declared files")

# Read both vars into one description and one value map each
tables, values = {}, {}
for var in INDICATORS:
    tables[var], cells = read_var(var, lookup, codes)
    values.update(cells)

# Each note must still read clause for clause as declared and state exactly the declared statuses; every row takes the
# status its var's note gives its year, and is final (empty) otherwise
for var, table in tables.items():
    note = table["var"][0]["note"]
    if note_clauses(note) != NOTE_CLAUSES[var]:
        raise ValueError(f"var {var} note now reads {note_clauses(note)}, the script declares {NOTE_CLAUSES[var]}")
    if note_statuses(note) != NOTE_STATUS[var]:
        raise ValueError(f"var {var} note gives {note_statuses(note)}, the script declares {NOTE_STATUS[var]}")
if REVISED not in cleaning.BPS_STATUS:
    raise ValueError(f"BPS_STATUS has no marker {REVISED!r} for revised figures")
rows = [{"province_code": c, "indicator": i, "period": p, "status": NOTE_STATUS[VAR_OF[i]].get(int(p), ""), "value": v}
        for (c, i, p), v in values.items()]

# Unit (layer 1): every informal share lies between 0 and 100, which is what declares it a percentage; stops on failure
unit_check = check_percent(values)

# Layer 3: Indonesia lies between the lowest and highest province in every indicator and year; stops on failure
identities = national_within_provinces(values)

# Layer 5: every value and every change from the year before inside its stated range; outliers are only flagged
flags, read, skipped = plausibility(values)
seen = observed(read)

# Statements for the metadata, written from the values and declarations so that they cannot go stale
papua = {(c, p): values[(c, SHARE, p)] for c, p in [("94", "2023"), ("94", "2024"), ("96", "2024"), ("97", "2024")]}
revised_years = f"{min(NOTE_STATUS[1172])}-{max(NOTE_STATUS[1172])}"
new_codes = and_list(list(FIRST_YEAR))
first_new = min(FIRST_YEAR.values())

# Describe the dataset
meta = {
    "title": f"BPS informal employment share ({YEARS[SHARE][0]}-{YEARS[SHARE][-1]}) and average hourly wage "
             f"({YEARS[WAGE][0]}-{YEARS[WAGE][-1]}) by province, Indonesia",
    "columns": {
        "province_code": "BPS province code (kode_bps); 00 = Indonesia. Names and Kemendagri codes in 'provinces'.",
        "indicator": "Indicator code; definitions in 'indicators'.",
        "period": "YYYY, the year BPS gives the value for. Both tables label their one sub-period 'Tahun' (year), and "
                  "their notes name the source only as 'Sumber: Sakernas, BPS'; neither states which Sakernas round "
                  "(February or August) a value comes from, so periods are written YYYY, not YYYYS1 or YYYYS2.",
        "status": f"Revision marker from the table note: '{REVISED}' (revised) on every {WAGE} row of {revised_years}, "
                  f"which the var 1172 note states are revised figures ('{NOTE_CLAUSES[1172][1]}'); empty (final, no "
                  f"marker) on every other row. Meanings in 'status'.",
        "value": f"{SHARE}: percent of employment, 2 decimals; {WAGE}: Rupiah per hour, 0 decimals; both as published "
                 f"by BPS. Multiply by 'multiplier' for base units.",
    },
    "provinces": provinces,
    "province_source": {"url": URL_PROVINCES, "file": posix(RAW_PROVINCES),
                        "note": "BPS and Kemendagri codes differ for the six Papua provinces; join other datasets on "
                                "the code system they use. Every region label in both tables matches the BPS list "
                                "after cleaning.normalise_name, so no alias is declared."},
    "indicators": {
        SHARE: {
            **INDICATOR_INFO[SHARE],
            "decimals": tables[2153]["var"][0]["decimal"],
            "periods": f"{YEARS[SHARE][0]}-{YEARS[SHARE][-1]}, yearly",
            "unit_reading": f"The table's unit field reads '{UNITS[2153]}' (no unit). Its label calls the value a "
                            f"proportion (Proporsi) of informal employment (lapangan kerja informal), and every value "
                            f"lies between {PERCENT_BOUNDS[0]} and {PERCENT_BOUNDS[1]} with at most 2 decimals "
                            f"(checks.unit, which stops the build otherwise), so the values are read as percent of "
                            f"employment.",
            "definition": "The table gives none (its definition field is empty), so which jobs BPS counts as informal "
                          "is not stated in the raw files.",
            "source": f"BPS WebAPI var 2153 '{VAR_LABELS[2153]}', from Sakernas; see 'source_tables'",
            "download_script": RAW_DOWNLOAD_SCRIPT,
        },
        WAGE: {
            **INDICATOR_INFO[WAGE],
            "decimals": tables[1172]["var"][0]["decimal"],
            "periods": f"{YEARS[WAGE][0]}-{YEARS[WAGE][-1]}, yearly",
            "price_basis": "The table names no price base or deflator; values are the rupiah of each year as "
                           "published.",
            "definition": "The table gives none (its definition field is empty), so who counts as a worker (pekerja) "
                          "and what the wage (upah) includes are not stated in the raw files.",
            "revision": f"The note states '{NOTE_CLAUSES[1172][1]}': the {revised_years} values are revised figures "
                        f"because of a change of survey weights (penimbang), and carry status '{REVISED}'. The note "
                        f"does not say which weights replaced which, or whether "
                        f"{max(NOTE_STATUS[1172]) + 1}-{YEARS[WAGE][-1]} use the same weights.",
            "source": f"BPS WebAPI var 1172 '{VAR_LABELS[1172]}', from Sakernas; see 'source_tables'",
            "download_script": RAW_DOWNLOAD_SCRIPT,
        },
    },
    "periods": {
        "held": PERIODS,
        "by_indicator": {indicator: f"{years[0]}-{years[-1]}" for indicator, years in YEARS.items()},
        "survey_round": "Neither table states its Sakernas round: the one sub-period is 'Tahun' (year) and the notes "
                        "name only 'Sumber: Sakernas, BPS'. Each value is BPS's figure for the year, written YYYY.",
    },
    "coverage": {
        "years": coverage(codes),
        "first_year": {code: {"year": year, "reason": f"{provinces[code]['name']} became a province in 2022; both "
                                                      f"tables give it its own values from {year}, and {PARENT[code]} "
                                                      f"covers it before"}
                       for code, year in FIRST_YEAR.items()},
        "indonesia": f"Both tables list Indonesia (row {NATIONAL_ROW[0]} '{NATIONAL_ROW[1]}') after the 38 provinces, "
                     f"with a value in every year; it is written as code {cleaning.NATIONAL_CODE}.",
    },
    "borders": [
        f"65 (Kalimantan Utara) has its own values from the first year of each table ({YEARS[WAGE][0]} for {WAGE}, "
        f"{YEARS[SHARE][0]} for {SHARE}), so 64 (Kalimantan Timur) excludes it in every year held.",
        f"91 (Papua Barat) and 94 (Papua) up to {first_new - 1} cover the areas before the 2022 split: the tables give "
        f"{new_codes} no value before {first_new}. From {first_new}, 91 and 94 cover the provinces after the split: "
        f"Papua's (94) {SHARE} falls from {papua[('94', '2023')]:g} in 2023 to {papua[('94', '2024')]:g} in 2024, the "
        f"first year Papua Tengah (96) and Papua Pegunungan (97) have their own values, at {papua[('96', '2024')]:g} "
        f"and {papua[('97', '2024')]:g}.",
        f"Neither indicator adds across provinces. A share or an average for an area of several provinces, such as "
        f"Papua Barat before the split (91 + 92) or Papua (94 + 95 + 96 + 97), needs the employment, hours and wages "
        f"behind each value, which these tables do not give.",
        f"A change of 91 or 94 from {first_new - 1} to {first_new} compares different areas; the change checks leave "
        f"those changes out (checks.change_not_compared).",
    ],
    "source_tables": {str(var): describe_var(var, table) for var, table in tables.items()},
    "notes": [
        "No other raw file in the repository holds these values: the other wage tables in raw/labour give the average "
        "monthly net wage of employees (var 583 and the BPS static tables) and the minimum wage (var 220 and the "
        "Kemnaker datasets), which measure other things. There is no cross-source check (layer 4).",
        "Indonesia's value is BPS's own national figure, not computed here. It lies between the lowest and the highest "
        "province in every indicator and year (checks.identities), as a national share or average over the same "
        "workers must; the tables give no employment or hours weights, so no closer provinces-to-Indonesia identity "
        "can be checked.",
        f"Derived values are not stored. Change in the informal share (percentage points) = {SHARE} in t - {SHARE} in "
        f"t-1; hourly wage growth (%) = ({WAGE} in t / {WAGE} in t-1 - 1) x 100.",
        "checks.flags lists every value or change outside its range in checks.plausible_ranges for a person to review, "
        "with the two values each change compares; a flag stays whether it reflects a real event or a source error.",
    ],
    "checks": {
        "passed": ["unit", "identities", "plausibility checked (layer 5, flags listed)"],
        "unit": unit_check,
        "identities": identities,
        "cross_source": "Not applicable (layer 4): no other raw file holds these values; see 'notes'.",
        "plausible_ranges": {check: {"range": list(PLAUSIBLE[check]), "measure": PLAUSIBLE_MEASURES[check]}
                             for check in PLAUSIBLE},
        "plausibility_observed": seen,
        "change_not_compared": skipped,
        "flags": flags,
    },
}

# Layers 1, 2 and 6: check structure and completeness against the declared coverage, then write the CSV and metadata
raw_files = [RAW_PROVINCES] + [p for files in RAW_WEBAPI.values() for p in files.values()]
out = cleaning.write_dataset(
    rows, KEYS,
    allowed={"province_code": [cleaning.NATIONAL_CODE] + codes, "indicator": list(INDICATORS.values()),
             "period": PERIODS},
    expected=expected_keys(codes),
    csv_path=OUT_CSV, meta=meta, raw_files=raw_files,
    sort_orders={"indicator": list(INDICATORS.values()), "period": PERIODS},
)

# Report what was written, every check result and every plausibility flag
print(f"{OUT_CSV.name}: {len(out)} rows, {len(flags)} plausibility flags")
print(out.groupby(["indicator", "status"]).size().to_string())
print("  unit:", {k: v for k, v in unit_check.items() if k != "check"})
for check in identities:
    print("  identity:", check["check"], "-", check["compared"], "years")
print("  plausibility observed:", {k: (v["lowest"]["value"], v["highest"]["value"]) for k, v in seen.items()})
for s in skipped:
    print("  change not compared:", s["province_code"], s["indicator"], s["period"])
for f in flags:
    print("  flag:", f)
