from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# Load the shared chart module from tools/
import sys
sys.path.insert(0, str(ROOT / "tools"))
import charts

import math

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MultipleLocator
import numpy as np
import pandas as pd

# Parameters

# Real GRDP and real GRDP per capita: BPS WebAPI vars 286 and 288 at constant 2010 prices, GRDP in Rp billion and per
# capita in Rp thousand per person, in dataset 20261103_bps-province-grdp-2010-2025. The national row is left out
DATASET = ROOT / "data" / "20261103_bps-province-grdp-2010-2025"
DATA_CSV = DATASET / "20261103_bps-province-grdp-2010-2025.csv"
GRDP, PER_CAPITA = "grdp_constant_2010", "grdp_per_capita_constant_2010"
SECTOR = "TOTAL"
NATIONAL = "00"

# Years drawn, and the year every index is set to 100 in
FIRST_YEAR, LAST_YEAR = 2010, 2025
BASE_YEAR = 2010

# Time zones by BPS province code: WIB (UTC+7), WITA (UTC+8) and WIT (UTC+9). A zone's figures sum all its provinces,
# so the province splits inside the period (Kalimantan Utara out of Kalimantan Timur, reported apart in these tables
# from 2013; the four new Papua provinces, reported apart from 2023) stay inside their zone and every zone keeps fixed
# borders over the whole period
ZONES = {
    "WIB": ["11", "12", "13", "14", "15", "16", "17", "18", "19", "21", "31", "32", "33", "34", "35", "36", "61", "62"],
    "WITA": ["51", "52", "53", "63", "64", "65", "71", "72", "73", "74", "75", "76"],
    "WIT": ["81", "82", "91", "92", "94", "95", "96", "97"],
}

# Zone colours: charts.SERIES blue for WIB, amber for WITA and magenta for WIT, a set that keeps every pair at least
# 35 CIELAB units apart under simulated protanopia and 54 under deuteranopia (21 under tritanopia)
ZONE_COLORS = {"WIB": charts.SERIES, "WITA": "#c27c0e", "WIT": "#b03a7a"}

# Line widths in points: the zone lines, the line at 100 and the label leaders
ZONE_LW = 2.6
BASE_LW = 0.9
LEADER_LW = 0.6

# Y axis: linear, ticks every Y_STEP index points, with this room in index points below the lowest value and above
# the highest, rounded out to whole steps
Y_STEP = 20
Y_ROOM = 5

# X axis: years of room before the first year and after the last
X_PAD_LEFT, X_PAD_RIGHT = 0.3, 0.15

# End labels: font size, the gap in points between the axes' right edge and a label, the gap in points between two
# stacked labels, and the shift in points past which a moved label gets a leader to its line's end
LABEL_SIZE = 10
LABEL_OFFSET = 4
LABEL_GAP = 1.5
LEADER_FROM = 1.5

# Figure size, resolution and margins; the right margin is set from the widest end label, keeping this room in
# points between that label and the figure's edge
FIGSIZE = (12, 7.5)
DPI = 200
MARGINS = {"left": 0.07, "top": 0.885, "bottom": 0.07}
RIGHT_ROOM = 8

# Title, axis title and legend texts
TITLE = "Real GRDP per capita by time zone, Indonesia, index 2010 = 100, 2010–2025"
YLABEL = "Real GRDP per capita, index 2010 = 100"
LEGEND = {zone: f"{zone} ({len(codes)} provinces)" for zone, codes in ZONES.items()}

# Outputs beside this script
OUT_PNG = HERE / "20261105_timezone-growth.png"
OUT_CSV = HERE / "20261105_timezone-growth.csv"

# Functions


def stack_block(members, targets, heights, gap, low, high):
    """Return the bottom, height and member centres of a block of touching labels, in pixels.

    The block sits on its members' targets on average and stays between low and high.
    """
    offsets, run = [], 0.0
    for i in members:
        offsets.append(run + heights[i] / 2)
        run += heights[i] + gap
    size = run - gap
    bottom = float(np.mean([targets[i] - o for i, o in zip(members, offsets)]))
    bottom = min(max(bottom, low), high - size)
    return bottom, size, [bottom + o for o in offsets]


def spread(targets, heights, gap, low, high):
    """Return label centres in pixels, each as near its target as it can sit without overlapping another label.

    Labels are taken from the lowest target up; a label that overlaps the block below joins it, and the merged block
    is centred again on its members' targets, until no two blocks overlap.
    """
    blocks = []
    for i in sorted(range(len(targets)), key=lambda k: targets[k]):
        blocks.append([i])
        while len(blocks) > 1:
            lower, lower_size, _ = stack_block(blocks[-2], targets, heights, gap, low, high)
            upper, _, _ = stack_block(blocks[-1], targets, heights, gap, low, high)
            if lower + lower_size + gap <= upper:
                break
            merged = blocks.pop()
            blocks[-1] += merged
    centres = [0.0] * len(targets)
    for members in blocks:
        for i, c in zip(members, stack_block(members, targets, heights, gap, low, high)[2]):
            centres[i] = c
    return centres


# Steps

# Read every province's annual real GRDP and real GRDP per capita, 2010-2025, without the national row, keeping empty
# status markers as empty text
raw = pd.read_csv(DATA_CSV, dtype=str, keep_default_na=False, encoding="utf-8")
rows = raw[raw["indicator"].isin([GRDP, PER_CAPITA]) & (raw["sector"] == SECTOR) & (raw["province_code"] != NATIONAL)
           & raw["period"].str.fullmatch(r"\d{4}")].copy()
rows["year"] = rows["period"].astype(int)
rows = rows[rows["year"].between(FIRST_YEAR, LAST_YEAR)]
rows["value"] = rows["value"].astype(float)

# One row per province and year with both values; each province's population (million persons) is the one BPS's per
# capita figure implies: GRDP (Rp billion) / GRDP per capita (Rp thousand per person)
data = rows.pivot_table(index=["province_code", "year"], columns="indicator", values="value").reset_index()
if data[[GRDP, PER_CAPITA]].isna().any().any():
    raise ValueError("a province-year has GRDP without GRDP per capita, or the other way round")
data["value"] = data[GRDP]
data["population_m"] = data[GRDP] / data[PER_CAPITA]
data["status"] = data.set_index(["province_code", "year"]).index.map(
    rows[rows["indicator"] == GRDP].set_index(["province_code", "year"])["status"])

# Stop unless every province in the data sits in exactly one time zone and every zone code has values
zone_of = {code: zone for zone, codes in ZONES.items() for code in codes}
if len(zone_of) != sum(len(codes) for codes in ZONES.values()):
    raise ValueError("a province code is listed in more than one time zone")
unzoned = sorted(set(data["province_code"]) - set(zone_of))
missing = sorted(set(zone_of) - set(data["province_code"]))
if unzoned or missing:
    raise ValueError(f"codes in the data without a zone: {unzoned}; zone codes without data: {missing}")
data["zone"] = data["province_code"].map(zone_of)

# Take each year's BPS status marker, which every row of the year carries
markers = data.groupby("year")["status"].unique()
if (markers.map(len) != 1).any():
    raise ValueError(f"years with more than one status marker: {markers[markers.map(len) != 1].to_dict()}")
status = markers.map(lambda m: m[0]).to_dict()

# Sum each zone's GRDP and population in every year, listing the codes summed, and stop unless every zone has every
# year
grouped = data.groupby(["zone", "year"], sort=True)
table = grouped[["value", "population_m"]].sum().rename(columns={"value": "grdp_constant_2010_bn"}).reset_index()
table["area_codes"] = grouped["province_code"].apply(lambda c: "+".join(sorted(c))).to_numpy()
counts = table.groupby("zone")["year"].nunique()
if (counts != LAST_YEAR - FIRST_YEAR + 1).any():
    raise ValueError(f"zones without every year {FIRST_YEAR}-{LAST_YEAR}: {counts.to_dict()}")

# Each zone's real GRDP per capita (Rp thousand per person) is its summed GRDP over its summed population, indexed to
# its 2010 value = 100; then the year's status marker
table["grdp_pc_constant_2010_k"] = table["grdp_constant_2010_bn"] / table["population_m"]
base = table[table["year"] == BASE_YEAR].set_index("zone")["grdp_pc_constant_2010_k"]
table["index"] = (table["grdp_pc_constant_2010_k"] / table["zone"].map(base) * 100).round(2)
table["grdp_constant_2010_bn"] = table["grdp_constant_2010_bn"].round(2)
table["population_m"] = table["population_m"].round(4)
table["grdp_pc_constant_2010_k"] = table["grdp_pc_constant_2010_k"].round(2)
table["status"] = table["year"].map(status)
table["zone_rank"] = table["zone"].map({zone: i for i, zone in enumerate(ZONES)})
table = table.sort_values(["zone_rank", "year"]).reset_index(drop=True)
last = table[table["year"] == LAST_YEAR].set_index("zone")["index"]

# Set up the figure; the end labels are measured first, so the right margin leaves room for the widest
fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
fig.patch.set_facecolor(charts.SURFACE)
renderer = fig.canvas.get_renderer()
px = DPI / 72
labels = [{"text": f"{zone} {last[zone]:.0f}", "index": last[zone], "color": ZONE_COLORS[zone]} for zone in ZONES]
for lab in labels:
    probe = fig.text(0, 0, lab["text"], fontsize=LABEL_SIZE, fontweight="bold")
    box = probe.get_window_extent(renderer)
    lab["width"], lab["height"] = box.width, box.height
    probe.remove()
right = 1 - ((LABEL_OFFSET + RIGHT_ROOM) * px + max(lab["width"] for lab in labels)) / (FIGSIZE[0] * DPI)
fig.subplots_adjust(right=right, **MARGINS)

# Style the axes as the shared charts do, with the horizontal grid only, and a linear y axis in whole steps
charts.style_axes(ax)
ax.xaxis.grid(False)
low = math.floor((table["index"].min() - Y_ROOM) / Y_STEP) * Y_STEP
high = math.ceil((table["index"].max() + Y_ROOM) / Y_STEP) * Y_STEP
ax.set_ylim(low, high)
ax.yaxis.set_major_locator(MultipleLocator(Y_STEP))
ax.set_xlim(FIRST_YEAR - X_PAD_LEFT, LAST_YEAR + X_PAD_RIGHT)
ax.set_xticks(range(FIRST_YEAR, LAST_YEAR + 1))
ax.set_ylabel(YLABEL, color=charts.TEXT_SECONDARY, fontsize=10)

# Draw the thin line at 100, then each zone's total as a bold line in its own colour
ax.axhline(100, color=charts.CUT, lw=BASE_LW, zorder=1.5)
for zone in ZONES:
    part = table[table["zone"] == zone]
    ax.plot(part["year"], part["index"], color=ZONE_COLORS[zone], lw=ZONE_LW, zorder=4, solid_joinstyle="round",
            solid_capstyle="round")

# Name each zone line with its 2025 index at its right end, moving labels apart vertically where they would overlap,
# with a thin leader back to the line's end for a label that had to move
fig.canvas.draw()
frame = ax.get_window_extent(renderer)
ends = [ax.transData.transform((LAST_YEAR, lab["index"])) for lab in labels]
centres = spread([e[1] for e in ends], [lab["height"] for lab in labels], LABEL_GAP * px, frame.y0, frame.y1)
for lab, (x_end, y_end), centre in zip(labels, ends, centres):
    dx, dy = (frame.x1 + LABEL_OFFSET * px - x_end) / px, (centre - y_end) / px
    leader = {"arrowstyle": "-", "color": lab["color"], "lw": LEADER_LW, "shrinkA": 1, "shrinkB": 1} \
        if abs(dy) > LEADER_FROM else None
    ax.annotate(lab["text"], (LAST_YEAR, lab["index"]), xytext=(dx, dy), textcoords="offset points", ha="left",
                va="center", fontsize=LABEL_SIZE, fontweight="bold", color=lab["color"], arrowprops=leader,
                annotation_clip=False)

# Add the title and the legend of the three zones, and save the chart
handles = [Line2D([], [], color=ZONE_COLORS[zone], lw=ZONE_LW, label=LEGEND[zone]) for zone in ZONES]
charts.finish(fig, TITLE, handles, OUT_PNG, left=MARGINS["left"])

# Write every value the chart plots: each zone's GRDP, population, GRDP per capita and index by year
table[["zone", "area_codes", "year", "grdp_constant_2010_bn", "population_m", "grdp_pc_constant_2010_k", "index",
       "status"]].to_csv(OUT_CSV, index=False, encoding="utf-8", lineterminator="\n")

# Print each zone's 2025 index, its average yearly growth over 2010-2025 and the years its GRDP per capita fell
span = LAST_YEAR - BASE_YEAR
for zone in ZONES:
    part = table[table["zone"] == zone].set_index("year")["grdp_pc_constant_2010_k"]
    fell = [int(y) for y in part.index[1:] if part[y] < part[y - 1]]
    print(f"{zone}: 2025 index {last[zone]:.2f}, average yearly growth {((last[zone] / 100) ** (1 / span) - 1) * 100:.2f}%, "
          f"fell in {fell}")
