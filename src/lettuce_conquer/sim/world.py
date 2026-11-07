"""The game world and its fixed-step update.

Each tick: stumps regrow, every team's planner tree runs, then every unit's tree (in id order), then
sprouting buildings draw water and finish units, then units move. A unit only walks while one of its
tree's move actions is running. Units never share a tile: a unit reserves the next tile before
stepping into it, and waits (then re-plans) if it's taken.
"""
from __future__ import annotations

import hashlib
import json
from collections import deque
from dataclasses import asdict, dataclass, field
from math import isqrt

from lettuce_conquer.buildings import BUILDINGS
from lettuce_conquer.sim import bt, data, mapgen, pathfind
from lettuce_conquer.sim import trees as tree_lib
from lettuce_conquer.sim.rng import Rng, seed_state

T = data.TILE
ORTHOGONAL = pathfind.STEPS[:4]


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
    state: str = "grown"     # planted -> sprout -> grown; "sprouting" while a unit grows inside
    progress: int = 0        # tending done, in points (data.PACE per Spud-tick, more on fertile ground)
    work: int = 0            # points of tending needed to be grown
    fertile: int = 0         # percent faster growing and sprouting, from field tiles under it
    can: int = 0             # the Watering Can its channel was planned from (0: none yet)
    sprout_kind: str = ""    # unit being sprouted
    sprout_left: int = 0     # points of sprouting left (data.PACE a tick, more on fertile ground)
    water_owed: int = 0      # water still to draw for it


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
    amount: int = 0       # resource left (water, for a Watering Can)
    max_amount: int = 0
    regrow_at: int = -1   # tick a stump grows back (trees only)


@dataclass
class Channel:
    """One tile of irrigation ditch. Planned first, then dug by Spuds; water flows once dug."""
    x: int
    y: int
    team: int       # who planned it (and digs it)
    order: int      # digging order (planned routes are dug from the can outward)
    dug: bool = False
    progress: int = 0
    paid: bool = False


@dataclass
class Team:
    id: int
    color: str
    quadrant: int
    spawn: tuple
    tree: str                                       # the planner's behavior tree
    rng_state: int = 0                              # the team's own random stream (identical for every team)
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
        self.fields = layout.fields  # tilled plots as (x, y, w, h); their tiles are also marked in `tiles`
        self.tree_names = dict(data.DEFAULT_TREES, **(trees or {}))
        self.trees = {name: tree_lib.load(name) for name in sorted(set(self.tree_names.values()))}
        self._next_id = 1
        self.things: list[Thing] = []
        for f in layout.features:
            amount = data.CAN_CAPACITY if f.kind == "watering_can" else data.YIELDS.get(f.kind, ("", 0))[1]
            self.things.append(Thing(self._new_id(), f.kind, f.x, f.y, f.w, f.h, amount=amount, max_amount=amount))
        self.channels: dict[tuple[int, int], Channel] = {}
        self._channel_order = 0
        self.teams: list[Team] = []
        self.buildings: list[Building] = []
        self.units: list[Unit] = []
        for i, q in enumerate(mapgen.TEAM_QUADRANTS[teams]):
            base = layout.bases[q]
            team = Team(i, data.TEAM_COLORS[i], q, tuple(base["spawn"]), self.tree_names["planner"],
                        rng_state=seed_state(seed ^ 0x7EA4))
            self.teams.append(team)
            work = data.BUILD_WORK["greenhouse"] * data.PACE
            self.buildings.append(Building(self._new_id(), i, "greenhouse", *base["greenhouse"], work=work, progress=work))
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

    # ------------------------------------------------------------ fairness: mirrored tie-breaks
    # Every army starts in a mirrored copy of the same quarter. Whenever a choice is a tie, it is broken
    # in the team's own mirrored view of the map, so mirrored teams always make mirrored choices.
    @staticmethod
    def flips(team: Team) -> tuple[int, int]:
        """(-1 or 1, -1 or 1): whether the team's quarter is mirrored left-right and top-bottom."""
        return (-1 if team.quadrant in (1, 3) else 1), (-1 if team.quadrant in (2, 3) else 1)

    def flips_at(self, o) -> tuple[int, int]:
        """The same, for whichever quarter of the map an object sits in."""
        return (1 if 2 * o.x + o.w <= self.width else -1), (1 if 2 * o.y + o.h <= self.height else -1)

    def local(self, team: Team, x: int, y: int) -> tuple[int, int]:
        """A tile as the team sees it: mapped back into the top-left quarter's orientation."""
        sx, sy = self.flips(team)
        return (x if sx > 0 else self.width - 1 - x), (y if sy > 0 else self.height - 1 - y)

    def local_corner(self, team: Team, o) -> tuple[int, int]:
        """An object's footprint corner as the team sees it (the mirror of its top-left)."""
        sx, sy = self.flips(team)
        return (o.x if sx > 0 else self.width - o.x - o.w), (o.y if sy > 0 else self.height - o.y - o.h)

    def roll(self, team: Team, lo: int, hi: int) -> int:
        """A random int in [lo, hi] from the team's own stream: mirrored teams roll the same numbers."""
        rng = Rng(team.rng_state)
        value = rng.randint(lo, hi)
        team.rng_state = rng.state
        return value

    def steps_for(self, team: Team, steps=pathfind.STEPS) -> tuple:
        sx, sy = self.flips(team)
        return tuple((dx * sx, dy * sy) for dx, dy in steps)

    def nearest_walkable(self, x: int, y: int, team: Team | None = None, ignore: Unit | None = None,
                         need_free: bool = False) -> tuple[int, int]:
        """The closest walkable (or, with need_free, unoccupied) tile to (x, y), searching outward in a
        fixed order (mirrored for `team`)."""
        x, y = min(max(x, 0), self.width - 1), min(max(y, 0), self.height - 1)
        sx, sy = self.flips(team) if team is not None else (1, 1)
        seen, queue = {(x, y)}, deque([(x, y)])
        while queue:
            here = queue.popleft()
            if self.free(*here, ignore) if need_free else self.walkable(*here):
                return here
            hx, hy = here
            for nxt in ((hx + sx, hy), (hx - sx, hy), (hx, hy + sy), (hx, hy - sy)):
                if 0 <= nxt[0] < self.width and 0 <= nxt[1] < self.height and nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        raise RuntimeError("no walkable tile on the map")

    def team_of(self, unit: Unit) -> Team:
        return self.teams[unit.team]

    # ------------------------------------------------------------ economy
    def take(self, thing: Thing, n: int) -> int:
        """Remove up to n resource from a map feature; returns how much was taken."""
        if thing.kind in data.ENDLESS:
            return n
        n = min(n, thing.amount)
        thing.amount -= n
        if thing.kind in data.TREES:
            thing.state = "full" if thing.amount == thing.max_amount else ("half" if thing.amount else "stump")
            if thing.amount == 0:
                thing.regrow_at = self.tick + data.TREE_REGROW_TICKS
        elif thing.amount == 0 and thing.kind != "watering_can":  # compost heaps and rocks are used up for good
            self.things.remove(thing)
            self.blocked -= {(thing.x + i, thing.y + j) for i in range(thing.w) for j in range(thing.h)}
        else:
            self._set_level(thing)
        return n

    def pour(self, can: Thing, n: int) -> int:
        """Pour up to n water into a Watering Can; returns how much fit."""
        n = min(n, can.max_amount - can.amount)
        can.amount += n
        self._set_level(can)
        return n

    @staticmethod
    def _set_level(thing: Thing) -> None:
        third = thing.amount * 3
        thing.state = "full" if third > thing.max_amount * 2 else ("half" if third > thing.max_amount else "low")

    def deposit(self, team: Team, kind: str, amount: int) -> int:
        """Add a delivery to the team's stock, boosted 10% (compounding) per grown Root Cellar."""
        cellars = sum(1 for b in self.buildings if b.team == team.id and b.kind == "root_cellar" and b.state == "grown")
        for _ in range(cellars):
            amount = amount * data.ROOT_CELLAR_BONUS // 100
        team.stock[kind] += amount
        return amount

    # ------------------------------------------------------------ building
    def find_site(self, team: Team, kind: str, anchor: tuple[int, int]) -> tuple[int, int] | None:
        """The first good top-left tile for a new `kind` near `anchor`, searching outward in the team's
        mirrored order (so mirrored teams build in mirrored spots)."""
        size = BUILDINGS[kind].footprint
        sx, sy = self.flips(team)
        ax, ay = self.local(team, *anchor)
        for r in range(1, data.BUILD_SITE_RANGE + 1):
            ring = [(dx, -r) for dx in range(-r, r + 1)] + [(r, dy) for dy in range(-r + 1, r + 1)]
            ring += [(dx, r) for dx in range(r - 1, -r - 1, -1)] + [(-r, dy) for dy in range(r - 1, -r, -1)]
            for dx, dy in ring:
                lx, ly = ax + dx, ay + dy
                x = lx if sx > 0 else self.width - lx - size
                y = ly if sy > 0 else self.height - ly - size
                if self._site_ok(team, kind, x, y, size):
                    return x, y
        return None

    def _site_ok(self, team: Team, kind: str, x: int, y: int, size: int) -> bool:
        reserved = set(self.channels) | {self.inlet_tile(b) for b in self.buildings if b.kind in data.SPROUTS}
        tiles = [(x + i, y + j) for i in range(size) for j in range(size)]
        for tx, ty in tiles:
            if not self.walkable(tx, ty) or self.tiles[ty][tx] not in (mapgen.GRASS, mapgen.FIELD) or (tx, ty) in reserved \
                    or self.occupant((tx, ty)) is not None:
                return False
        probe = Building(0, team.id, kind, x, y, size, size)
        if any(not self.walkable(*t) for t in self.ring(probe)):  # keep a walkway all round
            return False
        inlet = self.inlet_tile(probe)
        return inlet is None or (self.walkable(*inlet) and inlet not in reserved)

    def fertility(self, x: int, y: int, w: int, h: int) -> int:
        """How much faster (percent) a building with this footprint would grow and sprout: the full
        FERTILE_BONUS on all-field ground, scaled down by the share of its tiles that are field."""
        fields = sum(1 for i in range(w) for j in range(h) if self.tiles[y + j][x + i] == mapgen.FIELD)
        return data.FERTILE_BONUS * fields // (w * h)

    def place_building(self, team: Team, kind: str, x: int, y: int) -> Building:
        size = BUILDINGS[kind].footprint
        b = Building(self._new_id(), team.id, kind, x, y, size, size, state="planted",
                     work=data.BUILD_WORK[kind] * data.PACE, fertile=self.fertility(x, y, size, size))
        self.buildings.append(b)
        self.blocked |= {(x + i, y + j) for i in range(size) for j in range(size)}
        return b

    @staticmethod
    def tend(b: Building) -> None:
        """One Spud-tick of tending (faster on fertile ground): Planted -> Sprout at half way -> Grown."""
        b.progress = min(b.work, b.progress + data.PACE * (100 + b.fertile) // 100)
        b.state = "grown" if b.progress >= b.work else ("sprout" if b.progress * 2 >= b.work else "planted")

    # ------------------------------------------------------------ irrigation
    def inlet_tile(self, b: Building) -> tuple[int, int] | None:
        """Where a channel must end to water `b`: in front of its corner facing the middle of the map."""
        if b.kind not in data.SPROUTS:
            return None
        sx, sy = self.flips(self.teams[b.team])
        return (b.x if sx > 0 else b.x + b.w - 1), (b.y + b.h if sy > 0 else b.y - 1)

    def outlet_tile(self, can: Thing) -> tuple[int, int]:
        """Where a Watering Can pours: in front of its spout, on the side facing the middle of the map."""
        sx, sy = self.flips_at(can)
        return (can.x + can.w - 1 if sx > 0 else can.x), (can.y + can.h if sy > 0 else can.y - 1)

    def plan_channel(self, team: Team, b: Building) -> bool:
        """Plan an unbroken channel from the nearest Watering Can to b's inlet (dug later by Spuds)."""
        inlet = self.inlet_tile(b)
        if inlet is None or not self.walkable(*inlet):
            return False
        cans = [t for t in self.things if t.kind == "watering_can" and self.walkable(*self.outlet_tile(t))]
        cans.sort(key=lambda c: (pathfind._octile(self.outlet_tile(c), inlet), self.local_corner(team, c)))
        reserved = {self.inlet_tile(o) for o in self.buildings if o.kind in data.SPROUTS and o is not b}
        ok = lambda x, y: self.walkable(x, y) and (x, y) not in reserved
        for can in cans:
            route = pathfind.find_path(self.outlet_tile(can), inlet, ok, self.steps_for(team, ORTHOGONAL))
            if route is not None:
                for tile in route:
                    if tile not in self.channels:
                        self.channels[tile] = Channel(tile[0], tile[1], team.id, self._channel_order)
                        self._channel_order += 1
                b.can = can.id
                return True
        return False

    def dig(self, channel: Channel) -> None:
        channel.progress += 1
        if channel.progress >= data.CHANNEL_WORK:
            channel.dug = True

    def _reach(self, start: tuple[int, int], team: Team | None = None) -> dict:
        """Dug channel tiles connected to `start`, with their distance along the channel."""
        if start not in self.channels or not self.channels[start].dug:
            return {}
        sx, sy = self.flips(team) if team is not None else (1, 1)
        dist, queue = {start: 0}, deque([start])
        while queue:
            x, y = queue.popleft()
            for nxt in ((x + sx, y), (x - sx, y), (x, y + sy), (x, y - sy)):
                ch = self.channels.get(nxt)
                if ch is not None and ch.dug and nxt not in dist:
                    dist[nxt] = dist[(x, y)] + 1
                    queue.append(nxt)
        return dist

    def connected_can(self, b: Building) -> Thing | None:
        """The Watering Can whose water reaches b's inlet through dug channels (nearest along the channel)."""
        inlet = self.inlet_tile(b)
        if inlet is None:
            return None
        team = self.teams[b.team]
        reach = self._reach(inlet, team)
        cans = [(reach[self.outlet_tile(c)], self.local_corner(team, c), c.id, c) for c in self.things
                if c.kind == "watering_can" and self.outlet_tile(c) in reach]
        return min(cans)[3] if cans else None

    def wet_channels(self) -> set:
        """Dug channel tiles connected to a Watering Can that still holds water (for drawing)."""
        wet = set()
        for c in self.things:
            if c.kind == "watering_can" and c.amount > 0:
                wet |= set(self._reach(self.outlet_tile(c)))
        return wet

    # ------------------------------------------------------------ sprouting
    def start_sprout(self, team: Team, b: Building, kind: str) -> bool:
        cost = data.UNIT_COST[kind]
        if (b.state != "grown" or b.sprout_kind or data.SPROUTS.get(b.kind) != kind
                or team.stock["compost"] < cost["compost"] or self.connected_can(b) is None):
            return False
        team.stock["compost"] -= cost["compost"]
        b.sprout_kind, b.sprout_left, b.water_owed, b.state = kind, data.SPROUT_TICKS[kind] * data.PACE, cost["water"], "sprouting"
        return True

    def _grow_sprouts(self) -> None:
        for b in self.buildings:
            if not b.sprout_kind:
                continue
            pace = data.PACE * (100 + b.fertile) // 100
            ticks_left = -(-b.sprout_left // pace)
            draw = -(-b.water_owed // ticks_left)  # spread the water evenly over the sprouting time
            can = self.connected_can(b)
            if draw and (can is None or can.amount < draw):
                continue  # no water: sprouting pauses
            if draw:
                can.amount -= draw
                self._set_level(can)
                b.water_owed -= draw
            b.sprout_left = max(0, b.sprout_left - pace)
            if b.sprout_left == 0:
                team = self.teams[b.team]
                tile = self.nearest_walkable(*self.inlet_tile(b), team, need_free=True)
                self._spawn(team, b.sprout_kind, *tile)
                b.sprout_kind, b.state = "", "grown"

    def _update_water_stock(self) -> None:
        """A team's Water is what its connected Watering Cans hold."""
        for team in self.teams:
            cans = {}
            for b in self.buildings:
                if b.team == team.id:
                    can = self.connected_can(b)
                    if can is not None:
                        cans[can.id] = can.amount
            team.stock["water"] = sum(cans.values())

    # ------------------------------------------------------------ update
    def step(self) -> None:
        for thing in self.things:
            if thing.regrow_at >= 0 and self.tick >= thing.regrow_at:
                thing.amount, thing.state, thing.regrow_at = thing.max_amount, "full", -1
        for team in self.teams:
            bt.run(self.trees[team.tree], bt.Context(self, team, team, "team"))
        for unit in list(self.units):
            unit.prev_x, unit.prev_y = unit.x, unit.y
            unit.move_requested = False
            bt.run(self.trees[unit.tree], bt.Context(self, unit, self.team_of(unit), "unit"))
            if not unit.move_requested:
                unit.path.clear()
        self._grow_sprouts()
        for unit in self.units:
            self._move(unit)
        self._update_water_stock()
        self.tick += 1

    def _move(self, unit: Unit) -> None:
        if not unit.path:
            unit.reserved = None
            return
        nxt = tuple(unit.path[0])
        if nxt != self.tile_of(unit) and not self.walkable(*nxt):  # something was planted in the way: re-plan
            unit.path.clear()
            unit.reserved = None
            return
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
        else:  # round toward zero, so a step is the same size in every direction (mirror fairness)
            unit.x += (1 if dx >= 0 else -1) * (abs(dx) * speed // dist)
            unit.y += (1 if dy >= 0 else -1) * (abs(dy) * speed // dist)

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
            "channels": [plain(c) for c in sorted(self.channels.values(), key=lambda c: c.order)],
            "units": [plain(u, ("trace", "move_requested")) for u in self.units],
        }

    def state_hash(self) -> str:
        text = json.dumps(self.snapshot(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
