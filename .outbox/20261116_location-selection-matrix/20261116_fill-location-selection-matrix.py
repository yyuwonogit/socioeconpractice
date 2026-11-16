from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# Load the shared cleaning module from tools/ for province-name matching
import sys
sys.path.insert(0, str(ROOT / "tools"))
import cleaning

import hashlib

import openpyxl
from openpyxl.styles import Alignment, Font
import pandas as pd

# Parameters

# The template is read and never written; the filled copy is a new file in this folder
TEMPLATE = ROOT / "reference/20261116_location-selection-matrix.xlsx"
TEMPLATE_SHA256 = "b5bed77be7735885088a16ccbb06403e6814ab49d8b3eeeb40cb250cc6cb98d0"
RAW_PROVINCES = ROOT / "raw/province-codes/20261102_bps-province-codes-2025-s1.json"
VALUES = ROOT / "analysis/20261116_jet-cross-cutting-indicators/20261116_cross-cutting-indicator-values.csv"
COLUMNS = ROOT / "analysis/20261116_jet-cross-cutting-indicators/20261116_cross-cutting-indicator-columns.csv"

OUT = HERE / "20261116_location-selection-matrix.xlsx"

# Template rows 2-39 hold the 38 provinces in column B
FIRST_ROW, LAST_ROW, NAME_COLUMN = 2, 39, "B"

# Headers each sheet must still carry, so a changed template stops the fill
HEADERS = {
    "CC3 Fiscal & Service Sens. Inde": {"B": "Province", "C": "DBH SDA / Total Pendapatan Daerah", "D": "TBD", "E": "Fiscal & Service Sensitivity Index"},
    "CC4 Poverty & Resilience Index": {"B": "Province", "C": "Poverty headcount", "D": "TBD", "E": "Poverty & Resilience Index"},
    "CC5 Adapt. Capacity Defisit Ind": {"B": "Province", "C": "IPM and components", "D": "TBD", "E": "Adaptive Capacity Defisit Index"},
    "CC6 Inclusion & Ener. Jus.Index": {"B": "Province", "C": "Electricity reliability", "D": "TBD", "E": "Inclusion & Energy Justice Index"},
}

NUMBER_FORMAT = "0.00"
NOTES_SHEET = "Notes"

# Functions

def sheet_codes(ws, lookup):
    """Return template row -> BPS province code for one sheet, stopping unless all 38 provinces appear once."""
    rows = {}
    for r in range(FIRST_ROW, LAST_ROW + 1):
        name = ws[f"{NAME_COLUMN}{r}"].value
        rows[r] = cleaning.province_code(cleaning.english_to_bps_name(name), lookup)
    if len(set(rows.values())) != 38:
        raise ValueError(f"{ws.title}: province names do not give 38 distinct codes")
    return rows


def write_notes(wb, columns, codes, names, provinces):
    """Add a Notes sheet: what each CC3-CC6 column holds, and how template names map to BPS codes."""
    ws = wb.create_sheet(NOTES_SHEET)
    bold, wrap = Font(bold=True), Alignment(wrap_text=True, vertical="top")
    ws.append(["REDI4JET location selection matrix: cross-cutting indicators CC3-CC6, first version"])
    ws["A1"].font = Font(bold=True, size=12)
    ws.append(["Values are as published by the source, unscaled. Index columns (E) are blank until the team sets the index method. Sheets FA1-FB4, CC1 and CC2 are not filled."])
    ws.append([])
    header = ["Sheet", "Column", "Template header", "Indicator used", "Definition", "Unit", "Year", "Source", "Status"]
    ws.append(header)
    for cell in ws[ws.max_row]:
        cell.font = bold
    for c in columns.itertuples():
        ws.append([c.sheet, c.column, HEADERS[c.sheet][c.column], c.label, c.definition, c.unit, c.period, c.source, c.status])
    ws.append([])
    ws.append(["Province rows are matched to BPS province codes by name (tools/cleaning.py, english_to_bps_name), never by row position."])
    ws.append(["Template row", "Province (template)", "BPS code", "BPS name"])
    for cell in ws[ws.max_row]:
        cell.font = bold
    for r, code in codes.items():
        ws.append([r, names[r], code, provinces[code]["name"]])
    for row in ws.iter_rows(min_row=4):
        for cell in row:
            cell.alignment = wrap
    for col, width in zip("ABCDEFGHI", [32, 20, 34, 44, 70, 22, 8, 50, 60]):
        ws.column_dimensions[col].width = width

# Steps

# Check the template is the filed version, unchanged
assert hashlib.sha256(TEMPLATE.read_bytes()).hexdigest() == TEMPLATE_SHA256, "template differs from the filed version"

# Read the BPS province list, the values and the column descriptions
provinces, lookup = cleaning.load_bps_provinces(RAW_PROVINCES)
values = pd.read_csv(VALUES, dtype={"province_code": str, "period": str})
columns = pd.read_csv(COLUMNS, dtype={"period": str}, keep_default_na=False)

# Open the template in memory; only the copy is saved
wb = openpyxl.load_workbook(TEMPLATE)

# Check headers and match every sheet's province rows to codes
codes_by_sheet = {}
for sheet, headers in HEADERS.items():
    ws = wb[sheet]
    for col, text in headers.items():
        cell = ws[f"{col}1"].value
        assert cell is not None and cell.strip() == text, (sheet, col, cell)
    codes_by_sheet[sheet] = sheet_codes(ws, lookup)

# Write each value into its sheet, column and province row, leaving every other cell as in the template
written = 0
for (sheet, col), group in values.groupby(["sheet", "column"]):
    rows = {code: r for r, code in codes_by_sheet[sheet].items()}
    by_code = dict(zip(group["province_code"], group["value"]))
    assert set(by_code) == set(rows), (sheet, col)
    for code, r in rows.items():
        cell = wb[sheet][f"{col}{r}"]
        assert cell.value is None, (sheet, cell.coordinate, "template cell not empty")
        cell.value = float(by_code[code])
        cell.number_format = NUMBER_FORMAT
        written += 1

# Every filled column must be described, and every described column must be on a known sheet
assert set(map(tuple, values[["sheet", "column"]].drop_duplicates().values)) == set(map(tuple, columns.loc[columns["status"] == "filled", ["sheet", "column"]].values))

# Add the Notes sheet and save the filled copy
first_sheet = next(iter(HEADERS))
names = {r: wb[first_sheet][f"{NAME_COLUMN}{r}"].value for r in codes_by_sheet[first_sheet]}
write_notes(wb, columns, codes_by_sheet[first_sheet], names, provinces)
wb.save(OUT)

# Confirm the template file was not touched
assert hashlib.sha256(TEMPLATE.read_bytes()).hexdigest() == TEMPLATE_SHA256
print(f"{OUT.name}: {written} cells filled in {values.groupby(['sheet', 'column']).ngroups} columns; template unchanged")
