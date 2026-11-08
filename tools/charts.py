"""Shared chart styling and labelling for every script in analysis/.

Colours follow the reference data-viz palette: a light chart surface, text in ink tokens,
categorical slots in fixed order, a blue ramp for ordered bands, and a recessive grid.
"""

import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# Surface, ink and chrome
SURFACE = "#fcfcfb"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
TEXT_MUTED = "#8a8985"
GRID = "#e4e3df"
CUT = "#9b9a96"

# Categorical slots in fixed order, and the neutral used for "everything else"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
NEUTRAL = "#c3c2b7"

# Blue ramp steps for ordered bands, lightest first (no lighter than step 250 on the light surface)
ORDINAL_BLUE = ["#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]

# Province names kept in capitals when the BPS upper-case name is title-cased
UPPER_WORDS = {"DKI", "DI"}


def display_name(name):
    """Title-case a BPS province name, keeping abbreviations such as DKI and DI in capitals."""
    return " ".join(w if w in UPPER_WORDS else w.capitalize() for w in name.split())


def new_figure(width=14, height=10):
    """Return a figure and axes on the chart surface."""
    fig, ax = plt.subplots(figsize=(width, height), dpi=200)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    return fig, ax


def style_axes(ax, xlabel="", ylabel="", grid_axis="both"):
    """Make grid and axes recessive: hairline solid grid, no top or right spine, ink-coloured labels."""
    ax.grid(color=GRID, lw=0.8, zorder=0, axis=grid_axis)
    ax.set_axisbelow(True)
    for side in ["top", "right"]:
        ax.spines[side].set_visible(False)
    for side in ["left", "bottom"]:
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=TEXT_SECONDARY, labelsize=9, length=0)
    ax.set_xlabel(xlabel, color=TEXT_SECONDARY, fontsize=10)
    ax.set_ylabel(ylabel, color=TEXT_SECONDARY, fontsize=10)


def finish(fig, title, subtitle, note, path, left=0.06, right=0.98, top=0.9, bottom=0.1, wrap=190):
    """Add title, subtitle and source note, then save the figure on the chart surface."""
    fig.text(left, 0.965, title, fontsize=15, fontweight="bold", color=TEXT_PRIMARY)
    fig.text(left, 0.935, subtitle, fontsize=10, color=TEXT_SECONDARY)
    fig.text(left, 0.015, textwrap.fill(note, wrap), fontsize=7.5, color=TEXT_MUTED)
    fig.subplots_adjust(left=left, right=right, top=top, bottom=bottom)
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def place_labels(ax, xs, ys, labels, fontsize=7.5, sizes=None):
    """Place one label per point, trying offsets around it and skipping any that overlap a placed label or point.

    sizes gives each point's marker area in points squared, so labels clear large markers.
    """
    fig = ax.figure
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    pts = ax.transData.transform(list(zip(xs, ys)))
    scale = fig.dpi / 72
    radius = [max(5, (s ** 0.5) / 2 * scale) if sizes is not None else 5 for s in (sizes if sizes is not None else [0] * len(xs))]
    placed = []
    # Points are obstacles too, as boxes the size of their marker
    obstacles = [(px - r, py - r, px + r, py + r) for (px, py), r in zip(pts, radius)]
    # Candidate offsets: eight directions at growing distances; past the first ring a leader line is drawn
    directions = [(1, 0, "left", "center"), (-1, 0, "right", "center"), (0, 1, "center", "bottom"),
                  (0, -1, "center", "top"), (1, 1, "left", "bottom"), (-1, 1, "right", "bottom"),
                  (1, -1, "left", "top"), (-1, -1, "right", "top")]
    # Label the points farthest from the crowd first, then fit the crowded ones around them
    order = sorted(range(len(labels)), key=lambda i: -min(
        [abs(pts[i][0] - pts[j][0]) + abs(pts[i][1] - pts[j][1]) for j in range(len(labels)) if j != i] or [0]))
    for i in order:
        # Rings of offsets in points; with marker sizes they start at the marker's edge
        if sizes is None:
            rings, shrink = (6, 14, 22, 30, 40), 4
        else:
            base = radius[i] / scale + 1
            rings, shrink = tuple(base + r for r in (1, 9, 17, 25, 35)), base
        offsets = [(dx * r, dy * r, ha, va) for r in rings for dx, dy, ha, va in directions]
        best = None
        for dx, dy, ha, va in offsets:
            leader = {"arrowstyle": "-", "color": TEXT_MUTED, "lw": 0.6, "shrinkA": 0, "shrinkB": shrink} \
                if max(abs(dx), abs(dy)) > rings[0] else None
            t = ax.annotate(labels[i], (xs[i], ys[i]), xytext=(dx, dy), textcoords="offset points",
                            ha=ha, va=va, fontsize=fontsize, color=TEXT_PRIMARY, arrowprops=leader)
            bb = t.get_window_extent(renderer)
            box = (bb.x0 - 1, bb.y0 - 1, bb.x1 + 1, bb.y1 + 1)
            clash = any(not (box[2] < o[0] or box[0] > o[2] or box[3] < o[1] or box[1] > o[3])
                        for o in placed + [ob for k, ob in enumerate(obstacles) if k != i])
            if not clash:
                best = (t, box)
                break
            t.remove()
        if best is None:
            # No free spot: keep the first position with a leader line so the label still reads
            t = ax.annotate(labels[i], (xs[i], ys[i]), xytext=(18, 12), textcoords="offset points",
                            ha="left", va="bottom", fontsize=fontsize, color=TEXT_PRIMARY,
                            arrowprops={"arrowstyle": "-", "color": TEXT_MUTED, "lw": 0.6})
            bb = t.get_window_extent(renderer)
            best = (t, (bb.x0, bb.y0, bb.x1, bb.y1))
        placed.append(best[1])
