from lettuce_conquer.sim import data
from lettuce_conquer.sim.world import Building, World


def first(world, kind):
    return next(t for t in world.things if t.kind == kind)


def test_spuds_gather_all_three_resources():
    world = World(seed=7, teams=2)
    for _ in range(1500):
        world.step()
    for team in world.teams:
        assert team.stock["compost"] > 0 and team.stock["lumber"] > 0 and team.stock["stone"] > 0
        assert team.stock["water"] == 0  # water comes with irrigation, not gathering


def test_mirrored_two_army_game_stays_even():
    world = World(seed=3, teams=2)
    for _ in range(1500):
        world.step()
    blue, red = world.teams
    assert blue.stock == red.stock


def test_units_never_share_a_tile():
    world = World(seed=5, teams=4)
    for _ in range(800):
        world.step()
        tiles = [world.tile_of(u) for u in world.units]
        assert len(tiles) == len(set(tiles)), world.tick


def test_trees_turn_to_stumps_and_regrow():
    world = World(seed=2, demo_army=False)  # one Spud, on compost: nobody chops the tree again
    tree = first(world, "apple_tree")
    assert world.take(tree, 10) == 10 and tree.state == "half"
    assert world.take(tree, 999) == data.YIELDS["apple_tree"][1] - 10
    assert tree.state == "stump" and tree.amount == 0
    for _ in range(data.TREE_REGROW_TICKS):
        world.step()
    assert tree.state == "stump"  # regrows at the start of the next tick
    world.step()
    assert tree.state == "full" and tree.amount == tree.max_amount


def test_compost_heaps_shrink_through_their_frames_then_vanish():
    world = World(seed=2)
    heap = first(world, "compost_heap")
    full = heap.max_amount
    world.take(heap, full // 3)
    assert heap.state == "full"  # still above two-thirds
    world.take(heap, 1)
    assert heap.state == "half"
    world.take(heap, full // 3)
    assert heap.state == "low"
    tile = (heap.x, heap.y)
    world.take(heap, full)
    assert heap not in world.things and world.walkable(*tile)


def test_rocks_are_used_up_for_good():
    world = World(seed=2)
    rocks = first(world, "rocks_a")
    world.take(rocks, rocks.max_amount)
    for _ in range(data.TREE_REGROW_TICKS + 10):
        world.step()
    assert rocks not in world.things


def test_root_cellars_compound_the_delivery_bonus():
    world = World(seed=2)
    team = world.teams[0]
    assert world.deposit(team, "lumber", 100) == 100
    world.buildings.append(Building(900, team.id, "root_cellar", 0, 0, 2, 2))
    assert world.deposit(team, "lumber", 100) == 110
    world.buildings.append(Building(901, team.id, "root_cellar", 0, 0, 2, 2, state="sprout"))  # not grown: no bonus
    assert world.deposit(team, "lumber", 100) == 110
    world.buildings.append(Building(902, team.id, "root_cellar", 0, 0, 2, 2))
    assert world.deposit(team, "lumber", 100) == 121
    assert world.deposit(world.teams[1], "lumber", 100) == 100  # only your own cellars count


def test_planner_gives_each_spud_a_job():
    world = World(seed=4, teams=2)
    world.step()
    jobs = sorted(u.bb["job"] for u in world.units if u.kind == "spud" and u.team == 0)
    assert jobs == ["compost", "lumber", "stone"]
