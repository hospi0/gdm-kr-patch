# -*- coding: utf-8 -*-
"""메시지 블록을 토큰열로 파싱한다 (텍스트 ↔ 제어코드 분리).

제어코드 길이표 (실측 확정, docs/survey.md §9):
  01 02 07 0B 0E → 1바이트,  그 밖의 제어코드 → 2바이트(오피코드+인수)
  0x10~0x14      → 2바이트 한자 이스케이프 (제어가 아니라 글자)

⚠️ 길이표에는 **표기 중의성**이 있다. `0F 03 0A 0C 00 21` 은
   `0F 03|0A 0C|00 21`(2+2+2) 로도 `0F 03 0A|0C 00 21`(3+3) 으로도 갈라지며
   **텍스트 경계는 같다.** 우리에게 필요한 건 경계뿐이므로 문제되지 않는다.

번역 재삽입은 제어코드를 **불투명하게 그대로 보존**한다. 의미를 몰라도 된다.
"""
CTRL_LEN = {b: 2 for b in range(0x20) if not (0x10 <= b <= 0x14)}
CTRL_LEN.update({0x01: 1, 0x02: 1, 0x05: 1, 0x06: 1, 0x07: 1, 0x09: 1,
                 0x0B: 1, 0x1A: 1, 0x0C: 3, 0x0E: 3, 0x0F: 3})

TEXT, CTRL = 'g', 'c'


def parse(blk):
    """블록 → [(TEXT, 폰트코드) | (CTRL, bytes)]

    ★ 마지막 바이트는 **항상 종결자 0x07** 이다(282개 전량 실측).
      이걸 고정하지 않으면 `10 07` 을 한자 이스케이프로 오인해 종결자를 먹는다.
    """
    out, i = [], 0
    n = len(blk) - 1                      # 마지막 종결자는 본문에서 제외
    while i < n:
        b = blk[i]
        if b >= 0x20:
            out.append((TEXT, b - 0x20))
            i += 1
        elif 0x10 <= b <= 0x14 and i + 1 < n:
            out.append((TEXT, 0xE0 + (b - 0x10) * 256 + blk[i + 1]))
            i += 2
        else:
            ln = min(CTRL_LEN.get(b, 2), n - i)
            out.append((CTRL, bytes(blk[i:i + ln])))
            i += ln
    out.append((CTRL, bytes(blk[n:])))
    return out


def emit(toks):
    """토큰열 → 바이트열 (파싱의 역연산). parse↔emit 는 반드시 왕복해야 한다."""
    out = bytearray()
    for t, v in toks:
        if t == CTRL:
            out += v
        elif v < 0xE0:
            out.append(v + 0x20)
        else:
            k = v - 0xE0
            out += bytes((0x10 + k // 256, k % 256))
    return bytes(out)
