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

import pdfplumber

# Parameters

# Raw inputs: the BPS province list, one DJPK APBD export per province government (2024), and the BPS
# provincial finance booklet whose Tabel 7 (PAD / revenue, 2024 realisation) checks each export
RAW_PROVINCES = ROOT / "raw/province-codes/20261102_bps-province-codes-2025-s1.json"
RAW_BOOKLET = ROOT / "raw/fiscal/20261116_bps-statistik-keuangan-pemerintah-provinsi-2024-dan-2025.pdf"

# DJPK exports downloaded by the user from the APBD portal (Tahun 2024, Sub-wilayah "Provinsi ..."), named
# by province in the file name; the files themselves carry no province name or year
FILES = {
    "aceh": "ACEH", "bangka-belitung": "KEPULAUAN BANGKA BELITUNG", "bengkulu": "BENGKULU", "jambi": "JAMBI",
    "kalbar": "KALIMANTAN BARAT", "kalteng": "KALIMANTAN TENGAH", "kaltim": "KALIMANTAN TIMUR", "kalut": "KALIMANTAN UTARA",
    "malut": "MALUKU UTARA", "ntb": "NUSA TENGGARA BARAT", "papua-tengah": "PAPUA TENGAH", "sulsel": "SULAWESI SELATAN",
    "sulteng": "SULAWESI TENGAH", "sultra": "SULAWESI TENGGARA",
    "kalsel": "KALIMANTAN SELATAN", "sumsel": "SUMATERA SELATAN",
}
RAW_FILE = "raw/fiscal/20261116_data-apbd-2024-{}.xls"

# Output; the metadata JSON is written beside it with a -metadata suffix
OUT_CSV = HERE / "20261116_djpk-province-apbd-2024.csv"

KEYS = ["province_code", "indicator", "period"]
PERIOD = "2024"

# How the exports write their values, read from opening them: Excel 2003 XML (SpreadsheetML), one sheet
# "Data APBD", header row Akun / Anggaran / Realisasi / Persentase, rupiah as plain numbers (ss:Type
# "Number", "." decimal mark, no thousands separator), account names with a leading space
READ_CONTEXT = {
    "sheet": "Data APBD",
    "header": ["Akun", "Anggaran", "Realisasi", "Persentase"],
    "unit": "rupiah",
    "revenue_parts": ["PAD", "TKDD", "Pendapatan Lainnya"],
    "pad_parts": ["Pajak Daerah", "Retribusi Daerah", "Hasil Pengelolaan Kekayaan Daerah yang Dipisahkan", "Lain-Lain PAD yang Sah"],
}
ACCOUNTS = {"Pendapatan Daerah": "revenue", "PAD": "pad", "TKDD": "transfers", "Pendapatan Lainnya": "other_revenue"}
COLUMNS = {"Anggaran": "budget", "Realisasi": "actual"}

INDICATORS = {f"{a}_{c}": {"name": f"{acct} ({'Anggaran, APBD murni' if c == 'budget' else 'Realisasi'}), province government",
                            "unit": "Rp", "multiplier": 1, "source": "DJPK APBD portal, export per province (Tahun 2024)"}
              for acct, a in ACCOUNTS.items() for c in COLUMNS.values()}

# Sum checks in rupiah: account parts may be rounded to whole rupiah in the export
TOLERANCE_RP = 1000

# Cross-check: each export's realised PAD / revenue against the booklet's Tabel 7 (PDF page 78), in
# percentage points. The two need not match exactly: the portal's realisation is data received by SIKD at
# download time, the booklet's is BPS's compilation; a wrong province, year or "semua pemda" export
# differs by far more (the duplicate Kalsel download differed by 12 points)
BOOKLET_PAGE = 78
CHECK_TOLERANCE_PT = 3.0

# Plausibility: PAD share of budgeted revenue, percent
PLAUSIBLE = {"pad_share_budget_pct": (5, 80)}

# Functions

def read_export(path):
    """Read one SpreadsheetML export into account -> {budget, actual} in rupiah."""
    ns = {"ss": "urn:schemas-microsoft-com:office:spreadsheet"}
    root = ET.parse(path).getroot()
    [sheet] = root.findall("ss:Worksheet", ns)
    assert sheet.get(f"{{{ns['ss']}}}Name") == READ_CONTEXT["sheet"], path
    rows = [[(d.get(f"{{{ns['ss']}}}Type"), (d.text or "").strip()) for d in r.findall("ss:Cell/ss:Data", ns)]
            for r in sheet.findall("ss:Table/ss:Row", ns)]
    assert [t for _, t in rows[0]] == READ_CONTEXT["header"], (path, rows[0])
    out = {}
    for r in rows[1:]:
        name = r[0][1]
        # Revenue accounts come first; spending and financing (from Belanja Daerah on) are not read
        if name == "Belanja Daerah":
            break
        assert name not in out, (path, name, "repeated revenue account")
        cells = {}
        for col, (kind, text) in zip(READ_CONTEXT["header"][1:3], r[1:3]):
            assert kind == "Number", (path, name, col, kind)
            cells[COLUMNS[col]] = float(cleaning.parse_number(text, ".", None, max_decimals=2))
        out[name] = cells
    return out


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

# Read each export, checking its revenue parts add up
rows, sums, read, missing = [], [], {}, []
for slug, name in FILES.items():
    path = ROOT / RAW_FILE.format(slug)
    code = cleaning.province_code(name, lookup)
    acc = read_export(path)
    for col in COLUMNS.values():
        for whole, parts in [("Pendapatan Daerah", READ_CONTEXT["revenue_parts"]), ("PAD", READ_CONTEXT["pad_parts"])]:
            # An account an export leaves out (e.g. no Pendapatan Lainnya) counts as zero
            gap = abs(sum(acc[p][col] for p in parts if p in acc) - acc[whole][col])
            assert gap <= TOLERANCE_RP, (name, whole, col, gap)
            sums.append(gap)
    for acct, a in ACCOUNTS.items():
        if acct not in acc:
            missing.append((code, acct))
            continue
        for col in COLUMNS.values():
            rows.append({"province_code": code, "indicator": f"{a}_{col}", "period": PERIOD, "status": "", "value": acc[acct][col]})
    read[code] = acc

# Layer 4: realised PAD share matches the booklet within the stated tolerance
booklet = booklet_ratios(lookup)
compared = {}
for code, acc in read.items():
    ours = acc["PAD"]["actual"] / acc["Pendapatan Daerah"]["actual"] * 100
    diff = ours - booklet[code]
    if abs(diff) > CHECK_TOLERANCE_PT:
        raise ValueError(f"{provinces[code]['name']}: realised PAD share {ours:.2f}% vs booklet {booklet[code]:.2f}%")
    compared[code] = {"export_pct": round(ours, 2), "booklet_pct": booklet[code], "difference_pt": round(diff, 2)}

# Layer 5: plausibility only flags
flags = cleaning.flag_outside([{"province_code": c, "period": PERIOD, "value": a["PAD"]["budget"] / a["Pendapatan Daerah"]["budget"] * 100}
                               for c, a in read.items()], "pad_share_budget_pct", *PLAUSIBLE["pad_share_budget_pct"])

# Describe the dataset
meta = {
    "title": "DJPK APBD 2024 revenue and PAD of selected province governments (budget and realisation), Indonesia",
    "columns": {
        "province_code": "BPS province code (kode_bps) of the province government. Names and Kemendagri codes in 'provinces'.",
        "indicator": "Account and column; definitions in 'indicators'.",
        "period": "YYYY, budget year.",
        "status": "Empty; the exports carry no markers.",
        "value": "Rupiah, as exported.",
    },
    "provinces": {c: provinces[c] for c in sorted(read)},
    "indicators": INDICATORS,
    "source_tables": {"exports": {"source": "DJPK portal, Data APBD (https://djpk.kemenkeu.go.id/portal/data/apbd), Tahun 2024, Sub-wilayah 'Provinsi ...', Excel export, downloaded by the user on 2026-11-16",
                                  "files": {provinces[cleaning.province_code(n, lookup)]["name"]: RAW_FILE.format(s) for s, n in FILES.items()}},
                      "booklet": {"title": "BPS, Statistik Keuangan Pemerintah Provinsi 2024 dan 2025, Tabel 7", "file": str(RAW_BOOKLET.relative_to(ROOT)), "use": "check only"}},
    "notes": [
        "Anggaran is the APBD murni budget (the portal notes 'Data APBD Murni'); Realisasi is what SIKD had received when the file was downloaded.",
        "The exports carry no province name or year; each is identified by its file name and checked against the BPS booklet's realised PAD share (checks.cross_source).",
        "Only the province governments the user downloaded are included: those with DBH Minerba of Rp 50 billion or more in 2024 (16 provinces). The first Kalimantan Selatan download duplicated the Kalimantan Tengah file and was replaced.",
        "Kalimantan Timur's 2024 revenue budget is exactly Rp 20,000,000,000,000 in the export.",
        "An export that has no row for an account (Bangka Belitung: Pendapatan Lainnya; Papua Tengah: Hasil Pengelolaan Kekayaan Daerah yang Dipisahkan) has no row here; the sum checks count it as zero.",
        "Realisation is partial for some provinces at download time (Maluku Utara about 43% of budgeted revenue); CC3 uses the budget.",
    ],
    "checks": {
        "passed": ["identities", "cross-source"],
        "identities": {"PAD + TKDD + Pendapatan Lainnya = Pendapatan Daerah, and PAD parts = PAD, budget and realisation": {"compared": len(sums), "largest_gap_rp": max(sums), "tolerance_rp": TOLERANCE_RP}},
        "cross_source": {"tolerance_pt": CHECK_TOLERANCE_PT, "provinces": compared},
        "plausible_ranges": PLAUSIBLE,
        "flags": flags,
    },
}

# Layers 1, 2 and 6: every downloaded province has every account and column
out = cleaning.write_dataset(
    rows, KEYS,
    allowed={"province_code": list(read), "indicator": list(INDICATORS)},
    expected={(c, f"{a}_{col}", PERIOD) for c in read for acct, a in ACCOUNTS.items() if (c, acct) not in missing for col in COLUMNS.values()},
    csv_path=OUT_CSV, meta=meta, raw_files=[RAW_PROVINCES, RAW_BOOKLET] + [ROOT / RAW_FILE.format(s) for s in FILES],
    sort_orders={"indicator": list(INDICATORS)},
)

# Report what was written
print(f"{OUT_CSV.name}: {len(out)} rows, {len(read)} provinces, largest sum gap Rp {max(sums):,.0f}, {len(flags)} flags")
for c, x in compared.items():
    print(f"  {provinces[c]['name']:28s} {x}")
