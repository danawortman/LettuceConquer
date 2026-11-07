"""Tunable game data. Placeholder numbers: balance later."""

TICKS_PER_SECOND = 10
TILE = 120  # world units per tile; the same as art pixels, so 1 world unit = 1 px at zoom 1

TEAM_COLORS = ("blue", "red", "purple", "yellow")

# World units per tick (a tile is 120).
UNIT_SPEED = {"spud": 40, "cabbage": 32, "pea": 40, "carrot": 56}

# Tiles per side of one map quadrant; maps are two quadrants wide and tall.
QUADRANT = 20

# Extra units each team gets in demo mode, so there's something for the trees to drive.
# The real starting rule is one Spud per team.
DEMO_ARMY = ("spud", "spud", "cabbage", "pea", "carrot")

# Which behavior tree each unit kind runs, and the team planner's tree (files in lettuce_conquer/trees/).
DEFAULT_TREES = {
    "spud": "unit_worker",
    "cabbage": "unit_fighter",
    "pea": "unit_fighter",
    "carrot": "unit_fighter",
    "planner": "planner_battle",
}

# ---------------------------------------------------------------- economy
RESOURCES = ("compost", "lumber", "stone", "water")

# What each map feature yields, and how much it holds when full.
YIELDS = {
    "compost_heap": ("compost", 400),
    "apple_tree": ("lumber", 50),
    "pine_tree": ("lumber", 50),
    "rocks_a": ("stone", 200),
    "rocks_b": ("stone", 200),
    "lake": ("water", 0),   # endless: carried to Watering Cans to refill them
    "remains_spud": ("compost", 20),      # Compost piles left by fallen units
    "remains_cabbage": ("compost", 40),
    "remains_pea": ("compost", 30),
    "remains_carrot": ("compost", 35),
}
TREES = ("apple_tree", "pine_tree")   # become stumps and regrow instead of disappearing
TREE_REGROW_TICKS = 600

CARRY_CAPACITY = 10   # resource a Spud carries per trip
GATHER_TICKS = 5      # ticks to harvest one unit of resource

DROPOFFS = ("greenhouse", "root_cellar")   # where Spuds deliver (only once grown)
ROOT_CELLAR_BONUS = 110                    # percent per grown Root Cellar, compounding

STUCK_TICKS = 5   # a unit blocked this long re-plans its route around other units

# ---------------------------------------------------------------- building, irrigation, sprouting
BUILD_COST = {
    "greenhouse": {"lumber": 200, "stone": 100},
    "root_cellar": {"lumber": 80, "stone": 60},
    "cabbage_patch": {"lumber": 60, "stone": 40},
    "pea_trellis": {"lumber": 80, "stone": 20},
    "carrot_bed": {"lumber": 70, "stone": 30},
    "scarecrow": {"lumber": 40, "stone": 40},
}
BUILD_WORK = {"greenhouse": 600, "root_cellar": 300, "cabbage_patch": 300, "pea_trellis": 300,
              "carrot_bed": 300, "scarecrow": 150}   # Spud-ticks of tending; Spuds tending together add up
BUILD_SITE_RANGE = 12   # how far from the anchor a build-site search looks, in tiles

SPROUTS = {"greenhouse": "spud", "cabbage_patch": "cabbage", "pea_trellis": "pea", "carrot_bed": "carrot"}
UNIT_COST = {"spud": {"compost": 50, "water": 20}, "cabbage": {"compost": 80, "water": 40},
             "pea": {"compost": 60, "water": 30}, "carrot": {"compost": 70, "water": 50}}
SPROUT_TICKS = {"spud": 100, "cabbage": 150, "pea": 120, "carrot": 150}

# Fertile ground: a building planted on tilled field tiles grows and sprouts faster, by this percent
# when every tile of its footprint is field (scaled by how many are). Growth and sprouting are counted in
# PACE points per tick, so the bonus stays whole-number math.
FERTILE_BONUS = 50
PACE = 100

CHANNEL_COST = 5     # Lumber per channel tile, paid when digging starts
CHANNEL_WORK = 30    # Spud-ticks to dig one tile
CAN_CAPACITY = 500   # Water a Watering Can holds
ENDLESS = ("lake",)  # sources that never run out

# ---------------------------------------------------------------- combat
UNIT_HP = {"spud": 40, "cabbage": 120, "pea": 60, "carrot": 80}
ATTACK = {  # damage per hit, reach in tiles (1 = the next tile, diagonals too), ticks between hits
    "cabbage": {"damage": 12, "range": 1, "cooldown": 10},
    "pea": {"damage": 8, "range": 4, "cooldown": 10},
    "carrot": {"damage": 14, "range": 1, "cooldown": 8},
}
BEATS = {"cabbage": "pea", "pea": "carrot", "carrot": "cabbage"}   # each deals double to the one it beats
COUNTER_PERCENT = 200     # damage against the unit you beat
COUNTERED_PERCENT = 50    # damage against the unit that beats you
SIGHT = 6                 # tiles: how far units notice enemies (and switch to battle mode)
BATTLE_LINGER = 30        # ticks a unit stays in battle mode after its last fight

BUILDING_HP = {"greenhouse": 1500, "root_cellar": 400, "cabbage_patch": 400, "pea_trellis": 400,
               "carrot_bed": 400, "scarecrow": 300}
SCARECROW = {"damage": 6, "range": 5, "cooldown": 10}   # the crow on its arm does the attacking
