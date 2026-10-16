# -*- coding: utf-8 -*-
r"""상영 메뉴 극 제목판 5장 한글화 (2026-10-14) — build_banners 의 상영메뉴 블록(DORAM.DAT 0x26500 풀린 0x15000)에 함께 씀.
  판 = 152×48 8bpp(팔레트 CRAM 0x500 — ★흑백판·컬러판 둘 다 있음: 같은 색인, 컬러 팔레트 = DORAM.DAT 0x25B66,
        흑백 = 그 밝기. 색 고르기는 컬러 팔레트로 → 흑백도 밝기가 맞음), 오른쪽 130‥151 은 표 받침(안 건드림). 순서 = 극 1,3,5,2,4(영문 gfx_build_plates).
  판마다(사용자 «판마다 정해»): 지울 상자 + 지울 화소 규칙 → 둘레에서 안쪽으로 번지기(라플라스) 메우기 → 그 판 배경 색 몇 개로만
  → 원래 양식으로 한글(몸·테두리·그림자, aatext 안티).
  번역: 간보, 연회가 끝난 후 / 떨어져 가는 곳…(사용자 지정) / 요리로 결전! / 이것이 사나이가 사는 길 / 세계의 끝을 넘어서
"""
from collections import Counter

import aatext

FB = r'C:\Windows\Fonts\malgunbd.ttf'
W, H = 152, 48
ART_W = 130


def lum(c):
    return (c[0] * 299 + c[1] * 587 + c[2] * 114) // 1000


# (풀린 위치, 지울 상자들 [(x0,y0,x1,y1, 규칙)], 글 줄들 [(글, 상자 x0,y0,x1,y1)], 양식)
#   규칙 'ink' = 밝은 글자(≥hi)·검은 테두리(≤lo) + 1px 넓힘 / 'rect' = 상자 통째
PLATES = [
    (0x3300, [(2, 6, 64, 24, 'ink'), (40, 21, 126, 41, 'ink')],
     [('간보,', 4, 7, 60, 22), ('연회가 끝난 후', 38, 23, 126, 40)], 'white_black'),
    (0x4F80, [(0, 0, ART_W - 1, H - 1, 'rows')],    # 배경 장식(흐린 落ち·사선·밑줄) 전부 날림 — 사용자 «배경 다 날려»
     [('떨어져 가는 곳…', 2, 12, 108, 34)], 'black'),
    (0x6C00, [(4, 19, 128, 45, 'ink_hi')],
     [('요리로 결전!', 5, 21, 127, 44)], 'white_black'),
    (0x8880, [(8, 2, 126, 44, 'rect')],
     [('이것이 사나이가', 22, 3, 124, 21), ('사는 길', 52, 22, 124, 43)], 'bubble'),
    (0xA500, [(0, 0, ART_W - 1, H - 1, 'cols')],    # 배경 다 날리고 그라데이션만 — 사용자 «배경 다 날려 그라데이션 남기고»
     [('세계의 끝을 넘어서', 2, 8, 122, 31)], 'grey_reflect'),
]


def _mask(b, pal, boxes):
    m = [[False] * W for _ in range(H)]
    for x0, y0, x1, y1, rule in boxes:
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                L = lum(pal[b[y * W + x]])
                if rule in ('rect', 'rows', 'cols'):
                    hit = True
                elif rule == 'ink':
                    hit = L >= 150 or L <= 30
                elif rule == 'ink_hi':
                    hit = L >= 195 or L <= 30
                elif rule == 'dark+ghost':
                    hit = L <= 45 or (x < 36 and y < 20 and L >= 140)
                m[y][x] = m[y][x] or hit
    grow = [[m[y][x] or any(0 <= y + dy < H and 0 <= x + dx < W and m[y + dy][x + dx]
                            for dy in (-1, 0, 1) for dx in (-1, 0, 1)) for x in range(W)] for y in range(H)]
    for x0, y0, x1, y1, rule in boxes:               # 넓힘은 상자 안에서만
        pass
    return grow


def _inpaint(b, pal, m, ncol=6):
    """가려진 화소를 둘레에서 번지기(라플라스 반복) → 판 배경 색 ncol 개 중 최근접."""
    c = [[list(pal[b[y * W + x]]) for x in range(W)] for y in range(H)]
    hole = [(x, y) for y in range(H) for x in range(ART_W) if m[y][x]]
    # 처음값 = 같은 줄 가장 가까운 비가림 화소
    for x, y in hole:
        for d in range(1, W):
            for xx in (x - d, x + d):
                if 0 <= xx < ART_W and not m[y][xx]:
                    c[y][x] = list(pal[b[y * W + xx]]); break
            else:
                continue
            break
    for _ in range(200):
        for x, y in hole:
            acc = [0, 0, 0]; n = 0
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                xx, yy = x + dx, y + dy
                if 0 <= xx < ART_W and 0 <= yy < H:
                    for i in range(3):
                        acc[i] += c[yy][xx][i]
                    n += 1
            c[y][x] = [v / n for v in acc]
    bgc = Counter(b[y * W + x] for y in range(H) for x in range(ART_W) if not m[y][x] and b[y * W + x])
    cands = [v for v, _ in bgc.most_common(ncol)]
    out = bytearray(b)
    for x, y in hole:
        rgb = c[y][x]
        out[y * W + x] = min(cands, key=lambda i: sum((pal[i][k] - rgb[k]) ** 2 for k in range(3)))
    return out


def _near(pal, rgb, cands):
    return min(cands, key=lambda i: sum((pal[i][k] - rgb[k]) ** 2 for k in range(3)))


def _sample(b, m, pal, box):
    """원본 글자(가림 화소)에서 몸·테두리 색인 뽑기 — 테두리 = 가장 어두운 쪽 최빈, 몸 = 나머지 중 최빈."""
    x0, y0, x1, y1 = box
    c = Counter(b[y * W + x] for y in range(y0, y1 + 1) for x in range(x0, x1 + 1) if m[y][x] and b[y * W + x])
    dark = [v for v in c if lum(pal[v]) <= 40]
    outl = max(dark, key=lambda v: c[v]) if dark else min(c, key=lambda v: lum(pal[v]))
    full = sum(map(sum, m)) >= ART_W * H * 0.9          # 배경을 통째로 지운 판 → 가림 화소 대부분이 배경
    light = [v for v in c if lum(pal[v]) >= 150]
    if full and light:                                 # 그때 몸 = 글자 안 밝은 색(배경색이 뽑히면 글자가 안 보임 — 세계의 끝)
        body = max(light, key=lambda v: c[v])
    else:
        body = max((v for v in c if lum(pal[v]) > 60), key=lambda v: c[v])
    return body, outl


GAL = r'C:\claude\utils\font\Galmuri-v2.40.3'
PIXEL_FONTS = [(14, GAL + r'\Galmuri14.ttf', 15), (11, GAL + r'\Galmuri11-Bold.ttf', 12), (0, GAL + r'\Galmuri9.ttf', 10)]


def _pixel_cov(text, x0, y0, bw, bh, pad):
    """줄 높이에 맞는 화소 글꼴을 제 크기로(임계 128) → [몸, 몸+pad 넓힘] 0/1 덮임.
    (윤곽선 글꼴을 작게 + 몇 색으로 반올림하면 비뚤비뚤 — 2026-10-14 사용자)"""
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops
    i = next(k for k, (minh, _, _) in enumerate(PIXEL_FONTS) if bh - 2 * pad >= minh)
    while True:
        path, size = PIXEL_FONTS[i][1], PIXEL_FONTS[i][2]
        f = ImageFont.truetype(path, size)
        bb = ImageDraw.Draw(Image.new('L', (8, 8))).textbbox((0, 0), text, font=f)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        if tw <= bw - 2 * pad or i == len(PIXEL_FONTS) - 1:
            break
        i += 1                                         # 넓으면 한 단계 작은 글꼴
    im = Image.new('L', (W, H), 0)
    ImageDraw.Draw(im).text((x0 + (bw - tw) // 2 - bb[0], y0 + (bh - th) // 2 - bb[1]), text, font=f, fill=255)
    im = im.point(lambda v: 255 if v >= 128 else 0)
    if size >= 15:                                     # 갈무리14 는 획이 가늘다 → 가로 1px 덧대 굵게(게임 글꼴 굵게와 같은 방식)
        from PIL import ImageChops
        im = ImageChops.lighter(im, ImageChops.offset(im, 1, 0))
    out = [im]
    if pad:                                            # 마름모(맨해튼 거리) 넓힘 — 네모로 넓히면 말풍선이 각진 상자가 됨
        g = im
        for _ in range(pad):
            g = ImageChops.lighter(g, ImageChops.lighter(ImageChops.lighter(ImageChops.offset(g, 1, 0), ImageChops.offset(g, -1, 0)),
                                                         ImageChops.lighter(ImageChops.offset(g, 0, 1), ImageChops.offset(g, 0, -1))))
        out.append(g)
    return [[[px[x, y] / 255.0 for x in range(W)] for y in range(H)] for px in (o.load() for o in out)]


def _draw(base, orig, m, pal, lines, style, cands):
    out = bytes(base)
    for text, x0, y0, x1, y1 in lines:
        bw, bh = x1 - x0 + 1, y1 - y0 + 1
        body, outl = _sample(orig, m, pal, (x0, y0, x1, y1))
        pad = {'white_black': 1, 'bubble': 3, 'black': 0, 'grey_reflect': 0}[style]   # 흰 글자 테두리 2→1px(굵은 검은 덩어리라 거침 — 2026-10-14)
        cov = _pixel_cov(text, x0, y0, bw, bh, pad)   # ★화소 글꼴 제 크기·안티 없음
        cur = out
        bg = lambda x, y: pal[cur[y * W + x]]
        if style == 'white_black':     # 원본 몸 색 + 원본 검은 테두리 2px
            layers = [(cov[1], pal[outl]), (cov[0], pal[body])]
        elif style == 'bubble':        # 원본 밝은 말풍선 3px + 원본 검은 글자
            layers = [(cov[1], pal[body]), (cov[0], pal[outl])]
        elif style == 'black':         # 원본 검은 글자
            layers = [(cov[0], pal[outl])]
        else:                          # 원본 글자 색 한 색 + (1,1) 어두운 그림자 (반사 2색 → 한 색, 2026-10-14 사용자 «통일해»)
            layers = [(aatext.shift(cov[0], 1, 1), pal[outl]), (cov[0], pal[body])]
        out = bytes(aatext.compose_over(layers, W, H, pal, cands, bg=bg, base=cur))
    return out


NSTEP_COLOR = 24
NSTEP_GREY = 99
NAA = 16                          # 글자 안티 후보 배경색 수(8 이면 계단이 남아 거침)
COLS_FROM_ORIG = True
COLOR_SHIFT = 0xC180 - 0x3300     # ★컬러판 5장 = 같은 블록 +0xC180‥(흑백판 바로 뒤, 같은 순서·배치) — 선택된 판(VDP1 0x35B40) 실기 스테이트로 확인


def apply(blk, pal, log=print, ncol=6, pal_color=None):
    blk = bytearray(blk)
    sets = [(PLATES, pal)]
    if pal_color is not None:
        sets.append(([(p[0] + COLOR_SHIFT,) + tuple(p[1:]) for p in PLATES], pal_color))
    for plates, pal in sets:
      for off, boxes, lines, style in plates:
          b = bytes(blk[off:off + W * H])
          m = _mask(b, pal, boxes)
          if boxes[0][4] == 'rows':                     # 줄마다 배경 최빈색 한 색으로(세로 그라데이션만 남김)
              clean = bytearray(b)
              for y in range(H):
                  row = [b[y * W + x] for x in range(ART_W) if 45 < lum(pal[b[y * W + x]]) < 230]   # 검은 글자·흰 장식만 뺌(컬러판 하늘색 포함)
                  if row:
                      v = Counter(row).most_common(1)[0][0]
                      for x in range(ART_W):
                          clean[y * W + x] = v
          elif boxes[0][4] == 'cols':                   # 열마다 위(0‥5)·아래(36‥47) 평균 RGB → 가로 ±6 평균 → 세로 보간 → 판의 회색 계열 중 최근접
              clean = bytearray(b)                      # (최빈색·16색이면 거칠다 — 2026-10-14 사용자)
              avg = lambda ys, x: [sum(pal[b[y * W + x]][i] for y in ys) / len(ys) for i in range(3)]
              T0 = [avg(range(6), x) for x in range(ART_W)]; B0 = [avg(range(36, H), x) for x in range(ART_W)]
              sm = lambda A, x: [sum(A[j][i] for j in range(max(0, x - 6), min(ART_W, x + 7))) / (min(ART_W, x + 7) - max(0, x - 6)) for i in range(3)]
              T1 = [sm(T0, x) for x in range(ART_W)]; B1 = [sm(B0, x) for x in range(ART_W)]
              greys = sorted({b[y * W + x] for y in list(range(6)) + list(range(36, H)) for x in range(ART_W) if b[y * W + x]}, key=lambda v: -lum(pal[v]))   # 위·아래 배경 띠의 색(흑백판=회색, 컬러판=금갈색)
              # 열 색 = 실제 RGB 에 가장 가까운 배경 띠 색(밝기로 뽑으면 컬러판 색조가 틀어짐 — 보라·회색, 2026-10-14)
              #   → 많이 쓰인 NSTEP 색으로 줄여 다시 최근접(띠가 넓을수록 압축 쌈). 모든 줄 같은 열 색 = 가로 그라데이션만.
              NSTEP = NSTEP_COLOR if off >= COLOR_SHIFT else NSTEP_GREY
              rgbs = [list(T1[x]) for x in range(ART_W)]   # 위 띠 색만(위·아래 평균은 금색+검정이 섞여 탁한 회색·보라가 됨)
              first = [_near(pal, c, greys) for c in rgbs]
              keep = [v for v, _ in Counter(first).most_common(NSTEP)]
              colv = [_near(pal, c, keep) for c in rgbs]
              if COLS_FROM_ORIG:                          # 원본 위 띠(0‥5줄) 열마다 최빈 색인 그대로 — 원본 배열이라 압축이 쌈
                  colv = [Counter(b[y * W + x] for y in range(6)).most_common(1)[0][0] for x in range(ART_W)]
              for x in range(ART_W):
                  for y in range(H):
                      clean[y * W + x] = colv[x]
          else:
              clean = _inpaint(b, pal, m, ncol)
          # 글자 안티는 몸·테두리 + 지운 뒤 판 배경 최빈 8색 사이에서만(색이 늘면 DORAM 자리 넘침 — 2026-10-14)
          used = Counter(v for v in clean[:W * H] if v)
          cands = [v for v, _ in used.most_common(NAA)] + list(_sample(b, m, pal, lines[0][1:])) +                 [v for ln in lines[1:] for v in _sample(b, m, pal, ln[1:])]
          new = _draw(clean, b, m, pal, lines, style, cands)
          blk[off:off + W * H] = new
          log('  제목판 +0x%X «%s» 지움 %d화소' % (off, ' / '.join(t for t, *_ in lines), sum(map(sum, m))))
    return bytes(blk)
