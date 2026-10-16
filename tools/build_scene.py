# -*- coding: utf-8 -*-
"""명장면 목록(「あの名シーンをもう一度」)을 한글로 재인코딩해 `FIELD/SVRDT.DAT` 에 넣는다.

## 배경 — 왜 여기 있나

이 텍스트는 디스크에 **평문으로 없다**(여러 세션 헛돌았다). 실기 쓰기 워치포인트로
`0x002E40A0` 을 채우는 루프(`0x06015E5A`)를 잡아 역어셈블한 결과 **비트 트리 허프만**
이었고, 리필 명령 `MOV.L @R13+, R11` 의 `R13` 을 따라가 원본이 `FIELD/SVRDT.DAT`
(RAM `0x00210000` 에 통째 적재, 전체 바이트 일치)임을 확정했다. → `tools/huff.py`

## 스플라이스 — 시작점을 몰라도 되는 이유

허프만은 자기동기화라 스트림 시작점을 정적으로 특정할 수 없다. 그래서
**첫 변경 심볼 앞의 비트를 원본 그대로 두고 그 뒤만 새로 인코딩**한다.
게임이 어느 비트에서 시작하든 앞부분 해독 결과가 같으므로 안전하다.

## 불변식

* 트리는 실행 바이너리 안이라 **바꿀 수 없다** — 기존 코드로만 인코딩한다.
  트리에 리프가 없는 바이트가 하나라도 나오면 **중단**한다
  (`kocodes` 교환으로 미리 해소해 둠 → `work/trans/kocodes_swap.json`).
* 스트림은 파일 끝까지라 **크기 불변**, 남는 자리는 0 비트로 채운다.
* 문자열 개수·널 경계는 원본과 같아야 한다(렌더러가 널을 세어 N번째를 찾는다).
"""
import json
import os
import struct
import sys

sys.path.insert(0, 'tools')
import bintext as B
from runs_build import load_maps

_, KO = load_maps()

SRC, DST = 'work/dm_all', 'work/build'
FN = 'FIELD_SVRDT.DAT'
START = 0x6A0D                 # 해독 가능한 시작점(앞부분은 원본 비트 그대로 보존)
STATE_H = 'work/museum_state/WorkRAMH.bin'
TREE_BASE, ROOT, THR = 0x28800, 0xE00, 0x800
TEXT_MARK = 'work/trans/scene_text.bin'      # RAM 0x2E40A0~0x2E4A48 원본 텍스트
TABLE = 'work/trans/scene_ko.json'
CODES = 'work/trans/huff_tree.json'


def decode_all(H, stream, pos):
    """(출력, 심볼별 비트길이) — 스플라이스 지점을 비트로 재려면 길이가 필요하다."""
    node, mask = ROOT, 0x80000000
    buf = struct.unpack_from('>I', stream, pos)[0]
    pos += 4
    out, lens, cur = bytearray(), [], 0
    while pos <= len(stream):
        v = struct.unpack_from('>H', H, TREE_BASE + node + (6 if (buf & mask) else 4))[0]
        cur += 1
        mask = ((mask >> 1) | ((mask & 1) << 31)) & 0xFFFFFFFF
        if mask == 0x80000000:
            if pos + 4 > len(stream):
                break
            buf = struct.unpack_from('>I', stream, pos)[0]
            pos += 4
        if v > THR:
            node = v
            continue
        if v == THR:
            break
        out.append((v >> 3) & 0xFF)
        lens.append(cur)
        cur = 0
        node = ROOT
    return bytes(out), lens


def main():
    H = open(STATE_H, 'rb').read()
    orig = open(os.path.join(SRC, FN), 'rb').read()
    codes = {int(k): v for k, v in json.load(open(CODES))['codes'].items()}
    term = json.load(open(CODES))['term']

    out, lens = decode_all(H, orig, START)
    text = open(TEXT_MARK, 'rb').read()
    k = out.find(text[:32])
    if k < 0:
        raise SystemExit('★해독 결과에서 텍스트 시작을 못 찾았다')
    head_bits = sum(lens[:k])
    print('해독 %d심볼 / 텍스트 시작 심볼 %d (앞 %d비트 보존)' % (len(out), k, head_bits))

    # ── 새 텍스트 조립 (문자열 개수·널 경계 유지) ──
    tr = json.load(open(TABLE, encoding='utf-8'))
    rows, cur = [], bytearray()
    for b in text:
        if b == 0:
            rows.append(B.decode(bytes(cur)))
            cur = bytearray()
        else:
            cur.append(b)
    # ★표시폭까지 «공백»으로 채운다 — 이 화면은 상자를 지우지 않고 덮어쓴다.
    #   짧게 쓰면 앞 항목의 꼬리가 그대로 남는다(실기: 「도착합니다물론이지！ 을거」).
    body = bytearray()
    wide = 0
    for s in rows:
        from punct import squeeze      # 공백 삭제를 «채우기 전»에 — 인코더에서 빠지면 폭이 모자라 잔상(2026-10-14)
        ko = squeeze(tr.get(s.rstrip(), s.rstrip()))
        if len(ko) > len(s):
            wide += 1
            print('  ★폭 초과 %d>%d : %s' % (len(ko), len(s), ko))
        else:
            ko += ' ' * (len(s) - len(ko))
        body += B.encode_with_vars(ko, KO) + b'\x00'
    if wide:
        raise SystemExit('★표시폭을 넘는 번역 %d건 — 줄여야 잔상이 안 남는다' % wide)
    print('문자열 %d건 → 새 텍스트 %d B (원본 %d B)' % (len(rows), len(body), len(text)))

    bad = sorted({b for b in body if b not in codes})
    if bad:
        raise SystemExit('★트리에 리프가 없는 바이트 %s — kocodes 교환이 필요하다'
                         % ' '.join('%02X' % b for b in bad))

    # ── 비트 스플라이스 ──
    region = orig[START:]
    allbits = ''.join(format(b, '08b') for b in region)
    bits = allbits[:head_bits] + ''.join(codes[b] for b in body) + term
    cap = len(region) * 8
    print('새 비트 %d / 자리 %d (%.1f%%, 여유 %d비트)'
          % (len(bits), cap, 100.0 * len(bits) / cap, cap - len(bits)))
    if len(bits) > cap:
        raise SystemExit('★자리 초과')
    bits += '0' * (cap - len(bits))

    new = bytearray(orig)
    for i in range(len(region)):
        new[START + i] = int(bits[i * 8:(i + 1) * 8], 2)
    assert len(new) == len(orig), '크기가 바뀌었다'

    # ── 되읽기: 다시 해독해 새 텍스트가 나오는지 ──
    chk, _ = decode_all(H, bytes(new), START)
    j = chk.find(bytes(body[:32]))
    ok = j >= 0 and chk[j:j + len(body)] == bytes(body)
    print('되읽기 검증: %s (텍스트 시작 심볼 %d)' % ('일치 ✅' if ok else '★불일치', j))
    if not ok:
        raise SystemExit('되읽기 실패 — 넣지 않는다')
    head_ok = chk[:k] == out[:k]
    print('앞부분 보존 검증: %s' % ('일치 ✅' if head_ok else '★깨짐'))
    if not head_ok:
        raise SystemExit('앞부분이 바뀌었다 — 넣지 않는다')

    os.makedirs(DST, exist_ok=True)
    open(os.path.join(DST, FN), 'wb').write(bytes(new))
    print('%s 갱신  크기 %d (원본 %d)' % (FN, len(new), len(orig)))


if __name__ == '__main__':
    main()
