#!/usr/bin/env python3
"""Lane W7: residual-JP scan of the SHIPPED rc-build MDT scripts.

Re-parses every script-bearing MDT straight off the rc Track1 (Java MDTFileParser/
ScriptParser, same pipeline as src/extract.py) and decodes every dialogue segment /
text run with Grandia16x16.tbl, reporting any run that still glosses to Japanese
(kana/kanji). This covers the MDT *script encoding* surface, which the SJIS/HWK
disc census cannot see.

Usage: pW7_mdt_scan.py <rc_track1.bin> [<MDT> ...]   (default: all script MDTs)
Writes nothing to script/ — pure report on stdout; work under output/.extract_work_pW7/.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import extract  # noqa: E402
import decode as decode_mod  # noqa: E402

JP = lambda ch: (0x3041 <= ord(ch) <= 0x30FF or 0x4E00 <= ord(ch) <= 0x9FFF
                 or ord(ch) in (0x3005, 0x30FC))


def main() -> int:
    bin1 = sys.argv[1]
    extract.WORK = ROOT / "output/.extract_work_pW7"
    extract.WORK.mkdir(parents=True, exist_ok=True)
    table = decode_mod.load_table()
    targets = sys.argv[2:] or extract.script_mdts(bin1)
    total_hits = 0
    for name in targets:
        try:
            result = extract.extract_mdt(name, bin1, table)
        except Exception as e:  # parser choke = report, never fake a pass
            print(f"!! {name}: PARSE FAILED: {e}")
            total_hits += 1
            continue
        hits = []
        for code, p in result.get("pieces", {}).items():
            for s in p.get("segments", []):
                njp = sum(1 for c in s["jp"] if JP(c))
                if njp >= 2:
                    hits.append(("seg", code, s["idx"], njp, s["jp"][:70]))
            for r in p.get("text_runs", []):
                jp = r.get("jp", "")
                njp = sum(1 for c in jp if JP(c))
                if njp >= 2 and not p.get("segments"):
                    hits.append(("run", code, r["i"], njp, jp[:70]))
        status = f"{len(hits)} JP hits" if hits else "clean"
        print(f"== {name}: {status}")
        for kind, code, idx, njp, text in hits[:30]:
            print(f"   {kind} piece={code} idx={idx} jp_glyphs={njp}: {text}")
        if len(hits) > 30:
            print(f"   ... +{len(hits)-30} more")
        total_hits += len(hits)
    print(f"TOTAL residual-JP hits: {total_hits}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
