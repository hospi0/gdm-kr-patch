#!/usr/bin/env python3
"""mg_logo_author.py — author an English minigame TITLE LOGO into a resolved title
slot and splice it size-preserving. Geometry (w,h,bpp,linear) is recovered offline by
rendering the decoded JP slot (see docs/mgame-format.md per-game table). Clears the
slot's sprite to transparent (index 0) and stamps the English title embossed (dark
outline + bright core), centred; mg_codec.snap_to_tree keeps it inside the fixed tree.
Colourful logos have near-full trees so snapping is essentially lossless.

  mg_logo_author.py DAT BLOB_SRC SLOT_END W H PAL_OFF "TITLE" OUT.dat
                    [--core IDX --outline IDX --scale N --lines "A|B"]
"""
import argparse, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mg_splice, mg_text

def rgbpal(pal):
    out=[]
    for i in range(256):
        v=struct.unpack(">H",pal[i*2:i*2+2])[0]
        out.append(((v&0x1f)<<3,((v>>5)&0x1f)<<3,((v>>10)&0x1f)<<3))
    return out

def stamp(buf,W,H,text,scale,x0,y0,core,outline,gap=1):
    for pas in (0,1):
        cx=x0
        for ch in text.upper():
            g=mg_text.FONT.get(ch,mg_text.FONT[' '])
            for ry,row in enumerate(g):
                for rx,c in enumerate(row):
                    if c=='1':
                        for sy in range(scale):
                            for sx in range(scale):
                                X=cx+rx*scale+sx; Y=y0+ry*scale+sy
                                if pas==0:
                                    for dx in(-1,0,1):
                                        for dy in(-1,0,1):
                                            xx,yy=X+dx,Y+dy
                                            if 0<=xx<W and 0<=yy<H: buf[yy*W+xx]=outline
                                elif 0<=X<W and 0<=Y<H: buf[Y*W+X]=core
            cx+=5*scale+gap*scale

def text_w(s,scale,gap=1): return len(s)*(5*scale+gap*scale)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("dat"); ap.add_argument("blob_src"); ap.add_argument("slot_end")
    ap.add_argument("w",type=int); ap.add_argument("h",type=int); ap.add_argument("pal_off")
    ap.add_argument("lines"); ap.add_argument("out")
    ap.add_argument("--core",type=int,default=101); ap.add_argument("--outline",type=int,default=45)
    ap.add_argument("--scale",type=int,default=3)
    a=ap.parse_args()
    blob_src=int(a.blob_src,0); slot_end=int(a.slot_end,0); pal_off=int(a.pal_off,0)
    W,H=a.w,a.h
    dat=open(a.dat,"rb").read()
    pal=rgbpal(dat[pal_off:pal_off+512])
    buf=bytearray(W*H)  # transparent
    lines=a.lines.split("|")
    total_h=len(lines)*(7*a.scale)+(len(lines)-1)*2*a.scale
    y=(H-total_h)//2
    for ln in lines:
        x=(W-text_w(ln,a.scale))//2
        stamp(buf,W,H,ln,a.scale,x,y,a.core,a.outline); y+=7*a.scale+2*a.scale
    chunks=mg_splice.decode_slot(dat,blob_src)
    orig_len=sum(c["size"] for c in chunks)
    pix=bytes(buf)[:orig_len]
    edits={}; off=0
    for k,c in enumerate(chunks):
        edits[k]=pix[off:off+c["size"]]; off+=c["size"]
    new=mg_splice.patch_slot(dat,blob_src,slot_end,edits,snap=True,palette_rgb=pal)
    open(a.out,"wb").write(new)
    got=mg_splice.slot_pixels(new,blob_src)[:orig_len]
    # render preview
    open(a.out+".pix","wb").write(got)
    print(f"authored logo -> {a.out}  slot-fit OK  decoded={len(got)}B ({W}x{H})")

if __name__=="__main__": main()
