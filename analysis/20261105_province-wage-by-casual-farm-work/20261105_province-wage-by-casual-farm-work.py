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
from matplotlib.ticker import MultipleLocator
import numpy as np
import pandas as pd

# Parameters

# Input: BPS's average hourly wage of workers by province (Upah rata-rata per jam pekerja, Rupiah per hour, Sakernas,
# WebAPI var 1172), and the metadata beside it that names each province. BPS gives one figure a year without naming its
# Sakernas round; the 2025 values carry no revision marker. The wages are in each province's own prices, not adjusted
# for regional price levels, so part of any gap between provinces is a gap in living costs
WAGE_DATA = ROOT / "data" / "20261104_bps-province-informal-work-and-hourly-wage"
WAGE_CSV = WAGE_DATA / "20261104_bps-province-informal-work-and-hourly-wage.csv"
WAGE_META = WAGE_DATA / "20261104_bps-province-informal-work-and-hourly-wage-metadata.json"

# Input: BPS's employed persons aged 15 and over by status in the main job (Sakernas, WebAPI var 2335, persons). The
# share of casual farm workers = casual workers in agriculture (Pekerja bebas di pertanian) / all employed persons
# (TOTAL) x 100, from the August 2025 round
EMP_DATA = ROOT / "data" / "20261104_bps-province-employment-by-status"
EMP_CSV = EMP_DATA / "20261104_bps-province-employment-by-status.csv"

# Outputs, beside this script
OUT_PNG = HERE / "20261105_wage-by-casual-farm-work.png"
OUT_CSV = HERE / "20261105_wage-by-casual-farm-work.csv"

# Indicator and period of the wage, and the indicator, the two work statuses and the round (2025S2, August 2025) of the
# employment counts
WAGE, WAGE_PERIOD = "hourly_wage", "2025"
EMPLOYED, CASUAL_FARM, ALL_STATUSES, EMP_PERIOD = "employed_persons", "casual_agriculture", "TOTAL", "2025S2"

# The national row (Indonesia, code 00) is left out, which leaves the 38 provinces. BPS hides the August 2025
# casual-farm cell of DKI Jakarta (31) and Papua Pegunungan (97), as its relative standard error is 50% or more (note 2
# of the table), so those two have no share and stay off the chart, which leaves 36 provinces. Their 2025 hourly wages
# are the highest and the third highest of the 38 provinces; the script prints them
NATIONAL = "00"
PROVINCES = 38
HIDDEN = {"31", "97"}

# Groups: the 36 provinces are cut into thirds at the terciles of their casual-farm share (pd.qcut on the values; the
# cuts fall near 1.97% and 4.57% of the employed), 12 provinces each, named by how many casual farm workers they have.
# Order (legend left to right), and each group's place on the colour ramp from charts.TEXT_MUTED grey (0) to
# charts.SERIES blue (1): the third with the fewest casual farm workers, mostly thinly settled frontier provinces, takes
# the blue end and the third with the most the grey end
THIRDS = 3
GROUPS = ["few", "middle", "many"]
RAMP = {"few": 1.0, "middle": 0.5, "many": 0.0}

# Texts: title, x axis title, each group's legend entry with its range of casual-farm shares and its count, the label
# of each group's median line, each province's value label, and rupiah per thousand rupiah, the unit the chart plots
TITLE = "Average hourly wage by the share of casual farm workers, Indonesian provinces, 2025"
XLABEL = "Average hourly wage, Rp thousand, 2025"
LEGEND = {"few": "Few casual farm workers: {lo}–{hi}% of workers ({n})",
          "middle": "Middle: {lo}–{hi}% ({n})",
          "many": "Many casual farm workers: {lo}–{hi}% ({n})"}
MEDIAN_TEXT = {"few": "Few {m:.1f}", "middle": "Middle {m:.1f}", "many": "Many {m:.1f}"}
VALUE_TEXT = "{v:.1f}"
THOUSAND = 1000

# Marks: stem width in points, dot area in points squared, and the median lines' width and dash pattern
STEM_LW = 1.2
DOT_SIZE = 42
MEDIAN_LW, MEDIAN_DASH = 1.1, (0, (5, 3))

# Text sizes of the province names, the value labels, the median labels and the axis title; the gaps in points from a
# dot's centre to its value label and from the plot's left edge to the names; the margin of the surface-coloured patch
# behind each value label, as a share of its text size (it stays clear of the dot's ring); and a median label's gaps in
# points from its line (across) and from the top of the plot (down)
NAME_SIZE, VALUE_SIZE, MEDIAN_SIZE, AXIS_TITLE_SIZE = 8, 7.5, 9.5, 10
VALUE_OFFSET, NAME_PAD = 6, 6
LABEL_PAD = 0.1
MEDIAN_GAP, MEDIAN_DROP = 4, 3

# x axis: 0 to 40 thousand rupiah with ticks every 5; y axis: one row per province, ROW_PAD rows of room under the
# lowest and TOP_ROOM rows above the highest, which hold the median labels
X_LIMITS = (0, 40)
X_STEP = 5
ROW_PAD, TOP_ROOM = 0.6, 1.6

# Figure: a full 16:9 slide (charts.SLIDE_SIZE, in inches) at 200 dpi, the axes margins as figure fractions (the left
# one leaves room for the longest province name), and where the title and legend start
FIGSIZE, DPI = charts.SLIDE_SIZE, 200
MARGINS = {"left": 0.155, "right": 0.985, "top": 0.875, "bottom": 0.085}
TEXT_LEFT = 0.03


# Functions

def mix(color_a, color_b, weight):
    """Return a colour between two colours: weight 0 gives the first, 1 the second."""
    a, b = np.array(to_rgb(color_a)), np.array(to_rgb(color_b))
    return to_hex(a + weight * (b - a))


def read(path, **keys):
    """Return the rows of a data/ CSV, read as text, that match every key, without Indonesia's row."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    match = df["province_code"] != NATIONAL
    for column, value in keys.items():
        match &= df[column] == value
    return df[match]


# Steps

# Read the 2025 hourly wages as text, one for each of the 38 provinces, and turn them into numbers
wages = read(WAGE_CSV, indicator=WAGE, period=WAGE_PERIOD).set_index("province_code")["value"].astype(float)
assert len(wages) == PROVINCES and wages.index.is_unique, f"{WAGE_PERIOD}: not one hourly wage per province"

# Read the August 2025 counts: all employed persons for each of the 38 provinces, and casual farm workers for every
# province but the two whose cell BPS hides
employed = read(EMP_CSV, indicator=EMPLOYED, period=EMP_PERIOD)
total = employed[employed["work_status"] == ALL_STATUSES].set_index("province_code")["value"].astype(float)
casual = employed[employed["work_status"] == CASUAL_FARM].set_index("province_code")["value"].astype(float)
assert len(total) == PROVINCES and total.index.is_unique and set(total.index) == set(wages.index), \
    f"{EMP_PERIOD}: not one employment total for each province with a wage"
assert casual.index.is_unique and set(total.index) - set(casual.index) == HIDDEN, \
    f"{EMP_PERIOD}: casual-farm cells missing for {sorted(set(total.index) - set(casual.index))}, not {sorted(HIDDEN)}"

# Each shown province's share of casual farm workers in the employed, in percent, its hourly wage and its name from the
# metadata in display case
meta = json.loads(WAGE_META.read_text(encoding="utf-8"))
share = casual / total[casual.index] * 100
df = pd.DataFrame({"unit": share.index, "casual_farm_share_pct": share.to_numpy(),
                   "hourly_wage_rp": wages[share.index].to_numpy()})
df["province"] = df["unit"].map(lambda code: charts.display_name(meta["provinces"][code]["name"]))

# Cut the provinces into thirds on their casual-farm share, noting the cuts and each group's range of shares and size
df["casual_farm_group"] = pd.qcut(df["casual_farm_share_pct"], THIRDS, labels=GROUPS).astype(str)
cuts = df["casual_farm_share_pct"].quantile([1 / 3, 2 / 3]).tolist()
ranges = {g: (df.loc[df["casual_farm_group"] == g, "casual_farm_share_pct"].min(),
              df.loc[df["casual_farm_group"] == g, "casual_farm_share_pct"].max(),
              int((df["casual_farm_group"] == g).sum())) for g in GROUPS}

# Each group's wages and median wage, the gap between the few and the many in rupiah and in percent of the many's
# median, and how many of the few pay more per hour than every province of the many
members = {g: df.loc[df["casual_farm_group"] == g, "hourly_wage_rp"] for g in GROUPS}
medians = {g: m.median() for g, m in members.items()}
gap = medians["few"] - medians["many"]
gap_pct = gap / medians["many"] * 100
above_all = int((members["few"] > members["many"].max()).sum())

# Rank the provinces by hourly wage, the lowest in the bottom row and the highest in the top row, and colour each by its
# group's place on the ramp
df = df.sort_values(["hourly_wage_rp", "unit"]).reset_index(drop=True)
rows = np.arange(len(df))
colors = {g: mix(charts.TEXT_MUTED, charts.SERIES, RAMP[g]) for g in GROUPS}
row_colors = df["casual_farm_group"].map(colors).tolist()
x = (df["hourly_wage_rp"] / THOUSAND).to_numpy()

# Draw the axes: the shared style with the vertical grid lines removed, so only the horizontal grid stays
fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
fig.patch.set_facecolor(charts.SURFACE)
fig.subplots_adjust(**MARGINS)
charts.style_axes(ax)
ax.xaxis.grid(False)
ax.set_axisbelow(True)

# Mark each group's median with a dashed line in its colour beneath the provinces, labelled in bold at the top of the
# plot: the lowest median's label hangs left of its line and the others hang right, so the two close medians keep their
# labels apart
lowest = min(medians, key=medians.get)
for g in GROUPS:
    m = medians[g] / THOUSAND
    ax.axvline(m, color=colors[g], lw=MEDIAN_LW, linestyle=MEDIAN_DASH, zorder=1.5)
    side = -1 if g == lowest else 1
    ax.annotate(MEDIAN_TEXT[g].format(m=m), (m, 1), xycoords=("data", "axes fraction"),
                xytext=(side * MEDIAN_GAP, -MEDIAN_DROP), textcoords="offset points", ha="right" if side < 0 else "left",
                va="top", fontsize=MEDIAN_SIZE, fontweight="bold", color=colors[g], zorder=5)

# Draw each province as a thin stem from 0 to its wage and a filled dot in its group's colour
ax.hlines(rows, 0, x, colors=row_colors, lw=STEM_LW, zorder=2)
for g in GROUPS:
    part = (df["casual_farm_group"] == g).to_numpy()
    ax.scatter(x[part], rows[part], zorder=3, **charts.point_marks({"color": colors[g]}, DOT_SIZE))

# Label each dot with its wage in Rp thousand just right of it, in bold in its group's colour on a patch of the surface
# colour, so a grid or median line stops at the label instead of running between its digits
for r, v, c in zip(rows, x, row_colors):
    ax.annotate(VALUE_TEXT.format(v=v), (v, r), xytext=(VALUE_OFFSET, 0), textcoords="offset points", ha="left",
                va="center", fontsize=VALUE_SIZE, fontweight="bold", color=c, zorder=4,
                bbox={"boxstyle": f"square,pad={LABEL_PAD}", "facecolor": charts.SURFACE, "edgecolor": "none"})

# Set the axis limits and ticks: wages from 0 with ticks every 5 thousand, and one row per province named on the left
ax.set_xlim(*X_LIMITS)
ax.xaxis.set_major_locator(MultipleLocator(X_STEP))
ax.set_ylim(-ROW_PAD, rows[-1] + TOP_ROOM)
ax.set_yticks(rows, labels=df["province"].tolist())
ax.tick_params(axis="y", labelsize=NAME_SIZE, labelcolor=charts.TEXT_PRIMARY, pad=NAME_PAD)
ax.set_xlabel(XLABEL, fontsize=AXIS_TITLE_SIZE, color=charts.TEXT_SECONDARY, labelpad=8)

# Add the title and the legend of the three groups with their ranges of casual-farm shares and counts, and save the chart
handles = [charts.legend_key({"color": colors[g], "label": LEGEND[g].format(
    lo=f"{ranges[g][0]:.1f}", hi=f"{ranges[g][1]:.1f}", n=ranges[g][2])}, g) for g in GROUPS]
charts.finish(fig, TITLE, handles, OUT_PNG, left=TEXT_LEFT)

# Write the table, one row per province in the chart's order from the top; shares rounded to 2 decimals, wages in whole
# rupiah as BPS publishes them
table = df.iloc[::-1][["unit", "province", "casual_farm_share_pct", "casual_farm_group", "hourly_wage_rp"]].copy()
table["casual_farm_share_pct"] = table["casual_farm_share_pct"].round(2)
table["hourly_wage_rp"] = table["hourly_wage_rp"].round().astype(int)
table.to_csv(OUT_CSV, index=False, encoding="utf-8", lineterminator="\n")

# Report the cuts, each group's range of shares, median and range of wages, the gap, and the two provinces left out
print(f"Casual-farm share cuts: {cuts[0]:.2f}% and {cuts[1]:.2f}% of the employed")
for g in GROUPS:
    lo, hi, n = ranges[g]
    print(f"{g}: {lo:.2f}-{hi:.2f}% casual farm, {n} provinces; hourly wage median Rp {medians[g]:,.1f}, "
          f"range Rp {members[g].min():,.0f}-{members[g].max():,.0f}")
print(f"Few minus many: Rp {gap:,.1f} per hour, {gap_pct:.1f}% of the many's median")
print(f"Few provinces paying more than every many province (max Rp {members['many'].max():,.0f}): {above_all} of "
      f"{len(members['few'])}")
for code in sorted(HIDDEN):
    print(f"Left out, casual-farm cell hidden: {charts.display_name(meta['provinces'][code]['name'])}, hourly wage "
          f"Rp {wages[code]:,.0f}")
