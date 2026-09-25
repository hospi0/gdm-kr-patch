# -*- coding: utf-8 -*-
"""글리프 스테이징 버퍼(0x06020000대)를 가리키는 포인터 변수와,
그 변수를 참조하는 코드 위치를 찾는다.

경로:
  1) RAM에서 값이 0x0601FF00~0x06020200인 BE32 워드를 찾는다 → 포인터 변수 후보
  2) 각 후보 '변수 주소'를 리터럴로 들고 있는 모듈 코드를 찾는다 → 참조 코드
  3) 그 지점을 디스어셈블하면 글리프 전개기에 닿는다
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iso9660 as I

TRACK1 = (r'C:/claude/roms/ss/Grandia - Digital Museum (Japan) (Rev A) (10M)'
          r'/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin')
LO, HI = 0x0601FF00, 0x06020200

MODULES = [
    ('/FIELD/FIELD.BIN', 0x0602C000), ('/0', 0x0600A000),
    ('/FIELD/MWIN6.BIN', 0x0601BC94), ('/BIN/TESTM.BIN', 0x0606C224),
    ('/FIELD/MGAME.BIN', 0x060643E4), ('/FIELD/SAVER.BIN', 0x06029F50),
    ('/FIELD/CNFIG.BIN', 0x06002D60), ('/FIELD/ITGET.BIN', 0x060009E8),
    ('/FIELD/SHOP.BIN', 0x05FFF71C), ('/FIELD/CMDMN.BIN', 0x05FFA130),
    ('/BIN/SUEWN.BIN', 0x05FFAC04), ('/FIELD/SUEWN.BIN', 0x06014D80),
]


def main():
    out = open('work/trace_stage.txt', 'w', encoding='utf-8')

    def say(s):
        print(s, flush=True)
        out.write(s + '\n')

    # 1) 포인터 변수 후보
    varaddrs = []
    for tag, base in (('WorkRAMH_sw', 0x06000000), ('WorkRAML_sw', 0x00200000)):
        mem = open('work/state_b/%s.bin' % tag, 'rb').read()
        for off in range(0, len(mem) - 3, 4):
            v = struct.unpack_from('>I', mem, off)[0]
            if LO <= v < HI:
                varaddrs.append((base + off, v, tag))
    say('스테이징 버퍼를 가리키는 포인터 변수 후보 %d개' % len(varaddrs))
    for a, v, tag in varaddrs[:30]:
        say('   변수 0x%08X = 0x%08X   (%s)' % (a, v, tag))

    # 2) 그 변수 주소를 리터럴로 든 코드
    buf = I.load_track(TRACK1)
    files = I.list_files(buf)
    want = {a for a, _, _ in varaddrs}
    say('')
    say('== 변수 주소를 리터럴로 참조하는 코드 ==')
    found = 0
    for path, base in MODULES:
        if path not in files:
            continue
        d = I.read_range(buf, *files[path])
        for off in range(0, len(d) - 3, 4):
            v = struct.unpack_from('>I', d, off)[0]
            if v in want or (v & 0x0FFFFFFF) | 0x00000000 in want:
                say('   %-22s 파일오프 0x%06X (버스 0x%08X) → 변수 0x%08X'
                    % (path, off, base + off, v))
                found += 1
    say('참조 %d건' % found)
    out.close()


if __name__ == '__main__':
    main()
