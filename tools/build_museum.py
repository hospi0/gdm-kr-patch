# -*- coding: utf-8 -*-
"""박물관 컨텐츠(MTMES/MTOUT/DICDT) 한글 반영 빌더.

섹션 단위로 문자열을 다시 이어 붙인다. 규칙:
  · 문자열 **개수와 순서**를 절대 바꾸지 않는다(렌더러가 널을 세어 N번째를 찾음).
  · 빈 문자열(길이 0)은 빈 채로 유지 — 지우면 순번이 밀린다.
  · 남는 자리는 **공백 0x20**으로 채운다. 널 패딩 금지.
    [[feedback_null_padding_shifts_string_index]]
  · 섹션 총 바이트는 원본과 **정확히 동일**하게 맞춘다(뒤 섹션 오프셋 불변).

빌드 후 회귀검사:
  · 널 경계 목록이 원본과 완전히 일치하는가 (되읽기 검증만으론 못 잡는다)
  · 파일 크기 동일
"""
import os
import sys

sys.path.insert(0, 'tools')
sys.path.insert(0, 'work/trans')
import bintext as B
from museum import SPECS, bounds, strings
from runs_build import load_maps

_, KOCODES = load_maps()


def load_ko():
    import museum_ko
    import museum_desc_ko
    ko = {}
    for k, v in museum_ko.KO.items():
        ko[k] = list(v)
    for k, v in museum_desc_ko.KO.items():
        ko.setdefault(k, [v])
    return ko


def null_shape(d, lo, hi):
    """섹션의 «문자열 순번 구조» — 회귀검사의 기준.

    렌더러는 널을 세어 N번째 문자열을 찾는다. 그러니 지켜야 하는 것은
    **개수와 빈칸 위치**이지 오프셋 자체가 아니다(섹션 안에서 길이를
    재분배하면 오프셋은 당연히 밀린다).
    빈 문자열이 하나라도 생기거나 사라지면 그 뒤가 전부 어긋난다.
    [[feedback_null_padding_shifts_string_index]]
    """
    return [l == 0 for _, l, _ in strings(d, lo, hi)]


def main():
    KO = load_ko()
    os.makedirs('work/build', exist_ok=True)
    grand = 0
    for fn, spec in SPECS.items():
        src = os.path.join('work/dm', fn)
        dst = os.path.join('work/build', fn)
        base = open(dst, 'rb').read() if os.path.exists(dst) else open(src, 'rb').read()
        orig = open(src, 'rb').read()
        out = bytearray(base)
        n_file = 0
        for name, lo, hi in bounds(orig, spec):
            ss = strings(orig, lo, hi)
            # ── 1) 각 문자열 인코딩 (길이 제한 없이) ──
            enc = []
            n = 0
            for o, l, t in ss:
                if l == 0:
                    enc.append(b'')
                    continue
                cands = KO.get(t.rstrip('　 ')) or KO.get(t)
                got = None
                for c in cands or []:
                    try:
                        got = B.encode_with_vars(c, KOCODES)
                        break
                    except KeyError:
                        continue
                if got is None:
                    enc.append(orig[o:o + l])
                else:
                    enc.append(got)
                    n += 1
            # ── 2) 섹션 예산 재분배 ──
            #    예산은 «문자열별»이 아니라 «섹션 총량»이다. 남는 바이트는
            #    각 문자열을 원래 길이까지 공백으로 되돌리는 데 먼저 쓰고,
            #    그래도 남으면 마지막 문자열 뒤에 붙인다(전부 공백이라 무해).
            room = (hi - lo) - sum(len(e) + 1 for e in enc)
            if room < 0:
                raise SystemExit('%s/%s 예산 초과 %d B' % (fn, name, -room))
            final = list(enc)
            for i, (o, l, t) in enumerate(ss):
                if room <= 0:
                    break
                want = min(l - len(final[i]), room)
                if want > 0:
                    final[i] += b'\x20' * want
                    room -= want
            if room:
                for i in range(len(final) - 1, -1, -1):
                    if final[i]:
                        final[i] += b'\x20' * room
                        room = 0
                        break
            seg = bytearray()
            for e in final:
                seg += e + b'\x00'
            assert len(seg) == hi - lo, '%s/%s 길이 불일치 %d != %d' % (fn, name, len(seg), hi - lo)
            out[lo:hi] = seg
            n_file += n
            print('  %-16s %-10s 반영 %4d / %d' % (fn[6:], name, n, len(ss)))

        # ── 회귀검사: 널 경계(문자열 시작 오프셋)가 원본과 같은가 ──
        ok = True
        for name, lo, hi in bounds(orig, spec):
            a = null_shape(orig, lo, hi)
            b = null_shape(bytes(out), lo, hi)
            if a != b:
                ok = False
                print('  ★순번구조 어긋남 %s/%s  원본 %d개(빈칸 %d) -> 빌드 %d개(빈칸 %d)'
                      % (fn, name, len(a), sum(a), len(b), sum(b)))
        assert len(out) == len(orig), '파일 크기 변경'
        open(dst, 'wb').write(bytes(out))
        print('%-20s 반영 %d  크기 %d  순번구조 %s' %
              (fn, n_file, len(out), '일치 ✅' if ok else '★불일치'))
        grand += n_file
    print('\n합계 반영 %d' % grand)


if __name__ == '__main__':
    main()
