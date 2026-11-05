"""Test scene for unit and building art.

Units view: both teams' units side by side; Space toggles idle/battle.
Buildings view: every building for one team; S cycles the building state, R the resource level,
T the team. Tab switches views, the mouse wheel zooms, Esc quits.
`--screenshot PATH` renders one frame headlessly and saves it instead of opening a window.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

WINDOW_SIZE = (1280, 720)
SKY = (246, 239, 217)
GROUND = (227, 214, 178)
INK = (43, 33, 24)
MUTED = (120, 105, 85)
MIN_SCALE, MAX_SCALE = 0.2, 1.5
DEFAULT_SCALE = {"units": 0.8, "buildings": 0.5}
# The order S steps through; a building without a state shows "grown" at that step.
BUILDING_STATES = ("planted", "sprout", "grown", "sprouting", "wilted")
RESOURCE_LEVELS = ("full", "half", "low")


def draw_header(screen, font, small_font, hint: str) -> None:
    screen.fill(SKY)
    screen.blit(font.render("Lettuce Conquer: Leaf No One Behind", True, INK), (20, 16))
    screen.blit(small_font.render(hint, True, INK), (20, 52))


def draw_units(screen, font, small_font, state: str, scale: float) -> None:
    from lettuce_conquer.art import TEAM_COLORS, blit_unit
    from lettuce_conquer.units import ROSTER

    draw_header(screen, font, small_font, f"{state.upper()}  ·  scale {scale:.2f}  ·  Space: idle/battle  ·  "
                "Tab: buildings  ·  Wheel: zoom  ·  Esc: quit")
    w, h = screen.get_size()
    rows = (("blue", h * 0.48), ("red", h * 0.90))
    spacing = w / (len(ROSTER) + 1)
    for team, ground_y in rows:
        pygame.draw.ellipse(screen, GROUND, (10, ground_y - 12, w - 20, 24))
        pygame.draw.circle(screen, TEAM_COLORS[team], (24, ground_y - 40), 10)
        for i, unit in enumerate(ROSTER):
            x = spacing * (i + 1)
            blit_unit(screen, unit.key, state, team, (x, ground_y), scale)
            label = small_font.render(unit.name, True, INK)
            screen.blit(label, label.get_rect(midtop=(x, ground_y + 10)))


def draw_buildings(screen, font, small_font, state: str, level: str, team: str, scale: float) -> None:
    from lettuce_conquer.art import TEAM_COLORS, blit_building
    from lettuce_conquer.buildings import CATALOG

    draw_header(screen, font, small_font, f"{team.upper()} team  ·  {state.upper()}  ·  resources {level.upper()}  ·  "
                f"scale {scale:.2f}  ·  S: state  ·  R: resource level  ·  T: team  ·  Tab: units  ·  Esc: quit")
    w, h = screen.get_size()
    per_row = 4
    rows = (h * 0.52, h * 0.92)
    for r, ground_y in enumerate(rows):
        pygame.draw.ellipse(screen, GROUND, (10, ground_y - 12, w - 20, 24))
    pygame.draw.circle(screen, TEAM_COLORS[team], (24, 100), 10)
    for i, building in enumerate(CATALOG):
        x, ground_y = w * (i % per_row + 0.5) / per_row, rows[i // per_row]
        if building.owned:
            shown = state if state in building.states else "grown"
        else:
            shown = level
        blit_building(screen, building.key, shown, team, (x, ground_y), scale)
        label = small_font.render(building.name, True, INK)
        screen.blit(label, label.get_rect(midtop=(x, ground_y + 8)))
        note = shown if shown == state or not building.owned else f"{shown} (no {state})"
        sub = small_font.render(note, True, MUTED)
        screen.blit(sub, sub.get_rect(midtop=(x, ground_y + 30)))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--screenshot", type=Path, help="render one frame to this PNG and exit")
    parser.add_argument("--view", choices=("units", "buildings"), default="units")
    parser.add_argument("--battle", action="store_true", help="units view: start in battle mode")
    parser.add_argument("--state", choices=BUILDING_STATES, default="grown", help="buildings view: building state")
    parser.add_argument("--level", choices=RESOURCE_LEVELS, default="full", help="buildings view: resource level")
    parser.add_argument("--team", choices=("blue", "red"), default="blue", help="buildings view: team")
    parser.add_argument("--scale", type=float, help="art scale for the starting view (1.0 = full size)")
    args = parser.parse_args(argv)

    if args.screenshot:
        os.environ["SDL_VIDEODRIVER"] = "dummy"

    global pygame
    import pygame

    pygame.init()
    try:
        screen = pygame.display.set_mode(WINDOW_SIZE)
        pygame.display.set_caption("Lettuce Conquer - art test scene")
        font = pygame.font.Font(None, 40)
        small_font = pygame.font.Font(None, 26)
        view = args.view
        unit_state = "battle" if args.battle else "idle"
        state, level, team = args.state, args.level, args.team
        scales = dict(DEFAULT_SCALE)
        if args.scale:
            scales[view] = args.scale

        def draw():
            if view == "units":
                draw_units(screen, font, small_font, unit_state, scales["units"])
            else:
                draw_buildings(screen, font, small_font, state, level, team, scales["buildings"])

        if args.screenshot:
            draw()
            args.screenshot.parent.mkdir(parents=True, exist_ok=True)
            pygame.image.save(screen, str(args.screenshot))
            return

        clock = pygame.time.Clock()
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                    running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_TAB:
                    view = "buildings" if view == "units" else "units"
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE and view == "units":
                    unit_state = "idle" if unit_state == "battle" else "battle"
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_s and view == "buildings":
                    state = BUILDING_STATES[(BUILDING_STATES.index(state) + 1) % len(BUILDING_STATES)]
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_r and view == "buildings":
                    level = RESOURCE_LEVELS[(RESOURCE_LEVELS.index(level) + 1) % len(RESOURCE_LEVELS)]
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_t and view == "buildings":
                    team = "red" if team == "blue" else "blue"
                elif event.type == pygame.MOUSEWHEEL:
                    scales[view] = min(MAX_SCALE, max(MIN_SCALE, round(scales[view] + 0.05 * event.y, 2)))
            draw()
            pygame.display.flip()
            clock.tick(60)
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
