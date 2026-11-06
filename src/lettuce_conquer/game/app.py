"""Run a game: behavior trees drive every army; you watch, pan, zoom and inspect.

`--screenshot PATH` runs headlessly for `--ticks` ticks, draws one frame and saves it.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from lettuce_conquer.sim.data import TICKS_PER_SECOND, TILE
from lettuce_conquer.sim.world import World

WINDOW_SIZE = (1280, 720)
SPEEDS = (1, 2, 4, 8)
PAN_SPEED = 900  # screen pixels per second


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Lettuce Conquer: watch behavior-tree armies on a farm.")
    parser.add_argument("--seed", type=int, default=1, help="map seed")
    parser.add_argument("--teams", type=int, choices=(2, 3, 4), default=4, help="number of armies")
    parser.add_argument("--one-worker", action="store_true",
                        help="start each army with one Spud only (the real rule) instead of the demo army")
    parser.add_argument("--ticks", type=int, default=0, help="run this many ticks before showing anything")
    parser.add_argument("--zoom", type=float, default=0.5)
    parser.add_argument("--inspect", type=int, help="select the unit with this id at the start")
    parser.add_argument("--inspect-team", type=int, help="select this team's planner at the start")
    parser.add_argument("--screenshot", type=Path, help="draw one frame to this PNG and exit")
    args = parser.parse_args(argv)

    if args.screenshot:
        os.environ["SDL_VIDEODRIVER"] = "dummy"
    import pygame
    from lettuce_conquer.game import render

    world = World(seed=args.seed, teams=args.teams, demo_army=not args.one_worker)
    for _ in range(args.ticks):
        world.step()

    pygame.init()
    try:
        screen = pygame.display.set_mode(WINDOW_SIZE)
        pygame.display.set_caption("Lettuce Conquer: Leaf No One Behind")
        font, small = pygame.font.Font(None, 26), pygame.font.Font(None, 22)
        zoom = min(render.ZOOM_STEPS, key=lambda z: abs(z - args.zoom))
        cam = render.Camera(0, 0, zoom)
        cam.center_on(*world.center(*world.teams[0].spawn), screen)
        selected = None
        if args.inspect is not None:
            selected = next((u for u in world.units if u.id == args.inspect), None)
        elif args.inspect_team is not None:
            selected = world.teams[args.inspect_team]
        speed_i, paused = 0, False

        def draw(alpha):
            cam.clamp(world.width * TILE, world.height * TILE, screen)
            render.draw_world(screen, world, cam, alpha, selected)
            render.draw_hud(screen, small, world, SPEEDS[speed_i], paused)
            if selected is not None:
                render.draw_inspector(screen, font, small, world, selected)

        if args.screenshot:
            draw(1.0)
            args.screenshot.parent.mkdir(parents=True, exist_ok=True)
            pygame.image.save(screen, str(args.screenshot))
            return

        clock = pygame.time.Clock()
        carry = 0.0
        dragging = None
        running = True
        while running:
            dt = clock.tick(60) / 1000
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_SPACE:
                        paused = not paused
                    elif event.key == pygame.K_RIGHTBRACKET:
                        speed_i = min(speed_i + 1, len(SPEEDS) - 1)
                    elif event.key == pygame.K_LEFTBRACKET:
                        speed_i = max(speed_i - 1, 0)
                    elif event.key == pygame.K_TAB and world.units:
                        ids = [u.id for u in world.units]
                        nxt = ids[(ids.index(selected.id) + 1) % len(ids)] if selected in world.units else ids[0]
                        selected = next(u for u in world.units if u.id == nxt)
                        cam.center_on(selected.x, selected.y, screen)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    selected = render.pick(world, cam, event.pos, carry * TICKS_PER_SECOND * SPEEDS[speed_i])
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                    dragging = event.pos
                elif event.type == pygame.MOUSEBUTTONUP and event.button == 3:
                    dragging = None
                elif event.type == pygame.MOUSEMOTION and dragging:
                    cam.x -= (event.pos[0] - dragging[0]) / cam.zoom
                    cam.y -= (event.pos[1] - dragging[1]) / cam.zoom
                    dragging = event.pos
                elif event.type == pygame.MOUSEWHEEL:
                    i = render.ZOOM_STEPS.index(cam.zoom)
                    new = render.ZOOM_STEPS[min(max(i + event.y, 0), len(render.ZOOM_STEPS) - 1)]
                    mx, my = pygame.mouse.get_pos()
                    wx, wy = cam.to_world(mx, my)
                    cam.zoom = new
                    cam.x, cam.y = wx - mx / new, wy - my / new  # keep the point under the mouse still
            keys = pygame.key.get_pressed()
            step = PAN_SPEED * dt / cam.zoom
            cam.x += step * ((keys[pygame.K_RIGHT] or keys[pygame.K_d]) - (keys[pygame.K_LEFT] or keys[pygame.K_a]))
            cam.y += step * ((keys[pygame.K_DOWN] or keys[pygame.K_s]) - (keys[pygame.K_UP] or keys[pygame.K_w]))

            interval = 1 / (TICKS_PER_SECOND * SPEEDS[speed_i])
            if not paused:
                carry += dt
                while carry >= interval:
                    world.step()
                    carry -= interval
            draw(min(carry / interval, 1.0) if not paused else 1.0)
            pygame.display.flip()
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
