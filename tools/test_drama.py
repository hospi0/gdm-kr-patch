# -*- coding: utf-8 -*-
r"""드라마 자막 vhook 검산(2026-10-16) — 실제 블롭을 SH-2 흉내기로 돌려 VDP1 프레임버퍼 화소를 build_drama 미리보기 규칙과 대조.
  python tools/test_drama.py   → work/drama/sim_*.png
"""
import os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.argv += ['--dry', '--orig']
import build_drama as D
import sh2sim as S
from PIL import Image

STOP = 0x06000846                       # V_HANDLER(원래 VBlank 처리기)로 돌아오면 끝


def run(blob, meta, fad, fb=None, last=None):
    m = S.Mem()
    hw = m.add(0x06000000, 0x100000); lw = m.add(0x00200000, 0x100000)
    v1 = m.add(0x25C80000, 0x40000)
    if fb is not None: v1[:] = fb
    o = meta['base'] - 0x00200000; lw[o:o + len(blob)] = blob
    if last is not None: struct.pack_into('>I', lw, meta['v_last'] - 0x00200000, last)
    struct.pack_into('>I', hw, D.FAD_VAR - 0x06000000, fad)
    regs = [0] * 16; regs[15] = 0x060FF000
    r, n = S.run(m, meta['vhook'], regs, stop=STOP)
    return bytes(v1), struct.unpack_from('>I', lw, meta['v_last'] - 0x00200000)[0], n


def expect(rows, font):
    want = set()
    for r, txt in enumerate(rows):
        x = D.CAP_X + (D.FIELD_W - sum(font.adv(c) for c in txt)) // 2
        for c in txt:
            g = font.glyphs[font.idx[c]]
            for y in range(D.GH):
                for xx in range(12):
                    if g[y] >> (15 - xx) & 1:
                        want.add((x + xx, D.CAP_Y + r * D.LINE_H + y))
            x += font.adv(c)
    return want


def test_boot(blob, meta):
    """IP 부트스트랩: 드라마 FAD → 설치(블롭 있을 때만) / BGM FAD → 그대로 / 퇴장 FAD(E800 0x7A21) → 해제"""
    boot = D.build_boot(meta, D.drama_fad(295), D.GM3_LBA + D.DRAMA_END_SEC[299] + 150)
    ok = True
    def go(fad, vec, with_blob=True):
        m = S.Mem(); hw = m.add(0x06000000, 0x100000); lw = m.add(0x00200000, 0x100000)
        if with_blob:
            o = meta['base'] - 0x00200000; lw[o:o + len(blob)] = blob
        a = D.IP_BASE + D.IP_GAP - 0x06000000; hw[a:a + len(boot)] = boot
        struct.pack_into('>I', hw, D.VEC41 - 0x06000000, vec)
        struct.pack_into('>I', hw, D.FAD_VAR - 0x06000000, fad)
        S.run(m, D.IP_BASE + D.IP_GAP, [0] * 15 + [0x060FF000], stop=D.ORIG_FN)
        return struct.unpack_from('>I', hw, D.VEC41 - 0x06000000)[0], struct.unpack_from('>I', lw, meta['v_handler'] - 0x00200000)[0]
    cases = [('드라마 첫 조각', D.drama_fad(295) + 3, D.ORIG_VBLANK, True, meta['vhook']),
             ('드라마 · 블롭 없음', D.drama_fad(297), D.ORIG_VBLANK, False, D.ORIG_VBLANK),
             ('방 BGM(설치 안 됨)', 0xA2A0, D.ORIG_VBLANK, True, D.ORIG_VBLANK),
             ('방 BGM(설치됨 유지)', 0xA2A0, meta['vhook'], True, meta['vhook']),
             ('퇴장 E800 읽기', 0x7A21, meta['vhook'], True, D.ORIG_VBLANK),
             ('옮긴 E804 다시 읽기', 0x2F000, meta['vhook'], True, meta['vhook'])]
    for name, fad, vec, wb, want in cases:
        v, h = go(fad, vec, wb)
        good = v == want and (want != meta['vhook'] or vec == meta['vhook'] or h == D.ORIG_VBLANK)
        ok &= good
        print('  부트 %-18s FAD %#7x → 벡터 %#x %s' % (name, fad, v, '✓' if good else '★'))
    return ok


def main():
    blob, meta, pages, font = D.main()
    fad_lo = D.drama_fad(295)
    ok = True; fb = None; last = None
    os.makedirs(os.path.join(D.ROOT, 'work', 'drama'), exist_ok=True)
    picks = [0, 2, 5, 120, 250, len(pages) - 1]
    for k in picks:
        idx, fs, fe, rows = pages[k]
        fb, last, n = run(blob, meta, fad_lo + (fs + fe) // 2, fb, last)
        got = set()
        for y in range(D.CAP_Y - 2, D.CAP_Y + D.MAX_ROWS * D.LINE_H + 2):
            for x in range(0, 352):
                if struct.unpack_from('>H', fb, (y * D.FB_W + x) * 2)[0] == D.COLOR:
                    got.add((x, y))
        want = expect(rows, font)
        good = got == want
        ok &= good
        print('판 %3d (드라마 %d) %s  화소 %d/%d  %d 명령  «%s»' % (k, idx - 294, '일치' if good else '★불일치', len(got & want), len(want), n, ' / '.join(rows)[:40]))
        im = Image.new('RGB', (352, 80))
        for (x, y) in got: im.putpixel((x, y - D.CAP_Y + 4), (255, 255, 255))
        im.resize((1056, 240), Image.NEAREST).save(os.path.join(D.ROOT, 'work', 'drama', 'sim_%03d.png' % k))
    # 자막 없는 구간 → 지우기
    fb, last, n = run(blob, meta, fad_lo - 10, fb, last)
    print('드라마 밖 FAD: last=%#x (그대로 = 체인만)' % last)
    ok &= test_boot(blob, meta)
    print('★전부 일치' if ok else '★불일치 있음')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
