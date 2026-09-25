# -*- coding: utf-8 -*-
"""**ISO 356개 파일 전수** 텍스트 census — "어느 파일에 번역 대상 텍스트가 있는가"를
파일 목록 추측이 아니라 계산으로 확정한다.

배경(§20.10 교훈의 3번째 재발): `道具` 를 세 번이나 "다 찾았다"고 했는데
실기에서 계속 깨졌다. 원인은 매번 **일부 파일만 조사**했기 때문.
이번엔 전 파일을 같은 기준으로 세고, 이미 손댄 파일과 대조해 누락을 0으로 만든다.

기준: 널 종단 구간을 디코드해 `bintext.real_jp()` 를 통과하는 문자열 수.
     (MDT 대사처럼 널 종단이 아닌 포맷은 이 census 로는 안 잡히지만,
      MDT 는 이미 `extract_runs.py` 로 별도 처리돼 있다.)
"""
import os
import sys

sys.path.insert(0, 'tools')
import bintext as B
import find_menu_source as F

HANDLED_PREFIX = ('FIELD_TEXT2.BIN', 'BATLE_TEXT2.BIN', 'FIELD_CMDMN.BIN')


def census(d, min_len=2):
    n = 0
    samples = []
    i = 0
    while i < len(d):
        j = i
        while j < len(d) and d[j] != 0:
            j += 1
        if j > i:
            t = B.decode_with_vars(d[i:j])
            if len(t) >= min_len and B.real_jp(t):
                n += 1
                if len(samples) < 4:
                    samples.append(t[:24])
        i = j + 1
    return n, samples


def main():
    print('트랙 로드 중 (455MB)…', flush=True)
    flat, _ = F.load_flat()
    files = F.load_filetable()
    handled = set(os.listdir('work/dm')) if os.path.isdir('work/dm') else set()

    rows = []
    for path, lba, size in files:
        if size == 0 or size > 4 * 1024 * 1024:
            continue                      # 초대형(그래픽/스트리밍)은 별도 취급
        d = flat[lba * 2048: lba * 2048 + size]
        n, samples = census(d)
        if n == 0:
            continue
        dmname = path[1:].replace('/', '_')
        rows.append((n, path, dmname, dmname in handled, samples))

    rows.sort(reverse=True)
    print('\n%-26s %6s %-8s %s' % ('파일', '문자열', '추출됨', '예시'))
    print('-' * 100)
    tot_new = 0
    for n, path, dmname, done, samples in rows:
        mark = 'O' if done else '★NEW'
        if not done:
            tot_new += n
        print('%-26s %6d %-8s %s' % (path, n, mark, ' | '.join(samples)))
    print('-' * 100)
    print('아직 추출조차 안 된 파일의 문자열 합계: %d' % tot_new)


if __name__ == '__main__':
    main()
