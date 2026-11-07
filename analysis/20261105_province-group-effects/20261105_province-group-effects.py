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
from matplotlib.ticker import MaxNLocator
import pandas as pd
from scipy import stats

# Parameters

# Outputs, beside this script
OUT_PNG = HERE / "20261105_group-effects.png"
OUT_CSV = HERE / "20261105_group-effects.csv"

# Estimates: for each outcome and each extractive group, two-way fixed effects (province_panel.twfe: unit and year
# effects, standard errors clustered by panel unit, p from t with G - 1 degrees of freedom, G the units) of the outcome
# on the group's share of GRDP at current prices (<group>_share_pct, %) and log real GRDP per capita
# (province_panel.INCOME), on the harmonised panel's unit-years from the first year given, as the panel tests T1-T6 run
# them (analysis/20261103_province-panel-correlations). Sources of the outcomes, all BPS, built in data/ and read
# through tools/province_panel.py: household consumption (PKRT) and net exports as % of GRDP at current prices from
# GRDP by expenditure (var 534); the informal share of employment (var 2153, from 2018), the hourly wage and the
# provincial minimum wage, both in Rp and taken in logs; the March Susenas Gini ratio (total); the employee wage bill
# (Agustus Sakernas employees x net monthly wage x 12) as % of GRDP at current prices (from 2017, the first year of the
# employee counts); school participation (APS, %) at ages 16-18 and 19-23. The household-share row by group is new;
# the other eight outcomes repeat the panel tests T2-T6
# Each outcome: (panel column, multiplier applied to its slope and standard error, the outcome as the CSV names it,
# panel title, first sample year). Logs are multiplied by 100, so a slope reads as an approximate % change per point,
# and the Gini ratio (0-1) by 100, so a slope reads in Gini points
SHARP, WAGE = province_panel.SHARP_FIRST_YEAR, province_panel.WAGE_FIRST_YEAR
OUTCOMES = [
    ("pkrt_share_pct", 1, "pkrt_share_pct", "Household consumption share, points", SHARP),
    ("informal_share_pct", 1, "informal_share_pct", "Informal share of employment, points", SHARP),
    ("ln_hourly_wage", 100, "100*ln_hourly_wage", "Hourly wage, %", SHARP),
    ("ln_minimum_wage", 100, "100*ln_minimum_wage", "Minimum wage, %", SHARP),
    ("gini_total", 100, "100*gini_total", "Gini ratio, Gini points", SHARP),
    ("netekspor_share_pct", 1, "netekspor_share_pct", "Net exports share, points", SHARP),
    ("wage_share_pct", 1, "wage_share_pct", "Wage share of GRDP, points", WAGE),
    ("aps_16_18_pct", 1, "aps_16_18_pct", "School participation, ages 16–18, points", SHARP),
    ("aps_19_23_pct", 1, "aps_19_23_pct", "School participation, ages 19–23, points", SHARP),
]

# The five groups, top row to bottom, with the short name each row carries on the left column's y axis; the legend
# gives each group's full label from charts.EXTRACTIVE_GROUP_STYLE
GROUPS = list(province_panel.EXTRACTIVE_GROUPS)
ROW_NAMES = {"fossil": "Fossil", "metals": "Metals", "plantation": "Plantation", "forest": "Forest",
             "quarrying": "Quarrying"}

# Interval: two-sided 95%, slope +/- t(0.975, G - 1) x clustered standard error
LEVEL = 0.95

# Figure: size in inches at 200 dpi, a 3 x 3 grid, plot margins as figure fractions, and the figure fraction where
# the title and legend start
FIGSIZE, DPI = (14.5, 10.4), 200
GRID_SHAPE = (3, 3)
MARGINS = {"left": 0.075, "right": 0.985, "top": 0.875, "bottom": 0.085, "wspace": 0.12, "hspace": 0.42}
TITLE_LEFT = 0.012
XLABEL_Y = 0.022
# Legend keys long enough (in font sizes) that the interval line shows on both sides of the marker's ring
LEGEND_HANDLE_LENGTH = 3.0

# Marks: marker area of a circle in points squared (other shapes scaled by charts.EXTRACTIVE_MARKER_AREA), interval
# width and zero line width in points, the space each panel leaves beyond its widest interval (share of its span), and
# the most x ticks a panel shows
POINT_SIZE = 54
INTERVAL_WIDTH = 2.0
ZERO_WIDTH = 1.0
X_PAD = 0.08
X_BINS = 5

# Texts
TITLE = "Within-province effect of each extractive group's share of GRDP on nine outcomes, 2015–2025"
XLABEL = ("Change in the outcome per 1-point rise in the group's share of GRDP, within provinces, "
          "income held equal")
PANEL_TITLE_SIZE = 11
ROW_LABEL_SIZE = 10
XLABEL_SIZE = 10.5

# Functions

def estimate(sample, column, share, scale):
    """Return the group share's slope, clustered standard error, 95% interval, p-value and sample of one test."""
    fe = province_panel.twfe(sample, column, [share, province_panel.INCOME])
    slope, se = scale * float(fe["slopes"][0]), scale * float(fe["se"][0])
    half = stats.t.ppf(0.5 + LEVEL / 2, fe["units"] - 1) * se
    return {"slope": slope, "std_error": se, "ci_low": slope - half, "ci_high": slope + half,
            "p_value": float(fe["p"][0]), "n": fe["n"], "units": fe["units"],
            "years": f"{fe['years'][0]}-{fe['years'][1]}"}


def legend_handle(group):
    """Return a group's legend entry: its marker as the points draw it, on a short line in its colour."""
    style = charts.EXTRACTIVE_GROUP_STYLE[group]
    handle = charts.legend_key(style, group)
    handle.set_linestyle("-")
    handle.set_color(style["color"])
    handle.set_linewidth(INTERVAL_WIDTH)
    handle.set_markerfacecolor(style["color"])
    return handle


# Steps

# Build the harmonised panel with all its checks
b = province_panel.build()
panel = b.panel

# Estimate each group's within-province slope on each outcome, income held equal, on the outcome's sample
rows = []
for column, scale, outcome, _, first in OUTCOMES:
    sample = panel[panel["year"] >= first]
    for group in GROUPS:
        rows.append({"outcome": outcome, "group": group,
                     **estimate(sample, column, f"{group}_share_pct", scale)})
results = pd.DataFrame(rows)

# Draw the grid: one panel per outcome, one row per group, fossil at the top
fig, axes = plt.subplots(*GRID_SHAPE, figsize=FIGSIZE, dpi=DPI, sharey=True)
fig.patch.set_facecolor(charts.SURFACE)
fig.subplots_adjust(**MARGINS)
for ax, (column, scale, outcome, panel_title, first) in zip(axes.flat, OUTCOMES):
    charts.style_axes(ax)
    # Keep the vertical grid only, so the rows carry no line of their own
    ax.yaxis.grid(False)
    part = results[results["outcome"] == outcome].set_index("group")
    # The zero line under the marks
    ax.axvline(0, color=charts.CUT, lw=ZERO_WIDTH, zorder=1)
    for row, group in enumerate(GROUPS):
        style = charts.EXTRACTIVE_GROUP_STYLE[group]
        r = part.loc[group]
        # The 95% interval as a line, and the slope as the group's marker on it
        ax.plot([r["ci_low"], r["ci_high"]], [row, row], color=style["color"], lw=INTERVAL_WIDTH,
                solid_capstyle="butt", zorder=2)
        size = POINT_SIZE * charts.EXTRACTIVE_MARKER_AREA[style["marker"]]
        ax.scatter([r["slope"]], [row], marker=style["marker"], zorder=3, **charts.point_marks(style, size))
    # Each panel's own x range: every interval and zero, with room on both sides
    low, high = min(part["ci_low"].min(), 0.0), max(part["ci_high"].max(), 0.0)
    pad = X_PAD * (high - low)
    ax.set_xlim(low - pad, high + pad)
    ax.xaxis.set_major_locator(MaxNLocator(nbins=X_BINS, steps=[1, 2, 2.5, 5, 10]))
    ax.set_title(panel_title, loc="left", fontsize=PANEL_TITLE_SIZE, color=charts.TEXT_PRIMARY, pad=7)

# Group names on the left column's y axis only (sharey hides the others), fossil at the top
axes[0, 0].set_yticks(range(len(GROUPS)))
axes[0, 0].set_yticklabels([ROW_NAMES[g] for g in GROUPS])
axes[0, 0].set_ylim(len(GROUPS) - 0.5, -0.5)
for ax in axes[:, 0]:
    ax.tick_params(axis="y", labelsize=ROW_LABEL_SIZE, labelcolor=charts.TEXT_PRIMARY)

# One x label under the grid, centred on the plot area
fig.text((MARGINS["left"] + MARGINS["right"]) / 2, XLABEL_Y, XLABEL, ha="center", va="bottom",
         fontsize=XLABEL_SIZE, color=charts.TEXT_SECONDARY)

# Add the title and the legend of the five groups, with longer keys, and save the chart
plt.rcParams["legend.handlelength"] = LEGEND_HANDLE_LENGTH
charts.finish(fig, TITLE, [legend_handle(g) for g in GROUPS], OUT_PNG, left=TITLE_LEFT)

# Write every plotted value: slope, standard error, interval and p-value per outcome and group, with the sample
table = results.copy()
for col in ["slope", "std_error", "ci_low", "ci_high"]:
    table[col] = table[col].map(province_panel.num)
table["p_value"] = table["p_value"].map(lambda v: province_panel.num(v, 4))
table.to_csv(OUT_CSV, index=False, encoding="utf-8", lineterminator="\n")

# Print the household-share slopes and every outcome-group pair whose interval excludes zero
print(table[table["outcome"] == "pkrt_share_pct"].to_string(index=False))
excludes = results[(results["ci_low"] > 0) | (results["ci_high"] < 0)]
print(excludes.to_string(index=False))
