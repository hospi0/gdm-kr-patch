# -*- coding: utf-8 -*-
r"""스테이트 → VDP1 명령표의 스프라이트를 전부 그림으로 뽑기 (2026-10-14, 전투 화면 그래픽 글자 추출용).
  색 모드(PMOD 비트 3‥5): 0 = 4bpp 색뱅크(CMDCOLR 하위 4비트 버림), 1 = 4bpp LUT(CMDCOLR×8 = VRAM 의 16색 표),
                          4 = 8bpp 256색(CMDCOLR = CRAM 워드 오프셋), 5 = 16bpp RGB.
  같은 텍스처(주소·크기·모드·색)는 한 번만. 출력: <out>/<n>_<VRAM>_<w>x<h>.png + <out>/sheet.png(목록) + list.tsv
  python tools/dump_vdp1_sprites.py <state> <out_dir>
  (Beetle Saturn 스테이트 VDP1 VRAM·WorkRAM 은 swap16 — 이 게임 [[project_grandia_dm_kr]] 확인)
"""
import os, struct, sys
from PIL import Image, ImageDraw
sys.path.insert(0, r'C:\claude\project\virus-kr-patch\tools')
import rzip
from mdfnstate import sections, swap16


def rgb555(w):
    return ((w & 31) << 3, ((w >> 5) & 31) << 3, ((w >> 10) & 31) << 3)


def main(state, out):
    os.makedirs(out, exist_ok=True)
    raw = open(state, 'rb').read()
    if raw[:6] == b'#RZIPv':
        raw = rzip.unpack(state)[0] if 'gdm' in rzip.__file__ else rzip.unpack(raw)
    s = sections(raw)
    V = swap16(s['VDP1']['VRAM'])
    c = s['VDP2']['CRAM']; c = bytes(b for i in range(0, len(c), 2) for b in (c[i + 1], c[i]))
    cram = [rgb555(struct.unpack_from('>H', c, i * 2)[0]) for i in range(len(c) // 2)]
    # 스프라이트 색 = (색 코드 & 스프라이트 형식 비트) + CRAOFB×256 (VDP2 레지스터 — 안 넣으면 색이 엉뚱함)
    rr = s['VDP2']['RawRegs']; reg = lambda o: struct.unpack_from('<H', rr, o)[0]
    spctl, craofb = reg(0xE0), reg(0xE6)
    stype = spctl & 15
    cmask = 0x7FF if stype < 8 else 0xFF
    cofs = ((craofb >> 4) & 7) * 256
    cidx = lambda code: cram[((code & cmask) + cofs) % len(cram)]
    print('  SPCTL %X 형식 %d · 색 마스크 %X · CRAM 오프셋 %X' % (spctl, stype, cmask, cofs))
    a = 0; n = 0; seen = set(); items = []; ret = None
    while a < 0x80000 and n < 4000:
        cmd = struct.unpack_from('>16H', V, a); ctrl = cmd[0]
        if ctrl & 0x8000:
            break
        jp = (ctrl >> 12) & 7; ct = ctrl & 15
        if not (ctrl & 0x4000) and ct in (0, 1, 2):
            pm, col, src = cmd[2], cmd[3], cmd[4] * 8
            w = ((cmd[5] >> 8) & 0x3F) * 8; h = cmd[5] & 0xFF
            cm = (pm >> 3) & 7
            key = (src, w, h, cm, col)
            if w and h and key not in seen:
                seen.add(key)
                im = Image.new('RGBA', (w, h), (0, 0, 0, 0)); px = im.load()
                for y in range(h):
                    for x in range(w):
                        if cm in (0, 1):
                            o = src + (y * w + x) // 2
                            if o >= len(V):
                                continue
                            v = V[o] >> 4 if x % 2 == 0 else V[o] & 15
                            if v == 0:
                                continue
                            if cm == 0:
                                rgb = cidx((col & 0xFFF0) | v)
                            else:
                                rgb = rgb555(struct.unpack_from('>H', V, (col * 8 + v * 2) % 0x80000)[0])
                        elif cm == 5:
                            o = src + (y * w + x) * 2
                            if o + 2 > len(V):
                                continue
                            ww = struct.unpack_from('>H', V, o)[0]
                            if not ww & 0x8000:
                                continue
                            rgb = rgb555(ww)
                        else:
                            o = src + y * w + x
                            if o >= len(V):
                                continue
                            v = V[o]
                            if v == 0:
                                continue
                            rgb = cidx((col & 0xFF00) | v) if cm == 4 else cidx(col + v)
                        px[x, y] = rgb + (255,)
                fn = '%03d_%05X_%dx%d_m%d.png' % (len(items), src, w, h, cm)
                im.save(os.path.join(out, fn))
                items.append((fn, src, w, h, cm, col, im))
        # 점프: 0 다음 · 1 이동 · 2 호출(복귀 주소 저장) · 3 복귀 · 4‥7 = 건너뛰기(+같은 규칙)
        j = jp & 3
        if j == 0:
            nxt = a + 0x20
        elif j == 1:
            nxt = cmd[1] * 8
        elif j == 2:
            ret = a + 0x20; nxt = cmd[1] * 8
        else:
            nxt = ret if ret is not None else a + 0x20; ret = None
        a = nxt; n += 1
    with open(os.path.join(out, 'list.tsv'), 'w', encoding='utf-8') as f:
        f.write('파일\tVRAM\tw\th\t색모드\tCMDCOLR\n')
        for fn, src, w, h, cm, col, _ in items:
            f.write('%s\t0x%05X\t%d\t%d\t%d\t0x%04X\n' % (fn, src, w, h, cm, col))
    # 목록 그림(2배, 줄바꿈)
    S = 2; W = 1400; x = y = 0; rowh = 0; pos = []
    for it in items:
        w, h = it[2] * S, it[3] * S + 12
        if x + w > W:
            x = 0; y += rowh + 6; rowh = 0
        pos.append((x, y)); x += w + 6; rowh = max(rowh, h)
    sheet = Image.new('RGB', (W, y + rowh + 6), (50, 50, 60)); d = ImageDraw.Draw(sheet)
    for (x, y), it in zip(pos, items):
        im = it[6].resize((it[2] * S, it[3] * S), Image.NEAREST)
        sheet.paste(im, (x, y + 12), im)
        d.text((x, y), '%s %X' % (it[0][:3], it[1]), fill=(255, 255, 0))
    sheet.save(os.path.join(out, 'sheet.png'))
    print('%s: 스프라이트 %d개 → %s' % (os.path.basename(state), len(items), out))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
