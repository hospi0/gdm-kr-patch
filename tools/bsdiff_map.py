# -*- coding: utf-8 -*-
"""영문패치의 `_DFR`(BSDIFF40) 항목을 풀어 '새 파일에서 실제로 바뀐 구간'을 뽑는다.

BSDIFF40 레이아웃:
    0  "BSDIFF40"
    8  ctrl 블록(bzip2) 길이   — offtin 8바이트(최상위 비트가 부호)
   16  diff 블록(bzip2) 길이
   24  새 파일 크기
   32  ctrl(bzip2) | diff(bzip2) | extra(bzip2)

ctrl 항목 = (x, y, z) 3개의 offtin:
    new[pos..pos+x) = old[oldpos..oldpos+x) + diff[..x)   ← diff 바이트가 0이 아니면 '변경'
    new[pos+x..pos+x+y) = extra[..y)                      ← 통째로 '새 데이터'
    oldpos += z

원본(일본판 Grandia)이 없어도 diff의 비영 구간과 extra 구간만으로
'무엇이 바뀌었는지'의 위치 지도를 만들 수 있다.
"""
import bz2
import struct
import sys
import zipfile

BS = chr(92)


def offtin(b):
    v = struct.unpack('<Q', b)[0]
    if v & (1 << 63):
        return -(v & ~(1 << 63))
    return v


def parse(data):
    assert data[:8] == b'BSDIFF40', 'BSDIFF40 아님'
    clen = offtin(data[8:16])
    dlen = offtin(data[16:24])
    newsize = offtin(data[24:32])
    p = 32
    ctrl = bz2.decompress(data[p:p + clen]); p += clen
    diff = bz2.decompress(data[p:p + dlen]); p += dlen
    extra = bz2.decompress(data[p:])
    return ctrl, diff, extra, newsize


def changed_runs(ctrl, diff, extra, newsize, merge_gap=64):
    """새 파일 기준 변경 구간 [(start, end, kind)] kind='D'(델타) 또는 'X'(신규)"""
    runs = []
    pos = dp = xp = 0
    for i in range(0, len(ctrl), 24):
        x = offtin(ctrl[i:i + 8])
        y = offtin(ctrl[i + 8:i + 16])
        # z = offtin(ctrl[i+16:i+24])  — old 쪽 이동, 여기선 불필요
        seg = diff[dp:dp + x]
        s = None
        for k, v in enumerate(seg):
            if v:
                if s is None:
                    s = k
            elif s is not None:
                runs.append((pos + s, pos + k, 'D'))
                s = None
        if s is not None:
            runs.append((pos + s, pos + x, 'D'))
        dp += x
        pos += x
        if y:
            runs.append((pos, pos + y, 'X'))
            xp += y
            pos += y
    # 가까운 구간 병합
    out = []
    for s, e, k in runs:
        if out and s - out[-1][1] <= merge_gap:
            out[-1] = (out[-1][0], e, out[-1][2] if out[-1][2] == k else 'DX')
        else:
            out.append((s, e, k))
    return out


def main(ssp, only=None, top=40):
    z = zipfile.ZipFile(ssp)
    rows = []
    for n in z.namelist():
        if not n.endswith('._DFR'):
            continue
        path = n.replace(BS, '/')[:-5]
        if only and only not in path:
            continue
        try:
            ctrl, diff, extra, newsize = parse(z.read(n))
        except Exception as ex:
            print('  ! %s: %s' % (path, ex))
            continue
        runs = changed_runs(ctrl, diff, extra, newsize)
        total = sum(e - s for s, e, _ in runs)
        rows.append((total, path, newsize, runs))
    rows.sort(reverse=True)
    print('%-26s %-10s %-9s %s' % ('파일', '새크기', '변경합계', '구간수'))
    for total, path, newsize, runs in rows[:top]:
        print('%-26s %-10d %-9d %d' % (path, newsize, total, len(runs)))
        for s, e, k in runs[:5]:
            print('      %s 0x%06X-0x%06X (%d B)' % (k, s, e, e - s))
        if len(runs) > 5:
            print('      … 외 %d 구간' % (len(runs) - 5))
    return rows


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
