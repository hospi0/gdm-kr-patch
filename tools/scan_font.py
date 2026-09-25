# -*- coding: utf-8 -*-
"""디스크 전 파일을 훑어 '글리프 시트'로 보이는 구간을 찾는다.

메모리 교훈 [[feedback_scan_coverage_and_detectors]]:
검출기는 양성·음성·고유율 3종 제약을 모두 걸어야 한다. 특히 '빈 데이터'가
만점을 받지 않게 해야 한다.

제약:
  1) 밀도  — 셀 평균 set-bit 비율이 글자다운 범위(0.12~0.55)
  2) 채움  — 셀 중 완전 공백이 아닌 비율이 충분히 높음(>=0.6)
  3) 고유율 — 서로 다른 셀의 비율이 높음(>=0.7). 같은 타일 반복은 폰트가 아니다
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iso9660 as I

TRACK1 = (r'C:/claude/roms/ss/Grandia - Digital Museum (Japan) (Rev A) (10M)'
          r'/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin')

# (이름, 셀바이트) — 1bpp 가정
CELLS = [('8x8', 8), ('8x16', 16), ('12x12', 24), ('16x16', 32), ('24x24', 72)]
BLOCK = 128          # 한 번에 평가할 셀 수
POPC = bytes(bin(i).count('1') for i in range(256))


def score_block(buf, off, cell, n=BLOCK):
    seg = buf[off:off + cell * n]
    if len(seg) < cell * n:
        return None
    bits = sum(POPC[b] for b in seg)
    dens = bits / (len(seg) * 8.0)
    cells = [bytes(seg[i * cell:(i + 1) * cell]) for i in range(n)]
    nonempty = sum(1 for c in cells if any(c)) / float(n)
    uniq = len(set(cells)) / float(n)
    if not (0.12 <= dens <= 0.55):
        return None
    if nonempty < 0.6 or uniq < 0.7:
        return None
    # 밀도가 글자다운 중앙(0.3)에 가까울수록, 고유·채움이 높을수록 좋다
    return (1 - abs(dens - 0.30) / 0.30) * uniq * nonempty


def scan_file(data, name, out, limit=4 << 20):
    if len(data) > limit:
        data = data[:limit]        # 대용량은 앞부분만(부재의 증거로 쓰지 않는다)
    best = {}
    for label, cell in CELLS:
        step = cell * 16
        b = None
        for off in range(0, max(0, len(data) - cell * BLOCK), step):
            s = score_block(data, off, cell)
            if s is not None and (b is None or s > b[0]):
                b = (s, off)
        if b:
            best[label] = b
    if best:
        for label, (s, off) in sorted(best.items(), key=lambda kv: -kv[1][0]):
            out.append((s, name, label, off, len(data)))


def main():
    buf = I.load_track(TRACK1)
    files = I.list_files(buf)
    out = []
    skip = ('GM3.STZ',)
    for path, (lba, size) in sorted(files.items()):
        if any(path.endswith(s) for s in skip) or size < 4096:
            continue
        data = I.read_range(buf, lba, min(size, 4 << 20))
        scan_file(data, path, out)
    out.sort(reverse=True)
    with open('work/scan_font.txt', 'w', encoding='utf-8') as f:
        f.write('점수  파일  셀규격  오프셋  (검사바이트)\n')
        for s, name, label, off, n in out[:80]:
            f.write('%.3f  %-28s %-6s 0x%06X  (%d)\n' % (s, name, label, off, n))
    print('후보 %d건 → work/scan_font.txt' % len(out))
    for s, name, label, off, n in out[:25]:
        print('%.3f  %-28s %-6s 0x%06X' % (s, name, label, off))


if __name__ == '__main__':
    main()
