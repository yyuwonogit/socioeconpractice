"""Shared cleaning and checking for every build script in data/.

README.md, section Cleaning and checking, sets the rules this module enforces. A build script
imports it, parses its own raw files into long rows with these functions, and calls
write_dataset, which runs the checks and writes nothing unless they pass.
"""

import csv
import hashlib
import html
import json
import re
from decimal import Decimal
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

# Output format shared by every dataset
CSV_FORMAT = {
    "encoding": "UTF-8, no byte-order mark",
    "delimiter": ",",
    "decimal": ".",
    "thousands_separator": None,
    "missing": "a missing row means the source has no value; no placeholder values are written",
    "layout": "one value per row: key columns, then status, then value",
}

# BPS cell markers (keterangan data) and their meaning
BPS_STATUS = {
    "": "final, or no marker in the source",
    "*": "Angka sementara (preliminary)",
    "**": "Angka sangat sementara (very preliminary)",
    "***": "Angka sangat sangat sementara (very, very preliminary)",
    "e": "Angka estimasi (estimate)",
    "r": "Angka diperbaiki (revised)",
}

# BPS precision markers on survey estimates (Sakernas, Susenas), written in status like revision markers
BPS_STATUS["rse25-50"] = "Kesalahan baku relatif 25% <= RSE <= 50% (relative standard error between 25% and 50%; use with caution)"

# BPS markers that mean no value is published, so no row is written
BPS_NO_VALUE = {"...", "NA", "–", "-", "x"}

# Indonesia has no entry in the BPS province list
NATIONAL_CODE = "00"


# Reading numbers

def number_pattern(decimal, thousands):
    """Return a regex for a number written with the given decimal mark and thousands separator."""
    d, t = re.escape(decimal), re.escape(thousands) if thousands else None
    integer = rf"\d{{1,3}}({t}\d{{3}})*" if t else r"\d+"
    return re.compile(rf"^-?{integer}({d}\d+)?$")


def parse_number(text, decimal=".", thousands=None, decimals=None, max_decimals=None, shift=0):
    """Turn a published number string into a float.

    Stops on any text that does not match the declared decimal mark and thousands separator,
    so 1.234,5 written in Indonesian style is never read as 1.2345. When decimals is given,
    the number of digits after the decimal mark must equal it; when max_decimals is given, it
    must not exceed it (JSON drops trailing zeros). shift moves the decimal point exactly, as
    in -3 for a value published in Juta Rupiah and written in Milyar Rupiah.
    """
    text = str(text).strip()
    if not number_pattern(decimal, thousands).match(text):
        raise ValueError(f"{text!r} does not match decimal {decimal!r}, thousands {thousands!r}")
    found = len(text.split(decimal)[1]) if decimal in text else 0
    if decimals is not None and found != decimals:
        raise ValueError(f"{text!r} has {found} decimals, source declares {decimals}")
    if max_decimals is not None and found > max_decimals:
        raise ValueError(f"{text!r} has {found} decimals, source declares at most {max_decimals}")
    if thousands:
        text = text.replace(thousands, "")
    return float(Decimal(text.replace(decimal, ".")).scaleb(shift))


def parse_cell(value, missing=()):
    """Turn an Excel cell into a float, or None for a declared missing marker."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if value in missing:
        return None
    raise ValueError(f"unexpected cell {value!r}")


def read_csv_rows(path, encoding, delimiter):
    """Read a raw CSV with its declared encoding and field separator."""
    with open(path, encoding=encoding, newline="") as f:
        return list(csv.reader(f, delimiter=delimiter))


def require_text(haystack, needle, where):
    """Stop unless a header or note still carries the text the build script declared."""
    if needle not in (haystack or ""):
        raise ValueError(f"{where}: expected {needle!r} in {haystack!r}")


def html_to_text(s):
    """Strip tags and entities from BPS note HTML and collapse whitespace."""
    s = html.unescape(html.unescape(s or ""))
    s = re.sub(r"<sup>\s*\(?(\d+)\)?\s*</sup>", r"(\1) ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    return " ".join(s.split())


# Regions

def normalise_name(name):
    """Return a region name in the BPS reference spelling: upper case, KEP. spelled out, D I and D.I. as DI, single spaces."""
    name = " ".join(str(name).upper().split())
    name = re.sub(r"^D\.? ?I\.? (?=YOGYAKARTA)", "DI ", name)
    return re.sub(r"^KEP\. ", "KEPULAUAN ", name)


def load_bps_provinces(path):
    """Read the BPS province list from raw/province-codes and return code -> record and name -> code."""
    records = json.loads(Path(path).read_text(encoding="utf-8"))
    provinces = {r["kode_bps"]: {"name": r["nama_bps"], "kode_dagri": r["kode_dagri"]} for r in records}
    provinces[NATIONAL_CODE] = {"name": "INDONESIA", "kode_dagri": None}
    lookup = {normalise_name(p["name"]): code for code, p in provinces.items()}
    return provinces, lookup


# English province names, as in English-language reports and templates: a direction word before
# the name, "Islands" after it, English spellings of Sumatra and Java, and two names that follow no rule
ENGLISH_DIRECTIONS = {"NORTH": "UTARA", "SOUTH": "SELATAN", "WEST": "BARAT", "EAST": "TIMUR", "CENTRAL": "TENGAH",
                      "SOUTHEAST": "TENGGARA", "SOUTHWEST": "BARAT DAYA", "HIGHLAND": "PEGUNUNGAN"}
ENGLISH_WORDS = {"SUMATRA": "SUMATERA", "JAVA": "JAWA"}
ENGLISH_NAMES = {"JAKARTA SPECIAL CAPITAL REGION": "DKI JAKARTA", "SPECIAL REGION OF YOGYAKARTA": "DI YOGYAKARTA"}


def english_to_bps_name(name):
    """Return the BPS spelling of an English province name, for matching with province_code.

    North Sumatra -> SUMATERA UTARA, Bangka Belitung Islands -> KEPULAUAN BANGKA BELITUNG,
    Highland Papua -> PAPUA PEGUNUNGAN. The result is not checked here; province_code stops on a
    name that is not in the BPS list.
    """
    name = " ".join(str(name).upper().split())
    if name in ENGLISH_NAMES:
        return ENGLISH_NAMES[name]
    words = name.split()
    islands = len(words) > 1 and words[-1] == "ISLANDS"
    if islands:
        words = words[:-1]
    direction = ENGLISH_DIRECTIONS.get(words[0]) if len(words) > 1 else None
    if direction:
        words = words[1:]
    words = [ENGLISH_WORDS.get(w, w) for w in words]
    return " ".join((["KEPULAUAN"] if islands else []) + words + ([direction] if direction else []))


def province_code(name, lookup, code_in_source=None):
    """Return the BPS code for a name, and stop if the source's own code disagrees with it."""
    code = lookup.get(normalise_name(name))
    if code is None:
        raise KeyError(f"province {name!r} is not in the BPS province list")
    if code_in_source is not None and code != code_in_source:
        raise ValueError(f"{name!r}: source code {code_in_source} but BPS list code {code}")
    return code


# BPS website pages (Next.js flight data)

def bps_flight_text(path):
    """Return the data stream embedded in a saved bps.go.id table page."""
    page = Path(path).read_text(encoding="utf-8")
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', page)
    return "".join(json.loads('"' + c + '"') for c in chunks)


def bps_find_object(text, keys):
    """Return the first JSON object in the stream that has all the given keys."""
    decoder = json.JSONDecoder()
    for m in re.finditer(r"\{", text):
        try:
            obj, _ = decoder.raw_decode(text, m.start())
        except ValueError:
            continue
        if isinstance(obj, dict) and all(k in obj for k in keys):
            return obj
    raise ValueError(f"no object with keys {keys}")


def bps_resolve(text, value):
    """Resolve a "$id" reference in the stream to the text chunk it points to."""
    if not (isinstance(value, str) and re.fullmatch(r"\$[0-9a-f]+", value)):
        return value
    m = re.search(rf"(?:^|\n){value[1:]}:T([0-9a-f]+),", text)
    if not m:
        raise ValueError(f"reference {value} not found")
    data = text[m.end():].encode("utf-8")[: int(m.group(1), 16)]
    return data.decode("utf-8")


# BPS WebAPI responses

# BPS publication PDFs (read with pdfplumber)

# Fill colours that make text invisible on a white page: grey, RGB and CMYK white
WHITE_FILLS = {(1.0,), (1.0, 1.0, 1.0), (0.0, 0.0, 0.0, 0.0)}


def pdf_visible_lines(page, line_tolerance=4):
    """Return the text lines a reader sees on a pdfplumber page, top to bottom.

    BPS publication pages carry a rotated "https://www.bps.go.id" watermark whose letters fall
    between table digits, and some carry white text left over from an earlier edition. Both are
    dropped. Each line is a list of words (text, x0, x1, top, size) from left to right; words in a
    smaller font, such as footnote markers, join the line they sit on.
    """
    def visible(obj):
        if obj.get("object_type") != "char":
            return True
        m = obj.get("matrix")
        if m is not None and (abs(m[1]) > 1e-6 or abs(m[2]) > 1e-6):
            return False
        fill = obj.get("non_stroking_color")
        return fill is None or tuple(round(float(c), 3) for c in fill) not in WHITE_FILLS

    words = page.filter(visible).extract_words(extra_attrs=["size"], keep_blank_chars=False)
    if not words:
        return []
    main = max({round(w["size"], 1) for w in words}, key=lambda s: sum(round(w["size"], 1) == s for w in words))
    lines = []
    for w in sorted((w for w in words if round(w["size"], 1) == main), key=lambda w: (w["top"], w["x0"])):
        if lines and abs(w["top"] - lines[-1][0]["top"]) <= line_tolerance:
            lines[-1].append(w)
        else:
            lines.append([w])
    for w in (w for w in words if round(w["size"], 1) != main):
        near = [line for line in lines if line[0]["top"] - line_tolerance <= w["top"] <= line[0]["bottom"]]
        if near:
            near[0].append(w)
        else:
            lines.append([w])
    lines.sort(key=lambda line: min(x["top"] for x in line))
    return [[{"text": x["text"], "x0": x["x0"], "x1": x["x1"], "top": x["top"], "size": round(x["size"], 1)}
             for x in sorted(line, key=lambda x: x["x0"])] for line in lines]


def bps_report_province_table(pdf, pages, lookup, marker_status, marker_text, no_value=("NA",), cell_fixes=None,
                              decimal=",", thousands=".", decimals=0, national_label="Jumlah", max_marker_size=7.5):
    """Read a province table from a BPS report PDF into cells, by name and column order.

    pages: page number -> the column codes its value cells hold, left to right.
    Each data line is a province name (matched to a BPS code) or, after a line reading national_label,
    an unlabelled line of numbers for Indonesia. A small superscript marker_text after a value sets
    that value's status to marker_status. Lines whose label is not a province name (headers, page
    numbers) are skipped, so the caller must check every province is present. Cells in no_value (such as NA) give no value and are
    returned as gaps. cell_fixes: (province name as printed, column) -> (printed text, corrected text)
    for a value the report prints wrongly; each fix must be used and its printed text must still match.
    Returns cells (province_code, column, value, status) and gaps (province_code, column, marker).
    A labelled line with the wrong number of values stops the read.
    """
    fixes = dict(cell_fixes or {})
    cells, gaps, seen = [], [], set()
    token = re.compile(r"^[\d.,]+$")
    for number, columns in pages.items():
        national_next = False
        for line in pdf_visible_lines(pdf.pages[number - 1]):
            big = [w for w in line if w["size"] > max_marker_size]
            label = " ".join(w["text"] for w in big if not token.match(w["text"]) and w["text"] not in no_value)
            if label == national_label:
                national_next = True
                continue
            values = []
            for w in line:
                if w["size"] <= max_marker_size:
                    if values:
                        if w["text"] != marker_text or values[-1][1]:
                            raise ValueError(f"page {number}: unexpected small text {w['text']!r} after a value")
                        values[-1][1] = marker_status
                elif token.match(w["text"]) or w["text"] in no_value:
                    values.append([w["text"], ""])
            if not values:
                continue
            if label == "":
                if not national_next:
                    continue
                code, name, national_next = NATIONAL_CODE, national_label, False
            elif normalise_name(label) in lookup:
                code, name = province_code(label, lookup), label
            else:
                # Headers and page numbers; a missing province is caught by the caller's completeness check
                continue
            if len(values) != len(columns):
                raise ValueError(f"page {number}: {label!r} has {len(values)} values for {len(columns)} columns")
            for column, (text, status) in zip(columns, values):
                if (code, column) in seen:
                    raise ValueError(f"page {number}: {name} {column} read twice")
                seen.add((code, column))
                if text in no_value:
                    gaps.append({"province_code": code, "column": column, "marker": text})
                    continue
                if (name, column) in fixes:
                    printed, corrected = fixes.pop((name, column))
                    if text != printed:
                        raise ValueError(f"{name} {column}: declared fix expects {printed!r}, page has {text!r}")
                    text = corrected
                value = parse_number(text, decimal, thousands, decimals=decimals)
                cells.append({"province_code": code, "column": column, "value": value, "status": status})
    if fixes:
        raise ValueError(f"cell fixes not used: {fixes}")
    return cells, gaps


def read_jsonl(path):
    """Read a .jsonl file of saved responses, keeping every number as its published text."""
    with open(path, encoding="utf-8") as f:
        return [json.loads(line, parse_float=str, parse_int=str) for line in f if line.strip()]


def bps_api_cells(response):
    """Yield (vervar, turvar, tahun, turtahun, text) for every filled cell of a WebAPI data response.

    BPS keys datacontent by joining the vervar, var, turvar, tahun and turtahun codes. The function
    stops if two cells would share a key or if datacontent holds a key that matches no cell, so every
    published value is read and none is read twice.
    """
    var = response["var"][0]["val"]
    cells = {}
    for v in response["vervar"]:
        for tv in response["turvar"]:
            for th in response["tahun"]:
                for tt in response["turtahun"]:
                    k = f"{v['val']}{var}{tv['val']}{th['val']}{tt['val']}"
                    if k in cells:
                        raise ValueError(f"datacontent key {k} fits two cells")
                    cells[k] = (v, tv, th, tt)
    unknown = set(response["datacontent"]) - set(cells)
    if unknown:
        raise ValueError(f"datacontent keys that match no cell: {sorted(unknown)[:5]}")
    for k, (v, tv, th, tt) in cells.items():
        if k in response["datacontent"]:
            yield v, tv, th, tt, response["datacontent"][k]


def bps_api_province_cells(table, lookup, national_source_code="9999", national_label="INDONESIA"):
    """Yield (province code, turvar label, turtahun label, year, text) for every filled cell of a national WebAPI table.

    Rows are matched to BPS codes by name, and each name's code must agree with the first two digits
    of the source's own region code. The source writes Indonesia as national_source_code with the row
    label national_label (INDONESIA in most tables, RATA-RATA in some wage tables); it becomes code 00.
    """
    for r, tv, th, tt, text in bps_api_cells(table):
        source, name = str(r["val"]), html_to_text(r["label"])
        if source == national_source_code:
            if normalise_name(name) != normalise_name(national_label):
                raise ValueError(f"region {source} is labelled {name!r}, expected {national_label!r}")
            code = NATIONAL_CODE
        else:
            code = province_code(name, lookup, source[:2])
        yield code, html_to_text(tv["label"]).strip(), html_to_text(tt["label"]).strip(), str(th["label"]), text


# Row labels

LEADING_CODE = re.compile(r"^(?:[A-U](?:\s*,\s*[A-U])*|\d{1,2}|[a-g])(?:\.|\s|$)\s*")


def row_name(label):
    """Return a table row label without HTML, outline codes (A., B.2., 1., 11., a., R,S,T,U) or extra spaces."""
    name = html_to_text(label)
    while True:
        stripped = LEADING_CODE.sub("", name, count=1)
        if stripped == name:
            return name
        name = stripped


def match_rows(labels, patterns, fixes=None, where=""):
    """Match row labels to codes by name and return code -> row index.

    patterns: code -> regex on the row name (case ignored), in the order the rows must appear.
    fixes: raw label -> code, for a label the source gets wrong, or -> None for a row whose label
    names another row and must not be read; each fix must be used.
    Every code must match exactly one row, and the matched rows must keep the order of patterns.
    """
    fixes = dict(fixes or {})
    found = {}
    for i, label in enumerate(labels):
        if label in fixes:
            code = fixes.pop(label)
            if code is not None:
                found.setdefault(code, []).append(i)
            continue
        name = row_name(label)
        for code, pattern in patterns.items():
            if re.search(pattern, name, re.IGNORECASE):
                found.setdefault(code, []).append(i)
    if fixes:
        raise ValueError(f"{where}: label fixes not used: {fixes}")
    bad = {c: found.get(c, []) for c in patterns if len(found.get(c, [])) != 1}
    if bad:
        raise ValueError(f"{where}: codes without exactly one row: {bad}")
    index = {c: found[c][0] for c in patterns}
    order = [index[c] for c in patterns]
    if order != sorted(order):
        raise ValueError(f"{where}: rows are out of the expected order")
    return index


# Combining sources

def key_of(row, key_columns):
    """Return the identifying fields of a long row."""
    return tuple(row[c] for c in key_columns)


def merge_sources(sources, key_columns):
    """Merge lists of long rows in priority order; a repeated key must carry exactly the same value.

    sources is a list of (name, rows). The first source to give a key keeps its row and status.
    Returns the merged rows and a count of overlaps checked per pair of sources.
    """
    merged, origin, overlaps = {}, {}, {}
    for name, rows in sources:
        for r in rows:
            k = key_of(r, key_columns)
            if k in merged:
                if merged[k]["value"] != r["value"]:
                    raise ValueError(f"{k}: {origin[k]} has {merged[k]['value']}, {name} has {r['value']}")
                pair = f"{name} = {origin[k]}"
                overlaps[pair] = overlaps.get(pair, 0) + 1
            else:
                merged[k], origin[k] = r, name
    return list(merged.values()), overlaps


# Checks

def check_structure(df, key_columns, allowed):
    """Layer 1: exact columns, numeric values, unique keys, and every code in its lookup."""
    expected = key_columns + ["status", "value"]
    if list(df.columns) != expected:
        raise ValueError(f"columns {list(df.columns)} != {expected}")
    if df.duplicated(key_columns).any():
        raise ValueError(f"duplicate keys: {df[df.duplicated(key_columns)].head().to_dict('records')}")
    if not pd.api.types.is_float_dtype(df["value"]) or df["value"].isna().any():
        raise ValueError("value column must be numeric with no gaps")
    if not set(df["status"]) <= set(BPS_STATUS):
        raise ValueError(f"unknown status {set(df['status']) - set(BPS_STATUS)}")
    for column, codes in allowed.items():
        unknown = set(df[column]) - set(codes)
        if unknown:
            raise ValueError(f"{column} has codes outside its lookup: {sorted(unknown)[:10]}")
    if "period" in df and not df["period"].str.fullmatch(r"\d{4}(Q[1-4])?").all():
        raise ValueError("period must be YYYY or YYYYQn")


def check_complete(df, key_columns, expected):
    """Layer 2: the keys present equal the keys expected, no more and no fewer."""
    found = {tuple(r) for r in df[key_columns].itertuples(index=False)}
    missing, extra = sorted(expected - found), sorted(found - expected)
    if missing or extra:
        raise ValueError(f"completeness: {len(missing)} missing {missing[:5]}, {len(extra)} extra {extra[:5]}")


def check_sum(parts, total, tolerance, label, relative=False):
    """Layer 3: parts (a Series indexed like total) sum to total within a tolerance."""
    gap = (parts - total).dropna().abs()
    if relative:
        gap = gap / total.abs()
    if len(gap) == 0:
        raise ValueError(f"{label}: nothing to compare")
    if gap.max() > tolerance:
        raise ValueError(f"{label}: largest gap {gap.max():.6g} at {gap.idxmax()} exceeds {tolerance}")
    return {"check": label, "compared": int(len(gap)), "largest_gap": float(round(gap.max(), 6)), "tolerance": tolerance}


def flag_outside(rows, check, low, high):
    """Layer 5: return flags for rows whose 'value' lies outside [low, high]."""
    return [{"check": check, **{k: v for k, v in r.items() if k != "value"}, "value": round(r["value"], 4),
             "range": [low, high]} for r in rows if not low <= r["value"] <= high]


def sha256(path):
    """Layer 6: return the SHA-256 hash of a file."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# Writing

def write_dataset(rows, key_columns, allowed, expected, csv_path, meta, raw_files, sort_orders=None):
    """Check a dataset and write its CSV and metadata JSON, or stop before writing anything.

    rows: list of dicts with key_columns, 'status' and 'value'.
    allowed: column -> codes that column may use (layer 1).
    expected: set of key tuples that must be present exactly (layer 2).
    meta: dataset metadata; checks already run by the build go in meta['checks'].
    raw_files: every raw file read, hashed into the metadata (layer 6).
    sort_orders: column -> list giving a custom sort order for that column.
    """
    df = pd.DataFrame(rows, columns=key_columns + ["status", "value"])
    df["status"] = df["status"].fillna("")
    df["value"] = df["value"].astype(float)
    check_structure(df, key_columns, allowed)
    check_complete(df, key_columns, expected)

    # Sort by every key column, using a custom order where one is given
    sort_orders = sort_orders or {}
    sort_keys = []
    for c in key_columns:
        if c in sort_orders:
            df[f"_{c}"] = df[c].map({v: i for i, v in enumerate(sort_orders[c])})
            sort_keys.append(f"_{c}")
        else:
            sort_keys.append(c)
    df = df.sort_values(sort_keys).drop(columns=[k for k in sort_keys if k.startswith("_")])

    # Write the CSV in the shared format, then the metadata with format, status codes and hashes
    df.to_csv(csv_path, index=False, float_format="%.10g", lineterminator="\n", encoding="utf-8")
    meta = {
        **meta,
        "file": Path(csv_path).name,
        "rows": int(len(df)),
        "format": CSV_FORMAT,
        "status": {k: v for k, v in BPS_STATUS.items() if k in set(df["status"])},
        "raw_files": {str(Path(p).resolve().relative_to(ROOT)): {"sha256": sha256(p)} for p in raw_files},
    }
    meta["checks"] = {"passed": ["structure", "completeness"] + meta.get("checks", {}).get("passed", []),
                      **{k: v for k, v in meta.get("checks", {}).items() if k != "passed"}}
    meta_path = Path(csv_path).with_name(Path(csv_path).stem + "-metadata.json")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return df
