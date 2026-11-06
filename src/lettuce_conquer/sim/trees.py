"""Loading behavior-tree files from lettuce_conquer/trees/."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from lettuce_conquer.sim import bt
from lettuce_conquer.sim import nodes  # noqa: F401  (registers the node library)

TREE_DIR = Path(__file__).resolve().parent.parent / "trees"


def names() -> list[str]:
    return sorted(p.stem for p in TREE_DIR.glob("*.json"))


@lru_cache(maxsize=None)
def load(name: str) -> dict:
    """A validated tree. Raises ValueError listing every problem if the file is invalid."""
    tree = json.loads((TREE_DIR / f"{name}.json").read_text(encoding="utf-8"))
    errors = bt.validate(tree)
    if errors:
        raise ValueError(f"tree {name!r} is invalid:\n  " + "\n  ".join(errors))
    return tree
