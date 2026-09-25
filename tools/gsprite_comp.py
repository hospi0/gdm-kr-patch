# -*- coding: utf-8 -*-
"""Grandia(새턴) 스프라이트 **압축기** — nanash1 `compress.c` v0.95 이식.

출처·라이선스: https://github.com/nanash1/Grandia_Saturn  (AS IS, 고지 유지)

`gsprite.decompress` 의 역연산. 원본 C 의 정적 변수(`prev_num_zeros`, `val`,
`last_p_input_data` …)까지 그대로 옮겼다 — 여기서 어긋나면 왕복이 깨진다.

검증은 **왕복 테스트**로만 한다: 원본 압축본을 풀고 같은 (모드·표·RLE한계) 로
다시 압축해 **바이트 단위로 일치**하는지 본다([[reference_custom_codec_playbook]]
의 「인코더가 디코더보다 잘 깨진다」).
"""
import struct
import sys

sys.path.insert(0, 'tools')
from gsprite import LUT_SEED, MOV, SUB, XOR


class _Enc(object):
    def __init__(self, data, table, mode, rle_limit):
        self.src = data
        self.pos = 0                      # 니블 단위 입력 위치
        self.eof = False
        self.mode = mode
        self.rle_limit = rle_limit
        self.prev_zeros = 0               # encode_zeros 의 static
        self.val = 0                      # encode_data 의 static
        self._saved = (0, )
        # --- 표 전개 ---
        t = bytearray(table[:9])
        self.off = [0] * 16
        self.sh = [0] * 16
        self.off_stop = self.sh_stop = 0
        cur = 0
        for _ in range(17):
            best = 0
            ch = 0
            for i in range(17):
                b = (t[i // 2] & 0xF) if i % 2 else (t[i // 2] >> 4)
                if b > best:
                    best, ch = b, i
            if best > 8:
                raise ValueError('표 무효(비트수 %d)' % best)
            if best == 0:
                break
            if ch % 2:
                t[ch // 2] &= 0xF0
            else:
                t[ch // 2] &= 0x0F
            if ch == 16:
                self.off_stop, self.sh_stop = cur, best
            else:
                self.off[ch], self.sh[ch] = cur, best
            cur += LUT_SEED[best]
        if cur != 256:
            raise ValueError('표 전개 %d != 256' % cur)
        # --- 출력 버퍼 ---
        n = len(data) * 2 + 4096
        self.rle = bytearray(n)
        self.rp = 0
        self.rbit = 1                     # C 의 rle_bit_pos (1부터)
        self.dlt = bytearray(n)
        self.dp = 0
        self.dbit = 0

    # ---- 입력 ----
    def nib(self):
        if self.pos // 2 > len(self.src) - 1:
            self.eof = True
            return 0
        b = self.src[self.pos // 2]
        v = (b >> 4) if self.pos % 2 == 0 else (b & 0xF)
        self.pos += 1
        return v

    def save(self):
        self._saved = (self.pos, )

    def restore(self):
        self.pos = self._saved[0]

    # ---- RLE 스트림 ----
    def put_rle(self, value, nlen):
        for k in range(nlen - 1, -1, -1):
            self.rle[self.rp] |= ((value >> (k * 4)) & 0xF) << ((self.rbit % 2) * 4)
            if not (self.rbit % 2):
                self.rp += 1
                self.rle[self.rp] = 0
            self.rbit += 1

    def encode_zeros(self, num):
        d = num - self.prev_zeros
        blocks = num // 8
        rest = num % 8
        if -7 < d < 7:
            self.put_rle(d + 6, 1)
        elif -15 < d < 15:
            v = (0xD << 4) | ((d + 1) if d >= 7 else (d + 14))
            self.put_rle(v, 2)
        elif blocks < 32:
            self.put_rle((0xE << 8) | (blocks << 3) | rest, 3)
        else:
            self.put_rle((0xF << 16) | (blocks << 3) | rest, 5)
        self.prev_zeros = num

    # ---- LUT 스트림 ----
    def put_code(self, off, shifts):
        if self.dbit == 0:
            self.dlt[self.dp] = off
        else:
            self.dlt[self.dp] |= off >> self.dbit
            self.dlt[self.dp + 1] |= (off << (8 - self.dbit)) & 0xFF
        self.dbit += shifts
        if self.dbit >= 8:
            self.dbit -= 8
            self.dp += 1

    def encode_data(self, num):
        for _ in range(num):
            nv = self.nib()
            if self.mode == SUB:
                diff = (self.val - nv) & 0xF
            elif self.mode == MOV:
                diff = nv & 0xF
            else:
                diff = (self.val ^ nv) & 0xF
            self.val = nv
            self.put_code(self.off[diff], self.sh[diff])
        self.put_code(self.off_stop, self.sh_stop)

    # ---- 구간 판정 (C 의 test_next_bits 를 그대로) ----
    def test_next(self):
        num = 0
        ref = 1 if self.nib() == 0 else 0
        zc = 0
        sp = self.pos
        while True:
            sp = self.pos
            test = 1 if self.nib() == 0 else 0
            num += 1
            zc = (self.rle_limit - 1) & 0xFF
            # C: while ((!ref && test_bits) && zero_cntr--) — 감소는 조건 안에서
            while True:
                if not ((not ref) and test):
                    break
                old = zc
                zc = (zc - 1) & 0xFF      # 0 이었으면 255 로 감김
                if old == 0:
                    break
                test = 1 if self.nib() == 0 else 0
                num += 1
            # C 의 do{…}while(ref == test_bits && !eof) — 같을 때 «계속»한다
            if ref != test or self.eof:
                break
        zc = (zc + 1) & 0xFF
        if zc == 0:
            num -= self.rle_limit - 1
        if ref:
            self.pos = sp
        return ref, num


def compress(data, table, mode, rle_limit):
    """해제본 `data` 를 압축한다. 돌려주는 값: bytes(헤더 포함 완성본)"""
    e = _Enc(data, table, mode, rle_limit)
    e.rle[0] = 0

    e.save()
    is_zeros, cnt = e.test_next()
    if is_zeros and cnt < rle_limit:
        init = cnt
        _, cnt = e.test_next()
        head = 0x2000
        e.restore()
        e.encode_data(cnt + init)
    else:
        head = 0
        e.restore()

    while not e.eof:
        e.save()
        is_zeros, cnt = e.test_next()
        if is_zeros:
            e.encode_zeros(cnt)
        else:
            e.restore()
            e.encode_data(cnt)

    e.put_rle(0xE00, 3)
    if not (e.rbit % 2):
        e.rp += 1

    if is_zeros:
        e.put_code(e.off_stop, e.sh_stop)
    if e.dbit != 0:
        e.dp += 1

    head |= {SUB: 0b10, MOV: 0b00, XOR: 0b01}[mode] << 14
    head |= e.rp
    return (struct.pack('>H', head) + bytes(e.rle[:e.rp])
            + bytes(table[:9]) + bytes(e.dlt[:e.dp]))
