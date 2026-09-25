# -*- coding: utf-8 -*-
"""RetroArch RZIP 세이브스테이트를 푼다.

레이아웃:
    0   "#RZIPv\x01#"        (8 B)
    8   청크 크기 (LE32)
   12   푼 뒤 전체 크기 (LE64)
   20   [LE32 압축길이][zlib 데이터] … 반복
"""
import struct
import sys
import zlib

MAGIC = b'#RZIPv\x01#'


def unpack(path):
    d = open(path, 'rb').read()
    if d[:8] != MAGIC:
        raise ValueError('RZIP 아님: %s' % d[:8])
    chunk = struct.unpack_from('<I', d, 8)[0]
    total = struct.unpack_from('<Q', d, 12)[0]
    out = bytearray()
    p = 20
    while p + 4 <= len(d) and len(out) < total:
        clen = struct.unpack_from('<I', d, p)[0]
        p += 4
        if clen == 0:
            break
        out += zlib.decompress(d[p:p + clen])
        p += clen
    if len(out) != total:
        print('경고: 크기 불일치 %d != %d' % (len(out), total), file=sys.stderr)
    return bytes(out), chunk, total


if __name__ == '__main__':
    data, chunk, total = unpack(sys.argv[1])
    out = sys.argv[2]
    open(out, 'wb').write(data)
    print('청크 %d B, 전체 %d B → %s (%d B)' % (chunk, total, out, len(data)))
