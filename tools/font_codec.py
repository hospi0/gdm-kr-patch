# -*- coding: utf-8 -*-
"""GDM 폰트 코덱 — 디코더와 인코더를 한 곳에 둔다 (단일 출처).

코덱은 `0x0601DC00`의 SH-2 전개 루틴을 그대로 옮긴 것이다. docs/survey.md §5 참조.

레코드 = [BE32 플래그워드][델타바이트 × popcount(플래그)]
  글리프 32바이트 = 왼쪽 8px 열 16행(0~15) + 오른쪽 8px 열 16행(16~31)
  플래그를 MSB부터 소비:
    비트 1 → 델타를 하나 읽어 누산기에 XOR (그 값이 그 행의 바이트)
    비트 0 → 누산기 그대로 (윗행과 동일)
  누산기는 바이트 0과 16에서 0으로 리셋 (좌·우 열이 독립 체인)

반각은 레코드 하나에 글리프 2개(32바이트)가 들어가고 코드의 LSB로 고른다.
오프셋표는 `코드 & 0xFFFE`를 바이트 오프셋으로 써서 색인한다(= 항목당 코드 2개).

⚠️ 인코더는 디코더보다 잘 깨진다. 반드시 `font_roundtrip.py`로 전수 왕복 검증할 것.
"""
import struct

FULL_BASE = 0xA00      # 전각 16×16
HALF_BASE = 0x000      # 반각 8×16
NBYTE = 32             # 글리프 한 개의 원시 바이트 수
CHAIN = 16             # 누산기 리셋 주기 (열 하나의 행 수)


# ------------------------------------------------------------------ 디코드
def decode_record(d, rec):
    """레코드 위치 → (원시 32바이트, 레코드 총 길이)"""
    flags = struct.unpack_from('>I', d, rec)[0]
    q = rec + 4
    acc, out = 0, []
    for i in range(NBYTE):
        if i % CHAIN == 0:
            acc = 0
        if flags & (0x80000000 >> i):
            acc ^= d[q]
            q += 1
        out.append(acc)
    return bytes(out), q - rec


def encode_record(raw):
    """원시 32바이트 → 레코드 바이트열 (최소 인코딩)"""
    if len(raw) != NBYTE:
        raise ValueError('글리프는 %d바이트여야 한다 (받은 값 %d)' % (NBYTE, len(raw)))
    flags, deltas = 0, bytearray()
    acc = 0
    for i, b in enumerate(raw):
        if i % CHAIN == 0:
            acc = 0
        if b != acc:
            flags |= 0x80000000 >> i
            deltas.append(b ^ acc)
            acc = b
    return struct.pack('>I', flags) + bytes(deltas)


# ------------------------------------------------------------------ 표 접근
def table_count(d, base):
    """첫 오프셋 = 표 크기(바이트) → 항목 수"""
    return struct.unpack_from('>H', d, base)[0] // 2


def entry_offset(d, base, idx):
    return struct.unpack_from('>H', d, base + idx * 2)[0]


def glyph_full(d, code, base=FULL_BASE):
    """전각 코드 → 원시 32바이트"""
    raw, _ = decode_record(d, base + entry_offset(d, base, code))
    return raw


def glyph_half(d, code, base=HALF_BASE):
    """반각 코드 → 원시 16바이트 (레코드의 앞/뒤 절반)"""
    raw, _ = decode_record(d, base + entry_offset(d, base, code >> 1))
    return raw[CHAIN:] if (code & 1) else raw[:CHAIN]


# ------------------------------------------------------------------ 재구성
def build(records, share=False, align=1):
    """[레코드 바이트열] → (오프셋표 + 데이터) 블롭.

    원본의 배치 정책은 **공유 없음 · 빈틈 없음 · 정렬 없음**이다(실측).
    기본값은 그 정책을 그대로 재현한다.

    `share=True`는 내용이 같은 레코드를 공유해 자리를 아낀다.
    원본과 바이트가 달라지므로, 자리가 모자랄 때만 의도적으로 쓴다.
    """
    n = len(records)
    tab_size = n * 2
    blob = bytearray()
    offs, seen = [], {}
    for r in records:
        if share and r in seen:
            offs.append(seen[r])
            continue
        while len(blob) % align:
            blob.append(0)
        o = tab_size + len(blob)
        if o > 0xFFFF:
            raise ValueError('오프셋이 BE16을 넘었다 (0x%X)' % o)
        seen[r] = o
        offs.append(o)
        blob += r
    return b''.join(struct.pack('>H', o) for o in offs) + bytes(blob)


# ------------------------------------------------------------------ 픽셀 변환
def raw_to_rows(raw):
    """원시 32바이트 → 16행 × 16비트 (좌열 상위, 우열 하위)"""
    return [(raw[y] << 8) | raw[CHAIN + y] for y in range(CHAIN)]


def rows_to_raw(rows):
    """16행 × 16비트 → 원시 32바이트"""
    if len(rows) != CHAIN:
        raise ValueError('16행이어야 한다')
    return bytes([(r >> 8) & 0xFF for r in rows] + [r & 0xFF for r in rows])
