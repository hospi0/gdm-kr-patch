# -*- coding: utf-8 -*-
"""propagate_ui_dup.py 결과 검증:
  1) work/build/<file> 의 바뀐 위치가 전부 기대한 KO 인코딩과 바이트 일치하는가
  2) 대상 밖 바이트는 원본(work/dm/<file>)과 완전히 같은가(누출 0)
"""
import os
import sys

sys.path.insert(0, 'tools')
import bintext as B
from runs_build import load_maps
import propagate_ui_dup as P

_, KO = load_maps()


def main():
    pairs = P.load_translations()
    total_bad = total_leak = total_checked = 0
    for fname in P.TARGETS:
        src = os.path.join(P.SRC, fname)
        dst = os.path.join(P.DST, fname)
        if not os.path.exists(dst):
            continue
        orig = open(src, 'rb').read()
        built = open(dst, 'rb').read()
        if len(orig) != len(built):
            print('★크기 변경!', fname, len(orig), '->', len(built))
            continue
        touched = bytearray(len(orig))
        bad = 0
        for jp_bytes, ko_text in pairs.items():
            if len(jp_bytes) < 2:
                continue
            for pos in P.find_all(orig, jp_bytes):
                end = pos + len(jp_bytes)
                if end >= len(orig) or orig[end] != 0:
                    continue
                if pos != 0 and orig[pos - 1] != 0:
                    continue
                slot = end - pos
                try:
                    enc = B.encode_with_vars(ko_text, KO)
                except KeyError:
                    continue
                if len(enc) > slot:
                    continue
                want = enc + b'\x20' * (slot - len(enc))   # ★공백 패딩(널 금지)
                got = built[pos:pos + slot]
                for i in range(pos, end):
                    touched[i] = 1
                if got != want:
                    bad += 1
                    if bad <= 3:
                        print('  ★불일치', fname, hex(pos), 'want', want.hex(), 'got', got.hex())
        leak = sum(1 for i in range(len(orig)) if not touched[i] and orig[i] != built[i])
        total_bad += bad
        total_leak += leak
        total_checked += 1
        print('%-20s 불일치 %4d  대상밖누출 %6d' % (fname, bad, leak))
    print('\n검사한 파일 %d개 — 불일치 합계 %d, 누출 합계 %d'
          % (total_checked, total_bad, total_leak))


if __name__ == '__main__':
    main()
