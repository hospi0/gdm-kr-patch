import sys, importlib.util
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("render_all_mod", ROOT/"work/pW6_renders/render_all.py")
# can't import render_all (it runs everything); replicate g6_pixels here
sys.path.insert(0, str(ROOT/"tools"))
import sh2emu

def g6_pixels(hyabg_bytes):
    class SH2(sh2emu.SH2):
        def _exec_at(self, pc, in_delay=False):
            op = self.m.r16(pc)
            if (op & 0xF0FF) == 0x0023 and not in_delay:
                n = (op >> 8) & 0xF
                self.steps += 1
                self._branch((pc + 4 + self.R[n]) & 0xFFFFFFFF, delay=True)
                return
            if (op & 0xF0FF) == 0x0003 and not in_delay:
                n = (op >> 8) & 0xF
                self.steps += 1
                self.PR = (pc + 4) & 0xFFFFFFFF
                self._branch((pc + 4 + self.R[n]) & 0xFFFFFFFF, delay=True)
                return
            if (op & 0xF00F) == 0x200D:
                self.steps += 1
                n = (op >> 8) & 0xF
                m2 = (op >> 4) & 0xF
                self.R[n] = ((self.R[m2] << 16) | (self.R[n] >> 16)) & 0xFFFFFFFF
                return
            super()._exec_at(pc, in_delay)
    dump = ROOT / "work/pD_nav/g6re/dump471"
    lw = bytearray((dump / "bp-wram-lo.bin").read_bytes())
    lw[0xC0000:0xC0000 + len(hyabg_bytes)] = hyabg_bytes
    mem = sh2emu.Mem()
    mem.map(0x06000000, (dump / "bp-wram-hi.bin").read_bytes())
    mem.map(0x00200000, bytes(lw))
    mem.map(0x25C00000, bytes(0x80000))
    cpu = SH2(mem)
    cpu.R[4] = 0x25C50000; cpu.R[5] = 0x002E9E9C; cpu.R[6] = 0; cpu.R[7] = 0x0000FD80
    cpu.R[15] = 0x25C7F000
    try:
        cpu.run(0x0601A716, max_steps=60_000_000)
    except Exception as e:
        print("  g6 decode stop:", e)
    return mem.region(0x25C00000)[0x50000:0x50000 + 256*104]

if __name__ == "__main__":
    src = Path(sys.argv[1]); out = Path(sys.argv[2])
    pix = g6_pixels(src.read_bytes())
    out.write_bytes(pix)
    print(f"decoded {src} -> {out} ({len(pix)}B, nonzero {sum(1 for p in pix if p)})")
