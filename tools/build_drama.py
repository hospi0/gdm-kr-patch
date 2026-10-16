# -*- coding: utf-8 -*-
r"""상영관 보이스 드라마 5편 한국어 자막 (2026-10-16) — 영문 패치 lane E 구조를 우리 디스크에 맞춰 다시 짬.

구조(영문 new-parm-archives-tools/src/theater: hook_loader·rc_integrate·hook_caption_table 참고, MIT):
  · 시계 = HWRAM 0x06002008 의 현재 CD 스트림 FAD(약 12.116 섹터/초). 드라마 5편 = GM3.STZ ADX idx 295‥299,
    FAD 구간이 서로 겹치지 않는다 → 표 하나에 [시작FAD, 끝FAD) 레코드.
  · 그리기 = VBlank 벡터 0x41(0x06000104)에 vhook 를 체인. FAD 로 레코드를 찾아 「SOUND ONLY」 아래 VDP1 프레임버퍼
    (0x25C80000, 512폭 16bpp)에 갈무리11 12px 1bpp 글리프를 찍는다(줄이 바뀔 때만 영역 지우기, 매 프레임 그리기).
  · 블롭 = [매직(=vhook 주소) | vhook | 글자폭표 | 글리프 | 자막표] → E804.MDT(극장 방, LWRAM 0x280000 에 통째로 적재)의
    CPU 적재 창 꼬리. 창(머리 0x180·0x1F4 섹터 수)을 늘리고 파일은 커지므로 build_iso 가 트랙 끝으로 옮긴다.
  · 설치 = IP.BIN 0x2394(조각마다 부르는 CD 함수 리터럴) → IP 꼬리 빈칸 0x7F10(0x06009F10) 부트스트랩.
    ⛔0x54B8(0x060074B8)은 «0 인 IP 칸»이지만 게임 변수(전투가 104 B 전부 덮음 → 던전 다운, 2026-10-16). 0x06009F00‥F10 = IP CD 라이브러리 변수.
    ★우리 배치용 3구역(영문 RC 는 E800 을 위로 옮겨 «≥문턱=퇴장»이었지만 우리는 E800 이 원래 자리 FAD 0x7A21):
       FAD < 0x7B17(E804 원래 시작) → 퇴장(해제) / 드라마 구간 → 설치(매직 확인) / 그 밖(방 BGM·옮긴 E804) → 그대로.
출력: work/build/FIELD_E804.MDT(늘린 판) · work/build/SYS_IP.BIN(IP 16섹터) · work/drama/preview.png(--png)
  python tools/build_drama.py [--png] [--dry]
"""
import csv
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.append(os.path.join(HERE, 'third_party', 'new-parm-archives-tools', 'src', 'theater'))
import hook_sh2asm                                                       # noqa: E402  (영문 텍스트 어셈블러)
sys.path.insert(0, HERE)
from punct import squeeze                                                # noqa: E402  (문장부호 뒤 공백 삭제 — 전프로젝트 규칙)

TSV = os.path.join(ROOT, 'work', 'trans', 'drama_ko.tsv')   # my files/drama_001_번역.tsv(사용자 번역) 복사본 + 인명 통일(가드인·뮤렌·가라일)
FONT = r'C:\claude\utils\font\Galmuri-v2.40.3\Galmuri11.ttf'
TRACK = (r'C:/claude/roms/ss/Grandia - Digital Museum (Japan) (Rev A) (10M)'
         r'/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin')

# 시계
SECTORS_PER_SEC = 12.116
GM3_LBA = 39128
DRAMA_START_SEC = {295: 75328, 296: 78391, 297: 82578, 298: 87129, 299: 90504}
DRAMA_END_SEC = {295: 78391, 296: 82578, 297: 87129, 298: 90504, 299: 94245}
FAD_SHIFT = 7                           # ★자막을 늦추는 섹터 수(+). 2026-10-16 실기 «약 1초 빠름»(−5 로 당겼던 것 → +7 = 1초 늦춤).
                                        #   영문은 +5(미리읽기)+19(사용자) 로 «늦췄다» — 처음에 방향을 반대로 넣었다
MIN_DWELL, MAX_SHIFT = 2.5, 1.0         # 짧은 줄 최소 노출(영문 rc_27 사용자 의견)
# 화면
VDP1_FB, FB_W = 0x25C80000, 512
CAP_X, CAP_Y = 48, 142                  # 「SOUND ONLY» 아래 검은 무대(x 46‥303)
FIELD_W = 256
GH = 12                                  # 글리프 높이(갈무리11 12px)
LINE_H = 15
MAX_ROWS = 4
COLOR = 0x050F                           # SOUND ONLY 와 같은 흰색
# 디스크·메모리
FAD_VAR = 0x06002008
VEC41, ORIG_VBLANK, ORIG_FN = 0x06000104, 0x06000846, 0x06009B32
IP_JSR_LIT, IP_GAP, IP_GAP_LEN = 0x2394, 0x7F10, 240   # ★0x06009F10‥0x06009FFF — 사용자 스테이트 전부에서 안 쓰임(check_boot_free)
IP_BASE = 0x06002000
E804_LOAD, E804_FAD_LO = 0x00280000, 0x7B17
LWRAM_LIMIT = 0x2D8000                   # E800 이 들어오며 덮는 구역 끝(영문 실측)


# ───────────────────────── 자막표 ─────────────────────────
def drama_fad(idx):
    return GM3_LBA + DRAMA_START_SEC[idx] + 150


def load_lines():
    rows = list(csv.DictReader(open(TSV, encoding='utf-8'), delimiter='\t'))
    by = {}
    for r in rows:
        n = int(r['편'].replace('drama', ''))
        by.setdefault(294 + n, []).append(dict(start=float(r['시작']), end=float(r['끝']), ko=squeeze(r['번역'].strip()), jp=r['원문']))
    refine_starts(by)
    for idx, lines in by.items():                  # 받아쓰기 구간이 겹치는 줄: 앞 줄 끝을 다음 줄 시작으로 자른다
        lines.sort(key=lambda l: l['start'])
        dur = (DRAMA_END_SEC[idx] - DRAMA_START_SEC[idx]) / SECTORS_PER_SEC - 0.5   # 편 끝을 넘는 줄(ASR 꼬리)
        for l in lines:
            l['end'] = min(l['end'], dur)
            l['start'] = min(l['start'], dur - 0.3)
        for a, b in zip(lines, lines[1:]):
            if a['end'] > b['start']:
                a['end'] = b['start']
            if a['end'] - a['start'] < 0.3:
                a['end'] = a['start'] + 0.3
                b['start'] = max(b['start'], a['end'])
    return by


def refine_starts(by):
    """줄 시작 = 단어 시각 받아쓰기(drama_asr --words)의 첫 단어 시작(같은 원문 줄과 짝지어질 때만). 줄 단위 시작은 ±0.5초 흩어진다."""
    import difflib, glob, json
    n_ok = n_all = 0
    for idx, lines in by.items():
        g = glob.glob(os.path.join(ROOT, 'work', 'theater', 'drama%d_idx*_words.json' % (idx - 294)))
        if not g:
            continue
        W = json.load(open(g[0], encoding='utf-8'))
        for l in lines:
            n_all += 1
            best = None
            for seg in W:
                if abs(seg['start'] - l['start']) <= 2.0 and seg['words']:
                    sc = difflib.SequenceMatcher(None, seg['text'], l['jp']).ratio()
                    if best is None or sc > best[0]:
                        best = (sc, seg)
            if best and best[0] >= 0.5:
                fw = best[1]['words'][0][0]
                if abs(fw - l['start']) <= 1.5:
                    l['start'] = fw; n_ok += 1
    print('  첫 단어 시각으로 맞춘 줄 %d/%d' % (n_ok, n_all))


def dwell(lines):
    se = [(l['start'], l['end']) for l in lines]
    for i in range(len(se) - 1):
        s, e = se[i]
        if e - s >= MIN_DWELL:
            continue
        ns, ne = se[i + 1]
        if abs(ns - e) > 0.05:
            continue
        d = min(MIN_DWELL - (e - s), MAX_SHIFT, max(0.0, (ne - ns) - MIN_DWELL))
        if d > 0:
            se[i] = (s, e + d); se[i + 1] = (ns + d, ne)
    return se


class Font:
    def __init__(self):
        from PIL import ImageFont
        self.f = ImageFont.truetype(FONT, 12)
        self.idx, self.glyphs, self.widths = {}, [], []

    def adv(self, ch):
        if '가' <= ch <= '힣':
            return 12
        if ch == ' ':
            return 4
        return max(3, int(round(self.f.getlength(ch))) + 1)

    def code(self, ch):
        if ch not in self.idx:
            from PIL import Image, ImageDraw
            im = Image.new('L', (16, 16), 0)
            ImageDraw.Draw(im).text((0, 0), ch, font=self.f, fill=255)
            px = im.load()
            rows = [sum(1 << (15 - x) for x in range(16) if px[x, y] >= 128) for y in range(GH)]
            self.idx[ch] = len(self.glyphs); self.glyphs.append(rows); self.widths.append(self.adv(ch))
        return self.idx[ch]


def wrap(text, font):
    out, cur, w = [], '', 0
    for word in text.split(' '):
        ww = sum(font.adv(c) for c in word)
        if cur and w + font.adv(' ') + ww > FIELD_W:
            out.append(cur); cur, w = word, ww
        else:
            cur = (cur + ' ' + word) if cur else word
            w = w + (font.adv(' ') if cur != word else 0) + ww
        while sum(font.adv(c) for c in cur) > FIELD_W:          # 한 낱말이 너무 길면 자른다
            k = len(cur)
            while sum(font.adv(c) for c in cur[:k]) > FIELD_W:
                k -= 1
            out.append(cur[:k]); cur = cur[k:]; w = sum(font.adv(c) for c in cur)
    if cur:
        out.append(cur)
    return out


def bake_table(font):
    by = load_lines()
    fad_lo = drama_fad(295)
    fad_hi = GM3_LBA + DRAMA_END_SEC[299] + 150 + FAD_SHIFT
    recs, pages = [], []
    for idx in sorted(by):
        lines = by[idx]
        for l, (s, e) in zip(lines, dwell(lines)):
            rows = wrap(l['ko'], font)
            chunks = [rows[i:i + MAX_ROWS] for i in range(0, len(rows), MAX_ROWS)] or [[]]
            dur = (e - s) / len(chunks)
            for k, ch in enumerate(chunks):                         # 4줄 넘으면 시간을 나눠 다음 판으로
                cs, ce = s + dur * k, s + dur * (k + 1)
                fs = drama_fad(idx) + round(cs * SECTORS_PER_SEC) + FAD_SHIFT - fad_lo
                fe = drama_fad(idx) + round(ce * SECTORS_PER_SEC) + FAD_SHIFT - fad_lo
                body = bytearray()
                for r, txt in enumerate(ch):
                    w = sum(font.adv(c) for c in txt)
                    x = (FIELD_W - w) // 2
                    body += struct.pack('>HH', 0xFFFE, (r * LINE_H * FB_W + x) * 2)
                    for c in txt:
                        body += struct.pack('>H', font.code(c))
                recs.append((fs, fe, bytes(body))); pages.append((idx, fs, fe, ch))
    recs.sort()
    for a, b in zip(recs, recs[1:]):
        assert a[1] <= b[0] + 1, ('겹침', a[:2], b[:2])
    tbl = bytearray()
    for fs, fe, body in recs:
        assert 0 <= fs < 0xFFFE and fe < 0xFFFE
        tbl += struct.pack('>HHH', fs, max(fe, fs + 1), len(body)) + body
    tbl += struct.pack('>H', 0xFFFF)
    return bytes(tbl), fad_lo, fad_hi, pages


# ───────────────────────── vhook ─────────────────────────
VHOOK_SRC = """
vhook:
  mov.l r0,@-r15
  mov.l r1,@-r15
  mov.l r2,@-r15
  mov.l r3,@-r15
  mov.l r5,@-r15
  mov.l r6,@-r15
  mov.l r7,@-r15
  mov.l r8,@-r15
  mov.l r9,@-r15
  mov.l r10,@-r15
  mov.l r11,@-r15
  mov.l r12,@-r15
  mov.l r13,@-r15
  mov.l r14,@-r15
  sts.l pr,@-r15
  mov.l @(V_FADVAR,PC),r0
  mov.l @r0,r1
  mov.l @(V_FADLO,PC),r2
  cmp/hs r2,r1
  bf vchain
  mov.l @(V_FADHI,PC),r3
  cmp/hs r3,r1
  bt vchain
  sub r2,r1
  mov.l @(V_TABLE,PC),r13
vscan:
  mov.w @r13+,r0
  extu.w r0,r0
  mov.l @(V_FFFF,PC),r2
  cmp/eq r2,r0
  bt vnone
  mov.w @r13+,r2
  extu.w r2,r2
  mov.w @r13+,r14
  extu.w r14,r14
  cmp/hs r0,r1
  bf vnext
  cmp/hs r2,r1
  bf vfound
vnext:
  add r14,r13
  bra vscan
  nop
vnone:
  mov.l @(V_LASTP,PC),r5
  mov.l @r5,r0
  tst r0,r0
  bt vchain
  mov #0,r0
  mov.l r0,@r5
  bsr vclear
  nop
  bra vchain
  nop
vfound:
  mov.l @(V_LASTP,PC),r5
  mov.l @r5,r0
  cmp/eq r13,r0
  bt vdraw
  mov.l r13,@r5
  bsr vclear
  nop
vdraw:
  mov.l @(V_COLOR,PC),r9
  mov.l @(V_FB,PC),r11
  shlr r14
  tst r14,r14
  bt vchain
vtok:
  mov.w @r13+,r0
  extu.w r0,r0
  dt r14
  mov.l @(V_ROW,PC),r2
  cmp/eq r2,r0
  bf vglyph
  mov.w @r13+,r0
  extu.w r0,r0
  dt r14
  mov.l @(V_FB,PC),r11
  add r0,r11
  bra vnexttok
  nop
vglyph:
  mov.l @(V_WID,PC),r2
  add r0,r2
  mov.b @r2,r8
  extu.b r8,r8
  mov r0,r2
  shll2 r2
  shll r2
  mov r2,r3
  shll r3
  add r3,r2
  mov.l @(V_GLY,PC),r1
  add r2,r1
  mov r11,r7
  mov.l @(V_STRIDE,PC),r6
  mov #12,r2
vrow:
  mov.w @r1+,r0
  shll16 r0
  mov r7,r3
  mov #12,r5
vcol:
  shll r0
  bf vskip
  mov.w r9,@r3
vskip:
  add #2,r3
  dt r5
  bf vcol
  add r6,r7
  dt r2
  bf vrow
  mov r8,r0
  shll r0
  add r0,r11
vnexttok:
  tst r14,r14
  bf vtok
vchain:
  lds.l @r15+,pr
  mov.l @r15+,r14
  mov.l @r15+,r13
  mov.l @r15+,r12
  mov.l @r15+,r11
  mov.l @r15+,r10
  mov.l @r15+,r9
  mov.l @r15+,r8
  mov.l @r15+,r7
  mov.l @r15+,r6
  mov.l @r15+,r5
  mov.l @r15+,r3
  mov.l @r15+,r2
  mov.l @r15+,r1
  mov.l @(V_HANDLER,PC),r0
  jmp @r0
  mov.l @r15+,r0
vclear:
  mov.l @(V_FB,PC),r3
  mov #0,r0
  mov.l @(V_STRIDE,PC),r8
  mov.l @(V_CLROWS,PC),r6
vclrrow:
  mov r3,r7
  mov #64,r2
vclrpx:
  mov.w r0,@r7
  add #2,r7
  mov.w r0,@r7
  add #2,r7
  mov.w r0,@r7
  add #2,r7
  mov.w r0,@r7
  add #2,r7
  dt r2
  bf vclrpx
  add r8,r3
  dt r6
  bf vclrrow
  rts
  nop
.align 4
V_FADVAR:  .long %d
V_FADLO:   .long %d
V_FADHI:   .long %d
V_FFFF:    .long 0x0000FFFF
V_ROW:     .long 0x0000FFFE
V_FB:      .long %d
V_STRIDE:  .long %d
V_CLROWS:  .long %d
V_COLOR:   .long %d
V_WID:     .long %d
V_GLY:     .long %d
V_TABLE:   .long %d
V_LASTP:   .long %d
V_HANDLER: .long 0x06000846
V_LAST:    .long 0
"""

BOOT_SRC = """
boot:
  mov.l @(P_VEC,PC),r0
  mov.l @r0,r3
  mov.l @(P_VHOOK,PC),r5
  mov.l @(P_FADVAR,PC),r1
  mov.l @r1,r1
  mov.l @(P_EXIT,PC),r2
  cmp/hs r2,r1
  bf p_exit
  mov.l @(P_DLO,PC),r2
  cmp/hs r2,r1
  bf p_done
  mov.l @(P_DHI,PC),r2
  cmp/hs r2,r1
  bt p_done
  cmp/eq r5,r3
  bt p_done
  mov.l @(P_BASE,PC),r1
  mov.l @r1,r1
  cmp/eq r5,r1
  bf p_done
  mov.l @(P_HSLOT,PC),r2
  mov.l r3,@r2
  bra p_done
  mov.l r5,@r0
p_exit:
  cmp/eq r5,r3
  bf p_done
  mov.l @(P_ORIGH,PC),r2
  mov.l r2,@r0
p_done:
  mov.l @(P_ORIG,PC),r3
  jmp @r3
  nop
.align 4
P_VEC:    .long %d
P_VHOOK:  .long %d
P_FADVAR: .long %d
P_EXIT:   .long %d
P_DLO:    .long %d
P_DHI:    .long %d
P_BASE:   .long %d
P_HSLOT:  .long %d
P_ORIGH:  .long %d
P_ORIG:   .long %d
"""


def bake_blob(base, font, table, fad_lo, fad_hi):
    """base = 블롭 첫 바이트(매직) 주소. 반환 (blob, meta)"""
    A = hook_sh2asm.Asm
    vaddr = base + 4
    args = lambda w, g, t, lp: (FAD_VAR, fad_lo, fad_hi, VDP1_FB + (CAP_Y * FB_W + CAP_X) * 2, FB_W * 2,
                                MAX_ROWS * LINE_H, COLOR, w, g, t, lp)
    prov = A(); code0 = prov.assemble2(VHOOK_SRC % args(0, 0, 0, 0), vaddr)
    vlen = (len(code0) + 3) & ~3
    wid_addr = vaddr + vlen
    nG = len(font.glyphs)
    gly_addr = (wid_addr + nG + 3) & ~3
    tbl_addr = gly_addr + nG * GH * 2
    a = A(); code = a.assemble2(VHOOK_SRC % args(wid_addr, gly_addr, tbl_addr, prov.labels['V_LAST']), vaddr)
    assert len(code) == len(code0) and a.labels['V_LAST'] == prov.labels['V_LAST']
    blob = bytearray(struct.pack('>I', vaddr)) + code + bytes(vlen - len(code))
    blob += bytes(font.widths) + bytes(gly_addr - wid_addr - nG)
    for rows in font.glyphs:
        for r in rows:
            blob += struct.pack('>H', r)
    blob += table
    meta = dict(base=base, vhook=vaddr, v_handler=a.labels['V_HANDLER'], v_last=a.labels['V_LAST'],
                glyphs=nG, table=tbl_addr, len=len(blob))
    return bytes(blob), meta


def check_boot_free(n, blen):
    """부트스트랩 자리를 게임이 쓰는지 사용자 스테이트 전부로 검사(0 이 아닌 값이 있으면 실패)."""
    import glob, gzip
    sys.path.append(r'C:\claude\project\virus-kr-patch\tools')   # mdfnstate 만 — rzip 은 우리 tools/rzip.py(virus 판은 형식 다름)
    import rzip, mdfnstate as M
    a = IP_BASE + IP_GAP - 0x06000000
    paths = (glob.glob(os.path.join(ROOT, 'my files', '**', '*.state*'), recursive=True) +
             glob.glob(os.path.join(ROOT, 'work', 'states', '*.mc*')))
    k = 0
    for p in paths:
        try:
            raw = open(p, 'rb').read()
            if raw[:6] == b'#RZIPv':
                raw = rzip.unpack(p)[0]
            elif raw[:2] == b'\x1f\x8b':                       # Mednafen .mcN (gzip, 머리 뒤 미리보기 그림)
                raw = gzip.decompress(raw); i = raw.find(b'BIOS_HASH\x00'); raw = b'MDFNSVST' + bytes(24) + raw[i:]
            H = M.swap16(M.sections(raw)['MAIN']['WorkRAMH'])
        except Exception:
            continue
        k += 1
        mine = struct.unpack_from('>I', H, IP_BASE + IP_JSR_LIT - 0x06000000)[0] == IP_BASE + IP_GAP
        lo = a + blen if mine else a                 # 우리 부트스트랩이 깔린 빌드로 찍은 스테이트 → 코드 뒤 꼬리만 검사
        assert not any(H[lo:a + n]), '부트스트랩 자리를 게임이 씀: %s' % os.path.basename(p)
    assert k >= 10, ('검사한 스테이트가 너무 적다', k)
    return k


def build_boot(meta, drama_lo, drama_hi):
    src = BOOT_SRC % (VEC41, meta['vhook'], FAD_VAR, E804_FAD_LO, drama_lo, drama_hi,
                      meta['base'], meta['v_handler'], ORIG_VBLANK, ORIG_FN)
    code = hook_sh2asm.Asm().assemble2(src, IP_BASE + IP_GAP)
    assert len(code) <= IP_GAP_LEN, len(code)
    return code


# ───────────────────────── 조립 ─────────────────────────
def read_ip():
    with open(TRACK, 'rb') as f:
        ip = b''
        for s in range(16):
            f.seek(s * 2352 + 16); ip += f.read(2048)
    return bytearray(ip)


def main():
    dry = '--dry' in sys.argv
    font = Font()
    table, fad_lo, fad_hi, pages = bake_table(font)
    src = os.path.join(ROOT, 'work', 'build', 'FIELD_E804.MDT')
    if not os.path.exists(src) or '--orig' in sys.argv:          # --orig = 검산용(블롭 계산만, 쓰지 않음)
        src = os.path.join(ROOT, 'work', 'dm', 'FIELD_E804.MDT')
    mdt = bytearray(open(src, 'rb').read())
    vanilla = open(os.path.join(ROOT, 'work', 'dm', 'FIELD_E804.MDT'), 'rb').read()
    assert len(mdt) == len(vanilla), 'E804 가 이미 늘어나 있다 — build_all 처음부터'
    A = struct.unpack_from('>I', mdt, 0x180)[0]
    win = A * 2048
    eod = struct.unpack_from('>I', mdt, 0x1FC)[0]
    off = (eod + 3) & ~3
    assert not any(mdt[off:win]), 'E804 꼬리가 0 이 아니다'
    blob0, _ = bake_blob(E804_LOAD + off, font, table, fad_lo, fad_hi)
    grow = max(0, (len(blob0) - (win - off) + 2047) // 2048)
    if grow:
        mdt = mdt[:win] + bytearray(grow * 2048) + mdt[win:]
        struct.pack_into('>I', mdt, 0x180, A + grow); struct.pack_into('>I', mdt, 0x1F4, A + grow)
        win += grow * 2048
    assert E804_LOAD + win <= LWRAM_LIMIT, hex(E804_LOAD + win)
    blob, meta = bake_blob(E804_LOAD + off, font, table, fad_lo, fad_hi)
    assert len(blob) == len(blob0)
    mdt[off:off + len(blob)] = blob
    drama_lo = drama_fad(295)
    drama_hi = GM3_LBA + DRAMA_END_SEC[299] + 150
    boot = build_boot(meta, drama_lo, drama_hi)
    ip = read_ip()
    assert struct.unpack_from('>I', ip, IP_JSR_LIT)[0] == ORIG_FN and not any(ip[IP_GAP:IP_GAP + IP_GAP_LEN])
    nst = check_boot_free(IP_GAP_LEN, len(boot))
    struct.pack_into('>I', ip, IP_JSR_LIT, IP_BASE + IP_GAP)
    ip[IP_GAP:IP_GAP + len(boot)] = boot
    print('자막 판 %d개 · 글리프 %d · 자막표 %d B · 블롭 %d B @ LWRAM 0x%06X(E804 +0x%X) · E804 창 +%d섹터 → %d B'
          % (len(pages), meta['glyphs'], len(table), len(blob), meta['base'], off, grow, len(mdt)))
    print('부트스트랩 %d B @ 0x%08X · 설치 FAD 0x%X‥0x%X · 해제 FAD < 0x%X'
          % (len(boot), IP_BASE + IP_GAP, drama_lo, drama_hi, E804_FAD_LO))
    if '--png' in sys.argv:
        preview(pages, font)
    if not dry:
        open(os.path.join(ROOT, 'work', 'build', 'FIELD_E804.MDT'), 'wb').write(bytes(mdt))
        open(os.path.join(ROOT, 'work', 'build', 'SYS_IP.BIN'), 'wb').write(bytes(ip))
        print('썼음: work/build/FIELD_E804.MDT, work/build/SYS_IP.BIN')
    return blob, meta, pages, font


def preview(pages, font, n=8):
    from PIL import Image
    os.makedirs(os.path.join(ROOT, 'work', 'drama'), exist_ok=True)
    W, H = 352, MAX_ROWS * LINE_H + 8
    sel = pages[:n]
    im = Image.new('RGB', (W, H * len(sel)), (0, 0, 0)); px = im.load()
    for k, (_, _, _, rows) in enumerate(sel):
        for r, txt in enumerate(rows):
            x = CAP_X + (FIELD_W - sum(font.adv(c) for c in txt)) // 2
            for c in txt:
                g = font.glyphs[font.idx[c]]
                for y in range(GH):
                    for xx in range(12):
                        if g[y] >> (15 - xx) & 1:
                            px[x + xx, k * H + 4 + r * LINE_H + y] = (248, 248, 248)
                x += font.adv(c)
    im.resize((W * 3, H * len(sel) * 3), Image.NEAREST).save(os.path.join(ROOT, 'work', 'drama', 'preview.png'))
    print('미리보기 work/drama/preview.png')


if __name__ == '__main__':
    main()
