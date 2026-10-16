# -*- coding: utf-8 -*-
r"""그림 글자 안티에일리어싱 (2026-10-14 사용자: «안티 좀 넣어») — build_title_gfx·build_scene_banner 공용.
  4배로 그려 층별(몸·테두리…) 덮임 비율을 구하고, 안쪽 층부터 섞은 RGB 를
  «원본 그림이 쓰던 색인» 중 가장 가까운 색으로 고른다(새 색을 만들지 않음).
  bg=None(투명 바탕)이면 바깥 덮임 < 0.5 는 투명(0), 그 이상은 바탕과 섞지 않음.
"""
from PIL import Image, ImageDraw, ImageFilter, ImageFont

SS = 4


def coverage(text, font, size, w, h, grows, x0=None, y0=None, fit=None, sx=1.0):
    """grows = [0, 2, 3] 처럼 층별 누적 두께(px). 반환: 층별 덮임 [[0..1]] (안쪽 층 먼저)."""
    f = ImageFont.truetype(font, size * SS)
    d = ImageDraw.Draw(Image.new('L', (8, 8)))
    bb = d.textbbox((0, 0), text, font=f)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    if sx != 1.0:                                   # 가로 늘이기(장평) — 일본어처럼 폭을 채울 때
        g = Image.new('L', (tw + 8, th + 8), 0)
        ImageDraw.Draw(g).text((4 - bb[0], 4 - bb[1]), text, font=f, fill=255)
        g = g.resize((int((tw + 8) * sx), th + 8), Image.LANCZOS)
        tw = int(tw * sx); bb = (-int(4 * sx), -4, 0, 0)
    else:
        g = None
    if fit:
        fx0, fy0, fw, fh = fit
        x0 = fx0 * SS + (fw * SS - tw) // 2
        y0 = fy0 * SS + (fh * SS - th) // 2
    im = Image.new('L', (w * SS, h * SS), 0)
    if g is not None:
        im.paste(g, (x0 + bb[0], y0 + bb[1]))
    else:
        ImageDraw.Draw(im).text((x0 - bb[0], y0 - bb[1]), text, font=f, fill=255)
    out = []
    for g in grows:
        m = im if g == 0 else im.filter(ImageFilter.MaxFilter(2 * g * SS + 1))
        m = m.resize((w, h), Image.BOX)
        px = m.load()
        out.append([[px[x, y] / 255.0 for x in range(w)] for y in range(h)])
    return out, (tw / SS, th / SS)


def compose(cov, colors, w, h, pal, cands, bg=None, base=None, edge_bg=None, thr=0.5):
    """cov/colors 안쪽 층 먼저. bg(x,y)->RGB 또는 None. base = 덮을 원래 색인 배열(바깥은 그대로)."""
    cands = sorted(set(cands))
    cache = {}

    def near(rgb):
        if rgb not in cache:
            cache[rgb] = min(cands, key=lambda i: sum((a - b) ** 2 for a, b in zip(pal[i], rgb)))
        return cache[rgb]

    out = bytearray(base) if base is not None else bytearray(w * h)
    for y in range(h):
        for x in range(w):
            c = [layer[y][x] for layer in cov]
            if c[-1] <= 0.02:
                continue
            rgb = [0.0, 0.0, 0.0]; prev = 0.0
            for k, ck in enumerate(c):
                part = max(0.0, ck - prev); prev = max(prev, ck)
                for i in range(3):
                    rgb[i] += colors[k][i] * part
            if bg is None:
                if c[-1] < thr:
                    continue
                if edge_bg is None:
                    rgb = [v / c[-1] for v in rgb]
                else:                                      # 투명 바탕 위 가장자리 = 화면 뒤 배경 추정색과 섞음
                    rgb = [rgb[i] + edge_bg[i] * (1 - c[-1]) for i in range(3)]
            else:
                b = bg(x, y)
                rgb = [rgb[i] + b[i] * (1 - c[-1]) for i in range(3)]
            out[y * w + x] = near(tuple(int(round(v)) for v in rgb))
    return out


def shift(cov, dx, dy):
    h, w = len(cov), len(cov[0])
    return [[cov[y - dy][x - dx] if 0 <= y - dy < h and 0 <= x - dx < w else 0.0 for x in range(w)] for y in range(h)]


def compose_over(layers, w, h, pal, cands, bg, base, thr=0.02):
    """layers = [(덮임, RGB)] 뒤에서 앞 순서(그림자 → 몸)로 겹쳐 칠함. bg(x,y)->RGB."""
    cands = sorted(set(cands)); cache = {}

    def near(rgb):
        if rgb not in cache:
            cache[rgb] = min(cands, key=lambda i: sum((a - b) ** 2 for a, b in zip(pal[i], rgb)))
        return cache[rgb]

    out = bytearray(base)
    for y in range(h):
        for x in range(w):
            if max(c[y][x] for c, _ in layers) <= thr:          # 투명 바탕이면 thr 를 올려 옅은 가장자리는 투명으로
                continue
            rgb = list(bg(x, y))
            for c, col in layers:
                a = c[y][x]
                rgb = [rgb[i] * (1 - a) + col[i] * a for i in range(3)]
            out[y * w + x] = near(tuple(int(round(v)) for v in rgb))
    return out
