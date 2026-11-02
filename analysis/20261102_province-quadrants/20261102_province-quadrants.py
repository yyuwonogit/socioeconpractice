from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

import json
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FixedLocator, NullLocator
import pandas as pd

# Parameters

DATASET = ROOT / "data/20261102_bps-province-grdp-population/20261102_bps-province-grdp-population.csv"
METADATA = ROOT / "data/20261102_bps-province-grdp-population/20261102_bps-province-grdp-population-metadata.json"

OUT_WEALTH_PNG = HERE / "20261102_wealth-vs-momentum.png"
OUT_WEALTH_CSV = HERE / "20261102_wealth-vs-momentum.csv"

# Chart colours: one series on a light surface, text in ink tokens, recessive grid
SURFACE = "#fcfcfb"
SERIES = "#2a78d6"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
TEXT_MUTED = "#8a8985"
GRID = "#e4e3df"
CUT = "#9b9a96"

# Province names kept in capitals when the BPS upper-case name is title-cased
UPPER_WORDS = {"DKI", "DI"}

# Functions

def display_name(name):
    """Title-case a BPS province name, keeping abbreviations such as DKI and DI in capitals."""
    return " ".join(w if w in UPPER_WORDS else w.capitalize() for w in name.split())


def load():
    """Read the dataset and the province names from its metadata."""
    df = pd.read_csv(DATASET, dtype={"province_code": str, "sector": str, "period": str, "status": str},
                     keep_default_na=False)
    meta = json.loads(METADATA.read_text(encoding="utf-8"))
    names = {code: display_name(p["name"]) for code, p in meta["provinces"].items()}
    return df, names


def place_labels(ax, xs, ys, labels, fontsize=7.5):
    """Place one label per point, trying offsets around it and skipping any that overlap a placed label or point."""
    fig = ax.figure
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    pts = ax.transData.transform(list(zip(xs, ys)))
    placed = []
    # Points are obstacles too, as 10-pixel boxes
    obstacles = [(px - 5, py - 5, px + 5, py + 5) for px, py in pts]
    # Candidate offsets: eight directions at growing distances; past the first ring a leader line is drawn
    directions = [(1, 0, "left", "center"), (-1, 0, "right", "center"), (0, 1, "center", "bottom"),
                  (0, -1, "center", "top"), (1, 1, "left", "bottom"), (-1, 1, "right", "bottom"),
                  (1, -1, "left", "top"), (-1, -1, "right", "top")]
    offsets = [(dx * r, dy * r, ha, va) for r in (6, 14, 22, 30, 40) for dx, dy, ha, va in directions]
    # Label the points farthest from the crowd first, then fit the crowded ones around them
    order = sorted(range(len(labels)), key=lambda i: -min(
        [abs(pts[i][0] - pts[j][0]) + abs(pts[i][1] - pts[j][1]) for j in range(len(labels)) if j != i] or [0]))
    for i in order:
        best = None
        for dx, dy, ha, va in offsets:
            leader = {"arrowstyle": "-", "color": TEXT_MUTED, "lw": 0.6, "shrinkA": 0, "shrinkB": 4} \
                if max(abs(dx), abs(dy)) > 6 else None
            t = ax.annotate(labels[i], (xs[i], ys[i]), xytext=(dx, dy), textcoords="offset points",
                            ha=ha, va=va, fontsize=fontsize, color=TEXT_PRIMARY, arrowprops=leader)
            bb = t.get_window_extent(renderer)
            box = (bb.x0 - 1, bb.y0 - 1, bb.x1 + 1, bb.y1 + 1)
            clash = any(not (box[2] < o[0] or box[0] > o[2] or box[3] < o[1] or box[1] > o[3])
                        for o in placed + [ob for k, ob in enumerate(obstacles) if k != i])
            if not clash:
                best = (t, box)
                break
            t.remove()
        if best is None:
            # No free spot: keep the first position with a leader line so the label still reads
            t = ax.annotate(labels[i], (xs[i], ys[i]), xytext=(18, 12), textcoords="offset points",
                            ha="left", va="bottom", fontsize=fontsize, color=TEXT_PRIMARY,
                            arrowprops={"arrowstyle": "-", "color": TEXT_MUTED, "lw": 0.6})
            bb = t.get_window_extent(renderer)
            best = (t, (bb.x0, bb.y0, bb.x1, bb.y1))
        placed.append(best[1])


def quadrant_chart(df, x, y, xcut, ycut, quadrant_names, xlabel, ylabel, title, subtitle, note, path,
                   logx=False, ylim=None, yunit=""):
    """Draw a four-quadrant scatter with cut lines, quadrant names and a label on every province.

    With ylim, points outside it are drawn as triangles on the edge, labelled with their value.
    """
    fig, ax = plt.subplots(figsize=(14, 10), dpi=200)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    if logx:
        ax.set_xscale("log")

    # Set limits with headroom
    xmin, xmax = df[x].min(), df[x].max()
    if logx:
        ax.set_xlim(xmin / 1.2, xmax * 1.2)
    else:
        pad = (xmax - xmin) * 0.08
        ax.set_xlim(xmin - pad, xmax + pad)
    if ylim is None:
        ypad = (df[y].max() - df[y].min()) * 0.08
        ylim = (df[y].min() - ypad, df[y].max() + ypad)
    ax.set_ylim(*ylim)

    # Split points inside the y range from those beyond it, which sit on the edge as triangles
    inside = df[(df[y] >= ylim[0]) & (df[y] <= ylim[1])]
    above, below = df[df[y] > ylim[1]], df[df[y] < ylim[0]]
    edge = (ylim[1] - ylim[0]) * 0.015

    # Draw the cut lines, then the points with a surface ring so overlaps stay legible
    ax.axvline(xcut, color=CUT, lw=1, zorder=1)
    ax.axhline(ycut, color=CUT, lw=1, zorder=1)
    ax.scatter(inside[x], inside[y], s=46, color=SERIES, edgecolor=SURFACE, linewidth=2, zorder=3)
    for part, marker, ypos, va, dy in [(above, "^", ylim[1] - edge, "top", -8), (below, "v", ylim[0] + edge, "bottom", 8)]:
        for r in part.itertuples():
            ax.scatter(getattr(r, x), ypos, s=70, marker=marker, color=SERIES, edgecolor=SURFACE, linewidth=2, zorder=3, clip_on=False)
            ax.annotate(f"{r.province} ({getattr(r, y):+.1f}{yunit}, off scale)", (getattr(r, x), ypos),
                        xytext=(9, dy), textcoords="offset points", ha="left", va=va, fontsize=7.5, color=TEXT_PRIMARY)

    # Name each quadrant in its outer corner
    for (right, top), name in quadrant_names.items():
        ax.text(0.99 if right else 0.01, 0.98 if top else 0.02, name, transform=ax.transAxes,
                ha="right" if right else "left", va="top" if top else "bottom",
                fontsize=11, fontweight="bold", color=TEXT_SECONDARY)

    # Label the cut lines with their values
    ax.annotate(f"Indonesia {xcut:.1f}", (xcut, 0), xycoords=("data", "axes fraction"), xytext=(4, 4),
                textcoords="offset points", fontsize=8, color=TEXT_MUTED)
    ax.annotate(f"Indonesia {ycut:.1f}%", (1, ycut), xycoords=("axes fraction", "data"), xytext=(-4, 4),
                textcoords="offset points", ha="right", fontsize=8, color=TEXT_MUTED)

    # Style axes and grid recessively
    if logx:
        ticks = [v for v in [20, 30, 50, 75, 100, 150, 200, 300, 400] if xmin / 1.2 <= v <= xmax * 1.2]
        ax.xaxis.set_major_locator(FixedLocator(ticks))
        ax.xaxis.set_minor_locator(NullLocator())
        ax.set_xticklabels([str(v) for v in ticks])
    ax.grid(color=GRID, lw=0.8, zorder=0)
    for side in ["top", "right"]:
        ax.spines[side].set_visible(False)
    for side in ["left", "bottom"]:
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=TEXT_SECONDARY, labelsize=9, length=0)
    ax.set_xlabel(xlabel, color=TEXT_SECONDARY, fontsize=10)
    ax.set_ylabel(ylabel, color=TEXT_SECONDARY, fontsize=10)

    # Label every province inside the range; edge points were labelled with their values above
    place_labels(ax, inside[x].tolist(), inside[y].tolist(), inside["province"].tolist())

    # Title, subtitle and source note
    fig.text(0.06, 0.965, title, fontsize=15, fontweight="bold", color=TEXT_PRIMARY)
    fig.text(0.06, 0.935, subtitle, fontsize=10, color=TEXT_SECONDARY)
    fig.text(0.06, 0.015, textwrap.fill(note, 190), fontsize=7.5, color=TEXT_MUTED)
    fig.subplots_adjust(left=0.06, right=0.98, top=0.9, bottom=0.1)
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


# Steps

# Read the dataset
df, names = load()

# Plot 1: GRDP per capita 2025 against nominal GRDP growth 2024-2025, for all 38 provinces
grdp = df[(df["indicator"] == "grdp_current") & (df["sector"] == "TOTAL")].pivot(index="province_code", columns="period", values="value")
pop = df[df["indicator"] == "population"].pivot(index="province_code", columns="period", values="value")
provs = grdp.index[grdp["2024"].notna() & grdp["2025"].notna()]
wealth = pd.DataFrame({
    "province_code": provs,
    "province": [names[c] for c in provs],
    "grdp_per_capita_2025": (grdp.loc[provs, "2025"] / pop.loc[provs, "2025"]).values,
    "grdp_growth_2025_pct": ((grdp.loc[provs, "2025"] / grdp.loc[provs, "2024"] - 1) * 100).values,
})
assert len(wealth) == 38

# Cut at the national values: provincial GRDP summed over Indonesia's population, and growth of that sum
x_cut = grdp["2025"].sum() / pop.loc["00", "2025"]
y_cut = (grdp["2025"].sum() / grdp["2024"].sum() - 1) * 100
names_q = {(True, True): "Rich & fast", (True, False): "Rich & slowing",
           (False, True): "Catching up", (False, False): "Lagging"}
wealth["quadrant"] = [names_q[(a >= x_cut, b >= y_cut)]
                      for a, b in zip(wealth["grdp_per_capita_2025"], wealth["grdp_growth_2025_pct"])]

# Write the table behind the chart
wealth.sort_values(["quadrant", "grdp_per_capita_2025"], ascending=[True, False]).to_csv(
    OUT_WEALTH_CSV, index=False, float_format="%.2f", lineterminator="\n")

# Draw the chart
quadrant_chart(
    wealth, "grdp_per_capita_2025", "grdp_growth_2025_pct", x_cut, y_cut, names_q,
    xlabel="GRDP per capita, 2025 (Rp million per person, log scale)",
    ylabel="Nominal GRDP growth, 2024 to 2025 (%)",
    title="Wealth vs momentum: Indonesian provinces, 2025",
    subtitle="GRDP per capita against GRDP growth; lines mark the Indonesia-wide values",
    note=("Source: BPS, PDRB atas dasar harga berlaku (Seri 2010) and population projections; repo dataset 20261102_bps-province-grdp-population. "
          "GRDP is at current prices, so growth includes inflation and commodity prices. 2025 GRDP is very preliminary (**) and 2024 preliminary (*). "
          "Per capita = GRDP (Rp billion) / mid-year population (thousand). The Indonesia line sums provincial GRDP, which BPS does not reconcile with national GDP."),
    path=OUT_WEALTH_PNG, logx=True, ylim=(2.5, 12), yunit="%",
)
print(wealth["quadrant"].value_counts().to_string())
