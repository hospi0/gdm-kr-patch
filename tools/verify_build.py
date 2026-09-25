# -*- coding: utf-8 -*-
"""빌드 결과를 되읽어 의도한 번역과 일치하는지 검증한다.

검사 항목:
  1. 모든 파일에서 섹션 크기·메시지 개수가 원본과 같다
  2. 각 메시지를 다시 파싱해 글자를 복원하면 ko의 글자 부분과 일치한다
     (끝 공백 패딩은 허용)
  3. 제어코드 바이트열이 원본과 같다 (번역이 제어를 건드리지 않았다)
"""
import csv
import os
import re
import sys

sys.path.insert(0, 'tools')
import codemap
from codemap_kanji_src import kanji_map
from script_budget import script_section
from script_build import PUNCT_FALLBACK, load_rev
from script_extract import mark_suspects
from script_parse import CTRL, TEXT, parse
from script_render import messages

TOKRE = re.compile(r'(\{[0-9a-f]+\}|\\n|\\p)')


def normalize(s):
    """빌더가 하는 반각→전각 구두점 치환을 기대값에도 똑같이 적용"""
    for a, b in PUNCT_FALLBACK.items():
        s = s.replace(a, b)
    return s


def main():
    m = codemap.base_map()
    m.update(kanji_map())
    ko_map = {}
    for line in open('work/trans/kocodes.tsv', encoding='utf-8'):
        if line.strip() and not line.startswith('#'):
            a, b = line.rstrip('\n').split('\t')[:2]
            ko_map[int(a, 16)] = b
    full = dict(m)
    full.update(ko_map)          # 한글 슬롯이 기존 글자를 덮어씀

    rows = list(csv.DictReader(open('work/trans/script.tsv', encoding='utf-8'),
                               delimiter='\t'))
    byfile = {}
    for r in rows:
        byfile.setdefault(r['file'], {})[int(r['off'], 16)] = r

    ok = bad = 0
    for f in sorted(os.listdir('work/dm')):
        if not f.endswith('.MDT'):
            continue
        a = open('work/dm/' + f, 'rb').read()
        b = open('work/build/' + f, 'rb').read()
        oa, la, _ = script_section(a)
        ob, lb, _ = script_section(b)
        if (oa, la) != (ob, lb):
            print('★ %s 섹션 위치/크기 불일치 %s != %s' % (f, (oa, la), (ob, lb)))
            bad += 1
            continue
        # ⚠️ 빌드본에 messages() 를 다시 돌리면 안 된다.
        #    스캐너는 블록 내용이 제어코드(<0x20)로 시작할 것을 요구하는데,
        #    번역문이 1바이트 한글로 시작하면 그 조건에 걸려 못 찾는다.
        #    게임은 `20 LL` 의 길이만 읽으므로 실제 동작엔 영향이 없다.
        #    → **원본에서 찾은 오프셋·길이를 그대로 써서** 빌드본을 읽는다.
        ma = dict(messages(a[oa:oa + la]))
        sb = b[ob:ob + lb]
        mb = {}
        for p, blk in ma.items():
            if sb[p] != 0x20 or sb[p + 1] != len(blk):
                print('★ %s +0x%04X 블록 헤더 깨짐 (20 %02X 기대, %02X %02X)'
                      % (f, p, len(blk), sb[p], sb[p + 1]))
                bad += 1
                continue
            mb[p] = sb[p + 2:p + 2 + len(blk)]
        for p in sorted(mb):
            if len(ma[p]) != len(mb[p]):
                print('★ %s +0x%04X 길이 %d != %d' % (f, p, len(ma[p]), len(mb[p])))
                bad += 1
                continue
            # ⚠️ mark_suspects 는 쓰지 않는다. 끝에 붙는 공백 패딩 때문에 런 길이가
            #    달라져 불투명 판정이 원본과 어긋난다(바이트는 정상).
            #    원시 parse() 로 제어코드만 비교하고, 불투명 토큰은 글자로 되살려 비교한다.
            ta, tb = parse(ma[p]), parse(mb[p])
            ca = [v for t, v in ta if t == CTRL]
            cb = [v for t, v in tb if t == CTRL]
            if ca != cb:
                print('★ %s +0x%04X 제어코드 변경됨' % (f, p))
                print('   원본: %s' % [x.hex() for x in ca][:12])
                print('   빌드: %s' % [x.hex() for x in cb][:12])
                bad += 1
                continue
            got = ''.join(full.get(v, '?%03X' % v) for t, v in tb if t == TEXT)
            r = byfile[f[6:]][p]
            # ko 의 불투명 토큰 중 내용이 전부 0x20 이상인 것은 실제로는 글자다
            parts = []
            for s in TOKRE.split(r['ko']):
                if not s:
                    continue
                if TOKRE.fullmatch(s):
                    if s.startswith('{'):
                        raw = bytes.fromhex(s[1:-1])
                        if all(x >= 0x20 for x in raw):
                            parts.append(''.join(full.get(x - 0x20, '?') for x in raw))
                    continue
                parts.append(s)
            want = normalize(''.join(parts))
            if got.rstrip() != want.rstrip():
                print('★ %s +0x%04X 본문 불일치' % (f, p))
                print('   기대: %r' % want[:80])
                print('   실제: %r' % got[:80])
                bad += 1
                continue
            ok += 1
    print('메시지 검증 통과 %d / 실패 %d' % (ok, bad))


if __name__ == '__main__':
    main()
