# -*- coding: utf-8 -*-
"""리터럴 풀의 특정 주소를 PC 상대로 참조하는 명령을 전부 찾는다.

SH-2 `MOV.L @(disp,PC),Rn` = 1101nnnn dddddddd
   target = ((PC + 4) & ~3) + disp*4
사용: python tools/find_ref.py <리터럴이 놓인 버스주소hex> [스캔시작] [스캔끝]
"""
import struct
import sys

BASE = 0x06000000


def main():
    lit = int(sys.argv[1], 16)
    lo = int(sys.argv[2], 16) if len(sys.argv) > 2 else lit - 0x420
    hi = int(sys.argv[3], 16) if len(sys.argv) > 3 else lit + 4
    d = open('work/state_b/WorkRAMH_sw.bin', 'rb').read()

    hits = []
    for pc in range(lo, hi, 2):
        w = struct.unpack_from('>H', d, pc - BASE)[0]
        if (w >> 12) != 0xD:
            continue
        disp = w & 0xFF
        tgt = ((pc + 4) & ~3) + disp * 4
        if tgt == lit:
            hits.append((pc, (w >> 8) & 0xF))
    print('리터럴 0x%08X 를 참조하는 MOV.L @(PC) %d곳:' % (lit, len(hits)))
    for pc, rn in hits:
        print('  0x%08X  → R%d' % (pc, rn))


if __name__ == '__main__':
    main()
