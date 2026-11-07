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
from matplotlib.lines import Line2D
from matplotlib.ticker import FixedLocator
import pandas as pd

# Parameters

# Datasets read, each a folder in data/ holding <folder>.csv and <folder>-metadata.json
GRDP = "20261103_bps-province-grdp-2010-2025"
MINIMUM_WAGE = "20261104_bps-kemnaker-province-minimum-wage"
HOURLY_WAGE = "20261104_bps-province-informal-work-and-hourly-wage"

# The three series in legend order: dataset, indicator, legend label, line colour and line width in points. All are
# at current prices, as published, and each is indexed to its own 2015 value = 100, province by province.
# - grdp_per_capita_current: GRDP per capita at current prices, Seri 2010, Rp thousand per person, BPS WebAPI var 288;
#   2024 is preliminary (*) and 2025 very preliminary (**).
# - minimum_wage: provincial minimum wage (UMP), Rp per month. BPS WebAPI var 220 for 2015-2016 and 2018-2020, and
#   Kemnaker Satu Data for 2017 and 2021-2025 (datasets 36, 473, 942, 1611 and 2252), as the dataset's metadata states.
#   Most provinces kept their 2020 UMP in 2021 (SE Menaker M/11/HK.04/X/2020). Jawa Tengah, DI Yogyakarta and Jawa
#   Timur (33-35) have no 2016 value in either source, so they drop out of this series' median.
# - hourly_wage: average hourly wage of workers (upah rata-rata per jam pekerja), Rp per hour, BPS WebAPI var 1172 from
#   Sakernas; 2015-2019 are revised figures (status r) after a change of survey weights.
# GRDP per capita takes the shared series blue and a thicker line. The two wages take a muted orange and a muted mauve,
# which stay apart from each other and from the blue under colour-vision deficiency
SERIES = [
    {"key": "grdp_per_capita_current", "dataset": GRDP, "label": "GRDP per capita", "color": charts.SERIES,
     "lw": 2.4},
    {"key": "minimum_wage", "dataset": MINIMUM_WAGE, "label": "Minimum wage (UMP)", "color": "#d2793f", "lw": 1.6},
    {"key": "hourly_wage", "dataset": HOURLY_WAGE, "label": "Hourly wage", "color": "#b474ad", "lw": 1.6},
]

# Years shown, and the base year of every index with its value
FIRST_YEAR, LAST_YEAR = 2015, 2025
BASE_YEAR, BASE = 2015, 100

# Provinces drawn in their own panels, by BPS code: Maluku Utara and Sulawesi Tengah
PROVINCES = ["82", "72"]

# Name of the third panel, and of its rows in the table
MEDIAN_NAME = "Median province"

# Codes left out of the median: Indonesia (00), and the six Papua provinces, whose borders changed in 2015-2025.
# 91 Papua Barat and 94 Papua cover the pre-split areas until 2022 in the GRDP table and until 2023 in the wage tables,
# and 92, 95, 96 and 97 start in 2023 or 2024. Every other province kept its borders through 2015-2025, Kalimantan
# Utara (65) included, which has its own values in all three series from 2015.
# The median is taken per series and year over the remaining provinces that have the series in every year 2015-2025,
# Maluku Utara and Sulawesi Tengah among them; the number of provinces is printed when the script runs
EXCLUDED = {"00", "91", "92", "94", "95", "96", "97"}

# Figure: a full 16:9 slide (charts.SLIDE_SIZE, in inches) and its resolution
FIGSIZE, DPI = charts.SLIDE_SIZE, 200

# Plot edges as figure fractions, and the gap between panels as a share of a panel's width
LEFT, RIGHT, TOP, BOTTOM, WSPACE = 0.055, 0.972, 0.83, 0.075, 0.09

# Axis ranges and ticks; x leaves room on the right for the 2025 labels
XLIM, XTICKS = (2014.5, 2025.5), [2015, 2017, 2019, 2021, 2023, 2025]
YLIM, YTICKS = (80, 450), [100, 200, 300, 400]

# Title and y axis title
TITLE = "GRDP per capita, minimum wage and hourly wage at current prices, index 2015 = 100, 2015–2025"
YLABEL = "Index, 2015 = 100"

# Tops of the title and of the legend, as figure fractions
TITLE_Y, LEGEND_Y = 0.965, 0.902

# Panel titles: size in points and gap above the plot in points
PANEL_SIZE, PANEL_PAD = 11, 8

# 2025 value labels: font size, gap from the line end and vertical gap between stacked labels, in points
LABEL_SIZE, LABEL_DX, LABEL_GAP = 8.5, 6, 1.5

# Marker at each line's 2025 end and its ring in the surface colour, in points
END_SIZE, END_RING = 5, 1.2

# Line at the base value, in points
BASE_LW = 1.0

# Decimals of the index in the table
INDEX_DECIMALS = 2

# Outputs
OUT_PNG = HERE / "20261105_output-and-pay-index.png"
OUT_CSV = HERE / "20261105_output-and-pay-index.csv"

# Functions

def read_series(dataset, indicator):
    """Return one indicator as province-by-year tables of its values and of its value text, for the years shown."""
    rows = pd.read_csv(ROOT / "data" / dataset / f"{dataset}.csv", dtype=str, keep_default_na=False)
    rows = rows[rows["indicator"] == indicator]
    # The GRDP dataset holds province totals under sector TOTAL
    if "sector" in rows.columns:
        rows = rows[rows["sector"] == "TOTAL"]
    rows = rows.assign(year=rows["period"].astype(int), number=rows["value"].astype(float))
    rows = rows[rows["year"].between(FIRST_YEAR, LAST_YEAR)]
    years = list(range(FIRST_YEAR, LAST_YEAR + 1))
    values = rows.pivot(index="province_code", columns="year", values="number").reindex(columns=years)
    text = rows.pivot(index="province_code", columns="year", values="value").reindex(columns=years)
    return values, text


def index_table(values):
    """Return the provinces with fixed borders and a value in every year, each as an index of its base-year value."""
    fixed = values.drop(index=[c for c in EXCLUDED if c in values.index])
    complete = fixed.dropna()
    return complete.div(complete[BASE_YEAR], axis=0) * BASE


def spread(centres, height):
    """Return label centres in pixels, moved apart until no two are closer than height.

    Labels that would overlap form a group, stacked height apart around the mean of their own centres, and groups
    merge until none overlap; each label keeps its order and stays as near its line end as the others allow.
    """
    order = sorted(range(len(centres)), key=lambda i: centres[i])
    groups = [[i] for i in order]
    while True:
        # Stack each group around the mean of its members' centres
        stacks = []
        for group in groups:
            mean = sum(centres[i] for i in group) / len(group)
            stacks.append([mean + (k - (len(group) - 1) / 2) * height for k in range(len(group))])
        # Merge the first pair of neighbouring groups that overlap, or stop when none do
        clash = next((g for g in range(len(groups) - 1) if stacks[g + 1][0] - stacks[g][-1] < height), None)
        if clash is None:
            break
        groups[clash] += groups.pop(clash + 1)
    return {i: y for group, stack in zip(groups, stacks) for i, y in zip(group, stack)}


def style_axes(ax):
    """Style a panel as the shared charts do: recessive grid beneath the data, no top or right spine, quiet ticks."""
    ax.set_facecolor(charts.SURFACE)
    ax.set_axisbelow(True)
    ax.grid(color=charts.GRID, lw=0.8, zorder=0)
    for side in ["top", "right"]:
        ax.spines[side].set_visible(False)
    for side in ["left", "bottom"]:
        ax.spines[side].set_color(charts.GRID)
    ax.tick_params(colors=charts.TEXT_SECONDARY, labelsize=9, length=0)


def draw_panel(ax, title, lines):
    """Draw one panel: the line at the base value, the three series with a marker at each 2025 end, and its title.

    lines: one index series by year per entry of SERIES, in the same order.
    """
    style_axes(ax)
    ax.axhline(BASE, color=charts.CUT, lw=BASE_LW, zorder=1.5)
    # Wages first and GRDP per capita last, so the thicker blue line sits on top where the lines meet
    for rank, (spec, line) in reversed(list(enumerate(zip(SERIES, lines)))):
        ax.plot(line.index, line.values, color=spec["color"], lw=spec["lw"], solid_capstyle="round",
                solid_joinstyle="round", zorder=3 + (len(SERIES) - rank) / 10)
        ax.plot([LAST_YEAR], [line[LAST_YEAR]], linestyle="none", marker="o", markersize=END_SIZE,
                markerfacecolor=spec["color"], markeredgecolor=charts.SURFACE, markeredgewidth=END_RING,
                zorder=4 + (len(SERIES) - rank) / 10)
    ax.set_title(title, loc="left", fontsize=PANEL_SIZE, fontweight="bold", color=charts.TEXT_PRIMARY, pad=PANEL_PAD)


def label_ends(ax, ends):
    """Write each line's 2025 index just right of its end, moving the labels apart where they would overlap.

    ends: each line's index in 2025. The labels wear the primary text colour; the end marker carries the line's colour.
    """
    fig = ax.figure
    renderer = fig.canvas.get_renderer()
    # A label's height in pixels, measured on a label of the same size, plus the gap between stacked labels
    probe = ax.text(0, 0, "0", fontsize=LABEL_SIZE)
    height = probe.get_window_extent(renderer).height + LABEL_GAP * fig.dpi / 72
    probe.remove()
    # Pixel heights of the line ends, and the label centres spread apart from them
    ys = [ax.transData.transform((LAST_YEAR, v))[1] for v in ends]
    placed = spread(ys, height)
    for i, (value, y) in enumerate(zip(ends, ys)):
        ax.annotate(f"{value:.0f}", (LAST_YEAR, value), xytext=(LABEL_DX, (placed[i] - y) * 72 / fig.dpi),
                    textcoords="offset points", ha="left", va="center", fontsize=LABEL_SIZE,
                    color=charts.TEXT_PRIMARY, annotation_clip=False)


# Steps

# Read the province names from the GRDP dataset's metadata, title-cased from BPS's spelling
meta = json.loads((ROOT / "data" / GRDP / f"{GRDP}-metadata.json").read_text(encoding="utf-8"))
names = {code: charts.display_name(p["name"]) for code, p in meta["provinces"].items()}

# Index each series to its 2015 value, province by province, and take each year's median over the provinces with fixed
# borders and every year; keep the two provinces' indices and published values for their panels and the table
areas = [names[c] for c in PROVINCES] + [MEDIAN_NAME]
panels = {area: [] for area in areas}
counts, rows = {}, []
for spec in SERIES:
    values, text = read_series(spec["dataset"], spec["key"])
    index = index_table(values)
    counts[spec["key"]] = len(index)
    for code, area in zip(PROVINCES, areas):
        # Each named province must be among the provinces with every year, or its line would be incomplete
        if code not in index.index:
            raise SystemExit(f"{area} lacks a year of {spec['key']} in {FIRST_YEAR}-{LAST_YEAR}")
        panels[area].append(index.loc[code])
        rows += [{"area": area, "series": spec["key"], "year": year, "value": text.loc[code, year],
                  "index": index.loc[code, year]} for year in index.columns]
    median = index.median(axis=0)
    panels[MEDIAN_NAME].append(median)
    rows += [{"area": MEDIAN_NAME, "series": spec["key"], "year": year, "value": "", "index": median[year]}
             for year in median.index]

# Lay out the three panels side by side on one shared y axis, with the plot edges fixed before any label is measured
fig, axes = plt.subplots(1, len(areas), sharey=True, figsize=FIGSIZE, dpi=DPI)
fig.patch.set_facecolor(charts.SURFACE)
fig.subplots_adjust(left=LEFT, right=RIGHT, top=TOP, bottom=BOTTOM, wspace=WSPACE)

# Draw each panel and set the shared ranges and ticks, with the years as plain numbers
for ax, area in zip(axes, areas):
    draw_panel(ax, area, panels[area])
    ax.set_xlim(*XLIM)
    ax.xaxis.set_major_locator(FixedLocator(XTICKS))
    ax.set_xticklabels([str(year) for year in XTICKS])
axes[0].set_ylim(*YLIM)
axes[0].yaxis.set_major_locator(FixedLocator(YTICKS))
axes[0].set_yticklabels([str(v) for v in YTICKS])
axes[0].set_ylabel(YLABEL, color=charts.TEXT_SECONDARY, fontsize=10)

# Write the 2025 values at the line ends once the layout is final
fig.canvas.draw()
for ax, area in zip(axes, areas):
    label_ends(ax, [line[LAST_YEAR] for line in panels[area]])

# Title at the top left, and one legend of the three series beneath it
fig.text(LEFT, TITLE_Y, TITLE, ha="left", va="top", fontsize=15, fontweight="bold", color=charts.TEXT_PRIMARY)
handles = [Line2D([], [], color=s["color"], lw=s["lw"], solid_capstyle="round", label=s["label"]) for s in SERIES]
fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(LEFT, LEGEND_Y), ncol=len(SERIES), frameon=False,
           fontsize=9, labelcolor=charts.TEXT_SECONDARY, handlelength=2.4, handletextpad=0.6, columnspacing=1.8,
           borderaxespad=0, borderpad=0)

# Save the chart without a software stamp, so a rerun writes the same bytes
fig.savefig(OUT_PNG, facecolor=charts.SURFACE, metadata={"Software": None})
plt.close(fig)

# Write every plotted index with the published value behind it; the median rows have no value
table = pd.DataFrame(rows, columns=["area", "series", "year", "value", "index"])
table["index"] = table["index"].map(lambda v: f"{v:.{INDEX_DECIMALS}f}")
table.to_csv(OUT_CSV, index=False, encoding="utf-8", lineterminator="\n")

# Report the provinces behind each median and the 2025 index of every line
print("Provinces in the median:", ", ".join(f"{k} {n}" for k, n in counts.items()))
for area in areas:
    print(f"{area} 2025:", ", ".join(f"{s['label']} {line[LAST_YEAR]:.1f}" for s, line in zip(SERIES, panels[area])))
