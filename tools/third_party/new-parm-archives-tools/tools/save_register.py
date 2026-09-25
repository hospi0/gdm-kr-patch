#!/usr/bin/env python3
"""save_register.py — back up + catalogue YMIR savestates inside the repo.

Per CLAUDE.md: every savestate used with the harness MUST be registered here so
future testing/validation is reproducible. Savestates are stored **gzipped** under
`saves/` (a 5.7 MB state -> ~1.5 MB) with metadata in `saves/manifest.json`.

Subcommands:
  register YMIR_STATE SLUG "description" [--tags a,b] [--disc-build NAME]
        gzip-copy a YMIR savestate into saves/SLUG.savestate.gz + add metadata.
        The disc hash is taken from the parent dir name (YMIR keys saves by it).
  restore SLUG [DESTDIR]   gunzip saves/SLUG.savestate.gz -> DESTDIR/SLUG.savestate
                           (default DESTDIR=work/saves) and print the path for --state.
  list                     print the manifest.
  path SLUG                ensure-restore then print the usable .savestate path.

Example:
  tools/save_register.py register \\
    "~/Library/Application Support/StrikerX3/Ymir/savestates/D493.../0.savestate" \\
    monster-book1-list "Monster encyclopedia, book 1 selection list" \\
    --tags monster,viewer --disc-build "original-JP (input/)"
  S=$(tools/save_register.py path monster-book1-list); harness --state "$S" ...
"""
import argparse
import gzip
import json
import os
import shutil
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAVES = ROOT / "saves"
MANIFEST = SAVES / "manifest.json"
CACHE = ROOT / "work" / "saves"


def load_manifest():
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text())
    return []


def save_manifest(m):
    SAVES.mkdir(exist_ok=True)
    MANIFEST.write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n")


def cmd_register(a):
    src = Path(os.path.expanduser(a.ymir_state))
    if not src.exists():
        sys.exit(f"no such savestate: {src}")
    disc_hash = src.parent.name  # YMIR savestates/<DISCHASH>/N.savestate
    SAVES.mkdir(exist_ok=True)
    dst = SAVES / f"{a.slug}.savestate.gz"
    with open(src, "rb") as fi, gzip.open(dst, "wb", compresslevel=9) as fo:
        shutil.copyfileobj(fi, fo)
    m = [e for e in load_manifest() if e["slug"] != a.slug]
    m.append({
        "slug": a.slug,
        "file": f"saves/{a.slug}.savestate.gz",
        "description": a.description,
        "tags": [t for t in (a.tags.split(",") if a.tags else []) if t],
        "disc_hash": disc_hash,
        "disc_build": a.disc_build or "",
        "orig_ymir_path": str(src),
        "raw_bytes": src.stat().st_size,
        "added": date.today().isoformat(),
    })
    m.sort(key=lambda e: (e["disc_hash"], e["slug"]))
    save_manifest(m)
    print(f"registered {a.slug} ({disc_hash}) -> {dst.relative_to(ROOT)} "
          f"[{dst.stat().st_size} B gz]")


def restore_path(slug):
    gz = SAVES / f"{slug}.savestate.gz"
    if not gz.exists():
        sys.exit(f"not registered: {slug} (expected {gz})")
    CACHE.mkdir(parents=True, exist_ok=True)
    out = CACHE / f"{slug}.savestate"
    if not out.exists() or out.stat().st_mtime < gz.stat().st_mtime:
        with gzip.open(gz, "rb") as fi, open(out, "wb") as fo:
            shutil.copyfileobj(fi, fo)
    return out


def cmd_restore(a):
    dest = Path(a.destdir) if a.destdir else CACHE
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / f"{a.slug}.savestate"
    with gzip.open(SAVES / f"{a.slug}.savestate.gz", "rb") as fi, open(out, "wb") as fo:
        shutil.copyfileobj(fi, fo)
    print(out)


def cmd_path(a):
    print(restore_path(a.slug))


def cmd_list(a):
    for e in load_manifest():
        tags = ",".join(e.get("tags", []))
        print(f"  {e['slug']:28s} [{e['disc_hash'][:8]}] {e['description']}"
              + (f"  ({tags})" if tags else ""))


def main(argv):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("register"); r.add_argument("ymir_state"); r.add_argument("slug")
    r.add_argument("description"); r.add_argument("--tags", default="")
    r.add_argument("--disc-build", default=""); r.set_defaults(fn=cmd_register)
    s = sub.add_parser("restore"); s.add_argument("slug"); s.add_argument("destdir", nargs="?")
    s.set_defaults(fn=cmd_restore)
    pa = sub.add_parser("path"); pa.add_argument("slug"); pa.set_defaults(fn=cmd_path)
    li = sub.add_parser("list"); li.set_defaults(fn=cmd_list)
    a = p.parse_args(argv[1:])
    a.fn(a)


if __name__ == "__main__":
    main(sys.argv)
