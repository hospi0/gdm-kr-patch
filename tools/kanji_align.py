# -*- coding: utf-8 -*-
"""한자 구간(0x35B~)을 JIS X 0208 순서에 **단조 정렬**해 자동 라벨링한다.

시트를 눈으로 읽어 확인한 사실: 0x35B부터 한자가 **JIS 순서의 부분수열**이다
(亜 握 圧 扱 暗 案 闇 依 偉 尉 胃 違 医 育 印 因 飲 院 陰 運 …).

그래서 자유 최근접 대조(평균 해밍거리 40이라 위험)를 쓰지 않고,
**순서를 보존하는 정렬**로 푼다. 후보를 건너뛸 수는 있어도 되돌아갈 수는 없다는
제약이 오대응을 크게 줄인다.

검증: 눈으로 읽어 둔 0x35B~0x3D7 구간과 대조한다.
"""
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, 'tools')
import font_codec as C

BOX = 16
FONT = r'C:\Windows\Fonts\msgothic.ttc'
DX, DY = 0, 1
START = 0x35B

# 눈으로 읽어 둔 검증용 (시트 k_358.png)
CHECK = {
    0x35B: '亜', 0x35C: '握', 0x35D: '圧', 0x35E: '扱', 0x35F: '暗',
    0x360: '案', 0x361: '闇', 0x362: '依', 0x363: '偉', 0x364: '尉',
    0x365: '胃', 0x366: '違', 0x367: '医', 0x368: '育', 0x369: '印',
    0x36A: '因', 0x36B: '飲', 0x36C: '院', 0x36D: '陰', 0x36E: '運',
    0x377: '駅', 0x378: '越', 0x387: '嫁', 0x392: '開', 0x3A7: '管',
    0x3B7: '季', 0x3C7: '給', 0x3D7: '郷',
}


def jis_kanji():
    """JIS X 0208 한자를 JIS 순서(구점 순)로"""
    out = []
    for ku in range(16, 85):
        for ten in range(1, 95):
            j = bytes([0xA0 + ku, 0xA0 + ten])
            try:
                ch = j.decode('euc_jp')
            except Exception:
                continue
            if len(ch) == 1 and 0x3400 <= ord(ch) <= 0x9FFF:
                out.append(ch)
    return out


def render(ch, f):
    img = Image.new('L', (BOX, BOX), 0)
    ImageDraw.Draw(img).text((DX, DY), ch, fill=255, font=f)
    px = img.load()
    return [sum((1 if px[x, y] >= 128 else 0) << (15 - x) for x in range(BOX))
            for y in range(BOX)]


def dist(a, b):
    return sum(bin(a[y] ^ b[y]).count('1') for y in range(BOX))


def main():
    d = open('work/dm/BIN_FDATA.BIN', 'rb').read()
    n = C.table_count(d, C.FULL_BASE)
    codes = list(range(START, n))
    game = [C.raw_to_rows(C.glyph_full(d, c)) for c in codes]

    f = ImageFont.truetype(FONT, 16)
    cands = jis_kanji()
    print('게임 코드 %d개, JIS 후보 %d자' % (len(codes), len(cands)), flush=True)
    cimg = [render(ch, f) for ch in cands]

    # DP: codes[i] ↔ cands[j], 단조 증가. 건너뛴 후보에는 벌점 0(부분수열이므로)
    INF = float('inf')
    m, k = len(codes), len(cands)
    if m > k:
        print('게임 코드가 후보보다 많다 — 정렬 불가')
        return
    prev = [INF] * (k + 1)
    prev[0] = 0.0
    for j in range(1, k + 1):
        prev[j] = 0.0                      # 아직 아무것도 배정 안 함
    bt = []
    for i in range(m):
        cur = [INF] * (k + 1)
        row = [0] * (k + 1)
        best_prev, best_j = INF, 0
        for j in range(1, k + 1):
            if prev[j - 1] < best_prev:
                best_prev, best_j = prev[j - 1], j - 1
            if best_prev == INF:
                continue
            cur[j] = best_prev + dist(game[i], cimg[j - 1])
            row[j] = best_j
        bt.append(row)
        prev = cur
        if (i + 1) % 200 == 0:
            print('  %d/%d' % (i + 1, m), flush=True)

    j = min(range(1, k + 1), key=lambda x: prev[x])
    total = prev[j]
    assign = [0] * m
    for i in range(m - 1, -1, -1):
        assign[i] = j - 1
        j = bt[i][j]
    print('총 해밍거리 %.0f (평균 %.1f)' % (total, total / m))

    out = open('work/codemap_kanji_auto.tsv', 'w', encoding='utf-8')
    ok = bad = 0
    for i, c in enumerate(codes):
        ch = cands[assign[i]]
        out.write('%03X\t%s\n' % (c, ch))
        if c in CHECK:
            if CHECK[c] == ch:
                ok += 1
            else:
                bad += 1
                print('  불일치 0x%03X 눈=%s 자동=%s' % (c, CHECK[c], ch))
    out.close()
    print('검증(눈으로 읽은 %d자): 일치 %d / 불일치 %d' % (len(CHECK), ok, bad))


if __name__ == '__main__':
    main()
