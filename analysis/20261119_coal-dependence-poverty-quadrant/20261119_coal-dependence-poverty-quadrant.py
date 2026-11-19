from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

import sys

# Load the shared chart module from tools/
sys.path.insert(0, str(ROOT / "tools"))
import charts

import textwrap

import matplotlib.image as mpimg
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch, Rectangle
from matplotlib.ticker import FixedLocator, NullLocator
import pandas as pd

# Parameters

# Datasets read; analysis scripts read data/ only
DATA = ROOT / "data"
GRDP = DATA / "20261116_bps-province-grdp-by-industry-2021-2025/20261116_bps-province-grdp-by-industry-2021-2025.csv"
GRDP_META = DATA / "20261116_bps-province-grdp-by-industry-2021-2025/20261116_bps-province-grdp-by-industry-2021-2025-metadata.json"
POPULATION = DATA / "20261102_bps-province-grdp-population/20261102_bps-province-grdp-population.csv"
WELFARE = DATA / "20261108_bps-province-welfare/20261108_bps-province-welfare.csv"

OUT_PNG = HERE / "20261119_coal-dependence-poverty-quadrant.png"
OUT_CSV = HERE / "20261119_coal-dependence-poverty-quadrant.csv"
OUT_SLIDE = HERE / "20261119_coal-dependence-poverty-slide.png"

# Economic dependence is coal's share of GRDP (CC2 C); absolute poverty is the March headcount rate P0 (CC4 C)
YEAR = "2025"

# Bottom fraction of the chart image that holds its footnote, cut when the chart sits on the slide
CHART_NOTE_HEIGHT = 0.075

# Slide-ready figure: 16:9 at 13.33 x 7.5 inches, no title in the image so the slide carries it
WIDTH, HEIGHT = 13.33, 7.5
MARGINS = dict(left=0.07, right=0.98, top=0.97, bottom=0.14)

# Plot window: coal share (log scale, %) and poverty rate (%)
XLIM, YLIM = (0.01, 60), (0, 14)
XTICKS = [0.01, 0.1, 1, 2, 5, 10, 25]

# Smallest coal share placed on the log axis; below it coal output is at the level of BPS rounding to whole Rp billions
MIN_SHARE = 0.01

# Bubble area in points squared per thousand poor people, and the reference sizes in the size legend
AREA_PER_THOUSAND = 1.2
SIZE_KEYS = [100, 500, 1000]

# Quadrant names, keyed by (coal share at or above the cut, poverty at or above the cut)
QUADRANTS = {(True, True): "High dependence, high poverty:\nmost vulnerable",
             (True, False): "High dependence, low poverty:\nfiscal and job risk",
             (False, True): "Low dependence, high poverty:\nstructural poverty",
             (False, False): "Low dependence, low poverty"}

# Light shade behind the most vulnerable quadrant, as on the CC2 chart, and the accent for its point on the slide
VULNERABLE_SHADE = "#f3e3d9"
VULNERABLE_ACCENT = charts.SERIES[1]

# Functions

def read(path):
    """Read a repo dataset with codes, periods and status as text and values as numbers."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df["value"] = df["value"].astype(float)
    return df


def pick(df, **keys):
    """Return the value column indexed by province for the rows matching every key."""
    for col, val in keys.items():
        df = df[df[col] == val]
    return df.set_index("province_code")["value"]


def build_table():
    """Return one row per coal-producing province with coal share, poverty rate and estimated poor people, plus the Indonesia cuts."""
    grdp, pop, wel = read(GRDP), read(POPULATION), read(WELFARE)
    names = charts.province_names(GRDP_META)

    # Coal mining (B2) and total GRDP at current prices; an unpublished coal cell means no coal output
    total = pick(grdp, indicator="grdp_current", sector="TOTAL", period=YEAR)
    coal = pick(grdp, indicator="grdp_current", sector="B2", period=YEAR).reindex(total.index).fillna(0)

    # Poverty rate (March, whole province) and population in thousands
    p0 = pick(wel, indicator="poverty_rate_march", area="total", period=YEAR)
    people = pick(pop, indicator="population", sector="", period=YEAR)

    t = pd.DataFrame(index=total.index)
    t.index.name = "province_code"
    t["province"] = [names[c] for c in t.index]
    t["coal_share_pct"] = coal / total * 100
    t["poverty_rate_pct"] = p0
    t["population_thousand"] = people
    t["poor_people_thousand_est"] = p0 / 100 * people

    # Indonesia cuts: coal share from summed provinces, poverty as BPS publishes it for Indonesia (00)
    cuts = (coal.sum() / total.sum() * 100, p0["00"])

    # Only provinces with a coal share of at least MIN_SHARE are placed on the log coal-share axis
    shown = t["coal_share_pct"] >= MIN_SHARE
    return t[shown].copy(), t[~shown], cuts


def draw(t, x_cut, y_cut, n_without):
    """Bubble quadrant: coal share (log) against poverty rate, bubble area by estimated poor people."""
    fig, ax = charts.new_figure(WIDTH, HEIGHT)
    fig.subplots_adjust(**MARGINS)
    ax.set_xscale("log")
    ax.set_xlim(*XLIM)
    ax.set_ylim(*YLIM)

    # Shade the most vulnerable quadrant, then draw the Indonesia cut lines
    ax.add_patch(Rectangle((x_cut, y_cut), XLIM[1] - x_cut, YLIM[1] - y_cut, color=VULNERABLE_SHADE, zorder=0, lw=0))
    ax.axvline(x_cut, color=charts.CUT, lw=1, zorder=1)
    ax.axhline(y_cut, color=charts.CUT, lw=1, zorder=1)

    # Bubbles, largest first so small ones stay on top
    sizes = (t["poor_people_thousand_est"] * AREA_PER_THOUSAND).clip(lower=40)
    order = sizes.sort_values(ascending=False).index
    ax.scatter(t.loc[order, "coal_share_pct"], t.loc[order, "poverty_rate_pct"], s=sizes[order],
               color=charts.SERIES[0], alpha=0.85, edgecolor=charts.SURFACE, linewidth=2, zorder=3)

    # Name each quadrant in its outer corner
    for (right, top), name in QUADRANTS.items():
        ax.text(0.99 if right else 0.01, 0.98 if top else 0.02, name, transform=ax.transAxes,
                ha="right" if right else "left", va="top" if top else "bottom",
                fontsize=11, fontweight="bold", color=charts.TEXT_SECONDARY)

    # Label the cut lines with the Indonesia values
    ax.annotate(f"Indonesia {x_cut:.1f}%", (x_cut, 0), xycoords=("data", "axes fraction"), xytext=(4, 40),
                textcoords="offset points", fontsize=9, color=charts.TEXT_MUTED)
    ax.annotate(f"Indonesia {y_cut:.2f}%", (0, y_cut), xycoords=("axes fraction", "data"), xytext=(4, 4),
                textcoords="offset points", fontsize=9, color=charts.TEXT_MUTED)

    # Size legend: reference bubbles for the estimated number of poor people
    # Reference bubbles are grey outlines so they never read as provinces
    keys = [Line2D([], [], marker="o", ls="", markerfacecolor="none", markeredgecolor=charts.TEXT_MUTED, markeredgewidth=1,
                   markersize=(k * AREA_PER_THOUSAND) ** 0.5, label=f"{k:,} thousand") for k in SIZE_KEYS]
    leg = ax.legend(handles=keys, title="Bubble size: poor people (estimate)", loc="lower left", bbox_to_anchor=(0.0, 0.07),
                    ncol=len(SIZE_KEYS), frameon=False, fontsize=9, title_fontsize=9, columnspacing=2.5, handletextpad=1.2, borderpad=1, handleheight=3.2)
    leg._legend_box.align = "left"
    leg.get_title().set_color(charts.TEXT_SECONDARY)
    for txt in leg.get_texts():
        txt.set_color(charts.TEXT_SECONDARY)

    # Readable ticks on the log axis, recessive axes and grid
    ax.xaxis.set_major_locator(FixedLocator(XTICKS))
    ax.xaxis.set_minor_locator(NullLocator())
    ax.set_xticklabels([f"{v:g}%" for v in XTICKS])
    charts.style_axes(ax, f"Economic dependence: coal mining (B2) share of GRDP, {YEAR} (log scale)",
                      f"Absolute poverty: poverty rate P0, March {YEAR} (%)")
    for lab in [ax.xaxis.label, ax.yaxis.label]:
        lab.set_fontsize(11)
    ax.tick_params(labelsize=10)

    # Label every province with its name and its two values
    labels = [f"{r.province} ({r.coal_share_pct:.1f}%, {r.poverty_rate_pct:.1f}%)" if r.coal_share_pct >= 0.1
              else f"{r.province} ({r.coal_share_pct:.2f}%, {r.poverty_rate_pct:.1f}%)" for r in t.itertuples()]
    charts.place_labels(ax, t["coal_share_pct"].tolist(), t["poverty_rate_pct"].tolist(), labels, fontsize=9, sizes=sizes.tolist())

    charts.finish(
        fig, title="", subtitle="",
        note=("Source: BPS; repo datasets 20261116_bps-province-grdp-by-industry-2021-2025, 20261108_bps-province-welfare, 20261102_bps-province-grdp-population. "
              "Labels give (coal share of GRDP, poverty rate). Lines mark Indonesia: coal share from summed provinces, poverty as published. "
              f"Bubble area = poverty rate x mid-year population, an estimate. Not shown: {n_without} provinces with no coal output or coal under {MIN_SHARE}% of GRDP. 2025 GRDP is very preliminary (**)."),
        path=OUT_PNG, wrap=195, **MARGINS)


def slide(t, x_cut, y_cut):
    """Mock up one 16:9 slide: a conclusion title, the chart on the left, three so-what points on the right, the source below."""
    fig = plt.figure(figsize=(WIDTH, HEIGHT), dpi=200)
    fig.patch.set_facecolor(charts.SURFACE)

    # The points come from the table, so the slide text follows the data
    hh = t[(t["coal_share_pct"] >= x_cut) & (t["poverty_rate_pct"] >= y_cut)]
    hl = t[(t["coal_share_pct"] >= x_cut) & (t["poverty_rate_pct"] < y_cut) & (t["coal_share_pct"] >= 10)]
    edge = t[(t["coal_share_pct"] < x_cut) & (t["coal_share_pct"] >= x_cut / 2) & (t["poverty_rate_pct"] >= y_cut)]
    lead = hh.sort_values("poor_people_thousand_est", ascending=False).iloc[0]
    rng = lambda col: f"{hl[col].min():.0f}-{hl[col].max():.0f}%" if col == "coal_share_pct" else f"{hl[col].min():.1f}-{hl[col].max():.1f}%"
    only = "Only " if len(hh) == 1 else ""
    points = [
        ("Priority", f"{lead.province}: coal is {lead.coal_share_pct:.1f}% of GRDP and {lead.poverty_rate_pct:.1f}% of people are poor "
                     f"(about {lead.poor_people_thousand_est / 1000:.1f} million). The coal exit hits the households with the least cushion."),
        ("Different risk", f"{', '.join(hl['province'])}: coal is {rng('coal_share_pct')} of GRDP, poverty only {rng('poverty_rate_pct')}. "
                           "The risk is to provincial revenue and mining jobs."),
        ("Watch", f"{' and '.join(edge['province'])}: poverty above 12%, coal just under the {x_cut:.1f}% national share."),
    ]

    # Title as the conclusion, with the analysis name as a small subtitle
    fig.text(0.035, 0.925, f"{only}{' and '.join(hh['province'])} is both coal-dependent and poorer than average",
             fontsize=20, fontweight="bold", color=charts.TEXT_PRIMARY)
    fig.text(0.035, 0.88, f"Economic Dependence x Absolute Poverty, {YEAR}: coal's share of GRDP against the poverty rate, by province",
             fontsize=12.5, color=charts.TEXT_SECONDARY)

    # Chart on the left two-thirds
    image = mpimg.imread(OUT_PNG)
    ax = fig.add_axes([0.02, 0.07, 0.67, 0.78])
    ax.imshow(image[: int(image.shape[0] * (1 - CHART_NOTE_HEIGHT))])
    ax.axis("off")

    # So-what panel on the right
    panel = fig.add_axes([0.705, 0.11, 0.27, 0.72])
    panel.axis("off")
    panel.add_patch(FancyBboxPatch((0, 0), 1, 1, boxstyle="round,pad=0,rounding_size=0.03", transform=panel.transAxes,
                                   facecolor="#f3f2ee", edgecolor="none"))
    panel.text(0.07, 0.94, "SO WHAT", transform=panel.transAxes, fontsize=11, fontweight="bold", color=charts.TEXT_MUTED, va="top")
    # Stack each point under the last, measuring the drawn text so blocks never overlap
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    to_axes = panel.transAxes.inverted()
    bottom_of = lambda txt: to_axes.transform(txt.get_window_extent(renderer))[0][1]
    y = 0.85
    for i, (head, body) in enumerate(points):
        colour = VULNERABLE_ACCENT if i == 0 else charts.TEXT_SECONDARY
        h = panel.text(0.07, y, head, transform=panel.transAxes, fontsize=12.5, fontweight="bold", color=colour, va="top")
        b = panel.text(0.07, bottom_of(h) - 0.02, textwrap.fill(body, 40), transform=panel.transAxes, fontsize=10.5,
                       color=charts.TEXT_PRIMARY, va="top", linespacing=1.35)
        y = bottom_of(b) - 0.07

    # Source line
    fig.text(0.035, 0.03, f"Source: BPS, GRDP by industry {YEAR} (very preliminary) and Susenas March {YEAR}. Lines mark the Indonesia values; "
                          "bubble size = poverty rate x population (estimate).", fontsize=9, color=charts.TEXT_MUTED)
    fig.savefig(OUT_SLIDE, facecolor=charts.SURFACE)
    plt.close(fig)


# Steps

# Build the table of coal-producing provinces and the Indonesia cuts
table, without, (x_cut, y_cut) = build_table()

# Name each province's quadrant
table["quadrant"] = [QUADRANTS[(s >= x_cut, p >= y_cut)].replace("\n", " ")
                     for s, p in zip(table["coal_share_pct"], table["poverty_rate_pct"])]

# Draw the slide-ready chart
draw(table, x_cut, y_cut, len(without))

# Mock up the slide around the chart
slide(table, x_cut, y_cut)

# Write the table behind the chart, most vulnerable quadrant first, then by coal share
order = {name.replace("\n", " "): i for i, name in enumerate(QUADRANTS.values())}
out = table.assign(_o=table["quadrant"].map(order)).sort_values(["_o", "coal_share_pct"], ascending=[True, False]).drop(columns="_o")
out.reset_index().to_csv(OUT_CSV, index=False, float_format="%.4f", lineterminator="\n")
print(f"Indonesia cuts: coal share {x_cut:.2f}%, poverty {y_cut:.2f}%")
print(out[["province", "coal_share_pct", "poverty_rate_pct", "poor_people_thousand_est", "quadrant"]].round(2).to_string(index=False))
