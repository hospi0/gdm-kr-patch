# -*- coding: utf-8 -*-
r"""박물관 화면 머리 금판 배너 4개 한글화 (2026-10-14) — banner_kr.make 공용.
  표정집   「キャラクター表情集」 FIELD_FACE0.DAT  판 코덱(gsprite) 0xB54C → 풀린 6,672 B, 배너 +0x300 144×41  (영문 facer_banner 와 같은 자리)
  설정자료집 「設定資料集」       FIELD_MTOUT.DAT  판 코덱 0x13E00 → 0xC900 B, 배너 +0x1680 144×24        (build_mtout_gfx 와 같은 블록 — 그 결과 위에)
  상영메뉴 「上映メニュー」       FIELD_DORAM.DAT  판 코덱 0x26500 → 0x15000 B, 배너 +0 144×40            (영문 gfx_build_plates 머리)
  몬스터도감 「モンスター図鑑」    FIELD_DICDT.DAT  비압축 raw 0x27AD0 144×40 (스테이트 VDP1 0x492C0 ↔ 디스크 바이트 일치로 찾음)
  재압축 = gsprite_comp(원래 표·모드·RLE), 원래 압축 길이 안(뒤는 원래 바이트 그대로) → 되풀어 검산.
  팔레트 = 각 화면 스테이트 CRAM(work/ttlgfx/pal_*.bin, 색 고르기에만 씀).
  python tools/build_banners.py [--png]   (build_museum·build_mtout_gfx·build_dicdt_gfx 뒤)
"""
import os, sys
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import gsprite as G, gsprite_comp as GC, banner_kr

ITEMS = [  # (이름, 파일, 압축 위치 또는 None=raw, 배너 위치, w, h, 글) — 몬스터 도감 먼저(그 깨끗한 판을 표정집이 씀)
    ('monst', 'FIELD_DICDT.DAT', None, 0x27AD0, 144, 40, '몬스터 도감'),
    ('face', 'FIELD_FACE0.DAT', 0xB54C, 0x300, 144, 41, '캐릭터 표정집'),
    ('mtout', 'FIELD_MTOUT.DAT', 0x13E00, 0x1680, 144, 24, '설정 자료집'),
    ('theater', 'FIELD_DORAM.DAT', 0x26500, 0x0, 144, 40, '상영 메뉴'),   # 자리 빠듯(파일 끝까지 80,624 B) → 판 금색 NGOLD 개로
]

MON_PLATE = []
REUSE_MON = True                                   # 표정집 = 몬스터 도감 판 그대로(사용자 지시 2026-10-14)
NGOLD = {'theater': int(next((a.split('=')[1] for a in sys.argv if a.startswith('--ngold=')), '8'))}


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    prev = []
    for nm, f, comp, off, w, h, text in ITEMS:
        src = os.path.join(ROOT, 'work', 'build', f)
        if f in ('FIELD_FACE0.DAT', 'FIELD_DORAM.DAT') or not os.path.exists(src):   # 다른 빌더가 안 건드림 → 늘 원본에서(다시 돌려도 같게)
            src = os.path.join(ROOT, 'work', 'dm_all', f)
        dat = bytearray(open(src, 'rb').read()); n0 = len(dat)
        rgb = open(os.path.join(ROOT, 'work', 'ttlgfx', 'pal_%s.bin' % nm), 'rb').read()
        pal = [tuple(rgb[i * 3:i * 3 + 3]) for i in range(256)]
        print(nm, os.path.relpath(src, ROOT))
        if comp is None:                                 # 배너 자리는 늘 원본에서(빌드본엔 이전 한글판이 남아 있을 수 있음 — 몬스터 도감)
            ban = open(os.path.join(ROOT, 'work', 'dm_all', f), 'rb').read()[off:off + w * h]
            new, plate = banner_kr.make(ban, w, h, pal, text)
            dat[off:off + w * h] = new
            MON_PLATE[:] = [[pal[plate[y * w + x]] if plate[y * w + x] else None for x in range(w)] for y in range(h)]
        else:
            info = {}
            blk, mode, lut, rl = G.decompress(bytes(dat), comp, limit=0x40000, info=info)
            oi = {}                                         # 자리 = «원본» 스트림 길이(빌드본은 이미 짧게 다시 압축됐을 수 있음)
            G.decompress(open(os.path.join(ROOT, 'work', 'dm_all', f), 'rb').read(), comp, limit=0x40000, info=oi)
            budget = min(oi['end'], n0) - comp
            if f == 'FIELD_MTOUT.DAT':
                budget = min(budget, 0x1AFF0 - comp)        # 뒤 = 카테고리 문자열표(0x1AFF0) — build_mtout_gfx 와 같음
            ob = G.decompress(open(os.path.join(ROOT, 'work', 'dm_all', f), 'rb').read(), comp, limit=0x40000)[0]
            ban = ob[off:off + w * h]                    # 배너 자리는 늘 원본에서(빌드본엔 이전 한글판이 남아 있을 수 있음)
            prgb = None
            if nm == 'face' and MON_PLATE and REUSE_MON:  # 표정집 = 몬스터 도감 깨끗한 판 재활용(41줄 ← 40줄: 가운데 한 줄 복제) — 사용자 지시(자리 넘치면 끔)
                prgb = MON_PLATE[:20] + [MON_PLATE[20]] + MON_PLATE[20:]
            new, plate = banner_kr.make(ban, w, h, pal, text, ngold=NGOLD.get(nm), plate_rgb=prgb)
            nb = bytearray(blk); nb[off:off + w * h] = new
            if nm == 'theater':                              # 같은 블록의 극 제목판 5장(theater_plates)
                import theater_plates
                rc = open(os.path.join(ROOT, 'work', 'ttlgfx', 'pal_theater_color.bin'), 'rb').read()   # 컬러판 팔레트(선택 화면 스테이트 CRAM 0x500)
                pc = [tuple(rc[i * 3:i * 3 + 3]) for i in range(256)]
                nb = bytearray(theater_plates.apply(bytes(nb), pal, pal_color=pc))
            st = GC.compress(bytes(nb), lut, mode, rl)
            assert len(st) <= budget, (nm, '압축 넘침', len(st), budget)
            dat[comp:comp + len(st)] = st
            chk = G.decompress(bytes(dat) + b'\0' * 8, comp, limit=0x40000)[0]
            assert chk == bytes(nb), (nm, '되풀기 불일치')
            print('  압축 %d B / 자리 %d B · 되풀기 일치' % (len(st), budget))
        assert len(dat) == n0
        open(os.path.join(ROOT, 'work', 'build', f), 'wb').write(dat)
        prev.append((ban, plate, new, w, h, pal))
    print('✅ work/build: FACE0·MTOUT·DORAM.DAT·DICDT')
    if '--png' in sys.argv:
        H = sum(3 * h + 12 for *_, h, _ in prev)
        im = Image.new('RGB', (144 * 3 + 8, H), (0, 0, 0)); y = 0
        for ban, plate, new, w, h, pal in prev:
            for k, b in enumerate((ban, plate, new)):
                t = Image.new('RGB', (w, h)); t.putdata([(40, 40, 90) if v == 0 else pal[v] for v in b])
                im.paste(t, (k * (w + 4), y))
            y += h + 6
        im = im.crop((0, 0, im.width, y))
        im.resize((im.width * 2, im.height * 2), Image.NEAREST).save(os.path.join(ROOT, 'work', 'ttlgfx', 'ko_banners.png'))


if __name__ == '__main__':
    main()
