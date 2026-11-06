import io
import re
from pathlib import Path

import pygame
import pytest

from lettuce_conquer import art
from lettuce_conquer.buildings import CATALOG
from lettuce_conquer import fieldart
from lettuce_conquer.terrain import DECAL_FRAME, DECALS, GROUND_TILES, LAKE_FOOTPRINT, OBJECT_FRAME, OBJECTS, overlay_files

TERRAIN_DIR = Path(art.UNIT_DIR).parent / "terrain"
OBJECT_STEMS = [f"{o.key}_{s}" for o in OBJECTS for s in o.states]
DECAL_STEMS = [f"decal_{d}" for d in DECALS]
ALL_STEMS = list(GROUND_TILES) + overlay_files() + ["lake"] + OBJECT_STEMS + DECAL_STEMS


def _text(stem):
    return (TERRAIN_DIR / f"{stem}.svg").read_text(encoding="utf-8")


def _load(stem):
    return pygame.image.load(io.BytesIO(_text(stem).encode("utf-8")), "x.svg")


def test_every_svg_belongs_to_the_catalog():
    assert {p.stem for p in TERRAIN_DIR.glob("*.svg")} == set(ALL_STEMS)


@pytest.mark.parametrize("stem", ALL_STEMS)
def test_svg_is_nanosvg_safe_and_neutral(stem):
    text = _text(stem)
    assert "<style" not in text and not re.search(r"\sclass=", text) and "<text" not in text
    assert art.TEAM_KEY_COLOR not in text, "terrain has no team colors"


@pytest.mark.parametrize("stem", list(GROUND_TILES) + overlay_files())
def test_tiles_and_overlays_are_one_tile(stem):
    assert 'viewBox="0 0 120 120"' in _text(stem)


@pytest.mark.parametrize("stem", GROUND_TILES)
def test_ground_tiles_are_solid(stem):
    surf = _load(stem)
    assert all(surf.get_at(p).a == 255 for p in [(1, 1), (118, 1), (1, 118), (118, 118), (60, 60)])


@pytest.mark.parametrize("stem", overlay_files())
def test_overlays_are_see_through_at_the_corners(stem):
    surf = _load(stem)
    assert all(surf.get_at(p).a == 0 for p in [(2, 2), (117, 2), (2, 117), (117, 117)])
    assert surf.get_at((60, 60)).a == 255  # every piece covers the tile centre


def test_lake_fits_its_footprint():
    w, h = (n * 120 for n in LAKE_FOOTPRINT)
    assert f'viewBox="0 0 {w} {h}"' in _text("lake")
    rects = pygame.mask.from_surface(_load("lake")).get_bounding_rects()
    box = rects[0].unionall(rects[1:])
    assert box.left > 0 and box.top > 0 and box.right < w and box.bottom < h


@pytest.mark.parametrize("stem", OBJECT_STEMS)
def test_objects_stay_inside_their_frame(stem):
    x, y, w, h = OBJECT_FRAME
    assert f'viewBox="{x} {y} {w} {h}"' in _text(stem)
    rects = pygame.mask.from_surface(_load(stem)).get_bounding_rects()
    box = rects[0].unionall(rects[1:])
    assert box.left > 0 and box.top > 0 and box.right < w and box.bottom < h


@pytest.mark.parametrize("stem", DECAL_STEMS)
def test_decals_stay_inside_their_frame(stem):
    x, y, w, h = DECAL_FRAME
    assert f'viewBox="{x} {y} {w} {h}"' in _text(stem)
    rects = pygame.mask.from_surface(_load(stem), 1).get_bounding_rects()  # count faint, see-through patches too
    box = rects[0].unionall(rects[1:])
    assert box.left > 0 and box.top > 0 and box.right < w and box.bottom < h


@pytest.mark.parametrize("size", [(2, 2), (4, 3), (8, 3)])
def test_field_plots_are_repeatable_safe_and_framed(size):
    svg = fieldart.field_svg(*size, seed=5)
    assert svg == fieldart.field_svg(*size, seed=5)
    assert svg != fieldart.field_svg(*size, seed=6)
    assert "<style" not in svg and "<text" not in svg and " A" not in svg and art.TEAM_KEY_COLOR not in svg
    x, y, w, h = fieldart.frame(*size)
    surf = pygame.image.load(io.BytesIO(svg.encode()), "x.svg")
    assert surf.get_size() == (w, h)
    rects = pygame.mask.from_surface(surf).get_bounding_rects()
    box = rects[0].unionall(rects[1:])
    assert box.left > 0 and box.top > 0 and box.right < w and box.bottom < h  # clods stay in the frame


def test_inlets_belong_to_water_using_buildings():
    for b in CATALOG:
        assert (b.inlet_tile is not None) == bool(b.sprouts)
        if b.inlet_tile:
            assert b.inlet_tile == (0, b.footprint)  # directly in front of the left-hand column
