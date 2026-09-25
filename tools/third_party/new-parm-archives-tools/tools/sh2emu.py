#!/usr/bin/env python3
"""sh2emu.py — minimal SH-2 interpreter to RUN resident engine routines.

Rather than hand-port the minigame Huffman tree-builder (0x0601401A and helpers
0x060147C0/0x0601491C/0x06014AC4) from SH-2 assembly — a long, error-prone
translation — we execute the *real* machine code captured in an HWRAM dump. This
removes all reverse-engineering guesswork: the algorithm is exactly the game's.

Memory model: a flat sparse byte space (big-endian). The caller maps the HWRAM
image (code + the cursor variable [0x06014D9C] + the tree output region + stack)
and writes the source blob somewhere addressable, then sets registers and runs
from the entry PC until the matching RTS pops the saved PR (call-depth 0).

Only the opcodes used by those routines are implemented; unknown opcodes raise.
"""
import struct


class Mem:
    def __init__(self):
        self.spaces = []  # (base, bytearray)

    def map(self, base, data):
        self.spaces.append((base, bytearray(data)))

    def _find(self, addr):
        for base, buf in self.spaces:
            if base <= addr < base + len(buf):
                return buf, addr - base
        raise KeyError(f"unmapped address {addr:#010x}")

    def r8(self, a):
        buf, o = self._find(a)
        return buf[o]

    def r16(self, a):
        buf, o = self._find(a)
        return (buf[o] << 8) | buf[o + 1]

    def r32(self, a):
        buf, o = self._find(a)
        return struct.unpack_from(">I", buf, o)[0]

    def w8(self, a, v):
        buf, o = self._find(a)
        buf[o] = v & 0xFF

    def w16(self, a, v):
        buf, o = self._find(a)
        buf[o] = (v >> 8) & 0xFF
        buf[o + 1] = v & 0xFF

    def w32(self, a, v):
        buf, o = self._find(a)
        struct.pack_into(">I", buf, o, v & 0xFFFFFFFF)

    def region(self, base):
        for b, buf in self.spaces:
            if b == base:
                return buf
        raise KeyError(base)


def _u32(v):
    return v & 0xFFFFFFFF


def _s32(v):
    v &= 0xFFFFFFFF
    return v - (1 << 32) if v & 0x80000000 else v


class SH2:
    def __init__(self, mem):
        self.m = mem
        self.R = [0] * 16
        self.PC = 0
        self.PR = 0
        self.T = 0
        self.MACH = 0
        self.MACL = 0
        self.Q = 0
        self.M = 0
        self.steps = 0

    def run(self, entry, max_steps=20_000_000, stop_pr=0xDEADBEEF):
        """Execute from `entry`. Stops when an RTS returns to `stop_pr`."""
        self.PR = stop_pr
        self.PC = entry
        while self.steps < max_steps:
            if self.PC == stop_pr:
                return
            self.step()
        raise RuntimeError("max_steps exceeded")

    def _branch(self, target, delay=True):
        if delay:
            slot_pc = self.PC
            self.PC = target
            # execute delay slot instruction at slot_pc
            self._exec_at(slot_pc, in_delay=True)
        else:
            self.PC = target

    def step(self):
        pc = self.PC
        self.PC = pc + 2
        self._exec_at(pc)

    def _exec_at(self, pc, in_delay=False):
        self.steps += 1
        op = self.m.r16(pc)
        R = self.R
        H = op >> 12
        n = (op >> 8) & 0xF
        m = (op >> 4) & 0xF
        d4 = op & 0xF
        i8 = op & 0xFF
        d8 = op & 0xFF
        i12 = op & 0xFFF

        def s8(v):
            return v - 256 if v >= 128 else v

        def s12(v):
            return v - 4096 if v >= 2048 else v

        if op == 0x000B:  # rts
            t = self.PR
            self._branch(t, delay=True)
            return
        if op == 0x0009:  # nop
            return
        if op == 0x0019:  # div0u
            self.Q = self.M = self.T = 0
            return
        if op == 0x0008:  # clrt
            self.T = 0
            return
        if op == 0x0018:  # sett
            self.T = 1
            return

        if H == 0x0:
            lo = op & 0xF
            if lo == 0xC:  # mov.b @(r0,rm),rn  (sign-extend)
                v = self.m.r8(_u32(R[0] + R[m]))
                R[n] = _u32(v - 256 if v & 0x80 else v)
                return
            if lo == 0xD:  # mov.w @(r0,rm),rn
                v = self.m.r16(_u32(R[0] + R[m]))
                R[n] = _u32(v - 65536 if v & 0x8000 else v)
                return
            if lo == 0xE:  # mov.l @(r0,rm),rn
                R[n] = self.m.r32(_u32(R[0] + R[m]))
                return
            if lo == 0x4:  # mov.b rm,@(r0,rn)
                self.m.w8(_u32(R[0] + R[n]), R[m])
                return
            if lo == 0x5:  # mov.w rm,@(r0,rn)
                self.m.w16(_u32(R[0] + R[n]), R[m])
                return
            if lo == 0x6:  # mov.l rm,@(r0,rn)
                self.m.w32(_u32(R[0] + R[n]), R[m])
                return
            if (op & 0xFF) == 0x29:  # movt rn
                R[n] = self.T
                return
            if (op & 0xFF) == 0x2A:  # sts pr,rn
                R[n] = self.PR
                return
            if (op & 0xFF) == 0x0A:  # sts mach,rn
                R[n] = self.MACH
                return
            if (op & 0xFF) == 0x1A:  # sts macl,rn
                R[n] = self.MACL
                return
        if H == 0x1:  # mov.l rm,@(d4*4,rn)
            self.m.w32(_u32(R[n] + d4 * 4), R[m])
            return
        if H == 0x2:
            t = d4
            if t == 0:
                self.m.w8(R[n], R[m]); return
            if t == 1:
                self.m.w16(R[n], R[m]); return
            if t == 2:
                self.m.w32(R[n], R[m]); return
            if t == 4:
                R[n] = _u32(R[n] - 1); self.m.w8(R[n], R[m]); return
            if t == 5:
                R[n] = _u32(R[n] - 2); self.m.w16(R[n], R[m]); return
            if t == 6:
                R[n] = _u32(R[n] - 4); self.m.w32(R[n], R[m]); return
            if t == 7:  # div0s rm,rn
                self.Q = (R[n] >> 31) & 1
                self.M = (R[m] >> 31) & 1
                self.T = self.Q ^ self.M
                return
            if t == 8:  # tst rm,rn
                self.T = 1 if (R[n] & R[m]) == 0 else 0
                return
            if t == 9:  # and
                R[n] = R[n] & R[m]; return
            if t == 10:  # xor
                R[n] = R[n] ^ R[m]; return
            if t == 11:  # or
                R[n] = R[n] | R[m]; return
            if t == 12:  # cmp/str
                tmp = R[n] ^ R[m]
                self.T = 1 if any(((tmp >> (8 * k)) & 0xFF) == 0 for k in range(4)) else 0
                return
        if H == 0x3:
            t = d4
            if t == 0:  # cmp/eq
                self.T = 1 if R[n] == R[m] else 0; return
            if t == 2:  # cmp/hs (unsigned >=)
                self.T = 1 if _u32(R[n]) >= _u32(R[m]) else 0; return
            if t == 3:  # cmp/ge (signed >=)
                self.T = 1 if _s32(R[n]) >= _s32(R[m]) else 0; return
            if t == 6:  # cmp/hi (unsigned >)
                self.T = 1 if _u32(R[n]) > _u32(R[m]) else 0; return
            if t == 7:  # cmp/gt (signed >)
                self.T = 1 if _s32(R[n]) > _s32(R[m]) else 0; return
            if t == 4:  # div1 rm,rn
                self._div1(m, n); return
            if t == 8:  # sub
                R[n] = _u32(R[n] - R[m]); return
            if t == 10:  # subc
                tmp1 = _u32(R[n] - R[m])
                tmp0 = R[n]
                res = _u32(tmp1 - self.T)
                self.T = 1 if (_u32(tmp0) < _u32(tmp1)) or (_u32(tmp1) < _u32(res)) else 0
                R[n] = res
                return
            if t == 12:  # add
                R[n] = _u32(R[n] + R[m]); return
            if t == 14:  # addc
                tmp1 = _u32(R[n] + R[m])
                res = _u32(tmp1 + self.T)
                self.T = 1 if (_u32(tmp1) < _u32(R[n])) or (_u32(res) < _u32(tmp1)) else 0
                R[n] = res
                return
        if H == 0x4:
            lo = op & 0xFF
            if lo == 0x00:  # shll
                self.T = (R[n] >> 31) & 1; R[n] = _u32(R[n] << 1); return
            if lo == 0x01:  # shlr
                self.T = R[n] & 1; R[n] = R[n] >> 1; return
            if lo == 0x04:  # rotl
                self.T = (R[n] >> 31) & 1; R[n] = _u32((R[n] << 1) | self.T); return
            if lo == 0x05:  # rotr
                self.T = R[n] & 1; R[n] = _u32((R[n] >> 1) | (self.T << 31)); return
            if lo == 0x24:  # rotcl
                oldt = self.T
                self.T = (R[n] >> 31) & 1
                R[n] = _u32((R[n] << 1) | oldt)
                return
            if lo == 0x25:  # rotcr
                oldt = self.T
                self.T = R[n] & 1
                R[n] = _u32((R[n] >> 1) | (oldt << 31))
                return
            if lo == 0x08:  # shll2
                R[n] = _u32(R[n] << 2); return
            if lo == 0x09:  # shlr2
                R[n] = R[n] >> 2; return
            if lo == 0x18:  # shll8
                R[n] = _u32(R[n] << 8); return
            if lo == 0x19:  # shlr8
                R[n] = R[n] >> 8; return
            if lo == 0x28:  # shll16
                R[n] = _u32(R[n] << 16); return
            if lo == 0x29:  # shlr16
                R[n] = R[n] >> 16; return
            if lo == 0x20:  # shal
                self.T = (R[n] >> 31) & 1; R[n] = _u32(R[n] << 1); return
            if lo == 0x21:  # shar
                self.T = R[n] & 1
                R[n] = _u32((R[n] >> 1) | (R[n] & 0x80000000))
                return
            if lo == 0x10:  # dt
                R[n] = _u32(R[n] - 1); self.T = 1 if R[n] == 0 else 0; return
            if lo == 0x11:  # cmp/pz
                self.T = 1 if _s32(R[n]) >= 0 else 0; return
            if lo == 0x15:  # cmp/pl
                self.T = 1 if _s32(R[n]) > 0 else 0; return
            if lo == 0x0B:  # jsr @rn
                t = R[n]
                self.PR = self.PC + 2  # return after delay slot
                self._branch(t, delay=True)
                return
            if lo == 0x2B:  # jmp @rn
                self._branch(R[n], delay=True)
                return
            if lo == 0x2A:  # lds rn,pr
                self.PR = R[n]; return
            if lo == 0x22:  # sts.l pr,@-rn
                R[n] = _u32(R[n] - 4); self.m.w32(R[n], self.PR); return
            if lo == 0x26:  # lds.l @rn+,pr
                self.PR = self.m.r32(R[n]); R[n] = _u32(R[n] + 4); return
            if lo == 0x0A:  # lds rn,mach
                self.MACH = R[n]; return
            if lo == 0x1A:  # lds rn,macl
                self.MACL = R[n]; return
        if H == 0x5:  # mov.l @(d4*4,rm),rn
            R[n] = self.m.r32(_u32(R[m] + d4 * 4)); return
        if H == 0x6:
            t = d4
            if t == 0:  # mov.b @rm,rn (sign)
                v = self.m.r8(R[m]); R[n] = _u32(v - 256 if v & 0x80 else v); return
            if t == 1:  # mov.w @rm,rn
                v = self.m.r16(R[m]); R[n] = _u32(v - 65536 if v & 0x8000 else v); return
            if t == 2:  # mov.l @rm,rn
                R[n] = self.m.r32(R[m]); return
            if t == 3:  # mov rm,rn
                R[n] = R[m]; return
            if t == 4:  # mov.b @rm+,rn
                v = self.m.r8(R[m]); R[n] = _u32(v - 256 if v & 0x80 else v); R[m] = _u32(R[m] + 1); return
            if t == 5:
                v = self.m.r16(R[m]); R[n] = _u32(v - 65536 if v & 0x8000 else v); R[m] = _u32(R[m] + 2); return
            if t == 6:
                R[n] = self.m.r32(R[m]); R[m] = _u32(R[m] + 4); return
            if t == 7:  # not
                R[n] = _u32(~R[m]); return
            if t == 11:  # neg
                R[n] = _u32(-R[m]); return
            if t == 12:  # extu.b
                R[n] = R[m] & 0xFF; return
            if t == 13:  # extu.w
                R[n] = R[m] & 0xFFFF; return
            if t == 14:  # exts.b
                v = R[m] & 0xFF; R[n] = _u32(v - 256 if v & 0x80 else v); return
            if t == 15:  # exts.w
                v = R[m] & 0xFFFF; R[n] = _u32(v - 65536 if v & 0x8000 else v); return
        if H == 0x7:  # add #imm,rn
            R[n] = _u32(R[n] + s8(i8)); return
        if H == 0x8:
            sub = (op >> 8) & 0xF
            if sub == 0:  # mov.b r0,@(d4,rm)
                self.m.w8(_u32(R[m] + d4), R[0]); return
            if sub == 1:  # mov.w r0,@(d4*2,rm)
                self.m.w16(_u32(R[m] + d4 * 2), R[0]); return
            if sub == 4:  # mov.b @(d4,rm),r0
                v = self.m.r8(_u32(R[m] + d4)); R[0] = _u32(v - 256 if v & 0x80 else v); return
            if sub == 5:  # mov.w @(d4*2,rm),r0
                v = self.m.r16(_u32(R[m] + d4 * 2)); R[0] = _u32(v - 65536 if v & 0x8000 else v); return
            if sub == 8:  # cmp/eq #imm,r0
                self.T = 1 if _s32(R[0]) == s8(i8) else 0; return
            if sub == 9:  # bt
                if self.T:
                    self._branch(pc + 4 + s8(i8) * 2, delay=False)
                return
            if sub == 0xB:  # bf
                if not self.T:
                    self._branch(pc + 4 + s8(i8) * 2, delay=False)
                return
            if sub == 0xD:  # bt/s
                if self.T:
                    self._branch(pc + 4 + s8(i8) * 2, delay=True)
                return
            if sub == 0xF:  # bf/s
                if not self.T:
                    self._branch(pc + 4 + s8(i8) * 2, delay=True)
                return
        if H == 0x9:  # mov.w @(d8*2,pc),rn (sign-extended)
            v = self.m.r16(pc + 4 + d8 * 2)
            R[n] = _u32(v - 65536 if v & 0x8000 else v); return
        if H == 0xA:  # bra
            self._branch(pc + 4 + s12(i12) * 2, delay=True); return
        if H == 0xB:  # bsr
            self.PR = self.PC + 2
            self._branch(pc + 4 + s12(i12) * 2, delay=True); return
        if H == 0xC:
            sub = (op >> 8) & 0xF
            if sub == 8:  # tst #imm,r0
                self.T = 1 if (R[0] & i8) == 0 else 0; return
            if sub == 9:  # and #imm,r0
                R[0] = R[0] & i8; return
            if sub == 10:  # xor
                R[0] = R[0] ^ i8; return
            if sub == 11:  # or
                R[0] = R[0] | i8; return
            if sub == 7:  # mova @(d8*4,pc),r0
                R[0] = ((pc & ~3) + 4 + d8 * 4); return
        if H == 0xD:  # mov.l @(d8*4,pc),rn
            R[n] = self.m.r32(((pc & ~3) + 4 + d8 * 4)); return
        if H == 0xE:  # mov #imm,rn
            R[n] = _u32(s8(i8)); return

        raise NotImplementedError(f"opcode {op:04x} at {pc:08x}")

    def _div1(self, m, n):
        # Faithful SH-2 DIV1 (single-step divide).
        R = self.R
        old_q = self.Q
        self.Q = (R[n] >> 31) & 1
        tmp2 = R[m]
        R[n] = _u32((R[n] << 1) | self.T)
        if old_q == 0:
            if self.M == 0:
                tmp0 = R[n]
                R[n] = _u32(R[n] - tmp2)
                tmp1 = 1 if _u32(R[n]) > _u32(tmp0) else 0
                self.Q = tmp1 if self.Q == 0 else (1 - tmp1)
            else:
                tmp0 = R[n]
                R[n] = _u32(R[n] + tmp2)
                tmp1 = 1 if _u32(R[n]) < _u32(tmp0) else 0
                self.Q = (1 - tmp1) if self.Q == 0 else tmp1
        else:
            if self.M == 0:
                tmp0 = R[n]
                R[n] = _u32(R[n] + tmp2)
                tmp1 = 1 if _u32(R[n]) < _u32(tmp0) else 0
                self.Q = tmp1 if self.Q == 0 else (1 - tmp1)
            else:
                tmp0 = R[n]
                R[n] = _u32(R[n] - tmp2)
                tmp1 = 1 if _u32(R[n]) > _u32(tmp0) else 0
                self.Q = (1 - tmp1) if self.Q == 0 else tmp1
        self.T = 1 if self.Q == self.M else 0
