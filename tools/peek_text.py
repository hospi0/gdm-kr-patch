# -*- coding: utf-8 -*-
"""DM 텍스트 후보 파일의 인코딩·구조를 눈으로 확인한다.

판정 대상:
  - 앞머리가 오프셋 테이블인가(BE16/LE16 오름차순)?
  - 본문이 Shift-JIS인가, 자체 코드인가?
"""
import sys
import os
import struct

CANDS = [
    'work/dm/BATLE_TEXT2.BIN',
    'work/dm/FIELD_TEXT2.BIN',
    'work/dm/BIN_MES1B.DAT',
    'work/dm/BIN_MES1C.DAT',
    'work/dm/FIELD_MTMES.DAT',
    'work/dm/BATLE_SYS_B.STB',
    'work/dm/FIELD_SYS_F.STB',
    'work/dm/BIN_SYS_T.STB',
]


def sjis_score(data):
    """Shift-JIS 2바이트 문자로 해석 가능한 비율(거칠게)."""
    ok = tot = 0
    i = 0
    while i < len(data) - 1:
        c = data[i]
        if 0x81 <= c <= 0x9F or 0xE0 <= c <= 0xEF:
            d = data[i + 1]
            tot += 1
            if 0x40 <= d <= 0xFC and d != 0x7F:
                ok += 1
            i += 2
        else:
            i += 1
    return ok, tot


def try_decode(data, enc='cp932'):
    out = []
    i = 0
    while i < len(data):
        c = data[i]
        if 0x81 <= c <= 0x9F or 0xE0 <= c <= 0xEF:
            try:
                out.append(data[i:i + 2].decode(enc))
            except Exception:
                out.append('.')
            i += 2
        elif 0x20 <= c < 0x7F:
            out.append(chr(c))
            i += 1
        else:
            out.append('<%02X>' % c)
            i += 1
    return ''.join(out)


def main():
    # 콘솔이 CP949라 일본어를 못 찍는다 → UTF-8 파일로 내보낸다.
    rep = open('work/peek_text.txt', 'w', encoding='utf-8')

    def emit(s):
        print(s.encode('ascii', 'replace').decode('ascii'))
        rep.write(s + '\n')

    for p in CANDS:
        if not os.path.exists(p):
            emit('없음 %s' % p)
            continue
        d = open(p, 'rb').read()
        be32 = struct.unpack_from('>8I', d, 0)
        ok, tot = sjis_score(d)
        emit('== %s  (%d B)' % (os.path.basename(p), len(d)))
        emit('   head hex : %s' % d[:24].hex())
        emit('   BE32[0:8]: %s' % [hex(v) for v in be32])
        emit('   BE32 오름차순·파일내 여부: %s'
             % all(0 <= be32[i] <= be32[i + 1] <= len(d) for i in range(7)))
        emit('   SJIS 2바이트 후보 %d개 중 유효 %d (%.0f%%)'
              % (tot, ok, 100.0 * ok / tot if tot else 0))
        # 첫 포인터가 가리키는 곳을 본문으로 본다
        start = be32[1] if 0 < be32[1] < len(d) else 0x100
        emit('   본문(0x%X) : %s' % (start, try_decode(d[start:start + 140])))
        print()


if __name__ == '__main__':
    main()
