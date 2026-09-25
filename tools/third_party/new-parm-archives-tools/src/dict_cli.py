#!/usr/bin/env python3
"""Dictionary CLI for the Grandia: Digital Museum translation.

Keeps JP->EN term mappings consistent across the whole script and logs deliberate
deviations to an exceptions file for later user review.

Storage: JSON (dictionary/terms.json, dictionary/exceptions.json).

Usage:
    dict_cli.py add   <jp> <en> [--note NOTE]      # record/confirm a canonical mapping
    dict_cli.py lookup <jp>                         # print the canonical EN for a JP term
    dict_cli.py check <jp> <en>                     # verify a proposed EN matches canon
    dict_cli.py except <jp> <en> --reason REASON    # log a deliberate deviation
    dict_cli.py list                                # dump all terms
    dict_cli.py exceptions                          # dump the exceptions log

Exit codes: 0 ok / consistent, 2 conflict (check failed), 3 not found (lookup).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TERMS_PATH = ROOT / "dictionary" / "terms.json"
EXC_PATH = ROOT / "dictionary" / "exceptions.json"


def _load(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _save(path: Path, data: dict) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def cmd_add(args) -> int:
    data = _load(TERMS_PATH)
    terms = data["terms"]
    existing = terms.get(args.jp)
    if existing and existing["en"] != args.en:
        print(
            f"CONFLICT: '{args.jp}' already maps to '{existing['en']}', "
            f"not '{args.en}'. Use `except` to log a deliberate deviation.",
            file=sys.stderr,
        )
        return 2
    entry = {"en": args.en, "added": existing["added"] if existing else str(date.today())}
    if args.note:
        entry["note"] = args.note
    terms[args.jp] = entry
    _save(TERMS_PATH, data)
    print(f"OK: {args.jp} -> {args.en}")
    return 0


def cmd_lookup(args) -> int:
    terms = _load(TERMS_PATH)["terms"]
    entry = terms.get(args.jp)
    if not entry:
        print(f"NOT FOUND: {args.jp}", file=sys.stderr)
        return 3
    print(entry["en"])
    return 0


def cmd_check(args) -> int:
    terms = _load(TERMS_PATH)["terms"]
    entry = terms.get(args.jp)
    if not entry:
        print(f"UNKNOWN: {args.jp} (no canonical mapping yet)")
        return 0
    if entry["en"] == args.en:
        print(f"CONSISTENT: {args.jp} -> {args.en}")
        return 0
    print(
        f"CONFLICT: canonical '{args.jp}' -> '{entry['en']}', proposed '{args.en}'.",
        file=sys.stderr,
    )
    return 2


def cmd_except(args) -> int:
    data = _load(EXC_PATH)
    data["exceptions"].append(
        {
            "jp": args.jp,
            "en": args.en,
            "reason": args.reason,
            "logged": str(date.today()),
        }
    )
    _save(EXC_PATH, data)
    print(f"LOGGED exception: {args.jp} -> {args.en} ({args.reason})")
    return 0


def cmd_list(_args) -> int:
    terms = _load(TERMS_PATH)["terms"]
    for jp, entry in sorted(terms.items()):
        print(f"{jp}\t{entry['en']}")
    return 0


def cmd_exceptions(_args) -> int:
    for e in _load(EXC_PATH)["exceptions"]:
        print(f"{e['jp']}\t{e['en']}\t{e['reason']}\t({e['logged']})")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add"); a.add_argument("jp"); a.add_argument("en")
    a.add_argument("--note"); a.set_defaults(func=cmd_add)

    a = sub.add_parser("lookup"); a.add_argument("jp"); a.set_defaults(func=cmd_lookup)

    a = sub.add_parser("check"); a.add_argument("jp"); a.add_argument("en")
    a.set_defaults(func=cmd_check)

    a = sub.add_parser("except"); a.add_argument("jp"); a.add_argument("en")
    a.add_argument("--reason", required=True); a.set_defaults(func=cmd_except)

    sub.add_parser("list").set_defaults(func=cmd_list)
    sub.add_parser("exceptions").set_defaults(func=cmd_exceptions)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
