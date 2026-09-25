# -*- coding: utf-8 -*-
"""예/아니오 확인 상자(`終了しますか？` / `タイトルに戻りますか？`) 번역 빌더.

## 왜 이 파일들이 따로 필요했나

이 상자는 **글자가 아니라 그림처럼 보이지만 실은 폰트 렌더**다.
VDP1 텍스처(128×48, 8bpp)의 글자 픽셀이 `BIN/FDATA.BIN` 16×16 글리프와
**픽셀 단위로 일치**하는 것을 세이브스테이트에서 확인했다(2026-08-08).
따라서 원문 문자열이 디스크에 있고, 그걸 고치면 화면이 바뀐다.

## 레코드 형식 (실측으로 확정)

    01 00 LL   ff ff ff ff   <블록 A: LL바이트>   <블록 B: LL바이트>
    블록 = 20 XX  <payload XX바이트>  f0 00        (LL == XX + 4)

payload 문법:
    <1행 텍스트> 01 <공백> 0a00c1 <예> 0a00c2 <공백> 0a00c3 <아니오> 0a00c4 07 [00]

* `01` = 줄바꿈, `07` = 끝, `0a xx yy` = 색 지정(2바이트 인수)
* `0a 00 fa` = 강조색, `0a 00 f0` = 보통색 → **블록 A는 「예」가, 블록 B는
  「아니오」가 강조**돼 있다. 그래서 같은 상자가 2벌 들어 있다.
* payload 길이가 홀수면 끝에 `00` 한 바이트를 붙여 짝수로 맞춘다.

## 예산 — 정확히 맞는다

    終了しますか？        9B → 종료할까요？        9B
    タイトルに戻りますか？ 12B → 타이틀로 돌아갈까요？ 14B  (공백 2칸→1칸으로 흡수)
    はい                2B → 예                 2B
    いいえ               3B → 아니오              3B

불변식: `XX`·`LL` 불변 / 파일 크기 불변 / 레코드 밖 무변화.
"""
import os
import shutil
import sys

sys.path.insert(0, 'tools')
from runs_build import encode, load_maps

SRC, DST = 'work/dm_all', 'work/build'

# 1행 원문 → 번역
LINE1 = {
    '終了しますか？': '종료할까요？',
    'タイトルに戻りますか？': '타이틀로 돌아갈까요？',
}
YES, NO = '예', '아니오'


def parse_block(pay):
    """payload → (1행 바이트, [색인수 4개], 예 바이트, 아니오 바이트)

    구조가 예상과 다르면 None 을 돌려준다(조용히 넘어가지 않고 호출부에서 실패시킨다).
    """
    i = 0
    while i < len(pay) and pay[i] != 0x01:
        b = pay[i]
        if 0x0A <= b <= 0x0F:
            return None                      # 1행에 제어코드가 있으면 미지원
        i += 2 if 0x10 <= b <= 0x1F else 1
    line1 = bytes(pay[:i]).strip(b'\x20')
    if i >= len(pay):
        return None
    i += 1                                   # 01 소비
    cols, runs, cur = [], [], bytearray()
    while i < len(pay):
        b = pay[i]
        if b == 0x07:
            break
        if 0x0A <= b <= 0x0F:
            cols.append(bytes(pay[i:i + 3]))
            if cur.strip(b'\x20'):
                runs.append(bytes(cur).strip(b'\x20'))
            cur = bytearray()
            i += 3
            continue
        n = 2 if 0x10 <= b <= 0x1F else 1
        cur += pay[i:i + n]
        i += n
    if cur.strip(b'\x20'):
        runs.append(bytes(cur).strip(b'\x20'))
    if len(cols) != 4 or len(runs) != 2:
        return None
    return line1, cols, runs[0], runs[1]


def build_block(XX, l1, cols, yes, no):
    base = len(l1) + 1 + 3 + len(yes) + 3 + 3 + len(no) + 3 + 1
    rem = XX - base
    if rem < 2:
        raise SystemExit('예산 부족: XX=%d 필요=%d' % (XX, base + 2))
    a = b = rem // 2
    tail = b'\x00' * (rem - a - b)
    out = (l1 + b'\x01' + b'\x20' * a + cols[0] + yes + cols[1]
           + b'\x20' * b + cols[2] + no + cols[3] + b'\x07' + tail)
    assert len(out) == XX, (len(out), XX)
    return out


def find_records(d):
    """`01 00 LL ff ff ff ff` + 2블록 구조를 전수 탐색"""
    out = []
    i = -1
    while True:
        i = d.find(b'\x01\x00', i + 1)
        if i < 0 or i + 9 > len(d):
            return out
        LL = d[i + 2]
        if d[i + 3:i + 7] != b'\xff\xff\xff\xff' or d[i + 7] != 0x20:
            continue
        XX = d[i + 8]
        if LL != XX + 4 or not (4 < XX < 0xF0) or i + 7 + 2 * LL > len(d):
            continue
        blocks = [d[i + 7 + k * LL:i + 7 + (k + 1) * LL] for k in (0, 1)]
        if any(b[0] != 0x20 or b[1] != XX or b[-2:] != b'\xf0\x00' for b in blocks):
            continue
        out.append((i, LL, XX))


def main():
    rev, ko = load_maps()
    enc = {k: encode(v, rev, ko) for k, v in LINE1.items()}
    jp = {encode(k, rev, ko): k for k in LINE1}
    kyes, kno = encode(YES, rev, ko), encode(NO, rev, ko)
    n_file = n_box = 0
    for fn in sorted(os.listdir(SRC)):
        orig = open(os.path.join(SRC, fn), 'rb').read()
        recs = [r for r in find_records(orig)
                if any(p in orig[r[0]:r[0] + 7 + 2 * r[1]] for p in jp)]
        if not recs:
            continue
        dst = os.path.join(DST, fn)
        if not os.path.exists(dst):
            shutil.copyfile(os.path.join(SRC, fn), dst)
        cur = bytearray(open(dst, 'rb').read())
        before = bytes(cur)
        touched = []
        for i, LL, XX in recs:
            for k in (0, 1):
                bo = i + 7 + k * LL
                pay = orig[bo + 2:bo + 2 + XX]
                p = parse_block(pay)
                if p is None:
                    raise SystemExit('%s 0x%05X 블록 해석 실패' % (fn, bo))
                l1, cols, yes, no = p
                if l1 not in jp:
                    raise SystemExit('%s 0x%05X 미지원 1행' % (fn, bo))
                new = build_block(XX, enc[jp[l1]], cols, kyes, kno)
                cur[bo + 2:bo + 2 + XX] = new
                touched.append((bo + 2, XX))
                n_box += 1
        mask = bytearray(len(cur))
        for a, L in touched:
            mask[a:a + L] = b'\x01' * L
        out = sum(1 for j in range(len(cur)) if not mask[j] and cur[j] != before[j])
        assert len(cur) == len(orig), '크기 변경'
        assert out == 0, '구간 밖 %d바이트 변경' % out
        open(dst, 'wb').write(bytes(cur))
        n_file += 1
        print('  %-22s 레코드 %d  블록 %d' % (fn, len(recs), 2 * len(recs)))
    print('예/아니오 상자: %d파일 %d블록 반영 (크기 불변, 구간밖변경 0)'
          % (n_file, n_box))


if __name__ == '__main__':
    main()
