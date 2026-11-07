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
from matplotlib.colors import to_hex, to_rgb
from matplotlib.patches import Patch
from matplotlib.ticker import FormatStrFormatter, MultipleLocator
import numpy as np
import pandas as pd

# Parameters

# Year of the cross-section: the panel's 2025 rows hold the 38 provinces, one unit each
YEAR = 2025

# Gini ratio of household spending per capita by area, BPS WebAPI var 98 (dataset 20261103_bps-province-gini), from
# the March Susenas round (S1) as province_panel.build() picks it; a ratio with no unit, published to 3 decimals. DKI
# Jakarta (31) has no rural area and so no rural Gini, which leaves 37 provinces in the rural boxes. T3 found the
# lower Gini of extractive provinces in the urban Gini (partial rank correlation -0.38 at equal income) and not in the
# rural Gini; this chart shows the 2025 levels by group, with no income control
AREAS = {"urban": {"column": "gini_urban", "label": "Urban"}, "rural": {"column": "gini_rural", "label": "Rural"}}

# Extractive share: province_panel.SHARP_SHARE, the share of GRDP at current prices of the fossil, metals, plantation,
# forest and quarrying groups (BPS GRDP by detailed industry, SIMDASI yearbook tables, on the panel's borders). High
# extraction is a 2025 share strictly above the median of the 38 provinces' 2025 shares (province_panel.above_median),
# 19 provinces; low extraction is the other 19
GROUPS = {
    "high": {"color": charts.SERIES, "label": "Extractive share above the 2025 median"},
    "low": {"color": charts.TEXT_MUTED, "label": "Extractive share below the 2025 median"},
}

# Box layout in data units: cluster centres on the x axis, each group's shift from its cluster centre (high left, low
# right), box width, and the share of the box width the dots spread over
CLUSTER_X = {"urban": 1.0, "rural": 2.0}
BOX_SHIFT = {"high": -0.19, "low": 0.19}
BOX_WIDTH = 0.3
SPREAD = 0.62 * BOX_WIDTH
XLIM = (0.5, 2.5)

# Whiskers reach the furthest value within 1.5 times the interquartile range of the box; matplotlib's quartiles
# interpolate linearly between values
WHIS = 1.5

# Deterministic dot spread: evenly spaced slots across SPREAD, taken in this cycle by order of value, so dots next in
# value sit at least one slot apart (no random jitter)
SLOT_CYCLE = [2, 0, 4, 1, 3]

# Box look: share of the group colour in the light fill, and line widths in points
FILL_SHARE = 0.16
BOX_LW = 1.3
MEDIAN_LW = 2.4
WHISKER_LW = 1.1

# Dots: marker area in points squared, and the gap in pixels that labels keep from every dot and box line
DOT_SIZE = 34
LABEL_GAP = 2

# Y axis: tick step, tick label format and the headroom above and below the values as a share of their span
Y_STEP = 0.05
Y_FORMAT = "%.2f"
Y_PAD = 0.1

# Figure size, resolution, margins and text
FIGSIZE = (11, 7)
DPI = 200
MARGINS = {"left": 0.07, "right": 0.98, "top": 0.87, "bottom": 0.08}
LABEL_SIZE = 8
TITLE = "Urban and rural Gini ratio in high- and low-extraction provinces, March 2025"
YLABEL = "Gini ratio, March 2025"

# Outputs beside this script
OUT_PNG = HERE / "20261105_gini-urban-rural.png"
OUT_CSV = HERE / "20261105_gini-urban-rural.csv"

# Functions


def tint(color, share):
    """Return a colour mixed into the chart surface, keeping share of the colour, as a hex code."""
    mixed = share * np.array(to_rgb(color)) + (1 - share) * np.array(to_rgb(charts.SURFACE))
    return to_hex(mixed)


def spread_offsets(n):
    """Return n horizontal offsets in data units for the dots of a box taken in order of value."""
    slots = np.linspace(-SPREAD / 2, SPREAD / 2, len(SLOT_CYCLE))
    return np.array([slots[SLOT_CYCLE[k % len(SLOT_CYCLE)]] for k in range(n)])


def dot_box(ax, x, y, radius):
    """Return a dot's box in display pixels, (x0, y0, x1, y1), radius pixels around its centre."""
    px, py = ax.transData.transform((x, y))
    return (px - radius, py - radius, px + radius, py + radius)


# Steps

# Build the harmonised panel with all its checks, and keep the 2025 rows
b = province_panel.build()
year = b.panel[b.panel["year"] == YEAR].reset_index(drop=True)

# Split the provinces at the median of their 2025 extractive shares
share = year[province_panel.SHARP_SHARE]
group = np.where(province_panel.above_median(share), "high", "low")

# Gather one row per province and area that has a Gini ratio (DKI Jakarta has no rural row), ordered as drawn
parts = []
for area, spec in AREAS.items():
    part = pd.DataFrame({"unit": year["unit"], "province": year["unit_name"].map(charts.display_name),
                         "extractive_share_pct": share, "group": group, "area": area, "gini": year[spec["column"]]})
    parts.append(part.dropna(subset=["gini"]))
table = pd.concat(parts, ignore_index=True)
table["area_order"] = table["area"].map({a: i for i, a in enumerate(AREAS)})
table["group_order"] = table["group"].map({g: i for i, g in enumerate(GROUPS)})
table = table.sort_values(["area_order", "group_order", "gini", "unit"], ascending=[True, True, False, True])
table = table.drop(columns=["area_order", "group_order"]).reset_index(drop=True)

# Set up the figure and its axes in their final place, so labels can be measured in pixels
fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
fig.patch.set_facecolor(charts.SURFACE)
charts.style_axes(ax)
ax.xaxis.grid(False)
fig.subplots_adjust(**MARGINS)

# Draw each box with its dots spread across it, and keep the dots, their labels and the box artists for labelling
xs, ys, labels, artists, medians = [], [], [], [], {}
for area in AREAS:
    for g, style in GROUPS.items():
        part = table[(table["area"] == area) & (table["group"] == g)].sort_values(["gini", "unit"])
        pos = CLUSTER_X[area] + BOX_SHIFT[g]
        color = style["color"]
        # The box: light fill, coloured edge and median, whiskers at 1.5 IQR, no flier marks since every dot is drawn
        drawn = ax.boxplot(part["gini"], positions=[pos], widths=BOX_WIDTH, whis=WHIS, patch_artist=True,
                           showfliers=False, manage_ticks=False,
                           boxprops={"facecolor": tint(color, FILL_SHARE), "edgecolor": color, "linewidth": BOX_LW},
                           medianprops={"color": color, "linewidth": MEDIAN_LW, "solid_capstyle": "butt"},
                           whiskerprops={"color": color, "linewidth": WHISKER_LW},
                           capprops={"color": color, "linewidth": WHISKER_LW})
        for key in ["boxes", "whiskers", "caps", "medians"]:
            for artist in drawn[key]:
                artist.set_zorder(2)
                artists.append(artist)
        medians[(area, g)] = float(np.median(part["gini"]))
        # The dots, spread over deterministic slots by order of value, above the box
        dx = pos + spread_offsets(len(part))
        ax.scatter(dx, part["gini"], marker="o", zorder=3, **charts.point_marks({"color": color}, DOT_SIZE))
        # Name the highest and lowest province of the box, every one of them if values tie
        top, low = part["gini"].max(), part["gini"].min()
        xs += dx.tolist()
        ys += part["gini"].tolist()
        labels += [n if v in (top, low) else "" for n, v in zip(part["province"], part["gini"])]

# Set the axis limits, ticks and titles before any label is measured
span = table["gini"].max() - table["gini"].min()
ax.set_xlim(*XLIM)
ax.set_ylim(table["gini"].min() - Y_PAD * span, table["gini"].max() + Y_PAD * span)
ax.yaxis.set_major_locator(MultipleLocator(Y_STEP))
ax.yaxis.set_major_formatter(FormatStrFormatter(Y_FORMAT))
ax.set_xticks([CLUSTER_X[a] for a in AREAS])
ax.set_xticklabels([AREAS[a]["label"] for a in AREAS])
ax.tick_params(axis="x", labelsize=10, colors=charts.TEXT_PRIMARY)
ax.set_ylabel(YLABEL, color=charts.TEXT_SECONDARY, fontsize=10)

# Label the extremes clear of every dot and every box line
fig.canvas.draw()
renderer = fig.canvas.get_renderer()
radius = (np.sqrt(DOT_SIZE) / 2 + 1) * DPI / 72 + LABEL_GAP
avoid = [dot_box(ax, x, y, radius) for x, y in zip(xs, ys)]
avoid += [charts.box_of(a, renderer, pad=LABEL_GAP) for a in artists]
charts.place_labels(ax, xs, ys, labels, fontsize=LABEL_SIZE, avoid=avoid)

# Add the title and the legend of the two groups, and save the chart
handles = [Patch(facecolor=tint(s["color"], FILL_SHARE), edgecolor=s["color"], linewidth=BOX_LW, label=s["label"])
           for s in GROUPS.values()]
charts.finish(fig, TITLE, handles, OUT_PNG, left=MARGINS["left"])

# Write every value the chart plots
table.to_csv(OUT_CSV, index=False, encoding="utf-8", lineterminator="\n")

# Print the four medians and the high-minus-low gap in each area
for area in AREAS:
    high, low = medians[(area, "high")], medians[(area, "low")]
    n_high = int(((table["area"] == area) & (table["group"] == "high")).sum())
    n_low = int(((table["area"] == area) & (table["group"] == "low")).sum())
    print(f"{area}: median high {high:.4f} (n={n_high}), low {low:.4f} (n={n_low}), high minus low {high - low:+.4f}")
