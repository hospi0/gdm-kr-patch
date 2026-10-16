# -*- coding: utf-8 -*-
r"""전투 BBG 안의 9구역 글 묶음(전투 중 LWRAM 0x00239000·0x002BEA58 로 복사) 찾기·나누기·반각 해독 (2026-10-16).

찾기: 영문 패치 battle_sec0._locate 와 같은 방식 — 선두 BE32 오프셋표(디렉터리)를 재귀로 내려가며
      «리더 칸 서명»을 품은 조각의 부모 = 글 묶음. (출처 tools/third_party/new-parm-archives-tools, MIT)
      우리 빌드는 그 서명 주변을 바꿨을 수 있으므로 위치는 늘 «원본(work/dm)» 에서 잡는다.
구역(머리 BE32×9, 첫 값 0x24): 0 명령(반각) · 1 기술·마법 이름(반각) · 2 ? · 3 기술·마법 이름(전각, 시전 띠가 읽음)
      · 4 기술 설명(전각) · 5 도구 이름(반각) · 6 도구 이름(전각) · 7 도구 설명 · 8 ?
반각 8×8 해독: 0xA1~0xDF 표준 반각 가타카나 / 0x86~0x9F = 히라가나(코드+0x20 의 가타카나) / 0xE0~0xFD = 히라가나(코드−0x20).
"""
import os
import struct
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
LEADER_SIG = bytes.fromhex('0397c298a582d004')


def _is_dir(b, base, size):
    if size < 8:
        return None
    first = struct.unpack_from('>I', b, base)[0]
    if first % 4 or not (8 <= first <= min(size, 0x100)):
        return None
    n = first // 4
    offs = [struct.unpack_from('>I', b, base + i * 4)[0] for i in range(n)]
    if any(o > size for o in offs) or offs != sorted(offs):
        return None
    return offs


def locate(b):
    target = b.find(LEADER_SIG)
    if target < 0:
        raise ValueError('리더 칸 서명 없음')
    chain = []

    def rec(base, size):
        offs = _is_dir(b, base, size)
        if offs is None:
            return
        ends = offs + [size]
        for i in range(len(offs)):
            cs, ce = base + offs[i], base + ends[i + 1]
            if cs <= target < ce:
                chain.append((base, i, cs, ce - cs)); rec(cs, ce - cs); return
    rec(0, len(b))
    _, _, off, ln = chain[-2]
    return off, ln


def sections(b, off, ln):
    hdr = [struct.unpack_from('>I', b, off + i * 4)[0] for i in range(9)]
    assert hdr[0] == 0x24, hdr
    ends = hdr[1:] + [ln]
    return [bytes(b[off + hdr[i]: off + ends[i]]) for i in range(9)]


def strings(sec):
    out = sec.split(b'\x00')
    return out[:-1] if out and out[-1] == b'' else out


def _kata(c):
    return bytes([c]).decode('cp932')


def decode_half(bs):
    out = []
    for c in bs:
        if 0x20 <= c < 0x7F:
            out.append(chr(c))
        elif 0xA1 <= c <= 0xDF:
            out.append(_kata(c))
        elif 0x86 <= c <= 0x9F:
            k = unicodedata.normalize('NFKC', _kata(c + 0x20))
            out.append(chr(ord(k) - 0x60) if 'ァ' <= k <= 'ヶ' else k)
        elif 0xE0 <= c <= 0xFD:
            k = unicodedata.normalize('NFKC', _kata(c - 0x20))
            out.append(chr(ord(k) - 0x60) if 'ァ' <= k <= 'ヶ' else k)
        else:
            out.append('{%02X}' % c)
    return unicodedata.normalize('NFKC', ''.join(out)).replace('゙', '゛')


def bbg_files():
    d = os.path.join(ROOT, 'work', 'dm_all')
    return sorted(f for f in os.listdir(d) if f.endswith('.BBG') and f.startswith('BATLE_'))


# ── 전각 구역(2·3·4·6·7·8)은 글자 단위로 쪼갠다: 2바이트 글자의 둘째 바이트가 0x00·0x20 일 수 있다 ──
#    (원본 구역 4 에도 `1x 00` 글자가 있는데 게임이 정상 → 게임도 글자 단위로 문자열을 센다)
def fw_tokens(s):
    out = []; i = 0
    while i < len(s):
        b = s[i]
        if 0x10 <= b <= 0x1F:
            n = 2
        elif 0x0A <= b <= 0x0F:
            n = 3
        elif b == 0x03 and i + 2 < len(s) and s[i + 2] == 0x04:
            n = 3
        else:
            n = 1
        out.append(bytes(s[i:i + n])); i += n
    return out


def fw_split(sec):
    """구역 → 조각 목록(마지막 0 뒤 꼬리 포함, b'\x00'.join 으로 원래대로 돌아간다)"""
    parts, cur = [], bytearray()
    for t in fw_tokens(sec):
        if t == b'\x00':
            parts.append(bytes(cur)); cur = bytearray()
        else:
            cur += t
    parts.append(bytes(cur))
    return parts


def fw_rstrip(s):
    t = fw_tokens(s)
    while t and t[-1] == b' ':
        t.pop()
    return b''.join(t)
