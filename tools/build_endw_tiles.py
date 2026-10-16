# -*- coding: utf-8 -*-
r"""전투 결과 3화면의 VDP2 타일 글자 한글화 — BATLE/ENDW.DAT 무압축 8×8 4bpp 셀 (2026-10-14).
  배치표 = VDP2 VRAM 0xE000 1워드(셀 번호 하위 10비트, 64칸 폭) — 화면 스테이트에서 읽음.
  ENDW 오프셋 = 셀×0x20 + 화면별 상수(영문 패치 battle_results_gfx·battle_skillgain_gfx 기록, 우리 스테이트 VRAM 과 대조):
    결과·보상 0x151E4 / 스킬 0x5D4C / 경험치 0xAD48
  라벨마다 화면 좌표 상자(px) → 글자 화소(바탕 번호 아닌 것) 지우기 → 줄마다 바탕색 메우기 → 원래 양식으로 한글 → 걸친 셀 써넣기.
  같은 셀을 여러 곳이 쓰면(스킬·이름 등 공용) 내용이 같아야 함(다르면 멈춤).
  python tools/build_endw_tiles.py [--png]   (build_battle_gfx 뒤 — 같은 ENDW.DAT 의 다른 구간)
"""
import os, struct, sys
from collections import Counter, defaultdict
from PIL import Image, ImageDraw, ImageFont
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)

GAL = r'C:\claude\utils\font\Galmuri-v2.40.3'
F_G11B, F_G7 = GAL + r'\Galmuri11-Bold.ttf', GAL + r'\Galmuri7.ttf'
F_G11, F_G9 = GAL + r'\Galmuri11.ttf', GAL + r'\Galmuri9.ttf'   # 2026-10-14 «글씨 흐림» → 결과 문장은 안티 없는 화소 글꼴
F_THIN = r'C:\claude\utils\font\nanum-gothic\NanumGothic.ttf'
F_BOLD = r'C:\Windows\Fonts\malgunbd.ttf'
NAMES = [((24, 8, 72, 23), '저스틴'), ((290, 8, 317, 23), '수'), ((29, 120, 68, 135), '피나')]
SCREENS = [
    ('b3', 0x151E4, [
        ((80, 24, 233, 39), '의 경험치를 획득했다!', 'thin'),   # 「1200の経験値」 → 「1200의 경험치」(숫자 바로 뒤에 붙임)
        ((28, 52, 64, 71), '보상', 'red'),
        ((32, 72, 79, 87), '골드', 'gold'),
        ((32, 104, 79, 119), '아이템', 'gold')]),
    ('b4', 0x5D4C, [(r, t, 'name') for r, t in NAMES] + [
        ((96, 16 + 16 * k, 127, 23 + 16 * k), t, 'bar') for k, t in enumerate(['무기', '불', '물', '바람', '땅'])] + [
        ((128, 16, 167, 23), '스킬', 'bar')]),
    ('b5', 0xAD48, [(r, t, 'name') for r, t in NAMES] + [
        ((88, 16 + 8 * k, 111, 23 + 8 * k), t, 'wedge') for k, t in enumerate(['힘', '체력', '민첩', '이동력'])]),
]
BG = {'bar': {5, 6}, 'wedge': {3, 4}}


def load_map(name):
    v = open(os.path.join(ROOT, 'work', 'mem', name, 'VDP2_VRAM.bin'), 'rb').read()
    return v, (lambda r, c: struct.unpack_from('>H', v, 0xE000 + (r * 64 + c) * 2)[0] & 0x3FF)


def cell_px(buf, off):
    return [[(buf[off + y * 4 + x // 2] >> (4 if x % 2 == 0 else 0)) & 15 for x in range(8)] for y in range(8)]


def mask(text, font, size, w, h, thr=128):
    f = ImageFont.truetype(font, size)
    bb = ImageDraw.Draw(Image.new('L', (8, 8))).textbbox((0, 0), text, font=f)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    im = Image.new('L', (w, h), 0)
    ImageDraw.Draw(im).text(((w - tw) // 2 - bb[0], (h - th) // 2 - bb[1]), text, font=f, fill=255)
    p = im.load()
    return [[p[x, y] for x in range(w)] for y in range(h)], tw, th


def mask_tight(text, font, size, w, h, space):
    """글자마다 제 간격으로 찍되 띄어쓰기만 space px — 화소 글꼴(안티 없음 판정은 부르는 쪽)."""
    f = ImageFont.truetype(font, size)
    im = Image.new('L', (w + 64, h), 0); d = ImageDraw.Draw(im)
    bb = d.textbbox((0, 0), text, font=f)
    x = 0
    for ch in text:
        if ch == ' ':
            x += space; continue
        d.text((x, (h - (bb[3] - bb[1])) // 2 - bb[1]), ch, font=f, fill=255)
        x += round(f.getlength(ch))
    p = im.load()
    xs = [xx for xx in range(w + 64) for y in range(h) if p[xx, y] >= 128]
    tw = max(xs) - min(xs) + 1 if xs else 0
    return [[p[xx, y] for xx in range(w)] for y in range(h)], tw


def fit(text, font, sizes, w, h):
    for s in sizes:
        m, tw, th = mask(text, font, s, w, h)
        if tw <= w and th <= h:
            return m, s
    return m, s


def draw(region, text, style):
    """region = 원래 화소 [h][w] → 새 화소."""
    h, w = len(region), len(region[0])
    used = Counter(v for row in region for v in row if v)
    bg = BG.get(style, set())
    out = [[0] * w for _ in range(h)]
    for y in range(h):                                 # 바탕(막대·쐐기)만 남기고 줄마다 메우기
        row = region[y]
        bgs = [v for v in row if v in bg]
        if bgs:
            fillv = Counter(bgs).most_common(1)[0][0]
            last = max(x for x in range(w) if row[x] in bg)
            for x in range(w):
                out[y][x] = row[x] if row[x] in bg else (fillv if x <= last else 0)
    on = lambda m, y, x: 0 <= y < h and 0 <= x < w and m[y][x] >= 128
    if style == 'thin':                                # 흰 글자 한 색 f(안티 없음 — 2026-10-14 사용자 «흐림»)
        DW = 120                                   # 글자는 x 80‥199 안에만 — x 200‥207 윗줄이 공용 빈칸(0x1A0)
        m, tw = mask_tight(text, F_G11, 12, DW, h, space=3); s = 12   # 띄어쓰기만 3px 로 좁혀 크기 유지
        print('    갈무리11 폭 %d / %d' % (tw, DW))
        assert tw <= DW, ('결과 문장 폭 넘침', tw)
        cols = [x for x in range(DW) if any(m[y][x] >= 128 for y in range(h))]   # 왼쪽 붙임(숫자 뒤에 바로 «의»)
        if cols:
            sh = max(0, cols[0] - 1)
            m = [row[sh:] + [0] * sh for row in m]
        m = [row + [0] * (w - DW) for row in m]
        for y in range(h):
            for x in range(w):
                out[y][x] = 0xF if m[y][x] >= 128 else out[y][x]
        return out, s
    if style in ('bar', 'wedge'):                      # 8px 글자 + (1,1) 그림자 1
        m, s = fit(text, F_G7, [8], w, h)
        body = Counter(v for row in region for v in row if v and v not in bg and v != 1).most_common(1)[0][0]
        for y in range(h):
            for x in range(w):
                if not on(m, y, x) and on(m, y - 1, x - 1):
                    out[y][x] = 1
        for y in range(h):
            for x in range(w):
                if on(m, y, x):
                    out[y][x] = body
        return out, s
    if style == 'red':                                 # 빨간 양각: 테두리 9 + 몸 f
        m, s = fit(text, F_BOLD, range(h, 8, -1), w - 2, h - 2)
        m = [[0] * w] + [[0] + r + [0] for r in m] + [[0] * w]
        for y in range(h):
            for x in range(w):
                if on(m, y, x):
                    out[y][x] = 0xF if y < h * 0.6 else 0xE
                elif any(on(m, y + dy, x + dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1)):
                    out[y][x] = 9
        return out, s
    # gold / name: 위·왼 가장자리 c, 몸 f(이름은 아래 절반 e), (1,1) 그림자(골드 b · 이름 1)
    m, s = fit(text, F_G11B, [12], w, h)
    shadow = 0xB if style == 'gold' else 1
    ys = [y for y in range(h) for x in range(w) if on(m, y, x)] or [0, h]
    mid = (min(ys) + max(ys)) // 2
    for y in range(h):
        for x in range(w):
            if not on(m, y, x) and on(m, y - 1, x - 1):
                out[y][x] = shadow
    for y in range(h):
        for x in range(w):
            if on(m, y, x):
                edge = not on(m, y - 1, x) or not on(m, y, x - 1)
                if style == 'gold':                    # 골드·아이템: 한 색 f(가장자리 c 가 흐려 보임 — 2026-10-14)
                    out[y][x] = 0xF
                elif style == 'name':                   # 2026-10-16 사용자: 전투 HUD 이름표와 같은 양식 — 갈무리11 Bold 몸 한 색 + (1,1) 그림자
                    out[y][x] = 0xF
                else:
                    out[y][x] = 0xC if edge else 0xF
    return out, s


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    src = os.path.join(ROOT, 'work', 'build', 'BATLE_ENDW.DAT')
    if not os.path.exists(src):
        src = os.path.join(ROOT, 'work', 'dm_all', 'BATLE_ENDW.DAT')
    orig = open(os.path.join(ROOT, 'work', 'dm_all', 'BATLE_ENDW.DAT'), 'rb').read()
    dat = bytearray(open(src, 'rb').read())
    previews = []
    for st, const, labels in SCREENS:
        v, ent = load_map(st)
        usage = Counter(ent(r, c) for r in range(32) for c in range(64))
        frozen = lambda ch: usage[ch] > 1 and not any(v[ch * 0x20:ch * 0x20 + 32])   # 공용 빈칸 — 쓰면 다른 자리도 바뀜
        want = {}                                       # 셀 번호 → 새 32 B
        for (x0, y0, x1, y1), text, style in labels:
            w, h = x1 - x0 + 1, y1 - y0 + 1
            cells = {}
            for r in range(y0 // 8, y1 // 8 + 1):
                for c in range(x0 // 8, x1 // 8 + 1):
                    ch = ent(r, c); off = ch * 0x20 + const
                    if frozen(ch):
                        cells[(r, c)] = (None, [[0] * 8 for _ in range(8)]); continue
                    assert orig[off:off + 32] == v[ch * 0x20:ch * 0x20 + 32], (st, text, hex(ch), 'ENDW ≠ VRAM')
                    cells[(r, c)] = (ch, cell_px(orig, off))
            region = [[cells[((y0 + y) // 8, (x0 + x) // 8)][1][(y0 + y) % 8][(x0 + x) % 8] for x in range(w)] for y in range(h)]
            new, size = draw(region, text, style)
            lost = 0
            for (r, c), (ch, px) in cells.items():
                if ch is None:                             # 고정 빈칸 위에 그린 화소는 버림(보고)
                    lost += sum(1 for y in range(8) for x in range(8)
                                if 0 <= c * 8 + x - x0 < w and 0 <= r * 8 + y - y0 < h and new[r * 8 + y - y0][c * 8 + x - x0])
                    continue
                cp = [row[:] for row in (want[ch] if ch in want else px)]
                for y in range(8):
                    for x in range(8):
                        sx, sy = c * 8 + x - x0, r * 8 + y - y0
                        if 0 <= sx < w and 0 <= sy < h:
                            cp[y][x] = new[sy][sx]
                if ch in want and want[ch] != cp:
                    print('  ★공용 셀 %03X 내용 다름(%s «%s») — 뒤 것으로' % (ch, st, text))
                want[ch] = cp
            previews.append((region, new, text))
            print('  %s «%s» %s %dpx · 셀 %d%s' % (st, text, style, size, len(cells), (' · ★빈칸 위라 잘린 화소 %d' % lost) if lost else ''))
        for ch, px in want.items():
            off = ch * 0x20 + const
            dat[off:off + 32] = bytes((px[y][x] << 4) | px[y][x + 1] for y in range(8) for x in range(0, 8, 2))
        print('%s 셀 %d개 씀' % (st, len(want)))
    if '--dry' in sys.argv:
        open(os.path.join(ROOT, 'work', 'battlegfx', '_dry_ENDW.DAT'), 'wb').write(dat); print('(--dry: work/build 안 씀 → work/battlegfx/_dry_ENDW.DAT)')
    else:
        open(os.path.join(ROOT, 'work', 'build', 'BATLE_ENDW.DAT'), 'wb').write(dat)
    print('✅ work/build/BATLE_ENDW.DAT %d B' % len(dat))
    if '--png' in sys.argv:
        grey = lambda n: (0, 0, 0) if n == 0 else (40 + n * 13,) * 3
        rows = []
        for region, new, text in previews:
            h, w = len(region), len(region[0])
            im = Image.new('RGB', (w * 2 + 4, h), (30, 0, 30))
            for k, p in enumerate((region, new)):
                for y in range(h):
                    for x in range(w):
                        im.putpixel((k * (w + 4) + x, y), grey(p[y][x]))
            rows.append(im)
        W = max(r.width for r in rows); H = sum(r.height + 3 for r in rows)
        sh = Image.new('RGB', (W, H)); y = 0
        for r in rows:
            sh.paste(r, (0, y)); y += r.height + 3
        sh.resize((W * 3, H * 3), Image.NEAREST).save(os.path.join(ROOT, 'work', 'battlegfx', 'ko_endw_tiles.png'))


if __name__ == '__main__':
    main()
