from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

import json
import sys

# Load the shared chart module from tools/
sys.path.insert(0, str(ROOT / "tools"))
import charts

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FixedLocator, NullLocator
import numpy as np
import pandas as pd

# Parameters

SUBSECTOR = ROOT / "data/20261108_bps-province-grdp-subsector/20261108_bps-province-grdp-subsector.csv"
SUBSECTOR_META = ROOT / "data/20261108_bps-province-grdp-subsector/20261108_bps-province-grdp-subsector-metadata.json"
NATIONAL = ROOT / "data/20261102_bps-province-grdp-population/20261102_bps-province-grdp-population.csv"
NATIONAL_META = ROOT / "data/20261102_bps-province-grdp-population/20261102_bps-province-grdp-population-metadata.json"
WELFARE = ROOT / "data/20261108_bps-province-welfare/20261108_bps-province-welfare.csv"

OUT_SHARES = HERE / "20261108_province-extractive-shares.csv"
OUT_HOUSEHOLDS = HERE / "20261108_households-vs-grdp.csv"
OUT_CHART1 = HERE / "20261108_wealth-momentum-by-coal-share.png"
OUT_CHART2 = HERE / "20261108_coal-vs-other-extractives.png"
OUT_CHART3 = HERE / "20261108_grdp-per-capita-by-source.png"
OUT_CHART4 = HERE / "20261108_wealth-without-coal.png"
OUT_CHART5 = HERE / "20261108_extractive-wealth-and-households.png"

# The year of the national GRDP and population values used for every province
YEAR = "2025"

# Extractive groups of subsectors (codes of the subsector dataset)
COAL = ["B2"]
OIL_GAS = ["B1"]
METALS = ["B3", "C11"]          # metal ores and basic metals (nickel smelting sits in C11)
REFINING = ["C1"]               # coal products and oil refining; kept out of the coal share

# Cut-off for "reliant" on an extractive, in percent of GRDP (a convention, not a BPS definition)
RELIANT = 10

# Coal-share bands for chart 1, in percent of GRDP: (label, upper bound)
COAL_BANDS = [("No coal", 0.05), ("Under 5%", 5), ("5-20%", 20), ("Over 20%", 101)]

# A province's main extractive is not coal when other extractives are at least this share and exceed coal
OTHER_MAIN = 5

# Classes from chart 2, in the colour slot order they take
GROUPS = {
    "Coal economy": charts.SERIES[0],
    "Nickel, copper or oil economy": charts.SERIES[1],
    "Mixed extractive economy": charts.SERIES[2],
    "Non-extractive economy": charts.NEUTRAL,
}
NO_TABLE = "No subsector table"

SOURCE_NOTE = ("Source: BPS provincial GRDP by industry (Seri 2010, current prices) through the BPS WebAPI, repo dataset 20261108_bps-province-grdp-subsector; "
               "GRDP totals and population from 20261102_bps-province-grdp-population. ")

# Functions

def load():
    """Read the three datasets and the province names."""
    read = lambda p: pd.read_csv(p, dtype={"province_code": str, "sector": str, "period": str, "status": str, "area": str},
                                 keep_default_na=False)
    sub, nat, wel = read(SUBSECTOR), read(NATIONAL), read(WELFARE)
    meta = json.loads(NATIONAL_META.read_text(encoding="utf-8"))
    names = {c: charts.display_name(p["name"]) for c, p in meta["provinces"].items()}
    return sub, nat, wel, names


def latest_shares(sub, nat):
    """Return one row per province with a subsector table: its latest year, extractive shares and GRDP per capita.

    Shares are of GRDP at current prices in that year. A subsector BPS leaves empty counts as zero.
    GRDP per capita is set against Indonesia's in the same year (Indonesia = 100), so provinces whose
    latest table is older than 2025 stay comparable.
    """
    cur = sub[sub["indicator"] == "grdp_current"].pivot_table(index=["province_code", "period"], columns="sector", values="value")
    cur = cur.reset_index().sort_values("period").groupby("province_code").tail(1).set_index("province_code").fillna(0.0)
    pop = nat[nat["indicator"] == "population"].pivot(index="province_code", columns="period", values="value")
    total = nat[(nat["indicator"] == "grdp_current") & (nat["sector"] == "TOTAL") & ~nat["period"].str.contains("Q")]
    indonesia_pc = total.groupby("period")["value"].sum() / pop.loc["00"]
    share = lambda codes: cur[codes].sum(axis=1) / cur["TOTAL"] * 100
    out = pd.DataFrame({"year": cur["period"]})
    out["coal_pct"] = share(COAL)
    out["oil_gas_pct"] = share(OIL_GAS)
    out["metals_pct"] = share(METALS)
    out["refining_pct"] = share(REFINING)
    out["other_extractive_pct"] = out["oil_gas_pct"] + out["metals_pct"]
    out["non_extractive_pct"] = 100 - out["coal_pct"] - out["other_extractive_pct"] - out["refining_pct"]
    # GRDP per capita in Rp million: Rp billion / thousand people
    pop_same_year = [pop.loc[c, y] for c, y in zip(out.index, out["year"])]
    out["grdp_per_capita"] = cur["TOTAL"] / pop_same_year
    out["indonesia_per_capita"] = [indonesia_pc[y] for y in out["year"]]
    out["grdp_pc_index"] = out["grdp_per_capita"] / out["indonesia_per_capita"] * 100
    out["grdp_pc_index_without_coal"] = out["grdp_pc_index"] * (1 - out["coal_pct"] / 100)
    extractive = out["coal_pct"] + out["other_extractive_pct"] + out["refining_pct"]
    out["grdp_pc_index_without_extractives"] = out["grdp_pc_index"] * (1 - extractive / 100)
    out["group"] = [classify(c, o) for c, o in zip(out["coal_pct"], out["other_extractive_pct"])]
    out["coal_band"] = [next(label for label, top in COAL_BANDS if c < top) for c in out["coal_pct"]]
    out["main_extractive_not_coal"] = (out["other_extractive_pct"] >= OTHER_MAIN) & (out["other_extractive_pct"] > out["coal_pct"])
    return out


def classify(coal, other):
    """Return the chart 2 class of a province from its coal and other-extractive shares."""
    if coal >= RELIANT and other >= RELIANT:
        return "Mixed extractive economy"
    if coal >= RELIANT:
        return "Coal economy"
    if other >= RELIANT:
        return "Nickel, copper or oil economy"
    return "Non-extractive economy"


def all_provinces(nat, names, shares):
    """Return every province with 2025 GRDP per capita, nominal growth, mining share and its chart 2 class."""
    total = nat[(nat["indicator"] == "grdp_current") & ~nat["period"].str.contains("Q")]
    grdp = total[total["sector"] == "TOTAL"].pivot(index="province_code", columns="period", values="value")
    mining = total[(total["sector"] == "B") & (total["period"] == YEAR)].set_index("province_code")["value"]
    pop = nat[nat["indicator"] == "population"].pivot(index="province_code", columns="period", values="value")
    codes = [c for c in grdp.index if pd.notna(grdp.loc[c, YEAR])]
    df = pd.DataFrame(index=pd.Index(codes, name="province_code"))
    df["province"] = [names[c] for c in codes]
    df["grdp_per_capita_2025"] = grdp.loc[codes, YEAR] / pop.loc[codes, YEAR]
    df["grdp_growth_2025_pct"] = (grdp.loc[codes, YEAR] / grdp.loc[codes, str(int(YEAR) - 1)] - 1) * 100
    df["mining_pct_2025"] = mining.loc[codes] / grdp.loc[codes, YEAR] * 100
    df = df.join(shares)
    df["group"] = df["group"].fillna(NO_TABLE)
    assert len(df) == 38
    return df


def label_of(r):
    """Return a province label, with the year of its subsector table when that is not 2025."""
    return r.province if pd.isna(r.year) or r.year == YEAR else f"{r.province} ({r.year})"


def log_axis(ax, lo, hi, ticks=(20, 30, 50, 75, 100, 150, 200, 300, 400, 600)):
    """Set a log x axis with plain tick labels between lo and hi."""
    ax.set_xscale("log")
    ax.set_xlim(lo, hi)
    shown = [v for v in ticks if lo <= v <= hi]
    ax.xaxis.set_major_locator(FixedLocator(shown))
    ax.xaxis.set_minor_locator(NullLocator())
    ax.set_xticklabels([str(v) for v in shown])


def chart_wealth_momentum(df, x_cut, y_cut, path):
    """Chart 1: GRDP per capita against nominal growth, each point coloured by its coal-share band."""
    fig, ax = charts.new_figure()
    ylim = (2.5, 12)
    log_axis(ax, df["grdp_per_capita_2025"].min() / 1.2, df["grdp_per_capita_2025"].max() * 1.2)
    ax.set_ylim(*ylim)
    ax.axvline(x_cut, color=charts.CUT, lw=1, zorder=1)
    ax.axhline(y_cut, color=charts.CUT, lw=1, zorder=1)
    colour = dict(zip([b for b, _ in COAL_BANDS], charts.ORDINAL_BLUE))
    inside = df[(df["grdp_growth_2025_pct"] >= ylim[0]) & (df["grdp_growth_2025_pct"] <= ylim[1])]
    off = df[~df.index.isin(inside.index)]
    # Draw each point: filled by coal band, a ring of that colour when the main extractive is not coal, gray with no table
    for frame, clip_y in [(inside, None), (off, True)]:
        for c, r in frame.iterrows():
            y = r.grdp_growth_2025_pct if clip_y is None else (ylim[1] - 0.15 if r.grdp_growth_2025_pct > ylim[1] else ylim[0] + 0.15)
            marker = "o" if clip_y is None else ("^" if r.grdp_growth_2025_pct > ylim[1] else "v")
            if r.group == NO_TABLE:
                ax.scatter(r.grdp_per_capita_2025, y, s=55, marker=marker, color=charts.NEUTRAL, edgecolor=charts.SURFACE, lw=2, zorder=3, clip_on=False)
            elif r.main_extractive_not_coal:
                ax.scatter(r.grdp_per_capita_2025, y, s=60, marker=marker, facecolor=charts.SURFACE, edgecolor=colour[r.coal_band], lw=2.2, zorder=4, clip_on=False)
            else:
                ax.scatter(r.grdp_per_capita_2025, y, s=60, marker=marker, color=colour[r.coal_band], edgecolor=charts.SURFACE, lw=2, zorder=3, clip_on=False)
            if clip_y:
                ax.annotate(f"{r.province} ({r.grdp_growth_2025_pct:+.1f}%, off scale)", (r.grdp_per_capita_2025, y), xytext=(9, -2 if y > 10 else 2),
                            textcoords="offset points", ha="left", va="top" if y > 10 else "bottom", fontsize=7.5, color=charts.TEXT_PRIMARY)
    # Name the cut lines and the quadrants
    ax.annotate(f"Indonesia {x_cut:.1f}", (x_cut, 0), xycoords=("data", "axes fraction"), xytext=(4, 4), textcoords="offset points", fontsize=8, color=charts.TEXT_MUTED)
    ax.annotate(f"Indonesia {y_cut:.1f}%", (1, y_cut), xycoords=("axes fraction", "data"), xytext=(-4, 4), textcoords="offset points", ha="right", fontsize=8, color=charts.TEXT_MUTED)
    for (right, top), name in {(True, True): "Rich & fast", (True, False): "Rich & slowing", (False, True): "Catching up", (False, False): "Lagging"}.items():
        ax.text(0.99 if right else 0.01, 0.98 if top else 0.02, name, transform=ax.transAxes, ha="right" if right else "left",
                va="top" if top else "bottom", fontsize=11, fontweight="bold", color=charts.TEXT_SECONDARY)
    charts.style_axes(ax, "GRDP per capita, 2025 (Rp million per person, log scale)", "Nominal GRDP growth, 2024 to 2025 (%)")
    # Legend: the four coal bands, the ring, and the gray points
    handles = [Line2D([], [], ls="", marker="o", ms=8, color=colour[b], label=f"Coal {b.lower()}" if b != "No coal" else "No coal") for b, _ in COAL_BANDS]
    handles += [Line2D([], [], ls="", marker="o", ms=8, markerfacecolor=charts.SURFACE, markeredgecolor=charts.ORDINAL_BLUE[1], markeredgewidth=2,
                       label=f"Ring: main extractive is not coal (oil, gas or metals over {OTHER_MAIN}%)"),
                Line2D([], [], ls="", marker="o", ms=8, color=charts.NEUTRAL, label="Gray: no usable subsector table")]
    ax.legend(handles=handles, loc="lower left", bbox_to_anchor=(0, 1.01), ncol=3, frameon=False, fontsize=8.5, labelcolor=charts.TEXT_SECONDARY)
    labels = [r.province if r.group != NO_TABLE or r.mining_pct_2025 < RELIANT else f"{r.province} (mining {r.mining_pct_2025:.0f}%)" for r in inside.itertuples()]
    charts.place_labels(ax, inside["grdp_per_capita_2025"].tolist(), inside["grdp_growth_2025_pct"].tolist(), labels)
    charts.finish(fig, "Wealth vs momentum, coloured by coal: Indonesian provinces, 2025",
                  "GRDP per capita against GRDP growth; colour is coal's share of GRDP in each province's latest subsector table",
                  SOURCE_NOTE + "Growth is nominal: real growth by province is available for 2025 in only 16 provinces' tables, so this keeps the 38-province view, and coal and nickel prices move it. "
                  "Coal share = B.2 Pertambangan Batubara dan Lignit / GRDP. Gray provinces have no subsector table (or an unusable one, Sulawesi Tenggara); their label gives total mining, an upper bound on coal. "
                  "2025 GRDP is very preliminary.", path, top=0.85)


def chart_classification(df, path):
    """Chart 2: coal share against other-extractive share, point size by GRDP per capita."""
    fig, ax = charts.new_figure(13, 10)
    s = df.dropna(subset=["coal_pct"])
    size = lambda idx: 30 + idx * 2.2
    ax.axvline(RELIANT, color=charts.CUT, lw=1, zorder=1)
    ax.axhline(RELIANT, color=charts.CUT, lw=1, zorder=1)
    ax.scatter(s["other_extractive_pct"], s["coal_pct"], s=size(s["grdp_pc_index"]), color=charts.SERIES[0], alpha=0.85,
               edgecolor=charts.SURFACE, lw=2, zorder=3)
    xmax = max(s["other_extractive_pct"].max() * 1.1, 25)
    ymax = max(s["coal_pct"].max() * 1.15, 25)
    ax.set_xlim(-2, xmax)
    # Room below zero so the bottom quadrant names sit under the points on the baseline
    ax.set_ylim(-0.16 * ymax, ymax)
    for (right, top), name in {(False, True): "Coal economy", (True, True): "Mixed extractive economy",
                               (False, False): "Non-extractive economy", (True, False): "Nickel, copper or oil economy"}.items():
        ax.text(0.99 if right else 0.01, 0.98 if top else 0.02, name, transform=ax.transAxes, ha="right" if right else "left",
                va="top" if top else "bottom", fontsize=11, fontweight="bold", color=charts.TEXT_SECONDARY)
    ax.annotate(f"{RELIANT}%", (RELIANT, 1), xycoords=("data", "axes fraction"), xytext=(4, -12), textcoords="offset points", fontsize=8, color=charts.TEXT_MUTED)
    ax.annotate(f"{RELIANT}%", (1, RELIANT), xycoords=("axes fraction", "data"), xytext=(-4, 4), textcoords="offset points", ha="right", fontsize=8, color=charts.TEXT_MUTED)
    charts.style_axes(ax, "Other extractives: oil and gas (B.1) + metal ores (B.3) + basic metals (C.11), % of GRDP", "Coal (B.2), % of GRDP")
    # Label provinces away from the origin; the crowd near zero is named in one note
    coal = s[s["coal_pct"] >= 2]
    baseline = s[(s["coal_pct"] < 2) & (s["other_extractive_pct"] >= 5)].sort_values("other_extractive_pct")
    near = s[(s["coal_pct"] < 2) & (s["other_extractive_pct"] < 5)]
    charts.place_labels(ax, coal["other_extractive_pct"].tolist(), coal["coal_pct"].tolist(), [label_of(r) for r in coal.itertuples()],
                        sizes=size(coal["grdp_pc_index"]).tolist(), fontsize=8)
    # Points on the zero-coal baseline crowd together, so their labels stack at rising heights with a leader each
    step, level, prev = ymax * 0.055, 0, None
    for r in baseline.itertuples():
        level = 0 if prev is None or r.other_extractive_pct - prev > 6 else (level + 1) % 4
        prev = r.other_extractive_pct
        ax.annotate(label_of(r), (r.other_extractive_pct, r.coal_pct), xytext=(r.other_extractive_pct + 0.4, step * (level + 1.3)),
                    textcoords="data", fontsize=8, color=charts.TEXT_PRIMARY, ha="left", va="center",
                    arrowprops={"arrowstyle": "-", "color": charts.TEXT_MUTED, "lw": 0.6, "shrinkA": 2, "shrinkB": 6})
    ax.annotate(f"{len(near)} provinces with coal under 2% and other extractives under 5% (unlabelled; see the table)",
                (1.5, -0.3), xytext=(0.3, -0.09 * ymax), textcoords="data", fontsize=8, color=charts.TEXT_SECONDARY, ha="left", va="center",
                arrowprops={"arrowstyle": "-", "color": charts.TEXT_MUTED, "lw": 0.6})
    # Size legend: three reference values of GRDP per capita
    handles = [Line2D([], [], ls="", marker="o", color=charts.SERIES[0], alpha=0.85, ms=size(v) ** 0.5, label=f"{v}") for v in (50, 100, 200)]
    ax.legend(handles=handles, title="GRDP per capita (Indonesia = 100)", loc="upper right", bbox_to_anchor=(0.99, 0.93), frameon=False,
              fontsize=8.5, title_fontsize=8.5, labelcolor=charts.TEXT_SECONDARY, labelspacing=1.4, borderpad=1)
    charts.finish(fig, "Coal reliance vs other extractive reliance",
                  f"Share of GRDP at current prices in each province's latest subsector table; lines at {RELIANT}%",
                  SOURCE_NOTE + "Coal and oil refining (C.1) is left out of both axes because in most provinces it is refining. "
                  f"The {RELIANT}% cut is a convention, not a BPS definition. 26 provinces have a usable subsector table; the year is shown where it is not 2025. "
                  "Shares move with commodity prices as well as output.", path)


def chart_sources(df, path):
    """Chart 3: GRDP per capita of each province, split into coal, oil and gas, metals, refining and the rest."""
    s = df.dropna(subset=["coal_pct"]).sort_values("grdp_pc_index")
    parts = [("Coal (B.2)", "coal_pct", charts.SERIES[0]), ("Oil and gas (B.1)", "oil_gas_pct", charts.SERIES[1]),
             ("Metal ores and basic metals (B.3 + C.11)", "metals_pct", charts.SERIES[2]),
             ("Coal products and oil refining (C.1)", "refining_pct", charts.SERIES[3]),
             ("Everything else", "non_extractive_pct", charts.NEUTRAL)]
    fig, ax = charts.new_figure(13, 11)
    y = np.arange(len(s))
    left = np.zeros(len(s))
    for label, col, colour in parts:
        width = (s[col] / 100 * s["grdp_pc_index"]).values
        # A 2px surface gap between segments separates them without a border
        ax.barh(y, width, left=left, height=0.68, color=colour, edgecolor=charts.SURFACE, lw=1.5, label=label, zorder=3)
        left += width
    ax.axvline(100, color=charts.TEXT_SECONDARY, lw=1, zorder=4)
    ax.annotate("Indonesia = 100", (100, len(s) - 0.4), xytext=(4, 0), textcoords="offset points", fontsize=8, color=charts.TEXT_SECONDARY, va="bottom")
    # Value at each bar end, the one number the reader compares
    for yi, v in zip(y, s["grdp_pc_index"]):
        ax.annotate(f"{v:.0f}", (v, yi), xytext=(4, 0), textcoords="offset points", va="center", fontsize=7.5, color=charts.TEXT_SECONDARY,
                    bbox={"boxstyle": "square,pad=0.1", "fc": charts.SURFACE, "ec": "none"}, zorder=5)
    ax.set_yticks(y)
    ax.set_yticklabels([label_of(r) for r in s.itertuples()], fontsize=8.5)
    ax.set_ylim(-0.6, len(s) - 0.2)
    ax.set_xlim(0, s["grdp_pc_index"].max() * 1.08)
    charts.style_axes(ax, "GRDP per capita, Indonesia = 100 (same year)", "", grid_axis="x")
    ax.legend(loc="lower right", frameon=False, fontsize=8.5, labelcolor=charts.TEXT_SECONDARY)
    charts.finish(fig, "Where each province's GRDP per capita comes from",
                  "GRDP per person relative to Indonesia, split by source; each province at its latest subsector year",
                  SOURCE_NOTE + "Index = province GRDP per capita / Indonesia GRDP per capita in the same year x 100, where Indonesia = sum of provincial GRDP / Indonesia population. "
                  "Each segment = that source's share of the province's GRDP x the index. Production located in a province is not its residents' income.",
                  path, left=0.2, top=0.91, bottom=0.08, wrap=170)


def chart_without(df, path):
    """Chart 4: GRDP per capita with and without coal, and with and without all extractives (dumbbells)."""
    panels = [("Without coal", "grdp_pc_index_without_coal", df[df["coal_pct"] >= 1]),
              ("Without any extractive (coal, oil and gas, metals, refining)", "grdp_pc_index_without_extractives",
               df[(df["coal_pct"] + df["other_extractive_pct"] + df["refining_pct"]) >= 5])]
    heights = [len(p[2]) for p in panels]
    fig, axes = plt.subplots(2, 1, figsize=(13, 11), dpi=200, gridspec_kw={"height_ratios": heights})
    fig.patch.set_facecolor(charts.SURFACE)
    xmax = df["grdp_pc_index"].max() * 1.1
    for ax, (title, col, s) in zip(axes, panels):
        ax.set_facecolor(charts.SURFACE)
        s = s.assign(drop=s["grdp_pc_index"] - s[col]).sort_values("drop")
        y = np.arange(len(s))
        ax.hlines(y, s[col], s["grdp_pc_index"], color=charts.NEUTRAL, lw=2, zorder=2)
        ax.scatter(s["grdp_pc_index"], y, s=60, color=charts.SERIES[0], edgecolor=charts.SURFACE, lw=2, zorder=3, label="Actual")
        ax.scatter(s[col], y, s=60, color=charts.SERIES[1], edgecolor=charts.SURFACE, lw=2, zorder=3, label=title)
        ax.axvline(100, color=charts.TEXT_SECONDARY, lw=1, zorder=1)
        # Name the provinces that fall from above to below the Indonesia line
        for yi, (_, r) in zip(y, s.iterrows()):
            crosses = r.grdp_pc_index >= 100 > r[col]
            ax.annotate(f"{r.grdp_pc_index:.0f} to {r[col]:.0f}" + ("  falls below Indonesia" if crosses else ""),
                        (max(r.grdp_pc_index, r[col]), yi), xytext=(8, 0), textcoords="offset points", va="center",
                        fontsize=7.5, color=charts.TEXT_PRIMARY if crosses else charts.TEXT_SECONDARY,
                        fontweight="bold" if crosses else "normal")
        ax.set_yticks(y)
        ax.set_yticklabels([label_of(r) for r in s.itertuples()], fontsize=8.5)
        ax.set_xlim(0, xmax)
        ax.set_ylim(-0.7, len(s) - 0.3)
        charts.style_axes(ax, "GRDP per capita, Indonesia = 100 (same year)", "", grid_axis="x")
        ax.set_title(title, loc="left", fontsize=10.5, fontweight="bold", color=charts.TEXT_SECONDARY)
        ax.legend(loc="lower right", frameon=False, fontsize=8.5, labelcolor=charts.TEXT_SECONDARY)
    fig.subplots_adjust(hspace=0.28)
    charts.finish(fig, "Wealth with and without extractives",
                  "GRDP per capita relative to Indonesia, actual and with the extractive sector's value added removed",
                  SOURCE_NOTE + "Without coal = (GRDP - B.2) / population, against the actual Indonesia average of the same year; removing all extractives subtracts B.1, B.2, B.3, C.1 and C.11. "
                  "Upper panel: provinces with coal at least 1% of GRDP; lower panel: extractives at least 5%. This is an accounting removal, not a counterfactual: other sectors would also be smaller without mining.",
                  path, left=0.2, top=0.9, bottom=0.12, wrap=170)


def households(df, wel):
    """Return GRDP per capita, adjusted household expenditure and poverty for 2025, with each province's gap to the trend."""
    exp = wel[(wel["indicator"] == "expenditure_per_capita_adjusted") & (wel["period"] == YEAR)].set_index("province_code")["value"]
    pov = wel[(wel["indicator"] == "poverty_rate_march") & (wel["area"] == "total") & (wel["period"] == YEAR)].set_index("province_code")["value"]
    h = df[["province", "group", "coal_pct", "other_extractive_pct", "mining_pct_2025", "grdp_per_capita_2025"]].copy()
    h["expenditure_2025_rp_million"] = exp.loc[h.index] / 1000
    h["poverty_rate_march_2025"] = pov.loc[h.index]
    # Trend: least squares of log expenditure on log GRDP per capita across the 38 provinces
    slope, intercept = np.polyfit(np.log(h["grdp_per_capita_2025"]), np.log(h["expenditure_2025_rp_million"]), 1)
    h["trend_expenditure"] = np.exp(intercept + slope * np.log(h["grdp_per_capita_2025"]))
    h["gap_to_trend_pct"] = (h["expenditure_2025_rp_million"] / h["trend_expenditure"] - 1) * 100
    return h, slope


def chart_households(h, slope, path):
    """Chart 5: GRDP per capita against adjusted household expenditure, coloured by extractive class."""
    fig, ax = charts.new_figure(14, 10)
    # Extra room on the right so the label of the richest province fits
    lo, hi = h["grdp_per_capita_2025"].min() / 1.15, h["grdp_per_capita_2025"].max() * 1.6
    log_axis(ax, lo, hi)
    xs = np.exp(np.linspace(np.log(lo), np.log(hi), 50))
    ratio = h["trend_expenditure"] / h["grdp_per_capita_2025"] ** slope
    ax.plot(xs, ratio.iloc[0] * xs ** slope, color=charts.CUT, lw=1.5, zorder=1)
    # Name the trend line below it, right of the richest provinces where the plot is empty
    x_note = hi / 1.9
    ax.annotate(f"Trend across 38 provinces (elasticity {slope:.2f})", (x_note, ratio.iloc[0] * x_note ** slope), xytext=(6, -16),
                textcoords="offset points", ha="left", va="top", fontsize=8, color=charts.TEXT_MUTED)
    for group, colour in {**GROUPS, NO_TABLE: None}.items():
        g = h[h["group"] == group]
        # A class with no province gets no legend entry
        if g.empty:
            continue
        if colour is None:
            ax.scatter(g["grdp_per_capita_2025"], g["expenditure_2025_rp_million"], s=60, facecolor=charts.SURFACE, edgecolor=charts.TEXT_MUTED, lw=1.8, zorder=3, label=f"{NO_TABLE} (label gives total mining)")
        else:
            ax.scatter(g["grdp_per_capita_2025"], g["expenditure_2025_rp_million"], s=60, color=colour, edgecolor=charts.SURFACE, lw=2, zorder=3, label=f"{group} ({len(g)})")
    charts.style_axes(ax, "GRDP per capita, 2025 (Rp million per person, log scale)", "Adjusted household expenditure per capita, 2025 (Rp million per person per year, 2012 prices)")
    ax.legend(loc="lower right", frameon=False, fontsize=8.5, labelcolor=charts.TEXT_SECONDARY)
    # Label extractive provinces, those far from the trend, and gray provinces with large mining
    show = h[(h["group"] != "Non-extractive economy") | (h["gap_to_trend_pct"].abs() >= 12)]
    labels = []
    for r in show.itertuples():
        text = f"{r.province} {r.gap_to_trend_pct:+.0f}%"
        if r.group == NO_TABLE and r.mining_pct_2025 >= RELIANT:
            text += f" (mining {r.mining_pct_2025:.0f}%)"
        labels.append(text)
    charts.place_labels(ax, show["grdp_per_capita_2025"].tolist(), show["expenditure_2025_rp_million"].tolist(), labels)
    charts.finish(fig, "Does extractive wealth reach households?",
                  "GRDP per capita against household spending, 2025; labels give each province's distance from the trend",
                  SOURCE_NOTE + "Household expenditure: BPS pengeluaran per kapita disesuaikan (HDI method, real 2012 prices, purchasing-power adjusted), repo dataset 20261108_bps-province-welfare. "
                  "Trend = least squares of log expenditure on log GRDP per capita. Classes come from the coal and other-extractive shares (chart 2). "
                  "Provinces far below the trend produce value that their households do not spend: profits and rents leave the province. Unlabelled provinces are non-extractive and within 12% of the trend.",
                  path)


# Steps

# Read the datasets
sub, nat, wel, names = load()

# Compute each province's extractive shares and GRDP per capita, and join them to all 38 provinces
shares = latest_shares(sub, nat)
df = all_provinces(nat, names, shares)

# Write the table behind charts 1-4
cols = ["province", "year", "group", "coal_band", "main_extractive_not_coal", "coal_pct", "oil_gas_pct", "metals_pct", "refining_pct",
        "other_extractive_pct", "non_extractive_pct", "mining_pct_2025", "grdp_per_capita_2025", "grdp_growth_2025_pct",
        "grdp_pc_index", "grdp_pc_index_without_coal", "grdp_pc_index_without_extractives"]
df[cols].sort_values(["group", "coal_pct"], ascending=[True, False]).to_csv(OUT_SHARES, float_format="%.2f", lineterminator="\n")

# Chart 1: wealth vs momentum, cut at the Indonesia-wide values as in analysis/20261102_province-quadrants
grdp = nat[(nat["indicator"] == "grdp_current") & (nat["sector"] == "TOTAL")].pivot(index="province_code", columns="period", values="value")
pop = nat[nat["indicator"] == "population"].pivot(index="province_code", columns="period", values="value")
x_cut = grdp[YEAR].sum() / pop.loc["00", YEAR]
y_cut = (grdp[YEAR].sum() / grdp[str(int(YEAR) - 1)].sum() - 1) * 100
chart_wealth_momentum(df, x_cut, y_cut, OUT_CHART1)

# Charts 2-4: classification, sources of GRDP per capita, and wealth without extractives
chart_classification(df, OUT_CHART2)
chart_sources(df, OUT_CHART3)
chart_without(df.dropna(subset=["coal_pct"]), OUT_CHART4)

# Chart 5: household spending against GRDP per capita, with the table behind it
h, slope = households(df, wel)
h.sort_values("gap_to_trend_pct").to_csv(OUT_HOUSEHOLDS, float_format="%.2f", lineterminator="\n")
chart_households(h, slope, OUT_CHART5)

# Report the classes and the provinces furthest below the household trend
print(df["group"].value_counts().to_string())
print(h.sort_values("gap_to_trend_pct")[["province", "group", "grdp_per_capita_2025", "expenditure_2025_rp_million", "gap_to_trend_pct"]].head(8).round(1).to_string())
