# -*- coding: utf-8 -*-
"""한글 글리프를 16×16 1bpp로 렌더하고 XOR 델타 인코딩 크기를 실측한다.

폰트는 나눔명조. 아웃라인 폰트라 16px에서는 크기·임계값·원점에 따라
결과가 크게 달라지므로, 조합을 훑어 **인코딩 크기와 모양을 함께** 낸다.

사용:
  python tools/hangul_glyph.py sweep          크기/임계값 조합 실측
  python tools/hangul_glyph.py sheet <크기> <임계값> [문자열]   미리보기 시트
"""
import struct
import sys
import zlib

sys.path.insert(0, 'tools')
import font_codec as C
from PIL import Image, ImageDraw, ImageFont

FONT = r'C:\claude\utils\font\nanum-myeongjo\NanumMyeongjo.ttf'
BOLD = r'C:\claude\utils\font\nanum-myeongjo\NanumMyeongjoBold.ttf'
GOTHIC = r'C:\claude\utils\font\nanum-gothic\NanumGothic.ttf'
GOTHIC_BOLD = r'C:\claude\utils\font\nanum-gothic\NanumGothicBold.ttf'
GOTHIC_XBOLD = r'C:\claude\utils\font\nanum-gothic\NanumGothicExtraBold.ttf'
BOX = 16


def render(ch, font, size, thr, dx=0, dy=0):
    """글자 하나 → 16행 × 16비트"""
    img = Image.new('L', (BOX, BOX), 0)
    dr = ImageDraw.Draw(img)
    f = ImageFont.truetype(font, size)
    a = f.getbbox(ch)
    w = a[2] - a[0]
    ox = (BOX - w) // 2 - a[0] + dx
    oy = (BOX - size) // 2 - a[1] + (size - (a[3] - a[1])) // 2 + dy
    dr.text((ox, oy), ch, fill=255, font=f)
    px = img.load()
    rows = []
    for y in range(BOX):
        v = 0
        for x in range(BOX):
            v = (v << 1) | (1 if px[x, y] >= thr else 0)
        rows.append(v)
    return rows


def syllables():
    return [chr(c) for c in range(0xAC00, 0xD7A4)]


def sweep():
    S = syllables()
    print('%-22s %-6s %-7s %-7s %-7s %s'
          % ('폰트/크기/임계값', '평균B', '최대B', '빈글자', '박스넘침', '세로획2px비'))
    for font, fname in ((FONT, '명조'), (BOLD, '명조Bold')):
        for size in (14, 15, 16):
            for thr in (96, 128, 160):
                tot = mx = empty = over = 0
                stem2 = 0
                for ch in S:
                    rows = render(ch, font, size, thr)
                    raw = C.rows_to_raw(rows)
                    n = len(C.encode_record(raw))
                    tot += n
                    mx = max(mx, n)
                    if not any(rows):
                        empty += 1
                    if rows[0] or rows[BOX - 1] or any(r & 1 for r in rows) \
                            or any(r & 0x8000 for r in rows):
                        over += 1
                    # 가로 잉크런 중 길이1 비율(가늘기 지표)
                    ones = 0
                    runs = 0
                    for r in rows:
                        b = bin(r)[2:].zfill(16)
                        for part in b.split('0'):
                            if part:
                                runs += 1
                                if len(part) == 1:
                                    ones += 1
                    if runs:
                        stem2 += 1 - ones / runs
                k = len(S)
                print('%-22s %-6.1f %-7d %-7d %-7d %.2f'
                      % ('%s/%d/%d' % (fname, size, thr), tot / k, mx, empty,
                         over, stem2 / k))


def sheet(size, thr, text, font=FONT):
    rows_all = [render(ch, font, size, thr) for ch in text]
    cols = min(32, len(text))
    rn = (len(text) + cols - 1) // cols
    W, H = cols * 17, rn * 17
    img = [bytearray([48] * W) for _ in range(H)]
    for k, rows in enumerate(rows_all):
        gx, gy = (k % cols) * 17, (k // cols) * 17
        for y in range(BOX):
            for x in range(BOX):
                img[gy + y][gx + x] = 255 if (rows[y] >> (15 - x)) & 1 else 0

    def chunk(t, b):
        return (struct.pack('>I', len(b)) + t + b
                + struct.pack('>I', zlib.crc32(t + b) & 0xFFFFFFFF))

    raw = b''.join(b'\x00' + bytes(r) for r in img)
    out = 'work/hangul_%d_%d.png' % (size, thr)
    open(out, 'wb').write(
        b'\x89PNG\r\n\x1a\n'
        + chunk(b'IHDR', struct.pack('>IIBBBBB', W, H, 8, 0, 0, 0, 0))
        + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))
    enc = [len(C.encode_record(C.rows_to_raw(r))) for r in rows_all]
    print('%s  %d글자  평균 %.1f B  최대 %d B'
          % (out, len(text), sum(enc) / len(enc), max(enc)))


if __name__ == '__main__':
    if sys.argv[1] == 'sweep':
        sweep()
    else:
        t = sys.argv[4] if len(sys.argv) > 4 else \
            '가나다라마바사아자차카타파하검은고양이가담장위를조용히걸어간다우리는' \
            '이제마을로돌아가야한다무엇을찾고있었지왕국의비밀을알려주마'
        sheet(int(sys.argv[2]), int(sys.argv[3]), t)
