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


def parse_number(text, decimal=".", thousands=None, decimals=None):
    """Turn a published number string into a float.

    Stops on any text that does not match the declared decimal mark and thousands separator,
    so 1.234,5 written in Indonesian style is never read as 1.2345. When decimals is given,
    the number of digits after the decimal mark must equal it.
    """
    text = str(text).strip()
    if not number_pattern(decimal, thousands).match(text):
        raise ValueError(f"{text!r} does not match decimal {decimal!r}, thousands {thousands!r}")
    if decimals is not None:
        found = len(text.split(decimal)[1]) if decimal in text else 0
        if found != decimals:
            raise ValueError(f"{text!r} has {found} decimals, source declares {decimals}")
    if thousands:
        text = text.replace(thousands, "")
    return float(text.replace(decimal, "."))


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
    """Return a region name in the BPS reference spelling: upper case, KEP. spelled out, single spaces."""
    name = " ".join(str(name).upper().split())
    return re.sub(r"^KEP\. ", "KEPULAUAN ", name)


def load_bps_provinces(path):
    """Read the BPS province list from raw/province-codes and return code -> record and name -> code."""
    records = json.loads(Path(path).read_text(encoding="utf-8"))
    provinces = {r["kode_bps"]: {"name": r["nama_bps"], "kode_dagri": r["kode_dagri"]} for r in records}
    provinces[NATIONAL_CODE] = {"name": "INDONESIA", "kode_dagri": None}
    lookup = {normalise_name(p["name"]): code for code, p in provinces.items()}
    return provinces, lookup


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
