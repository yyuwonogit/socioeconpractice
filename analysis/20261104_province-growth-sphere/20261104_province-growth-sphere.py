from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# Load the shared chart module from tools/
import sys
sys.path.insert(0, str(ROOT / "tools"))
import charts

import json
import re

import numpy as np
import pandas as pd
from scipy import stats

# Parameters

# Datasets, all in data/: an analysis script never reads raw/
GRDP = ROOT / "data/20261103_bps-province-grdp-2010-2025/20261103_bps-province-grdp-2010-2025.csv"
INDUSTRY = ROOT / ("data/20261103_bps-province-grdp-detailed-industry-2010-2025/"
                   "20261103_bps-province-grdp-detailed-industry-2010-2025.csv")
INDUSTRY_META = ROOT / ("data/20261103_bps-province-grdp-detailed-industry-2010-2025/"
                        "20261103_bps-province-grdp-detailed-industry-2010-2025-metadata.json")
POPULATION = ROOT / "data/20261102_bps-province-grdp-population/20261102_bps-province-grdp-population.csv"
POPULATION_META = ROOT / "data/20261102_bps-province-grdp-population/20261102_bps-province-grdp-population-metadata.json"
REAL_SPENDING = ROOT / "data/20261104_bps-province-real-spending/20261104_bps-province-real-spending.csv"
NOMINAL_SPENDING = ROOT / "data/20261103_bps-province-household-spending/20261103_bps-province-household-spending.csv"

# Outputs: the table behind both spheres, the check of the rebuilt Papua areas at the split, and the two sphere pages
OUT_TABLE = HERE / "20261104_growth-sphere.csv"
OUT_STEPS = HERE / "20261104_old-border-steps.csv"
OUT_REAL = HERE / "20261104_growth-sphere-real-3d.html"
OUT_NOMINAL = HERE / "20261104_growth-sphere-nominal-3d.html"

# The window the user chose: each area's growth from 2015 to 2025
START, END = 2015, 2025
YEARS = list(range(START, END + 1))
INDONESIA, TOTAL = "00", "TOTAL"

# Papua and Papua Barat at their borders before the 2022 split, as the user chose. Each dataset publishes them as one
# province up to the year before its split year; from the split year the area is the sum of the provinces carved
# from it, rebuilt here (the datasets' metadata 'borders' give these years)
OLD_BORDERS = {"91": ["91", "92"], "94": ["94", "95", "96", "97"]}
OLD_NAMES = {"91": "Papua Barat (pre-2022)", "94": "Papua (pre-2022)"}
SPLIT_YEAR = {"grdp": 2023, "industry": 2023, "real_spending": 2024, "nominal_spending": 2024}

# The extractive groups the user set, as BPS sector codes of GRDP by detailed industry
GROUPS = {
    "fossil": {"name": "Fossil fuels", "sectors": ["B1", "B2", "C1"], "color": "#000000"},
    "metals": {"name": "Metals", "sectors": ["B3", "C11"], "color": "#CC79A7"},
    "plantation": {"name": "Plantation", "sectors": ["A1c"], "color": "#009E73"},
    "forest": {"name": "Forest", "sectors": ["A2", "C6", "C7"], "color": "#E69F00"},
    "quarrying": {"name": "Quarrying", "sectors": ["B4", "C10"], "color": "#0072B2"},
}
# Food and beverage manufacturing (C2) holds the palm oil mills. It counts with plantation, in every year, for an area
# whose estate crops (A1c) average at least this share of GRDP over 2015-2025: the rule fixed per area, as the user
# chose, so a year-to-year switch cannot show up as a jump in the share
MILLS_SECTOR, MILLS_BASE, MILLS_MIN_PCT = "C2", "A1c", 10.0
# An area whose largest extractive group is under this share of GRDP in 2025 is drawn grey, in a group of its own
MIN_GROUP_PCT = 5.0
LOW, LOW_LABEL, LOW_COLOR = "low", "No group above 5% of GRDP", charts.TEXT_MUTED

# The spheres: x is the change in the extractive share, cut at 0 (the share rose or fell); y is spending growth and z
# GRDP growth per person, each cut at Indonesia's own growth. The real sphere sets real GRDP against BPS real
# spending; the nominal sphere sets GRDP at current prices against Susenas spending at current prices
X_ENDS = ("More extractive", "Less extractive")
Z_ENDS = ("GRDP per person grew faster", "GRDP per person grew slower")
VERSIONS = {
    "real": {"grdp": "grdp_real_growth", "spending": "real_spending_growth", "out": OUT_REAL,
             "title": "GRDP growth, extraction and real household spending: Indonesian provinces, 2015–2025",
             "y_ends": ("Real spending grew faster", "Real spending grew slower"),
             "grdp_tip": "GRDP per person: {:+.1f}% a year (2010 prices)",
             "spending_tip": "Real spending per person: {:+.1f}% a year (2012 prices)"},
    "nominal": {"grdp": "grdp_nominal_growth", "spending": "nominal_spending_growth", "out": OUT_NOMINAL,
                "title": "GRDP growth, extraction and household spending at current prices: Indonesian provinces, "
                         "2015–2025",
                "y_ends": ("Spending grew faster", "Spending grew slower"),
                "grdp_tip": "GRDP per person: {:+.1f}% a year (current prices)",
                "spending_tip": "Spending per person: {:+.1f}% a year (current prices)"},
}
# Zone colours keyed (GRDP grew faster, spending grew slower, more extractive): warm where GRDP grew faster than
# Indonesia, cool where slower, darkest where spending grew slower and the share rose
ZONE_COLORS = {(True, True, True): "#b2182b", (True, True, False): "#ef8a62", (True, False, True): "#d6604d",
               (True, False, False): "#fddbc7", (False, True, True): "#2166ac", (False, True, False): "#67a9cf",
               (False, False, True): "#4393c3", (False, False, False): "#d1e5f0"}
MODES = [("zone", "Zone"), ("group", "Extractive group")]
LEGEND_TITLE = "Largest extractive group, 2025"

# Functions

def read_long(path):
    """Read a long dataset with codes, periods and statuses as text, so '00' and empty statuses survive."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df["value"] = df["value"].astype(float)
    return df


def wide(df, indicator):
    """Return one indicator as a table of areas by year (int), stopping if a cell repeats."""
    rows = df[df["indicator"] == indicator]
    assert not rows.duplicated(["province_code", "period"]).any(), f"{indicator}: repeated cells"
    table = rows.pivot(index="province_code", columns="period", values="value")
    table.columns = table.columns.astype(int)
    return table


def year_set(text):
    """Return the years of a metadata range such as '2014, 2016-2025'."""
    years = set()
    for part in text.split(","):
        first, _, last = part.strip().partition("-")
        years.update(range(int(first), int(last or first) + 1))
    return years


def growth(first, last):
    """Return average growth in % a year from START to END."""
    return ((last / first) ** (1 / (END - START)) - 1) * 100


def weighted(values, weights):
    """Return the mean of values weighted by weights, both indexed by province."""
    return float((values * weights).sum() / weights.sum())


def ancestors(code, parents):
    """Return every sector above a sector in the metadata's tree."""
    above = []
    while parents.get(code):
        code = parents[code]
        above.append(code)
    return above


def zone_of(faster, slower, more):
    """Return the name of the zone for one side of each cut."""
    return (f"{'Faster' if faster else 'Slower'} GRDP growth × {'more' if more else 'less'} extractive × spending grew "
            f"{'slower' if slower else 'faster'}")


def grdp_per_capita(level, population, per_capita, code, year):
    """Return GRDP per person (Rp thousand) of an area, rebuilt after the split as summed GRDP over summed population."""
    if code in OLD_BORDERS and year >= SPLIT_YEAR["grdp"]:
        members = OLD_BORDERS[code]
        return float(1000 * level.loc[members, year].sum() / population.loc[members, year].sum())
    return float(per_capita.at[code, year])


def sector_table(current, sectors, dashes, year):
    """Return Rp billion by province and sector in a year, with the listed en-dash cells as 0."""
    rows = current[current["period"] == str(year)]
    values = rows.pivot(index="province_code", columns="sector", values="value").reindex(columns=sectors)
    missing = {(p, s, year) for p in values.index for s in values.columns if pd.isna(values.at[p, s])}
    assert missing == {d for d in dashes if d[2] == year and d[0] in values.index}, f"unlisted gaps in {year}"
    return values.fillna(0.0)


def spending(table, population, split, code, year):
    """Return an area's spending per person in a year, after the split its provinces' mean weighted by population."""
    if code in OLD_BORDERS and year >= split:
        members = OLD_BORDERS[code]
        return weighted(table.loc[members, year], population.loc[members, year])
    return float(table.at[code, year])

# Steps

# Read the province names from the population dataset's metadata, which holds the BPS list
names = {code: charts.display_name(p["name"]) for code, p in
         json.loads(POPULATION_META.read_text(encoding="utf-8"))["provinces"].items()}
names.update(OLD_NAMES)
carved = [c for members in OLD_BORDERS.values() for c in members[1:]]
areas = sorted(c for c in names if c not in carved and c != INDONESIA)
assert len(areas) == 34, f"{len(areas)} areas"

# GRDP and GRDP per person at both price bases; BPS divides GRDP by its own population, which 1000 x GRDP / per capita
# gives back in thousands, so a pre-split area's per capita is its summed GRDP over its summed population
grdp = read_long(GRDP)
assert set(grdp["sector"]) == {TOTAL}
level = {"real": wide(grdp, "grdp_constant_2010"), "nominal": wide(grdp, "grdp_current")}
per_capita = {"real": wide(grdp, "grdp_per_capita_constant_2010"), "nominal": wide(grdp, "grdp_per_capita_current")}
implied = {basis: 1000 * level[basis] / per_capita[basis] for basis in level}

# Both price bases imply the same population, within the rounding of the published values
basis_gap = float((implied["real"] / implied["nominal"] - 1).abs().max().max())
assert basis_gap < 0.001, f"the price bases imply populations {basis_gap:.4%} apart"

# Population from the population dataset (thousand people), which weights the spending of the pre-split areas; it must
# agree with the population behind BPS's GRDP per capita in 2025 within 1%
population = wide(read_long(POPULATION), "population")
provinces = [c for c in names if c != INDONESIA]
population_gap = float((population.loc[provinces, END] / implied["real"].loc[provinces, END] - 1).abs().max())
assert population_gap < 0.01, f"population and GRDP per capita disagree by {population_gap:.2%}"

# GRDP at current prices by detailed industry; a cell without a row must be an en dash the metadata lists (none or
# zero), so it counts as 0, and no current-price cell of 2015-2025 may be unpublished or excluded
industry = read_long(INDUSTRY)
industry_meta = json.loads(INDUSTRY_META.read_text(encoding="utf-8"))
current = industry[industry["indicator"] == "grdp_current"]
sectors = list(industry_meta["sectors"])
parents = {code: s["parent"] for code, s in industry_meta["sectors"].items()}
dashes = {(code, sector, year) for code, cells in industry_meta["none_or_zero_cells"]["cells"]["grdp_current"].items()
          for sector, text in cells.items() for year in year_set(text)}
assert all(c["indicator"] == "grdp_constant_2010" for c in industry_meta["none_or_zero_cells"]["small_values"]["cells"])
for listed in (industry_meta["unpublished_cells"]["tables"], industry_meta["excluded"]["tables"]):
    assert not [t for t in listed if t["indicator"] == "grdp_current" and int(t["period"]) >= START]

# The extractive sectors exist, and none sits above another, so no value counts twice
extractive_sectors = [s for g in GROUPS.values() for s in g["sectors"]] + [MILLS_SECTOR]
assert set(extractive_sectors) <= set(sectors) and len(set(extractive_sectors)) == len(extractive_sectors)
assert not [s for s in extractive_sectors if set(ancestors(s, parents)) & set(extractive_sectors)]

# Each area's sector values in each year, the pre-split areas summed from their provinces after the split
tables = {year: sector_table(current, sectors, dashes, year) for year in YEARS}
area_values = {year: pd.DataFrame({code: (tables[year].loc[OLD_BORDERS[code]].sum()
                                          if code in OLD_BORDERS and year >= SPLIT_YEAR["industry"]
                                          else tables[year].loc[code]) for code in areas}).T for year in YEARS}

# The mill rule, fixed per area: C2 counts in every year where estate crops average at least 10% of GRDP
estate_share = pd.DataFrame({year: area_values[year][MILLS_BASE] / area_values[year][TOTAL] * 100 for year in YEARS})
mills = estate_share.mean(axis=1) >= MILLS_MIN_PCT

# Extractive value added and share of GRDP by area and year, and each group's share in 2025
extractive = pd.DataFrame({year: sum(area_values[year][s] for g in GROUPS.values() for s in g["sectors"])
                                 + area_values[year][MILLS_SECTOR].where(mills, 0.0) for year in YEARS})
gdp_total = pd.DataFrame({year: area_values[year][TOTAL] for year in YEARS})
share = extractive / gdp_total * 100
group_share = pd.DataFrame({g: sum(area_values[END][s] for s in spec["sectors"]) for g, spec in GROUPS.items()})
group_share["plantation"] += area_values[END][MILLS_SECTOR].where(mills, 0.0)
group_share = group_share.div(area_values[END][TOTAL], axis=0) * 100
national_share = extractive.sum() / gdp_total.sum() * 100

# Household spending per person: BPS real spending (thousand Rp a year, 2012 prices) and Susenas spending at current
# prices (Rp a month, food and non-food); a pre-split area after the split is its provinces' mean, weighted by population
real = wide(read_long(REAL_SPENDING), "real_spending_per_capita")
nominal_rows = read_long(NOMINAL_SPENDING)
nominal = wide(nominal_rows[nominal_rows["item"] == "total"], "spending_per_capita_month")

# Each area's yearly GRDP per person at both price bases and spending per person, rebuilt after the split for the
# pre-split areas, from 2015 to 2025
pc_years = {basis: {(code, year): grdp_per_capita(level[basis], implied[basis], per_capita[basis], code, year)
                    for code in areas for year in YEARS} for basis in level}
real_years = {(code, year): spending(real, population, SPLIT_YEAR["real_spending"], code, year)
              for code in areas for year in YEARS}
nominal_years = {(code, year): spending(nominal, population, SPLIT_YEAR["nominal_spending"], code, year)
                 for code in areas for year in YEARS}

# The table behind both spheres: one row per area, with its 2015 and 2025 values and their growth
rows = []
for code in areas:
    largest = group_share.loc[code].idxmax()
    row = {"area_code": code, "area": names[code],
           "borders": "pre-2022: " + " + ".join(OLD_BORDERS[code]) + " after the split" if code in OLD_BORDERS else "",
           "grdp_pc_real_2015": pc_years["real"][(code, START)], "grdp_pc_real_2025": pc_years["real"][(code, END)],
           "grdp_pc_current_2015": pc_years["nominal"][(code, START)],
           "grdp_pc_current_2025": pc_years["nominal"][(code, END)],
           "extractive_share_2015": share.at[code, START], "extractive_share_2025": share.at[code, END],
           "mills_counted": bool(mills[code]),
           "largest_group_2025": largest if group_share.at[code, largest] >= MIN_GROUP_PCT else LOW,
           "largest_group_share_2025": group_share.at[code, largest],
           "real_spending_2015": real_years[(code, START)], "real_spending_2025": real_years[(code, END)],
           "nominal_spending_2015": nominal_years[(code, START)], "nominal_spending_2025": nominal_years[(code, END)]}
    rows.append(row)
table = pd.DataFrame(rows)

# Indonesia's reference values: GRDP per person and spending from BPS's national rows (national GDP throughout
# 2015-2025), and the extractive share of all provinces summed
nation = {"area_code": INDONESIA, "area": "Indonesia", "borders": "",
          "grdp_pc_real_2015": per_capita["real"].at[INDONESIA, START],
          "grdp_pc_real_2025": per_capita["real"].at[INDONESIA, END],
          "grdp_pc_current_2015": per_capita["nominal"].at[INDONESIA, START],
          "grdp_pc_current_2025": per_capita["nominal"].at[INDONESIA, END],
          "extractive_share_2015": national_share[START], "extractive_share_2025": national_share[END],
          "real_spending_2015": real.at[INDONESIA, START], "real_spending_2025": real.at[INDONESIA, END],
          "nominal_spending_2015": nominal.at[INDONESIA, START], "nominal_spending_2025": nominal.at[INDONESIA, END]}
table = pd.concat([table, pd.DataFrame([nation])], ignore_index=True)

# Growth in % a year and the change in the extractive share in points
for out, first, last in (("grdp_real_growth", "grdp_pc_real_2015", "grdp_pc_real_2025"),
                         ("grdp_nominal_growth", "grdp_pc_current_2015", "grdp_pc_current_2025"),
                         ("real_spending_growth", "real_spending_2015", "real_spending_2025"),
                         ("nominal_spending_growth", "nominal_spending_2015", "nominal_spending_2025")):
    table[out] = growth(table[first], table[last])
table["extractive_change"] = table["extractive_share_2025"] - table["extractive_share_2015"]
assert table.drop(columns=["borders", "mills_counted", "largest_group_2025", "largest_group_share_2025"]).notna().all().all()

# The check of the rebuilt areas: the step from the last published pre-split year to the first rebuilt year, beside the
# area's typical yearly step since 2015, for every rebuilt series
steps = []
share_years = {(code, year): float(share.at[code, year]) for code in areas for year in YEARS}
series = {"grdp_pc_real (% change)": (SPLIT_YEAR["grdp"], pc_years["real"], "pct"),
          "extractive_share (points)": (SPLIT_YEAR["industry"], share_years, "points"),
          "real_spending (% change)": (SPLIT_YEAR["real_spending"], real_years, "pct"),
          "nominal_spending (% change)": (SPLIT_YEAR["nominal_spending"], nominal_years, "pct")}
for code in OLD_BORDERS:
    for label, (split, values, kind) in series.items():
        path = [values[(code, y)] for y in range(START, split + 1)]
        moves = [(b / a - 1) * 100 if kind == "pct" else b - a for a, b in zip(path, path[1:])]
        steps.append({"area_code": code, "series": label, "from_year": split - 1, "to_year": split,
                      "from_value": round(path[-2], 4), "to_value": round(path[-1], 4), "step": round(moves[-1], 3),
                      "median_abs_step_before": round(float(np.median(np.abs(moves[:-1]))), 3)})
steps = pd.DataFrame(steps)

# Write the table and the step check, with LF line endings
numeric = table.select_dtypes("number").columns
table[numeric] = table[numeric].round(4)
table.to_csv(OUT_TABLE, index=False, lineterminator="\n")
steps.to_csv(OUT_STEPS, index=False, lineterminator="\n")

# Draw both spheres from the 34 areas, each cut through its references
points_table = table[table["area_code"] != INDONESIA].reset_index(drop=True)
reference = table[table["area_code"] == INDONESIA].iloc[0]
group_labels = {**{g: s["name"] for g, s in GROUPS.items()}, LOW: LOW_LABEL}
group_colors = {**{g: s["color"] for g, s in GROUPS.items()}, LOW: LOW_COLOR}
for version, spec in VERSIONS.items():
    x, y, z = (points_table[c].to_numpy() for c in ("extractive_change", spec["spending"], spec["grdp"]))
    y_ref, z_ref = float(reference[spec["spending"]]), float(reference[spec["grdp"]])
    positions = charts.into_sphere(np.column_stack([charts.spread(x, 0.0), charts.spread(y, y_ref),
                                                    charts.spread(z, z_ref)]))
    keys = [(bool(f), bool(s), bool(m)) for f, s, m in zip(z >= z_ref, y < y_ref, x >= 0.0)]
    zones = [zone_of(*k) for k in keys]
    zone_colors = {zone_of(*k): ZONE_COLORS[k] for k in ZONE_COLORS}
    group_keys = points_table["largest_group_2025"].tolist()
    points = [{"name": r["area"], "pos": positions[n], "color": group_colors[r["largest_group_2025"]],
               "groups": {"zone": zones[n], "group": r["largest_group_2025"]},
               "tip": [zones[n], spec["grdp_tip"].format(r[spec["grdp"]]),
                       f"Extractive share of GRDP: {r['extractive_share_2015']:.1f}% → {r['extractive_share_2025']:.1f}% "
                       f"({r['extractive_change']:+.1f} points)",
                       spec["spending_tip"].format(r[spec["spending"]]),
                       f"Largest extractive group, 2025: {group_labels[r['largest_group_2025']]}"
                       f" ({r['largest_group_share_2025']:.1f}% of GRDP)"]
                      + (["Borders before the 2022 split"] if r["area_code"] in OLD_BORDERS else [])}
              for n, r in points_table.iterrows()]
    groups = {"zone": charts.sphere_groups(zones, {zn: zn for zn in zones}, zone_colors, positions),
              "group": charts.sphere_groups(group_keys, group_labels, group_colors, positions)}
    legend = [(group_labels[g], group_colors[g]) for g in [*GROUPS, LOW] if g in group_keys]
    charts.write_sphere_page(spec["out"], spec["title"], [X_ENDS, spec["y_ends"], Z_ENDS], points, groups, MODES,
                             LEGEND_TITLE, legend)

    # Report the test: how many areas fall in each zone, and how spending growth ranks against the other two axes
    print(f"\n== {version} sphere: Indonesia GRDP per person {z_ref:+.2f}% a year, spending {y_ref:+.2f}% a year, "
          f"extractive share {reference['extractive_share_2015']:.2f}% -> {reference['extractive_share_2025']:.2f}%")
    for zone, count in pd.Series(zones).value_counts().items():
        members = [points_table.at[n, "area"] for n, zn in enumerate(zones) if zn == zone]
        print(f"  {count:2d}  {zone}: {', '.join(members)}")
    fell = points_table.loc[points_table[spec["spending"]] < 0, "area"].tolist()
    print(f"  spending per person fell in {len(fell)} of {len(points_table)} areas{': ' + ', '.join(fell) if fell else ''}")
    for a, b in (("extractive_change", spec["spending"]), (spec["grdp"], spec["spending"]),
                 ("extractive_change", spec["grdp"])):
        rho, p = stats.spearmanr(points_table[a], points_table[b])
        print(f"  Spearman {a} vs {b}: rho {rho:+.2f} (p {p:.3f}, n {len(points_table)})")
    gap = points_table[spec["spending"]] - points_table[spec["grdp"]]
    rho, p = stats.spearmanr(points_table["extractive_change"], gap)
    print(f"  Spearman extractive_change vs (spending growth - GRDP growth): rho {rho:+.2f} (p {p:.3f})")

# Report the checks behind the rebuilt areas and the mill rule
print(f"\nprice bases imply populations at most {basis_gap:.4%} apart; population dataset vs GRDP per capita "
      f"population in {END}: at most {population_gap:.3%} apart")
print("mill rule counts C2 for:", ", ".join(names[c] for c in mills[mills].index))
print(steps.to_string(index=False))
