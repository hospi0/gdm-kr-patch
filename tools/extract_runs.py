# -*- coding: utf-8 -*-
"""런 단위 추출 — 메시지 구조에 의존하지 않는다.

세션2에서 메시지 컨테이너 구조를 세 번 잘못 짚었다(`20 LL` → 패딩 규칙 → 선형 보완).
그래서 **구조를 아예 쓰지 않는** 방식으로 간다:

  스크립트 섹션에서 **연속된 글자 코드**를 런으로 잡고, 런을 **같은 바이트 길이로
  제자리 교체**한다. 길이를 안 바꾸므로 명령 스트림·메시지 길이·점프가 전부 그대로다.

⚠️ 섹션 선택은 옛 `script_section()` 을 그대로 쓴다. 큰 섹션들은 3D 데이터가
   우연히 가나로 읽히는 노이즈다(「方ひ自だ方ざ」식) — 일본어 판정으로는 못 거른다.
   실측 결과 **옛 스크립트 섹션에만 진짜 대사가 있다.**

## 세션3 → 세션4 (2026-08-05) — 바이트 규칙을 인터프리터 확정판으로 교체

인터프리터(`0x0601D5A4`, docs/survey.md §16)를 디스어셈블해 바이트별 뜻이 확정됐다.
그동안 「`0x10~0x14` 는 제어이기도 글자이기도 해서 모호하다」며 바이그램 통계
(`lead10_is_ctrl`)로 추측하던 것과, 「제어코드 인수가 글자로 오독된다」며
`work/trans/junk_prefix.tsv` 수동 보정표로 때우던 것 — **둘 다 진짜 규칙을 몰라서
생긴 임시방편**이었다.

확정 규칙:
    0x00~0x09  제어 (인수 없음, 1B)
    0x0A~0x0F  제어 + **2바이트 인수** (총 3B) ★이걸 건너뛰지 않은 게 진짜 원인이었다
    0x10~0x1F  2바이트 글자 선두 (모호하지 않다 — 항상 글자)
    0x20~0xFF  1바이트 글자

실측(`00 00 0B 00 | 21 | 10 17…`, 2000.MDT +0x23F5): 옛 스캐너는 `0B`에서 멈추고
1바이트만 건너뛰어, 인수의 하위 바이트 `0x21`을 다음 런의 시작 글자로 오독했다.
이제 `0x0B`(0x0A~0x0F 범위)를 만나면 **인수 2바이트까지 통째로 건너뛴다** —
바이그램 추측도 보정표도 필요 없다.

런 판정:
  - 0x20~0xFF → 1바이트 글자, 0x10~0x1F+1B → 2바이트 글자
  - 제어코드(0x00~0x0F)에서 끊김, 인수가 있으면(0x0A~0x0F) 통째로 건너뜀
  - 길이 minlen 이상 & 일본어 비율 이상만 번역 대상

### ★ 잔차 문제 — 블록 「앞」에서 위상이 밀린다

위 수정으로 옛 방식의 인수 침범(같은 기준 실측 137건)은 절반(64건)까지 줄었지만
0은 아니다. 원인은 **맹목적 전체 스캔**이라 실제 블록이 시작하기 전의 VM 명령
바이트 구간에서 우연히 `0x0A~0x0F` 패턴이 나오면 위상이 밀린다.

실측(2000.MDT, 섹션 +0xEB2E): 진짜 텍스트 블록은 `0A 00C0 | パームの港 | 0A 00D0 | へ | 07`
로 시작하는데, 그 **직전** 바이트 `+0xEB2D`가 우연히 `0x0E`(제어+인수 패턴)라서
블록 헤더 `0A`를 인수로 삼켜버리고, 남은 `C0`(=블록 시작 3번째 바이트, 사실은
`0A`의 인수 하위바이트)를 글자로 오독해 「ニパームの港」가 나온다.

해법 = **앵커**. `text_vm.scan_candidates`(워드 정렬 `2LLL` 헤더 후보) +
`decode_block`(끝까지 정렬·글리프 유효·`07` 종단·일본어 비율)로 **완전히 검증되는
블록만** 신뢰하고, 그 블록의 바이트 범위는 맹목적 스캔에서 통째로 제외한다
(`blocked`에 합침 → 스캔이 절대 안으로도, 밖에서 안으로도 위상이 새지 않는다).
검증된 블록 안의 글자런은 `decode_block` 결과에서 **직접** 뽑으므로 원리적으로
인수를 포함할 수 없다. 나머지(검증 못한 영역)는 기존 맹목 스캔이 보완한다.
"""
import os
import sys

sys.path.insert(0, 'tools')
import codemap
from codemap_kanji_src import kanji_map
from script_budget import script_section, scan_skips
from text_vm import decode_block, scan_candidates, GLYPH_MAX

m = codemap.base_map()
m.update(kanji_map())
KANA = set(codemap.HIRA + codemap.KATA)
JPP = set('‥…。、・「」『』！？⁉‼～ー♪♥○※（）　 ')
MINLEN, MINRATIO = 3, 0.6

# ★ 노이즈(3D 데이터·명령 인수가 우연히 가나로 읽히는 것)를 거르는 실측 지문.
#   ⚠️ 파일 단위 공백률로 자르면 **표지판만 있는 파일이 통째로 버려진다**
#      (「ギーオスの塔・1」 에는 공백이 없다). 그래서 런 단위로 본다.
#
#   진짜 텍스트 런의 성질:
#     - 공백이 들어가거나(문장), 또는
#     - 한자·장음·중점이 이어지는 고유명사/표지판이거나
#   노이즈 런: 가나가 무작위로 흩어지고 공백도 한자 구조도 없다.
LONG_RUN = 12               # 이 길이 넘으면 문장으로 보고 공백을 요구한다


def is_jp(ch):
    return ch in KANA or 0x4E00 <= ord(ch) <= 0x9FFF or ch in JPP


def kana_ratio(t):
    return sum(1 for x in t if x in KANA) / max(len(t), 1)


def looks_noise(t):
    """노이즈(3D 데이터·명령 인수가 우연히 글자로 읽힌 것) 판정.

    실측 지문 — 확실한 대사 7런 vs 확실한 노이즈 20런:
        라틴문자 비율   대사 0.000  /  노이즈 0.143   ← 가장 잘 갈린다
        공백/글자      대사 0.054  /  노이즈 0.007
    일본어 대사에는 영문자가 사실상 안 나온다.
    """
    if not t:
        return True
    # ⚠️ 숫자는 세지 않는다 — 「ギーオスの塔・1」 같은 정상 표지판이 걸린다.
    latin = sum(1 for c in t if c.isascii() and c.isalpha())
    if latin / len(t) > 0.08:
        return True
    if len(t) < LONG_RUN:
        return False
    # 긴 런인데 공백도 한자·중점도 없으면 무작위 가나
    if ' ' in t:
        return False
    if sum(1 for c in t if 0x4E00 <= ord(c) <= 0x9FFF or c == '・') >= 2:
        return False                    # 고유명사·표지판
    return True


def blocked_ranges(s):
    """`1000 30LL` 조건부 스킵 명령의 4바이트 헤더 — 값이 우연히 인쇄 가능
    범위(>=0x20)라 스캐너가 글자로 잘못 삼킨다. 이 구간은 강제로 런을 끊는다.
    (docs/survey.md §13 — 좌F 접두 오염 사례로 실측 확인)"""
    return [(sp, sp + 4) for sp, st, en, LL in scan_skips(s)]


def trusted_blocks(s):
    """`text_vm` 확정 디코더로 **완전히 검증된** op2 블록만 골라낸다 (docs §16.3).

    검증 조건 (전부 충족해야 신뢰):
      - 워드 정렬 `2LLL` 헤더로 디코드했을 때 정확히 끝에서 끝난다
      - 글자 코드가 전부 폰트 표 안(< GLYPH_MAX)
      - 제어 `0x07`(종단)이 있고, **그 뒤는 전부 패딩 `0x00` 뿐**
      - 글자 4개 이상, 일본어 비율 0.8 이상

    ★세션6 수정 — 종단검사가 진짜 블록 376개를 버리고 있었다 (docs §19).
    옛 검사는 `toks[-1].code == 0x07`(**마지막** 토큰이 07)이었는데, 블록 길이는
    **워드 정렬**이라 본문+`07` 이 홀수 바이트면 뒤에 패딩 `00` 이 하나 붙는다.
    그러면 마지막 토큰이 `00` 이라 탈락 → 맹목 스캔이 대신 담당 → 얘는 블록 시작을
    모르니 **헤더 `20 1X` 부터** 읽어 `20`=스페이스, `10 97`=2바이트 글자로 오독하고
    **첫 글자 `ア` 의 바이트 `97` 을 인수로 먹어** ` 射レント博物館` 을 만들었다.
    게다가 런이 헤더 2바이트를 포함하니 **빌더가 헤더 위에 번역문을 써서** 실측
    8건에서 헤더 `20 10` → `a7 10` 으로 파괴됐다.
    실측(E800 +01C68): `20 10 | 97 e1 e6 bd … e0 | 07 00` — `scan_candidates` 는
    처음부터 `01C6A L=16` 로 정답을 알고 있었다.

    낸다: [(off, length, 토큰목록)] — 겹치는 후보는 **더 긴 쪽**을 남긴다
    (짧은 후보가 긴 진짜 블록 내부에서 우연히 자기완결적으로 보일 수 있어서).
    """
    cand = []
    for off, L in scan_candidates(s):
        try:
            toks, end = decode_block(s, off, L)
        except IndexError:
            continue
        if end != off + L:
            continue
        chars = [t for t in toks if t.kind == 'char']
        if not chars or any(not (0 <= t.code < GLYPH_MAX) for t in chars):
            continue
        # ★종단 `0x07` 을 뒤에서 찾고, 그 뒤는 패딩 `0x00` 만 허용(워드 정렬 보정)
        term = None
        for i in range(len(toks) - 1, -1, -1):
            if toks[i].kind == 'ctrl' and toks[i].code == 0x07:
                term = i
                break
        if term is None:
            continue
        if any(not (t.kind == 'ctrl' and t.code == 0x00) for t in toks[term + 1:]):
            continue
        txt = text([t.code for t in chars])
        if len(txt) < 4 or sum(1 for c in txt if is_jp(c)) / len(txt) < 0.8:
            continue
        # ★ E8FF.MDT 실측: 위 조건을 다 통과하고도 라틴 문자가 섞인 가짜가 하나
        #   나왔다(`るNきXガ…` — N·X 는 진짜 일본어 대사에 나오지 않는다). looks_noise
        #   와 같은 잣대를 여기서도 적용한다.
        latin = sum(1 for c in txt if c.isascii() and c.isalpha())
        if latin / len(txt) > 0.08:
            continue
        cand.append((off, L, toks))
    # ★세션6 수정 — 「긴 것부터」가 아니라 **주소 순서**로 고른다.
    #   실측(2000.MDT): 진짜 블록은 `0C492`(헤더 `20 62`, LLL=98)인데, 그 본문 한가운데
    #   ` た`(`20 63`)를 헤더로 오인한 가짜 후보 `0C4AC`(LLL=99)가 **1바이트 더 길다는
    #   이유만으로** 이겨서, `こんなに たくさん` 이 `こんなに`/`くさん` 으로 찢어졌다.
    #   진짜 블록은 스크립트에 **순차·비중첩**으로 놓이므로 왼쪽부터 훑으면 복원된다.
    #   (짧은 가짜가 긴 진짜 안에 들어있는 경우도, 진짜가 더 앞에서 시작하므로 안전.)
    cand.sort(key=lambda x: x[0])
    out, used = [], bytearray(len(s))
    for off, L, toks in cand:
        lo = max(off - 2, 0)             # 헤더 2바이트까지 점유로 친다
        if any(used[lo:off + L]):
            continue
        out.append((off, L, toks))
        for i in range(lo, min(off + L, len(s))):
            used[i] = 1
    return out


def trusted_runs(off, L, toks):
    """검증된 블록 하나에서 (바이트오프셋, 길이, 코드리스트) 글자런들을 뽑는다."""
    out = []
    p = off
    cur, st = [], None
    for t in toks:
        if t.kind == 'char':
            if st is None:
                st = p
            cur.append(t.code)
        else:
            if st is not None:
                out.append((st, p - st, cur))
            cur, st = [], None
        p += len(t.raw)
    if st is not None:
        out.append((st, p - st, cur))
    return out


def scan_runs(s, blocked=()):
    """[(바이트offset, 바이트길이, 코드리스트)] — 글자 코드가 이어지는 구간 전부

    바이트 규칙은 인터프리터 확정판(위 docstring). `0x10~0x1F`는 항상 2바이트
    글자 선두이고, `0x0A~0x0F`는 제어+2바이트 인수라 **3바이트를 통째로 건너뛴다**
    (이걸 안 하면 인수 하위바이트가 다음 런의 첫 글자로 오독된다).

    ★세션5 실측(§18.9): 검증 안 된 구간에서 2바이트 글자로 나온 코드가 **폰트
    표 밖(≥GLYPH_MAX)** 이면 진짜 글자가 아니라 반복 데이터 테이블이 우연히
    맞아떨어진 것이다(`80 1A 00 XX 70…` 6바이트 패턴이 파일 전역에 반복,
    example 2000.MDT +0xC6). 이런 자리는 런을 끊는다 — 표 밖 코드를 그대로
    담아 「?」 섞인 가짜 번역대상을 만들지 않는다.
    """
    block = bytearray(len(s))
    for a, b in blocked:
        for i in range(a, min(b, len(s))):
            block[i] = 1
    out, i, n = [], 0, len(s)
    cur, st = [], None

    def flush():
        nonlocal cur, st
        if st is not None:
            out.append((st, i - st, cur))
        cur, st = [], None

    while i < n:
        if block[i]:
            flush()
            i += 1
            continue
        b = s[i]
        if b >= 0x20:
            if st is None:
                st = i
            cur.append(b - 0x20)
            i += 1
        elif 0x10 <= b <= 0x1F and i + 1 < n and not block[i + 1] \
                and 0xE0 + (b - 0x10) * 256 + s[i + 1] < GLYPH_MAX:
            if st is None:
                st = i
            cur.append(0xE0 + (b - 0x10) * 256 + s[i + 1])
            i += 2
        else:
            flush()
            i += 3 if 0x0A <= b <= 0x0F else 1   # ★제어+2바이트 인수는 통째로 건너뜀
    flush()
    return out


def text(codes):
    return ''.join(m.get(c, '?') for c in codes)


def translatable(codes):
    t = text(codes)
    if len(t) < MINLEN:
        return False
    return sum(1 for c in t if is_jp(c)) / len(t) >= MINRATIO


def code_bytes(c):
    return 1 if c < 0xE0 else 2


def extract(d, name=None):
    """(섹션오프셋, 섹션바이트, 번역대상 런목록)

    `name` 은 옛 인수-오염 보정표(junk_prefix.tsv) 시절의 흔적으로 이제 안 쓴다
    (호출부 호환을 위해 인자만 남겨둔다) — 바이트 규칙 자체가 인수를 건너뛰므로
    보정이 필요 없다.

    두 채널을 합친다:
      1. **검증된 블록**(`trusted_blocks`) 안의 글자런 — 인수 침범이 원리적으로 불가능
      2. 그 밖의 구간에 대한 맹목 스캔(`scan_runs`) — 검증된 블록 범위는 통째로
         제외해 위상이 안에서도 밖에서도 새지 않게 한다

    ★ 검증된 블록이 **단 하나도 없는 파일**은 대사 스크립트가 아니라고 판단해
    맹목 스캔도 건너뛴다. 실측(2026-08-05, §17 후속): 0000·0004·EC08·E8FF.MDT
    는 (모든 섹션을 통틀어도) 신뢰 블록이 0개인데 맹목 스캔만으로는 글자 906개
    런이 나왔었다 — 전부 3D 데이터가 우연히 가나로 읽힌 노이즈였다
    (예 `自自自ヅまッぼ`). 이 노이즈를 「미번역 대사」로 잘못 세면 폰트 슬롯
    재배정 계산(§15.4)이 왜곡된다.
    """
    o, b, _ = script_section(d)
    s = d[o:o + b]

    trusted = trusted_blocks(s)
    if not trusted:
        return o, s, []
    out = []
    for off, L, toks in trusted:
        for roff, rL, c in trusted_runs(off, L, toks):
            if not translatable(c):
                continue
            if looks_noise(text(c)):
                continue
            out.append((roff, rL, c))

    # ★블록 **본문 앞 2바이트 = `2LLL` 헤더**까지 막는다. 본문만 막으면 앞쪽 맹목
    #   런이 헤더를 글자로 삼키고, 빌더가 그 위에 번역문을 써서 헤더가 깨진다
    #   (실측 2000.MDT +0x0C49C: `たくさん` 이 `た`/`くさん` 으로 쪼개진 게 그 흔적).
    blocked = blocked_ranges(s) + [(max(off - 2, 0), off + L) for off, L, _ in trusted]
    for off, L, c in scan_runs(s, blocked):
        if not translatable(c):
            continue
        if looks_noise(text(c)):
            continue
        out.append((off, L, c))

    out.sort(key=lambda x: x[0])
    return o, s, out


def main():
    tot = chars = 0
    for f in sorted(os.listdir('work/dm')):
        if not f.endswith('.MDT'):
            continue
        d = open('work/dm/' + f, 'rb').read()
        o, s, rs = extract(d)
        c = sum(len(r[2]) for r in rs)
        tot += len(rs)
        chars += c
        print('%-14s 런 %5d  글자 %6d' % (f[6:], len(rs), c))
    print('-' * 46)
    print('합계 런 %d개, 글자 %d자' % (tot, chars))


if __name__ == '__main__':
    main()
