# -*- coding: utf-8 -*-
"""메시지 추출 v2 — VM 워크 + 미커버 영역 선형 보완.

VM 워크(`vm_walk`)는 정확하지만 진입점 테이블만으로는 도달하지 못하는 코드가 많다
(스크립트가 다른 경로로도 호출되기 때문). 반대로 선형 스캔은 다 훑지만 오탐이 있다.

그래서 둘을 합친다:
  1) 워크로 찾은 메시지를 **확정**으로 삼고 그 구간을 커버로 표시
  2) 커버되지 않은 영역만 `0x2NNN`(12비트 길이) 선형 스캔으로 보완
  3) 보완분은 **일본어율**로 걸러 오탐을 뺀다

검증은 `verify_extract` 사상 그대로 — **메시지 밖에 일본어가 남으면 미완**이다.
"""
import os
import sys

sys.path.insert(0, 'tools')
import codemap
from codemap_kanji_src import kanji_map
from script_budget import script_section
from vm_walk import entrypoints, walk

m = codemap.base_map()
m.update(kanji_map())
KANA = set(codemap.HIRA + codemap.KATA)


def text(blk):
    out, i = [], 0
    while i < len(blk):
        b = blk[i]
        if b >= 0x20:
            out.append(m.get(b - 0x20, '?'))
            i += 1
        elif 0x10 <= b <= 0x14 and i + 1 < len(blk):
            out.append(m.get(0xE0 + (b - 0x10) * 256 + blk[i + 1], '?'))
            i += 2
        else:
            i += 1
    return ''.join(out)


JP_PUNCT = set('‥…。、・「」『』！？⁉‼～ー♪♥○※（）　 ')


def jp_ratio(t):
    """일본어다움. ⚠️ 기호·숫자만으로 이뤄진 정상 대사(「‥‥‥‥‥」, 『バール記念博物館』)를
    오탐으로 몰지 않도록 **일본어 문장부호도 일본어로 센다.**"""
    if not t:
        return 0.0
    ok = sum(1 for c in t
             if c in KANA or 0x4E00 <= ord(c) <= 0x9FFF or c in JP_PUNCT)
    return ok / len(t)


def extract(d):
    o, b, _ = script_section(d)
    s = d[o:o + b]
    msgs = dict(walk(s, entrypoints(d)))
    covered = bytearray(len(s))
    for p, blk in msgs.items():
        for i in range(p, min(len(s), p + 2 + len(blk))):
            covered[i] = 1

    # 미커버 영역 선형 보완
    p = 0
    while p < len(s) - 1:
        if covered[p] or p % 2:
            p += 2 if not p % 2 else 1
            continue
        w = (s[p] << 8) | s[p + 1]
        if (w >> 12) == 2:
            L = w & 0x0FFF
            if 0 < L and p + 2 + L <= len(s) and not any(covered[p:p + 2 + L]):
                blk = s[p + 2:p + 2 + L]
                if jp_ratio(text(blk)) >= 0.5:
                    msgs[p] = blk
                    for i in range(p, p + 2 + L):
                        covered[i] = 1
                    p += 2 + L
                    continue
        p += 2
    return o, s, msgs


def main():
    tot = chars = 0
    for f in sorted(os.listdir('work/dm')):
        if not f.endswith('.MDT'):
            continue
        d = open('work/dm/' + f, 'rb').read()
        o, s, msgs = extract(d)
        n = sum(len(text(b)) for b in msgs.values())
        tot += len(msgs)
        chars += n
        print('%-14s 메시지 %4d  글자 %6d' % (f[6:], len(msgs), n))
    print('-' * 50)
    print('합계 메시지 %d개, 글자 %d자' % (tot, chars))


if __name__ == '__main__':
    main()
