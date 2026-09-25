# -*- coding: utf-8 -*-
"""스크립트 VM을 실제 인터프리터 규칙대로 훑어 메시지를 찾는다.

인터프리터(`0x0601E5C4`) 실측:
  - 스크립트는 **BE16 워드 스트림**, 포인터는 워드 단위로 전진한다
  - 명령 워드의 **상위 니블이 오피코드**, 하위 12비트가 인수다
      1 → 0x0601E69C     2 → 0x0601E700 (**텍스트 출력**)   4 → 0x0601E88E
      5 → 0x0601E9F2     6 → 0x0601EA4A                     7 → 0x0601EAD6
      8 → **상대 점프**(다음 워드를 포인터에 더함)          9 → 0x0601EFA0
      F → 종료
  - 텍스트 핸들러는 명령 워드를 `0x0FFF` 로 마스크한다 → **길이는 12비트**

★ 세션2에서 이걸 `20 LL`(상위 바이트 0x20 + 8비트 길이)로 잘못 읽어,
  길이가 0x100 이상인 메시지(`0x212E` = 302바이트 등)를 전부 놓쳤다.
"""
import os
import sys

sys.path.insert(0, 'tools')
import codemap
from codemap_kanji_src import kanji_map
from script_budget import script_section

m = codemap.base_map()
m.update(kanji_map())


def messages(s):
    """[(워드오프셋, 길이, 블록바이트)] — 0x2NNN 명령을 찾는다"""
    out, p, n = [], 0, len(s) - 1
    while p < n:
        w = (s[p] << 8) | s[p + 1]
        if (w >> 12) == 2:
            L = w & 0x0FFF
            if 0 < L and p + 2 + L <= len(s):
                out.append((p, L, s[p + 2:p + 2 + L]))
                p += 2 + L
                continue
        p += 2
    return out


def main():
    tot = chars = 0
    for f in sorted(os.listdir('work/dm')):
        if not f.endswith('.MDT'):
            continue
        d = open('work/dm/' + f, 'rb').read()
        o, b, _ = script_section(d)
        msgs = messages(d[o:o + b])
        n = sum(sum(1 for x in blk if x >= 0x20) for _, _, blk in msgs)
        tot += len(msgs)
        chars += n
        print('%-14s 메시지 %4d  글자 %6d' % (f[6:], len(msgs), n))
    print('-' * 50)
    print('합계 메시지 %d개, 글자 %d자' % (tot, chars))


if __name__ == '__main__':
    main()
