# -*- coding: utf-8 -*-
"""번역 작업용 — 각 메시지의 ja를 텍스트 런 단위로 쪼개 번호를 매겨 보여준다.

TSV의 ja 문자열은 {hex} 토큰과 \\n, \\p 로 나뉜다. 이 사이의 텍스트 런들이
번역 시 채워야 할 조각(parts)이다. apply_ko.py 의 build() 와 정확히 같은
분할 규칙을 쓴다.
"""
import csv
import re

TOKRE = re.compile(r'(\{[0-9a-f]+\}|\\n|\\p)')


def segments(ja):
    return [s for s in TOKRE.split(ja) if s and not TOKRE.fullmatch(s)]


def main():
    rows = list(csv.DictReader(open('work/trans/script.tsv', encoding='utf-8'),
                               delimiter='\t'))
    with open('work/trans/segments.txt', 'w', encoding='utf-8') as f:
        for r in rows:
            segs = segments(r['ja'])
            f.write('### %s +%s (%d조각)\n' % (r['file'], r['off'], len(segs)))
            for i, s in enumerate(segs):
                f.write('  [%d] %s\n' % (i, s))
            f.write('\n')
    print('work/trans/segments.txt 작성 완료, 총 %d메시지' % len(rows))


if __name__ == '__main__':
    main()
