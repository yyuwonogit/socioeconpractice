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

# Input: BPS's provincial population table (sex ratio, men per 100 women, and population density, people per km2) and
# the metadata beside it that names each province. The 2025 values are BPS's Indonesia Population Projection 2020-2050
# (SP2020 base), not counts
DATA = ROOT / "data" / "20261102_bps-province-grdp-population"
IN_CSV = DATA / "20261102_bps-province-grdp-population.csv"
IN_META = DATA / "20261102_bps-province-grdp-population-metadata.json"

# Outputs, beside this script
OUT_PNG = HERE / "20261105_sex-ratio-by-density.png"
OUT_CSV = HERE / "20261105_sex-ratio-by-density.csv"

# Indicators and year, and the national row (Indonesia, code 00) that is left out, which leaves the 38 provinces
SEX_RATIO = "sex_ratio"
DENSITY = "population_density"
YEAR = "2025"
NATIONAL = "00"
PROVINCES = 38

# Groups: the 38 provinces are cut into thirds at the terciles of their 2025 population density (pd.qcut on the
# values), fixed before looking at the sex ratio. The middle and dense thirds overlap on the sex ratio, so the chart
# sets the sparse third (13 provinces) against the other two thirds together (25 provinces), as the schooling chart
# sets the third with the fewest men against the rest. Box order (sparse left), colours, and the x tick text of each
# group with its density range and count
THIRDS = 3
GROUPS = ["sparse", "rest"]
COLORS = {"sparse": charts.SERIES, "rest": charts.TEXT_MUTED}
TICKS = {"sparse": "Sparse\n{lo}–{hi} people per km²\n{n} provinces",
         "rest": "The rest\n{lo}–{hi} people per km²\n{n} provinces"}

# Texts: title, y axis title, each box's median label, the label of a named province, the line at 100 men per 100
# women and its label, and the gap label above the boxes (the sparse third's median minus the rest's)
TITLE = "Men per 100 women by population density, Indonesian provinces, 2025"
YLABEL = "Men per 100 women, 2025"
MEDIAN_TEXT = "{m:.1f}"
NAME_TEXT = "{name} {v:.1f}"
PARITY, PARITY_TEXT = 100, "100"
GAP_TEXT = "{gap} men per 100 women, sparse vs the rest"

# Boxes: centres on the x axis, width, standard whiskers at 1.5 times the interquartile range beyond the box (the most
# extreme province inside that reach ends the whisker), fill as a light tint of the group's colour (its weight mixed
# into the surface colour) and line widths. A province beyond the whiskers would be drawn as a dot with its name; the
# provinces with the most and the fewest men of all 38 are named where they sit, at a whisker end or as such a dot
POSITIONS = [0, 1]
BOX_WIDTH = 0.34
WHISKER = 1.5
TINT_WEIGHT = 0.18
EDGE_LW, MEDIAN_LW, PARITY_LW = 1.2, 2.6, 0.9
DOT_SIZE = charts.POINT_SIZE

# Text sizes of the median labels, the province names, the gap label, the axis title, the x ticks and the line label;
# the gaps in points right of a box (median labels), of a dot or a cap (names) and of the line's right end, and the
# gap label's offset in points above the top of the y axis
MEDIAN_SIZE, NAME_SIZE, GAP_SIZE, AXIS_TITLE_SIZE, TICK_SIZE, PARITY_SIZE = 10, 9, 11, 10, 10, 8
MEDIAN_OFFSET, NAME_OFFSET, PARITY_OFFSET = 5, 7, 4
GAP_OFFSET = 10

# y axis: 96 to 116 men per 100 women with ticks every 2, and the x axis limits in box positions
Y_LIMITS = (96, 116)
Y_STEP = 2
X_LIMITS = (-0.7, 1.7)

# Figure: a full 16:9 slide (charts.SLIDE_SIZE, in inches) at 200 dpi, the axes margins as figure fractions (the top
# one leaves the gap label's row clear of the title, the bottom one room for the three-line ticks), and where the
# title starts
FIGSIZE, DPI = charts.SLIDE_SIZE, 200
MARGINS = {"left": 0.075, "right": 0.98, "top": 0.86, "bottom": 0.15}
TEXT_LEFT = 0.03


# Functions

def mix(color_a, color_b, weight):
    """Return a colour between two colours: weight 0 gives the first, 1 the second."""
    a, b = np.array(to_rgb(color_a)), np.array(to_rgb(color_b))
    return to_hex(a + weight * (b - a))


def signed(value):
    """Format a gap with one decimal and its sign, a true minus sign for a fall and no sign for 0.0."""
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
    return {"q1": q1, "q3": q3, "low": inside.min(), "high": inside.max(),
            "outliers": values[(values < low_reach) | (values > high_reach)]}


# Steps

# Read the 2025 sex ratio and density of the provinces, without Indonesia's row; each of the 38 provinces must have
# both once
raw = pd.read_csv(IN_CSV, dtype=str, keep_default_na=False)
rows = raw[raw["indicator"].isin([SEX_RATIO, DENSITY]) & (raw["period"] == YEAR) & (raw["province_code"] != NATIONAL)]
wide = rows.assign(value=rows["value"].astype(float)).pivot(index="province_code", columns="indicator", values="value")
assert len(wide) == PROVINCES and wide.notna().all().all(), f"{YEAR}: not both values for each of the 38 provinces"

# Name each province from the metadata in display case, and keep the code as the unit
meta = json.loads(IN_META.read_text(encoding="utf-8"))
df = pd.DataFrame({"unit": wide.index, "density_per_km2": wide[DENSITY].to_numpy(),
                   "sex_ratio": wide[SEX_RATIO].to_numpy()})
df["province"] = df["unit"].map(lambda code: charts.display_name(meta["provinces"][code]["name"]))

# Cut the provinces into thirds on their density, then set the sparse third against the other two, noting each group's
# density range and size
sparse = (pd.qcut(df["density_per_km2"], THIRDS, labels=False) == 0).to_numpy()
df["group"] = np.where(sparse, GROUPS[0], GROUPS[1])
ranges = {g: (df.loc[df["group"] == g, "density_per_km2"].min(), df.loc[df["group"] == g, "density_per_km2"].max(),
              int((df["group"] == g).sum())) for g in GROUPS}

# Order the rows by group (sparse first), then sex ratio (lowest first)
df["group_order"] = df["group"].map(GROUPS.index)
df = df.sort_values(["group_order", "sex_ratio", "unit"]).reset_index(drop=True)

# Each box's sex ratios, median and whisker statistics, and the gap between the groups' medians
members = {g: df.loc[df["group"] == g].set_index("province")["sex_ratio"] for g in GROUPS}
medians = {g: m.median() for g, m in members.items()}
boxes = {g: box_stats(m) for g, m in members.items()}
gap = medians[GROUPS[0]] - medians[GROUPS[1]]

# Draw the axes: the shared style with the vertical grid lines removed, so only the horizontal grid stays
fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
fig.patch.set_facecolor(charts.SURFACE)
fig.subplots_adjust(**MARGINS)
charts.style_axes(ax)
ax.xaxis.grid(False)
ax.set_axisbelow(True)

# Draw the line at 100 men per 100 women, labelled at its right end
ax.axhline(PARITY, color=charts.CUT, lw=PARITY_LW, zorder=1)
ax.annotate(PARITY_TEXT, (1, PARITY), xycoords=("axes fraction", "data"), xytext=(-PARITY_OFFSET, -PARITY_OFFSET),
            textcoords="offset points", ha="right", va="top", fontsize=PARITY_SIZE, color=charts.TEXT_MUTED)

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

# Draw any province beyond the whiskers as a dot with its name; then name the provinces with the most and the fewest
# men of all 38 where they sit, beside their dot or beside the cap of the whisker they end
named = []
for g, p in zip(GROUPS, POSITIONS):
    for name, value in boxes[g]["outliers"].items():
        ax.scatter([p], [value], zorder=4, **charts.point_marks({"color": COLORS[g]}, DOT_SIZE))
        ax.annotate(NAME_TEXT.format(name=name, v=value), (p, value), xytext=(NAME_OFFSET, 0),
                    textcoords="offset points", ha="left", va="center", fontsize=NAME_SIZE, color=charts.TEXT_PRIMARY)
        named.append(name)
for i in (df["sex_ratio"].idxmax(), df["sex_ratio"].idxmin()):
    name, value, g = df.at[i, "province"], df.at[i, "sex_ratio"], df.at[i, "group"]
    if name in named:
        continue
    p = POSITIONS[GROUPS.index(g)]
    ax.annotate(NAME_TEXT.format(name=name, v=value), (p + BOX_WIDTH / 4, value), xytext=(NAME_OFFSET, 0),
                textcoords="offset points", ha="left", va="center", fontsize=NAME_SIZE, color=charts.TEXT_PRIMARY)
    named.append(name)

# Set the axis limits and the y ticks every 2
ax.set_ylim(*Y_LIMITS)
ax.set_xlim(*X_LIMITS)
ax.yaxis.set_major_locator(MultipleLocator(Y_STEP))

# Name the groups, their density ranges and their counts on the x ticks, and title the y axis
ax.set_xticks(POSITIONS, labels=[TICKS[g].format(lo=f"{ranges[g][0]:,.0f}", hi=f"{ranges[g][1]:,.0f}", n=ranges[g][2])
                                 for g in GROUPS])
ax.tick_params(axis="x", labelsize=TICK_SIZE, labelcolor=charts.TEXT_PRIMARY, pad=8)
ax.set_ylabel(YLABEL, fontsize=AXIS_TITLE_SIZE, color=charts.TEXT_SECONDARY, labelpad=10)

# Label the gap between the groups' medians above the top of the y axis, centred over the two boxes
ax.annotate(GAP_TEXT.format(gap=signed(gap)), (sum(POSITIONS) / len(POSITIONS), Y_LIMITS[1]), xytext=(0, GAP_OFFSET),
            textcoords="offset points", ha="center", va="bottom", fontsize=GAP_SIZE, fontweight="bold",
            color=charts.TEXT_PRIMARY, zorder=5, annotation_clip=False)

# Add the title, with the groups named on the x axis and no legend, and save the chart
charts.finish(fig, TITLE, [], OUT_PNG, left=TEXT_LEFT)

# Write the table, one row per province, group first, then sex ratio
df[["unit", "province", "density_per_km2", "group", "sex_ratio"]].to_csv(
    OUT_CSV, index=False, encoding="utf-8", lineterminator="\n")

# Report each group's density range, median, box and whiskers, the named provinces and the gap
for g in GROUPS:
    lo, hi, n = ranges[g]
    b = boxes[g]
    print(f"{g}: {lo:,.0f}-{hi:,.0f} people per km2, {n} provinces; median {medians[g]:.2f}, box {b['q1']:.2f}-"
          f"{b['q3']:.2f}, whiskers {b['low']:.2f}-{b['high']:.2f}, beyond: {len(b['outliers'])}")
print("Named:", ", ".join(named))
print(f"Sparse minus rest: {gap:+.2f} (label {signed(gap)})")
