"""Shared cleaning and checking for every build script in data/.

README.md, section Cleaning and checking, sets the rules this module enforces. A build script
imports it, parses its own raw files into long rows with these functions, and calls
write_dataset, which runs the checks and writes nothing unless they pass.
"""

import csv
import hashlib
import html
import itertools
import json
import math
import re
from decimal import Decimal
from html.parser import HTMLParser
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

# A WebAPI datacontent key joins the values of these lists, in this order
WEBAPI_KEY_PARTS = ("vervar", "var", "turvar", "tahun", "turtahun")

# Fields a SIMDASI response holds when it carries a table rather than an error object
SIMDASI_TABLE_FIELDS = ("judul_tabel", "tahun_data", "wilayah", "keterangan_data", "kolom", "data")

# One layout cell of a SIMDASI row label: <div class="col-md-N ...">text</div>
SIMDASI_CELL = re.compile(r'<div class="(col-md-\d+)[^"]*">(.*?)</div>', re.S)

# A year written in a BPS note
NOTE_YEAR = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")

# Excel-made HTML tables (BPS static tables): the style of a padding span, which holds no-break spaces before or after
# some numbers; HTML white space as a browser collapses it; and the page's style rules with the number format each sets
EXCEL_PADDING_STYLE = "mso-spacerun:yes"
HTML_SPACE = re.compile(r"[ \t\n\f\r]+")
EXCEL_STYLE_RULE = re.compile(r"\.(xl\d+)\s*\{([^}]*)\}")
EXCEL_NUMBER_FORMAT = re.compile(r"mso-number-format:([^;]*);")


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
    """Return a region name in the BPS reference spelling: upper case, KEP. spelled out, D I written DI, single spaces.

    Some BPS tables, such as WebAPI var 416, write D I YOGYAKARTA where the BPS province list has DI YOGYAKARTA.
    """
    name = " ".join(str(name).upper().split())
    name = re.sub(r"^D I ", "DI ", name)
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


def webapi_region_code(vervar, label, lookup):
    """Return the BPS code of a WebAPI vervar value, and stop if its label names another region.

    WebAPI tables number provinces in two ways: by kode_bps itself (11 ... 97, as in vars 2267 and
    2268, which have no Indonesia row) or by kode_bps x 100 (1100 ... 9700, with 9999 for Indonesia,
    as in vars 286 and 98).
    """
    vervar = int(vervar)
    if vervar == 9999:
        code = NATIONAL_CODE
    elif vervar % 100 == 0 and 1100 <= vervar <= 9900:
        code = f"{vervar // 100:02d}"
    elif 11 <= vervar <= 99:
        code = f"{vervar:02d}"
    else:
        raise ValueError(f"vervar {vervar} ({label}) is neither a province nor Indonesia")
    return province_code(label, lookup, code)


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


# BPS static tables (Excel-made HTML pages)

class ExcelCells(HTMLParser):
    """Collect each row of an Excel-made HTML table as cells with their text, padding text, class, colspan, rowspan and
    inline markup.

    Text inside a padding span (EXCEL_PADDING_STYLE) is kept apart from the cell's own text. A tag named in inline (tag
    -> the attributes it may carry), such as a named anchor, a rich-text font run or a superscript footnote marker, may
    sit inside a cell: its text joins the cell's text and the cell lists the tag under 'inline', so a build can refuse
    markup in its value cells. With hidden set to a style such as 'display:none', a span carrying exactly that style
    (Excel's hidden overflow text, outside a padding span) is read the same way and listed as 'span'. Any other tag
    inside a cell stops the read, so that markup this reader does not know cannot hide or join a value.
    """

    def __init__(self, inline=None, hidden=None):
        super().__init__(convert_charrefs=True)
        self.inline, self.hidden = inline or {}, hidden
        self.rows, self.row, self.cell, self.in_padding, self.open = [], None, None, False, []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "tr":
            if self.row is not None:
                raise ValueError("a table row opens inside another row")
            self.row = []
        elif tag in ("td", "th"):
            if self.row is None or self.cell is not None:
                raise ValueError(f"a <{tag}> cell opens outside a row or inside another cell")
            self.cell = {"text": [], "padding": [], "class": attrs.get("class"), "inline": [],
                         "colspan": int(attrs.get("colspan") or 1), "rowspan": int(attrs.get("rowspan") or 1)}
        elif self.cell is not None:
            if tag == "span" and attrs.get("style") == EXCEL_PADDING_STYLE and not self.in_padding:
                self.in_padding = True
            elif (tag == "span" and self.hidden is not None and attrs == {"style": self.hidden}
                  and not self.in_padding):
                self.open.append(tag)
                self.cell["inline"].append(tag)
            elif tag in self.inline and set(attrs) <= set(self.inline[tag]):
                self.open.append(tag)
                self.cell["inline"].append(tag)
            else:
                raise ValueError(f"unexpected <{tag}> {attrs} inside a cell")

    def handle_endtag(self, tag):
        if tag == "span" and self.in_padding:
            self.in_padding = False
        elif self.open and tag == self.open[-1]:
            self.open.pop()
        elif tag in self.open:
            raise ValueError(f"</{tag}> closes inside <{self.open[-1]}>")
        elif tag in ("td", "th") and self.cell is not None:
            if self.open or self.in_padding:
                raise ValueError(f"a cell closes inside {self.open or 'a padding span'}")
            self.row.append(self.cell)
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if self.cell is not None:
                raise ValueError("a table row closes inside a cell")
            self.rows.append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell["padding" if self.in_padding else "text"].append(data)


def excel_grid(page, inline=None, hidden=None, padding_space=False):
    """Lay the rows of an Excel-made HTML table, such as a BPS static table, out on a grid in which every row has the
    same width.

    Each slot holds (text, cell, own): the text of the cell that covers the slot, after dropping its padding and
    collapsing HTML white space; the cell; and whether the slot is the cell's own top-left slot. A cell whose text is
    only no-break spaces (&nbsp;) is empty. inline and hidden name the markup allowed inside cells (ExcelCells). Stops
    if a padding span holds anything but no-break spaces, or also HTML white space when padding_space is true (Excel
    wraps long source lines inside padding spans, and some pages pad with spaces), or if any slot is left uncovered.
    """
    parser = ExcelCells(inline, hidden)
    parser.feed(page)
    parser.close()
    allowed_padding = "\xa0" + (" \t\n\f\r" if padding_space else "")
    slots = {}
    for i, row in enumerate(parser.rows):
        j = 0
        for cell in row:
            # A slot covered from a row above by a rowspan is skipped
            while (i, j) in slots:
                j += 1
            padding = "".join(cell["padding"])
            if padding.strip(allowed_padding):
                raise ValueError(f"table row {i}: a padding span holds {padding!r}")
            text = HTML_SPACE.sub(" ", "".join(cell["text"])).strip(" ")
            text = "" if not text.strip("\xa0 ") else text
            for di in range(cell["rowspan"]):
                for dj in range(cell["colspan"]):
                    slots[(i + di, j + dj)] = (text, cell, (di, dj) == (0, 0))
            j += cell["colspan"]
    height = max(i for i, _ in slots) + 1
    width = max(j for _, j in slots) + 1
    uncovered = [(i, j) for i in range(height) for j in range(width) if (i, j) not in slots]
    if uncovered:
        raise ValueError(f"the table leaves {len(uncovered)} slots uncovered, such as {uncovered[:5]}")
    return [[slots[(i, j)] for j in range(width)] for i in range(height)]


def excel_own_texts(row):
    """Return the texts of the cells that start in a grid row of excel_grid, without the empty ones."""
    return [text for text, _, own in row if own and text]


def excel_number_formats(page):
    """Return each style class of an Excel-made page with the number format it sets (mso-number-format), or None."""
    formats = {}
    for name, body in EXCEL_STYLE_RULE.findall(page):
        found = EXCEL_NUMBER_FORMAT.search(body)
        formats[name] = found.group(1) if found else None
    return formats


# BPS WebAPI responses

def webapi_unlisted_turvar(reply, keys, name):
    """Split WebAPI datacontent keys into those that decode only with a turvar the table does not list, and the rest.

    Such a key joins a listed vervar, var, tahun and turtahun around a turvar code missing from the
    table's turvar list, as 110053468611931 in var 534 is vervar 1100, var 534, the unlisted turvar 686,
    tahun 119 and turtahun 31: a value BPS left in datacontent under a code of an earlier release.
    Returns (keys left undecoded, cells); a key that decodes in more than one way stays undecoded, and
    each cell holds var, vervar, vervar_label, turvar (an int), year, turtahun, turtahun_label and value.
    """
    listed = {str(t["val"]) for t in reply["turvar"]}
    left, cells = [], []
    for key in keys:
        found = []
        for v, x, th, tt in itertools.product(reply["vervar"], reply["var"], reply["tahun"], reply["turtahun"]):
            head, tail = f"{v['val']}{x['val']}", f"{th['val']}{tt['val']}"
            middle = key[len(head):len(key) - len(tail)]
            if (len(key) > len(head) + len(tail) and key.startswith(head) and key.endswith(tail)
                    and middle.isdigit() and middle not in listed):
                found.append((v, x, middle, th, tt))
        if len(found) != 1:
            left.append(key)
            continue
        v, x, middle, th, tt = found[0]
        value = reply["datacontent"][key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{name}: {key} holds {value!r}, not a number")
        cells.append({"var": x["val"], "vervar": v["val"], "vervar_label": v["label"], "turvar": int(middle),
                      "year": int(th["label"]), "turtahun": tt["val"], "turtahun_label": tt["label"],
                      "value": float(value)})
    return left, cells


def read_webapi_table(path, var=None, unit=None, decimals=None, encoding="utf-8", unlisted_turvar=False):
    """Read a saved BPS WebAPI dynamic table (model data) into its description and one record per value.

    A datacontent key joins the vervar, var, turvar, tahun and turtahun values, as 11009818912561 is
    vervar 1100, var 98, turvar 189, tahun 125 and turtahun 61. The key of every combination of the
    table's own lists is rebuilt, and the read stops if any datacontent key is left undecoded or
    matches two combinations, or if any value is not a number. When var, unit or decimals is given,
    the table must hold only that variable, every variable must declare that unit and that number of
    decimals, and no value may carry more decimals than declared. When unlisted_turvar is true, a key
    that decodes only with a turvar the table does not list (webapi_unlisted_turvar) is set aside
    rather than read: table['unlisted_turvar'] lists each such cell for the build to declare and
    report, and any other undecoded key still stops the read.

    Returns (table, records). table is the response without datacontent: var (with unit, decimal and
    note), vervar, turvar, tahun, turtahun, labelvervar and last_update. Each record holds var,
    vervar, vervar_label, turvar, turvar_label, year (an int from the tahun label), turtahun,
    turtahun_label and value (a float), in the order of the table's own lists.
    """
    name = Path(path).name
    reply = json.loads(Path(path).read_text(encoding=encoding))
    if reply.get("status") != "OK" or reply.get("data-availability") != "available":
        raise ValueError(f"{name}: no table in the response ({reply.get('status')}, {reply.get('data-availability')})")

    # Check the variable, its unit and its decimals against what the build declared
    if var is not None and [v["val"] for v in reply["var"]] != [var]:
        raise ValueError(f"{name}: var {[v['val'] for v in reply['var']]}, expected [{var}]")
    for v in reply["var"]:
        if unit is not None and v["unit"] != unit:
            raise ValueError(f"{name}: var {v['val']} unit {v['unit']!r}, expected {unit!r}")
        if decimals is not None and v["decimal"] != decimals:
            raise ValueError(f"{name}: var {v['val']} declares {v['decimal']} decimals, expected {decimals}")
    for th in reply["tahun"]:
        if not re.fullmatch(r"\d{4}", str(th["label"])):
            raise ValueError(f"{name}: tahun label {th['label']!r} is not a year")
    content = reply.get("datacontent") or {}
    if not content:
        raise ValueError(f"{name}: datacontent holds no values")

    # Rebuild the key of every combination; a key two combinations share could belong to either
    cells, shared = {}, set()
    for combo in itertools.product(*(reply[part] for part in WEBAPI_KEY_PARTS)):
        key = "".join(str(item["val"]) for item in combo)
        if key in cells:
            shared.add(key)
        cells[key] = combo
    undecoded = [k for k in content if k not in cells]
    unlisted = []
    if undecoded and unlisted_turvar:
        undecoded, unlisted = webapi_unlisted_turvar(reply, undecoded, name)
    if undecoded:
        raise ValueError(f"{name}: {len(undecoded)} datacontent keys left undecoded, such as {undecoded[:5]}")
    ambiguous = [k for k in content if k in shared]
    if ambiguous:
        raise ValueError(f"{name}: datacontent keys {ambiguous[:5]} match more than one combination")

    # One record per published value
    records = []
    for key, (v, x, t, th, tt) in cells.items():
        if key not in content:
            continue
        value = content[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{name}: {key} holds {value!r}, not a number")
        if decimals is not None and round(value, decimals) != value:
            raise ValueError(f"{name}: {key} = {value} has more than {decimals} decimals")
        records.append({"var": x["val"], "vervar": v["val"], "vervar_label": v["label"],
                        "turvar": t["val"], "turvar_label": t["label"], "year": int(th["label"]),
                        "turtahun": tt["val"], "turtahun_label": tt["label"], "value": float(value)})
    table = {k: v for k, v in reply.items() if k != "datacontent"}
    if unlisted_turvar:
        table["unlisted_turvar"] = unlisted
    return table, records


def simdasi_label_level(label):
    """Return (level, marker) for a SIMDASI row label, read from the layout cells of its HTML.

    A category carries its code in col-md-2 ('A', 'M,N'), a numbered sub-category its number in
    col-md-1, and a lettered item its letter at the start of col-md-9 ('a. Tanaman Pangan'), giving
    ('category', 'A'), ('subcategory', '1') or ('item', 'a'). A plain label without layout cells, such
    as a total or a region name, gives (None, None), and any other layout stops the read.
    """
    cells = SIMDASI_CELL.findall(label or "")
    if not cells:
        return None, None
    text = {}
    for column, inner in cells:
        if column in text:
            raise ValueError(f"label repeats {column}: {label!r}")
        text[column] = html_to_text(inner)
    if set(text) == {"col-md-2", "col-md-10"} and text["col-md-2"]:
        return "category", text["col-md-2"]
    if set(text) == {"col-md-2", "col-md-1", "col-md-9"} and not text["col-md-2"]:
        if text["col-md-1"]:
            return "subcategory", text["col-md-1"]
        letter = re.match(r"([a-z])\.\s", text["col-md-9"])
        if letter:
            return "item", letter.group(1)
    raise ValueError(f"unrecognised SIMDASI label layout: {label!r}")


def read_simdasi_table(path, year, area, decimals=None, unit_text=None, decimal=",", thousands=".",
                       missing=BPS_NO_VALUE, encoding="utf-8"):
    """Read a saved SIMDASI table (WebAPI interoperabilitas id/25) into its description and one record per cell.

    Stops unless the response is a filled table for the expected year and area: a missing year
    answers status OK with an error object where the table should be, and an empty shell lists the
    rows with no values. The area is compared after normalise_name, so 'Aceh' matches 'ACEH'. Each
    value_raw is parsed with parse_number against the declared decimal mark and thousands separator
    and its column's declared decimals, which must equal decimals when given, and the title must carry
    unit_text when given. A cell without a value must carry a marker in missing, such as the en dash
    for 'Tidak ada atau nol' (none or zero); its record keeps value None and the marker, so a build
    can list it. A row whose values are an empty list takes each column's marker from the row itself.
    The household-spending statistics tables (tablestatistic) share this layout and read the same way.

    Returns (table, records). table holds title, title_en, year, area, legend (marker -> meaning),
    columns (column key -> name, name_en, decimals), notes, source, table_updated and change_log.
    Each record holds the row's category, subcategory and item (from the label HTML, carried down
    from the rows above, None where the row has no such level), label (label_raw as published),
    kode_wilayah, column, value (a float or None) and value_code ('' when the cell has no marker).
    """
    name = Path(path).name
    reply = json.loads(Path(path).read_text(encoding=encoding))
    data = reply.get("data")
    table = data[1] if isinstance(data, list) and len(data) == 2 and isinstance(data[1], dict) else {}

    # A missing year answers status OK with an error object where the table should be
    if (reply.get("status") != "OK" or reply.get("data-availability") != "available"
            or not all(k in table for k in SIMDASI_TABLE_FIELDS) or not isinstance(table["data"], list)):
        raise ValueError(f"{name}: no table in the response: {json.dumps(data, ensure_ascii=False)[:300]}")
    if table["tahun_data"] != year:
        raise ValueError(f"{name}: tahun_data is {table['tahun_data']}, expected {year}")
    if normalise_name(table["wilayah"]) != normalise_name(area):
        raise ValueError(f"{name}: wilayah is {table['wilayah']!r}, expected {area!r}")

    # An empty shell lists the row labels with no values
    if not any(r.get("variables") for r in table["data"]):
        raise ValueError(f"{name}: an empty table shell, no row has values")
    if unit_text is not None:
        require_text(table["judul_tabel"], unit_text, f"{name} title")

    # Each column declares its decimals, which every value must carry
    columns = {}
    for key, column in table["kolom"].items():
        places = column["angka_desimal_dibelakang_koma"]
        if decimals is not None and places != decimals:
            raise ValueError(f"{name}: column {key} declares {places} decimals, expected {decimals}")
        columns[key] = {"name": column.get("nama_variabel"), "name_en": column.get("nama_variabel_en"),
                        "decimals": places}

    records = []
    category = subcategory = item = None
    for r in table["data"]:
        # Carry the hierarchy down: a category resets its sub-category, a sub-category its item
        level, marker = simdasi_label_level(r["label"])
        if level == "category":
            category, subcategory, item = marker, None, None
        elif level is None:
            category = subcategory = item = None
        elif category is None:
            raise ValueError(f"{name}: {level} {r['label_raw']!r} comes before any category")
        elif level == "subcategory":
            subcategory, item = marker, None
        else:
            item = marker
        cells = r.get("variables") or {}
        if not isinstance(cells, dict) or set(cells) - set(columns):
            raise ValueError(f"{name}: row {r['label_raw']!r} has cells outside the table's columns")
        for key in columns:
            if cells:
                if key not in cells:
                    raise ValueError(f"{name}: row {r['label_raw']!r} has no cell for column {key}")
                raw, code = cells[key].get("value_raw"), cells[key].get("value_code") or ""
            else:
                # A row without values names each column's marker beside its empty list, such as '...'
                raw, code = None, r.get(key) or ""
            if raw is None:
                if code not in missing:
                    raise ValueError(f"{name}: row {r['label_raw']!r} column {key} has no value and marker {code!r}")
                value = None
            elif code in missing:
                raise ValueError(f"{name}: row {r['label_raw']!r} column {key} has value {raw!r} beside marker {code!r}")
            else:
                try:
                    value = parse_number(raw, decimal, thousands, columns[key]["decimals"])
                except ValueError as e:
                    raise ValueError(f"{name}: row {r['label_raw']!r} column {key}: {e}") from None
            records.append({"category": category, "subcategory": subcategory, "item": item,
                            "label": r["label_raw"], "kode_wilayah": r.get("kode_wilayah"),
                            "column": key, "value": value, "value_code": code})

    # Describe the table: title with its unit, year, area, marker legend, columns and notes
    info = {
        "title": table["judul_tabel"],
        "title_en": table.get("judul_tabel_en"),
        "year": table["tahun_data"],
        "area": table["wilayah"],
        "legend": {code: html.unescape(text) for code, text in table["keterangan_data"].items()},
        "columns": columns,
        "notes": html_to_text(table.get("catatan")),
        "source": html_to_text(table.get("sumber")),
        "table_updated": table.get("table_updated"),
        "change_log": [{"time": c.get("waktu"), "change": html_to_text(c.get("perubahan"))}
                       for c in table.get("change_log") or []],
    }
    return info, records


def parse_status_note(note):
    """Return {year: status marker} from the revision statements in a BPS note.

    Each list item, line or ';'-separated clause of the note (HTML or plain text) is read on its own.
    A clause '<text naming one year>: <phrase>', as in 'Data 2024: Angka sementara' or 'Triwulan I–IV
    2024 dan Tahun 2024: Angka sementara', gives that year the BPS_STATUS marker whose meaning starts
    with the phrase, so 'Data 2024: Angka sementara; Data 2025: Angka sangat sementara' gives
    {2024: '*', 2025: '**'}. Stops on a phrase BPS_STATUS does not know, on a clause naming two years,
    on a year given two markers, and on any other clause that names a year beside a status phrase. A
    clause without a year, such as a legend line '* Angka sementara', is skipped, and a note with no
    statements gives {}.
    """
    phrases = {meaning.split(" (")[0].lower(): marker for marker, meaning in BPS_STATUS.items() if marker}
    text = html.unescape(html.unescape(note or ""))
    status = {}
    for clause in re.split(r"<\s*/?\s*(?:li|ul|ol|p|br|div)\b[^>]*>|[\r\n;]", text, flags=re.I):
        clause = " ".join(re.sub(r"<[^>]+>", " ", clause).split())
        statement = re.fullmatch(r"(.*?\d{4})[^\w:]*:\s*(angka\b.*?)[\s.]*", clause, re.I)
        if statement:
            phrase = " ".join(statement.group(2).lower().split())
            years = set(NOTE_YEAR.findall(statement.group(1)))
            if phrase not in phrases:
                raise ValueError(f"note clause {clause!r}: {statement.group(2)!r} is not a status in BPS_STATUS")
            if len(years) != 1:
                raise ValueError(f"note clause {clause!r} names {len(years)} years, not one")
            year = int(years.pop())
            if status.setdefault(year, phrases[phrase]) != phrases[phrase]:
                raise ValueError(f"note gives {year} both {status[year]!r} and {phrases[phrase]!r}")
        elif NOTE_YEAR.search(clause) and any(p in clause.lower() for p in phrases):
            raise ValueError(f"note clause {clause!r} names a year and a status in a form this parser does not read")
    return status


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


def compare_sources(first, second, tolerance, label, relative=False):
    """Layer 4: compare the values two sources give for the same keys, within a stated tolerance.

    first and second map key -> value, first being the higher-priority source. A gap is the absolute
    difference of the two values written as the shortest decimals that read back as the same floats,
    so float rounding never counts as a difference, or that difference over the first value's size
    when relative is true. Returns a summary for the metadata that lists every key whose values differ,
    and stops when any gap exceeds the tolerance, or when no key is in both; a tolerance of 0 means the
    values must match exactly.
    """
    def as_decimal(x):
        """Return a number as the shortest decimal that reads back as the same float."""
        d = Decimal(str(float(x)))
        if not d.is_finite():
            raise ValueError(f"{label}: {x!r} is not a finite number")
        return d

    shared = [k for k in first if k in second]
    if not shared:
        raise ValueError(f"{label}: no key is in both sources")
    limit = as_decimal(tolerance)
    differences, over = [], []
    for k in shared:
        a, b = as_decimal(first[k]), as_decimal(second[k])
        if a == b:
            continue
        gap = abs(a - b)
        if relative:
            gap = gap / abs(a) if a else Decimal("Infinity")
        entry = {"key": list(k) if isinstance(k, tuple) else k, "first": float(a), "second": float(b),
                 "gap": float(f"{gap:.6g}") if relative else float(gap)}
        differences.append(entry)
        if gap > limit:
            over.append(entry)
    if over:
        worst = max(over, key=lambda d: d["gap"])
        raise ValueError(f"{label}: {len(over)} of {len(shared)} shared values differ by more than {tolerance}, "
                         f"largest {worst['gap']:.6g} at {worst['key']} ({worst['first']} vs {worst['second']})")
    return {"check": label, "compared": len(shared), "tolerance": tolerance, "relative": relative,
            "largest_gap": max((d["gap"] for d in differences), default=0.0), "differences": differences}


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
    if "period" in df and not df["period"].str.fullmatch(r"\d{4}(Q[1-4]|S[12])?").all():
        raise ValueError("period must be YYYY, YYYYQn or YYYYSn")


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

    # Write the CSV in the shared format, then the metadata with format, status codes and hashes;
    # both files end lines with LF and raw file paths use forward slashes, so every OS writes the same bytes
    df.to_csv(csv_path, index=False, float_format="%.10g", lineterminator="\n", encoding="utf-8")
    meta = {
        **meta,
        "file": Path(csv_path).name,
        "rows": int(len(df)),
        "format": CSV_FORMAT,
        "status": {k: v for k, v in BPS_STATUS.items() if k in set(df["status"])},
        "raw_files": {Path(p).resolve().relative_to(ROOT).as_posix(): {"sha256": sha256(p)} for p in raw_files},
    }
    meta["checks"] = {"passed": ["structure", "completeness"] + meta.get("checks", {}).get("passed", []),
                      **{k: v for k, v in meta.get("checks", {}).items() if k != "passed"}}
    meta_path = Path(csv_path).with_name(Path(csv_path).stem + "-metadata.json")
    with open(meta_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(meta, ensure_ascii=False, indent=1) + "\n")
    return df
