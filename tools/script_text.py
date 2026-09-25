# -*- coding: utf-8 -*-
"""전 MDT의 대사를 읽을 수 있는 텍스트로 뽑는다.

인코딩(docs/survey.md §7):
  0x20~0xFF     → 폰트 코드 = 바이트 − 0x20
  0x10~0x14     → 2바이트, 폰트 코드 = 0xE0 + (b−0x10)*256 + 다음바이트
  그 외          → 제어코드 (`{XX}` 로 표기)

코드 → 글자는 `codemap.py`(가나·기호) + `codemap_kanji_src.py`(한자).
대응이 없는 코드는 `<0x???>` 로 남긴다 — 이게 남아 있으면 대응표가 덜 된 것이다.
"""
import os
import sys

sys.path.insert(0, 'tools')
import codemap
from codemap_kanji_src import kanji_map
from script_budget import script_section
from script_render import messages

OUT = 'work/script_ja.txt'


def full_map():
    m = codemap.base_map()
    m.update(kanji_map())
    return m


def decode_block(blk, m):
    out, i = [], 0
    unknown = []
    while i < len(blk):
        b = blk[i]
        if b >= 0x20:
            c = b - 0x20
            i += 1
        elif 0x10 <= b <= 0x14 and i + 1 < len(blk):
            c = 0xE0 + (b - 0x10) * 256 + blk[i + 1]
            i += 2
        else:
            out.append('{%02X}' % b)
            i += 1
            continue
        ch = m.get(c)
        if ch is None:
            out.append('<%03X>' % c)
            unknown.append(c)
        else:
            out.append(ch)
    return ''.join(out), unknown


def main():
    m = full_map()
    f = open(OUT, 'w', encoding='utf-8')
    total = 0
    unk = {}
    for name in sorted(os.listdir('work/dm')):
        if not name.endswith('.MDT'):
            continue
        d = open('work/dm/' + name, 'rb').read()
        o, b, _ = script_section(d)
        s = d[o:o + b]
        msgs = messages(s)
        if not msgs:
            continue
        f.write('=== %s  (섹션 +0x%06X, %d B, 메시지 %d개)\n'
                % (name[6:], o, b, len(msgs)))
        for p, blk in msgs:
            txt, u = decode_block(blk, m)
            for c in u:
                unk[c] = unk.get(c, 0) + 1
            f.write('[+0x%04X %3dB] %s\n' % (p, len(blk), txt))
            total += 1
        f.write('\n')
    f.close()
    print('%s — 메시지 %d개' % (OUT, total))
    if unk:
        print('대응 없는 코드 %d종: %s'
              % (len(unk), sorted('%03X:%d' % (c, n) for c, n in unk.items())[:20]))
    else:
        print('대응 없는 코드 0 — 대응표가 전 대사를 덮는다')


if __name__ == '__main__':
    main()
