# -*- coding: utf-8 -*-
"""트랙 전체를 메모리에 올리지 않고 LBA 지점만 직접 읽는다.

사용: python tools/peek_lba.py <lba> <크기> [출력파일]
"""
import sys

TRACK1 = (r'C:/claude/roms/ss/Grandia - Digital Museum (Japan) (Rev A) (10M)'
          r'/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin')
SECTOR, DATA_OFF, DATA_LEN = 2352, 16, 2048


def read(lba, size):
    out = bytearray()
    with open(TRACK1, 'rb') as f:
        while len(out) < size:
            f.seek(lba * SECTOR + DATA_OFF)
            c = f.read(DATA_LEN)
            if not c:
                break
            out += c
            lba += 1
    return bytes(out[:size])


if __name__ == '__main__':
    lba, size = int(sys.argv[1]), int(sys.argv[2])
    d = read(lba, size)
    if len(sys.argv) > 3:
        open(sys.argv[3], 'wb').write(d)
        print('%d B → %s' % (len(d), sys.argv[3]))
    else:
        for i in range(0, min(len(d), 512), 16):
            row = d[i:i + 16]
            print('%06X  %-47s  %s' % (
                i, ' '.join('%02X' % b for b in row),
                ''.join(chr(b) if 32 <= b < 127 else '.' for b in row)))
