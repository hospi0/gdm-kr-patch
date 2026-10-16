# -*- coding: utf-8 -*-
r"""전투·전투 결과 화면의 «구운 그림 글자» 한글화 — 압축 그림 3묶음 (2026-10-14).
  코덱 = 판 코덱(엔진 0x0601A716) = 우리 gsprite/gsprite_comp. 모두 VDP1 4bpp 색표(LUT) 스프라이트.
  A. 결과 머리  BATLE/ENDW.DAT  0x3A48 → VDP1 0x44000 (10,976 B)  : 戦闘結果 0x44000 112×32 · 経験値 0x44700 64×24 · 習得技術 0x46720 80×24
  B. 전투 크롬  BATLE/MGDAT.BIN 0x18B90 → VDP1 0x44000 (28,640 B) : 링 라벨 56×16 (コンボ 0x441C0 …どうぐ 0x44C40) · 技 0x473A0 16×16 ·
                                                                  魔法 0x477C0 32×16 · 머리 위 이름판 スー 0x453A0 48×16 …
  C. 파티 이름표 BATLE/*.BBG    0x10634(B001 기준, 같은 스트림 사본을 파일마다 찾아 씀) → VDP1 0x4000 (40,056 B, XOR):
                                                                  ジャスティン 0x5950 48×14 · フィーナ 0x5AA0 48×12 · スー 0x5BC0 48×12
  (위치 출처: 영문 패치 pO4_chrome_codec·pW3_endw_style·pO4c_nameplate_fold 기록 → 우리 스테이트 VRAM 과 바이트 일치 확인)
  셀마다: 원본 글자의 몸·테두리 번호(밝은 최빈·가장 어두운) 뽑기 → 셀 비우기 → 한글(4배 그려 안티, 원본 셀이 쓰던 번호 안에서만) + 1px 테두리.
  색은 스테이트의 색표(LUT, CMDCOLR×8) → CRAM 으로 풀어 고름.
  python tools/build_battle_gfx.py [--png]   (build_batle·build_mdat 뒤 — BBG 를 그 결과 위에 고침)
"""
import os, struct, sys
from collections import Counter
from PIL import Image, ImageDraw, ImageFont
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, r'C:\claude\project\virus-kr-patch\tools')
import gsprite as G, gsprite_comp as GC, aatext

FB = r'C:\Windows\Fonts\malgunbd.ttf'
G7 = r'C:\claude\utils\font\Galmuri-v2.40.3\Galmuri7.ttf'
G11 = r'C:\claude\utils\font\Galmuri-v2.40.3\Galmuri11-Bold.ttf'   # 크롬 라벨 — 화소 글꼴이 압축 쌈(MGDAT 16,384 B 빠듯)
ST = os.path.join(ROOT, 'my files', '할일')
NEWST, NEW_LO, NEW_HI = '전투추가/작전.state', 0x48000, 0x4A920
DEFST, DEF_LO, DEF_HI = '전투추가/방어.state', 0x4A920, 0x4B000   # 방어 하위 메뉴 防御·実行·回避(2026-10-16 사용자 방어.state)
DRY = '--dry' in sys.argv                         # 미리보기만(work/build 안 씀)
KJ = ('emboss', dict(body=0xF, hi=None, shade=0xE, shadow=0x1, font='G11', sh3=True))   # 작전·도구 창 한자 칸: 흰 몸 + 오른쪽·아래 검은 그림자
KT = ('emboss', dict(body=0xE, hi=None, shade=0xD, shadow=0x1, font='G11', sh3=True, left=1))   # 작전 이름(색표 FE88: E=흰·F=검정), 원본처럼 왼쪽 붙임
# (묶음, 파일, 압축 위치, 풀린 기준 VRAM, 스테이트(색표용), [(VRAM, w, h, 글, CMDCOLR, 글꼴)])
SETS = [
    ('A', 'BATLE_ENDW.DAT', 0x3A48, 0x44000, '전투/5.state4', [
        (0x44000, 112, 32, '전투 결과', 0xFE00, FB),
        (0x44700, 64, 24, '경험치', 0xFE04, FB),
        (0x46720, 80, 24, '습득 기술', 0xFE04, FB)]),
    ('B', 'BATLE_MGDAT.BIN', 0x18B90, 0x44000, '전투/1.state', [
        (0x441C0, 56, 16, '＼콤보', 0xFE80, G11), (0x44380, 56, 16, '＼크리티컬', 0xFE80, G11),
        (0x44540, 56, 16, '＼방어', 0xFE80, G11), (0x44700, 56, 16, '＼보기', 0xFE80, G11),
        (0x448C0, 56, 16, '＼도주', 0xFE80, G11), (0x44A80, 56, 16, '＼작전', 0xFE80, G11),
        (0x44C40, 56, 16, '＼도구', 0xFE80, G11),
        (0x450A0, 48, 16, '저스틴', 0xFE80, 'head'), (0x45220, 48, 16, '피나', 0xFE80, 'head'),   # 머리 위 이름판(2026-10-14 사용자 스테이트)
        (0x453A0, 48, 16, '수', 0xFE80, 'head'),
        (0x45520, 48, 16, '가드인', 0xFE80, 'head'), (0x456A0, 48, 16, '랩', 0xFE80, 'head'), (0x45820, 48, 16, '밀다', 0xFE80, 'head'),
        (0x459A0, 48, 16, '기드', 0xFE80, 'head'), (0x45B20, 48, 16, '리에테', 0xFE80, 'head'),   # 나머지 이름판(スー 뒤 0x180 간격)
        (0x477C0, 32, 16, '마법', 0xFE80, ('emboss', dict(body=0xF, hi=None, shade=0xE, shadow=0x1, font='G11'))),
        (0x473A0, 16, 16, '기', 0xFE80, ('emboss', dict(body=0xF, hi=None, shade=0xE, shadow=0x1, font='G11'))),   # 技 → «기» 한 글자, 마법과 같은 글꼴(사용자 지시)
        # 2026-10-14 전투추가: 8번째 링 라벨 ＼わざ・まほう · 도구 창 머리 道具 · 작전 창(머리·탭·작전 이름 8개)
        (0x44E00, 56, 16, '＼기술·마법', 0xFE80, G11),
        (0x48060, 32, 16, '도구', 0xFE80, KJ),
        (0x48160, 32, 16, '작전', 0xFE80, KJ), (0x48260, 32, 16, '설정', 0xFE80, KJ),
        (0x488A0, 32, 16, '변경', 0xFE80, KJ),   # 작전 창 머리 変更(2026-10-16 사용자 변경.state1)
        (0x489A0, 32, 16, '개인', 0xFF80, KJ), (0x48AA0, 32, 16, '작전', 0xFF80, KJ),
        (0x48BA0, 32, 16, '실행', 0xFF80, KJ), (0x48CA0, 32, 16, '전체', 0xFF80, KJ),
        (0x49920, 64, 16, '수동', 0xFE88, KT), (0x49B20, 64, 16, '정정당당', 0xFE88, KT),
        (0x49D20, 64, 16, '준비만전', 0xFE88, KT), (0x49F20, 64, 16, '묻어가기', 0xFE88, KT),
        (0x4A120, 64, 16, '십인십색', 0xFE88, KT), (0x4A320, 64, 16, '안전제일', 0xFE88, KT),
        (0x4A520, 64, 16, '광희난무', 0xFE88, KT), (0x4A720, 64, 16, '비겁천만', 0xFE88, KT),
        # 2026-10-16 방어 하위 메뉴(L 防御実行 · 가운데 防御 · R 回避) — 防御 칸은 FE80/FF80 두 번 찍힘(같은 그림)
        (0x4A920, 32, 16, '방어', 0xFF80, KJ), (0x4ADE0, 32, 16, '실행', 0xFF80, KJ), (0x4AEE0, 32, 16, '회피', 0xFF80, KJ)]),
    ('C', 'BATLE_B001.BBG', 0x10634, 0x4000, '전투/1.state', [
        (0x5950, 48, 14, '저스틴', 0xFC08, ('emboss', dict(body=0xE, hi=None, shade=None, shadow=0x1, font='G11', plate=True))), (0x5AA0, 48, 12, '피나', 0xFC08, ('emboss', dict(body=0xE, hi=None, shade=None, shadow=0x1, font='G11', plate=True))),
        (0x5BC0, 48, 12, '수', 0xFC08, ('emboss', dict(body=0xE, hi=None, shade=None, shadow=0x1, font='G11', plate=True))),
        # 나머지 파티 이름표(スー 뒤 48×14, 0x150 간격 — 2026-10-14 사용자 «다른 이름판»)
        ] + [(0x5CE0 + 0x150 * k, 48, 14, t, 0xFC08, ('emboss', dict(body=0xE, hi=None, shade=None, shadow=0x1, font='G11', plate=True)))
             for k, t in enumerate(['가드인', '랩', '밀다', '기드', '리에테'])]),
    # D. 기술 창 머리 「しゅうとくスキル」 — MGDAT 0xC6A4 판 코덱 → VDP2 0x3400, 셀 0x1B2‥0x1B9 가로 한 줄(64×8)
    #    (영문 pVDF_battlemenu_fold 기록의 디스크 원시 0xEB0674). 테두리 점무늬(2·e·9·b) 위 글자(f·d·1).
    ('D', 'BATLE_MGDAT.BIN', 0xC6A4, 0x3400, None, {'tiles': list(range(0x1B2, 0x1BA)), 'text': '습득 스킬'}),
    # E. 작전 창 줄 라벨 「個人作戦:」「全体作戦:」 — MGDAT 0x15FE4 판 코덱 → VDP2 0x3400 (NBG3, 배치표 0xE000, 팔레트 5)
    #    한자 하나 = 16×16(셀 2×2), 「作戦」 칸은 두 줄 공유. 콜론 0x1A1/0x1A2 는 그대로. (전투추가/작전.state 로 확인)
    ('E', 'BATLE_MGDAT.BIN', 0x15FE4, 0x3400, None, {'blocks': [
        ([0x1A3, 0x1A4, 0x1A5, 0x1A6], [0x1AB, 0x1AC, 0x1AD, 0x1AE], '개인'),
        ([0x1A7, 0x1A8, 0x1A9, 0x1AA], [0x1AF, 0x1B0, 0x1B1, 0x1B2], '작전'),
        ([0x1B3, 0x1B4, 0x1B5, 0x1B6], [0x1B7, 0x1B8, 0x1B9, 0x1BA], '전체')], 'pal': ('전투추가/작전.state', 0x500 + 5 * 16)}),
]


def rgb555(w):
    return ((w & 31) << 3, ((w >> 5) & 31) << 3, ((w >> 10) & 31) << 3)


_st = {}


def state(fn):
    if fn not in _st:
        import rzip
        from mdfnstate import sections, swap16
        path = os.path.join(ST, fn)
        raw = open(path, 'rb').read()
        if raw[:6] == b'#RZIPv':
            raw = rzip.unpack(path)[0]                 # gdm tools/rzip (경로 받음)
        s = sections(raw)
        c = s['VDP2']['CRAM']; c = bytes(b for i in range(0, len(c), 2) for b in (c[i + 1], c[i]))
        rr = s['VDP2']['RawRegs']; reg = lambda o: struct.unpack_from('<H', rr, o)[0]
        _st[fn] = (swap16(s['VDP1']['VRAM']), [rgb555(struct.unpack_from('>H', c, i * 2)[0]) for i in range(len(c) // 2)],
                   reg(0xE0) & 15, ((reg(0xE6) >> 4) & 7) * 256)
    return _st[fn]


def lut_rgb(fn, col):
    V, cram, stype, cofs = state(fn)
    out = []
    for i in range(16):
        w = struct.unpack_from('>H', V, (col * 8 + i * 2) % 0x80000)[0]
        if w & 0x8000:
            out.append(rgb555(w))
        else:
            out.append(cram[((w & (0x7FF if stype < 8 else 0xFF)) + cofs) % len(cram)])
    return out


def get4(blk, off, w, h):
    return [[(blk[off + (y * w + x) // 2] >> (4 if x % 2 == 0 else 0)) & 15 for x in range(w)] for y in range(h)]


def put4(blk, off, w, h, px):
    for y in range(h):
        for x in range(0, w, 2):
            blk[off + (y * w + x) // 2] = (px[y][x] << 4) | px[y][x + 1]


def lum(c):
    return c[0] * 299 + c[1] * 587 + c[2] * 114


G9 = G11.replace('Galmuri11-Bold', 'Galmuri9')
G11R = G11.replace('Galmuri11-Bold', 'Galmuri11')
TICK_W = 9                                        # 링 라벨 앞 연결 꺾쇠(＼‾) 폭 — 잉크 덩어리로 찾으면 첫 글자까지 붙음


def _pixel_mask(text, font, size, w, h, x0, y0, bw, bh):
    """화소 글꼴을 제 크기로, 안티 없이(임계 128) — 상자 가운데."""
    f = ImageFont.truetype(font, size)
    bb = ImageDraw.Draw(Image.new('L', (8, 8))).textbbox((0, 0), text, font=f)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    im = Image.new('L', (w, h), 0)
    ImageDraw.Draw(im).text((x0 + (bw - tw) // 2 - bb[0], y0 + max(0, (bh - th) // 2) - bb[1]), text, font=f, fill=255)   # 상자보다 크면 위를 자르지 않고 아래로
    p = im.load()
    return [[p[x, y] >= 128 for x in range(w)] for y in range(h)], tw, th


def _roles(px, w, h):
    """몸·테두리 번호를 «구조»로: 투명(0)과 맞닿는 비율이 높은 = 테두리, 안쪽에 많은 = 몸.
    (색표 밝기로 고르면 화면마다 색표가 달라 반전 — 마법·이름표, 2026-10-14)"""
    used = Counter(v for row in px for v in row if v)
    touch = Counter()
    for y in range(h):
        for x in range(w):
            v = px[y][x]
            if v and any(not (0 <= x + dx < w and 0 <= y + dy < h) or px[y + dy][x + dx] == 0
                         for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                touch[v] += 1
    top = [v for v, _ in used.most_common(4)]
    outl = max(top, key=lambda v: touch[v] / used[v])
    rest = [v for v in top if v != outl] or [outl]
    body = min(rest, key=lambda v: touch[v] / used[v] - used[v] / 1e6)
    return used, body, outl


def ring_params(px, w, h):
    """링 라벨 셀 하나에서 모양 변수(글꼴·크기·윗줄·테두리 유무)와 색 번호를 뽑음."""
    used, body, outl = _roles(px, w, h)
    ink = [(x, y) for y in range(h) for x in range(TICK_W, w) if px[y][x]]
    iy0, iy1 = min(p[1] for p in ink), max(p[1] for p in ink)
    edge = sum(1 for x, y in ink if px[y][x] == body and any(
        0 <= x + dx < w and 0 <= y + dy < h and px[y + dy][x + dx] == outl for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))))
    nb = sum(1 for x, y in ink if px[y][x] == body) or 1
    has_out = edge / nb > 0.25
    bh = iy1 - iy0 + 1
    fnt, size = (G11 if has_out else G11R, 12) if bh >= 11 else ((G9, 10) if bh >= 9 else (G7, 8))
    return dict(fnt=fnt, size=size, iy0=iy0, bh=bh, has_out=has_out, body=body, outl=outl)


RING = {}                                         # main 에서 채움: 모양 = «도구» 셀, 색 = «작전» 셀(2026-10-14 사용자 지시)


def redraw(px, w, h, text, pal, font, aa=True):
    used, body, outl = _roles(px, w, h)
    if text.startswith('＼') and RING:                # 링 라벨 7개 통일
        r = RING
        new = [[px[y][x] if x < TICK_W else 0 for x in range(w)] for y in range(h)]
        x0 = TICK_W + 1; bw = w - x0 - 1
        m, tw, th = _pixel_mask(text[1:], G7, 8, w, h, x0, r['iy0'], bw, r['bh'])
        sh = max(0, (bw - tw) // 2)
        m = [[row[x + sh] if x + sh < w else False for x in range(w)] for row in m]
        # 원본 = 흰 몸 f + 오른쪽·아래 회색 그림자 a (테두리 아님 — 하늘색 4 는 꺾쇠 색)
        for y in range(h):
            for x in range(w):
                if not m[y][x] and any(0 <= y - dy < h and 0 <= x - dx < w and m[y - dy][x - dx]
                                       for dx, dy in ((1, 0), (0, 1), (1, 1))):
                    new[y][x] = 0xA
        for y in range(h):
            for x in range(w):
                if m[y][x]:
                    new[y][x] = 0xF
        return new, r['size']
    keep_w = 0
    if text.startswith('＼'):                       # 링 라벨 앞 꺾쇠는 원본 그대로
        text = text[1:]; keep_w = TICK_W
    ink = [(x, y) for y in range(h) for x in range(keep_w, w) if px[y][x]]
    ix0, ix1 = min(p[0] for p in ink), max(p[0] for p in ink)
    iy0, iy1 = min(p[1] for p in ink), max(p[1] for p in ink)
    # 원본에 테두리가 있나: 몸 화소 둘레(4방향)에 가장 어두운 색이 붙은 비율
    edge = sum(1 for x, y in ink if px[y][x] == body and any(
        0 <= x + dx < w and 0 <= y + dy < h and px[y + dy][x + dx] == outl for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))))
    nb = sum(1 for x, y in ink if px[y][x] == body) or 1
    has_out = edge / nb > 0.25
    new = [[px[y][x] if x < keep_w else 0 for x in range(w)] for y in range(h)]
    bh = iy1 - iy0 + 1
    if font in (G11, G7):                            # 화소 글꼴: 원본 글자 높이에 맞는 크기, 안티 없음
        fnt, size = (G11 if has_out else G11R, 12) if bh >= 11 else ((G9, 10) if bh >= 9 else (G7, 8))
        x0 = keep_w + 1 if keep_w else max(0, ix0 - 1)
        bw = w - x0 - (1 if has_out else 0)
        m, tw, th = _pixel_mask(text, fnt, size, w, h, x0, iy0 - (1 if has_out else 0), bw, bh + (2 if has_out else 0))
        if keep_w:                                   # 링 라벨은 꺾쇠 바로 뒤에 왼쪽 맞춤
            sh = max(0, (bw - tw) // 2)
            m = [[row[x + sh] if x + sh < w else False for x in range(w)] for row in m]
        for y in range(h):
            for x in range(w):
                if m[y][x]:
                    new[y][x] = body
                elif has_out and any(0 <= x + dx < w and 0 <= y + dy < h and m[y + dy][x + dx]
                                     for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                    new[y][x] = outl
        return new, size
    x0 = keep_w + 1
    bw, bh2 = w - x0 - 1, h - 2
    for size in range(bh2 + 6, 5, -1):
        _, (tw, th) = aatext.coverage(text, font, size, w, h, [0], fit=(x0, 1, bw, bh2))
        if tw <= bw and th <= bh2:
            break
    cov, _ = aatext.coverage(text, font, size, w, h, [0, 1], fit=(x0, 1, bw, bh2))
    flat = [v for row in new for v in row]
    cands = [v for v in used] if aa else [body, outl]
    out = aatext.compose(cov, [pal[body], pal[outl]], w, h, pal, cands, base=bytes(flat), thr=0.35,
                         edge_bg=pal[outl])
    return [[out[y * w + x] for x in range(w)] for y in range(h)], size


# 이름표 바탕 무늬(아래에서부터): 기준선 5 / 점선 6,7,8,8,7,7,6(짝수 x 2‥44) — 원본 수·피나 셀에서 읽음
PLATE_ROWS = [6, 7, 7, 8, 8, 7, 6]


def headplate(px, w, h, text):
    """머리 위 이름판(48×16): 원본 양식 고정 — 몸 F(위)·E(아래), 둘레 1px 중 왼·위 쪽 3(파랑)·오른·아래 쪽 2(어둠).
    칸 전체 가운데 정렬(원본 잉크 위치 따르면 짧은 이름이 밀림), 글자 위는 0행부터 — 2026-10-14 사용자 «색·정렬 개판»."""
    m, tw, th = _pixel_mask(text, G11, 12, w, h, 0, 0, w, 13)
    ys = [y for y in range(h) for x in range(w) if m[y][x]]
    mid = (min(ys) + max(ys)) // 2 if ys else h // 2
    on = lambda y, x: 0 <= y < h and 0 <= x < w and m[y][x]
    new = [[0] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            if on(y, x):
                new[y][x] = 0xF if y <= mid else 0xE
            elif any(on(y + dy, x + dx) for dy in (0, 1) for dx in (0, 1)):
                new[y][x] = 3                          # 글자의 왼·위 쪽
            elif any(on(y + dy, x + dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1)):
                new[y][x] = 2                          # 오른·아래 쪽
    return new, 12


def emboss(px, w, h, text, st):
    """양각 양식: 위 가장자리 hi · 몸 body · 아래 절반 shade · (1,1) 그림자 shadow. plate=True 면 이름표 바탕 무늬 다시 깔기."""
    fnt = {'G11': G11, 'G9': G9, 'G7': G7}[st['font']]
    size = {'G11': 12, 'G9': 10, 'G7': 8}[st['font']]
    new = [[0] * w for _ in range(h)]
    if st.get('plate'):
        for k, v in enumerate(reversed(PLATE_ROWS)):
            y = h - 2 - k
            for x in range(2, 46, 2):
                new[y][x] = v
            new[y][46] = 5
        for x in range(2, 47):
            new[h - 1][x] = 5
        top, bot = 0, h - 2                           # 글자는 기준선 위
    else:
        top, bot = 0, h
    m, tw, th = _pixel_mask(text, fnt, size, w, h, 0, top, w - 1, bot - top - 1)
    if st.get('left') is not None:                    # 왼쪽 붙임: 잉크 왼끝을 left 열로
        xs = [x for y in range(h) for x in range(w) if m[y][x]]
        sh = min(xs) - st['left'] if xs else 0
        m = [[row[x + sh] if 0 <= x + sh < w else False for x in range(w)] for row in m]
    if st.get('plate'):                               # 새 글자 가로 범위(±1)엔 무늬 없음 — 원본도 글자 뒤는 비어 있음, 압축 −
        xs = [x for y in range(h) for x in range(w) if m[y][x]]
        if xs:
            for y in range(h - 1):
                for x in range(max(0, min(xs) - 1), min(w, max(xs) + 3)):
                    if new[y][x] in PLATE_ROWS:
                        new[y][x] = 0
    ys = [y for y in range(h) for x in range(w) if m[y][x]]
    my0, my1 = (min(ys), max(ys)) if ys else (0, h)
    for y in range(h):
        for x in range(w):
            dirs = ((1, 0), (0, 1), (1, 1)) if st.get('sh3') else ((1, 1),)   # sh3 = 오른쪽·아래·대각 그림자(작전 창 한자 칸)
            if not m[y][x] and st['shadow'] is not None and any(
                    x >= dx and y >= dy and m[y - dy][x - dx] for dx, dy in dirs):
                new[y][x] = st['shadow']
    for y in range(h):
        for x in range(w):
            if m[y][x]:
                v = st['body']
                if st.get('hi') is not None and (y == 0 or not m[y - 1][x]):
                    v = st['hi']
                elif st.get('shade') is not None and y > (my0 + my1) // 2 + 1:
                    v = st['shade']
                new[y][x] = v
    return new, size


def fit_table(data, lut, mode, rl, budget):
    """자리를 넘으면 9바이트 부호 길이표의 두 칸을 맞바꿔 가며(유효 표만) 줄이기 — 자리에 들면 멈춤."""
    import itertools
    SEED = [0, 128, 64, 32, 16, 8, 4, 2, 1]
    nib = lambda t: [(t[i // 2] >> (4 if i % 2 == 0 else 0)) & 15 for i in range(18)]
    pack = lambda n: bytes((n[i] << 4) | n[i + 1] for i in range(0, 18, 2))
    cur = nib(lut); best = len(GC.compress(data, lut, mode, rl)); bt = None
    for _ in range(3):
        moved = False
        for i, j in itertools.permutations(range(17), 2):
            n = cur[:]; n[i], n[j] = n[j], n[i]
            if n == cur or sum(SEED[v] for v in n[:17]) != 256:
                continue
            t = pack(n)
            try:
                st = GC.compress(data, t, mode, rl)
                if G.decompress(st + b'\0' * 8, 0, limit=0x20000)[0] != data:
                    continue
            except Exception:
                continue
            if len(st) < best:
                best, cur, bt, moved = len(st), n, st, True
                print('  부호표 바꿈 → %d B' % best, flush=True)
                if best <= budget:
                    return bt
        if not moved:
            break
    return bt if bt and len(bt) <= budget else None


def tile_label(px, w, h, text):
    """점무늬 테두리 위 글자 줄: 글자 화소(f·d·1·c) 지우고 줄마다 2칸 주기 무늬로 되살림 → 갈무리7 몸 f + (1,1) 그림자 1."""
    TXT = {0xF, 0xD, 0x1, 0xC}
    new = [row[:] for row in px]
    for y in range(h):
        pat = {}
        for x in range(w):
            if px[y][x] not in TXT:
                pat.setdefault(x % 2, Counter())[px[y][x]] += 1
        for x in range(w):
            if px[y][x] in TXT:
                c = pat.get(x % 2)
                new[y][x] = c.most_common(1)[0][0] if c else 0
    f = ImageFont.truetype(G7, 8)
    bb = ImageDraw.Draw(Image.new('L', (8, 8))).textbbox((0, 0), text, font=f)
    im = Image.new('L', (w, h), 0)
    ImageDraw.Draw(im).text((2 - bb[0], (h - (bb[3] - bb[1])) // 2 - bb[1]), text, font=f, fill=255)
    p = im.load(); on = lambda y, x: 0 <= y < h and 0 <= x < w and p[x, y] >= 128
    for y in range(h):
        for x in range(w):
            if not on(y, x) and on(y - 1, x - 1):
                new[y][x] = 1
    for y in range(h):
        for x in range(w):
            if on(y, x):
                new[y][x] = 0xF
    return new


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    previews = []
    done = set()                                       # 이번 실행에서 이미 쓴 파일(B·D 가 같은 MGDAT) → 그 결과 위에
    for tag, fn, comp, base, stf, cells in SETS:
        src = os.path.join(ROOT, 'work', 'build', fn)
        if fn not in done:   # 처음엔 늘 원본에서 풂(ENDW·MGDAT 는 다른 빌더가 안 건드림, 이름표 C 는 BBG 마다 원본 스트림을 찾아 바꿈 → 다시 돌려도 같게)
            src = os.path.join(ROOT, 'work', 'dm' if os.path.exists(os.path.join(ROOT, 'work', 'dm', fn)) else 'dm_all', fn)
        dat = open(src, 'rb').read()
        oi = {}
        blk, mode, lut, rl = G.decompress(dat, comp, limit=0x20000, info=oi)
        budget = oi['end'] - comp
        nb = bytearray(blk)
        if isinstance(cells, dict) and 'blocks' in cells:   # 16 줄 높이 타일 묶음(위 셀 줄 + 아래 셀 줄) → 한자 칸 양식
            for top, bot, text in cells['blocks']:
                w, h = 8 * len(top), 16
                px = [[(blk[t * 0x20 - base + (y % 8) * 4 + x // 2] >> (4 if x % 2 == 0 else 0)) & 15
                       for t in (top if y < 8 else bot) for x in range(8)] for y in range(16)]
                new, size = emboss(px, w, h, text, KJ[1])
                for row, tl in ((0, top), (8, bot)):
                    for k, t in enumerate(tl):
                        o = t * 0x20 - base
                        for y in range(8):
                            for x in range(0, 8, 2):
                                nb[o + y * 4 + x // 2] = (new[row + y][k * 8 + x] << 4) | new[row + y][k * 8 + x + 1]
                stn, cbase = cells['pal']
                cram = state(stn)[1]
                previews.append((px, new, w, h, [cram[cbase + i] for i in range(16)], text))
                print('  %s 타일 묶음 «%s» %dpx' % (tag, text, size))
            cells = []
        if isinstance(cells, dict):                    # 8×8 타일 가로 줄
            tl = cells['tiles']; w, h = 8 * len(tl), 8
            px = [[(blk[t * 0x20 - base + y * 4 + x // 2] >> (4 if x % 2 == 0 else 0)) & 15
                   for t in tl for x in range(8)] for y in range(8)]
            new = tile_label(px, w, h, cells['text'])
            for k, t in enumerate(tl):
                o = t * 0x20 - base
                for y in range(8):
                    for x in range(0, 8, 2):
                        nb[o + y * 4 + x // 2] = (new[y][k * 8 + x] << 4) | new[y][k * 8 + x + 1]
            grey = [(40 + i * 13,) * 3 for i in range(16)]
            previews.append((px, new, w, h, grey, cells['text']))
            print('  %s 타일 %d칸 «%s»' % (tag, len(tl), cells['text']))
            cells = []
        if tag == 'B':
            pick_skip = {'작전', '＼기술·마법'}           # 링 통일 기준은 원래 «＼작전»·«＼도구» 셀
            pick = {t: get4(blk, v - base, ww, hh) for v, ww, hh, t, c, f in cells if t not in pick_skip}
            lay = ring_params(pick['＼도구'], 56, 16); colp = ring_params(pick['＼작전'], 56, 16)
            RING.clear(); RING.update(lay); RING.update(body=colp['body'], outl=colp['outl'])
            print('  링 라벨 통일: 모양=도구(%s %dpx 테두리 %s) · 색=작전(몸 %X 테두리 %X)'
                  % (os.path.basename(lay['fnt']), lay['size'], lay['has_out'], RING['body'], RING['outl']))
        for vram, w, h, text, col, font in cells:
            off = vram - base
            pal = lut_rgb(DEFST if DEF_LO <= vram < DEF_HI else NEWST if NEW_LO <= vram < NEW_HI or vram == 0x44E00 else stf, col)   # 전투추가 셀은 그 화면 스테이트 색
            px = get4(blk, off, w, h)
            if font == 'head':
                new, size = headplate(px, w, h, text)
            elif isinstance(font, tuple):
                new, size = emboss(px, w, h, text, font[1])
            else:
                new, size = redraw(px, w, h, text, pal, font, aa=(tag != 'B'))
            put4(nb, off, w, h, new)
            previews.append((px, new, w, h, pal, text))
            if '--png' in sys.argv and DEF_LO <= vram < DEF_HI:
                one = Image.new('RGB', (w * 2 + 6, h), (40, 40, 90))
                for k, p_ in enumerate((px, new)):
                    for y in range(h):
                        for x in range(w):
                            if p_[y][x]:
                                one.putpixel((k * (w + 6) + x, y), pal[p_[y][x]])
                one.resize((one.width * 6, h * 6), Image.NEAREST).save(os.path.join(ROOT, 'work', 'battlegfx', 'def_%05X.png' % vram))
            print('  %s %05X %dx%d «%s» %dpx' % (tag, vram, w, h, text, size))
        st = min((GC.compress(bytes(nb), lut, mode, r) for r in sorted({rl, 4, 5, 6, 7, 8})), key=len)   # 0 묶음 값은 헤더에 실림 → 가장 작은 것
        if len(st) > budget:
            st = fit_table(bytes(nb), lut, mode, rl, budget) or st
        assert len(st) <= budget, (fn, '압축 넘침', len(st), budget)
        assert G.decompress(st + b'\0' * 8, 0, limit=0x20000)[0] == bytes(nb), (fn, '되풀기 불일치')
        print('%s %s 압축 %d / 자리 %d B · 되풀기 일치' % (tag, fn, len(st), budget))
        if DRY:                                        # 미리보기는 늘 원본에서(지난 빌드 결과를 읽으면 자리 크기가 줄어 보임)
            continue
        done.add(fn)
        if tag != 'C':
            out = bytearray(dat); out[comp:comp + len(st)] = st
            open(os.path.join(ROOT, 'work', 'build', fn), 'wb').write(out)
        else:                                             # 이름표 = BBG 마다 같은 스트림 사본 → 원본 스트림을 찾아 모두 교체
            orig = dat[comp:comp + budget]
            n = 0
            for f in sorted(os.listdir(os.path.join(ROOT, 'work', 'dm_all'))):
                if not f.endswith('.BBG'):
                    continue
                p = os.path.join(ROOT, 'work', 'build', f)
                if not os.path.exists(p):
                    p = os.path.join(ROOT, 'work', 'dm', f)
                if not os.path.exists(p):
                    continue
                d = bytearray(open(p, 'rb').read())
                i = d.find(orig)
                if i < 0:
                    print('  ★%s 이름표 스트림 없음' % f); continue
                d[i:i + len(st)] = st
                open(os.path.join(ROOT, 'work', 'build', f), 'wb').write(d); n += 1
            print('  이름표 스트림 교체 BBG %d개' % n)
    if '--png' in sys.argv:
        S = 3; rows = []
        for px, new, w, h, pal, text in previews:
            im = Image.new('RGB', (w * 2 + 6, h), (40, 40, 90))
            for k, p in enumerate((px, new)):
                for y in range(h):
                    for x in range(w):
                        if p[y][x]:
                            im.putpixel((k * (w + 6) + x, y), pal[p[y][x]])
            rows.append(im)
        W = max(r.width for r in rows); Hh = sum(r.height + 4 for r in rows)
        sheet = Image.new('RGB', (W, Hh), (0, 0, 0)); y = 0
        for r in rows:
            sheet.paste(r, (0, y)); y += r.height + 4
        sheet.resize((W * S, Hh * S), Image.NEAREST).save(os.path.join(ROOT, 'work', 'battlegfx', 'ko_battle_gfx.png'))


if __name__ == '__main__':
    main()
