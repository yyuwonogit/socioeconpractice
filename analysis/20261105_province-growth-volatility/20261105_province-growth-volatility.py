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
from matplotlib.ticker import FixedLocator
import numpy as np
import pandas as pd
from scipy.stats import gaussian_kde

# Parameters

# Quarterly GRDP by industry at constant 2010 prices, BPS WebAPI var 2267 '[Seri 2010] PDRB Triwulanan Atas Dasar Harga
# Konstan Menurut Lapangan Usaha di Provinsi Seluruh Indonesia', sector TOTAL (PDRB), in Rp billion with 2 decimals.
# BPS marks the 2024 quarters preliminary (status *) and the 2025 quarters very preliminary (**); the chart shows no
# marker. Growth = value / value of the same quarter a year earlier - 1, in %, for 2011Q1-2025Q4
DATASET = ROOT / ("data/20261103_bps-province-grdp-by-industry-2010-2025/"
                  "20261103_bps-province-grdp-by-industry-2010-2025.csv")
INDICATOR, SECTOR = "grdp_constant_2010", "TOTAL"
GROWTH_FIRST, GROWTH_LAST = "2011Q1", "2025Q4"

# 34 areas, each on one border for the whole series. Kalimantan Utara (65) has its own values from 2010 in these tables,
# so 64 and 65 are fixed areas. 91 (Papua Barat) and 94 (Papua) cover the pre-split areas to 2023Q4, and 92, 95, 96
# and 97 start in 2024Q1 (dataset metadata 'borders'), so the old areas are rebuilt from 2024Q1 by summing levels and
# no growth rate spans a border change. Keys are the panel's pre-split unit codes:
# {area: (codes summed, first quarter of the sum, chart name)}
OLD_BORDERS = {
    "91+92": (["91", "92"], "2024Q1", "Papua Barat (old borders)"),
    "94+95+96+97": (["94", "95", "96", "97"], "2024Q1", "Papua (old borders)"),
}
AREA_COUNT = 34

# Groups: each area's mean extractive share (province_panel.SHARP_SHARE, % of GRDP at current prices) over 2015-2025
# from the harmonised panel; the old-border Papua areas take their pre-split units, whose shares cover 2015-2023.
# High extraction = mean strictly above the median of the 34 areas (province_panel.above_median), low = the rest
SHARE_FIRST, SHARE_LAST = province_panel.SHARP_FIRST_YEAR, 2025
GROUPS = {
    "high": {"color": charts.SERIES, "tick": "High extraction",
             "legend": "Extractive share above the median, 2015–2025 average"},
    "low": {"color": charts.TEXT_MUTED, "tick": "Low extraction",
            "legend": "Extractive share below the median, 2015–2025 average"},
}

# Violins: x positions, share of the group colour in the light fill, outline width, grid points of the density, and
# the half-width in x units of the tallest density; both violins share one scale, so equal areas mean equal counts.
# Bandwidth: Silverman's robust rule of thumb, 0.9 * min(SD, IQR / 1.34) * n^(-1/5), so the heavy tails do not smooth
# away the centre
POSITIONS = {"high": 0.0, "low": 1.0}
FILL_SHARE, OUTLINE = 0.22, 1.0
POINTS = 1200
MAX_HALF_WIDTH = 0.36

# Marks inside each violin: median solid, quartiles dashed, as line widths in points
MEDIAN_WIDTH, QUARTILE_WIDTH = 1.8, 1.0
QUARTILE_DASH = (0, (3, 2))

# Figure: size in inches at 200 dpi, plot margins as figure fractions, the x range, the y room beyond the lowest and
# highest quarter in growth points, and the y tick step
FIGSIZE, DPI = (11, 8.4), 200
MARGINS = {"left": 0.09, "right": 0.98, "top": 0.875, "bottom": 0.1}
XLIM = (-0.5, 1.8)
YPAD, YSTEP = 3, 10

# Texts
TITLE = "Quarterly real GRDP growth in high- and low-extraction provinces, 2011–2025"
YLABEL = "Real GRDP growth on the same quarter a year earlier, %"
LABEL_SIZE = 8.5

# Outputs
OUT_PNG = HERE / "20261105_quarterly-growth-violins.png"
OUT_CSV = HERE / "20261105_quarterly-growth.csv"

# Functions

def read_dataset(path):
    """Read a long dataset with every column as text, so codes and empty statuses survive, and turn values to numbers."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df["value"] = df["value"].astype(float)
    return df


def quarter_key(period):
    """Return a running quarter number for a YYYYQn period, so the same quarter a year earlier is 4 less."""
    return int(period[:4]) * 4 + int(period[5]) - 1


def area_levels(wide, fixed, old_borders):
    """Return one row per area and quarter with its level: a fixed area's own column, and an old-border area's first
    code until the split and the sum of its codes from then on, stopping when a code is missing in a summed quarter."""
    parts = {code: wide[code] for code in fixed}
    for area, (codes, start, _) in old_borders.items():
        level = wide[codes[0]].copy()
        later = wide.index >= start
        summed = wide.loc[later, codes].sum(axis=1, min_count=len(codes))
        if summed.isna().any():
            raise ValueError(f"{area}: a code is missing in a quarter from {start}")
        level[later] = summed.round(2)
        parts[area] = level
    long = pd.DataFrame(parts).rename_axis("period").reset_index().melt(
        id_vars="period", var_name="area", value_name="grdp_constant_2010_bn")
    return long.dropna(subset=["grdp_constant_2010_bn"])


def add_growth(levels):
    """Add growth on the same quarter a year earlier, in %, matched by quarter number so no gap is bridged."""
    levels = levels.copy()
    levels["key"] = levels["period"].map(quarter_key)
    earlier = levels[["area", "key", "grdp_constant_2010_bn"]].rename(columns={"grdp_constant_2010_bn": "earlier"})
    earlier["key"] += 4
    out = levels.merge(earlier, on=["area", "key"], how="left")
    out["growth_pct"] = ((out["grdp_constant_2010_bn"] / out["earlier"] - 1) * 100).round(6)
    return out.drop(columns=["key", "earlier"])


def tint(color, share):
    """Return a colour mixed with the surface colour, share of it being the colour, as a solid hex."""
    c, s = np.array(to_rgb(color)), np.array(to_rgb(charts.SURFACE))
    return to_hex(share * c + (1 - share) * s)


def density(values):
    """Return a Gaussian density of the values with Silverman's robust bandwidth."""
    sd = values.std(ddof=1)
    q1, q3 = np.percentile(values, [25, 75])
    h = 0.9 * min(sd, (q3 - q1) / 1.34) * len(values) ** -0.2
    return gaussian_kde(values, bw_method=h / sd)


def minus(text):
    """Write the minus signs of a number as the typographic minus."""
    return text.replace("-", "−")


# Steps

# Build the harmonised panel, with all its checks, for each area's extractive share
b = province_panel.build()

# Read the quarterly GRDP at constant 2010 prices, sector TOTAL, as one column per province code
data = read_dataset(DATASET)
rows = data[(data["indicator"] == INDICATOR) & (data["sector"] == SECTOR) & data["period"].str.fullmatch(r"\d{4}Q[1-4]")]
wide = rows.pivot(index="period", columns="province_code", values="value").sort_index()

# The areas: every province on fixed borders, then the two old-border Papua areas
split_codes = {c for codes, _, _ in OLD_BORDERS.values() for c in codes}
fixed = sorted(c for c in wide.columns if c not in split_codes)
areas = fixed + list(OLD_BORDERS)
if len(areas) != AREA_COUNT:
    raise ValueError(f"expected {AREA_COUNT} areas, found {len(areas)}")
names = {c: charts.display_name(b.names[c]) for c in fixed} | {a: v[2] for a, v in OLD_BORDERS.items()}

# Levels on each area's fixed borders and growth on the same quarter a year earlier
table = add_growth(area_levels(wide, fixed, OLD_BORDERS))

# Split the areas at the median of their mean extractive share over 2015-2025
years = b.panel[(b.panel["year"] >= SHARE_FIRST) & (b.panel["year"] <= SHARE_LAST) & b.panel["unit"].isin(areas)]
mean_share = years.groupby("unit")[province_panel.SHARP_SHARE].mean().reindex(areas)
if mean_share.isna().any():
    raise ValueError(f"no extractive share for {mean_share[mean_share.isna()].index.tolist()}")
group = province_panel.above_median(mean_share).map({True: "high", False: "low"})
print("median of mean shares:", round(mean_share.median(), 3), "| areas per group:", group.value_counts().to_dict())

# Lay the table out: area, name, group, quarter, level and growth, high group first, then by area and quarter
table["area_name"] = table["area"].map(names)
table["group"] = table["area"].map(group)
table["order"] = table["group"].map({g: i for i, g in enumerate(GROUPS)})
table = table.sort_values(["order", "area", "period"]).reset_index(drop=True)
table = table[["area", "area_name", "group", "period", "grdp_constant_2010_bn", "growth_pct"]]

# The growth rates each violin pools, 2011Q1-2025Q4
growth = table[(table["period"] >= GROWTH_FIRST) & (table["period"] <= GROWTH_LAST)].dropna(subset=["growth_pct"])

# Each group's spread, quartiles, 5th percentile and deepest quarter
stats = {}
for g in GROUPS:
    part = growth[growth["group"] == g]
    v = part["growth_pct"].to_numpy()
    q1, median, q3, p5 = np.percentile(v, [25, 50, 75, 5])
    low = part.loc[part["growth_pct"].idxmin()]
    stats[g] = {"values": v, "n": len(v), "areas": part["area"].nunique(), "sd": v.std(ddof=1), "q1": q1,
                "median": median, "q3": q3, "iqr": q3 - q1, "p5": p5, "deepest": low}
    print(f"{g}: n={len(v)} areas={part['area'].nunique()} sd={v.std(ddof=1):.2f} iqr={q3 - q1:.2f} "
          f"p5={p5:.2f} median={median:.2f} q1={q1:.2f} q3={q3:.2f} min={v.min():.2f} max={v.max():.2f} | deepest "
          f"{low['area_name']} {low['period']} {low['growth_pct']:.2f}")

# One density per group on a grid from its lowest to its highest quarter, on one shared width scale
shapes = {}
for g in GROUPS:
    v = stats[g]["values"]
    kde = density(v)
    grid = np.linspace(v.min(), v.max(), POINTS)
    shapes[g] = (kde, grid, kde(grid))
scale = MAX_HALF_WIDTH / max(d.max() for _, _, d in shapes.values())

# Figure and axes, styled as the shared charts, with the grid across only
fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
fig.patch.set_facecolor(charts.SURFACE)
fig.subplots_adjust(**MARGINS)
charts.style_axes(ax)
ax.xaxis.grid(False)
ax.set_axisbelow(True)

# A thin line at 0 beneath the violins
ax.axhline(0, color=charts.CUT, lw=0.9, zorder=1)

for g, style in GROUPS.items():
    kde, grid, dens = shapes[g]
    s, x, color = stats[g], POSITIONS[g], style["color"]
    # The violin in a light fill of the group colour, outlined in the colour
    ax.fill_betweenx(grid, x - dens * scale, x + dens * scale, facecolor=tint(color, FILL_SHARE), edgecolor=color,
                     linewidth=OUTLINE, zorder=2)
    # Median and quartiles as lines across the violin
    for q, width, dash in [(s["q1"], QUARTILE_WIDTH, QUARTILE_DASH), (s["median"], MEDIAN_WIDTH, "solid"),
                           (s["q3"], QUARTILE_WIDTH, QUARTILE_DASH)]:
        half = kde(q)[0] * scale
        ax.plot([x - half, x + half], [q, q], color=color, lw=width, linestyle=dash, solid_capstyle="butt", zorder=3)
    # The median and quartiles as values beside the violin's widest part
    widest = dens.max() * scale
    ax.annotate(minus(f"Median {s['median']:.1f}%\nQuartiles {s['q1']:.1f}% to {s['q3']:.1f}%"),
                (x + widest, s["median"]), xytext=(8, 0), textcoords="offset points", ha="left", va="center",
                fontsize=LABEL_SIZE, color=charts.TEXT_SECONDARY, linespacing=1.3)
    # The deepest quarter as a point, named beside it
    low = s["deepest"]
    ax.scatter([x], [low["growth_pct"]], zorder=4, **charts.point_marks({"color": color}, charts.POINT_SIZE))
    ax.annotate(minus(f"{low['area_name']} {low['period']}, {low['growth_pct']:.1f}%"), (x, low["growth_pct"]),
                xytext=(8, 0), textcoords="offset points", ha="left", va="center", fontsize=LABEL_SIZE,
                color=charts.TEXT_PRIMARY)

# Axes: the groups as x tick labels with their counts, the y range YPAD points beyond the data, ticks every YSTEP
ax.set_xlim(*XLIM)
ax.set_xticks(list(POSITIONS.values()))
ax.set_xticklabels([f"{GROUPS[g]['tick']}\n{stats[g]['areas']} provinces, {stats[g]['n']:,} quarters"
                    for g in POSITIONS], fontsize=10, color=charts.TEXT_PRIMARY, linespacing=1.4)
low_y = min(s["values"].min() for s in stats.values())
high_y = max(s["values"].max() for s in stats.values())
ylim = (low_y - YPAD, high_y + YPAD)
ax.set_ylim(*ylim)
ticks = np.arange(np.ceil(ylim[0] / YSTEP) * YSTEP, ylim[1] + 0.001, YSTEP)
ax.yaxis.set_major_locator(FixedLocator(ticks))
ax.set_yticklabels([minus(f"{t:.0f}") for t in ticks])
ax.set_ylabel(YLABEL, color=charts.TEXT_SECONDARY, fontsize=10)

# Title and legend, then save the PNG
handles = [Patch(facecolor=tint(s["color"], FILL_SHARE), edgecolor=s["color"], linewidth=OUTLINE, label=s["legend"])
           for s in GROUPS.values()]
charts.finish(fig, TITLE, handles, OUT_PNG, left=0.02)

# Write every level and growth rate behind the chart; the 2010 quarters carry the levels the 2011 growth rates start from
table.to_csv(OUT_CSV, index=False, encoding="utf-8", lineterminator="\n")
print("wrote", OUT_PNG.name, "and", OUT_CSV.name, len(table), "rows")
