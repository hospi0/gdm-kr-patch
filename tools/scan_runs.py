# -*- coding: utf-8 -*-
"""메시지 경계를 쓰지 않고 **텍스트 런**만 찾는다.

세션2에서 메시지 컨테이너 구조를 두 번 잘못 확립했다(`20 LL` + 종결자 규칙).
구조 추측을 또 얹는 대신, 구조에 의존하지 않는 방식으로 간다:

  스크립트 섹션에서 **연속된 글자 코드**를 런으로 잡는다.
    - 0x20~0xFF        → 1바이트 글자 (코드 = 바이트 - 0x20)
    - 0x10~0x14 + 1B   → 2바이트 한자 이스케이프
    - 그 밖(<0x10, 0x15~0x1F) → 런 종료
  런이 일본어로 읽히면 번역 대상이다.

번역은 **런을 같은 바이트 길이로 제자리 교체**한다. 길이를 안 바꾸므로
메시지 블록 길이·조건부 스킵·섹션 크기 무엇도 건드리지 않는다.
"""
import os
import sys

sys.path.insert(0, 'tools')
import codemap
from codemap_kanji_src import kanji_map
from script_budget import script_section

m = codemap.base_map()
m.update(kanji_map())
KANA = set(codemap.HIRA + codemap.KATA)


def runs(s, minlen=3):
    """[(시작offset, 바이트길이, 코드리스트)]"""
    out, i, n = [], 0, len(s)
    cur, start = [], None
    while i < n:
        b = s[i]
        if b >= 0x20:
            if start is None:
                start = i
            cur.append(b - 0x20)
            i += 1
        elif 0x10 <= b <= 0x14 and i + 1 < n:
            if start is None:
                start = i
            cur.append(0xE0 + (b - 0x10) * 256 + s[i + 1])
            i += 2
        else:
            if start is not None and len(cur) >= minlen:
                out.append((start, i - start, cur))
            cur, start = [], None
            i += 1
    if start is not None and len(cur) >= minlen:
        out.append((start, n - start, cur))
    return out


def text(codes):
    return ''.join(m.get(c, '?') for c in codes)


def is_jp(t):
    k = sum(1 for c in t if c in KANA or 0x4E00 <= ord(c) <= 0x9FFF)
    return k >= max(2, len(t) * 0.35)


def main():
    tot = totjp = chars = 0
    for f in sorted(os.listdir('work/dm')):
        if not f.endswith('.MDT'):
            continue
        d = open('work/dm/' + f, 'rb').read()
        o, b, _ = script_section(d)
        s = d[o:o + b]
        rs = runs(s)
        jp = [r for r in rs if is_jp(text(r[2]))]
        tot += len(rs)
        totjp += len(jp)
        chars += sum(len(r[2]) for r in jp)
        print('%-14s 런 %4d / 일본어 런 %4d / 글자 %5d'
              % (f[6:], len(rs), len(jp), sum(len(r[2]) for r in jp)))
    print('-' * 60)
    print('합계: 일본어 런 %d개, 글자 %d자 (전체 런 %d)' % (totjp, chars, tot))


if __name__ == '__main__':
    main()
