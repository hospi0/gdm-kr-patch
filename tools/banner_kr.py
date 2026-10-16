# -*- coding: utf-8 -*-
r"""금판 배너(파란 글자 + 오른쪽 아래 그림자) 한글화 공용 (2026-10-14).
  쓰는 곳: build_banners.py(표정집·설정자료집·상영메뉴·몬스터도감), build_scene_banner.py 와 같은 방식.
  1) 깨끗한 판: 글자 띠 위·아래 깨끗한 줄의 «색 단계 순서»(같은 값 연속 묶음)를 읽고, 두 줄 모두에 있는 단계(LCS)의
     시작 x 를 줄 번호로 선형 보간해 띠 안쪽(줄마다 왼쪽 첫 판 화소‥오른쪽 끝 판 화소)을 통째로 다시 칠함.
     (획만 지우면 잔티가 남는다 — 2026-10-14 사용자 «깨끗한 노란 판때기부터»)
  2) 글자: 테두리 없음 — 파란 몸 + (1,1) 짙은 그림자, 4배 그려 안티(aatext), 원본 배너가 쓰던 색인 안에서만 섞음.
"""
from collections import Counter

import aatext

FONT_B = r'C:\Windows\Fonts\malgunbd.ttf'
NMAP = 12


def _runs(row, L, R, ok=lambda v: True):
    out = []
    for x in range(L, R + 1):
        v = row[x]
        if not ok(v):                               # 금색 아닌 화소(테두리·잔티)는 단계로 안 침
            continue
        if out and out[-1][0] == v:
            continue
        out.append((v, x))
    return out


def _lcs(a, b):
    n, m = len(a), len(b)
    T = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            T[i][j] = T[i + 1][j + 1] + 1 if a[i][0] == b[j][0] else max(T[i + 1][j], T[i][j + 1])
    i = j = 0; out = []
    while i < n and j < m:
        if a[i][0] == b[j][0]:
            out.append((a[i][0], a[i][1], b[j][1])); i += 1; j += 1
        elif T[i + 1][j] >= T[i][j + 1]:
            i += 1
        else:
            j += 1
    return out


def make(ban, w, h, pal, text, size_max=None, nblue=6, font=FONT_B, log=print, ngold=None, plate_rgb=None):
    """ban = 원본 배너 색인(bytes, w*h). 반환 (새 배너 bytes, 깨끗한 판 bytes)."""
    isblue = lambda i: i and pal[i][2] > pal[i][0] + 20
    isgold = lambda i: i and pal[i][0] >= pal[i][2] and pal[i][0] > 120
    pure = lambda i: i and pal[i][0] > 120 and pal[i][0] - pal[i][2] > 40   # 노란 기 뚜렷한 판 색(글자 가장자리 회갈색 섞임은 뺌)
    # 글자 줄 = 파란 화소 3개↑ 줄의 가장 긴 연속 구간(판 가장자리 음영의 파란 점은 뺌 — 상영메뉴 아래 테두리)
    cnt = [sum(1 for x in range(w) if isblue(ban[y * w + x])) for y in range(h)]
    best = (0, 0, -1); s = None
    for y in range(h + 1):
        if y < h and cnt[y] >= 3:
            s = y if s is None else s
        elif s is not None:
            if y - s > best[0]:
                best = (y - s, s, y - 1)
            s = None
    y0, y1 = best[1], best[2]
    bl = [(x, y) for y in range(y0, y1 + 1) for x in range(w) if isblue(ban[y * w + x])]
    x0, x1 = min(p[0] for p in bl), max(p[0] for p in bl)
    def dirty(y):                                   # 판 안쪽(양끝 3px 빼고)에 금색 아닌 화소가 있나
        g = [x for x in range(w) if isgold(ban[y * w + x])]
        return not g or any(not pure(ban[y * w + x]) for x in range(g[0] + 3, g[-1] - 2))
    top, bot = y0 - 1, min(h - 1, y1 + 1)
    while top > max(0, y0 - 4) and dirty(top):
        top -= 1
    while bot < min(h - 1, y1 + 4) and dirty(bot):
        bot += 1

    def span(y):
        row = ban[y * w:(y + 1) * w]
        g = [x for x in range(w) if isgold(row[x])]
        return (g[0], g[-1]) if g else None

    rt, rb = ban[top * w:(top + 1) * w], ban[bot * w:(bot + 1) * w]
    st, sb = span(top), span(bot)
    lv = _lcs(_runs(rt, *st, ok=isgold), _runs(rb, *sb, ok=isgold))
    # 같은 열의 위·아래 깨끗한 화소 RGB 를 세로 보간 → 판이 쓰던 금색 중 가장 가까운 색(단계 경계 보간은 1px 짙은 점이 생김)
    gc = Counter(v for v in list(rt) + list(rb) if pure(v))       # 기준 두 줄에 있는 금색만(색이 늘면 압축 넘침 — 상영메뉴 45 B)
    golds = sorted(v for v, _ in gc.most_common(ngold))
    near = {}

    def pick(rgb):
        if rgb not in near:
            near[rgb] = min(golds, key=lambda i: sum((a - b) ** 2 for a, b in zip(pal[i], rgb)))
        return near[rgb]

    def smooth(row, x, r=4):                         # 기준 줄을 가로 ±4px 금색 평균 RGB 로(화소 잡티가 세로 줄무늬로 번지지 않게)
        vs = [pal[row[i]] for i in range(max(0, x - r), min(w, x + r + 1)) if pure(row[i])]
        if not vs:
            return None
        return tuple(sum(c[i] for c in vs) / len(vs) for i in range(3))

    st_rgb = [smooth(rt, x) for x in range(w)]; sb_rgb = [smooth(rb, x) for x in range(w)]
    plate = bytearray(ban)
    for y in range(max(top + 1, y0 - 2), min(bot, y1 + 3)):   # ★세로도 글자 줄(±2)만 — 글자 없는 위 줄까지 칠하면 하이라이트가 네모로 잘림(2026-10-14)
        sp = span(y)
        if not sp:
            continue
        L, R = max(sp[0], x0 - 3), min(sp[1], x1 + 3)   # ★원래 글자 범위만 — 판 끝 그라데이션·하이라이트까지 칠하면 노란 네모가 생김(2026-10-14)
        k = (y - top) / (bot - top)
        for x in range(L, R + 1):
            ca, cb = st_rgb[x], sb_rgb[x]
            ca = ca or cb; cb = cb or ca
            if ca is None:
                continue
            plate[y * w + x] = pick(tuple(int(round(ca[i] + (cb[i] - ca[i]) * k)) for i in range(3)))
    if plate_rgb is not None:                         # 다른 배너의 깨끗한 판(RGB)을 이 팔레트로 옮겨 씀(표정집 ← 몬스터 도감, 사용자 지시)
        golds_all = [v for v, _ in Counter(v for v in ban if isgold(v)).most_common(NMAP)]   # 많이 쓰인 금색만(다 쓰면 잘게 섞여 압축 넘침)
        plate = bytearray(ban)
        for y in range(h):
            for x in range(w):
                c = plate_rgb[y][x]
                if c is not None and ban[y * w + x] != 0:
                    plate[y * w + x] = min(golds_all + [v for v in set(ban) if v and not isblue(v)],
                                           key=lambda i: sum((pal[i][k] - c[k]) ** 2 for k in range(3)))
    used = Counter(v for v in ban if isblue(v))
    body = used.most_common(1)[0][0]
    shad = min(used, key=lambda i: sum(pal[i]))
    bw, bh = x1 - x0 + 1, y1 - y0 + 1
    # 높이 = 원래 글자 높이, 가로 = 원래 글자 폭까지 최대 1.3배 늘임(일본어는 폭이 꽉 참 — 2026-10-14 너무 작다)
    for size in range(size_max or bh + 8, 8, -1):
        _, (tw, th) = aatext.coverage(text, font, size, w, h, [0], fit=(x0, y0, bw, bh))
        if tw <= bw and th <= bh:
            break
    sx = max(1.0, min(1.3, (bw - 1) / tw))
    cov, (tw, th) = aatext.coverage(text, font, size, w, h, [0], fit=(x0, y0, bw - 1, bh - 1), sx=sx)
    cands = {v for v, _, _ in lv} | {body, shad} | {i for i, _ in used.most_common(nblue)} | set(plate[top * w:(bot + 1) * w])
    cands.discard(0)
    out = aatext.compose_over([(aatext.shift(cov[0], 1, 1), pal[shad]), (cov[0], pal[body])], w, h, pal, cands,
                              bg=lambda x, y: pal[plate[y * w + x]] if plate[y * w + x] else (0, 0, 0), base=plate)
    log('  «%s» %dpx ×%.2f · 원래 글자 x%d‥%d y%d‥%d · 판 단계 %d개 · 몸 %s 그림자 %s'
        % (text, size, sx, x0, x1, y0, y1, len(lv), pal[body], pal[shad]))
    return bytes(out), bytes(plate)
