from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# Load the shared chart and panel modules from tools/
import sys
sys.path.insert(0, str(ROOT / "tools"))
import charts
import province_panel

import matplotlib.pyplot as plt
from matplotlib import patheffects
from matplotlib.patches import Patch
from matplotlib.ticker import FixedLocator

# Parameters

# The harmonised panel of tools/province_panel.py, built from data/ only. The extractive share is the sharpened
# definition, province_panel.SHARP_SHARE (extractive_sharp_share_pct): the share of GRDP at current prices of five
# commodity groups from the BPS yearbook tables of GRDP by detailed industry (SIMDASI), summed per group as
# <group>_current_bn / detailed_total_current_bn x 100:
#   fossil = B1 oil, gas and geothermal + B2 coal and lignite + C1 coal products and oil and gas refining
#   metals = B3 metal ore mining + C11 basic metals (smelters)
#   plantation = A1c estate crops, + C2 food and beverage mills where A1c is at least 10% of GRDP
#   forest = A2 forestry and logging + C6 wood products + C7 paper, printing and recorded media
#   quarrying = B4 other mining and quarrying + C10 non-metallic mineral products (cement)
# The five group shares add to the extractive share. BPS marks 2025 GRDP as very preliminary; the chart shows no
# marker. In 2025 the panel holds the 38 provinces, one unit each, so every unit is a single BPS province code
YEAR = 2025
TOTAL = province_panel.SHARP_SHARE

# Stack order from 0 outward, with each group's colour and legend label from charts.EXTRACTIVE_GROUP_STYLE
GROUPS = ["fossil", "metals", "plantation", "forest", "quarrying"]

# Reference line: half of GRDP, with its label at the top of the line
CUT_AT = 50
CUT_LABEL = "50%"

# Figure: size in inches at 200 dpi, plot margins as figure fractions, and the figure fraction where the title and
# legend start, at the left edge of the longest province name
FIGSIZE, DPI = (13.5, 11.5), 200
MARGINS = {"left": 0.165, "right": 0.975, "top": 0.885, "bottom": 0.055}
LEFT = 0.02

# Axes: x from 0 with room past the largest bar (74.5%) for its total, fixed ticks every 10 points
XLIM = (0, 82)
XTICKS = list(range(0, 81, 10))

# Marks: bar thickness in row units, the surface-coloured gap between a bar's groups and the reference line's width,
# in points
BAR_HEIGHT = 0.72
GAP = 0.5
CUT_WIDTH = 1.0

# Total labels: font size and the gap from the bar's end, in points
VALUE_SIZE = 8.5
VALUE_OFFSET = 4

# Texts
TITLE = "Extractive share of GRDP by commodity group, Indonesian provinces, 2025"
XLABEL = "Share of GRDP at current prices, 2025, %"

# Outputs
OUT_PNG = HERE / "20261105_extractive-share-ranked.png"
OUT_CSV = HERE / "20261105_extractive-share-ranked.csv"

# Functions

def ranked_shares(panel, year):
    """Return one row per unit in a year with its group shares and total, ranked by the total, largest first; ties go
    to the lower unit code, so the order is the same on every run."""
    rows = panel[panel["year"] == year]
    table = rows[["unit", "unit_name"] + [f"{g}_share_pct" for g in GROUPS] + [TOTAL]].copy()
    table = table.rename(columns={f"{g}_share_pct": g for g in GROUPS} | {TOTAL: "total"})
    table["province"] = table["unit_name"].map(charts.display_name)
    table = table.sort_values(["total", "unit"], ascending=[False, True], kind="mergesort").reset_index(drop=True)
    table.insert(0, "rank", range(1, len(table) + 1))
    return table[["rank", "unit", "province"] + GROUPS + ["total"]]


# Steps

# Build the harmonised panel with all its checks
b = province_panel.build()

# Rank the 2025 provinces by extractive share, with each group's share of GRDP
table = ranked_shares(b.panel, YEAR)

# Lay out one plot, rows top to bottom from the largest share
fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
fig.patch.set_facecolor(charts.SURFACE)
fig.subplots_adjust(**MARGINS)
charts.style_axes(ax)
ax.set_axisbelow(True)
# Keep the grid on the x ticks only, so no line runs on from a bar's end
ax.grid(False, axis="y")

# Stack each province's groups from 0 outward in the group order, each edged by a thin surface gap
rows = list(range(len(table)))
start = [0.0] * len(table)
for g in GROUPS:
    style = charts.EXTRACTIVE_GROUP_STYLE[g]
    ax.barh(rows, table[g], left=start, height=BAR_HEIGHT, color=style["color"], edgecolor=charts.SURFACE,
            linewidth=GAP, zorder=2)
    start = [s + v for s, v in zip(start, table[g])]

# Write the total at the end of each bar, with a surface halo so the reference line stops short of the digits
halo = [patheffects.withStroke(linewidth=charts.HALO, foreground=charts.SURFACE)]
for y, (end, total) in enumerate(zip(start, table["total"])):
    ax.annotate(f"{total:.1f}%", (end, y), xytext=(VALUE_OFFSET, 0), textcoords="offset points", ha="left",
                va="center", fontsize=VALUE_SIZE, color=charts.TEXT_PRIMARY, path_effects=halo, zorder=4)

# Mark half of GRDP with a reference line over the bars, labelled at its top
ax.axvline(CUT_AT, color=charts.CUT, lw=CUT_WIDTH, zorder=3)
ax.annotate(CUT_LABEL, (CUT_AT, 1), xycoords=("data", "axes fraction"), xytext=(0, 4), textcoords="offset points",
            ha="center", va="bottom", fontsize=8, color=charts.TEXT_MUTED)

# Province names on the y axis, the largest share at the top; x from 0 with fixed ticks and its title
ax.set_yticks(rows)
ax.set_yticklabels(table["province"])
ax.set_ylim(len(table) - 0.5, -0.5)
ax.set_xlim(*XLIM)
ax.xaxis.set_major_locator(FixedLocator(XTICKS))
ax.set_xticklabels([str(v) for v in XTICKS])
ax.set_xlabel(XLABEL, color=charts.TEXT_SECONDARY, fontsize=10)

# Title at the top left and the five groups in one legend row under it, then save without a software stamp
handles = [Patch(facecolor=charts.EXTRACTIVE_GROUP_STYLE[g]["color"], edgecolor="none",
                 label=charts.EXTRACTIVE_GROUP_STYLE[g]["label"]) for g in GROUPS]
charts.finish(fig, TITLE, handles, OUT_PNG, left=LEFT)

# Write every plotted value: rank, unit code, province name, the five group shares and the total, in % of GRDP
table.to_csv(OUT_CSV, index=False, encoding="utf-8", lineterminator="\n")

# Report each province above half of GRDP with its largest group and that group's part of its extractive share
for _, r in table[table["total"] > CUT_AT].iterrows():
    top = max(GROUPS, key=lambda g: r[g])
    print(f"{r['rank']:>2} {r['province']}: {r['total']:.1f}%, largest {top} {r[top]:.1f} points = "
          f"{100 * r[top] / r['total']:.0f}% of its total")
print(f"Wrote {OUT_PNG.relative_to(ROOT)} and {OUT_CSV.relative_to(ROOT)}")
