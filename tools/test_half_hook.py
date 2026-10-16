# -*- coding: utf-8 -*-
r"""반각 8×8 한글 훅 검산 (2026-10-16) — 패치된 실제 모듈 코드를 SH-2 흉내기로 돌린다.
  전투: BATLE.BIN 8×8 문자열 루프(0x0603F722‥)에 섞인 문자열 → VDP2 NBG3 맵(0x25E0E000) 단어 + 캐시 셀 글리프 대조.
  메뉴: CMDMN 문자열 함수의 루프(0x060BB39A‥, 서식 뒤) → 분배기 훅 → 화면 버퍼(@(D+0x302)) 단어 대조.
  python tools/test_half_hook.py   (build_half_hook --dry 결과로 검산, work/build 안 씀)
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import build_half_hook as BH
import half_ko as K
import han8gdm
import sh2sim as S

STOP = 0x06001000


def mem_with(out):
    m = S.Mem()
    hw = m.add(0x06000000, 0x100000)
    lw = m.add(0x00200000, 0x100000)
    vr = m.add(0x25E00000, 0x80000)
    lw[:len(out['BIN_FDATA.BIN'])] = out['BIN_FDATA.BIN']
    return m, hw, lw, vr


def expect_cell(vr, cell, ch):
    g = han8gdm.glyph(ch)
    for y in range(8):
        row = vr[cell * 32 + y * 4: cell * 32 + y * 4 + 4]
        px = [(row[x // 2] >> (4 if x % 2 == 0 else 0)) & 15 for x in range(8)]
        want = [K.INK if g[y][x] else 0 for x in range(8)]
        if px != want:
            return False
    return True


def test_battle(out):
    m, hw, lw, vr = mem_with(out)
    b = out[BH.BATLE]; o = BH.BATLE_LOAD - 0x06000000; hw[o:o + len(b)] = b
    text = '번플레어'
    s = K.encode(text) + b'7' + K.encode('번') + b'\x00'
    hw[0xF0000:0xF0000 + len(s)] = s
    F = 0x060FE000; hw[F - 0x06000000 + 8:F - 0x06000000 + 12] = struct.pack('>I', 4)  # @(0xB,R15) = 팔레트 4
    regs = [0] * 16; regs[4] = 0x060F0000; regs[6] = 3; regs[7] = 5; regs[15] = F
    # 함수 꼬리(mov.l @r15+,r13 ; rts ; mov.l @r15+,r14)까지 돌고 PR(=STOP)로 돌아온다
    r, n = S.run(m, 0x0603F722, regs, stop=STOP)
    ok = True
    base = 0xE000 + (5 * 64 + 3) * 2
    words = [struct.unpack_from('>H', vr, base + 2 * k)[0] for k in range(7)]
    cells = [w & 0xFFF for w in words]
    want_chars = list(text) + ['7', '번']
    for k, ch in enumerate(want_chars):
        w = words[k]
        if (w >> 12) != 4: ok = False; print('  ✗ 팔레트', k, hex(w))
        if ch == '7':
            if cells[k] != 0x37: ok = False; print('  ✗ ASCII', hex(w))
        else:
            if not (K.CELL0 <= cells[k] < K.CELL0 + K.NSLOT and expect_cell(vr, cells[k], ch)):
                ok = False; print('  ✗ 한글', k, ch, hex(w))
    if words[6] != 0: ok = False; print('  ✗ 끝 뒤에 씀', hex(words[6]))
    if cells[0] != cells[5]: ok = False; print('  ✗ 같은 음절인데 다른 칸', cells)
    print('전투  %s  맵 %s  (%d 명령)' % ('통과' if ok else '실패', ' '.join('%04X' % w for w in words), n))
    return ok


def test_menu(out):
    m, hw, lw, vr = mem_with(out)
    name = 'FIELD_CMDMN.BIN'; d = out[name]; o = BH.MENU_LOAD - 0x06000000; hw[o:o + len(d)] = d
    D = BH.MENU_LOAD + BH.MENU[name]
    buf = struct.unpack_from('>I', d, BH.MENU[name] + BH.BUF_LIT)[0]
    text = 'A번플레어 7힘'
    s = b''
    for part in ('A', '번플레어', ' 7', '힘'):
        s += K.encode(part)
    F = 0x060FD000; fo = F - 0x06000000
    hw[fo + 0] = 10                      # x
    hw[fo + 4] = 2                       # 모드 2(그대로). 모드 3 은 원래도 ASCII 를 −0x20 한다(히라가나 전용)
    struct.pack_into('>H', hw, fo + 8, 9)  # 팔레트 9
    hw[fo + 0xC] = 7                     # y
    hw[fo + 0x10:fo + 0x10 + len(s)] = s
    struct.pack_into('>I', hw, fo + 0x110, STOP)        # lds.l @r15+,pr
    regs = [0] * 16; regs[0] = len(s); regs[15] = F
    r, n = S.run(m, 0x060BB39A, regs, stop=STOP)
    words = [struct.unpack_from('>H', hw, buf - 0x06000000 + ((7 * 64) + 10 + k) * 2)[0] for k in range(10)]
    want = ['A'] + list('번플레어') + [' ', '7', '힘']
    ok = True
    for k, ch in enumerate(want):
        w = words[k]
        if w >> 12 != 9: ok = False; print('  ✗ 팔레트', k, hex(w))
        c = w & 0xFFF
        if '가' <= ch <= '힣':
            if not (K.CELL0 <= c < K.CELL0 + K.NSLOT and expect_cell(vr, c, ch)): ok = False; print('  ✗ 한글', k, ch, hex(w))
        else:
            # 모드 3 은 0x20~0x7F 를 그대로 둔다(히라가나 변환은 0xA6‥ 만)
            if c != ord(ch): ok = False; print('  ✗ 글자', k, ch, hex(w))
    if words[len(want)] != 0: ok = False; print('  ✗ 끝 뒤에 씀', hex(words[len(want)]))
    print('메뉴  %s  버퍼 %s  (%d 명령)' % ('통과' if ok else '실패', ' '.join('%04X' % w for w in words), n))
    return ok


def built():
    """work/build 에 이미 훅이 들어가 있으면 그 결과물을 그대로 검산(빌더를 다시 돌리면 패치된 모듈을 원본처럼 읽는다)"""
    b = lambda n: os.path.join(HERE, '..', 'work', 'build', n)
    names = ['BIN_FDATA.BIN', 'FIELD_CMDMN.BIN', BH.BATLE]
    if '--orig' in sys.argv:
        return None
    if not all(os.path.exists(b(n)) for n in names):
        return None
    out = {n: open(b(n), 'rb').read() for n in names}
    off = BH.MENU['FIELD_CMDMN.BIN']
    if out['FIELD_CMDMN.BIN'][off:off + 2] != bytes.fromhex('d101'):
        return None
    return out


def test_status(out):
    """전투 상태창 처리(st)를 진입점부터: 한글이면 VDP1 글꼴 칸에 글리프 + R9 = 0x6C00+칸*4, 포인터 +1"""
    m, hw, lw, vr = mem_with(out)
    v1 = m.add(0x25C00000, 0x80000)
    b = out[BH.BATLE]; o = BH.BATLE_LOAD - 0x06000000; hw[o:o + len(b)] = b
    lit = struct.unpack_from('>I', b, BH.S_LIT - BH.BATLE_LOAD)[0]
    ok = True
    enc = K.encode('런너') + b'7'
    hw[0xF0000:0xF0000 + len(enc)] = enc
    F = 0x060FE000
    seen = []
    ptr = 0x060F0000
    for want in ('런', '너', '7'):
        c = hw[ptr - 0x06000000]
        struct.pack_into('>I', hw, F - 0x06000000 + 4, ptr + 1)       # 루프가 이미 +1 해 둔 포인터
        regs = [0] * 16; regs[9] = c if c < 0x80 else c - 0x100 & 0xFFFFFFFF; regs[4] = 0x060E0000; regs[15] = F
        r, n = S.run(m, lit, regs, stop=BH.S_RET)
        code = (r[9] - 0x6C00) // 4
        ptr = struct.unpack_from('>I', hw, F - 0x06000000 + 4)[0]
        if r[1] != 0x0108: ok = False; print('  ✗ R1', hex(r[1]))
        if want == '7':
            if code != 0x37: ok = False; print('  ✗ ASCII', hex(r[9]))
        else:
            if code not in BH.V1_SLOTS or not expect_cell(v1, 0x36000 // 32 + code, want): ok = False; print('  ✗ 한글', want, hex(r[9]))
        seen.append(hex(r[9]))
    if ptr != 0x060F0000 + len(enc): ok = False; print('  ✗ 포인터', hex(ptr))
    print('상태창 %s  CMDSRCA %s' % ('통과' if ok else '실패', ' '.join(seen)))
    return ok


def main():
    out = built()
    if out is None:
        sys.argv.append('--dry')
        out, ent, lay = BH.main()
    else:
        print('work/build 결과물로 검산')
    a = test_battle(out); b = test_menu(out); c = test_status(out)
    print('★전부 통과' if a and b and c else '★실패 있음')
    sys.exit(0 if a and b and c else 1)


if __name__ == '__main__':
    main()
