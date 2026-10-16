# -*- coding: utf-8 -*-
r"""전투·결과 화면 한글 그림 «실제 색» 미리보기 (2026-10-14 사용자: 미리보기부터 보여주고 작업해야지).
  각 항목: [게임 스크린샷의 원본 자리 | 새 그림(같은 팔레트)] 를 같은 배율로 나란히.
  VDP2 타일 = 배치표 0xE000 + work/build ENDW 셀, 색 = CRAM(바이트 뒤집음) 뱅크×16+번호+0x400.
  VDP1 = build_battle_gfx 결과 블록을 풀어 셀 잘라 색표→CRAM.
  python tools/preview_battle_gfx.py → work/battlegfx/preview_*.png
"""
import os, struct, sys
from PIL import Image, ImageDraw
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import gsprite as G
import build_battle_gfx as BB
import build_endw_tiles as ET

SHOT = {'b3': '전투/3.png', 'b4': '전투/4.png', 'b5': '전투/5.png',
        's1': '전투/1.png', 's2': '전투/2.png'}
ST = os.path.join(ROOT, 'my files', '할일')
OUT = os.path.join(ROOT, 'work', 'battlegfx')
SCALE = 3
COFS = {'b3': 0x400, 'b4': 0x500, 'b5': 0x500}   # 화면별 CRAM 오프셋(뱅크3 f=흰색 되는 값, 실측)


def cram_of(mem):
    c = open(os.path.join(ROOT, 'work', 'mem', mem, 'CRAM.bin'), 'rb').read()
    c = bytes(x for i in range(0, len(c), 2) for x in (c[i + 1], c[i]))
    return lambda i: (lambda w: ((w & 31) * 8, ((w >> 5) & 31) * 8, ((w >> 10) & 31) * 8))(struct.unpack_from('>H', c, (i % 2048) * 2)[0])


def shot_crop(key, x0, y0, x1, y1):
    im = Image.open(os.path.join(ST, SHOT[key])).convert('RGB')
    sx, sy = im.width / 352, im.height / 240
    c = im.crop((int(x0 * sx), int(y0 * sy), int((x1 + 1) * sx), int((y1 + 1) * sy)))
    return c.resize(((x1 - x0 + 1) * SCALE, (y1 - y0 + 1) * SCALE), Image.LANCZOS)


def tiles_render(mem, const, endw, x0, y0, x1, y1):
    v = open(os.path.join(ROOT, 'work', 'mem', mem, 'VDP2_VRAM.bin'), 'rb').read()
    col = cram_of(mem)
    im = Image.new('RGB', (x1 - x0 + 1, y1 - y0 + 1), (0, 0, 0))
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            e = struct.unpack_from('>H', v, 0xE000 + ((y // 8) * 64 + x // 8) * 2)[0]
            ch, bank = e & 0x3FF, (e >> 12) & 0xF
            o = ch * 0x20 + const + (y % 8) * 4 + (x % 8) // 2
            n = (endw[o] >> (4 if x % 2 == 0 else 0)) & 15 if o < len(endw) else 0
            if n:
                im.putpixel((x - x0, y - y0), col(bank * 16 + n + COFS[mem]))
    return im.resize((im.width * SCALE, im.height * SCALE), Image.NEAREST)


def pair(a, b, label):
    W = a.width + b.width + 12; H = max(a.height, b.height) + 14
    im = Image.new('RGB', (W, H), (60, 60, 70)); im.paste(a, (0, 14)); im.paste(b, (a.width + 12, 14))
    ImageDraw.Draw(im).text((2, 1), label, fill=(255, 255, 0))
    return im


def stack(rows, path):
    W = max(r.width for r in rows); H = sum(r.height + 6 for r in rows)
    out = Image.new('RGB', (W, H), (30, 30, 36)); y = 0
    for r in rows:
        out.paste(r, (0, y)); y += r.height + 6
    out.save(path); print(path)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    endw = open(os.path.join(ROOT, 'work', 'build', 'BATLE_ENDW.DAT'), 'rb').read()
    for st, const, labels in ET.SCREENS:
        rows = []
        for (x0, y0, x1, y1), text, style in labels:
            X0, Y0, X1, Y1 = max(0, x0 - 4), max(0, y0 - 2), x1 + 4, y1 + 2
            rows.append(pair(shot_crop(st, X0, Y0, X1, Y1), tiles_render(st, const, endw, X0, Y0, X1, Y1), text))
        stack(rows, os.path.join(OUT, 'preview_%s_tiles.png' % st))


if __name__ == '__main__':
    main()


def vdp1_positions(stf):
    """스테이트 명령표 → {VRAM: (x, y, 표시폭, 표시높이)}"""
    V, cram, stype, cofs = BB.state(stf)
    a = 0; n = 0; out = {}
    while a < 0x80000 and n < 4000:
        c = struct.unpack_from('>16H', V, a); ctrl = c[0]
        if ctrl & 0x8000:
            break
        ct = ctrl & 15; jp = (ctrl >> 12) & 7
        if not (ctrl & 0x4000) and ct in (0, 1, 2):
            src = c[4] * 8; w = ((c[5] >> 8) & 0x3F) * 8; h = c[5] & 0xFF
            sx = lambda v: struct.unpack('>h', struct.pack('>H', v))[0]
            x, y = sx(c[6]), sx(c[7])
            dw, dh = w, h
            if ct == 1:                                # 확대 스프라이트: 두 점(A·C) 모드면 c[10],c[11] = 오른쪽 아래
                dw, dh = sx(c[10]) - x + 1, sx(c[11]) - y + 1
                if dw <= 0 or dh <= 0 or dw > 352:
                    dw, dh = w, h
            out.setdefault(src, (x, y, dw, dh))
        a = c[1] * 8 if jp == 1 else a + 0x20; n += 1
    return out


def vdp1_main():
    rows = []
    for tag, fn, comp, base, stf, cells in BB.SETS:
        if isinstance(cells, dict) or stf is None:
            continue
        built = open(os.path.join(ROOT, 'work', 'build', fn if tag != 'C' else 'BATLE_B001.BBG'), 'rb').read()
        blk = G.decompress(built, comp, limit=0x20000)[0]
        orig = G.decompress(open(os.path.join(ROOT, 'work', 'dm' if os.path.exists(os.path.join(ROOT, 'work', 'dm', fn)) else 'dm_all', fn), 'rb').read(), comp, limit=0x20000)[0]
        key = {'전투/1.state': 's1', '전투/2.state1': 's2', '전투/5.state4': 'b5', '전투/4.state3': 'b4'}[stf]
        pos = vdp1_positions(stf)
        for vram, w, h, text, col, font in cells:
            pal = BB.lut_rgb(stf, col)
            imgs = []
            for src in (orig, blk):
                px = BB.get4(src, vram - base, w, h)
                im = Image.new('RGB', (w, h), (0, 0, 0))
                for y in range(h):
                    for x in range(w):
                        if px[y][x]:
                            im.putpixel((x, y), pal[px[y][x]])
                imgs.append(im.resize((w * SCALE, h * SCALE), Image.NEAREST))
            if vram in pos:
                x, y, dw, dh = pos[vram]
                shot = shot_crop(key, max(0, x), max(0, y), min(351, x + dw - 1), min(239, y + dh - 1))
            else:
                shot = Image.new('RGB', (w * SCALE, h * SCALE), (80, 0, 0))
            a = pair(shot, imgs[0], '%s %05X 스샷|원본(우리 색)' % (tag, vram))
            rows.append(pair(a, imgs[1], '→ «%s»' % text))
    stack(rows, os.path.join(OUT, 'preview_vdp1.png'))


if __name__ == '__main__' and '--vdp1' in sys.argv:
    vdp1_main()
