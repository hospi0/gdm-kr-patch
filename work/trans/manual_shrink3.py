# -*- coding: utf-8 -*-
import csv
import sys

sys.path.insert(0, 'tools')
from runs_build import load_maps, encode, BuildError

rev, ko = load_maps()

NEW = {
1: "정신 못차리고", 2: "안 어지렀어!", 3: "뭔 소리냐!", 7: "그래서 어떻게됐어?",
21: "흐응, 열쇠 든 채로", 24: "하아, 참 언제나", 31: "뭐야 갠츠 녀석‥‥",
32: "나무상자 열개 쌓은 건", 40: "앞치마를 갠츠에게 보였다",
41: "빛의 방패, 정령검 두 개‥‥", 44: "필요 없어져? 그럴리 없잖아!",
47: "누워 떡먹기!", 53: "훈련해보면?", 59: "그럼 얼굴 어떠냐!",
61: "앗, 그 얼굴이다!", 78: "이 열쇠주지 말라고", 79: "숨바꼭질하나?",
80: "뭘 할까나?", 87: "석탄 잔뜩나오던 시절엔", 90: "어디서 떨어뜨렸는데?",
93: "감사로 받아줘", 94: "브로치 떨어졌네‥‥", 96: "하‥‥ 그런 멍청한 녀석",
99: "글쎄 열차바퀴 떨어져 있더라고", 101: "그래 나처럼 엉망‥‥",
103: "저스틴 생각은?", 104: "살토서 발견된건", 107: "저스틴 생각은?",
108: "살토서 발견된건", 114: "그 애 아니야!", 115: "그대로 괜찮죠?",
117: "귀엽게 그릴때까지", 119: "못 그리면", 122: "엣, 뭔 소리야?!",
124: "엣 뭔 소리야?", 125: "잡아떼지마!", 128: "남편도 검댕으로 새까매서",
132: "다른애랑 안 놀아?", 138: "답례하려 찾고 있었어",
142: "상관없어요, 쓰는법은", 144: "근데요, 혹시", 151: "이야, 그리 칭찬받으니",
152: "칭찬 안 받았는데‥", 153: "넌 모험인지 뭔지 푹빠져 있으니까",
171: "석탄사탕 받았다니까", 172: "그렉 일행", 176: "헤헷 농담!",
179: "며느리삼고 싶어졌죠?", 190: "마침내 이겼다‥‥", 200: "음, 지금이면 특별히",
203: "손님 잔뜩 몰려올거야", 204: "음, 지금이면 특별히", 214: "길어도 돼!",
219: "무슨무슨 킹 만나러 갈거야", 233: "엣! 또 하고있었어, 피피⁉",
238: "텐츠·코즈루뿐", 239: "헤헷 당연한 거지!", 241: "우두커니 있어야하나‥‥",
245: "숨바꼭질하기 싫었어", 246: "다른 놀이할 걸 그랬어",
248: "당연 숨바꼭질인줄 알았어", 256: "근데 가만있고", 259: "맡아달래서 받았거든",
266: "원하는 설정 십자버튼으로 선택", 269: "원하는 몬스터 십자버튼으로 선택",
275: "보너스늘어납니다", 280: "버튼： 식사, 계속 눌렀다 떼면 공격",
281: "버튼： 장애물・공격 튕겨냄", 282: "먼저 저쪽으로 어머! 벌써",
285: "걱정돼서 이곳 떠날 수가", 291: "병사훈련이라 생각하냐?",
297: "큭 크크크… 아직 안 끝났다…", 300: "그런 얼굴로?",
}


def main():
    lines = [l.rstrip('\n').split('\t') for l in open('work/trans/shrink_fail.txt', encoding='utf-8')]
    runs = list(csv.DictReader(open('work/trans/runs.tsv.merged4', encoding='utf-8'), delimiter='\t'))
    idx = {(r['file'], r['off']): i for i, r in enumerate(runs)}
    round2 = {}
    for line in open('work/trans/round2_fixed.txt', encoding='utf-8'):
        i, t = line.rstrip('\n').split('\t', 1)
        round2[int(i)] = t

    ok = bad = 0
    fails = []
    for i, (f, off, L, oldko) in enumerate(lines):
        L = int(L)
        newko = NEW.get(i) or round2.get(i)
        if newko is None:
            continue  # already applied in earlier rounds
        try:
            n = len(encode(newko, rev, ko))
        except BuildError as e:
            fails.append((i, f, off, L, newko, 'ENC:' + str(e)))
            bad += 1
            continue
        if n > L:
            fails.append((i, f, off, L, newko, 'OVER:%d' % (n - L)))
            bad += 1
            continue
        ri = idx.get((f, off))
        if ri is None:
            fails.append((i, f, off, L, newko, 'NOKEY'))
            bad += 1
            continue
        runs[ri]['ko'] = newko
        ok += 1

    print('적용 %d / 실패 %d' % (ok, bad))
    with open('work/trans/runs.tsv.merged5', 'w', encoding='utf-8', newline='') as fp:
        w = csv.writer(fp, delimiter='\t')
        w.writerow(['file', 'off', 'len', 'ja', 'ko'])
        for r in runs:
            w.writerow([r['file'], r['off'], r['len'], r['ja'], r['ko']])
    with open('work/trans/round3_fail.txt', 'w', encoding='utf-8') as f:
        for x in fails:
            f.write(repr(x) + '\n')
    print('저장: runs.tsv.merged5 / round3_fail.txt (%d건)' % len(fails))


if __name__ == '__main__':
    main()
