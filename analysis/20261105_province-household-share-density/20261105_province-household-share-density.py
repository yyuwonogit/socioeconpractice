from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# Load the shared chart and panel modules from tools/
import sys
sys.path.insert(0, str(ROOT / "tools"))
import charts
import province_panel

from matplotlib.lines import Line2D
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

# Parameters

# Outputs: the chart and one row per province of every value it plots
OUT_PNG = HERE / "20261105_household-share-density.png"
OUT_CSV = HERE / "20261105_household-share-density.csv"

# T1, two kinds of province. The panel comes from province_panel.build(), which reads data/ only and runs every panel
# check. In 2025 it holds the 38 provinces, one unit each. pkrt_share_pct is household consumption (PKRT) over GRDP by
# expenditure at current prices, both from BPS WebAPI var 534 (Rp billion), in percent. extractive_sharp_share_pct is
# the share of GRDP at current prices of five commodity groups from the BPS SIMDASI yearbook tables of GRDP by detailed
# industry: fossil (oil, gas, coal, refining), metals (ores, smelters), plantation (estate crops, plus food and
# beverage mills where estate crops reach 10% of GRDP), forest (logging, wood, paper) and quarrying (stone, sand,
# cement). BPS marks 2025 GRDP as very preliminary (status ** in the panel's grdp_status for all 38 provinces)
YEAR = 2025
PROVINCES = 38
OUTCOME = "pkrt_share_pct"
GROUPING = province_panel.SHARP_SHARE

# Groups: high extraction is a 2025 extractive share strictly above the median of the 38 provinces' 2025 values
# (province_panel.above_median, 19 provinces), low extraction the other 19; drawn in the series blue and muted grey,
# in this order in the legend and in the rug rows from the top
GROUPS = {
    "high": {"color": charts.SERIES, "label": "Extractive share above the 2025 median"},
    "low": {"color": charts.TEXT_MUTED, "label": "Extractive share below the 2025 median"},
}

# Densities: Gaussian kernel densities with Scott's bandwidth (scipy.stats.gaussian_kde's default), evaluated every
# 0.1 points over one x range that covers all 38 values with room on both sides, wide enough that both tails reach
# about zero inside the plot
XLIM = (0, 100)
XTICKS = list(range(0, 101, 10))
GRID_POINTS = 1001
ROOM = 5
BANDWIDTH = "scott"

# Provinces named at their rug ticks: the three lowest and the three highest household shares
NAMED_EACH_END = 3

# Figure: a full 16:9 slide (charts.SLIDE_SIZE, in inches) at 200 dpi, the plot's left and right edges, the top of the
# density plot and the room under the rug strip for the tick labels and x axis title, as figure fractions
FIGSIZE, DPI = charts.SLIDE_SIZE, 200
LEFT, RIGHT = 0.065, 0.985
PLOT_TOP, BOTTOM = 0.895, 0.085

# Curves: line width in points, fill opacity, headroom above the highest curve as a multiple of its peak, and the mean
# lines' width and dash pattern
LINE_WIDTH, FILL_ALPHA, HEADROOM = 2.0, 0.12, 1.2
MEAN_WIDTH, MEAN_DASH = 1.1, (0, (5, 3))

# Rug strip under the curves, in points: gap under the density baseline, tick length, gap between the two rug rows,
# tick width, gap from the lower rug row to the first name row, gap between name rows, gap from a leader's foot to its
# name, gap between a tick and its leader, the clearance every name and leader keeps, the room under the last name row,
# the leader line width, the name size and the most name rows allowed. A leader runs on from its tick in the tick's
# colour, so one dropping through the other group's rug row cannot read as a tick of that group
RUG_TOP, RUG_LENGTH, RUG_ROW_GAP, RUG_WIDTH = 3, 9, 3, 1.2
NAME_TOP_GAP, NAME_ROW_GAP, LEADER_GAP, LEADER_START = 5, 2, 2, 0
CLEAR, STRIP_FOOT, LEADER_WIDTH, NAME_SIZE, MAX_NAME_ROWS = 2, 2, 0.6, 7.5, 6

# Texts
TITLE = "Household consumption share of GRDP in high- and low-extraction provinces, 2025"
XLABEL = "Household consumption (PKRT), % of GRDP at current prices, 2025"
YLABEL = "Density"
MEAN_LABEL = "Mean {:.1f}%"
LEGEND_LABEL = "{label} ({n} provinces)"

# Functions

def density(values, grid):
    """Return the Gaussian kernel density of values on grid, with the bandwidth BANDWIDTH."""
    return stats.gaussian_kde(values, bw_method=BANDWIDTH)(grid)


def peaks(curve, grid):
    """Return the x positions of a curve's local maxima on its grid, a plateau counting once."""
    inner = (curve[1:-1] > curve[:-2]) & (curve[1:-1] >= curve[2:])
    return grid[1:-1][inner]


def text_size(fig, text, size):
    """Return the width and height in points of a text at a font size, as the figure would draw it."""
    t = fig.text(0, 0, text, fontsize=size)
    bb = t.get_window_extent(fig.canvas.get_renderer())
    t.remove()
    return bb.width * 72 / fig.dpi, bb.height * 72 / fig.dpi


def rug_rows(count):
    """Return the (top, bottom) of each rug row in points below the strip's top edge, as negative numbers."""
    rows = []
    for k in range(count):
        top = -(RUG_TOP + k * (RUG_LENGTH + RUG_ROW_GAP))
        rows.append((top, top - RUG_LENGTH))
    return rows


def stair_names(named, ticks, scale, frame_width):
    """Give each named rug tick a name row below the rug and a side of its leader, like a staircase.

    named: (x in points from the strip's left edge, rug row, width in points) per name, in placing order, the names
        nearest the middle of the x range first. ticks: (x in points, rug row) of every rug tick.
    A name hangs toward the middle of the x range beside the foot of a leader dropping from its tick, or the other way
    when that fits a higher row, and takes the highest row where its name touches no other name or leader, covers no
    named tick still to be placed (whose leader it would block), its leader crosses no name above it and no tick of a
    lower rug row, and the name stays inside the plot.
    Returns (row, side) per name, rows counted from 1 and side +1 for a name right of its leader.
    """
    names, leaders, placed = [], [], []
    middle = frame_width / 2
    for i, (x, rug, width) in enumerate(named):
        prefer = 1 if x < middle else -1
        pending = [p[0] for p in named[i + 1:]]
        choice = None
        for row in range(1, MAX_NAME_ROWS + 1):
            for side in (prefer, -prefer):
                x0 = x + LEADER_GAP if side > 0 else x - LEADER_GAP - width
                x1 = x0 + width
                if x0 < 0 or x1 > frame_width:
                    continue
                # The name leaves room for the leaders of the named ticks still to be placed
                if any(x0 - CLEAR <= px <= x1 + CLEAR for px in pending):
                    continue
                # The name touches no name in its row and no leader passing through or ending in its row
                if any(r == row and not (x1 + CLEAR < a or x0 - CLEAR > b) for a, b, r in names):
                    continue
                if any(r >= row and x0 - CLEAR <= lx <= x1 + CLEAR for lx, r in leaders):
                    continue
                # Its leader crosses no name in the rows it passes and no tick of a lower rug row
                if any(r <= row and a - CLEAR <= x <= b + CLEAR for a, b, r in names):
                    continue
                if any(k > rug and abs(tx - x) < CLEAR + RUG_WIDTH for tx, k in ticks):
                    continue
                choice = (row, side)
                break
            if choice is not None:
                break
        if choice is None:
            raise RuntimeError("a province name finds no free row under the rug")
        row, side = choice
        x0 = x + LEADER_GAP if side > 0 else x - LEADER_GAP - width
        names.append((x0, x0 + width, row))
        leaders.append((x, row))
        placed.append(choice)
    return placed


# Steps

# Build the harmonised panel with all its checks and keep the 2025 rows, one per province
b = province_panel.build()
rows = b.panel[b.panel["year"] == YEAR]
assert len(rows) == PROVINCES and rows["unit"].is_unique, "2025 should hold the 38 provinces, one unit each"
assert rows[[OUTCOME, GROUPING]].notna().all().all(), "every province needs both shares in 2025"

# Split the provinces at the median 2025 extractive share and keep one row per province of what the chart plots
high = province_panel.above_median(rows[GROUPING]).to_numpy()
cutoff = rows[GROUPING].median()
table = pd.DataFrame({"unit": rows["unit"].to_numpy(),
                      "province": rows["unit_name"].map(charts.display_name).to_numpy(),
                      "extractive_share_pct": rows[GROUPING].to_numpy(),
                      "group": np.where(high, "high", "low"),
                      OUTCOME: rows[OUTCOME].to_numpy()})
table = table.sort_values(["group", OUTCOME, "unit"]).reset_index(drop=True)
assert (table["group"].value_counts() == PROVINCES // 2).all(), "the median should split the provinces 19 and 19"

# Check that the x range covers every value with room on both sides
assert XLIM[0] <= table[OUTCOME].min() - ROOM and table[OUTCOME].max() + ROOM <= XLIM[1], "widen XLIM"

# Each group's density on the grid, its summary statistics and its peaks
grid = np.linspace(*XLIM, GRID_POINTS)
summary = {}
for g in GROUPS:
    v = table.loc[table["group"] == g, OUTCOME].to_numpy()
    curve = density(v, grid)
    summary[g] = {"n": len(v), "mean": v.mean(), "median": np.median(v), "min": v.min(), "max": v.max(),
                  "curve": curve, "peaks": peaks(curve, grid)}

# Report the numbers the hypothesis turns on
print(f"Median 2025 extractive share {cutoff:.2f}%")
for g, s in summary.items():
    print(f"{g}: n {s['n']}, mean {s['mean']:.2f}, median {s['median']:.2f}, min {s['min']:.2f}, "
          f"max {s['max']:.2f}, peaks at {', '.join(f'{p:.1f}' for p in s['peaks'])}")

# Open the figure, and measure the names of the three lowest and three highest household shares
fig = plt.figure(figsize=FIGSIZE, dpi=DPI)
fig.patch.set_facecolor(charts.SURFACE)
by_share = table.sort_values([OUTCOME, "unit"])
named = pd.concat([by_share.head(NAMED_EACH_END), by_share.tail(NAMED_EACH_END)])
sizes = {p: text_size(fig, p, NAME_SIZE) for p in named["province"]}
text_height = max(h for _, h in sizes.values())

# Lay the names out under the rug in points: x from the plot's left edge, rows below the two rug rows
frame_width = (RIGHT - LEFT) * FIGSIZE[0] * 72
scale = frame_width / (XLIM[1] - XLIM[0])
rug_index = {g: k for k, g in enumerate(GROUPS)}
rugs = rug_rows(len(GROUPS))
ticks = [((x - XLIM[0]) * scale, rug_index[g]) for x, g in zip(table[OUTCOME], table["group"])]
middle = (XLIM[0] + XLIM[1]) / 2
named = named.assign(distance=(named[OUTCOME] - middle).abs()).sort_values(["distance", "unit"])
layout = stair_names([((x - XLIM[0]) * scale, rug_index[g], sizes[p][0])
                      for x, g, p in zip(named[OUTCOME], named["group"], named["province"])], ticks, scale, frame_width)
name_top = rugs[-1][1] - NAME_TOP_GAP
step = text_height + NAME_ROW_GAP
rows_used = max(r for r, _ in layout)
strip_height = -(name_top - (rows_used - 1) * step - text_height) + STRIP_FOOT

# Place the rug strip under the density plot, both on one x axis
strip = strip_height / 72 / FIGSIZE[1]
ax_rug = fig.add_axes([LEFT, BOTTOM, RIGHT - LEFT, strip])
ax = fig.add_axes([LEFT, BOTTOM + strip, RIGHT - LEFT, PLOT_TOP - BOTTOM - strip], sharex=ax_rug)

# Draw each group's density as a line over a light fill in its colour
for g, style in GROUPS.items():
    ax.fill_between(grid, 0, summary[g]["curve"], facecolor=style["color"], alpha=FILL_ALPHA, linewidth=0, zorder=2)
    ax.plot(grid, summary[g]["curve"], color=style["color"], lw=LINE_WIDTH, zorder=3)
top = HEADROOM * max(s["curve"].max() for s in summary.values())
ax.set_xlim(*XLIM)
ax.set_ylim(0, top)

# Mark each group's mean with a dashed line in its colour, labelled at the top on the side away from the other mean
means = {g: s["mean"] for g, s in summary.items()}
for g, style in GROUPS.items():
    lower = means[g] == min(means.values())
    ax.axvline(means[g], color=style["color"], lw=MEAN_WIDTH, linestyle=MEAN_DASH, zorder=2.5)
    ax.annotate(MEAN_LABEL.format(means[g]), (means[g], 1), xycoords=("data", "axes fraction"),
                xytext=(-5 if lower else 5, -4), textcoords="offset points", ha="right" if lower else "left",
                va="top", fontsize=9, color=style["color"])

# Style the density plot: recessive grid, no top or right spine, x tick labels left to the strip below
charts.style_axes(ax)
ax.tick_params(labelbottom=False)
ax.set_ylabel(YLABEL, color=charts.TEXT_SECONDARY, fontsize=10)
ax.set_xticks(XTICKS)

# Style the rug strip: no spines, grid or y ticks, the x tick labels and axis title at its foot
ax_rug.set_facecolor(charts.SURFACE)
for side in ax_rug.spines.values():
    side.set_visible(False)
ax_rug.set_ylim(-strip_height, 0)
ax_rug.set_yticks([])
ax_rug.tick_params(colors=charts.TEXT_SECONDARY, labelsize=9, length=0)
ax_rug.set_xlabel(XLABEL, color=charts.TEXT_SECONDARY, fontsize=10)

# Draw the rug: one short tick per province in its group's colour, one row per group
for g, style in GROUPS.items():
    y_top, y_bottom = rugs[rug_index[g]]
    ax_rug.vlines(table.loc[table["group"] == g, OUTCOME], y_bottom, y_top, colors=style["color"], lw=RUG_WIDTH)

# Name the three lowest and three highest provinces beside the foot of a leader dropping from their ticks
for (x, g, p), (row, side) in zip(zip(named[OUTCOME], named["group"], named["province"]), layout):
    centre = name_top - (row - 1) * step - text_height / 2
    ax_rug.plot([x, x], [rugs[rug_index[g]][1] - LEADER_START, centre], color=GROUPS[g]["color"], lw=LEADER_WIDTH)
    ax_rug.annotate(p, (x, centre), xytext=(side * LEADER_GAP, 0), textcoords="offset points",
                    ha="left" if side > 0 else "right", va="center", fontsize=NAME_SIZE, color=charts.TEXT_PRIMARY)

# Add the title and the legend of the two groups with their counts, and save the chart
handles = [Line2D([], [], color=style["color"], lw=LINE_WIDTH,
                  label=LEGEND_LABEL.format(label=style["label"], n=summary[g]["n"])) for g, style in GROUPS.items()]
charts.finish(fig, TITLE, handles, OUT_PNG, left=LEFT)

# Write every value the chart plots, one row per province
table.to_csv(OUT_CSV, index=False, encoding="utf-8", lineterminator="\n")
