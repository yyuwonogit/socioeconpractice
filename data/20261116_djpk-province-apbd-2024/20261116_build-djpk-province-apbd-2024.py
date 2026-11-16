from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# Load the shared cleaning module from tools/
import sys
sys.path.insert(0, str(ROOT / "tools"))
import cleaning

import re
import xml.etree.ElementTree as ET

import openpyxl
import pdfplumber

# Parameters

# Raw inputs, in priority order:
# 1. DJPK APBD portal exports, one per province government (Tahun 2024, periode November, Sub-wilayah
#    "Provinsi ..."), downloaded by the user and named by province in the file name
# 2. A workbook the user compiled (with Perplexity) from the same portal for all 38 province governments,
#    with sheets for periode November and Desember 2024
# The BPS provincial finance booklet's Tabel 7 (PAD / revenue, realisation 2024) checks the December figures.
RAW_PROVINCES = ROOT / "raw/province-codes/20261102_bps-province-codes-2025-s1.json"
RAW_BOOKLET = ROOT / "raw/fiscal/20261116_bps-statistik-keuangan-pemerintah-provinsi-2024-dan-2025.pdf"
RAW_COMPILED = ROOT / "raw/fiscal/20261116_pendapatan-daerah-pad-provinsi-2024.xlsx"
FILES = {
    "aceh": "ACEH", "bangka-belitung": "KEPULAUAN BANGKA BELITUNG", "bengkulu": "BENGKULU", "jambi": "JAMBI",
    "kalbar": "KALIMANTAN BARAT", "kalteng": "KALIMANTAN TENGAH", "kaltim": "KALIMANTAN TIMUR", "kalut": "KALIMANTAN UTARA",
    "malut": "MALUKU UTARA", "ntb": "NUSA TENGGARA BARAT", "papua-tengah": "PAPUA TENGAH", "sulsel": "SULAWESI SELATAN",
    "sulteng": "SULAWESI TENGAH", "sultra": "SULAWESI TENGGARA", "kalsel": "KALIMANTAN SELATAN", "sumsel": "SUMATERA SELATAN",
}
RAW_FILE = "raw/fiscal/20261116_data-apbd-2024-{}.xls"

# Output; the metadata JSON is written beside it with a -metadata suffix
OUT_CSV = HERE / "20261116_djpk-province-apbd-2024.csv"

KEYS = ["province_code", "indicator", "period"]
PERIOD = "2024"

# How each source writes its values, read from opening the files
READ_CONTEXT = {
    # Exports: Excel 2003 XML (SpreadsheetML), sheet "Data APBD", header Akun / Anggaran / Realisasi / Persentase,
    # rupiah as plain numbers with "." as the decimal mark, account names with a leading space; revenue
    # accounts come first, then spending (from "Belanja Daerah" on), which is not read
    "export": {"sheet": "Data APBD", "header": ["Akun", "Anggaran", "Realisasi", "Persentase"],
               "revenue_parts": ["PAD", "TKDD", "Pendapatan Lainnya"],
               "pad_parts": ["Pajak Daerah", "Retribusi Daerah", "Hasil Pengelolaan Kekayaan Daerah yang Dipisahkan", "Lain-Lain PAD yang Sah"]},
    # Compiled workbook: one sheet per periode, header in row 1, provinces named "Provinsi X" in rows 2-39,
    # rupiah as numbers, a source note in the row after the last province
    "compiled": {"sheets": {"November 2024": "nov", "Desember 2024": "dec"},
                 "header": ["Kode", "Provinsi", "Pendapatan Daerah - Anggaran (Rp)", "Pendapatan Daerah - Realisasi (Rp)",
                            "PAD - Anggaran (Rp)", "PAD - Realisasi (Rp)", "Realisasi PAD / Realisasi Pendapatan (%)", "Realisasi PAD / Anggaran PAD (%)"],
                 "rows": range(2, 40), "source_note": "Sumber: DJPK Kemenkeu, Portal Data SIKD APBD",
                 "label_fixes": {"Bangka Belitung": "KEPULAUAN BANGKA BELITUNG"}},
}
EXPORT_ACCOUNTS = {"Pendapatan Daerah": "revenue", "PAD": "pad", "TKDD": "transfers", "Pendapatan Lainnya": "other_revenue"}

INDICATORS = {}
for acct, a in EXPORT_ACCOUNTS.items():
    INDICATORS[f"{a}_budget"] = {"name": f"{acct}, Anggaran (APBD murni budget), province government", "unit": "Rp", "multiplier": 1}
    for p, month in [("nov", "November"), ("dec", "December")]:
        INDICATORS[f"{a}_actual_{p}"] = {"name": f"{acct}, Realisasi to the end of {month} 2024, province government", "unit": "Rp", "multiplier": 1}

# Values are kept in whole rupiah: the two sources carry sen (sub-rupiah decimals) inconsistently, e.g.
# Kalimantan Barat November revenue ...979.8 in the export and ...979.7 in the compiled workbook
WHOLE_RUPIAH = 0

# Sum checks in rupiah on the exports
TOLERANCE_RP = 1000

# Cross-check: December realised PAD / revenue against the booklet's Tabel 7 (PDF page 78), percentage points;
# both are printed to two decimals, so they agree within rounding
BOOKLET_PAGE = 78
CHECK_TOLERANCE_PT = 0.011

# Known December differences from the booklet (BPS code -> difference in points, compiled minus booklet). Both are
# in realisation, which CC3 does not use; the build checks they are unchanged so any new difference still stops it
KNOWN_DIFFERENCES = {
    "94": {"difference_pt": 4.5966, "why": "Papua: portal December realisation (22.05%) differs from the booklet (17.45%), likely a later realisation update"},
    "76": {"difference_pt": -0.0359, "why": "Sulawesi Barat: 26.27% against 26.31%, timing of the realisation data"},
}

PLAUSIBLE = {"pad_share_budget_pct": (5, 80)}

# Functions

def read_export(path):
    """Read one SpreadsheetML export into account -> {budget, actual_nov} in rupiah (revenue accounts only)."""
    c = READ_CONTEXT["export"]
    ns = {"ss": "urn:schemas-microsoft-com:office:spreadsheet"}
    [sheet] = ET.parse(path).getroot().findall("ss:Worksheet", ns)
    assert sheet.get(f"{{{ns['ss']}}}Name") == c["sheet"], path
    rows = [[(d.get(f"{{{ns['ss']}}}Type"), (d.text or "").strip()) for d in r.findall("ss:Cell/ss:Data", ns)]
            for r in sheet.findall("ss:Table/ss:Row", ns)]
    assert [t for _, t in rows[0]] == c["header"], (path, rows[0])
    out = {}
    for r in rows[1:]:
        name = r[0][1]
        if name == "Belanja Daerah":
            break
        assert name not in out, (path, name, "repeated revenue account")
        cells = {}
        for key, (kind, text) in zip(["budget", "actual_nov"], r[1:3]):
            assert kind == "Number", (path, name, key, kind)
            cells[key] = float(cleaning.parse_number(text, ".", None, max_decimals=2))
        out[name] = cells
    return out


def read_compiled(lookup):
    """Read the compiled workbook into long rows (revenue and PAD, budget and realisation) for each periode sheet."""
    c = READ_CONTEXT["compiled"]
    wb = openpyxl.load_workbook(RAW_COMPILED, data_only=True)
    assert set(wb.sheetnames) == set(c["sheets"]), wb.sheetnames
    rows, ratios = [], {}
    for sheet, p in c["sheets"].items():
        ws = wb[sheet]
        assert [ws.cell(1, k).value for k in range(1, 9)] == c["header"], sheet
        # The source note sits below the last province, after a blank row
        cleaning.require_text(" ".join(str(ws.cell(r, 1).value) for r in (c["rows"].stop, c["rows"].stop + 1)), c["source_note"], sheet)
        seen = set()
        for r in c["rows"]:
            name = re.sub(r"^Provinsi ", "", ws.cell(r, 2).value)
            code = cleaning.province_code(c["label_fixes"].get(name, name), lookup)
            assert code not in seen, (sheet, name)
            seen.add(code)
            v = {k: ws.cell(r, col).value for k, col in [("rev_b", 3), ("rev_a", 4), ("pad_b", 5), ("pad_a", 6), ("share", 7)]}
            assert all(isinstance(x, (int, float)) for x in v.values()), (sheet, name, v)
            # The workbook's own ratio column must follow from its numbers
            assert abs(v["pad_a"] / v["rev_a"] * 100 - v["share"]) < 0.006, (sheet, name)
            for ind, x in [("revenue_budget", v["rev_b"]), ("pad_budget", v["pad_b"]), (f"revenue_actual_{p}", v["rev_a"]), (f"pad_actual_{p}", v["pad_a"])]:
                rows.append({"province_code": code, "indicator": ind, "period": PERIOD, "status": "", "value": float(round(x, WHOLE_RUPIAH))})
            ratios[(code, p)] = v["pad_a"] / v["rev_a"] * 100
        assert len(seen) == 38, sheet
    return rows, ratios


def booklet_ratios(lookup):
    """Read Tabel 7 of the booklet: PAD / total revenue (percent, realisation 2024) by province code."""
    with pdfplumber.open(RAW_BOOKLET) as pdf:
        lines = [" ".join(w["text"] for w in line) for line in cleaning.pdf_visible_lines(pdf.pages[BOOKLET_PAGE - 1])]
    cleaning.require_text("\n".join(lines), "Tabel 7 Derajat", f"booklet page {BOOKLET_PAGE}")
    out = {}
    for t in lines:
        m = re.match(r"^\d+\.\s+(.+?)\s+(\d+,\d+)$", t)
        if m:
            # The booklet letter-spaces short names ("A c e h") and writes Bangka Belitung without Kepulauan
            name = re.sub(r"\b(\w) (?=\w\b)", r"\1", m.group(1))
            name = {"Bangka Belitung": "KEPULAUAN BANGKA BELITUNG"}.get(name, name)
            out[cleaning.province_code(name, lookup)] = cleaning.parse_number(m.group(2), ",", None, decimals=2)
    assert len(out) == 38, len(out)
    return out

# Steps

# Read the BPS province list that every province name is matched against
provinces, lookup = cleaning.load_bps_provinces(RAW_PROVINCES)
regions = [c for c in provinces if c != cleaning.NATIONAL_CODE]

# Read each export, checking its revenue parts add up; an account an export leaves out counts as zero
export_rows, sums = [], []
for slug, name in FILES.items():
    code = cleaning.province_code(name, lookup)
    acc = read_export(ROOT / RAW_FILE.format(slug))
    for col in ["budget", "actual_nov"]:
        for whole, parts in [("Pendapatan Daerah", READ_CONTEXT["export"]["revenue_parts"]), ("PAD", READ_CONTEXT["export"]["pad_parts"])]:
            gap = abs(sum(acc[p][col] for p in parts if p in acc) - acc[whole][col])
            assert gap <= TOLERANCE_RP, (name, whole, col, gap)
            sums.append(gap)
    for acct, a in EXPORT_ACCOUNTS.items():
        if acct in acc:
            export_rows += [{"province_code": code, "indicator": f"{a}_{col}", "period": PERIOD, "status": "", "value": float(round(acc[acct][col], WHOLE_RUPIAH))}
                            for col in ["budget", "actual_nov"]]

# Read the compiled workbook (all 38 provinces)
compiled_rows, compiled_ratios = read_compiled(lookup)

# Layer 4: exports first; every budget and November figure the compiled workbook repeats must match exactly
rows, overlaps = cleaning.merge_sources([("DJPK exports", export_rows), ("compiled workbook", compiled_rows)], KEYS)

# Layer 4: December realised PAD share equals the booklet's Tabel 7 for every province
booklet = booklet_ratios(lookup)
gaps = {c: round(compiled_ratios[(c, "dec")] - booklet[c], 4) for c in regions}
for c, k in KNOWN_DIFFERENCES.items():
    assert abs(gaps[c] - k["difference_pt"]) < 0.001, (c, gaps[c], "known difference changed")
others = {c: g for c, g in gaps.items() if c not in KNOWN_DIFFERENCES}
worst = max(others, key=lambda c: abs(others[c]))
if abs(others[worst]) > CHECK_TOLERANCE_PT:
    raise ValueError(f"{provinces[worst]['name']}: December PAD share differs from the booklet by {others[worst]} points")

# Layer 5: plausibility only flags
budget = {(r["province_code"], r["indicator"]): r["value"] for r in rows}
flags = cleaning.flag_outside([{"province_code": c, "period": PERIOD, "value": budget[(c, "pad_budget")] / budget[(c, "revenue_budget")] * 100}
                               for c in regions], "pad_share_budget_pct", *PLAUSIBLE["pad_share_budget_pct"])

# Describe the dataset
meta = {
    "title": "DJPK APBD 2024 revenue and PAD of the 38 province governments (budget and realisation), Indonesia",
    "columns": {
        "province_code": "BPS province code (kode_bps) of the province government. Names and Kemendagri codes in 'provinces'.",
        "indicator": "Account and column; definitions in 'indicators'. Transfers and other revenue come from the exports only (16 provinces).",
        "period": "YYYY, budget year.",
        "status": "Empty; the sources carry no markers.",
        "value": "Rupiah, rounded to whole rupiah (the sources differ in sen).",
    },
    "provinces": {c: provinces[c] for c in regions},
    "indicators": INDICATORS,
    "source_tables": {
        "exports": {"source": "DJPK portal, Data APBD (https://djpk.kemenkeu.go.id/portal/data/apbd), Tahun 2024, periode November, Sub-wilayah 'Provinsi ...', Excel export, downloaded by the user on 2026-11-16",
                    "files": {provinces[cleaning.province_code(n, lookup)]["name"]: RAW_FILE.format(s) for s, n in FILES.items()}},
        "compiled": {"file": str(RAW_COMPILED.relative_to(ROOT)), "source": "Compiled by the user with Perplexity from the same DJPK portal (periode 11 and 12, 2024), uploaded 2026-11-16",
                     "trust": "Used because every value it shares with the exports matches exactly and its December PAD shares equal the BPS booklet for all 38 provinces"},
        "booklet": {"title": "BPS, Statistik Keuangan Pemerintah Provinsi 2024 dan 2025, Tabel 7", "file": str(RAW_BOOKLET.relative_to(ROOT)), "use": "check only"},
    },
    "notes": [
        "Anggaran is the APBD murni budget (the portal notes 'Data APBD Murni'); Realisasi is cumulative to the end of November or December 2024 as received by SIKD.",
        "The exports carry no province name or year; each is identified by its file name, and every figure in it matches the compiled workbook.",
        "The first Kalimantan Selatan export duplicated the Kalimantan Tengah file and was replaced.",
        "Kalimantan Timur's 2024 revenue budget is exactly Rp 20,000,000,000,000 in both sources.",
        "An export with no row for an account (Bangka Belitung: Pendapatan Lainnya; Papua Tengah: Hasil Pengelolaan Kekayaan Daerah yang Dipisahkan) has no row here; the sum checks count it as zero.",
    ],
    "checks": {
        "passed": ["identities", "cross-source"],
        "identities": {"PAD + TKDD + Pendapatan Lainnya = Pendapatan Daerah, and PAD parts = PAD (exports, budget and November)": {"compared": len(sums), "largest_gap_rp": max(sums), "tolerance_rp": TOLERANCE_RP}},
        "cross_source_overlaps": overlaps,
        "booklet_december_pad_share": {"tolerance_pt": CHECK_TOLERANCE_PT, "matching_provinces": len(others), "largest_difference_pt_among_them": abs(others[worst]), "known_differences": KNOWN_DIFFERENCES},
        "plausible_ranges": PLAUSIBLE,
        "flags": flags,
    },
}

# Layers 1, 2 and 6: every province has revenue and PAD, budget and both realisations; exports add transfers and other revenue
expected = {(r["province_code"], r["indicator"], PERIOD) for r in rows}
assert {(c, i, PERIOD) for c in regions for i in ["revenue_budget", "pad_budget", "revenue_actual_nov", "pad_actual_nov", "revenue_actual_dec", "pad_actual_dec"]} <= expected
out = cleaning.write_dataset(
    rows, KEYS,
    allowed={"province_code": regions, "indicator": list(INDICATORS)},
    expected=expected,
    csv_path=OUT_CSV, meta=meta,
    raw_files=[RAW_PROVINCES, RAW_BOOKLET, RAW_COMPILED] + [ROOT / RAW_FILE.format(s) for s in FILES],
    sort_orders={"indicator": list(INDICATORS)},
)

# Report what was written
print(f"{OUT_CSV.name}: {len(out)} rows, 38 provinces, overlaps {overlaps}, booklet: {len(others)} match, {len(KNOWN_DIFFERENCES)} known differences, {len(flags)} flags")
for f in flags:
    print("  flag:", f)
