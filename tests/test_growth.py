"""Milestone 3: building, irrigation, water and sprouting."""
import pytest

from lettuce_conquer.sim import bt, data, mapgen
from lettuce_conquer.sim.world import World

NO_PLANS = {"planner": "planner_rally"}  # Spuds still work, but the planner never builds or sprouts


def greenhouse(world, team=0):
    return next(b for b in world.buildings if b.team == team and b.kind == "greenhouse")


def can_of(world, team=0):
    """The Watering Can in the team's own base."""
    gh = greenhouse(world, team)
    cans = [t for t in world.things if t.kind == "watering_can"]
    return min(cans, key=lambda c: abs(c.x - gh.x) + abs(c.y - gh.y))


def run_node(world, name, team=0, **args):
    t = world.teams[team]
    ctx = bt.Context(world, t, t, "team", path="test")
    spec = bt.NODES[name]
    full = {k: a.default for k, a in spec.args.items()}
    full.update(args)
    return spec.fn(ctx, **full)


def dig_all(world, team=0):
    for c in world.channels.values():
        if c.team == team:
            c.dug = True


def test_tending_grows_planted_to_sprout_to_grown():
    world = World(seed=3, teams=2, trees=NO_PLANS)
    b = world.place_building(world.teams[0], "cabbage_patch", 0, 0)
    ticks = data.BUILD_WORK["cabbage_patch"]
    assert b.state == "planted" and b.fertile == 0
    states = []
    for _ in range(ticks):
        world.tend(b)
        states.append(b.state)
    assert states.index("sprout") == ticks // 2 - 1
    assert states[-2] == "sprout" and states[-1] == "grown"


def test_order_building_pays_and_plants_on_grass_near_home():
    world = World(seed=3, teams=2, trees=NO_PLANS)
    team = world.teams[0]
    assert run_node(world, "order_building", kind="cabbage_patch") == bt.FAILURE  # can't pay yet
    team.stock.update(lumber=100, stone=100)
    assert run_node(world, "order_building", kind="cabbage_patch") == bt.SUCCESS
    assert team.stock["lumber"] == 40 and team.stock["stone"] == 60
    b = world.buildings[-1]
    assert (b.kind, b.state, b.team) == ("cabbage_patch", "planted", 0)
    tiles = [(b.x + i, b.y + j) for i in range(2) for j in range(2)]
    assert all(world.tiles[y][x] in (mapgen.GRASS, mapgen.FIELD) for x, y in tiles)
    assert all(t in world.blocked for t in tiles)
    assert all(world.walkable(*t) for t in world.ring(b))  # a walkway all round
    assert world.walkable(*world.inlet_tile(b))


@pytest.mark.parametrize("teams", [2, 4])
def test_inlets_and_spouts_face_the_middle_of_the_map(teams):
    world = World(seed=5, teams=teams, trees=NO_PLANS)
    mid = world.width / 2
    for team in world.teams:
        gh = greenhouse(world, team.id)
        ix, iy = world.inlet_tile(gh)
        sx, sy = world.flips(team)
        assert iy == (gh.y + gh.h if sy > 0 else gh.y - 1)  # in front of the building, toward the middle
        assert abs(iy + 0.5 - mid) < abs(gh.y + gh.h / 2 - mid)
        assert ix == (gh.x if sx > 0 else gh.x + gh.w - 1)
        can = can_of(world, team.id)
        ox, oy = world.outlet_tile(can)
        assert abs(oy + 0.5 - mid) < abs(can.y + can.h / 2 - mid)
    # every team's inlet is the mirror of blue's
    blue = world.inlet_tile(greenhouse(world, 0))
    for team in world.teams[1:]:
        sx, sy = world.flips(team)
        x, y = world.inlet_tile(greenhouse(world, team.id))
        assert (x if sx > 0 else world.width - 1 - x, y if sy > 0 else world.height - 1 - y) == blue


def test_planned_channel_connects_the_can_once_dug():
    world = World(seed=3, teams=2, trees=NO_PLANS)
    gh = greenhouse(world)
    assert run_node(world, "order_channel", kind="greenhouse") == bt.SUCCESS
    route = {t for t, c in world.channels.items() if c.team == 0}
    can = can_of(world)
    assert world.inlet_tile(gh) in route and world.outlet_tile(can) in route and gh.can == can.id
    assert world.connected_can(gh) is None  # planned isn't dug
    dig_all(world)
    assert world.connected_can(gh) is can
    assert route <= world.wet_channels()
    world.step()
    assert world.teams[0].stock["water"] == can.amount == data.CAN_CAPACITY


def test_spuds_dig_channels_paying_lumber():
    world = World(seed=3, teams=2, trees=NO_PLANS)
    run_node(world, "order_channel", kind="greenhouse")
    world.teams[0].stock["lumber"] = 500
    tiles = [c for c in world.channels.values() if c.team == 0]
    for _ in range(1200):
        world.step()
        if all(c.dug for c in tiles):
            break
    assert all(c.dug and c.paid for c in tiles)
    assert world.teams[0].stock["lumber"] <= 500 - data.CHANNEL_COST * len(tiles) + 100  # gathering adds some back


def test_sprouting_pays_compost_draws_water_and_pops_out_a_unit():
    world = World(seed=3, teams=2, trees=NO_PLANS)
    team, gh, can = world.teams[0], greenhouse(world), can_of(world)
    run_node(world, "order_channel", kind="greenhouse")
    assert run_node(world, "sprout", kind="spud") == bt.FAILURE  # not watered yet
    dig_all(world)
    assert run_node(world, "sprout", kind="spud") == bt.FAILURE  # no Compost
    team.stock["compost"] = 60
    assert run_node(world, "sprout", kind="spud") == bt.SUCCESS
    assert team.stock["compost"] == 10 and gh.state == "sprouting"
    assert run_node(world, "sprout", kind="spud") == bt.FAILURE  # one at a time
    spuds = sum(1 for u in world.units if u.team == 0 and u.kind == "spud")
    for _ in range(data.SPROUT_TICKS["spud"]):
        world.step()
    assert sum(1 for u in world.units if u.team == 0 and u.kind == "spud") == spuds + 1
    assert gh.state == "grown" and not gh.sprout_kind
    assert can.amount == data.CAN_CAPACITY - data.UNIT_COST["spud"]["water"]


def test_sprouting_pauses_while_the_can_is_dry():
    world = World(seed=3, teams=2, trees=NO_PLANS)
    team, gh, can = world.teams[0], greenhouse(world), can_of(world)
    run_node(world, "order_channel", kind="greenhouse")
    dig_all(world)
    team.stock["compost"] = 50
    run_node(world, "sprout", kind="spud")
    can.amount = 0
    for _ in range(data.SPROUT_TICKS["spud"] + 20):
        world.step()
        can.amount = 0  # nobody refills it
    assert gh.sprout_left == data.SPROUT_TICKS["spud"] * data.PACE and gh.state == "sprouting"


def test_water_spud_refills_a_connected_can_from_the_lake():
    world = World(seed=3, teams=2, trees=NO_PLANS)
    can = can_of(world)
    run_node(world, "order_channel", kind="greenhouse")
    dig_all(world)
    can.amount = 100
    for _ in range(1500):
        for u in world.units:
            if u.team == 0 and u.kind == "spud":
                u.bb["job"] = "water"  # the planner would hand out other jobs
        world.step()
        if can.amount >= 200:
            break
    assert can.amount >= 200


def test_water_cannot_be_deposited():
    world = World(seed=3, teams=2, trees=NO_PLANS)
    unit = next(u for u in world.units if u.team == 0 and u.kind == "spud")
    gh = greenhouse(world)
    unit.carry, unit.carry_kind = 10, "water"
    unit.bb["dropoff"] = gh.id
    ctx = bt.Context(world, unit, world.teams[0], "unit", path="test")
    assert bt.NODES["deposit"].fn(ctx, key="dropoff") == bt.FAILURE
    assert world.teams[0].stock["water"] == 0


def test_default_trees_grow_an_army_from_scratch():
    world = World(seed=1, teams=2)
    start = {k: sum(1 for u in world.units if u.team == 0 and u.kind == k) for k in data.UNIT_SPEED}
    for _ in range(3000):
        world.step()
    now = {k: sum(1 for u in world.units if u.team == 0 and u.kind == k) for k in data.UNIT_SPEED}
    kinds = {b.kind for b in world.buildings if b.team == 0 and b.state in ("grown", "sprouting")}
    assert now["spud"] > start["spud"] and now["cabbage"] > start["cabbage"]
    assert {"greenhouse", "cabbage_patch"} <= kinds


def test_four_armies_stay_mirrored():
    world = World(seed=11, teams=4)
    size = world.width * data.TILE
    for _ in range(1200):
        world.step()
        armies = [[u for u in world.units if u.team == t.id] for t in world.teams]
        for team, army in zip(world.teams[1:], armies[1:]):
            sx, sy = world.flips(team)
            assert [u.kind for u in army] == [u.kind for u in armies[0]], world.tick
            for b, u in zip(armies[0], army):
                assert ((u.x if sx > 0 else size - u.x), (u.y if sy > 0 else size - u.y)) == (b.x, b.y), world.tick
            assert team.stock == world.teams[0].stock, world.tick


def test_units_never_stand_inside_buildings():
    world = World(seed=4, teams=2)
    for _ in range(2500):
        world.step()
        for u in world.units:
            assert world.tile_of(u) not in {(b.x + i, b.y + j) for b in world.buildings
                                            for i in range(b.w) for j in range(b.h)}, (world.tick, u.kind)


# ---------------------------------------------------------------- fertile ground
def field_site(world, size=2):
    """A spot fully on one tilled field where a size x size building could go."""
    for fx, fy, fw, fh in world.fields:
        if fw >= size and fh >= size:
            return fx, fy
    raise AssertionError("no field big enough")


def test_fertility_scales_with_field_tiles():
    world = World(seed=3, teams=2, trees=NO_PLANS)
    x, y = field_site(world)
    assert world.fertility(x, y, 2, 2) == data.FERTILE_BONUS
    gh = greenhouse(world)
    assert world.fertility(gh.x, gh.y, 3, 3) == 0
    tiles = [world.tiles[y + j][x - 1 + i] == mapgen.FIELD for i in range(2) for j in range(2)]
    assert world.fertility(x - 1, y, 2, 2) == data.FERTILE_BONUS * sum(tiles) // 4  # half on, half off


def test_buildings_can_be_planted_on_fields():
    world = World(seed=3, teams=2, trees=NO_PLANS)
    team = world.teams[0]
    spots = [(x, y) for fx, fy, fw, fh in world.fields for x in range(fx, fx + fw - 1) for y in range(fy, fy + fh - 1)
             if world._site_ok(team, "cabbage_patch", x, y, 2)]
    assert spots  # field ground is buildable (some spots are ruled out by the walkway or map edge)
    x, y = spots[0]
    assert world.find_site(team, "cabbage_patch", (x, y)) is not None
    b = world.place_building(team, "cabbage_patch", x, y)
    assert b.fertile == world.fertility(x, y, 2, 2) > 0


def test_fertile_buildings_grow_faster():
    world = World(seed=3, teams=2, trees=NO_PLANS)
    x, y = field_site(world)
    plain = world.place_building(world.teams[0], "cabbage_patch", 0, 0)
    rich = world.place_building(world.teams[0], "cabbage_patch", x, y)
    def ticks_to_grow(b):
        n = 0
        while b.state != "grown":
            world.tend(b)
            n += 1
        return n
    slow, fast = ticks_to_grow(plain), ticks_to_grow(rich)
    assert slow == data.BUILD_WORK["cabbage_patch"]
    assert fast == -(-slow * 100 // (100 + data.FERTILE_BONUS))


def test_fertile_buildings_sprout_faster_with_the_same_water():
    world = World(seed=3, teams=2, trees=NO_PLANS)
    team, gh, can = world.teams[0], greenhouse(world), can_of(world)
    run_node(world, "order_channel", kind="greenhouse")
    dig_all(world)
    gh.fertile = data.FERTILE_BONUS  # pretend it was planted on a field
    team.stock["compost"] = 50
    assert run_node(world, "sprout", kind="spud") == bt.SUCCESS
    ticks = 0
    while gh.sprout_kind:
        world.step()
        ticks += 1
    assert ticks == -(-data.SPROUT_TICKS["spud"] * 100 // (100 + data.FERTILE_BONUS))
    assert can.amount == data.CAN_CAPACITY - data.UNIT_COST["spud"]["water"]


def test_building_fertile_condition():
    world = World(seed=3, teams=2, trees=NO_PLANS)
    assert run_node(world, "building_fertile", kind="cabbage_patch") == bt.FAILURE
    x, y = field_site(world)
    world.place_building(world.teams[0], "cabbage_patch", x, y)
    assert run_node(world, "building_fertile", kind="cabbage_patch", percent=data.FERTILE_BONUS) == bt.SUCCESS
    assert run_node(world, "building_fertile", team=1, kind="cabbage_patch") == bt.FAILURE
