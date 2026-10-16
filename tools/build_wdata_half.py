# -*- coding: utf-8 -*-
r"""필드 메뉴 `FIELD/WDATA.DAT`(LWRAM 0x002F0000) — 반각 이름 한글화 + 전각 기술·마법 이름 온전히 (2026-10-16).

WDATA = 전투 BBG 글 묶음과 같은 내용 + 사이사이 이진 구역(머리 BE32×13).
  구역 2 반각 도구(↔원본 3 전각 도구, 순번 1:1) · 3 전각 도구 · 4 도구 설명
  구역 6 반각 기술·마법(↔원본 7) · 7 전각 기술·마법 · 8 기술 설명      (0·1·5·9~12 = 이진, 제자리 고정)
이진 구역은 움직이지 않는다 — 이어진 글 구역 묶음 [2,3,4] / [6,7,8] 을 각자 원래 범위 안에서 다시 채우고 머리표만 고친다
(남는 자리는 묶음 끝에 0). 전각 구역은 글자 단위로 쪼갠다(bbg_text.fw_split — 둘째 바이트 0x00 글자 있음).
build_all: build_wdata(전각 제자리) **뒤**.
  python tools/build_wdata_half.py [--dry]
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import bbg_text as T
import bintext as B
from build_bbg_half import H, KO, half_decode_ko, names

FN = 'FIELD_WDATA.DAT'
GROUPS = [(2, 3, 4), (6, 7, 8)]          # (반각, 전각, 설명)


def secs_of(d):
    hdr = [struct.unpack_from('>I', d, i * 4)[0] for i in range(13)]
    ends = hdr[1:] + [len(d)]
    return hdr, [d[hdr[i]:ends[i]] for i in range(13)]


def main():
    dry = '--dry' in sys.argv
    N = names()
    orig = open(os.path.join(ROOT, 'work', 'dm', FN), 'rb').read()
    bp = os.path.join(ROOT, 'work', 'build', FN)
    cur = open(bp, 'rb').read() if os.path.exists(bp) else orig
    assert len(cur) == len(orig)
    ho, So = secs_of(orig)
    hc, Sc = secs_of(cur)
    assert ho == hc, '머리표가 원본과 다름(이미 다시 짠 파일?) — build_wdata 결과 위에서만 돌린다'
    out = bytearray(cur); newh = list(hc); expect = {}; miss = set(); report = []
    for hw, fw, ds in GROUPS:
        o_fw = T.fw_split(So[fw])[:-1]
        n_hw = Sc[hw].split(b'\x00')
        n_fw = T.fw_split(Sc[fw])
        n_ds = [T.fw_rstrip(x) for x in T.fw_split(Sc[ds])]
        assert len(n_hw) > len(o_fw) - 1 and len(n_fw) > len(o_fw)
        full_fw = list(n_fw)
        for i, s in enumerate(o_fw):
            jp = B.decode(s).strip()
            if not jp:
                continue
            if jp == '禁':
                n_fw[i] = full_fw[i] = b''
                if i < len(n_hw):
                    n_hw[i] = b''
                continue
            if jp not in N:
                miss.add(jp); continue
            full_fw[i] = B.encode(N[jp].replace('+', '十'), KO)
            n_fw[i] = T.fw_rstrip(n_fw[i])
            if i < len(n_hw):
                n_hw[i] = H(N[jp]); expect[(hw, i)] = half_decode_ko(n_hw[i])
        start, end = hc[hw], hc[ds + 1] if ds + 1 < 13 else len(cur)
        span = end - start
        for use_full in (True, False):
            parts = [b'\x00'.join(n_hw), b'\x00'.join(full_fw if use_full else n_fw), b'\x00'.join(n_ds)]
            parts = [x + b'\x00' * (-len(x) % 4) for x in parts[:2]] + parts[2:]   # ★구역 시작 4의 배수(게임이 &~3)
            if sum(map(len, parts)) <= span:
                break
        else:
            raise SystemExit('구역 %s 넘침 %d > %d' % ((hw, fw, ds), sum(map(len, parts)), span))
        blob = b''.join(parts)
        out[start:end] = blob + b'\x00' * (span - len(blob))
        newh[hw] = start; newh[fw] = start + len(parts[0]); newh[ds] = newh[fw] + len(parts[1])
        report.append('[%d,%d,%d] %d/%d B (전각 이름 %s)' % (hw, fw, ds, len(blob), span, '온전' if use_full else '기존 축약'))
    for i, h in enumerate(newh):
        struct.pack_into('>I', out, i * 4, h)
    # 검산
    hn, Sn = secs_of(bytes(out)); bad = 0
    for (k, i), want in expect.items():
        got = half_decode_ko(Sn[k].split(b'\x00')[i])
        if got != want:
            bad += 1
    for k in (0, 1, 5, 9, 10, 11, 12):
        if Sn[k][:len(So[k])] != Sc[k][:len(So[k])] or hn[k] != hc[k]:
            bad += 1; print('  ✗ 이진 구역 %d 바뀜' % k)
    print('%s  %s  반각 %d  검산 불일치 %d' % (FN, ' / '.join(report), len(expect), bad))
    if miss:
        print('  번역 없음(원문 유지) %d: %s' % (len(miss), ' / '.join(sorted(miss))[:300]))
    if bad:
        raise SystemExit(1)
    if not dry:
        open(bp, 'wb').write(bytes(out))


if __name__ == '__main__':
    main()
