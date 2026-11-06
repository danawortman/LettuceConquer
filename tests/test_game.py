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
