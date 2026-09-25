# -*- coding: utf-8 -*-
"""`audit_missed` 가 찾은 문장의 **정확한 바이트 시작/길이**를 낸다.

검출된 구간 앞에는 제어코드 인수가 글자로 잘못 읽힌 **쓰레기 접두**가 붙어 있을
수 있다(`左Fハ ニ見たい…`, `の左Fう あ`). 그 접두를 떼고 진짜 문장 시작을 잡는다.

판정: 문장 뒤쪽부터 보아 **가나·한자·구두점·(UI용 라틴)만으로 이루어진 최장 접미**를
고르되, 라틴은 `ACボタン`/`LRボタン`/`XYZボタン`/`Aボタン`/`Cボタン`/`TIME` 같은
알려진 UI 패턴 안에서만 허용한다.
"""
import os
import re
import sys

sys.path.insert(0, 'tools')
import extract_runs as ER
import audit_missed as AM
import codemap

HIRA = set(codemap.HIRA)
KATA = set(codemap.KATA)
PUNCT = AM.PUNCT
UI_LAT = re.compile(r'^(AC|LR|XYZ|A|B|C|X|Y|Z|TIME)')
UI_TOKENS = {'AC','LR','XYZ','A','B','C','X','Y','Z','TIME','HP','MP','SP'}


def clean_start(chars):
    """[(off,ch)] → 진짜 문장이 시작하는 인덱스."""
    n = len(chars)
    for i in range(n):
        t = ''.join(c for _, c in chars[i:])
        if len(t) < 5:
            break
        c0 = t[0]
        # ★시작 글자는 가나/한자/『 이거나, **UI 토큰 + ボタン/：** 형태여야 한다.
        #   그냥 라틴 한 글자로 시작하면 그건 제어코드 인수가 글자로 읽힌 것이다
        #   (`Bなかなか…` 의 B, `Gいらっしゃい…` 의 G). 덮어쓰면 스크립트가 깨진다.
        ok0 = (c0 in HIRA or c0 in KATA or AM.is_kanji(c0) or c0 in '『「'
               or re.match(r'^(AC|LR|XYZ|A|B|C|X|Y|Z)(ボタン|：)', t)
               or t.startswith('TIME'))
        if not ok0:
            continue
        # 남은 라틴 **런**이 전부 알려진 UI 토큰인가 (글자 단위로 보면 `LR` 의 R 이 걸린다)
        if any(m.group(0) not in UI_TOKENS for m in re.finditer(r'[A-Z]+', t)):
            continue
        hira = sum(1 for c in t if c in HIRA)
        if hira < 3:
            continue
        return i
    return 0


def main():
    rows = []
    for fn in sorted(os.listdir(AM.DM)):
        if not fn.endswith('.MDT'):
            continue
        short = fn[6:]
        if short in ('0000.MDT', '0004.MDT', 'EC08.MDT', 'E8FF.MDT'):
            continue
        d = open(os.path.join(AM.DM, fn), 'rb').read()
        try:
            o, sec, _ = ER.extract(d, short)
        except Exception:
            continue
        tsv = AM.load_tsv_ranges().get(short, [])
        toks = AM.greedy(sec)
        # audit_missed 와 같은 방식으로 구간을 다시 만든다
        cur, groups = [], []
        for off, ch in toks:
            good = ch is not None and (ch in HIRA or ch in KATA or AM.is_kanji(ch)
                                       or ch in PUNCT or ch.isdigit()
                                       or ch in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ')
            if good:
                cur.append((off, ch))
            else:
                if cur:
                    groups.append(cur)
                cur = []
        if cur:
            groups.append(cur)

        for g in groups:
            t = ''.join(c for _, c in g)
            if len(t) < 6:
                continue
            a, b = g[0][0], g[-1][0]
            if any(not (b < s or a > e) for s, e, _ in tsv):
                continue
            if not AM.sentences(sec[a:b + 3]):
                continue
            i = clean_start(g)
            start = g[i][0]
            end = g[-1][0]
            # 끝 글자의 바이트 길이
            last = sec[end]
            end_len = 2 if 0x10 <= last <= 0x1F else 1
            rows.append((short, start, end + end_len - start,
                         ''.join(c for _, c in g[i:])))

    out = 'work/trans/todo_missed.tsv'
    with open(out, 'w', encoding='utf-8') as f:
        f.write('file\toff\tlen\tja\tko\n')
        for s_, off, ln, ja in rows:
            f.write('%s\t%05X\t%d\t%s\t\n' % (s_, off, ln, ja))
    print('%d건 -> %s' % (len(rows), out))
    for s_, off, ln, ja in rows:
        print('  %-12s %05X len=%2d  %s' % (s_, off, ln, ja))


if __name__ == '__main__':
    main()
