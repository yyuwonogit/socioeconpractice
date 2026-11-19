from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

import sys

# Load the shared chart module from tools/
sys.path.insert(0, str(ROOT / "tools"))
import charts

from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from matplotlib.ticker import FixedLocator, NullLocator
import numpy as np
import pandas as pd

# Parameters

# Datasets read; analysis scripts read data/ only
DATA = ROOT / "data"
GRDP = DATA / "20261116_bps-province-grdp-by-industry-2021-2025/20261116_bps-province-grdp-by-industry-2021-2025.csv"
GRDP_META = DATA / "20261116_bps-province-grdp-by-industry-2021-2025/20261116_bps-province-grdp-by-industry-2021-2025-metadata.json"
POPULATION = DATA / "20261102_bps-province-grdp-population/20261102_bps-province-grdp-population.csv"
WELFARE = DATA / "20261108_bps-province-welfare/20261108_bps-province-welfare.csv"
DEPTH = DATA / "20261116_bps-province-poverty-depth-ipm/20261116_bps-province-poverty-depth-ipm.csv"
WORKERS = DATA / "20261116_bps-province-workers-by-industry/20261116_bps-province-workers-by-industry.csv"

OUT_CSV = HERE / "20261119_wealth-distribution-quadrants.csv"
OUT_POVERTY = HERE / "20261119_grdp-per-capita-vs-poverty.png"
OUT_ENCLAVE = HERE / "20261119_mining-output-vs-mining-jobs.png"
OUT_GROWTH = HERE / "20261119_growth-vs-poverty-change.png"
OUT_DEPTH = HERE / "20261119_poverty-rate-vs-depth.png"

# Snapshot year for levels, and the window for growth and poverty change (the window of the GRDP-by-industry dataset)
YEAR, FIRST_YEAR = "2025", "2021"

# A province is a coal economy when coal mining (B2) is at least this share of GRDP, and another mining economy
# when all mining (B) reaches it without coal doing so; the 10% cut matches analysis/20261108_coal-reliance
RELIANT = 10

# Provinces whose 2021 values cover the pre-2022 Papua areas, so a 2021-2025 change is not comparable
PAPUA_SPLIT = ["91", "92", "94", "95", "96", "97"]

# Groups in the colour slot order they take, with their legend text
GROUPS = {
    "coal": ("Coal economy (coal mining 10%+ of GRDP)", charts.SERIES[0]),
    "mining": ("Other mining economy (mining 10%+, coal under 10%)", charts.SERIES[1]),
    "other": ("Mining under 10% of GRDP", charts.NEUTRAL),
}

# Light shade behind the quadrant each chart asks about
SHADE = "#f3e3d9"

SOURCE = ("Source: BPS, through repo datasets 20261116_bps-province-grdp-by-industry-2021-2025 (GRDP by industry, Seri 2010), "
          "20261102_bps-province-grdp-population (population), 20261108_bps-province-welfare (poverty rate P0), "
          "20261116_bps-province-poverty-depth-ipm (poverty depth P1) and 20261116_bps-province-workers-by-industry (Sakernas). ")

# Functions

def read(path):
    """Read a repo dataset with codes, periods and status as text and values as numbers."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df["value"] = df["value"].astype(float)
    return df


def pick(df, **keys):
    """Return the value column indexed by province for the rows matching every key."""
    part = df
    for col, val in keys.items():
        part = part[part[col] == val]
    return part.set_index("province_code")["value"]


def build_table():
    """Return one row per province with every metric the four charts plot, plus the Indonesia values."""
    grdp, pop, wel, dep, wrk = read(GRDP), read(POPULATION), read(WELFARE), read(DEPTH), read(WORKERS)
    names = charts.province_names(GRDP_META)

    # GRDP at current prices in the snapshot year: total, all mining (B) and coal mining (B2); an unpublished coal cell means no coal
    total = pick(grdp, indicator="grdp_current", sector="TOTAL", period=YEAR)
    mining = pick(grdp, indicator="grdp_current", sector="B", period=YEAR).reindex(total.index)
    coal = pick(grdp, indicator="grdp_current", sector="B2", period=YEAR).reindex(total.index).fillna(0)

    # Population in thousands; GRDP in Rp billion over thousand people gives Rp million per person
    people = pick(pop, indicator="population", sector="", period=YEAR)

    # Real GRDP growth: compound average per year at constant 2010 prices
    real = lambda y: pick(grdp, indicator="grdp_constant", sector="TOTAL", period=y)
    years = int(YEAR) - int(FIRST_YEAR)
    cagr = ((real(YEAR) / real(FIRST_YEAR)) ** (1 / years) - 1) * 100

    # Poverty headcount (P0) and depth (P1), March survey, whole province
    p0 = lambda y: pick(wel, indicator="poverty_rate_march", area="total", period=y)
    p1 = pick(dep, indicator="poverty_depth_march", area="total", period=YEAR)

    # Mining's share of employment; BPS marks some cells as having a relative standard error of 25-50%
    workers = wrk[wrk["period"] == YEAR]
    mine_jobs = pick(workers, sector="B")
    all_jobs = pick(workers, sector="TOTAL")
    mine_jobs_status = workers[workers["sector"] == "B"].set_index("province_code")["status"]

    t = pd.DataFrame(index=total.index)
    t.index.name = "province_code"
    t["province"] = [names[c] for c in t.index]
    t["coal_share_pct"] = coal / total * 100
    t["mining_share_pct"] = mining / total * 100
    t["group"] = ["coal" if c >= RELIANT else "mining" if m >= RELIANT else "other"
                  for c, m in zip(t["coal_share_pct"], t["mining_share_pct"])]
    t["grdp_per_capita_rp_million"] = total / people
    t["poverty_rate_pct"] = p0(YEAR)
    t["poverty_depth_p1"] = p1
    t["poor_shortfall_pct_of_line"] = p1 / p0(YEAR) * 100
    t["mining_jobs_share_pct"] = mine_jobs / all_jobs * 100
    t["mining_jobs_rse_25_50"] = mine_jobs_status.reindex(t.index).eq("rse25-50")
    t["mining_output_per_job_vs_province"] = t["mining_share_pct"] / t["mining_jobs_share_pct"]
    t["real_grdp_cagr_pct"] = cagr
    t["poverty_change_pp"] = p0(YEAR) - p0(FIRST_YEAR)
    t.loc[t.index.isin(PAPUA_SPLIT), ["real_grdp_cagr_pct", "poverty_change_pp"]] = None

    # Indonesia values: GRDP and population summed over provinces; poverty, depth and jobs as BPS publishes them for 00
    nat = {
        "grdp_per_capita_rp_million": total.sum() / people.drop("00").sum(),
        "mining_share_pct": mining.sum() / total.sum() * 100,
        "poverty_rate_pct": p0(YEAR)["00"],
        "poor_shortfall_pct_of_line": p1["00"] / p0(YEAR)["00"] * 100,
        "mining_jobs_share_pct": mine_jobs["00"] / all_jobs["00"] * 100,
        "real_grdp_cagr_pct": ((real(YEAR).sum() / real(FIRST_YEAR).sum()) ** (1 / years) - 1) * 100,
        "poverty_change_pp": p0(YEAR)["00"] - p0(FIRST_YEAR)["00"],
    }
    return t, nat


def new_figure():
    """A chart figure with the final margins already set, so label placement sees the axes at their saved size."""
    fig, ax = charts.new_figure(14, 10)
    fig.subplots_adjust(left=0.06, right=0.98, top=0.9, bottom=0.1)
    return fig, ax


def draw_points(ax, t, x, y, hollow=None):
    """Scatter provinces coloured by group; hollow rings mark estimates BPS flags as less reliable."""
    hollow = pd.Series(False, index=t.index) if hollow is None else hollow
    for key, (_, colour) in GROUPS.items():
        part = t[t["group"] == key]
        solid, ring = part[~hollow[part.index]], part[hollow[part.index]]
        ax.scatter(solid[x], solid[y], s=60, color=colour, edgecolor=charts.SURFACE, linewidth=2, zorder=3)
        ax.scatter(ring[x], ring[y], s=50, facecolor=charts.SURFACE, edgecolor=colour, linewidth=2, zorder=3)


def legend(ax, t, loc, extra=None, anchor=None):
    """Legend with each group's province count, plus any extra entries, placed at loc or at loc of the anchor point."""
    handles = [Line2D([], [], marker="o", ls="", markersize=8, color=colour, markeredgecolor=charts.SURFACE,
                      label=f"{text} ({(t['group'] == key).sum()})") for key, (text, colour) in GROUPS.items()]
    handles += extra or []
    leg = ax.legend(handles=handles, loc=loc, bbox_to_anchor=anchor, frameon=False, fontsize=9)
    for txt in leg.get_texts():
        txt.set_color(charts.TEXT_SECONDARY)


def quadrants(ax, x_cut, y_cut, names, shade, xlim, ylim):
    """Shade the quadrant in question, draw the Indonesia cut lines and name each quadrant in its outer corner.

    names is keyed by (right of the x cut, above the y cut); shade is the key of the shaded quadrant.
    """
    right, top = shade
    x0, x1 = (x_cut, xlim[1]) if right else (xlim[0], x_cut)
    y0, y1 = (y_cut, ylim[1]) if top else (ylim[0], y_cut)
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, color=SHADE, zorder=0, lw=0))
    ax.axvline(x_cut, color=charts.CUT, lw=1, zorder=1)
    ax.axhline(y_cut, color=charts.CUT, lw=1, zorder=1)
    for (r, tp), name in names.items():
        ax.text(0.99 if r else 0.01, 0.985 if tp else 0.015, name, transform=ax.transAxes,
                ha="right" if r else "left", va="top" if tp else "bottom",
                fontsize=10.5, fontweight="bold", color=charts.TEXT_SECONDARY)


def cut_labels(ax, x_text, y_text, x_cut, y_cut):
    """Label the two cut lines with the Indonesia values."""
    ax.annotate(x_text, (x_cut, 0), xycoords=("data", "axes fraction"), xytext=(4, 22),
                textcoords="offset points", fontsize=8, color=charts.TEXT_MUTED)
    ax.annotate(y_text, (1, y_cut), xycoords=("axes fraction", "data"), xytext=(-4, 4),
                textcoords="offset points", ha="right", fontsize=8, color=charts.TEXT_MUTED)


def assign(t, x, y, x_cut, y_cut, names):
    """Return each province's quadrant name, or empty where either value is missing."""
    return [names[(a >= x_cut, b >= y_cut)] if pd.notna(a) and pd.notna(b) else ""
            for a, b in zip(t[x], t[y])]


def log_ticks(ax, ticks, fmt):
    """Fixed readable ticks on a log x axis."""
    ax.xaxis.set_major_locator(FixedLocator(ticks))
    ax.xaxis.set_minor_locator(NullLocator())
    ax.set_xticklabels([fmt(v) for v in ticks])


# Quadrant names for each chart, keyed by (right of the x cut, above the y cut)
Q_POVERTY = {(True, True): "High output, high poverty:\noutput not reaching households",
             (True, False): "High output, low poverty",
             (False, True): "Low output, high poverty",
             (False, False): "Low output, low poverty"}
Q_GROWTH = {(True, True): "Faster growth, slower poverty fall:\ngrowth bypassing the poor",
            (True, False): "Faster growth, faster poverty fall",
            (False, True): "Slower growth, slower poverty fall",
            (False, False): "Slower growth, faster poverty fall"}
Q_DEPTH = {(True, True): "More poor, and poorer:\nwidespread and deep",
           (True, False): "More poor, closer to the line",
           (False, True): "Fewer poor, but deep",
           (False, False): "Fewer poor, closer to the line"}

# Bands of mining output per mining job relative to the province average, (label, lower bound)
ENCLAVE_BANDS = [("30x or more: enclave", 30), ("10-30x", 10), ("3-10x", 3), ("Under 3x", 0)]


def chart_poverty(t, nat):
    """GRDP per capita (log) against the poverty rate."""
    x, y = "grdp_per_capita_rp_million", "poverty_rate_pct"
    xlim, ylim = (15, 500), (0, 33)
    fig, ax = new_figure()
    ax.set_xscale("log")
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    quadrants(ax, nat[x], nat[y], Q_POVERTY, (True, True), xlim, ylim)
    draw_points(ax, t, x, y)
    cut_labels(ax, f"Indonesia Rp {nat[x]:.0f} million", f"Indonesia {nat[y]:.2f}%", nat[x], nat[y])
    log_ticks(ax, [20, 30, 50, 75, 100, 150, 200, 300, 400], lambda v: f"{v:g}")
    charts.style_axes(ax, f"GRDP per capita, {YEAR} (Rp million per person, current prices, log scale)",
                      f"Poverty rate, March {YEAR} (% of population below the BPS poverty line)")
    legend(ax, t, "center left", anchor=(0, 0.72))
    charts.place_labels(ax, t[x].tolist(), t[y].tolist(), t["province"].tolist(), fontsize=8, sizes=[60] * len(t))
    charts.finish(fig,
        title="Output per person against poverty: where does provincial wealth reach households?",
        subtitle=f"GRDP per capita against the poverty rate, {YEAR}; lines mark the Indonesia values",
        note=SOURCE + ("GRDP per capita = GRDP at current prices / mid-year population; Indonesia sums the provinces. "
                       "GRDP counts output produced in the province, including profits paid to owners elsewhere, so it measures production, not income. "
                       f"Groups use {YEAR} shares of GRDP at current prices; nickel smelting sits in manufacturing and is not counted as mining. "
                       f"{YEAR} GRDP is very preliminary (**)."),
        path=OUT_POVERTY)


def chart_enclave(t, nat):
    """Mining's share of GRDP against its share of jobs, both log, with the equal-share diagonal."""
    x, y = "mining_share_pct", "mining_jobs_share_pct"
    d = t.dropna(subset=[x, y])
    d = d[d[x] > 0]
    xlim, ylim = (0.1, 100), (0.03, 30)
    fig, ax = new_figure()
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.axvline(RELIANT, color=charts.CUT, lw=1, zorder=1)

    # Reference diagonals: mining output per job equal to, 10 times and 30 times the province average
    p0, p1 = ax.transData.transform([(1, 1), (10, 10)])
    angle = np.degrees(np.arctan2(p1[1] - p0[1], p1[0] - p0[0]))
    for k, style, at in [(1, "-", 20), (10, "--", 0.6), (30, ":", 1.8)]:
        ax.plot([xlim[0], xlim[1]], [xlim[0] / k, xlim[1] / k], color=charts.CUT, lw=0.9, ls=style, zorder=1)
        ax.annotate("equal shares" if k == 1 else f"output per mining job {k}x the province average",
                    (at, at / k), xytext=(0, 4), textcoords="offset points", ha="left", va="bottom",
                    rotation=angle, rotation_mode="anchor", fontsize=8, color=charts.TEXT_MUTED)

    draw_points(ax, d, x, y, hollow=d["mining_jobs_rse_25_50"])
    ax.annotate(f"{RELIANT}% of GRDP: mining-reliant", (RELIANT, 0), xycoords=("data", "axes fraction"), xytext=(4, 22),
                textcoords="offset points", fontsize=8, color=charts.TEXT_MUTED)
    log_ticks(ax, [0.1, 0.3, 1, 3, 10, 30, 100], lambda v: f"{v:g}%")
    ax.yaxis.set_major_locator(FixedLocator([0.03, 0.1, 0.3, 1, 3, 10, 30]))
    ax.yaxis.set_minor_locator(NullLocator())
    ax.set_yticklabels([f"{v:g}%" for v in [0.03, 0.1, 0.3, 1, 3, 10, 30]])
    charts.style_axes(ax, f"Mining and quarrying (B) share of GRDP, {YEAR}, current prices (log scale)",
                      f"Mining and quarrying share of employed persons, August {YEAR} (log scale)")
    ring = Line2D([], [], marker="o", ls="", markersize=8, markerfacecolor=charts.SURFACE, markeredgecolor=charts.TEXT_MUTED,
                  markeredgewidth=2, label="Ring: BPS job estimate has a 25-50% relative standard error")
    legend(ax, d, "upper left", extra=[ring], anchor=(0, 0.93))
    charts.place_labels(ax, d[x].tolist(), d[y].tolist(), d["province"].tolist(), fontsize=8, sizes=[60] * len(d))
    dropped = ", ".join(t.drop(d.index)["province"])
    charts.finish(fig,
        title="Mining output against mining jobs: how few workers hold the extractive economy?",
        subtitle=f"Mining's share of GRDP against its share of jobs, {YEAR}; distance below the diagonal is output per mining job relative to the province average",
        note=SOURCE + ("Output per mining job relative to the province average = mining share of GRDP / mining share of employed persons. "
                       "Mining value added includes the operator's profit and rent, so a high ratio shows output concentrated in capital, not wages. "
                       f"Workers are counted where they live (Sakernas) and output where it is produced. Not shown: {dropped} (no published mining job estimate or no mining output)."),
        path=OUT_ENCLAVE)
    return d


def chart_growth(t, nat):
    """Real GRDP growth against the change in the poverty rate."""
    x, y = "real_grdp_cagr_pct", "poverty_change_pp"
    d = t.dropna(subset=[x, y])
    xlim, ylim = (3, 13), (-3.6, 0.6)
    fig, ax = new_figure()
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    quadrants(ax, nat[x], nat[y], Q_GROWTH, (True, True), xlim, ylim)
    beyond = d[d[x] > xlim[1]]
    d_in = d.drop(beyond.index)
    draw_points(ax, d_in, x, y)
    for r in beyond.itertuples():
        ax.scatter(xlim[1], getattr(r, y), s=80, marker=">", color=GROUPS[r.group][1], edgecolor=charts.SURFACE,
                   linewidth=2, zorder=3, clip_on=False)
        ax.annotate(f"{r.province}\n{getattr(r, x):.1f}% a year, off scale", (xlim[1], getattr(r, y)), xytext=(-10, 6),
                    textcoords="offset points", ha="right", va="bottom", fontsize=8, color=charts.TEXT_PRIMARY)
    cut_labels(ax, f"Indonesia {nat[x]:.1f}% a year", f"Indonesia {nat[y]:+.2f} points", nat[x], nat[y])
    charts.style_axes(ax, f"Real GRDP growth, average per year {FIRST_YEAR}-{YEAR} (%, constant 2010 prices)",
                      f"Change in the poverty rate, March {FIRST_YEAR} to March {YEAR} (percentage points)")
    legend(ax, d, "lower right", anchor=(1, 0.06))
    charts.place_labels(ax, d_in[x].tolist(), d_in[y].tolist(), d_in["province"].tolist(), fontsize=8, sizes=[60] * len(d_in))
    charts.finish(fig,
        title="Growth against poverty reduction: did faster-growing provinces cut poverty faster?",
        subtitle=f"Real GRDP growth against the change in the poverty rate, {FIRST_YEAR}-{YEAR}; lines mark the Indonesia values",
        note=SOURCE + (f"Growth = ((GRDP {YEAR} / GRDP {FIRST_YEAR})^(1/{int(YEAR) - int(FIRST_YEAR)}) - 1) x 100 at constant 2010 prices; Indonesia sums the provinces. "
                       "A change below zero means poverty fell. The six Papua provinces are left out because their 2021 values cover the areas before the 2022 split. "
                       "2024 GRDP is preliminary (*) and 2025 very preliminary (**)."),
        path=OUT_GROWTH)
    return d


def chart_depth(t, nat):
    """Poverty rate against how far the poor fall below the poverty line."""
    x, y = "poverty_rate_pct", "poor_shortfall_pct_of_line"
    xlim, ylim = (0, 33), (10, 27)
    fig, ax = new_figure()
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    quadrants(ax, nat[x], nat[y], Q_DEPTH, (True, True), xlim, ylim)
    draw_points(ax, t, x, y)
    cut_labels(ax, f"Indonesia {nat[x]:.2f}%", f"Indonesia {nat[y]:.1f}%", nat[x], nat[y])
    charts.style_axes(ax, f"Poverty rate P0, March {YEAR} (% of population)",
                      f"Average shortfall of the poor, March {YEAR} (% of the poverty line, P1 / P0)")
    legend(ax, t, "lower right", anchor=(1, 0.06))
    charts.place_labels(ax, t[x].tolist(), t[y].tolist(), t["province"].tolist(), fontsize=8, sizes=[60] * len(t))
    charts.finish(fig,
        title="How many are poor, and how poor: breadth against depth of poverty",
        subtitle=f"Poverty rate against the average gap between the poor's spending and the poverty line, March {YEAR}; lines mark the Indonesia values",
        note=SOURCE + ("P1 (Indeks Kedalaman Kemiskinan) averages each person's shortfall below the provincial poverty line, with the non-poor counted as zero; "
                       "dividing P1 by P0 gives the average shortfall among the poor only. Poverty lines differ by province, so depth compares each province with its own line."),
        path=OUT_DEPTH)


# Steps

# Build the province table and the Indonesia values
table, nat = build_table()

# Draw the four charts
chart_poverty(table, nat)
chart_enclave(table, nat)
chart_growth(table, nat)
chart_depth(table, nat)

# Record each province's quadrant on every chart
table["quadrant_grdp_poverty"] = assign(table, "grdp_per_capita_rp_million", "poverty_rate_pct",
                                        nat["grdp_per_capita_rp_million"], nat["poverty_rate_pct"], Q_POVERTY)
table["band_mining_output_per_job"] = [next(n for n, lo in ENCLAVE_BANDS if r >= lo) if pd.notna(r) else ""
                                       for r in table["mining_output_per_job_vs_province"]]
table["quadrant_growth_poverty_change"] = assign(table, "real_grdp_cagr_pct", "poverty_change_pp",
                                                 nat["real_grdp_cagr_pct"], nat["poverty_change_pp"], Q_GROWTH)
table["quadrant_poverty_depth"] = assign(table, "poverty_rate_pct", "poor_shortfall_pct_of_line",
                                         nat["poverty_rate_pct"], nat["poor_shortfall_pct_of_line"], Q_DEPTH)
for col in [c for c in table.columns if c.startswith("quadrant_")]:
    table[col] = table[col].str.replace("\n", " ")

# Write the table behind the charts, coal economies first, then by mining share
order = {k: i for i, k in enumerate(GROUPS)}
out = table.assign(_o=table["group"].map(order)).sort_values(["_o", "mining_share_pct"], ascending=[True, False]).drop(columns="_o")
out["group"] = out["group"].map({k: v[0] for k, v in GROUPS.items()})
out.reset_index().to_csv(OUT_CSV, index=False, float_format="%.4f", lineterminator="\n")

# Print the Indonesia cuts and the provinces in each chart's shaded quadrant
print({k: round(v, 2) for k, v in nat.items()})
for col, shaded in [("quadrant_grdp_poverty", Q_POVERTY[(True, True)]), ("band_mining_output_per_job", ENCLAVE_BANDS[0][0]), ("band_mining_output_per_job", ENCLAVE_BANDS[1][0]),
                    ("quadrant_growth_poverty_change", Q_GROWTH[(True, True)]), ("quadrant_poverty_depth", Q_DEPTH[(True, True)])]:
    print(f"\n{col}: {shaded.replace(chr(10), ' ')}")
    print(", ".join(table[table[col] == shaded.replace("\n", " ")]["province"]))
