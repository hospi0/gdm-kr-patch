# -*- coding: utf-8 -*-
r"""명장면 화면 머리 배너 「あの名シーンをもう一度」 한글화 (2026-10-14) — `/FIELD/SVRBG.DAT`.
  찾은 길: 스테이트 VDP1 0x40000(192×24 8bpp) → SAVER.BIN(0x0602C000) 상수표 0x0602F1F4‥:
    0x16C28→CRAM 0x25F00200(팔레트) · 0x16E28→VDP1 0x25C40000(배너) · 0x18028→0x25C41200 — 0x230000 버퍼 기준.
  0x230000 버퍼 = SVRBG.DAT(ST1 KNPAN 틀, 조각 7개, 99,036 B)를 푼 것과 통째로 일치.
  배너 = 풀린 +0x16E28‥+0x18028 → 조각 5(0x14000‥) 끝 + 조각 6 앞 0x28 B 에 걸침.
  다시 넣기 = mg_splice.patch_slot(조각 5·6, 트리 고정·snap) — 파일 크기 불변, 되풀어 검산.
  글자: 일본어 획을 줄마다 금판 색(양 끝 깨끗한 열에서 뽑음)으로 메우고, 파란 한 색 + 1px 어두운 테두리.
  필요: tools/third_party/new-parm-archives-tools/work/mgame/hwram.bin (엔진 코드, build_title_gfx 와 같음)
  python tools/build_scene_banner.py [--png] → work/build/FIELD_SVRBG.DAT
"""
import os, struct, sys
from collections import Counter
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
TP = os.path.join(HERE, 'third_party', 'new-parm-archives-tools')
sys.path[:0] = [os.path.join(TP, 'tools')]
import mg_splice, mg_tree     # noqa: E402

TEXT = '그 명장면을 다시 한번'
FONT_B = r'C:\Windows\Fonts\malgunbd.ttf'
PAL_OFF, BAN_OFF, W, H = 0x16C28, 0x16E28, 192, 24
CHUNK = 0x4000
NBLUE = int(next((a.split('=')[1] for a in sys.argv if a.startswith('--nblue=')), '6'))


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    src = os.path.join(ROOT, 'work', 'dm_all', 'FIELD_SVRBG.DAT')
    dat = open(src, 'rb').read()
    ch = mg_splice.decode_slot(dat, 0)
    flat = bytearray(b''.join(bytes(c['pixels']) for c in ch))
    assert len(ch) == 7 and len(flat) == 99036
    pal = [(((w) & 31) << 3, ((w >> 5) & 31) << 3, ((w >> 10) & 31) << 3)
           for w in struct.unpack_from('>256H', flat, PAL_OFF)]
    ban = bytearray(flat[BAN_OFF:BAN_OFF + W * H])
    isblue = lambda i: i and pal[i][2] > pal[i][0] + 20
    isgold = lambda i: i and pal[i][0] >= pal[i][2] and pal[i][0] > 120
    # 글자 칸(파란 획) 범위
    bl = [(x, y) for y in range(H) for x in range(W) if isblue(ban[y * W + x])]
    x0, x1 = min(p[0] for p in bl), max(p[0] for p in bl)
    y0, y1 = min(p[1] for p in bl), max(p[1] for p in bl)
    print('일본어 획 x%d‥%d y%d‥%d · 화소 %d' % (x0, x1, y0, y1, len(bl)))
    # ★깨끗한 판부터(2026-10-14 사용자): 판 = 가로 8단계 그라데이션(44→56→58→60→65→67→68→70)이고
    #   단계 경계가 줄마다 비스듬히 밀린다 → 글자 띠 위·아래 깨끗한 줄(CLEAN_TOP·CLEAN_BOT)의 경계 x 를
    #   줄 번호로 선형 보간해 띠 안쪽을 통째로 다시 칠한다(획만 지우면 잔티가 남음).
    LEVELS = [44, 56, 58, 60, 65, 67, 68, 70]
    CLEAN_TOP, CLEAN_BOT = y0 - 1, y1 + 2

    def starts(y):
        row = ban[y * W:(y + 1) * W]
        return [next(x for x in range(W) if row[x] == lv) for lv in LEVELS]

    st_t, st_b = starts(CLEAN_TOP), starts(CLEAN_BOT)
    out = bytearray(ban)
    for y in range(CLEAN_TOP + 1, CLEAN_BOT):
        k = (y - CLEAN_TOP) / (CLEAN_BOT - CLEAN_TOP)
        bnd = [round(a + (b - a) * k) for a, b in zip(st_t, st_b)]
        row = ban[y * W:(y + 1) * W]
        L = next(x for x in range(W) if row[x] == 44)                  # 왼쪽 테두리 안쪽 첫 판 화소
        R = max(x for x in range(W) if row[x] == 70)                   # 오른쪽 테두리 안쪽 끝 판 화소
        for x in range(L, R + 1):
            lv = LEVELS[0]
            for j, bx in enumerate(bnd):
                if x >= bx:
                    lv = LEVELS[j]
            out[y * W + x] = lv
    plate = bytes(out)
    used = Counter(v for v in ban if isblue(v))
    body = used.most_common(1)[0][0]
    outl = min(used, key=lambda i: sum(pal[i]))
    # 글자 맞추기 + 안티(aatext — 원본 배너가 쓰던 색인 안에서 섞음, 바탕 = 깨끗한 판)
    import aatext
    bw, bh = x1 - x0 + 1, y1 - y0 + 1
    for size in range(bh + 6, 8, -1):
        cov, (tw, th) = aatext.coverage(TEXT, FONT_B, size, W, H, [0], fit=(x0, y0, bw - 1, bh - 1))
        if tw <= bw - 1 and th <= bh - 1:
            break
    # ★원본 = 테두리 없음 — 파란 몸 + 오른쪽 아래 1px 짙은 남색 그림자(2026-10-14 사용자 지적)
    # 섞을 색 = 판 8단계 + 원본 글자가 많이 쓰던 파란색 NBLUE 개(트리 고정이라 색이 늘면 자리 넘침 — 2026-10-14 27 B 넘침)
    cands = set(LEVELS) | {body, outl} | {i for i, _ in used.most_common(NBLUE)}
    out = aatext.compose_over([(aatext.shift(cov[0], 1, 1), pal[outl]), (cov[0], pal[body])], W, H, pal, cands,
                              bg=lambda x, y: pal[plate[y * W + x]], base=plate)
    print('글자 %dpx · 몸 %d %s · 그림자 %d %s' % (size, body, pal[body], outl, pal[outl]))
    flat[BAN_OFF:BAN_OFF + W * H] = out
    rep = {k: bytes(flat[k * CHUNK:k * CHUNK + len(ch[k]['pixels'])]) for k in (5, 6)}
    new = mg_splice.patch_slot(dat, 0, len(dat), rep, snap=True, palette_rgb=pal)
    assert len(new) == len(dat)
    chk = mg_tree.decode_blob(new, 0)
    for k in range(7):
        if k not in rep:
            assert chk[k]['pixels'] == ch[k]['pixels'], ('다른 조각이 바뀜', k)
    got = b''.join(bytes(c['pixels']) for c in chk)
    nd = sum(1 for a, b in zip(got, flat) if a != b)
    print('되풀기 차이 %d화소(트리 밖 색 snap) · 다른 조각 불변 · 크기 %d 불변' % (nd, len(new)))
    open(os.path.join(ROOT, 'work', 'build', 'FIELD_SVRBG.DAT'), 'wb').write(new)
    print('✅ work/build/FIELD_SVRBG.DAT')
    if '--png' in sys.argv:
        b = got[BAN_OFF:BAN_OFF + W * H]
        img = Image.new('RGB', (W, H * 3 + 4), (40, 40, 90))
        sep = [(0, 0, 0)] * (W * 2)
        img.putdata([(40, 40, 90) if v == 0 else pal[v] for v in ban] + sep
                    + [(40, 40, 90) if v == 0 else pal[v] for v in plate] + sep
                    + [(40, 40, 90) if v == 0 else pal[v] for v in b])
        img.resize((W * 3, (H * 3 + 4) * 3), Image.NEAREST).save(os.path.join(ROOT, 'work', 'ttlgfx', 'ko_scene_banner.png'))


if __name__ == '__main__':
    main()
