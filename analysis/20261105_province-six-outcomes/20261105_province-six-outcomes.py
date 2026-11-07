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
from matplotlib.ticker import FixedLocator, FuncFormatter, MaxNLocator, NullLocator
import pandas as pd

# Parameters

# Outputs
OUT_PNG = HERE / "20261105_six-outcomes.png"
OUT_CSV = HERE / "20261105_six-outcomes.csv"

# The predictor on both rows: the sharpened extractive share of GRDP at current prices (%), the panel's
# extractive_sharp_share_pct: fossil (oil, gas, coal, refining), metals (ores, smelters), plantation (estate crops, plus
# food and beverage mills where estate crops reach 10% of GRDP), forest (logging, wood, paper) and quarrying (stone,
# sand, cement), from the BPS SIMDASI yearbook tables 13.1.1 and 13.1.2 over GRDP at current prices; every unit has it
# from province_panel.SHARP_FIRST_YEAR (2015)
SHARE = province_panel.SHARP_SHARE

# The six outcomes of T1-T6 in column order. Each names the panel column averaged for the top row; the panel column
# whose change makes the bottom row, the factor on that change and the name the CSV gives it; the first year of the
# test's sample (the panel tests' samples: from 2015, the wage share from 2017 as in T5); the column title; the y title
# of the change row; and the format of the y ticks (None for plain numbers).
# - T1 household consumption share: BPS household consumption (PKRT) over expenditure-side PDRB at current prices
#   (WebAPI var 534), % of GRDP
# - T2 hourly wage: BPS average hourly wage (var 1172, Sakernas), Rp per hour as published, averaged in Rp; its change
#   is 100 x the change in ln_hourly_wage, a log change in percent, as T2 tests the wage in logs
# - T3 Gini ratio of household spending per capita, total of urban and rural areas, Susenas March round (var 98)
# - T4 net exports share: exports minus imports of goods and services, to other provinces and abroad, over
#   expenditure-side PDRB at current prices (var 534), % of GRDP
# - T5 wage share of GRDP: employees x average net monthly employee wage x 12 over GRDP at current prices (vars 2335,
#   583 and 286), Sakernas Agustus round, %; from 2017, the first year of the employee counts, so its column covers
#   2017-2025 and its title says so
# - T6 school participation rate (APS) at ages 16-18, BPS var 2211 (Susenas), %
OUTCOMES = [
    {"key": "pkrt_share_pct", "average": "pkrt_share_pct", "change": "pkrt_share_pct", "factor": 1,
     "change_name": "pkrt_share_pct", "first": province_panel.SHARP_FIRST_YEAR,
     "title": "Household consumption share,\n% of GRDP", "change_label": "Change, points", "yformat": None},
    {"key": "hourly_wage", "average": "hourly_wage_rp", "change": "ln_hourly_wage", "factor": 100,
     "change_name": "ln_hourly_wage x 100", "first": province_panel.SHARP_FIRST_YEAR,
     "title": "Hourly wage, Rp", "change_label": "Change, %", "yformat": "{:,.0f}"},
    {"key": "gini_total", "average": "gini_total", "change": "gini_total", "factor": 1,
     "change_name": "gini_total", "first": province_panel.SHARP_FIRST_YEAR,
     "title": "Gini ratio", "change_label": "Change in ratio", "yformat": None},
    {"key": "netekspor_share_pct", "average": "netekspor_share_pct", "change": "netekspor_share_pct", "factor": 1,
     "change_name": "netekspor_share_pct", "first": province_panel.SHARP_FIRST_YEAR,
     "title": "Net exports share,\n% of GRDP", "change_label": "Change, points", "yformat": None},
    {"key": "wage_share_pct", "average": "wage_share_pct", "change": "wage_share_pct", "factor": 1,
     "change_name": "wage_share_pct", "first": province_panel.WAGE_FIRST_YEAR,
     "title": "Wage share of GRDP, %,\n2017–2025", "change_label": "Change, points", "yformat": None},
    {"key": "aps_16_18_pct", "average": "aps_16_18_pct", "change": "aps_16_18_pct", "factor": 1,
     "change_name": "aps_16_18_pct", "first": province_panel.SHARP_FIRST_YEAR,
     "title": "School participation,\nages 16–18, %", "change_label": "Change, points", "yformat": None},
]

# The two rows: what the CSV calls each, the row label at the left and the x title under the row
ROWS = [("average", "Province averages, 2015–2025", "Average extractive share of GRDP, % (log scale)"),
        ("change", "Change, 2015 to 2025", "Change in extractive share of GRDP, points")]

# Axes: x ticks of the top (log) and bottom (linear) rows; headroom as a factor on a log axis and as a share of the
# data span on a linear one; at most this many y intervals per panel
TOP_XTICKS = [1, 2, 5, 10, 20, 50]
BOTTOM_XTICKS = [-10, 0, 10, 20, 30, 40]
LOG_PAD, LINEAR_PAD = 1.25, 0.08
Y_BINS = 5

# Marks: point area in points squared, and the width of the zero lines on the change row
POINT_SIZE = 40
ZERO_WIDTH = 0.8

# Figure: size in inches at 200 dpi, plot margins as figure fractions, and the left edge of the title and row labels
FIGSIZE, DPI = (18, 8.4), 200
MARGINS = {"left": 0.058, "right": 0.99, "top": 0.835, "bottom": 0.075, "wspace": 0.32, "hspace": 0.32}
TEXT_LEFT = 0.012

# Text sizes in points, and the gap in points between a row's tick labels and its x title
COLUMN_TITLE_SIZE, ROW_LABEL_SIZE, AXIS_TITLE_SIZE, RHO_SIZE = 10.5, 11, 9.5, 10
X_TITLE_GAP = 5

# The rank correlation's label: the corners tried in turn, as (x, y, ha, va) in axes fractions; the room in points it
# keeps from every point's centre; and how far the top of the y axis rises, as a share of its span, when every corner
# is taken
CORNERS = [(0.04, 0.96, "left", "top"), (0.96, 0.96, "right", "top"), (0.96, 0.04, "right", "bottom"),
           (0.04, 0.04, "left", "bottom")]
RHO_ROOM = 6
RHO_RAISE, RHO_TRIES = 0.12, 6

# Title
TITLE = "Six outcomes against the extractive share of GRDP: province averages and changes, 2015–2025"

# Functions

def averages(sample, outcome):
    """Return each unit's average extractive share (x) and outcome (y) over its years in the test's sample, with the
    first and last of those years, on the units and years province_panel.between takes."""
    d = province_panel.cross_section(sample, outcome, [SHARE])
    means = d.groupby("unit")[[SHARE, outcome]].mean()
    years = d.groupby("unit")["year"].agg(["min", "max"])
    return pd.DataFrame({"x": means[SHARE], "y": means[outcome], "first_year": years["min"],
                         "last_year": years["max"]})


def changes(sample, outcome, factor):
    """Return each unit's change in the extractive share (x) and in the outcome times factor (y) from its first to its
    last year in the test's sample, as province_panel.long_difference takes them."""
    ld = province_panel.long_differences(sample, outcome, SHARE)
    return pd.DataFrame({"x": ld["d_x"], "y": ld["d_y"] * factor, "first_year": ld["first"], "last_year": ld["last"]})


def padded(values, log=False):
    """Return axis limits around the values with headroom: a factor on a log axis, a share of the span otherwise."""
    low, high = float(min(values)), float(max(values))
    if log:
        return low / LOG_PAD, high * LOG_PAD
    pad = (high - low) * LINEAR_PAD
    return low - pad, high + pad


def signed(value, fmt="{:g}"):
    """Format a number with a true minus sign."""
    return fmt.format(value).replace("-", "−")


def rho_label(ax, xs, ys, text):
    """Write the rank correlation in the first corner whose label keeps RHO_ROOM from every point; when every corner
    is taken, raise the top of the y axis and try again."""
    renderer = ax.figure.canvas.get_renderer()
    room = RHO_ROOM * ax.figure.dpi / 72
    halo = [patheffects.withStroke(linewidth=3, foreground=charts.SURFACE)]
    for _ in range(RHO_TRIES):
        pts = ax.transData.transform(list(zip(xs, ys)))
        for fx, fy, ha, va in CORNERS:
            t = ax.text(fx, fy, text, transform=ax.transAxes, ha=ha, va=va, fontsize=RHO_SIZE,
                        color=charts.TEXT_PRIMARY, zorder=4, path_effects=halo)
            bb = t.get_window_extent(renderer)
            if not any(bb.x0 - room <= px <= bb.x1 + room and bb.y0 - room <= py <= bb.y1 + room for px, py in pts):
                return t
            t.remove()
        low, high = ax.get_ylim()
        ax.set_ylim(low, high + (high - low) * RHO_RAISE)
    raise RuntimeError(f"no free corner for '{text}'")


# Steps

# Build the harmonised panel with all its checks
b = province_panel.build()
panel = b.panel
names = panel.groupby("unit")["unit_name"].first().map(charts.display_name)

# For every outcome, each unit's averages and changes on the test's sample, and the plain rank correlations of the
# points drawn (between and long_difference with no controls; scaling a change by 100 leaves its ranks alone)
points, stats = {}, {}
for spec in OUTCOMES:
    sample = panel[panel["year"] >= spec["first"]]
    points[(spec["key"], "average")] = averages(sample, spec["average"])
    points[(spec["key"], "change")] = changes(sample, spec["change"], spec["factor"])
    stats[(spec["key"], "average")] = province_panel.between(sample, spec["average"], SHARE)
    stats[(spec["key"], "change")] = province_panel.long_difference(sample, spec["change"], SHARE)

# One x range per row, shared by its six panels: log for the averages, linear for the changes
xlims = {"average": padded(pd.concat([points[(s["key"], "average")]["x"] for s in OUTCOMES]), log=True),
         "change": padded(pd.concat([points[(s["key"], "change")]["x"] for s in OUTCOMES]))}

# Lay out the 2 x 6 grid
fig, axes = plt.subplots(len(ROWS), len(OUTCOMES), figsize=FIGSIZE, dpi=DPI)
fig.patch.set_facecolor(charts.SURFACE)
fig.subplots_adjust(**MARGINS)

for col, spec in enumerate(OUTCOMES):
    for row, (kind, _, _) in enumerate(ROWS):
        ax = axes[row, col]
        pts = points[(spec["key"], kind)]
        charts.style_axes(ax)
        ax.set_axisbelow(True)
        # The top row reads the average share on a log axis; the change row gets zero lines beneath the points
        if kind == "average":
            ax.set_xscale("log")
        else:
            ax.axvline(0, color=charts.CUT, lw=ZERO_WIDTH, zorder=1.5)
            ax.axhline(0, color=charts.CUT, lw=ZERO_WIDTH, zorder=1.5)
        # The points, filled in the series colour inside a surface ring
        ax.scatter(pts["x"], pts["y"], zorder=3, **charts.point_marks({}, POINT_SIZE))
        # Shared x range and fixed x ticks for the row, the panel's own y range
        ax.set_xlim(*xlims[kind])
        ax.set_ylim(*padded(pts["y"]))
        ticks = TOP_XTICKS if kind == "average" else BOTTOM_XTICKS
        low, high = xlims[kind]
        ax.xaxis.set_major_locator(FixedLocator([v for v in ticks if low <= v <= high]))
        ax.xaxis.set_minor_locator(NullLocator())
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: signed(v)))
        ax.yaxis.set_major_locator(MaxNLocator(nbins=Y_BINS, steps=[1, 2, 5, 10]))
        if spec["yformat"]:
            ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _, f=spec["yformat"]: signed(v, f)))
        # Column titles over the top row; the change row's y title gives the unit of the change
        if kind == "average":
            ax.set_title(spec["title"], loc="left", fontsize=COLUMN_TITLE_SIZE, fontweight="bold",
                         color=charts.TEXT_PRIMARY, pad=8)
        else:
            ax.set_ylabel(spec["change_label"], fontsize=AXIS_TITLE_SIZE, color=charts.TEXT_SECONDARY)

# The rank correlation in a free corner of each panel
for col, spec in enumerate(OUTCOMES):
    for row, (kind, _, _) in enumerate(ROWS):
        pts = points[(spec["key"], kind)]
        rho_label(axes[row, col], pts["x"].tolist(), pts["y"].tolist(),
                  "ρ " + signed(stats[(spec["key"], kind)]["rho"], "{:.2f}"))

# Row labels at the left, and each row's x title centred under its tick labels
fig.canvas.draw()
renderer = fig.canvas.get_renderer()
for row, (_, label, xtitle) in enumerate(ROWS):
    first, last = axes[row, 0].get_position(), axes[row, -1].get_position()
    fig.text(TEXT_LEFT, (first.y0 + first.y1) / 2, label, rotation=90, ha="left", va="center",
             fontsize=ROW_LABEL_SIZE, fontweight="bold", color=charts.TEXT_PRIMARY)
    bottom = min(ax.xaxis.get_tightbbox(renderer).y0 for ax in axes[row])
    fig.text((first.x0 + last.x1) / 2, (bottom - X_TITLE_GAP * DPI / 72) / fig.bbox.height, xtitle, ha="center",
             va="top", fontsize=AXIS_TITLE_SIZE, color=charts.TEXT_SECONDARY)

# Write every plotted value: one row per outcome, row and unit
table = []
for spec in OUTCOMES:
    for kind, _, _ in ROWS:
        pts = points[(spec["key"], kind)]
        table.append(pd.DataFrame({
            "outcome": spec["average"] if kind == "average" else spec["change_name"], "row": kind,
            "unit": pts.index, "province": names.reindex(pts.index).to_numpy(),
            "x": pts["x"].round(6).to_numpy(), "y": pts["y"].round(6).to_numpy(),
            "first_year": pts["first_year"].astype(int).to_numpy(),
            "last_year": pts["last_year"].astype(int).to_numpy()}))
pd.concat(table, ignore_index=True).to_csv(OUT_CSV, index=False, encoding="utf-8", lineterminator="\n")

# Add the title and save the chart
charts.finish(fig, TITLE, [], OUT_PNG, left=TEXT_LEFT)

# Print the rank correlations with their p-values and samples
for spec in OUTCOMES:
    for kind, _, _ in ROWS:
        s = stats[(spec["key"], kind)]
        print(f"{spec['key']:20s} {kind:8s} rho {s['rho']:+.3f}  p {s['p']:.4f}  units {s['units']}  "
              f"years {s['years'][0]}-{s['years'][1]}")
