"""The unit roster. Data only for now: no stats or behaviour yet."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UnitType:
    key: str            # art file prefix: assets/units/<key>_<state>.svg
    name: str
    role: str
    beats: str | None   # key of the unit this one counters (rock-paper-scissors)


ROSTER: tuple[UnitType, ...] = (
    UnitType("spud", "Spud", "Worker", None),
    UnitType("cabbage", "Sir Cabbage", "Bruiser", "pea"),
    UnitType("pea", "Pea Shooter", "Skirmisher", "carrot"),
    UnitType("carrot", "Carrot Lancer", "Charger", "cabbage"),
)

UNITS: dict[str, UnitType] = {u.key: u for u in ROSTER}
