from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# Load the shared chart module from tools/
import sys
sys.path.insert(0, str(ROOT / "tools"))
import charts

import json

import pandas as pd

# Parameters

# GRDP and population for per capita, the same data as the 20261102 wealth-vs-momentum chart
POP_DATASET = ROOT / "data/20261102_bps-province-grdp-population/20261102_bps-province-grdp-population.csv"
POP_METADATA = ROOT / "data/20261102_bps-province-grdp-population/20261102_bps-province-grdp-population-metadata.json"
# GRDP by detailed industry from each province's BPS SIMDASI table, for the coal share
INDUSTRY_DATASET = ROOT / "data/20261103_bps-province-grdp-detailed-industry/20261103_bps-province-grdp-detailed-industry.csv"
INDUSTRY_METADATA = (ROOT / "data/20261103_bps-province-grdp-detailed-industry/"
                     "20261103_bps-province-grdp-detailed-industry-metadata.json")

OUT_PNG = HERE / "20261103_coal-reliance.png"
OUT_CSV = HERE / "20261103_coal-reliance.csv"

# The chart's year, and the year that checks how stable its quadrants are
YEAR, CHECK_YEAR = "2025", "2024"
# Coal and lignite mining (KBLI 05) is BPS sub-category B2, TOTAL is GRDP and 00 is Indonesia
COAL, TOTAL, INDONESIA = "B2", "TOTAL", "00"
# BPS prints a cell with no value as an en dash, 'Tidak ada atau nol' (none or zero)
DASH = "–"
# Provinces whose 2025 B2 cell BPS prints as an en dash, as confirmed with the user
DASH_2025 = ["12", "18", "19", "21", "31", "32", "33", "34", "35", "51", "52", "53",
             "71", "72", "74", "75", "81", "82", "91", "94", "95", "96", "97"]
# Quadrant names by (at or above the per capita line, at or above the coal share line)
QUADRANTS = {(True, True): "Rich & coal-reliant", (False, True): "Poorer & coal-reliant",
             (True, False): "Rich & less coal-reliant", (False, False): "Poorer & less coal-reliant"}
# Y axis in %, from just below 0, so the points at 0 show whole, to just above the highest share; the chart module
# extends it below 0 as far as the names hanging under the zero line need, and the ticks stay at 0-25
YLIM = (-0.5, 27.5)
YTICKS = [0, 5, 10, 15, 20, 25]
# Points at or near 0, whose names hang in rows under the zero line, each on its own leader. Bengkulu (1.9%) and
# Aceh (1.7%), just under the 2% line, sit above this band and are labelled beside or below their dots
ZERO_BAND = (YLIM[0], 0.5)
# Layout of those names, in pixels of the 200-dpi PNG: points whose markers sit under 8 px apart share one name and
# leader, each name keeps 17 px across from every other leader and its distance from other markers, and two names
# in neighbouring rows never stack into what reads as one label
FLAGS = {"merge": 10, "leader_room": 17, "dot_room": 26, "stack_gap": 20}
# Leaders thinner than the 1-point cut lines, in the cut-line grey
LEADER = {"color": charts.CUT, "lw": 0.5}

# Functions

def read_long(path):
    """Read a long dataset with codes, periods and statuses as text, so '00' and empty statuses survive."""
    return pd.read_csv(path, dtype={"province_code": str, "sector": str, "period": str, "status": str},
                       keep_default_na=False)


def cells(df, indicator, sector, period):
    """Return the value and status of one indicator, sector and period, indexed by province code."""
    rows = df[(df["indicator"] == indicator) & (df["sector"] == sector) & (df["period"] == period)]
    assert rows["province_code"].is_unique, f"repeated provinces in {indicator} {sector} {period}"
    return rows.set_index("province_code")[["value", "status"]]


def dash_cells(meta, sector, period):
    """Return the provinces whose cell BPS prints as an en dash, from the metadata's none_or_zero_cells."""
    listed = meta["none_or_zero_cells"]
    assert listed["marker"] == DASH
    return sorted(c["province_code"] for c in listed["cells"] if c["sector"] == sector and c["period"] == period)


def year_values(pop, industry, industry_meta, provinces, year):
    """Compute each province's per capita GRDP and coal share in a year, and the two Indonesia lines.

    Per capita = grdp_current TOTAL (Rp billion) / population (thousand) from the 20261102 dataset, in Rp
    million per person. Coal share = B2 / TOTAL x 100, both grdp_current from the province's SIMDASI table,
    with B2 = 0 where BPS prints an en dash. The per capita line is summed provincial GRDP over Indonesia's
    population, and the coal share line summed B2 over summed TOTAL of the 38 provinces.
    """
    grdp = cells(pop, "grdp_current", TOTAL, year)
    people = cells(pop, "population", "", year)
    total = cells(industry, "grdp_current", TOTAL, year)
    coal = cells(industry, "grdp_current", COAL, year)
    # Every province has GRDP and a SIMDASI total, and population covers the provinces and Indonesia
    assert sorted(grdp.index) == provinces and sorted(total.index) == provinces
    assert sorted(people.index) == sorted(provinces + [INDONESIA])
    # The provinces without a B2 row are exactly the en-dash cells the metadata lists
    dashes = dash_cells(industry_meta, COAL, year)
    assert sorted(set(provinces) - set(coal.index)) == dashes, f"B2 rows and en-dash cells differ in {year}"
    # Both datasets give the same provincial GRDP, within BPS's rounding of 0.01 Rp billion
    assert (grdp["value"] - total.loc[grdp.index, "value"]).abs().max() <= 0.01 + 1e-9
    # Every GRDP cell used for a province carries one revision status, which the table reports
    status = {}
    for code in provinces:
        found = {grdp.at[code, "status"], total.at[code, "status"]}
        found |= {coal.at[code, "status"]} if code in coal.index else set()
        assert len(found) == 1, f"GRDP cells of {code} differ in status in {year}: {found}"
        status[code] = found.pop()
    # Indonesia lines: summed provincial GRDP over Indonesia's population, and summed B2 over summed TOTAL
    lines = {"grdp_sum": grdp["value"].sum(), "population": people.at[INDONESIA, "value"],
             "coal_sum": coal["value"].sum(), "total_sum": total["value"].sum()}
    lines["x"] = lines["grdp_sum"] / lines["population"]
    lines["y"] = lines["coal_sum"] / lines["total_sum"] * 100
    # Each province's per capita GRDP, coal output and share, en-dash marker, status and quadrant
    values = pd.DataFrame(index=pd.Index(provinces, name="province_code"))
    values["grdp_per_capita"] = grdp.loc[provinces, "value"] / people.loc[provinces, "value"]
    values["coal"] = coal["value"].reindex(provinces)
    values["grdp_simdasi"] = total.loc[provinces, "value"]
    values["coal_share_pct"] = values["coal"].fillna(0) / values["grdp_simdasi"] * 100
    values["b2_marker"] = [DASH if code in dashes else "" for code in provinces]
    values["status"] = [status[code] for code in provinces]
    values["quadrant"] = [QUADRANTS[(pc >= lines["x"], share >= lines["y"])]
                          for pc, share in zip(values["grdp_per_capita"], values["coal_share_pct"])]
    return values, lines


# Steps

# Read both datasets and their metadata, and take province names from the 20261102 metadata as Maysa's chart does
pop, industry = read_long(POP_DATASET), read_long(INDUSTRY_DATASET)
pop_meta = json.loads(POP_METADATA.read_text(encoding="utf-8"))
industry_meta = json.loads(INDUSTRY_METADATA.read_text(encoding="utf-8"))
provinces = sorted(industry_meta["provinces"])
assert len(provinces) == 38 and all(industry_meta["provinces"][c]["name"] == pop_meta["provinces"][c]["name"]
                                    for c in provinces)
names = {code: charts.display_name(pop_meta["provinces"][code]["name"]) for code in provinces}

# Stop unless the 2025 en-dash cells for B2 are the 23 provinces confirmed with the user
assert dash_cells(industry_meta, COAL, YEAR) == DASH_2025, "the 2025 en-dash B2 cells changed"

# Compute 2025 for the chart and 2024 as a check, each year against its own Indonesia lines
now, lines_now = year_values(pop, industry, industry_meta, provinces, YEAR)
then, lines_then = year_values(pop, industry, industry_meta, provinces, CHECK_YEAR)

# Build the table behind the chart, one row per province, from the most to the least coal-reliant
table = pd.DataFrame({
    "province_code": provinces,
    "province": [names[c] for c in provinces],
    "grdp_per_capita_2025": now["grdp_per_capita"].values,
    "coal_2025": now["coal"].values,
    "grdp_2025_simdasi": now["grdp_simdasi"].values,
    "coal_share_2025_pct": now["coal_share_pct"].values,
    "b2_marker_2025": now["b2_marker"].values,
    "status_2025": now["status"].values,
    "quadrant_2025": now["quadrant"].values,
    "grdp_per_capita_2024": then["grdp_per_capita"].values,
    "coal_share_2024_pct": then["coal_share_pct"].values,
    "status_2024": then["status"].values,
    "quadrant_2024": then["quadrant"].values,
})
table = table.sort_values(["coal_share_2025_pct", "province_code"], ascending=[False, True], kind="mergesort")

# Write the table: Rp values to the 2 decimals BPS publishes, shares to 6 so the smallest stay above 0
formats = {"grdp_per_capita_2025": "{:.2f}", "coal_2025": "{:.2f}", "grdp_2025_simdasi": "{:.2f}",
           "coal_share_2025_pct": "{:.6f}", "grdp_per_capita_2024": "{:.2f}", "coal_share_2024_pct": "{:.6f}"}
written = table.copy()
for column, fmt in formats.items():
    written[column] = ["" if pd.isna(v) else fmt.format(v) for v in table[column]]
written.to_csv(OUT_CSV, index=False, lineterminator="\n")

# Take the Indonesia lines of the chart year
x_cut, y_cut = lines_now["x"], lines_now["y"]

# Draw provinces with a published coal value as filled points and en-dash provinces as hollow points at 0; a hollow
# point has no fill, so a filled point beneath it stays in view
counts = table["b2_marker_2025"].value_counts()
styles = {"": {"label": f"Coal and lignite mining value published ({counts.get('', 0)} provinces)",
               "filled": True},
          DASH: {"label": f"BPS prints \"{DASH}\" (none or zero), plotted at 0 ({counts.get(DASH, 0)} provinces)",
                 "filled": False, "face": "none"}}
charts.quadrant_chart(
    table, "grdp_per_capita_2025", "coal_share_2025_pct", x_cut, y_cut, QUADRANTS,
    xlabel="GRDP per capita, 2025 (Rp million per person, log scale)",
    ylabel="Coal and lignite mining as a share of GRDP, 2025 (%)",
    title="Wealth vs coal reliance: Indonesian provinces, 2025",
    subtitle="GRDP per capita against the share of GRDP from coal and lignite mining; "
             "lines mark the Indonesia-wide values",
    note=None, path=OUT_PNG, logx=True, ylim=YLIM, yticks=YTICKS, yunit="%",
    group="b2_marker_2025", styles=styles,
    band=ZERO_BAND, low_names_at="cut", xcut_label_at="top", legend_cols=1,
    keep_quadrants=True, flag_options=FLAGS, leader=LEADER, halo=True, grow_ylim=True, lines_over_points=True,
)

# Report the Indonesia lines, each quadrant's members and the provinces whose quadrant differs in 2024
for year, lines in [(YEAR, lines_now), (CHECK_YEAR, lines_then)]:
    print(f"Indonesia {year}: per capita {lines['x']:.4f} Rp million (GRDP {lines['grdp_sum']:.2f} Rp billion / "
          f"population {lines['population']:.1f} thousand); coal share {lines['y']:.4f}% "
          f"(B2 {lines['coal_sum']:.2f} / GRDP {lines['total_sum']:.2f} Rp billion)")
for name in QUADRANTS.values():
    members = table[table["quadrant_2025"] == name]
    print(f"{name}: {len(members)}: " + ", ".join(f"{c} {n}" for c, n in zip(members["province_code"],
                                                                          members["province"])))
moved = table[table["quadrant_2025"] != table["quadrant_2024"]]
print("Quadrant differs between 2024 and 2025 (each year against its own lines):")
for _, r in moved.iterrows():
    print(f"  {r['province_code']} {r['province']}: 2024 {r['quadrant_2024']} -> 2025 {r['quadrant_2025']}")
