from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# Load the shared chart and panel modules from tools/
import sys
sys.path.insert(0, str(ROOT / "tools"))
import charts
import province_panel

import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.transforms import blended_transform_factory
import numpy as np
import pandas as pd
from scipy import stats

# Parameters

# T1's within-province test from the harmonised panel (tools/province_panel.py, which reads data/ only): BPS household
# consumption (PKRT) as a share of GRDP on the expenditure side at current prices (var 534, %) on the sharpened
# extractive share (province_panel.EXTRACTIVE_GROUPS, % of GRDP at current prices, BPS SIMDASI yearbook table 13.1.1)
# and log real GRDP per capita (var 286), with unit and year effects and standard errors clustered by unit (CR1),
# 2015-2025. The extractive share's slope is the base; each chart row changes one choice and keeps every other at the
# base. The household share stays at current prices in every row, the only basis the expenditure data has
OUTCOME = "pkrt_share_pct"
SHARE = province_panel.SHARP_SHARE
INCOME = province_panel.INCOME
MINING = "extractive_share_pct"
FIRST_YEAR, LAST_YEAR = province_panel.SHARP_FIRST_YEAR, province_panel.LAST_YEAR

OUT_PNG = HERE / "20261105_household-share-tornado.png"
OUT_CSV = HERE / "20261105_household-share-sensitivity.csv"

# Row 3, constant 2010 prices: the five-group share rebuilt from yearbook table 13.1.2 (grdp_constant_2010) on the same
# unit borders, with C2 in the plantation group in the same unit-years as at current prices (plantation_includes_c2),
# over the constant-price TOTAL of the same tables. An en-dash cell counts as 0, and so does an en dash the metadata
# lists under small_values (a small value BPS did not print in the 2016 and 2017 constant-price tables)
CONSTANT = "constant_2010"
CONSTANT_SHARE = "extractive_sharp_constant_share_pct"
# Row 5, province trends: a linear trend for each unit (unit dummy times the year less CENTRE_YEAR, the middle of
# 2015-2025; the centre does not change the slopes) beside the unit and year effects. A unit with fewer than
# TREND_MIN_YEARS years is fitted exactly by its effect and trend, so it carries no information and is left out
CENTRE_YEAR, TREND_MIN_YEARS = 2020, 3
# Row 6: the years of the pandemic dropped, and the years cut at the last year before the Papua split
DROPPED_YEARS, CUT_YEAR = [2020, 2021], 2023
# Row 7: a unit is left out when its BPS codes include one of the six Papua provinces
PAPUA_CODES = {"91", "92", "94", "95", "96", "97"}

# Row labels in plain words, keyed by row
ROWS = {
    "mining": "Mining and quarrying only",
    "groups": "One commodity group left out",
    "constant": "Constant 2010 prices",
    "no_income": "No income control",
    "trends": "Province trends",
    "years": "2020–21 dropped or years cut at 2023",
    "papua": "Papua dropped",
    "units": "One province left out",
}
BASE_ROW = "Base"

# Figure: size in inches at 200 dpi, the title's left edge and the plot area's other margins as figure fractions
FIGSIZE, DPI = (12.5, 6.4), 200
TITLE_LEFT = 0.012
MARGINS = {"right": 0.985, "top": 0.835, "bottom": 0.115}
# Marks: the bar height in row units and its two tones, the series blue left of the base and a light tint of it right
# of the base, and the reference lines' widths in points
BAR_HEIGHT = 0.5
LEFT_TONE, RIGHT_TONE = charts.SERIES, "#9fc2ed"
BASE_WIDTH, ZERO_WIDTH = 1.1, 1.0
# Text sizes in points, the gap between a bar end and its label and the room kept beyond the outermost label, in points
ROW_SIZE, VALUE_SIZE, REF_SIZE, AXIS_SIZE = 10, 8.5, 9, 9.5
LABEL_GAP, EDGE_ROOM = 4, 6
# x ticks every TICK_STEP points
TICK_STEP = 0.1

# Texts
TITLE = "Sensitivity of the within-province household-share estimate to each choice, 2015–2025"
XLABEL = ("Within-province effect on the household consumption share, points per 1-point rise in the extractive "
          "share")
LEGEND = ["Estimate below the base", "Estimate above the base"]

# Functions


def minus(text):
    """Write a number's minus sign as the typographic minus."""
    return text.replace("-", "−")


def estimate(df, predictors, row, setting, label):
    """Run the two-way fixed effects test of the household share on the predictors and return the first predictor's
    slope with its row, setting and the text its bar-end label carries."""
    r = province_panel.twfe(df, OUTCOME, predictors)
    return {"row": row, "setting": setting, "label": label, "slope": r["slopes"][0], "std_error": r["se"][0],
            "p_value": r["p"][0], "n": r["n"], "units": r["units"]}


def twfe_trends(df, predictors, row, setting, label):
    """Least squares with a dummy for every unit, every year but one and a linear trend for every unit, by
    residualising the outcome and the predictors on the dummies (Frisch-Waugh-Lovell), with standard errors clustered
    by unit as province_panel.twfe clusters them.

    The unit trends add up to the common trend that the year and unit dummies span, so the dummy matrix lacks one rank;
    the least-squares residuals are the same whichever trend is dropped. As in province_panel.twfe, the CR1 factor
    counts the slopes, the year effects but one and the constant; the unit effects and unit trends lie inside the
    clusters and are not counted. p comes from t with units - 1 degrees of freedom.
    """
    d = df.dropna(subset=[OUTCOME, *predictors]).sort_values(["unit", "year"])
    units, unit_idx = np.unique(d["unit"].to_numpy(), return_inverse=True)
    years, year_idx = np.unique(d["year"].to_numpy(), return_inverse=True)
    t = d["year"].to_numpy(float) - CENTRE_YEAR
    dummies = np.column_stack([(unit_idx == g).astype(float) for g in range(len(units))]
                              + [(year_idx == j).astype(float) for j in range(1, len(years))]
                              + [(unit_idx == g) * t for g in range(len(units))])

    # Residualise a column on the dummies by least squares
    def residual(values):
        values = values.astype(float)
        return values - dummies @ np.linalg.lstsq(dummies, values, rcond=None)[0]

    y = residual(d[OUTCOME].to_numpy())
    x = np.column_stack([residual(d[p].to_numpy()) for p in predictors])
    xtx_inv = np.linalg.inv(x.T @ x)
    slopes = xtx_inv @ (x.T @ y)
    resid = y - x @ slopes
    n, g, k = len(d), len(units), len(predictors) + (len(years) - 1) + 1
    scores = np.zeros((g, len(predictors)))
    np.add.at(scores, unit_idx, x * resid[:, None])
    variance = (g / (g - 1)) * ((n - 1) / (n - k)) * xtx_inv @ (scores.T @ scores) @ xtx_inv
    se = np.sqrt(np.diag(variance))
    p = 2 * stats.t.sf(np.abs(slopes / se), g - 1)
    return {"row": row, "setting": setting, "label": label, "slope": slopes[0], "std_error": se[0], "p_value": p[0],
            "n": n, "units": g}


def constant_share(b, sample):
    """Rebuild the five-group extractive share at constant 2010 prices on each unit's borders, as build() derives it at
    current prices, and return it on the sample's unit-years with the count of en-dash cells of the sharpened sectors in
    the sample's years that hide a small value and were counted as 0, and the sample's unit-years without the detail."""
    meta = b.meta["detailed"]
    table, _ = province_panel.detailed_table(b.data["detailed"], meta, b.detailed_sectors, prices=CONSTANT)
    sharp_sectors = [code for codes in province_panel.EXTRACTIVE_GROUPS.values() for code in codes]
    # Count each small value hidden under an en dash as 0, as the other en dashes are
    hidden = 0
    for cell in meta["none_or_zero_cells"]["small_values"]["cells"]:
        key, sector = (cell["province_code"], int(cell["period"])), cell["sector"]
        if cell["indicator"] == f"grdp_{CONSTANT}" and sector in table.columns and key in table.index:
            table.loc[key, sector] = 0.0
            if sector in sharp_sectors and FIRST_YEAR <= key[1] <= LAST_YEAR:
                hidden += 1
    # Sum the sectors over each unit's area, keeping the sample's unit-years
    units, _, gaps = province_panel.gather_detailed(table, b.units, b.detailed_sectors)
    keys = pd.MultiIndex.from_frame(sample[["unit", "year"]])
    units = units.reindex(keys)
    sample_gaps = {k: v for k, v in gaps.items() if k in set(keys)}
    # C2 counts in the plantation group in the unit-years it counts at current prices
    mills = pd.Series((sample["plantation_includes_c2"] == "yes").to_numpy(), index=keys)
    value = pd.Series(0.0, index=keys)
    for codes in province_panel.EXTRACTIVE_GROUPS.values():
        group = units[[c for c in codes if c != province_panel.MILLS_SECTOR]].sum(axis=1, min_count=1)
        if province_panel.MILLS_SECTOR in codes:
            group = group + units[province_panel.MILLS_SECTOR].where(mills, 0.0)
        value = value + group.round(2)
    share = (value.round(2) / units["TOTAL"].round(2) * 100).round(province_panel.DERIVED_DECIMALS)
    return share.to_numpy(), hidden, sample_gaps


def bar_label(ax, x, y, text, side):
    """Write a bar end's label just beyond the end, on the bar's outer side, and return it."""
    return ax.annotate(text, (x, y), xytext=(side * LABEL_GAP, 0), textcoords="offset points",
                       ha="left" if side > 0 else "right", va="center", fontsize=VALUE_SIZE,
                       color=charts.TEXT_SECONDARY)


# Steps

# Build the harmonised panel with all its checks and keep the unit-years of the sharpened share, 2015-2025
b = province_panel.build()
panel = b.panel
sample = panel[panel["year"].between(FIRST_YEAR, LAST_YEAR)].copy()
names = {unit: info[0] for unit, info in b.units.items()}

# The base: the household share on the five-group share and log real GRDP per capita
base = estimate(sample, [SHARE, INCOME], BASE_ROW, "five-group share at current prices, income held equal", "")
results = [base]

# Row 1: mining and quarrying (sector B) alone in place of the five-group share
results.append(estimate(sample, [MINING, INCOME], ROWS["mining"], "sector B share in place of the five-group share",
                        ""))

# Row 2: the five-group share less one group's share, once for each group
for group, share in zip(province_panel.EXTRACTIVE_GROUPS, province_panel.GROUP_SHARES):
    d = sample.assign(less_group=sample[SHARE] - sample[share])
    results.append(estimate(d, ["less_group", INCOME], ROWS["groups"], f"{group} left out", f"without {group}"))

# Row 3: the five-group share at constant 2010 prices, the household share and income as in the base
sample[CONSTANT_SHARE], hidden_zeros, constant_gaps = constant_share(b, sample)
results.append(estimate(sample, [CONSTANT_SHARE, INCOME], ROWS["constant"],
                        "five-group share at constant 2010 prices", ""))

# Row 4: the extractive share alone, without the income control
results.append(estimate(sample, [SHARE], ROWS["no_income"], "five-group share alone", ""))

# Row 5: unit and year effects plus a linear trend for each unit, leaving out the units with fewer than three years
years_held = sample.groupby("unit")["year"].transform("size")
short_units = sorted(sample.loc[years_held < TREND_MIN_YEARS, "unit"].unique())
results.append(twfe_trends(sample[years_held >= TREND_MIN_YEARS], [SHARE, INCOME], ROWS["trends"],
                           f"linear trend for each unit; units with fewer than {TREND_MIN_YEARS} years left out "
                           f"({' '.join(short_units)})", ""))

# Row 6: (a) 2020 and 2021 dropped; (b) the years cut at 2023, before the Papua split
results.append(estimate(sample[~sample["year"].isin(DROPPED_YEARS)], [SHARE, INCOME], ROWS["years"],
                        "2020 and 2021 dropped", "without 2020–21"))
results.append(estimate(sample[sample["year"] <= CUT_YEAR], [SHARE, INCOME], ROWS["years"],
                        f"{FIRST_YEAR}-{CUT_YEAR} only", f"to {CUT_YEAR} only"))

# Row 7: every unit that covers a Papua province left out
papua = sample["bps_codes"].str.split().apply(lambda codes: bool(PAPUA_CODES & set(codes)))
results.append(estimate(sample[~papua], [SHARE, INCOME], ROWS["papua"],
                        "units covering " + ", ".join(sorted(PAPUA_CODES)) + " left out", ""))

# Row 8: each unit of the sample left out once
for unit in sorted(sample["unit"].unique()):
    results.append(estimate(sample[sample["unit"] != unit], [SHARE, INCOME], ROWS["units"],
                            f"without {names[unit]} ({unit})", f"without {names[unit]}"))

# Order the rows by their swing, from the lowest to the highest estimate with the base included, widest first
table = pd.DataFrame(results)
base_slope = base["slope"]
spans = (table[table["row"] != BASE_ROW].groupby("row")["slope"].agg(["min", "max"])
         .assign(low=lambda s: s["min"].clip(upper=base_slope), high=lambda s: s["max"].clip(lower=base_slope)))
spans["swing"] = spans["high"] - spans["low"]
order = spans.sort_values("swing", ascending=False).index.tolist()

# Report the base, each row's range, whether any estimate reaches 0, and the en dashes counted as 0
print(f"Base {base_slope:.4f} (se {base['std_error']:.4f}, n {base['n']}, units {base['units']})")
for row in order:
    rows = table[table["row"] == row]
    low, high = rows.loc[rows["slope"].idxmin()], rows.loc[rows["slope"].idxmax()]
    print(f"  {row}: {low['slope']:.4f} ({low['setting']}) to {high['slope']:.4f} ({high['setting']}), "
          f"swing {spans.loc[row, 'swing']:.4f}")
print(f"Estimates at 0 or above: {int((table['slope'] >= 0).sum())}; highest {table['slope'].max():.4f}")
print(f"Constant prices: {hidden_zeros} en-dash cells of the sharpened sectors in {FIRST_YEAR}-{LAST_YEAR} hide a "
      f"small value and count as 0; sample unit-years without the detail: {constant_gaps or 'none'}")
print(f"Province trends leave out {', '.join(names[u] + ' (' + u + ')' for u in short_units)}")

# Write every value the chart plots, the base first and then the rows from top to bottom
out = pd.concat([table[table["row"] == BASE_ROW]] + [table[table["row"] == row] for row in order])
out = out.assign(slope=out["slope"].map(province_panel.num), std_error=out["std_error"].map(province_panel.num),
                 p_value=out["p_value"].map(lambda v: province_panel.num(v, 4)))
out[["row", "setting", "slope", "std_error", "p_value", "n", "units"]].to_csv(
    OUT_CSV, index=False, encoding="utf-8", lineterminator="\n")

# Draw the tornado: one bar per row from its lowest to its highest estimate, split at the base into two tones
fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
fig.patch.set_facecolor(charts.SURFACE)
charts.style_axes(ax)
ax.yaxis.grid(False)
labels = []
for y, row in enumerate(order):
    low, high = spans.loc[row, "low"], spans.loc[row, "high"]
    if low < base_slope:
        ax.barh(y, base_slope - low, left=low, height=BAR_HEIGHT, color=LEFT_TONE, zorder=3)
    if high > base_slope:
        ax.barh(y, high - base_slope, left=base_slope, height=BAR_HEIGHT, color=RIGHT_TONE, zorder=3)
    # Label each bar end that is an estimate with its value and, in a row of several settings, the setting
    rows = table[table["row"] == row]
    for end, side in [(rows["slope"].idxmin(), -1), (rows["slope"].idxmax(), +1)]:
        value = rows.loc[end, "slope"]
        if (side < 0 and value < base_slope) or (side > 0 and value > base_slope):
            text = minus(f"{value:.2f}") + (f" {rows.loc[end, 'label']}" if len(rows) > 1 else "")
            labels.append(bar_label(ax, value, y, text, side))
ax.set_yticks(range(len(order)), [r for r in order], fontsize=ROW_SIZE, color=charts.TEXT_PRIMARY)
ax.set_ylim(len(order) - 0.5, -0.5)

# Reference lines at the base and at 0, each labelled above the plot area
top = blended_transform_factory(ax.transData, ax.transAxes)
ax.axvline(base_slope, color=charts.TEXT_SECONDARY, lw=BASE_WIDTH, zorder=4)
ax.axvline(0, color=charts.CUT, lw=ZERO_WIDTH, ls=(0, (4, 3)), zorder=2)
ax.text(base_slope, 1.012, minus(f"Base {base_slope:.2f}"), transform=top, ha="center", va="bottom",
        fontsize=REF_SIZE, color=charts.TEXT_PRIMARY)
ax.text(0, 1.012, "0", transform=top, ha="center", va="bottom", fontsize=REF_SIZE, color=charts.TEXT_SECONDARY)
ax.set_xlabel(XLABEL, fontsize=AXIS_SIZE, color=charts.TEXT_SECONDARY, labelpad=8)

# Place the plot area so the longest row label starts at the title's left edge
fig.subplots_adjust(left=0.3, **MARGINS)
fig.canvas.draw()
renderer = fig.canvas.get_renderer()
label_width = max(t.get_window_extent(renderer).width for t in ax.get_yticklabels())
pad = ax.yaxis.get_tick_padding() * DPI / 72
fig.subplots_adjust(left=TITLE_LEFT + (label_width + pad + 2) / (FIGSIZE[0] * DPI))

# Widen the x axis until every bar-end label fits inside the plot area, keeping 0 in view
xlim = (table["slope"].min(), max(0.0, table["slope"].max()))
for _ in range(charts.GROW_PASSES):
    ax.set_xlim(xlim)
    fig.canvas.draw()
    inverse = ax.transData.inverted()
    room = EDGE_ROOM * DPI / 72
    edges = [t.get_window_extent(renderer) for t in labels]
    low = min([xlim[0]] + [inverse.transform((e.x0 - room, 0))[0] for e in edges])
    high = max([xlim[1], inverse.transform((ax.transData.transform((0, 0))[0] + room, 0))[0]]
               + [inverse.transform((e.x1 + room, 0))[0] for e in edges])
    if np.isclose(low, xlim[0]) and np.isclose(high, xlim[1]):
        break
    xlim = (low, high)
ax.set_xlim(xlim)
ticks = np.arange(np.ceil(xlim[0] / TICK_STEP), np.floor(xlim[1] / TICK_STEP) + 1) * TICK_STEP
ax.set_xticks(ticks, ["0" if abs(t) < 1e-9 else minus(f"{t:.1f}") for t in ticks])

# Add the title and the legend of the two tones, and save the chart
handles = [Patch(facecolor=LEFT_TONE, label=LEGEND[0]), Patch(facecolor=RIGHT_TONE, label=LEGEND[1])]
charts.finish(fig, TITLE, handles, OUT_PNG, left=TITLE_LEFT)
print(f"Saved {OUT_PNG.relative_to(ROOT)} and {OUT_CSV.relative_to(ROOT)}")
