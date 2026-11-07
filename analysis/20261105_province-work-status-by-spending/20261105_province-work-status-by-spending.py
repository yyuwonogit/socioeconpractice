from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# Load the shared chart module from tools/
import sys
sys.path.insert(0, str(ROOT / "tools"))
import charts

import json

import matplotlib.pyplot as plt
from matplotlib.colors import to_hex, to_rgb
from matplotlib.patches import Patch
from matplotlib.ticker import MultipleLocator
import numpy as np
import pandas as pd

# Parameters

# Input: BPS's adjusted real spending per capita by province (Pengeluaran per Kapita Disesuaikan, the spending part of
# the new-method Human Development Index, from Susenas; WebAPI var 416), in thousand rupiah per person per year at
# constant 2012 prices, and the metadata beside it that names each province
SPEND_DATA = ROOT / "data" / "20261104_bps-province-real-spending"
SPEND_CSV = SPEND_DATA / "20261104_bps-province-real-spending.csv"
SPEND_META = SPEND_DATA / "20261104_bps-province-real-spending-metadata.json"
SPENDING = "real_spending_per_capita"
YEAR = "2025"

# Input: BPS's persons aged 15 and over who worked in the past week, by status in the main job (Sakernas; WebAPI var
# 2335), in persons; the Agustus 2025 round is period 2025S2, and TOTAL is all seven statuses
EMP_DATA = ROOT / "data" / "20261104_bps-province-employment-by-status"
EMP_CSV = EMP_DATA / "20261104_bps-province-employment-by-status.csv"
EMPLOYED = "employed_persons"
ROUND = "2025S2"
TOTAL = "TOTAL"

# Outputs, beside this script
OUT_PNG = HERE / "20261105_work-status-by-spending.png"
OUT_CSV = HERE / "20261105_work-status-by-spending.csv"

# The national row (Indonesia, code 00) that is left out, which leaves the 38 provinces
NATIONAL = "00"
PROVINCES = 38

# Statuses in the main job, in segment order from the left, with their legend names in plain English. A status's
# share is its persons over TOTAL x 100, the formula the employment metadata gives. BPS hides a cell whose relative
# standard error is 50% or more (note line 2 of the table); in August 2025 these are Jakarta's casual farm cell and
# Papua Pegunungan's employer-with-paid-staff, casual non-farm and casual farm cells. A hidden cell counts as 0 in its
# province's shares, so that province's shares add to less than 100 by the hidden persons' share (the hidden gap)
STATUSES = ["employee", "employer_permanent_paid_help", "own_account", "employer_temporary_or_unpaid_help",
            "casual_non_agriculture", "casual_agriculture", "unpaid_family"]
NAMES = {"employee": "Employee", "employer_permanent_paid_help": "Employer with paid staff",
         "own_account": "Own-account", "employer_temporary_or_unpaid_help": "Employer with unpaid or temporary help",
         "casual_non_agriculture": "Casual non-farm", "casual_agriculture": "Casual farm",
         "unpaid_family": "Unpaid family worker"}

# Segment colours: employees in the series blue and unpaid family workers in a strong warm colour (the Okabe-Ito
# vermilion of the repository's other charts), so the eye goes to the two ends of each bar; the five statuses between
# them in neutral greys, the muted ink mixed toward the surface by these weights, mid grey on the left to light grey
# on the right
END_COLORS = {"employee": charts.SERIES, "unpaid_family": "#D55E00"}
GREY_WEIGHTS = {"employer_permanent_paid_help": 0.0, "own_account": 0.2, "employer_temporary_or_unpaid_help": 0.4,
                "casual_non_agriculture": 0.6, "casual_agriculture": 0.76}

# Segments labelled with their share inside the segment, and the text colour that reads on each fill
LABEL_COLORS = {"employee": charts.SURFACE, "own_account": charts.TEXT_PRIMARY, "unpaid_family": charts.SURFACE}
VALUE_TEXT = "{v:.1f}%"

# Groups: the 38 provinces are cut into thirds at the terciles of their 2025 real spending per capita (pd.qcut on the
# values, cuts near Rp 11.06 and 12.45 million per person per year). Each bar is the unweighted mean of its provinces'
# shares (each province counts once, whatever its number of workers), scaled so the seven means add to 100; the
# scaling only fills the hidden gaps of Jakarta and Papua Pegunungan. Bar order (Lowest third at the top), and the
# colour of each group's name on the ramp from the muted grey (weight 0) to the series blue (weight 1): the lowest
# third, where the thinly settled frontier provinces sit, takes the blue end, as the frontier group does in the sister
# charts, and the highest third the grey end
THIRDS = 3
GROUPS = ["Lowest", "Middle", "Highest"]
GROUP_WEIGHTS = {"Lowest": 1.0, "Middle": 0.5, "Highest": 0.0}

# y tick text of each group, one line each: its name, its range of real spending (Rp million, one decimal) and its count
TICK_LINES = ["{g} third", "Rp {lo}–{hi} million per person per year", "{n} provinces"]

# Texts: title and x axis title
TITLE = "Workers by status in the main job, by real spending per capita, Indonesian provinces, August 2025"
XLABEL = "% of employed persons, August 2025"

# Bars: centres on the y axis (Lowest third at the top), height, and the width in points of the surface-coloured gap
# drawn between segments
POSITIONS = {"Lowest": 2, "Middle": 1, "Highest": 0}
BAR_HEIGHT = 0.56
SEGMENT_GAP = 1.5

# Text sizes of the value labels, the y tick text and the axis title; the gap in points between the y tick text and the
# axis, and the step in points between its lines
VALUE_SIZE, TICK_SIZE, AXIS_TITLE_SIZE = 11, 10, 10
TICK_PAD, LINE_STEP = 10, 13.5

# x axis: 0 to 100 with ticks every 10; y limits in bar positions
X_LIMITS = (0, 100)
X_STEP = 10
Y_LIMITS = (-0.6, 2.6)

# Figure: a full 16:9 slide (charts.SLIDE_SIZE, in inches) at 200 dpi, the axes margins as figure fractions (the left
# one holds the y tick text), and where the title and legend start
FIGSIZE, DPI = charts.SLIDE_SIZE, 200
MARGINS = {"left": 0.27, "right": 0.975, "top": 0.87, "bottom": 0.1}
TEXT_LEFT = 0.03


# Functions

def mix(color_a, color_b, weight):
    """Return a colour between two colours: weight 0 gives the first, 1 the second."""
    a, b = np.array(to_rgb(color_a)), np.array(to_rgb(color_b))
    return to_hex(a + weight * (b - a))


def millions(thousands):
    """Format an amount in thousand rupiah as rupiah millions with one decimal."""
    return f"{thousands / 1000:.1f}"


# Steps

# Read the 2025 real spending per capita of the provinces as text, without Indonesia's row, and turn it into numbers;
# the 38 provinces must each appear once
raw = pd.read_csv(SPEND_CSV, dtype=str, keep_default_na=False)
rows = raw[(raw["indicator"] == SPENDING) & (raw["period"] == YEAR) & (raw["province_code"] != NATIONAL)]
spending = rows.set_index("province_code")["value"].astype(float)
assert len(spending) == PROVINCES and spending.index.is_unique, f"{YEAR}: not one real spending value per province"

# Read the August 2025 employed persons of the provinces by status, one column per status; a hidden cell has no row in
# the dataset and stays empty here
raw = pd.read_csv(EMP_CSV, dtype=str, keep_default_na=False)
rows = raw[(raw["indicator"] == EMPLOYED) & (raw["period"] == ROUND) & (raw["province_code"] != NATIONAL)].copy()
rows["value"] = rows["value"].astype(float)
counts = rows.pivot(index="province_code", columns="work_status", values="value")[STATUSES + [TOTAL]]
assert len(counts) == PROVINCES and counts[TOTAL].notna().all(), f"{ROUND}: not one total per province"
assert set(counts.index) == set(spending.index), "the spending values and the employment counts cover other provinces"

# Note each province's hidden cells, and the persons they leave out: TOTAL minus the published statuses
hidden = {code: [s for s in STATUSES if pd.isna(counts.loc[code, s])] for code in counts.index}
gap_persons = counts[TOTAL] - counts[STATUSES].sum(axis=1)

# Turn each status into its share of the province's employed persons, a hidden cell counting as 0
shares = counts[STATUSES].fillna(0).div(counts[TOTAL], axis=0) * 100

# Cut the provinces into thirds of real spending, noting each group's range and size
group = pd.qcut(spending, THIRDS, labels=GROUPS)
ranges = {g: (spending[group == g].min(), spending[group == g].max(), int((group == g).sum())) for g in GROUPS}
cuts = spending.quantile([1 / THIRDS, 2 / THIRDS]).tolist()

# Each group's bar: the unweighted mean of its provinces' shares, scaled so the seven segments add to 100, and the
# largest move of a segment by the scaling
means = shares.groupby(group, observed=True).mean().loc[GROUPS]
sums = means.sum(axis=1)
bars = means.div(sums, axis=0) * 100
moved = (bars - means).abs().to_numpy().max()

# Colour the segments, and each group's name on the grey-to-blue ramp
colors = {**END_COLORS, **{s: mix(charts.TEXT_MUTED, charts.SURFACE, w) for s, w in GREY_WEIGHTS.items()}}
group_colors = {g: mix(charts.TEXT_MUTED, charts.SERIES, w) for g, w in GROUP_WEIGHTS.items()}

# Draw the axes: the shared style with the vertical grid lines removed, so only the horizontal grid stays
fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
fig.patch.set_facecolor(charts.SURFACE)
fig.subplots_adjust(**MARGINS)
charts.style_axes(ax)
ax.xaxis.grid(False)
ax.set_axisbelow(True)

# Draw each group's bar as seven segments from the left, split by thin gaps in the surface colour, and label the
# employee, own-account and unpaid family segments with their shares inside them
for g in GROUPS:
    y, start = POSITIONS[g], 0.0
    for s in STATUSES:
        width = bars.loc[g, s]
        ax.barh(y, width, left=start, height=BAR_HEIGHT, color=colors[s], edgecolor=charts.SURFACE,
                linewidth=SEGMENT_GAP, zorder=2)
        if s in LABEL_COLORS:
            ax.text(start + width / 2, y, VALUE_TEXT.format(v=width), ha="center", va="center", fontsize=VALUE_SIZE,
                    fontweight="bold", color=LABEL_COLORS[s], zorder=3)
        start += width

# Set the axis limits, the x ticks every 10 points and the x axis title
ax.set_xlim(*X_LIMITS)
ax.set_ylim(*Y_LIMITS)
ax.xaxis.set_major_locator(MultipleLocator(X_STEP))
ax.set_xlabel(XLABEL, fontsize=AXIS_TITLE_SIZE, color=charts.TEXT_SECONDARY, labelpad=10)

# Name each group left of its bar in three lines: its name in bold in the group's colour, then its range of real
# spending and its count, in place of the plain tick labels
ax.set_yticks([POSITIONS[g] for g in GROUPS], labels=[""] * len(GROUPS))
for g in GROUPS:
    lo, hi, n = ranges[g]
    texts = [line.format(g=g, lo=millions(lo), hi=millions(hi), n=n) for line in TICK_LINES]
    for k, text in enumerate(texts):
        ax.annotate(text, (0, POSITIONS[g]), xycoords=("axes fraction", "data"),
                    xytext=(-TICK_PAD, LINE_STEP * (len(texts) // 2 - k)), textcoords="offset points", ha="right",
                    va="center", fontsize=TICK_SIZE, fontweight="bold" if k == 0 else "normal",
                    color=group_colors[g] if k == 0 else charts.TEXT_PRIMARY, annotation_clip=False)

# Add the title and the legend of the seven statuses in segment order, and save the chart
handles = [Patch(facecolor=colors[s], edgecolor="none", label=NAMES[s]) for s in STATUSES]
charts.finish(fig, TITLE, handles, OUT_PNG, left=TEXT_LEFT)

# Write the table: one row per province (group, then real spending, lowest first) with its shares, its hidden cells
# (counted as 0) and its hidden gap in % of employed persons; then one row per group, marked 'mean' in the unit column,
# with the scaled mean shares the bars show and, as its hidden gap, how far the unscaled means fell short of 100
meta = json.loads(SPEND_META.read_text(encoding="utf-8"))
table = pd.DataFrame({"unit": spending.index})
table["province"] = table["unit"].map(lambda code: charts.display_name(meta["provinces"][code]["name"]))
table["real_spending_k"] = table["unit"].map(spending).astype(int)
table["spending_group"] = table["unit"].map(group).astype(str)
for s in STATUSES:
    table[f"{s}_pct"] = table["unit"].map(shares[s]).round(3)
table["hidden_cells"] = table["unit"].map(lambda code: " ".join(hidden[code]))
table["hidden_gap_pct"] = table["unit"].map(gap_persons / counts[TOTAL] * 100).round(3)
table["group_order"] = table["spending_group"].map(GROUPS.index)
table = table.sort_values(["group_order", "real_spending_k", "unit"]).drop(columns="group_order")
group_rows = pd.DataFrame({"unit": "mean", "spending_group": GROUPS,
                           "province": [f"Mean of the {g.lower()} third ({ranges[g][2]} provinces), scaled to 100"
                                        for g in GROUPS]})
for s in STATUSES:
    group_rows[f"{s}_pct"] = [round(bars.loc[g, s], 3) for g in GROUPS]
group_rows["hidden_cells"] = ""
group_rows["hidden_gap_pct"] = [round(100 - sums[g], 3) for g in GROUPS]
pd.concat([table, group_rows], ignore_index=True)[table.columns].to_csv(
    OUT_CSV, index=False, encoding="utf-8", lineterminator="\n")

# Report the cuts, each group's range, size, shares and members, the largest move by the scaling, and the hidden cells
names = dict(zip(table["unit"], table["province"]))
print(f"Cuts: Rp {cuts[0]:,.1f} and {cuts[1]:,.1f} thousand per person per year")
for g in GROUPS:
    lo, hi, n = ranges[g]
    print(f"{g}: Rp {lo:,.0f}-{hi:,.0f} thousand, {n} provinces; unscaled sum {sums[g]:.3f}")
    print("   " + ", ".join(f"{s} {bars.loc[g, s]:.2f}" for s in STATUSES))
    print("   " + "; ".join(f"{names[c]} {spending[c]:,.0f}" for c in spending[group == g].sort_values().index))
print(f"Largest move of a segment by the scaling: {moved:.3f} points")
for code, cells in hidden.items():
    if cells:
        print(f"Hidden in {names[code]} ({group[code]} third): {', '.join(cells)}; "
              f"gap {gap_persons[code]:,.0f} persons, {gap_persons[code] / counts.loc[code, TOTAL] * 100:.2f}% of "
              f"{counts.loc[code, TOTAL]:,.0f} employed")
