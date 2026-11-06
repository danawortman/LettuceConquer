"""Deterministic random numbers (xorshift32). The state is a plain int, saved with the world."""
from __future__ import annotations

MASK = 0xFFFFFFFF


def seed_state(seed: int) -> int:
    """Spread a small seed over 32 bits; xorshift must never start at zero."""
    state = (seed * 2654435761 + 0x9E3779B9) & MASK
    return state or 0x6D2B79F5


class Rng:
    def __init__(self, state: int):
        self.state = state

    def next_u32(self) -> int:
        x = self.state
        x ^= (x << 13) & MASK
        x ^= x >> 17
        x ^= (x << 5) & MASK
        self.state = x
        return x

    def randint(self, lo: int, hi: int) -> int:
        """An int in [lo, hi], inclusive."""
        return lo + self.next_u32() % (hi - lo + 1)

    def choice(self, seq):
        return seq[self.randint(0, len(seq) - 1)]
