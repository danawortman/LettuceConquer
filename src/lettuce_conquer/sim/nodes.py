"""The node library: the conditions and actions behavior trees can use.

Tiles in blackboards are stored as [x, y] lists and map objects by their id, so blackboards stay
plain JSON.
"""
from __future__ import annotations

from collections import namedtuple

from lettuce_conquer.sim import data
from lettuce_conquer.sim.bt import FAILURE, RUNNING, SUCCESS, Arg, node
from lettuce_conquer.sim.pathfind import _octile, find_path

_Box = namedtuple("_Box", "x y w h")  # a footprint, for World.ring


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
            route = find_path(world.tile_of(unit), target, lambda x, y: world.free(x, y, unit), world.steps_for(ctx.team))
        else:
            route = find_path(world.tile_of(unit), target, world.walkable, world.steps_for(ctx.team))
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
    sx, sy = world.flips(ctx.team)
    for _ in range(20):  # the team's own stream, offsets mirrored: mirrored units pick mirrored spots
        x, y = hx + sx * world.roll(ctx.team, -radius, radius), hy + sy * world.roll(ctx.team, -radius, radius)
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
        chosen = min(spots, key=lambda t: (_octile(here, t), world.local(ctx.team, *t)))  # mirrored tie-break
    return _walk_to(ctx, chosen)


@node("action", "unit", "Copy the team planner's tile `team_key` into `key`, shifted up to `spread` tiles "
      "per unit so a squad doesn't stack on one tile.",
      team_key=Arg("str", "rally"), key=Arg("str", "goal"), spread=Arg("int", 1))
def copy_team_key(ctx, team_key, key, spread):
    spot = _tile(ctx.team.bb.get(team_key))
    if spot is None:
        return FAILURE
    sx, sy = ctx.world.flips(ctx.team)
    offsets = [(dx * sx, dy * sy) for r in range(spread + 1) for dy in range(-r, r + 1) for dx in range(-r, r + 1)
               if max(abs(dx), abs(dy)) == r]
    rank = [u.id for u in ctx.world.units if u.team == ctx.agent.team].index(ctx.agent.id)
    start = rank % len(offsets)
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


@node("action", "unit", "Find the nearest map feature holding `resource` (compost, lumber, stone or water; or, if "
      "`resource` is empty, the resource named in blackboard `resource_key`) and store its id in `key`.",
      resource=Arg("str", ""), resource_key=Arg("str", "job"), key=Arg("str", "target"))
def find_nearest_resource(ctx, resource, resource_key, key):
    world = ctx.world
    wanted = resource or ctx.bb.get(resource_key)
    here = world.tile_of(ctx.agent)
    best = None
    for t in world.things:
        if data.YIELDS.get(t.kind, ("",))[0] == wanted and (t.amount > 0 or t.kind in data.ENDLESS):
            rank = (_distance_to(here, t), world.local_corner(ctx.team, t))
            if best is None or rank < best[0]:
                best = (rank, t.id)
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
    if o is None or (o.amount == 0 and o.kind not in data.ENDLESS):  # used up (or a stump): fine if we got something
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
    spots = [(_distance_to(here, b), world.local_corner(ctx.team, b), b.id) for b in world.buildings
             if b.team == ctx.agent.team and b.kind in data.DROPOFFS and b.state == "grown"]
    if not spots:
        return FAILURE
    ctx.bb[key] = min(spots)[2]
    return SUCCESS


@node("action", "unit", "Hand the load to the team while standing beside the drop-off whose id is in `key`. "
      "Water can't be delivered: it goes into a Watering Can (see pour).",
      key=Arg("str", "dropoff"))
def deposit(ctx, key):
    unit, world = ctx.agent, ctx.world
    b = world.entity(ctx.bb.get(key))
    if (b is None or getattr(b, "team", None) != unit.team or b.kind not in data.DROPOFFS
            or not _beside(ctx, b) or unit.carry == 0 or unit.carry_kind == "water"):
        return FAILURE
    world.deposit(ctx.team, unit.carry_kind, unit.carry)
    unit.carry, unit.carry_kind = 0, ""
    return SUCCESS


# ---------------------------------------------------------------- team planners
@node("action", "team", "Store a rally tile in `key`: 'home' is in front of the team's Greenhouse; "
      "'center' is the middle of the map, on this team's side; 'toggle' switches between the two each time.",
      key=Arg("str", "rally"), mode=Arg("str", "center"))
def choose_rally(ctx, key, mode):
    world, team = ctx.world, ctx.agent
    if mode == "toggle":
        mode = "home" if ctx.bb.get(key + "_mode") == "center" else "center"
        ctx.bb[key + "_mode"] = mode
    if mode == "home":
        spot = tuple(team.spawn)
    elif mode == "center":
        cx, cy = world.width // 2, world.height // 2
        sx = -3 if team.spawn[0] < cx else 2
        sy = -3 if team.spawn[1] < cy else 2
        spot = world.nearest_walkable(cx + sx, cy + sy, team)
    else:
        return FAILURE
    ctx.bb[key] = list(spot)
    return SUCCESS


@node("action", "team", "Give the team's Spuds jobs, in id order: the first `compost` gather Compost, the next "
      "`lumber` Lumber, the next `stone` Stone, the next `water` fetch Water for the Watering Cans; any extra "
      "Spuds go round the list again. Sets each Spud's `job`.",
      compost=Arg("int", 1), lumber=Arg("int", 1), stone=Arg("int", 1), water=Arg("int", 0))
def assign_spud_jobs(ctx, compost, lumber, stone, water):
    jobs = ["compost"] * compost + ["lumber"] * lumber + ["stone"] * stone + ["water"] * water
    if not jobs:
        return FAILURE
    spuds = [u for u in ctx.world.units if u.team == ctx.agent.id and u.kind == "spud"]
    for i, spud in enumerate(spuds):
        spud.bb["job"] = jobs[i % len(jobs)]
    return SUCCESS


# ---------------------------------------------------------------- general conditions
@node("condition", "any", "True when blackboard `key` holds the text `value`.", key=Arg("str"), value=Arg("str"))
def key_equals(ctx, key, value):
    return SUCCESS if ctx.bb.get(key) == value else FAILURE


@node("condition", "any", "True when the team has at least `amount` of `resource` in stock.",
      resource=Arg("str"), amount=Arg("int", 1))
def stock_at_least(ctx, resource, amount):
    return SUCCESS if ctx.team.stock.get(resource, 0) >= amount else FAILURE


@node("condition", "any", "True when the team has fewer than `count` buildings of `kind` (any state, sites too).",
      kind=Arg("str"), count=Arg("int", 1))
def building_count_below(ctx, kind, count):
    have = sum(1 for b in ctx.world.buildings if b.team == ctx.team.id and b.kind == kind)
    return SUCCESS if have < count else FAILURE


@node("condition", "any", "True when the team has fewer than `count` units of `kind` (counting ones still sprouting).",
      kind=Arg("str"), count=Arg("int", 1))
def unit_count_below(ctx, kind, count):
    world, team = ctx.world, ctx.team
    have = sum(1 for u in world.units if u.team == team.id and u.kind == kind)
    have += sum(1 for b in world.buildings if b.team == team.id and b.sprout_kind == kind)
    return SUCCESS if have < count else FAILURE


@node("condition", "any", "True when the team has a `kind` building at least `percent` fertile (planted on "
      "tilled field tiles, it grows and sprouts that much faster).", kind=Arg("str"), percent=Arg("int", 1))
def building_fertile(ctx, kind, percent):
    return SUCCESS if any(b.team == ctx.team.id and b.kind == kind and b.fertile >= percent
                          for b in ctx.world.buildings) else FAILURE


# ---------------------------------------------------------------- units: building and irrigation
@node("condition", "unit", "True when the unit carries some `resource`.", resource=Arg("str", "water"))
def carrying(ctx, resource):
    return SUCCESS if ctx.agent.carry > 0 and ctx.agent.carry_kind == resource else FAILURE


@node("action", "unit", "Find the team's nearest building that still needs tending (Planted or Sprout); "
      "store its id in `key`.", key=Arg("str", "site"))
def find_construction(ctx, key):
    world = ctx.world
    here = world.tile_of(ctx.agent)
    sites = [(_distance_to(here, b), world.local_corner(ctx.team, b), b.id) for b in world.buildings
             if b.team == ctx.agent.team and b.state in ("planted", "sprout")]
    if not sites:
        return FAILURE
    ctx.bb[key] = min(sites)[2]
    return SUCCESS


@node("action", "unit", "Tend the building whose id is in `key` while standing beside it, one Spud-tick each tick "
      "(Spuds tending together add up). Succeeds once it has grown; fails if not beside it.",
      key=Arg("str", "site"))
def tend(ctx, key):
    world = ctx.world
    b = world.entity(ctx.bb.get(key))
    if b is None or getattr(b, "team", None) != ctx.agent.team or ctx.agent.kind != "spud":
        return FAILURE
    if b.state not in ("planted", "sprout"):
        return SUCCESS
    if not _beside(ctx, b):
        return FAILURE
    world.tend(b)
    return SUCCESS if b.state == "grown" else RUNNING


@node("action", "unit", "Find the next undug tile of the team's planned irrigation channels (dug from the "
      "Watering Can outward) that no teammate is already on or headed for; store the tile in `key`.",
      key=Arg("str", "ditch"))
def find_channel_work(ctx, key):
    world, unit = ctx.world, ctx.agent
    taken = set()
    for u in world.units:
        if u is not unit and u.team == unit.team:
            t = _tile(u.bb.get(key))
            if t is not None:
                taken.add(t)
    todo = sorted((c.order, (c.x, c.y)) for c in world.channels.values() if c.team == unit.team and not c.dug)
    for _, tile in todo:
        if tile not in taken and world.occupant(tile, unit) is None:
            ctx.bb[key] = list(tile)
            return SUCCESS
    ctx.bb.pop(key, None)
    return FAILURE


@node("action", "unit", "Dig the channel tile stored in `key` while standing on it. The first dig pays the "
      "tile's Lumber; fails if the team can't pay. Succeeds once the tile is dug.", key=Arg("str", "ditch"))
def dig(ctx, key):
    world, unit = ctx.world, ctx.agent
    tile = _tile(ctx.bb.get(key))
    channel = world.channels.get(tile) if tile is not None else None
    if channel is None or channel.team != unit.team or unit.kind != "spud":
        ctx.bb.pop(key, None)
        return FAILURE
    if channel.dug:
        ctx.bb.pop(key, None)
        return SUCCESS
    if world.tile_of(unit) != tile or not world.at_center(unit):
        return FAILURE
    if not channel.paid:
        if ctx.team.stock["lumber"] < data.CHANNEL_COST:
            ctx.bb.pop(key, None)
            return FAILURE
        ctx.team.stock["lumber"] -= data.CHANNEL_COST
        channel.paid = True
    world.dig(channel)
    if channel.dug:
        ctx.bb.pop(key, None)
        return SUCCESS
    return RUNNING


@node("action", "unit", "Find the nearest Watering Can that waters one of the team's buildings and isn't full; "
      "store its id in `key`. Fails if no can needs water.", key=Arg("str", "can"))
def find_can(ctx, key):
    world = ctx.world
    here = world.tile_of(ctx.agent)
    cans = {}
    for b in world.buildings:
        if b.team == ctx.agent.team:
            can = world.connected_can(b)
            if can is not None and can.amount < can.max_amount:
                cans[can.id] = can
    if not cans:
        return FAILURE
    ctx.bb[key] = min((_distance_to(here, c), world.local_corner(ctx.team, c), c.id) for c in cans.values())[2]
    return SUCCESS


@node("action", "unit", "Pour the Water the unit carries into the Watering Can whose id is in `key` while standing "
      "beside it. Whatever doesn't fit spills. Fails if not beside a can or carrying no water.", key=Arg("str", "can"))
def pour(ctx, key):
    world, unit = ctx.world, ctx.agent
    can = world.entity(ctx.bb.get(key))
    if (can is None or getattr(can, "kind", "") != "watering_can" or unit.carry_kind != "water"
            or unit.carry == 0 or not _beside(ctx, can)):
        return FAILURE
    world.pour(can, unit.carry)
    unit.carry, unit.carry_kind = 0, ""
    return SUCCESS


# ---------------------------------------------------------------- team planners: building and sprouting
def _anchor(world, team, near):
    if near == "home":
        return tuple(team.spawn)
    spots = [(_distance_to(tuple(team.spawn), t), world.local_corner(team, t), t.id, t) for t in world.things
             if data.YIELDS.get(t.kind, ("",))[0] == near]
    if not spots:
        return None
    t = min(spots, key=lambda s: s[:3])[3]
    return t.x, t.y


@node("action", "team", "Order a new `kind` building: find a free spot near `near` ('home', or a resource such as "
      "'compost', 'lumber', 'stone', 'water'), pay its Lumber and Stone, and plant it for Spuds to tend. "
      "Fails if the team can't pay or there's no room.", kind=Arg("str"), near=Arg("str", "home"))
def order_building(ctx, kind, near):
    world, team = ctx.world, ctx.agent
    cost = data.BUILD_COST.get(kind)
    if cost is None or any(team.stock[r] < n for r, n in cost.items()):
        return FAILURE
    anchor = _anchor(world, team, near)
    site = world.find_site(team, kind, anchor) if anchor is not None else None
    if site is None:
        return FAILURE
    for r, n in cost.items():
        team.stock[r] -= n
    world.place_building(team, kind, *site)
    return SUCCESS


@node("action", "team", "Plan irrigation channels from the nearest Watering Can to every `kind` building of the "
      "team that has none yet (Spuds dig them). Succeeds when every such building has a channel planned.",
      kind=Arg("str", "greenhouse"))
def order_channel(ctx, kind):
    world, team = ctx.world, ctx.agent
    ok = True
    for b in world.buildings:
        if b.team == team.id and b.kind == kind and not b.can:
            ok = world.plan_channel(team, b) and ok
    return SUCCESS if ok else FAILURE


@node("action", "team", "Start sprouting a `kind` unit in an idle, grown, watered building that makes it: pays the "
      "Compost now; Water is drawn from the connected can while it grows. Fails if none can.",
      kind=Arg("str", "spud"))
def sprout(ctx, kind):
    world, team = ctx.world, ctx.agent
    homes = sorted((world.local_corner(team, b), b.id, b) for b in world.buildings
                   if b.team == team.id and data.SPROUTS.get(b.kind) == kind)
    for _, _, b in homes:
        if world.start_sprout(team, b, kind):
            return SUCCESS
    return FAILURE


# ---------------------------------------------------------------- combat
def _enemies(ctx, reach):
    world, unit = ctx.world, ctx.agent
    return [o for o in world.units if world.is_enemy(unit.team, o) and world.tiles_between(unit, o) <= reach]


@node("condition", "unit", "True when an enemy unit is within `range` tiles.", range=Arg("int", data.SIGHT))
def enemy_near(ctx, range):  # noqa: A002  (the argument is named for tree authors)
    return SUCCESS if _enemies(ctx, range) else FAILURE


@node("action", "unit", "Find the nearest enemy unit within `range` tiles (fighters before Spuds); store its id "
      "in `key`.", key=Arg("str", "foe"), range=Arg("int", data.SIGHT))
def find_enemy(ctx, key, range):  # noqa: A002
    world = ctx.world
    foes = [(world.tiles_between(ctx.agent, o), o.kind == "spud", world.local(ctx.team, *world.tile_of(o)), o.id)
            for o in _enemies(ctx, range)]
    if not foes:
        return FAILURE
    ctx.bb[key] = min(foes)[3]
    return SUCCESS


@node("action", "unit", "Attack the enemy unit or building whose id is in `key`: walk up to it, then hit it "
      "whenever ready (Pea Shooters from 4 tiles, others from the next tile). Runs while fighting; succeeds once "
      "it has fallen; fails if it can't be reached or this unit can't fight.", key=Arg("str", "foe"))
def attack(ctx, key):
    world, unit = ctx.world, ctx.agent
    stats = data.ATTACK.get(unit.kind)
    eid = ctx.bb.get(key)
    if stats is None or eid is None:
        return FAILURE
    foe = world.target(eid)
    if foe is None or not world.is_enemy(unit.team, foe):
        ctx.bb.pop(key, None)  # it fell (or was never an enemy)
        return SUCCESS if foe is None else FAILURE
    if world.tiles_between(unit, foe) <= stats["range"]:
        world.strike(unit, foe)  # stand and fight (does nothing while getting ready to hit again)
        return RUNNING
    here = world.tile_of(unit)
    ring = world.ring(_Box(*world.footprint(foe)))
    spots = [t for t in ring if world.free(*t, unit)]
    if not spots:
        return FAILURE
    spot = min(spots, key=lambda t: (_octile(here, t), world.local(ctx.team, *t)))  # mirrored tie-break
    status = _walk_to(ctx, spot)
    return RUNNING if status == SUCCESS else status


@node("action", "unit", "Copy whatever the team planner stores under `team_key` (a tile, an id, a word) into `key`.",
      team_key=Arg("str"), key=Arg("str"))
def copy_team_value(ctx, team_key, key):
    if team_key not in ctx.team.bb:
        return FAILURE
    value = ctx.team.bb[team_key]
    ctx.bb[key] = list(value) if isinstance(value, list) else value
    return SUCCESS


@node("condition", "any", "True when the team has at least `count` fighters (Sir Cabbages, Pea Shooters and Carrot "
      "Lancers).", count=Arg("int", 1))
def fighters_at_least(ctx, count):
    have = sum(1 for u in ctx.world.units if u.team == ctx.team.id and u.kind in data.ATTACK)
    return SUCCESS if have >= count else FAILURE


@node("action", "team", "Store the id of the nearest enemy Greenhouse still standing in `key`.", key=Arg("str", "target"))
def choose_enemy_greenhouse(ctx, key):
    world, team = ctx.world, ctx.agent
    home = tuple(team.spawn)
    targets = [(_distance_to(home, b), world.local_corner(team, b), b.id) for b in world.buildings
               if b.kind == "greenhouse" and world.is_enemy(team.id, b)]
    if not targets:
        return FAILURE
    ctx.bb[key] = min(targets)[2]
    return SUCCESS
