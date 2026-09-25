# -*- coding: utf-8 -*-
"""추출 v2 의 **완전성**을 검증한다.

세션2 교훈([[feedback_verify_extraction_completeness]]): 재삽입 왕복 검증은
"추출한 것이 잘 들어갔는가"만 보증한다. 완전성은 **추출 안 된 나머지**를 봐야 안다.

판정: 스크립트 섹션에서 메시지가 차지하지 않은 영역에 **일본어 텍스트 런이 남으면 미완**.
"""
import os
import sys

sys.path.insert(0, 'tools')
import codemap
from codemap_kanji_src import kanji_map
from extract_v2 import extract, jp_ratio, text

m = codemap.base_map()
m.update(kanji_map())
KANA = set(codemap.HIRA + codemap.KATA)


def main():
    minlen = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    tot_msg = tot_run = 0
    worst = []
    for f in sorted(os.listdir('work/dm')):
        if not f.endswith('.MDT'):
            continue
        d = open('work/dm/' + f, 'rb').read()
        o, s, msgs = extract(d)
        cov = bytearray(len(s))
        for p, blk in msgs.items():
            for i in range(p, min(len(s), p + 2 + len(blk))):
                cov[i] = 1
        # 메시지 밖 일본어 런
        runs, cur, st = [], [], None
        for i, b in enumerate(s):
            ch = m.get(b - 0x20) if (not cov[i] and b >= 0x20) else None
            if ch and (ch in KANA or 0x4E00 <= ord(ch) <= 0x9FFF):
                if st is None:
                    st = i
                cur.append(ch)
            else:
                if st is not None and len(cur) >= minlen:
                    runs.append((st, ''.join(cur)))
                cur, st = [], None
        if st is not None and len(cur) >= minlen:
            runs.append((st, ''.join(cur)))
        tot_msg += len(msgs)
        tot_run += len(runs)
        if runs:
            worst.append((f[6:], len(msgs), runs))
    print('메시지 %d개' % tot_msg)
    print('메시지 밖 일본어 런(길이 %d+) %d개 %s'
          % (minlen, tot_run, '← 0이어야 완전' if tot_run else '✔ 완전'))
    for f, nm, runs in worst[:6]:
        print('  %-14s 메시지 %3d, 남은 런 %d' % (f, nm, len(runs)))
        for off, t in runs[:3]:
            print('      +0x%04X %s' % (off, t[:60]))


if __name__ == '__main__':
    main()
