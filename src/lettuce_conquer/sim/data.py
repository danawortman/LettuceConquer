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
DEMO_ARMY = ("cabbage", "pea", "carrot")

# Which behavior tree each unit kind runs, and the team planner's tree (files in lettuce_conquer/trees/).
DEFAULT_TREES = {
    "spud": "unit_wander",
    "cabbage": "unit_follow_rally",
    "pea": "unit_follow_rally",
    "carrot": "unit_follow_rally",
    "planner": "planner_rally",
}
