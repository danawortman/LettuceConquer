"""Unit and building art: loads the SVGs, recolors them per team, and caches the rasterized result."""
from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path

import pygame

from lettuce_conquer import fieldart
from lettuce_conquer.buildings import BUILDINGS, FRAMES
from lettuce_conquer.terrain import DECAL_FRAME, GROUND_TILES, LAKE_FOOTPRINT, OBJECT_FRAME

UNIT_DIR = Path(__file__).parent / "assets" / "units"
BUILDING_DIR = Path(__file__).parent / "assets" / "buildings"
TERRAIN_DIR = Path(__file__).parent / "assets" / "terrain"
STATES = ("idle", "battle")

# Team-colored regions in every SVG are drawn in this key color and swapped at load time.
TEAM_KEY_COLOR = "#3a7bd5"
TEAM_COLORS = {"blue": "#3a7bd5", "red": "#d0453a", "purple": "#8f5fc8", "yellow": "#e0b030"}

# Every unit SVG shares one frame (viewBox="-200 40 340 220") with the feet at (0, 248),
# so in frame pixels the feet are at (200, 208) for any unit.
FRAME_SIZE = (340, 220)
FEET_ANCHOR = (200, 208)


def svg_path(unit: str, state: str) -> Path:
    return UNIT_DIR / f"{unit}_{state}.svg"


def building_path(building: str, state: str) -> Path:
    return BUILDING_DIR / f"{building}_{state}.svg"


@lru_cache(maxsize=None)
def _team_source(path: Path, team: str) -> str:
    return path.read_text(encoding="utf-8").replace(TEAM_KEY_COLOR, TEAM_COLORS[team])


def svg_text(unit: str, state: str, team: str) -> str:
    """The unit's SVG source with the team key color replaced by the team's color."""
    return _team_source(svg_path(unit, state), team)


@lru_cache(maxsize=512)
def _rasterize(path: Path, team: str, width: int, height: int) -> pygame.Surface:
    data = io.BytesIO(_team_source(path, team).encode("utf-8"))
    return pygame.image.load_sized_svg(data, (width, height))


def unit_surface(unit: str, state: str, team: str, scale: float) -> pygame.Surface:
    """The unit rasterized at `scale` (1.0 = 340x220 frame). Rasterizing at the target size keeps
    edges crisp, unlike scaling a bitmap."""
    w, h = (max(1, round(n * scale)) for n in FRAME_SIZE)
    return _rasterize(svg_path(unit, state), team, w, h)


def blit_unit(dest: pygame.Surface, unit: str, state: str, team: str,
              feet: tuple[float, float], scale: float) -> pygame.Rect:
    """Draw the unit so its feet land on `feet`. Returns the area drawn."""
    surf = unit_surface(unit, state, team, scale)
    top_left = (round(feet[0] - FEET_ANCHOR[0] * scale), round(feet[1] - FEET_ANCHOR[1] * scale))
    return dest.blit(surf, top_left)


def building_surface(building: str, state: str, team: str, scale: float) -> pygame.Surface:
    """The building rasterized at `scale` (1.0 = 120 px per tile, the same scale as units).
    Neutral resources have no team colors, so `team` changes nothing for them."""
    _, _, fw, fh = FRAMES[BUILDINGS[building].footprint]
    w, h = max(1, round(fw * scale)), max(1, round(fh * scale))
    return _rasterize(building_path(building, state), team, w, h)


def blit_building(dest: pygame.Surface, building: str, state: str, team: str,
                  ground: tuple[float, float], scale: float) -> pygame.Rect:
    """Draw the building so its ground point lands on `ground`. Returns the area drawn."""
    fx, fy, _, _ = FRAMES[BUILDINGS[building].footprint]
    surf = building_surface(building, state, team, scale)
    return dest.blit(surf, (round(ground[0] + fx * scale), round(ground[1] + fy * scale)))


def terrain_surface(stem: str, scale: float) -> pygame.Surface:
    """A terrain file (tile, overlay, lake or standing object) rasterized at `scale`. Terrain is neutral."""
    if stem == "lake":
        fw, fh = (n * 120 for n in LAKE_FOOTPRINT)
    elif stem in GROUND_TILES or stem.startswith(("path_", "channel_")):
        fw, fh = 120, 120
    else:
        fw, fh = OBJECT_FRAME[2:]
    w, h = max(1, round(fw * scale)), max(1, round(fh * scale))
    return _rasterize(TERRAIN_DIR / f"{stem}.svg", "blue", w, h)


def decal_surface(name: str, scale: float) -> pygame.Surface:
    """A grass decoration (DECAL_FRAME, centered on its middle) rasterized at `scale`."""
    fw, fh = DECAL_FRAME[2:]
    return _rasterize(TERRAIN_DIR / f"decal_{name}.svg", "blue", max(1, round(fw * scale)), max(1, round(fh * scale)))


@lru_cache(maxsize=128)
def field_surface(w_tiles: int, h_tiles: int, seed: int, scale: float) -> pygame.Surface:
    """A freshly tilled plot for a w x h tile field. Its frame starts PAD units up and left of the field."""
    _, _, fw, fh = fieldart.frame(w_tiles, h_tiles)
    data = io.BytesIO(fieldart.field_svg(w_tiles, h_tiles, seed).encode("utf-8"))
    return pygame.image.load_sized_svg(data, (max(1, round(fw * scale)), max(1, round(fh * scale))))


def blit_terrain_object(dest: pygame.Surface, stem: str, ground: tuple[float, float], scale: float) -> pygame.Rect:
    """Draw a standing terrain object (tree, rocks, remains) so its ground point lands on `ground`."""
    fx, fy = OBJECT_FRAME[:2]
    surf = terrain_surface(stem, scale)
    return dest.blit(surf, (round(ground[0] + fx * scale), round(ground[1] + fy * scale)))
