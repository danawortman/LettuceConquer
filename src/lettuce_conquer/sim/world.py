"""The game world and its fixed-step update.

Each tick: stumps regrow, every team's planner tree runs, then every unit's tree (in id order), then
units move. A unit only walks while one of its tree's move actions is running. Units never share a
tile: a unit reserves the next tile before stepping into it, and waits (then re-plans) if it's taken.
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
    carry_kind: str = ""                           # resource being carried
    carry: int = 0
    reserved: list | None = None                   # the tile it is stepping into
    wait_ticks: int = 0                            # ticks spent blocked by another unit
    stuck: bool = False                            # blocked long enough to re-plan around units
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
    amount: int = 0       # resource left
    max_amount: int = 0
    regrow_at: int = -1   # tick a stump grows back (trees only)


@dataclass
class Team:
    id: int
    color: str
    quadrant: int
    spawn: tuple
    tree: str                                       # the planner's behavior tree
    stock: dict = field(default_factory=lambda: {r: 0 for r in data.RESOURCES})
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
        self.things: list[Thing] = []
        for f in layout.features:
            amount = data.YIELDS.get(f.kind, ("", 0))[1]
            self.things.append(Thing(self._new_id(), f.kind, f.x, f.y, f.w, f.h, amount=amount, max_amount=amount))
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

    def occupant(self, tile: tuple[int, int], ignore: Unit | None = None) -> Unit | None:
        """The unit standing on (or stepping into) `tile`, other than `ignore`."""
        tile = tuple(tile)
        for u in self.units:
            if u is not ignore and (self.tile_of(u) == tile or (u.reserved is not None and tuple(u.reserved) == tile)):
                return u
        return None

    def free(self, x: int, y: int, ignore: Unit | None = None) -> bool:
        """Walkable and nobody else on it."""
        return self.walkable(x, y) and self.occupant((x, y), ignore) is None

    @staticmethod
    def center(x: int, y: int) -> tuple[int, int]:
        return x * T + T // 2, y * T + T // 2

    @staticmethod
    def tile_of(unit: Unit) -> tuple[int, int]:
        return unit.x // T, unit.y // T

    @staticmethod
    def at_center(unit: Unit) -> bool:
        return unit.x % T == T // 2 and unit.y % T == T // 2

    def entity(self, eid) -> Thing | Building | None:
        for o in self.things:
            if o.id == eid:
                return o
        for b in self.buildings:
            if b.id == eid:
                return b
        return None

    @staticmethod
    def ring(o) -> list[tuple[int, int]]:
        """The tiles touching an object's footprint (diagonals too), in a fixed order."""
        x0, y0, x1, y1 = o.x - 1, o.y - 1, o.x + o.w, o.y + o.h
        top = [(x, y0) for x in range(x0, x1 + 1)]
        right = [(x1, y) for y in range(y0 + 1, y1 + 1)]
        bottom = [(x, y1) for x in range(x1 - 1, x0 - 1, -1)]
        left = [(x0, y) for y in range(y1 - 1, y0, -1)]
        return top + right + bottom + left

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

    # ------------------------------------------------------------ economy
    def take(self, thing: Thing, n: int) -> int:
        """Remove up to n resource from a map feature; returns how much was taken."""
        n = min(n, thing.amount)
        thing.amount -= n
        if thing.kind in data.TREES:
            thing.state = "full" if thing.amount == thing.max_amount else ("half" if thing.amount else "stump")
            if thing.amount == 0:
                thing.regrow_at = self.tick + data.TREE_REGROW_TICKS
        elif thing.amount == 0:  # compost heaps and rocks are used up for good
            self.things.remove(thing)
            self.blocked -= {(thing.x + i, thing.y + j) for i in range(thing.w) for j in range(thing.h)}
        else:
            thing.state = "full" if thing.amount * 3 > thing.max_amount * 2 else ("half" if thing.amount * 3 > thing.max_amount else "low")
        return n

    def deposit(self, team: Team, kind: str, amount: int) -> int:
        """Add a delivery to the team's stock, boosted 10% (compounding) per grown Root Cellar."""
        cellars = sum(1 for b in self.buildings if b.team == team.id and b.kind == "root_cellar" and b.state == "grown")
        for _ in range(cellars):
            amount = amount * data.ROOT_CELLAR_BONUS // 100
        team.stock[kind] += amount
        return amount

    # ------------------------------------------------------------ update
    def step(self) -> None:
        for thing in self.things:
            if thing.regrow_at >= 0 and self.tick >= thing.regrow_at:
                thing.amount, thing.state, thing.regrow_at = thing.max_amount, "full", -1
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
            unit.reserved = None
            return
        nxt = tuple(unit.path[0])
        if nxt != self.tile_of(unit) and unit.reserved != list(nxt):
            if self.occupant(nxt, unit) is not None:  # someone's there: wait, and re-plan if it lasts
                unit.wait_ticks += 1
                unit.stuck = unit.wait_ticks >= data.STUCK_TICKS
                return
            unit.reserved = list(nxt)
        cx, cy = self.center(*nxt)
        dx, dy = cx - unit.x, cy - unit.y
        dist = isqrt(dx * dx + dy * dy)
        speed = data.UNIT_SPEED[unit.kind]
        if dist <= speed:
            unit.x, unit.y = cx, cy
            unit.path.pop(0)
            unit.reserved, unit.wait_ticks, unit.stuck = None, 0, False
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
