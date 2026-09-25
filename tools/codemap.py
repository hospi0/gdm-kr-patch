# -*- coding: utf-8 -*-
"""폰트 코드 ↔ 글자 대응표.

가나·영숫자·기호 구간(0x000~0x0D7)은 **JIS 배열**을 따르며, 시트를 눈으로 읽어
확정했다(`work/sheet_000.png`, `sheet_070.png`, `sheet_0C0.png`, `sheet_0D0.png`).
표준 JIS와의 차이: **`ゐ ゑ ヰ ヱ` 4자가 빠져 있다.**

한자는 0x0D8부터이고 **JIS 순서가 아니라 게임 자체 순서**라 시트를 읽어
`work/codemap_kanji.tsv` 에 채워 넣는다.
"""
import os

HIRA = ('ぁあぃいぅうぇえぉおかがきぎくぐけげこごさざしじすずせぜそぞただちぢっつづてでとど'
        'なにぬねのはばぱひびぴふぶぷへべぺほぼぽまみむめもゃやゅゆょよらりるれろゎわをん')
KATA = ('ァアィイゥウェエォオカガキギクグケゲコゴサザシジスズセゼソゾタダチヂッツヅテデトド'
        'ナニヌネノハバパヒビピフブプヘベペホボポマミムメモャヤュユョヨラリルレロヮワヲンヴヵヶ')
SYMS = '・：？！々ー～‥─♪♥○‼⁉'

KANJI_TSV = 'work/codemap_kanji.tsv'


def base_map():
    m = {0x000: ' '}
    for i in range(10):
        m[0x001 + i] = chr(ord('0') + i)
    for i in range(26):
        m[0x00B + i] = chr(ord('A') + i)
    for i, ch in enumerate(HIRA):
        m[0x025 + i] = ch
    for i, ch in enumerate(KATA):
        m[0x025 + len(HIRA) + i] = ch
    for i, ch in enumerate(SYMS):
        m[0x025 + len(HIRA) + len(KATA) + i] = ch
    return m


def load():
    m = base_map()
    if os.path.exists(KANJI_TSV):
        for line in open(KANJI_TSV, encoding='utf-8'):
            line = line.rstrip('\n')
            if not line or line.startswith('#'):
                continue
            a, b = line.split('\t')[:2]
            m[int(a, 16)] = b
    return m


def check():
    m = base_map()
    exp = {0x000: ' ', 0x026: 'あ', 0x037: 'こ', 0x070: 'れ', 0x078: 'ィ',
           0x08E: 'ス', 0x09F: 'ナ', 0x0AA: 'フ', 0x0C6: 'ン', 0x0CC: '？',
           0x0CD: '！', 0x0CF: 'ー', 0x0D7: '⁉'}
    bad = 0
    for c, ch in sorted(exp.items()):
        got = m.get(c)
        ok = got == ch
        if not ok:
            bad += 1
        print('  0x%03X 기대 %s 실제 %s %s' % (c, ch, got, '' if ok else '← 불일치'))
    print('가나·기호 구간 끝 = 0x%03X (한자 시작 0x%03X)'
          % (max(m), max(m) + 1))
    print('검증 %s' % ('통과' if bad == 0 else '실패 %d건' % bad))
    return bad == 0


if __name__ == '__main__':
    check()
