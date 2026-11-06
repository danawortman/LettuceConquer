import json

import pytest

from lettuce_conquer.sim import mapgen
from lettuce_conquer.sim.pathfind import find_path
from lettuce_conquer.sim.rng import Rng, seed_state
from lettuce_conquer.sim.world import World


# ---------------------------------------------------------------- random numbers
def test_rng_is_repeatable_and_in_range():
    a, b = Rng(seed_state(42)), Rng(seed_state(42))
    rolls = [a.randint(3, 8) for _ in range(200)]
    assert rolls == [b.randint(3, 8) for _ in range(200)]
    assert set(rolls) == set(range(3, 9))


# ---------------------------------------------------------------- maps
@pytest.mark.parametrize("seed", [1, 2, 7, 99])
def test_map_is_mirrored_into_four_identical_quarters(seed):
    layout = mapgen.generate(seed)
    w, h = layout.width, layout.height
    for y in range(h):
        for x in range(w):
            assert layout.tiles[y][x] == layout.tiles[y][w - 1 - x] == layout.tiles[h - 1 - y][x]
    spots = {(f.kind, f.x, f.y, f.w, f.h) for f in layout.features}
    for kind, x, y, fw, fh in spots:
        assert (kind, w - x - fw, y, fw, fh) in spots
        assert (kind, x, h - y - fh, fw, fh) in spots


@pytest.mark.parametrize("seed", [1, 2, 7, 99])
def test_fields_are_mirrored_and_match_the_tiles(seed):
    layout = mapgen.generate(seed)
    w, h = layout.width, layout.height
    fields = set(layout.fields)
    for x, y, fw, fh in fields:
        assert (w - x - fw, y, fw, fh) in fields and (x, h - y - fh, fw, fh) in fields
        assert all(layout.tiles[y + j][x + i] == mapgen.FIELD for i in range(fw) for j in range(fh))


def test_groves_and_rock_clusters_are_clumped():
    layout = mapgen.generate(7)
    for kinds in (mapgen.TREE_KINDS, mapgen.ROCK_KINDS):
        spots = {(f.x, f.y) for f in layout.features if f.kind in kinds}
        lonely = [s for s in spots if not any((s[0] + dx, s[1] + dy) in spots for dx, dy in mapgen.NEIGHBORS)]
        assert len(spots) >= 8 and not lonely


def test_same_seed_same_map_different_seed_different_map():
    assert mapgen.generate(5) == mapgen.generate(5)
    assert mapgen.generate(5).features != mapgen.generate(6).features


def test_bases_sit_in_mirrored_corners():
    layout = mapgen.generate(3)
    spawns = [b["spawn"] for b in layout.bases]
    w, h = layout.width, layout.height
    assert spawns[1] == (w - 1 - spawns[0][0], spawns[0][1])
    assert spawns[3] == (w - 1 - spawns[0][0], h - 1 - spawns[0][1])


# ---------------------------------------------------------------- pathfinding
def open_grid(blocked=(), size=10):
    return lambda x, y: 0 <= x < size and 0 <= y < size and (x, y) not in blocked


def test_path_goes_straight_on_open_ground():
    assert find_path((0, 0), (3, 0), open_grid()) == [(0, 0), (1, 0), (2, 0), (3, 0)]


def test_path_goes_around_a_wall_without_cutting_corners():
    wall = {(2, y) for y in range(0, 8)}
    route = find_path((0, 0), (4, 0), open_grid(wall))
    assert route[0] == (0, 0) and route[-1] == (4, 0)
    assert not set(route) & wall
    blocked = open_grid(wall)
    for (ax, ay), (bx, by) in zip(route, route[1:]):
        if ax != bx and ay != by:
            assert blocked(bx, ay) and blocked(ax, by)


def test_unreachable_goal_has_no_path():
    box = {(5, 4), (5, 6), (4, 5), (6, 5), (4, 4), (6, 6), (4, 6), (6, 4)}
    assert find_path((0, 0), (5, 5), open_grid(box)) is None
    assert find_path((0, 0), (4, 4), open_grid(box)) is None  # goal itself blocked


# ---------------------------------------------------------------- the world
@pytest.mark.parametrize("teams", [2, 3, 4])
def test_same_seed_plays_out_identically(teams):
    a, b = World(seed=11, teams=teams), World(seed=11, teams=teams)
    for _ in range(300):
        a.step()
        b.step()
        if a.tick % 50 == 0:
            assert a.state_hash() == b.state_hash()


def test_different_seeds_play_out_differently():
    a, b = World(seed=1), World(seed=2)
    for _ in range(50):
        a.step()
        b.step()
    assert a.state_hash() != b.state_hash()


def test_state_is_plain_integers_and_text():
    world = World(seed=4, teams=4)
    for _ in range(120):
        world.step()

    def check(value):
        assert not isinstance(value, float), value
        if isinstance(value, dict):
            for v in value.values():
                check(v)
        elif isinstance(value, (list, tuple)):
            for v in value:
                check(v)
    check(json.loads(json.dumps(world.snapshot())))


def test_one_worker_rule_and_team_count():
    world = World(seed=2, teams=3, demo_army=False)
    assert [t.color for t in world.teams] == ["blue", "red", "purple"]
    assert sorted((u.team, u.kind) for u in world.units) == [(0, "spud"), (1, "spud"), (2, "spud")]
    assert len([b for b in world.buildings if b.kind == "greenhouse"]) == 3


def test_trees_move_units_and_planners_set_rally_points():
    world = World(seed=7, teams=4)
    start = {u.id: (u.x, u.y) for u in world.units}
    for _ in range(100):
        world.step()
    assert all((u.x, u.y) != start[u.id] for u in world.units)
    assert all("rally" in t.bb for t in world.teams)
    assert all(world.walkable(*t.bb["rally"]) for t in world.teams)


def test_units_never_stand_on_blocked_tiles():
    world = World(seed=9, teams=4)
    for _ in range(400):
        world.step()
        for u in world.units:
            assert world.walkable(*world.tile_of(u)), (u.kind, u.id, world.tile_of(u))
