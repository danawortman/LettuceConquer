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

## Run the art test scene

```bash
.venv/Scripts/python -m lettuce_conquer.demo
```

- `Tab`: switch between the units view and the buildings view
- `Space` (units): toggle idle / battle mode
- `S` (buildings): cycle planted, sprout, grown, sprouting, wilted
- `R` (buildings): cycle resource level full, half, low
- `T` (buildings): switch team
- Mouse wheel: zoom (check how art reads when small)
- `Esc`: quit

Start in the buildings view with `--view buildings`; `--state`, `--level` and `--team` pick
what it shows first.

Headless check (no window), writes a PNG:

```bash
.venv/Scripts/python -m lettuce_conquer.demo --screenshot screenshots/demo.png
.venv/Scripts/python -m lettuce_conquer.demo --view buildings --state wilted --screenshot screenshots/buildings.png
```

## Tests

```bash
.venv/Scripts/python -m pytest
```

### Pre-commit hook

`scripts/hooks/pre-commit` runs the tests before every commit and aborts the commit if
any fail. Git doesn't install hooks automatically, so do it once per clone:

```bash
cp scripts/hooks/pre-commit .git/hooks/pre-commit
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

### Buildings

Building art lives in `src/lettuce_conquer/assets/buildings/` as `<building>_<state>.svg`.
The catalog (footprints, states, which unit each building sprouts) is in
`src/lettuce_conquer/buildings.py`.

| Building | Footprint | Notes |
|---|---|---|
| Greenhouse | 3x3 | HQ; sprouts Spuds |
| Root Cellar | 2x2 | Unit upgrades; +10% resource collection per cellar, compounding |
| Cabbage Patch | 2x2 | Sprouts Sir Cabbage |
| Pea Trellis | 2x2 | Sprouts Pea Shooters |
| Carrot Bed | 2x2 | Sprouts Carrot Lancers |
| Scarecrow Watchtower | 1x1 | Defense |
| Compost Heap | 2x2 | Neutral resource: Compost |
| Watering Can | 2x2 | Neutral resource: Water |

Team-owned buildings have the states `planted`, `sprout`, `grown`, `wilted` (damaged), and
`sprouting` (a unit popping out) if they sprout units. While planted and sprouting up, the team
pennant climbs its pole to show construction progress. Resources have `full`, `half` and `low`
frames.

Art is drawn at 120 px per grid tile, the same scale as the units. Buildings of one footprint
share a frame (see `FRAMES` in `buildings.py`) with the building's ground point at `(0, 0)`.

Buildings that sprout units need water. Each has a wooden sluice-gate **inlet** at the front of
its left-hand tile; an irrigation channel waters the building when it ends on the tile directly in
front of the inlet (`BuildingType.inlet_tile`).

### Terrain

Terrain art lives in `src/lettuce_conquer/assets/terrain/`; the catalog is
`src/lettuce_conquer/terrain.py`. Everything is neutral (no team colors).

- **Ground tiles** (`grass`, `field`): solid 120 x 120 squares with hard edges.
- **Path and channel pieces** (`path_<piece>`, `channel_<piece>_<dry|wet>`): see-through overlays
  drawn on top of a ground tile. Each piece is drawn in one orientation (see `PIECE_SIDES`); rotate it
  in 90-degree steps for the others. Pieces meet exactly at tile edges, so junctions join cleanly.
- **Lake** (`lake`): one drawing covering 3 x 2 tiles, placed by its top-left tile corner.
- **Standing objects** (trees, rocks, fallen-unit compost piles): one shared frame with the ground
  point at `(0, 0)`, like buildings.

### Resources

| Resource | Where it comes from | Spent on |
|---|---|---|
| Compost | Compost Heaps, and piles left by fallen units | Sprouting units |
| Lumber | Trees (they regrow from stumps) | Buildings, irrigation channels, upgrades |
| Stone | Rocks | Buildings, upgrades |
| Water | Watering Cans, through irrigation channels; refill cans from a lake | Sprouting units |

### SVG rules

pygame loads SVGs with nanosvg, which has limits:

- Use inline attributes only (`fill=`, `stroke=`). CSS `<style>` and classes are ignored.
- `<text>` is ignored.
- Team-colored areas use the key color `#3a7bd5`, which is swapped per team at load time.

## License

[MIT](LICENSE). That covers everything in this repository: code, art and docs.
