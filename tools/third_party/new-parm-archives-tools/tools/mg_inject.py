#!/usr/bin/env python3
"""Size-preserving in-place injector for a Saturn MODE1/2352 track.
Writes an authored file's bytes back into its on-disc sectors (2048 user bytes per
2352 raw sector) at the file's ISO9660 LBA. Refuses if the new size != on-disc size.
  mg_inject.py TRACK_IN TRACK_OUT NAME AUTHORED  [NAME AUTHORED ...]
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import iso, shutil
def inject(track_out, name, authored):
    with open(track_out, "r+b") as f:
        hit = iso.find(f, name)
        if not hit: raise SystemExit(f"NOT FOUND {name}")
        _, lba, size = hit
        data = open(authored, "rb").read()
        if len(data) != size:
            raise SystemExit(f"{name}: size {len(data)} != on-disc {size}")
        nsec = (size + iso.USER_DATA - 1)//iso.USER_DATA
        for i in range(nsec):
            chunk = data[i*iso.USER_DATA:(i+1)*iso.USER_DATA]
            f.seek(iso.raw_offset(lba+i))
            f.write(chunk)
        print(f"injected {name}: {size}B over {nsec} sectors @LBA {lba}")
def main():
    tin, tout = sys.argv[1], sys.argv[2]
    shutil.copyfile(tin, tout)
    args = sys.argv[3:]
    for i in range(0, len(args), 2):
        inject(tout, args[i], args[i+1])
if __name__=="__main__": main()
