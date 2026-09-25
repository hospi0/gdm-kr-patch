# -*- coding: utf-8 -*-
"""스크립트 인터프리터를 코드 지문으로 찾는다.

지문:
  - `ADD #0xE0, Rn` (= -0x20)   글자 코드 = 바이트 - 0x20
  - `ADD #0xF0, Rn` (= -0x10)   이스케이프 판정 0x10~0x14
  - `CMP/EQ #0x07`              메시지 종결자
  - `MOV #0x20, Rn`             글자 경계 상수
둘 이상이 가까이 모여 있으면 인터프리터일 가능성이 높다.
"""
import struct
import sys

BASE = 0x06000000
LO, HI = 0x06000000, 0x060E0000


def main():
    d = open('work/state_b/WorkRAMH_sw.bin', 'rb').read()
    marks = {}          # 주소 → 지문 이름
    for pc in range(LO, min(HI, BASE + len(d)) - 2, 2):
        w = struct.unpack_from('>H', d, pc - BASE)[0]
        op = w >> 12
        if op == 0x7:                       # ADD #imm,Rn
            imm = w & 0xFF
            rn = (w >> 8) & 0xF
            if rn == 15:                    # ⚠️ R15 는 스택 포인터 — 프레임 조정이지 지문이 아니다
                continue
            if imm == 0xE0:
                marks[pc] = 'ADD #-0x20'
            elif imm == 0xF0:
                marks[pc] = 'ADD #-0x10'
        elif op == 0xE:                     # MOV #imm,Rn
            if (w & 0xFF) == 0x20:
                marks[pc] = 'MOV #0x20'
        elif (w & 0xFF00) == 0x8800:        # CMP/EQ #imm,R0
            if (w & 0xFF) == 0x07:
                marks[pc] = 'CMP/EQ #7'
            elif (w & 0xFF) == 0x20:
                marks[pc] = 'CMP/EQ #0x20'

    # 128바이트 창 안에 서로 다른 지문이 3종 이상 모인 곳
    addrs = sorted(marks)
    print('지문 %d개' % len(addrs))
    best = []
    for i, a in enumerate(addrs):
        win = [x for x in addrs[i:] if x - a <= 128]
        kinds = {marks[x] for x in win}
        if len(kinds) >= 3:
            best.append((a, len(win), sorted(kinds)))
    # 겹치는 것 정리
    out, last = [], -999
    for a, n, k in best:
        if a - last < 128:
            continue
        last = a
        out.append((a, n, k))
    print('후보 %d곳:' % len(out))
    for a, n, k in out:
        print('  0x%08X  지문 %d개  %s' % (a, n, k))


if __name__ == '__main__':
    main()
