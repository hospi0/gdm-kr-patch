# -*- coding: utf-8 -*-
"""장소 배너 끝의 일본어 조사 `へ` 를 지운다 (2026-08-08).

원문은 「<장소>へ」(=…로) 형태라 배너 오른쪽 끝에 `へ` 한 글자가 따로 찍힌다.
장소명은 한글로 바꿨는데 이 조사만 남아 `군기지・입구      へ` 로 보였다.

`へ` 는 런 밖의 «홀로 선 1바이트 글자»라 번역표 경로로는 닿지 않는다.
바이트 패턴 `0A xx yy 7C 07` 의 `7C`(=へ)만 공백 `0x20` 으로 바꾼다.
  · `0A~0F` = 제어코드 + **2바이트 인수** ([[reference_gdm_text_decoder]])
  · 그래서 `0A xx yy` 다음 바이트가 첫 글자다
검증: 바꾼 바이트가 전부 0x7C 였는지 / 그 외 바이트 무변화 / 크기 불변.
"""
import os
import sys

sys.path.insert(0, 'tools')
from extract_runs import extract

SRC, DST = 'work/dm', 'work/build'


def marks(s):
    out = []
    i = 0
    while i < len(s) - 4:
        if s[i] == 0x0A and s[i + 3] == 0x7C and s[i + 4] == 0x07:
            out.append(i + 3)
        i += 1
    return out


def main():
    total = 0
    for f in sorted(os.listdir(SRC)):
        if not f.endswith('.MDT'):
            continue
        name = f[6:]
        orig = open(os.path.join(SRC, f), 'rb').read()
        base, s, rs = extract(orig, name)
        if not rs:
            continue
        p = os.path.join(DST, f)
        cur = bytearray(open(p, 'rb').read())
        hits = marks(s)
        if not hits:
            continue
        before = bytes(cur)
        for rel in hits:
            a = base + rel
            assert cur[a] == 0x7C, '%s rel 0x%X 가 へ 가 아니다 (0x%02X)' % (name, rel, cur[a])
            cur[a] = 0x20
        diff = sum(1 for i in range(len(cur)) if cur[i] != before[i])
        assert diff == len(hits), '%s 예상 %d != 실제 %d' % (name, len(hits), diff)
        assert len(cur) == len(orig)
        open(p, 'wb').write(bytes(cur))
        total += len(hits)
        print('%-10s へ 제거 %d' % (name, len(hits)))
    print('\n합계 %d곳' % total)


if __name__ == '__main__':
    main()
