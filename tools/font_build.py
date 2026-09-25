# -*- coding: utf-8 -*-
"""FDATA.BIN 재빌드 — 글리프를 갈아끼우고 오프셋표를 다시 쓴다.

레코드가 가변 길이라 표를 다시 쓰면 글리프를 늘리고 줄일 수 있다.
다만 **폰트 구간이 커질 수 있는 한계**가 있다:

  전각 폰트는 FDATA `+0xA00`에서 시작하고, 파일 안에서 다음 구조가
  `+0xAA03`부터 시작한다(그 사이는 0 패딩). 그 지점을 넘기면 다른 데이터를
  덮으므로 **`+0xAA03`이 하드 상한**이다.

빌드 결과는 반드시 다시 디코드해 의도한 글리프와 대조한다.
"""
import struct
import sys

sys.path.insert(0, 'tools')
import font_codec as C

SRC = 'work/dm/BIN_FDATA.BIN'
FULL_LIMIT = 0xAA03        # 전각 폰트 구간의 하드 상한 (파일 오프셋)
HALF_LIMIT = C.FULL_BASE   # 반각 폰트 구간의 하드 상한


def read_all(d, base):
    """구간의 전 글리프를 원시 바이트로"""
    n = C.table_count(d, base)
    return [C.decode_record(d, base + C.entry_offset(d, base, i))[0] for i in range(n)]


def region_end(d, base):
    n = C.table_count(d, base)
    return base + max(C.entry_offset(d, base, i)
                      + C.decode_record(d, base + C.entry_offset(d, base, i))[1]
                      for i in range(n))


def budget(d):
    fe, he = region_end(d, C.FULL_BASE), region_end(d, C.HALF_BASE)
    print('전각: 0x%X ~ 0x%X (%d B), 상한 0x%X → 여유 %d B'
          % (C.FULL_BASE, fe, fe - C.FULL_BASE, FULL_LIMIT, FULL_LIMIT - fe))
    print('반각: 0x%X ~ 0x%X (%d B), 상한 0x%X → 여유 %d B'
          % (C.HALF_BASE, he, he - C.HALF_BASE, HALF_LIMIT, HALF_LIMIT - he))
    # 중복 공유로 아낄 수 있는 양
    for nm, base in (('전각', C.FULL_BASE), ('반각', C.HALF_BASE)):
        recs = [C.encode_record(g) for g in read_all(d, base)]
        save = len(C.build(recs)) - len(C.build(recs, share=True))
        print('  %s 중복 공유 시 추가 확보 %d B' % (nm, save))


def rebuild(d, full=None, half=None, share=False):
    """full/half = {코드: 원시32바이트} 교체 지시. 새 FDATA 바이트열을 낸다."""
    out = bytearray(d)
    for base, repl, limit, nm in ((C.FULL_BASE, full, FULL_LIMIT, '전각'),
                                  (C.HALF_BASE, half, HALF_LIMIT, '반각')):
        glyphs = read_all(d, base)
        for code, raw in (repl or {}).items():
            if not 0 <= code < len(glyphs):
                raise ValueError('%s 코드 0x%X 는 범위 밖 (0~0x%X)'
                                 % (nm, code, len(glyphs) - 1))
            if len(raw) != C.NBYTE:
                raise ValueError('%s 코드 0x%X: 글리프는 %d바이트여야 한다'
                                 % (nm, code, C.NBYTE))
            glyphs[code] = bytes(raw)
        blob = C.build([C.encode_record(g) for g in glyphs], share=share)
        end = base + len(blob)
        if end > limit:
            raise ValueError('%s 구간이 상한을 넘었다: 끝 0x%X > 0x%X (%d B 초과)'
                             % (nm, end, limit, end - limit))
        out[base:base + len(blob)] = blob
        # 남은 자리는 0으로 (이전 내용이 남지 않도록)
        for i in range(end, limit):
            out[i] = 0
    return bytes(out)


def verify(new, d, full=None, half=None):
    """새 파일을 다시 디코드해 의도한 글리프와 전량 대조"""
    bad = 0
    for base, repl, nm in ((C.FULL_BASE, full, '전각'), (C.HALF_BASE, half, '반각')):
        want = read_all(d, base)
        for code, raw in (repl or {}).items():
            want[code] = bytes(raw)
        got = read_all(new, base)
        if len(want) != len(got):
            print('  %s 항목 수 불일치 %d ≠ %d' % (nm, len(want), len(got)))
            bad += 1
            continue
        for i, (a, b) in enumerate(zip(want, got)):
            if a != b:
                print('  %s 코드 0x%X 불일치' % (nm, i))
                bad += 1
    print('재빌드 검증: %s (불일치 %d)' % ('통과' if bad == 0 else '실패', bad))
    return bad == 0


def main():
    d = open(SRC, 'rb').read()
    budget(d)
    print()
    # 스모크 테스트: 교체 없이 재빌드하면 원본과 바이트가 같아야 한다
    same = rebuild(d) == d
    print('무교체 재빌드 = 원본과 바이트 동일: %s' % same)
    # 스모크 테스트: 글리프 하나를 합성 패턴으로 교체
    test = C.rows_to_raw([0x0000, 0x7FFE, 0x4002, 0x4002, 0x4002, 0x7FFE,
                          0x0000, 0x1248, 0x1248, 0x7FFE, 0x1248, 0x1248,
                          0x0000, 0x3FFC, 0x2004, 0x0000])
    new = rebuild(d, full={0x300: test})
    verify(new, d, full={0x300: test})


if __name__ == '__main__':
    main()
