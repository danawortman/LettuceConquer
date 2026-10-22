"""Unit art: loads the per-unit SVGs, recolors them per team, and caches the rasterized result."""
from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path

import pygame

UNIT_DIR = Path(__file__).parent / "assets" / "units"
STATES = ("idle", "battle")

# Team-colored regions in every SVG are drawn in this key color and swapped at load time.
TEAM_KEY_COLOR = "#3a7bd5"
TEAM_COLORS = {"blue": "#3a7bd5", "red": "#d0453a"}

# Every unit SVG shares one frame (viewBox="-200 40 340 220") with the feet at (0, 248),
# so in frame pixels the feet are at (200, 208) for any unit.
FRAME_SIZE = (340, 220)
FEET_ANCHOR = (200, 208)


def svg_path(unit: str, state: str) -> Path:
    return UNIT_DIR / f"{unit}_{state}.svg"


@lru_cache(maxsize=None)
def svg_text(unit: str, state: str, team: str) -> str:
    """The unit's SVG source with the team key color replaced by the team's color."""
    text = svg_path(unit, state).read_text(encoding="utf-8")
    return text.replace(TEAM_KEY_COLOR, TEAM_COLORS[team])


@lru_cache(maxsize=256)
def _rasterize(unit: str, state: str, team: str, width: int, height: int) -> pygame.Surface:
    data = io.BytesIO(svg_text(unit, state, team).encode("utf-8"))
    return pygame.image.load_sized_svg(data, (width, height))


def unit_surface(unit: str, state: str, team: str, scale: float) -> pygame.Surface:
    """The unit rasterized at `scale` (1.0 = 340x220 frame). Rasterizing at the target size keeps
    edges crisp, unlike scaling a bitmap."""
    w, h = (max(1, round(n * scale)) for n in FRAME_SIZE)
    return _rasterize(unit, state, team, w, h)


def blit_unit(dest: pygame.Surface, unit: str, state: str, team: str,
              feet: tuple[float, float], scale: float) -> pygame.Rect:
    """Draw the unit so its feet land on `feet`. Returns the area drawn."""
    surf = unit_surface(unit, state, team, scale)
    top_left = (round(feet[0] - FEET_ANCHOR[0] * scale), round(feet[1] - FEET_ANCHOR[1] * scale))
    return dest.blit(surf, top_left)
