from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# Load the shared chart module from tools/
import sys
sys.path.insert(0, str(ROOT / "tools"))
import charts

import json
from collections import Counter

import pandas as pd

# Parameters

DATASET = ROOT / "data/20261103_bps-province-grdp-2010-2025/20261103_bps-province-grdp-2010-2025.csv"
METADATA = ROOT / "data/20261103_bps-province-grdp-2010-2025/20261103_bps-province-grdp-2010-2025-metadata.json"

OUT_PNG = HERE / "20261103_long-run-momentum.png"
OUT_RELATIVE_PNG = HERE / "20261103_long-run-momentum-relative.png"
OUT_CSV = HERE / "20261103_long-run-momentum.csv"

# BPS's national row, and the last year of every growth window
NATIONAL = "00"
END_YEAR = 2025

# First year of each province's window: the first year its values cover its present borders.
# 2010 for the 30 provinces whose borders did not change.
# 2013 for 64 Kalimantan Timur and 65 Kalimantan Utara: 65 has its own values only from 2013,
# and 64 in 2010-2012 includes it.
# 2023 for 91 Papua Barat, 92 Papua Barat Daya, 94 Papua, 95 Papua Selatan, 96 Papua Tengah and
# 97 Papua Pegunungan: the four new provinces start in 2023, and 91 and 94 cover the pre-split areas before 2023.
FIRST_YEAR = 2010
SPLIT_START = {"64": 2013, "65": 2013, "91": 2023, "92": 2023, "94": 2023, "95": 2023, "96": 2023, "97": 2023}

# Provinces BPS first publishes in a later year, which must have no value before it
NEW_PROVINCES = {"65": 2013, "92": 2023, "95": 2023, "96": 2023, "97": 2023}

# Provinces BPS publishes in each window's start year and in 2025; each set covers the whole country
PROVINCES_PRESENT = {2010: 33, 2013: 34, 2023: 38, END_YEAR: 38}

# Number of provinces in each window, as the legend states
WINDOW_COUNTS = {2010: 30, 2013: 2, 2023: 6}

# Marker style and legend text of each window: filled from 2010, hollow from 2013, hollow diamonds from 2023
STYLES = {
    2010: {"label": "2010–2025: 30 provinces", "filled": True},
    2013: {"label": "2013–2025: Kalimantan Timur and Kalimantan Utara", "filled": False},
    2023: {"label": "2023–2025: the six Papua provinces (2 years of growth)", "filled": False, "marker": "D"},
}

# Quadrant names as in the wealth-vs-momentum chart: right = at or above the X cut, top = at or above the Y cut
QUADRANTS = {(True, True): "Rich & fast", (True, False): "Rich & slowing",
             (False, True): "Catching up", (False, False): "Lagging"}

# Y range of chart 1 (% a year), which keeps the 30-province cluster readable and leaves Papua Tengah off scale,
# and its ticks, which keep clear of the Papua Pegunungan label at the left edge
YLIM = (2.0, 14.0)
YTICKS = [2.5, 5, 7.5, 10, 12.5]

# Lower end of the y range of chart 2 (percentage points); the top is chart 1's less the 2010-2025 cut. At this
# height the corner name turns the Kalimantan Timur label inward, inside the figure
YLOW_RELATIVE = -2.45

# Growth bands whose points the chart module labels in rows above the crowd, each name on a leader: chart 1 in
# % a year; chart 2 in percentage points, reaching lower to take in Papua, Papua Selatan, Papua Barat Daya and
# Kepulauan Bangka Belitung, whose labels otherwise sit beside each other's markers
BAND = (4.3, 6.4)
BAND_RELATIVE = (-1.3, 1.0)

# Province whose off-scale label in chart 2 stays on one line, where a second line would cover Riau's point
ONE_LINE_RELATIVE = ["96"]

# Layout of the band's names, in pixels of the 200-dpi PNG, as in the coal-reliance chart: points whose markers sit
# under 10 px apart share one name and leader, each name keeps 17 px across from every other leader and its distance
# from points labelled beside themselves, and two names in neighbouring rows never stack into what reads as one label
FLAGS = {"merge": 10, "leader_room": 17, "dot_room": 26, "stack_gap": 20}
# Leaders thinner than the 1-point cut lines, in the cut-line grey
LEADER = {"color": charts.CUT, "lw": 0.5}

# Ticks of the log X axes
XTICKS = [10, 15, 20, 30, 50, 75, 100, 150]
XTICKS_RELATIVE = [20, 30, 50, 75, 100, 150, 200, 300, 400]

# Tolerance for BPS's national row against the provincial sum in 2010: 33 values rounded to 0.01
NATIONAL_SUM_TOLERANCE = 33 * 0.005

# Decimals in the table: Rp values keep BPS's two decimals, derived rates carry four
DECIMALS = {"grdp_constant_2010_start": 2, "grdp_constant_2010_2025": 2, "grdp_per_capita_constant_2010_start": 2,
            "indonesia_per_capita_constant_2010_start": 2, "per_capita_index": 2, "growth_pct_per_year": 4,
            "indonesia_growth_same_window_pct": 4, "growth_gap_pp": 4}

# Functions

def load():
    """Read the dataset and the province names from its metadata."""
    df = pd.read_csv(DATASET, dtype={"province_code": str, "sector": str, "period": str, "status": str},
                     keep_default_na=False)
    meta = json.loads(METADATA.read_text(encoding="utf-8"))
    names = {code: charts.display_name(p["name"]) for code, p in meta["provinces"].items()}
    return df, names


def wide(df, indicator, column="value"):
    """Return one TOTAL indicator as a province-by-year table, with years as integers."""
    rows = df[(df["indicator"] == indicator) & (df["sector"] == "TOTAL")]
    table = rows.pivot(index="province_code", columns="period", values=column)
    table.columns = table.columns.astype(int)
    return table


def cagr(start_value, end_value, years):
    """Return the compound average annual growth from start_value to end_value over years, in % a year."""
    return ((end_value / start_value) ** (1 / years) - 1) * 100


def window(start):
    """Return a window's years as they appear on a label, such as 2013–25."""
    return f"{start}–{END_YEAR % 100:02d}"


def chart_labels(table, y, band, one_line=()):
    """Return each province's label for one chart: its name, with the years of a later window.

    The years go on a second line for a point outside the band, which keeps the labels at the plot edges inside
    the figure; a name in the band keeps one line, since the band's rows take the height of its tallest name.
    Without a band every label keeps one line.
    """
    labels = []
    for code, name, start_year, value in zip(table["province_code"], table["province"], table["window_start"], table[y]):
        if start_year == FIRST_YEAR:
            labels.append(name)
        elif band is None or band[0] <= value <= band[1] or code in one_line:
            labels.append(f"{name} ({window(start_year)})")
        else:
            labels.append(f"{name}\n({window(start_year)})")
    return labels


def members(table, column):
    """Return the provinces of each quadrant of one chart as text, quadrant by quadrant."""
    lines = []
    for name, part in table.groupby(column, sort=True):
        lines.append(f"{name} ({len(part)}): " + ", ".join(f"{c} {p}" for c, p in zip(part["province_code"], part["province"])))
    return "\n".join(lines)


# Steps

# Read the dataset: real GRDP and real GRDP per capita by province and year, and the status of each value
df, names = load()
real = wide(df, "grdp_constant_2010")
per_capita = wide(df, "grdp_per_capita_constant_2010")
status = wide(df, "grdp_constant_2010", "status")

# Give each province its window start year, and check the windows hold the stated numbers of provinces
provinces = sorted(c for c in names if c != NATIONAL)
start = {c: SPLIT_START.get(c, FIRST_YEAR) for c in provinces}
assert len(provinces) == 38, len(provinces)
assert Counter(start.values()) == WINDOW_COUNTS, Counter(start.values())

# Check from the data that the new provinces have no value before their first year
for code, first in NEW_PROVINCES.items():
    earlier = df[(df["province_code"] == code) & (df["period"].astype(int) < first)]
    assert earlier.empty, f"{code} has values before {first}"

# Check that every province has real GRDP and per capita in its start year and in 2025
for code, s in start.items():
    for table in (real, per_capita):
        assert pd.notna(table.loc[code, s]) and pd.notna(table.loc[code, END_YEAR]), f"{code} lacks {s} or {END_YEAR}"

# Check the number of provinces BPS publishes in each start year and in 2025, so each sum covers the whole country
provincial = real.drop(index=NATIONAL)
for year, count in PROVINCES_PRESENT.items():
    assert provincial[year].notna().sum() == count, (year, provincial[year].notna().sum())

# Check that BPS's national row equals the provincial sum in 2010, which makes its 2010 per capita the national value
assert abs(provincial[FIRST_YEAR].sum() - real.loc[NATIONAL, FIRST_YEAR]) <= NATIONAL_SUM_TOLERANCE

# Indonesia's growth over each window: compound growth of the sum of the provinces, since BPS's national row
# changes basis between 2014 and 2015
national_growth = {s: cagr(provincial[s].sum(), provincial[END_YEAR].sum(), END_YEAR - s) for s in WINDOW_COUNTS}

# Build one row per province: values at both ends of its window, its growth and its gaps to Indonesia
t = pd.DataFrame({"province_code": provinces})
t["province"] = [names[c] for c in provinces]
t["window_start"] = [start[c] for c in provinces]
t["window_end"] = END_YEAR
t["years"] = t["window_end"] - t["window_start"]
t["grdp_constant_2010_start"] = [real.loc[c, start[c]] for c in provinces]
t["grdp_constant_2010_2025"] = [real.loc[c, END_YEAR] for c in provinces]
t["grdp_per_capita_constant_2010_start"] = [per_capita.loc[c, start[c]] for c in provinces]
t["indonesia_per_capita_constant_2010_start"] = [per_capita.loc[NATIONAL, start[c]] for c in provinces]
t["per_capita_index"] = t["grdp_per_capita_constant_2010_start"] / t["indonesia_per_capita_constant_2010_start"] * 100
t["growth_pct_per_year"] = cagr(t["grdp_constant_2010_start"], t["grdp_constant_2010_2025"], t["years"])
t["indonesia_growth_same_window_pct"] = t["window_start"].map(national_growth)
t["growth_gap_pp"] = t["growth_pct_per_year"] - t["indonesia_growth_same_window_pct"]
t["status_2025"] = [status.loc[c, END_YEAR] for c in provinces]

# Chart 1 axes: per capita in the start year in Rp million, against growth; cut at Indonesia's 2010 per capita
# and the 2010-2025 growth of the summed provinces
t["per_capita_start_million"] = t["grdp_per_capita_constant_2010_start"] / 1000
x_cut = per_capita.loc[NATIONAL, FIRST_YEAR] / 1000
y_cut = national_growth[FIRST_YEAR]
t["quadrant_chart1"] = [QUADRANTS[(a >= x_cut, b >= y_cut)]
                        for a, b in zip(t["per_capita_start_million"], t["growth_pct_per_year"])]

# Chart 2 axes: per capita as an index of Indonesia's in the same year, against the growth gap over the same years
t["quadrant_chart2"] = [QUADRANTS[(a >= 100, b >= 0)] for a, b in zip(t["per_capita_index"], t["growth_gap_pp"])]

# Write the table behind both charts, sorted by chart 1 quadrant and then by growth, fastest first
out = t.sort_values(["quadrant_chart1", "growth_pct_per_year"], ascending=[True, False])
out = out[["province_code", "province", "window_start", "window_end", "years", "grdp_constant_2010_start",
           "grdp_constant_2010_2025", "grdp_per_capita_constant_2010_start", "indonesia_per_capita_constant_2010_start",
           "per_capita_index", "growth_pct_per_year", "indonesia_growth_same_window_pct", "growth_gap_pp",
           "quadrant_chart1", "quadrant_chart2", "status_2025"]].copy()
for column, places in DECIMALS.items():
    out[column] = out[column].map(lambda v, p=places: f"{v:.{p}f}")
out.to_csv(OUT_CSV, index=False, lineterminator="\n")

# Label each chart's points: the name, with the years of a later window
t["label"] = chart_labels(t, "growth_pct_per_year", BAND)
t["label_relative"] = chart_labels(t, "growth_gap_pp", BAND_RELATIVE, ONE_LINE_RELATIVE)

# Indonesia's per capita in the later start years, Rp million, for the printed report (the charts carry no note)
pc_2013, pc_2023 = per_capita.loc[NATIONAL, 2013] / 1000, per_capita.loc[NATIONAL, 2023] / 1000

# Draw chart 1 on the agreed axes
charts.quadrant_chart(
    t, "per_capita_start_million", "growth_pct_per_year", x_cut, y_cut, QUADRANTS,
    xlabel="Real GRDP per capita in the start year (Rp million per person at constant 2010 prices, log scale)",
    ylabel="Real GRDP growth, start year to 2025 (% a year, compound average)",
    title="Long-run momentum: Indonesian provinces, 2010–2025",
    subtitle="Real GRDP per capita at the start of each window against real GRDP growth to 2025; lines mark Indonesia",
    note=None, path=OUT_PNG, logx=True, ylim=YLIM, yunit="%", xticks=XTICKS, yticks=YTICKS,
    xcut_label="Indonesia 2010: {:.1f}", ycut_label="Indonesia 2010–25: {:.1f}%",
    label="label", group="window_start", styles=STYLES, band=BAND, legend_cols=1,
    keep_quadrants=True, flag_options=FLAGS, leader=LEADER, halo=True,
)

# Draw chart 2 with each province against Indonesia over its own years
charts.quadrant_chart(
    t, "per_capita_index", "growth_gap_pp", 100, 0, QUADRANTS,
    xlabel="Real GRDP per capita in the start year, Indonesia in the same year = 100 (log scale)",
    ylabel="Real GRDP growth minus Indonesia's over the same years (percentage points)",
    title="Long-run momentum relative to Indonesia, 2010–2025",
    subtitle="Each province against Indonesia over its own window: per capita index and growth gap; lines mark Indonesia",
    note=None, path=OUT_RELATIVE_PNG, logx=True, ylim=(YLOW_RELATIVE, YLIM[1] - y_cut), yunit=" pp",
    xticks=XTICKS_RELATIVE, xcut_label="Indonesia = {:.0f}", ycut_label="Indonesia = {:.0f} pp",
    label="label_relative", group="window_start", styles=STYLES, band=BAND_RELATIVE, legend_cols=1,
    keep_quadrants=True, flag_options=FLAGS, leader=LEADER, halo=True,
)

# Report the cut lines, both charts' quadrants and the provinces whose quadrant differs between them
print(f"Chart 1 cuts: X {x_cut:.4f} (Rp million), Y {y_cut:.4f}% a year")
print("Indonesia growth by window (% a year): " + ", ".join(f"{s}–{END_YEAR}: {g:.4f}" for s, g in national_growth.items()))
print(f"Indonesia per capita (Rp million): 2013 {pc_2013:.5f}, 2023 {pc_2023:.5f}")
print(f"Growth range: {t['growth_pct_per_year'].min():.3f} to {t['growth_pct_per_year'].max():.3f}% a year")
for column in ("quadrant_chart1", "quadrant_chart2"):
    print(f"\n{column}:\n" + members(t, column))
moved = t[t["quadrant_chart1"] != t["quadrant_chart2"]]
print("\nQuadrant differs between the charts:")
for _, r in moved.iterrows():
    print(f"  {r['province_code']} {r['province']}: {r['quadrant_chart1']} -> {r['quadrant_chart2']}")
