# -*- coding: utf-8 -*-
r"""GDM 반각 8×8 한글 글리프(2026-10-16) — AWW hangul8comp 바탕, 고정 폭 8 에 맞춘 손질.
  · ㅔ/ㅖ: hangul8comp 은 ㅐ 와 같은 그림. ㅐ 자리(4·6열 세로획 + 5열 연결)를 그대로 두면 짧은 획을 넣을
    빈 열이 없다 → ㅔ 글자만 자음을 3칸 폭(0‥2열)으로 줄이고 3열 = 짧은 획(ㅓ), 4·6열 = 세로획.
  · ㅎ(4×4 칸 = 받침 있는 세로 모음 글자): 획 래스터가 동그라미 아래를 못 닫아 «힘»이 «침»으로 보임 → 리터럴.
  · 그림자 없음(사용자 2026-10-16 «가시성만 좋으면 그림자 필요없음») — 몸 한 색(색인 E), 7열은 자간.
  glyph(ch) → 8×8 0/1 행렬. cell4(ch) → 4bpp 색인 행렬.
"""
import sys
sys.path.append(r'C:\claude\project\aww-kr-patch\tools')   # 맨 뒤 — 앞에 두면 같은 이름 도구(sh2sim 등)를 가로챈다
import hangul8comp as hc

_H4 = ['.##.', '####', '#..#', '.##.']
_B4 = ['#..#', '####', '#..#', '####']
_SS3 = ['.#...#.', '.#...#.', '#.#.#.#']
_E = {5: 1, 7: 2}            # ㅔ → 짧은 획 1개, ㅖ → 2개


def glyph(ch):
    o = ord(ch) - 0xAC00
    if not 0 <= o < 11172:
        raise ValueError(ch)
    cho, jung, jong = o // 588, (o // 28) % 21, o % 28
    if jung in _E:
        g = [[0] * 8 for _ in range(8)]
        c, jg = hc.decompose(ch)[0], hc.decompose(ch)[2]
        if jong:
            hc._put(g, hc.CHO, c, (0, 0, 3, 4))
            top, bot = 0, 4
            if jg in hc.LIT_JONG7:
                hc._lit(g, hc.LIT_JONG7[jg], 0, 5)
            else:
                hc._put(g, hc.JONG, jg, (1, 5, 5, 3))
        else:
            hc._put(g, hc.CHO, c, (0, 1, 3, 6))
            top, bot = 0, 7
        for y in range(top, bot + 1):
            g[y][4] = g[y][6] = 1
        mid = (top + bot) // 2
        want = [mid] if _E[jung] == 1 else [top + (bot - top) // 3, top + 2 * (bot - top) // 3 + 1]
        free = [y for y in range(top + 1, bot) if not g[y][2]]      # 자음 오른쪽 끝(2열)이 빈 줄이라야 획이 안 붙는다
        used = set()
        for w in want:
            cand = [y for y in free if y not in used and all(abs(y - u) > 1 for u in used)]
            y = min(cand, key=lambda y: abs(y - w)) if cand else w
            used.add(y)
            g[y][3] = 1
        return g
    g = [list(r) for r in hc.glyph8(ch)]
    vert = jung in (0, 1, 2, 3, 4, 6, 20)
    if cho == 18 and vert and jong:                      # ㅎ + 세로 모음 + 받침 → 4×4 칸
        for y in range(4):
            for x in range(4):
                g[y][x] = 1 if _H4[y][x] == '#' else 0
    if cho == 7 and vert and jong:                       # ㅂ 4×4: 아래 두 줄이 다 차서 «발»이 «글»로 보임(2026-10-16 실기)
        for y in range(4):
            for x in range(4):
                g[y][x] = 1 if _B4[y][x] == '#' else 0
    if cho == 10 and jung in (8, 12, 13, 17, 18) and not jong:   # ㅆ + 가로 모음(ㅗㅛㅜㅠㅡ): 위 3줄 + 빈 줄(«쏘» 실기 «이상함»)
        for y in range(4):
            for x in range(8):
                g[y][x] = 1 if y < 3 and x < len(_SS3[y]) and _SS3[y][x] == '#' else 0
    return g


def cell4(ch, ink=0xE):
    g = glyph(ch)
    return [[ink if g[y][x] else 0 for x in range(8)] for y in range(8)]
