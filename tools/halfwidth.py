# -*- coding: utf-8 -*-
"""반각(8×16) 글리프표 — **글리프 렌더로 전수 식별 완료** (2026-08-07).

기존 `work/trans/halfwidth_map.json` 은 개수-대응 다수결로 유도한 70항목짜리
부분표라 대부분이 `?` 로 나왔다. 반각 글리프 128레코드(=256글리프)를 직접 렌더해
(`work/half_sheet.png`) 전수 식별했다.

**인코딩 규칙(전각과 동일)**: 문자열 바이트 `b` → 글리프 인덱스 `b - 0x20`.
  · 인덱스 0x00~0x5F = ASCII 0x20~0x7F  (0x00=공백, 0x01='!' … 0x1A='ｚ')
  · 인덱스 0x60~0xC0 = 가타카나·기호

검증: `カートリッジRAM` = `8a d5 a7 c9 a2 97 52 41 4d`
      → 인덱스 6A B5 87 A9 82 77 32 21 2D → カ ー ト リ ッ ジ R A M ✓
"""

# 인덱스 0x60 부터의 가타카나·기호 (렌더 시트에서 직독)
_KANA = (
    'ァアィイゥウェエォオカガキギクグ'      # 60-6F
    'ケゲコゴサザシジスズセゼソゾタダ'      # 70-7F
    'チヂッツヅテデトドナニヌネノハバ'      # 80-8F
    'パヒビピフブプヘベペホボポマミム'      # 90-9F
    'メモャヤュユョヨラリルレロヮワヲ'      # A0-AF
    'ンヴヵヶ・ー～…○♩♪♬♥§M◆'         # B0-BF
    '★'                                    # C0
)

IDX2CH = {}
for _i in range(0x60):                      # ASCII 구간
    IDX2CH[_i] = chr(0x20 + _i)
for _k, _c in enumerate(_KANA):
    IDX2CH[0x60 + _k] = _c

CH2IDX = {}
for _i, _c in sorted(IDX2CH.items()):
    CH2IDX.setdefault(_c, _i)


def decode(bs):
    """반각 바이트열 → 문자열 (바이트 − 0x20 = 인덱스)."""
    out = []
    for b in bs:
        out.append(IDX2CH.get(b - 0x20, '?') if b >= 0x20 else '.')
    return ''.join(out)


def encode(s):
    """문자열 → 반각 바이트열. 표에 없는 글자는 KeyError."""
    return bytes(CH2IDX[c] + 0x20 for c in s)


def encodable(s):
    return all(c in CH2IDX for c in s)
