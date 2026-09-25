#!/usr/bin/env python3
"""Find the linear-bitmap width of an 8bpp decoded sprite by maximizing the
vertical continuity of its transparency (value-0) mask over candidate widths."""
import sys
def find_width(pix, wmin=32, wmax=720, transp=0):
    n=len(pix); best=[]
    for W in range(wmin, wmax+1):
        if n % W: continue
        H=n//W
        if not (8<=H<=400): continue
        mask=[1 if b==transp else 0 for b in pix]
        same=0; tot=0
        for y in range(H-1):
            r0=y*W; r1=r0+W
            for x in range(W):
                tot+=1
                if mask[r0+x]==mask[r1+x]: same+=1
        score=same/tot if tot else 0
        best.append((score,W,H))
    best.sort(reverse=True)
    return best[:8]
if __name__=="__main__":
    pix=open(sys.argv[1],"rb").read()
    for sc,W,H in find_width(pix, int(sys.argv[2]) if len(sys.argv)>2 else 32,
                             int(sys.argv[3]) if len(sys.argv)>3 else 720):
        print(f"W={W} H={H} score={sc:.4f}")
