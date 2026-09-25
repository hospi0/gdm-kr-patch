# Step 1 — Limits & constraints (findings)

To be filled in empirically via `src/limits_probe.py` and YMIR verification. Record every
confirmed constraint here; Steps 2 and 3 depend on these being accurate.

| Constraint | Value | Confirmed? | Notes |
| --- | --- | --- | --- |
| Toolchain round-trips losslessly | yes | ✅ | E800 rebuilt byte-identical (503808) |
| `.MDT` files on disc | 36 | ✅ | via `src/iso.py list` |
| E800.MDT location | LBA 31115, 503808 B, 246 sectors | ✅ | `/FIELD/E800.MDT` |
| Next file (E804.MDT) | LBA 31361 (adjacent) | ✅ | E800 + 246 = 31361 → no gap |
| **In-place hole for E800** | **~196 bytes** | ✅ | 503808 − 503612 content; tiny |
| Disc sector format | MODE1/2352 (raw) | ✅ | inject must be sector-aware |
| Max chars per dialogue box | ? | ☐ | needs YMIR test (once we can fit text) |
| Max chars per line (8x16 font) | ? | ☐ | needs YMIR test |
| Line-wrap behavior | ? | ☐ | auto vs manual newline control code |
| Safe control codes | `0x03`, `0x07`, header `0F 03 0A 0C 00 0x` | ☐ | header low byte varies (02, 06…) |
| 44-byte offset shift | not needed for E800 | ✅ | round-trip exact without it; recheck per-MDT |

## Open questions / risks
- **In-place injection is essentially impossible for E800** (196-byte hole). Real text needs
  either single-file **relocation** to free track space or a full **track relayout**. This is
  the key gate decision for Step 1 — see `docs/step1-injection.md`.
- Confirm there is free space at the end of Track 1 to relocate files into (likely, since the
  filesystem rarely fills the whole track). `src/iso.py list` + track size will tell us.
- Whether YMIR tolerates stale EDC/ECC after sector-aware injection (expected yes; verify on
  first real build).
