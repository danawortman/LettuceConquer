"""Drawing the world: ground, lakes, standing things in depth order, the HUD and the tree inspector."""
from __future__ import annotations

import random
from dataclasses import dataclass

import pygame

from lettuce_conquer import art, fieldart
from lettuce_conquer.terrain import DECAL_FRAME, piece_for
from lettuce_conquer.sim import bt
from lettuce_conquer.sim.data import BUILDING_HP, CHANNEL_WORK, TILE, UNIT_HP
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

    for thing in world.things:
        if thing.kind == "lake":
            screen.blit(art.terrain_surface("lake", z), (thing.x * ts - ox, thing.y * ts - oy))
    draw_channels(screen, world, cam)

    standing = []  # (ground y, ground x, id, draw)
    for thing in world.things:
        if thing.kind == "lake":
            continue
        if thing.kind in NEUTRAL_BUILDINGS:
            gx, gy = (thing.x + thing.w / 2) * TILE, (thing.y + thing.h) * TILE
            flip = thing.kind == "watering_can" and world.flips_at(thing)[0] < 0  # spout toward the middle
            standing.append((gy, gx, thing.id, lambda t=thing, g=(gx, gy), f=flip: art.blit_building(
                screen, t.kind, t.state, "blue", cam.to_screen(*g), z, f)))
        else:
            dx, dy, size = nudge(world, thing)
            gx, gy = (thing.x + 0.5) * TILE + dx, thing.y * TILE + TREE_GROUND_OFFSET + dy
            standing.append((gy, gx, thing.id, lambda t=thing, g=(gx, gy), s=size: art.blit_terrain_object(
                screen, f"{t.kind}_{t.state}", cam.to_screen(*g), z * s)))
    for b in world.buildings:
        gx, gy = (b.x + b.w / 2) * TILE, (b.y + b.h) * TILE
        color = world.teams[b.team].color
        flip = world.flips(world.teams[b.team])[0] < 0  # mirrored quarters get mirrored art (inlet side)
        look = "wilted" if b.state == "grown" and b.hp * 2 < BUILDING_HP[b.kind] else b.state  # badly damaged

        def draw_building(b=b, g=(gx, gy), c=color, f=flip, look=look):
            sx, sy = cam.to_screen(*g)
            art.blit_building(screen, b.kind, look, c, (sx, sy), z, f)
            if b.hp < BUILDING_HP[b.kind]:
                draw_health(screen, sx, sy - (b.h * 85 + 40) * z, b.w * 70 * z, b.hp / BUILDING_HP[b.kind], z)
        standing.append((gy, gx, b.id, draw_building))
        anchor = inlet_anchor(world, b)
        if anchor is not None:  # a sluice gate once grown, a water-drop sign before that
            stem = "inlet_sign" if b.state in ("planted", "sprout") else "inlet_gate"
            ax, ay, back = anchor
            key = b.y * TILE + 1 if back else ay + 1  # back gates draw behind the building, front ones in front
            standing.append((key, ax, b.id, lambda s=stem, a=(ax, ay), f=flip: art.blit_inlet(
                screen, s, cam.to_screen(*a), z, f)))
    for u in world.units:
        gx, gy = unit_position(u, alpha)
        color = world.teams[u.team].color

        def draw_unit(u=u, g=(gx, gy), c=color):
            sx, sy = cam.to_screen(*g)
            if u is selected:
                pygame.draw.ellipse(screen, (255, 250, 220), (sx - 46 * z, sy - 14 * z, 92 * z, 28 * z), max(2, round(4 * z)))
            art.blit_unit(screen, u.kind, "battle" if world.in_battle(u) else "idle", c, (sx, sy), z)
            if u.carry:
                draw_load(screen, u.carry_kind, sx + 34 * z, sy - 150 * z, z)
            if u.hp < UNIT_HP[u.kind]:
                draw_health(screen, sx, sy - 205 * z, 70 * z, u.hp / UNIT_HP[u.kind], z)
        standing.append((gy, gx, u.id, draw_unit))

    margin = 260
    for gy, gx, _, draw in sorted(standing, key=lambda s: s[:3]):
        sx, sy = cam.to_screen(gx, gy)
        if -margin < sx < sw + margin and -margin * 0.3 < sy < sh + margin * 1.6:
            draw()
    draw_shots(screen, world, cam, alpha)


PEA = (126, 190, 70)
SHOT_TICKS = 3  # a pea takes this long to fly


def draw_shots(screen, world: World, cam: Camera, alpha: float) -> None:
    """Peas in flight from Pea Shooters' latest shots (drawing only; the hit itself lands at once)."""
    z = cam.zoom
    for u in world.units:
        if u.kind != "pea" or not u.shot:
            continue
        tx, ty, tick = u.shot
        k = (world.tick - 1 - tick + alpha) / SHOT_TICKS
        if not 0 <= k <= 1:
            continue
        ux, uy = unit_position(u, alpha)
        x, y = cam.to_screen(ux + (tx - ux) * k, uy - 110 + (ty - 70 - (uy - 110)) * k)
        r = max(3, round(11 * z))
        pygame.draw.circle(screen, PEA, (round(x), round(y)), r)
        pygame.draw.circle(screen, INK, (round(x), round(y)), r, max(1, round(3 * z)))


def draw_health(screen, cx: float, y: float, width: float, frac: float, z: float) -> None:
    """A small health bar centred on cx: green, then yellow, then red as it empties."""
    w, h = max(16, round(width)), max(4, round(12 * z))
    rect = pygame.Rect(round(cx - w / 2), round(y), w, h)
    pygame.draw.rect(screen, (60, 45, 35), rect, border_radius=h // 2)
    frac = max(0.0, min(1.0, frac))
    color = (90, 180, 70) if frac > 0.5 else ((230, 180, 50) if frac > 0.25 else (210, 70, 55))
    if frac > 0:
        pygame.draw.rect(screen, color, (rect.x, rect.y, max(h, round(w * frac)), h), border_radius=h // 2)
    pygame.draw.rect(screen, INK, rect, max(1, round(2 * z)), border_radius=h // 2)


BACK_GATE_GAP = 6  # art units between a back-side gate and the top of the building's drawing


def inlet_anchor(world: World, b):
    """Where to draw a building's inlet gate or sign: (world x, world y, at the back?), or None. A front
    inlet stands on the edge its tile shares with the building. A back inlet (bases in the bottom half,
    facing the middle) is pulled forward to stand just behind the drawing, since beds are drawn low."""
    inlet = world.inlet_tile(b)
    if inlet is None:
        return None
    ax = (inlet[0] + 0.5) * TILE
    if inlet[1] >= b.y + b.h:
        return ax, inlet[1] * TILE, False
    ground = (b.y + b.h) * TILE
    return ax, max(b.y * TILE, ground + art.art_top(b.kind, b.state) - BACK_GATE_GAP), True


def draw_inlet_runs(screen, world: World, cam: Camera, wet: set) -> None:
    """For back inlets: the dug channel carries on from the inlet tile across the footprint's back tiles
    to the pulled-forward gate (the building's drawing covers the rest). Likewise a Watering Can whose
    outlet is behind it: the channel runs under the can to the puddle at its front."""
    z = cam.zoom
    for b in world.buildings:
        anchor = inlet_anchor(world, b)
        inlet = world.inlet_tile(b)
        ch = world.channels.get(inlet) if inlet is not None else None
        if anchor is None or not anchor[2] or ch is None or not ch.dug:
            continue
        piece = art.channel_surface("straight", "wet" if inlet in wet else "dry", 1, z)
        for row in range(b.y, b.y + b.h):
            if row * TILE >= anchor[1]:
                break
            sx, sy = cam.to_screen(inlet[0] * TILE, row * TILE)
            screen.blit(piece, (round(sx), round(sy)))
    for can in world.things:  # a can facing the middle from the back pours at the front: the channel runs under it
        if can.kind != "watering_can":
            continue
        out = world.outlet_tile(can)
        ch = world.channels.get(out)
        if out[1] >= can.y or ch is None or not ch.dug:
            continue
        piece = art.channel_surface("straight", "wet" if out in wet else "dry", 1, z)
        for row in range(can.y, can.y + can.h):
            sx, sy = cam.to_screen(out[0] * TILE, row * TILE)
            screen.blit(piece, (round(sx), round(sy)))


CHANNEL_SIDES = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}
STAKE = (122, 82, 40)


def channel_ends(world: World) -> dict:
    """Extra sides that dug channel tiles connect to: a building's inlet opens toward the building, and a
    Watering Can's outlet toward the can."""
    ends = {}
    for b in world.buildings:
        inlet = world.inlet_tile(b)
        if inlet is not None:
            ends.setdefault(inlet, set()).add("N" if inlet[1] >= b.y + b.h else "S")
    for c in world.things:
        if c.kind == "watering_can":
            out = world.outlet_tile(c)
            ends.setdefault(out, set()).add("N" if out[1] >= c.y + c.h else "S")
    return ends


def draw_channels(screen, world: World, cam: Camera) -> None:
    """Dug channels as joined pieces (wet when a can with water feeds them); planned tiles as stakes and string."""
    if not world.channels:
        return
    z = cam.zoom
    ts = round(TILE * z)
    sw, sh = screen.get_size()
    wet, ends = world.wet_channels(), channel_ends(world)
    draw_inlet_runs(screen, world, cam, wet)
    for (x, y), ch in world.channels.items():
        sx, sy = cam.to_screen(x * TILE, y * TILE)
        if not (-ts < sx < sw and -ts < sy < sh):
            continue
        sx, sy = round(sx), round(sy)
        if ch.dug:
            sides = "".join(d for d, (dx, dy) in CHANNEL_SIDES.items()
                            if (n := world.channels.get((x + dx, y + dy))) is not None and n.dug)
            sides += "".join(ends.get((x, y), ()))
            piece, turns = piece_for(sides)
            screen.blit(art.channel_surface(piece, "wet" if (x, y) in wet else "dry", turns, z), (sx, sy))
            continue
        # planned: four stakes with string between them, and a growing heap of dug earth
        m, r = round(26 * z), max(2, round(6 * z))
        corners = [(sx + m, sy + m), (sx + ts - m, sy + m), (sx + ts - m, sy + ts - m), (sx + m, sy + ts - m)]
        pygame.draw.lines(screen, (238, 226, 196), True, corners, max(1, round(3 * z)))
        if ch.progress:
            k = min(1.0, ch.progress / CHANNEL_WORK)
            rect = pygame.Rect(0, 0, round(70 * z * k) + 2, round(40 * z * k) + 2)
            rect.center = (sx + ts // 2, sy + ts // 2)
            pygame.draw.ellipse(screen, (107, 74, 43), rect)
            pygame.draw.ellipse(screen, INK, rect, max(1, round(2 * z)))
        for c in corners:
            pygame.draw.circle(screen, STAKE, c, r)
            pygame.draw.circle(screen, INK, c, r, max(1, round(2 * z)))


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


PANEL_WIDTH = 214
PANEL_MARGIN = 10
PANEL_FILL = (246, 239, 217, 175)   # semi-transparent: the map shows through
ROW_MAX, ROW_MIN = 30, 18           # row height; rows shrink when two panels share one side of the screen
UNIT_ICONS = ("spud", "cabbage", "pea", "carrot")
BUILDING_ICONS = ("greenhouse", "root_cellar", "cabbage_patch", "pea_trellis", "carrot_bed", "scarecrow")
SHORT_NAMES = {"scarecrow": "Scarecrow"}
HEADER_H, GAP = 30, 8
HELP = ("Arrows/WASD or right-drag: pan", "Wheel: zoom", "Space: pause", "[ ]: speed", "Click: inspect",
        "Tab: next unit", "F11: full screen", "Esc: quit")


def _rows() -> int:
    return len(UNIT_ICONS) + len(BUILDING_ICONS) + 4  # units, buildings and the four resources


def panel_layout(screen, world: World) -> tuple[dict, int]:
    """Each army's panel (in the corner of the screen matching its base's corner of the map) and the row height."""
    sw, sh = screen.get_size()
    corners = {t.id: world.flips(t) for t in world.teams}
    shared = any(c[1] > 0 for c in corners.values()) and any(c[1] < 0 for c in corners.values())
    fixed = HEADER_H + 2 * GAP + 10
    room = (sh - 3 * PANEL_MARGIN) // 2 if shared else sh - 2 * PANEL_MARGIN
    row = max(ROW_MIN, min(ROW_MAX, (room - fixed) // _rows()))
    h = fixed + row * _rows()
    rects = {}
    for tid, (sx, sy) in corners.items():
        x = PANEL_MARGIN if sx > 0 else sw - PANEL_WIDTH - PANEL_MARGIN
        y = PANEL_MARGIN if sy > 0 else sh - h - PANEL_MARGIN
        rects[tid] = pygame.Rect(x, y, PANEL_WIDTH, h)
    return rects, row


def panel_rects(screen, world: World) -> dict:
    return panel_layout(screen, world)[0]


def panel_at(screen, world: World, pos):
    """The team whose panel is under `pos`, if any."""
    for tid, rect in panel_rects(screen, world).items():
        if rect.collidepoint(pos):
            return world.teams[tid]
    return None


def _icon(surf, height: int):
    """Trim a sprite to its drawn pixels and scale it to `height`."""
    rect = surf.get_bounding_rect()
    part = surf.subsurface(rect)
    w = max(1, round(rect.width * height / max(1, rect.height)))
    return pygame.transform.smoothscale(part, (w, height))


_ICONS: dict = {}


def icon(kind: str, team: str, height: int):
    key = (kind, team, height)
    if key not in _ICONS:
        if kind in UNIT_HP:
            surf = art.unit_surface(kind, "idle", team, 0.4)
        else:
            surf = art.building_surface(kind, "grown", team, 0.3)
        _ICONS[key] = _icon(surf, height)
    return _ICONS[key]


def draw_army_panel(screen, font, world: World, team, rect, row: int) -> None:
    from lettuce_conquer.buildings import BUILDINGS
    from lettuce_conquer.units import UNITS
    color = pygame.Color(art.TEAM_COLORS[team.color])
    panel = pygame.Surface(rect.size, pygame.SRCALPHA)
    panel.fill(PANEL_FILL)
    pygame.draw.rect(panel, (*color[:3], 230), panel.get_rect(), 3, border_radius=10)
    pygame.draw.circle(panel, color, (18, 17), 8)
    pygame.draw.circle(panel, INK, (18, 17), 8, 2)
    panel.blit(font.render(f"{team.color.capitalize()} army", True, INK), (32, 10))
    if not team.alive:
        panel.blit(font.render("out: Greenhouse", True, UNVISITED), (14, HEADER_H + 8))
        panel.blit(font.render("destroyed", True, UNVISITED), (14, HEADER_H + 26))
        screen.blit(panel, rect)
        return
    units = [u for u in world.units if u.team == team.id]
    growing = [b.sprout_kind for b in world.buildings if b.team == team.id and b.sprout_kind]
    mine = [b for b in world.buildings if b.team == team.id]
    pic_h = row - 4
    text_y = (row - font.get_height()) // 2

    def line(y, pic, name, count, extra, faded=False):
        """One row: the art (or a resource dot), the name, and the count on the right."""
        if pic is None:
            return
        if isinstance(pic, tuple):  # a resource colour
            r = max(5, row // 4)
            pygame.draw.circle(panel, pic, (12 + 18, y + row // 2), r)
            pygame.draw.circle(panel, INK, (12 + 18, y + row // 2), r, 1)
        else:
            panel.blit(pic, (12 + 18 - pic.get_width() // 2, y + 2))
        ink = UNVISITED if faded else INK
        panel.blit(font.render(name, True, ink), (60, y + text_y))
        label = font.render(str(count) + (f"+{extra}" if extra else ""), True, ink)
        panel.blit(label, (rect.width - 14 - label.get_width(), y + text_y))

    y = HEADER_H + 4
    for kind in UNIT_ICONS:  # units, with "+n" for ones still sprouting
        have = sum(1 for u in units if u.kind == kind)
        extra = sum(1 for k in growing if k == kind)
        line(y, icon(kind, team.color, pic_h), UNITS[kind].name, have, extra, faded=not (have or extra))
        y += row
    y += GAP
    for kind, amount in team.stock.items():  # resources
        line(y, RESOURCE_COLORS[kind], kind.capitalize(), amount, 0)
        y += row
    y += GAP
    for kind in BUILDING_ICONS:  # buildings grown, with "+n" for ones still growing
        done = sum(1 for b in mine if b.kind == kind and b.progress >= b.work)
        extra = sum(1 for b in mine if b.kind == kind and b.progress < b.work)
        name = SHORT_NAMES.get(kind, BUILDINGS[kind].name)
        line(y, icon(kind, team.color, pic_h), name, done, extra, faded=not (done or extra))
        y += row
    pygame.draw.line(panel, (*INK[:3], 60), (12, HEADER_H + 4 + row * 4 + GAP // 2),
                     (rect.width - 12, HEADER_H + 4 + row * 4 + GAP // 2))
    pygame.draw.line(panel, (*INK[:3], 60), (12, HEADER_H + 4 + row * 8 + GAP + GAP // 2),
                     (rect.width - 12, HEADER_H + 4 + row * 8 + GAP + GAP // 2))
    screen.blit(panel, rect)


def _wrap(font, items, width: int) -> list:
    """Join `items` into as few centred lines as fit in `width`."""
    lines, line = [], ""
    for item in items:
        trial = item if not line else line + "    " + item
        if line and font.size(trial)[0] > width:
            lines.append(line)
            line = item
        else:
            line = trial
    return lines + ([line] if line else [])


def draw_hud(screen, font, world: World, speed: int, paused: bool) -> None:
    sw, sh = screen.get_size()
    rects, row = panel_layout(screen, world)
    for team in world.teams:
        draw_army_panel(screen, font, world, team, rects[team.id], row)
    side_room = sw - 2 * (PANEL_WIDTH + 2 * PANEL_MARGIN)  # between the left and right panel columns

    # the title line, top centre
    text = f"seed {world.seed}    tick {world.tick}    speed x{speed}{'    PAUSED' if paused else ''}"
    if font.size("Lettuce Conquer    " + text)[0] + 24 <= side_room:  # the title only when there's room
        text = "Lettuce Conquer    " + text
    label = font.render(text, True, INK)
    box = label.get_rect(midtop=(sw // 2, PANEL_MARGIN + 4)).inflate(24, 10)
    _pill(screen, box)
    screen.blit(label, label.get_rect(center=box.center))

    if world.winner is not None:
        draw_banner(screen, world)

    # the controls, bottom centre, wrapped to fit between the bottom panels
    lines = _wrap(font, HELP, max(200, side_room - 24))
    line_h = font.get_linesize()
    y = sh - PANEL_MARGIN - line_h * len(lines) - 8
    box = pygame.Rect(0, 0, max(font.size(t)[0] for t in lines) + 24, line_h * len(lines) + 8)
    box.midtop = (sw // 2, y - 4)
    _pill(screen, box)
    for i, text in enumerate(lines):
        label = font.render(text, True, INK)
        screen.blit(label, label.get_rect(midtop=(sw // 2, y + i * line_h)))


def _pill(screen, box) -> None:
    back = pygame.Surface(box.size, pygame.SRCALPHA)
    back.fill(PANEL_FILL)
    screen.blit(back, box)


def inspector_area(screen, world: World) -> pygame.Rect:
    """The open space for the tree inspector: between the left and right panel columns, below the title
    line and above the controls."""
    sw, sh = screen.get_size()
    left = PANEL_WIDTH + 2 * PANEL_MARGIN
    return pygame.Rect(left, 48, sw - 2 * left, sh - 48 - 100)


def draw_banner(screen, world: World) -> None:
    """The result, once the game is decided."""
    if world.winner < 0:
        text, color = "A draw! Every Greenhouse fell.", INK
    else:
        team = world.teams[world.winner]
        text, color = f"{team.color.capitalize()} wins!", pygame.Color(art.TEAM_COLORS[team.color])
    big = pygame.font.Font(None, 72)
    label = big.render(text, True, color)
    box = label.get_rect(center=(screen.get_width() // 2, screen.get_height() // 2)).inflate(60, 36)
    panel = pygame.Surface(box.size, pygame.SRCALPHA)
    panel.fill((246, 239, 217, 235))
    screen.blit(panel, box)
    pygame.draw.rect(screen, INK, box, 3, border_radius=10)
    screen.blit(label, label.get_rect(center=box.center))


def _node_text(node: dict) -> str:
    t = node["type"]
    if t in ("condition", "action"):
        args = ", ".join(f"{k}={v}" for k, v in node.get("args", {}).items())
        return f"{'?' if t == 'condition' else '!'} {node['name']}({args})"
    extra = f" x{node['times']}" if t == "repeat" and "times" in node else (f" {node['ticks']}t" if t == "cooldown" else "")
    return t + extra + (f"  - {node['label']}" if "label" in node else "")


def tree_lines(node: dict, path: str = "r", depth: int = 0, prefix: str = "", outer: tuple = ()):
    """(depth, paths, text) for every line, in display order. A decorator shares its child's line
    ("succeeder > sequence"); `paths` lists the line's nodes from the innermost out, so the line can show
    the innermost status that was reached this tick."""
    if "child" in node:
        yield from tree_lines(node["child"], path + "/0", depth, prefix + _node_text(node) + " > ", (path,) + outer)
        return
    yield depth, (path,) + outer, prefix + _node_text(node)
    for i, child in enumerate(node.get("children", ())):
        yield from tree_lines(child, f"{path}/{i}", depth + 1)


def draw_inspector(screen, font, small, world: World, agent) -> None:
    """A panel showing the agent's tree, each node colored by its status this tick, and its blackboard.
    Lines flow into more columns when they don't fit the screen's height."""
    tree = world.trees[agent.tree]
    is_team = not hasattr(agent, "kind")
    who = f"{agent.color} team planner" if is_team else f"{agent.kind} #{agent.id} ({world.teams[agent.team].color})"
    extra = {} if is_team else {"health": f"{agent.hp} / {UNIT_HP[agent.kind]}",
                                "carrying": f"{agent.carry} {agent.carry_kind}" if agent.carry else "nothing"}
    rows = []  # (indent, dot color or None, text, text color)
    for depth, paths, text in tree_lines(tree["root"]):
        status = next((agent.trace[p] for p in paths if p in agent.trace), None)
        color = STATUS_COLORS.get(status, UNVISITED)
        rows.append((depth, color, text, color if status else UNVISITED))
    rows.append((0, None, "", INK))
    rows.append((0, None, "blackboard", INK))
    rows += [(0, None, f"  {k} = {v}", INK) for k, v in agent.bb.items()]
    rows += [(0, None, f"{k}: {v}", INK) for k, v in extra.items()]

    area = inspector_area(screen, world)
    head, col_w, line_h = 60, 480, 18
    per_col = max(1, (area.height - head - 10) // line_h)
    cols = -(-len(rows) // per_col)
    per_col = -(-len(rows) // cols)  # balance the columns
    col_w = min(col_w, area.width // cols)  # long lines are clipped to fit
    width, height = col_w * cols, head + line_h * per_col + 10
    panel = pygame.Surface((width, height), pygame.SRCALPHA)
    panel.fill((246, 239, 217, 235))
    pygame.draw.rect(panel, INK, panel.get_rect(), 2)
    panel.blit(font.render(who, True, INK), (12, 10))
    panel.blit(small.render(f"tree: {tree.get('name', agent.tree)}", True, INK), (12, 34))
    for i, (depth, dot, text, color) in enumerate(rows):
        x, y = col_w * (i // per_col) + 12, head + line_h * (i % per_col)
        if dot is not None:
            pygame.draw.circle(panel, dot, (x + 6 + depth * 14, y + 8), 5)
            x += 16 + depth * 14
        panel.set_clip(pygame.Rect(col_w * (i // per_col), 0, col_w - 6, height))
        panel.blit(small.render(text, True, color), (x, y))
        panel.set_clip(None)
    screen.blit(panel, (area.right - width, area.top))
