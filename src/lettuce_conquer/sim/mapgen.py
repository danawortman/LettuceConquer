"""Seeded farm maps for 2 to 4 armies.

One quadrant is generated from the seed and mirrored into the other three, so every army starts on
identical ground. Quadrant 0 is the top-left; 1 is mirrored left-right, 2 top-bottom, 3 both.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from lettuce_conquer.sim.data import QUADRANT
from lettuce_conquer.sim.rng import Rng, seed_state

GRASS, FIELD = "g", "f"

# Every base has the same layout, in top-left-quadrant tiles: (x, y, w, h).
GREENHOUSE = (2, 2, 3, 3)
BASE_FEATURES = (("compost_heap", 7, 2, 2, 2), ("watering_can", 2, 7, 2, 2))
SPAWN = (5, 5)
DEMO_SPAWNS = ((6, 5), (5, 6), (6, 6), (7, 5), (5, 7))
BASE_ZONE = 10  # random features stay out of the corner square this many tiles wide

# Which quadrants the armies start in, by army count (opposite corners for two).
TEAM_QUADRANTS = {2: (0, 3), 3: (0, 1, 2), 4: (0, 1, 2, 3)}

TREE_KINDS = ("apple_tree", "pine_tree")
ROCK_KINDS = ("rocks_a", "rocks_b")
NEIGHBORS = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))


@dataclass(frozen=True)
class Feature:
    kind: str
    x: int
    y: int
    w: int = 1
    h: int = 1


@dataclass
class MapLayout:
    width: int
    height: int
    tiles: list[list[str]]       # tiles[y][x]
    features: list[Feature]      # everything that blocks movement, except buildings
    bases: list[dict]            # per quadrant: greenhouse (x, y, w, h), spawn, demo_spawns
    fields: list[tuple]          # each tilled field as (x, y, w, h), for drawing it as one plot


def generate(seed: int, size: int = QUADRANT) -> MapLayout:
    """A mirrored map for `seed`. Re-rolls (deterministically) until every base can reach the others."""
    rng = Rng(seed_state(seed))
    for _ in range(50):
        layout = _mirror(*_quadrant(rng, size), size)
        if _connected(layout):
            return layout
    raise RuntimeError(f"no connected map found for seed {seed}")


def _quadrant(rng: Rng, size: int):
    tiles = [[GRASS] * size for _ in range(size)]
    taken: set[tuple[int, int]] = set()
    features: list[Feature] = []

    def footprint(x, y, w, h):
        return {(x + i, y + j) for i in range(w) for j in range(h)}

    def fits(x, y, w, h):
        return 0 <= x and 0 <= y and x + w <= size and y + h <= size and not (footprint(x, y, w, h) & taken)

    def in_base(x, y):
        return x < BASE_ZONE and y < BASE_ZONE

    def place(kind, x, y, w=1, h=1):
        if not fits(x, y, w, h):
            return False
        taken.update(footprint(x, y, w, h))
        features.append(Feature(kind, x, y, w, h))
        return True

    # The fixed base: Greenhouse spot, its resources, and the start tiles (kept clear).
    taken.update(footprint(*GREENHOUSE))
    for kind, x, y, w, h in BASE_FEATURES:
        place(kind, x, y, w, h)
    taken.update([SPAWN, *DEMO_SPAWNS])

    # Fields are walkable ground, but nothing grows on top of them.
    fields = []
    for _ in range(2):
        w, h = rng.randint(2, 4), rng.randint(2, 3)
        x, y = rng.randint(0, size - w), rng.randint(0, size - h)
        if fits(x, y, w, h) and not any(in_base(i, j) for i, j in footprint(x, y, w, h)):
            taken.update(footprint(x, y, w, h))
            fields.append((x, y, w, h))
            for i, j in footprint(x, y, w, h):
                tiles[j][i] = FIELD
    for _ in range(30):  # one lake, away from the base
        if place("lake", rng.randint(BASE_ZONE, size - 4), rng.randint(BASE_ZONE, size - 3), 3, 2):
            break
    for _ in range(30):  # a second compost heap out in the open
        x, y = rng.randint(0, size - 2), rng.randint(0, size - 2)
        if not in_base(x, y) and place("compost_heap", x, y, 2, 2):
            break
    def grow(pick_kind, count):
        """An organic clump: start on a free tile, then keep adding beside a random member."""
        for _ in range(30):
            cx, cy = rng.randint(0, size - 1), rng.randint(0, size - 1)
            if not in_base(cx, cy) and place(pick_kind(), cx, cy):
                break
        else:
            return
        group, want = [(cx, cy)], rng.randint(*count)
        for _ in range(want * 8):
            if len(group) >= want:
                break
            gx, gy = rng.choice(group)
            dx, dy = rng.choice(NEIGHBORS)
            if not in_base(gx + dx, gy + dy) and place(pick_kind(), gx + dx, gy + dy):
                group.append((gx + dx, gy + dy))

    for _ in range(3):  # groves: mostly one kind of tree, a few of the other
        main, other = (TREE_KINDS if rng.randint(0, 1) else TREE_KINDS[::-1])
        grow(lambda: other if rng.randint(1, 100) <= 20 else main, (6, 12))
    for _ in range(3):  # rock clusters
        grow(lambda: rng.choice(ROCK_KINDS), (3, 6))
    return tiles, features, fields


def _mirror(tiles, features, fields, size) -> MapLayout:
    width = height = size * 2
    full = [[GRASS] * width for _ in range(height)]
    all_features: list[Feature] = []
    all_fields = []
    bases = []
    for q in range(4):
        fx, fy = q in (1, 3), q in (2, 3)
        mx = (lambda x, w=1: width - x - w) if fx else (lambda x, w=1: x)
        my = (lambda y, h=1: height - y - h) if fy else (lambda y, h=1: y)
        for y in range(size):
            for x in range(size):
                full[my(y)][mx(x)] = tiles[y][x]
        all_features += [Feature(f.kind, mx(f.x, f.w), my(f.y, f.h), f.w, f.h) for f in features]
        all_fields += [(mx(x, w), my(y, h), w, h) for x, y, w, h in fields]
        gx, gy, gw, gh = GREENHOUSE
        bases.append({"quadrant": q, "greenhouse": (mx(gx, gw), my(gy, gh), gw, gh),
                      "spawn": (mx(SPAWN[0]), my(SPAWN[1])),
                      "demo_spawns": [(mx(x), my(y)) for x, y in DEMO_SPAWNS]})
    return MapLayout(width, height, full, all_features, bases, all_fields)


def _connected(layout: MapLayout) -> bool:
    """Every base's spawn can walk to every other (greenhouses count as blocked)."""
    blocked = {(f.x + i, f.y + j) for f in layout.features for i in range(f.w) for j in range(f.h)}
    for base in layout.bases:
        gx, gy, gw, gh = base["greenhouse"]
        blocked |= {(gx + i, gy + j) for i in range(gw) for j in range(gh)}
    start = layout.bases[0]["spawn"]
    seen, queue = {start}, deque([start])
    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < layout.width and 0 <= ny < layout.height and (nx, ny) not in blocked and (nx, ny) not in seen:
                seen.add((nx, ny))
                queue.append((nx, ny))
    return all(tuple(b["spawn"]) in seen for b in layout.bases)
