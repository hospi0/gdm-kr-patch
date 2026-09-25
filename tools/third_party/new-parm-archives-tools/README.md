# New Parm Archives — Tools

Reproducible tooling and reverse-engineering notes behind the
**[Grandia: Digital Museum English translation patch](https://github.com/AngelouCurator/new-parm-archives-patch)**.

> ⚠️ **Alpha / research-grade.** These are the *original* scripts and methods docs used to build the
> patch. They intentionally **do not** redistribute third-party material: the upstream Grandia Java
> tools are *fetched* at build time (not vendored here), and **no copyrighted game data** — no disc
> images, no extracted script, no modified game assets, no derived dictionary — is included.

## What's here

- **`src/`** — the core pipeline (all original Python): disc I/O (`iso.py`), text
  extract/inject (`extract.py`, `inject.py`), MDT build + box expansion (`build_mdt.py`,
  `build_expand.py`, `relayout.py`), the xdelta patch builder (`build_delta.py`), the
  dictionary CLI + term consistency (`dict_cli.py`, `subst.py`, `validate_*`), the web review
  tool (`review_web.py`), and the **theater captioning** tooling under `src/theater/` (audio
  transcription, caption-table hooks, SH-2 loader/asm, plate graphics).
- **`tools/`** — additional original Python: battle/menu/minigame/gallery graphics + text
  authoring, MDT/format viewers and audit scripts, the headless-YMIR harness drivers
  (`jinloop.py`, `mg_loop.py`, `mg_drive.py`), and **`setup.sh`**, which *fetches* the upstream
  tools rather than bundling them.
- **`docs/`** — methods & file-format writeups: script/MDT format, the minigame and museum-viewer
  formats, the injection pipeline and its length limits, control-code font switching, theater
  captioning, and the style guide.

## Not included (by design)

The upstream Java tools, the Digital-Museum adaptation **diffs** against them, the derived
dictionary data, the verbatim Japanese `script/`, and the modified `*.MDT` game assets are **not**
in this repo. `tools/setup.sh` clones the upstream
[`GrandiaTranslation`](https://github.com/TrekkiesUnite118/GrandiaTranslation) tools into a
gitignored `tools/vendor/` and applies any diffs you place in `tools/patches/` (not shipped —
upstream is unlicensed; recreate or request them). Point the pipeline at your own disc dump via the
`GDM_BIOS` / `GDM_STATE` / `GDM_MG_STATEDIR` environment variables (the in-file defaults are
placeholders).

## Acknowledgments

Built on the reverse-engineering **methods** of
**[TrekkiesUnite118](https://github.com/TrekkiesUnite118/GrandiaTranslation)** — the Saturn
disc/text-format research, fonts, and control codes — credited with gratitude. See [`NOTICE`](NOTICE).

## Legal

Original code/docs here are MIT-licensed ([`LICENSE`](LICENSE)). No copyrighted game data or
third-party tools are redistributed; see [`NOTICE`](NOTICE).
