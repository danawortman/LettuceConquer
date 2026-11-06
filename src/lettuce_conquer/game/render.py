"""Drawing the world: ground, lakes, standing things in depth order, the HUD and the tree inspector."""
from __future__ import annotations

import random
from dataclasses import dataclass

import pygame

from lettuce_conquer import art, fieldart
from lettuce_conquer.terrain import DECAL_FRAME
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


CHUNK = 8  # tiles per side of a cached ground chunk
DECAL_WEIGHTS = (("tuft_a", 30), ("tuft_b", 18), ("clover", 10), ("daisies", 6), ("buttercups", 6),
                 ("light_patch", 7), ("dark_patch", 5))


class Ground:
    """The ground layer (grass, scattered decorations, tilled fields), drawn once per zoom into chunks.

    Decorations are placed at random positions, not on the grid, so the grass doesn't look tiled. They
    are display-only and use their own random stream, never the simulation's.
    """

    def __init__(self, world: World):
        rnd = random.Random(world.seed * 101 + 7)
        kinds = [k for k, w in DECAL_WEIGHTS for _ in range(w)]
        self.decals = []  # (name, world x, world y)
        for ty in range(world.height):
            for tx in range(world.width):
                if world.tiles[ty][tx] == "g":
                    for _ in range(rnd.choice((0, 1, 1, 2, 2, 3))):
                        self.decals.append((rnd.choice(kinds), tx * TILE + rnd.uniform(0, TILE), ty * TILE + rnd.uniform(0, TILE)))
        for t in world.things:  # pebbles scattered around rocks
            if t.kind.startswith("rocks"):
                for _ in range(2):
                    self.decals.append(("pebbles", (t.x + 0.5) * TILE + rnd.uniform(-90, 90), (t.y + 0.5) * TILE + rnd.uniform(-70, 90)))
        self.decals.sort(key=lambda d: ("patch" not in d[0], d[2]))  # soft patches underneath, then top to bottom
        self.fields = list(world.fields)
        self.seed = world.seed
        self.zoom = None
        self.chunks: dict = {}

    def chunk(self, cx: int, cy: int, z: float) -> pygame.Surface:
        if z != self.zoom:
            self.zoom, self.chunks = z, {}
        if (cx, cy) not in self.chunks:
            ts = round(TILE * z)
            surf = pygame.Surface((CHUNK * ts, CHUNK * ts))
            grass = art.terrain_surface("grass", z)
            for j in range(CHUNK):
                for i in range(CHUNK):
                    surf.blit(grass, (i * ts, j * ts))
            x0, y0 = cx * CHUNK * TILE, cy * CHUNK * TILE
            span = CHUNK * TILE
            dx0, dy0, dw, dh = DECAL_FRAME
            for name, wx, wy in self.decals:  # anything overlapping this chunk, so decals cross chunk edges cleanly
                if x0 + dx0 - dw < wx < x0 + span - dx0 and y0 + dy0 - dh < wy < y0 + span - dy0:
                    surf.blit(art.decal_surface(name, z), (round((wx - x0 + dx0) * z), round((wy - y0 + dy0) * z)))
            for i, (fx, fy, fw, fh) in enumerate(self.fields):
                px, py, pw, ph = (fx * TILE - fieldart.PAD, fy * TILE - fieldart.PAD,
                                  fw * TILE + 2 * fieldart.PAD, fh * TILE + 2 * fieldart.PAD)
                if px < x0 + span and px + pw > x0 and py < y0 + span and py + ph > y0:
                    plot = art.field_surface(fw, fh, self.seed * 13 + i, z)
                    surf.blit(plot, (round((px - x0) * z), round((py - y0) * z)))
            self.chunks[(cx, cy)] = surf
        return self.chunks[(cx, cy)]


def nudge(world: World, thing) -> tuple[int, int, float]:
    """A fixed, display-only offset and size for a tree or rock, so groves don't sit on the grid."""
    h = (thing.x * 73856093 ^ thing.y * 19349663 ^ world.seed * 83492791) & 0xFFFFFFFF
    dx, dy = h % 57 - 28, (h >> 8) % 31 - 22
    sizes = (0.88, 1.0, 1.1) if thing.kind.endswith("tree") else (0.85, 1.0, 1.08)
    return dx, dy, sizes[(h >> 16) % 3]


def draw_world(screen: pygame.Surface, world: World, cam: Camera, alpha: float = 1.0, selected=None) -> None:
    screen.fill(PAPER)
    z = cam.zoom
    ts = round(TILE * z)
    ox, oy = round(cam.x * z), round(cam.y * z)
    sw, sh = screen.get_size()
    ground = world.__dict__.get("_ground")  # display-only cache, kept on the world it draws
    if ground is None:
        ground = world.__dict__["_ground"] = Ground(world)
    span = CHUNK * ts
    for cy in range(max(0, oy // span), min(-(-world.height // CHUNK), (oy + sh) // span + 1)):
        for cx in range(max(0, ox // span), min(-(-world.width // CHUNK), (ox + sw) // span + 1)):
            screen.blit(ground.chunk(cx, cy, z), (cx * span - ox, cy * span - oy))

    standing = []  # (ground y, ground x, id, draw)
    for thing in world.things:
        if thing.kind == "lake":
            screen.blit(art.terrain_surface("lake", z), (thing.x * ts - ox, thing.y * ts - oy))
        elif thing.kind in NEUTRAL_BUILDINGS:
            gx, gy = (thing.x + thing.w / 2) * TILE, (thing.y + thing.h) * TILE
            standing.append((gy, gx, thing.id, lambda t=thing, g=(gx, gy): art.blit_building(
                screen, t.kind, t.state, "blue", cam.to_screen(*g), z)))
        else:
            dx, dy, size = nudge(world, thing)
            gx, gy = (thing.x + 0.5) * TILE + dx, thing.y * TILE + TREE_GROUND_OFFSET + dy
            standing.append((gy, gx, thing.id, lambda t=thing, g=(gx, gy), s=size: art.blit_terrain_object(
                screen, f"{t.kind}_{t.state}", cam.to_screen(*g), z * s)))
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
            if u.carry:
                draw_load(screen, u.carry_kind, sx + 34 * z, sy - 150 * z, z)
        standing.append((gy, gx, u.id, draw_unit))

    margin = 260
    for gy, gx, _, draw in sorted(standing, key=lambda s: s[:3]):
        sx, sy = cam.to_screen(gx, gy)
        if -margin < sx < sw + margin and -margin * 0.3 < sy < sh + margin * 1.6:
            draw()


RESOURCE_COLORS = {"compost": (107, 74, 43), "lumber": (176, 122, 69), "stone": (169, 163, 155), "water": (111, 195, 232)}


def draw_load(screen, kind: str, x: float, y: float, z: float) -> None:
    """A small token above a Spud's head showing what it carries."""
    r = max(4, round(16 * z))
    color = RESOURCE_COLORS.get(kind, INK)
    if kind == "lumber":  # a little log
        rect = pygame.Rect(0, 0, r * 3, r * 2)
        rect.center = (round(x), round(y))
        pygame.draw.rect(screen, color, rect, border_radius=r)
        pygame.draw.rect(screen, INK, rect, max(1, round(3 * z)), border_radius=r)
        pygame.draw.circle(screen, (217, 185, 138), (rect.right - r, rect.centery), max(2, r * 2 // 3))
    else:
        pygame.draw.circle(screen, color, (round(x), round(y)), r)
        pygame.draw.circle(screen, INK, (round(x), round(y)), r, max(1, round(3 * z)))


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
    bar = pygame.Surface((w, 34 + 22 * len(world.teams)), pygame.SRCALPHA)
    bar.fill((246, 239, 217, 225))
    screen.blit(bar, (0, 0))
    text = f"Lettuce Conquer   seed {world.seed}   tick {world.tick}   speed x{speed}{'   PAUSED' if paused else ''}"
    screen.blit(font.render(text, True, INK), (10, 8))
    for i, team in enumerate(world.teams):  # each team's stock
        y = 32 + 22 * i
        pygame.draw.circle(screen, pygame.Color(art.TEAM_COLORS[team.color]), (18, y + 8), 7)
        x = 34
        for kind, amount in team.stock.items():
            pygame.draw.circle(screen, RESOURCE_COLORS[kind], (x + 6, y + 8), 6)
            label = font.render(f"{kind} {amount}", True, INK)
            screen.blit(label, (x + 16, y))
            x += 30 + label.get_width()
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
    width, line_h = 470, 20
    extra = {} if is_team else {"carrying": f"{agent.carry} {agent.carry_kind}" if agent.carry else "nothing"}
    height = 86 + line_h * (len(lines) + 2 + len(agent.bb) + len(extra))
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
    for key, value in extra.items():
        panel.blit(small.render(f"{key}: {value}", True, INK), (12, y))
        y += line_h
    screen.blit(panel, (screen.get_width() - width - 10, 44 + 22 * len(world.teams)))
