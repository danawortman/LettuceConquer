"""The terrain catalog. Data only: no movement costs or resource amounts yet."""
from __future__ import annotations

from dataclasses import dataclass

# Ground tiles are full 120 x 120 squares (viewBox 0 0 120 120); fields of any size are just these
# tiles side by side, with hard edges.
GROUND_TILES = ("grass", "field")

# Path and irrigation-channel pieces are see-through overlays drawn on top of a ground tile, in the
# same 120 x 120 frame. Each piece is drawn once, connecting the sides listed here; rotate it in
# 90-degree clockwise steps (N -> E -> S -> W) to get the other orientations. Pieces meet exactly at
# the tile edge, so neighbouring pieces join without seams.
PIECE_SIDES = {"end": "S", "straight": "EW", "corner": "NE", "t": "EWS", "cross": "NESW"}
CHANNEL_STATES = ("dry", "wet")  # dug but empty / connected to a Watering Can
SIDES = "NESW"


def piece_for(sides: str) -> tuple[str, int]:
    """The piece and number of clockwise quarter turns that connect exactly `sides` (any of N, E, S, W).
    A tile with no connections is drawn as an end piece."""
    want = {s for s in sides if s in SIDES} or {"S"}
    for piece, base in PIECE_SIDES.items():
        for turns in range(4):
            if {SIDES[(SIDES.index(c) + turns) % 4] for c in base} == want:
                return piece, turns
    raise ValueError(sides)

# A lake is one drawing covering 3 x 2 tiles (viewBox 0 0 360 240), placed by its top-left tile corner.
LAKE_FOOTPRINT = (3, 2)

# Standing objects share one frame (viewBox x, y, width, height) with the object's ground point at (0, 0).
OBJECT_FRAME = (-130, -250, 260, 280)

# Grass decorations (assets/terrain/decal_<name>.svg), scattered over the ground at random positions
# so the grass doesn't look like a grid. Centered on (0, 0) in this frame.
DECALS = ("tuft_a", "tuft_b", "clover", "daisies", "buttercups", "pebbles", "light_patch", "dark_patch")
DECAL_FRAME = (-70, -50, 140, 100)


@dataclass(frozen=True)
class TerrainObject:
    key: str               # art file prefix: assets/terrain/<key>_<state>.svg
    name: str
    resource: str | None   # what Spuds collect from it
    states: tuple[str, ...]


OBJECTS: tuple[TerrainObject, ...] = (
    TerrainObject("apple_tree", "Apple Tree", "lumber", ("full", "half", "stump")),
    TerrainObject("pine_tree", "Pine Tree", "lumber", ("full", "half", "stump")),
    TerrainObject("rocks_a", "Rocks", "stone", ("full", "half", "low")),
    TerrainObject("rocks_b", "Rocks", "stone", ("full", "half", "low")),
    TerrainObject("remains_spud", "Fallen Spud", "compost", ("full",)),
    TerrainObject("remains_cabbage", "Fallen Sir Cabbage", "compost", ("full",)),
    TerrainObject("remains_pea", "Fallen Pea Shooter", "compost", ("full",)),
    TerrainObject("remains_carrot", "Fallen Carrot Lancer", "compost", ("full",)),
)


def overlay_files() -> list[str]:
    """Every path and channel overlay, as file stems."""
    stems = [f"path_{p}" for p in PIECE_SIDES]
    stems += [f"channel_{p}_{s}" for p in PIECE_SIDES for s in CHANNEL_STATES]
    return stems
