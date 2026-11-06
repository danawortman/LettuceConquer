"""A* pathfinding on the tile grid: 8 directions, no cutting corners past blocked tiles.
Integer costs and an insertion counter for tie-breaks keep it deterministic."""
from __future__ import annotations

import heapq
from typing import Callable

STRAIGHT, DIAGONAL = 10, 14
STEPS = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))


def _octile(a, b):
    dx, dy = abs(a[0] - b[0]), abs(a[1] - b[1])
    return STRAIGHT * max(dx, dy) + (DIAGONAL - STRAIGHT) * min(dx, dy)


def find_path(start: tuple[int, int], goal: tuple[int, int],
              walkable: Callable[[int, int], bool], steps=STEPS) -> list[tuple[int, int]] | None:
    """Tiles from start to goal inclusive, or None if the goal can't be reached.
    `steps` sets the order neighbours are tried in, which decides ties between equally short routes;
    mirrored teams pass mirrored steps (World.steps_for) so they pick mirrored routes."""
    start, goal = tuple(start), tuple(goal)
    if not walkable(*goal):
        return None
    if start == goal:
        return [start]
    counter = 0
    frontier = [(_octile(start, goal), 0, counter, start)]
    came_from = {start: None}
    cost = {start: 0}
    while frontier:
        _, g, _, here = heapq.heappop(frontier)
        if here == goal:
            route = []
            while here is not None:
                route.append(here)
                here = came_from[here]
            return route[::-1]
        if g > cost[here]:
            continue
        x, y = here
        for dx, dy in steps:
            nxt = (x + dx, y + dy)
            if not walkable(*nxt):
                continue
            if dx and dy and not (walkable(x + dx, y) and walkable(x, y + dy)):
                continue  # no squeezing diagonally between two blocked tiles
            ng = g + (DIAGONAL if dx and dy else STRAIGHT)
            if ng < cost.get(nxt, 1 << 30):
                cost[nxt] = ng
                came_from[nxt] = here
                counter += 1
                heapq.heappush(frontier, (ng + _octile(nxt, goal), ng, counter, nxt))
    return None
