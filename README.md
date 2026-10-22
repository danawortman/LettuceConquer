# Lettuce Conquer: Leaf No One Behind

An educational real-time strategy game about a very serious vegetable army, built on
[pygame-ce](https://pyga.me/) so it runs on Linux and Windows.

## Setup

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"   # Windows
.venv/bin/python -m pip install -e ".[dev]"       # Linux/macOS
```

Use **pygame-ce**, not legacy `pygame`. Both install a module called `pygame`, so keep
this project in its own virtual environment.

## Run the unit test scene

```bash
.venv/Scripts/python -m lettuce_conquer.demo
```

- `Space`: toggle idle / battle mode
- Mouse wheel: zoom (check how units read when small)
- `Esc`: quit

Headless check (no window), writes a PNG:

```bash
.venv/Scripts/python -m lettuce_conquer.demo --screenshot screenshots/demo.png
```

## Tests

```bash
.venv/Scripts/python -m pytest
```

## Units

| Unit | Role | Beats |
|---|---|---|
| Spud | Worker | — |
| Sir Cabbage | Bruiser | Pea Shooter |
| Pea Shooter | Skirmisher | Carrot Lancer |
| Carrot Lancer | Charger | Sir Cabbage |

## Art

Unit art lives in `src/lettuce_conquer/assets/units/` as one SVG per unit and state
(`<unit>_idle.svg`, `<unit>_battle.svg`). All share one frame (`viewBox="-200 40 340 220"`)
with the unit's feet at `(0, 248)`, so any unit can be placed by the same anchor.

pygame loads SVGs with nanosvg, which has limits:

- Use inline attributes only (`fill=`, `stroke=`). CSS `<style>` and classes are ignored.
- `<text>` is ignored.
- Team-colored areas use the key color `#3a7bd5`, which is swapped per team at load time.

## License

[MIT](LICENSE). That covers everything in this repository: code, art and docs.
