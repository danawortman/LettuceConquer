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
