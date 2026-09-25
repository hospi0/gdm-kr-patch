# -*- coding: utf-8 -*-
"""코드 라벨이 달린 글리프 시트를 뽑는다 (코드↔글자 대응표를 사람이 읽어 만들기 위한 것).

사용: python tools/font_sheet.py <시작코드hex> <개수> <출력png> [열수] [배율]
"""
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, 'tools')
import font_codec as C

BOX = 16


def main():
    lo = int(sys.argv[1], 16)
    cnt = int(sys.argv[2])
    out = sys.argv[3]
    cols = int(sys.argv[4]) if len(sys.argv) > 4 else 16
    Z = int(sys.argv[5]) if len(sys.argv) > 5 else 3

    d = open('work/dm/BIN_FDATA.BIN', 'rb').read()
    n = C.table_count(d, C.FULL_BASE)
    codes = [c for c in range(lo, min(lo + cnt, n))]
    rows = (len(codes) + cols - 1) // cols
    LAB = 46                                  # 왼쪽 라벨 폭
    cell = BOX * Z + 4
    W, H = LAB + cols * cell, rows * (cell + 10) + 14
    img = Image.new('RGB', (W, H), (24, 24, 28))
    dr = ImageDraw.Draw(img)
    try:
        f = ImageFont.truetype(r'C:\Windows\Fonts\consola.ttf', 11)
    except Exception:
        f = ImageFont.load_default()

    # 열 번호
    for j in range(cols):
        dr.text((LAB + j * cell + 6, 2), '%X' % (j % 16), fill=(150, 150, 160), font=f)

    for k, code in enumerate(codes):
        r, cidx = divmod(k, cols)
        x0 = LAB + cidx * cell
        y0 = 14 + r * (cell + 10)
        if cidx == 0:
            dr.text((3, y0 + cell // 2 - 6), '%03X' % code, fill=(150, 200, 150), font=f)
        g = C.raw_to_rows(C.glyph_full(d, code))
        for y in range(BOX):
            for x in range(BOX):
                if (g[y] >> (15 - x)) & 1:
                    dr.rectangle([x0 + 2 + x * Z, y0 + y * Z,
                                  x0 + 2 + x * Z + Z - 1, y0 + y * Z + Z - 1],
                                 fill=(255, 255, 255))
        dr.text((x0 + 2, y0 + BOX * Z), '%02X' % (code & 0xFF),
                fill=(110, 110, 130), font=f)

    img.save(out)
    print('%s  코드 0x%03X~0x%03X (%d개)  %dx%d' % (out, codes[0], codes[-1], len(codes), W, H))


if __name__ == '__main__':
    main()
