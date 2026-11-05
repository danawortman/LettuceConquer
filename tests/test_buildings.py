import io
import re
from pathlib import Path

import pygame
import pytest

from lettuce_conquer import art
from lettuce_conquer.buildings import BUILDINGS, CATALOG, FRAMES
from lettuce_conquer.units import UNITS

BUILDING_DIR = Path(art.UNIT_DIR).parent / "buildings"
CASES = [(b.key, s) for b in CATALOG for s in b.states]


def _svg(key, state):
    return (BUILDING_DIR / f"{key}_{state}.svg").read_text(encoding="utf-8")


def _load(text):
    return pygame.image.load(io.BytesIO(text.encode("utf-8")), "x.svg")


def test_every_svg_belongs_to_a_catalog_state():
    on_disk = {p.stem for p in BUILDING_DIR.glob("*.svg")}
    assert on_disk == {f"{k}_{s}" for k, s in CASES}


@pytest.mark.parametrize("key,state", CASES)
def test_svg_is_nanosvg_safe_and_framed(key, state):
    text = _svg(key, state)
    assert "<style" not in text and not re.search(r"\sclass=", text) and "<text" not in text
    x, y, w, h = FRAMES[BUILDINGS[key].footprint]
    assert f'viewBox="{x} {y} {w} {h}"' in text


@pytest.mark.parametrize("key,state", CASES)
def test_team_colour_only_on_owned_buildings(key, state):
    assert (art.TEAM_KEY_COLOR in _svg(key, state)) == BUILDINGS[key].owned


@pytest.mark.parametrize("key,state", [c for c in CASES if BUILDINGS[c[0]].owned])
def test_team_recolor(key, state):
    red = _load(_svg(key, state).replace(art.TEAM_KEY_COLOR, art.TEAM_COLORS["red"]))
    blue_px = pygame.mask.from_threshold(red, pygame.Color(art.TEAM_COLORS["blue"]), (1, 1, 1, 255)).count()
    red_px = pygame.mask.from_threshold(red, pygame.Color(art.TEAM_COLORS["red"]), (1, 1, 1, 255)).count()
    assert blue_px == 0 and red_px > 30


@pytest.mark.parametrize("key,state", CASES)
def test_drawing_stays_inside_its_frame(key, state):
    surf = _load(_svg(key, state))
    w, h = surf.get_size()
    rects = pygame.mask.from_surface(surf).get_bounding_rects()
    box = rects[0].unionall(rects[1:])
    assert box.left > 0 and box.top > 0 and box.right < w and box.bottom < h, f"clipped: {box} in {w}x{h}"


def test_sprouting_buildings_name_real_units():
    for b in CATALOG:
        if b.sprouts:
            assert b.sprouts in UNITS
