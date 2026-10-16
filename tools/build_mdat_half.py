# -*- coding: utf-8 -*-
r"""`BATLE/M_DAT.BIN` 적 이름·기술의 «반각» 칸 한글화 (2026-10-16) — 전투 상태창 NAME·ACTION.

레코드: 전각 문자열(build_mdat 가 번역) 바로 앞에 반각 칸이 고정 폭으로 붙어 있다(끝 널 포함).
  적 이름 = 전각 −10 바이트부터 10 B(예 0xD2996 `ｸﾞﾚｰﾄﾍﾞﾚｰ` · 0xD29A0 전각) / 기술 = −8 바이트부터 8 B.
  칸 시작 = 전각 앞의 0 런을 거슬러 올라간 뒤, 반각 글자(0x20 이상)를 −10 까지 거슬러 간 자리.
번역 = mdat_ko.json(전각과 같은 표). ★사용자 2026-10-16: «띄어쓰기 삭제 + 칸 바이트 수에 맞춰 앞에서 자르기만,
  다른 말로 바꾸지 말 것». 한글 2바이트(half_ko)·ASCII 1바이트, 칸 폭 −1 까지, 남는 자리 0.
build_all: build_mdat **뒤**.  python tools/build_mdat_half.py [--dry]
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import bintext as B
import bbg_text as T
import half_ko as K

FN = 'BATLE_M_DAT.BIN'


def fit(ko, budget):
    out = b''; txt = ''
    for ch in ko.replace(' ', ''):
        e = K.encode(ch)
        if len(out) + len(e) > budget:
            break
        out += e; txt += ch
    return out, txt


def main():
    dry = '--dry' in sys.argv
    table = json.load(open(os.path.join(ROOT, 'work', 'trans', 'mdat_ko.json'), encoding='utf-8'))
    orig = open(os.path.join(ROOT, 'work', 'dm_all', FN), 'rb').read()      # 원본과 바이트 일치(build_mdat 주석)
    bp = os.path.join(ROOT, 'work', 'build', FN)
    cur = bytearray(open(bp, 'rb').read() if os.path.exists(bp) else orig)
    assert len(cur) == len(orig)
    raws = {}
    start = 0
    for i, b in enumerate(orig):                    # build_mdat 와 같은 방식으로 전각 원문 바이트열 수집
        if b == 0:
            if 4 <= i - start <= 40:
                try:
                    s = B.decode(orig[start:i])
                except Exception:
                    s = None
                if s in table:
                    raws.setdefault(orig[start:i], table[s])
            start = i + 1
    n = cut = skip = 0; touched = set(); samples = []
    for raw, ko in raws.items():
        pos = orig.find(raw)
        while pos != -1:
            if orig[pos + len(raw)] == 0 and orig[pos - 1] == 0:
                j = pos
                while j > pos - 10 and orig[j - 1] == 0:
                    j -= 1
                s = j
                while s > pos - 10 and orig[s - 1] >= 0x20:
                    s -= 1
                width = pos - s
                hw = orig[s:j]
                if width in (8, 10) and hw and all(c >= 0x20 for c in hw):
                    new, txt = fit(ko, width - 1)
                    cur[s:pos] = new + bytes(width - len(new))
                    touched.update(range(s, pos)); n += 1
                    if len(new) < len(K.encode(ko.replace(' ', ''))):
                        cut += 1
                        if len(samples) < 12 and ('%s' % ko) not in ' '.join(samples):
                            samples.append('%s→%s' % (ko, txt))
                else:
                    skip += 1
            pos = orig.find(raw, pos + 1)
    # 칸 밖 변화 0 (build_mdat 결과와 비교)
    prev = open(bp, 'rb').read() if os.path.exists(bp) else orig
    leak = sum(1 for i in range(len(cur)) if cur[i] != prev[i] and i not in touched)
    print('%s  반각 칸 %d  (잘림 %d, 칸 못 찾음 %d)  칸 밖 변화 %d' % (FN, n, cut, skip, leak))
    if samples:
        print('  잘림 예: ' + ' / '.join(samples))
    if leak:
        raise SystemExit(1)
    if not dry:
        open(bp, 'wb').write(bytes(cur))


if __name__ == '__main__':
    main()
