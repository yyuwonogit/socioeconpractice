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
from matplotlib.colors import to_hex, to_rgb
from matplotlib.ticker import MultipleLocator
import numpy as np
import pandas as pd

# Parameters

# Input: BPS's school participation rates by province and age group (Angka Partisipasi Sekolah, % of the age group,
# Susenas), and the metadata beside them that names each province
DATA = ROOT / "data" / "20261104_bps-province-school-participation"
IN_CSV = DATA / "20261104_bps-province-school-participation.csv"
IN_META = DATA / "20261104_bps-province-school-participation-metadata.json"

# Input: BPS's sex ratio by province (men per 100 women, the population tables), in the population dataset
POP_DATA = ROOT / "data" / "20261102_bps-province-grdp-population"
POP_CSV = POP_DATA / "20261102_bps-province-grdp-population.csv"
SEX_RATIO = "sex_ratio"

# Outputs, beside this script
OUT_PNG = HERE / "20261105_schooling-cliff.png"
OUT_CSV = HERE / "20261105_schooling-cliff.csv"

# Indicator, year and the age group shown (higher education age, as the CSV labels it), and the national row
# (Indonesia, code 00) that is left out, which leaves the 38 provinces
INDICATOR = "school_participation_rate"
YEAR = "2025"
AGE_GROUP = "19-23"
NATIONAL = "00"
PROVINCES = 38

# Groups: the 38 provinces are cut into thirds at the terciles of their 2025 sex ratio (pd.qcut on the values, so
# provinces with the same ratio share a group; two tie at 102.2 on the lower cut). The middle and top thirds have
# about the same median school participation at ages 19-23, so the chart sets the third with the fewest men (14
# provinces) against the other two thirds together (24 provinces). Only three provinces have fewer than 100 men per
# 100 women, so the groups are named by how many men they have, not as provinces with more women. Box order (fewest
# men left), colours, and the x tick text of each group with its range of men per 100 women and its count
THIRDS = 3
GROUPS = ["fewest men", "more men"]
COLORS = {"fewest men": charts.TEXT_MUTED, "more men": charts.SERIES}
TICKS = {"fewest men": "Fewest men\n{lo}–{hi} men per 100 women\n{n} provinces",
         "more men": "More men\n{lo}–{hi} men per 100 women\n{n} provinces"}

# Texts: title, y axis title, each box's median label, the label of a named province and the gap label above the
# boxes (the median of the provinces with more men minus the median of those with the fewest, in percentage points)
TITLE = "School participation at ages 19–23 by men per 100 women, provinces, 2025"
YLABEL = "School participation, ages 19–23, % of the age group"
MEDIAN_TEXT = "{m:.1f}%"
NAME_TEXT = "{name} {v:.1f}%"
GAP_TEXT = "{gap} points, more vs fewest men"

# Boxes: centres on the x axis, width, standard whiskers at 1.5 times the interquartile range beyond the box (the most
# extreme province inside that reach ends the whisker), fill as a light tint of the group's colour (its weight mixed
# into the surface colour) and line widths. A province beyond the whiskers is drawn as a dot with its name; so is the
# province at the end of a long whisker, one reaching more than LONG_WHISKER interquartile ranges past its box
POSITIONS = [0, 1]
BOX_WIDTH = 0.34
WHISKER = 1.5
LONG_WHISKER = 1.0
TINT_WEIGHT = 0.18
EDGE_LW, MEDIAN_LW = 1.2, 2.6
DOT_SIZE = charts.POINT_SIZE

# Text sizes of the median labels, the province names, the gap label, the axis title and the x ticks; the gaps in
# points right of a box (median labels) and of a dot or cap (names), and the gap label's offset in points above the
# top of the y axis
MEDIAN_SIZE, NAME_SIZE, GAP_SIZE, AXIS_TITLE_SIZE, TICK_SIZE = 10, 9, 11, 10, 10
MEDIAN_OFFSET, NAME_OFFSET = 5, 7
GAP_OFFSET = 10

# y axis: 0 to 60 with ticks every 10, and the x axis limits in box positions
Y_LIMITS = (0, 60)
Y_STEP = 10
X_LIMITS = (-0.7, 1.7)

# Figure: a full 16:9 slide (charts.SLIDE_SIZE, in inches) at 200 dpi, the axes margins as figure fractions (the top
# one leaves the gap label's row clear of the title, the bottom one room for the three-line ticks), and where the title
# starts
FIGSIZE, DPI = charts.SLIDE_SIZE, 200
MARGINS = {"left": 0.075, "right": 0.98, "top": 0.86, "bottom": 0.15}
TEXT_LEFT = 0.03


# Functions

def mix(color_a, color_b, weight):
    """Return a colour between two colours: weight 0 gives the first, 1 the second."""
    a, b = np.array(to_rgb(color_a)), np.array(to_rgb(color_b))
    return to_hex(a + weight * (b - a))


def signed(value):
    """Format a gap in points with one decimal and its sign, a true minus sign for a fall and no sign for 0.0."""
    text = f"{abs(value):.1f}"
    if text == "0.0":
        return text
    return f"{'+' if value > 0 else '−'}{text}"


def box_stats(values):
    """Return the quartiles, the whisker ends and the values beyond the whiskers, as matplotlib's box plot draws them
    with whiskers at WHISKER interquartile ranges (linear percentiles)."""
    q1, q3 = np.percentile(values, [25, 75])
    iqr = q3 - q1
    low_reach, high_reach = q1 - WHISKER * iqr, q3 + WHISKER * iqr
    inside = values[(values >= low_reach) & (values <= high_reach)]
    return {"q1": q1, "q3": q3, "iqr": iqr, "low": inside.min(), "high": inside.max(),
            "outliers": values[(values < low_reach) | (values > high_reach)]}


# Steps

# Read the rates as text and keep the 2025 rows of the higher education age group for the provinces, without
# Indonesia's row; the 38 provinces must each appear once
raw = pd.read_csv(IN_CSV, dtype=str, keep_default_na=False)
df = raw[(raw["indicator"] == INDICATOR) & (raw["period"] == YEAR) & (raw["age_group"] == AGE_GROUP)
         & (raw["province_code"] != NATIONAL)].copy()
assert len(df) == PROVINCES and df["province_code"].is_unique, f"{YEAR}: not the 38 provinces once each"

# Turn the rates into numbers, and name each province from the metadata in display case
df["aps_pct"] = df["value"].astype(float)
meta = json.loads(IN_META.read_text(encoding="utf-8"))
df["unit"] = df["province_code"]
df["province"] = df["unit"].map(lambda code: charts.display_name(meta["provinces"][code]["name"]))

# Read each province's 2025 sex ratio, one value for each of the 38 provinces
pop = pd.read_csv(POP_CSV, dtype=str, keep_default_na=False)
rows = pop[(pop["indicator"] == SEX_RATIO) & (pop["period"] == YEAR) & (pop["province_code"] != NATIONAL)]
sex_ratio = rows.set_index("province_code")["value"].astype(float)
assert len(sex_ratio) == PROVINCES and sex_ratio.index.is_unique, f"{YEAR}: not one sex ratio per province"
assert set(sex_ratio.index) == set(df["unit"]), f"{YEAR}: the sex ratios and the rates cover other provinces"

# Cut the provinces into thirds on their sex ratio, then set the third with the fewest men against the other two,
# noting each group's range and size
bottom = pd.qcut(sex_ratio, THIRDS, labels=False) == 0
group = pd.Series(np.where(bottom, GROUPS[0], GROUPS[1]), index=sex_ratio.index)
ranges = {g: (sex_ratio[group == g].min(), sex_ratio[group == g].max(), int((group == g).sum())) for g in GROUPS}
df["sex_ratio"] = df["unit"].map(sex_ratio)
df["group"] = df["unit"].map(group)

# Order the rows by group (fewest men first), then rate (lowest first)
df["group_order"] = df["group"].map(GROUPS.index)
df = df.sort_values(["group_order", "aps_pct", "unit"]).reset_index(drop=True)

# Each box's rates, median and whisker statistics, and the gap between the groups' medians
members = {g: df.loc[df["group"] == g].set_index("province")["aps_pct"] for g in GROUPS}
medians = {g: m.median() for g, m in members.items()}
boxes = {g: box_stats(m) for g, m in members.items()}
gap = medians[GROUPS[1]] - medians[GROUPS[0]]

# Draw the axes: the shared style with the vertical grid lines removed, so only the horizontal grid stays
fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
fig.patch.set_facecolor(charts.SURFACE)
fig.subplots_adjust(**MARGINS)
charts.style_axes(ax)
ax.xaxis.grid(False)
ax.set_axisbelow(True)

# Draw each group's box in its colour: tinted fill, edges, standard whiskers, caps and median; label the median just
# right of its box
for g, p in zip(GROUPS, POSITIONS):
    color = COLORS[g]
    line = {"color": color, "lw": EDGE_LW}
    ax.boxplot([members[g].to_numpy()], positions=[p], widths=BOX_WIDTH, whis=WHISKER, showfliers=False,
               patch_artist=True, zorder=2,
               boxprops={"facecolor": mix(charts.SURFACE, color, TINT_WEIGHT), "edgecolor": color, "lw": EDGE_LW},
               medianprops={"color": color, "lw": MEDIAN_LW, "solid_capstyle": "butt"},
               whiskerprops=line, capprops=line)
    ax.annotate(MEDIAN_TEXT.format(m=medians[g]), (p + BOX_WIDTH / 2, medians[g]), xytext=(MEDIAN_OFFSET, 0),
                textcoords="offset points", ha="left", va="center", fontsize=MEDIAN_SIZE, fontweight="bold",
                color=color)

# Draw each province beyond the whiskers as a dot in its group's colour with its name and rate to the right, and
# name the province at the end of a long whisker beside its cap
named = []
for g, p in zip(GROUPS, POSITIONS):
    stats_g = boxes[g]
    for name, value in stats_g["outliers"].items():
        ax.scatter([p], [value], zorder=4, **charts.point_marks({"color": COLORS[g]}, DOT_SIZE))
        ax.annotate(NAME_TEXT.format(name=name, v=value), (p, value), xytext=(NAME_OFFSET, 0),
                    textcoords="offset points", ha="left", va="center", fontsize=NAME_SIZE,
                    color=charts.TEXT_PRIMARY)
        named.append((g, name, value, "beyond the whisker"))
    for end, edge in [("low", stats_g["q1"]), ("high", stats_g["q3"])]:
        value = stats_g[end]
        if abs(value - edge) > LONG_WHISKER * stats_g["iqr"]:
            name = members[g][members[g] == value].index[0]
            ax.annotate(NAME_TEXT.format(name=name, v=value), (p + BOX_WIDTH / 4, value), xytext=(NAME_OFFSET, 0),
                        textcoords="offset points", ha="left", va="center", fontsize=NAME_SIZE,
                        color=charts.TEXT_PRIMARY)
            named.append((g, name, value, f"end of the {end} whisker"))

# Set the axis limits and the y ticks every 10 points
ax.set_ylim(*Y_LIMITS)
ax.set_xlim(*X_LIMITS)
ax.yaxis.set_major_locator(MultipleLocator(Y_STEP))

# Name the groups, their ranges of men per 100 women and their counts on the x ticks, and title the y axis
ax.set_xticks(POSITIONS, labels=[TICKS[g].format(lo=f"{ranges[g][0]:.1f}", hi=f"{ranges[g][1]:.1f}", n=ranges[g][2])
                                 for g in GROUPS])
ax.tick_params(axis="x", labelsize=TICK_SIZE, labelcolor=charts.TEXT_PRIMARY, pad=8)
ax.set_ylabel(YLABEL, fontsize=AXIS_TITLE_SIZE, color=charts.TEXT_SECONDARY, labelpad=10)

# Label the gap between the groups' medians above the top of the y axis, centred over the two boxes
ax.annotate(GAP_TEXT.format(gap=signed(gap)), (sum(POSITIONS) / len(POSITIONS), Y_LIMITS[1]), xytext=(0, GAP_OFFSET),
            textcoords="offset points", ha="center", va="bottom", fontsize=GAP_SIZE, fontweight="bold",
            color=charts.TEXT_PRIMARY, zorder=5, annotation_clip=False)

# Add the title, with the groups named on the x axis and no legend, and save the chart
charts.finish(fig, TITLE, [], OUT_PNG, left=TEXT_LEFT)

# Write the table, one row per province, group first, then rate
df[["unit", "province", "sex_ratio", "group", "age_group", "aps_pct", "status"]].to_csv(
    OUT_CSV, index=False, encoding="utf-8", lineterminator="\n")

# Report each group's range of men per 100 women, median, box and whiskers, the named provinces and the gap
for g in GROUPS:
    lo, hi, n = ranges[g]
    b = boxes[g]
    print(f"{g}: {lo:.2f}-{hi:.2f} men per 100 women, {n} provinces; median {medians[g]:.2f}, box {b['q1']:.2f}-"
          f"{b['q3']:.2f}, whiskers {b['low']:.2f}-{b['high']:.2f}, beyond: {len(b['outliers'])}")
for g, name, value, why in named:
    print(f"Named ({g}, {why}): {name} {value:.2f}")
print(f"More minus fewest men: {gap:+.2f} (label {signed(gap)})")
