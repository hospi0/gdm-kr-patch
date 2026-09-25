# -*- coding: utf-8 -*-
"""몬스터 도감 화면의 예/아니오 상자·배너가 든 압축 블록을 전 파일에서 찾는다.

⚠️출력은 **파일에 직접** 쓴다. `| tail` 로 파이프하면 끝날 때까지 한 글자도
안 나온다(이 저장소 메모의 「파이프 버퍼링 3종 세트」).
"""
import os
import sys
import time

sys.path.insert(0, 'tools')
from find_sprites import blocks

LOG = 'work/hunt_box2.log'


def main():
    tgt = open('work/gfx/tgt_box2.bin', 'rb').read()
    ban = open('work/gfx/tgt_banner.bin', 'rb').read()
    # ★순서가 중요하다. BBG(전투 배경) 는 파일이 크고 블록이 많아 한 개에 9초씩
    #   걸린다. 박물관 UI 가 들어 있을 법한 파일부터 본다.
    all_f = [f for f in sorted(os.listdir('work/dm_all')) if not f.endswith('GM3.STZ')]

    def rank(f):
        if f.endswith('.BBG'):
            return 3
        if f.endswith('.MDT') or f.endswith('.CPD') or f.endswith('.STB'):
            return 2
        return 0
    files = sorted(all_f, key=lambda f: (rank(f), f))
    t0 = time.time()
    tot = 0
    with open(LOG, 'w', encoding='utf-8') as lg:
        def say(s):
            lg.write(s + '\n')
            lg.flush()
        for i, fn in enumerate(files):
            buf = open('work/dm_all/' + fn, 'rb').read()
            try:
                bs = blocks(buf)
            except Exception as e:
                say('  !! %s %s' % (fn, e))
                continue
            tot += len(bs)
            for off, d, mode, lut, rl in bs:
                a, b = d.find(tgt), d.find(ban)
                if a >= 0 or b >= 0:
                    say('★★ %s 0x%06X %dB %s RLE=%d 표=%s  상자@%s 배너@%s'
                        % (fn, off, len(d), mode, rl, lut.hex(),
                           hex(a) if a >= 0 else '-', hex(b) if b >= 0 else '-'))
            say('[%3d/%d] %-22s 블록 %-3d  누적 %-5d  %.0fs'
                % (i + 1, len(files), fn, len(bs), tot, time.time() - t0))
        say('완료 — 블록 합계 %d' % tot)


if __name__ == '__main__':
    main()
