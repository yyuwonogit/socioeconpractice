from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# Load the shared cleaning module from tools/
import sys
sys.path.insert(0, str(ROOT / "tools"))
import cleaning

# Modules for reading the table note clause by clause: html for its entities, re for its tags and line breaks
import html
import re

# Parameters

# Raw inputs: the BPS province list, and the BPS WebAPI dynamic table of domain 0000, var 2335 (Penduduk Berumur 15
# Tahun Keatas yang Bekerja Selama Seminggu Terakhir Menurut Provinsi dan Status Pekerjaan Utama), saved by the
# download script in the year ranges it requested, at most three years per request. var 2335 gives every value in
# the CSV
RAW_PROVINCES = ROOT / "raw/province-codes/20261102_bps-province-codes-2025-s1.json"
RAW_DIR = ROOT / "raw/labour"
RAW_DOWNLOAD_SCRIPT = "raw/labour/20261104_download-bps-employment-by-status-by-province.py"
VAR = 2335
YEAR_RANGES = [(2017, 2019), (2020, 2022), (2023, 2025), (2026, 2026)]
RAW_WEBAPI = {span: RAW_DIR / f"20261104_bps-api-var{VAR}-employment-by-status-by-province-{span[0]}-{span[1]}.json"
              for span in YEAR_RANGES}

# Output; the metadata JSON is written beside it with a -metadata suffix
OUT_CSV = HERE / "20261104_bps-province-employment-by-status.csv"

# How each raw file is written, read from opening all five files. The province list is UTF-8 JSON without a byte-order
# mark: 38 records whose four fields (kode_bps, nama_bps, kode_dagri, nama_dagri) are all text, so it holds no numbers,
# units or missing values. The four WebAPI files are UTF-8 JSON without a byte-order mark. Every value is a JSON
# integer with no decimal point and no thousands separator, and the unit field reads 'Orang' (persons) with decimal
# field 0. A value BPS does not publish is a key absent from datacontent: the cells the note says are hidden because
# their relative standard error is 50% or more (HIDDEN), the four new Papua provinces before 2024, and the Agustus 2026
# round, which the 2026 file lists but has no value for yet. The files hold no missing-value markers
UNIT = "Orang"
DECIMALS = 0
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
VAR_LABEL = ("Penduduk Berumur 15 Tahun Keatas yang Bekerja Selama Seminggu Terakhir Menurut Provinsi dan Status "
             "Pekerjaan Utama")
SUBJECT = [{"val": 520, "label": "Tenaga Kerja"}]
COLLECTION = "Tenaga Kerja"

# The table's breakdown (turvar): the seven statuses in the main job (status pekerjaan utama) in BPS's numbering, then
# their Total, each with its BPS label and the code this dataset writes in work_status
WORK_STATUS = {
    2086: ("1. Berusaha Sendiri", "own_account"),
    2087: ("2. Berusaha Dibantu Buruh Tidak Tetap/Pekerja Keluarga/Tidak dibayar", "employer_temporary_or_unpaid_help"),
    2088: ("3. Berusaha Dibantu Buruh Tetap dan Dibayar", "employer_permanent_paid_help"),
    2089: ("4. Buruh / Karyawan / Pegawai", "employee"),
    2090: ("5. Pekerja Bebas di Pertanian", "casual_agriculture"),
    2091: ("6. Pekerja Bebas di Non Pertanian", "casual_non_agriculture"),
    2092: ("7. Pekerja Keluarga Tak Dibayar", "unpaid_family"),
    2093: ("Total", "TOTAL"),
}
STATUS_CODE = {turvar: code for turvar, (_, code) in WORK_STATUS.items()}
STATUS_NAMES = {
    "own_account": "Berusaha sendiri (own-account worker)",
    "employer_temporary_or_unpaid_help": "Berusaha dibantu buruh tidak tetap/pekerja keluarga/tidak dibayar (employer "
                                         "helped by temporary workers or unpaid workers)",
    "employer_permanent_paid_help": "Berusaha dibantu buruh tetap dan dibayar (employer helped by permanent paid "
                                    "workers)",
    "employee": "Buruh/karyawan/pegawai (employee)",
    "casual_agriculture": "Pekerja bebas di pertanian (casual worker in agriculture)",
    "casual_non_agriculture": "Pekerja bebas di non pertanian (casual worker outside agriculture)",
    "unpaid_family": "Pekerja keluarga/tak dibayar (unpaid family worker)",
    "TOTAL": "Total (all statuses)",
}
PARTS = [code for code in STATUS_CODE.values() if code != "TOTAL"]

# The table's two sub-periods (turtahun), the Sakernas rounds, with their BPS labels as published ('Februari ' ends in
# a space) and the half-year each is written as: Februari as S1, Agustus as S2
ROUNDS = {254: ("Februari ", "S1"), 255: ("Agustus", "S2")}

# The name of the table's region list, and the row BPS lists after the 38 provinces, Indonesia
LABEL_VERVAR = "38 Provinsi"
NATIONAL_ROW = (9999, "INDONESIA")

# The table's note, line by line (empty lines dropped); the build stops if it changes. It names the survey, says that
# some values have a relative standard error (RSE) of 25-50% and that an empty cell has an RSE of 50% or more and is
# not shown, and defines the industry (lapangan usaha, KBLI 2025), which this table does not break down by. It states
# no revision status, and the definition field is empty
NOTE_CLAUSES = [
    "Catatan:",
    "1. Beberapa angka memiliki nilai Kesalahan Baku Relatif (Relative Standard Error/RSE) dalam rentang 25%≤ "
    "RSE ≤ 50%. Informasi lebih lanjut dapat dilihat pada Publikasi Statistik Pendapatan Februari dan Agustus 2026.",
    "2. Data yang kosong menandakan bahwa nilai RSE ≥ 50%, sehingga data tidak ditampilkan",
    "3. Lapangan usaha adalah bidang kegiatan dari pekerjaan/usaha/ perusahaan/kantor tempat seseorang bekerja. "
    "Lapangan usaha pada publikasi ini didasarkan pada KBLI 2025.",
    "Sumber: Survei Angkatan Kerja Nasional (Sakernas) Februari dan Agustus 2025",
]

# Output indicator, with its name, unit and multiplier to base units
INDICATOR = "employed_persons"
INDICATOR_INFO = {"name": "Penduduk berumur 15 tahun ke atas yang bekerja selama seminggu terakhir (persons aged 15 "
                          "and over who worked in the past week), by status in the main job",
                  "unit": "persons (Orang)", "multiplier": 1, "base_unit": "persons"}

# Periods held: both rounds of 2017-2025 and the Februari round of 2026; the 2026 file lists Agustus but holds no value
# for it
YEARS = range(2017, 2027)
PERIODS = [f"{year}{half}" for year in YEARS for _, half in ROUNDS.values() if f"{year}{half}" != "2026S2"]
UNPUBLISHED_ROUNDS = ["2026S2"]

# Coverage, read from opening the files: the four provinces split from Papua Barat and Papua in 2022 have values from
# 2024, and every other province, Kalimantan Utara (65) included, and Indonesia have values in every round
FIRST_YEAR = {"92": 2024, "95": 2024, "96": 2024, "97": 2024}
PARENT = {"92": "91", "95": "94", "96": "94", "97": "94"}

# Cells BPS leaves empty because their relative standard error is 50% or more (note line 2), read from opening the
# files: province, status and the rounds without a value. Each is a gap the completeness check allows, and any other
# absent cell stops the build
HIDDEN = {
    ("31", "casual_agriculture"): ["2018S1", "2021S1", "2023S1", "2025S1", "2025S2", "2026S1"],
    ("81", "casual_agriculture"): ["2026S1"],
    ("91", "casual_agriculture"): ["2025S1"],
    ("92", "casual_agriculture"): ["2025S1", "2026S1"],
    ("92", "casual_non_agriculture"): ["2025S1"],
    ("94", "casual_agriculture"): ["2025S1", "2026S1"],
    ("97", "employer_permanent_paid_help"): ["2025S2", "2026S1"],
    ("97", "casual_agriculture"): ["2025S1", "2025S2", "2026S1"],
    ("97", "casual_non_agriculture"): ["2025S1", "2025S2", "2026S1"],
}

# Layer 3, read from opening the files: in every round of 2017-2025 the seven statuses add to Total in every region,
# and the provinces add to Indonesia in every status, to the person. A region or status with hidden cells can only be
# checked one way: the published parts must not exceed the total. The Februari 2026 round does not add up: in ten
# provinces the published statuses exceed Total, and in three statuses the provinces exceed Indonesia. These are BPS's
# own gaps, kept as published and declared here to the person (Total - published statuses, and Indonesia - published
# provinces); any other gap stops the build
SUM_TOLERANCE = 0
KNOWN_GAPS_STATUSES = {("21", "2026S1"): -373468, ("51", "2026S1"): -598052, ("65", "2026S1"): -228730,
                       ("81", "2026S1"): -202788, ("82", "2026S1"): -57215, ("91", "2026S1"): -156615,
                       ("92", "2026S1"): -153886, ("94", "2026S1"): -79038, ("95", "2026S1"): -41458,
                       ("96", "2026S1"): -89088}
KNOWN_GAPS_PROVINCES = {("employer_permanent_paid_help", "2026S1"): -494698,
                        ("casual_agriculture", "2026S1"): -869515, ("casual_non_agriculture", "2026S1"): -608750}

# Provinces whose area changes, keyed by the first year on the new borders, with the provinces split off; a change of
# such a province from the year before compares different areas, so no change check reads it
BORDER_CHANGES = {("91", 2024): ["92"], ("94", 2024): ["95", "96", "97"]}

# Plausibility ranges (layer 5); a value or change outside its range is flagged for review, not dropped
PLAUSIBLE = {
    "total_change_pct": (-10, 15),
    "employee_change_pct": (-20, 30),
    "employee_share_pct": (3, 80),
}
PLAUSIBLE_MEASURES = {
    "total_change_pct": "Change of TOTAL from the same region's same round a year before, in percent ((TOTAL in t / "
                        "TOTAL in t-1 - 1) x 100). Employment grows with the working-age population and seldom moves "
                        "more than a few percent a year, so a fall of more than 10 percent or a rise of more than 15 "
                        "percent is flagged for review.",
    "employee_change_pct": "Change of employee from the same region's same round a year before, in percent. Employees "
                           "are a sample estimate that moves more than all employment in a small province, so only a "
                           "fall of more than 20 percent or a rise of more than 30 percent is flagged for review.",
    "employee_share_pct": "Employees as a percent of TOTAL in the same region and round (employee / TOTAL x 100). "
                          "Below 3 or above 80 would lie far outside the provinces' values (checks."
                          "plausibility_observed), so it is flagged for review.",
}

# Source addresses for the metadata; the WebAPI request is given without its key
URL_PROVINCES = "https://sig.bps.go.id/rest-bridging/getwilayah?level=provinsi&periode_merge=2025_1.2025"
URL_WEBAPI = f"https://webapi.bps.go.id/v1/api/list/model/data/domain/0000/var/{VAR}/th/{{th}}/key/{{key}}"

# Key columns of this dataset
KEYS = ["province_code", "indicator", "work_status", "period"]


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
    """Stop unless the file holds the declared table: its label, subject and collection, an empty definition, the
    eight statuses and the two rounds."""
    v = table["var"][0]
    if v["label"] != VAR_LABEL or table["subject"] != SUBJECT or v["subj"] != COLLECTION:
        raise ValueError(f"{name}: label {v['label']!r}, subject {table['subject']}, collection {v['subj']!r}")

    # The metadata states that the table defines nothing, so a definition that appears must be read into it first
    if v["def"] != "":
        raise ValueError(f"{name}: the definition field now reads {v['def']!r}; read it into the metadata")
    if [(t["val"], t["label"]) for t in table["turvar"]] != [(k, label) for k, (label, _) in WORK_STATUS.items()]:
        raise ValueError(f"{name}: turvar {table['turvar']}, expected the declared statuses")
    if [(t["val"], t["label"]) for t in table["turtahun"]] != [(k, label) for k, (label, _) in ROUNDS.items()]:
        raise ValueError(f"{name}: turtahun {table['turtahun']}, expected the declared rounds")


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
    """Read every WebAPI file; return the description they share and {(code, status, period): value}."""
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

        # Each value goes to its region code (checked against the BPS list by name), status and round, once
        for r in records:
            code = cleaning.webapi_region_code(r["vervar"], r["vervar_label"], lookup)
            key = (code, STATUS_CODE[r["turvar"]], f"{r['year']}{ROUNDS[r['turtahun']][1]}")
            if key in values:
                raise ValueError(f"{path.name}: {key} read twice")
            values[key] = r["value"]

    # All files must come from one release of the table, note, unit and decimals included
    for table in tables[1:]:
        for field in ("var", "turvar", "turtahun", "vervar", "labelvervar", "subject", "last_update"):
            if table[field] != tables[0][field]:
                raise ValueError(f"var {VAR}: files differ in {field}")
    return tables[0], values


def regions_in(period, codes):
    """Return Indonesia and the provinces with their own values in a round."""
    year = int(period[:4])
    return [code for code in [cleaning.NATIONAL_CODE] + codes if year >= FIRST_YEAR.get(code, YEARS[0])]


def expected_keys(codes):
    """Every key the table should yield: each status in each round for Indonesia and every province with its own values
    then, without the declared hidden cells; the four new Papua provinces before 2024 are the only other gaps."""
    hidden = {(code, status, period) for (code, status), periods in HIDDEN.items() for period in periods}
    return {(code, INDICATOR, status, period) for period in PERIODS for code in regions_in(period, codes)
            for status in STATUS_CODE.values() if (code, status, period) not in hidden}


def coverage(codes):
    """Describe each run of rounds with the same provinces: how many have values and which are absent."""
    runs = []
    for period in PERIODS:
        absent = [code for code in codes if code not in regions_in(period, codes)]
        if runs and runs[-1]["absent"] == absent:
            runs[-1]["last"] = period
        else:
            runs.append({"first": period, "last": period, "absent": absent})
    return {f"{r['first']}-{r['last']}": {"provinces": len(codes) - len(r["absent"]), "absent": r["absent"]}
            for r in runs}


def sum_check(groups, declared, label, part_name):
    """Layer 3: in each group (key -> (total, published parts, parts expected)), the parts add to the total to the
    person when all are published, and do not exceed it when some are hidden; a declared gap must hold to the person.
    Returns the check for the metadata; any other gap stops the build."""
    exact, bounded, known = 0, 0, []
    for key, (total, parts, expected) in sorted(groups.items()):
        gap = total - sum(parts)
        if key in declared:
            if gap != declared[key]:
                raise ValueError(f"{label} {key}: gap {gap:g}, declared {declared[key]}")
            known.append({"key": list(key), "gap": gap, "published_parts": len(parts), "parts": expected})
        elif len(parts) == expected:
            if abs(gap) > SUM_TOLERANCE:
                raise ValueError(f"{label} {key}: {part_name} miss the total by {gap:g}")
            exact += 1
        else:
            if gap < 0:
                raise ValueError(f"{label} {key}: the published {part_name} exceed the total by {-gap:g}")
            bounded += 1
    undeclared = [key for key in declared if key not in groups]
    if undeclared:
        raise ValueError(f"{label}: declared gaps {undeclared} have no group to check")
    return {"check": label, "exact": exact, "tolerance": SUM_TOLERANCE,
            "bounded_by_hidden_cells": bounded, "declared_gaps": known}


def identities(values, codes):
    """Layer 3: the statuses add to TOTAL in every region and round, and the provinces add to Indonesia in every
    status and round, except BPS's declared gaps."""
    by_region, by_status = {}, {}
    for period in PERIODS:
        regions = regions_in(period, codes)
        for code in regions:
            parts = [values[(code, s, period)] for s in PARTS if (code, s, period) in values]
            by_region[(code, period)] = (values[(code, "TOTAL", period)], parts, len(PARTS))
        provinces = [code for code in regions if code != cleaning.NATIONAL_CODE]
        for status in STATUS_CODE.values():
            parts = [values[(code, status, period)] for code in provinces if (code, status, period) in values]
            by_status[(status, period)] = (values[(cleaning.NATIONAL_CODE, status, period)], parts, len(provinces))
    return [sum_check(by_region, KNOWN_GAPS_STATUSES, "the seven statuses add to TOTAL (key: region, round)",
                      "statuses"),
            sum_check(by_status, KNOWN_GAPS_PROVINCES, "the provinces add to Indonesia (key: status, round)",
                      "provinces")]


def plausibility(values):
    """Layer 5: every change from the same round a year before, and every employee share, inside its stated range.
    Returns the flags, the values each check read, and the changes left out at a border change."""
    read = {check: [] for check in PLAUSIBLE}
    skipped = []
    for (code, status, period), value in sorted(values.items()):
        if status not in ("TOTAL", "employee"):
            continue
        if status == "employee" and (code, "TOTAL", period) in values:
            read["employee_share_pct"].append({"province_code": code, "period": period,
                                               "value": value / values[(code, "TOTAL", period)] * 100})
        before_period = f"{int(period[:4]) - 1}{period[4:]}"
        before = values.get((code, status, before_period))
        if before is None:
            continue

        # A change across a border change compares different areas, so it is listed and left out
        if (code, int(period[:4])) in BORDER_CHANGES:
            split = BORDER_CHANGES[(code, int(period[:4]))]
            own = "has its" if len(split) == 1 else "have their"
            skipped.append({"province_code": code, "work_status": status, "period": period,
                            "reason": f"{code} in {before_period} includes {and_list(split)}, which {own} own values "
                                      f"from {period[:4]}, so the change compares different areas"})
            continue
        check = "total_change_pct" if status == "TOTAL" else "employee_change_pct"
        if before > 0:
            read[check].append({"province_code": code, "period": period, "from_period": before_period,
                                "persons": {before_period: before, period: value},
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
# files of the var
if not (ROOT / RAW_DOWNLOAD_SCRIPT).is_file():
    raise FileNotFoundError(f"download script {RAW_DOWNLOAD_SCRIPT} not found")
found = sorted(RAW_DIR.glob(f"20261104_bps-api-var{VAR}-*.json"))
if found != sorted(RAW_WEBAPI.values()):
    raise ValueError(f"var {VAR}: raw/labour holds {[p.name for p in found]}, expected the declared files")

# Read every file into one description and one value map
table, values = read_files(lookup, codes)

# The note must still read line for line as declared and state no revision status, so every row is final (empty)
note = table["var"][0]["note"]
if note_clauses(note) != NOTE_CLAUSES:
    raise ValueError(f"var {VAR} note now reads {note_clauses(note)}, the script declares {NOTE_CLAUSES}")
if cleaning.parse_status_note(note):
    raise ValueError(f"var {VAR} note now states revision statuses {cleaning.parse_status_note(note)}")
if any(period in UNPUBLISHED_ROUNDS for _, _, period in values):
    raise ValueError(f"a round declared unpublished ({UNPUBLISHED_ROUNDS}) now has values; add it to PERIODS")
rows = [{"province_code": c, "indicator": INDICATOR, "work_status": s, "period": p, "status": "", "value": v}
        for (c, s, p), v in values.items()]

# Layer 3: the statuses add to TOTAL and the provinces to Indonesia, except BPS's declared gaps; stops on failure
sums = identities(values, codes)

# Layer 5: every change from the year before and every employee share inside its stated range; outliers are only
# flagged
flags, read, skipped = plausibility(values)
seen = observed(read)

# Statements for the metadata, written from the declarations so that they cannot go stale
hidden_count = sum(len(periods) for periods in HIDDEN.values())
new_codes = and_list(list(FIRST_YEAR))
first_new = min(FIRST_YEAR.values())
v = table["var"][0]

# Describe the dataset
meta = {
    "title": f"BPS employed persons by status in the main job, by province, Sakernas Februari and Agustus rounds, "
             f"{PERIODS[0]}-{PERIODS[-1]}, Indonesia",
    "columns": {
        "province_code": "BPS province code (kode_bps); 00 = Indonesia. Names and Kemendagri codes in 'provinces'.",
        "indicator": "Indicator code; definition in 'indicators'.",
        "work_status": "Status in the main job (status pekerjaan utama), BPS's seven statuses and their TOTAL; names "
                       "in 'work_status'.",
        "period": "YYYYS1 = the Februari round of Sakernas in year YYYY, YYYYS2 = the Agustus round (see 'periods').",
        "status": "Revision marker; the table note states none, so every row is empty (final).",
        "value": "Persons (Orang), whole persons as BPS publishes them. Multiply by 'multiplier' for base units.",
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
            "periods": f"{PERIODS[0]}-{PERIODS[-1]}, two rounds a year (Februari and Agustus); 2026 has the Februari "
                       f"round only",
            "definition": "The table's definition field is empty; its label defines the count: persons aged 15 and "
                          "over who worked during the past week (yang bekerja selama seminggu terakhir), by status "
                          "in their main job.",
            "source": f"BPS WebAPI var {VAR} '{VAR_LABEL}', from Sakernas; see 'source_table'",
            "download_script": RAW_DOWNLOAD_SCRIPT,
        },
    },
    "work_status": {code: {"name": STATUS_NAMES[code], "bps_label": label, "turvar": turvar}
                    for turvar, (label, code) in WORK_STATUS.items()},
    "periods": {
        "held": PERIODS,
        "rounds": {half: {"turtahun": turtahun, "bps_label": label} for turtahun, (label, half) in ROUNDS.items()},
        "not_published": f"{and_list(UNPUBLISHED_ROUNDS)}: the 2026 file lists the Agustus round (turtahun 255) but "
                         f"holds no value for it.",
    },
    "coverage": {
        "rounds": coverage(codes),
        "first_year": {code: {"year": year, "reason": f"{provinces[code]['name']} became a province in 2022; the "
                                                      f"table gives it its own values from {year}, and "
                                                      f"{PARENT[code]} covers it before"}
                       for code, year in FIRST_YEAR.items()},
        "hidden_cells": {
            "reason": f"Note line 2: '{NOTE_CLAUSES[2]}' (an empty cell has a relative standard error of 50% or more "
                      f"and is not shown). {hidden_count} cells are empty for this reason; each has no row.",
            "cells": {f"{code} {status}": periods for (code, status), periods in HIDDEN.items()},
        },
        "indonesia": f"The table lists Indonesia (row {NATIONAL_ROW[0]} '{NATIONAL_ROW[1]}') after the 38 provinces, "
                     f"with a value in every status and round; it is written as code {cleaning.NATIONAL_CODE}.",
    },
    "borders": [
        "65 (Kalimantan Utara) has its own values in every round held, so 64 (Kalimantan Timur) excludes it.",
        f"91 (Papua Barat) and 94 (Papua) up to {first_new - 1} cover the areas before the 2022 split: the table gives "
        f"{new_codes} no value before {first_new}. From {first_new}, 91 and 94 cover the provinces after the split.",
        "Counts add across provinces, so an area of several provinces, such as Papua Barat before the split (91 + 92) "
        "or Papua (94 + 95 + 96 + 97), is the sum of its provinces' values from 2024, except where a cell is hidden.",
        f"A change of 91 or 94 from {first_new - 1} to {first_new} compares different areas; the change checks leave "
        f"those changes out (checks.change_not_compared).",
    ],
    "source_table": {
        "role": "gives every value in the CSV",
        "label": v["label"],
        "subject": table["subject"],
        "collection": v["subj"],
        "unit": v["unit"],
        "decimals": v["decimal"],
        "definition": "none: the table's definition field ('def') is empty",
        "turvar": {str(t["val"]): t["label"] for t in table["turvar"]},
        "turtahun": {str(t["val"]): t["label"] for t in table["turtahun"]},
        "regions": table["labelvervar"],
        "years": f"{YEAR_RANGES[0][0]}-{YEAR_RANGES[-1][1]}",
        "last_update": table["last_update"],
        "note": cleaning.html_to_text(v["note"]),
        "note_clauses": NOTE_CLAUSES,
        "note_reading": "The note's source line names only the 2025 rounds and its publication line the 2026 "
                        "publication, though the table holds 2017-2026; its third line defines industry (lapangan "
                        "usaha, KBLI 2025), a breakdown this table does not have. All four files carry the same note "
                        "and release date. The note states no revision status.",
        "request": URL_WEBAPI + f" (th = first:last year minus 1900, such as {YEAR_RANGES[0][0] - 1900}:"
                                f"{YEAR_RANGES[0][1] - 1900} for {YEAR_RANGES[0][0]}-{YEAR_RANGES[0][1]}; the key "
                                f"is not stored)",
        "download_script": RAW_DOWNLOAD_SCRIPT,
        "files": [posix(p) for p in RAW_WEBAPI.values()],
    },
    "notes": [
        "No other raw file in the repository holds these counts, so there is no cross-source check (layer 4).",
        "Indonesia's values are BPS's own national figures, not computed here; the provinces add to them to the person "
        "in every status and round of 2017-2025 (checks.identities).",
        "The Februari 2026 round does not add up: in ten provinces the published statuses exceed TOTAL, and in three "
        "statuses the provinces exceed Indonesia, by up to 869,515 persons. The values are kept as published and the "
        "gaps declared (checks.identities, declared_gaps); a later BPS release is filed as a new raw file.",
        "Derived values are not stored. Share of a status in employment (%) = status / TOTAL x 100; change from the "
        "same round a year before (%) = (value in t / value in t-1 - 1) x 100.",
        "checks.flags lists every value or change outside its range in checks.plausible_ranges for a person to review; "
        "a flag stays whether it reflects a real event or a source error.",
    ],
    "checks": {
        "passed": ["identities", "plausibility checked (layer 5, flags listed)"],
        "identities": sums,
        "cross_source": "Not applicable (layer 4): no other raw file holds these values; see 'notes'.",
        "plausible_ranges": {check: {"range": list(PLAUSIBLE[check]), "measure": PLAUSIBLE_MEASURES[check]}
                             for check in PLAUSIBLE},
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
             "work_status": list(STATUS_CODE.values()), "period": PERIODS},
    expected=expected_keys(codes),
    csv_path=OUT_CSV, meta=meta, raw_files=raw_files,
    sort_orders={"work_status": list(STATUS_CODE.values()), "period": PERIODS},
)

# Report what was written, every check result and every plausibility flag
print(f"{OUT_CSV.name}: {len(out)} rows, {len(flags)} plausibility flags, {hidden_count} hidden cells")
for check in sums:
    print(f"  identity: {check['check']} - exact {check['exact']}, bounded {check['bounded_by_hidden_cells']}, "
          f"declared gaps {len(check['declared_gaps'])}")
print("  plausibility observed:", {k: (v["lowest"]["value"], v["highest"]["value"]) for k, v in seen.items()})
for s in skipped:
    print("  change not compared:", s["province_code"], s["work_status"], s["period"])
for f in flags:
    print("  flag:", f)
