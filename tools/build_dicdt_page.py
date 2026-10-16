# -*- coding: utf-8 -*-
r"""몬스터 도감 상세 페이지의 «구운» 능력치 라벨 한글화 (2026-10-14).
  화면 = VDP2 NBG2 256색 타일, 배치표 VRAM 0xC000(1워드, 셀 번호 = 하위 12비트, 주소 = 번호×0x20), CRAM +0x400
  (사용자 디버거 화면으로 확인 — 우리 vdp2render 는 NBG2 설정을 잘못 읽었음).
  페이지 셀 0x800‥0xFA4(979개, 칸마다 다른 셀) = FIELD/DICDT.DAT 0xCFA0 + (셀−0x800)×0x20 에 무압축(바이트 전량 일치).
  라벨: ステータス / レベル / たいきゅうりょく / こうげきりょく / ぼうぎょりょく / すばやさ / そうりょく / けいけんち
  → 글자(어두운 갈색) 화소 지우고 같은 줄의 글자 없는 종이를 옮겨 메움 → 원본 갈색 한 색으로 갈무리7(8px) 한글.
  배치표는 스테이트(work/mem/mon3, «my files/할일/그래픽/도감.state3»)에서 읽음.
  python tools/build_dicdt_page.py [--png]   (build_banners 뒤 — 같은 DICDT)
"""
import os, struct, sys
from collections import Counter
from PIL import Image, ImageDraw, ImageFont
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
G7 = r'C:\claude\utils\font\Galmuri-v2.40.3\Galmuri7.ttf'
BASE, CH0 = 0xCFA0, 0x800
LABELS = ['스테이터스', '레벨', '내구력', '공격력', '방어력', '민첩', '이동력', '경험치']
BOX = (46, 88, 113, 152)          # 라벨 범위(px) — x<46 은 책 접힌 곳 그림자(글자 아님)
BANDS = [(88, 95)] + [(96 + 8 * k, 103 + 8 * k) for k in range(7)]   # 머리 + 일곱 줄(8px 간격, 화소 지도로 확인)
FILL_DX = 72                      # 메울 때 가져올 종이: 같은 줄 오른쪽 이만큼(라벨과 «=» 사이는 깨끗한 종이)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    mem = os.path.join(ROOT, 'work', 'mem', 'mon3')
    v = open(os.path.join(mem, 'VDP2_VRAM.bin'), 'rb').read()
    c = open(os.path.join(mem, 'CRAM.bin'), 'rb').read(); c = bytes(x for i in range(0, len(c), 2) for x in (c[i + 1], c[i]))
    col = lambda i: (lambda w: ((w & 31) * 8, ((w >> 5) & 31) * 8, ((w >> 10) & 31) * 8))(struct.unpack_from('>H', c, (i % 2048) * 2)[0])
    lum = lambda i: sum(col(0x400 + i))
    ent = lambda r, cc: struct.unpack_from('>H', v, 0xC000 + (r * 64 + cc) * 2)[0] & 0xFFF
    src = os.path.join(ROOT, 'work', 'build', 'FIELD_DICDT.DAT')
    if not os.path.exists(src):
        src = os.path.join(ROOT, 'work', 'dm_all', 'FIELD_DICDT.DAT')
    orig = open(os.path.join(ROOT, 'work', 'dm_all', 'FIELD_DICDT.DAT'), 'rb').read()
    dat = bytearray(open(src, 'rb').read())
    W, H = 352, 240
    pg = [[0] * W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            ch = ent(y // 8, x // 8)
            if ch >= CH0:
                pg[y][x] = orig[BASE + (ch - CH0) * 0x20 + (y % 8) * 8 + (x % 8)]
    x0, y0, x1, y1 = BOX
    paper = Counter(pg[y][x] for y in range(y0, y1) for x in range(x0 + FILL_DX, x1 + FILL_DX))
    plum = sum(lum(i) * n for i, n in paper.items()) / sum(paper.values())
    dark = lambda i: lum(i) < plum * 0.72
    ink = [(x, y) for y in range(y0, y1) for x in range(x0, x1) if dark(pg[y][x])]
    inkc = Counter(pg[y][x] for x, y in ink).most_common(1)[0][0]
    bands = BANDS
    print('잉크 색 %d %s' % (inkc, col(0x400 + inkc)))
    new = [r[:] for r in pg]
    # ★지우기: 열마다 라벨 위 깨끗한 종이(80‥87행) 밝기 기준으로 확실히 어두운 화소(+둘레 1px)만 →
    #   같은 열의 80‥87행 종이를 아래로 반복해 메움(접힌 곳 그림자 같은 가로 명암 유지, 오른쪽 회색 상자 안 가져옴)
    EX0, EX1 = 38, 113
    est = {x: sum(lum(pg[y][x]) for y in range(80, 88)) / 8 for x in range(EX0, EX1)}
    inkm = {(x, y) for y in range(bands[0][0], bands[-1][1] + 1) for x in range(EX0, EX1) if lum(pg[y][x]) < est[x] * 0.9}
    grow = {(x + dx, y + dy) for x, y in inkm for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
    for x, y in grow:
        if EX0 <= x < EX1 and bands[0][0] - 1 <= y <= bands[-1][1] + 1:
            new[y][x] = pg[80 + (y % 8)][x]
    LEFT = min(x for x, y in ink if y >= bands[1][0])
    f = ImageFont.truetype(G7, 8)
    for (b0, b1), text in zip(bands, LABELS):
        bx = [x for x, y in ink if b0 <= y <= b1]
        lx = LEFT                                       # 일곱 줄 왼쪽 시작 통일
        if text == LABELS[0]:                               # 머리(ステータス)는 원래 자리 가운데
            lx = (min(bx) + max(bx)) // 2
        bb = ImageDraw.Draw(Image.new('L', (8, 8))).textbbox((0, 0), text, font=f)
        tw = bb[2] - bb[0]
        if text == LABELS[0]:
            lx -= tw // 2
        im = Image.new('L', (W, H), 0)
        ImageDraw.Draw(im).text((lx - bb[0], (b0 + b1) // 2 - (bb[3] - bb[1]) // 2 - bb[1]), text, font=f, fill=255)
        p = im.load()
        for y in range(H):
            for x in range(W):
                if p[x, y] >= 128:
                    new[y][x] = inkc
    # 써넣기(셀 단위 — 바뀐 칸만)
    n = 0
    for r in range(H // 8):
        for cc in range(W // 8):
            ch = ent(r, cc)
            if ch < CH0:
                continue
            o = BASE + (ch - CH0) * 0x20
            cell = bytes(new[r * 8 + y][cc * 8 + x] for y in range(8) for x in range(8))
            if cell != orig[o:o + 64]:
                dat[o:o + 64] = cell; n += 1
    open(os.path.join(ROOT, 'work', 'build', 'FIELD_DICDT.DAT'), 'wb').write(dat)
    print('✅ work/build/FIELD_DICDT.DAT 페이지 셀 %d개 바꿈' % n)
    if '--png' in sys.argv:
        S = 3; X0, Y0, X1, Y1 = 20, 70, 200, 170
        out = Image.new('RGB', ((X1 - X0) * 2 + 8, Y1 - Y0), (0, 0, 0))
        for k, src_ in enumerate((pg, new)):
            for y in range(Y0, Y1):
                for x in range(X0, X1):
                    out.putpixel((k * (X1 - X0 + 8) + x - X0, y - Y0), col(0x400 + src_[y][x]))
        out.resize((out.width * S, out.height * S), Image.NEAREST).save(os.path.join(ROOT, 'work', 'ttlgfx', 'preview_dicdt_page.png'))


if __name__ == '__main__':
    main()
