"""Shared chart code for every analysis script in analysis/.

An analysis script adds tools/ to sys.path and imports this module, as build scripts do for
cleaning.py. It holds the colour tokens, province display names, label placement, the
four-quadrant scatter and the interactive 3D sphere page, so every chart shares one look and no
script redefines them. Static charts are drawn off screen with the Agg backend and saved as PNG
files; sphere pages are single HTML files drawn with three.js.
"""

import json
import math
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import patheffects
from matplotlib.lines import Line2D
from matplotlib.text import Text
from matplotlib.ticker import FixedLocator, NullLocator
import numpy as np
import pandas as pd

# Chart colours: one series on a light surface, text in ink tokens, recessive grid
SURFACE = "#fcfcfb"
SERIES = "#2a78d6"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
TEXT_MUTED = "#8a8985"
GRID = "#e4e3df"
CUT = "#9b9a96"

# Province names kept in capitals when the BPS upper-case name is title-cased
UPPER_WORDS = {"DKI", "DI"}

# Candidate ticks for a log axis; the ones inside the axis range are shown
LOG_TICKS = [20, 30, 50, 75, 100, 150, 200, 300, 400]

# Marker area of a point and of an off-scale triangle, in points squared
POINT_SIZE = 46
EDGE_SIZE = 70

# Stroke width, in points, of the surface-coloured halo around label text on a chart that asks for one
HALO = 2.0

# Times a chart may be redrawn while its y axis grows to fit flag names
GROW_PASSES = 6


def display_name(name):
    """Title-case a BPS province name, keeping abbreviations such as DKI and DI in capitals."""
    return " ".join(w if w in UPPER_WORDS else w.capitalize() for w in name.split())


def label_text(value):
    """Return a point's label as text, with None or a missing value as an empty label."""
    return "" if pd.isna(value) else str(value)


def point_marks(style, size):
    """Return the scatter arguments that draw a point style at a marker area in points squared.

    A filled style sits inside a 2-point ring in the surface colour, so overlapping points stay
    legible. A hollow style is a 1.2-point outline in the style's colour around the surface colour,
    drawn along the edge of a filled point's visible disc, so both styles read at the same size.
    A hollow style's 'face' key, when present, replaces the surface colour inside the outline: 'none'
    leaves a filled point beneath a hollow one in view.
    """
    color = style.get("color", SERIES)
    if style.get("filled", True):
        return {"s": size, "facecolor": color, "edgecolor": SURFACE, "linewidth": 2}
    return {"s": (math.sqrt(size) - 2) ** 2, "facecolor": style.get("face", SURFACE), "edgecolor": color,
            "linewidth": 1.2}


def legend_key(style, value):
    """Return a legend entry drawn like the points of a style, named by its 'label' or the group value."""
    marks = point_marks(style, POINT_SIZE)
    return Line2D([], [], linestyle="none", marker=style.get("marker", "o"), markersize=math.sqrt(marks["s"]),
                  markerfacecolor=marks["facecolor"], markeredgecolor=marks["edgecolor"],
                  markeredgewidth=marks["linewidth"], label=style.get("label", str(value)))


def log_ticks(low, high):
    """Return plain-number ticks for a log axis running from low to high.

    Gives the LOG_TICKS inside the range when at least two fall inside, otherwise the 1-2-5 steps of
    each decade inside it, otherwise None, which leaves matplotlib's own log ticks.
    """
    ticks = [v for v in LOG_TICKS if low <= v <= high]
    if len(ticks) >= 2:
        return ticks
    decades = range(math.floor(math.log10(low)), math.ceil(math.log10(high)) + 1)
    ticks = [m * 10 ** e for e in decades for m in (1, 2, 5) if low <= m * 10 ** e <= high]
    return ticks if len(ticks) >= 2 else None


def place_labels(ax, xs, ys, labels, fontsize=7.5, avoid=None, cuts=None, leader=None, halo=False):
    """Place one label per point, trying offsets around it and skipping any that overlap a placed label or point.

    A point whose label is empty stays an obstacle for the other labels but gets no label itself.
    avoid: further boxes in display pixels, (x0, y0, x1, y1), that labels keep clear of, such as text drawn earlier.
    The options below change nothing when left at their defaults.
    cuts: (x, y) positions of the two cut lines in data units. Each label then stays inside its point's quadrant of
        the plot: on its point's side of both lines, a point on a line counting as right of it or above it. A label
        is then judged by its text alone and its leader as a line, which leaves the label from the corner or edge
        nearest the point and crosses no label, point or text; two further rings are tried; and when a label finds
        no free spot, the labels are placed again with that one first.
    leader: line style of the leader lines, {"color": ..., "lw": ...}; TEXT_MUTED at 0.6 points by default.
    halo: draw each label with a thin halo in the surface colour, so grid lines stop short of its letters.
    Returns the boxes of the labels placed, in display pixels.
    """
    fig = ax.figure
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    pts = ax.transData.transform(list(zip(xs, ys)))
    # Leader style, and the halo when asked for
    line = {"color": TEXT_MUTED, "lw": 0.6, **(leader or {})}
    extra = {"path_effects": [patheffects.withStroke(linewidth=HALO, foreground=SURFACE)]} if halo else {}
    # Points are obstacles too, as 10-pixel boxes
    obstacles = [(px - 5, py - 5, px + 5, py + 5) for px, py in pts]
    # Candidate offsets: eight directions at growing distances; past the first ring a leader line is drawn
    directions = [(1, 0, "left", "center"), (-1, 0, "right", "center"), (0, 1, "center", "bottom"),
                  (0, -1, "center", "top"), (1, 1, "left", "bottom"), (-1, 1, "right", "bottom"),
                  (1, -1, "left", "top"), (-1, -1, "right", "top")]
    offsets = [(dx * r, dy * r, ha, va) for r in (6, 14, 22, 30, 40) for dx, dy, ha, va in directions]
    # With cuts: each point's quadrant in pixels, the plot frame, and two further rings
    if cuts is not None:
        cx, cy = ax.transData.transform(cuts)
        sides = [(x >= cuts[0], y >= cuts[1]) for x, y in zip(xs, ys)]
        frame = ax.get_window_extent(renderer)
        offsets += [(dx * r, dy * r, ha, va) for r in (52, 66) for dx, dy, ha, va in directions]
        px = fig.dpi / 72

    def fitted(i, t, arrow, others):
        """With cuts, return a label's text box and the small boxes along its leader when the text stays in its
        point's quadrant and touches nothing and the leader crosses nothing, else None."""
        t.get_window_extent(renderer)
        bb = Text.get_window_extent(t, renderer)
        box = (bb.x0 - 1, bb.y0 - 1, bb.x1 + 1, bb.y1 + 1)
        right, top = sides[i]
        if not ((box[0] > cx if right else box[2] < cx) and (box[1] > cy if top else box[3] < cy)
                and frame.x0 < box[0] and box[2] < frame.x1 and frame.y0 < box[1] and box[3] < frame.y1):
            return None
        if touches(box, others, pad=0):
            return None
        trail = []
        if arrow is not None:
            # The leader runs from the label's corner or edge nearest the point to just short of the point
            start = (bb.x0 + arrow["relpos"][0] * bb.width, bb.y0 + arrow["relpos"][1] * bb.height)
            steps = int(math.dist(start, pts[i]) // 3) + 1
            for k in range(steps + 1):
                p = (start[0] + (pts[i][0] - start[0]) * k / steps, start[1] + (pts[i][1] - start[1]) * k / steps)
                if math.dist(p, pts[i]) > 4 * px:
                    trail.append((p[0] - 1, p[1] - 1, p[0] + 1, p[1] + 1))
            if any(touches(b, others, pad=0) for b in trail):
                return None
        return box, trail

    def run(order):
        """Label the points in order; return the labels drawn, their boxes and the points that found no free spot."""
        # Labels keep clear of the boxes given by the caller as well as of the labels placed here
        placed = list(avoid or [])
        made, boxes, missed = [], [], []
        for i in order:
            # A point without label text keeps its obstacle box and gets no label
            if not labels[i]:
                continue
            best = None
            for dx, dy, ha, va in offsets:
                arrow = {"arrowstyle": "-", "color": line["color"], "lw": line["lw"], "shrinkA": 0, "shrinkB": 4} \
                    if max(abs(dx), abs(dy)) > 6 else None
                if arrow is not None and cuts is not None:
                    # The leader leaves the label from its corner or edge nearest the point
                    arrow["relpos"] = (0.5 - 0.5 * (dx > 0) + 0.5 * (dx < 0), 0.5 - 0.5 * (dy > 0) + 0.5 * (dy < 0))
                t = ax.annotate(labels[i], (xs[i], ys[i]), xytext=(dx, dy), textcoords="offset points",
                                ha=ha, va=va, fontsize=fontsize, color=TEXT_PRIMARY, arrowprops=arrow, **extra)
                if cuts is None:
                    bb = t.get_window_extent(renderer)
                    box = (bb.x0 - 1, bb.y0 - 1, bb.x1 + 1, bb.y1 + 1)
                    clash = any(not (box[2] < o[0] or box[0] > o[2] or box[3] < o[1] or box[1] > o[3])
                                for o in placed + [ob for k, ob in enumerate(obstacles) if k != i])
                    if not clash:
                        best = (t, box, [])
                        break
                else:
                    found = fitted(i, t, arrow, placed + [ob for k, ob in enumerate(obstacles) if k != i])
                    if found is not None:
                        best = (t, *found)
                        break
                t.remove()
            if best is None:
                # No free spot: keep the first position with a leader line so the label still reads, pointing into
                # the point's own quadrant when there are cuts
                missed.append(i)
                right, top = sides[i] if cuts is not None else (True, True)
                t = ax.annotate(labels[i], (xs[i], ys[i]), xytext=(18 if right else -18, 12 if top else -12),
                                textcoords="offset points", ha="left" if right else "right",
                                va="bottom" if top else "top", fontsize=fontsize, color=TEXT_PRIMARY,
                                arrowprops={"arrowstyle": "-", "color": line["color"], "lw": line["lw"]}, **extra)
                bb = t.get_window_extent(renderer)
                best = (t, (bb.x0, bb.y0, bb.x1, bb.y1), [])
            made.append(best[0])
            placed += [best[1]] + best[2]
            boxes.append(best[1])
        return made, boxes, missed

    # Label the points farthest from the crowd first, then fit the crowded ones around them
    order = sorted(range(len(labels)), key=lambda i: -min(
        [abs(pts[i][0] - pts[j][0]) + abs(pts[i][1] - pts[j][1]) for j in range(len(labels)) if j != i] or [0]))
    made, boxes, missed = run(order)
    # With cuts, place the labels again while some found no free spot, those first, and keep the best attempt
    if cuts is not None:
        orders, counts = [order], [len(missed)]
        while missed and len(orders) < 4:
            order = missed + [i for i in order if i not in missed]
            if order in orders:
                break
            for t in made:
                t.remove()
            made, boxes, missed = run(order)
            orders.append(order)
            counts.append(len(missed))
        best = counts.index(min(counts))
        if best != len(orders) - 1:
            for t in made:
                t.remove()
            made, boxes, missed = run(orders[best])
    return boxes


def box_of(artist, renderer, pad=0):
    """Return an artist's extent in display pixels as (x0, y0, x1, y1), grown by pad pixels on every side."""
    bb = artist.get_window_extent(renderer)
    return (bb.x0 - pad, bb.y0 - pad, bb.x1 + pad, bb.y1 + pad)


def touches(box, others, pad=1):
    """Return True when a box, grown by pad pixels, overlaps any of the other boxes; boxes are (x0, y0, x1, y1)."""
    return any(not (box[2] + pad < o[0] or box[0] - pad > o[2] or box[3] + pad < o[1] or box[1] - pad > o[3])
               for o in others)


def flag_labels(ax, xs, ys, labels, split, avoid=(), lines=(), fontsize=7.5, cut=None, merge=0, leader_room=0,
                dot_room=0, stack_gap=0, leader=None, halo=False, grow=False):
    """Label the points of a crowded band, each name beside the top of a thin vertical leader rising from its point.

    Names sit in rows one text height apart, counted up from the lowest labelled point, and each point takes
    the lowest row where its name and leader touch nothing. Row 0 sets the name beside the point with no
    leader, but only where no other point sits near either end of the name, so the name cannot be read as
    another point's. Each higher row hangs the name beside a leader rising from the point. Points left of
    split, an x position in data units, hang their names to the left and are placed from left to right; the
    others hang them to the right and are placed from right to left. Each side then climbs like a staircase
    toward split. A name may hang the other way when that row is lower, unless it would cover a point still
    to be placed, whose leader it would then block; so no leader crosses a name. A point whose label is
    empty gets no name and stays an obstacle.

    avoid: boxes in display pixels, (x0, y0, x1, y1), that names and leaders keep clear of, such as text drawn
        earlier. lines: boxes that names keep clear of but leaders may cross, such as cut lines.
    The options below change nothing when left at their defaults.
    cut: a y position in data units, normally the y cut line. Points below it hang their names below the band
        instead, in rows counted down from the highest of them, each name beside the foot of a leader dropping
        from its point, and those points are placed after the rising ones. Every name then also keeps to its
        point's side of split and of cut, so it sits in its point's quadrant.
    merge: pixels. Points on the same side of split and of cut whose markers overlap, and whose leaders would run
        less than merge pixels apart, share one flag: a single leader from the middle of the group, leaving it
        beyond its outermost marker, and their names joined with commas from left to right.
    leader_room: pixels that a name keeps across from every leader that is not its own, so it cannot be read as
        that leader's name, and from the points still waiting for a name, where their leaders will run.
    dot_room: pixels that a name keeps, in every direction, from the marker of every point without a leader: a
        point whose label is empty here, which is labelled beside itself later, and a flag set beside its point
        in row 0, which is set there only when its points keep that room from the names already placed. So no
        name can be read as the label of such a point by sitting next to, under or over it.
    stack_gap: pixels. Two names in neighbouring rows that overlap across must hang on the same side of leaders at
        least stack_gap apart, so they never read as one name of two lines.
    leader: line style of the leaders, {"color": ..., "lw": ...}; TEXT_MUTED at 0.6 points by default.
    halo: draw each name with a thin halo in the surface colour, so grid lines stop short of its letters.
    grow: let rows run past the edge of the plot that they grow toward, for a caller that then extends the axis.
    Returns the boxes of the names and leaders drawn, for labels placed later to avoid.
    """
    # Nothing to flag without a name
    if not any(labels):
        return []
    fig = ax.figure
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    px = fig.dpi / 72
    pts = ax.transData.transform(list(zip(xs, ys)))
    frame = ax.get_window_extent(renderer)
    avoid, lines = list(avoid), list(lines)
    # Leader style, and the halo when asked for
    line = {"color": TEXT_MUTED, "lw": 0.6, **(leader or {})}
    extra = {"path_effects": [patheffects.withStroke(linewidth=HALO, foreground=SURFACE)]} if halo else {}
    # Gaps in points: a name beside its point sits where place_labels puts its first ring and keeps the same
    # room free of other points beyond either end; a name beside a leader sits just off it; a leader starts
    # just above its point's marker
    beside, off_leader, clear = 6, 2, 3.5
    # Every point is an obstacle, as a box that covers its marker. A leader may rise through the markers that
    # overlap its own point's, since it leaves that cluster of markers from its top, and a name beside its
    # point ignores only the points drawn on top of its own
    dots = [(qx - 8, qy - 8, qx + 8, qy + 8) for qx, qy in pts]
    # With a cut, the pixel positions of both lines, which every name keeps to its point's side of
    if cut is not None:
        cx, cy = ax.transData.transform((split, cut))

    # Gather the labelled points into flags: each point is one flag, rising above the band unless a cut puts it
    # below the line, where it hangs
    labelled = [i for i in range(len(xs)) if labels[i]]
    rises = {i: cut is None or ys[i] >= cut for i in labelled}
    groups = {i: [i] for i in labelled}
    if merge:
        # Join flags while a point sits less than merge pixels across from a point of another flag, with
        # overlapping markers, on the same side of both lines; the lower index keeps the group
        owner = {i: i for i in labelled}
        for a in labelled:
            for b in labelled:
                if (owner[a] != owner[b] and rises[a] == rises[b] and (xs[a] >= split) == (xs[b] >= split)
                        and abs(pts[a][0] - pts[b][0]) < merge and math.dist(pts[a], pts[b]) < 16):
                    keep, drop = sorted((owner[a], owner[b]))
                    groups[keep] += groups.pop(drop)
                    for m in groups[keep]:
                        owner[m] = keep
    flags = []
    for key in sorted(groups):
        # A flag's names read from left to right, and its leader leaves from the middle of its points, beyond
        # the outermost marker in the direction it runs
        members = sorted(groups[key], key=lambda i: (xs[i], i))
        rise = rises[members[0]]
        if len(members) == 1:
            i = members[0]
            anchor, at, middle = (xs[i], ys[i]), (pts[i][0], pts[i][1]), pts[i][1]
        else:
            at = (sum(pts[m][0] for m in members) / len(members), (max if rise else min)(pts[m][1] for m in members))
            anchor = tuple(ax.transData.inverted().transform(at))
            middle = sum(pts[m][1] for m in members) / len(members)
        # Measure the name once
        text = ", ".join(labels[m] for m in members)
        t = ax.text(0, 0, text, fontsize=fontsize)
        bb = t.get_window_extent(renderer)
        t.remove()
        # The markers its leader may not cross (beyond the group's cluster) and those its name keeps room from
        near = [min(math.dist(pts[j], pts[m]) for m in members) for j in range(len(pts))]
        flags.append({"text": text, "members": members, "first": members[0] if len(members) == 1 else min(members),
                      "rise": rise, "right": xs[members[0]] >= split, "anchor": anchor, "at": at,
                      "middle": middle, "lo": min(pts[m][0] for m in members), "hi": max(pts[m][0] for m in members),
                      "width": bb.width, "height": bb.height,
                      "far": [d for j, d in enumerate(dots) if near[j] >= 16],
                      "apart": [d for j, d in enumerate(dots) if near[j] >= 3],
                      "loose": [d for j, d in enumerate(dots) if near[j] >= 3 and not labels[j]]})

    # Rows are one text height plus 2 pixels apart: rising rows counted up from just above the lowest rising
    # flag, hanging rows down from just below the highest hanging flag; with grow, rows may pass the plot's edge
    height = max(f["height"] for f in flags)
    step = height + 2
    more = len(flags) if grow else 0
    base = top = None
    rows_up = rows_down = 0
    if any(f["rise"] for f in flags):
        base = min(f["at"][1] for f in flags if f["rise"]) + clear * px
        rows_up = int((frame.y1 - base) // step) + 1 + more
    if not all(f["rise"] for f in flags):
        top = max(f["at"][1] for f in flags if not f["rise"]) - clear * px
        rows_down = int((top - frame.y0) // step) + 1 + more

    def candidate(c, row, side):
        """Return the name box, the leader box (None in row 0), the name's offset in points from the flag's anchor
        and the x where the name meets its leader or point; or None for a row on the wrong side of the flag."""
        f = flags[c]
        qx, qy = f["at"]
        width = f["width"]
        if row == 0:
            edge = f["hi"] if side > 0 else f["lo"]
            x0 = edge + beside * px if side > 0 else edge - beside * px - width
            mid = f["middle"]
            offset = (side * beside, 0) if len(f["members"]) == 1 else \
                (side * beside + (edge - qx) / px, (mid - qy) / px)
            return (x0, mid - height / 2, x0 + width, mid + height / 2), None, offset, edge
        if f["rise"]:
            y0 = base + (row - 1) * step
            if y0 < qy + clear * px:
                return None
            mid = y0 + height / 2
            lead = (qx - 1, qy + clear * px, qx + 1, mid)
        else:
            y0 = top - (row - 1) * step - height
            if y0 + height > qy - clear * px:
                return None
            mid = y0 + height / 2
            lead = (qx - 1, mid, qx + 1, qy - clear * px)
        x0 = qx + off_leader * px if side > 0 else qx - off_leader * px - width
        return (x0, y0, x0 + width, y0 + height), lead, (side * off_leader, (mid - qy) / px), qx

    def fits(c, cand, side):
        """Return True when a name stays inside the axes (and, with a cut, its quadrant), blocks no flag still to be
        placed, keeps its distances, and it and its leader touch nothing placed."""
        f = flags[c]
        name, lead, _, meets = cand
        # The name stays inside the axes, except past the edge its rows grow toward when the axis will grow, and
        # clear of text, lines, points, names and leaders
        inside = (frame.x0 + 2 < name[0] and name[2] < frame.x1 - 2
                  and (frame.y0 + 2 < name[1] or grow and not f["rise"])
                  and (name[3] < frame.y1 - 2 or grow and f["rise"]))
        if not inside or touches(name, avoid + lines + dots + names + leaders):
            return False
        # With a cut, the name keeps to its point's side of both lines
        if cut is not None and not ((name[0] > cx if f["right"] else name[2] < cx)
                                    and (name[1] > cy if f["rise"] else name[3] < cy)):
            return False
        # The name covers no flag still to be placed on its side of the band, whose leader would have to cross it,
        # and with leader_room it keeps that room from where those leaders will run
        reach = max(1, leader_room)
        if any(name[0] - reach <= flags[k]["at"][0] <= name[2] + reach for k in pending
               if k != c and flags[k]["rise"] == f["rise"]):
            return False
        # The name keeps its distance from leaders and markers not its own, and from names in the rows beside it
        if leader_room and touches((name[0] - leader_room, name[1], name[2] + leader_room, name[3]), leaders, pad=0):
            return False
        if dot_room and touches((name[0] - dot_room, name[1] - dot_room, name[2] + dot_room, name[3] + dot_room),
                                f["loose"] + [d for k, d in lone if k != c], pad=0):
            return False
        # A name set beside its point keeps that room between its point and the names already placed
        if dot_room and lead is None and any(touches((d[0] - dot_room, d[1] - dot_room, d[2] + dot_room,
                                                      d[3] + dot_room), names, pad=0)
                                             for d in (dots[m] for m in f["members"])):
            return False
        if stack_gap and any(0 <= max(o[1] - name[3], name[1] - o[3]) < height and name[0] < o[2] and o[0] < name[2]
                             and (s != side or abs(m - meets) < stack_gap) for o, m, s in zip(names, meet, sides)):
            return False
        # Beside the point, the name keeps room free of other points beyond both ends
        if lead is None:
            room = (name[0] - beside * px, name[1], name[2] + beside * px, name[3])
            return not touches(room, f["apart"])
        # The leader passes no text, name or point outside its own point's cluster, and keeps its room from names
        if touches(lead, avoid + f["far"] + names, pad=0):
            return False
        return not (leader_room and touches((lead[0] - leader_room, lead[1], lead[2] + leader_room, lead[3]),
                                            names, pad=0))

    # Rising flags first, then hanging ones. On each side of split the flags are placed from the outside in with
    # names hanging away from split: points left of it climb from left to right with names to the left, and the
    # rest mirror them
    order = []
    for rise in (True, False):
        left = sorted([c for c, f in enumerate(flags) if f["rise"] == rise and not f["right"]],
                      key=lambda c: (flags[c]["at"][0], flags[c]["first"]))
        right = sorted([c for c, f in enumerate(flags) if f["rise"] == rise and f["right"]],
                       key=lambda c: (-flags[c]["at"][0], flags[c]["first"]))
        order += [(c, -1) for c in left] + [(c, 1) for c in right]
    pending = {c for c, _ in order}
    names, leaders, meet, sides = [], [], [], []
    # Markers of the flags set beside their points, which keep dot_room from the names placed after them
    lone = []
    for c, side in order:
        f = flags[c]
        # Take the row nearest the band that fits, on the flag's own side first
        choice = next(((cand, s) for row in range((rows_up if f["rise"] else rows_down) + 1) for s in (side, -side)
                       for cand in [candidate(c, row, s)] if cand is not None and fits(c, cand, s)), None)
        if choice is None:
            # No free row: set the name beside the point on its own side
            choice = (candidate(c, 0, side), side)
        (name, lead, offset, meets), s = choice
        ax.annotate(f["text"], f["anchor"], xytext=offset, textcoords="offset points",
                    ha="left" if s > 0 else "right", va="center", fontsize=fontsize, color=TEXT_PRIMARY, **extra)
        if lead is not None:
            # The leader runs from just beyond the point's marker to the middle of its name, beneath the markers
            ax.annotate("", f["anchor"], xytext=(0, offset[1]), textcoords="offset points", zorder=2,
                        arrowprops={"arrowstyle": "-", "color": line["color"], "lw": line["lw"], "shrinkA": 0,
                                    "shrinkB": clear})
            leaders.append(lead)
        else:
            lone += [(c, dots[m]) for m in f["members"]]
        names.append(name)
        meet.append(meets)
        sides.append(s)
        pending.discard(c)
    return names + leaders


def grown_ylim(ax, ylim, boxes, refs, log, margin=4):
    """Return y limits extended just far enough that boxes fit inside the plot, or ylim itself when they fit.

    boxes: (x0, y0, x1, y1) in display pixels, such as flag names, that keep their pixel distance from the band
        while the axis grows. refs: (low, high), the lowest and highest y of the band in data units, which the
        boxes below and above it are measured from. A log axis grows in log units.
    margin: pixels that must stay free between the boxes and the edge of the plot. A grown axis leaves twice
        that, so a layout that shifts a little when it is redrawn still fits.
    """
    frame = ax.get_window_extent(ax.figure.canvas.get_renderer())
    low_box, high_box = min(b[1] for b in boxes), max(b[3] for b in boxes)
    short_low, short_high = low_box < frame.y0 + margin, high_box > frame.y1 - margin
    if not (short_low or short_high):
        return ylim
    scale, back = (math.log10, lambda v: 10 ** v) if log else ((lambda v: v), (lambda v: v))
    lo, hi = scale(ylim[0]), scale(ylim[1])
    ref_lo, ref_hi = scale(refs[0]), scale(refs[1])
    # Share of the plot height needed below the lowest band point and above the highest
    below = (ax.transData.transform((1, refs[0]))[1] - low_box + 2 * margin) / frame.height
    above = (high_box - ax.transData.transform((1, refs[1]))[1] + 2 * margin) / frame.height
    # Solve for the limits that put the band points that far from the edges, moving only the edges too short
    if short_low and short_high:
        span = (ref_hi - ref_lo) / (1 - below - above)
        lo, hi = ref_lo - below * span, ref_hi + above * span
    elif short_low:
        lo = (ref_lo - below * hi) / (1 - below)
    else:
        hi = (ref_hi - above * lo) / (1 - above)
    return back(lo), back(hi)


def quadrant_chart(df, x, y, xcut, ycut, quadrant_names, xlabel, ylabel, title, subtitle, note, path,
                   logx=False, ylim=None, yunit="", logy=False, xticks=None, yticks=None,
                   xcut_label="Indonesia {:.1f}", ycut_label="Indonesia {:.1f}%",
                   label="province", group=None, styles=None,
                   band=None, low_names_at="corner", xcut_label_at="bottom", legend_cols=None,
                   note_wrap=190, bottom=None, keep_quadrants=False, flag_options=None, leader=None, halo=False,
                   grow_ylim=False, lines_over_points=False):
    """Draw a four-quadrant scatter with cut lines, quadrant names and a label on every point, and save it.

    df: one row per point, with the columns named by x, y and label, and by group when styles are used.
    xcut, ycut: positions of the vertical and horizontal cut lines, in data units.
    quadrant_names: {(right, top): name} for the names shown in the outer corners, right and top booleans.
    xlabel, ylabel, title, subtitle: axis titles and header lines.
    note: a wrapped source note at the bottom of the figure, or None (or "") for no note.
    path: the PNG file to write, 14 x 10 inches at 200 dpi.
    logx, logy: put that axis on a log scale. Limits get a factor of 1.2 of headroom on a log axis and
        8% of the data span on a linear one.
    ylim: (low, high) for the y axis; points outside it sit on the edge as triangles labelled
        '<label> (<value><yunit>, off scale)', with the value written as +0.0.
    xticks, yticks: tick values for that axis, shown as plain numbers; a log axis left at None takes
        log_ticks, so LOG_TICKS inside its range.
    xcut_label, ycut_label: format strings filled with xcut or ycut for the cut-line labels, or None
        for no label.
    label: column holding each point's label text; a point whose text is empty is drawn without a label.
    group, styles: together, give each point the style its group value names in
        styles = {value: {"label": legend text, "filled": True or False, "color": hex, "marker": "o"}},
        where every key is optional (filled, SERIES and "o" by default). A filled point sits in a
        surface ring and a hollow one is an outline of the same visible size (see point_marks); off-scale
        triangles keep their point's style. The legend shows one entry per style, in the order of
        styles, at the top right. Without them every point is filled in SERIES and there is no legend.
    The options below change nothing when left at their defaults.
    band: (low, high) in y data units, or None. Points with low <= y <= high are labelled by flag_labels:
        each name sits in a row above the band, beside the top of a leader rising from its point, and the
        rows climb toward the x cut line from both sides. The other points are labelled around themselves.
        With a band, every label also keeps clear of the cut lines, the quadrant names and the cut-line
        labels.
    low_names_at: "corner" puts the names of the two bottom quadrants in the bottom corners, and "cut"
        hangs them just under the y cut line, for a chart whose points line the bottom edge.
    xcut_label_at: "bottom" or "top", the end of the x cut line that carries its label.
    legend_cols: number of legend columns; None puts every style in one row.
    note_wrap: characters per line of the source note.
    bottom: figure fraction below the plot, holding the axis title and the note; None gives 0.1 with a
        note and 0.07 without one. A note of more than three lines needs more than 0.1.
    keep_quadrants: keep every label in its point's quadrant. The band's points below the y cut hang their
        names in rows below the band (flag_labels with cut=ycut), and labels set around a point keep to
        its side of both cut lines (place_labels with cuts).
    flag_options: further keywords for flag_labels, such as {"merge": 8, "leader_room": 17}.
    leader: line style of every leader line, {"color": ..., "lw": ...}; TEXT_MUTED at 0.6 points by default.
    halo: draw the point labels with a thin halo in the surface colour, so grid lines stop short of their
        letters.
    grow_ylim: with a band, extend the y axis beyond ylim as far as the flag rows need, so every name fits
        inside the plot; the ticks stay as yticks gives them.
    lines_over_points: draw the cut lines above the markers, so a marker's surface ring cannot hide them.
    """
    # Leave room for the note only when there is one
    if bottom is None:
        bottom = 0.1 if note else 0.07
    # Every point needs a style when the chart has groups
    if (group is None) != (styles is None):
        raise ValueError("quadrant_chart takes group and styles together")
    if group is not None and set(df[group]) - set(styles):
        raise ValueError(f"no style for group values {sorted(set(df[group]) - set(styles), key=str)}")
    if low_names_at not in ("corner", "cut") or xcut_label_at not in ("bottom", "top"):
        raise ValueError("low_names_at takes 'corner' or 'cut', and xcut_label_at 'bottom' or 'top'")

    # Set limits with headroom
    xmin, xmax = df[x].min(), df[x].max()
    if logx:
        xlim = (xmin / 1.2, xmax * 1.2)
    else:
        pad = (xmax - xmin) * 0.08
        xlim = (xmin - pad, xmax + pad)
    if ylim is None and logy:
        ylim = (df[y].min() / 1.2, df[y].max() * 1.2)
    elif ylim is None:
        ypad = (df[y].max() - df[y].min()) * 0.08
        ylim = (df[y].min() - ypad, df[y].max() + ypad)
    # Options for the labels; left at their defaults they change nothing
    place_options = {"leader": leader, "halo": halo}
    flag_kw = {**(flag_options or {}), "leader": leader, "halo": halo, "grow": grow_ylim}
    if keep_quadrants:
        place_options["cuts"] = (xcut, ycut)
        flag_kw["cut"] = ycut
    extra = {"path_effects": [patheffects.withStroke(linewidth=HALO, foreground=SURFACE)]} if halo else {}

    # Draw the chart; with grow_ylim and a band, draw it again with a taller y axis until every flag fits
    passes = GROW_PASSES if grow_ylim and band is not None else 1
    for attempt in range(passes):
        fig, ax = plt.subplots(figsize=(14, 10), dpi=200)
        fig.patch.set_facecolor(SURFACE)
        ax.set_facecolor(SURFACE)
        if band is not None:
            # Flags are laid out in pixels, so the plot takes its final place before any label is measured
            fig.subplots_adjust(left=0.06, right=0.98, top=0.9, bottom=bottom)
        if logx:
            ax.set_xscale("log")
        if logy:
            ax.set_yscale("log")
        ax.set_xlim(*xlim)
        ax.set_ylim(*ylim)

        # Split points inside the y range from those beyond it, which sit on the edge as triangles
        inside = df[(df[y] >= ylim[0]) & (df[y] <= ylim[1])]
        above, below = df[df[y] > ylim[1]], df[df[y] < ylim[0]]
        if logy:
            step = (ylim[1] / ylim[0]) ** 0.015
            top_edge, bottom_edge = ylim[1] / step, ylim[0] * step
        else:
            edge = (ylim[1] - ylim[0]) * 0.015
            top_edge, bottom_edge = ylim[1] - edge, ylim[0] + edge

        # Draw the cut lines, beneath the points or above them, then the points of each style with a surface ring
        # so overlaps stay legible
        ax.axvline(xcut, color=CUT, lw=1, zorder=3.2 if lines_over_points else 1)
        ax.axhline(ycut, color=CUT, lw=1, zorder=3.2 if lines_over_points else 1)
        parts = [({}, inside)] if group is None else [(s, inside[inside[group] == v]) for v, s in styles.items()]
        for style, part in parts:
            ax.scatter(part[x], part[y], marker=style.get("marker", "o"), zorder=3, **point_marks(style, POINT_SIZE))
        # Keep the text drawn before the point labels, which the labels of a band keep clear of
        texts = []
        for part, marker, ypos, va, dy in [(above, "^", top_edge, "top", -8), (below, "v", bottom_edge, "bottom", 8)]:
            keys = part[group].tolist() if group is not None else [None] * len(part)
            for xv, yv, text, key in zip(part[x].tolist(), part[y].tolist(), part[label].tolist(), keys):
                style = styles[key] if group is not None else {}
                ax.scatter(xv, ypos, marker=marker, zorder=3, clip_on=False, **point_marks(style, EDGE_SIZE))
                text = label_text(text)
                value = f"{yv:+.1f}{yunit}, off scale"
                texts.append(ax.annotate(f"{text} ({value})" if text else f"({value})", (xv, ypos),
                                         xytext=(9, dy), textcoords="offset points", ha="left", va=va, fontsize=7.5,
                                         color=TEXT_PRIMARY, **extra))

        # Name each quadrant in its outer corner, or the bottom two just under the y cut line
        for (right, top), name in quadrant_names.items():
            if top or low_names_at == "corner":
                texts.append(ax.text(0.99 if right else 0.01, 0.98 if top else 0.02, name, transform=ax.transAxes,
                                     ha="right" if right else "left", va="top" if top else "bottom",
                                     fontsize=11, fontweight="bold", color=TEXT_SECONDARY))
            else:
                texts.append(ax.annotate(name, (0.99 if right else 0.01, ycut), xycoords=("axes fraction", "data"),
                                         xytext=(0, -4), textcoords="offset points", ha="right" if right else "left",
                                         va="top", fontsize=11, fontweight="bold", color=TEXT_SECONDARY))

        # Label the cut lines with their values
        if xcut_label is not None and xcut_label_at == "bottom":
            texts.append(ax.annotate(xcut_label.format(xcut), (xcut, 0), xycoords=("data", "axes fraction"),
                                     xytext=(4, 4), textcoords="offset points", fontsize=8, color=TEXT_MUTED))
        elif xcut_label is not None:
            texts.append(ax.annotate(xcut_label.format(xcut), (xcut, 1), xycoords=("data", "axes fraction"),
                                     xytext=(4, -4), textcoords="offset points", va="top", fontsize=8,
                                     color=TEXT_MUTED))
        if ycut_label is not None:
            texts.append(ax.annotate(ycut_label.format(ycut), (1, ycut), xycoords=("axes fraction", "data"),
                                     xytext=(-4, 4), textcoords="offset points", ha="right", fontsize=8,
                                     color=TEXT_MUTED))

        # Style axes and grid recessively; fixed ticks read as plain numbers, a log axis has no minor ticks
        for axis, log, ticks, (low, high), set_labels in [(ax.xaxis, logx, xticks, xlim, ax.set_xticklabels),
                                                           (ax.yaxis, logy, yticks, ylim, ax.set_yticklabels)]:
            if ticks is None and log:
                ticks = log_ticks(low, high)
            if ticks is not None:
                ticks = [v for v in ticks if low <= v <= high]
                axis.set_major_locator(FixedLocator(ticks))
                if log:
                    axis.set_minor_locator(NullLocator())
                set_labels([str(v) for v in ticks])
        ax.grid(color=GRID, lw=0.8, zorder=0)
        for side in ["top", "right"]:
            ax.spines[side].set_visible(False)
        for side in ["left", "bottom"]:
            ax.spines[side].set_color(GRID)
        ax.tick_params(colors=TEXT_SECONDARY, labelsize=9, length=0)
        ax.set_xlabel(xlabel, color=TEXT_SECONDARY, fontsize=10)
        ax.set_ylabel(ylabel, color=TEXT_SECONDARY, fontsize=10)

        # Label every point inside the range; edge points were labelled with their values above
        xs, ys = inside[x].tolist(), inside[y].tolist()
        labels = [label_text(t) for t in inside[label].tolist()]
        if band is None:
            place_labels(ax, xs, ys, labels, **place_options)
        else:
            # Flag the points of the band first, then label the rest clear of the flags, the cut lines and the text
            fig.canvas.draw()
            renderer = fig.canvas.get_renderer()
            frame = ax.get_window_extent(renderer)
            cx, cy = ax.transData.transform((xcut, ycut))
            lines = [(cx - 1.5, frame.y0, cx + 1.5, frame.y1), (frame.x0, cy - 1.5, frame.x1, cy + 1.5)]
            drawn = [box_of(t, renderer, pad=2) for t in texts]
            in_band = [band[0] <= v <= band[1] for v in ys]
            flags = flag_labels(ax, xs, ys, [t if b else "" for t, b in zip(labels, in_band)], xcut,
                                avoid=drawn, lines=lines, **flag_kw)
            place_labels(ax, xs, ys, ["" if b else t for t, b in zip(labels, in_band)], avoid=drawn + lines + flags,
                         **place_options)

        # Title, subtitle, legend of the styles and the source note when there is one
        fig.text(0.06, 0.965, title, fontsize=15, fontweight="bold", color=TEXT_PRIMARY)
        fig.text(0.06, 0.935, subtitle, fontsize=10, color=TEXT_SECONDARY)
        if group is not None:
            fig.legend(handles=[legend_key(s, v) for v, s in styles.items()], loc="upper right",
                       bbox_to_anchor=(0.98, 0.975), ncol=len(styles) if legend_cols is None else legend_cols,
                       frameon=False, fontsize=9, labelcolor=TEXT_SECONDARY, handletextpad=0.4, columnspacing=1.6,
                       borderaxespad=0)
        if note:
            fig.text(0.06, 0.015, textwrap.fill(note, note_wrap), fontsize=7.5, color=TEXT_MUTED)
        fig.subplots_adjust(left=0.06, right=0.98, top=0.9, bottom=bottom)

        # With grow_ylim, stop once every flag fits inside the plot or the passes run out; otherwise grow the y axis
        # and draw again
        if not (grow_ylim and band is not None and flags) or attempt == passes - 1:
            break
        band_ys = [v for v, b in zip(ys, in_band) if b]
        grown = grown_ylim(ax, ylim, flags, (min(band_ys), max(band_ys)), logy)
        if grown == ylim:
            break
        plt.close(fig)
        ylim = grown
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


# Interactive 3D sphere pages

# three.js release the sphere pages load from the jsDelivr CDN, pinned to one version
THREE_URL = "https://cdn.jsdelivr.net/npm/three@0.160.0"

# Camera from the front-right and a little above, at this distance from the centre: x runs mostly left to right, z
# points up, and the front-to-back y axis stays visible as a diagonal instead of pointing at the viewer
SPHERE_CAMERA_DIRECTION, SPHERE_CAMERA_DISTANCE = (1.1, -1.8, 0.75), 5.6

# Points reach this share of the sphere's radius, so none sits on its surface
SPHERE_POINT_REACH = 0.94


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


def into_sphere(cube, reach=SPHERE_POINT_REACH):
    """Draw points of the cube [-1, 1]^3 into the ball of radius reach along rays from the centre.

    A point keeps the sign of each coordinate, so it stays on its own side of all three cuts through the centre.
    """
    cube = np.asarray(cube, dtype=float)
    norm = np.sqrt((cube ** 2).sum(axis=1))
    scale = np.divide(np.abs(cube).max(axis=1), norm, out=np.zeros(len(cube)), where=norm > 0)
    return cube * scale[:, None] * reach


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


def sphere_groups(keys, labels, colors, positions):
    """Return each group's label, line colour, members and constellation edges, in the order groups first appear."""
    groups = {}
    for key in dict.fromkeys(keys):
        members = [n for n, k in enumerate(keys) if k == key]
        edges = constellation(positions[members])
        groups[key] = {"label": labels[key], "color": colors[key], "members": members,
                       "edges": [[members[a], members[b]] for a, b in edges]}
    return groups


# The page around the data: styles, the scene holder, the title, the controls, the info line, the legend and the tip
SPHERE_HEAD = """<!doctype html>
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
#controls { position: absolute; top: 48px; left: 16px; z-index: 5; font-size: 13px; color: AXIS; }
#controls button { font: inherit; padding: 4px 10px; margin: 0 4px 0 0; border: 1px solid GRIDCOLOR; border-radius: 4px;
  background: #f1f0ec; color: TEXT; cursor: pointer; }
#controls button.on { background: TEXT; color: SURFACE; }
#info { position: absolute; top: 82px; left: 16px; z-index: 5; max-width: 430px; font-size: 13px; line-height: 1.45; }
#legend { position: absolute; top: 14px; right: 16px; z-index: 5; font-size: 12px; color: AXIS; }
#legend .title { font-weight: bold; margin-bottom: 4px; }
#legend .row { display: flex; align-items: center; gap: 6px; margin: 3px 0; }
#legend .dot { width: 11px; height: 11px; border-radius: 50%; display: inline-block; }
#tip { position: absolute; z-index: 6; pointer-events: none; display: none; background: #ffffff; border: 1px solid GRIDCOLOR;
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
<div id="controls"></div>
<div id="info"></div>
<div id="legend"></div>
<div id="tip"></div>
"""

# The scene: renderer, camera, wire sphere, cuts, axes, points with names, legend, controls, constellations and tips
SPHERE_SCRIPT = """<script type="module">
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
const esc = s => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

// Renderer, label layer, camera with z pointing up, and orbit controls around the centre
const renderer = new THREE.WebGLRenderer({antialias: true, preserveDrawingBuffer: true});
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
// The three cuts through the centre, where the sphere meets the plane of each reference value
scene.add(lineSet([circle((c, s) => [c, s, 0]), circle((c, s) => [c, 0, s]), circle((c, s) => [0, c, s])], D.colors.cut));

// Axes through the centre, an arrowhead at each high end, and names at both ends outside the sphere
function textLabel(text, className, position, bold) {
  const element = document.createElement("div");
  element.className = className;
  element.innerHTML = bold ? "<b>" + esc(text) + "</b>" : esc(text);
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
// The centre, where the three cuts meet
scene.add(new THREE.Mesh(new THREE.SphereGeometry(0.022, 16, 12), new THREE.MeshBasicMaterial({color: D.colors.text})));

// Points as shaded balls in their colours, each with its name just above
const ball = new THREE.SphereGeometry(0.034, 24, 16);
const names = D.points.map(p => {
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

// Legend of point colours
document.getElementById("legend").innerHTML = '<div class="title">' + esc(D.legend.title) + "</div>" +
  D.legend.items.map(item => '<div class="row"><span class="dot" style="background:' + item.color + '"></span>' +
  esc(item.label) + "</div>").join("");

// Controls: one button per constellation mode, then names on or off, and clear
document.getElementById("controls").innerHTML = "Constellation: " + D.modes.map(([m, label], i) =>
  '<button data-mode="' + m + '"' + (i === 0 ? ' class="on"' : "") + ">" + esc(label) + "</button>").join("") +
  ' &nbsp; <button id="names">Names off</button><button id="clear">Clear</button>';

// The constellation: thick lines along the group's shortest tree and halos around its points, added on a click
const lineMaterial = new LineMaterial({color: 0x000000, linewidth: 3.5, transparent: true, opacity: 0.9});
lineMaterial.resolution.set(...size());
const halo = new THREE.SphereGeometry(0.06, 24, 16);
let mode = D.modes[0][0], selected = null, showNames = true, drawn = [];
function draw() {
  for (const object of drawn) { scene.remove(object); if (object.geometry !== halo) object.geometry.dispose(); }
  drawn = [];
  if (selected === null) { info.textContent = ""; return; }
  const group = D.groups[mode][D.points[selected].groups[mode]];
  if (group.edges.length) {
    const points = [];
    for (const [a, b] of group.edges) points.push(...D.points[a].pos, ...D.points[b].pos);
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
    ring.position.set(...D.points[i].pos);
    scene.add(ring);
    drawn.push(ring);
  }
  info.innerHTML = "<b>" + esc(group.label) + " (" + group.members.length + ")</b><br>" +
    group.members.map(i => esc(D.points[i].name)).join(", ");
}

// Find the point whose ball is nearest a spot on screen, within a radius in pixels
const projected = new THREE.Vector3();
function nearest(x, y, radius) {
  const box = renderer.domElement.getBoundingClientRect();
  let best = null, bestDistance = radius;
  D.points.forEach((p, i) => {
    projected.set(...p.pos).project(camera);
    const sx = (projected.x + 1) / 2 * box.width + box.left, sy = (1 - projected.y) / 2 * box.height + box.top;
    const distance = Math.hypot(sx - x, sy - y);
    if (distance < bestDistance) { best = i; bestDistance = distance; }
  });
  return best;
}

// A press and release without dragging selects the nearest point; a second click on it clears the constellation
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
// Hovering near a point shows its tip lines
renderer.domElement.addEventListener("pointermove", event => {
  if (pressed) { tip.style.display = "none"; return; }
  const hit = nearest(event.clientX, event.clientY, 12);
  renderer.domElement.style.cursor = hit === null ? "grab" : "pointer";
  if (hit === null) { tip.style.display = "none"; return; }
  const p = D.points[hit];
  tip.innerHTML = "<b>" + esc(p.name) + "</b><br>" + p.tip.map(esc).join("<br>");
  tip.style.left = (event.clientX + 14) + "px";
  tip.style.top = (event.clientY + 14) + "px";
  tip.style.display = "block";
});
renderer.domElement.addEventListener("pointerleave", () => { tip.style.display = "none"; });

// The mode buttons pick the grouping, the names button shows or hides the names, and clear removes the constellation
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


def write_sphere_page(path, title, axes, points, groups, modes, legend_title, legend):
    """Write an interactive sphere as one HTML page drawn with three.js.

    axes: three (high-end name, low-end name) pairs for x (left to right), y (front to back) and z (up).
    points: dicts with name, pos (inside the unit sphere), color, groups (mode -> group key) and tip (hover lines).
    groups: mode -> the sphere_groups of that mode. modes: (mode, button label) pairs, the first shown on opening.
    legend: (label, colour) pairs of the point colours, under legend_title.

    The page shows the points as shaded balls with their names, the faint sphere, the three cuts through the centre
    and the axes with their end names, and no subtitle or notes. Clicking a point (press and release without
    dragging, within a few pixels of its ball) adds its constellation, the shortest tree joining it to the other
    points of its group in the chosen mode; hovering shows its tip lines.
    """
    direction = np.array(SPHERE_CAMERA_DIRECTION, dtype=float)
    data = {
        "colors": {"surface": SURFACE, "text": TEXT_PRIMARY, "axis": TEXT_SECONDARY, "cut": CUT, "wire": GRID},
        "camera": [round(float(v), 4) for v in direction / np.linalg.norm(direction) * SPHERE_CAMERA_DISTANCE],
        "axes": [{"dir": [float(v) for v in np.eye(3)[n]], "high": high, "low": low}
                 for n, (high, low) in enumerate(axes)],
        "points": [{"name": p["name"], "pos": [round(float(v), 4) for v in p["pos"]], "color": p["color"],
                    "groups": p["groups"], "tip": p["tip"]} for p in points],
        "groups": groups,
        "modes": [list(m) for m in modes],
        "legend": {"title": legend_title, "items": [{"label": label, "color": color} for label, color in legend]},
    }
    # The data goes in a JSON script block; '</' is escaped so no value can close the block early
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    imports = json.dumps({"imports": {"three": f"{THREE_URL}/build/three.module.js",
                                      "three/addons/": f"{THREE_URL}/examples/jsm/"}})
    escaped_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    head = SPHERE_HEAD
    for token, value in (("SURFACE", SURFACE), ("TEXT", TEXT_PRIMARY), ("AXIS", TEXT_SECONDARY), ("GRIDCOLOR", GRID),
                         ("IMPORTS", imports), ("PAGETITLE", escaped_title)):
        head = head.replace(token, value)
    page = (head + '<script id="data" type="application/json">' + payload + "</script>\n" + SPHERE_SCRIPT
            + "</body>\n</html>\n")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(page)
