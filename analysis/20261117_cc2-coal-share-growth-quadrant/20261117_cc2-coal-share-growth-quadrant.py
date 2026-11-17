from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

import sys

# Load the shared chart module from tools/
sys.path.insert(0, str(ROOT / "tools"))
import charts

from matplotlib.patches import Rectangle
from matplotlib.ticker import FixedLocator, NullLocator
import pandas as pd

# Parameters

# Dataset read; analysis scripts read data/ only
DATASET = ROOT / "data/20261116_bps-province-grdp-by-industry-2021-2025/20261116_bps-province-grdp-by-industry-2021-2025.csv"
METADATA = ROOT / "data/20261116_bps-province-grdp-by-industry-2021-2025/20261116_bps-province-grdp-by-industry-2021-2025-metadata.json"

OUT_PNG = HERE / "20261117_cc2-coal-share-growth-quadrant.png"
OUT_CSV = HERE / "20261117_cc2-coal-share-growth-quadrant.csv"

# CC2 C is the coal share in the share year; CC2 D is the average annual real growth from the first to the last year
SHARE_YEAR, FIRST_YEAR, LAST_YEAR = "2025", "2021", "2025"

# Plot window: coal share (log scale, %) and growth (% per year); points beyond it sit on the edge with their values
XLIM, YLIM = (0.01, 150), (-12, 16)
XTICKS = [0.01, 0.1, 0.5, 1, 2, 5, 10, 25]

# Quadrant names, keyed by (share at or above the cut, growth at or above the cut)
QUADRANTS = {(True, True): "Large and growing: most vulnerable",
             (True, False): "Large, growing slower",
             (False, True): "Small, growing fast: emerging dependence",
             (False, False): "Small, growing slower or shrinking"}

# Light shade behind the most vulnerable quadrant
VULNERABLE_SHADE = "#f3e3d9"

# Functions

def load():
    """Read the GRDP dataset with codes and periods as text, and the province names from its metadata."""
    df = pd.read_csv(DATASET, dtype={"province_code": str, "sector": str, "period": str, "status": str}, keep_default_na=False)
    return df, charts.province_names(METADATA)


def series(df, indicator, sector):
    """Return province rows by period columns for one indicator and sector."""
    part = df[(df["indicator"] == indicator) & (df["sector"] == sector)]
    return part.pivot(index="province_code", columns="period", values="value")


def fmt_share(v):
    """Write a coal share with enough decimals to stay non-zero."""
    return f"{v:.1f}%" if v >= 1 else f"{v:.2f}%" if v >= 0.01 else f"{v:.4f}%"


def quadrant_chart(table, x_cut, y_cut):
    """Scatter coal share (log) against coal CAGR, with Indonesia cut lines, named quadrants and every province labelled."""
    fig, ax = charts.new_figure(14, 10)
    ax.set_xscale("log")
    ax.set_xlim(*XLIM)
    ax.set_ylim(*YLIM)

    # Shade the most vulnerable quadrant, then draw the cut lines
    ax.add_patch(Rectangle((x_cut, y_cut), XLIM[1] - x_cut, YLIM[1] - y_cut, color=VULNERABLE_SHADE, zorder=0, lw=0))
    ax.axvline(x_cut, color=charts.CUT, lw=1, zorder=1)
    ax.axhline(y_cut, color=charts.CUT, lw=1, zorder=1)

    # Points inside the window are dots; a point beyond it sits on the edge as a triangle, labelled with its values
    inside = table[(table["share"] >= XLIM[0]) & table["cagr"].between(*YLIM)]
    outside = table.drop(inside.index)
    sizes = [60] * len(inside)
    ax.scatter(inside["share"], inside["cagr"], s=sizes, color=charts.SERIES[0], edgecolor=charts.SURFACE, linewidth=2, zorder=3)
    for r in outside.itertuples():
        x = min(max(r.share, XLIM[0] * 1.08), XLIM[1] / 1.08)
        y = min(max(r.cagr, YLIM[0] + 0.5), YLIM[1] - 0.5)
        ax.scatter(x, y, s=80, marker="v" if r.cagr < YLIM[0] else "^", color=charts.SERIES[0],
                   edgecolor=charts.SURFACE, linewidth=2, zorder=3, clip_on=False)
        ax.annotate(f"{r.province} (share {fmt_share(r.share)}, {r.cagr:+.1f}% a year, off scale)", (x, y),
                    xytext=(10, 4), textcoords="offset points", ha="left", va="bottom", fontsize=8, color=charts.TEXT_PRIMARY)

    # Name each quadrant in its outer corner
    for (right, top), name in QUADRANTS.items():
        ax.text(0.99 if right else 0.01, 0.98 if top else 0.06, name, transform=ax.transAxes,
                ha="right" if right else "left", va="top" if top else "bottom",
                fontsize=11, fontweight="bold", color=charts.TEXT_SECONDARY)

    # Label the cut lines with the Indonesia values
    ax.annotate(f"Indonesia {x_cut:.1f}%", (x_cut, 0), xycoords=("data", "axes fraction"), xytext=(4, 4),
                textcoords="offset points", fontsize=8, color=charts.TEXT_MUTED)
    ax.annotate(f"Indonesia {y_cut:+.1f}% a year", (1, y_cut), xycoords=("axes fraction", "data"), xytext=(-4, 4),
                textcoords="offset points", ha="right", fontsize=8, color=charts.TEXT_MUTED)

    # Readable ticks on the log axis, recessive axes and grid
    ax.xaxis.set_major_locator(FixedLocator(XTICKS))
    ax.xaxis.set_minor_locator(NullLocator())
    ax.set_xticklabels([f"{v:g}%" for v in XTICKS])
    charts.style_axes(ax, f"Coal mining (B2) share of GRDP, {SHARE_YEAR}, current prices (CC2 C, log scale)",
                      f"Coal mining real growth, average per year {FIRST_YEAR}-{LAST_YEAR} (CC2 D, %)")

    # Label every province in the window with its name
    charts.place_labels(ax, inside["share"].tolist(), inside["cagr"].tolist(), inside["province"].tolist(), fontsize=8.5, sizes=sizes)

    charts.finish(
        fig,
        title="Coal dependence and its direction: coal-producing provinces",
        subtitle=f"Coal's share of GRDP ({SHARE_YEAR}) against the coal sector's own real growth ({FIRST_YEAR}-{LAST_YEAR}); lines mark the Indonesia-wide values",
        note=("Source: BPS, PDRB Provinsi-Provinsi di Indonesia Menurut Lapangan Usaha 2021-2025; repo dataset 20261116_bps-province-grdp-by-industry-2021-2025. "
              "Growth is the compound annual growth of coal mining GRDP at constant 2010 prices, ((2025/2021)^(1/4) - 1) x 100; it compares the coal sector with itself. "
              "Share is coal mining GRDP divided by total GRDP at current prices. Indonesia values sum the provinces. "
              f"Only the {len(table)} provinces with coal output in both {FIRST_YEAR} and {LAST_YEAR} are shown; the others have no CC2 D value. "
              "2024 values are preliminary (*) and 2025 very preliminary (**). Small coal sectors swing widely because BPS rounds to whole Rp billions."),
        path=OUT_PNG,
    )


# Steps

# Read the dataset and the province names
df, names = load()

# CC2 C: coal mining share of GRDP at current prices in the share year
current_coal, current_total = series(df, "grdp_current", "B2"), series(df, "grdp_current", "TOTAL")
share = current_coal[SHARE_YEAR] / current_total[SHARE_YEAR] * 100

# CC2 D: compound average annual real growth of coal mining at constant prices, first to last year
constant_coal = series(df, "grdp_constant", "B2")
years = int(LAST_YEAR) - int(FIRST_YEAR)
cagr = ((constant_coal[LAST_YEAR] / constant_coal[FIRST_YEAR]) ** (1 / years) - 1) * 100

# Keep the provinces that have both values
table = pd.DataFrame({"share": share, "cagr": cagr,
                      f"coal_grdp_constant_{FIRST_YEAR}": constant_coal[FIRST_YEAR],
                      f"coal_grdp_constant_{LAST_YEAR}": constant_coal[LAST_YEAR]}).dropna(subset=["share", "cagr"])
table.index.name = "province_code"
table.insert(0, "province", [names[c] for c in table.index])

# Cut at the Indonesia values: provinces summed, for the share and for the growth
x_cut = current_coal[SHARE_YEAR].sum() / current_total[SHARE_YEAR].sum() * 100
y_cut = ((constant_coal[LAST_YEAR].sum() / constant_coal[FIRST_YEAR].sum()) ** (1 / years) - 1) * 100
table["quadrant"] = [QUADRANTS[(s >= x_cut, g >= y_cut)] for s, g in zip(table["share"], table["cagr"])]

# Write the table behind the chart, most vulnerable quadrant first
order = {name: i for i, name in enumerate(QUADRANTS.values())}
out = table.sort_values(["quadrant", "share"], key=lambda c: c.map(order) if c.name == "quadrant" else -c)
out = out.rename(columns={"share": f"coal_share_{SHARE_YEAR}_pct", "cagr": f"coal_real_cagr_{FIRST_YEAR}_{LAST_YEAR}_pct"})
out.reset_index().to_csv(OUT_CSV, index=False, float_format="%.4f", lineterminator="\n")

# Draw the chart
quadrant_chart(table, x_cut, y_cut)
print(f"Indonesia cut: share {x_cut:.2f}%, growth {y_cut:.2f}% a year")
print(out.reset_index()[["province", out.columns[1], out.columns[2], "quadrant"]].to_string(index=False))
