# -*- coding: utf-8 -*-
"""sec4_10_merged.json(jp->ko, 유니크셋)을 FIELD_TEXT2.BIN / BATLE_TEXT2.BIN
각 파일의 실제 오프셋에 매칭해 ui_build.py 가 먹는 off/ko tsv 로 낸다.

섹션3(전투UI, 이미 처리됨)과 노이즈(섹션7)는 제외 — classify_sec4_10.classify() 재사용.
"""
import json
import sys

sys.path.insert(0, 'tools')
import classify_sec4_10 as C


def main():
    trans = json.load(open('work/trans/sec4_10_merged.json', encoding='utf-8'))
    for fn, out in [('work/dm/FIELD_TEXT2.BIN', 'work/trans/ui_sec4_10_field.tsv'),
                    ('work/dm/BATLE_TEXT2.BIN', 'work/trans/ui_sec4_10_batle.tsv')]:
        real, noise = C.classify(fn)
        rows = []
        missing = []
        for s, off, ln, t in real:
            if t in trans:
                rows.append((off, trans[t]))
            else:
                missing.append((off, t))
        with open(out, 'w', encoding='utf-8') as f:
            f.write('off\tko\n')
            for off, ko in sorted(rows):
                f.write('%06X\t%s\n' % (off, ko))
        print('%s: 매칭 %d / 번역없음 %d -> %s' % (fn, len(rows), len(missing), out))
        for off, t in missing[:10]:
            print('   ★번역없음 0x%X %r' % (off, t))


if __name__ == '__main__':
    main()
