# -*- coding: utf-8 -*-
"""스크립트 VM 을 **진입점부터 실제로 워크**해 메시지를 정확히 열거한다.

인터프리터 `0x0601E5C4` 실측 결과 (docs/survey.md §13):
  스크립트 = BE16 워드 스트림, 명령 워드의 **상위 니블 = 오피코드**.

| op | 핸들러 | 인수 소비 |
|----|--------|-----------|
| 1 | `E69C` | **조건부** 0 또는 1워드 (명령비트0 · 런타임 상태에 따름) → 상대 점프 |
| 2 | `E700` | **텍스트** — 명령워드 `&0x0FFF` 바이트 (`0x0601E71E` 에서 마스크) |
| 4 | `E88E` | **조건부** 0 또는 1워드 |
| 5 | `E9F2` | 1워드 (무조건, `0x0601E9FC`) |
| 6 | `EA4A` | 0워드 (포인터를 안 건드린다) |
| 7 | `EAD6` | 1워드 (무조건, `0x0601EAEC`) |
| 8 | 인라인 | 1워드 — 그 값을 포인터에 더함 (**상대 점프**) |
| 9 | `EFA0` | 1워드 (`0x0601EFE6`) |
| F | 인라인 | 종료 |
| 그 외 | — | 0워드 |

조건부 소비(op 1·4)와 점프가 있으므로 **단일 경로 실행이 아니라 워크리스트로
도달 가능한 모든 명령 위치**를 모은다. 그래야 텍스트를 하나도 안 놓친다.
"""
import os
import struct
import sys

sys.path.insert(0, 'tools')
import codemap
from codemap_kanji_src import kanji_map

m = codemap.base_map()
m.update(kanji_map())

# 인수 워드 수
#   op1 : 런타임 상태(0x06021CF3 비트1)에 따라 0 또는 1 — **정적 판정 불가**.
#         인수를 먹는 해석만 따라간다(안 먹는 쪽을 따라가면 인수 워드를 명령으로 오독한다).
#         단 명령워드 비트0 이 서 있으면 확정적으로 0워드다(`0x0601E6B0` TST #1).
#   op4 : **명령워드 비트11(0x800)** 로 정적 판정 (`0x0601E898` 마스크 0x800)
#         비트가 서면 0워드, 아니면 1워드.
ARGW = {0x1: 'COND1', 0x2: 'TEXT', 0x4: 'COND4', 0x5: 1, 0x6: 0,
        0x7: 1, 0x8: 'JUMP', 0x9: 1, 0xF: 'END'}


def entrypoints(d):
    """진입점 테이블 = `[BE16 ID][BE16 스크립트섹션내 오프셋]` × N, `FFFFFFFF` 로 끝.

    ⚠️ 처음엔 **섹션 레코드 11** 로 하드코딩했는데(E800 에서 확인한 값), 파일마다
       인덱스가 다르다. 2000.MDT 는 이 때문에 진입점을 22개만 보고 98개를 놓쳐
       워크 도달률이 낮았다. → 형식으로 찾는다.
    """
    from find_eptables import candidates
    _, _, cands = candidates(d)
    out = []
    for so, sb, ents in cands:
        out += [eoff for _, eoff in ents]
    return sorted(set(out))


def walk(s, starts):
    """도달 가능한 명령 위치를 모아 텍스트 블록 목록을 낸다.

    ⚠️ **인수 워드를 명령 시작으로 탐색하면 안 된다.** 그러면 같은 문장을 한두 워드씩
       밀려서 중복으로 잡고(E800 +0x07A0/+0x07C0/+0x07D8 사례), 오염이 퍼져
       무작위 문자열까지 '메시지'가 된다.
       → 인수로 소비된 워드는 `argw` 에 표시하고 명령 후보에서 제외한다.
       → 조건부(op 1·4)도 **인수를 먹는 해석을 우선**하고, 안 먹는 경로는
         그 워드가 인수로 안 쓰인 경우에만 탐색한다.
    """
    n = len(s)
    seen, argw = set(), set()
    msgs = {}
    stack = [p for p in starts if 0 <= p < n - 1 and p % 2 == 0]
    order = []
    while stack:
        p = stack.pop()
        if p in seen or p < 0 or p + 2 > n or p % 2:
            continue
        seen.add(p)
        order.append(p)
        w = (s[p] << 8) | s[p + 1]
        op = w >> 12
        kind = ARGW.get(op, 0)
        if kind == 'END':
            continue
        if kind == 'TEXT':
            L = w & 0x0FFF
            if L == 0 or p + 2 + L > n:
                continue
            msgs[p] = s[p + 2:p + 2 + L]
            for q in range(p + 2, p + 2 + L, 2):
                argw.add(q)
            nxt = p + 2 + L
            stack.append(nxt + (nxt % 2))
            continue
        if kind == 'JUMP':
            if p + 4 > n:
                continue
            argw.add(p + 2)
            d16 = (s[p + 2] << 8) | s[p + 3]
            stack.append((p + 4 + d16) & ~1)
            continue
        if kind == 'COND1':                         # op1: 비트0 서면 0워드, 아니면 인수+점프
            if w & 1 or p + 4 > n:
                stack.append(p + 2)
                continue
            argw.add(p + 2)
            d16 = ((s[p + 2] << 8) | s[p + 3]) & 0x0FFF
            stack.append(p + 4)
            stack.append((p + 4 + d16) & ~1)
            continue
        if kind == 'COND4':                         # op4: 비트11(0x800) 로 정적 판정
            if w & 0x800 or p + 4 > n:
                stack.append(p + 2)
                continue
            argw.add(p + 2)
            stack.append(p + 4)
            continue
        for k in range(kind):
            argw.add(p + 2 + k * 2)
        stack.append(p + 2 + kind * 2)

    # 인수로 쓰인 워드에서 시작한 '명령'은 오탐이므로 버린다
    return {p: b for p, b in msgs.items() if p not in argw}


def main():
    tot = chars = 0
    for f in sorted(os.listdir('work/dm')):
        if not f.endswith('.MDT'):
            continue
        d = open('work/dm/' + f, 'rb').read()
        eps = entrypoints(d)
        if not eps:
            print('%-14s 진입점 없음' % f[6:])
            continue
        # 스크립트 섹션 = 진입점이 가리키는 섹션(레코드 12 계열). 헤더에서 크기를 찾는다.
        from script_budget import script_section
        o, b, _ = script_section(d)
        s = d[o:o + b]
        msgs = walk(s, eps)
        n = sum(sum(1 for x in blk if x >= 0x20) for blk in msgs.values())
        tot += len(msgs)
        chars += n
        print('%-14s 진입점 %2d  메시지 %4d  글자 %6d' % (f[6:], len(eps), len(msgs), n))
    print('-' * 56)
    print('합계 메시지 %d개, 글자 %d자' % (tot, chars))


if __name__ == '__main__':
    main()
