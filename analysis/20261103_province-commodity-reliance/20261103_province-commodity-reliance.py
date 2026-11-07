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
import numpy as np
import pandas as pd

# Parameters

# GRDP and population for per capita, the same data as the 20261102 wealth-vs-momentum chart
POP_DATASET = ROOT / "data/20261102_bps-province-grdp-population/20261102_bps-province-grdp-population.csv"
POP_METADATA = ROOT / "data/20261102_bps-province-grdp-population/20261102_bps-province-grdp-population-metadata.json"
# GRDP by detailed industry from each province's BPS SIMDASI table, for the commodity shares
INDUSTRY_DATASET = ROOT / "data/20261103_bps-province-grdp-detailed-industry/20261103_bps-province-grdp-detailed-industry.csv"
INDUSTRY_METADATA = (ROOT / "data/20261103_bps-province-grdp-detailed-industry/"
                     "20261103_bps-province-grdp-detailed-industry-metadata.json")

OUT_PNG = HERE / "20261103_commodity-reliance.png"
OUT_CSV = HERE / "20261103_commodity-reliance.csv"

# Gini ratio by province from BPS Susenas, the third axis of the 3D chart: the total (urban and rural) ratio of the
# March 2025 round, the round chosen for inequality in this work
GINI_DATASET = ROOT / "data/20261103_bps-province-gini/20261103_bps-province-gini.csv"
GINI_PERIOD, GINI_AREA = "2025S1", "total"
# The line between more and less unequal: a Gini ratio of 0.30, the equality threshold of 'A good life for all within
# planetary boundaries' (O'Neill, Fanning, Lamb and Steinberger 2018, Nature Sustainability), where an equality score
# (1 - Gini) x 100 of at least 70 meets the threshold. The paper sets it on the Gini of household disposable income;
# BPS measures household spending, which is usually more evenly spread, so on BPS data the line is if anything lenient
GINI_LINE = 0.30
# Household spending per person from BPS Susenas (static table 945), the third axis of the second sphere: total (food and
# non-food) monthly spending in 2025, rupiah at current prices, against Indonesia's average
SPENDING_DATASET = ROOT / "data/20261103_bps-province-household-spending/20261103_bps-province-household-spending.csv"
SPENDING_PERIOD, SPENDING_ITEM = "2025", "total"

# The 3D charts: a static PNG of the three measures on their own axes, and an interactive page that shows them as a
# sphere drawn with three.js, rotates, and adds a province's constellation (its zone or its commodity group) when it
# is clicked. The page is one file; the browser loads three.js from a CDN at a pinned version
OUT_3D_PNG = HERE / "20261103_commodity-reliance-gini-3d.png"
OUT_3D_HTML = HERE / "20261103_commodity-reliance-gini-3d.html"
OUT_SPENDING_HTML = HERE / "20261103_commodity-reliance-spending-3d.html"
THREE_URL = "https://cdn.jsdelivr.net/npm/three@0.160.0"
# Axis ranges of the 3D chart: the Gini ratio (March 2025 runs from 0.222 to 0.441) and the commodity share
ZLIM_3D, YLIM_3D = (0.20, 0.46), (0.0, 70.0)
# Viewing angle of the static 3D chart, in degrees
VIEW = {"elev": 18, "azim": -62}

# The interactive charts are spheres centred on the three lines: x runs left to right toward more commodity-reliant, z
# upward toward richer, and y front to back along the page's third measure. Names at the high and low end of x and z
AXIS_ENDS = {"x": ("More commodity-reliant", "More diverse"), "z": ("Richer", "Poorer")}
# The third measure of each sphere page: its column; its axis-end and zone words; which end the darkest zone colours
# mark ('bad_high': the high end for inequality, the low end for household spending, where the user's hunch points);
# whether its words come before the commodity words in a zone name; the page title; the hover text; the output file
THIRD_MEASURES = {
    "gini": {"column": "gini_2025s1", "ends": ("More unequal", "Less unequal"),
             "sides": ("more unequal", "less unequal"), "bad_high": True, "third_first": True,
             "title": "Rich, commodity-reliant and unequal: Indonesian provinces, 2025",
             "hover": "Gini ratio (March 2025): {:.3f}", "out": OUT_3D_HTML},
    "spending": {"column": "spending_2025", "ends": ("Households spend more", "Households spend less"),
                 "sides": ("households spend more", "households spend less"), "bad_high": False, "third_first": False,
                 "title": "Wealth, commodity reliance and household spending: Indonesian provinces, 2025",
                 "hover": "Household spending: Rp {:,.0f} a month per person (2025)", "out": OUT_SPENDING_HTML},
}
# Provinces reach this share of the sphere's radius, so none sits on its surface
POINT_REACH = 0.94
# The colour of each zone's constellation, keyed (rich, on the third measure's darker end, commodity-reliant): warm for
# richer than Indonesia, cool for poorer, darkest on the third measure's darker end and commodity-reliant
ZONE_COLORS = {(True, True, True): "#b2182b", (True, True, False): "#ef8a62", (True, False, True): "#d6604d",
               (True, False, False): "#fddbc7", (False, True, True): "#2166ac", (False, True, False): "#67a9cf",
               (False, False, True): "#4393c3", (False, False, False): "#d1e5f0"}
# Camera from the front-right and a little above, at this distance from the centre: x runs mostly left to right, z points
# up, and the front-to-back third axis stays visible as a diagonal instead of pointing at the viewer
CAMERA_DIRECTION, CAMERA_DISTANCE = {"x": 1.1, "y": -1.8, "z": 0.75}, 5.6
# Provinces named in the static 3D chart, where 38 names would cover each other: every province at or above the 20%
# line, every one with a Gini ratio of at least this value, and every one with per capita of at least this many
# Rp million; the interactive chart names all 38
LABEL_GINI_MIN, LABEL_PC_MIN = 0.38, 150.0
# Static 3D labels that would sit on a neighbour's: which side of the point each one goes, and its height above (or
# below, when negative) the point in Gini units
LABEL_PLACE = {"32": ("right", 0.006), "75": ("left", 0.006), "95": ("center", 0.010),
               "96": ("right", 0.006), "31": ("left", 0.006), "72": ("right", -0.016), "64": ("left", 0.006),
               "12": ("right", 0.006), "62": ("left", -0.016), "15": ("left", 0.008)}
# Size of the static 3D box inside the figure
ZOOM_3D = 1.08

# The chart's year; TOTAL is GRDP and 00 is Indonesia
YEAR, TOTAL, INDONESIA = "2025", "TOTAL", "00"
# BPS prints a cell with no value as an en dash, 'Tidak ada atau nol' (none or zero), which counts as 0
DASH = "–"
# The 52 leaf sectors sum to TOTAL within BPS's rounding of every row to 0.01 Rp billion; the largest gap in 2025 is
# 0.06 Rp billion
LEAF_TOLERANCE = 0.1

# Each commodity is its raw production (mining or farming) plus the local first processing that BPS records in a
# manufacturing sub-category of its own, as BPS sector codes, in the order the table lists them
COMMODITIES = {
    # Metal ore mining (nickel, copper, gold, tin, bauxite) plus basic metals, which hold the nickel, copper and tin
    # smelters
    "metals": {"name": "Metals", "raw": ["B3"], "processing": ["C11"]},
    # Oil, gas and geothermal extraction plus coal and oil refining (C1), which holds the oil refineries and LNG
    # plants; C1's coal products, such as coke and briquettes, are small next to them, so the whole of C1 counts here
    "oil_gas": {"name": "Oil & gas", "raw": ["B1"], "processing": ["C1"]},
    # Coal and lignite mining, with no processing part: the coal products in C1 count with oil and gas
    "coal": {"name": "Coal", "raw": ["B2"], "processing": []},
    # Other mining and quarrying: sand, stone, clay and limestone
    "quarrying": {"name": "Quarrying", "raw": ["B4"], "processing": []},
    # Food crops: rice, maize, cassava and soybeans
    "food_crops": {"name": "Food crops", "raw": ["A1a"], "processing": []},
    # Horticulture: vegetables, fruit and ornamental plants
    "horticulture": {"name": "Horticulture", "raw": ["A1b"], "processing": []},
    # Livestock and its products
    "livestock": {"name": "Livestock", "raw": ["A1d"], "processing": []},
    # Forestry and logging
    "forestry": {"name": "Forestry", "raw": ["A2"], "processing": []},
    # Capture fisheries and aquaculture
    "fisheries": {"name": "Fisheries", "raw": ["A3"], "processing": []},
    # Estate crops (palm oil, rubber, coffee, cocoa) plus food and beverage manufacturing, which holds the palm oil
    # mills, counted only under the MILLS_MIN_PCT rule below
    "estate_crops": {"name": "Estate crops", "raw": ["A1c"], "processing": ["C2"]},
}
# Agricultural services and hunting (A1e) serve every crop and belong to no single commodity, so they are left out
LEFT_OUT = ["A1e"]
# The sectors of farming (A) and mining (B), every leaf of which is a commodity's raw part or left out
PRIMARY = ["A", "B"]
# Food and beverage manufacturing (C2), the processing part of estate crops, holds the palm oil mills, which press
# the fruit where it is grown, but also every other food and drink factory. It counts only where estate crops (A1c)
# are at least this share of GRDP, so that the mills are likely to be most of it; elsewhere, as in Java, C2 is mainly
# other food industry and is left out
MILLS_COMMODITY, MILLS_MIN_PCT = "estate_crops", 10.0
# The provinces that rule adds C2 to in 2025: Riau, Sulawesi Barat, Kalimantan Tengah, Jambi, Sumatera Utara,
# Kalimantan Barat and Aceh
MILLS_PROVINCES = ["14", "76", "62", "15", "12", "61", "11"]

# Y cut line at 20% of GRDP from one commodity, as the user chose
Y_CUT = 20.0
# Quadrant names by (at or above the per capita line, at or above the 20% line)
QUADRANTS = {(True, True): "Rich & commodity-reliant", (False, True): "Poorer & commodity-reliant",
             (True, False): "Rich & less commodity-reliant", (False, False): "Poorer & less commodity-reliant"}

# Colour of each largest commodity, from the Okabe-Ito palette, which stays distinct under the common forms of colour
# blindness; its yellow is left out because it fades on the light surface. A largest commodity without a colour stops
# the script, so a new one gets its colour on purpose
COLORS = {"coal": "#000000", "metals": "#CC79A7", "oil_gas": "#D55E00", "estate_crops": "#009E73",
          "food_crops": "#E69F00", "fisheries": "#56B4E9", "livestock": "#0072B2"}
# Provinces whose largest commodity is under this share of GRDP are drawn in grey in a group of their own
MIN_SHARE_PCT = 5.0
LOW, LOW_LABEL, GREY = "none_above_5", "No commodity above 5%", charts.TEXT_MUTED

# Y axis in %, from 0 to just above Papua Tengah's 66.4%. It reaches a little below 0 so that Jakarta's point (0.3%)
# sits above the names of the two bottom quadrants, and the ticks run from 0
YLIM = (-4.0, 70.0)
YTICKS = [0, 10, 20, 30, 40, 50, 60, 70]

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
    """Return the sectors with no child in the metadata, and each sector's parent."""
    parents = {code: s["parent"] for code, s in meta["sectors"].items()}
    return [code for code in parents if code != TOTAL and code not in parents.values()], parents


def under(code, ancestor, parents):
    """Return True when a sector sits below an ancestor sector in the metadata's tree."""
    while parents[code] is not None:
        code = parents[code]
        if code == ancestor:
            return True
    return False


def sector_table(industry, meta, provinces, year):
    """Return grdp_current by province and sector in a year, Rp billion, with en-dash cells as 0, and the statuses.

    Every cell the metadata lists as an en dash has no row and becomes 0; every other cell of the 38 provinces and
    62 sectors must have a row.
    """
    rows = industry[(industry["indicator"] == "grdp_current") & (industry["period"] == year)]
    values = rows.pivot(index="province_code", columns="sector", values="value")
    status = rows.pivot(index="province_code", columns="sector", values="status")
    listed = meta["none_or_zero_cells"]
    assert listed["marker"] == DASH
    dashes = {(c["province_code"], c["sector"]) for c in listed["cells"] if c["period"] == year}
    # The missing cells are exactly the en-dash cells the metadata lists
    values = values.reindex(index=provinces, columns=list(meta["sectors"]))
    missing = {(p, s) for p in values.index for s in values.columns if pd.isna(values.at[p, s])}
    assert missing == dashes, f"cells without a row differ from the en-dash cells in {year}"
    return values.fillna(0.0), status.reindex(index=provinces, columns=list(meta["sectors"]))


def log_tick_values(low, high):
    """Return the round per capita values (Rp million) that fall inside a log axis from low to high."""
    return [v for v in [10, 20, 30, 50, 75, 100, 150, 200, 300, 400, 500] if low <= v <= high]


def draw_3d_png(table, styles, x_cut, gini_line, path):
    """Draw the static 3D chart: per capita (log), largest commodity share and Gini ratio, coloured by commodity.

    Each point stands on a thin stem from the floor, whose foot marks its place on the flat chart; the floor carries
    the two cut lines of the flat chart, and a faint plane marks Indonesia's Gini ratio.
    """
    lx = np.log10(table["grdp_per_capita_2025"].to_numpy())
    y, z = table["largest_commodity_pct"].to_numpy(), table["gini_2025s1"].to_numpy()
    xlim = (np.log10(table["grdp_per_capita_2025"].min() / 1.15), np.log10(table["grdp_per_capita_2025"].max() * 1.15))
    with plt.rc_context({"grid.color": charts.GRID, "grid.linewidth": 0.6}):
        fig = plt.figure(figsize=(14, 10), dpi=200)
        fig.patch.set_facecolor(charts.SURFACE)
        ax = fig.add_subplot(projection="3d", computed_zorder=False)
        ax.set_facecolor(charts.SURFACE)
        ax.set_position([-0.02, 0.0, 0.9, 0.94])
        for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
            axis.set_pane_color((0.985, 0.985, 0.98, 1.0))
            axis.pane.set_edgecolor(charts.GRID)
        ax.set_xlim(*xlim)
        ax.set_ylim(*YLIM_3D)
        ax.set_zlim(*ZLIM_3D)
        ax.set_box_aspect((1.35, 1.0, 0.8), zoom=ZOOM_3D)

        # Draw the floor's cut lines (Indonesia's per capita and the 20% line) and Indonesia's Gini plane
        floor = ZLIM_3D[0]
        ax.plot([np.log10(x_cut)] * 2, YLIM_3D, [floor] * 2, color=charts.CUT, lw=1.0, ls="--", zorder=1)
        ax.plot(xlim, [Y_CUT] * 2, [floor] * 2, color=charts.CUT, lw=1.0, ls="--", zorder=1)
        px, py = np.meshgrid(xlim, YLIM_3D)
        ax.plot_surface(px, py, np.full_like(px, gini_line), color=charts.SERIES, alpha=0.07, shade=False, zorder=1)
        ax.text(xlim[1], YLIM_3D[1], gini_line + 0.004, f"Good-life Gini line {gini_line:.2f}", fontsize=8,
                color=charts.TEXT_MUTED, ha="right", zorder=2)

        # Draw each point's stem from the floor, its foot on the floor, then the points by commodity group
        for xi, yi, zi in zip(lx, y, z):
            ax.plot([xi, xi], [yi, yi], [floor, zi], color="#b9b8b3", lw=0.8, zorder=2)
        ax.scatter(lx, y, np.full(len(lx), floor), s=9, color="#c9c8c4", depthshade=False, zorder=2)
        for key, style in styles.items():
            part = table[table["group"] == key]
            ax.scatter(np.log10(part["grdp_per_capita_2025"]), part["largest_commodity_pct"], part["gini_2025s1"],
                       s=70, color=style["color"], edgecolors=charts.SURFACE, linewidths=0.9, depthshade=False,
                       label=style["label"], zorder=3)

        # Name the provinces the static chart has room for, just above their points
        named = table[(table["largest_commodity_pct"] >= Y_CUT) | (table["gini_2025s1"] >= LABEL_GINI_MIN)
                      | (table["grdp_per_capita_2025"] >= LABEL_PC_MIN)]
        for _, r in named.iterrows():
            side, dz = LABEL_PLACE.get(r["province_code"], ("center", 0.006))
            ax.text(np.log10(r["grdp_per_capita_2025"]), r["largest_commodity_pct"], r["gini_2025s1"] + dz,
                    r["province"], fontsize=7.5, color=charts.TEXT_PRIMARY, ha=side,
                    va="bottom" if dz > 0 else "top", zorder=4)

        # Label the axes, with per capita ticks at round Rp million values on the log scale
        ticks = log_tick_values(10 ** xlim[0], 10 ** xlim[1])
        ax.set_xticks(np.log10(ticks))
        ax.set_xticklabels([str(t) for t in ticks])
        ax.set_yticks([0, 10, 20, 30, 40, 50, 60, 70])
        ax.set_zticks([0.20, 0.25, 0.30, 0.35, 0.40, 0.45])
        ax.tick_params(colors=charts.TEXT_SECONDARY, labelsize=8.5)
        ax.set_xlabel("GRDP per capita, 2025\n(Rp million per person, log scale)", color=charts.TEXT_SECONDARY,
                      fontsize=9.5, labelpad=14)
        ax.set_ylabel("Largest single commodity,\nshare of GRDP, 2025 (%)", color=charts.TEXT_SECONDARY, fontsize=9.5,
                      labelpad=12)
        ax.set_zlabel("Gini ratio, March 2025", color=charts.TEXT_SECONDARY, fontsize=9.5, labelpad=10)
        ax.view_init(**VIEW)

        # Title and the legend of commodity colours
        fig.text(0.06, 0.965, "Wealth, single-commodity reliance and inequality: Indonesian provinces, 2025",
                 fontsize=15, fontweight="bold", color=charts.TEXT_PRIMARY)
        fig.legend(loc="upper right", bbox_to_anchor=(0.98, 0.9), ncol=1, frameon=False, fontsize=9,
                   labelcolor=charts.TEXT_SECONDARY, handletextpad=0.4, borderaxespad=0)
        fig.savefig(path, facecolor=charts.SURFACE)
        plt.close(fig)


def spread(values, reference):
    """Place each value on (-1, 1) by its rank on its side of a reference.

    Values at or above the reference spread evenly over (0, 1), the closest to the reference first, and values below
    it over (-1, 0), so that no stretch of an axis is crowded; ties share their average rank.
    """
    values = pd.Series(np.asarray(values, dtype=float))
    place = pd.Series(0.0, index=values.index)
    above = values >= reference
    for side, sign in ((above, 1.0), (~above, -1.0)):
        distance = (values[side] - reference).abs()
        if len(distance):
            place[side] = sign * (distance.rank(method="average") - 0.5) / len(distance)
    return place.to_numpy()


def zone_name(rich, high, reliant, measure):
    """Return the name of the zone for one side of each line, in the third measure's word order."""
    wealth, reliance = ("Rich" if rich else "Poor"), ("commodity-reliant" if reliant else "diverse")
    third = measure["sides"][0] if high else measure["sides"][1]
    return f"{wealth} × {third} × {reliance}" if measure["third_first"] else f"{wealth} × {reliance} × {third}"


def sphere_positions(table, x_cut, third_ref, measure):
    """Place every province inside the unit sphere and name its zone.

    x runs from more diverse (left) to more commodity-reliant (right), y from the low to the high end of the third
    measure (front to back), and z from poorer (bottom) to richer (top), each measured from its line: the 20% line,
    the third measure's line and Indonesia's per capita. On each axis a province's place is its rank on its side of the
    line, spread
    evenly. The cube those ranks fill is drawn into the sphere along rays from the centre, which keeps every province
    on its own side of all three cuts, so its zone shows where it sits.
    """
    share, third, per_capita = (table[c].to_numpy() for c in
                                ("largest_commodity_pct", measure["column"], "grdp_per_capita_2025"))
    cube = np.column_stack([spread(share, Y_CUT), spread(third, third_ref), spread(per_capita, x_cut)])
    ball = cube * (np.abs(cube).max(axis=1) / np.sqrt((cube ** 2).sum(axis=1)))[:, None] * POINT_REACH
    zones = [zone_name(r, h, c, measure) for r, h, c in zip(per_capita >= x_cut, third >= third_ref, share >= Y_CUT)]
    return ball, zones


def constellation(points):
    """Return the edges of the shortest tree that joins the points, as pairs of indices into points.

    Prim's algorithm from the first point; ties go to the lower index, so the tree is the same on every run.
    """
    if len(points) < 2:
        return []
    best = {j: (float(np.linalg.norm(points[j] - points[0])), 0) for j in range(1, len(points))}
    edges = []
    while best:
        j = min(best, key=lambda k: (best[k][0], k))
        _, i = best.pop(j)
        edges.append((i, j))
        for k in best:
            d = float(np.linalg.norm(points[k] - points[j]))
            if d < best[k][0]:
                best[k] = (d, j)
    return edges


def groups_of(keys, labels, colors, positions):
    """Return each group's label, line colour, members and constellation edges, in the order groups first appear."""
    groups = {}
    for key in dict.fromkeys(keys):
        members = [n for n, k in enumerate(keys) if k == key]
        edges = constellation(positions[members])
        groups[key] = {"label": labels[key], "color": colors[key], "members": members,
                       "edges": [[members[a], members[b]] for a, b in edges]}
    return groups


def write_sphere_page(table, positions, zones, commodity_styles, x_cut, third_ref, measure):
    """Write the interactive sphere as one HTML page drawn with three.js.

    The page shows the provinces as shaded balls coloured by largest commodity, the faint sphere, the three cuts
    through Indonesia and the measure axes. Clicking a province (press and release without dragging, within a few
    pixels of its ball) adds its constellation, the shortest tree joining it to the provinces of its zone or of its
    largest commodity, as the switch picks; nothing else in the scene is rebuilt, so the click is instant.
    """
    rows = table.reset_index(drop=True)
    zone_colors = {zone_name(r, h, c, measure): ZONE_COLORS[(r, h if measure["bad_high"] else not h, c)]
                   for r in (True, False) for h in (True, False) for c in (True, False)}
    direction = np.array([CAMERA_DIRECTION[k] for k in "xyz"], dtype=float)
    data = {
        "colors": {"surface": charts.SURFACE, "text": charts.TEXT_PRIMARY, "axis": charts.TEXT_SECONDARY,
                   "cut": charts.CUT, "wire": "#e4e3df"},
        "camera": [round(float(v), 4) for v in direction / np.linalg.norm(direction) * CAMERA_DISTANCE],
        "axes": [{"dir": [float(v) for v in np.eye(3)[axis]], "high": high, "low": low}
                 for axis, (high, low) in enumerate([AXIS_ENDS["x"], measure["ends"], AXIS_ENDS["z"]])],
        "reference": {"perCapita": round(float(x_cut), 2), "third": round(float(third_ref), 3), "line": Y_CUT},
        "provinces": [{"name": r["province"], "pos": [round(float(v), 4) for v in positions[n]],
                       "color": commodity_styles[r["group"]]["color"], "zone": zones[n], "commodity": r["group"],
                       "commodityName": COMMODITIES[r["largest_commodity"]]["name"],
                       "perCapita": round(float(r["grdp_per_capita_2025"]), 2),
                       "share": round(float(r["largest_commodity_pct"]), 2),
                       "thirdText": measure["hover"].format(float(r[measure["column"]]))}
                      for n, r in rows.iterrows()],
        "groups": {
            "zone": groups_of(zones, {z: z for z in zones}, zone_colors, positions),
            "commodity": groups_of(rows["group"].tolist(), {k: s["label"] for k, s in commodity_styles.items()},
                                   {k: s["color"] for k, s in commodity_styles.items()}, positions),
        },
        "legend": [{"label": s["label"], "color": s["color"]} for s in commodity_styles.values()],
    }
    # The data goes in a JSON script block; '</' is escaped so no value can close the block early
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    imports = json.dumps({"imports": {"three": f"{THREE_URL}/build/three.module.js",
                                      "three/addons/": f"{THREE_URL}/examples/jsm/"}})
    head = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PAGETITLE</title>
<style>
html, body { margin: 0; height: 100%; overflow: hidden; background: SURFACE; color: TEXT;
  font-family: 'DejaVu Sans', Arial, sans-serif; }
#scene { position: absolute; inset: 0; }
#header { position: absolute; top: 12px; left: 16px; right: 320px; z-index: 5; pointer-events: none; }
#header h1 { font-size: 18px; margin: 0 0 4px; }
#header p { font-size: 13px; margin: 0; color: AXIS; max-width: 920px; line-height: 1.4; }
#controls { position: absolute; top: 48px; left: 16px; z-index: 5; font-size: 13px; color: AXIS; }
#controls button { font: inherit; padding: 4px 10px; margin: 0 4px 0 0; border: 1px solid #e4e3df; border-radius: 4px;
  background: #f1f0ec; color: TEXT; cursor: pointer; }
#controls button.on { background: TEXT; color: SURFACE; }
#info { position: absolute; top: 82px; left: 16px; z-index: 5; max-width: 430px; font-size: 13px; line-height: 1.45; }
#legend { position: absolute; top: 14px; right: 16px; z-index: 5; font-size: 12px; color: AXIS; }
#legend .title { font-weight: bold; margin-bottom: 4px; }
#legend .row { display: flex; align-items: center; gap: 6px; margin: 3px 0; }
#legend .dot { width: 11px; height: 11px; border-radius: 50%; display: inline-block; }
#tip { position: absolute; z-index: 6; pointer-events: none; display: none; background: #ffffff; border: 1px solid #e4e3df;
  border-radius: 4px; padding: 6px 8px; font-size: 12px; line-height: 1.4; box-shadow: 0 1px 4px rgba(0,0,0,0.12); }
.name { font-size: 10px; color: TEXT; white-space: nowrap; pointer-events: none;
  text-shadow: 0 0 3px SURFACE, 0 0 3px SURFACE, 0 0 2px SURFACE; }
.name span { position: relative; top: -13px; }
.axis { font-size: 13px; color: AXIS; white-space: nowrap; pointer-events: none; }
</style>
<script type="importmap">IMPORTS</script>
</head>
<body>
<div id="scene"></div>
<div id="header"><h1>PAGETITLE</h1></div>
<div id="controls">Constellation: <button data-mode="zone" class="on">Zone</button><button data-mode="commodity">Commodity</button>
&nbsp; <button id="names">Names off</button><button id="clear">Clear</button></div>
<div id="info"></div>
<div id="legend"></div>
<div id="tip"></div>
"""
    for token, value in (("SURFACE", charts.SURFACE), ("TEXT", charts.TEXT_PRIMARY), ("AXIS", charts.TEXT_SECONDARY),
                         ("IMPORTS", imports), ("PAGETITLE", measure["title"])):
        head = head.replace(token, value)
    script = """<script type="module">
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { CSS2DRenderer, CSS2DObject } from "three/addons/renderers/CSS2DRenderer.js";
import { LineSegments2 } from "three/addons/lines/LineSegments2.js";
import { LineSegmentsGeometry } from "three/addons/lines/LineSegmentsGeometry.js";
import { LineMaterial } from "three/addons/lines/LineMaterial.js";

const D = JSON.parse(document.getElementById("data").textContent);
const holder = document.getElementById("scene");
const info = document.getElementById("info");
const tip = document.getElementById("tip");
const size = () => [holder.clientWidth, holder.clientHeight];

// Renderer, label layer, camera with z pointing up, and orbit controls around Indonesia at the centre
const renderer = new THREE.WebGLRenderer({antialias: true});
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setSize(...size());
renderer.setClearColor(D.colors.surface);
holder.appendChild(renderer.domElement);
const labels = new CSS2DRenderer();
labels.setSize(...size());
Object.assign(labels.domElement.style, {position: "absolute", top: "0", left: "0", pointerEvents: "none"});
holder.appendChild(labels.domElement);
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(35, size()[0] / size()[1], 0.1, 100);
camera.up.set(0, 0, 1);
camera.position.set(...D.camera);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.target.set(0, 0, 0);
controls.update();
scene.add(new THREE.AmbientLight(0xffffff, 1.6));
const sun = new THREE.DirectionalLight(0xffffff, 1.8);
sun.position.set(2, -3, 4);
scene.add(sun);

// Thin lines from lists of points: the wire sphere, the cuts and the axes
function lineSet(paths, color) {
  const points = [];
  for (const path of paths) for (let i = 0; i + 1 < path.length; i++) points.push(...path[i], ...path[i + 1]);
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(points, 3));
  return new THREE.LineSegments(geometry, new THREE.LineBasicMaterial({color}));
}
function circle(at) {
  const path = [];
  for (let i = 0; i <= 96; i++) { const t = i / 96 * 2 * Math.PI; path.push(at(Math.cos(t), Math.sin(t))); }
  return path;
}
const rad = d => d * Math.PI / 180;
const wire = [];
for (const lat of [-60, -30, 30, 60]) wire.push(circle((c, s) => [Math.cos(rad(lat)) * c, Math.cos(rad(lat)) * s, Math.sin(rad(lat))]));
for (const lon of [30, 60, 120, 150]) wire.push(circle((c, s) => [c * Math.cos(rad(lon)), c * Math.sin(rad(lon)), s]));
scene.add(lineSet(wire, D.colors.wire));
// The three cuts through Indonesia, where the sphere meets the plane of each reference value
scene.add(lineSet([circle((c, s) => [c, s, 0]), circle((c, s) => [c, 0, s]), circle((c, s) => [0, c, s])], D.colors.cut));

// Measure axes through the centre, an arrowhead at each high end, and names at both ends outside the sphere
function textLabel(text, className, position, bold) {
  const element = document.createElement("div");
  element.className = className;
  element.innerHTML = bold ? "<b>" + text + "</b>" : text;
  const label = new CSS2DObject(element);
  label.position.copy(position);
  scene.add(label);
  return label;
}
for (const axis of D.axes) {
  const d = new THREE.Vector3(...axis.dir);
  scene.add(lineSet([[d.clone().multiplyScalar(-1.35).toArray(), d.clone().multiplyScalar(1.35).toArray()]], D.colors.axis));
  const head = new THREE.Mesh(new THREE.ConeGeometry(0.035, 0.11, 16), new THREE.MeshBasicMaterial({color: D.colors.axis}));
  head.position.copy(d.clone().multiplyScalar(1.35));
  head.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), d);
  scene.add(head);
  textLabel(axis.high, "axis", d.clone().multiplyScalar(1.55), true);
  textLabel(axis.low, "axis", d.clone().multiplyScalar(-1.55), false);
}
// Indonesia at the centre
scene.add(new THREE.Mesh(new THREE.SphereGeometry(0.022, 16, 12), new THREE.MeshBasicMaterial({color: D.colors.text})));

// Provinces as shaded balls coloured by largest commodity, each with its name just above
const ball = new THREE.SphereGeometry(0.034, 24, 16);
const names = D.provinces.map(p => {
  const dot = new THREE.Mesh(ball, new THREE.MeshStandardMaterial({color: p.color, roughness: 0.45, metalness: 0.05}));
  dot.position.set(...p.pos);
  scene.add(dot);
  const element = document.createElement("div");
  element.className = "name";
  element.innerHTML = "<span></span>";
  element.firstChild.textContent = p.name;
  const label = new CSS2DObject(element);
  label.position.set(...p.pos);
  scene.add(label);
  return label;
});

// Legend of commodity colours
const legend = document.getElementById("legend");
legend.innerHTML = '<div class="title">Largest commodity</div>' + D.legend.map(item =>
  '<div class="row"><span class="dot" style="background:' + item.color + '"></span>' + item.label + "</div>").join("");

// The constellation: thick lines along the group's shortest tree and halos around its provinces, added on a click
const lineMaterial = new LineMaterial({color: 0x000000, linewidth: 3.5, transparent: true, opacity: 0.9});
lineMaterial.resolution.set(...size());
const halo = new THREE.SphereGeometry(0.06, 24, 16);
let mode = "zone", selected = null, showNames = true, drawn = [];
function draw() {
  for (const object of drawn) { scene.remove(object); if (object.geometry !== halo) object.geometry.dispose(); }
  drawn = [];
  if (selected === null) { info.textContent = ""; return; }
  const group = D.groups[mode][D.provinces[selected][mode]];
  if (group.edges.length) {
    const points = [];
    for (const [a, b] of group.edges) points.push(...D.provinces[a].pos, ...D.provinces[b].pos);
    const geometry = new LineSegmentsGeometry();
    geometry.setPositions(points);
    lineMaterial.color.set(group.color);
    const lines = new LineSegments2(geometry, lineMaterial);
    scene.add(lines);
    drawn.push(lines);
  }
  for (const i of group.members) {
    const ring = new THREE.Mesh(halo, new THREE.MeshBasicMaterial({color: group.color, transparent: true,
      opacity: i === selected ? 0.5 : 0.28, depthWrite: false}));
    ring.position.set(...D.provinces[i].pos);
    scene.add(ring);
    drawn.push(ring);
  }
  const title = mode === "zone" ? group.label + " (" + group.members.length + ")" : group.label;
  info.innerHTML = "<b>" + title + "</b><br>" + group.members.map(i => D.provinces[i].name).join(", ");
}

// Find the province whose ball is nearest a point on screen, within a radius in pixels
const projected = new THREE.Vector3();
function nearest(x, y, radius) {
  const box = renderer.domElement.getBoundingClientRect();
  let best = null, bestDistance = radius;
  D.provinces.forEach((p, i) => {
    projected.set(...p.pos).project(camera);
    const sx = (projected.x + 1) / 2 * box.width + box.left, sy = (1 - projected.y) / 2 * box.height + box.top;
    const distance = Math.hypot(sx - x, sy - y);
    if (distance < bestDistance) { best = i; bestDistance = distance; }
  });
  return best;
}

// A press and release without dragging selects the nearest province; a second click on it clears the constellation
let pressed = null;
renderer.domElement.addEventListener("pointerdown", event => { pressed = [event.clientX, event.clientY]; });
renderer.domElement.addEventListener("pointerup", event => {
  if (!pressed) return;
  const moved = Math.hypot(event.clientX - pressed[0], event.clientY - pressed[1]);
  pressed = null;
  if (moved > 5) return;
  const hit = nearest(event.clientX, event.clientY, 16);
  if (hit === null) return;
  selected = selected === hit ? null : hit;
  draw();
});
// Hovering near a province shows its values
renderer.domElement.addEventListener("pointermove", event => {
  if (pressed) { tip.style.display = "none"; return; }
  const hit = nearest(event.clientX, event.clientY, 12);
  renderer.domElement.style.cursor = hit === null ? "grab" : "pointer";
  if (hit === null) { tip.style.display = "none"; return; }
  const p = D.provinces[hit];
  tip.innerHTML = "<b>" + p.name + "</b><br>" + p.zone + "<br>GRDP per capita: Rp " + p.perCapita.toFixed(1) +
    " million<br>Largest commodity: " + p.commodityName + ", " + p.share.toFixed(1) + "% of GRDP<br>" + p.thirdText;
  tip.style.left = (event.clientX + 14) + "px";
  tip.style.top = (event.clientY + 14) + "px";
  tip.style.display = "block";
});
renderer.domElement.addEventListener("pointerleave", () => { tip.style.display = "none"; });

// The switch picks the grouping, the names button shows or hides the names, and clear removes the constellation
document.querySelectorAll("[data-mode]").forEach(button => button.addEventListener("click", () => {
  mode = button.dataset.mode;
  document.querySelectorAll("[data-mode]").forEach(other => other.classList.toggle("on", other === button));
  draw();
}));
document.getElementById("names").addEventListener("click", event => {
  showNames = !showNames;
  for (const label of names) label.visible = showNames;
  event.target.textContent = showNames ? "Names off" : "Names on";
});
document.getElementById("clear").addEventListener("click", () => { selected = null; draw(); });

// Keep the view sized to the window, and draw every frame so the rotation glides
window.addEventListener("resize", () => {
  const [w, h] = size();
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  renderer.setSize(w, h);
  labels.setSize(w, h);
  lineMaterial.resolution.set(w, h);
});
renderer.setAnimationLoop(() => { controls.update(); renderer.render(scene, camera); labels.render(scene, camera); });
window.sphereReady = true;
draw();
</script>
<script>
// Say so if three.js could not be loaded from the web, instead of leaving an empty page
setTimeout(() => { if (!window.sphereReady) document.getElementById("info").textContent =
  "Could not load three.js from cdn.jsdelivr.net. The page needs an internet connection the first time it opens."; }, 8000);
</script>
"""
    page = (head + '<script id="data" type="application/json">' + payload + "</script>\n" + script
            + "</body>\n</html>\n")
    with open(measure["out"], "w", encoding="utf-8", newline="\n") as f:
        f.write(page)


# Steps

# Read both datasets and their metadata, and take province names from the 20261102 metadata as Maysa's chart does
pop, industry = read_long(POP_DATASET), read_long(INDUSTRY_DATASET)
pop_meta = json.loads(POP_METADATA.read_text(encoding="utf-8"))
industry_meta = json.loads(INDUSTRY_METADATA.read_text(encoding="utf-8"))
provinces = sorted(industry_meta["provinces"])
assert len(provinces) == 38 and all(industry_meta["provinces"][c]["name"] == pop_meta["provinces"][c]["name"]
                                    for c in provinces)
names = {code: charts.display_name(pop_meta["provinces"][code]["name"]) for code in provinces}

# Read the Gini ratio of the March 2025 Susenas round, urban and rural areas together, for every province and Indonesia
gini_rows = pd.read_csv(GINI_DATASET, dtype={"province_code": str, "area": str, "period": str, "status": str},
                        keep_default_na=False)
gini = gini_rows[(gini_rows["indicator"] == "gini_ratio") & (gini_rows["area"] == GINI_AREA)
                 & (gini_rows["period"] == GINI_PERIOD)].set_index("province_code")["value"]
assert sorted(gini.index) == sorted(provinces + [INDONESIA]), "the Gini ratio does not cover the 38 provinces and 00"

# Read household spending per person per month in 2025, food and non-food together, for every province and Indonesia
spending_rows = pd.read_csv(SPENDING_DATASET, dtype={"province_code": str, "item": str, "period": str, "status": str},
                            keep_default_na=False)
spending = spending_rows[(spending_rows["indicator"] == "spending_per_capita_month")
                         & (spending_rows["item"] == SPENDING_ITEM)
                         & (spending_rows["period"] == SPENDING_PERIOD)].set_index("province_code")["value"]
assert sorted(spending.index) == sorted(provinces + [INDONESIA]), "spending does not cover the 38 provinces and 00"

# Check the commodity chains against the sector tree: every code is a leaf, raw parts lie in farming or mining and
# processing in manufacturing, and the raw parts and A1e together cover every leaf of farming and mining once
leaves, parents = leaf_sectors(industry_meta)
raw_codes = [c for spec in COMMODITIES.values() for c in spec["raw"]]
processing_codes = [c for spec in COMMODITIES.values() for c in spec["processing"]]
assert all(c in leaves for c in raw_codes + processing_codes + LEFT_OUT)
assert all(under(c, "C", parents) for c in processing_codes)
primary_leaves = sorted(c for c in leaves if any(under(c, a, parents) for a in PRIMARY))
assert sorted(raw_codes + LEFT_OUT) == primary_leaves, "commodities and A1e do not cover farming and mining once"
assert len(set(raw_codes + processing_codes)) == len(raw_codes + processing_codes)

# Read the 2025 sector values, en-dash cells as 0, and check that the 52 leaf sectors add up to TOTAL
values, statuses = sector_table(industry, industry_meta, provinces, YEAR)
assert len(leaves) == 52
leaf_gap = (values[leaves].sum(axis=1) - values[TOTAL]).abs()
assert leaf_gap.max() <= LEAF_TOLERANCE, f"leaf sectors miss TOTAL by {leaf_gap.max():.2f} Rp billion"

# Per capita GRDP from the 20261102 dataset, in Rp million per person, and the Indonesia line: summed provincial GRDP
# over Indonesia's population
grdp = cells(pop, "grdp_current", TOTAL, YEAR)
people = cells(pop, "population", "", YEAR)
assert sorted(grdp.index) == provinces and sorted(people.index) == sorted(provinces + [INDONESIA])
per_capita = grdp.loc[provinces, "value"] / people.loc[provinces, "value"]
x_cut = grdp.loc[provinces, "value"].sum() / people.at[INDONESIA, "value"]
# Both datasets give the same provincial GRDP, within BPS's rounding of 0.01 Rp billion
assert (grdp.loc[provinces, "value"] - values[TOTAL]).abs().max() <= 0.01 + 1e-9

# Every GRDP cell used for a province carries one revision status, which the table reports
used = [TOTAL] + raw_codes + processing_codes
status = {}
for code in provinces:
    found = {grdp.at[code, "status"]} | {statuses.at[code, s] for s in used if pd.notna(statuses.at[code, s])}
    assert len(found) == 1, f"GRDP cells of {code} differ in status in {YEAR}: {found}"
    status[code] = found.pop()

# Shares of GRDP in %, each sector over the province's SIMDASI TOTAL
shares = values.div(values[TOTAL], axis=0) * 100

# Each commodity's raw and processing shares
raw = pd.DataFrame({k: shares[spec["raw"]].sum(axis=1) for k, spec in COMMODITIES.items()})
processing = pd.DataFrame({k: shares[spec["processing"]].sum(axis=1) for k, spec in COMMODITIES.items()})

# Keep the mills (C2) in estate crops only where estate crops reach MILLS_MIN_PCT of GRDP, and stop unless those are
# the seven provinces agreed with the user
mills_added = raw[MILLS_COMMODITY] >= MILLS_MIN_PCT
assert sorted(raw.index[mills_added]) == sorted(MILLS_PROVINCES), \
    f"C2 goes to {sorted(raw.index[mills_added])}, not the agreed provinces"
processing[MILLS_COMMODITY] = processing[MILLS_COMMODITY].where(mills_added, 0.0)
commodity = raw + processing

# Each province's largest commodity; a tie would make it depend on the order of COMMODITIES, so it stops the script
largest = commodity.idxmax(axis=1)
assert all(r[0] > r[1] for r in (sorted(row, reverse=True) for row in commodity.to_numpy())), \
    "two commodities tie for the largest share"
largest_pct = commodity.max(axis=1)

# Group each province by its largest commodity, or into the grey group when that is under MIN_SHARE_PCT
group = pd.Series([LOW if pct < MIN_SHARE_PCT else k for k, pct in zip(largest, largest_pct)], index=provinces)
assert set(group) - {LOW} <= set(COLORS), f"no colour for {sorted(set(group) - {LOW} - set(COLORS))}"

# Build the table behind the chart, one row per province, from the most to the least reliant on one commodity
table = pd.DataFrame({
    "province_code": provinces,
    "province": [names[c] for c in provinces],
    "grdp_per_capita_2025": per_capita.loc[provinces].values,
    "largest_commodity": largest.loc[provinces].values,
    "largest_commodity_pct": largest_pct.loc[provinces].values,
    "raw_pct": [raw.at[c, largest[c]] for c in provinces],
    "processing_pct": [processing.at[c, largest[c]] for c in provinces],
    **{f"{k}_pct": commodity.loc[provinces, k].values for k in COMMODITIES},
    "palm_mills_added": ["yes" if mills_added[c] else "no" for c in provinces],
    "gini_2025s1": gini.loc[provinces].values,
    "spending_2025": spending.loc[provinces].values,
    "status_2025": [status[c] for c in provinces],
    "quadrant": [QUADRANTS[(per_capita[c] >= x_cut, largest_pct[c] >= Y_CUT)] for c in provinces],
    "group": group.loc[provinces].values,
})
table = table.sort_values(["largest_commodity_pct", "province_code"], ascending=[False, True], kind="mergesort")

# The inequality line: the good-life equality threshold. A province exactly on it would make 'at or above' and 'above'
# differ (the paper counts 0.30 as meeting the threshold), so that stops the script for a decision
gini_cut = GINI_LINE
assert not (gini.loc[provinces] == GINI_LINE).any(), "a province's Gini equals the line; decide which side it is on"

# Place every province in each sphere and name its zone: its side of each line on per capita, commodity share and the
# page's third measure (Gini against the good-life line; household spending against Indonesia's average)
third_lines = {"gini": gini_cut, "spending": float(spending[INDONESIA])}
assert not (spending.loc[provinces] == third_lines["spending"]).any(), "a province's spending equals Indonesia's"
spheres = {key: sphere_positions(table, x_cut, third_lines[key], measure) for key, measure in THIRD_MEASURES.items()}
table["zone"] = spheres["gini"][1]
table["zone_spending"] = spheres["spending"][1]

# Write the table: per capita to 2 decimals as the sibling tables do, shares to 4
written = table.drop(columns="group")
for column in written.columns:
    if column.endswith("_pct"):
        written[column] = [f"{v:.4f}" for v in written[column]]
written["grdp_per_capita_2025"] = [f"{v:.2f}" for v in written["grdp_per_capita_2025"]]
written["gini_2025s1"] = [f"{v:.3f}" for v in written["gini_2025s1"]]
written["spending_2025"] = [f"{v:.0f}" for v in written["spending_2025"]]
written.to_csv(OUT_CSV, index=False, lineterminator="\n")

# Order the legend from the most to the fewest provinces, ties in the order of COMMODITIES, with the grey group last
counts = table["group"].value_counts()
order = sorted(set(group) - {LOW}, key=lambda k: (-counts[k], list(COMMODITIES).index(k)))
styles = {k: {"label": f"{COMMODITIES[k]['name']} ({counts[k]})", "color": COLORS[k]} for k in order}
if LOW in counts:
    styles[LOW] = {"label": f"{LOW_LABEL} ({counts[LOW]})", "color": GREY}

# Draw the chart with the shared quadrant chart, without a source note
charts.quadrant_chart(
    table, "grdp_per_capita_2025", "largest_commodity_pct", x_cut, Y_CUT, QUADRANTS,
    xlabel="GRDP per capita, 2025 (Rp million per person, log scale)",
    ylabel="Largest single commodity, share of GRDP, 2025 (%)",
    title="Wealth vs single-commodity reliance: Indonesian provinces, 2025",
    subtitle="GRDP per capita against the share of GRDP from the largest single commodity, mining or farming plus "
             "local processing",
    note=None, path=OUT_PNG, logx=True, ylim=YLIM, yticks=YTICKS, yunit="%",
    ycut_label="{:.0f}%", group="group", styles=styles, legend_cols=2,
    keep_quadrants=True, halo=True, lines_over_points=True,
)

# Draw the 3D chart with the Gini ratio as height, as a static PNG and as an interactive page
draw_3d_png(table, styles, x_cut, gini_cut, OUT_3D_PNG)
for key, measure in THIRD_MEASURES.items():
    write_sphere_page(table, *spheres[key], styles, x_cut, third_lines[key], measure)

# Report each sphere's zones and their members
for key, column in (("gini", "zone"), ("spending", "zone_spending")):
    print(f"Zones of the {key} sphere (line {third_lines[key]:,.3f}):")
    for r in (True, False):
        for c in (True, False):
            for h in (True, False):
                name = zone_name(r, h, c, THIRD_MEASURES[key])
                members = table[table[column] == name]
                print(f"  {name} ({len(members)}): " + ", ".join(members["province"]))

# Report the rank correlations between the three axes, and the most unequal provinces
ranks = table[["grdp_per_capita_2025", "largest_commodity_pct", "gini_2025s1", "spending_2025"]].rank()
corr = ranks.corr()
print(f"Rank correlation (Spearman), 38 provinces: per capita vs commodity share "
      f"{corr.iloc[0, 1]:+.2f}; per capita vs Gini {corr.iloc[0, 2]:+.2f}; commodity share vs Gini {corr.iloc[1, 2]:+.2f}; "
      f"per capita vs spending {corr.iloc[0, 3]:+.2f}; commodity share vs spending {corr.iloc[1, 3]:+.2f}")
print(f"Gini {GINI_PERIOD}: Indonesia {gini[INDONESIA]:.3f}, good-life line {gini_cut:.2f}; highest " + ", ".join(
    f"{r['province']} {r['gini_2025s1']:.3f}" for _, r in table.nlargest(6, "gini_2025s1").iterrows()))

# Report the Indonesia line, each quadrant's members, the count of each largest commodity and the provinces near 20%
print(f"Indonesia {YEAR}: per capita {x_cut:.4f} Rp million (GRDP {grdp.loc[provinces, 'value'].sum():.2f} Rp billion "
      f"/ population {people.at[INDONESIA, 'value']:.1f} thousand); Y cut {Y_CUT:.0f}%")
for name in QUADRANTS.values():
    members = table[table["quadrant"] == name]
    print(f"{name}: {len(members)}: " + ", ".join(f"{c} {n}" for c, n in zip(members["province_code"],
                                                                          members["province"])))
print("Largest commodity: " + ", ".join(f"{COMMODITIES[k]['name']} {n}"
                                        for k, n in table["largest_commodity"].value_counts().items()))
print("Legend: " + ", ".join(s["label"] for s in styles.values()))
print(f"C2 added to estate crops (A1c at least {MILLS_MIN_PCT:.0f}% of GRDP): "
      + ", ".join(f"{c} {names[c]}" for c in table["province_code"] if mills_added[c]))
near = table[(table["largest_commodity_pct"] - Y_CUT).abs() <= 2]
print(f"Within 2 points of the {Y_CUT:.0f}% line:")
for _, r in near.iterrows():
    print(f"  {r['province_code']} {r['province']}: {COMMODITIES[r['largest_commodity']]['name']} "
          f"{r['largest_commodity_pct']:.2f}% ({r['quadrant']})")
