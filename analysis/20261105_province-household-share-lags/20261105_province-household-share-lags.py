from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# Load the shared chart and panel modules from tools/
import sys
sys.path.insert(0, str(ROOT / "tools"))
import charts
import province_panel

import math

import matplotlib.pyplot as plt
from matplotlib import patheffects
from matplotlib.ticker import FixedLocator, FuncFormatter
import numpy as np
import pandas as pd

# Parameters

# Panel columns, both at current prices and in %, from province_panel.build():
# - the extractive share (sharpened definition): fossil, metals, plantation, forest and quarrying as a share of GRDP,
#   from the BPS SIMDASI yearbook tables of GRDP by detailed industry;
# - the household share: household consumption (PKRT) as a share of GRDP by expenditure = PKRT / PDRB x 100, BPS
#   WebAPI var 534.
# Changes are in percentage points between consecutive years of one panel unit. A pre-split unit (91+92 and
# 94+95+96+97, 2010-2023) and the provinces it split into (from 2024) are different units, so no change spans the split
# and 2024 has no Papua change; 64+65 ends in 2014, before the sample.
SHARE = province_panel.SHARP_SHARE
PKRT = "pkrt_share_pct"

# Sample: panel rows from the first year with the sharpened share to the panel's last year
FIRST_YEAR, LAST_YEAR = province_panel.SHARP_FIRST_YEAR, 2025

# Lags k in years: the change in extractive share in year t pairs with the change in household share in year t + k of
# the same unit. Before pairing, each year's mean change across the units with a change that year is taken out of both
# series, as the year effects of the panel tests do; first differences already take out each unit's level.
# r is the Pearson correlation of the year-demeaned changes over the pairs a series keeps
LAGS = [0, 1, 2, 3]

# Series in legend order: label, which pairs it keeps by the sign of the raw change in extractive share in year t
# (before year demeaning; None keeps every pair), colour, marker, offset from the lag on the x axis, and whether its
# points carry their r. Each subset takes a muted ink tone, and its triangle points the way extraction moved
SERIES = [
    {"label": "All years", "sign": None, "color": charts.SERIES, "marker": "o", "dodge": 0.0, "labelled": True},
    {"label": "Years extraction rose", "sign": 1, "color": charts.TEXT_SECONDARY, "marker": "^", "dodge": -0.2,
     "labelled": False},
    {"label": "Years extraction fell", "sign": -1, "color": charts.TEXT_MUTED, "marker": "v", "dodge": 0.2,
     "labelled": False},
]

# 95% bands: a cluster bootstrap by unit, drawing units with replacement; each resample reruns the year demeaning,
# pairing and correlation on its units (a unit drawn twice counts twice), and the same resamples serve every lag and
# series. Bands are percentile intervals
RESAMPLES, SEED, BAND = 2000, 20261105, (2.5, 97.5)

# Decimals of r and its band in the table
DECIMALS = 4

# Figure size in inches and its resolution
FIGSIZE, DPI = (14, 6.4), 200

# Plot edges as figure fractions, and where the title and legend start
LEFT, RIGHT, TOP, BOTTOM, TITLE_LEFT = 0.07, 0.985, 0.87, 0.11, 0.025

# x axis range; y axis tick step, and the margin kept between the bands and the y axis ends
XLIM, YSTEP, YMARGIN = (-0.5, 3.5), 0.1, 0.01

# Axis titles and their size in points
XLABEL = "Years after the change in extractive share"
YLABEL = "Correlation with the change in household consumption share"
AXIS_SIZE = 10

# Title
TITLE = "Change in household consumption share after a change in extractive share, within provinces, 2015–2025"

# Marker area of a circle in points squared, the width of the 95% bars and of the zero line in points
POINT_SIZE, BAR_LW, ZERO_LW = 60, 1.6, 1.0

# r labels: size in points and gap from the point's centre in points
LABEL_SIZE, LABEL_DX = 8.5, 7

# Outputs
OUT_PNG = HERE / "20261105_household-share-lags.png"
OUT_CSV = HERE / "20261105_household-share-lags.csv"

# Functions


def changes(panel):
    """Return each unit's changes in both shares between consecutive years, with the unit and the later year t."""
    p = panel.sort_values(["unit", "year"])
    prev = p.groupby("unit")[["year", SHARE, PKRT]].shift(1)
    keep = (p["year"] - prev["year"]) == 1
    return pd.DataFrame({"unit": p["unit"], "year": p["year"], "d_share": p[SHARE] - prev[SHARE],
                         "d_pkrt": p[PKRT] - prev[PKRT]})[keep].reset_index(drop=True)


def lag_pairs(ch):
    """Return {k: (a, b)}: the rows of ch whose d_share(t) pairs with the row holding d_pkrt(t + k) of the same unit."""
    row = {(u, t): i for i, (u, t) in enumerate(zip(ch["unit"], ch["year"]))}
    pairs = {}
    for k in LAGS:
        found = [(i, row[(u, t + k)]) for i, (u, t) in enumerate(zip(ch["unit"], ch["year"])) if (u, t + k) in row]
        pairs[k] = tuple(np.array(side) for side in zip(*found))
    return pairs


def keeps(raw_share, sign):
    """Return the pairs a series keeps, by the sign of the raw change in extractive share in year t."""
    return np.ones(len(raw_share), bool) if sign is None else np.sign(raw_share) == sign


def correlations(weights, unit_idx, year_idx, d_share, d_pkrt, pairs):
    """Return r for each row of weights, lag and series, as an array (resamples, lags, series).

    weights: (resamples, units), the times each unit is drawn; a row of ones is the sample itself. Each row takes out
    its own year means (a unit counting as often as it is drawn), pairs the changes, and takes the weighted Pearson
    correlation, which equals the plain one on the units repeated.
    """
    rw = weights[:, unit_idx]
    years = np.eye(year_idx.max() + 1)[year_idx]
    count = rw @ years
    share_dm = d_share - ((rw * d_share) @ years / count)[:, year_idx]
    pkrt_dm = d_pkrt - ((rw * d_pkrt) @ years / count)[:, year_idx]
    out = np.empty((len(weights), len(LAGS), len(SERIES)))
    for j, k in enumerate(LAGS):
        a, b = pairs[k]
        for s, series in enumerate(SERIES):
            w = rw[:, a] * keeps(d_share[a], series["sign"])
            total = w.sum(1, keepdims=True)
            x = share_dm[:, a] - (w * share_dm[:, a]).sum(1, keepdims=True) / total
            z = pkrt_dm[:, b] - (w * pkrt_dm[:, b]).sum(1, keepdims=True) / total
            out[:, j, s] = (w * x * z).sum(1) / np.sqrt((w * x * x).sum(1) * (w * z * z).sum(1))
    return out


def tick_text(value, _):
    """Write a tick value with one decimal and a true minus sign, and zero as 0."""
    return "0" if abs(value) < 1e-9 else f"{value:.1f}".replace("-", "−")


# Steps

# Build the harmonised panel with all its checks, and keep the sample years
b = province_panel.build()
panel = b.panel[b.panel["year"].between(FIRST_YEAR, LAST_YEAR)][["unit", "unit_name", "year", SHARE, PKRT]]
assert panel[[SHARE, PKRT]].notna().all().all(), "a sample row lacks a share"
above = panel[panel[PKRT] > 100]
print(f"sample rows with a household share above 100%: {len(above)} "
      f"({', '.join(f'{u} {y}' for u, y in zip(above['unit'], above['year']))})")

# Take each unit's changes between consecutive years, and index units and years
ch = changes(panel)
units, unit_idx = np.unique(ch["unit"].to_numpy(), return_inverse=True)
_, year_idx = np.unique(ch["year"].to_numpy(), return_inverse=True)
d_share, d_pkrt = ch["d_share"].to_numpy(float), ch["d_pkrt"].to_numpy(float)
print(f"{len(ch)} changes in {len(units)} units, {ch['year'].min()}-{ch['year'].max()}; "
      f"rose {int((d_share > 0).sum())}, fell {int((d_share < 0).sum())}, unchanged {int((d_share == 0).sum())}")

# Pair each change in extractive share with the household-share change k years later in the same unit
pairs = lag_pairs(ch)

# r on the sample itself
estimate = correlations(np.ones((1, len(units))), unit_idx, year_idx, d_share, d_pkrt, pairs)[0]

# Draw the bootstrap resamples of units once, and rerun the whole statistic on each
rng = np.random.default_rng(SEED)
draws = rng.integers(0, len(units), size=(RESAMPLES, len(units)))
weights = np.stack([np.bincount(row, minlength=len(units)) for row in draws]).astype(float)
boot = correlations(weights, unit_idx, year_idx, d_share, d_pkrt, pairs)
assert np.isfinite(boot).all(), "a resample gave no correlation"
low, high = np.percentile(boot, BAND, axis=0)

# Tabulate r, its band, and the pairs and units behind it, for every lag and series
rows = []
for j, k in enumerate(LAGS):
    a, b_rows = pairs[k]
    for s, series in enumerate(SERIES):
        keep = keeps(d_share[a], series["sign"])
        rows.append({"k": k, "series": series["label"], "r": round(float(estimate[j, s]), DECIMALS),
                     "low": round(float(low[j, s]), DECIMALS), "high": round(float(high[j, s]), DECIMALS),
                     "pairs": int(keep.sum()), "units": len(np.unique(unit_idx[a][keep]))})
table = pd.DataFrame(rows)
table.to_csv(OUT_CSV, index=False, encoding="utf-8", lineterminator="\n")
print(table.to_string(index=False))

# Draw the axes: recessive grid on y only, the zero line, the lag ticks and the axis titles
fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
fig.subplots_adjust(left=LEFT, right=RIGHT, top=TOP, bottom=BOTTOM)
charts.style_axes(ax)
ax.set_axisbelow(True)
ax.xaxis.grid(False)
ax.axhline(0, color=charts.CUT, lw=ZERO_LW, zorder=1)
ax.set_xlim(XLIM)
ax.xaxis.set_major_locator(FixedLocator(LAGS))
ax.set_xlabel(XLABEL, fontsize=AXIS_SIZE, color=charts.TEXT_SECONDARY, labelpad=8)
ax.set_ylabel(YLABEL, fontsize=AXIS_SIZE, color=charts.TEXT_SECONDARY, labelpad=8)

# Fit the y axis to the bands and zero, on whole tick steps
y0 = math.floor((min(table["low"].min(), 0) - YMARGIN) / YSTEP) * YSTEP
y1 = math.ceil((max(table["high"].max(), 0) + YMARGIN) / YSTEP) * YSTEP
ax.set_ylim(y0, y1)
ax.yaxis.set_major_locator(FixedLocator(np.round(np.arange(y0, y1 + YSTEP / 2, YSTEP), 10)))
ax.yaxis.set_major_formatter(FuncFormatter(tick_text))

# Draw each series as points with their 95% bars, dodged around each lag, and label the main series with its r
halo = [patheffects.withStroke(linewidth=charts.HALO, foreground=charts.SURFACE)]
handles = []
for series in SERIES:
    d = table[table["series"] == series["label"]]
    xs = d["k"] + series["dodge"]
    ax.vlines(xs, d["low"], d["high"], color=series["color"], lw=BAR_LW, zorder=2)
    size = POINT_SIZE * charts.EXTRACTIVE_MARKER_AREA[series["marker"]]
    ax.scatter(xs, d["r"], marker=series["marker"], zorder=3, **charts.point_marks({"color": series["color"]}, size))
    if series["labelled"]:
        for x, r in zip(xs, d["r"]):
            ax.annotate(f"{r:.2f}".replace("-", "−"), (x, r), xytext=(LABEL_DX, 0), textcoords="offset points",
                        ha="left", va="center", fontsize=LABEL_SIZE, color=series["color"], path_effects=halo,
                        zorder=4)
    # Name the series in the legend with its pairs at k = 0, its key drawn at the size of the points
    pairs_0 = int(d.loc[d["k"] == LAGS[0], "pairs"].iloc[0])
    key = charts.legend_key({"color": series["color"], "marker": series["marker"],
                             "label": f"{series['label']}, {pairs_0} pairs"}, series["label"])
    key.set_markersize(math.sqrt(size))
    handles.append(key)

# Add the title and legend and save the chart
charts.finish(fig, TITLE, handles, OUT_PNG, left=TITLE_LEFT)
