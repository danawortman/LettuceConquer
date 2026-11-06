"""The game world and its fixed-step update.

Each tick: every team's planner tree runs, then every unit's tree (in id order), then units move.
A unit only walks while one of its tree's move actions is running.
"""
from __future__ import annotations

import hashlib
import json
from collections import deque
from dataclasses import asdict, dataclass, field
from math import isqrt

from lettuce_conquer.sim import bt, data, mapgen
from lettuce_conquer.sim import trees as tree_lib
from lettuce_conquer.sim.rng import Rng, seed_state

T = data.TILE


@dataclass
class Unit:
    id: int
    team: int
    kind: str
    x: int                  # feet position, world units
    y: int
    prev_x: int             # position at the start of the tick (for smooth drawing)
    prev_y: int
    tree: str               # behavior tree name
    path: list = field(default_factory=list)       # tiles still to walk, as [x, y]
    bb: dict = field(default_factory=dict)         # blackboard
    bt_state: dict = field(default_factory=dict)   # the tree's running memory
    trace: dict = field(default_factory=dict)      # node statuses from the last tick (inspection only)
    move_requested: bool = False


@dataclass
class Building:
    id: int
    team: int
    kind: str
    x: int      # top-left tile
    y: int
    w: int
    h: int
    state: str = "grown"


@dataclass
class Thing:
    """Neutral map features: trees, rocks, lakes, compost heaps, watering cans."""
    id: int
    kind: str
    x: int
    y: int
    w: int = 1
    h: int = 1
    state: str = "full"


@dataclass
class Team:
    id: int
    color: str
    quadrant: int
    spawn: tuple
    tree: str                                       # the planner's behavior tree
    bb: dict = field(default_factory=dict)
    bt_state: dict = field(default_factory=dict)
    trace: dict = field(default_factory=dict)


class World:
    def __init__(self, seed: int = 1, teams: int = 2, demo_army: bool = True, trees: dict | None = None):
        if teams not in mapgen.TEAM_QUADRANTS:
            raise ValueError("2 to 4 teams")
        layout = mapgen.generate(seed)
        self.seed, self.tick = seed, 0
        self.rng = Rng(seed_state(seed ^ 0x5EED))  # its own stream, separate from map generation
        self.width, self.height, self.tiles = layout.width, layout.height, layout.tiles
        self.tree_names = dict(data.DEFAULT_TREES, **(trees or {}))
        self.trees = {name: tree_lib.load(name) for name in sorted(set(self.tree_names.values()))}
        self._next_id = 1
        self.things = [Thing(self._new_id(), f.kind, f.x, f.y, f.w, f.h) for f in layout.features]
        self.teams: list[Team] = []
        self.buildings: list[Building] = []
        self.units: list[Unit] = []
        for i, q in enumerate(mapgen.TEAM_QUADRANTS[teams]):
            base = layout.bases[q]
            team = Team(i, data.TEAM_COLORS[i], q, tuple(base["spawn"]), self.tree_names["planner"])
            self.teams.append(team)
            self.buildings.append(Building(self._new_id(), i, "greenhouse", *base["greenhouse"]))
            kinds = ("spud",) + (data.DEMO_ARMY if demo_army else ())
            for kind, tile in zip(kinds, [base["spawn"], *base["demo_spawns"]]):
                self._spawn(team, kind, *tile)
        self.blocked = {(o.x + i, o.y + j) for o in self.things + self.buildings for i in range(o.w) for j in range(o.h)}

    # ------------------------------------------------------------ queries
    def walkable(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height and (x, y) not in self.blocked

    @staticmethod
    def center(x: int, y: int) -> tuple[int, int]:
        return x * T + T // 2, y * T + T // 2

    @staticmethod
    def tile_of(unit: Unit) -> tuple[int, int]:
        return unit.x // T, unit.y // T

    def nearest_walkable(self, x: int, y: int) -> tuple[int, int]:
        """The closest walkable tile to (x, y), searching outward in a fixed order."""
        x, y = min(max(x, 0), self.width - 1), min(max(y, 0), self.height - 1)
        seen, queue = {(x, y)}, deque([(x, y)])
        while queue:
            here = queue.popleft()
            if self.walkable(*here):
                return here
            hx, hy = here
            for nxt in ((hx + 1, hy), (hx - 1, hy), (hx, hy + 1), (hx, hy - 1)):
                if 0 <= nxt[0] < self.width and 0 <= nxt[1] < self.height and nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        raise RuntimeError("no walkable tile on the map")

    def team_of(self, unit: Unit) -> Team:
        return self.teams[unit.team]

    # ------------------------------------------------------------ update
    def step(self) -> None:
        for team in self.teams:
            bt.run(self.trees[team.tree], bt.Context(self, team, team, "team"))
        for unit in self.units:
            unit.prev_x, unit.prev_y = unit.x, unit.y
            unit.move_requested = False
            bt.run(self.trees[unit.tree], bt.Context(self, unit, self.team_of(unit), "unit"))
            if not unit.move_requested:
                unit.path.clear()
        for unit in self.units:
            self._move(unit)
        self.tick += 1

    def _move(self, unit: Unit) -> None:
        if not unit.path:
            return
        cx, cy = self.center(*unit.path[0])
        dx, dy = cx - unit.x, cy - unit.y
        dist = isqrt(dx * dx + dy * dy)
        speed = data.UNIT_SPEED[unit.kind]
        if dist <= speed:
            unit.x, unit.y = cx, cy
            unit.path.pop(0)
        else:
            unit.x += dx * speed // dist
            unit.y += dy * speed // dist

    # ------------------------------------------------------------ setup helpers
    def _new_id(self) -> int:
        self._next_id += 1
        return self._next_id - 1

    def _spawn(self, team: Team, kind: str, tx: int, ty: int) -> Unit:
        x, y = self.center(tx, ty)
        unit = Unit(self._new_id(), team.id, kind, x, y, x, y, self.tree_names[kind], bb={"home": [tx, ty]})
        self.units.append(unit)
        return unit

    # ------------------------------------------------------------ saving and comparing
    def snapshot(self) -> dict:
        """Everything that defines the game state, as JSON-ready data (traces are display-only)."""
        def plain(obj, drop=()):
            return {k: v for k, v in asdict(obj).items() if k not in drop}
        return {
            "seed": self.seed, "tick": self.tick, "rng": self.rng.state,
            "tiles": ["".join(row) for row in self.tiles],
            "teams": [plain(t, ("trace",)) for t in self.teams],
            "buildings": [plain(b) for b in self.buildings],
            "things": [plain(t) for t in self.things],
            "units": [plain(u, ("trace", "move_requested")) for u in self.units],
        }

    def state_hash(self) -> str:
        text = json.dumps(self.snapshot(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
