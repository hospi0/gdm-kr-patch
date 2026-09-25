#!/usr/bin/env python3
"""Round-trip safety check for dialogue substitution.

Guarantees we only ever change TEXT bytes — never a control code, portrait code, or event
bytecode byte. Run on any (original_piece, substituted_piece) pair. Exit 0 if safe.

    validate_subst.py <original_piece> <substituted_piece>

This is the guardrail that prevents the freezes (corrupted controls) and graphics corruption
(corrupted portrait codes) we hit in attempts 021/022. See docs/script-format.md.
"""
from __future__ import annotations

import sys

import subst


def text_mask(data: bytes) -> bytearray:
    """1 where a byte is dialogue TEXT (inside a portrait-started box's text runs)."""
    mask = bytearray(len(data))
    i = 0
    while i < len(data):
        if subst._is_portrait(data, i):
            try:
                end = data.index(subst.END, i + 6)
            except ValueError:
                break
            j = i + 6
            while j <= end:
                c = data[j]
                if c == subst.END:
                    break
                if subst._is_portrait(data, j):
                    j += 6
                elif c <= 0x0F:
                    j += 1
                else:
                    while j <= end and data[j] > 0x0F:
                        n = 2 if 0x10 <= data[j] <= 0x1F else 1
                        for k in range(n):
                            if j + k < len(mask):
                                mask[j + k] = 1
                        j += n
            i = end + 1
        else:
            i += 1
    return mask


def validate(orig: bytes, new: bytes) -> int:
    if len(orig) != len(new):
        print(f"LENGTH CHANGED {len(orig)} -> {len(new)}", file=sys.stderr)
        return 1
    mask = text_mask(orig)
    unsafe = [k for k in range(len(orig)) if orig[k] != new[k] and not mask[k]]
    changed = sum(1 for k in range(len(orig)) if orig[k] != new[k])
    if unsafe:
        print(f"UNSAFE: {len(unsafe)} non-text bytes changed, e.g. {unsafe[:10]}", file=sys.stderr)
        return 2
    print(f"SAFE: {changed} text bytes changed, no control/portrait/bytecode byte touched.")
    return 0


def main() -> int:
    orig = open(sys.argv[1], "rb").read()
    new = open(sys.argv[2], "rb").read()
    return validate(orig, new)


if __name__ == "__main__":
    raise SystemExit(main())
