"""Unit test scene: both teams' units side by side, idle or in battle mode.

Space toggles idle/battle, the mouse wheel zooms, Esc quits.
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
MIN_SCALE, MAX_SCALE = 0.2, 1.5


def draw_scene(screen, font, small_font, state: str, scale: float) -> None:
    from lettuce_conquer.art import TEAM_COLORS, blit_unit
    from lettuce_conquer.units import ROSTER

    screen.fill(SKY)
    w, h = screen.get_size()
    title = font.render("Lettuce Conquer: Leaf No One Behind", True, INK)
    screen.blit(title, (20, 16))
    hint = small_font.render(f"{state.upper()}  ·  scale {scale:.2f}  ·  Space: idle/battle  ·  "
                             "Wheel: zoom  ·  Esc: quit", True, INK)
    screen.blit(hint, (20, 52))

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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--screenshot", type=Path, help="render one frame to this PNG and exit")
    parser.add_argument("--battle", action="store_true", help="start in battle mode")
    parser.add_argument("--scale", type=float, default=0.8, help="unit scale (1.0 = full size)")
    args = parser.parse_args(argv)

    if args.screenshot:
        os.environ["SDL_VIDEODRIVER"] = "dummy"

    global pygame
    import pygame

    pygame.init()
    try:
        screen = pygame.display.set_mode(WINDOW_SIZE)
        pygame.display.set_caption("Lettuce Conquer - unit test scene")
        font = pygame.font.Font(None, 40)
        small_font = pygame.font.Font(None, 26)
        state = "battle" if args.battle else "idle"
        scale = args.scale

        if args.screenshot:
            draw_scene(screen, font, small_font, state, scale)
            args.screenshot.parent.mkdir(parents=True, exist_ok=True)
            pygame.image.save(screen, str(args.screenshot))
            return

        clock = pygame.time.Clock()
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                    running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                    state = "idle" if state == "battle" else "battle"
                elif event.type == pygame.MOUSEWHEEL:
                    scale = min(MAX_SCALE, max(MIN_SCALE, round(scale + 0.05 * event.y, 2)))
            draw_scene(screen, font, small_font, state, scale)
            pygame.display.flip()
            clock.tick(60)
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
