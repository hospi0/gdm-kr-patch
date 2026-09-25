# -*- coding: utf-8 -*-
"""시스템 메뉴 번역을 CMDMN/SAVER/SVLD/SHOP 에 **개별 제자리 교체**로 반영 + 되읽기 검증.

정책은 `ui_build.py` 와 동일: 원래 널 종단 구간 길이를 넘지 않는 한도 안에서만
교체하고 남는 자리는 0x00 패딩. 대상 밖 바이트는 단 1바이트도 안 바뀐다.

⚠️ 이 파일들은 `work/build/` 에 기존 산출물이 있을 수 있으므로(예: CMDMN 은
propagate_ui_dup 이 이미 건드렸다) **원본이 아니라 work/build/ 가 있으면 그것을
입력으로** 삼아 누적한다 — 안 그러면 앞 단계 번역이 날아간다(§21.6 교훈).
"""
import csv
import os
import sys

sys.path.insert(0, 'tools')
sys.path.insert(0, 'work/trans')
import bintext as B
from runs_build import load_maps
import sysmenu_ko as S

_, KO = load_maps()
SRC, DST = 'work/dm', 'work/build'


def enc_len(t):
    try:
        return len(B.encode_with_vars(t, KO))
    except KeyError:
        return None


def pick(jp, slot):
    for c in S.KO.get(jp, []):
        n = enc_len(c)
        if n is not None and n <= slot:
            return c
    return None


def main():
    rows = list(csv.DictReader(open('work/trans/sysmenu.tsv', encoding='utf-8'), delimiter='\t'))
    byfile = {}
    for r in rows:
        byfile.setdefault(r['file'], []).append((int(r['off'], 16), int(r['len']), r['jp']))

    total_ok = total_skip = 0
    for fname, items in byfile.items():
        base = os.path.join(DST, fname)
        if not os.path.exists(base):
            base = os.path.join(SRC, fname)
        orig_ref = open(os.path.join(SRC, fname), 'rb').read()   # 슬롯 경계는 원본 기준
        d = bytearray(open(base, 'rb').read())
        before = bytes(d)
        applied = []
        skipped = 0
        for off, slot, jp in items:
            ko_text = pick(jp, slot)
            if ko_text is None:
                skipped += 1
                continue
            e = B.encode_with_vars(ko_text, KO)
            d[off:off + slot] = e + b'\x20' * (slot - len(e))   # ★공백 패딩(널 금지)
            applied.append((off, slot, jp, ko_text, e))
        newb = bytes(d)
        if len(newb) != len(before):
            print('★크기 변함!', fname)
            continue
        os.makedirs(DST, exist_ok=True)
        open(os.path.join(DST, fname), 'wb').write(newb)

        # 되읽기 검증
        bad = 0
        touched = bytearray(len(newb))
        for off, slot, jp, ko_text, e in applied:
            want = e + b'\x20' * (slot - len(e))
            if newb[off:off + slot] != want:
                bad += 1
                print('  ★불일치 %s 0x%X' % (fname, off))
            for i in range(off, off + slot):
                touched[i] = 1
        leak = sum(1 for i in range(len(newb))
                   if not touched[i] and newb[i] != before[i])
        print('%-18s 반영 %2d  보류 %d  불일치 %d  대상밖변경 %d'
              % (fname, len(applied), skipped, bad, leak))
        total_ok += len(applied)
        total_skip += skipped

    print('\n합계 반영 %d, 보류 %d' % (total_ok, total_skip))


if __name__ == '__main__':
    main()
