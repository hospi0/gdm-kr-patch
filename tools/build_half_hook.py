# -*- coding: utf-8 -*-
r"""반각(8×8) 한글 그리기 훅 (2026-10-16).

무엇을 하나
  1) BIN_FDATA.BIN(LWRAM 0x00200000 상주) 안 «전각 폰트 구간의 빈 꼬리»에 블롭을 넣는다:
     코드(훅 본체) + 선두 바이트 표 + 4bpp 변환표 + 캐시 표 + 1bpp 8×8 한글 글리프(half_ko.syllables 순).
     한자 칸을 비운 뒤(font_apply) 폰트 끝이 BLOB_OFF 아래여야 한다 — 파일 크기는 그대로.
  2) 메뉴 모듈 5개(CMDMN·CNFIG·ITGET·SHOP·SVLD): 글자 분배기 D(모드 R4, x R5, y R6, 팔레트 R7, 코드 @R15)
     첫 10바이트를 «블롭 모듈별 입구로 점프»로 바꾼다. 블롭은
       · 모드 2·3(8×8) + 호출자 = 문자열 루프(PR == D+0x358) + 코드가 한글 선두 바이트 → 둘째 바이트(@(1,R14))를 읽어
         음절을 캐시 셀에 그리고 화면 버퍼(@(D+0x302) 리터럴)의 (y*64+x)에 (팔레트<<12)|셀 을 쓴다.
         호출자 루프 변수 R13(번째)·R14(포인터)를 하나 더 올려 둘째 바이트를 건너뛰게 한다(x 는 한 칸만 전진).
       · 그 밖 → 덮어쓴 원래 명령 5개를 대신 실행하고 D+10 으로 돌아간다.
  3) BATLE.BIN(0x0602C000): 8×8 문자열 찍기 루프 0x0603F744‥ 를 블롭으로 점프 → 한글이면 그리고, 아니면 원래대로
     (코드|팔레트비트)를 VDP2 0x25E0E000 맵에 쓰고 x++ 후 루프 머리 0x0603F73C 로.

  python tools/build_half_hook.py [--dry]
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import half_ko as K
import han8gdm
from sh2asm import Asm

BLOB_OFF = 0x7800                    # FDATA 파일 오프셋(= RAM 0x00200000 + BLOB_OFF)
BLOB_RAM = 0x00200000 + BLOB_OFF
FONT_LIMIT = 0xAA03                  # 전각 폰트 구간 하드 상한(font_build.FULL_LIMIT)
VRAM = 0x25E00000

# 메뉴 모듈: 파일명 → 분배기 D 의 파일 오프셋 (모두 0x060B2000 적재, D ≡ 2 mod 4)
MENU = {'FIELD_CMDMN.BIN': 0x9072, 'FIELD_CNFIG.BIN': 0x16C2, 'FIELD_ITGET.BIN': 0x302A,
        'FIELD_SHOP.BIN': 0x4DD6, 'FIELD_SVLD.BIN': 0x2DB6}
MENU_LOAD = 0x060B2000
D_ORIG10 = bytes.fromhex('2fe6 2fd6 2fc6 2fb6 6c53'.replace(' ', ''))   # 덮어쓸 원래 명령 5개
LOOP_RET = 0x358                     # 문자열 루프의 BSR 다음 주소 - D
BUF_LIT = 0x302                      # 화면 버퍼 리터럴(putc 가 씀) - D

BATLE = 'BATLE_BATLE.BIN'; BATLE_LOAD = 0x0602C000
B_PATCH = 0x0603F744; B_LOOP = 0x0603F73C
B_ORIG = bytes.fromhex('626f321c4200325c644c24eb2241aff37601')          # 0x0603F744‥0x0603F755
S_PATCH = 0x0603466C; S_RET = 0x06034676; S_LIT = 0x06034778     # 전투 상태창(VDP1 글자 스프라이트) CMDSRCA 계산
S_ORIG = bytes.fromhex('9384699c91834908393c')   # mov.w 6C00 / extu.b / mov.w 0108 / shll2 / add
V1_FONT = 0x25C36000                 # VDP1 VRAM 0x36000 = 8×8 글꼴 사본(코드×32)
V1_SLOTS = list(range(0x61, 0x7B))   # 상태창 한글 캐시 = 소문자 a~z 칸 26(상태창은 대문자·숫자만). ⛔가나 칸은 적 이름(반각, 아직 일본어)이 쓴다


class A(Asm):
    def stspr(self, n):            self.w(0x002A | int(n[1:]) << 8)
    def shll16(self, n):           self.w(0x4028 | int(n[1:]) << 8)
    def movb_disp_r0(self, d, m):  self.w(0x8400 | int(m[1:]) << 4 | d)        # mov.b @(d,Rm),R0
    def movw_r0n_store(self, m, n): self.w(0x0005 | int(n[1:]) << 8 | int(m[1:]) << 4)  # mov.w Rm,@(R0,Rn)
    def movb_r0n_store(self, m, n): self.w(0x0004 | int(n[1:]) << 8 | int(m[1:]) << 4)  # mov.b Rm,@(R0,Rn)
    def movl_store(self, m, n):    self.w(0x2002 | int(n[1:]) << 8 | int(m[1:]) << 4)   # mov.l Rm,@Rn
    def cmpeqi(self, i):           self.w(0x8800 | (i & 0xFF))
    def tsti(self, i):             self.w(0xC800 | (i & 0xFF))
    def extsw(self, m, n):         self.w(0x600F | int(n[1:]) << 8 | int(m[1:]) << 4)
    def shll8(self, n):            self.w(0x4018 | int(n[1:]) << 8)


def build_blob(menu_D, pool=b''):
    syl = K.syllables(); N = len(syl)
    # 데이터 배치(블롭 안 오프셋)
    O_LEAD, O_LUT, O_NEXT, O_NEXT1, O_SLOTC = 0x400, 0x500, 0x520, 0x524, 0x528
    O_OWNER = 0x560
    O_OWNER1 = O_OWNER + K.NSLOT * 2
    O_MAP = (O_OWNER1 + len(V1_SLOTS) * 2 + 15) & ~15
    O_MAP1 = O_MAP + N
    O_GLY = (O_MAP1 + N + 15) & ~15
    O_POOL = O_GLY + N * 8
    size = O_POOL + len(pool)

    a = A(BLOB_RAM)
    a.defl('LEAD', BLOB_RAM + O_LEAD); a.defl('LUT', BLOB_RAM + O_LUT); a.defl('NEXT', BLOB_RAM + O_NEXT)
    a.defl('OWNER', BLOB_RAM + O_OWNER); a.defl('MAP', BLOB_RAM + O_MAP); a.defl('GLY', BLOB_RAM + O_GLY)
    a.defl('VRAM', VRAM); a.defl('BLOOP', B_LOOP)
    a.defl('W223', K.PER_LEAD); a.defl('WCELL0', K.CELL0); a.defl('WNSLOT', K.NSLOT)
    a.defl('WFFFF', 0xFFFF); a.defl('WRET', LOOP_RET); a.defl('WBUF', BUF_LIT)
    a.defl('NEXT1', BLOB_RAM + O_NEXT1); a.defl('OWNER1', BLOB_RAM + O_OWNER1); a.defl('MAP1', BLOB_RAM + O_MAP1)
    a.defl('SLOTC', BLOB_RAM + O_SLOTC); a.defl('V1FONT', V1_FONT); a.defl('STRET', S_RET)
    a.defl('WNSLOT1', len(V1_SLOTS)); a.defl('W6C00', 0x6C00); a.defl('W0108', 0x0108)

    # ── 메뉴 모듈별 입구: r2 = D ──
    for i, D in enumerate(menu_D):
        a.label('mstub%d' % i)
        a.movl_pc('D%d' % i, 'r2'); a.bra('menu'); a.nop()
        a.defl('D%d' % i, D)

    # ── 메뉴 공통 ──
    a.label('menu')
    a.mov('r4', 'r0'); a.extub('r0', 'r0')
    a.cmpeqi(2); a.bt('m_mode'); a.cmpeqi(3); a.bf('m_orig')
    a.label('m_mode')
    a.stspr('r1'); a.movl_pc('WRET', 'r3'); a.mov('r2', 'r0'); a.add('r3', 'r0'); a.cmpeq('r1', 'r0'); a.bf('m_orig')
    a.movl_load('r15', 'r0'); a.extub('r0', 'r0')                      # 코드(호출자가 push 한 long 의 하위)
    a.movl_pc('LEAD', 'r1'); a.movb_r0m('r1', 'r1'); a.mov('r1', 'r0'); a.tsti(0x80); a.bf('m_orig')
    # 한글: r1 = 선두 번호, 둘째 바이트 = @(1,R14)
    a.movb_disp_r0(1, 'r14'); a.extub('r0', 'r3')
    a.movi(0x25, 'r0'); a.cmphi('r0', 'r3')                             # T = idx > 0x25
    a.addi(-0x20, 'r3'); a.bf('m_noskip'); a.addi(-1, 'r3')
    a.label('m_noskip')
    a.movl_pc('W223', 'r0'); a.muluw('r0', 'r1'); a.sts_macl('r0'); a.add('r0', 'r3')   # r3 = 음절 번호
    a.addi(1, 'r14'); a.addi(1, 'r13')                                  # 호출자 루프가 둘째 바이트를 건너뛰게
    a.stspr_predec('r15'); a.movl_predec('r5', 'r15'); a.movl_predec('r6', 'r15')
    a.movl_predec('r7', 'r15'); a.movl_predec('r2', 'r15')
    a.items.append(('bra_sub', 'kdraw'))                               # bsr kdraw
    a.mov('r3', 'r4')
    a.movl_postinc('r15', 'r2'); a.movl_postinc('r15', 'r7'); a.movl_postinc('r15', 'r6')
    a.movl_postinc('r15', 'r5'); a.ldspr_postinc('r15')
    a.extuw('r7', 'r7'); a.shll8('r7'); a.shll2('r7'); a.shll2('r7')
    a.orr('r0', 'r7')                                                   # 단어 = (팔레트<<12)|셀
    a.movl_pc('WBUF', 'r1'); a.add('r2', 'r1'); a.movl_load('r1', 'r1') # 화면 버퍼 = @(D+0x302)
    a.mov('r6', 'r0'); a.extub('r0', 'r0'); a.shll2('r0'); a.shll2('r0'); a.shll2('r0')
    a.mov('r5', 'r3'); a.extub('r3', 'r3'); a.add('r3', 'r0'); a.shll('r0')
    a.rts(); a.movw_r0n_store('r7', 'r1')
    a.label('m_orig')                                                   # 덮어쓴 원래 명령 5개 + D+10 로
    a.movl_predec('r14', 'r15'); a.movl_predec('r13', 'r15'); a.movl_predec('r12', 'r15'); a.movl_predec('r11', 'r15')
    a.mov('r2', 'r1'); a.addi(10, 'r1'); a.jmp('r1'); a.mov('r5', 'r12')

    # ── 전투: R4=코드(부호확장), R13=다음 바이트, R6=x, R1=y*64, R5=VRAM 맵, R14=팔레트비트 ──
    a.label('bat')
    a.mov('r4', 'r0'); a.extub('r0', 'r0'); a.mov('r0', 'r7')          # r7 = 코드(R4 는 mov.b 부호확장이라 r0 도 풀어야 표 색인이 맞다)
    a.movl_pc('LEAD', 'r2'); a.movb_r0m('r2', 'r3'); a.mov('r3', 'r0'); a.tsti(0x80); a.bf('b_put')
    a.movb_postinc('r13', 'r0'); a.extub('r0', 'r4')                    # 둘째 바이트
    a.movi(0x25, 'r0'); a.cmphi('r0', 'r4'); a.addi(-0x20, 'r4'); a.bf('b_noskip'); a.addi(-1, 'r4')
    a.label('b_noskip')
    a.extub('r3', 'r3'); a.movl_pc('W223', 'r0'); a.muluw('r0', 'r3'); a.sts_macl('r0'); a.add('r0', 'r4')
    a.stspr_predec('r15'); a.movl_predec('r1', 'r15'); a.movl_predec('r5', 'r15'); a.movl_predec('r6', 'r15')
    a.items.append(('bra_sub', 'kdraw')); a.nop()
    a.mov('r0', 'r7')
    a.movl_postinc('r15', 'r6'); a.movl_postinc('r15', 'r5'); a.movl_postinc('r15', 'r1'); a.ldspr_postinc('r15')
    a.label('b_put')
    a.mov('r6', 'r2'); a.extsw('r2', 'r2'); a.add('r1', 'r2'); a.shll('r2'); a.add('r5', 'r2')
    a.orr('r14', 'r7'); a.movw_store('r7', 'r2'); a.addi(1, 'r6')
    a.movl_pc('BLOOP', 'r0'); a.jmp('r0'); a.nop()

    # ── 전투 상태창(VDP1 글자 스프라이트, BATLE 0x0603466C): R9 = 코드(부호확장), @(4,R15) = 다음 바이트 포인터,
    #    R4 = 명령 버퍼 → R9 = CMDSRCA(0x6C00 + 코드*4), R1 = 0x0108 로 0x06034676 에 돌아간다 ──
    a.label('st')
    a.mov('r9', 'r0'); a.extub('r0', 'r0'); a.mov('r0', 'r9')
    a.movl_pc('LEAD', 'r2'); a.movb_r0m('r2', 'r3'); a.mov('r3', 'r0'); a.tsti(0x80); a.bf('st_plain')
    a.w(0x52F1)                                                          # mov.l @(4,r15),r2
    a.movb_postinc('r2', 'r0'); a.w(0x1F21)                              # mov.l r2,@(4,r15)
    a.extub('r0', 'r1'); a.movi(0x25, 'r0'); a.cmphi('r0', 'r1'); a.addi(-0x20, 'r1'); a.bf('st_ns'); a.addi(-1, 'r1')
    a.label('st_ns')
    a.extub('r3', 'r3'); a.movl_pc('W223', 'r0'); a.muluw('r0', 'r3'); a.sts_macl('r0'); a.add('r0', 'r1')
    a.stspr_predec('r15'); a.movl_predec('r4', 'r15')
    a.items.append(('bra_sub', 'kdraw1')); a.mov('r1', 'r4')
    a.movl_postinc('r15', 'r4'); a.ldspr_postinc('r15')
    a.mov('r0', 'r9')
    a.label('st_plain')
    a.shll2('r9'); a.movl_pc('W6C00', 'r3'); a.add('r3', 'r9'); a.movl_pc('W0108', 'r1')
    a.movl_pc('STRET', 'r0'); a.jmp('r0'); a.nop()

    emit_kdraw(a, 'kdraw', 'MAP', 'OWNER', 'NEXT', 'WNSLOT', vdp1=False)
    emit_kdraw(a, 'kdraw1', 'MAP1', 'OWNER1', 'NEXT1', 'WNSLOT1', vdp1=True)

    code, _ = assemble_with_bsr(a)
    assert len(code) <= O_LEAD, ('코드가 표 자리를 넘음', len(code))
    blob = bytearray(size); blob[:len(code)] = code
    lead = [0xFF] * 256
    for n, L in enumerate(K.LEADS):
        lead[L] = n
    blob[O_LEAD:O_LEAD + 256] = bytes(lead)
    for v in range(16):
        w = 0
        for b in range(4):
            if v >> (3 - b) & 1:
                w |= K.INK << (12 - 4 * b)
        struct.pack_into('>H', blob, O_LUT + v * 2, w)
    struct.pack_into('>I', blob, O_NEXT, 0); struct.pack_into('>I', blob, O_NEXT1, 0)
    for k in range(K.NSLOT):
        struct.pack_into('>H', blob, O_OWNER + k * 2, 0xFFFF)
    for k in range(len(V1_SLOTS)):
        struct.pack_into('>H', blob, O_OWNER1 + k * 2, 0xFFFF)
    blob[O_SLOTC:O_SLOTC + len(V1_SLOTS)] = bytes(V1_SLOTS)
    blob[O_MAP:O_MAP + N] = b'\xFF' * N
    blob[O_MAP1:O_MAP1 + N] = b'\xFF' * N
    for s, ch in enumerate(syl):
        g = han8gdm.glyph(ch)
        for y in range(8):
            blob[O_GLY + s * 8 + y] = sum(g[y][x] << (7 - x) for x in range(8))
    entries = {('mstub%d' % i): a.labels['mstub%d' % i] for i in range(len(menu_D))}
    entries['bat'] = a.labels['bat']; entries['kdraw'] = a.labels['kdraw']; entries['st'] = a.labels['st']; entries['kdraw1'] = a.labels['kdraw1']
    blob[O_POOL:O_POOL + len(pool)] = pool
    layout = dict(O_POOL=O_POOL, O_LEAD=O_LEAD, O_LUT=O_LUT, O_NEXT=O_NEXT, O_OWNER=O_OWNER, O_MAP=O_MAP, O_GLY=O_GLY, N=N, code=len(code))
    return bytes(blob), entries, layout


def emit_kdraw(a, label, MAP, OWNER, NEXT, WNSLOT, vdp1):
    """r4 = 음절 번호 → r0 = (VDP2: 셀 번호 CELL0+칸 / VDP1: 글꼴 칸 코드 SLOTC[칸]). r1~r4 파괴, r5~r7 보존.
    캐시 = MAP[s]→칸, OWNER[칸]→s, NEXT 돌림. 글리프는 매번 다시 쓴다(VRAM 이 덮였어도 복구)."""
    L = lambda t: label + '_' + t
    a.label(label)
    a.movl_predec('r5', 'r15'); a.movl_predec('r6', 'r15'); a.movl_predec('r7', 'r15')
    a.movl_pc(MAP, 'r1'); a.movl_pc(OWNER, 'r3')
    a.mov('r4', 'r0'); a.movb_r0m('r1', 'r2'); a.extub('r2', 'r2')
    a.movi(-1, 'r5'); a.extub('r5', 'r5'); a.cmpeq('r5', 'r2'); a.bt(L('alloc'))
    a.mov('r2', 'r0'); a.shll('r0'); a.movw_r0m('r3', 'r5'); a.extuw('r5', 'r5'); a.cmpeq('r4', 'r5'); a.bt(L('have'))
    a.label(L('alloc'))
    a.movl_pc(NEXT, 'r6'); a.movl_load('r6', 'r2')
    a.mov('r2', 'r0'); a.addi(1, 'r0'); a.movl_pc(WNSLOT, 'r5'); a.cmphs('r5', 'r0'); a.bf(L('nw')); a.movi(0, 'r0')
    a.label(L('nw'))
    a.movl_store('r0', 'r6')
    a.mov('r2', 'r0'); a.shll('r0'); a.movw_r0m('r3', 'r5'); a.extuw('r5', 'r5')
    a.movl_pc('WFFFF', 'r6'); a.extuw('r6', 'r6'); a.cmpeq('r6', 'r5'); a.bt(L('noev'))
    a.mov('r5', 'r0'); a.movi(-1, 'r7'); a.movb_r0n_store('r7', 'r1')
    a.label(L('noev'))
    a.mov('r2', 'r0'); a.shll('r0'); a.movw_r0n_store('r4', 'r3')
    a.mov('r4', 'r0'); a.movb_r0n_store('r2', 'r1')
    a.label(L('have'))
    if vdp1:
        a.movl_pc('SLOTC', 'r0'); a.add('r2', 'r0'); a.movb_load('r0', 'r5'); a.extub('r5', 'r5')   # r5 = 글꼴 칸 코드
        a.mov('r5', 'r6'); a.shll2('r6'); a.shll2('r6'); a.shll('r6'); a.movl_pc('V1FONT', 'r0'); a.add('r0', 'r6')
    else:
        a.movl_pc('WCELL0', 'r5'); a.add('r2', 'r5')
        a.mov('r5', 'r6'); a.shll2('r6'); a.shll2('r6'); a.shll('r6'); a.movl_pc('VRAM', 'r0'); a.add('r0', 'r6')
    a.mov('r4', 'r7'); a.shll2('r7'); a.shll('r7'); a.movl_pc('GLY', 'r0'); a.add('r0', 'r7')
    a.movl_pc('LUT', 'r3'); a.movi(8, 'r1')
    a.label(L('row'))
    a.movb_postinc('r7', 'r4'); a.extub('r4', 'r4')
    a.mov('r4', 'r0'); a.shlr2('r0'); a.shlr2('r0'); a.shll('r0'); a.movw_r0m('r3', 'r2'); a.shll16('r2')
    a.mov('r4', 'r0'); a.andi(15); a.shll('r0'); a.movw_r0m('r3', 'r0'); a.extuw('r0', 'r0'); a.orr('r0', 'r2')
    a.movl_store('r2', 'r6'); a.addi(4, 'r6')
    a.dt('r1'); a.bf(L('row'))
    a.mov('r5', 'r0')
    a.movl_postinc('r15', 'r7'); a.movl_postinc('r15', 'r6'); a.rts(); a.movl_postinc('r15', 'r5')


def assemble_with_bsr(a):
    """sh2asm 에 bsr 이 없어 ('bra_sub', 라벨) 항목을 bsr 로 푼다(bra 와 같은 변위)."""
    items = a.items; a.items = []
    marks = []
    for it in items:
        if it[0] == 'bra_sub':
            marks.append(len(a.items)); a.items.append(('bra', it[1]))
        else:
            a.items.append(it)
    code, n = a.assemble()
    code = bytearray(code)
    addr = a.base; idx = 0; pos = {}
    for k, it in enumerate(a.items):
        if it[0] == 'label':
            continue
        pos[k] = addr; addr += 2
    for k in marks:
        o = pos[k] - a.base
        w = struct.unpack_from('>H', code, o)[0]
        assert w >> 12 == 0xA
        struct.pack_into('>H', code, o, 0xB000 | (w & 0xFFF))
    return bytes(code), n


def src(name):
    if '--orig' in sys.argv and name != 'BIN_FDATA.BIN':   # 시험용: 원본 모듈 위에 다시
        return os.path.join(ROOT, 'work', 'dm', name)
    p = os.path.join(ROOT, 'work', 'build', name)
    return p if os.path.exists(p) else os.path.join(ROOT, 'work', 'dm', name)


def main():
    dry = '--dry' in sys.argv
    menu_D = [MENU_LOAD + o for o in MENU.values()]
    import menu_labels as ML
    plans = {name: ML.plan(open(src(name), 'rb').read(), MENU_LOAD) for name in MENU}
    pool, pool_refs = ML.make_pool(plans)
    blob, ent, lay = build_blob(menu_D, pool)
    pool_base = BLOB_RAM + lay['O_POOL']
    print('블롭 %d B (코드 %d B, 음절 %d) → FDATA 0x%X‥0x%X / RAM 0x%08X'
          % (len(blob), lay['code'], lay['N'], BLOB_OFF, BLOB_OFF + len(blob), BLOB_RAM))
    assert BLOB_OFF + len(blob) <= FONT_LIMIT, '블롭이 폰트 구간 상한을 넘음'

    sys.path.insert(0, HERE)
    import font_build as FB, font_codec as C
    fd = bytearray(open(src('BIN_FDATA.BIN'), 'rb').read())
    fend = FB.region_end(bytes(fd), C.FULL_BASE)
    assert fend <= BLOB_OFF, '폰트 끝 0x%X 가 블롭 자리 0x%X 를 침범 — 한자 칸을 비운 font_apply 먼저' % (fend, BLOB_OFF)
    if '--orig' in sys.argv:                       # 시험용: 이전 블롭 지우고 다시
        fd[BLOB_OFF:FONT_LIMIT] = bytes(FONT_LIMIT - BLOB_OFF)
    assert not any(fd[BLOB_OFF:BLOB_OFF + len(blob)]) or bytes(fd[BLOB_OFF:BLOB_OFF + len(blob)]) == blob, '블롭 자리가 0 이 아님'
    fd[BLOB_OFF:BLOB_OFF + len(blob)] = blob
    out = {'BIN_FDATA.BIN': bytes(fd)}
    print('  폰트 끝 0x%X (블롭까지 여유 %d B)' % (fend, BLOB_OFF - fend))

    for i, (name, off) in enumerate(MENU.items()):
        d = bytearray(open(src(name), 'rb').read())
        assert bytes(d[off:off + 10]) == D_ORIG10, (name, '분배기 머리가 예상과 다름', d[off:off + 10].hex())
        D = MENU_LOAD + off
        assert D % 4 == 2
        # D+0: mov.l @(1,pc),r1 → (D+4)&~3 + 4 = D+6 ; D+2: jmp @r1 ; D+4: nop ; D+6: 리터럴
        patch = struct.pack('>HHH', 0xD101, 0x412B, 0x0009) + struct.pack('>I', ent['mstub%d' % i])
        d[off:off + 10] = patch
        nin, npool = ML.apply(d, plans[name], pool_refs, pool_base, MENU_LOAD)
        out[name] = bytes(d)
        print('    라벨 제자리 %d · 풀로 돌림 %d' % (nin, npool))
        print('  %-16s D=0x%08X → 0x%08X' % (name, D, ent['mstub%d' % i]))

    # 저장 화면 SAVER.BIN(0x0602C000 적재): 훅 없이 라벨만 제자리(글자는 훅 걸린 모듈의 문자열 함수로 찍힌다 — 이름은 이미 한글로 나옴)
    sv = bytearray(open(src('FIELD_SAVER.BIN'), 'rb').read())
    sops = [op for op in ML.plan(bytes(sv), 0x0602C000) if op[0] != 'names']
    assert all(op[0] == 'in' for op in sops), 'SAVER 라벨이 칸을 넘음'
    ML.apply(sv, sops, {}, 0, 0x0602C000)
    out['FIELD_SAVER.BIN'] = bytes(sv)
    print('  %-16s 라벨 제자리 %d' % ('FIELD_SAVER.BIN', len(sops)))

    b = bytearray(open(src(BATLE), 'rb').read())
    o = B_PATCH - BATLE_LOAD
    assert bytes(b[o:o + len(B_ORIG)]) == B_ORIG, ('BATLE 루프가 예상과 다름', b[o:o + len(B_ORIG)].hex())
    # 0x0603F744: mov.l @(2,pc),r3 → (0x748)&~3 + 8 = 0x0603F750 ; jmp @r3 ; nop ; nop… ; 0x0603F750: 리터럴
    patch = struct.pack('>HHHHHH', 0xD302, 0x432B, 0x0009, 0x0009, 0x0009, 0x0009) + struct.pack('>I', ent['bat'])
    b[o:o + len(patch)] = patch
    o2 = S_PATCH - BATLE_LOAD
    assert bytes(b[o2:o2 + len(S_ORIG)]) == S_ORIG, ('상태창 계산부가 예상과 다름', b[o2:o2 + 10].hex())
    disp = (S_LIT - ((S_PATCH + 4) & ~3)) // 4
    b[o2:o2 + 10] = struct.pack('>HHHHH', 0xD300 | disp, 0x432B, 0x0009, 0x0009, 0x0009)
    struct.pack_into('>I', b, S_LIT - BATLE_LOAD, ent['st'])          # 원래 0x6C00·0x0108 자리(이 두 명령만 쓰던 풀)
    print('  %-16s 0x%08X → 0x%08X (상태창)' % (BATLE, S_PATCH, ent['st']))
    out[BATLE] = bytes(b)
    print('  %-16s 0x%08X → 0x%08X' % (BATLE, B_PATCH, ent['bat']))

    if dry:
        print('--dry: 안 씀'); return out, ent, lay
    os.makedirs(os.path.join(ROOT, 'work', 'build'), exist_ok=True)
    for name, data in out.items():
        open(os.path.join(ROOT, 'work', 'build', name), 'wb').write(data)
    print('썼음:', ', '.join(out))
    return out, ent, lay


if __name__ == '__main__':
    main()
