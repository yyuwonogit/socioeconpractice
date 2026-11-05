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
# GRDP by detailed industry from each province's BPS SIMDASI table, for the sector shares
INDUSTRY_DATASET = ROOT / "data/20261103_bps-province-grdp-detailed-industry/20261103_bps-province-grdp-detailed-industry.csv"
INDUSTRY_METADATA = (ROOT / "data/20261103_bps-province-grdp-detailed-industry/"
                     "20261103_bps-province-grdp-detailed-industry-metadata.json")

OUT_PNG = HERE / "20261103_sector-concentration.png"
OUT_CSV = HERE / "20261103_sector-concentration.csv"

# The chart's year; TOTAL is GRDP, B2 is coal and lignite mining (KBLI 05) and 00 is Indonesia
YEAR = "2025"
TOTAL, COAL, INDONESIA = "TOTAL", "B2", "00"
# BPS prints a cell with no value as an en dash, 'Tidak ada atau nol' (none or zero), which counts as 0
DASH = "–"
# Number of leaf sectors: the sectors with no sub-sector, where A1 gives way to its items A1a-A1e
LEAF_COUNT = 52
# The leaves sum to TOTAL within the rounding of the 52 leaves and TOTAL, each printed to 0.01 Rp billion
LEAF_SUM_TOLERANCE = (LEAF_COUNT + 1) * 0.005
# Both datasets give the same provincial GRDP within BPS's rounding of 0.01 Rp billion
GRDP_TOLERANCE = 0.01 + 1e-9
# The one value cell BPS prints with no status marker, a published 0 that the metadata notes
UNMARKED_CELLS = [("81", "C13")]

# Y cut fixed by the user: the index of an economy split into 10 equal sectors. Indonesia as a whole is far lower,
# so the line is not the national value
Y_CUT = 0.10
# Provinces printed as sitting near that line
NEAR_LINE = 0.005

# Coal producers: coal mining at least 1% of GRDP, which the data must give as exactly these 8 provinces
COAL_MIN_PCT = 1.0
COAL_PROVINCES = ["11", "15", "16", "17", "62", "63", "64", "65"]

# Quadrant names by (at or above the per capita line, at or above the concentration line)
QUADRANTS = {(True, True): "Rich & concentrated", (False, True): "Poorer & concentrated",
             (True, False): "Rich & diversified", (False, False): "Poorer & diversified"}

# Ticks of the log Y axis, in the 1-1.5-2-3-5 steps the module uses for a log X axis
YTICKS = [0.05, 0.075, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5]

# A band above every point: it flags no point, but with a band the chart module fixes the plot's place before it
# measures any label, and keeps every label clear of the cut lines, the quadrant names and the cut-line labels
EMPTY_BAND = (1.0, 1.0)

# Decimals in the table: Rp values keep two, the index and the coal share six, so the smallest share stays above 0
DECIMALS = {"grdp_per_capita_2025": 2, "hhi_2025": 6, "effective_sectors": 2, "largest_sector_pct": 2,
            "coal_pct": 6}

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


def leaf_sectors(meta):
    """Return the sector codes that are no other sector's parent, in the metadata's order."""
    parents = {s["parent"] for s in meta["sectors"].values() if s["parent"]}
    return [code for code in meta["sectors"] if code not in parents]


def herfindahl(shares):
    """Return the Herfindahl index of shares that sum to about 1: the sum of each share squared."""
    return (shares ** 2).sum(axis=1)


# Steps

# Read both datasets and their metadata, and take province names from the 20261102 metadata as Maysa's chart does
pop, industry = read_long(POP_DATASET), read_long(INDUSTRY_DATASET)
pop_meta = json.loads(POP_METADATA.read_text(encoding="utf-8"))
industry_meta = json.loads(INDUSTRY_METADATA.read_text(encoding="utf-8"))
provinces = sorted(industry_meta["provinces"])
assert len(provinces) == 38 and all(industry_meta["provinces"][c]["name"] == pop_meta["provinces"][c]["name"]
                                    for c in provinces)
names = {code: charts.display_name(pop_meta["provinces"][code]["name"]) for code in provinces}

# Find the 52 leaf sectors, so each part of GRDP is counted once
leaves = leaf_sectors(industry_meta)
assert len(leaves) == LEAF_COUNT and "A1" not in leaves and TOTAL not in leaves and COAL in leaves
sector_names = {code: s["name"] for code, s in industry_meta["sectors"].items()}

# Lay out each province's 2025 GRDP by sector, with each sector's status beside it
rows = industry[(industry["indicator"] == "grdp_current") & (industry["period"] == YEAR)]
values = rows.pivot(index="province_code", columns="sector", values="value").reindex(index=provinces)
statuses = rows.pivot(index="province_code", columns="sector", values="status").reindex(index=provinces)
assert values[TOTAL].notna().all(), "a province lacks its 2025 TOTAL"

# Check that the leaf cells without a row are exactly the en-dash cells the metadata lists, then count them as 0
listed = industry_meta["none_or_zero_cells"]
assert listed["marker"] == DASH
dashes = {(c["province_code"], c["sector"]) for c in listed["cells"] if c["period"] == YEAR and c["sector"] in leaves}
missing = {(p, s) for p in provinces for s in leaves if pd.isna(values.at[p, s])}
assert missing == dashes, f"leaf cells without a row differ from the en-dash cells: {sorted(missing ^ dashes)}"
parts = values[leaves].fillna(0.0)
assert (parts >= 0).all().all(), "a leaf sector has a negative value"

# Check that the leaves sum to TOTAL in every province, so the shares cover all of GRDP
leaf_gap = (parts.sum(axis=1) - values[TOTAL]).abs()
assert leaf_gap.max() <= LEAF_SUM_TOLERANCE, leaf_gap.sort_values().tail(3).to_dict()

# Take each province's revision status from its leaf cells and TOTAL, skipping the published 0 BPS prints unmarked
unmarked = sorted((p, s) for p in provinces for s in leaves if (p, s) not in dashes and statuses.at[p, s] == "")
assert unmarked == UNMARKED_CELLS and all(values.at[p, s] == 0 for p, s in unmarked), unmarked
grdp = cells(pop, "grdp_current", TOTAL, YEAR)
status = {}
for code in provinces:
    found = {statuses.at[code, s] for s in leaves + [TOTAL] if (code, s) not in dashes and (code, s) not in unmarked}
    found.add(grdp.at[code, "status"])
    assert len(found) == 1, f"GRDP cells of {code} differ in status in {YEAR}: {found}"
    status[code] = found.pop()

# Per capita GRDP from the 20261102 dataset, as in Maysa's chart: TOTAL (Rp billion) / population (thousand)
people = cells(pop, "population", "", YEAR)
assert sorted(grdp.index) == provinces and sorted(people.index) == sorted(provinces + [INDONESIA])
assert (grdp.loc[provinces, "value"] - values[TOTAL]).abs().max() <= GRDP_TOLERANCE, "the two GRDP sources differ"
per_capita = grdp.loc[provinces, "value"] / people.loc[provinces, "value"]

# Herfindahl index of each province: every leaf's share of TOTAL, squared and summed; 1 / index is the number of
# equal sectors that would give the same index
shares = parts.div(values[TOTAL], axis=0)
hhi = herfindahl(shares)

# Indonesia as a whole: each leaf summed over the 38 provinces as a share of their summed TOTAL
indonesia_shares = parts.sum() / values[TOTAL].sum()
indonesia_hhi = herfindahl(indonesia_shares.to_frame().T).iloc[0]

# Each province's largest leaf sector, which must be a clear maximum, and its coal share
largest = shares.idxmax(axis=1)
assert all((shares.loc[p] == shares.at[p, largest[p]]).sum() == 1 for p in provinces), "a tie for largest sector"
coal_pct = shares[COAL] * 100

# Check from the data that exactly the 8 stated provinces have coal mining at least 1% of GRDP
producers = sorted(coal_pct.index[coal_pct >= COAL_MIN_PCT])
assert producers == COAL_PROVINCES, f"coal producers changed: {producers}"

# Cut lines: per capita at Indonesia's (summed provincial GRDP over Indonesia's population) and the fixed index
x_cut = grdp.loc[provinces, "value"].sum() / people.at[INDONESIA, "value"]

# Build the table behind the chart, one row per province, from the most to the least concentrated
table = pd.DataFrame({
    "province_code": provinces,
    "province": [names[c] for c in provinces],
    "grdp_per_capita_2025": per_capita.values,
    "hhi_2025": hhi.values,
    "effective_sectors": (1 / hhi).values,
    "largest_sector": largest.values,
    "largest_sector_name": [sector_names[s] for s in largest],
    "largest_sector_pct": [shares.at[p, largest[p]] * 100 for p in provinces],
    "coal_pct": coal_pct.values,
    "coal_producer": ["yes" if c in COAL_PROVINCES else "no" for c in provinces],
    "status_2025": [status[c] for c in provinces],
})
table["quadrant"] = [QUADRANTS[(pc >= x_cut, h >= Y_CUT)] for pc, h in zip(table["grdp_per_capita_2025"],
                                                                         table["hhi_2025"])]
table = table.sort_values(["hhi_2025", "province_code"], ascending=[False, True], kind="mergesort")

# Write the table with fixed decimals
written = table.copy()
for column, places in DECIMALS.items():
    written[column] = table[column].map(lambda v, p=places: f"{v:.{p}f}")
written.to_csv(OUT_CSV, index=False, lineterminator="\n")

# Label each point with the province's name, and a coal producer's with its coal share
table["label"] = [f"{name} (coal {share:.0f}%)" if flag == "yes" else name
                  for name, share, flag in zip(table["province"], table["coal_pct"], table["coal_producer"])]

# Draw coal producers as filled near-black points and every other province in the series colour
count = int((table["coal_producer"] == "yes").sum())
styles = {"yes": {"label": f"Coal mining at least {COAL_MIN_PCT:.0f}% of GRDP ({count} provinces)",
                  "filled": True, "color": charts.TEXT_PRIMARY},
          "no": {"label": f"Other provinces ({len(table) - count})", "filled": True}}
charts.quadrant_chart(
    table, "grdp_per_capita_2025", "hhi_2025", x_cut, Y_CUT, QUADRANTS,
    xlabel="GRDP per capita, 2025 (Rp million per person, log scale)",
    ylabel=f"Concentration of GRDP across {LEAF_COUNT} sectors, 2025 (Herfindahl index, log scale)",
    title="Wealth vs economic concentration: Indonesian provinces, 2025",
    subtitle=f"GRDP per capita against how concentrated GRDP is across {LEAF_COUNT} sectors; "
             f"lines mark Indonesia's per capita and an index of {Y_CUT:.2f}",
    note=None, path=OUT_PNG, logx=True, logy=True, yticks=YTICKS,
    ycut_label="HHI {:.2f}", label="label", group="coal_producer", styles=styles,
    band=EMPTY_BAND, keep_quadrants=True, halo=True, lines_over_points=True,
)

# Report the lines, the quadrants and their members, and the provinces near the concentration line
print(f"X cut: Indonesia per capita {x_cut:.4f} Rp million (GRDP {grdp.loc[provinces, 'value'].sum():.2f} Rp billion "
      f"/ population {people.at[INDONESIA, 'value']:.1f} thousand)")
print(f"Y cut: HHI {Y_CUT:.2f}, fixed. Indonesia as a whole (summed provinces): HHI {indonesia_hhi:.6f}, "
      f"{1 / indonesia_hhi:.2f} effective sectors, below every province (lowest {hhi.min():.6f})")
print(f"Leaves sum to TOTAL within {leaf_gap.max():.3f} Rp billion")
for name in QUADRANTS.values():
    members = table[table["quadrant"] == name]
    print(f"{name} ({len(members)}): " + ", ".join(f"{c} {n}" for c, n in zip(members["province_code"],
                                                                         members["province"])))
print(f"Within {NEAR_LINE} of the {Y_CUT:.2f} line:")
for _, r in table[(table["hhi_2025"] - Y_CUT).abs() <= NEAR_LINE].iterrows():
    print(f"  {r['province_code']} {r['province']}: HHI {r['hhi_2025']:.6f}, {r['quadrant']}")
print("Coal producers: " + ", ".join(f"{r['province_code']} {r['province']} {r['coal_pct']:.1f}%"
                                     for _, r in table.sort_values("coal_pct", ascending=False).head(count).iterrows()))
rest = table[table["coal_producer"] == "no"].sort_values("coal_pct", ascending=False).iloc[0]
print(f"Highest other coal share: {rest['province_code']} {rest['province']} {rest['coal_pct']:.2f}%")
print("Most concentrated: " + ", ".join(f"{r['province']} {r['hhi_2025']:.3f} ({r['largest_sector']} "
                                        f"{r['largest_sector_pct']:.1f}%)" for _, r in table.head(7).iterrows()))
