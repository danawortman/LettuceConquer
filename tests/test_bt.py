import json

import pytest

from lettuce_conquer.sim import bt, trees
from lettuce_conquer.sim.bt import FAILURE, RUNNING, SUCCESS


class Agent:
    def __init__(self):
        self.bb, self.bt_state, self.trace = {}, {}, {}


class FakeWorld:
    tick = 0


def make(root, scope="unit"):
    tree = {"scope": scope, "root": root}
    assert bt.validate(tree) == []
    return tree


def leaf(name, **args):
    kind = "condition" if name == "has_key" else "action"
    return {"type": kind, "name": name, "args": args} if args else {"type": kind, "name": name}


def tick(tree, agent, world):
    status = bt.run(tree, bt.Context(world, agent, agent, tree["scope"]))
    world.tick += 1
    return status


def test_sequence_stops_at_the_first_failure():
    tree = make({"type": "sequence", "children": [leaf("succeed"), leaf("fail"), leaf("set_key", key="x", value=1)]})
    agent = Agent()
    assert tick(tree, agent, FakeWorld()) == FAILURE
    assert "x" not in agent.bb


def test_selector_takes_the_first_success():
    tree = make({"type": "selector", "children": [leaf("fail"), leaf("set_key", key="x", value=7), leaf("set_key", key="y")]})
    agent = Agent()
    assert tick(tree, agent, FakeWorld()) == SUCCESS
    assert agent.bb == {"x": 7}


def test_running_child_is_resumed_without_rerunning_earlier_siblings():
    tree = make({"type": "sequence", "children": [leaf("succeed"), leaf("wait", ticks=3), leaf("set_key", key="done", value=1)]})
    agent, world = Agent(), FakeWorld()
    assert tick(tree, agent, world) == RUNNING
    assert tick(tree, agent, world) == RUNNING
    assert "r/0" not in agent.trace  # resumed straight at the wait
    assert tick(tree, agent, world) == RUNNING
    assert tick(tree, agent, world) == SUCCESS
    assert agent.bb["done"] == 1
    assert agent.bt_state == {}  # finished trees leave no running memory behind


def test_inverter_and_succeeder():
    assert tick(make({"type": "inverter", "child": leaf("fail")}), Agent(), FakeWorld()) == SUCCESS
    assert tick(make({"type": "inverter", "child": leaf("succeed")}), Agent(), FakeWorld()) == FAILURE
    assert tick(make({"type": "succeeder", "child": leaf("fail")}), Agent(), FakeWorld()) == SUCCESS


def test_repeat_runs_its_child_the_given_number_of_times():
    tree = make({"type": "repeat", "times": 3, "child": leaf("succeed")})
    agent, world = Agent(), FakeWorld()
    assert [tick(tree, agent, world) for _ in range(3)] == [RUNNING, RUNNING, SUCCESS]


def test_repeat_stops_on_failure():
    assert tick(make({"type": "repeat", "child": leaf("fail")}), Agent(), FakeWorld()) == FAILURE


def test_cooldown_blocks_until_its_time_is_up():
    tree = make({"type": "cooldown", "ticks": 3, "child": leaf("succeed")})
    agent, world = Agent(), FakeWorld()
    assert [tick(tree, agent, world) for _ in range(5)] == [SUCCESS, FAILURE, FAILURE, SUCCESS, FAILURE]


@pytest.mark.parametrize("root,message", [
    ({"type": "dance"}, "unknown node type"),
    ({"type": "sequence", "children": []}, "non-empty"),
    ({"type": "action", "name": "teleport"}, "unknown action"),
    ({"type": "condition", "name": "wait"}, "is a action"),
    ({"type": "action", "name": "wait", "args": {"seconds": 3}}, "no argument 'seconds'"),
    ({"type": "action", "name": "wait", "args": {"ticks": "3"}}, "must be int"),
    ({"type": "action", "name": "move_to"}, None),  # all args have defaults
    ({"type": "action", "name": "set_key"}, "needs argument 'key'"),
    ({"type": "cooldown", "child": {"type": "action", "name": "succeed"}}, "needs 'ticks'"),
    ({"type": "action", "name": "choose_rally"}, "only works in team trees"),
])
def test_validation_messages(root, message):
    errors = bt.validate({"scope": "unit", "root": root})
    if message is None:
        assert errors == []
    else:
        assert any(message in e for e in errors), errors


def test_bundled_trees_are_valid():
    assert trees.names()
    for name in trees.names():
        trees.load(name)  # raises if invalid


def test_catalog_is_json_and_lists_every_node():
    catalog = json.loads(json.dumps(bt.node_catalog()))
    names = {leaf["name"] for leaf in catalog["leaves"]}
    assert {"move_to", "wait", "choose_rally", "copy_team_key", "pick_wander_spot"} <= names
    assert set(catalog["decorators"]) == {"inverter", "succeeder", "repeat", "cooldown"}
