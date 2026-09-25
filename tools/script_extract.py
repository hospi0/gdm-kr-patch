# -*- coding: utf-8 -*-
"""대사를 번역 작업용 TSV로 추출한다.

한 줄 = 메시지 블록 하나.
  file      MDT 파일 이름
  off       스크립트 섹션 안에서의 `20 LL` 위치
  len       원본 블록 길이(LL)
  ja        원문 (제어코드는 `{hex}` 로 보존, `01`→`\\n`, `02`→`\\p`)
  ko        번역문 (비우면 원문 유지)

★ 원문(ja)은 **절대 수정하지 않는다.** 빌더는 ko만 읽는다.
★ 제어 토큰 `{...}` 는 **개수·순서를 바꾸지 말 것.** 빌더가 그대로 되돌려 넣는다.
"""
import csv
import os
import sys

sys.path.insert(0, 'tools')
import codemap
from codemap_kanji_src import kanji_map
from script_budget import script_section
from script_parse import CTRL, TEXT, emit, parse
from script_render import messages

OUT = 'work/trans/script.tsv'
NL, PAGE = '\\n', '\\p'


SUSPECT_MAX = 2      # 제어코드에 둘러싸인 이 길이 이하의 런은 '수상'으로 본다


def opaque_bytes(v):
    """글자 코드를 원래 바이트열로 (불투명 보존용)"""
    if v < 0xE0:
        return bytes((v + 0x20,))
    k = v - 0xE0
    return bytes((0x10 + k // 256, k % 256))


def mark_suspects(toks):
    """★ 제어코드 길이표에 남은 중의성을 무해화한다.

    길이가 틀리면 그 **인수 바이트가 제어코드 옆의 1~2글자 부스러기**로 나타난다.
    그런 런은 진짜 글자가 아닐 수 있으므로 **불투명 토큰으로 되돌려** 번역 대상에서 뺀다.
    → 어떤 길이표가 정답이든 그 바이트는 원본 그대로 보존된다.
    """
    out, i, n = [], 0, len(toks)
    while i < n:
        if toks[i][0] != TEXT:
            out.append(toks[i])
            i += 1
            continue
        j = i
        while j < n and toks[j][0] == TEXT:
            j += 1
        run = toks[i:j]
        prev_ctrl = i > 0 and toks[i - 1][0] == CTRL
        next_ctrl = j < n and toks[j][0] == CTRL
        if len(run) <= SUSPECT_MAX and prev_ctrl and next_ctrl:
            out.append((CTRL, b''.join(opaque_bytes(v) for _, v in run)))
        else:
            out += run
        i = j
    return out


def tokens_to_text(toks, m):
    """⚠️ 생략해도 되는 0x07 은 **마지막 토큰뿐**이다.
    0x07 이 블록 중간에도 나오는 메시지가 있어서, 전부 생략하면 복원이 깨진다."""
    toks = mark_suspects(toks)
    out = []
    last = len(toks) - 1
    for k, (t, v) in enumerate(toks):
        if t == TEXT:
            ch = m.get(v)
            out.append(ch if ch is not None else '{?%03X}' % v)
        elif v == b'\x01':
            out.append(NL)
        elif v == b'\x02':
            out.append(PAGE)
        elif v == b'\x07' and k == last:
            pass                                   # 종결자만 생략
        else:
            out.append('{%s}' % v.hex())
    return ''.join(out)


def main():
    m = codemap.base_map()
    m.update(kanji_map())
    os.makedirs('work/trans', exist_ok=True)
    rows = []
    bad = 0
    for f in sorted(os.listdir('work/dm')):
        if not f.endswith('.MDT'):
            continue
        d = open('work/dm/' + f, 'rb').read()
        o, b, _ = script_section(d)
        s = d[o:o + b]
        for p, blk in messages(s):
            toks = parse(blk)
            if emit(toks) != bytes(blk):
                bad += 1
            rows.append([f[6:], '%04X' % p, str(len(blk)),
                         tokens_to_text(toks, m), ''])
    with open(OUT, 'w', encoding='utf-8', newline='') as fp:
        w = csv.writer(fp, delimiter='\t', quoting=csv.QUOTE_MINIMAL)
        w.writerow(['file', 'off', 'len', 'ja', 'ko'])
        w.writerows(rows)
    print('%s — 메시지 %d개' % (OUT, len(rows)))
    print('parse↔emit 왕복 실패 %d건 %s' % (bad, '' if bad == 0 else '★'))
    tot = sum(len(r[3]) for r in rows)
    print('원문 표기 총 %d자 (제어 토큰 포함)' % tot)


if __name__ == '__main__':
    main()
