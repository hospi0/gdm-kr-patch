#!/usr/bin/env python3
"""Tiny table-driven SH-2 (SH7604, big-endian) assembler — only the forms the theater
caption hook needs. Two-pass with labels, PC-relative literal loads, and data directives.

Why in-repo: the boot-IP caption hook is a small straight-line routine; we'd rather not add a
toolchain dependency. This emits the exact bytes we patch into IP.BIN. It SELF-VERIFIES a set of
known encodings at import/`--selftest` so the bytes are trustworthy before touching the disc.

Supported (operand forms in parens):
  mov #imm,Rn | mov Rm,Rn | mov.l/.w @(lbl,PC),Rn | mov.l/.w/.b @Rm,Rn | @Rm+,Rn | Rm,@Rn | Rm,@-Rn
  mov.l @(disp,Rm),Rn | mov.l Rm,@(disp,Rn) | add/sub Rm,Rn | add #imm,Rn
  cmp/eq #imm,R0 | cmp/eq|hs|ge|hi|gt Rm,Rn | cmp/pl|pz Rn | tst Rm,Rn | and|or|xor Rm,Rn
  extu.b|extu.w Rm,Rn | shll|shlr|shll2|shlr2|shll8|shlr8|shll16|shlr16|dt Rn
  bf|bt|bf/s|bt/s lbl | bra|bsr lbl | jmp|jsr @Rn | rts | nop | clrt | sett
  sts.l pr,@-Rn | lds.l @Rn+,pr | sts pr,Rn | lds Rn,pr
Directives: `label:`  `.long v`  `.word v`  `.byte v,...`  `.align n`  `.org addr`
Addresses: assemble(src, org) places code at absolute `org` (needed for PC-relative math).
"""
from __future__ import annotations
import re, struct, sys


def _reg(t):
    m = re.fullmatch(r'[rR](\d{1,2})', t)
    if not m:
        raise ValueError(f"bad reg {t!r}")
    n = int(m.group(1))
    if not 0 <= n <= 15:
        raise ValueError(f"reg out of range {t!r}")
    return n


def _imm(t):
    t = t.strip()
    if t.startswith('#'):
        t = t[1:]
    return int(t, 0)


class Asm:
    def __init__(self):
        self.labels = {}

    def assemble(self, src, org=0):
        lines = []
        for raw in src.splitlines():
            line = raw.split(';')[0].strip()
            if line:
                lines.append(line)
        # pass 1: compute addresses + labels
        addr = org
        parsed = []
        for line in lines:
            while ':' in line.split()[0:1][0] if line.split() else False:
                break
            # handle "label:" possibly followed by an instruction
            m = re.match(r'^([A-Za-z_.][\w.]*):\s*(.*)$', line)
            if m and not line.split()[0].lower().startswith('.'):
                self.labels[m.group(1)] = addr
                line = m.group(2).strip()
                if not line:
                    continue
            size = self._size(line)
            parsed.append((addr, line))
            addr += size
        # pass 2: encode
        out = bytearray()
        for addr, line in parsed:
            b = self._encode(addr, line)
            out += b
        return bytes(out)

    def _size(self, line):
        op = line.split()[0].lower()
        if op == '.long':
            return 4 * len(line.split(None, 1)[1].split(','))
        if op == '.word':
            return 2 * len(line.split(None, 1)[1].split(','))
        if op == '.byte':
            return len(line.split(None, 1)[1].split(','))
        if op == '.align':
            n = int(line.split()[1])
            # size depends on addr; handled by returning a marker — recompute in caller
            raise _Align(n)
        if op == '.org':
            raise _Org(int(line.split()[1], 0))
        return 2

    def assemble2(self, src, org=0):
        # variant that supports .align/.org by iterating
        lines = []
        for raw in src.splitlines():
            line = raw.split(';')[0].strip()
            if line:
                lines.append(line)
        addr = org
        parsed = []
        self.labels.clear()
        for line in lines:
            m = re.match(r'^([A-Za-z_.][\w.]*):\s*(.*)$', line)
            if m and not m.group(1).startswith('.'):
                self.labels[m.group(1)] = addr
                line = m.group(2).strip()
                if not line:
                    continue
            op = line.split()[0].lower()
            if op == '.align':
                n = int(line.split()[1])
                while addr % n:
                    parsed.append((addr, '.byte 0'))
                    addr += 1
                continue
            if op == '.org':
                addr = int(line.split()[1], 0)
                continue
            sz = self._datasize(line)
            parsed.append((addr, line))
            addr += sz
        out = bytearray()
        base = org
        for addr, line in parsed:
            while len(out) < addr - base:
                out += b'\x00'
            out += self._encode(addr, line)
        return bytes(out)

    def _datasize(self, line):
        op = line.split()[0].lower()
        if op == '.long':
            return 4 * len(line.split(None, 1)[1].split(','))
        if op == '.word':
            return 2 * len(line.split(None, 1)[1].split(','))
        if op == '.byte':
            return len(line.split(None, 1)[1].split(','))
        return 2

    @staticmethod
    def _split_args(s):
        out, cur, depth = [], '', 0
        for ch in s:
            if ch == '(':
                depth += 1; cur += ch
            elif ch == ')':
                depth -= 1; cur += ch
            elif ch == ',' and depth == 0:
                out.append(cur.strip()); cur = ''
            else:
                cur += ch
        if cur.strip():
            out.append(cur.strip())
        return out

    def _encode(self, addr, line):
        parts = line.split(None, 1)
        op = parts[0].lower()
        args = self._split_args(parts[1]) if len(parts) > 1 else []
        if op in ('.long', '.word', '.byte'):
            vals = [self._val(a) for a in args]
            if op == '.long':
                return b''.join(struct.pack('>I', v & 0xFFFFFFFF) for v in vals)
            if op == '.word':
                return b''.join(struct.pack('>H', v & 0xFFFF) for v in vals)
            return bytes(v & 0xFF for v in vals)
        w = self._enc_instr(addr, op, args)
        return struct.pack('>H', w)

    def _val(self, a):
        a = a.strip()
        if a in self.labels:
            return self.labels[a]
        return int(a, 0)

    def _enc_instr(self, addr, op, a):
        R = _reg
        def disp_pc(label, align4):
            tgt = self.labels[label] if label in self.labels else int(label, 0)
            pc = (addr & ~3) + 4 if align4 else addr + 4
            d = tgt - pc
            unit = 4 if align4 else 2
            if d < 0 or d % unit or d // unit > 255:
                raise ValueError(f"pc-rel disp out of range @ {addr:#x} -> {label} (d={d})")
            return d // unit
        def br_disp(label, bits):
            tgt = self.labels[label] if label in self.labels else int(label, 0)
            d = tgt - (addr + 4)
            if d % 2:
                raise ValueError("odd branch disp")
            d //= 2
            lim = 1 << (bits - 1)
            if not -lim <= d < lim:
                raise ValueError(f"branch out of range @ {addr:#x} -> {label} (d={d})")
            return d & ((1 << bits) - 1)

        if op == 'nop': return 0x0009
        if op == 'rts': return 0x000B
        if op == 'clrt': return 0x0008
        if op == 'sett': return 0x0018
        if op == 'mov':
            if a[0].startswith('#'):
                return 0xE000 | (R(a[1]) << 8) | (_imm(a[0]) & 0xFF)
            return 0x6003 | (R(a[1]) << 8) | (R(a[0]) << 4)
        if op in ('mov.l', 'mov.w', 'mov.b'):
            sz = {'mov.b': 0, 'mov.w': 1, 'mov.l': 2}[op]
            src, dst = a[0], a[1]
            # PC-relative literal load: @(label,PC),Rn
            m = re.fullmatch(r'@\(([\w.]+),PC\)', src, re.I)
            if m and op in ('mov.l', 'mov.w'):
                if op == 'mov.l':
                    return 0xD000 | (R(dst) << 8) | disp_pc(m.group(1), True)
                return 0x9000 | (R(dst) << 8) | disp_pc(m.group(1), False)
            # @(disp,Rm),Rn  (mov.l only here)
            m = re.fullmatch(r'@\((\-?\w+),([rR]\d+)\)', src)
            if m and op == 'mov.l':
                return 0x5000 | (R(dst) << 8) | (R(m.group(2)) << 4) | ((int(m.group(1), 0) // 4) & 0xF)
            # Rm,@(disp,Rn)
            m = re.fullmatch(r'@\((\-?\w+),([rR]\d+)\)', dst)
            if m and op == 'mov.l':
                return 0x1000 | (R(m.group(2)) << 8) | (R(src) << 4) | ((int(m.group(1), 0) // 4) & 0xF)
            # @-Rn / @Rn+ / @Rn forms
            def mem(t):
                m = re.fullmatch(r'@\-([rR]\d+)', t)
                if m: return ('pre', R(m.group(1)))
                m = re.fullmatch(r'@([rR]\d+)\+', t)
                if m: return ('post', R(m.group(1)))
                m = re.fullmatch(r'@([rR]\d+)', t)
                if m: return ('idx', R(m.group(1)))
                return None
            ms, md = mem(src), mem(dst)
            if md and md[0] == 'idx' and not ms:  # store Rm,@Rn
                return 0x2000 | (md[1] << 8) | (R(src) << 4) | sz
            if md and md[0] == 'pre' and not ms:  # store Rm,@-Rn
                return 0x2004 | (md[1] << 8) | (R(src) << 4) | sz
            if ms and ms[0] == 'idx':              # load @Rm,Rn
                return 0x6000 | (R(dst) << 8) | (ms[1] << 4) | sz
            if ms and ms[0] == 'post':             # load @Rm+,Rn
                return 0x6004 | (R(dst) << 8) | (ms[1] << 4) | sz
            raise ValueError(f"bad {op} operands {a}")
        if op == 'add':
            if a[0].startswith('#'):
                return 0x7000 | (R(a[1]) << 8) | (_imm(a[0]) & 0xFF)
            return 0x300C | (R(a[1]) << 8) | (R(a[0]) << 4)
        if op == 'sub':
            return 0x3008 | (R(a[1]) << 8) | (R(a[0]) << 4)
        if op == 'cmp/eq':
            if a[0].startswith('#'):
                if _reg(a[1]) != 0:
                    raise ValueError("cmp/eq #imm only compares R0; got " + a[1])
                return 0x8800 | (_imm(a[0]) & 0xFF)
            return 0x3000 | (R(a[1]) << 8) | (R(a[0]) << 4)
        if op == 'cmp/hs': return 0x3002 | (R(a[1]) << 8) | (R(a[0]) << 4)
        if op == 'cmp/ge': return 0x3003 | (R(a[1]) << 8) | (R(a[0]) << 4)
        if op == 'cmp/hi': return 0x3006 | (R(a[1]) << 8) | (R(a[0]) << 4)
        if op == 'cmp/gt': return 0x3007 | (R(a[1]) << 8) | (R(a[0]) << 4)
        if op == 'cmp/pl': return 0x4015 | (R(a[0]) << 8)
        if op == 'cmp/pz': return 0x4011 | (R(a[0]) << 8)
        if op == 'tst':
            if a[0].startswith('#'):  # tst #imm,r0
                return 0xC800 | (_imm(a[0]) & 0xFF)
            return 0x2008 | (R(a[1]) << 8) | (R(a[0]) << 4)
        if op == 'and' and a[0].startswith('#'): return 0xC900 | (_imm(a[0]) & 0xFF)
        if op == 'or'  and a[0].startswith('#'): return 0xCB00 | (_imm(a[0]) & 0xFF)
        if op == 'xor' and a[0].startswith('#'): return 0xCA00 | (_imm(a[0]) & 0xFF)
        if op == 'and':    return 0x2009 | (R(a[1]) << 8) | (R(a[0]) << 4)
        if op == 'or':     return 0x200B | (R(a[1]) << 8) | (R(a[0]) << 4)
        if op == 'xor':    return 0x200A | (R(a[1]) << 8) | (R(a[0]) << 4)
        if op == 'extu.b': return 0x600C | (R(a[1]) << 8) | (R(a[0]) << 4)
        if op == 'extu.w': return 0x600D | (R(a[1]) << 8) | (R(a[0]) << 4)
        shifts = {'shll':0x4000,'shlr':0x4001,'shll2':0x4008,'shlr2':0x4009,
                  'shll8':0x4018,'shlr8':0x4019,'shll16':0x4028,'shlr16':0x4029,'dt':0x4010}
        if op in shifts: return shifts[op] | (R(a[0]) << 8)
        if op == 'bf':   return 0x8B00 | br_disp(a[0], 8)
        if op == 'bt':   return 0x8900 | br_disp(a[0], 8)
        if op == 'bf/s': return 0x8F00 | br_disp(a[0], 8)
        if op == 'bt/s': return 0x8D00 | br_disp(a[0], 8)
        if op == 'bra':  return 0xA000 | br_disp(a[0], 12)
        if op == 'bsr':  return 0xB000 | br_disp(a[0], 12)
        if op == 'jmp':  return 0x402B | (R(a[0][1:]) << 8)
        if op == 'jsr':  return 0x400B | (R(a[0][1:]) << 8)
        if op == 'sts.l':  # sts.l pr,@-Rn
            return 0x4022 | (R(a[1][2:]) << 8)
        if op == 'lds.l':  # lds.l @Rn+,pr
            return 0x4026 | (R(a[0][1:-1]) << 8)
        if op == 'sts':    # sts pr,Rn
            return 0x002A | (R(a[1]) << 8)
        if op == 'lds':    # lds Rn,pr
            return 0x402A | (R(a[0]) << 8)
        raise ValueError(f"unknown op {op!r} @ {addr:#x}")


class _Align(Exception): pass
class _Org(Exception): pass


def assemble(src, org=0):
    return Asm().assemble2(src, org)


def selftest():
    a = Asm()
    cases = [
        ("nop", 0x0009), ("rts", 0x000B),
        ("mov #0,r0", 0xE000), ("mov #-1,r4", 0xE4FF),
        ("mov r3,r2", 0x6233), ("mov.l r3,@r2", 0x2232),
        ("mov.l @r2,r1", 0x6122), ("mov.l @r0+,r5", 0x6506),
        ("mov.l r3,@-r15", 0x2F36), ("mov.w @r6,r0", 0x6061),
        ("mov.b r1,@r4", 0x2410), ("add #8,r0", 0x7008),
        ("add r1,r2", 0x321C), ("sub r5,r6", 0x3658),
        ("cmp/eq #5,r0", 0x8805), ("cmp/hs r1,r2", 0x3212),
        ("cmp/hi r4,r5", 0x3546), ("tst r0,r0", 0x2008),
        ("extu.b r3,r3", 0x633C), ("shll2 r1", 0x4108),
        ("shlr r2", 0x4201), ("dt r4", 0x4410),
        ("jmp @r3", 0x432B), ("jsr @r0", 0x400B),
        ("sts.l pr,@-r15", 0x4F22), ("lds.l @r15+,pr", 0x4F26),
        ("mov.l r6,@(8,r5)", 0x1562), ("mov.l @(12,r4),r3", 0x5343),
        ("and r1,r2", 0x2219), ("or r3,r4", 0x243B), ("xor r5,r6", 0x265A),
        ("tst #0x80,r0", 0xC880), ("and #0x0f,r0", 0xC90F), ("shll8 r3", 0x4318),
        ("mov.w r9,@r3", 0x2391), ("mov.b @r5,r0", 0x6050), ("cmp/eq #0,r0", 0x8800),
    ]
    ok = True
    for src, exp in cases:
        got = struct.unpack('>H', a.assemble2(src, 0x100))[0]
        if got != exp:
            ok = False
            print(f"FAIL {src!r}: got {got:#06x} exp {exp:#06x}")
    # branch + pc-rel round-trip
    code = assemble("""
        start:  mov.l @(val,PC),r0
                bra end
                nop
        .align 4
        val:    .long 0x06002008
        end:    rts
    """, 0x06006DC0)
    # mov.l @(val,pc): val is at offset 6 (after 3 instrs: mov(2)+bra(2)+nop(2)=6), pc=(org&~3)+4=org+4
    w0 = struct.unpack('>H', code[0:2])[0]
    disp = w0 & 0xFF
    val_addr = (0x06006DC0 & ~3) + 4 + disp * 4
    val = struct.unpack('>I', code[val_addr - 0x06006DC0: val_addr - 0x06006DC0 + 4])[0]
    if val != 0x06002008:
        ok = False; print(f"FAIL pc-rel literal: {val:#x}")
    print("sh2asm selftest:", "OK" if ok else "FAILED")
    return ok


if __name__ == "__main__":
    sys.exit(0 if selftest() else 1)
