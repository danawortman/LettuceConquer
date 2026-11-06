"""Freshly tilled field plots, generated as SVG to fit each field's size.

A plot has soft, slightly wavy edges (no dark outline), raised soil ridges between dark furrows, and
crumbly clods spilling onto the grass. The same (width, height, seed) always draws the same plot.
nanosvg-safe: inline attributes only, no clip paths or arcs.
"""
from __future__ import annotations

import random

TILE = 120
PAD = 24  # room around the plot for clods that spill onto the grass
SOIL, SOIL_EDGE = "#9c7148", "#7d5a37"
RIDGE, FURROW = "#b88a5a", "#76542f"
CLODS = ("#8c653c", "#a47a4c", "#7d5a37")


def frame(w_tiles: int, h_tiles: int) -> tuple[int, int, int, int]:
    """The plot's viewBox; its (0, 0) is the field's top-left tile corner."""
    return -PAD, -PAD, w_tiles * TILE + 2 * PAD, h_tiles * TILE + 2 * PAD


def _outline(rnd, w, h, inset=10, step=28, wobble=10, corner=22):
    """Points around the plot's edge, nudged in and out; corners pulled in so they round off."""
    pts = []
    x0, y0, x1, y1 = inset, inset, w - inset, h - inset
    cx, cy = w / 2, h / 2
    edges = [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]
    for (ax, ay), (bx, by) in edges:
        n = max(2, round(max(abs(bx - ax), abs(by - ay)) / step))
        for i in range(n):
            t = i / n
            x, y = ax + (bx - ax) * t, ay + (by - ay) * t
            if i == 0:  # a corner: pull it toward the middle of the plot
                x += corner if x < cx else -corner
                y += corner if y < cy else -corner
            pts.append((x + rnd.uniform(-wobble, wobble), y + rnd.uniform(-wobble, wobble)))
    return pts


def _smooth_closed(pts) -> str:
    """A smooth closed path through the midpoints of the outline, using the points as curve handles."""
    mids = [((pts[i][0] + pts[(i + 1) % len(pts)][0]) / 2, (pts[i][1] + pts[(i + 1) % len(pts)][1]) / 2) for i in range(len(pts))]
    d = f"M{mids[-1][0]:.1f} {mids[-1][1]:.1f}"
    for (cx, cy), (mx, my) in zip(pts, mids):
        d += f" Q{cx:.1f} {cy:.1f} {mx:.1f} {my:.1f}"
    return d + " Z"


def field_svg(w_tiles: int, h_tiles: int, seed: int) -> str:
    rnd = random.Random(seed * 7919 + w_tiles * 31 + h_tiles)
    w, h = w_tiles * TILE, h_tiles * TILE
    pts = _outline(rnd, w, h)
    parts = [f'<path d="{_smooth_closed(pts)}" fill="{SOIL}" stroke="{SOIL_EDGE}" stroke-width="3" stroke-linejoin="round"/>']
    # Ridges and furrows, inset from the wavy edge so they never poke out (nanosvg has no clipping).
    for y in range(34, h - 24, 22):
        x_start, x_end = 30 + rnd.uniform(0, 8), w - 30 - rnd.uniform(0, 8)
        sag = rnd.uniform(-3, 3)
        ridge = f"M{x_start:.1f} {y - 6:.1f} Q{w / 2:.1f} {y - 6 + sag:.1f} {x_end:.1f} {y - 6:.1f}"
        furrow = f"M{x_start + 4:.1f} {y + 2:.1f} Q{w / 2:.1f} {y + 2 + sag:.1f} {x_end - 4:.1f} {y + 2:.1f}"
        parts.append(f'<path d="{ridge}" fill="none" stroke="{RIDGE}" stroke-width="7" stroke-linecap="round"/>')
        parts.append(f'<path d="{furrow}" fill="none" stroke="{FURROW}" stroke-width="4" stroke-linecap="round"/>')
    # Clods along the edge, some spilling onto the grass.
    for x, y in pts:
        for _ in range(rnd.randint(0, 2)):
            cx, cy = x + rnd.uniform(-14, 14), y + rnd.uniform(-14, 14)
            rx, ry = rnd.uniform(4, 8), rnd.uniform(3, 6)
            parts.append(f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="{rnd.choice(CLODS)}" '
                         f'stroke="{SOIL_EDGE}" stroke-width="1.5"/>')
    x, y, fw, fh = frame(w_tiles, h_tiles)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x} {y} {fw} {fh}" width="{fw}" height="{fh}">'
            + "".join(parts) + "</svg>")
