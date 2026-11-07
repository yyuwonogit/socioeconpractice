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
from matplotlib.lines import Line2D
from matplotlib.text import Text
from matplotlib.ticker import FixedLocator, NullLocator
import numpy as np
import pandas as pd

# Parameters

# GRDP per capita at constant 2010 prices: the harmonised panel's grdp_pc_constant_2010_k (Rp thousand per person),
# BPS WebAPI var 286 (PDRB per kapita atas dasar harga konstan 2010) as province_panel rebuilds it; BPS marks 2025 as
# very preliminary (**). In 2025 the panel holds the 38 provinces, one unit each, keyed by BPS code
YEAR = 2025
GRDP_PC = "grdp_pc_constant_2010_k"
SHARE = province_panel.SHARP_SHARE

# Real spending per capita: BPS WebAPI var 416, '[Metode Baru] Pengeluaran per Kapita Disesuaikan', the spending part of
# the new-method Human Development Index, from the March Susenas: Rp thousand per person per year at constant 2012
# prices, adjusted for regional price differences (0 decimals). The national row 00 is left out
SPENDING = ROOT / "data/20261104_bps-province-real-spending/20261104_bps-province-real-spending.csv"
SPENDING_INDICATOR = "real_spending_per_capita"
NATIONAL = "00"

# Both series are plotted in Rp million: thousands divided by this
PER_MILLION = 1000

# Fitted line: least squares of ln(spending) on ln(GRDP per capita) over the 38 provinces, drawn from the lowest to the
# highest GRDP per capita; fitted_m = exp(fitted ln(spending)), and residual_log = ln(spending) - fitted ln(spending) in
# natural log units (x100 = log points)

# Outputs beside this script
OUT_PNG = HERE / "20261105_grdp-vs-real-spending.png"
OUT_CSV = HERE / "20261105_grdp-vs-real-spending.csv"

# Groups: high extraction is a 2025 extractive share strictly above the median of the 38 provinces' 2025 shares, drawn
# filled; low extraction is the rest, drawn hollow in the same colour
GROUP_NAMES = {True: "high extraction", False: "low extraction"}
STYLES = {
    True: {"color": charts.SERIES, "filled": True, "label": "Extractive share above the 2025 median"},
    False: {"color": charts.SERIES, "filled": False, "label": "Extractive share below the 2025 median"},
}

# Figure: size in inches at 200 dpi, and plot margins as figure fractions under the title and legend rows
FIGSIZE, DPI = (16, 15), 200
MARGINS = {"left": 0.07, "right": 0.98, "top": 0.92, "bottom": 0.06}

# Axes: log limits as a factor beyond the data on each side, and plain-number ticks
X_PAD, Y_PAD = 1.12, 1.05
XTICKS = [10, 15, 20, 30, 50, 75, 100, 150, 200, 300]
YTICKS = [6, 7, 8, 10, 12, 15, 20]

# Marks: fitted line and residual segments (colour, width in points)
LINE_COLOR, LINE_WIDTH = charts.TEXT_SECONDARY, 1.4
RESIDUAL_COLOR, RESIDUAL_WIDTH = charts.TEXT_MUTED, 0.7

# Labels: pixels that every name and leader keep from the fitted line. The strip through a point that its own name and
# leader keep out of, so no leader runs vertically like a residual segment and no name sits on its segment: half-width
# in pixels, and reach in points toward the line (along the segment) and away from it (enough to stop a leader, not a
# name just above or below). The points from the centre of every other point that a name and its leader keep, a little
# beyond the marker. The band beside every other point that a name and its leader keep out of, where a name would read
# as that point's: half-width and half-height in points. A leader is measured from this many points short of its
# point, as place_labels measures it; and the orders in which the names are placed, while some find no free spot
LINE_ROOM = 2.5
STRIP_WIDTH, STRIP_TOWARD, STRIP_AWAY = 2, 7, 4.5
DOT_ROOM = 4.5
BESIDE_WIDTH, BESIDE_HEIGHT = 12, 2.2
LEADER_CLEAR = 4
LABEL_TRIES = 8

# Texts
TITLE = "GRDP per capita against real spending per capita, Indonesian provinces, 2025"
XLABEL = "GRDP per capita, Rp million at constant 2010 prices, 2025, log scale"
YLABEL = "Real spending per capita, Rp million per year at constant 2012 prices, 2025, log scale"
FIT_LABEL = "Fitted line, slope {:.2f}"
LABEL_SIZE = 7

# Decimals kept in the table's derived columns
DECIMALS = 6

# Functions

def read_dataset(path):
    """Read a long dataset with every column as text, so codes and empty statuses survive, and turn values to numbers."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df["value"] = df["value"].astype(float)
    return df


def fit_log_line(x, y):
    """Least squares of ln(y) on ln(x); return the slope, the intercept and R squared."""
    lx, ly = np.log(x), np.log(y)
    slope, intercept = np.polyfit(lx, ly, 1)
    residual = ly - (intercept + slope * lx)
    r2 = 1 - (residual ** 2).sum() / ((ly - ly.mean()) ** 2).sum()
    return slope, intercept, r2


def segment_boxes(start, end, room, step=3):
    """Return small boxes in display pixels, room pixels from the centre, every step pixels along a straight segment."""
    n = int(np.hypot(end[0] - start[0], end[1] - start[1]) // step) + 1
    return [(start[0] + (end[0] - start[0]) * k / n - room, start[1] + (end[1] - start[1]) * k / n - room,
             start[0] + (end[0] - start[0]) * k / n + room, start[1] + (end[1] - start[1]) * k / n + room)
            for k in range(n + 1)]


def set_log_ticks(axis, ticks, low, high):
    """Show the ticks inside a log axis's limits as plain numbers, with no minor ticks."""
    ticks = [v for v in ticks if low <= v <= high]
    axis.set_major_locator(FixedLocator(ticks))
    axis.set_minor_locator(NullLocator())
    axis.set_ticklabels([str(v) for v in ticks])


def leader_boxes(t, point, renderer, clear):
    """Return small boxes in display pixels along a label's leader, from the corner or edge of its text that the leader
    leaves to clear pixels short of its point, or none for a label without a leader."""
    if not t.arrowprops:
        return []
    bb = Text.get_window_extent(t, renderer)
    rx, ry = t.arrowprops.get("relpos", (0.5, 0.5))
    start = np.array([bb.x0 + rx * bb.width, bb.y0 + ry * bb.height])
    end = np.asarray(point, dtype=float)
    gap = np.hypot(*(start - end))
    if gap <= clear:
        return []
    return segment_boxes(start, end + (start - end) * clear / gap, 1)


def name_points(ax, xs, ys, names, avoid, strips, room, beside, clear, fontsize, cuts, tries):
    """Name the points one at a time with charts.place_labels, the most crowded first.

    Each name and leader keeps clear of the boxes in avoid, of its own point's strip, of the box room pixels from the
    centre of every other point, of the band beside every other point (beside: half-width and half-height in pixels),
    and of the names and leaders placed before it. While some names find no free spot, the names are placed again with
    those first, up to tries orders, and the order with the fewest misses is kept. Returns the names that found no free
    spot and sit at place_labels' fallback position.
    """
    fig = ax.figure
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    pts = ax.transData.transform(np.column_stack([xs, ys]))
    others = [[(px - room, py - room, px + room, py + room),
               (px - beside[0], py - beside[1], px + beside[0], py + beside[1])] for px, py in pts]
    nearest = [min(np.hypot(*(pts[i] - pts[j])) for j in range(len(pts)) if j != i) for i in range(len(pts))]

    def run(order):
        """Place the names in order; return the labels drawn and the points whose names found no free spot."""
        placed, made, missed = [], [], []
        for i in order:
            keep = avoid + [strips[i]] + [b for j in range(len(pts)) if j != i for b in others[j]] + placed
            before = set(ax.texts)
            box = charts.place_labels(ax, list(xs), list(ys), [n if k == i else "" for k, n in enumerate(names)],
                                      fontsize=fontsize, avoid=keep, cuts=cuts, halo=True)[0]
            t = next(t for t in ax.texts if t not in before)
            made.append(t)
            if charts.touches(box, keep, pad=0):
                missed.append(i)
            placed += [box] + leader_boxes(t, pts[i], renderer, clear)
        return made, missed

    # Place the most crowded first; while names miss, place again with those first, and keep the best order
    orders = [sorted(range(len(pts)), key=lambda k: (nearest[k], k))]
    results = [run(orders[0])]
    while results[-1][1] and len(orders) < tries:
        order = results[-1][1] + [i for i in orders[-1] if i not in results[-1][1]]
        if order in orders:
            break
        for t in results[-1][0]:
            t.remove()
        orders.append(order)
        results.append(run(order))
    best = min(range(len(orders)), key=lambda k: (len(results[k][1]), k))
    if best != len(orders) - 1:
        for t in results[-1][0]:
            t.remove()
        results.append(run(orders[best]))
    return [names[i] for i in results[-1][1]]


# Steps

# Build the harmonised panel with its checks, and keep the 2025 row of each of the 38 provinces
b = province_panel.build()
year = b.panel[b.panel["year"] == YEAR][["unit", "unit_name", GRDP_PC, SHARE]]

# Read BPS's adjusted real spending per capita for 2025, without the national row
spending = read_dataset(SPENDING)
spending = spending[(spending["indicator"] == SPENDING_INDICATOR) & (spending["period"] == str(YEAR))
                    & (spending["province_code"] != NATIONAL)]

# Join the two on the BPS code, stopping if either side has a province the other lacks
if set(year["unit"]) != set(spending["province_code"]):
    raise SystemExit(f"provinces differ: {sorted(set(year['unit']) ^ set(spending['province_code']))}")
df = year.merge(spending[["province_code", "value"]], left_on="unit", right_on="province_code", validate="1:1")
df = df.sort_values("unit").reset_index(drop=True)

# Put both series in Rp million, and split high and low extraction at the median of the 2025 shares
df["grdp_pc_m"] = df[GRDP_PC] / PER_MILLION
df["real_spending_m"] = df["value"] / PER_MILLION
df["high"] = province_panel.above_median(df[SHARE]).to_numpy()
df["province"] = df["unit_name"].map(charts.display_name)

# Fit ln(spending) on ln(GRDP per capita) over the 38 provinces, with each province's fitted value and residual
slope, intercept, r2 = fit_log_line(df["grdp_pc_m"], df["real_spending_m"])
df["fitted_m"] = np.exp(intercept + slope * np.log(df["grdp_pc_m"]))
df["residual_log"] = np.log(df["real_spending_m"]) - np.log(df["fitted_m"])

# Lay out one plot under the title and legend rows, on log axes with headroom beyond the data
fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
fig.patch.set_facecolor(charts.SURFACE)
fig.subplots_adjust(**MARGINS)
ax.set_xscale("log")
ax.set_yscale("log")
xlim = (df["grdp_pc_m"].min() / X_PAD, df["grdp_pc_m"].max() * X_PAD)
ylim = (df["real_spending_m"].min() / Y_PAD, df["real_spending_m"].max() * Y_PAD)
ax.set_xlim(*xlim)
ax.set_ylim(*ylim)
set_log_ticks(ax.xaxis, XTICKS, *xlim)
set_log_ticks(ax.yaxis, YTICKS, *ylim)
charts.style_axes(ax)
ax.set_axisbelow(True)
ax.set_xlabel(XLABEL, color=charts.TEXT_SECONDARY, fontsize=10)
ax.set_ylabel(YLABEL, color=charts.TEXT_SECONDARY, fontsize=10)

# Draw the fitted line across the data range, a straight line on log-log axes
ends = np.array([df["grdp_pc_m"].min(), df["grdp_pc_m"].max()])
ax.plot(ends, np.exp(intercept + slope * np.log(ends)), color=LINE_COLOR, lw=LINE_WIDTH, zorder=2.5,
        solid_capstyle="butt")

# Join each point to the line with a thin vertical residual segment
ax.vlines(df["grdp_pc_m"], df["real_spending_m"], df["fitted_m"], color=RESIDUAL_COLOR, lw=RESIDUAL_WIDTH, zorder=2)

# Draw high extraction filled and low extraction hollow, each in its surface ring or outline
for high, style in STYLES.items():
    part = df[df["high"] == high]
    ax.scatter(part["grdp_pc_m"], part["real_spending_m"], marker="o", zorder=3,
               **charts.point_marks(style, charts.POINT_SIZE))

# Keep names and leaders off the fitted line, and each off the short vertical strip through its own point, as boxes in
# display pixels; the residual segments in the crowded middle run too close together to keep names off their full
# length, so names may cross them away from the points, broken by the halo
fig.canvas.draw()
to_px = ax.transData.transform
line_px = to_px(np.column_stack([ends, np.exp(intercept + slope * np.log(ends))]))
line_boxes = segment_boxes(line_px[0], line_px[1], LINE_ROOM)
toward, away = STRIP_TOWARD * fig.dpi / 72, STRIP_AWAY * fig.dpi / 72
strips = [(px - STRIP_WIDTH, py - (toward if above else away), px + STRIP_WIDTH, py + (away if above else toward))
          for (px, py), above in zip(to_px(df[["grdp_pc_m", "real_spending_m"]].to_numpy()), df["residual_log"] > 0)]

# Name every province beside its point, one at a time and the most crowded first, each name clear of the other points.
# Cut lines at the plot's lower-left corner put every point in one quadrant, so place_labels keeps each name inside the
# plot, checks that its leader crosses nothing kept off and tries two further rings
pt = fig.dpi / 72
missed = name_points(ax, df["grdp_pc_m"].to_numpy(), df["real_spending_m"].to_numpy(), df["province"].tolist(),
                     line_boxes, strips, DOT_ROOM * pt, (BESIDE_WIDTH * pt, BESIDE_HEIGHT * pt), LEADER_CLEAR * pt,
                     LABEL_SIZE, (xlim[0], ylim[0]), LABEL_TRIES)
if missed:
    print(f"no free spot for: {', '.join(missed)}")

# Title, and a legend row of the two groups and the fitted line with its slope, then save without a software stamp
handles = [charts.legend_key(style, high) for high, style in STYLES.items()]
handles.append(Line2D([], [], color=LINE_COLOR, lw=LINE_WIDTH, label=FIT_LABEL.format(slope)))
charts.finish(fig, TITLE, handles, OUT_PNG, left=MARGINS["left"])

# Write every plotted value, by BPS code, with the group, the fitted value and the residual
df["extractive_share_pct"] = df[SHARE]
df["group"] = df["high"].map(GROUP_NAMES)
for column in ["grdp_pc_m", "real_spending_m", "fitted_m", "residual_log"]:
    df[column] = df[column].round(DECIMALS)
df[["unit", "province", "extractive_share_pct", "group", "grdp_pc_m", "real_spending_m", "fitted_m",
    "residual_log"]].to_csv(OUT_CSV, index=False, encoding="utf-8", lineterminator="\n")

# Report the slope, R squared, each group's mean residual in log points and the five provinces furthest below the line
print(f"slope {slope:.4f}, intercept {intercept:.4f}, R2 {r2:.4f}, n {len(df)}")
for high, name in GROUP_NAMES.items():
    part = df[df["high"] == high]
    print(f"{name}: n {len(part)}, mean residual {100 * part['residual_log'].mean():+.1f} log points")
for _, row in df.nsmallest(5, "residual_log").iterrows():
    print(f"  {row['province']} ({row['unit']}): {100 * row['residual_log']:+.1f} log points, {row['group']}, "
          f"share {row['extractive_share_pct']:.1f}%")
print(f"Wrote {OUT_PNG.relative_to(ROOT)} and {OUT_CSV.relative_to(ROOT)}")
