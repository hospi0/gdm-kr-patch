#!/usr/bin/env python3
"""sh2dis.py — minimal Hitachi SH-2 disassembler (enough to read engine routines).

Usage: sh2dis.py FILE.bin --base 0x06000000 --start 0x06015DF0 [--count 220]
FILE is a flat memory image whose first byte is at --base.
"""
import argparse, struct

def d(op, pc):
    n=(op>>8)&0xF; m=(op>>4)&0xF; i8=op&0xFF; d8=op&0xFF; d4=op&0xF; i12=op&0xFFF
    def s8(v): return v-256 if v>=128 else v
    def s12(v): return v-4096 if v>=2048 else v
    H=op>>12
    # full-match specials
    if op==0x000b: return "rts"
    if op==0x0009: return "nop"
    if op==0x001b: return "sleep"
    if op==0x002b: return "rte"
    if op==0x0008: return "clrt"
    if op==0x0018: return "sett"
    if op==0x0028: return "clrmac"
    if op==0x0019: return "div0u"
    # 0xF000 region by low nibble
    if H==0x0:
        if (op&0xF)==0xC: return f"mov.b @(r0,r{m}),r{n}"
        if (op&0xF)==0xD: return f"mov.w @(r0,r{m}),r{n}"
        if (op&0xF)==0xE: return f"mov.l @(r0,r{m}),r{n}"
        if (op&0xF)==0x4: return f"mov.b r{m},@(r0,r{n})"
        if (op&0xF)==0x5: return f"mov.w r{m},@(r0,r{n})"
        if (op&0xF)==0x6: return f"mov.l r{m},@(r0,r{n})"
        if (op&0xF)==0x7: return f"mul.l r{m},r{n}"
        if (op&0xFF)==0x29: return f"movt r{n}"
        if (op&0xFF)==0x2A: return f"sts pr,r{n}"
        if (op&0xFF)==0x0A: return f"sts mach,r{n}"
        if (op&0xFF)==0x1A: return f"sts macl,r{n}"
        if (op&0xFF)==0x23: return f"braf r{n}"
        if (op&0xFF)==0x03: return f"bsrf r{n}"
        if (op&0xFF)==0x02: return f"stc sr,r{n}"
    if H==0x1: return f"mov.l r{m},@({d4*4},r{n})"
    if H==0x2:
        t={0:"mov.b r%d,@r%d",1:"mov.w r%d,@r%d",2:"mov.l r%d,@r%d",
           4:"mov.b r%d,@-r%d",5:"mov.w r%d,@-r%d",6:"mov.l r%d,@-r%d",
           7:"div0s r%d,r%d",8:"tst r%d,r%d",9:"and r%d,r%d",10:"xor r%d,r%d",
           11:"or r%d,r%d",12:"cmp/str r%d,r%d",13:"xtrct r%d,r%d",
           14:"mulu.w r%d,r%d",15:"muls.w r%d,r%d"}
        if d4 in t: return t[d4]%(m,n)
    if H==0x3:
        t={0:"cmp/eq r%d,r%d",2:"cmp/hs r%d,r%d",3:"cmp/ge r%d,r%d",
           4:"div1 r%d,r%d",5:"dmulu.l r%d,r%d",6:"cmp/hi r%d,r%d",7:"cmp/gt r%d,r%d",
           8:"sub r%d,r%d",10:"subc r%d,r%d",11:"subv r%d,r%d",12:"add r%d,r%d",
           13:"dmuls.l r%d,r%d",14:"addc r%d,r%d",15:"addv r%d,r%d"}
        if d4 in t: return t[d4]%(m,n)
    if H==0x4:
        lo=op&0xFF
        u={0x00:"shll",0x01:"shlr",0x04:"rotl",0x05:"rotr",0x08:"shll2",0x09:"shlr2",
           0x18:"shll8",0x19:"shlr8",0x28:"shll16",0x29:"shlr16",0x20:"shal",0x21:"shar",
           0x24:"rotcl",0x25:"rotcr",0x10:"dt",0x11:"cmp/pz",0x15:"cmp/pl",
           0x0b:"jsr @r%d",0x2b:"jmp @r%d",0x0e:"ldc r%d,sr",0x1e:"ldc r%d,gbr",
           0x0a:"lds r%d,mach",0x1a:"lds r%d,macl",0x2a:"lds r%d,pr",
           0x06:"lds.l @r%d+,mach",0x16:"lds.l @r%d+,macl",0x26:"lds.l @r%d+,pr",
           0x22:"sts.l pr,@-r%d",0x07:"ldc.l @r%d+,sr",0x17:"ldc.l @r%d+,gbr",
           0x0f:"mac.w @r%d+,@r%d+",0x1f:"mac.l"}
        if lo in u:
            s=u[lo]
            return s%n if '%d' in s else f"{s} r{n}"
    if H==0x5: return f"mov.l @({d4*4},r{m}),r{n}"
    if H==0x6:
        t={0:"mov.b @r%d,r%d",1:"mov.w @r%d,r%d",2:"mov.l @r%d,r%d",3:"mov r%d,r%d",
           4:"mov.b @r%d+,r%d",5:"mov.w @r%d+,r%d",6:"mov.l @r%d+,r%d",7:"not r%d,r%d",
           8:"swap.b r%d,r%d",9:"swap.w r%d,r%d",10:"negc r%d,r%d",11:"neg r%d,r%d",
           12:"extu.b r%d,r%d",13:"extu.w r%d,r%d",14:"exts.b r%d,r%d",15:"exts.w r%d,r%d"}
        if d4 in t: return t[d4]%(m,n)
    if H==0x7: return f"add #{s8(i8)},r{n}"
    if H==0x8:
        sub=(op>>8)&0xF
        if sub==0: return f"mov.b r0,@({d4},r{m})"
        if sub==1: return f"mov.w r0,@({d4*2},r{m})"
        if sub==4: return f"mov.b @({d4},r{m}),r0"
        if sub==5: return f"mov.w @({d4*2},r{m}),r0"
        if sub==8: return f"cmp/eq #{s8(i8)},r0"
        if sub==9: return f"bt {pc+4+s8(i8)*2:08x}"
        if sub==0xb: return f"bf {pc+4+s8(i8)*2:08x}"
        if sub==0xd: return f"bt/s {pc+4+s8(i8)*2:08x}"
        if sub==0xf: return f"bf/s {pc+4+s8(i8)*2:08x}"
    if H==0x9: return f"mov.w @({d8*2},pc),r{n}  ; [{pc+4+d8*2:08x}]"
    if H==0xA: return f"bra {pc+4+s12(i12)*2:08x}"
    if H==0xB: return f"bsr {pc+4+s12(i12)*2:08x}"
    if H==0xC:
        sub=(op>>8)&0xF
        t={0:f"mov.b r0,@({d8},gbr)",1:f"mov.w r0,@({d8*2},gbr)",2:f"mov.l r0,@({d8*4},gbr)",
           3:f"trapa #{i8}",4:f"mov.b @({d8},gbr),r0",5:f"mov.w @({d8*2},gbr),r0",
           6:f"mov.l @({d8*4},gbr),r0",7:f"mova @({d8*4},pc),r0",8:f"tst #{i8},r0",
           9:f"and #{i8},r0",10:f"xor #{i8},r0",11:f"or #{i8},r0",12:f"tst.b #{i8},@(r0,gbr)",
           13:f"and.b #{i8},@(r0,gbr)",14:f"xor.b #{i8},@(r0,gbr)",15:f"or.b #{i8},@(r0,gbr)"}
        if sub in t: return t[sub]
    if H==0xD: return f"mov.l @({d8*4},pc),r{n}  ; [{(pc&~3)+4+d8*4:08x}]"
    if H==0xE: return f"mov #{s8(i8)},r{n}"
    if H==0xF: return f".word {op:04x} (fpu?)"
    return f".word {op:04x}"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("file"); ap.add_argument("--base",default="0x06000000")
    ap.add_argument("--start",required=True); ap.add_argument("--count",type=int,default=200)
    a=ap.parse_args()
    base=int(a.base,0); start=int(a.start,0)
    data=open(a.file,'rb').read()
    pc=start
    for _ in range(a.count):
        o=pc-base
        if o+2>len(data): break
        op=struct.unpack('>H',data[o:o+2])[0]
        print(f"{pc:08x}: {op:04x}  {d(op,pc)}")
        pc+=2

if __name__=="__main__": main()
