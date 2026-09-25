# -*- coding: utf-8 -*-
"""추출 **완전성**을 검증한다.

세션 2에서 겪은 사고: 메시지 스캐너가 "블록이 제어코드(<0x20)로 시작해야 한다"는
조건을 걸어 **텍스트로 시작하는 메시지 190개를 통째로 놓쳤다.**
그런데 재삽입 검증(verify_build)은 "추출된 것이 의도대로 들어갔는가"만 봤기 때문에
282/282 통과가 나왔고, 누락은 실기 화면에서야 드러났다.

그래서 이 도구는 **추출된 메시지 말고 나머지**를 본다:

  1. 스크립트 섹션에서 메시지 블록이 차지하지 않는 구간(=코드 영역)에
     **일본어 텍스트가 남아 있으면 안 된다.** 남아 있으면 그게 놓친 메시지다.
  2. 메시지 블록끼리 겹치면 안 되고, 블록 헤더(`20 LL`)와 종결자(`07`)가 성립해야 한다.
"""
import os
import sys

sys.path.insert(0, 'tools')
import codemap
from codemap_kanji_src import kanji_map
from script_budget import script_section

m = codemap.base_map()
m.update(kanji_map())
KANA = set(codemap.HIRA + codemap.KATA)


def scan(s, strict=False):
    """메시지 블록 순차 스캔.

    ★ 세션2에서 두 번 틀렸던 규칙이다. 확정판:
      - `20 LL` 로 시작, LL 은 **짝수**
      - 내용 길이가 짝수면 마지막 바이트가 종결자 `0x07`
      - 내용 길이가 **홀수면 종결자 뒤에 1바이트 패딩**이 붙어 LL 이 짝수가 된다
        → 종결자가 `LL-2` 위치에 온다
      옛 조건(블록이 제어코드로 시작)은 **텍스트로 시작하는 메시지를 놓쳤다.**
    """
    ln = len(s)
    out, p = [], 0
    while p < ln - 4:
        if s[p] == 0x20 and p % 2 == 0:
            L = s[p + 1]
            if L >= 6 and L % 2 == 0 and p + 2 + L <= ln:
                term = (s[p + 2 + L - 1] == 0x07 or s[p + 2 + L - 2] == 0x07)
                if term and (not strict or s[p + 2] < 0x20):
                    out.append((p, s[p + 2:p + 2 + L]))
                    p += 2 + L
                    continue
        p += 2
    return out


def jp_runs(s, covered, minlen=4):
    """메시지 밖 구간에서 '일본어로 읽히는 연속 런'을 찾는다."""
    runs, cur, start = [], [], None
    for i, b in enumerate(s):
        inside = covered[i]
        ch = m.get(b - 0x20) if (not inside and b >= 0x20) else None
        if ch and (ch in KANA or 0x4E00 <= ord(ch) <= 0x9FFF):
            if start is None:
                start = i
            cur.append(ch)
        else:
            if start is not None and len(cur) >= minlen:
                runs.append((start, ''.join(cur)))
            cur, start = [], None
    if start is not None and len(cur) >= minlen:
        runs.append((start, ''.join(cur)))
    return runs


def main():
    strict = '--strict' in sys.argv
    total_msg = total_run = 0
    for f in sorted(os.listdir('work/dm')):
        if not f.endswith('.MDT'):
            continue
        d = open('work/dm/' + f, 'rb').read()
        o, b, _ = script_section(d)
        s = d[o:o + b]
        msgs = scan(s, strict=strict)
        covered = bytearray(len(s))
        for p, blk in msgs:
            for i in range(p, p + 2 + len(blk)):
                covered[i] = 1
        runs = jp_runs(s, covered)
        total_msg += len(msgs)
        total_run += len(runs)
        if runs:
            print('%-14s 메시지 %3d, 메시지 밖 일본어 런 %d개' % (f[6:], len(msgs), len(runs)))
            for off, t in runs[:4]:
                print('     +0x%04X  %s' % (off, t[:70]))
    print('-' * 60)
    print('%s 규칙: 메시지 %d개, 메시지 밖 일본어 런 %d개 %s'
          % ('옛(엄격)' if strict else '새(완화)', total_msg, total_run,
             '← 0이어야 완전' if total_run else '✔ 완전'))


if __name__ == '__main__':
    main()
