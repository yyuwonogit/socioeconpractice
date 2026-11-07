from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# Load the shared chart and panel modules from tools/
import sys
sys.path.insert(0, str(ROOT / "tools"))
import charts
import province_panel

import math

import matplotlib.pyplot as plt
from matplotlib.colors import to_hex, to_rgb
from matplotlib.ticker import MultipleLocator
import numpy as np
import pandas as pd
from scipy import stats

# Parameters

# Outputs, beside this script
OUT_PNG = HERE / "20261105_schooling-by-grdp.png"
OUT_CSV = HERE / "20261105_schooling-by-grdp.csv"

# Cross-section year: the panel holds the 38 provinces on their own borders in 2025, one unit each
YEAR = 2025
PROVINCES = 38

# Panel columns: GRDP per capita at constant 2010 prices (Rp thousand per person) and BPS's school participation rate
# at ages 19-23 (Angka Partisipasi Sekolah, % of the age group, Susenas)
INCOME = "grdp_pc_constant_2010_k"
OUTCOME = "aps_19_23_pct"

# Western Indonesia (Kawasan Barat Indonesia, KBI): the BPS codes of Sumatra, Java and Bali. Every other province is
# Eastern Indonesia (Kawasan Timur Indonesia, KTI): Kalimantan, Sulawesi, Nusa Tenggara, Maluku and Papua
WEST_CODES = ["11", "12", "13", "14", "15", "16", "17", "18", "19", "21", "31", "32", "33", "34", "35", "36", "51"]
WEST_COUNT, EAST_COUNT = 17, 21

# Rp thousand in one Rp million, and the decimals the table keeps of GRDP per capita in Rp million (the panel's two
# decimals in Rp thousand)
THOUSAND_PER_MILLION = 1000
MILLION_DECIMALS = 5

# GRDP groups, poorest first: the 38 provinces ranked on GRDP per capita (ties broken by order) and cut into three
# groups with pd.qcut on the rank, which gives 13, 12 and 13 provinces
GROUPS = ["Poorest third", "Middle third", "Richest third"]

# Region of each province in the table, and the legend entries of the filled (eastern) and hollow (western) dots
REGION_EAST, REGION_WEST = "Eastern Indonesia", "Western Indonesia"
LEGEND_EAST = "Eastern Indonesia: Kalimantan, Sulawesi, Nusa Tenggara, Maluku, Papua"
LEGEND_WEST = "Western Indonesia: Sumatra, Java, Bali"

# Texts: title, axis titles, the second line of each x tick (GRDP per capita range of the group) and the gap label
# above the richest box (the richest third's median minus the poorest third's, in percentage points)
TITLE = "School participation at ages 19–23 by GRDP per capita group, Indonesian provinces, 2025"
YLABEL = "School participation, ages 19–23, % of the age group"
XLABEL = "GRDP per capita at constant 2010 prices, 2025"
RANGE_TEXT = "Rp {lo}–{hi} million"
GAP_TEXT = "{gap} points vs poorest third"

# Boxes: centres on the x axis, width, whiskers at 1.5 times the interquartile range, no outlier markers, fill as a
# light tint of the series colour (its weight mixed into the surface colour) and line widths of the edges and median
POSITIONS = [0, 1, 2]
BOX_WIDTH = 0.5
WHISKER = 1.5
TINT_WEIGHT = 0.16
EDGE_LW, MEDIAN_LW = 1.2, 2.4

# Dots: marker area in points squared (the shared size, which the legend keys use too), the half-width of their slots
# around a box's centre (inside the box's own half-width), and the stride of the slots as a fraction of a group's
# count (see slots)
DOT_SIZE = charts.POINT_SIZE
SPREAD = 0.18
STRIDE_FRACTION = 0.382

# Room in pixels that the province names keep from the boxes' edges, whiskers, caps and medians
EDGE_PAD = 2

# Text sizes of the province names, the gap label and the axis titles, and the gap label's offset in points above
# the richest third's highest dot
LABEL_SIZE, GAP_SIZE, AXIS_TITLE_SIZE, TICK_SIZE = 8.5, 11, 10, 10
GAP_OFFSET = 12

# y axis: tick step, and the room in percentage points kept below the lowest dot and above the highest one
Y_STEP = 10
Y_ROOM_LOW, Y_ROOM_HIGH = 3, 3

# x axis limits, in box positions
X_LIMITS = (-0.6, 2.6)

# Figure size in inches at 200 dpi, the axes margins as figure fractions, and where the title and legend start
FIGSIZE, DPI = (12.5, 7.6), 200
MARGINS = {"left": 0.075, "right": 0.985, "top": 0.885, "bottom": 0.15}
TEXT_LEFT = 0.03


# Functions

def tint(color, weight):
    """Return a colour mixed into the chart surface: weight 0 gives the surface colour, 1 the colour itself."""
    c, s = np.array(to_rgb(color)), np.array(to_rgb(charts.SURFACE))
    return to_hex(s + weight * (c - s))


def slots(values, half_width):
    """Return each value's horizontal offset from its box's centre, from evenly spaced slots.

    The n values take n slots spaced evenly from -half_width to +half_width. The value of rank r (lowest 0, ties
    broken by order) takes slot r * stride mod n, with stride the whole number nearest STRIDE_FRACTION * n that shares
    no factor with n, so every value has a slot of its own, values next in rank sit apart, and no slope runs across
    the box.
    """
    n = len(values)
    if n == 1:
        return np.zeros(1)
    lanes = np.linspace(-half_width, half_width, n)
    stride = min((s for s in range(1, n) if math.gcd(s, n) == 1), key=lambda s: (abs(s - STRIDE_FRACTION * n), s))
    ranks = pd.Series(values).rank(method="first").to_numpy().astype(int) - 1
    return lanes[(ranks * stride) % n]


def ranges(lows, highs):
    """Return each group's GRDP per capita range as text in whole Rp million; two groups that meet within half a
    million both show the shared figure."""
    return [RANGE_TEXT.format(lo=f"{lo:.0f}", hi=f"{hi:.0f}") for lo, hi in zip(lows, highs)]


def signed(value):
    """Format a gap in points with one decimal and its sign, a true minus sign for a fall."""
    return f"{'+' if value >= 0 else '−'}{abs(value):.1f}"


# Steps

# Build the harmonised panel from data/ and keep the 2025 cross-section, which must be the 38 provinces on their own
# borders with every value the chart needs
b = province_panel.build()
df = b.panel[b.panel["year"] == YEAR].copy()
assert len(df) == PROVINCES and not df["unit"].str.contains("+", regex=False).any(), f"{YEAR}: not the 38 provinces"
assert df[[INCOME, OUTCOME]].notna().all().all(), f"{YEAR}: a value the chart needs is missing"

# Rank the provinces on GRDP per capita and cut the ranks into the three groups, poorest first
df["grdp_group"] = pd.qcut(df[INCOME].rank(method="first"), len(GROUPS), labels=GROUPS)

# Sort the provinces into Western and Eastern Indonesia by their BPS codes
west = df["unit"].isin(WEST_CODES)
assert west.sum() == WEST_COUNT and (~west).sum() == EAST_COUNT, "the West/East split does not hold 17 and 21 provinces"
df["region"] = np.where(west, REGION_WEST, REGION_EAST)

# GRDP per capita in Rp million and the display names, then the rows from the poorest province up
df["grdp_pc_m"] = (df[INCOME] / THOUSAND_PER_MILLION).round(MILLION_DECIMALS)
df["province"] = df["unit_name"].map(charts.display_name)
df = df.sort_values(INCOME).reset_index(drop=True)

# Each group's rows, school participation median and GRDP per capita range
members = [df[df["grdp_group"] == g] for g in GROUPS]
medians = [m[OUTCOME].median() for m in members]
ticks = [f"{g}\n{r}" for g, r in zip(GROUPS, ranges([m["grdp_pc_m"].min() for m in members],
                                                     [m["grdp_pc_m"].max() for m in members]))]
gap = medians[-1] - medians[0]

# Each province's dot position: its group's box centre plus its slot
df["x"] = 0.0
for pos, m in zip(POSITIONS, members):
    df.loc[m.index, "x"] = pos + slots(m[OUTCOME], SPREAD)

# Draw the axes: the shared style with the vertical grid lines removed, so only the horizontal grid stays
fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
fig.patch.set_facecolor(charts.SURFACE)
fig.subplots_adjust(**MARGINS)
charts.style_axes(ax)
ax.xaxis.grid(False)
ax.set_axisbelow(True)

# Draw one box per group: tinted fill, series-coloured edges, whiskers and median, no outlier markers
line = {"color": charts.SERIES, "lw": EDGE_LW}
parts = ax.boxplot([m[OUTCOME] for m in members], positions=POSITIONS, widths=BOX_WIDTH, whis=WHISKER,
                   showfliers=False, patch_artist=True, zorder=2,
                   boxprops={"facecolor": tint(charts.SERIES, TINT_WEIGHT), "edgecolor": charts.SERIES,
                             "lw": EDGE_LW},
                   medianprops={"color": charts.SERIES, "lw": MEDIAN_LW, "solid_capstyle": "butt"},
                   whiskerprops=line, capprops=line)

# Draw every province as a dot over its box: filled for Eastern Indonesia, hollow for Western Indonesia
filled, hollow = {"color": charts.SERIES}, {"color": charts.SERIES, "filled": False}
for style, rows in [(filled, df[df["region"] == REGION_EAST]), (hollow, df[df["region"] == REGION_WEST])]:
    ax.scatter(rows["x"], rows[OUTCOME], zorder=4, **charts.point_marks(style, DOT_SIZE))

# Set the axis limits, with room below the lowest dot and above the highest for the names and the gap label
low = math.floor((df[OUTCOME].min() - Y_ROOM_LOW) / Y_STEP) * Y_STEP
high = math.ceil((df[OUTCOME].max() + Y_ROOM_HIGH) / Y_STEP) * Y_STEP
ax.set_ylim(low, high)
ax.set_xlim(*X_LIMITS)
ax.yaxis.set_major_locator(MultipleLocator(Y_STEP))

# Name the groups and their GRDP per capita ranges on the x ticks, and title both axes
ax.set_xticks(POSITIONS, labels=ticks)
ax.tick_params(axis="x", labelsize=TICK_SIZE, labelcolor=charts.TEXT_PRIMARY, pad=8)
ax.set_xlabel(XLABEL, fontsize=AXIS_TITLE_SIZE, color=charts.TEXT_SECONDARY, labelpad=10)
ax.set_ylabel(YLABEL, fontsize=AXIS_TITLE_SIZE, color=charts.TEXT_SECONDARY, labelpad=10)

# Label the gap between the richest and poorest thirds' medians above the richest third's highest dot
gap_label = ax.annotate(GAP_TEXT.format(gap=signed(gap)), (POSITIONS[-1], members[-1][OUTCOME].max()),
                        xytext=(0, GAP_OFFSET), textcoords="offset points", ha="center", va="bottom",
                        fontsize=GAP_SIZE, fontweight="bold", color=charts.TEXT_PRIMARY, zorder=5)

# Name the highest and the lowest province of each group, the labels keeping clear of the gap label, of every
# dot's full disc and of the boxes' edges, whiskers, caps and medians
fig.canvas.draw()
renderer = fig.canvas.get_renderer()
radius = (math.sqrt(DOT_SIZE) / 2 + 1) * fig.dpi / 72
centres = ax.transData.transform(df[["x", OUTCOME]].to_numpy())
avoid = [charts.box_of(gap_label, renderer, pad=2)]
avoid += [(cx - radius, cy - radius, cx + radius, cy + radius) for cx, cy in centres]
avoid += [charts.box_of(a, renderer, pad=EDGE_PAD) for a in parts["whiskers"] + parts["caps"] + parts["medians"]]
for patch in parts["boxes"]:
    x0, y0, x1, y1 = charts.box_of(patch, renderer)
    avoid += [(x0 - EDGE_PAD, y - EDGE_PAD, x1 + EDGE_PAD, y + EDGE_PAD) for y in (y0, y1)]
    avoid += [(x - EDGE_PAD, y0 - EDGE_PAD, x + EDGE_PAD, y1 + EDGE_PAD) for x in (x0, x1)]
labels = [""] * len(df)
for m in members:
    for i in (m[OUTCOME].idxmax(), m[OUTCOME].idxmin()):
        labels[i] = df.at[i, "province"]
charts.place_labels(ax, df["x"].tolist(), df[OUTCOME].tolist(), labels, fontsize=LABEL_SIZE, avoid=avoid, halo=True)

# Add the title and the legend under it, and save the chart
handles = [charts.legend_key({**hollow, "label": LEGEND_WEST}, None),
           charts.legend_key({**filled, "label": LEGEND_EAST}, None)]
charts.finish(fig, TITLE, handles, OUT_PNG, left=TEXT_LEFT)

# Write the table, one row per province from the poorest up
df[["unit", "province", "grdp_pc_m", "grdp_group", "region", OUTCOME]].to_csv(
    OUT_CSV, index=False, encoding="utf-8", lineterminator="\n")

# Report each group's school participation and GRDP per capita range, the gap and the rank correlation over the 38
rho = stats.spearmanr(df[INCOME], df[OUTCOME])
for g, m, t in zip(GROUPS, members, ticks):
    print(f"{g}: n {len(m)}, median {m[OUTCOME].median():.2f}, range {m[OUTCOME].min():.2f}-{m[OUTCOME].max():.2f}, "
          f"{t.splitlines()[1]} (GRDP pc {m['grdp_pc_m'].min():.3f}-{m['grdp_pc_m'].max():.3f})")
print(f"Richest minus poorest median: {gap:+.2f} points")
print(f"Spearman rho over {len(df)} provinces: {rho.statistic:.3f} (p {rho.pvalue:.3g})")
print("Labelled:", ", ".join(f"{df.at[i, 'province']} {df.at[i, OUTCOME]:.2f}" for i, t in enumerate(labels) if t))
for region in (REGION_WEST, REGION_EAST):
    part = df[df["region"] == region]
    print(f"{region}: n {len(part)}, median {part[OUTCOME].median():.2f}, by group "
          + ", ".join(f"{g} {int((part['grdp_group'] == g).sum())}" for g in GROUPS))
