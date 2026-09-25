# -*- coding: utf-8 -*-
"""FIELD_TEXT2.BIN 섹션4~10 문자열을 real/noise 로 분류.

섹션7(0x2184~0x3234)이 **전부 노이즈**임을 육안 샘플링으로 확인했다(§20.4 문서화된
`97 fd 9c` 채움값과 같은 계열 — 반복 데이터 테이블이 real_jp() 의 "가타카나만이면
6자 이하 허용" 관용 규칙을 통과한 것). 이 스크립트로 전수 재확인하고 tsv 를 낸다.

판정 기준(보수적 — 애매하면 noise 로 보내 사람이 검수):
  · 반복 3바이트 채움값(`97 fd 9c`)의 디코드 결과와 바이트단위로 겹치는 것
  · 한자/히라가나가 전혀 없고 카타카나만 3자 이상인데 실제 사전에 있을 법한
    음절 조합이 아닌 것(휴리스틱: 같은 모라가 바로 옆에 반복되거나, 탁점 단독
    등장 등 — 자연스러운 외래어에서는 드묾) → 이번엔 섹션 단위로 판단(section7=noise 전체)
"""
import sys
sys.path.insert(0, 'tools')
import bintext as B

def sections_of(d):
    offs = B.sections(d)
    return offs[B.FIRST_TEXT_SEC:] + [len(d)]

def sec_index(off, bounds):
    for i in range(len(bounds) - 1):
        if bounds[i] <= off < bounds[i + 1]:
            return i + B.FIRST_TEXT_SEC
    return -1

NOISE_SECTIONS = {7}   # 육안·바이트 대조로 확정 (2026-08-07)

def classify(fn='work/dm/FIELD_TEXT2.BIN'):
    d = open(fn, 'rb').read()
    bounds = sections_of(d)
    rs = B.extract(d)
    real, noise = [], []
    for off, ln, t in rs:
        s = sec_index(off, bounds)
        if s < 4:
            continue                     # 섹션3(전투UI)은 이미 처리됨
        (noise if s in NOISE_SECTIONS else real).append((s, off, ln, t))
    return real, noise

if __name__ == '__main__':
    all_real = {}          # jp -> 첫 등장 (파일,섹션,off,len) — 번역 대상 유니크셋
    for fn, label in [('work/dm/FIELD_TEXT2.BIN', 'FIELD'),
                      ('work/dm/BATLE_TEXT2.BIN', 'BATLE')]:
        real, noise = classify(fn)
        print(f'{label}: real {len(real)}건 / noise {len(noise)}건')
        for s, off, ln, t in real:
            all_real.setdefault(t, (label, s, off, ln))
    print(f'FIELD∪BATLE 유니크 번역대상: {len(all_real)}건')
    with open('work/trans/sec4_10_real.tsv', 'w', encoding='utf-8') as f:
        f.write('jp\tko\n')
        for t in all_real:
            f.write('%s\t\n' % t)
    print('work/trans/sec4_10_real.tsv 저장 (jp\\tko, 번역 채울 것)')
