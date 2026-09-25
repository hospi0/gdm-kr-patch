# -*- coding: utf-8 -*-
"""Mednafen(Beetle Saturn) 세이브스테이트에서 큰 메모리 블록을 꺼낸다.

레코드 형식(관측): [u8 이름길이][이름][u32 LE 바이트수][데이터]
  예: 04 "VRAM" 00 00 08 00 → 512 KB VDP1 VRAM

이름이 겹치므로(VRAM이 VDP1/VDP2 양쪽에 있음) 등장 순서로 구분한다.
"""
import os
import struct
import sys

MIN_DUMP = 4096


def records(d):
    """가능한 레코드를 전수 훑어 (오프셋, 이름, 크기, 데이터시작)을 낸다."""
    out = []
    n = len(d)
    i = 0
    while i < n - 6:
        ln = d[i]
        if 2 <= ln <= 40:
            name = d[i + 1:i + 1 + ln]
            if all(32 <= c < 127 for c in name):
                size = struct.unpack_from('<I', d, i + 1 + ln)[0]
                start = i + 1 + ln + 4
                if 0 < size <= n - start:
                    out.append((i, name.decode(), size, start))
                    if size >= MIN_DUMP:
                        i = start + size
                        continue
        i += 1
    return out


def main():
    d = open('work/state.bin', 'rb').read()
    recs = [r for r in records(d) if r[2] >= MIN_DUMP]
    os.makedirs('work/state', exist_ok=True)
    seen = {}
    print('%-18s %-10s %s' % ('이름', '크기', '데이터오프셋'))
    for off, name, size, start in recs:
        k = seen.get(name, 0)
        seen[name] = k + 1
        tag = '%s%s' % (name, ('_%d' % k) if k else '')
        safe = ''.join(c if c.isalnum() or c == '_' else '_' for c in tag)
        path = 'work/state/%s.bin' % safe
        open(path, 'wb').write(d[start:start + size])
        print('%-18s %-10d 0x%08X  -> %s' % (name, size, start, path))


if __name__ == '__main__':
    main()
