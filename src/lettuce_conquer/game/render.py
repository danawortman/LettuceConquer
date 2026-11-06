"""Drawing the world: ground, lakes, standing things in depth order, the HUD and the tree inspector."""
from __future__ import annotations

from dataclasses import dataclass

import pygame

from lettuce_conquer import art
from lettuce_conquer.sim import bt
from lettuce_conquer.sim.data import TILE
from lettuce_conquer.sim.world import World

INK = (43, 33, 24)
PAPER = (246, 239, 217)
STATUS_COLORS = {bt.SUCCESS: (70, 150, 60), bt.FAILURE: (200, 70, 60), bt.RUNNING: (215, 150, 20)}
UNVISITED = (150, 140, 120)
TREE_GROUND_OFFSET = 104  # standing objects sit near the bottom of their tile
NEUTRAL_BUILDINGS = ("compost_heap", "watering_can")
ZOOM_STEPS = tuple(round(0.25 + 0.05 * i, 2) for i in range(16))  # 0.25 .. 1.0; tile sizes stay whole pixels


@dataclass
class Camera:
    x: float     # world position of the screen's top-left corner
    y: float
    zoom: float

    def to_screen(self, wx: float, wy: float) -> tuple[float, float]:
        return (wx - self.x) * self.zoom, (wy - self.y) * self.zoom

    def to_world(self, sx: float, sy: float) -> tuple[float, float]:
        return sx / self.zoom + self.x, sy / self.zoom + self.y

    def center_on(self, wx: float, wy: float, screen: pygame.Surface) -> None:
        w, h = screen.get_size()
        self.x, self.y = wx - w / 2 / self.zoom, wy - h / 2 / self.zoom

    def clamp(self, world_w: int, world_h: int, screen: pygame.Surface) -> None:
        """Keep the view on the map (centered on it when the whole map fits on screen)."""
        view_w, view_h = (n / self.zoom for n in screen.get_size())
        self.x = (world_w - view_w) / 2 if view_w >= world_w else min(max(self.x, 0), world_w - view_w)
        self.y = (world_h - view_h) / 2 if view_h >= world_h else min(max(self.y, 0), world_h - view_h)


def unit_position(unit, alpha: float) -> tuple[float, float]:
    """Where to draw a unit between the last two ticks (alpha 0..1), so movement looks smooth."""
    return unit.prev_x + (unit.x - unit.prev_x) * alpha, unit.prev_y + (unit.y - unit.prev_y) * alpha


def draw_world(screen: pygame.Surface, world: World, cam: Camera, alpha: float = 1.0, selected=None) -> None:
    screen.fill(PAPER)
    z = cam.zoom
    ts = round(TILE * z)
    ox, oy = round(cam.x * z), round(cam.y * z)
    sw, sh = screen.get_size()
    x0, y0 = max(0, int(cam.x // TILE)), max(0, int(cam.y // TILE))
    x1, y1 = min(world.width, int((cam.x + sw / z) // TILE) + 1), min(world.height, int((cam.y + sh / z) // TILE) + 1)
    tiles = {"g": art.terrain_surface("grass", z), "f": art.terrain_surface("field", z)}
    for ty in range(y0, y1):
        row = world.tiles[ty]
        for tx in range(x0, x1):
            screen.blit(tiles[row[tx]], (tx * ts - ox, ty * ts - oy))

    standing = []  # (ground y, ground x, id, draw)
    for thing in world.things:
        if thing.kind == "lake":
            screen.blit(art.terrain_surface("lake", z), (thing.x * ts - ox, thing.y * ts - oy))
        elif thing.kind in NEUTRAL_BUILDINGS:
            gx, gy = (thing.x + thing.w / 2) * TILE, (thing.y + thing.h) * TILE
            standing.append((gy, gx, thing.id, lambda t=thing, g=(gx, gy): art.blit_building(
                screen, t.kind, t.state, "blue", cam.to_screen(*g), z)))
        else:
            gx, gy = (thing.x + 0.5) * TILE, thing.y * TILE + TREE_GROUND_OFFSET
            standing.append((gy, gx, thing.id, lambda t=thing, g=(gx, gy): art.blit_terrain_object(
                screen, f"{t.kind}_{t.state}", cam.to_screen(*g), z)))
    for b in world.buildings:
        gx, gy = (b.x + b.w / 2) * TILE, (b.y + b.h) * TILE
        color = world.teams[b.team].color
        standing.append((gy, gx, b.id, lambda b=b, g=(gx, gy), c=color: art.blit_building(
            screen, b.kind, b.state, c, cam.to_screen(*g), z)))
    for u in world.units:
        gx, gy = unit_position(u, alpha)
        color = world.teams[u.team].color

        def draw_unit(u=u, g=(gx, gy), c=color):
            sx, sy = cam.to_screen(*g)
            if u is selected:
                pygame.draw.ellipse(screen, (255, 250, 220), (sx - 46 * z, sy - 14 * z, 92 * z, 28 * z), max(2, round(4 * z)))
            art.blit_unit(screen, u.kind, "idle", c, (sx, sy), z)
        standing.append((gy, gx, u.id, draw_unit))

    margin = 260
    for gy, gx, _, draw in sorted(standing, key=lambda s: s[:3]):
        sx, sy = cam.to_screen(gx, gy)
        if -margin < sx < sw + margin and -margin * 0.3 < sy < sh + margin * 1.6:
            draw()


def pick(world: World, cam: Camera, pos, alpha: float = 1.0):
    """What's under the mouse: a unit, or a team (by clicking its Greenhouse). None if nothing."""
    mx, my = pos
    z = cam.zoom
    for u in sorted(world.units, key=lambda u: (unit_position(u, alpha)[1], u.id), reverse=True):
        sx, sy = cam.to_screen(*unit_position(u, alpha))
        if abs(mx - sx) < 50 * z and sy - 150 * z < my < sy + 10 * z:
            return u
    wx, wy = cam.to_world(mx, my)
    for b in world.buildings:
        if b.x * TILE <= wx < (b.x + b.w) * TILE and (b.y - 1) * TILE <= wy < (b.y + b.h) * TILE:
            return world.teams[b.team]
    return None


def draw_hud(screen, font, world: World, speed: int, paused: bool) -> None:
    w = screen.get_width()
    bar = pygame.Surface((w, 34), pygame.SRCALPHA)
    bar.fill((246, 239, 217, 225))
    screen.blit(bar, (0, 0))
    teams = "  ".join(t.color for t in world.teams)
    text = (f"Lettuce Conquer   seed {world.seed}   tick {world.tick}   speed x{speed}{'   PAUSED' if paused else ''}"
            f"   teams: {teams}")
    screen.blit(font.render(text, True, INK), (10, 8))
    help_text = "Arrows/WASD or right-drag: pan   Wheel: zoom   Space: pause   [ ]: speed   Click: inspect   Tab: next unit   Esc: quit"
    hint = font.render(help_text, True, INK)
    back = pygame.Surface((hint.get_width() + 16, 26), pygame.SRCALPHA)
    back.fill((246, 239, 217, 225))
    screen.blit(back, (0, screen.get_height() - 26))
    screen.blit(hint, (8, screen.get_height() - 22))


def tree_lines(node: dict, path: str = "r", depth: int = 0):
    """(depth, path, text) for every node, in display order."""
    t = node["type"]
    if t in ("condition", "action"):
        args = ", ".join(f"{k}={v}" for k, v in node.get("args", {}).items())
        text = f"{'?' if t == 'condition' else '!'} {node['name']}({args})"
    else:
        extra = f" x{node['times']}" if t == "repeat" and "times" in node else (f" {node['ticks']}t" if t == "cooldown" else "")
        text = t + extra + (f"  - {node['label']}" if "label" in node else "")
    yield depth, path, text
    if "children" in node:
        for i, child in enumerate(node["children"]):
            yield from tree_lines(child, f"{path}/{i}", depth + 1)
    elif "child" in node:
        yield from tree_lines(node["child"], path + "/0", depth + 1)


def draw_inspector(screen, font, small, world: World, agent) -> None:
    """A panel showing the agent's tree, each node colored by its status this tick, and its blackboard."""
    tree = world.trees[agent.tree]
    is_team = not hasattr(agent, "kind")
    who = f"{agent.color} team planner" if is_team else f"{agent.kind} #{agent.id} ({world.teams[agent.team].color})"
    lines = list(tree_lines(tree["root"]))
    width, line_h = 430, 20
    height = 86 + line_h * (len(lines) + 2 + len(agent.bb))
    panel = pygame.Surface((width, height), pygame.SRCALPHA)
    panel.fill((246, 239, 217, 235))
    pygame.draw.rect(panel, INK, panel.get_rect(), 2)
    panel.blit(font.render(who, True, INK), (12, 10))
    panel.blit(small.render(f"tree: {tree.get('name', agent.tree)}", True, INK), (12, 34))
    y = 60
    for depth, path, text in lines:
        status = agent.trace.get(path)
        color = STATUS_COLORS.get(status, UNVISITED)
        pygame.draw.circle(panel, color, (18 + depth * 16, y + 8), 5)
        panel.blit(small.render(text, True, color if status else UNVISITED), (28 + depth * 16, y))
        y += line_h
    y += 8
    panel.blit(small.render("blackboard", True, INK), (12, y))
    y += line_h
    for key, value in agent.bb.items():
        panel.blit(small.render(f"  {key} = {value}", True, INK), (12, y))
        y += line_h
    screen.blit(panel, (screen.get_width() - width - 10, 44))
