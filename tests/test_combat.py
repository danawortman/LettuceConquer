"""Milestone 4: combat, counters, fallen units, Scarecrows and winning."""
import pytest

from lettuce_conquer.sim import bt, data
from lettuce_conquer.sim.world import World

CALM = {"planner": "planner_rally", "spud": "unit_wander", "cabbage": "unit_wander", "pea": "unit_wander",
        "carrot": "unit_wander"}


def place(world, unit, tile):
    unit.x, unit.y = world.center(*tile)
    unit.prev_x, unit.prev_y = unit.x, unit.y
    unit.path.clear()


def pair(world, kind_a, kind_b, gap=1):
    """A blue `kind_a` and a red `kind_b` standing `gap` tiles apart on open ground."""
    a = next(u for u in world.units if u.team == 0 and u.kind == kind_a)
    b = next(u for u in world.units if u.team == 1 and u.kind == kind_b)
    x, y = 18, 18
    while not all(world.free(x + i, y) for i in range(gap + 1)):
        x, y = x + 1, y + 1
    place(world, a, (x, y))
    place(world, b, (x + gap, y))
    return a, b


@pytest.mark.parametrize("attacker,target,percent", [
    ("cabbage", "pea", 200), ("pea", "carrot", 200), ("carrot", "cabbage", 200),   # counters
    ("pea", "cabbage", 50), ("carrot", "pea", 50), ("cabbage", "carrot", 50),      # countered
    ("cabbage", "cabbage", 100), ("pea", "spud", 100),
])
def test_counters_double_and_halve_damage(attacker, target, percent):
    world = World(seed=3, teams=2, trees=CALM)
    a, b = pair(world, attacker, target)
    base = data.ATTACK[attacker]["damage"]
    assert world.damage(attacker, base, b) == base * percent // 100


def test_melee_reaches_one_tile_and_peas_reach_four():
    world = World(seed=3, teams=2, trees=CALM)
    cab, foe = pair(world, "cabbage", "carrot", gap=2)
    assert not world.strike(cab, foe)  # two tiles away: out of reach
    pea, foe2 = pair(world, "pea", "carrot", gap=4)
    assert world.strike(pea, foe2)
    assert not world.strike(pea, foe2)  # not ready to hit again yet
    world.tick = pea.next_attack
    assert world.strike(pea, foe2)


def test_hits_land_together_so_nobody_strikes_first():
    world = World(seed=3, teams=2, trees=CALM)
    a, b = pair(world, "cabbage", "cabbage")
    a.hp = b.hp = data.ATTACK["cabbage"]["damage"]  # one hit each is lethal
    assert world.strike(a, b) and world.strike(b, a)
    world._land_hits()
    assert a not in world.units and b not in world.units  # both fell: the first striker gained nothing


def test_fallen_units_leave_compost_piles_spuds_can_gather():
    world = World(seed=3, teams=2, trees=CALM)
    a, b = pair(world, "pea", "carrot")
    tile = world.tile_of(b)
    b.hp = 1
    world.strike(a, b)
    world._land_hits()
    pile = next(t for t in world.things if t.kind == "remains_carrot")
    assert (pile.x, pile.y) == tile and tile in world.blocked
    assert pile.amount == data.YIELDS["remains_carrot"][1]
    world.take(pile, 10)
    assert pile.state == "full"  # piles have one look until they're gone
    world.take(pile, 100)
    assert pile not in world.things and tile not in world.blocked


def test_attack_node_chases_then_fights():
    world = World(seed=3, teams=2, trees=CALM)
    a, b = pair(world, "carrot", "cabbage", gap=5)
    a.bb["foe"] = b.id
    ctx = bt.Context(world, a, world.teams[0], "unit", path="t")
    hp = b.hp
    for _ in range(80):
        assert bt.NODES["attack"].fn(ctx, key="foe") == bt.RUNNING
        a.move_requested and world._move(a, world._grant_steps())
        a.move_requested = False
        world._land_hits()
        world.tick += 1
        if b.hp < hp:
            break
    assert b.hp == hp - data.ATTACK["carrot"]["damage"] * 2  # carrots beat cabbages
    assert world.in_battle(a) and world.in_battle(b)


def test_scarecrow_crow_strikes_enemies_in_reach():
    world = World(seed=3, teams=2, trees=CALM)
    team = world.teams[0]
    x, y = world.find_site(team, "scarecrow", team.spawn)
    crow = world.place_building(team, "scarecrow", x, y)
    foe = next(u for u in world.units if u.team == 1)
    spot = world.nearest_walkable(x + 2, y + 2, need_free=True)
    place(world, foe, spot)
    world._scarecrows()
    assert not world._hits  # not grown yet
    crow.progress = crow.work
    world._scarecrows()
    world._land_hits()
    assert foe.hp == data.UNIT_HP[foe.kind] - data.SCARECROW["damage"]


def test_losing_the_greenhouse_knocks_a_team_out_and_decides_the_game():
    world = World(seed=3, teams=2, trees=CALM)
    red_gh = next(b for b in world.buildings if b.team == 1 and b.kind == "greenhouse")
    red_units = [u for u in world.units if u.team == 1]
    red_gh.hp = 0
    world._hits.append((red_gh, 0))
    world._land_hits()
    assert not world.teams[1].alive and world.winner == 0
    assert not any(u.team == 1 for u in world.units) and not any(b.team == 1 for b in world.buildings)
    assert sum(1 for t in world.things if t.kind.startswith("remains")) == len(red_units)
    world.step()  # the game keeps running; the beaten planner doesn't
    assert world.winner == 0


def test_both_greenhouses_falling_together_is_a_draw():
    world = World(seed=3, teams=2, trees=CALM)
    for b in world.buildings:
        if b.kind == "greenhouse":
            b.hp = 0
    world._land_hits()
    assert world.winner == -1


def test_units_never_rest_on_a_tile_edge():
    world = World(seed=1, teams=2)
    for _ in range(3300):
        world.step()
        for u in world.units:
            assert u.x % data.TILE and u.y % data.TILE, (world.tick, u.kind, u.x, u.y)


def test_mirrored_armies_fight_as_exact_mirrors():
    world = World(seed=1, teams=2)
    size = world.width * data.TILE
    deaths = 0
    while world.tick < 3600:
        before = {u.id for u in world.units}
        world.step()
        deaths += len(before - {u.id for u in world.units})
        blue = [u for u in world.units if u.team == 0]
        red = [u for u in world.units if u.team == 1]
        assert [u.kind for u in blue] == [u.kind for u in red], world.tick
        for b, r in zip(blue, red):
            assert (size - b.x, size - b.y, b.hp) == (r.x, r.y, r.hp), (world.tick, b.kind)
    assert deaths >= 2  # there really was fighting


def test_reactive_selector_lets_an_earlier_branch_take_over():
    tree = {"name": "t", "scope": "unit", "root": {"type": "reactive_selector", "children": [
        {"type": "sequence", "children": [{"type": "condition", "name": "has_key", "args": {"key": "alarm"}},
                                          {"type": "action", "name": "wait", "args": {"ticks": 50}}]},
        {"type": "action", "name": "wait", "args": {"ticks": 50}},
    ]}}
    assert bt.validate(tree) == []
    world = World(seed=3, teams=2, trees=CALM)
    u = world.units[0]
    u.bb.clear()
    u.bt_state.clear()
    ctx = bt.Context(world, u, world.teams[0], "unit")
    assert bt.run(tree, ctx) == bt.RUNNING and "r/1" in u.bt_state  # the second branch is waiting
    u.bb["alarm"] = 1
    assert bt.run(tree, ctx) == bt.RUNNING
    assert "r/1" not in u.bt_state and "r/0/1" in u.bt_state  # the old wait was stopped, the first branch runs
    plain = dict(tree, root=dict(tree["root"], type="selector"))
    u.bb.clear()
    u.bt_state.clear()
    bt.run(plain, ctx)
    u.bb["alarm"] = 1
    bt.run(plain, ctx)
    assert "r/1" in u.bt_state  # a plain selector keeps going with the running child


def test_contested_tiles_go_to_the_nearer_unit_and_enemies_level_with_each_other_both_wait():
    world = World(seed=3, teams=2, trees=CALM)
    a, b = pair(world, "cabbage", "cabbage", gap=2)
    (ax, ay), (bx, by) = world.tile_of(a), world.tile_of(b)
    middle = [ax + 1, ay]
    a.path, b.path = [list(middle)], [list(middle)]
    assert world._grant_steps() == set()  # exactly as near: neither goes, whichever army runs first
    a.x += 10  # blue is now a little nearer
    assert world._grant_steps() == {a.id}
