from pathlib import Path

# Locate this script's folder and the repository root two levels up
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# Load the shared chart and panel modules from tools/
import sys
sys.path.insert(0, str(ROOT / "tools"))
import charts
import province_panel

import math

import matplotlib.pyplot as plt
from matplotlib import patheffects
from matplotlib.lines import Line2D
from matplotlib.text import Text
from matplotlib.ticker import FixedLocator, NullLocator
import numpy as np
import pandas as pd

# Parameters

# Outputs, beside this script
OUT_PANEL = HERE / "20261103_harmonised-panel.csv"
OUT_COVERAGE = HERE / "20261103_panel-coverage.csv"
OUT_RESULTS = HERE / "20261103_panel-results.csv"
OUT_T1 = HERE / "20261103_t1-household-share-vs-extractive-share.png"
OUT_T3 = HERE / "20261103_t3-gini-vs-extractive-share.png"
OUT_T3_GROUPS = HERE / "20261103_t3-gini-vs-extractive-groups.png"

# Tests: (test, outcome, predictors, controls, sample). Without controls a test runs two-way fixed effects and the
# Spearman correlations of unit averages and of long differences. With controls, the fixed effects enter them beside
# the predictor, and the two comparisons become partial rank correlations that control for them (their unit averages,
# or their long differences).
# T1: BPS's household consumption share of GRDP on the extractive share, the sharpened one and, for comparison on the
# same unit-years, B alone.
# T2: each labour outcome (the informal share of employment, and the hourly and minimum wage in logs) on log real GRDP
# per capita alone (does a richer province have a better labour market?), then on the sharpened share and on each
# group's share; and T1's within-province test from INFORMAL_FIRST_YEAR with income held equal, without and then with
# the informal share held equal too (is informal work part of why extraction lowers the household share?).
# T3: each Gini ratio (total, urban, rural) on the sharpened share and on each group's share.
# T4: each of the other five expenditure components' share of GRDP on the sharpened share and on each group's share,
# T1's design: where the household share's loss goes.
# T5: the employee wage bill's share of GRDP on the sharpened share and on each group's share, T1's design from
# WAGE_FIRST_YEAR (do employees get a smaller slice of the output?); then its log and its three log parts on the
# sharpened share (where does a smaller slice come from?).
# T6: school participation at ages 16-18 and 19-23 on the sharpened share and on each group's share, T1's design
# (does extraction keep young people out of school?)
TESTS = [
    ("T1", "pkrt_share_pct", ["extractive_share_pct"], [], "all_years"),
    ("T1", "pkrt_share_pct", ["ln_grdp_pc_real"], [], "all_years"),
    *[("T1", "pkrt_share_pct", [share], controls, "sharp_years")
      for share in [province_panel.SHARP_SHARE, "extractive_share_pct"] for controls in [[], [province_panel.INCOME]]],
    *[("T2", outcome, [province_panel.INCOME], [], "sharp_years") for outcome in province_panel.T2_OUTCOMES],
    *[("T2", outcome, [share], controls, "sharp_years") for outcome in province_panel.T2_OUTCOMES
      for share in [province_panel.SHARP_SHARE] + province_panel.GROUP_SHARES
      for controls in [[], [province_panel.INCOME]]],
    *[("T2", "pkrt_share_pct", [province_panel.SHARP_SHARE], controls, "informal_years")
      for controls in [[province_panel.INCOME], [province_panel.INCOME, "informal_share_pct"]]],
    *[("T3", outcome, [share], controls, "sharp_years") for outcome in ["gini_total", "gini_urban", "gini_rural"]
      for share in [province_panel.SHARP_SHARE] + province_panel.GROUP_SHARES
      for controls in [[], [province_panel.INCOME]]],
    *[("T4", outcome, [share], controls, "sharp_years") for outcome in province_panel.T4_OUTCOMES
      for share in [province_panel.SHARP_SHARE] + province_panel.GROUP_SHARES
      for controls in [[], [province_panel.INCOME]]],
    *[("T5", "wage_share_pct", [share], controls, "wage_years")
      for share in [province_panel.SHARP_SHARE] + province_panel.GROUP_SHARES
      for controls in [[], [province_panel.INCOME]]],
    *[("T5", outcome, [province_panel.SHARP_SHARE], controls, "wage_years")
      for outcome in ["ln_wage_share", *province_panel.T5_PARTS] for controls in [[], [province_panel.INCOME]]],
    *[("T6", outcome, [share], controls, "sharp_years") for outcome in province_panel.T6_SERIES
      for share in [province_panel.SHARP_SHARE] + province_panel.GROUP_SHARES
      for controls in [[], [province_panel.INCOME]]],
]

# Charts: 200 dpi; thin province paths in a light tint of the series colour
DPI = 200
PATH_COLOR, PATH_WIDTH = "#a9c4e8", 0.8
# Point names: distances in points of the rings of spots each name tries, the first beside its point and the others
# at the end of a leader; and the half-width in pixels of the box that keeps names off a point's marker
LABEL_RINGS = (6, 14, 22, 30, 40, 52, 66, 80, 96)
DOT = 8
# T1: the extractive share on a log axis, which spreads the many provinces under 5% extractive, and the PKRT share of
# GRDP on a linear one, since it stays between 10% and 90%; the extractive axis ends at 100%
T1_XTICKS = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100]
T1_YTICKS = [10, 20, 30, 40, 50, 60, 70, 80, 90]
T1_XMAX = 100
# T3: marker area in points squared of a circle; the other shapes are scaled from it by
# charts.EXTRACTIVE_MARKER_AREA. Names keep T3_DOT pixels from each point's centre
T3_POINT_SIZE = 70
T3_DOT = 12
# T3: the extractive share on a log axis, the Gini ratio on a linear one
T3_XTICKS = [1, 2, 5, 10, 20, 50, 100]
T3_YTICKS = [0.26, 0.28, 0.30, 0.32, 0.34, 0.36, 0.38, 0.40, 0.42, 0.44]

# Functions

def fixed_ticks(axis, ticks, low, high, log, fmt):
    """Show fixed ticks inside a range as plain numbers, with no minor ticks on a log axis."""
    ticks = [v for v in ticks if low <= v <= high]
    axis.set_major_locator(FixedLocator(ticks))
    if log:
        axis.set_minor_locator(NullLocator())
    axis.set_ticklabels([fmt(v) for v in ticks])


def plain(v):
    """Write a tick value without trailing zeros, as 0.5, 2 or 0.25."""
    return f"{v:g}"


def name_points(ax, xs, ys, labels, fontsize=7.5, rings=LABEL_RINGS, required=True, halo=False, lines=(), dot=DOT,
                nearest=False):
    """Name points beside themselves or, where that is crowded, at the end of a thin leader line.

    Each name tries eight directions on rings of growing distance (points) and takes the first spot where it stays
    inside the plot and touches no other name, point, leader or line; past the first ring a leader joins it to its
    point, and the leader must cross no name or other point. Points farthest from the others are named first. A name
    that finds no free spot is left out when required is False; when required is True it takes the spot with the
    fewest clashes and is counted as crowded.
    lines: (xs, ys) arrays in data units of lines that names keep clear of, such as a fitted curve.
    dot: half-width in pixels of the box that keeps names off each point.
    nearest: when True, a name without a leader also takes only a spot nearer its own point than any other point, so
        it cannot be read as another point's name.
    Returns (named, crowded), the numbers of names placed and of names placed on a clash.
    """
    fig = ax.figure
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    pts = ax.transData.transform(np.column_stack([xs, ys]))
    frame = ax.get_window_extent(renderer)
    dots = [(px - dot, py - dot, px + dot, py + dot) for px, py in pts]
    clear = [(qx - 3, qy - 3, qx + 3, qy + 3) for lx, ly in lines
             for qx, qy in ax.transData.transform(np.column_stack([lx, ly]))]
    extra = {"path_effects": [patheffects.withStroke(linewidth=charts.HALO, foreground=charts.SURFACE)]} \
        if halo else {}
    offsets = [(dx * r, dy * r) for r in rings for dx, dy in
               [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, 1), (1, -1), (-1, -1)]]

    def candidate(i, dx, dy):
        """Draw a name at an offset; return it, its box, and the small boxes along its leader (none on ring one)."""
        lead = max(abs(dx), abs(dy)) > rings[0]
        relpos = (0.5 - 0.5 * (dx > 0) + 0.5 * (dx < 0), 0.5 - 0.5 * (dy > 0) + 0.5 * (dy < 0))
        arrow = {"arrowstyle": "-", "color": charts.TEXT_MUTED, "lw": 0.6, "shrinkA": 0, "shrinkB": 4,
                 "relpos": relpos} if lead else None
        t = ax.annotate(labels[i], (xs[i], ys[i]), xytext=(dx, dy), textcoords="offset points",
                        ha="left" if dx > 0 else "right" if dx < 0 else "center",
                        va="bottom" if dy > 0 else "top" if dy < 0 else "center",
                        fontsize=fontsize, color=charts.TEXT_PRIMARY, arrowprops=arrow, **extra)
        # The annotation's own extent places it first; the text's extent then leaves out the leader
        t.get_window_extent(renderer)
        bb = Text.get_window_extent(t, renderer)
        box = (bb.x0 - 1, bb.y0 - 1, bb.x1 + 1, bb.y1 + 1)
        trail = []
        if lead:
            start = (bb.x0 + relpos[0] * bb.width, bb.y0 + relpos[1] * bb.height)
            steps = int(math.dist(start, pts[i]) // 3) + 1
            for k in range(steps + 1):
                p = (start[0] + (pts[i][0] - start[0]) * k / steps, start[1] + (pts[i][1] - start[1]) * k / steps)
                if math.dist(p, pts[i]) > dot + 2:
                    trail.append((p[0] - 1, p[1] - 1, p[0] + 1, p[1] + 1))
        return t, box, trail

    def inside(box):
        """Return True when a box lies inside the plot frame."""
        return frame.x0 < box[0] and box[2] < frame.x1 and frame.y0 < box[1] and box[3] < frame.y1

    def gap(box, p):
        """Return the distance in pixels from a point to the nearest edge of a box, 0 inside it."""
        return math.hypot(max(box[0] - p[0], 0, p[0] - box[2]), max(box[1] - p[1], 0, p[1] - box[3]))

    def own(i, box, trail):
        """Return True unless nearest is on and a name without a leader lies nearer another point than its own."""
        return not nearest or bool(trail) or all(gap(box, p) > gap(box, pts[i]) for k, p in enumerate(pts) if k != i)

    order = sorted(range(len(labels)), key=lambda i: -min(
        [abs(pts[i][0] - pts[j][0]) + abs(pts[i][1] - pts[j][1]) for j in range(len(labels)) if j != i] or [0]))
    placed, trails, named, crowded = [], [], 0, 0
    for i in order:
        if not labels[i]:
            continue
        others = [d for k, d in enumerate(dots) if k != i]
        chosen = None
        for dx, dy in offsets:
            t, box, trail = candidate(i, dx, dy)
            if inside(box) and not charts.touches(box, placed + trails + others + clear, pad=0) \
                    and not any(charts.touches(b, placed + others, pad=0) for b in trail) and own(i, box, trail):
                chosen = (box, trail)
                break
            t.remove()
        if chosen is None and required:
            # No free spot: take the spot inside the plot with the fewest clashes, the nearest on a tie
            scores = []
            for dx, dy in offsets:
                t, box, trail = candidate(i, dx, dy)
                t.remove()
                if inside(box):
                    scores.append((sum(charts.touches(box, [o], pad=0) for o in placed + trails + others + clear)
                                   + sum(charts.touches(b, placed + others, pad=0) for b in trail), dx, dy))
            assert scores, f"no spot inside the plot for the name {labels[i]}"
            _, dx, dy = min(scores, key=lambda s: s[0])
            t, box, trail = candidate(i, dx, dy)
            chosen = (box, trail)
            crowded += 1
        if chosen is not None:
            placed.append(chosen[0])
            trails += chosen[1]
            named += 1
    return named, crowded


def draw_paths(ax, panel, x, y):
    """Draw each unit's path over its years as a thin line."""
    for _, part in panel.dropna(subset=[x, y]).sort_values(["unit", "year"]).groupby("unit"):
        ax.plot(part[x], part[y], color=PATH_COLOR, lw=PATH_WIDTH, zorder=1, solid_capstyle="round")


def end_points(panel, x, y):
    """Return each unit's last year in the sample, marking the units whose last year is not LAST_YEAR."""
    d = panel.dropna(subset=[x, y])
    ends = d.loc[d.groupby("unit")["year"].idxmax()].sort_values("unit")
    return ends[ends["year"] == province_panel.LAST_YEAR], ends[ends["year"] < province_panel.LAST_YEAR]


def legend_handles(path_label, last_label, pre_split_label):
    """Return the legend entries: a path line, a last-year point and a pre-split end point."""
    filled = charts.point_marks({}, charts.POINT_SIZE)
    hollow = charts.point_marks({"filled": False}, charts.POINT_SIZE)
    handles = [Line2D([], [], color=PATH_COLOR, lw=1.6, label=path_label),
               Line2D([], [], linestyle="none", marker="o", markersize=math.sqrt(filled["s"]),
                      markerfacecolor=filled["facecolor"], markeredgecolor=filled["edgecolor"],
                      markeredgewidth=filled["linewidth"], label=last_label),
               Line2D([], [], linestyle="none", marker="o", markersize=math.sqrt(hollow["s"]),
                      markerfacecolor=hollow["facecolor"], markeredgecolor=hollow["edgecolor"],
                      markeredgewidth=hollow["linewidth"], label=pre_split_label)]
    return handles


def axis_range(values, log, high=None):
    """Return axis limits with headroom: a factor of 1.25 on a log axis, 5% of the span on a linear one; high caps
    the upper limit."""
    low_v, high_v = values.min(), values.max()
    if log:
        lim = (low_v / 1.25, high_v * 1.25)
    else:
        pad = (high_v - low_v) * 0.05
        lim = (low_v - pad, high_v + pad)
    return (lim[0], min(lim[1], high)) if high is not None else lim


def path_chart(panel, x, y, xlabel, ylabel, title, path, logx, logy, xticks, yticks, xfmt, yfmt, xmax=None):
    """Draw each unit's path over the years with its last point named, and save the chart.

    A pre-split unit's path ends before LAST_YEAR in a hollow point named with the first and last years of its path.
    Returns (named, crowded) from name_points.
    """
    fig, ax = plt.subplots(figsize=(14, 10), dpi=DPI)
    fig.patch.set_facecolor(charts.SURFACE)
    fig.subplots_adjust(left=0.07, right=0.98, top=0.9, bottom=0.08)
    charts.style_axes(ax)
    d = panel.dropna(subset=[x, y])
    if logx:
        ax.set_xscale("log")
    if logy:
        ax.set_yscale("log")
    xlim, ylim = axis_range(d[x], logx, xmax), axis_range(d[y], logy)
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    fixed_ticks(ax.xaxis, xticks, *xlim, logx, xfmt)
    fixed_ticks(ax.yaxis, yticks, *ylim, logy, yfmt)
    draw_paths(ax, panel, x, y)
    last, early = end_points(panel, x, y)
    ax.scatter(last[x], last[y], zorder=3, **charts.point_marks({}, charts.POINT_SIZE))
    ax.scatter(early[x], early[y], zorder=3, **charts.point_marks({"filled": False}, charts.POINT_SIZE))
    ax.set_xlabel(xlabel, color=charts.TEXT_SECONDARY, fontsize=10)
    ax.set_ylabel(ylabel, color=charts.TEXT_SECONDARY, fontsize=10)
    # Name every end point: the last-year points by name, the pre-split ends by name and the years of their path
    ends = pd.concat([last, early])
    firsts = d.groupby("unit")["year"].min()
    labels = [n if yr == province_panel.LAST_YEAR else f"{n} {firsts[u]}–{yr}" for u, n, yr in
              zip(ends["unit"], ends["unit_name"], ends["year"])]
    result = name_points(ax, ends[x].to_numpy(), ends[y].to_numpy(), labels, halo=True)
    handles = legend_handles(f"Path over the years, {d['year'].min()}–{d['year'].max()}",
                             f"{province_panel.LAST_YEAR}", "Last year of a pre-split area")
    charts.finish(fig, title, handles, path)
    return result


def group_marks(style):
    """Return the scatter arguments of a group's points: its colour inside the shared surface ring, its marker, and
    the area of a circle of T3_POINT_SIZE."""
    return {**charts.point_marks({"color": style["color"]},
                                 T3_POINT_SIZE * charts.EXTRACTIVE_MARKER_AREA[style["marker"]]),
            "marker": style["marker"]}


def group_points(ax, means, x, y):
    """Draw one point per unit in the colour and marker of its largest extractive group."""
    for group, style in charts.EXTRACTIVE_GROUP_STYLE.items():
        part = means[means["largest_group"] == group]
        ax.scatter(part[x], part[y], zorder=3, **group_marks(style))


def group_handles():
    """Return the legend entries of the extractive groups, each drawn like its points."""
    handles = []
    for style in charts.EXTRACTIVE_GROUP_STYLE.values():
        marks = group_marks(style)
        handles.append(Line2D([], [], linestyle="none", marker=marks["marker"], markersize=math.sqrt(marks["s"]),
                              markerfacecolor=marks["facecolor"], markeredgecolor=marks["edgecolor"],
                              markeredgewidth=marks["linewidth"], label=style["label"]))
    return handles


def t3_chart(means, xlabel, ylabel, title, path):
    """Draw each unit's average Gini ratio against its average sharpened extractive share on a log axis, in the
    colour and marker of its largest extractive group, every point named; save the chart.

    Returns (named, crowded) from name_points. The chart fills a 16:9 slide (charts.SLIDE_SIZE).
    """
    fig, ax = plt.subplots(figsize=charts.SLIDE_SIZE, dpi=DPI)
    fig.patch.set_facecolor(charts.SURFACE)
    fig.subplots_adjust(left=0.07, right=0.98, top=0.86, bottom=0.09)
    charts.style_axes(ax)
    ax.set_xscale("log")
    xlim, ylim = axis_range(means[province_panel.SHARP_SHARE], True, T1_XMAX), axis_range(means["gini_total"], False)
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    fixed_ticks(ax.xaxis, T3_XTICKS, *xlim, True, plain)
    fixed_ticks(ax.yaxis, T3_YTICKS, *ylim, False, lambda v: f"{v:.2f}")
    group_points(ax, means, province_panel.SHARP_SHARE, "gini_total")
    ax.set_xlabel(xlabel, color=charts.TEXT_SECONDARY, fontsize=10)
    ax.set_ylabel(ylabel, color=charts.TEXT_SECONDARY, fontsize=10)
    result = name_points(ax, means[province_panel.SHARP_SHARE].to_numpy(), means["gini_total"].to_numpy(),
                         means["unit_name"].tolist(), halo=True, dot=T3_DOT)
    charts.finish(fig, title, group_handles(), path, legend_title="Largest extractive group")
    return result


def t3_groups_chart(means, panels, ylabel, title, path):
    """Draw one small panel per share, each unit's average Gini ratio against its average share on linear axes, in
    the colour and marker of its largest extractive group and named beside its point where there is room; save the
    chart.

    panels: (share column, x axis label) per panel, filled row by row. Returns {share: (named, units)}.
    """
    fig, axes = plt.subplots(2, 3, figsize=(16, 11), dpi=DPI, sharey=True)
    fig.patch.set_facecolor(charts.SURFACE)
    fig.subplots_adjust(left=0.05, right=0.99, top=0.87, bottom=0.08, wspace=0.06, hspace=0.32)
    ys = means["gini_total"].to_numpy()
    ylim = axis_range(means["gini_total"], False)
    named = {}
    for k, (ax, (share, xlabel)) in enumerate(zip(axes.flat, panels)):
        charts.style_axes(ax)
        xs = means[share].to_numpy()
        pad = (xs.max() - xs.min()) * 0.06
        ax.set_xlim(xs.min() - pad, xs.max() + pad)
        ax.set_ylim(*ylim)
        fixed_ticks(ax.yaxis, T3_YTICKS, *ylim, False, lambda v: f"{v:.2f}")
        group_points(ax, means, share, "gini_total")
        ax.set_xlabel(xlabel, color=charts.TEXT_SECONDARY, fontsize=9.5)
        if k % 3 == 0:
            ax.set_ylabel(ylabel, color=charts.TEXT_SECONDARY, fontsize=10)
        count, _ = name_points(ax, xs, ys, means["unit_name"].tolist(), fontsize=7, rings=(7,), required=False,
                               dot=T3_DOT, nearest=True)
        named[share] = (count, len(xs))
    charts.finish(fig, title, group_handles(), path, legend_title="Largest extractive group", left=0.05)
    return named


# Steps

# Build the harmonised panel from the datasets in data/, running every check of tools/province_panel.py
built = province_panel.build()
panel, units, checks = built.panel, built.units, built.checks

# Save the panel, which build() returns sorted by unit and year; each value is written at the precision it holds
panel.to_csv(OUT_PANEL, index=False, encoding="utf-8", lineterminator="\n")

# Each unit's largest extractive group: the group with the highest average share over the unit's years from
# SHARP_FIRST_YEAR
group_means = (panel[panel["year"] >= province_panel.SHARP_FIRST_YEAR]
               .groupby("unit")[province_panel.GROUP_SHARES].mean())
largest = group_means.idxmax(axis=1).str.removesuffix("_share_pct")

# Save the unit and year coverage: one row per unit with its codes, years, the years summed from several codes in
# each additive dataset, whether it enters the between-province and long-difference comparisons, the years of its
# sharpened share and its largest extractive group
coverage = []
for unit, (name, codes, first, last) in units.items():
    part = panel[panel["unit"] == unit]
    coverage.append({
        "unit": unit, "unit_name": name, "bps_codes": " ".join(codes), "first_year": first, "last_year": last,
        "years": len(part),
        "grdp_summed_years": province_panel.year_span(part.loc[part["grdp_rule"] == "summed", "year"]),
        "industry_summed_years": province_panel.year_span(part.loc[part["industry_rule"] == "summed", "year"]),
        "rural_gini_years": province_panel.year_span(part.dropna(subset=["gini_rural"])["year"]),
        "cross_section": "yes" if len(part) >= province_panel.CROSS_SECTION_MIN_YEARS else "no",
        "detailed_summed_years": province_panel.year_span(part.loc[part["detailed_rule"] == "summed", "year"]),
        "sharp_share_years": province_panel.year_span(part.dropna(subset=[province_panel.SHARP_SHARE])["year"]),
        "largest_extractive_group": largest.get(unit, ""),
        "expenditure_summed_years": province_panel.year_span(part.loc[part["expenditure_rule"] == "summed", "year"]),
        **{f"{column}_years": province_panel.year_span(part.dropna(subset=[column])["year"])
           for column in [*province_panel.LABOUR, *province_panel.T5_SERIES, *province_panel.T6_SERIES]}})
coverage = pd.DataFrame(coverage).sort_values("unit").reset_index(drop=True)
coverage.to_csv(OUT_COVERAGE, index=False, encoding="utf-8", lineterminator="\n")

# Run every test on its sample: two-way fixed effects on the sample's unit-years, and the Spearman correlations (partial
# rank correlations when the test has controls) of unit averages and of long differences on the units with enough
# years. Each row names the regressors estimated beside its predictor, or the variables a partial correlation
# controls for, and its sample
samples = {name: panel[panel["year"] >= start] for name, start in province_panel.SAMPLES.items()}
results, fits = [], {}
for test, outcome, predictors, controls, sample in TESTS:
    d = samples[sample]
    # The fixed effects enter the predictor and the controls together
    labels = predictors + controls
    fe = province_panel.twfe(d, outcome, labels)
    fits[(test, outcome, predictors[0], tuple(controls), sample)] = fe
    for j, label in enumerate(labels):
        results.append({"test": test, "outcome": outcome, "predictor": label,
                        "controls": " + ".join(other for other in labels if other != label),
                        "method": "two_way_fixed_effects", "sample": sample,
                        "coefficient": province_panel.num(fe["slopes"][j]),
                        "std_error": province_panel.num(fe["se"][j]), "p_value": province_panel.num(fe["p"][j], 4),
                        "spearman_rho": "", "n": fe["n"], "provinces": fe["units"],
                        "years": f"{fe['years'][0]}-{fe['years'][1]}"})
    kind = "partial_spearman" if controls else "spearman"
    for method, run in [(f"between_province_{kind}", province_panel.between),
                        (f"long_difference_{kind}", province_panel.long_difference)]:
        r = run(d, outcome, predictors[0], controls)
        results.append({"test": test, "outcome": outcome, "predictor": predictors[0], "controls": " + ".join(controls),
                        "method": method, "sample": sample, "coefficient": "", "std_error": "",
                        "p_value": province_panel.num(r["p"], 4), "spearman_rho": province_panel.num(r["rho"], 4),
                        "n": r["n"], "provinces": r["units"], "years": f"{r['years'][0]}-{r['years'][1]}"})
results = pd.DataFrame(results)
results.to_csv(OUT_RESULTS, index=False, encoding="utf-8", lineterminator="\n")

# Chart T1: BPS's household consumption (PKRT) share of GRDP against the sharpened extractive share over its years,
# each unit's path, the 2025 points named
labelled = {}
labelled["T1"] = path_chart(
    samples["sharp_years"], province_panel.SHARP_SHARE, "pkrt_share_pct",
    f"Extractive share of GRDP, % at current prices ({province_panel.SHARP_NAME}), log scale",
    "Household consumption (PKRT), % of GRDP at current prices",
    f"Household consumption share of GRDP against extractive share of GRDP, Indonesian provinces, "
    f"{province_panel.SHARP_FIRST_YEAR}–{province_panel.LAST_YEAR}", OUT_T1, True, False, T1_XTICKS, T1_YTICKS,
    plain, plain, xmax=T1_XMAX)

# Chart T3: each unit's average Gini ratio against its average sharpened share over the share's years, for the units
# of the between-province comparison, in the colour and marker of the unit's largest extractive group; then one small
# panel per share, the sharpened share and each group's
cross = province_panel.cross_section(samples["sharp_years"], "gini_total", [province_panel.SHARP_SHARE])
means = cross.groupby("unit")[["gini_total", province_panel.SHARP_SHARE, *province_panel.GROUP_SHARES]].mean()
means["unit_name"] = cross.groupby("unit")["unit_name"].first()
means["largest_group"] = largest[means.index]
years_text = f"average {cross['year'].min()}–{cross['year'].max()}"
labelled["T3"] = t3_chart(
    means, f"Extractive share of GRDP, % at current prices ({province_panel.SHARP_NAME}), {years_text}, log scale",
    f"Gini ratio, March, {years_text}",
    f"Gini ratio against extractive share of GRDP, Indonesian provinces, "
    f"{province_panel.SHARP_FIRST_YEAR}–{province_panel.LAST_YEAR}", OUT_T3)
group_codes = {group: " + ".join(c for c in codes if c != province_panel.MILLS_SECTOR)
               for group, codes in province_panel.EXTRACTIVE_GROUPS.items()}
group_codes["plantation"] += (f", plus {province_panel.MILLS_SECTOR} where {province_panel.ESTATE_SECTOR} ≥ "
                              f"{province_panel.ESTATE_MIN_SHARE}% of GRDP")
named_t3 = t3_groups_chart(
    means, [(province_panel.SHARP_SHARE, f"Extractive share of GRDP, %, {years_text}\n(the five groups)")]
    + [(share, f"{group.capitalize()} share of GRDP, %, {years_text}\n({group_codes[group]})")
       for group, share in zip(province_panel.EXTRACTIVE_GROUPS, province_panel.GROUP_SHARES)],
    f"Gini ratio, March, {years_text}",
    f"Gini ratio against the share of GRDP of each extractive group, Indonesian provinces, "
    f"{province_panel.SHARP_FIRST_YEAR}–{province_panel.LAST_YEAR}", OUT_T3_GROUPS)

# Print the coverage and a short results summary
print(f"Panel: {len(panel)} unit-years, {panel['unit'].nunique()} units, "
      f"{province_panel.FIRST_YEAR}-{province_panel.LAST_YEAR}")
print("Units per year: " + ", ".join(f"{y} {n}" for y, n in panel.groupby("year")["unit"].size().items()))
print("Border units:")
split_codes = list(province_panel.SPLITS) + list(province_panel.PARENT_OF)
for _, c in coverage[coverage["bps_codes"].str.contains(" ") | coverage["unit"].isin(split_codes)].iterrows():
    print(f"  {c['unit']:<12} {c['unit_name']:<30} {c['first_year']}-{c['last_year']} ({c['years']} years)"
          f"{'; GRDP summed ' + c['grdp_summed_years'] if c['grdp_summed_years'] else ''}"
          f"{'; industry summed ' + c['industry_summed_years'] if c['industry_summed_years'] else ''}"
          f"; cross-section: {c['cross_section']}")
print(f"Checks: implied population gap {checks['pop_gap']:.1e} (tolerance {province_panel.POP_TOL:.0e}); var 286 = "
      f"industry TOTAL on {checks['border_checks']} unit-year values (tolerance {province_panel.BORDER_TOL}, "
      f"declared gaps {len(province_panel.BORDER_GAPS)})")
print(f"Yearbook detail: {checks['dash_zeros']} en-dash cells of the {len(built.detailed_sectors)} sectors read as 0; "
      f"{checks['detail_checks']} border checks on {len(built.detailed_units)} unit-years, largest gaps "
      + ", ".join(f"{k} {v:.2f}" for k, v in checks["detail_worst"].items())
      + f" (tolerance {province_panel.DETAILED_TOL} per table)")
have = panel.dropna(subset=[province_panel.SHARP_SHARE])
print(f"Sharpened share: {len(have)} unit-years; per year " + ", ".join(
    f"{y} {n}" for y, n in have.groupby("year")["unit"].size().items()))
early_units = (have[have["year"] < province_panel.SHARP_FIRST_YEAR].groupby("unit")["year"]
               .apply(province_panel.year_span))
print(f"  Before {province_panel.SHARP_FIRST_YEAR} (not in the tests): "
      + "; ".join(f"{u} {s}" for u, s in early_units.items()))
reasons = {}
for (unit, year), reason in built.detailed_gaps.items():
    kind = "no yearbook table" if reason.startswith("no yearbook table") else reason
    reasons.setdefault(kind, {}).setdefault(unit, []).append(year)
for kind, by_unit in sorted(reasons.items()):
    spans = {}
    for unit, years in by_unit.items():
        spans.setdefault(province_panel.year_span(years), []).append(unit)
    print(f"  None, {kind}: {sum(len(y) for y in by_unit.values())} unit-years; "
          + "; ".join(f"{span} for {', '.join(us)}" for span, us in spans.items()))
print(f"  Summed yearbook unit-years: {', '.join(f'{u} {y}' for u, y in sorted(built.detailed_summed))}")
in_sample = samples["sharp_years"]
counted = (in_sample[in_sample["plantation_includes_c2"] == "yes"].groupby("unit")["year"]
           .apply(province_panel.year_span))
with_c2 = len(in_sample[in_sample["plantation_includes_c2"] == "yes"])
print(f"  C2 in the plantation group from {province_panel.SHARP_FIRST_YEAR} ({with_c2}"
      f" of {len(in_sample)} unit-years): " + "; ".join(f"{u} {s}" for u, s in counted.items()))
print("  Largest group by unit: " + "; ".join(
    f"{g} {len(us)} ({', '.join(us)})" for g, us in
    ((g, [u for u in means.index if means.loc[u, 'largest_group'] == g]) for g in province_panel.EXTRACTIVE_GROUPS)))
print(f"PKRT share: expenditure-side PDRB = var 286 on {checks['expenditure_checks']} unit-years, largest gap "
      f"{checks['expenditure_worst']:.2f} (tolerance {province_panel.BORDER_TOL}); summed unit-years "
      f"{', '.join(f'{u} {y}' for u, y in sorted(built.expenditure_summed))}; above 100%: "
      + ("; ".join(f"{a['unit_name']} {a['year']} {a['pkrt_share_pct']:.1f}%"
                   for _, a in checks["pkrt_above"].iterrows()) or "none"))
print("T2 labour series from " + str(province_panel.SHARP_FIRST_YEAR) + ": " + "; ".join(
    f"{column} {province_panel.year_span(panel.dropna(subset=[column])['year'])}, "
    f"{panel[column].notna().sum()} unit-years" for column in province_panel.LABOUR)
    + "; declared gaps: " + ", ".join(f"{c} {p} {y}" for c, p, y in sorted(province_panel.LABOUR_GAPS)))
t1_slope = fits[("T1", "pkrt_share_pct", province_panel.SHARP_SHARE, (province_panel.INCOME,),
                 "sharp_years")]["slopes"][0]
t4_slopes = {code: fits[("T4", f"{code.lower()}_share_pct", province_panel.SHARP_SHARE, (province_panel.INCOME,),
                         "sharp_years")]["slopes"][0]
             for code in province_panel.T4_COMPONENTS}
print(f"T4 split of T1's within-province slope at equal income ({t1_slope:.4f} points of household share per point "
      f"of extractive share): " + ", ".join(f"{province_panel.T4_COMPONENTS[c]} {s:+.4f}" for c, s in t4_slopes.items())
      + f"; the five add to {sum(t4_slopes.values()):+.4f}. Shares add to 100 within {checks['share_gap']:.1e}; "
        f"components add to PDRB within {checks['part_gap']:.2f} Rp billion")
print("T5 and T6 series: " + "; ".join(
    f"{column} {province_panel.year_span(panel.dropna(subset=[column])['year'])}, "
    f"{panel[column].notna().sum()} unit-years" for column in [*province_panel.T5_SERIES, *province_panel.T6_SERIES]))
t5_slope = fits[("T5", "ln_wage_share", province_panel.SHARP_SHARE, (province_panel.INCOME,),
                 "wage_years")]["slopes"][0]
t5_parts = {part: fits[("T5", part, province_panel.SHARP_SHARE, (province_panel.INCOME,), "wage_years")]["slopes"][0]
            for part in province_panel.T5_PARTS}
print(f"T5 split of the log wage share's within-province slope at equal income ({t5_slope:+.5f} per point of "
      f"extractive share): " + ", ".join(f"{'+' if sign > 0 else '-'} {part} ({s:+.5f})" for (part, sign), s in
                                         zip(province_panel.T5_PARTS.items(), t5_parts.values()))
      + f"; the signed parts add to {sum(province_panel.T5_PARTS[p] * s for p, s in t5_parts.items()):+.5f}. "
        f"Identity holds on every unit-year within {checks['split_gap']:.1e}")
print("Results (two-way FE: coefficient, clustered SE, p; Spearman: rho, p):")
for _, r in results.iterrows():
    stat = (f"b = {r['coefficient']} (se {r['std_error']}), p = {r['p_value']}" if r["coefficient"]
            else f"rho = {r['spearman_rho']}, p = {r['p_value']}")
    print(f"  {r['test']} {r['outcome']} ~ {r['predictor']}{' | ' + r['controls'] if r['controls'] else ''} "
          f"[{r['method']}, {r['sample']}]: {stat}; N = {r['n']}, provinces = {r['provinces']}, years = {r['years']}")
print("Chart names: " + ", ".join(f"{k} {a} named, {c} on a clash" for k, (a, c) in labelled.items())
      + "; T3 groups " + ", ".join(f"{k} {a} of {b}" for k, (a, b) in named_t3.items()))
