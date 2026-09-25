# -*- coding: utf-8 -*-
"""MODE1/2352 raw CD 트랙에서 ISO9660 파일시스템을 읽는다 (재귀 디렉터리 지원).

silmirage-kr-patch/tools/iso9660.py 에서 출발했으나, Grandia Digital Museum은
루트에 서브디렉터리가 있을 수 있으므로 재귀 탐색과 경로 기반 접근을 추가했다.

MODE1/2352 주의: 2048B 데이터 사이에 304B(EDC/ECC + 다음 섹터 sync/header)가
끼어 있다. 통짜 슬라이스로 대입하면 뒤 섹터를 밀어 파일 전체가 깨진다.
"""
import struct

SECTOR = 2352
DATA_OFF = 16      # sync(12) + header(4)
DATA_LEN = 2048


def read_sector_data(buf, lba):
    off = lba * SECTOR + DATA_OFF
    return buf[off:off + DATA_LEN]


def read_range(buf, lba, length):
    """LBA부터 length 바이트를 논리적으로(섹터 사이 여백을 건너뛰며) 읽는다.

    ⚠️ 트랙 끝을 넘는 LBA를 막지 않으면 무한루프가 된다.
    이 디스크의 `/CDDA1`은 LBA 193770인데 Track 1은 193,620섹터뿐이다
    (ISO 디렉터리가 오디오 트랙 영역을 가리킨다). 그러면 빈 슬라이스가
    계속 더해지며 루프가 끝나지 않는다. 짧게 읽히면 즉시 중단한다.
    """
    out = bytearray()
    while len(out) < length:
        chunk = read_sector_data(buf, lba)
        if not chunk:
            break                      # 트랙 끝을 넘었다
        out += chunk
        lba += 1
        if len(chunk) < DATA_LEN:
            break
    return bytes(out[:length])


def _parse_dir_records(data):
    """디렉터리 익스텐트 바이트열 → [(name, lba, size, is_dir)]"""
    out = []
    pos = 0
    while pos < len(data):
        if pos >= len(data):
            break
        rec_len = data[pos]
        if rec_len == 0:
            pos = (pos // DATA_LEN + 1) * DATA_LEN
            continue
        rec = data[pos:pos + rec_len]
        if len(rec) < 33:
            break
        lba = struct.unpack_from('<I', rec, 2)[0]
        size = struct.unpack_from('<I', rec, 10)[0]
        flags = rec[25]
        name_len = rec[32]
        raw = rec[33:33 + name_len]
        if name_len == 1 and raw in (b'\x00', b'\x01'):
            name = {b'\x00': '.', b'\x01': '..'}[raw]
        else:
            name = raw.decode('ascii', 'replace')
        out.append((name, lba, size, bool(flags & 0x02)))
        pos += rec_len
    return out


def root_extent(buf):
    pvd = read_sector_data(buf, 16)
    assert pvd[1:6] == b'CD001', 'PVD가 LBA16에 없음 — MODE1/2352가 맞는지 확인'
    root_rec = pvd[156:156 + 34]
    return struct.unpack_from('<I', root_rec, 2)[0], struct.unpack_from('<I', root_rec, 10)[0]


def walk(buf):
    """전체 파일시스템을 재귀 탐색 → [(path, lba, size, is_dir)] (경로는 '/DIR/NAME')"""
    out = []
    lba, size = root_extent(buf)
    stack = [('', lba, size)]
    seen = set()
    while stack:
        prefix, dlba, dsize = stack.pop(0)
        if (dlba, dsize) in seen:
            continue
        seen.add((dlba, dsize))
        data = read_range(buf, dlba, dsize)
        for name, flba, fsize, is_dir in _parse_dir_records(data):
            if name in ('.', '..'):
                continue
            clean = name.split(';')[0]
            path = prefix + '/' + clean
            out.append((path, flba, fsize, is_dir))
            if is_dir:
                stack.append((path, flba, fsize))
    return out


def list_files(buf):
    """{경로: (lba, size)} — 디렉터리 제외"""
    return {p: (l, s) for p, l, s, d in walk(buf) if not d}


def read_file(buf, path):
    lba, size = list_files(buf)[path]
    return read_range(buf, lba, size)


def load_track(path):
    with open(path, 'rb') as f:
        return bytearray(f.read())


if __name__ == '__main__':
    import sys
    buf = load_track(sys.argv[1])
    tot = 0
    for p, lba, size, is_dir in walk(buf):
        print('%-40s %-4s lba=%-8d size=%d' % (p, 'DIR' if is_dir else '', lba, size))
        if not is_dir:
            tot += size
    print('---- 파일 합계 %d B' % tot)
