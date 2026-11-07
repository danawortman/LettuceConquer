import pytest

from lettuce_conquer.game.app import main as game_main
from lettuce_conquer.sim.world import World


@pytest.mark.parametrize("teams", [2, 3, 4])
def test_game_screenshot(tmp_path, teams):
    out = tmp_path / "game.png"
    game_main(["--seed", "3", "--teams", str(teams), "--ticks", "40", "--screenshot", str(out)])
    assert out.exists() and out.stat().st_size > 50_000


def test_game_screenshot_with_inspector(tmp_path):
    unit_id = World(seed=5, teams=2).units[1].id
    for args in (["--inspect", str(unit_id)], ["--inspect-team", "1"]):
        out = tmp_path / "inspect.png"
        game_main(["--seed", "5", "--teams", "2", "--ticks", "60", *args, "--screenshot", str(out)])
        assert out.exists() and out.stat().st_size > 50_000



def test_wet_channels_draw_blue_in_every_base():
    import pygame
    from lettuce_conquer.game import render
    pygame.init()
    screen = pygame.Surface((800, 600))
    world = World(seed=1, teams=4)
    for _ in range(1300):  # long enough for the Greenhouse channels to be dug and wet
        world.step()
    wet = world.wet_channels()
    for team in world.teams:  # every base, the mirrored ones too
        gh = next(b for b in world.buildings if b.team == team.id and b.kind == "greenhouse")
        inlet = world.inlet_tile(gh)
        assert inlet in wet
        cam = render.Camera(0, 0, 0.5)
        cam.center_on(*world.center(*inlet), screen)
        render.draw_world(screen, world, cam)  # the whole scene draws (flipped art, gates, channels)
        screen.fill((0, 0, 0))
        render.draw_channels(screen, world, cam)  # the channels alone: water at the inlet tile's middle
        r, g, b, _ = screen.get_at((400, 300))
        assert b > r + 40, (team.color, (r, g, b))



def test_back_inlet_gates_stand_against_the_building_drawing():
    import pygame
    from lettuce_conquer import art
    from lettuce_conquer.game import render
    from lettuce_conquer.sim.data import TILE
    pygame.init()
    world = World(seed=1, teams=4)
    for team in world.teams:
        x, y = world.find_site(team, "cabbage_patch", team.spawn)
        world.place_building(team, "cabbage_patch", x, y)
    for b in world.buildings:
        ax, ay, back = render.inlet_anchor(world, b)
        inlet = world.inlet_tile(b)
        assert ax == (inlet[0] + 0.5) * TILE
        if world.flips(world.teams[b.team])[1] > 0:  # top-half bases: the gate is in front, on the shared edge
            assert not back and ay == (b.y + b.h) * TILE
        else:  # bottom-half bases: pulled in from the back edge to just behind the low drawing
            ground = (b.y + b.h) * TILE
            assert back and b.y * TILE <= ay < ground
            assert ay == max(b.y * TILE, ground + art.art_top(b.kind, b.state) - render.BACK_GATE_GAP)
    assert art.art_top("cabbage_patch", "grown") > -2 * TILE  # beds really are drawn lower than their footprint


def test_battle_drawing_health_wilt_and_winner_banner():
    import pygame
    from lettuce_conquer.game import render
    from lettuce_conquer.sim import data
    pygame.init()
    screen = pygame.Surface((800, 600))
    font = pygame.font.Font(None, 26)
    world = World(seed=3, teams=2)
    gh = next(b for b in world.buildings if b.team == 0)
    gh.hp = data.BUILDING_HP["greenhouse"] // 3  # badly damaged: drawn wilted, with a health bar
    for u in world.units:
        u.hp = data.UNIT_HP[u.kind] // 2
        u.battle_until = world.tick + 10
    pea = next(u for u in world.units if u.kind == "pea")
    pea.shot = [pea.x + 300, pea.y, world.tick - 1]
    cam = render.Camera(0, 0, 0.5)
    cam.center_on(*world.center(gh.x + 1, gh.y + 1), screen)
    render.draw_world(screen, world, cam, alpha=0.5)  # battle art, health bars, wilted Greenhouse, a pea in flight
    from lettuce_conquer import art
    blue = pygame.Color(art.TEAM_COLORS["blue"])[:3]

    def lettering():
        return sum(screen.get_at((x, y))[:3] == blue for x in range(250, 550) for y in range(280, 320))
    screen.fill((0, 0, 0))
    render.draw_hud(screen, font, world, 1, False)
    assert lettering() == 0  # no result yet
    world.teams[1].alive, world.winner = False, 0
    render.draw_hud(screen, font, world, 1, False)
    assert lettering() > 200  # "Blue wins!" across the middle of the screen


@pytest.mark.parametrize("size", [(1920, 1080), (1280, 720)])
def test_army_panels_sit_in_their_corners_and_leave_room_for_the_rest(size):
    import pygame
    from lettuce_conquer.game import render
    pygame.init()
    screen = pygame.Surface(size)
    font = pygame.font.Font(None, 22)
    world = World(seed=1, teams=4)
    rects = render.panel_rects(screen, world)
    sw, sh = size
    for team in world.teams:  # each army's panel is in its own base's corner of the screen
        sx, sy = world.flips(team)
        r = rects[team.id]
        assert (r.left < sw // 2) == (sx > 0) and (r.top < sh // 2) == (sy > 0)
        assert screen.get_rect().contains(r)
        assert render.panel_at(screen, world, r.center) is team
    assert render.panel_at(screen, world, (sw // 2, sh // 2)) is None
    room = sw - 2 * (render.PANEL_WIDTH + 2 * render.PANEL_MARGIN)
    lines = render._wrap(font, render.HELP, room - 24)
    assert all(font.size(t)[0] <= room for t in lines)
    assert " ".join(lines).split() == " ".join(render.HELP).split()  # nothing lost in the wrapping
    left, right = [r for r in rects.values() if r.left < sw // 2], [r for r in rects.values() if r.left >= sw // 2]
    for side in (left, right):  # panels sharing a side of the screen don't overlap, and are taller than wide
        assert not any(a.colliderect(b) for a in side for b in side if a is not b)
        assert all(r.height > r.width for r in side)
    area = render.inspector_area(screen, world)
    assert not any(area.colliderect(r) for r in rects.values())
    render.draw_hud(screen, font, world, 8, True)  # draws, paused, at either size
