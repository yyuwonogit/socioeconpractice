from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# Load the shared chart and panel modules from tools/
import sys
sys.path.insert(0, str(ROOT / "tools"))
import charts
import province_panel

import textwrap

import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.patches import Patch
from matplotlib.ticker import FixedLocator
import numpy as np
import pandas as pd

# Parameters

# Outputs, beside this script
OUT_PNG = HERE / "20261105_schooling-gains.png"
OUT_CSV = HERE / "20261105_schooling-gains.csv"

# Outcomes, those of T6 in the panel tests (province_panel.T6_SERIES): BPS's school participation rate (Angka
# Partisipasi Sekolah, APS), the share of an age group attending school, in percent with 2 decimals, at ages 16-18
# (senior secondary) and 19-23 (higher education), yearly, read by the panel on each unit's own borders. Each column's
# age-group code in the CSV and its panel title, left to right
AGES = {"aps_16_18_pct": ("16-18", "Ages 16–18"), "aps_19_23_pct": ("19-23", "Ages 19–23")}

# Gains run from 2015, the first year every unit has the extractive share (province_panel.SHARP_FIRST_YEAR), to 2025:
# the gain in a year is APS in that year minus APS in 2015, in percentage points, so every 2015 cell is 0
BASE_YEAR = province_panel.SHARP_FIRST_YEAR
LAST_YEAR = 2025
YEARS = list(range(BASE_YEAR, LAST_YEAR + 1))

# Extractive share, province_panel.SHARP_SHARE: the share of GRDP at current prices of the five commodity groups
# (fossil, metals, plantation, forest, quarrying). A row's change is its share in its last year (2025, or 2023 for the
# two pre-split units) minus its share in 2015, in points, and the rows run from the largest rise down
SHARE = province_panel.SHARP_SHARE

# Rows: the units the panel holds in 2015. These are the 32 provinces on fixed borders with every year 2015-2025 (every
# province but the six Papua ones) and the two Papua units on their pre-split borders, which the panel holds to 2023
# because the borders changed in 2024, so their 2024 and 2025 cells stay empty. The four new Papua provinces start in
# 2024 with no 2015 value and stay out. The pre-split units' row names
OLD_BORDERS = {"91+92": "Papua Barat (old borders)", "94+95+96+97": "Papua (old borders)"}

# Provinces whose 2015-2025 gains the run prints, and the gain counted for the median of the full-series provinces
REPORT = ["82", "72"]

# Colour scale: diverging and symmetric around 0, losses in red, 0 in the near-white warm grey of the dataviz skill's
# diverging midpoint, gains in the series blue (the red is matched to the blue's lightness, OKLab L 0.57 and 0.58).
# Linear to +-COLOUR_LIMIT points; the few cells beyond take the end colours, which the colour bar's pointed ends show:
# DKI Jakarta and three Java provinces at 16-18 (to +17.5), Maluku at 19-23 (to -13.2). Cells without a value take a
# light neutral grey
LOSS, ZERO, GAIN = "#cc3b36", "#f0efec", charts.SERIES
EMPTY = "#dcdbd7"
COLOUR_LIMIT = 10
COLOUR_TICKS = [-10, -5, 0, 5, 10]

# Figure size in inches at 200 dpi. Positions as figure fractions: the heatmaps' left edge (the province names sit to
# its left), their top and bottom, each heatmap's width and the gap between the two, then the extractive column's gap
# and width, and the x in that column, as a fraction of its width, where the numbers end
FIGSIZE, DPI = (15, 10.4), 200
LEFT, TOP, BOTTOM = 0.135, 0.835, 0.045
HEAT_WIDTH, HEAT_GAP = 0.364, 0.025
COLUMN_GAP, COLUMN_WIDTH, NUMBER_X = 0.012, 0.085, 0.64
# Title and colour-bar row: the left edge both start at, the baseline of the colour bar's label, and the bar's bottom,
# width and height; the "No value" key sits this far right of the bar
TITLE_X = 0.013
BAR_LABEL_Y, BAR_Y, BAR_WIDTH, BAR_HEIGHT = 0.926, 0.902, 0.2, 0.014
KEY_GAP = 0.018
# The surface-coloured gap between cells, in points
CELL_GAP = 0.8

# Texts and their sizes in points
TITLE = "School participation gained since 2015, by province, ordered by the rise in extractive share"
BAR_LABEL = "Points gained since 2015"
EMPTY_LABEL = "No value"
COLUMN_HEADER = "Change in extractive share, points"
COLUMN_WRAP = 17
PANEL_TITLE_SIZE, ROW_SIZE, SMALL_SIZE = 12, 9, 9

# Functions

def signed(value, digits=1):
    """Return a number as text with its sign, + for a rise and a true minus for a fall, as in +38.0 or −3.2; 0 as 0."""
    if digits == 0 and value == 0:
        return "0"
    return f"{value:+.{digits}f}".replace("-", "−")


def row_order(panel, base, last):
    """Return the units the panel holds in the base year, with each one's row name, last year and change in the
    extractive share from the base year to that last year, the largest rise first."""
    start = panel[panel["year"] == base].set_index("unit")
    rows = []
    for unit, first in start.iterrows():
        # A unit's last year is the end of its span, at most the chart's last year
        end_year = min(int(first["unit_last"]), last)
        end = panel[(panel["unit"] == unit) & (panel["year"] == end_year)].iloc[0]
        rows.append({"unit": unit, "province": OLD_BORDERS.get(unit, charts.display_name(first["unit_name"])),
                     "last_year": end_year, "extractive_change_pts": round(end[SHARE] - first[SHARE], 6)})
    return pd.DataFrame(rows).sort_values("extractive_change_pts", ascending=False, kind="stable").reset_index(drop=True)


def gains(panel, units, column, years, base):
    """Return a column's values as a unit-by-year table in the units' order, and the gain since the base year in each
    year, rounded to the values' 2 decimals; a year outside a unit's span is an empty cell."""
    wide = panel[panel["unit"].isin(units)].pivot(index="unit", columns="year", values=column)
    wide = wide.reindex(index=units, columns=years)
    return wide, wide.sub(wide[base], axis=0).round(2)


# Steps

# Build the harmonised panel with all its checks
panel = province_panel.build().panel

# Order the rows by the rise in the extractive share from 2015 to each unit's last year
rows = row_order(panel, BASE_YEAR, LAST_YEAR)
units, n = rows["unit"].tolist(), len(rows)

# Diverging colour map from the red through the near-white grey to the blue, with empty cells in the neutral grey
cmap = LinearSegmentedColormap.from_list("gain", [LOSS, ZERO, GAIN])
cmap.set_bad(EMPTY)
norm = Normalize(-COLOUR_LIMIT, COLOUR_LIMIT)

# Lay out the two heatmaps and the extractive column on one row grid
fig = plt.figure(figsize=FIGSIZE, dpi=DPI)
fig.patch.set_facecolor(charts.SURFACE)
axes = [fig.add_axes([LEFT + k * (HEAT_WIDTH + HEAT_GAP), BOTTOM, HEAT_WIDTH, TOP - BOTTOM]) for k in range(2)]
column = fig.add_axes([LEFT + 2 * HEAT_WIDTH + HEAT_GAP + COLUMN_GAP, BOTTOM, COLUMN_WIDTH, TOP - BOTTOM])

# Draw each age group's gains as cells edged by a surface gap, years across and rows down, and keep its values
x_edges, y_edges = np.arange(BASE_YEAR - 0.5, LAST_YEAR + 1), np.arange(-0.5, n)
parts = []
for k, (ax, (col, (code, title))) in enumerate(zip(axes, AGES.items())):
    levels, gain = gains(panel, units, col, YEARS, BASE_YEAR)
    mesh = ax.pcolormesh(x_edges, y_edges, np.ma.masked_invalid(gain.to_numpy()), cmap=cmap, norm=norm,
                         edgecolors=charts.SURFACE, linewidth=CELL_GAP)
    # Shared look without grid or spines, since the cells carry their own edges
    charts.style_axes(ax)
    ax.grid(False)
    for side in ["left", "bottom"]:
        ax.spines[side].set_visible(False)
    # Years as x ticks, the first row at the top, province names left of the first heatmap only
    ax.set_xlim(x_edges[0], x_edges[-1])
    ax.set_ylim(n - 0.5, -0.5)
    ax.xaxis.set_major_locator(FixedLocator(YEARS))
    ax.set_xticklabels([str(y) for y in YEARS])
    ax.yaxis.set_major_locator(FixedLocator(range(n)))
    if k == 0:
        ax.set_yticklabels(rows["province"].tolist())
        ax.tick_params(axis="y", labelsize=ROW_SIZE, labelcolor=charts.TEXT_PRIMARY, pad=6)
    else:
        ax.tick_params(axis="y", labelleft=False)
    ax.set_title(title, loc="left", fontsize=PANEL_TITLE_SIZE, fontweight="bold", color=charts.TEXT_PRIMARY, pad=8)
    # Keep each cell's level and gain, one row per unit and year with a value; an empty cell has no row
    long = levels.stack().rename("aps_pct").to_frame().join(gain.stack().rename("gain_pts")).reset_index()
    long = long.dropna(subset=["aps_pct"])
    parts.append(long.assign(age_group=code, panel=k))

# Write each row's change in the extractive share in the column right of the second heatmap, under its header
column.set_xlim(0, 1)
column.set_ylim(n - 0.5, -0.5)
column.axis("off")
for i, change in enumerate(rows["extractive_change_pts"]):
    column.text(NUMBER_X, i, signed(change), ha="right", va="center", fontsize=ROW_SIZE, color=charts.TEXT_PRIMARY)
column.set_title(textwrap.fill(COLUMN_HEADER, COLUMN_WRAP), loc="center", fontsize=SMALL_SIZE,
                 color=charts.TEXT_SECONDARY, pad=8, multialignment="center")

# One colour bar for both heatmaps under the title, labelled above, with pointed ends for the cells beyond the scale
bar_axes = fig.add_axes([TITLE_X, BAR_Y, BAR_WIDTH, BAR_HEIGHT])
bar = fig.colorbar(mesh, cax=bar_axes, orientation="horizontal", extend="both", extendfrac=0.05)
bar.set_ticks(COLOUR_TICKS)
bar.set_ticklabels([signed(v, 0) for v in COLOUR_TICKS])
bar.outline.set_visible(False)
bar_axes.tick_params(colors=charts.TEXT_SECONDARY, labelsize=SMALL_SIZE, length=0, pad=3)
fig.text(TITLE_X, BAR_LABEL_Y, BAR_LABEL, fontsize=SMALL_SIZE, color=charts.TEXT_SECONDARY, va="bottom")

# The key to the empty cells beside the colour bar
fig.legend(handles=[Patch(facecolor=EMPTY, edgecolor="none", label=EMPTY_LABEL)], loc="center left",
           bbox_to_anchor=(TITLE_X + BAR_WIDTH + KEY_GAP, BAR_Y + BAR_HEIGHT / 2), frameon=False, fontsize=SMALL_SIZE,
           labelcolor=charts.TEXT_SECONDARY, handlelength=1.0, handleheight=1.0, handletextpad=0.5, borderaxespad=0,
           borderpad=0)

# Add the title and save the chart without a software stamp, so a rerun writes the same bytes
charts.finish(fig, TITLE, [], OUT_PNG, left=TITLE_X)

# Write every plotted cell with its unit, row name and extractive change, in row, age-group and year order
cells = pd.concat(parts).merge(rows, on="unit")
cells["row"] = cells["unit"].map({u: i for i, u in enumerate(units)})
cells = cells.sort_values(["row", "panel", "year"])
cells[["unit", "province", "extractive_change_pts", "age_group", "year", "aps_pct", "gain_pts"]].to_csv(
    OUT_CSV, index=False, encoding="utf-8", lineterminator="\n")

# Print the gains the hypothesis turns on: two provinces at both ages, and the median of the full-series provinces
last = cells[cells["year"] == LAST_YEAR]
full = rows.loc[rows["last_year"] == LAST_YEAR, "unit"]
for code, (age, _) in [(c, a) for c in REPORT for a in AGES.values()]:
    row = last[(last["unit"] == code) & (last["age_group"] == age)].iloc[0]
    print(f"{row['province']} {age}: {row['gain_pts']:+.2f} points 2015-{LAST_YEAR}, "
          f"extractive share {row['extractive_change_pts']:+.1f} points")
for age, _ in AGES.values():
    median = last[last["unit"].isin(full) & (last["age_group"] == age)]["gain_pts"].median()
    print(f"Median of the {len(full)} full-series provinces {age}: {median:+.2f} points 2015-{LAST_YEAR}")
print(f"{n} rows; wrote {OUT_PNG.relative_to(ROOT)} and {OUT_CSV.relative_to(ROOT)}")
