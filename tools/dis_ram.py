# -*- coding: utf-8 -*-
"""세이브스테이트의 Work RAM을 버스 주소 기준으로 디스어셈블한다.

디스어셈블 코어는 terra-kr-patch/tools/sh2_disasm.py를 재사용한다.
사용: python tools/dis_ram.py <버스주소hex> <바이트수hex> [상태디렉터리]
"""
import os
import struct
import sys

sys.path.insert(0, r'C:\claude\project\terra-kr-patch\tools')
from sh2_disasm import disasm_sh2

REGIONS = [
    (0x06000000, 0x100000, 'WorkRAMH_sw'),
    (0x00200000, 0x100000, 'WorkRAML_sw'),
]


def load(bus, size, sdir):
    for base, ln, name in REGIONS:
        if base <= bus < base + ln:
            d = open(os.path.join(sdir, name + '.bin'), 'rb').read()
            o = bus - base
            return d[o:o + size]
    raise SystemExit('알 수 없는 주소 0x%08X' % bus)


def annotate(lines, code, base):
    """`@(0xNN,pc)` 리터럴을 실제 값으로 풀어 붙인다."""
    out = []
    for ln in lines:
        addr = int(ln.split(':')[0], 16)
        out.append(ln)
        if 'PC+' in ln or '(PC' in ln:
            pass
    return out


def main():
    bus = int(sys.argv[1], 16)
    size = int(sys.argv[2], 16)
    sdir = sys.argv[3] if len(sys.argv) > 3 else 'work/state_b'
    code = load(bus, size, sdir)
    lines = disasm_sh2(code, bus, max_instr=size // 2)
    # 리터럴 풀 값 붙이기
    for addr, w, ins in lines:
        extra = ''
        if 'PC+' in ins:
            try:
                off = int(ins.split('PC+')[1].split(')')[0], 0)
                long = 'MOV.L' in ins
                la = (((addr + 4) & ~3) + off) if long else (addr + 4 + off)
                i = la - bus
                if 0 <= i + 4 <= len(code):
                    if long:
                        v = struct.unpack_from('>I', code, i)[0]
                        tag = ''
                        if 0x06000000 <= v < 0x06100000:
                            tag = ' WRAM-Hi'
                        elif 0x00200000 <= v < 0x00300000:
                            tag = ' WRAM-Lo'
                        elif 0x25C00000 <= v < 0x25E00000:
                            tag = ' VDP1_VRAM'
                        elif 0x25E00000 <= v < 0x25F00000:
                            tag = ' VDP2_VRAM'
                        elif 0x25F00000 <= v < 0x25F01000:
                            tag = ' VDP2_CRAM'
                        extra = '   => 0x%08X%s' % (v, tag)
                    else:
                        extra = '   => 0x%04X' % struct.unpack_from('>H', code, i)[0]
            except Exception:
                pass
        print('%08X: %04X  %s%s' % (addr, w, ins, extra))


if __name__ == '__main__':
    main()
