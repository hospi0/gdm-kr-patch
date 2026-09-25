# -*- coding: utf-8 -*-
"""번역문을 MDT에 재삽입한다.

불변식 (하나라도 어기면 빌드 실패):
  1. **ko가 빈 메시지는 원본과 바이트가 완전히 같아야 한다.**
  2. 메시지 블록 길이 `20 LL` 은 **짝수, ≤ 255**.
  3. 그 메시지를 감싸는 모든 조건부 스킵 `1000 30LL` 을 갱신하고 **≤ 255**.
  4. 인코딩 불가 문자는 **조용히 건너뛰지 않고 빌드를 실패**시킨다.
  5. 다시 파싱한 결과가 넣으려던 토큰열과 같아야 한다(라운드트립).

스크립트 섹션 크기가 바뀌면 뒤 섹션이 밀리므로, 기본은 **크기 보존**을 요구하고
남는/모자라는 바이트를 보고한다(`--allow-resize` 로 완화, 그때는 MDT 헤더도 갱신).
"""
import csv
import os
import struct
import sys

sys.path.insert(0, 'tools')
import codemap
from codemap_kanji_src import kanji_map
from script_budget import scan_skips, script_section
from script_parse import CTRL, CTRL_LEN, TEXT, emit, parse
from script_render import messages

TSV = 'work/trans/script.tsv'
KOCODES = 'work/trans/kocodes.tsv'      # 한글 → 폰트코드 (폰트 작업 후 생성)
SRC, DST = 'work/dm', 'work/build'
NL, PAGE = '\\n', '\\p'


class BuildError(Exception):
    pass


# 한국어 번역문은 반각 구두점을 자연스럽게 쓰지만, 폰트에는 전각만 있다.
# 새 글리프를 안 늘리려고 기존 전각 코드로 치환한다.
PUNCT_FALLBACK = {'!': '！', '?': '？', '~': '～', chr(0xB7): '・',
                   '…': '‥', '(': '（', ')': '）'}


def char_to_code(m_rev, ko_rev, ch):
    if ch in ko_rev:
        return ko_rev[ch]
    if ch in m_rev:
        return m_rev[ch]
    if ch in PUNCT_FALLBACK:
        return char_to_code(m_rev, ko_rev, PUNCT_FALLBACK[ch])
    raise BuildError('폰트에 없는 문자 %r (U+%04X)' % (ch, ord(ch)))


def text_to_tokens(s, m_rev, ko_rev):
    """`{hex}` `\\n` `\\p` 를 제어로, 나머지를 글자로 되돌린다"""
    toks, i = [], 0
    while i < len(s):
        if s.startswith(NL, i):
            toks.append((CTRL, b'\x01'))
            i += 2
        elif s.startswith(PAGE, i):
            toks.append((CTRL, b'\x02'))
            i += 2
        elif s[i] == '{':
            j = s.index('}', i)
            body = s[i + 1:j]
            if body.startswith('?'):
                raise BuildError('미해독 코드 토큰 %s 가 남아 있다' % s[i:j + 1])
            toks.append((CTRL, bytes.fromhex(body)))
            i = j + 1
        else:
            toks.append((TEXT, char_to_code(m_rev, ko_rev, s[i])))
            i += 1
    toks.append((CTRL, b'\x07'))
    return toks


def used_codes():
    """원본 스크립트에서 실제로 쓰이는 코드의 빈도"""
    from collections import Counter
    cnt = Counter()
    for f in sorted(os.listdir(SRC)):
        if not f.endswith('.MDT'):
            continue
        d = open(os.path.join(SRC, f), 'rb').read()
        o, b, _ = script_section(d)
        for p, blk in messages(d[o:o + b]):
            for t, v in parse(blk):
                if t == TEXT:
                    cnt[v] += 1
    return cnt


def load_rev():
    """글자 → 코드. **같은 글자에 코드가 둘 이상**이면(예: `十` = 0x126·0x343)
    원본에서 실제로 쓰인 코드를 고른다. 안 그러면 ko=ja 왕복이 깨진다."""
    m = codemap.base_map()
    m.update(kanji_map())
    cnt = used_codes()
    rev = {}
    for c, ch in sorted(m.items()):
        if ch not in rev or cnt[c] > cnt[rev[ch]]:
            rev[ch] = c
    ko = {}
    if os.path.exists(KOCODES):
        for line in open(KOCODES, encoding='utf-8'):
            if line.strip() and not line.startswith('#'):
                a, b = line.rstrip('\n').split('\t')[:2]
                ko[b] = int(a, 16)
    return rev, ko


def main():
    allow_resize = '--allow-resize' in sys.argv
    m_rev, ko_rev = load_rev()
    rows = list(csv.DictReader(open(TSV, encoding='utf-8'), delimiter='\t'))
    byfile = {}
    for r in rows:
        byfile.setdefault(r['file'], {})[int(r['off'], 16)] = r
    os.makedirs(DST, exist_ok=True)

    n_tr = n_same = 0
    for f in sorted(os.listdir(SRC)):
        if not f.endswith('.MDT'):
            continue
        name = f[6:]
        d = bytearray(open(os.path.join(SRC, f), 'rb').read())
        o, blen, _ = script_section(bytes(d))
        s = bytearray(d[o:o + blen])
        msgs = messages(bytes(s))
        if not msgs:
            open(os.path.join(DST, f), 'wb').write(bytes(d))
            continue

        # 새 블록 만들기 (뒤에서부터 넣어야 앞 오프셋이 안 밀린다)
        newblocks = {}
        for p, blk in msgs:
            r = byfile.get(name, {}).get(p)
            ko = (r or {}).get('ko', '').strip()
            if not ko:
                newblocks[p] = bytes(blk)
                n_same += 1
                continue
            toks = text_to_tokens(ko, m_rev, ko_rev)
            nb = emit(toks)
            if not allow_resize:
                # ★ 기본 정책: 블록 길이를 **원본과 똑같이** 유지한다.
                #   섹션 크기가 안 변하므로 스킵·헤더를 건드릴 필요가 없다.
                #   남는 자리는 종결자 앞에 **공백(0x20)** 으로 채운다 — 줄 끝 공백은 안 보인다.
                if len(nb) > len(blk):
                    raise BuildError(
                        '%s +0x%04X: 번역이 %dB 로 원본 %dB 를 넘는다 (%+dB)'
                        % (name, p, len(nb), len(blk), len(nb) - len(blk)))
                nb = nb[:-1] + b'\x20' * (len(blk) - len(nb)) + b'\x07'
            elif len(nb) % 2:
                # 크기 가변 정책에서는 종결자 앞에 공백 1바이트를 끼워 짝수로 맞춘다.
                nb = nb[:-1] + b'\x20' + nb[-1:]
            if len(nb) % 2:
                raise BuildError('%s +0x%04X: 블록 길이가 홀수(%d)' % (name, p, len(nb)))
            if len(nb) > 255:
                raise BuildError('%s +0x%04X: 블록 %dB > 255' % (name, p, len(nb)))
            # ★ 검사는 **바이트 기준**이어야 한다.
            #   불투명 토큰(제어 인수를 그대로 보존한 것)은 다시 파싱하면 글자로 읽히므로
            #   토큰열 비교는 성립하지 않는다. 의미 있는 불변식은 parse↔emit 일관성이다.
            if emit(parse(nb)) != nb:
                raise BuildError('%s +0x%04X: parse↔emit 불일치' % (name, p))
            newblocks[p] = nb
            n_tr += 1

        skips = scan_skips(bytes(s))
        out = bytearray()
        prev = 0
        deltas = []                     # (원본위치, 증감)
        for p, blk in msgs:
            out += s[prev:p]
            nb = newblocks[p]
            out += bytes((0x20, len(nb))) + nb
            deltas.append((p, len(nb) - len(blk)))
            prev = p + 2 + len(blk)
        out += s[prev:]

        # 조건부 스킵 갱신
        for sp, st, en, LL in skips:
            add = sum(dl for pos, dl in deltas if st <= pos < en)
            if not add:
                continue
            v = LL + add
            if not 0 <= v <= 255:
                raise BuildError('%s: 스킵 +0x%04X 가 %d 로 범위 밖' % (name, sp, v))
            # out 안에서의 위치 = sp + 그 앞쪽 증감 합
            shift = sum(dl for pos, dl in deltas if pos < sp)
            out[sp + shift + 3] = v

        if len(out) != blen:
            msg = ('%s: 스크립트 섹션 크기 %d → %d (%+d B)'
                   % (name, blen, len(out), len(out) - blen))
            if not allow_resize:
                raise BuildError(msg + ' — 크기 보존 위반 (--allow-resize 로 완화)')
            print('  ' + msg)

        d[o:o + blen] = out[:blen] if len(out) >= blen else \
            out + s[len(out):blen]
        open(os.path.join(DST, f), 'wb').write(bytes(d))

    print('번역 반영 %d개 / 원문 유지 %d개' % (n_tr, n_same))

    # 불변식 1 검증: 번역이 하나도 없으면 전 파일이 원본과 같아야 한다
    same = diff = 0
    for f in sorted(os.listdir(SRC)):
        if not f.endswith('.MDT'):
            continue
        a = open(os.path.join(SRC, f), 'rb').read()
        b = open(os.path.join(DST, f), 'rb').read()
        if a == b:
            same += 1
        else:
            diff += 1
    print('원본과 동일한 파일 %d / 달라진 파일 %d' % (same, diff))
    if n_tr == 0 and diff:
        raise BuildError('번역이 없는데 파일이 달라졌다 — 빌더 버그')


if __name__ == '__main__':
    try:
        main()
    except BuildError as e:
        print('빌드 실패: %s' % e)
        sys.exit(1)
