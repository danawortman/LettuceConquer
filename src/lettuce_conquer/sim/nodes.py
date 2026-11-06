"""The node library: the conditions and actions behavior trees can use.

Tiles in blackboards are stored as [x, y] lists and map objects by their id, so blackboards stay
plain JSON.
"""
from __future__ import annotations

from lettuce_conquer.sim import data
from lettuce_conquer.sim.bt import FAILURE, RUNNING, SUCCESS, Arg, node
from lettuce_conquer.sim.pathfind import _octile, find_path


def _tile(value) -> tuple[int, int] | None:
    if isinstance(value, list) and len(value) == 2 and all(isinstance(v, int) for v in value):
        return value[0], value[1]
    return None


def _distance_to(tile, o) -> int:
    """Walking-distance estimate from a tile to the nearest tile of an object's footprint."""
    x, y = tile
    nx, ny = min(max(x, o.x), o.x + o.w - 1), min(max(y, o.y), o.y + o.h - 1)
    return _octile((x, y), (nx, ny))


def _walk_to(ctx, target: tuple[int, int]) -> str:
    """Shared by the move actions: keep walking to `target`; succeed on arrival at its centre."""
    unit, world = ctx.agent, ctx.world
    if not unit.path and (unit.x, unit.y) == world.center(*target):
        return SUCCESS
    if unit.stuck or not unit.path or ctx.state.get(ctx.path) != list(target):
        if unit.stuck:  # blocked by other units for a while: route around them, or give up
            unit.stuck = False
            if world.occupant(target, unit) is not None:
                return FAILURE
            route = find_path(world.tile_of(unit), target, lambda x, y: world.free(x, y, unit))
        else:
            route = find_path(world.tile_of(unit), target, world.walkable)
        if route is None:
            return FAILURE
        unit.path = [list(t) for t in route[1:]] or [list(target)]  # already on the tile: walk to its centre
        unit.wait_ticks = 0
        ctx.state[ctx.path] = list(target)
    unit.move_requested = True
    return RUNNING


def _beside(ctx, o) -> bool:
    """The unit is standing still on a tile touching the object."""
    unit, world = ctx.agent, ctx.world
    return not unit.path and world.at_center(unit) and world.tile_of(unit) in world.ring(o)


# ---------------------------------------------------------------- general (units and team planners)
@node("condition", "any", "True when the blackboard has `key`.", key=Arg("str"))
def has_key(ctx, key):
    return SUCCESS if key in ctx.bb else FAILURE


@node("action", "any", "Store the number `value` under `key`.", key=Arg("str"), value=Arg("int", 0))
def set_key(ctx, key, value):
    ctx.bb[key] = value
    return SUCCESS


@node("action", "any", "Remove `key` from the blackboard.", key=Arg("str"))
def clear_key(ctx, key):
    ctx.bb.pop(key, None)
    return SUCCESS


@node("action", "any", "Keep running for `ticks` ticks (10 ticks = 1 second), then succeed.", ticks=Arg("int", 10))
def wait(ctx, ticks):
    end = ctx.state.get(ctx.path)
    if end is None:
        if ticks <= 0:
            return SUCCESS
        ctx.state[ctx.path] = ctx.world.tick + ticks
        return RUNNING
    return SUCCESS if ctx.world.tick >= end else RUNNING


@node("action", "any", "Always succeed (a placeholder).")
def succeed(ctx):
    return SUCCESS


@node("action", "any", "Always fail (a placeholder).")
def fail(ctx):
    return FAILURE


# ---------------------------------------------------------------- units: moving
@node("condition", "unit", "True when the team planner's blackboard has `key`.", key=Arg("str"))
def team_has_key(ctx, key):
    return SUCCESS if key in ctx.team.bb else FAILURE


@node("condition", "unit", "True when the unit stands on the tile stored in `key`.", key=Arg("str", "goal"))
def at_tile(ctx, key):
    tile = _tile(ctx.bb.get(key))
    return SUCCESS if tile is not None and ctx.world.tile_of(ctx.agent) == tile else FAILURE


@node("action", "unit", "Pick a random free tile within `radius` tiles of home; store it in `key`.",
      key=Arg("str", "spot"), radius=Arg("int", 4))
def pick_wander_spot(ctx, key, radius):
    world = ctx.world
    hx, hy = _tile(ctx.bb.get("home")) or world.tile_of(ctx.agent)
    for _ in range(20):
        x, y = hx + world.rng.randint(-radius, radius), hy + world.rng.randint(-radius, radius)
        if world.free(x, y, ctx.agent):
            ctx.bb[key] = [x, y]
            return SUCCESS
    return FAILURE


@node("action", "unit", "Walk to the tile stored in `key`. Runs while walking, succeeds on arrival, "
      "fails if the tile can't be reached (or another unit is parked on it).", key=Arg("str", "goal"))
def move_to(ctx, key):
    target = _tile(ctx.bb.get(key))
    return FAILURE if target is None else _walk_to(ctx, target)


@node("action", "unit", "Walk to a free tile beside the object (resource or building) whose id is in `key`. "
      "Succeeds once standing beside it; fails if it's gone or can't be reached.", key=Arg("str", "target"))
def move_next_to(ctx, key):
    unit, world = ctx.agent, ctx.world
    o = world.entity(ctx.bb.get(key))
    if o is None:
        return FAILURE
    if _beside(ctx, o):
        return SUCCESS
    here = world.tile_of(unit)
    chosen = _tile(ctx.state.get(ctx.path))
    ring = world.ring(o)
    if chosen not in ring or not world.free(*chosen, unit):
        spots = [t for t in ring if world.free(*t, unit)]
        if not spots:
            return FAILURE
        chosen = min(spots, key=lambda t: _octile(here, t))  # ties keep the ring's fixed order
    return _walk_to(ctx, chosen)


@node("action", "unit", "Copy the team planner's tile `team_key` into `key`, shifted up to `spread` tiles "
      "per unit so a squad doesn't stack on one tile.",
      team_key=Arg("str", "rally"), key=Arg("str", "goal"), spread=Arg("int", 1))
def copy_team_key(ctx, team_key, key, spread):
    spot = _tile(ctx.team.bb.get(team_key))
    if spot is None:
        return FAILURE
    offsets = [(dx, dy) for r in range(spread + 1) for dy in range(-r, r + 1) for dx in range(-r, r + 1)
               if max(abs(dx), abs(dy)) == r]
    start = ctx.agent.id % len(offsets)
    for i in range(len(offsets)):
        dx, dy = offsets[(start + i) % len(offsets)]
        if ctx.world.free(spot[0] + dx, spot[1] + dy, ctx.agent):
            ctx.bb[key] = [spot[0] + dx, spot[1] + dy]
            return SUCCESS
    return FAILURE


# ---------------------------------------------------------------- units: gathering
@node("condition", "unit", "True when the unit carries a full load.")
def is_full(ctx):
    return SUCCESS if ctx.agent.carry >= data.CARRY_CAPACITY else FAILURE


@node("condition", "unit", "True when the unit carries anything.")
def is_carrying(ctx):
    return SUCCESS if ctx.agent.carry > 0 else FAILURE


@node("action", "unit", "Find the nearest map feature holding `resource` (compost, lumber or stone; or, if "
      "`resource` is empty, the resource named in blackboard `resource_key`) and store its id in `key`.",
      resource=Arg("str", ""), resource_key=Arg("str", "job"), key=Arg("str", "target"))
def find_nearest_resource(ctx, resource, resource_key, key):
    world = ctx.world
    wanted = resource or ctx.bb.get(resource_key)
    here = world.tile_of(ctx.agent)
    best = None
    for t in world.things:
        if data.YIELDS.get(t.kind, ("",))[0] == wanted and t.amount > 0:
            d = _distance_to(here, t)
            if best is None or d < best[0]:
                best = (d, t.id)
    if best is None:
        return FAILURE
    ctx.bb[key] = best[1]
    return SUCCESS


@node("action", "unit", "Gather from the map feature whose id is in `key` while standing beside it: one unit "
      "every half second until full. Fails if not beside it, or if already carrying a different resource.",
      key=Arg("str", "target"))
def harvest(ctx, key):
    unit, world = ctx.agent, ctx.world
    o = world.entity(ctx.bb.get(key))
    if o is None or o.amount == 0:  # used up (or a stump): fine if we got something
        return SUCCESS if unit.carry else FAILURE
    kind = data.YIELDS.get(o.kind, ("",))[0]
    if not kind or not _beside(ctx, o) or (unit.carry and unit.carry_kind != kind):
        return FAILURE
    if unit.carry >= data.CARRY_CAPACITY:
        return SUCCESS
    due = ctx.state.get(ctx.path)
    if due is None:
        ctx.state[ctx.path] = world.tick + data.GATHER_TICKS
        return RUNNING
    if world.tick < due:
        return RUNNING
    unit.carry += world.take(o, 1)
    unit.carry_kind = kind
    if unit.carry >= data.CARRY_CAPACITY:
        return SUCCESS
    ctx.state[ctx.path] = world.tick + data.GATHER_TICKS
    return RUNNING


@node("action", "unit", "Find the team's nearest drop-off (a grown Greenhouse or Root Cellar); store its id in `key`.",
      key=Arg("str", "dropoff"))
def find_dropoff(ctx, key):
    world = ctx.world
    here = world.tile_of(ctx.agent)
    spots = [(_distance_to(here, b), b.id) for b in world.buildings
             if b.team == ctx.agent.team and b.kind in data.DROPOFFS and b.state == "grown"]
    if not spots:
        return FAILURE
    ctx.bb[key] = min(spots)[1]
    return SUCCESS


@node("action", "unit", "Hand the load to the team while standing beside the drop-off whose id is in `key`.",
      key=Arg("str", "dropoff"))
def deposit(ctx, key):
    unit, world = ctx.agent, ctx.world
    b = world.entity(ctx.bb.get(key))
    if (b is None or getattr(b, "team", None) != unit.team or b.kind not in data.DROPOFFS
            or not _beside(ctx, b) or unit.carry == 0):
        return FAILURE
    world.deposit(ctx.team, unit.carry_kind, unit.carry)
    unit.carry, unit.carry_kind = 0, ""
    return SUCCESS


# ---------------------------------------------------------------- team planners
@node("action", "team", "Store a rally tile in `key`: 'home' is in front of the team's Greenhouse; "
      "'center' is the middle of the map, on this team's side.", key=Arg("str", "rally"), mode=Arg("str", "center"))
def choose_rally(ctx, key, mode):
    world, team = ctx.world, ctx.agent
    if mode == "home":
        spot = tuple(team.spawn)
    elif mode == "center":
        cx, cy = world.width // 2, world.height // 2
        sx = -3 if team.spawn[0] < cx else 2
        sy = -3 if team.spawn[1] < cy else 2
        spot = world.nearest_walkable(cx + sx, cy + sy)
    else:
        return FAILURE
    ctx.bb[key] = list(spot)
    return SUCCESS


@node("action", "team", "Give the team's Spuds jobs, in id order: the first `compost` gather Compost, the next "
      "`lumber` Lumber, the next `stone` Stone; any extra Spuds get the last job. Sets each Spud's `job`.",
      compost=Arg("int", 1), lumber=Arg("int", 1), stone=Arg("int", 1))
def assign_spud_jobs(ctx, compost, lumber, stone):
    jobs = ["compost"] * compost + ["lumber"] * lumber + ["stone"] * stone
    if not jobs:
        return FAILURE
    spuds = [u for u in ctx.world.units if u.team == ctx.agent.id and u.kind == "spud"]
    for i, spud in enumerate(spuds):
        spud.bb["job"] = jobs[min(i, len(jobs) - 1)]
    return SUCCESS
