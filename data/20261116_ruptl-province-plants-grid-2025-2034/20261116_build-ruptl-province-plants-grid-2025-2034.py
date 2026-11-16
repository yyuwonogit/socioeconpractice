from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# Load the shared cleaning module from tools/
import sys
sys.path.insert(0, str(ROOT / "tools"))
import cleaning

import re

import pdfplumber

# Parameters

# Raw inputs: the BPS province list and RUPTL PLN 2025-2034 (uploaded by the user)
RAW_PROVINCES = ROOT / "raw/province-codes/20261102_bps-province-codes-2025-s1.json"
RAW_PDF = ROOT / "raw/electricity/20261116_ruptl-2025-2034.pdf"

# Output; the metadata JSON is written beside it with a -metadata suffix
OUT_CSV = HERE / "20261116_ruptl-province-plants-grid-2025-2034.csv"

KEYS = ["region", "indicator", "period"]

# RUPTL appendices A-C hold one chapter per province ("LAMPIRAN X.n RENCANA PENGEMBANGAN SISTEM TENAGA LISTRIK
# ... DI PROVINSI ..."). Two chapters cover several provinces together. Chapter -> (first page, provinces).
CHAPTERS = {
    "A1": (601, ["ACEH"]), "A2": (615, ["SUMATERA UTARA"]), "A3": (632, ["RIAU"]),
    "A4": (644, ["KEPULAUAN RIAU"]), "A5": (657, ["KEPULAUAN BANGKA BELITUNG"]), "A6": (668, ["SUMATERA BARAT"]),
    "A7": (680, ["JAMBI"]), "A8": (691, ["SUMATERA SELATAN"]), "A9": (704, ["BENGKULU"]), "A10": (715, ["LAMPUNG"]),
    "A11": (727, ["KALIMANTAN BARAT"]), "A12": (744, ["KALIMANTAN SELATAN"]), "A13": (758, ["KALIMANTAN TENGAH"]),
    "A14": (771, ["KALIMANTAN TIMUR"]), "A15": (796, ["KALIMANTAN UTARA"]),
    "B1": (812, ["DKI JAKARTA"]), "B2": (824, ["BANTEN"]), "B3": (841, ["JAWA BARAT"]), "B4": (874, ["JAWA TENGAH"]),
    "B5": (898, ["DI YOGYAKARTA"]), "B6": (905, ["JAWA TIMUR"]), "B7": (938, ["BALI"]),
    "C1": (952, ["SULAWESI UTARA"]), "C2": (971, ["SULAWESI TENGAH"]), "C3": (990, ["GORONTALO"]),
    "C4": (1001, ["SULAWESI SELATAN"]), "C5": (1029, ["SULAWESI TENGGARA"]), "C6": (1049, ["SULAWESI BARAT"]),
    "C7": (1061, ["MALUKU"]), "C8": (1084, ["MALUKU UTARA"]),
    "C9": (1104, ["PAPUA", "PAPUA PEGUNUNGAN", "PAPUA TENGAH", "PAPUA SELATAN"]),
    "C10": (1130, ["PAPUA BARAT", "PAPUA BARAT DAYA"]),
    "C11": (1150, ["NUSA TENGGARA BARAT"]), "C12": (1166, ["NUSA TENGGARA TIMUR"]),
}
LAST_PAGE = 1253
HEADING = re.compile(r"LAMPIRAN ([A-C])\.\s?(\d+) RENCANA PENGEMBANGAN SISTEM TENAGA LISTRIK")

# How the tables are written, read from opening the PDF: grid tables that pdfplumber reads cell by cell; numbers
# with "." for thousands and "," for decimals; "-" for none. Titles name each table:
READ_CONTEXT = {
    "plants_title": re.compile(r"Pembangkit Tenaga Listrik Eksisting|Pembangkit Eksisting|Kapasitas Pembangkit Terpasang", re.I),
    "plants_header": re.compile(r"Pembangkit", re.I),
    "transmission_title": re.compile(r"Rekapitulasi (Rincian )?Rencana (Pembangunan|Pengembangan) (Jaringan )?Transmisi.{0,60}RE\s+Base", re.I | re.S),
    "substation_title": re.compile(r"Rekapitulasi (Rincian )?Rencana (Pembangunan|Pengembangan) (Gardu Induk|GI)\b.{0,60}RE\s+Base", re.I | re.S),
    "decimal": ",", "thousands": ".",
}

# Coal plants: PLTU (including mine-mouth PLTU MT); PLTGU is a gas plant
COAL = re.compile(r"^PLTU\b", re.I)

# Sum check: the plants read must add up to the table's grand total (rounded MW per row)
TOLERANCE_MW = 2.0

# Chapters whose printed plant rows do not add up to the printed totals (rows minus total, MW); the grand total is used
# for installed capacity, and coal rows are unaffected
KNOWN_PLANT_GAPS = {
    "A2": {"gap_mw": 54.0, "why": "Sumatera Utara: IPP PLTG Sumatera 54.0 MW row is not in the printed IPP subtotal (956.7) or the grand total (3,211.3)"},
    "A6": {"gap_mw": -4.9, "why": "Sumatera Barat: IPP rows add up to 128.9 MW but the printed IPP subtotal is 133.9 MW"},
    "C2": {"gap_mw": 70.6, "why": "Sulawesi Tengah: the printed Sewa subtotal is 0 MW although its rows add up to 48 MW, and IPP rows add up to 611 MW against a printed 600 MW"},
    "C8": {"gap_mw": -20.93, "why": "Maluku Utara: PLN and Sewa rows add up to 106.4 MW, matching both printed subtotals, but the printed grand total is 127.3 MW"},
    "C12": {"gap_mw": 50.01, "why": "Nusa Tenggara Timur: PLN rows add up to 391.46 MW but the printed PLN subtotal is 341.45 MW"},
    "A12": {"gap_mw": 8.5, "why": "Kalimantan Selatan: PLN rows add up to 595.8 MW but the printed PLN subtotal is 587.3 MW"},
}

INDICATORS = {
    "installed_capacity_mw": {"name": "Installed capacity of existing power plants on the PLN system (PLN, IPP, rented and excess power), all types", "unit": "MW"},
    "coal_capacity_mw": {"name": "Installed capacity of existing coal power plants (PLTU, including mine-mouth) on the PLN system", "unit": "MW"},
    "transmission_plan_2025_2034_kms": {"name": "Planned new transmission lines 2025-2034, RE Base scenario (Rekapitulasi, Jumlah)", "unit": "kms (circuit km)"},
    "substation_plan_2025_2034_mva": {"name": "Planned new substation transformer capacity 2025-2034, RE Base scenario (Rekapitulasi, Jumlah)", "unit": "MVA"},
}
# Periods are YYYY: 2024 for existing plants (latest RUPTL data), 2034 (end of the plan) for cumulative 2025-2034 plans
PERIODS = {"installed_capacity_mw": "2024", "coal_capacity_mw": "2024", "transmission_plan_2025_2034_kms": "2034", "substation_plan_2025_2034_mva": "2034"}

# Functions

DOT_DECIMALS = []
STARRED = []
TOTALS_FROM_YEARS = []
RECAP_MISMATCHES = []

# Recap tables whose Jumlah row's yearly cells do not add up to its printed total (years minus total); the
# printed total is used
KNOWN_YEAR_GAPS = {
    ("B1", "gardu induk"): {"gap": 60.0, "why": "DKI Jakarta substations: the 150/20 kV row's years add up to 2,040 MVA but its total is printed 1,980, and the grand total 5,980 uses 1,980"},
}

# Chapters with no existing-plant table: their capacity is written as 0
NO_PLANT_TABLE = {"B5": "DI Yogyakarta: the chapter has no existing-plant table (it lists substations only); the province is supplied from the Java-Bali grid"}

# Cells printed with a stray character: printed text -> intended text; each must be met at least once
TYPOS = {"2`,7": "2,7"}
TYPOS_SEEN = set()


def number(text):
    """Parse a RUPTL number ("1.193,6", "551", "-" for none).

    A few cells use a decimal point instead of a comma ("54.0"); a single dot followed by one or two digits
    cannot be a thousands separator (those are followed by three), so it is read as a decimal and counted.
    Declared typos (TYPOS) are corrected.
    """
    text = text.strip()
    # A trailing "*" is RUPTL's footnote marker (e.g. transmission length still an estimate before routes are fixed)
    if text.endswith("*"):
        STARRED.append(text)
        text = text.rstrip("*").strip()
    if text in TYPOS:
        TYPOS_SEEN.add(text)
        text = TYPOS[text]
    if text in ("-", ""):
        return 0.0
    if re.fullmatch(r"\d+\.\d{1,2}", text):
        DOT_DECIMALS.append(text)
        return cleaning.parse_number(text, ".", None)
    # Some whole numbers are printed without a thousands separator ("1980"); digits only cannot be misread
    if re.fullmatch(r"\d{4,}", text):
        DOT_DECIMALS.append(text)
        return float(text)
    return cleaning.parse_number(text, READ_CONTEXT["decimal"], READ_CONTEXT["thousands"])


def compact(row):
    """Drop empty cells and line breaks from a table row."""
    return [" ".join(str(c).split()) for c in row if c is not None and str(c).strip() != ""]


def check_headings(pdf):
    """Every chapter starts where declared, in order."""
    for code, (page, _) in CHAPTERS.items():
        text = " ".join((pdf.pages[page - 1].extract_text() or "").split())
        m = HEADING.search(text)
        assert m and f"{m.group(1)}{m.group(2)}" == code, (code, page, text[:120])


def chapter_pages(code):
    """Pages of one chapter: from its first page to the page before the next chapter."""
    codes = list(CHAPTERS)
    start = CHAPTERS[code][0]
    end = CHAPTERS[codes[codes.index(code) + 1]][0] - 1 if code != codes[-1] else LAST_PAGE
    return range(start, end + 1)


def read_plants(pdf, code):
    """Sum existing installed capacity by plant type, checking it against the table's grand total."""
    pages = chapter_pages(code)
    if code in NO_PLANT_TABLE:
        return {"installed_capacity_mw": 0.0, "coal_capacity_mw": 0.0, "plants_gap_mw": 0.0, "plants_page": None}
    start = next(p for p in pages if READ_CONTEXT["plants_title"].search(pdf.pages[p - 1].extract_text() or ""))
    total_all, coal, grand, current, importing = 0.0, 0.0, None, None, False
    # Capacity column, counted from the right of each row (most tables: units, capacity, DMN, DMP -> 3)
    from_end = 3
    for p in range(start, pages[-1] + 1):
        for table in pdf.pages[p - 1].extract_tables():
            rows = [compact(r) for r in table]
            rows = [r for r in rows if r]
            if not rows:
                continue
            # Only the existing-plants table: header naming Pembangkit, or a continuation whose rows start with PLT or an owner
            head = " ".join(rows[0])
            starts_plants = READ_CONTEXT["plants_header"].search(head) and re.search(r"Kapasitas", head)
            continuing = current is not None and any(re.match(r"^(PLT|Jumlah|IPP|Sewa|PLN)", r[0]) for r in rows)
            if not (starts_plants or continuing):
                continue
            if starts_plants:
                # Locate "Total Kapasitas" in the header; some chapters order or number the columns differently
                cap_col = [i for i, h in enumerate(rows[0]) if re.search(r"Kapasitas", h, re.I)]
                if cap_col and len(rows[0]) >= 5:
                    from_end = len(rows[0]) - cap_col[0]
            for r in rows[1:] if starts_plants else rows:
                first = r[0]
                if re.match(r"^(Jumlah|Total|Jumlah Total)$", first) and len(r) >= 4:
                    grand = number(r[-from_end])
                    continue
                # Ownership headings; imported power (e.g. Kalimantan Barat from Sarawak) is not a plant in the
                # province and the printed grand total leaves it out, so its rows are skipped
                if len(r) == 1 and re.match(r"^(PLN|IPP|Sewa|SEWA|Excess|Impor|Import)", first):
                    importing = first.lower().startswith("impor")
                    continue
                if importing and not re.match(r"^(Jumlah|Total)", first):
                    continue
                if re.match(r"^(Jumlah|Total)\b", first) or first in ("PLN", "IPP", "Sewa") or len(r) < 4:
                    if re.match(r"^PLT", first):
                        current = first
                    continue
                if re.match(r"^PLT", first):
                    current = first.split()[0] if not first.upper().startswith("PLTU") else first
                cap = number(r[-from_end])
                total_all += cap
                if current and COAL.match(current):
                    coal += cap
            if grand is not None:
                break
        if grand is not None:
            break
    assert grand is not None, (code, "no grand total found")
    known = KNOWN_PLANT_GAPS.get(code)
    if known is not None:
        assert abs((total_all - grand) - known["gap_mw"]) < 0.05, (code, total_all - grand, "known gap changed")
    elif abs(total_all - grand) > TOLERANCE_MW:
        raise ValueError(f"{code}: plants read sum to {total_all:.1f} MW, table total {grand:.1f} MW")
    return {"installed_capacity_mw": round(grand, 2), "coal_capacity_mw": round(coal, 2), "plants_gap_mw": round(total_all - grand, 2), "plants_page": start}


def read_recap(pdf, code, title, header):
    """Return the grand total (last cell of the Jumlah row) of the first recap table after the RE Base title.

    The recap table's first header cell names its rows (e.g. "Transmisi", "Gardu Induk" or "Trafo"); detail tables
    start with "No" and are skipped. A recap table may continue on the next page, repeating its header; its rows
    are collected until the Jumlah (or Total) row, and the rows' own totals must add up to it.
    """
    for p in chapter_pages(code):
        if not title.search(pdf.pages[p - 1].extract_text() or ""):
            continue
        parts = []
        # On the title's own page, only tables below the title count (an earlier table, e.g. another scenario's
        # transmission recap, can sit above it)
        hits = pdf.pages[p - 1].search(title.pattern, regex=True, case=False)
        title_top = hits[0]["top"] if hits else 0
        for q in (p, p + 1, p + 2):
            found = pdf.pages[q - 1].find_tables()
            for table in [t.extract() for t in found if q != p or t.bbox[1] >= title_top]:
                rows = [compact(r) for r in table if compact(r)]
                if not rows or not rows[0][0].lower().startswith(header):
                    continue
                # Some tables are read without their Total column (the header ends with a year); their total is
                # the sum of the Jumlah row's years, counted in TOTALS_FROM_YEARS
                has_total = not re.fullmatch(r"\d{4}", rows[0][-1])
                for r in rows[1:]:
                    if r[0].lower() in ("jumlah", "total"):
                        if not has_total:
                            total = sum(number(x) for x in r[1:])
                            TOTALS_FROM_YEARS.append({"chapter": code, "page": q, "table": header[0], "total": total})
                            return total, q
                        total = number(r[-1])
                        # The Jumlah row's yearly cells must add up to its total
                        yearly = sum(number(x) for x in r[1:-1])
                        known = KNOWN_YEAR_GAPS.get((code, header[0]))
                        if known is not None:
                            assert abs((yearly - total) - known["gap"]) < 0.5, (code, header[0], yearly - total, "known gap changed")
                        elif abs(yearly - total) > 1:
                            raise ValueError(f"{code} page {q}: Jumlah row years sum to {yearly}, total {total}")
                        # The rows' own totals should add up to it too; a mismatch is a printed error, recorded
                        if abs(sum(parts) - total) > 1:
                            RECAP_MISMATCHES.append({"chapter": code, "page": q, "table": header[0], "rows_sum": sum(parts), "jumlah": total})
                        return total, q
                    parts.append(number(r[-1]) if has_total else sum(number(x) for x in r[1:]))
        raise ValueError(f"{code}: recap table after page {p} has no Jumlah row")
    raise ValueError(f"{code}: no recap table title found")


# Steps

# Read the BPS province list that every province name is matched against
provinces, lookup = cleaning.load_bps_provinces(RAW_PROVINCES)

# Read each chapter's three tables
rows, pages = [], {}
with pdfplumber.open(RAW_PDF) as pdf:
    check_headings(pdf)
    for code in CHAPTERS:
        plants = read_plants(pdf, code)
        kms, kms_page = read_recap(pdf, code, READ_CONTEXT["transmission_title"], ("transmisi", "tegangan"))
        mva, mva_page = read_recap(pdf, code, READ_CONTEXT["substation_title"], ("gardu induk", "trafo", "gi ", "tegangan"))
        values = {"installed_capacity_mw": plants["installed_capacity_mw"], "coal_capacity_mw": plants["coal_capacity_mw"],
                  "transmission_plan_2025_2034_kms": kms, "substation_plan_2025_2034_mva": mva}
        rows += [{"region": code, "indicator": i, "period": PERIODS[i], "status": "", "value": v} for i, v in values.items()]
        pages[code] = {"plants_page": plants["plants_page"], "plants_gap_mw": plants["plants_gap_mw"], "transmission_page": kms_page, "substation_page": mva_page}
        print(code, values, pages[code])

# Every declared typo was met
assert TYPOS_SEEN == set(TYPOS), set(TYPOS) - TYPOS_SEEN

# Describe the dataset
regions = {code: {"provinces": [cleaning.province_code(n, lookup) for n in names], "names": names, "first_page": page}
           for code, (page, names) in CHAPTERS.items()}
meta = {
    "title": "RUPTL PLN 2025-2034 by province chapter: existing installed and coal (PLTU) capacity, planned transmission (kms) and substations (MVA), RE Base",
    "columns": {
        "region": "RUPTL appendix chapter; the provinces each covers are in 'regions' (two chapters cover several provinces).",
        "indicator": "Indicator code; definitions in 'indicators'.",
        "period": "2024 for existing plants (latest RUPTL data); 2034 for plans, which are cumulative over 2025-2034 (see the indicator names).",
        "status": "Empty.",
        "value": "In the indicator's unit, as printed or summed from printed rows.",
    },
    "regions": regions,
    "provinces": {k: v for k, v in provinces.items() if k != cleaning.NATIONAL_CODE},
    "indicators": INDICATORS,
    "source_tables": {"pdf": {"title": "Rencana Usaha Penyediaan Tenaga Listrik (RUPTL) PT PLN (Persero) 2025-2034, Lampiran A-C",
                              "file": str(RAW_PDF.relative_to(ROOT)), "pages": pages}},
    "notes": [
        "RUPTL covers the PLN system: PLN plants, IPPs selling to PLN, rented plants and excess power bought by PLN. Captive plants (e.g. in nickel industrial parks) are not included.",
        "Chapter A4 covers Kepulauan Riau without Batam, which PT PLN Batam serves outside RUPTL.",
        "Chapter C9 covers Papua, Papua Pegunungan, Papua Tengah and Papua Selatan together; chapter C10 covers Papua Barat and Papua Barat Daya together. Their values cannot be split by province.",
        "Coal capacity counts every row under a PLTU plant type (including PLTU MT, mine-mouth); PLTGU (gas combined cycle) is not coal.",
        "Each chapter's plant rows are checked against its table's grand total (Jumlah). Imported power (Kalimantan Barat buys 120 MW of hydro power from Sarawak) is not counted; the printed total leaves it out too.",
        "Bengkulu's existing-plant table lists no PLTU, although PLTU Teluk Sepang (2 x 100 MW, IPP, 2020) is in Bengkulu; coal capacity follows RUPTL and is 0.",
    ],
    "checks": {"passed": ["identities"], "tolerance_mw": TOLERANCE_MW, "known_plant_gaps": KNOWN_PLANT_GAPS,
               "known_year_gaps": {f"{c} {t}": v for (c, t), v in KNOWN_YEAR_GAPS.items()}, "no_plant_table": NO_PLANT_TABLE,
               "recap_rows_not_adding_up": RECAP_MISMATCHES, "totals_summed_from_years": TOTALS_FROM_YEARS,
               "cells_read_with_dot_or_no_separator": DOT_DECIMALS, "cells_with_footnote_star": STARRED,
               "typos_corrected": {k: TYPOS[k] for k in TYPOS_SEEN}, "flags": []},
}

# Layers 1, 2 and 6: every chapter has every indicator
out = cleaning.write_dataset(
    rows, KEYS,
    allowed={"region": list(CHAPTERS), "indicator": list(INDICATORS)},
    expected={(c, i, PERIODS[i]) for c in CHAPTERS for i in INDICATORS},
    csv_path=OUT_CSV, meta=meta, raw_files=[RAW_PROVINCES, RAW_PDF],
    sort_orders={"region": list(CHAPTERS), "indicator": list(INDICATORS)},
)
print(f"{OUT_CSV.name}: {len(out)} rows, {len(CHAPTERS)} chapters")
