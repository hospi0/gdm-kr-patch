# -*- coding: utf-8 -*-
"""패치된 파일들을 Track 1 사본에 써넣고 xdelta 패치를 만든다.

⚠️ **원본은 절대 건드리지 않는다.** 원본을 출력 경로로 복사한 뒤 그 사본만 고친다.
⚠️ MODE1/2352 는 섹터마다 EDC(4B)+ECC(276B) 가 있다.
   **재계산하지 않으면 에뮬레이터가 섹터를 읽을 때 내용과 무관하게 크래시한다**
   (silmirage-kr-patch `cdrom_ecc.py` 의 실측 교훈).

`work/build/` 안의 `<DIR>_<NAME>` 파일을 ISO 경로 `/DIR/NAME` 으로 되돌려 써넣는다.
크기가 원본과 같으면 제자리 교체. ★2026-10-16 확장:
  · 원본보다 «커진» 파일 → 트랙 끝에 새 섹터(동기·MSF 머리·EDC/ECC)로 붙이고 디렉터리 기록(LBA·크기, LE/BE)과
    PVD 볼륨 크기를 고친다(드라마 자막 블롭을 실은 E804.MDT). 원래 자리 섹터는 그대로 둔다.
  · `SYS_IP.BIN`(32 KB) → 시스템 영역 LBA 0‥15(IP.BIN — 드라마 자막 부트스트랩).
"""
import os
import shutil
import struct
import subprocess
import sys

sys.path.insert(0, 'tools')
import cdrom_ecc
import iso9660 as I

# ★무수정 원본. 2026-08-08에 C:/claude/roms/ss/… 사본이 사라져 F드라이브 하위
#   폴더의 사본으로 옮겼다. 이 파일은 `work/dm` 103개와 바이트 전량 일치를 확인한
#   진짜 원본이다 — **절대 여기에 빌드 결과를 쓰지 말 것**(아래 assert 로 방어).
# 2026-10-16: 원본이 다시 C:/claude/roms/ss/ 바로 아래로 옮겨짐(md5 59b19105… 같음).
# 2026-10-14: F: 이중 폴더 사본이 사라져 사용자가 C:/claude/roms/ss/완료/… 에 원본을 둠(md5 59b19105…,
#   `work/dm` 104개와 바이트 일치 확인). ⚠️`work/dm_all` 의 글 파일 76개는 패치 ISO 에서 뽑힌 것이라 원본 판정에 쓰지 말 것.
SRC = (r'C:/claude/roms/ss/Grandia - Digital Museum (Japan) (Rev A) (10M)'
       r'/Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin')
DSTDIR = (r'F:/hospi/roms/ss roms/Grandia - Digital Museum (Japan) (Rev A) (10M)')
DSTNAME = 'Grandia - Digital Museum (Japan) (Rev A) (10M) (Track 1).bin'
XDELTA = r'C:/claude/utils/xdelta.exe'
BUILD = 'work/build'


def iso_path(fname):
    """`FIELD_E800.MDT` → `/FIELD/E800.MDT`"""
    d, n = fname.split('_', 1)
    return '/%s/%s' % (d, n)


def find_record(f, path):
    """ISO 경로 → 그 디렉터리 기록의 트랙 파일 절대 오프셋(기록은 섹터를 넘지 않는다)"""
    def rd(lba, size):
        out = []
        for k in range((size + 2047) // 2048):
            f.seek((lba + k) * I.SECTOR + I.DATA_OFF); out.append(((lba + k), f.read(2048)))
        return out
    f.seek(16 * I.SECTOR + I.DATA_OFF); pvd = f.read(2048)
    lba, size = struct.unpack_from('<I', pvd, 156 + 2)[0], struct.unpack_from('<I', pvd, 156 + 10)[0]
    parts = [x for x in path.strip('/').split('/')]
    for depth, name in enumerate(parts):
        last = depth == len(parts) - 1
        hit = None
        for slba, sec in rd(lba, size):
            pos = 0
            while pos < 2048 and sec[pos]:
                rl = sec[pos]; nl = sec[pos + 32]
                nm = sec[pos + 33:pos + 33 + nl].decode('ascii', 'replace').split(';')[0]
                if nm == name:
                    hit = (slba, pos, struct.unpack_from('<I', sec, pos + 2)[0], struct.unpack_from('<I', sec, pos + 10)[0])
                    break
                pos += rl
            if hit:
                break
        if not hit:
            raise SystemExit('디렉터리 기록 없음: %s' % path)
        if last:
            return hit[0] * I.SECTOR + I.DATA_OFF + hit[1]
        lba, size = hit[2], hit[3]


def main():
    global SRC
    # --src 경로 = 바탕 트랙 바꾸기(2026-10-14 무수정 원본이 사라져 예전 패치판 사본으로 설치 확인용 빌드).
    #   이때는 «원본과 같으면 건너뜀»을 끄고(바탕에 예전 패치가 남지 않게) xdelta 는 안 만든다(배포는 무수정 원본 기준이어야 함).
    other_src = '--src' in sys.argv
    if other_src:
        SRC = sys.argv[sys.argv.index('--src') + 1]
    dst = os.path.join(DSTDIR, DSTNAME)
    files = [f for f in sorted(os.listdir(BUILD))
             if '_' in f and not f.endswith('.bin.tmp')]
    if not files:
        raise SystemExit('work/build 에 써넣을 파일이 없다')

    # 파일표는 이미 뽑아 둔 filelist.txt 를 쓴다 (455 MB 를 다시 안 읽는다)
    table = {}
    for line in open('work/filelist.txt', encoding='cp949', errors='replace'):
        if 'lba=' not in line:
            continue
        a = line.split()
        if 'DIR' in a:              # 디렉터리 줄은 건너뛴다
            continue
        lba = size = None
        for t in a[1:]:
            if t.startswith('lba='):
                lba = int(t[4:])
            elif t.startswith('size='):
                size = int(t[5:])
        if lba is not None and size is not None:
            table[a[0]] = (lba, size)

    plan = []
    grown = []
    sysip = None
    for f in files:
        if f == 'SYS_IP.BIN':
            sysip = open(os.path.join(BUILD, f), 'rb').read()
            assert len(sysip) == 16 * 2048
            continue
        p = iso_path(f)
        if p not in table:
            print('  건너뜀 %s (ISO에 없음)' % f)
            continue
        data = open(os.path.join(BUILD, f), 'rb').read()
        orig = os.path.join('work/dm', f)
        if not other_src and os.path.exists(orig) and open(orig, 'rb').read() == data:
            continue                       # 원본과 같으면 쓸 필요 없다
        lba, size = table[p]
        if len(data) > size:
            grown.append((p, data)); continue
        if len(data) != size:
            raise SystemExit('%s: 크기 %d < 원본 %d — 줄어든 파일은 지원 안 함'
                             % (p, len(data), size))
        plan.append((p, lba, size, data))
    if not plan and not grown and sysip is None:
        raise SystemExit('써넣을 대상이 없다')
    for p, lba, size, _ in plan:
        print('  %-22s LBA %-7d %d B' % (p, lba, size))

    print('원본 복사 중 (455 MB)…', flush=True)
    os.makedirs(DSTDIR, exist_ok=True)
    assert os.path.abspath(dst) != os.path.abspath(SRC),         '★SRC 에 덮어쓰기 시도 — 무수정 원본이 날아간다'
    shutil.copyfile(SRC, dst)

    ranges = []
    with open(dst, 'r+b') as f:
        for p, lba, size, data in plan:
            off = 0
            s = lba
            while off < size:
                n = min(I.DATA_LEN, size - off)
                pos = s * I.SECTOR + I.DATA_OFF
                f.seek(pos)
                f.write(data[off:off + n])
                ranges.append((pos, n))
                off += n
                s += 1
        if sysip is not None:                           # IP.BIN = 시스템 영역 LBA 0‥15
            for k in range(16):
                pos = k * I.SECTOR + I.DATA_OFF
                f.seek(pos); f.write(sysip[k * 2048:(k + 1) * 2048]); ranges.append((pos, 2048))
            plan.append(('(IP.BIN)', 0, len(sysip), sysip))
            print('  %-22s LBA 0‥15' % '(IP.BIN 시스템 영역)')
        for p, data in grown:                            # 커진 파일 → 트랙 끝으로
            f.seek(0, 2)
            lba = f.tell() // I.SECTOR
            n = (len(data) + 2047) // 2048
            for k in range(n):
                fad = lba + k + 150
                m, sec, fr = fad // 4500, fad // 75 % 60, fad % 75
                bcd = lambda v: (v // 10) << 4 | v % 10
                hdr = b'\x00' + b'\xff' * 10 + b'\x00' + bytes((bcd(m), bcd(sec), bcd(fr), 1))
                chunk = data[k * 2048:(k + 1) * 2048]
                f.write(hdr + chunk + bytes(2048 - len(chunk)) + bytes(288))
                ranges.append(((lba + k) * I.SECTOR + I.DATA_OFF, 2048))
            rpos = find_record(f, p)
            f.seek(rpos + 2); f.write(struct.pack('<I', lba) + struct.pack('>I', lba)
                                      + struct.pack('<I', len(data)) + struct.pack('>I', len(data)))
            ranges.append((rpos, 18))
            total = f.seek(0, 2) // I.SECTOR
            pvd = 16 * I.SECTOR + I.DATA_OFF
            f.seek(pvd + 80); f.write(struct.pack('<I', total) + struct.pack('>I', total))
            ranges.append((pvd + 80, 8))
            plan.append((p, lba, len(data), data))
            print('  %-22s → 트랙 끝 LBA %d (%d B, 원래 자리 그대로 둠)' % (p, lba, len(data)))
        print('EDC/ECC 재계산 중…', flush=True)
        ns = cdrom_ecc.fix_sectors(f, ranges)
    print('  섹터 %d개 재계산' % ns)

    # 검증: 다시 읽어 일치하는지
    print('검증 중…', flush=True)
    bad = 0
    with open(dst, 'rb') as f:
        for p, lba, size, data in plan:
            got = bytearray()
            s2 = lba
            while len(got) < size:
                f.seek(s2 * I.SECTOR + I.DATA_OFF)
                got += f.read(I.DATA_LEN)
                s2 += 1
            if bytes(got[:size]) != data:
                print('  ★ %s 되읽기 불일치' % p)
                bad += 1
    print('  되읽기 %d/%d 일치' % (len(plan) - bad, len(plan)))
    if bad:
        raise SystemExit('검증 실패')

    print('%s' % dst)
    if other_src:
        print('★--src 바탕 → xdelta 안 만듦(배포 패치는 무수정 원본 기준)')
    elif os.path.exists(XDELTA):
        out = 'work/gdm_kr.xdelta'
        r = subprocess.run([XDELTA, '-f', '-s', SRC, dst, out],
                           capture_output=True)
        if r.returncode == 0:
            print('%s  %d B' % (out, os.path.getsize(out)))
        else:
            print('xdelta 실패: %s' % r.stderr.decode('cp949', 'replace')[:200])


if __name__ == '__main__':
    main()
