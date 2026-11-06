"""The node library: the conditions and actions behavior trees can use.

Tiles in blackboards are stored as [x, y] lists so blackboards stay plain JSON.
"""
from __future__ import annotations

from lettuce_conquer.sim.bt import FAILURE, RUNNING, SUCCESS, Arg, node
from lettuce_conquer.sim.pathfind import find_path


def _tile(value) -> tuple[int, int] | None:
    if isinstance(value, list) and len(value) == 2 and all(isinstance(v, int) for v in value):
        return value[0], value[1]
    return None


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


# ---------------------------------------------------------------- units
@node("condition", "unit", "True when the team planner's blackboard has `key`.", key=Arg("str"))
def team_has_key(ctx, key):
    return SUCCESS if key in ctx.team.bb else FAILURE


@node("condition", "unit", "True when the unit stands on the tile stored in `key`.", key=Arg("str", "goal"))
def at_tile(ctx, key):
    tile = _tile(ctx.bb.get(key))
    return SUCCESS if tile is not None and ctx.world.tile_of(ctx.agent) == tile else FAILURE


@node("action", "unit", "Pick a random walkable tile within `radius` tiles of home; store it in `key`.",
      key=Arg("str", "spot"), radius=Arg("int", 4))
def pick_wander_spot(ctx, key, radius):
    world = ctx.world
    hx, hy = _tile(ctx.bb.get("home")) or world.tile_of(ctx.agent)
    for _ in range(20):
        x, y = hx + world.rng.randint(-radius, radius), hy + world.rng.randint(-radius, radius)
        if world.walkable(x, y):
            ctx.bb[key] = [x, y]
            return SUCCESS
    return FAILURE


@node("action", "unit", "Walk to the tile stored in `key`. Runs while walking, succeeds on arrival, "
      "fails if the tile can't be reached.", key=Arg("str", "goal"))
def move_to(ctx, key):
    unit, world = ctx.agent, ctx.world
    target = _tile(ctx.bb.get(key))
    if target is None:
        return FAILURE
    if not unit.path and (unit.x, unit.y) == world.center(*target):
        return SUCCESS
    if not unit.path or ctx.state.get(ctx.path) != list(target):
        route = find_path(world.tile_of(unit), target, world.walkable)
        if route is None:
            return FAILURE
        unit.path = [list(t) for t in route[1:]] or [list(target)]  # already on the tile: walk to its centre
        ctx.state[ctx.path] = list(target)
    unit.move_requested = True
    return RUNNING


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
        if ctx.world.walkable(spot[0] + dx, spot[1] + dy):
            ctx.bb[key] = [spot[0] + dx, spot[1] + dy]
            return SUCCESS
    return FAILURE


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
