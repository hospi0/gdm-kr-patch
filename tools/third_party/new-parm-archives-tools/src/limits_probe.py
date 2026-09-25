#!/usr/bin/env python3
"""Generate escalating test strings to characterize injection limits (Step 1).

Produces marked filler payloads (>=100 words and beyond) and increasingly long/edge-case
strings so we can find, via YMIR verification, the real constraints recorded in
docs/step1-limits.md: max chars per box/line, wrap behavior, multi-box sequencing, the
sector-hole budget, and which control codes are safe.

The string generation here is real and usable now; wiring it through the injection pipeline
depends on inject.py / the Java tools.
"""
from __future__ import annotations

import argparse

# Obvious, non-final placeholder so a test build is never mistaken for real translation.
MARK = "[[TEST]]"


def filler(words: int) -> str:
    """A clearly-marked filler string of `words` words."""
    base = (
        "the quick brown fox jumps over the lazy dog while narrating an obviously fake "
        "placeholder line used only to measure how much english text this dialogue box "
        "can hold before the game runs out of room or the pointers go wrong"
    ).split()
    out = []
    while len(out) < words:
        out.extend(base)
    return MARK + " " + " ".join(out[:words]) + " " + MARK


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--words", type=int, default=100, help="word count for the filler payload")
    args = p.parse_args()
    text = filler(args.words)
    print(text)
    print(f"\n# chars={len(text)} words={args.words}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
