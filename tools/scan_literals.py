# -*- coding: utf-8 -*-
"""SH-2 모듈의 리터럴 풀에서 하드웨어/메모리 주소 상수를 찾는다.

목적: 텍스트 블릿 루틴을 짚는다. 대사 차분으로 확인된 블릿 목적지는
VDP2 VRAM 오프셋 0x8000대와 0x4000대(버스 0x25E08000 / 0x25E04000)다.
그 상수를 리터럴로 들고 있는 코드가 블릿 루틴이거나 그 호출자다.

새턴 주소는 캐시/비캐시 별칭이 있으므로 하위 27비트로 비교한다.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iso9660 as I

TRACK1 = (r'C:/claude/roms/ss/Grandia - Digital Museum (Japan) (Rev A) (10M)'
          r'/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin')

RANGES = [
    ('VDP1_VRAM', 0x05C00000, 0x05C80000),
    ('VDP1_FB', 0x05C80000, 0x05CC0000),
    ('VDP1_reg', 0x05D00000, 0x05D00040),
    ('VDP2_VRAM', 0x05E00000, 0x05E80000),
    ('VDP2_CRAM', 0x05F00000, 0x05F01000),
    ('VDP2_reg', 0x05F80000, 0x05F80120),
    ('WRAM_Lo', 0x00200000, 0x00300000),
    ('WRAM_Hi', 0x06000000, 0x06100000),
]

# 조사 대상: 상주 확인된 모듈 (파일, 적재 버스주소)
MODULES = [
    ('/FIELD/FIELD.BIN', 0x0602C000),
    ('/0', 0x0600A000),
    ('/BIN/TESTM.BIN', 0x0606C224),
    ('/FIELD/MGAME.BIN', 0x060643E4),
    ('/FIELD/SAVER.BIN', 0x06029F50),
    ('/FIELD/CMDMN.BIN', 0x0602C000),
    ('/FIELD/SHOP.BIN', 0x0602C000),
]


def label(v):
    """실제 새턴 주소 리터럴만 인정한다.

    ⚠️ 하위 27비트만 보고 판정하면 SH-2 명령어 워드가 대량으로 주소처럼 보인다
    (예: 0x65E3430B = `mov r14,r5` + `jsr @r3`). 상위 니블이 캐시(0x0)/
    비캐시(0x2) 별칭인 경우만 통과시킨다.
    """
    top = v >> 28
    if top not in (0x0, 0x2):
        return None, v
    m = v & 0x0FFFFFFF
    for name, lo, hi in RANGES:
        if lo <= m < hi:
            return name, m
    return None, m


def main():
    buf = I.load_track(TRACK1)
    files = I.list_files(buf)
    out = open('work/literals.txt', 'w', encoding='utf-8')

    def say(s):
        print(s, flush=True)
        out.write(s + '\n')

    for path, base in MODULES:
        if path not in files:
            say('없음 %s' % path)
            continue
        d = I.read_range(buf, *files[path])
        say('')
        say('===== %s  (%d B, 적재 0x%08X) =====' % (path, len(d), base))
        counts = {}
        hits = []
        for off in range(0, len(d) - 3, 4):
            v = struct.unpack_from('>I', d, off)[0]
            name, m = label(v)
            if not name:
                continue
            counts[name] = counts.get(name, 0) + 1
            if name.startswith('VDP'):
                hits.append((off, v, name, m))
        say('  하드웨어/메모리 상수 개수: %s' % counts)
        for off, v, name, m in hits[:60]:
            say('   파일오프 0x%06X (버스 0x%08X)  값 0x%08X  %s+0x%X'
                % (off, base + off, v, name, m - dict(
                    (n, lo) for n, lo, _ in RANGES)[name]))
    out.close()


if __name__ == '__main__':
    main()
