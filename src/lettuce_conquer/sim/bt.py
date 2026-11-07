"""Behavior-tree engine.

Trees are plain JSON so they can be saved, diffed, validated and edited without code. A tree file is

    {"name": "...", "scope": "unit" | "team", "description": "...", "root": <node>}

and a node is one of

    {"type": "sequence" | "selector", "children": [<node>, ...]}
    {"type": "reactive_sequence" | "reactive_selector", "children": [<node>, ...]}
    {"type": "inverter" | "succeeder", "child": <node>}
    {"type": "repeat", "child": <node>, "times": 3}        # "times" optional: forever
    {"type": "cooldown", "child": <node>, "ticks": 50}
    {"type": "condition" | "action", "name": "<library node>", "args": {...}}

Any node may also carry a "label" for display. Leaves come from the node library (see nodes.py);
`node_catalog()` describes it as data for editors.

Ticking returns "success", "failure" or "running". Sequences and selectors remember a running child
and resume it next tick. Reactive ones start from their first child every tick instead, so an earlier
child (say, "an enemy is near") can take over from a running later one, which is then stopped. Each agent (unit or team) keeps its own running memory (`bt_state`) and
blackboard (`bb`), so many agents can share one tree.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

SUCCESS, FAILURE, RUNNING = "success", "failure", "running"
COMPOSITES = ("sequence", "selector", "reactive_sequence", "reactive_selector")
DECORATORS = {"inverter": {}, "succeeder": {}, "repeat": {"times": False}, "cooldown": {"ticks": True}}  # param: required?
LEAVES = ("condition", "action")
SCOPES = ("unit", "team")


@dataclass(frozen=True)
class Arg:
    type: str                 # "int" or "str"
    default: Any = None       # None means required
    doc: str = ""


@dataclass(frozen=True)
class NodeSpec:
    name: str
    kind: str                 # "condition" or "action"
    scope: str                # "unit", "team" or "any"
    doc: str
    args: dict
    fn: Callable


NODES: dict[str, NodeSpec] = {}


def node(kind: str, scope: str, doc: str, /, **args: Arg):
    """Register a library node. The function receives the context and its args as keywords."""
    def register(fn):
        NODES[fn.__name__] = NodeSpec(fn.__name__, kind, scope, doc, args, fn)
        return fn
    return register


@dataclass
class Context:
    world: Any
    agent: Any       # the Unit or Team running the tree
    team: Any        # the agent's team (the team itself for planners)
    scope: str
    path: str = ""   # the leaf being ticked; leaves use it to keep their own memory in `state`

    @property
    def bb(self) -> dict:
        return self.agent.bb

    @property
    def state(self) -> dict:
        return self.agent.bt_state


def run(tree: dict, ctx: Context) -> str:
    """Tick the tree once for ctx.agent. Records each visited node's status in agent.trace."""
    ctx.agent.trace = {}
    return _tick(tree["root"], "r", ctx)


def _tick(node: dict, path: str, ctx: Context) -> str:
    t = node["type"]
    state = ctx.state
    if t in COMPOSITES:
        is_sequence = t.endswith("sequence")
        reactive = t.startswith("reactive")
        stop = FAILURE if is_sequence else SUCCESS
        status = SUCCESS if is_sequence else FAILURE
        was = state.get(path)
        i = 0 if reactive else (was or 0)
        children = node["children"]
        while i < len(children):
            s = _tick(children[i], f"{path}/{i}", ctx)
            if s == RUNNING:
                if reactive and was is not None and was != i:  # another child took over: stop the old one
                    state.pop(f"{path}/{was}", None)
                    _forget(state, f"{path}/{was}/")
                state[path] = i
                status = RUNNING
                break
            if s == stop:
                status = stop
                break
            i += 1
    elif t == "inverter":
        s = _tick(node["child"], path + "/0", ctx)
        status = {SUCCESS: FAILURE, FAILURE: SUCCESS}.get(s, s)
    elif t == "succeeder":
        status = RUNNING if _tick(node["child"], path + "/0", ctx) == RUNNING else SUCCESS
    elif t == "repeat":
        s = _tick(node["child"], path + "/0", ctx)
        if s in (RUNNING, FAILURE):
            status = s
        else:
            done = state.get(path, 0) + 1
            times = node.get("times")
            if times is not None and done >= times:
                status = SUCCESS
            else:  # go again: count it, and let the child start fresh next tick
                state[path] = done
                _forget(state, path + "/")
                status = RUNNING
    elif t == "cooldown":
        key = "cooldown:" + path  # survives the subtree being reset
        if ctx.world.tick < state.get(key, 0):
            status = FAILURE
        else:
            status = _tick(node["child"], path + "/0", ctx)
            if status != RUNNING:
                state[key] = ctx.world.tick + node["ticks"]
    else:
        spec = NODES[node["name"]]
        args = {name: arg.default for name, arg in spec.args.items()}
        args.update(node.get("args", {}))
        ctx.path = path
        status = spec.fn(ctx, **args)
    ctx.agent.trace[path] = status
    if status != RUNNING:  # finished: the next visit starts this subtree from scratch
        state.pop(path, None)
        _forget(state, path + "/")
    return status


def _forget(state: dict, prefix: str) -> None:
    for key in [k for k in state if k.startswith(prefix)]:
        del state[key]


# ---------------------------------------------------------------- validation and catalog
def validate(tree: Any) -> list[str]:
    """Problems with a tree file, as readable messages (empty when the tree is fine)."""
    if not isinstance(tree, dict) or not isinstance(tree.get("root"), dict):
        return ["a tree must be an object with a 'root' node"]
    scope = tree.get("scope", "unit")
    errors = [] if scope in SCOPES else [f"scope must be one of {SCOPES}, not {scope!r}"]
    _validate(tree["root"], "root", scope, errors)
    return errors


def _validate(node: Any, where: str, scope: str, errors: list[str]) -> None:
    if not isinstance(node, dict):
        errors.append(f"{where}: a node must be an object")
        return
    t = node.get("type")
    if t in COMPOSITES:
        children = node.get("children")
        if not isinstance(children, list) or not children:
            errors.append(f"{where}: a {t} needs a non-empty 'children' list")
            return
        for i, child in enumerate(children):
            _validate(child, f"{where}/{i}", scope, errors)
    elif t in DECORATORS:
        for param, required in DECORATORS[t].items():
            value = node.get(param)
            if value is None and required:
                errors.append(f"{where}: a {t} needs '{param}'")
            elif value is not None and (not _is_int(value) or value < 1):
                errors.append(f"{where}: '{param}' must be a whole number of at least 1")
        if "child" not in node:
            errors.append(f"{where}: a {t} needs a 'child'")
        else:
            _validate(node["child"], f"{where}/0", scope, errors)
    elif t in LEAVES:
        name = node.get("name")
        spec = NODES.get(name)
        if spec is None:
            errors.append(f"{where}: unknown {t} {name!r}")
            return
        if spec.kind != t:
            errors.append(f"{where}: {name!r} is a {spec.kind}, not a {t}")
        if spec.scope not in (scope, "any"):
            errors.append(f"{where}: {name!r} only works in {spec.scope} trees")
        args = node.get("args", {})
        if not isinstance(args, dict):
            errors.append(f"{where}: 'args' must be an object")
            return
        for arg_name in args:
            if arg_name not in spec.args:
                errors.append(f"{where}: {name!r} has no argument {arg_name!r}")
        for arg_name, arg in spec.args.items():
            if arg_name not in args:
                if arg.default is None:
                    errors.append(f"{where}: {name!r} needs argument {arg_name!r}")
                continue
            ok = _is_int(args[arg_name]) if arg.type == "int" else isinstance(args[arg_name], str)
            if not ok:
                errors.append(f"{where}: {name!r} argument {arg_name!r} must be {arg.type}")
    else:
        errors.append(f"{where}: unknown node type {t!r}")


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def node_catalog() -> dict:
    """Everything an editor needs to offer and check nodes, as JSON-ready data."""
    return {
        "composites": list(COMPOSITES),
        "decorators": {name: {p: ("required" if req else "optional") for p, req in params.items()}
                       for name, params in DECORATORS.items()},
        "leaves": [{"name": s.name, "kind": s.kind, "scope": s.scope, "doc": s.doc,
                    "args": {n: {"type": a.type, "default": a.default, "doc": a.doc} for n, a in s.args.items()}}
                   for s in sorted(NODES.values(), key=lambda s: s.name)],
    }
