#!/usr/bin/env python3
"""Build a committable xdelta3 delta: original JP track -> patched EN track (Step 3).

The delta + modified .MDT files go under patches/ (committed). The full images never do.

NOT YET IMPLEMENTED — requires xdelta3 and a finished patched track in output/NNN/.
"""
from __future__ import annotations

import shutil
import sys


def main() -> int:
    if shutil.which("xdelta3") is None:
        print("xdelta3 not found on PATH (install via `brew install xdelta`).", file=sys.stderr)
    print(
        "build_delta.py is a stub. Implement after Step 3 produces a patched track. "
        "See docs/step3-build.md.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
