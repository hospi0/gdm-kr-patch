# -*- coding: utf-8 -*-
r"""타이틀 화면 그림 한글화 (2026-10-14) — `/BIN/TTL.DAT` 한 파일.
  TTL.DAT = BE u32 섹션 8개, 게임이 LWRAM 0x210000 에 통째로 적재.
    섹션 5 (0xC880) ST1 조각 2개 → VDP1 0x1000‥  메뉴 「新しく始める」0x5580·「続きを行なう」0x5B80(밝음)·0x6180(흐림) 96×16
            (영문 패치 tools/third_party/.../tools/title_menu.py 와 같은 방식 — mg_splice.patch_slot, 트리 고정·snap)
    섹션 6 (0xF1CC) 하위표 7칸 + 판 코덱 스트림 @+0x258(파일 0xF424) → VDP1 0xBC00 로고 296×89(= 풀린 크기 0x66E8)
    섹션 7 (0x13088) 하위표 7칸 + 판 코덱 스트림 @+0x2A0(파일 0x13328) → VDP1 0x1F000 부제 264×24 가 앞머리(풀린 크기 0x11040)
  판 코덱 = 엔진 0x0601A716(필드 스프라이트, 표 고정) — 근거: 타이틀 스테이트 HWRAM 0x060FC000 의 작업 기록
    [하위표 칸 7개, 대상 VDP1] 이 두 블롭을 가리킴(그 자리는 판 코덱 작업 공간). 엔진 디코더로 풀면 VDP1 과 바이트 일치.
  재압축 = viewer_mtout_gfx.encode_block(표정집 배너 facer_banner.py 와 같음) → 엔진 디코더로 되풀어 바이트 일치 검산,
           원래 스트림 자리(섹션 끝까지) 안 + 0 채움 → 파일 크기 불변.
  글자: 한 색 채움 + 글자 둘레 1px 테두리. 색 = 원본 그림에서 쓰던 색인.
  필요: 타이틀 스테이트 HWRAM(엔진 코드) → tools/third_party/new-parm-archives-tools/work/mgame/hwram.bin, work/ttlgfx/title_L.bin
  python tools/build_title_gfx.py [--png]  → work/build/BIN_TTL.DAT
"""
import importlib.util, os, struct, sys
from collections import Counter
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
TP = os.path.join(HERE, 'third_party', 'new-parm-archives-tools')
sys.path[:0] = [os.path.join(TP, 'tools'), os.path.join(TP, 'src', 'theater')]
import mg_splice, mg_tree, gfx_plate      # noqa: E402  (영문 패치 도구 — 우리 tools/ 와 이름 안 겹침)

MENU = [(0x5580, '새로 시작하기', False), (0x5B80, '이어서 하기', False), (0x6180, '이어서 하기', True)]
LOGO_KANA = '그란디아'
SUBTITLE = '~디지털 뮤지엄~'
FONT_B = r'C:\Windows\Fonts\malgunbd.ttf'
GAL_B = r'C:\claude\utils\font\Galmuri-v2.40.3\Galmuri11-Bold.ttf'
FONT_ROUND = r'C:\claude\utils\font\jua\Jua-Regular.ttf'   # 부제 — 원본처럼 둥근 글꼴(주아체, OFL)
LW_BASE = 0x210000
LOGO = dict(src=0xF424, end=0x13088, size=0x66E8, dst=0xBC00, w=296, h=89, col=0x300)
SUB = dict(src=0x13328, end=None, size=0x11040, dst=0x1F000, w=264, h=24, col=0x400)


def W(p):
    return os.path.join(ROOT, p)


def cram_rgb(col):
    c = open(W('work/ttlgfx/title_cram_be.bin'), 'rb').read()
    out = []
    for v in range(256):
        w = struct.unpack_from('>H', c, (col + v) * 2)[0]
        out.append(((w & 31) << 3, ((w >> 5) & 31) << 3, ((w >> 10) & 31) << 3))
    return out


def lwram(dat):
    lw = bytearray(open(W('work/ttlgfx/title_L.bin'), 'rb').read())
    lw[LW_BASE - 0x200000:LW_BASE - 0x200000 + len(dat)] = dat
    return bytes(lw)


def plate_decode(dat, P, hw):
    return bytes(gfx_plate.decode_plate(hw, lwram(dat), LW_BASE + P['src'], len(dat) - P['src'],
                                        P['size'], 1, P['dst'])[:P['size']])


def encoder():
    import types
    sys.modules.setdefault('dicdt', types.ModuleType('dicdt'))   # encode_block 은 안 씀(표 파일 없어도 되게)
    spec = importlib.util.spec_from_file_location('vm', os.path.join(TP, 'tools', 'viewer_mtout_gfx.py'))
    vm = importlib.util.module_from_spec(spec); spec.loader.exec_module(vm)
    return vm.encode_block


def mask_text(text, font, size, w, h, shear=0.0):
    """글 → w×h bool 마스크(가운데 정렬, 1px 테두리 자리 남김)."""
    f = ImageFont.truetype(font, size)
    im = Image.new('L', (w * 2, h * 2), 0)
    ImageDraw.Draw(im).text((w // 2, h // 2), text, font=f, fill=255)
    if shear:
        im = im.transform(im.size, Image.AFFINE, (1, shear, -shear * h, 0, 1, 0))
    bb = im.getbbox(); im = im.crop(bb)
    out = Image.new('L', (w, h), 0)
    out.paste(im, ((w - im.width) // 2, (h - im.height) // 2))
    px = out.load()
    return [[px[x, y] >= 128 for x in range(w)] for y in range(h)], im.size


def stamp(buf, w, h, m, x0, y0, fill, outline):
    H, Wd = len(m), len(m[0])
    for y in range(H):
        for x in range(Wd):
            if m[y][x]:
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        yy, xx = y + dy, x + dx
                        if 0 <= yy < H and 0 <= xx < Wd and not m[yy][xx]:
                            X, Y = x0 + xx, y0 + yy
                            if 0 <= X < w and 0 <= Y < h:
                                buf[Y * w + X] = outline
    for y in range(H):
        for x in range(Wd):
            if m[y][x]:
                X, Y = x0 + x, y0 + y
                if 0 <= X < w and 0 <= Y < h:
                    buf[Y * w + X] = fill


def nearest(rgbs, target, cands):
    return min(cands, key=lambda i: sum((a - b) ** 2 for a, b in zip(rgbs[i], target)))


def do_logo(img):
    """로고 오른쪽 위 가나 「グランディア」 지우고 「그란디아」."""
    w, h = LOGO['w'], LOGO['h']; rgb = cram_rgb(LOGO['col'])
    buf = bytearray(img)
    # 가나 = 로고 본체(GRANDIA 테두리)보다 위쪽 띠. 본체 맨 윗줄 찾기: 왼쪽 G 의 첫 잉크 줄
    top = next(y for y in range(h) if any(buf[y * w + x] for x in range(0, 120)))
    # 가나 상자: x 150‥295, y 0‥top+? → 본체와 떨어진 연결 덩어리만 지운다
    seen = set(); comps = []
    for y in range(h):
        for x in range(w):
            if buf[y * w + x] and (x, y) not in seen:
                st = [(x, y)]; seen.add((x, y)); c = []
                while st:
                    a, b = st.pop(); c.append((a, b))
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        q = (a + dx, b + dy)
                        if 0 <= q[0] < w and 0 <= q[1] < h and q not in seen and buf[q[1] * w + q[0]]:
                            seen.add(q); st.append(q)
                comps.append(c)
    big = max(comps, key=len)
    kana = [c for c in comps if c is not big]
    ys = [p[1] for c in kana for p in c]; xs = [p[0] for c in kana for p in c]
    print('  로고 가나 덩어리 %d개 · 화소 %d · 상자 x%d‥%d y%d‥%d · 본체 첫 줄 %d'
          % (len(kana), len(ys), min(xs), max(xs), min(ys), max(ys), top))
    used = Counter(buf[p[1] * w + p[0]] for c in kana for p in c)
    for c in kana:
        for a, b in c:
            buf[b * w + a] = 0
    fill = nearest(rgb, (248, 248, 248), used); outl = nearest(rgb, (0, 0, 0), used)
    bx0, bx1, by0, by1 = min(xs), max(xs), min(ys), max(ys)
    bw, bh = bx1 - bx0 + 1, by1 - by0 + 1
    import aatext   # 안티(2026-10-14 사용자) — 우주(검정) 위라 가장자리는 검정과 섞음, 원본 가나가 쓰던 색인 안에서
    for size in range(bh + 6, 6, -1):
        cov, (tw, th) = aatext.coverage(LOGO_KANA, FONT_B, size, w, h, [0, 1], fit=(bx0, by0, bw, bh))
        if tw <= bw - 2 and th <= bh - 2:
            break
    keep = bytearray(buf)
    buf = aatext.compose(cov, [rgb[fill], rgb[outl]], w, h, rgb, set(used) | {fill, outl},
                         base=buf, edge_bg=(0, 0, 0), thr=0.15)
    for a, b in big:
        buf[b * w + a] = keep[b * w + a]
    return bytes(buf)


def ring(m, n):
    """마스크를 n px 넓힌 것"""
    H, Wd = len(m), len(m[0]); cur = [r[:] for r in m]
    for _ in range(n):
        nx = [r[:] for r in cur]
        for y in range(H):
            for x in range(Wd):
                if cur[y][x]:
                    for dy in (-1, 0, 1):
                        for dx in (-1, 0, 1):
                            if 0 <= y + dy < H and 0 <= x + dx < Wd:
                                nx[y + dy][x + dx] = True
        cur = nx
    return cur


def do_sub(blob):
    """원본 = 노란 몸통(70) + 초록 테두리(42) + 짙은 초록 바깥선(25). 같은 세 층으로(2026-10-14 사용자: 녹색이 노랗게 됨)."""
    w, h = SUB['w'], SUB['h']; rgb = cram_rgb(SUB['col'])
    import aatext
    YEL, GRN, DARK = 70, 42, 25
    orig = blob[:w * h]
    for size in range(30, 8, -1):
        cov, (tw, th) = aatext.coverage(SUBTITLE, FONT_ROUND, size, w, h, [0, 2, 3], fit=(0, 0, w, h))
        if tw <= w - 8 and th <= h - 5:
            break
    buf = aatext.compose(cov, [rgb[YEL], rgb[GRN], rgb[DARK]], w, h, rgb, set(orig) - {0})   # 원본 부제 색인 안에서 섞음
    print('  부제 글자 %dpx · 몸 %s · 테두리 %s · 바깥선 %s' % (size, rgb[YEL], rgb[GRN], rgb[DARK]))
    return bytes(buf) + blob[w * h:]


def do_menu(dat):
    """섹션 5 메뉴 3장 — 영문 title_menu 의 회색 사다리 색인(RAMP) 중 흰색·검정·회색."""
    sec = list(struct.unpack_from('>8I', dat, 0))
    src, end = sec[5], sec[6]
    pal = []
    for i in range(256):
        v = struct.unpack_from('>H', dat, sec[4] + i * 2)[0]
        pal.append(((v & 31) << 3, ((v >> 5) & 31) << 3, ((v >> 10) & 31) << 3))
    RAMP = [0x01, 0x1a, 0x12, 0x13, 0x11, 0x18, 0x15, 0x14, 0x1d, 0x19, 0x17, 0x16, 0x1b, 0x1c, 0x10]
    white = nearest(pal, (248, 248, 248), RAMP); black = nearest(pal, (0, 0, 0), RAMP)
    grey = nearest(pal, (136, 136, 136), RAMP)
    ch = mg_splice.decode_slot(dat, src)
    c1 = bytearray(ch[1]['pixels'])
    for off, text, dim in MENU:
        b = bytearray(96 * 16)
        # ★원본 = 검은 테두리 없음 — 흰(흐림=회색 0x19) 몸 + 오른쪽 아래 1px 짙은 회색(0x12) 그림자 (2026-10-14 사용자 지적)
        #   안티: 지구 위라 가장자리는 중간 회색(영문 title_menu BG_LUMA 140)과 섞음, 회색 사다리 색인만, 옅은 끝은 투명
        import aatext
        for size in range(16, 8, -1):
            cov, (tw, th) = aatext.coverage(text, FONT_B, size, 96, 16, [0], fit=(0, 0, 95, 15))
            if tw <= 92 and th <= 13:
                break
        b = aatext.compose_over([(aatext.shift(cov[0], 1, 1), pal[0x12]), (cov[0], pal[grey if dim else white])],
                                96, 16, pal, RAMP, bg=lambda x, y: (140, 140, 140), base=bytes(96 * 16), thr=0.3)
        r = off - 0x4000; c1[r:r + 96 * 16] = b
    new = mg_splice.patch_slot(dat, src, end, {1: bytes(c1)}, snap=True, palette_rgb=pal)
    assert len(new) == len(dat)
    chk = mg_tree.decode_blob(new, src)
    assert chk[0]['pixels'] == ch[0]['pixels']
    nd = sum(1 for a, b in zip(chk[1]['pixels'], c1) if a != b)
    print('  메뉴 3장 · 되풀기 차이 %d화소(트리 밖 색 snap) · 크기 불변' % nd)
    return new, pal, bytes(chk[1]['pixels'])


def put_plate(dat, P, img, enc, hw):
    end = P['end'] or len(dat)
    st = enc(img)
    budget = end - P['src']
    assert len(st) <= budget, ('스트림 넘침', len(st), budget)
    out = bytearray(dat)
    out[P['src']:P['src'] + len(st)] = st
    out[P['src'] + len(st):end] = bytes(end - P['src'] - len(st))
    rt = plate_decode(bytes(out), P, hw)
    assert rt == img, '판 코덱 왕복 불일치'
    print('  스트림 %d B / 자리 %d B · 엔진 디코더 왕복 일치' % (len(st), budget))
    return bytes(out)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    src = W('work/dm_all/BIN_TTL.DAT')
    dat = open(src, 'rb').read(); n0 = len(dat)
    hw = open(os.path.join(TP, 'work', 'mgame', 'hwram.bin'), 'rb').read()
    enc = encoder()
    print('로고'); logo0 = plate_decode(dat, LOGO, hw)
    assert logo0 == open(W('work/ttlgfx/logo_v1.bin'), 'rb').read(), '원본 로고 해제가 화면과 다름'
    logo = do_logo(logo0); dat = put_plate(dat, LOGO, logo, enc, hw)
    print('부제'); sub0 = plate_decode(dat, SUB, hw)
    assert sub0[:264 * 24] == open(W('work/ttlgfx/sub_v1.bin'), 'rb').read(), '원본 부제 해제가 화면과 다름'
    sub = do_sub(sub0); dat = put_plate(dat, SUB, sub, enc, hw)
    print('메뉴'); dat, mpal, c1 = do_menu(dat)
    assert len(dat) == n0
    open(W('work/build/BIN_TTL.DAT'), 'wb').write(dat)
    print('✅ work/build/BIN_TTL.DAT %d B' % len(dat))
    if '--png' in sys.argv:
        def save(px, w, h, rgb, name, sc):
            im = Image.new('RGB', (w, h)); im.putdata([(40, 40, 90) if v == 0 else rgb[v] for v in px[:w * h]])
            im.resize((w * sc, h * sc), Image.NEAREST).save(W('work/ttlgfx/' + name))
        save(logo, 296, 89, cram_rgb(0x300), 'ko_logo.png', 2)
        save(sub, 264, 24, cram_rgb(0x400), 'ko_sub.png', 3)
        mm = b''.join(c1[o - 0x4000:o - 0x4000 + 96 * 16] for o, _, _ in MENU)
        save(mm, 96, 48, mpal, 'ko_menu.png', 4)


if __name__ == '__main__':
    main()
