# -*- coding: utf-8 -*-
"""반각 메뉴 라벨을 전각 한글로 교체 + 널경계 회귀검사.

`build_sysmenu2.py` **뒤에** 돌린다(전각 본문은 그쪽이 이미 처리).
"""
import os
import sys

sys.path.insert(0, 'tools')
sys.path.insert(0, 'work/trans')
import sysmenu2 as S2
import halfwidth as H
import extract_sysmenu as E
import halfmenu_ko as K

SRC, DST = 'work/dm', 'work/build'


def null_bounds(d, lo, hi):
    out, i = [], lo
    while i < hi:
        j = i
        while j < hi and d[j] != 0:
            j += 1
        out.append(i)
        i = j + 1
    return out


def main():
    files = sorted({f for f, _ in list(K.HALF_MENU) + list(K.HALF_PREFIX)})
    ok = fail = 0
    for fname in files:
        src = open(os.path.join(SRC, fname), 'rb').read()
        base = os.path.join(DST, fname)
        d = bytearray(open(base if os.path.exists(base) else os.path.join(SRC, fname), 'rb').read())

        for (f, off), ko_text in sorted(K.HALF_MENU.items()):
            if f != fname:
                continue
            j = off
            while src[j] != 0:
                j += 1
            slot = j - off
            # ★★반드시 `0x04`(전각 복귀)를 **명시**할 것.
            #   원본이 `0x03`(반각)으로 시작하는 자리는 렌더러가 그 시점에 반각
            #   모드다. 0x03 만 빼고 한글을 쓰면 **1바이트 한글 코드가 반각
            #   글리프로 읽힌다**(실기: `로드`→`cr`). 2바이트 토큰은 모드와 무관해
            #   멀쩡하므로(`本体RAM`→`본체RAM`) 증상이 글자마다 달라 헷갈린다.
            e = b'\x04' + S2.encode_ko(ko_text)
            if len(e) > slot:
                print('  X %s 0x%05X 바이트초과 %d>%d %r' % (fname[6:], off, len(e), slot, ko_text))
                fail += 1
                continue
            d[off:j] = e + b'\x20' * (slot - len(e))
            ok += 1

        for (f, off), ko_text in sorted(K.HALF_PREFIX.items()):
            if f != fname:
                continue
            # 반각 접두(= 첫 'keep' 런)만 한글로. 나머지 세그먼트는 현재 빌드 내용 유지.
            j = off
            while src[j] != 0:
                j += 1
            cur = bytes(d[off:j])          # 전각 본문은 이미 번역돼 있을 수 있다
            segs = S2.segments(cur)
            out = bytearray()
            done = False
            for kind, seg in segs:
                if not done and kind == 'keep' and len(seg) > 1:
                    out += b'\x04' + S2.encode_ko(ko_text)   # ★전각 복귀 명시
                    done = True
                elif not done and kind == 'keep' and len(seg) == 1 and seg[0] == 0x03:
                    continue               # 반각 전환 코드 제거(한글은 전각)
                else:
                    out += seg
            if len(out) > (j - off):
                print('  X %s 0x%05X 접두교체 초과 %d>%d' % (fname[6:], off, len(out), j - off))
                fail += 1
                continue
            d[off:j] = bytes(out) + b'\x20' * ((j - off) - len(out))
            ok += 1

        newb = bytes(d)
        open(os.path.join(DST, fname), 'wb').write(newb)
        lo, hi = next((a, b) for f2, a, b in E.REGIONS if f2 == fname) if any(
            f2 == fname for f2, a, b in E.REGIONS) else (0, len(newb))
        # 널 경계 회귀검사(해당 파일 전 영역)
        same = null_bounds(src, 0, len(src)) == null_bounds(newb, 0, len(newb))
        print('%-18s 널경계 %s' % (fname[6:], '일치 ✅' if same else '★불일치 ❌'))

    print('\n반영 %d, 실패 %d' % (ok, fail))


if __name__ == '__main__':
    main()
