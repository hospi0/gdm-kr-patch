# -*- coding: utf-8 -*-
"""Grandia(새턴) 스프라이트 압축 코덱 — nanash1 `decompress.c` v0.95 이식.

출처: https://github.com/nanash1/Grandia_Saturn  (Sprite Compression)
라이선스: 원문 고지 — "supplied AS IS", 복제·수정·배포 허용, 고지 유지.

## 구조

    [BE16 헤더] [RLE 데이터…] [LUT 9바이트] [LUT 인코딩 데이터…]

* 헤더 상위 2비트 = 모드 (`10`=SUB, `00`=MOV, `01`=XOR)
* 헤더 비트13 = 「LUT 데이터부터 시작」 플래그
* 헤더 하위 13비트 = 헤더 기준 테이블 오프셋
* RLE 는 **0 만** 압축한다. 나머지 값(4비트)은 직전 값과의 델타를 LUT 로 인코딩.

★오프셋은 **유저데이터 기준**(섹터당 2048B)이다. MODE1/2352 원본에서 읽으려면
  `raw = (off//2048)*2352 + 16 + off%2048` 로 환산해야 한다 — `UserImage` 참조.

README 가 알려 준 Digital Museum 디스크의 알려진 위치:
    0x00024634  전투 팝업
    0x00C87248  전투 결과 화면
    0x00CD6B90  전투 휠
"""
import struct

LUT_SEED = (0, 128, 64, 32, 16, 8, 4, 2, 1)
SUB, MOV, XOR = 'SUB', 'MOV', 'XOR'
MAX_DECOMP_LEN = 1 << 20


class UserImage:
    """MODE1/2352 원본을 «유저데이터 연속 스트림»처럼 읽는다."""

    def __init__(self, path, sector=2352, data_off=16, data_len=2048):
        self.f = open(path, 'rb')
        self.S, self.O, self.L = sector, data_off, data_len

    def read(self, off, n):
        out = bytearray()
        while n > 0:
            s, r = divmod(off, self.L)
            k = min(n, self.L - r)
            self.f.seek(s * self.S + self.O + r)
            out += self.f.read(k)
            off += k
            n -= k
        return bytes(out)


def generate_lut(tab):
    """9바이트 압축 테이블 → 256엔트리 디코드 표. 실패 시 None."""
    t = bytearray(tab[:9])
    lut = []
    for _ in range(17):
        best = 0
        ch = 0
        for i in range(17):
            b = (t[i // 2] & 0xF) if i % 2 else (t[i // 2] >> 4)
            if b > best:
                best, ch = b, i
        if best > 8:
            return None
        if best == 0:
            break
        if ch % 2:
            t[ch // 2] &= 0xF0
        else:
            t[ch // 2] &= 0x0F
        elem = (ch << 8) | (best << 4)
        if ch == 16:
            elem += 1
        lut += [elem] * LUT_SEED[best]
    return lut if len(lut) == 256 else None


def _fetch(shift_code, lut_data, buf):
    """8비트 슬라이딩 창을 읽는다. (index, shift_code, lut_data) 를 돌려준다."""
    sc = shift_code >> 4
    if sc > 31:
        lut_data += 4
        sc -= 32
        shift_code = sc << 4
    w0 = struct.unpack_from('>I', buf, lut_data)[0]
    if sc < 25:
        v = w0 >> (24 - sc)
    else:
        w1 = struct.unpack_from('>I', buf, lut_data + 4)[0]
        v = ((w0 << (sc - 24)) | (w1 >> (56 - sc))) & 0xFFFFFFFF
    return (v & 0xFF), shift_code, lut_data


def decompress(buf, off, limit=64000, info=None):
    """`buf` 의 `off` 에서 시작하는 압축 스프라이트를 푼다.

    돌려주는 값: (bytes, mode, lut9, rle_limit)
    `info` 에 dict 를 주면 `rle_end`·`lut_end`·`end`(압축본 끝) 를 채워 준다.
    형식이 아니면 ValueError.
    """
    head = struct.unpack_from('>H', buf, off)[0]
    mode = {0b10: SUB, 0b00: MOV, 0b01: XOR}.get(head >> 14)
    if mode is None:
        raise ValueError('헤더 모드 불명 0x%04X' % head)
    tab_off = head & 0x1FFF
    lut9 = bytes(buf[off + tab_off + 2:off + tab_off + 11])
    lut = generate_lut(lut9)
    if lut is None:
        raise ValueError('테이블 무효')

    out = bytearray(limit)
    op = 0
    rle = off + 2
    lut_data = (off + tab_off + 0xB) & ~3
    shift_code = ((tab_off + 0xB) & 3) << 7

    aligned = False
    nib = 0                 # decoded_bits_num (니블 개수)
    cur = 0                 # 직전 4비트 값
    zeros = 0
    z_cnt = 0
    rle_limit = 0
    runs = 0
    skip_first = bool((head >> 8) & 0x20)

    while True:
        runs += 1
        if runs > MAX_DECOMP_LEN:
            raise ValueError('폭주')
        if not skip_first:
            # --- RLE 니블 읽기 ---
            if aligned:
                p = buf[rle] & 0xF
                rle += 1
                aligned = False
            else:
                p = buf[rle] >> 4
                aligned = True
            if p == 0xD:
                if aligned:
                    zd = buf[rle] & 0xF
                    aligned = False
                    rle += 1
                else:
                    zd = buf[rle] >> 4
                    aligned = True
                zeros += (zd - 1) if zd >= 8 else (zd - 14)
                zeros &= 0xFFFF
            elif p == 0xE:
                if aligned:
                    zeros = (buf[rle] & 0xF) << 4
                    rle += 1
                    zeros |= buf[rle] >> 4
                else:
                    zeros = buf[rle]
                    rle += 1
            elif p == 0xF:
                if aligned:
                    zeros = (buf[rle] & 0xF) << 12
                    rle += 1
                    zeros |= buf[rle] << 4
                    rle += 1
                    zeros |= (buf[rle] & 0xF0) >> 4
                else:
                    zeros = buf[rle] << 8
                    rle += 1
                    zeros |= buf[rle]
                    rle += 1
            else:
                zeros = (zeros + p - 6) & 0xFFFF

            if zeros == 0:
                break
            op += (zeros - 1) // 2 if nib % 2 else zeros // 2
            nib += zeros
        skip_first = False

        # --- LUT 인코딩 데이터 ---
        while True:
            idx, shift_code, lut_data = _fetch(shift_code, lut_data, buf)
            e = lut[idx]
            if e & 1:                       # 정지 조건
                if nib % 2:
                    op += 1
                shift_code += e & 0xF0
                break
            shift_code += e & 0xFF
            v = e >> 8
            if mode == SUB:
                cur = (cur - v) & 0xF
            elif mode == MOV:
                cur = v & 0xF
            else:
                cur = (cur ^ v) & 0xF
            if cur == 0:
                z_cnt += 1
            else:
                rle_limit = max(rle_limit, z_cnt)
                z_cnt = 0
            if nib % 2:
                out[op] |= cur
                op += 1
            else:
                out[op] = cur << 4
            nib += 1
    if info is not None:
        lut_end = lut_data + 4 + ((shift_code >> 4) + 7) // 8
        info.update(rle_end=rle + (1 if aligned else 0),
                    lut_end=lut_end,
                    end=max(rle + (1 if aligned else 0), lut_end))
    return bytes(out[:op]), mode, lut9, rle_limit + 1
