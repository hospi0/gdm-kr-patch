# -*- coding: utf-8 -*-
"""MDT 전 파일의 대사 예산을 실측한다.

확정된 문법(docs/survey.md §7):
  메시지 블록 = `20 LL` + LL바이트 (0F… 로 시작해 07 로 끝남, LL은 짝수)
  조건부 분기 = `1000 30LL` = 이후 LL바이트를 건너뜀 (**상대**, 절대 오프셋 아님)

둘 다 길이가 **1바이트**라 상한 255다. 한글을 2바이트로 넣으면 텍스트가 늘어나므로
  (a) 메시지 블록 길이 ≤ 255
  (b) 그 메시지를 감싸는 모든 스킵 거리 ≤ 255
를 둘 다 지켜야 한다. 이 도구가 그 여유를 전 파일에서 잰다.
"""
import os
import struct
import sys

sys.path.insert(0, 'tools')
from peek_lba import read

FILELIST = 'work/filelist.txt'
DMDIR = 'work/dm'


def sections(d):
    out = []
    for i in range(64):
        if (i + 1) * 8 > len(d):
            break
        a, b = struct.unpack_from('>II', d, i * 8)
        if a == 0 and b == 0:
            break
        if (a >> 24) == 0xFF or b == 0 or b > len(d):
            continue
        o = a & 0xFFFFFF
        if o + b <= len(d):
            out.append((o, b))
    return out


def scan_messages(s):
    """순차 스캔으로 `20 LL` 메시지 블록을 찾는다"""
    ln = len(s)
    out, p = [], 0
    while p < ln - 4:
        if s[p] == 0x20 and p % 2 == 0:
            L = s[p + 1]
            if (L >= 6 and L % 2 == 0 and p + 2 + L <= ln
                    and s[p + 2] < 0x20 and s[p + 2 + L - 1] == 0x07):
                out.append((p, L))
                p += 2 + L
                continue
        p += 2
    return out


def scan_skips(s):
    ln = len(s)
    out = []
    for p in range(0, ln - 4, 2):
        if struct.unpack_from('>H', s, p)[0] != 0x1000:
            continue
        v = struct.unpack_from('>H', s, p + 2)[0]
        if (v >> 8) == 0x30:
            LL = v & 0xFF
            out.append((p, p + 4, p + 4 + LL, LL))
    return out


def script_section(d):
    """메시지 블록이 가장 많이 잡히는 섹션 = 스크립트"""
    best = None
    for o, b in sections(d):
        m = scan_messages(d[o:o + b])
        if best is None or len(m) > len(best[2]):
            best = (o, b, m)
    return best


def main():
    ratio = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
    rows = []
    for line in open(FILELIST, encoding='cp949', errors='replace'):
        if '.MDT' not in line:
            continue
        parts = line.split()
        name = parts[0].rsplit('/', 1)[-1]
        lba = int(parts[1].split('=')[1])
        size = int(parts[2].split('=')[1])
        path = os.path.join(DMDIR, 'FIELD_' + name)
        if not os.path.exists(path):
            open(path, 'wb').write(read(lba, size))
        d = open(path, 'rb').read()
        o, b, msgs = script_section(d)
        s = d[o:o + b]
        skips = scan_skips(s)
        chars = 0
        mx_blk = mx_skp = 0
        over_blk = over_skp = 0
        for bp, L in msgs:
            txt = s[bp + 2:bp + 2 + L]
            g = sum(1 for x in txt if x >= 0x20)
            chars += g
            c = L - g
            nl = c + int(round(g * ratio)) * 2
            nl += nl % 2
            mx_blk = max(mx_blk, nl)
            if nl > 255:
                over_blk += 1
            delta = nl - L
            for sp, st, en, LL in skips:
                if st <= bp and bp + 2 + L <= en:
                    v = LL + delta
                    mx_skp = max(mx_skp, v)
                    if v > 255:
                        over_skp += 1
        rows.append((name, b, len(msgs), chars, mx_blk, over_blk, mx_skp, over_skp))

    print('한글 글자수 비율 %.2f, 2바이트 인코딩 가정' % ratio)
    print('%-10s %-9s %-7s %-8s %-9s %-8s %-9s %s'
          % ('파일', '스크립트B', '메시지', '글자', '최대블록', '초과', '최대스킵', '초과'))
    tm = tc = 0
    ob = os_ = 0
    for r in rows:
        tm += r[2]
        tc += r[3]
        ob += r[5]
        os_ += r[7]
        print('%-10s %-9d %-7d %-8d %-9d %-8d %-9d %d' % r)
    print('-' * 72)
    print('합계: 메시지 %d개, 글자 %d자, 블록 초과 %d, 스킵 초과 %d'
          % (tm, tc, ob, os_))


if __name__ == '__main__':
    main()
