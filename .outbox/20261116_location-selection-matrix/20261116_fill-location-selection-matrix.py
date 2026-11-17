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
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import range_boundaries
import pandas as pd

# Parameters

# The template is read and never written; the filled copy is a new file in this folder
TEMPLATE = ROOT / "reference/20261116_location-selection-matrix.xlsx"
TEMPLATE_SHA256 = "b5bed77be7735885088a16ccbb06403e6814ab49d8b3eeeb40cb250cc6cb98d0"
RAW_PROVINCES = ROOT / "raw/province-codes/20261102_bps-province-codes-2025-s1.json"
ANALYSIS = ROOT / "analysis/20261116_jet-cross-cutting-indicators"
VALUES = ANALYSIS / "20261116_cross-cutting-indicator-values.csv"
COLUMNS = ANALYSIS / "20261116_cross-cutting-indicator-columns.csv"
PLN_UNITS = ANALYSIS / "20261116_pln-units-and-provinces.csv"
DBH = ANALYSIS / "20261116_dbh-2024-by-province.csv"
RUPTL = ANALYSIS / "20261116_ruptl-chapters-and-provinces.csv"

OUT = HERE / "20261116_location-selection-matrix.xlsx"

# Template rows 2-39 hold the 38 provinces in column B
FIRST_ROW, LAST_ROW, NAME_COLUMN = 2, 39, "B"

# Headers each sheet must still carry in the template, so a changed template stops the fill
HEADERS = {
    "FA1 Coal Mining Exposure Index": {"B": "Province", "C": "Coal Production", "D": "Share of Coal Sector in the GRDP", "E": "Coal Mining Exposure Index"},
    "FA2 Coal Power Exposure Index": {"B": "Province", "C": "Operating CFPP Capacity in the Area \n(On Grid + Captive)",
                                      "D": "Operating CFPP Capacity Per Resident", "E": "Coal Power Exposure Index"},
    "FB3 Crit Min & Bat SC Index": {"B": "Province", "C": "Nickel (and other battery-mineral) mine and smelter location - IUP?",
                                    "D": "Investment Realization", "E": "Critical Mineral and Battery Supply Chain Exposure Index"},
    "FB4 Energy Access Index": {"B": "Province", "C": "Electrification ratio", "D": "Clean-cooking-fuel access", "E": "Energy Access and Affordability Index"},
    "FB1 RE Exposure Index": {"B": "Province", "C": "Operating / Planned RE Capacity in the Region",
                              "D": "Share of Coal Sector in the GRDP", "E": "Renewabe Energy Exposure Index"},
    "FB2 Grid-Transm. Exp. Index": {"B": "Province", "C": "Planned / Grid Transmission Corridors and Substation in the Region",
                                    "D": "(TBD)", "E": "Grid and Transmission Exposure Index"},
    "CC1 Labor Market Sensit. Index": {"B": "Province",
                                       "C": "Employment concentration in the pathway-linked sector as a share of total local employment",
                                       "D": "Wages relative to provincial/national average",
                                       "E": "Social-protection coverage (BPJS Ketenagakerjaan / Kesehatan)",
                                       "F": "Labor Market Sensitivity Index"},
    "CC2 Econ. Depend. & Diver Index": {"B": "Province",
                                        "C": "Sector concentration and real growth (share of GRDP and growth rate attributable to the largest pathway-linked sector)",
                                        "D": "TBD", "E": "Economic Dependence & Diversification Index"},
    "CC3 Fiscal & Service Sens. Inde": {"B": "Province", "C": "DBH SDA / Total Pendapatan Daerah", "D": "TBD", "E": "Fiscal & Service Sensitivity Index"},
    "CC4 Poverty & Resilience Index": {"B": "Province", "C": "Poverty headcount", "D": "TBD", "E": "Poverty & Resilience Index"},
    "CC5 Adapt. Capacity Defisit Ind": {"B": "Province", "C": "IPM and components", "D": "TBD", "E": "Adaptive Capacity Defisit Index"},
    "CC6 Inclusion & Ener. Jus.Index": {"B": "Province", "C": "Electricity reliability", "D": "TBD", "E": "Inclusion & Energy Justice Index"},
}

NUMBER_FORMAT = "0.00"

# Header cells the user edited by hand in the delivered file, kept as typed: (sheet, column) -> text
HEADER_OVERRIDES = {
    ("FB2 Grid-Transm. Exp. Index", "C"): "Planned / Grid Transmission Corridors and Substation in the Region\n\n",
}

# Columns inserted into the filled copy on request: sheet -> (new column letter, header). The template's
# columns from that letter on move one column right; the header checks above use the template's letters
INSERTED = {}

# Single template columns filled outside the CC sheets: sheet -> columns
PARTIAL = {"FA1 Coal Mining Exposure Index": ["C", "D"], "FA2 Coal Power Exposure Index": ["C", "D"],
           "FB1 RE Exposure Index": ["C", "D"], "FB2 Grid-Transm. Exp. Index": ["C", "D"],
           "FB3 Crit Min & Bat SC Index": ["C", "D"], "FB4 Energy Access Index": ["C", "D"]}

# Sheets whose every template column is described in the analysis tables (the FB sheets are not filled)
DESCRIBED = [s for s in HEADERS if s.startswith("CC")]
NOTES_SHEET = "Notes"
PLN_SHEET = "CC6 PLN units"
DBH_SHEET = "CC3 DBH 2024"
RUPTL_SHEET = "RUPTL by chapter"

# Header label styling: the template header stays first, the data label follows on its own lines
LABEL_FONT = Font(italic=True, size=9, color="1F4E79")
HEADER_ROW_HEIGHT = 120
COLUMN_WIDTH = 30
PENDING_FILL = PatternFill("solid", fgColor="FFF2CC")

# Functions

def sheet_codes(ws, lookup):
    """Return template row -> BPS province code for one sheet, stopping unless all 38 provinces appear once."""
    rows = {}
    for r in range(FIRST_ROW, LAST_ROW + 1):
        rows[r] = cleaning.province_code(cleaning.english_to_bps_name(ws[f"{NAME_COLUMN}{r}"].value), lookup)
    if len(set(rows.values())) != 38:
        raise ValueError(f"{ws.title}: province names do not give 38 distinct codes")
    return rows


def label_headers(ws, sheet, columns):
    """Write each column's data label under its template header, so the sheet says what each column holds."""
    for c in columns[columns["sheet"] == sheet].itertuples():
        cell = ws[f"{c.column}1"]
        template = INSERTED[sheet][1] if INSERTED.get(sheet, ("",))[0] == c.column else HEADERS[sheet][c.column]
        cell.value = HEADER_OVERRIDES.get((sheet, c.column), f"{template}\n\n{c.header_label}")
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        if c.status != "filled":
            cell.fill = PENDING_FILL
        ws.column_dimensions[c.column].width = max(ws.column_dimensions[c.column].width or 0, COLUMN_WIDTH)
    ws.row_dimensions[1].height = HEADER_ROW_HEIGHT


def write_notes(wb, columns, codes, english, provinces):
    """Add a Notes sheet: what each CC1-CC6 column holds, which cells are blank and why, and the name matching."""
    ws = wb.create_sheet(NOTES_SHEET)
    bold, wrap = Font(bold=True), Alignment(wrap_text=True, vertical="top")
    ws.append(["REDI4JET location selection matrix: cross-cutting indicators CC1-CC6"])
    ws["A1"].font = Font(bold=True, size=12)
    ws.append(["Values are as published by the source, unscaled. Index columns are blank until the team sets the index method. "
               "Each CC1-CC6 header shows the template text, then 'Data: indicator | unit | year | source'. Yellow headers are pending or blank. "
               "Sheets FA1-FB4 are not filled."])
    ws.append([])
    ws.append(["Sheet", "Column", "Template header", "Indicator used", "Definition", "Unit", "Year", "Source", "Status", "Blank cells"])
    for cell in ws[ws.max_row]:
        cell.font = bold
    for c in columns.itertuples():
        ws.append([c.sheet, c.column, HEADERS[c.sheet][c.column], c.label, c.definition, c.unit, c.period, c.source, c.status, c.blank_cells])
    ws.append([])
    ws.append(["Province rows are matched to BPS province codes by name (tools/cleaning.py, english_to_bps_name), never by row position."])
    ws.append(["Template row", "Province (template)", "BPS code", "BPS name"])
    for cell in ws[ws.max_row]:
        cell.font = bold
    for r, code in codes.items():
        ws.append([r, english[code], code, provinces[code]["name"]])
    for row in ws.iter_rows(min_row=4):
        for cell in row:
            cell.alignment = wrap
    for col, width in zip("ABCDEFGHIJ", [32, 9, 34, 40, 70, 22, 10, 50, 40, 70]):
        ws.column_dimensions[col].width = width


def write_pln_sheet(wb, units, english, codes):
    """Add the CC6 illustration: PLN units with SAIDI and SAIFI and the provinces each serves, then each province's unit."""
    ws = wb.create_sheet(PLN_SHEET)
    bold, wrap = Font(bold=True), Alignment(wrap_text=True, vertical="top")
    ws.append(["CC6 C illustration: PLN reports electricity reliability by distribution unit, not by province (PLN Statistik 2024, Tabel 16)"])
    ws["A1"].font = Font(bold=True, size=12)
    ws.append(["SAIDI = average outage hours per customer in 2024; SAIFI = average number of outages per customer. Provinces in one unit share its value in sheet CC6 column C. "
               "Use this table to decide how to regroup: for example keep the shared value, use the Java / outside-Java figure, or weight by another source."])
    ws.append([])
    ws.append(["PLN unit", "SAIDI (hours/customer)", "SAIFI (times/customer)", "Provinces served", "Number of provinces"])
    for cell in ws[ws.max_row]:
        cell.font = bold
    for u in units.itertuples():
        served = ", ".join(english[c] for c in str(u.province_codes).split()) if isinstance(u.province_codes, str) else "(aggregate)"
        ws.append([u.unit_name, u.saidi, u.saifi, served, u.provinces if not u.aggregate else None])
        for cell in ws[ws.max_row][1:3]:
            cell.number_format = NUMBER_FORMAT
    ws.append([])
    ws.append(["Province (template order)", "PLN unit used in CC6 C", "SAIDI used", "Also served by"])
    for cell in ws[ws.max_row]:
        cell.font = bold
    serving = {}
    for u in units[~units["aggregate"]].itertuples():
        for c in str(u.province_codes).split():
            serving.setdefault(c, []).append(u)
    for code in codes.values():
        used = [u for u in serving[code] if u.saidi == PRIMARY_SAIDI[code]]
        others = [u.unit_name for u in serving[code] if u not in used[:1]]
        ws.append([english[code], used[0].unit_name, used[0].saidi, ", ".join(others)])
        ws[ws.max_row][2].number_format = NUMBER_FORMAT
    for row in ws.iter_rows(min_row=4):
        for cell in row:
            cell.alignment = wrap
    for col, width in zip("ABCDE", [42, 22, 22, 70, 20]):
        ws.column_dimensions[col].width = width

def write_dbh_sheet(wb, dbh, english, codes):
    """Add the CC3 DBH amounts: DBH SDA, DBH Minerba, DBH Migas and total DBH per province government, 2024 allocation."""
    ws = wb.create_sheet(DBH_SHEET)
    bold = Font(bold=True)
    ws.append(["CC3 inputs: Dana Bagi Hasil (DBH) allocated to each province government, 2024 (DJPK, Rincian Dana Transfer Umum TA 2024)"])
    ws["A1"].font = Font(bold=True, size=12)
    ws.append(["Thousand rupiah, as published (pagu alokasi). CC3 C and D divide DBH Minerba by total revenue and by PAD from the 2024 APBD once those are in."])
    ws.append([])
    ws.append(["Province", "DBH SDA total", "of which DBH Minerba", "of which DBH Migas", "Total DBH (tax + SDA + palm oil)", "DBH Minerba % of DBH SDA"])
    for cell in ws[ws.max_row]:
        cell.font = bold
    by_code = dbh.set_index("province_code")
    for code in codes.values():
        r = by_code.loc[code]
        share = r["dbh_minerba"] / r["dbh_sda_total"] * 100 if r["dbh_sda_total"] else None
        ws.append([english[code], r["dbh_sda_total"], r["dbh_minerba"], r["dbh_oil_gas"], r["dbh_total"], share])
        for cell in ws[ws.max_row][1:5]:
            cell.number_format = "#,##0"
        ws[ws.max_row][5].number_format = NUMBER_FORMAT
    for col, width in zip("ABCDEF", [32, 18, 20, 18, 26, 22]):
        ws.column_dimensions[col].width = width
    # Place the sheet right after the CC3 sheet, where readers look for the DBH figures
    wb.move_sheet(ws, offset=wb.sheetnames.index("CC3 Fiscal & Service Sens. Inde") + 1 - wb.sheetnames.index(DBH_SHEET))

def write_ruptl_sheet(wb, ruptl, english):
    """Add the RUPTL figures by chapter: existing installed and coal capacity, planned transmission and substations."""
    ws = wb.create_sheet(RUPTL_SHEET)
    bold = Font(bold=True)
    ws.append(["RUPTL PLN 2025-2034 by province chapter (used in FA2 C/D and FB2 C)"])
    ws["A1"].font = Font(bold=True, size=12)
    ws.append(["Existing plants are on the PLN system only (no captive plants). Two chapters cover several Papua provinces together, so those provinces are blank in FA2 and FB2 unless the group value is 0. Kepulauan Riau excludes Batam."])
    ws.append([])
    ws.append(["RUPTL chapter", "Provinces", "Installed capacity, all plants (MW, 2024)", "Coal PLTU capacity (MW, 2024)",
               "Planned transmission 2025-2034 (kms, RE Base)", "Planned substations 2025-2034 (MVA, RE Base)"])
    for cell in ws[ws.max_row]:
        cell.font = bold
    for r in ruptl.itertuples():
        ws.append([r.chapter, ", ".join(english[c] for c in str(r.province_codes).split()), r.installed_capacity_mw, r.coal_capacity_mw,
                   r.transmission_plan_2025_2034_kms, r.substation_plan_2025_2034_mva])
        for cell in ws[ws.max_row][2:]:
            cell.number_format = "#,##0.0"
    for col, width in zip("ABCDEF", [12, 60, 22, 18, 26, 26]):
        ws.column_dimensions[col].width = width

# Steps

# Check the template is the filed version, unchanged
assert hashlib.sha256(TEMPLATE.read_bytes()).hexdigest() == TEMPLATE_SHA256, "template differs from the filed version"

# Read the BPS province list, the values, the column descriptions and the PLN units
provinces, lookup = cleaning.load_bps_provinces(RAW_PROVINCES)
values = pd.read_csv(VALUES, dtype={"province_code": str, "period": str})
columns = pd.read_csv(COLUMNS, dtype={"period": str}, keep_default_na=False)
units = pd.read_csv(PLN_UNITS, dtype={"province_codes": str}, keep_default_na=False)
units["aggregate"] = units["aggregate"].astype(str) == "True"
dbh = pd.read_csv(DBH, dtype={"province_code": str})
ruptl = pd.read_csv(RUPTL, dtype={"province_codes": str})

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

# Every described column is a template column, and every filled column is described
assert {(c.sheet, c.column) for c in columns.itertuples()} == ({(s, k) for s in DESCRIBED for k in HEADERS[s] if k != "B"}
                                                               | {(s, col) for s, (col, _) in INSERTED.items()}
                                                               | {(s, col) for s, cols in PARTIAL.items() for col in cols})

# Insert the requested columns, after the header checks and row matching
for sheet, (col, header) in INSERTED.items():
    ws = wb[sheet]
    ws.insert_cols(openpyxl.utils.column_index_from_string(col))
    ws[f"{col}1"] = header
assert set(map(tuple, values[["sheet", "column"]].drop_duplicates().values)) == {(c.sheet, c.column) for c in columns.itertuples() if c.status == "filled"}

# Write each value into its sheet, column and province row; provinces without a value stay blank
written = 0
for (sheet, col), group in values.groupby(["sheet", "column"]):
    rows = {code: r for r, code in codes_by_sheet[sheet].items()}
    by_code = dict(zip(group["province_code"], group["value"]))
    assert set(by_code) <= set(rows), (sheet, col)
    for code, value in by_code.items():
        cell = wb[sheet][f"{col}{rows[code]}"]
        assert cell.value is None, (sheet, cell.coordinate, "template cell not empty")
        cell.value = float(value)
        cell.number_format = NUMBER_FORMAT
        written += 1

# Label every CC1-CC6 header with the data it holds
for sheet in DESCRIBED + list(INSERTED) + list(PARTIAL):
    label_headers(wb[sheet], sheet, columns)

# English names from the template, by code
first_sheet = next(iter(HEADERS))
english = {code: wb[first_sheet][f"{NAME_COLUMN}{r}"].value for r, code in codes_by_sheet[first_sheet].items()}

# SAIDI each province takes in CC6 C, to show which unit it came from
cc6 = values[(values["sheet"] == "CC6 Inclusion & Ener. Jus.Index") & (values["column"] == "C")]
PRIMARY_SAIDI = dict(zip(cc6["province_code"], cc6["value"]))

# Add the Notes, PLN and DBH sheets and save the filled copy
write_notes(wb, columns, codes_by_sheet[first_sheet], english, provinces)
write_pln_sheet(wb, units, english, codes_by_sheet[first_sheet])
write_dbh_sheet(wb, dbh, english, codes_by_sheet[first_sheet])
write_ruptl_sheet(wb, ruptl, english)

# Excel keeps each table's column names apart from the header cells and reports the file as damaged when
# they differ, so the table columns take the labelled header text
for ws in wb.worksheets:
    for table in ws.tables.values():
        first_col, header_row, last_col, _ = range_boundaries(table.ref)
        names = [ws.cell(header_row, c).value for c in range(first_col, last_col + 1)]
        assert all(isinstance(n, str) for n in names) and len(set(names)) == len(names), (ws.title, names)
        for column, name in zip(table.tableColumns, names):
            column.name = name

# Save the filled copy. Excel for the web (SharePoint) still reported the openpyxl file as damaged, so the
# delivered file is this output opened and re-saved in Excel desktop, after checking every cell value matches
wb.save(OUT)

# Confirm the template file was not touched
assert hashlib.sha256(TEMPLATE.read_bytes()).hexdigest() == TEMPLATE_SHA256
print(f"{OUT.name}: {written} cells filled in {values.groupby(['sheet', 'column']).ngroups} columns; template unchanged")
