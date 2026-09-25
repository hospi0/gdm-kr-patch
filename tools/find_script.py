# -*- coding: utf-8 -*-
"""화면 대사의 **폰트 코드열**로 대사 데이터를 찾는다.

폰트 색인을 알았으므로, 화면에 찍힌 글자의 코드를 그대로 이어 붙이면
대사 스트림의 실제 바이트가 된다. 1바이트 코드인지 2바이트인지도 이걸로 갈린다.

질의: 세이브스테이트 VDP2 VRAM에서 뜯은 글리프 → 폰트 표 역색인 → 코드열
형태: 1바이트 / BE16 / LE16, 그리고 공백(빈 상자) 포함·제외 두 가지
"""
import bisect
import os
import struct
import sys

sys.path.insert(0, 'tools')
import font_codec as C
import iso9660 as I

TRACK1 = (r'C:/claude/roms/ss/Grandia - Digital Museum (Japan) (Rev A) (10M)'
          r'/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin')
VRAM = 'work/state_b/VRAM_1_sw.bin'
BLIT, CB, CW, CH, NCELL = 0x8000, 64, 8, 16, 32
RAMDIR = 'work/state_b'


def screen_codes(d):
    """화면 상자 → (상자번호, 코드 또는 None)"""
    v = open(VRAM, 'rb').read()
    rows = []
    for y in range(CH):
        line = []
        for c in range(NCELL):
            base = BLIT + c * CB + y * (CW // 2)
            for x in range(CW):
                b = v[base + x // 2]
                line.append(1 if ((b >> 4) if x % 2 == 0 else (b & 15)) else 0)
        rows.append(line)

    n = C.table_count(d, C.FULL_BASE)
    idx = {}
    for code in range(n):
        r = C.raw_to_rows(C.glyph_full(d, code))
        idx.setdefault(tuple(r[:15]), code)          # 15행만 (화면 16행은 잘림)

    out = []
    for bi in range(NCELL // 2):
        r = tuple(int(''.join(str(rows[y][bi * 16 + x]) for x in range(16)), 2)
                  for y in range(15))
        out.append((bi, None if not any(r) else idx.get(r)))   # 빈 상자는 공백
    return out


def queries(codes):
    """코드열 → 검색 바이트열 여러 형태"""
    seqs = []
    # 잉크 있는 연속 구간을 잘라서 씀 (공백 코드가 뭔지 아직 모름)
    run = []
    for bi, c in codes:
        if c is None:
            if len(run) >= 3:
                seqs.append(run)
            run = []
        else:
            run.append(c)
    if len(run) >= 3:
        seqs.append(run)

    out = []
    for s in seqs:
        txt = '-'.join('%03X' % c for c in s)
        out.append(('1바이트 ' + txt, bytes(c & 0xFF for c in s)))
        out.append(('BE16    ' + txt, b''.join(struct.pack('>H', c) for c in s)))
        out.append(('LE16    ' + txt, b''.join(struct.pack('<H', c) for c in s)))
    return out


def main():
    d = open('work/dm/BIN_FDATA.BIN', 'rb').read()
    codes = screen_codes(d)
    print('화면 상자 → 코드:')
    print('  ' + ' '.join('%s' % ('%03X' % c if c is not None else '····')
                          for _, c in codes))
    qs = queries(codes)
    print('질의 %d개' % len(qs))
    for lab, q in qs:
        print('  %-40s %s' % (lab, q.hex()))
    print()

    hits = 0
    print('== RAM ==')
    for f in sorted(os.listdir(RAMDIR)):
        if not f.endswith('.bin'):
            continue
        b = open(os.path.join(RAMDIR, f), 'rb').read()
        for lab, q in qs:
            i = b.find(q)
            while i >= 0:
                print('  %-40s %s+0x%06X' % (lab, f[:-4], i))
                hits += 1
                i = b.find(q, i + 1)

    print('== 디스크 ==')
    raw = I.load_track(TRACK1)
    files = I.list_files(bytearray(raw))
    nsec = len(raw) // I.SECTOR
    data = bytearray(nsec * I.DATA_LEN)
    for s in range(nsec):
        o = s * I.SECTOR + I.DATA_OFF
        data[s * I.DATA_LEN:(s + 1) * I.DATA_LEN] = raw[o:o + I.DATA_LEN]
    data = bytes(data)
    del raw
    table = sorted(files.items(), key=lambda kv: kv[1][0])
    starts = [v[0] for _, v in table]

    def which(pos):
        lba = pos // I.DATA_LEN
        k = bisect.bisect_right(starts, lba) - 1
        if k < 0:
            return '(파일밖)', 0
        p, (fl, sz) = table[k]
        ns = (sz + I.DATA_LEN - 1) // I.DATA_LEN
        return (p, pos - fl * I.DATA_LEN) if fl <= lba < fl + ns else ('(파일밖)', 0)

    for lab, q in qs:
        i = data.find(q)
        cnt = 0
        while i >= 0 and cnt < 8:
            p, off = which(i)
            print('  %-40s %s +0x%X' % (lab, p, off))
            hits += 1
            cnt += 1
            i = data.find(q, i + 1)
    print('일치 %d건' % hits)


if __name__ == '__main__':
    main()
