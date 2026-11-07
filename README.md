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

## Run the game

```bash
.venv/Scripts/python -m lettuce_conquer
```

Behavior trees drive every army; you watch and inspect. Each demo army starts with three Spuds and
three fighters. The team planner hands the Spuds jobs, plants a Cabbage Patch, Pea Trellis and Carrot
Bed, plans irrigation channels to everything that sprouts, and sprouts more Spuds and fighters as
Compost and Water allow, and plants a Scarecrow. Spuds gather, tend new buildings until they grow,
dig channels and carry water to the Watering Cans. Fighters guard home and fight any enemy in sight;
once a team has 7 fighters it raids the nearest enemy Greenhouse, and calls the raid off when fewer
than 3 are left. A team whose Greenhouse falls is out; the last team standing wins. The top bar shows
each team's units and stock.

The armies are mirrored and run the same trees, so 2 or 4 armies usually fight to a standstill or a
draw. Three armies aren't symmetric (one sits between the other two), so `--teams 3` produces a
winner (seed 1: Red, at tick 3,904, about 6½ minutes of game time; use `]` to speed up). Options: `--seed N` (map), `--teams 2|3|4`,
`--one-worker` (start with one Spud per army, the real rule, instead of the demo army),
`--ticks N` (fast-forward), `--zoom Z`.

- Arrow keys / WASD, or right-drag: pan
- Mouse wheel: zoom
- Click a unit: show its behavior tree, colored by what ran this tick, and its blackboard
- Click a Greenhouse: show that team's planner tree
- `Tab`: jump to the next unit
- `Space`: pause; `[` / `]`: slower / faster
- `F11`: switch between full screen and a window
- `Esc`: quit

The game opens full screen at the desktop's resolution; `--windowed` starts it in a resizable window.

Headless frame: `.venv/Scripts/python -m lettuce_conquer --ticks 200 --screenshot screenshots/game.png`

## How the game is built

- `lettuce_conquer/sim/`: the simulation, with no pygame. It runs in fixed ticks (10 per second) with
  whole-number math and a seeded random generator, so the same seed and trees always play out the same
  way (`World.state_hash()` lets tests check that).
  - `mapgen.py`: seeded maps. One quarter is generated, then mirrored into the other three, so 2 to 4
    armies start on identical ground.
  - `pathfind.py`: A* on the tile grid.
  - `world.py`: the world and its update. Each tick stumps regrow, every team's planner tree runs, then
    every unit's tree, then sprouting buildings draw water and finish units, then units move. Units never share a tile: a unit reserves the next tile before
    stepping in, waits if it's taken, and re-plans around other units if the wait lasts.
  - `data.py`: tunable numbers (speeds, carry size, resource amounts, regrowth, the Root Cellar bonus,
    building and unit costs, tending and sprouting times, channel cost).
  - `bt.py`, `nodes.py`, `trees.py`: behavior trees (below).
- `lettuce_conquer/game/`: the pygame window that draws the world and the tree inspector.

## Behavior trees

Each unit runs a behavior tree, and each team has a planner tree that coordinates its army (for example
by setting a rally point the units read). Trees are JSON files in `src/lettuce_conquer/trees/`:

```json
{
  "name": "Wander near home",
  "scope": "unit",
  "root": {
    "type": "sequence",
    "children": [
      {"type": "action", "name": "pick_wander_spot", "args": {"key": "spot", "radius": 4}},
      {"type": "action", "name": "move_to", "args": {"key": "spot"}},
      {"type": "action", "name": "wait", "args": {"ticks": 15}}
    ]
  }
}
```

- **Composites:** `sequence` (runs children until one fails), `selector` (until one succeeds). Both
  remember a running child and resume it next tick. `reactive_sequence` and `reactive_selector` start
  from their first child every tick instead, so an earlier child (say, "an enemy is in sight") can take
  over from a running later one, which is then stopped.
- **Decorators** (one `child`): `inverter`, `succeeder`, `repeat` (optional `times`), `cooldown` (`ticks`).
- **Leaves:** `condition` and `action` nodes from the node library in `sim/nodes.py`, with `args`.
- Every node returns `success`, `failure` or `running`. Each agent keeps its own blackboard (`bb`) and
  running memory, so many units can share one tree. Tiles in blackboards are `[x, y]` lists.
- `sim.bt.validate(tree)` returns readable error messages; `sim.bt.node_catalog()` describes every node
  and its arguments as data.
- Which tree each unit kind and planner uses is set in `sim/data.py` (`DEFAULT_TREES`).

Node library, by area:

| Area | Nodes |
|---|---|
| General | `has_key`, `set_key`, `clear_key`, `wait`, `succeed`, `fail` |
| Moving | `move_to`, `move_next_to`, `pick_wander_spot`, `at_tile`, `team_has_key`, `copy_team_key` |
| Conditions | `key_equals`, `stock_at_least`, `building_count_below`, `unit_count_below`, `building_fertile`, `carrying` |
| Gathering | `find_nearest_resource`, `harvest`, `is_full`, `is_carrying`, `find_dropoff`, `deposit` |
| Building and water | `find_construction`, `tend`, `find_channel_work`, `dig`, `find_can`, `pour` |
| Combat | `enemy_near`, `find_enemy`, `attack`, `copy_team_value`, `fighters_at_least` |
| Team planner | `choose_rally`, `assign_spud_jobs`, `order_building`, `order_channel`, `sprout`, `choose_enemy_greenhouse` |

The default trees are `unit_worker` (Spuds), `unit_fighter` (fighters) and `planner_battle` (the
team planner). `planner_grow` (builds an army but never raids), `unit_follow_rally`, `unit_gather`,
`planner_rally` and `unit_wander` are simpler examples.

## Combat

- Fighters hit the enemy they're attacking whenever they're ready. Sir Cabbage and Carrot Lancer reach
  the next tile (diagonals too), Pea Shooters 4 tiles. Spuds don't fight.
- **Counters:** each fighter deals double damage to the one it beats and half to the one that beats it
  (Sir Cabbage > Pea Shooter > Carrot Lancer > Sir Cabbage).
- **No army acts first.** Every hit in a tick lands at the same moment, at the end of the tick. Units
  decide their steps from where everyone stood at the start of the move; when several want the same
  tile the nearest gets it, and enemies exactly as near both wait. Units also never stop exactly on a
  tile edge, where rounding a position to a tile wouldn't be mirror-symmetric.
- Fighters with an enemy within 6 tiles, and anyone hitting or being hit, switch to battle-mode art.
  Damaged units and buildings show a health bar; a grown building below half health looks wilted.
- A fallen unit leaves a Compost pile on its tile that Spuds can gather. Destroyed buildings are removed.
- A grown **Scarecrow Watchtower**'s crow strikes the nearest enemy unit within 5 tiles.
- **Losing:** a team whose Greenhouse is destroyed is out; its units fall and its buildings go too. The
  last team standing wins (if the last Greenhouses fall together, it's a draw).

| | Health | Damage | Reach (tiles) | Ticks between hits |
|---|---|---|---|---|
| Spud | 40 | | | |
| Sir Cabbage | 120 | 12 | 1 | 10 |
| Pea Shooter | 60 | 8 | 4 | 10 |
| Carrot Lancer | 80 | 14 | 1 | 8 |
| Scarecrow (crow) | 300 | 6 | 5 | 10 |

Building health: Greenhouse 1500, other buildings 400. Fallen units leave 20 to 40 Compost. All
placeholders in `sim/data.py`.

## Economy

- Spuds carry up to 10 of one resource and gather 1 every half second.
- Compost Heaps (400) and Rocks (200 Stone) shrink through their Full, Half and Low looks and are then
  gone for good. Trees (50 Lumber) turn into stumps and regrow after a minute.
- Spuds deliver to their team's nearest grown Greenhouse or Root Cellar. Each grown Root Cellar adds
  10% to every delivery, compounding (one: x1.1, two: x1.21).
- Water can't be delivered: a team's Water is what its connected Watering Cans hold (see below).

## Building, irrigation and sprouting

- **Building:** the planner's `order_building` finds a free spot near home (grass or tilled field, with
  a walkway all round and room for the inlet), pays the Lumber and Stone and plants the building. Spuds tend it:
  one point of growth per Spud per tick, so more Spuds grow it faster. It turns from Planted to Sprout
  half way, then to Grown.
- **Fertile ground:** the tilled fields out past each base are fertile. A building planted on them
  grows and sprouts up to 50% faster: the full bonus when its whole footprint is field, less when only
  some of it is (`World.fertility`, `Building.fertile`). Sprouting on fertile ground uses the same Water,
  just sooner. The demo planner still builds near home; choosing fertile sites is left open.
- **Irrigation:** `order_channel` plans a channel from the nearest Watering Can's spout to a building's
  inlet. Spuds dig it tile by tile, from the can outward, paying 5 Lumber per tile. Each can's first
  tile, where its puddle is, comes already dug and free, and belongs to nobody. Units walk across
  channels. Dug channels joined to a can holding water are drawn wet.
- **Water:** Watering Cans are neutral and hold 500 Water; any team can connect to any can. A Spud
  whose job is water fills up at a lake (lakes never run dry) and pours it into a connected can that
  isn't full.
- **Sprouting:** `sprout` picks an idle, grown building that makes the unit and is watered. It pays the
  Compost at once and draws the Water from the connected can a little each tick; sprouting pauses while
  the can is dry. The new unit appears beside the inlet.
- **Inlets face the middle of the map.** The armies' bases are mirrored, so building and can art is
  mirrored too, and the sluice gate sits on the side facing the middle. In bases in the bottom half that
  is the back, so the gate is drawn just behind the building's drawing and the channel runs on to meet it
  (and a can's channel runs under the can to its puddle). Gates are centred on their channel. Every tie is broken in the team's own mirrored view, so mirrored armies
  make mirrored choices; a test checks every unit, building and channel against its twin.

| Building | Lumber | Stone | Tending |
|---|---|---|---|
| Greenhouse | 200 | 100 | 600 |
| Root Cellar | 80 | 60 | 300 |
| Cabbage Patch | 60 | 40 | 300 |
| Pea Trellis | 80 | 20 | 300 |
| Carrot Bed | 70 | 30 | 300 |
| Scarecrow Watchtower | 40 | 40 | 150 |

| Unit | Compost | Water | Sprouting (ticks) |
|---|---|---|---|
| Spud | 50 | 20 | 100 |
| Sir Cabbage | 80 | 40 | 150 |
| Pea Shooter | 60 | 30 | 120 |
| Carrot Lancer | 70 | 50 | 150 |

All numbers are placeholders in `sim/data.py` (`FERTILE_BONUS` for fertile ground).

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

Buildings that sprout units need water. Each has a wooden sluice-gate **inlet**, drawn as a
separate overlay (`inlet_gate`, or `inlet_sign` before the building has grown) on whichever side the
inlet faces; an irrigation channel waters the building when it ends on the inlet tile
(`World.inlet_tile`).

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
