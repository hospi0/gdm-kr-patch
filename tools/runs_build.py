# -*- coding: utf-8 -*-
"""런 단위 제자리 교체 빌더.

정책: **런을 원본과 정확히 같은 바이트 길이로 바꾼다.**
  길이를 안 바꾸므로 명령 스트림·메시지 길이·조건부 스킵·점프가 전부 그대로다.
  남는 자리는 **공백(0x20)** 으로 채운다 — 줄 끝 공백은 화면에 안 보인다.

불변식 (하나라도 어기면 빌드 실패):
  1. ko 가 빈 런은 원본 바이트 그대로
  2. 번역 바이트가 **원본 런 길이를 넘으면 실패** (조용히 자르지 않는다)
  3. 인코딩 불가 문자는 실패
  4. 런 밖 바이트는 **단 하나도 바뀌지 않는다**
  5. 파일 크기 불변
"""
import csv
import os
import sys

sys.path.insert(0, 'tools')
import codemap
from codemap_kanji_src import kanji_map
from extract_runs import extract, text
from script_build import PUNCT_FALLBACK

TSV = 'work/trans/runs.tsv'
KOCODES = 'work/trans/kocodes.tsv'
SRC, DST = 'work/dm', 'work/build'


class BuildError(Exception):
    pass


def load_maps():
    m = codemap.base_map()
    m.update(kanji_map())
    rev = {}
    for c, ch in sorted(m.items()):
        rev.setdefault(ch, c)
    ko = {}
    if os.path.exists(KOCODES):
        for line in open(KOCODES, encoding='utf-8'):
            if line.strip() and not line.startswith('#'):
                a, b = line.rstrip('\n').split('\t')[:2]
                ko[b] = int(a, 16)
    return rev, ko


def encode(s, rev, ko):
    from punct import squeeze          # 문장부호 뒤 공백 삭제(전프로젝트 규칙)
    s = squeeze(s)
    out = bytearray()
    for ch in s:
        c = ko.get(ch, rev.get(ch))
        if c is None and ch in PUNCT_FALLBACK:
            t = PUNCT_FALLBACK[ch]
            c = ko.get(t, rev.get(t))
        if c is None:
            raise BuildError('폰트에 없는 문자 %r (U+%04X)' % (ch, ord(ch)))
        if c < 0xE0:
            out.append(c + 0x20)
        else:
            k = c - 0xE0
            out += bytes((0x10 + k // 256, k % 256))
    return bytes(out)


def main():
    rev, ko = load_maps()
    rows = list(csv.DictReader(open(TSV, encoding='utf-8'), delimiter='\t'))
    byfile = {}
    for r in rows:
        byfile.setdefault(r['file'], {})[int(r['off'], 16)] = r
    os.makedirs(DST, exist_ok=True)

    n_tr = n_same = 0
    over = []
    for f in sorted(os.listdir(SRC)):
        if not f.endswith('.MDT'):
            continue
        name = f[6:]
        d = bytearray(open(os.path.join(SRC, f), 'rb').read())
        o, s, rs = extract(bytes(d), name)
        for off, L, codes in rs:
            r = byfile.get(name, {}).get(off)
            kotext = (r or {}).get('ko', '').rstrip()   # ★앞 공백은 진짜 텍스트 바이트다 — 지우면 글자가 밀린다
            if not kotext:
                n_same += 1
                continue
            nb = encode(kotext, rev, ko)
            if len(nb) > L:
                over.append((name, off, L, len(nb), kotext))
                continue
            nb = nb + b'\x20' * (L - len(nb))
            d[o + off:o + off + L] = nb
            n_tr += 1
        open(os.path.join(DST, f), 'wb').write(bytes(d))

    print('번역 반영 %d런 / 원문 유지 %d런' % (n_tr, n_same))
    if over:
        print('★길이 초과 %d런 (반영 안 함):' % len(over))
        for name, off, L, n, t in over[:10]:
            print('   %-12s +0x%05X  %dB → %dB (+%d)  %s' % (name, off, L, n, n - L, t[:40]))

    # 불변식 4·5 검증: 런 밖은 한 바이트도 안 바뀌어야 한다
    bad = 0
    for f in sorted(os.listdir(SRC)):
        if not f.endswith('.MDT'):
            continue
        a = open(os.path.join(SRC, f), 'rb').read()
        b = open(os.path.join(DST, f), 'rb').read()
        if len(a) != len(b):
            print('★ %s 크기 변경 %d → %d' % (f, len(a), len(b)))
            bad += 1
            continue
        o, s, rs = extract(a, f[6:])
        allowed = bytearray(len(a))
        for off, L, _ in rs:
            for i in range(o + off, o + off + L):
                allowed[i] = 1
        for i in range(len(a)):
            if a[i] != b[i] and not allowed[i]:
                print('★ %s 런 밖 바이트 변경 @0x%X' % (f, i))
                bad += 1
                break
    print('런 밖 무결성: %s' % ('통과' if bad == 0 else '실패 %d' % bad))
    return 1 if (over or bad) else 0


if __name__ == '__main__':
    sys.exit(main())
