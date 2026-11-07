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

from matplotlib import patheffects
import matplotlib.pyplot as plt
from matplotlib.ticker import FixedLocator, NullLocator
import numpy as np
from scipy import stats

# Parameters

# T5, pay does not follow output: a four-quadrant scatter of the 38 provinces in 2025, GRDP per worker against the
# employees' average net monthly wage, with the provinces of high extraction filled and the others hollow
YEAR = 2025

# Panel columns read; tools/province_panel.py builds them from data/ with every check of the panel.
# - grdp_per_worker_k: GRDP at current prices (BPS WebAPI var 286, Rp billion; 2025 is very preliminary, **) divided by
#   employed persons of every work status in the Agustus 2025 Sakernas (var 2335), Rp thousand per worker per year,
#   from dataset 20261103_bps-province-grdp-2010-2025 and 20261104_bps-province-employment-by-status
# - employee_wage_month_rp: average net monthly wage of employees (buruh/karyawan/pegawai), Agustus 2025 Sakernas, Rp,
#   from dataset 20261104_bps-province-monthly-wage; casual and own-account work is not in it
# - extractive_sharp_share_pct: share of GRDP at current prices of the five extractive commodity groups (fossil,
#   metals, plantation, forest, quarrying), %, from the SIMDASI yearbook tables in
#   20261103_bps-province-grdp-detailed-industry-2010-2025
OUTPUT = "grdp_per_worker_k"
WAGE = "employee_wage_month_rp"
SHARE = province_panel.SHARP_SHARE

# Divisors to the axis units: Rp thousand to Rp million per year, and Rp to Rp million per month
OUTPUT_PER_MILLION = 1_000
WAGE_PER_MILLION = 1_000_000

# Decimals kept in the table and plotted; 6 decimals of Rp million keep every published digit of both series
DECIMALS = province_panel.DERIVED_DECIMALS

# High extraction: a 2025 extractive share strictly above the median of the 38 provinces (19 provinces). Each group's
# point style and legend text, and its name in the table; low extraction is drawn hollow in the same blue
STYLES = {
    True: {"label": "Extractive share above the 2025 median", "filled": True, "color": charts.SERIES},
    False: {"label": "Extractive share below the 2025 median", "filled": False, "color": charts.SERIES},
}
GROUP_NAMES = {True: "high extraction", False: "low extraction"}

# Cut lines sit at the medians of the 38 provinces on each axis. A point on a line counts as right of it or above it,
# as charts.place_labels counts it; with 38 values each median falls between two provinces, so none sits on a line
QUADRANTS = {
    (True, True): "High output, high pay",
    (True, False): "High output, low pay",
    (False, True): "Low output, high pay",
    (False, False): "Low output, low pay",
}
XCUT_LABEL = "Median {:.0f}"
YCUT_LABEL = "Median {:.2f}"

# Correlation label: Pearson r of the logs of both series and Spearman's rank correlation, which logs do not change
STAT_LABEL = "Pearson r {:.2f} (logs) · Spearman ρ {:.2f}"

# Axis titles, chart title and the files written
XLABEL = "GRDP per worker, Rp million per year at current prices, 2025, log scale"
YLABEL = "Employees' average net monthly wage, Rp million, August 2025, log scale"
TITLE = "GRDP per worker against employees' monthly wage, Indonesian provinces, 2025"
FIGURE = HERE / "20261105_output-vs-pay.png"
TABLE = HERE / "20261105_output-vs-pay.csv"

# Figure size in inches, resolution, and the plot's place in the figure (fractions); the title and the legend row sit
# above TOP, and LEFT is where the plot, the title and the legend start
FIGSIZE, DPI = (14, 11), 200
LEFT, RIGHT, TOP, BOTTOM = 0.07, 0.98, 0.9, 0.07

# Resolution at which the province names are laid out. charts.place_labels keeps each name clear of the other points by
# a 10-pixel box, which at 200 dpi is smaller than a marker, so a name could touch a neighbour's marker; at 72 dpi the
# box spans 10 points, a marker with a gap as wide as the one between a name and its own point. Every position is in
# points or data units, so the layout carries over unchanged when the figure is saved at DPI
LAYOUT_DPI = 72

# Provinces whose markers lie less than half a marker apart (centres closer than 1.5 marker widths, in the same
# quadrant) share one label, their names joined from left to right as the shared flag labels join them: a name set 6
# points from one of them would sit as near the other, so it could not say which marker it belongs to. The label hangs
# from the member farthest from the cut lines, which has the most room
MERGE_REACH_PT = 1.5 * math.sqrt(charts.POINT_SIZE)

# Headroom on each log axis, as a factor beyond the lowest and highest value (less on y, whose values span less than a
# doubling, so the crowd of provinces near both medians gets room for its names), and the plain-number ticks shown;
# charts.log_ticks stops at 400 on x and finds fewer than two ticks on y, so both axes take ticks of their own
X_PAD, Y_PAD = 1.2, 1.05
X_TICKS = [25, 50, 100, 200, 400, 800]
Y_TICKS = [2.5, 3, 3.5, 4, 4.5, 5]

# Font sizes in points: quadrant names, cut-line labels, the correlation label, axis titles
QUADRANT_SIZE, CUT_SIZE, STAT_SIZE, AXIS_SIZE = 11, 8, 9, 10

# Thin halo in the surface colour around all text inside the plot, so grid lines stop short of its letters
HALO = [patheffects.withStroke(linewidth=charts.HALO, foreground=charts.SURFACE)]

# Functions


def plain_log_axis(axis, ticks, set_labels):
    """Show a log axis with fixed ticks written as plain numbers and no minor ticks."""
    axis.set_major_locator(FixedLocator(ticks))
    axis.set_minor_locator(NullLocator())
    set_labels([str(v) for v in ticks])


def overlap_groups(pts, quadrants, reach):
    """Group points whose centres lie less than reach apart, in the same quadrant, chaining through shared members.

    pts: display positions in pixels; quadrants: each point's quadrant; reach: pixels. Returns lists of point indices,
    every point in exactly one list.
    """
    owner = list(range(len(pts)))
    for a in range(len(pts)):
        for b in range(a + 1, len(pts)):
            if quadrants[a] == quadrants[b] and math.dist(pts[a], pts[b]) < reach and owner[a] != owner[b]:
                keep, drop = sorted((owner[a], owner[b]))
                owner = [keep if o == drop else o for o in owner]
    return [[i for i in range(len(pts)) if owner[i] == g] for g in sorted(set(owner))]


# Steps

# Build the harmonised panel with all its checks and keep the 2025 rows, one per province
b = province_panel.build()
d = b.panel[b.panel["year"] == YEAR].copy().reset_index(drop=True)

# Put both series in Rp million, name each province, and split the provinces at the median extractive share
d["x"] = (d[OUTPUT] / OUTPUT_PER_MILLION).round(DECIMALS)
d["y"] = (d[WAGE] / WAGE_PER_MILLION).round(DECIMALS)
d["province"] = d["unit_name"].map(charts.display_name)
d["high"] = province_panel.above_median(d[SHARE])

# Cut both axes at the medians and give each province its quadrant
xcut, ycut = float(d["x"].median()), float(d["y"].median())
d["right"], d["top"] = d["x"] >= xcut, d["y"] >= ycut
d["quadrant"] = [QUADRANTS[(r, t)] for r, t in zip(d["right"], d["top"])]

# Correlate the two series: Pearson on the logs, Spearman on the ranks
pearson = stats.pearsonr(np.log(d["x"]), np.log(d["y"]))
spearman = stats.spearmanr(d["x"], d["y"])
r, rho = float(pearson.statistic), float(spearman.statistic)

# Set up the figure and its log axes, with headroom beyond the extreme points and the shared recessive style
fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
fig.patch.set_facecolor(charts.SURFACE)
fig.subplots_adjust(left=LEFT, right=RIGHT, top=TOP, bottom=BOTTOM)
ax.set_xscale("log")
ax.set_yscale("log")
ax.set_xlim(d["x"].min() / X_PAD, d["x"].max() * X_PAD)
ax.set_ylim(d["y"].min() / Y_PAD, d["y"].max() * Y_PAD)
charts.style_axes(ax)
plain_log_axis(ax.xaxis, X_TICKS, ax.set_xticklabels)
plain_log_axis(ax.yaxis, Y_TICKS, ax.set_yticklabels)
ax.set_xlabel(XLABEL, color=charts.TEXT_SECONDARY, fontsize=AXIS_SIZE)
ax.set_ylabel(YLABEL, color=charts.TEXT_SECONDARY, fontsize=AXIS_SIZE)

# Draw the cut lines beneath the points, then the hollow low-extraction points and the filled high-extraction ones
ax.axvline(xcut, color=charts.CUT, lw=1, zorder=1)
ax.axhline(ycut, color=charts.CUT, lw=1, zorder=1)
for high in (False, True):
    part = d[d["high"] == high]
    ax.scatter(part["x"], part["y"], marker="o", zorder=3, **charts.point_marks(STYLES[high], charts.POINT_SIZE))

# Name each quadrant in its outer corner
texts = []
for (right, top), name in QUADRANTS.items():
    texts.append(ax.text(0.99 if right else 0.01, 0.98 if top else 0.02, name, transform=ax.transAxes,
                         ha="right" if right else "left", va="top" if top else "bottom", fontsize=QUADRANT_SIZE,
                         fontweight="bold", color=charts.TEXT_SECONDARY, path_effects=HALO))

# Label the cut lines with their values: the x median at the foot of its line, the y median at the line's right end
texts.append(ax.annotate(XCUT_LABEL.format(xcut), (xcut, 0), xycoords=("data", "axes fraction"), xytext=(4, 4),
                         textcoords="offset points", fontsize=CUT_SIZE, color=charts.TEXT_MUTED, path_effects=HALO))
texts.append(ax.annotate(YCUT_LABEL.format(ycut), (1, ycut), xycoords=("axes fraction", "data"), xytext=(-4, 4),
                         textcoords="offset points", ha="right", fontsize=CUT_SIZE, color=charts.TEXT_MUTED,
                         path_effects=HALO))

# Write the correlations at the top of the plot, just left of the x cut line, where no point sits
texts.append(ax.annotate(STAT_LABEL.format(r, rho), (xcut, 1), xycoords=("data", "axes fraction"), xytext=(-8, -6),
                         textcoords="offset points", ha="right", va="top", fontsize=STAT_SIZE,
                         color=charts.TEXT_SECONDARY, path_effects=HALO))

# Lay the names out at the layout resolution; then join the names of provinces whose markers overlap into one label on
# the member farthest from the cut lines
fig.set_dpi(LAYOUT_DPI)
fig.canvas.draw()
renderer = fig.canvas.get_renderer()
pts = ax.transData.transform(list(zip(d["x"], d["y"])))
cx, cy = ax.transData.transform((xcut, ycut))
labels = [""] * len(d)
for group in overlap_groups(pts, d["quadrant"].tolist(), MERGE_REACH_PT * fig.dpi / 72):
    anchor = max(group, key=lambda i: min(abs(pts[i][0] - cx), abs(pts[i][1] - cy)))
    labels[anchor] = ", ".join(d["province"][i] for i in sorted(group, key=lambda i: d["x"][i]))
    if len(group) > 1:
        print("Shared label:", labels[anchor])

# Name every province, each name kept inside its point's quadrant and clear of the text drawn above
charts.place_labels(ax, d["x"].tolist(), d["y"].tolist(), labels,
                    avoid=[charts.box_of(t, renderer, pad=2) for t in texts], cuts=(xcut, ycut), halo=True)

# Return to the full resolution the figure was made at, add the title and the legend of the two groups, and save it
fig.set_dpi(DPI)
charts.finish(fig, TITLE, [charts.legend_key(STYLES[high], high) for high in (True, False)], FIGURE, left=LEFT)

# Write every plotted value, one row per province in unit order
table = d.assign(extractive_share_pct=d[SHARE], group=d["high"].map(GROUP_NAMES), grdp_per_worker_m=d["x"],
                 monthly_wage_m=d["y"])[["unit", "province", "extractive_share_pct", "group", "grdp_per_worker_m",
                                         "monthly_wage_m", "quadrant"]]
table.to_csv(TABLE, index=False, encoding="utf-8", lineterminator="\n")

# Report the correlations, the medians and the high-output, low-pay corner
corner = d[d["right"] & ~d["top"]]
print(f"Pearson r (logs) {r:.3f}, p {pearson.pvalue:.3f}; Spearman rho {rho:.3f}, p {spearman.pvalue:.3f}; "
      f"n {len(d)}")
print(f"Medians: GRDP per worker Rp {xcut:.2f} million per year, monthly wage Rp {ycut:.4f} million; "
      f"extractive share {d[SHARE].median():.2f}% ({int(d['high'].sum())} provinces above)")
print(f"High output, low pay: {len(corner)} provinces, {int(corner['high'].sum())} of high extraction")
for _, row in corner.iterrows():
    print(f"  {row['unit']} {row['province']}: {row[SHARE]:.1f}% extractive, {GROUP_NAMES[row['high']]}, "
          f"Rp {row['x']:.1f} million per worker, Rp {row['y']:.2f} million per month")
