# -*- coding: utf-8 -*-
"""한글 슬롯 배정 계획.

정책:
  - 반각 구두점 정규화: ! ? ~ U+00B7 는 기존 전각 글리프로 자동 치환
    (script_build.char_to_code 의 폴백으로 구현, 여기서는 계획만 확인)
  - 새로 필요한 진짜 신규 글리프: 한글 622자 + 쉼표(,) + 마침표(.)
  - 보호 코드(재배치 금지): 불투명 토큰이 참조하는 7개
    공백(0x000) V(0x020) へ(0x05C) ホ(0x0B0) ム(0x0B5) ・(0x0CA) ‥(0x0D1)
  - 재배치 가능 1바이트: 히라가나(0x025~0x075 중 0x05C 제외) +
    가타카나(0x076~0x0C9 중 0x0B0·0x0B5 제외) = 162칸
  - 빈도 상위 162자(쉼표·마침표 포함, 도합 164자리 필요하므로 상위 162개
    한글 음절만 1바이트, 쉼표/마침표는 실제 안 쓰이는 라틴 알파벳 자리에)
  - 나머지 한글은 2바이트(한자 영역, 필수 예약 코드만 제외)
"""
import csv
import re
import sys
from collections import Counter

sys.path.insert(0, 'tools')
import codemap
from codemap_kanji_src import kanji_map

PUNCT_FALLBACK = {'!': '！', '?': '？', '~': '～', chr(0xB7): '・'}
PROTECT = {0x000, 0x020, 0x05C, 0x0B0, 0x0B5, 0x0CA, 0x0D1}

TOKRE = re.compile(r'(\{[0-9a-f]+\}|\\n|\\p)')


def strip_tokens(s):
    return ''.join(p for p in TOKRE.split(s) if p and not TOKRE.fullmatch(p))


def normalize(s):
    for a, b in PUNCT_FALLBACK.items():
        s = s.replace(a, b)
    return s


def main():
    m = codemap.base_map()
    m.update(kanji_map())
    have = set(m.values())

    rows = list(csv.DictReader(open('work/trans/script.tsv', encoding='utf-8'),
                               delimiter='\t'))
    cnt = Counter()
    for r in rows:
        if not r['ko']:
            continue
        txt = normalize(strip_tokens(r['ko']))
        cnt.update(txt)

    latin_used = sorted(ch for ch in cnt if 'A' <= ch <= 'Z')
    print('실제 사용 라틴 대문자: %s' % latin_used)

    missing = {ch: n for ch, n in cnt.items() if ch not in have}
    hangul = sorted((ch for ch in missing if 0xAC00 <= ord(ch) <= 0xD7A3),
                    key=lambda c: -cnt[c])
    other = [ch for ch in missing if not (0xAC00 <= ord(ch) <= 0xD7A3)]
    print('한글 음절 %d종 (총 사용 %d회)' % (len(hangul), sum(cnt[c] for c in hangul)))
    print('한글 아님(진짜 신규) %d종: %s' % (len(other), other))

    # 재배치 가능 1바이트 슬롯
    hira = [c for c in range(0x025, 0x025 + len(codemap.HIRA)) if c not in PROTECT]
    kata = [c for c in range(0x025 + len(codemap.HIRA),
                             0x025 + len(codemap.HIRA) + len(codemap.KATA))
            if c not in PROTECT]
    free1 = hira + kata
    print('1바이트 재배치 가능 슬롯 %d개 (히라 %d + 가타 %d)'
          % (len(free1), len(hira), len(kata)))

    need_extra = len(other)          # 쉼표·마침표 등
    n1 = len(free1) - need_extra
    print('신규 기호(쉼표 등) %d개를 뺀 한글 1바이트 자리 %d개' % (need_extra, n1))

    top = hangul[:n1]
    rest = hangul[n1:]
    print('1바이트 배정 %d자 (누적 사용 %d회), 2바이트 배정 %d자 (누적 사용 %d회)'
          % (len(top), sum(cnt[c] for c in top),
             len(rest), sum(cnt[c] for c in rest)))

    # 산출물 저장 (다음 스크립트에서 사용)
    import json
    plan = {
        'free1': free1,
        'other': other,
        'top': top,
        'rest': rest,
        'counts': {c: cnt[c] for c in hangul + other},
    }
    with open('work/trans/slot_plan.json', 'w', encoding='utf-8') as f:
        json.dump(plan, f, ensure_ascii=False, indent=1)
    print('work/trans/slot_plan.json 저장')


if __name__ == '__main__':
    main()
