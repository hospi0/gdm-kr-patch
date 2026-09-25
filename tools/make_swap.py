# -*- coding: utf-8 -*-
"""명장면 목록이 쓰는 한글이 «허프만 트리에 리프가 있는 코드»에 오도록 kocodes 를 교환한다.

## 왜 «교환»인가

트리는 실행 바이너리 안이라 바꿀 수 없고, 리프가 있는 바이트는 192/256 뿐이다.
그렇다고 빈 코드로 «이사»하면 안 된다 — 「kocodes 에 없다」는 「빈 자리」가 아니다.
실제로 `0x000`은 공백(3,068회), `0x0CF`는 `ー`(4,377회)였다.

그래서 **한글끼리 코드를 맞바꾼다**. 원본 글리프는 하나도 안 건드리고,
**같은 바이트 등급끼리** 교환하므로 기존 번역의 길이가 전혀 변하지 않는다.

## 금지 조건

* 리프 없는 바이트를 쓰는 코드
* ⛔**하위 바이트가 `0x00`이 되는 코드** — `(c-0xE0)%256==0` (0x0E0·0x1E0·0x2E0·0x4E0…).
  문자열 한가운데 널이 박혀 「N번째 문자열」 세기가 깨진다(`SHOP.BIN` 검사가 잡았다).

입력: `kocodes.tsv.bak_session11`(교환 전 원본) + `scene_ko.json`
출력: `kocodes.tsv`, `kocodes_swap.json`
"""
import collections
import json
import sys

sys.path.insert(0, 'tools')
import bintext as B

BAK = 'work/trans/kocodes.tsv.bak_session11'
OUT = 'work/trans/kocodes.tsv'
SWAP = 'work/trans/kocodes_swap.json'
TREE = 'work/trans/huff_tree.json'
TEXT = 'work/trans/scene_text.bin'
TABLE = 'work/trans/scene_ko.json'


def load(path):
    out = {}
    for line in open(path, encoding='utf-8'):
        if line.strip() and not line.startswith('#'):
            a, b = line.rstrip('\n').split('\t')[:2]
            out[int(a, 16)] = b
    return out


def main():
    codes = {int(k): v for k, v in json.load(open(TREE))['codes'].items()}
    avail = set(codes)

    def bo(c):
        if c < 0xE0:
            return [(c + 0x20) & 0xFF]
        k = c - 0xE0
        return [0x10 + k // 256, k % 256]

    def ok(c):
        b = bo(c)
        return all(x in avail for x in b) and 0 not in b

    def cost(c):
        return sum(len(codes[x]) for x in bo(c))

    ko = load(BAK)
    rev = {}
    for c, ch in ko.items():
        rev.setdefault(ch, c)

    # 실제로 넣을 문자열(표시폭까지 공백 채운 것)에서 빈도를 센다
    text = open(TEXT, 'rb').read()
    rows, cur = [], bytearray()
    for b in text:
        if b == 0:
            rows.append(B.decode(bytes(cur)))
            cur = bytearray()
        else:
            cur.append(b)
    tr = json.load(open(TABLE, encoding='utf-8'))
    body = []
    for s in rows:
        t = tr.get(s.rstrip(), s.rstrip())
        body.append(t + ' ' * max(0, len(s) - len(t)))
    freq = collections.Counter(ch for line in body for ch in line if ch in rev)
    scene = set(freq)

    need = [(ch, n) for ch, n in freq.most_common() if not ok(rev[ch])]
    p1 = sorted([ch for ch, c in rev.items() if ch not in scene and c < 0xE0 and ok(c)],
                key=lambda ch: cost(rev[ch]))
    p2 = sorted([ch for ch, c in rev.items() if ch not in scene and c >= 0xE0 and ok(c)],
                key=lambda ch: cost(rev[ch]))
    n1 = sum(1 for ch, _ in need if rev[ch] < 0xE0)
    n2 = len(need) - n1
    print('교환 필요 1B %d(후보 %d) / 2B %d(후보 %d)' % (n1, len(p1), n2, len(p2)))
    if len(p1) < n1 or len(p2) < n2:
        raise SystemExit('★교환 후보 부족')

    swaps, i1, i2 = [], 0, 0
    for ch, _ in need:
        o = rev[ch]
        other = p1[i1] if o < 0xE0 else p2[i2]
        if o < 0xE0:
            i1 += 1
        else:
            i2 += 1
        swaps.append([ch, o, other, rev[other]])

    new = dict(ko)
    for a, ca, b, cb in swaps:
        new[ca], new[cb] = b, a

    lines = []
    for line in open(BAK, encoding='utf-8'):
        s = line.rstrip('\n')
        if not s or s.startswith('#'):
            lines.append(s)
            continue
        c = int(s.split('\t')[0], 16)
        lines.append('%03X\t%s' % (c, new[c]))
    open(OUT, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    json.dump(swaps, open(SWAP, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    chk = load(OUT)
    assert set(chk) == set(ko) and sorted(chk.values()) == sorted(ko.values()), '집합이 달라졌다'
    rev2 = {}
    for c, ch in chk.items():
        rev2.setdefault(ch, c)
    bad = [ch for ch in scene if not ok(rev2[ch])]
    print('교환 %d쌍 / kocodes %d항목 / 남은 미커버 음절: %s'
          % (len(swaps), len(chk), bad or '없음'))


if __name__ == '__main__':
    main()
