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
from matplotlib.ticker import FixedLocator, NullLocator
import pandas as pd
from scipy import stats

# Parameters

# Inputs: BPS's open unemployment rate by province (Sakernas, WebAPI var 543) and GRDP per capita at constant 2010
# prices (WebAPI var 288, Rp thousand per person), both in data/, with the unemployment metadata naming each province
UNEMP_DIR = ROOT / "data" / "20261105_bps-province-unemployment-rate"
UNEMP_CSV = UNEMP_DIR / "20261105_bps-province-unemployment-rate.csv"
UNEMP_META = UNEMP_DIR / "20261105_bps-province-unemployment-rate-metadata.json"
GRDP_CSV = ROOT / "data" / "20261103_bps-province-grdp-2010-2025" / "20261103_bps-province-grdp-2010-2025.csv"

# The August 2025 Sakernas round, GRDP per capita in 2025, Indonesia's row and the 38 provinces
ROUND, YEAR = "2025S2", "2025"
GRDP_PC = "grdp_per_capita_constant_2010"
NATIONAL, PROVINCES = "00", 38
THOUSAND = 1000

# Outputs, beside this script
OUT_PNG = HERE / "20261105_unemployment-vs-grdp.png"
OUT_CSV = HERE / "20261105_unemployment-vs-grdp.csv"

# Texts: title, axis titles, cut-line labels at Indonesia's values, the quadrant names by (more unemployed, richer)
# and the statistic label
TITLE = "GRDP per capita against the open unemployment rate, Indonesian provinces, 2025"
XLABEL = "Open unemployment rate, % of the labour force, August 2025"
YLABEL = "GRDP per capita, Rp million at constant 2010 prices, 2025, log scale"
XCUT_TEXT = "Indonesia {:.2f}%"
YCUT_TEXT = "Indonesia Rp {:.0f} million"
QUADRANTS = {(True, True): "Richer, more unemployed", (False, True): "Richer, fewer unemployed",
             (True, False): "Poorer, more unemployed", (False, False): "Poorer, fewer unemployed"}
STAT_TEXT = "Spearman ρ {r:.2f}"

# Axes: room in percentage points left and right of the points, a factor of headroom on the log y axis, and the plain
# y ticks shown where they fall inside it
X_PAD = 0.45
Y_FACTOR = 1.25
Y_TICKS = [10, 15, 20, 30, 50, 75, 100, 150, 200, 300]

# Text sizes of the province names, quadrant names, cut-line labels and statistic label
LABEL_SIZE, QUAD_SIZE, CUT_SIZE, STAT_SIZE = 8, 11, 8, 9.5

# Figure: a full 16:9 slide (charts.SLIDE_SIZE, in inches) at 200 dpi, the axes margins as figure fractions, and
# where the title starts
FIGSIZE, DPI = charts.SLIDE_SIZE, 200
MARGINS = {"left": 0.07, "right": 0.98, "top": 0.9, "bottom": 0.09}
TEXT_LEFT = 0.07


# Steps

# Read the August 2025 unemployment rates, Indonesia's apart from the 38 provinces'
unemp = pd.read_csv(UNEMP_CSV, dtype=str, keep_default_na=False)
unemp = unemp[unemp["period"] == ROUND].set_index("province_code")["value"].astype(float)

# Read 2025 GRDP per capita at constant 2010 prices, in Rp million
grdp = pd.read_csv(GRDP_CSV, dtype=str, keep_default_na=False)
grdp = grdp[(grdp["indicator"] == GRDP_PC) & (grdp["period"] == YEAR)].set_index("province_code")["value"]
grdp = grdp.astype(float) / THOUSAND

# Join the two for the provinces, each named from the metadata in display case; every province needs both values
meta = json.loads(UNEMP_META.read_text(encoding="utf-8"))
codes = sorted(c for c in unemp.index if c != NATIONAL)
df = pd.DataFrame({"unit": codes, "unemployment_rate_pct": unemp[codes].to_numpy(),
                   "grdp_pc_m": grdp.reindex(codes).to_numpy()})
df["province"] = df["unit"].map(lambda c: charts.display_name(meta["provinces"][c]["name"]))
assert len(df) == PROVINCES and df.notna().all().all(), f"{ROUND}: not both values for each of the 38 provinces"
xcut, ycut = unemp[NATIONAL], grdp[NATIONAL]

# Place each province in its quadrant against Indonesia's two values, and rank-correlate the two measures
df["quadrant"] = [QUADRANTS[(x > xcut, y > ycut)] for x, y in zip(df["unemployment_rate_pct"], df["grdp_pc_m"])]
rho = stats.spearmanr(df["unemployment_rate_pct"], df["grdp_pc_m"])

# Draw the axes in the shared style on a log y axis with plain-number ticks
fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
fig.patch.set_facecolor(charts.SURFACE)
fig.subplots_adjust(**MARGINS)
charts.style_axes(ax)
ax.set_yscale("log")
ax.set_xlim(df["unemployment_rate_pct"].min() - X_PAD, df["unemployment_rate_pct"].max() + X_PAD)
ylim = (df["grdp_pc_m"].min() / Y_FACTOR, df["grdp_pc_m"].max() * Y_FACTOR)
ax.set_ylim(*ylim)
ticks = [t for t in Y_TICKS if ylim[0] <= t <= ylim[1]]
ax.yaxis.set_major_locator(FixedLocator(ticks))
ax.yaxis.set_minor_locator(NullLocator())
ax.set_yticklabels([str(t) for t in ticks])
ax.set_xlabel(XLABEL, color=charts.TEXT_SECONDARY, fontsize=10)
ax.set_ylabel(YLABEL, color=charts.TEXT_SECONDARY, fontsize=10)

# Draw the cut lines at Indonesia's values with their labels, then the provinces as filled points with surface rings
ax.axvline(xcut, color=charts.CUT, lw=1, zorder=1)
ax.axhline(ycut, color=charts.CUT, lw=1, zorder=1)
texts = [ax.annotate(XCUT_TEXT.format(xcut), (xcut, 0), xycoords=("data", "axes fraction"), xytext=(4, 4),
                     textcoords="offset points", fontsize=CUT_SIZE, color=charts.TEXT_MUTED),
         ax.annotate(YCUT_TEXT.format(ycut), (0, ycut), xycoords=("axes fraction", "data"), xytext=(4, 4),
                     textcoords="offset points", ha="left", fontsize=CUT_SIZE, color=charts.TEXT_MUTED)]
ax.scatter(df["unemployment_rate_pct"], df["grdp_pc_m"], zorder=3, **charts.point_marks({}, charts.POINT_SIZE))

# Name each quadrant in its outer corner, and put the rank correlation under the top-left name
for (right, top), name in QUADRANTS.items():
    texts.append(ax.text(0.99 if right else 0.01, 0.98 if top else 0.02, name, transform=ax.transAxes,
                         ha="right" if right else "left", va="top" if top else "bottom", fontsize=QUAD_SIZE,
                         fontweight="bold", color=charts.TEXT_SECONDARY))
texts.append(ax.text(0.01, 0.935, STAT_TEXT.format(r=rho.statistic), transform=ax.transAxes, ha="left", va="top",
                     fontsize=STAT_SIZE, color=charts.TEXT_SECONDARY))

# Name every province, each name kept inside its point's quadrant and clear of the text drawn above
fig.canvas.draw()
renderer = fig.canvas.get_renderer()
avoid = [charts.box_of(t, renderer, pad=2) for t in texts]
charts.place_labels(ax, df["unemployment_rate_pct"].tolist(), df["grdp_pc_m"].tolist(), df["province"].tolist(),
                    fontsize=LABEL_SIZE, avoid=avoid, cuts=(xcut, ycut), halo=True)

# Add the title and save the chart
charts.finish(fig, TITLE, [], OUT_PNG, left=TEXT_LEFT)

# Write every plotted value, and report the correlation, the quadrant counts and the extremes
df[["unit", "province", "unemployment_rate_pct", "grdp_pc_m", "quadrant"]].to_csv(
    OUT_CSV, index=False, encoding="utf-8", lineterminator="\n")
print(f"Indonesia {xcut:.2f}% unemployed, GRDP per capita Rp {ycut:.1f} million")
print(f"Spearman rho {rho.statistic:.3f} (p {rho.pvalue:.3g}); quadrants {df['quadrant'].value_counts().to_dict()}")
