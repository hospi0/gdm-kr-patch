# -*- coding: utf-8 -*-
"""제어코드 길이표의 남은 중의성을 **합의(consensus)** 로 무해화한다.

문제: 길이표 후보가 여러 개인데 정적 분석으로 끝까지 갈리지 않는다.
      틀린 자리에서 제어 인수를 글자로 오인하면 번역이 그 바이트를 덮어써 버린다.

해결: 실기로 확인할 필요 없이, **모든 후보 길이표가 「글자」라고 동의하는 바이트만**
      번역 대상으로 삼는다. 하나라도 「제어(또는 인수)」라고 하면 **불투명 보존**한다.
      → 어떤 후보가 정답이든 우리는 절대 제어 바이트를 건드리지 않는다.

후보 길이표는 아래 조건을 만족하는 것만 쓴다:
  - 282개 메시지가 전부 정확히 파싱되고 마지막이 종결자다
  - 추출문 지표(나쁜시작·낱글자런)가 기준선보다 크게 나쁘지 않다
"""
import os
import sys

sys.path.insert(0, 'tools')
import codemap
from codemap_kanji_src import kanji_map
from ctrl_quality import BAD_START, CTRL, blocks

# 세션 2에서 근거를 갖고 도출한 후보들 (docs/survey.md §9)
BASE = {b: 2 for b in CTRL}
BASE[0x07] = 1


def T(**kw):
    d = dict(BASE)
    for k, v in kw.items():
        d[int(k[1:], 16)] = v
    return d


CANDIDATES = [
    T(x01=1, x02=1, x05=1, x06=1, x09=1, x0B=1, x1A=1, x0C=3, x0E=3, x0F=3),
    T(x01=1, x02=1, x07=1, x09=1, x0C=3, x0E=3, x0F=3),
    T(x01=1, x02=1, x05=1, x06=1, x09=1, x0A=2, x0B=1, x0C=3, x0D=2, x0E=2, x0F=2),
    T(x01=1, x02=1, x0B=1, x0E=1),
    T(x01=1, x02=1, x0E=1),
    T(x01=1, x02=1, x05=1, x06=1, x09=1, x0C=3, x0E=3, x0F=3, x0D=1, x03=1, x04=1),
]


def classify(blk, L):
    """블록 각 바이트의 역할: 'T'=글자 시작/구성, 'C'=제어(또는 인수), None=파싱실패"""
    n = len(blk) - 1
    role = ['C'] * len(blk)
    i = 0
    while i < n:
        b = blk[i]
        if b >= 0x20:
            role[i] = 'T'
            i += 1
        elif 0x10 <= b <= 0x14:
            if i + 1 >= n:
                return None
            role[i] = role[i + 1] = 'T'
            i += 2
        else:
            ln = L[b]
            if i + ln > n:
                return None
            i += ln
    return role


def main():
    m = codemap.base_map()
    m.update(kanji_map())
    blks = blocks()

    good = []
    for k, L in enumerate(CANDIDATES):
        fail = sum(1 for b in blks if classify(b, L) is None)
        bad = 0
        for b in blks:
            r = classify(b, L)
            if not r:
                continue
            prev = 'C'
            i = 0
            while i < len(b) - 1:
                if r[i] == 'T':
                    c = b[i] - 0x20 if b[i] >= 0x20 else \
                        0xE0 + (b[i] - 0x10) * 256 + b[i + 1]
                    if prev == 'C' and m.get(c) in BAD_START:
                        bad += 1
                    i += 1 if b[i] >= 0x20 else 2
                    prev = 'T'
                else:
                    i += 1
                    prev = 'C'
        print('후보 %d: 파싱실패 %d, 나쁜시작 %d %s'
              % (k, fail, bad, '' if fail == 0 else '← 제외'))
        if fail == 0:
            good.append(L)
    print('채택 후보 %d개' % len(good))

    tot = agree = only_text = 0
    per_msg = []
    for b in blks:
        rs = [classify(b, L) for L in good]
        n = len(b) - 1
        cons = []
        for i in range(n):
            vals = {r[i] for r in rs}
            cons.append('T' if vals == {'T'} else 'C')
        t_all = sum(1 for r in rs for i in range(n) if r[i] == 'T')
        tot += n
        agree += sum(1 for i in range(n) if len({r[i] for r in rs}) == 1)
        only_text += cons.count('T')
        # 기준 후보(첫 번째)가 글자라 했는데 합의는 아닌 자리 = 번역에서 빼는 자리
        base_t = sum(1 for i in range(n) if rs[0][i] == 'T')
        per_msg.append((base_t, cons.count('T')))

    print()
    print('본문 바이트 %d개' % tot)
    print('  후보 전부 같은 판정 : %d (%.2f%%)' % (agree, 100.0 * agree / tot))
    print('  전부 「글자」로 합의 : %d (%.2f%%)' % (only_text, 100.0 * only_text / tot))
    lost = sum(a - b for a, b in per_msg)
    print('  기준 후보 대비 번역에서 빠지는 바이트 : %d (%.2f%%)'
          % (lost, 100.0 * lost / max(sum(a for a, _ in per_msg), 1)))
    nz = sum(1 for a, b in per_msg if a != b)
    print('  영향을 받는 메시지 : %d / %d' % (nz, len(blks)))


if __name__ == '__main__':
    main()
