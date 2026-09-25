# -*- coding: utf-8 -*-
"""'my files/새 폴더'에서 돌아온 번역을 정리한다.

발견한 오염 패턴(세션 기록):
  1. `1000 30LL` 조건부 스킵 명령의 opcode 바이트가 텍스트로 오독됨 → extract_runs.py에서
     이미 수정, 재추출 완료.
  2. 그와 별개로, opcode 0x1XXX(COND1)가 상태 의존적으로 인수를 먹는 경우가 있어 일부
     런은 여전히 진짜 텍스트 앞에 낱글자 하나가 얹혀 나온다(臓‥で → で, 駅レント博物館 →
     アレント博物館 등). 같은 지명 문자열이 파일마다 다른 접두 글자를 달고 나오는 것으로
     확인(구조적 아티팩트, 내용 아님). 예외: '7不思議'처럼 진짜 숫자가 붙는 경우는 보존.
  3. 작은따옴표 ' 는 폰트에 없다 — 게임이 원래 쓰는 「」 인용부호로 치환(홀짝 번갈아).
"""
import csv
import glob
import re
import sys

sys.path.insert(0, 'tools')

EXC_JA = re.compile(r'^\d+不思議')


def is_hangul(c):
    return 0xAC00 <= ord(c) <= 0xD7A3


SAFE_LEAD = set('‥…!?~・.,()（）「」『』♥♪⁉‼～\'"○※　 ')


def strip_prefix(ko, ja):
    """번역문은 전부 한글이어야 한다 — 맨 앞에 한글도 아니고 안전 부호도 아닌
    글자(한자·가나·라틴·숫자)가 있으면 추출 오염이다(§ 임의 opcode 인수가
    글자처럼 읽힌 것). 유일한 예외: '7不思議'처럼 원문 자체가 그 숫자로
    시작하는 경우."""
    if len(ko) < 2 or is_hangul(ko[0]) or ko[0] in SAFE_LEAD:
        return ko
    if ja and EXC_JA.match(ja):
        return ko
    return strip_prefix(ko[1:], ja)


def fix_quotes(ko):
    if "'" not in ko:
        return ko
    out = []
    n = 0
    for ch in ko:
        if ch == "'":
            out.append('「' if n % 2 == 0 else '」')
            n += 1
        else:
            out.append(ch)
    return ''.join(out)


def clean(ko, ja):
    ko = strip_prefix(ko.strip(), ja)
    ko = fix_quotes(ko)
    return ko


def main():
    runs = list(csv.DictReader(open('work/trans/runs.tsv', encoding='utf-8'), delimiter='\t'))
    byoff = {(r['file'], r['off']): r['ja'] for r in runs}

    rows = []
    stripped = quoted = 0
    for path in sorted(glob.glob('my files/새 폴더/*.tsv')):
        for r in csv.DictReader(open(path, encoding='utf-8'), delimiter='\t'):
            ja = byoff.get((r['file'], r['off']), r['ja'])
            ko0 = r['ko'].strip()
            ko1 = strip_prefix(ko0, ja)
            if ko1 != ko0:
                stripped += 1
            ko2 = fix_quotes(ko1)
            if ko2 != ko1:
                quoted += 1
            rows.append({'file': r['file'], 'off': r['off'], 'len': r['len'], 'ja': ja, 'ko': ko2})

    print('접두 오염 제거 %d건 / 따옴표 치환 %d건 / 전체 %d행' % (stripped, quoted, len(rows)))
    with open('work/trans/batch_clean.tsv', 'w', encoding='utf-8', newline='') as fp:
        w = csv.writer(fp, delimiter='\t')
        w.writerow(['file', 'off', 'len', 'ja', 'ko'])
        for r in rows:
            w.writerow([r['file'], r['off'], r['len'], r['ja'], r['ko']])
    print('저장: work/trans/batch_clean.tsv')


if __name__ == '__main__':
    main()
