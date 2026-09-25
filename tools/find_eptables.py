# -*- coding: utf-8 -*-
"""진입점 테이블을 **일반화해서** 찾는다.

`vm_walk.entrypoints()` 는 E800 에서 확인한 **섹션 레코드 11** 을 하드코딩했다.
그런데 런타임 변수 `0x06021D28` 이 가리키는 섹션은 파일마다 다를 수 있고,
실제로 워크 도달률이 낮은 원인일 수 있다.

판정 기준: 섹션이 `[BE16 ID][BE16 오프셋]` 배열이고
  - 오프셋이 전부 스크립트 섹션 범위 안
  - `FFFF FFFF` 로 끝난다
  - 엔트리가 2개 이상
"""
import os
import struct
import sys

sys.path.insert(0, 'tools')
from script_budget import script_section, sections


def candidates(d):
    o, b, _ = script_section(d)
    out = []
    for so, sb in sections(d):
        if sb < 8 or sb > 4096 or sb % 4:
            continue
        ents, ok, ended = [], True, False
        for k in range(sb // 4):
            eid, eoff = struct.unpack_from('>HH', d, so + k * 4)
            if eid == 0xFFFF and eoff == 0xFFFF:
                ended = True
                break
            if eoff >= b:
                ok = False
                break
            ents.append((eid, eoff))
        if ok and ended and len(ents) >= 2:
            out.append((so, sb, ents))
    return o, b, out


def main():
    for f in sorted(os.listdir('work/dm')):
        if not f.endswith('.MDT'):
            continue
        d = open('work/dm/' + f, 'rb').read()
        o, b, cands = candidates(d)
        tot = sum(len(c[2]) for c in cands)
        print('%-14s 스크립트+0x%06X %6dB  진입점표 %d개, 엔트리 %d'
              % (f[6:], o, b, len(cands), tot))
        for so, sb, ents in cands:
            print('     섹션+0x%06X %4dB  %d개  예: %s'
                  % (so, sb, len(ents),
                     ' '.join('%04X→%04X' % e for e in ents[:4])))


if __name__ == '__main__':
    main()
