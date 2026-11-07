"""The building catalog. Data only for now: no costs, build times or behaviour yet."""
from __future__ import annotations

from dataclasses import dataclass

# Building and unit art share one scale: a grid tile is 120 art pixels, so a Spud is about one tile wide.
TILE = 120

# Every building SVG of the same footprint shares one frame (viewBox x, y, width, height); the
# building's ground point is (0, 0), so in frame pixels it sits at (-x, -y).
FRAMES = {1: (-130, -250, 260, 280), 2: (-170, -270, 340, 300), 3: (-250, -380, 500, 410)}

GROWTH_STATES = ("planted", "sprout", "grown", "wilted")
RESOURCE_LEVELS = ("full", "half", "low")

# The irrigation inlet is drawn separately from the building, on whichever side the inlet faces:
# a sluice gate once the building has grown, a water-drop sign before that. Anchor (0, 0) is the
# middle of the inlet tile's edge where it meets the building.
INLET_ART = ("inlet_gate", "inlet_sign")
INLET_FRAME = (-60, -90, 120, 110)


@dataclass(frozen=True)
class BuildingType:
    key: str            # art file prefix: assets/buildings/<key>_<state>.svg
    name: str
    footprint: int      # tiles per side
    owned: bool         # team-owned (team colours, flag) or a neutral resource
    sprouts: str | None = None  # unit key this building sprouts, if any

    @property
    def states(self) -> tuple[str, ...]:
        if not self.owned:
            return RESOURCE_LEVELS
        return GROWTH_STATES + (("sprouting",) if self.sprouts else ())

    @property
    def inlet_tile(self) -> tuple[int, int] | None:
        """Where an irrigation channel must end to water this building, for a base in the top-left
        quarter: a (column, row) tile offset from the footprint's top-left tile, directly in front of the
        left-hand column. Other quarters mirror it so the inlet always faces the middle of the map (see
        World.inlet_tile). Only buildings that sprout units use water."""
        return (0, self.footprint) if self.sprouts else None


CATALOG: tuple[BuildingType, ...] = (
    BuildingType("greenhouse", "Greenhouse", 3, True, "spud"),
    BuildingType("root_cellar", "Root Cellar", 2, True),
    BuildingType("cabbage_patch", "Cabbage Patch", 2, True, "cabbage"),
    BuildingType("pea_trellis", "Pea Trellis", 2, True, "pea"),
    BuildingType("carrot_bed", "Carrot Bed", 2, True, "carrot"),
    BuildingType("scarecrow", "Scarecrow Watchtower", 1, True),
    BuildingType("compost_heap", "Compost Heap", 2, False),
    BuildingType("watering_can", "Watering Can", 2, False),
)

BUILDINGS: dict[str, BuildingType] = {b.key: b for b in CATALOG}
