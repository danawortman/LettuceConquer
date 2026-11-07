import io
import re
from pathlib import Path

import pygame
import pytest

from lettuce_conquer import art
from lettuce_conquer.buildings import BUILDINGS, CATALOG, FRAMES, INLET_ART, INLET_FRAME
from lettuce_conquer.demo import BUILDING_STATES
from lettuce_conquer.demo import main as demo_main
from lettuce_conquer.units import UNITS

BUILDING_DIR = Path(art.UNIT_DIR).parent / "buildings"
CASES = [(b.key, s) for b in CATALOG for s in b.states]


def _svg(key, state):
    return (BUILDING_DIR / f"{key}_{state}.svg").read_text(encoding="utf-8")


def _load(text):
    return pygame.image.load(io.BytesIO(text.encode("utf-8")), "x.svg")


def test_every_svg_belongs_to_a_catalog_state():
    on_disk = {p.stem for p in BUILDING_DIR.glob("*.svg")}
    assert on_disk == {f"{k}_{s}" for k, s in CASES} | set(INLET_ART)


@pytest.mark.parametrize("stem", INLET_ART)
def test_inlet_art_is_safe_and_inside_its_frame(stem):
    text = (BUILDING_DIR / f"{stem}.svg").read_text(encoding="utf-8")
    assert "<style" not in text and "<text" not in text and art.TEAM_KEY_COLOR not in text
    x, y, w, h = INLET_FRAME
    assert f'viewBox="{x} {y} {w} {h}"' in text
    surf = _load(text)
    rects = pygame.mask.from_surface(surf).get_bounding_rects()
    box = rects[0].unionall(rects[1:])
    assert box.left > 0 and box.top > 0 and box.right < w and box.bottom < h


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


def test_inlet_art_and_can_puddle_are_centred_on_their_channel_column():
    import re as _re
    for stem in INLET_ART:  # the gate or sign is centred on its anchor (the middle of the inlet tile's edge)
        surf = _load((BUILDING_DIR / f"{stem}.svg").read_text(encoding="utf-8"))
        rects = pygame.mask.from_surface(surf).get_bounding_rects()
        box = rects[0].unionall(rects[1:])
        assert abs(box.centerx - -INLET_FRAME[0]) <= 3, (stem, box)
    for level in ("full", "half", "low"):  # the puddle sits over the middle of the outlet column (60 right of centre)
        text = _svg("watering_can", level)
        shift = int(_re.search(r'translate\((-?\d+),0\)', text).group(1))
        cx = int(_re.search(r'<ellipse cx="(-?\d+)" cy="-?\d+" rx="44"', text).group(1))
        assert shift + cx == 60, level


def test_building_surface_is_its_frame_at_scale():
    assert art.building_surface("greenhouse", "grown", "red", 0.5).get_size() == (250, 205)
    assert art.building_surface("scarecrow", "grown", "blue", 1.0).get_size() == (260, 280)


def test_blit_building_puts_the_ground_point_on_target():
    dest = pygame.Surface((600, 500), pygame.SRCALPHA)
    drawn = art.blit_building(dest, "greenhouse", "grown", "blue", (300, 450), 1.0)
    # The 3x3 frame starts at (-250, -380), so the ground point sits 250 px right and 380 px down.
    assert drawn.topleft == (50, 70)


@pytest.mark.parametrize("state", BUILDING_STATES)
def test_demo_buildings_view_screenshot(tmp_path, state):
    out = tmp_path / "buildings.png"
    demo_main(["--view", "buildings", "--state", state, "--level", "half", "--team", "red", "--screenshot", str(out)])
    assert out.exists() and out.stat().st_size > 10_000


def test_flipped_building_is_a_mirror_on_the_same_ground_point():
    dest = pygame.Surface((600, 500), pygame.SRCALPHA)
    plain = art.blit_building(dest, "cabbage_patch", "grown", "blue", (300, 450), 1.0)
    flipped = art.blit_building(dest, "cabbage_patch", "grown", "blue", (300, 450), 1.0, flip=True)
    assert plain == flipped  # the frames are symmetric about the ground point
    a = art.building_surface("cabbage_patch", "grown", "blue", 0.5)
    b = art.building_surface("cabbage_patch", "grown", "blue", 0.5, flip=True)
    w = a.get_width()
    assert all(a.get_at((x, y)) == b.get_at((w - 1 - x, y)) for x in range(0, w, 7) for y in range(0, a.get_height(), 7))


@pytest.mark.parametrize("stem", INLET_ART)
def test_blit_inlet_puts_the_anchor_on_target(stem):
    dest = pygame.Surface((300, 300), pygame.SRCALPHA)
    drawn = art.blit_inlet(dest, stem, (150, 200), 1.0)
    x, y, _, _ = INLET_FRAME
    assert drawn.topleft == (150 + x, 200 + y)
