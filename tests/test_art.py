import re

import pygame
import pytest

from lettuce_conquer import art
from lettuce_conquer.demo import main as demo_main
from lettuce_conquer.units import ROSTER, UNITS

ART_CASES = [(u.key, s) for u in ROSTER for s in art.STATES]


@pytest.mark.parametrize("unit,state", ART_CASES)
def test_svg_is_nanosvg_safe(unit, state):
    text = art.svg_path(unit, state).read_text(encoding="utf-8")
    assert "<style" not in text, "nanosvg ignores CSS: use inline attributes"
    assert not re.search(r"\sclass=", text), "nanosvg ignores classes: use inline attributes"
    assert "<text" not in text, "nanosvg ignores <text>: draw labels in the game"
    assert art.TEAM_KEY_COLOR in text, "every unit needs team-colored regions"


def _count(surface, rgb):
    w, h = surface.get_size()
    return sum(1 for x in range(w) for y in range(h) if surface.get_at((x, y))[:3] == rgb)


@pytest.mark.parametrize("unit,state", ART_CASES)
def test_team_recolor(unit, state):
    blue = pygame.Color(art.TEAM_COLORS["blue"])[:3]
    red = pygame.Color(art.TEAM_COLORS["red"])[:3]
    red_surf = art.unit_surface(unit, state, "red", 0.5)
    assert red_surf.get_size() == (170, 110)
    assert _count(red_surf, red) > 30
    assert _count(red_surf, blue) == 0


def test_roster_counters_form_a_triangle():
    fighters = [u for u in ROSTER if u.beats]
    assert {u.beats for u in fighters} == {u.key for u in fighters}
    for u in fighters:
        assert UNITS[u.beats].beats != u.key


@pytest.mark.parametrize("battle", [False, True])
def test_demo_screenshot(tmp_path, battle):
    out = tmp_path / "demo.png"
    demo_main(["--screenshot", str(out)] + (["--battle"] if battle else []))
    assert out.exists() and out.stat().st_size > 10_000
