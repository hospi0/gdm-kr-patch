# -*- coding: utf-8 -*-
r"""전투 BBG 9구역 글 묶음 — 반각 이름 한글화(8×8 한글 훅용 2바이트) + 전각 이름 온전히 (2026-10-16).

  구역 0 명령(반각)·1 기술·마법(반각)·5 도구(반각) → half_ko.encode(work/trans/half_names.tsv)
  구역 3 기술·마법(전각, 시전 띠)·6 도구(전각) → bintext.encode(같은 번역) — 예전 바이트 칸 축약(플레아 등)을 풀고 온전한 이름
  짝 맞추기 = «원본» 구역 3·6 의 전각 원문(순번 1:1, 구역 1↔3 128개, 5↔6 512개). 구역 0 은 반각 원문 해독으로.
  묶음 전체 길이는 고정(게임이 LWRAM 고정 자리로 복사) — 구역 경계는 머리표를 다시 쓰고, 남는 자리는 묶음 끝에 0.
  나머지 구역(2·4·7·8)은 지금 빌드(build_batle 등 결과) 그대로. 묶음 밖 바이트 불변.
  build_all: build_battle_gfx(BBG 이름표) **뒤**.
  python tools/build_bbg_half.py [--dry]
"""
import csv
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import bbg_text as T
import bintext as B
import half_ko as K
from runs_build import load_maps

_, KO = load_maps()


def names():
    m = {}
    for r in csv.DictReader(open(os.path.join(ROOT, 'work', 'trans', 'half_names.tsv'), encoding='utf-8'), delimiter='\t'):
        m[r['원문']] = r['번역']
    return m


def H(t):
    """반각용: 반각 글꼴에 없는 『』！ 정리(원래 반각도 괄호 없이 `おうえんガンバ` 꼴)"""
    return K.encode(t.replace('『', ' ').replace('』', '').replace('！', '!'))


def half_decode_ko(bs):
    """우리가 넣은 반각(한글 2바이트 + ASCII) → 글 (검산용)"""
    syl = K.syllables(); out = []; i = 0
    while i < len(bs):
        c = bs[i]
        if c in K.LEADS:
            out.append(syl[K.decode_index(c, bs[i + 1])]); i += 2
        else:
            out.append(chr(c) if 0x20 <= c < 0x7F else '{%02X}' % c); i += 1
    return ''.join(out)


def join(strs):
    return b''.join(s + b'\x00' for s in strs)


def rebuild(orig, cur, N, stub6=False):
    off, ln = T.locate(orig)
    So = T.sections(orig, off, ln)
    Sc = T.sections(cur, off, ln)
    o0, o1, o5 = (T.strings(So[i]) for i in (0, 1, 5))
    o3, o6 = (T.fw_split(So[i])[:-1] for i in (3, 6))   # 전각 = 글자 단위
    # 지금 빌드 구역을 0 으로 쪼갠 조각 그대로(끝의 0 덧붙임까지) — 바꾼 조각만 갈아 끼우고 b'\x00'.join 으로 되돌린다
    c0, c1, c5 = (Sc[i].split(b'\x00') for i in (0, 1, 5))
    c3, c6 = (T.fw_split(Sc[i]) for i in (3, 6))
    for o, c in ((o0, c0), (o1, c1), (o3, c3), (o5, c5), (o6, c6)):
        assert len(c) > len(o), (len(c), len(o))
    expect = {}
    n0, n1, n3, n5, n6 = list(c0), list(c1), list(c3), list(c5), list(c6)
    miss = set()
    for i, s in enumerate(o0):
        jp = T.decode_half(s)
        if jp in N:
            n0[i] = H(N[jp]); expect[(0, i)] = half_decode_ko(H(N[jp]))
        elif jp.strip('?'):
            miss.add(jp)
    for i, s in enumerate(o3):
        jp = B.decode(s).strip()
        if not jp:
            continue
        if jp in N:
            n3[i] = B.encode(N[jp].replace('+', '十'), KO)
            if i < len(n1):
                n1[i] = H(N[jp]); expect[(1, i)] = half_decode_ko(H(N[jp]))
        else:
            miss.add(jp)
    for i, s in enumerate(o6):
        jp = B.decode(s).strip()
        if not jp:
            continue
        if jp == '禁':                    # 안 쓰는 아이템 번호의 채움 칸 — 반각·전각 둘 다 빈 문자열(순번 유지, 자리 확보)
            n6[i] = b''
            if i < len(n5):
                n5[i] = b''
            continue
        if jp in N:
            # 구역 6(전각 도구 이름)은 전투에서 안 읽힘(영문 패치 읽기 감시 0회) — 넘침 때문에 지금 빌드 그대로 둔다
            if i < len(n5):
                n5[i] = H(N[jp]); expect[(5, i)] = half_decode_ko(H(N[jp]))
        else:
            miss.add(jp)
    secs = list(Sc)
    # 설명·기타 구역(2·4·7)의 문자열 끝 공백 걷기 — 예전 제자리 빌드가 원문 길이까지 0x20 으로 채운 것(묶음을 다시 짜니 필요 없음)
    for k in (2, 4, 7):
        secs[k] = b'\x00'.join(T.fw_rstrip(x) for x in T.fw_split(Sc[k]))
    n6 = [T.fw_rstrip(x) for x in n6]
    secs[0], secs[1], secs[3], secs[5], secs[6] = (b'\x00'.join(x) for x in (n0, n1, n3, n5, n6))
    # ★구역 시작은 4의 배수로(게임이 머리표 오프셋을 &~3 해서 쓴다 — WDATA 실기에서 순번 2칸 밀림 2026-10-16)
    for k in range(8):
        secs[k] = secs[k] + b'\x00' * (-len(secs[k]) % 4)
    body = b''.join(secs)
    total = 0x24 + len(body)
    if total > ln and stub6:
        # 예비책(시험 전투 BTEST 전용): 구역 6(전각 도구 이름) 문자열을 비운다 — 순번(널 개수)은 유지
        secs[6] = b'\x00'.join(b'' for _ in n6)
        secs[6] += b'\x00' * (-len(secs[6]) % 4)
        body = b''.join(secs); total = 0x24 + len(body)
    if total > ln:
        raise SystemExit('묶음 넘침 %d > %d' % (total, ln))
    hdr = []; p = 0x24
    for s in secs:
        hdr.append(p); p += len(s)
    item = b''.join(struct.pack('>I', h) for h in hdr) + body + b'\x00' * (ln - total)
    out = bytearray(cur); out[off:off + ln] = item
    return bytes(out), off, ln, expect, miss, ln - total


def verify(data, off, ln, expect, cur):
    S = T.sections(data, off, ln); bad = 0
    for (sec, i), want in expect.items():
        got = half_decode_ko(T.strings(S[sec])[i])
        if got != want:
            bad += 1
            if bad < 5:
                print('    ✗ 구역%d #%d %r != %r' % (sec, i, got, want))
    Sc = T.sections(cur, off, ln)
    for k in (2, 4, 7, 8):
        a_, b_ = [T.fw_rstrip(x) for x in T.fw_split(S[k])], [T.fw_rstrip(x) for x in T.fw_split(Sc[k])]
        while a_ and a_[-1] == b'': a_.pop()
        while b_ and b_[-1] == b'': b_.pop()
        if a_ != b_:
            bad += 1; print('    ✗ 구역%d 바뀜' % k)
    if data[:off] != cur[:off] or data[off + ln:] != cur[off + ln:]:
        bad += 1; print('    ✗ 묶음 밖 바뀜')
    return bad


def main():
    dry = '--dry' in sys.argv
    N = names()
    files = sorted(f for f in os.listdir(os.path.join(ROOT, 'work', 'dm')) if f.endswith('.BBG'))
    allmiss = set(); nbad = 0; slack = []
    for f in files:
        orig = open(os.path.join(ROOT, 'work', 'dm', f), 'rb').read()
        bp = os.path.join(ROOT, 'work', 'build', f)
        cur = open(bp, 'rb').read() if os.path.exists(bp) else orig
        try:
            new, off, ln, expect, miss, left = rebuild(orig, cur, N, stub6=(f == 'BATLE_BTEST.BBG'))
        except SystemExit as e:
            print('  ★%s: %s' % (f, e)); nbad += 1; continue
        allmiss |= miss
        bad = verify(new, off, ln, expect, cur)
        nbad += bad; slack.append(left)
        if not dry:
            open(bp, 'wb').write(new)
    print('BBG %d개  반각 %d문자열  여유 %d‥%d B  검산 불일치 %d' % (len(files), len(expect), min(slack), max(slack), nbad))
    if allmiss:
        print('  번역 없음(원문 유지) %d: %s' % (len(allmiss), ' / '.join(sorted(allmiss))[:400]))
    if nbad:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
