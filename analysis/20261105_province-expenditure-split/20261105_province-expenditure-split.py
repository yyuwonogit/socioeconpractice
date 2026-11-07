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
from matplotlib.patches import Patch
from matplotlib.ticker import FixedLocator
import numpy as np
import pandas as pd

# Parameters

# GRDP by expenditure at current prices, BPS WebAPI var 542 'Distribusi PDRB Atas Dasar Harga Berlaku Menurut
# Pengeluaran' (Seri 2010): each component's share of GRDP as BPS publishes it, in percent with 2 decimals. The six
# components sum to 100 within 0.02 points (the dataset's checks.identities). Net exports (NETEKSPOR) are exports minus
# imports of goods and services, to other provinces and abroad together. BPS marks 2024 as preliminary (status *) and
# 2025 as very preliminary (**); the CSV carries the status and the chart shows no marker
DATASET = ROOT / ("data/20261104_bps-province-grdp-by-expenditure-2010-2025/"
                  "20261104_bps-province-grdp-by-expenditure-2010-2025.csv")
METADATA = ROOT / ("data/20261104_bps-province-grdp-by-expenditure-2010-2025/"
                   "20261104_bps-province-grdp-by-expenditure-2010-2025-metadata.json")

OUT_PNG = HERE / "20261105_expenditure-split.png"
OUT_CSV = HERE / "20261105_expenditure-split.csv"

# The share indicator and the annual periods (four-digit periods; the YYYYQn quarter rows are left out)
INDICATOR = "grdp_distribution_current"
FIRST_YEAR, LAST_YEAR = 2010, 2025

# Panels from left to right: Maluku Utara, Kalimantan Timur, DI Yogyakarta. Kalimantan Utara (65) has its own values
# from 2010 in these tables, so Kalimantan Timur (64) is on today's borders in every year
PROVINCES = ["82", "64", "34"]

# The six components in stack order, outward from 0 on both sides, with their legend labels and colours: household
# consumption in the series blue and net exports in a strong warm orange, the four others in warm neutral greys from
# light to mid, about 10 points of CIE lightness apart (87, 77, 66 and 56), so the eye goes to the two slices the chart
# is about. TOTAL (PDRB, always 100) is left out
COMPONENTS = {
    "PKRT": ("Household consumption", charts.SERIES),
    "PKLNPRT": ("Non-profit consumption", "#868581"),
    "PKP": ("Government consumption", "#dbdad6"),
    "PMTB": ("Investment", "#bebdb9"),
    "PI": ("Change in inventories", "#a1a09c"),
    "NETEKSPOR": ("Net exports", "#D55E00"),
}

# Figure: size in inches at 200 dpi, plot margins as figure fractions, and the heights of the title and legend rows
FIGSIZE, DPI = (15, 6.6), 200
MARGINS = {"left": 0.05, "right": 0.985, "top": 0.835, "bottom": 0.065, "wspace": 0.13}
TITLE_Y, LEGEND_Y = 0.975, 0.918

# Axes: one y range for all panels, from below the deepest net-import slice (Maluku Utara 2020, -36.8) to above the
# tallest positive stack (Maluku Utara 2020, 136.8); x runs edge to edge over the years
YLIM = (-40, 140)
YTICKS = list(range(-40, 141, 20))
XTICKS = [2010, 2015, 2020, 2025]

# Marks: the surface-coloured gap between slices and the zero line, in points
GAP, ZERO_WIDTH = 0.6, 0.9

# Texts
TITLE = "GRDP by expenditure, Maluku Utara, Kalimantan Timur and DI Yogyakarta, 2010–2025"
YLABEL = "% of GRDP at current prices"
PANEL_TITLE_SIZE = 12

# Functions

def read_dataset(path):
    """Read a long dataset with every column as text, so codes and empty statuses survive, and turn values to numbers."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df["value"] = df["value"].astype(float)
    return df


def annual_shares(df, provinces, components, first, last):
    """Return the annual shares of the components for the provinces, one row per province, year and component."""
    rows = df[(df["indicator"] == INDICATOR) & df["period"].str.fullmatch(r"\d{4}")
              & df["province_code"].isin(provinces) & df["component"].isin(components)].copy()
    rows["year"] = rows["period"].astype(int)
    return rows[(rows["year"] >= first) & (rows["year"] <= last)]


def stack_edges(wide, order):
    """Return each component's slices as (lower edge, upper edge) pairs by year: its positive values stack upward from
    0 and its negative values downward from 0, each side in the stack order."""
    up, down = np.zeros(len(wide)), np.zeros(len(wide))
    edges = {}
    for c in order:
        v = wide[c].to_numpy()
        pos, neg = np.clip(v, 0, None), np.clip(v, None, 0)
        edges[c] = [(up, up + pos), (down + neg, down)]
        up, down = up + pos, down + neg
    return edges


def style_axes(ax):
    """Style a panel as the shared charts do: recessive grid beneath the data, no top or right spine, left and bottom
    spines in the grid colour beneath the slices, secondary-ink ticks. The grid runs across only: the slices cover the
    years, and a year line at the right edge would read as a right spine."""
    ax.set_facecolor(charts.SURFACE)
    ax.set_axisbelow(True)
    ax.grid(axis="y", color=charts.GRID, lw=0.8)
    for side in ["top", "right"]:
        ax.spines[side].set_visible(False)
    for side in ["left", "bottom"]:
        ax.spines[side].set_color(charts.GRID)
        ax.spines[side].set_zorder(1)
    ax.tick_params(colors=charts.TEXT_SECONDARY, labelsize=9, length=0)


# Steps

# Read the dataset, and the province names from its metadata in the chart's capitalisation
data = read_dataset(DATASET)
meta = json.loads(METADATA.read_text(encoding="utf-8"))
names = {c: charts.display_name(meta["provinces"][c]["name"]) for c in PROVINCES}

# Keep the annual shares of the six components for the three provinces
shares = annual_shares(data, PROVINCES, list(COMPONENTS), FIRST_YEAR, LAST_YEAR)

# Lay out three panels side by side on one y axis
fig, axes = plt.subplots(1, len(PROVINCES), figsize=FIGSIZE, dpi=DPI, sharey=True)
fig.patch.set_facecolor(charts.SURFACE)
fig.subplots_adjust(**MARGINS)

for ax, code in zip(axes, PROVINCES):
    # One column per component and one row per year
    wide = shares[shares["province_code"] == code].pivot(index="year", columns="component", values="value")
    wide = wide.sort_index()
    years = wide.index.to_numpy()
    style_axes(ax)
    # Stack the slices, positive above 0 and negative below in the same colour, each edged by a surface gap; a side
    # that is empty in every year is not drawn
    for c, slices in stack_edges(wide, list(COMPONENTS)).items():
        for low, high in slices:
            if (high - low).any():
                ax.fill_between(years, low, high, facecolor=COMPONENTS[c][1], edgecolor=charts.SURFACE,
                                linewidth=GAP, zorder=2)
    # A thin line at 0 above the slices, where the positive and negative stacks meet
    ax.axhline(0, color=charts.CUT, lw=ZERO_WIDTH, zorder=3)
    # Years run edge to edge with fixed ticks, and the province names the panel
    ax.set_xlim(FIRST_YEAR, LAST_YEAR)
    ax.xaxis.set_major_locator(FixedLocator(XTICKS))
    ax.set_xticklabels([str(y) for y in XTICKS])
    ax.set_title(names[code], loc="left", fontsize=PANEL_TITLE_SIZE, fontweight="bold", color=charts.TEXT_PRIMARY,
                 pad=8)

# The shared y axis: one range, fixed ticks, and its title on the first panel
axes[0].set_ylim(*YLIM)
axes[0].yaxis.set_major_locator(FixedLocator(YTICKS))
axes[0].set_ylabel(YLABEL, color=charts.TEXT_SECONDARY, fontsize=10)

# Title at the top left, and one legend for all panels in a row under it
left = MARGINS["left"]
fig.text(left, TITLE_Y, TITLE, fontsize=15, fontweight="bold", color=charts.TEXT_PRIMARY, va="top")
handles = [Patch(facecolor=color, edgecolor="none", label=label) for label, color in COMPONENTS.values()]
fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(left, LEGEND_Y), ncol=len(handles), frameon=False,
           fontsize=9, labelcolor=charts.TEXT_SECONDARY, handlelength=1.0, handleheight=1.0, handletextpad=0.5,
           columnspacing=1.8, borderaxespad=0)

# Save the chart without a software stamp, so a rerun writes the same bytes
fig.savefig(OUT_PNG, dpi=DPI, facecolor=charts.SURFACE, metadata={"Software": None})
plt.close(fig)

# Write every plotted share with its province, year, component code and BPS status, in panel, year and stack order
table = shares.assign(province=shares["province_code"].map(names), share_pct=shares["value"],
                      panel=shares["province_code"].map({c: i for i, c in enumerate(PROVINCES)}),
                      stack=shares["component"].map({c: i for i, c in enumerate(COMPONENTS)}))
table = table.sort_values(["panel", "year", "stack"])
table[["province_code", "province", "year", "component", "share_pct", "status"]].to_csv(
    OUT_CSV, index=False, encoding="utf-8", lineterminator="\n")
print(f"Wrote {OUT_PNG.relative_to(ROOT)} and {OUT_CSV.relative_to(ROOT)}")
