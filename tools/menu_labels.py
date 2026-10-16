# -*- coding: utf-8 -*-
r"""메뉴 모듈(CMDMN·CNFIG·ITGET·SHOP·SVLD) 반각 라벨 → 8×8 한글 (2026-10-16). build_half_hook 가 부른다.

라벨 = 반각 가타카나 문자열(상태창은 모드 3 = 히라가나로 바꿔 찍음 — 한글은 훅이 그 전에 가로챔).
  · 포인터 리터럴 하나로 참조되는 고정 칸: 한글(2바이트/음절)이 칸에 들어가면 제자리, 뒤는 공백(널 위치 유지).
    안 들어가면(예 `ブキ`·`スキル`·`マホウ` 3바이트 칸 — 「ぶきスキル」은 두 문자열을 붙여 찍는다)
    FDATA 블롭 뒤 «문자열 풀»에 두고 그 칸을 가리키는 절대 주소 리터럴을 전부 풀로 돌린다(리터럴 0개면 실패).
  · 캐릭터 이름 표(8개 널 연속, 순번으로 읽힘): 표 안에서 다시 채우고 마지막 이름 뒤를 공백으로(널 개수 유지).
"""
import re
import struct
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import bbg_text as T
import half_ko as K

LABELS = {
    'タンケン': '단검', 'トウケン': '도검', 'メイス': '메이스', 'オノ': '도끼', 'ムチ': '채찍', 'ナゲ': '투척',
    'ミズ': '물', 'カゼ': '바람', 'ツチ': '땅', 'アズカリジョ': '보관소', 'バージョン': '버전',
    'コウゲキ': '공격', 'ボウギョ': '방어', 'コウドウ': '행동', 'イドウ': '이동',
    'チカラ': '힘', 'タイリョク': '체력', 'スバヤサ': '민첩', 'ソウリョク': '지력',
    'ブキ': '무기', 'タテ': '방패', 'ヨロイ': '갑옷', 'カブト': '투구', 'クツ': '신발', 'アクセサリー': '장신구',
    'スキル': '스킬', 'マホウ': '마법', 'ゴールド': '골드', 'シュトク': '습득',
    'スキルアップパラメータ': '스킬업 능력치',
    'ウリネ': '판매가', 'マナエッグ': '마나 에그', 'シュウトクマホウ': '습득 마법', 'ゴウセイゾクセイ': '합성 속성',
    'イナズマ': '번개', 'フブキ': '눈보라', 'シンリン': '삼림', 'バクレツ': '폭렬',
    'ゲンザイ': '현재',
    # ⛔'ゲームアーツ' 는 세이브 파일 설명(백업 RAM 주석)으로 쓰일 수 있어 원래대로 — 본체 메모리 관리 화면에서 한글 바이트가 깨진다
}
NAMES = [('ジャスティン', '저스틴'), ('フィーナ', '피나'), ('スー', '수'), ('ガドイン', '가드인'),
         ('ラップ', '랩'), ('ミルダ', '밀다'), ('ギド', '기드'), ('リエーテ', '리에테')]
_KATA = {T.decode_half(bytes([c])): c for c in range(0xA6, 0xE0)}


def kata_bytes(jp):
    """가타카나 → 반각 원문 바이트(탁점 분리) — 이름 표 찾기용"""
    import unicodedata
    out = bytearray()
    for ch in unicodedata.normalize('NFKD', jp):
        if ch == '゙': out.append(0xDE)
        elif ch == '゚': out.append(0xDF)
        elif ch == 'ー': out.append(0xB0)
        else:
            out.append(_KATA[ch] if ch in _KATA else ord(ch))
    return bytes(out)


def plan(data, load):
    ops = []
    # 이름 표
    seq = b''.join(kata_bytes(j) + b'\x00' for j, _ in NAMES)
    alt = seq.replace(b'\xb0', b'\x90')          # 이 게임 반각 표의 ー 는 0x90 일 때도 있다
    for pat in (seq, alt):
        i = data.find(pat)
        if i >= 0:
            new = [K.encode(k) for _, k in NAMES]
            body = b'\x00'.join(new)
            room = len(pat) - 1
            assert len(body) <= room, ('이름 표 넘침', len(body), room)
            ops.append(('names', i, body + b' ' * (room - len(body)) + b'\x00'))
            names_span = (i, i + len(pat))
            break
    else:
        names_span = (0, 0)
    for m in re.finditer(rb'(?<=[\x00\xff])[\x20\x90\xa1-\xdf]{2,}(?=\x00)', data):
        if names_span[0] <= m.start() < names_span[1]:
            continue
        s = m.group(0); jp = T.decode_half(s).rstrip()
        if jp not in LABELS:
            continue
        ko = K.encode(LABELS[jp])
        cells_o = len(s)
        cells_k = len(LABELS[jp])
        if len(ko) <= len(s):
            pad = min(len(s) - len(ko), max(0, cells_o - cells_k))
            new = ko + b' ' * pad
            new += b' ' * (len(s) - len(new))            # 칸 끝까지 공백 — 널 위치 유지
            ops.append(('in', m.start(), new))
        else:
            addr = load + m.start()
            refs = [a for a in range(0, len(data) - 3, 2) if struct.unpack_from('>I', data, a)[0] == addr]
            if not refs:
                raise SystemExit('라벨 %r(0x%X) 칸 %dB < 한글 %dB 인데 포인터 리터럴이 없다' % (jp, m.start(), len(s), len(ko)))
            ops.append(('pool', m.start(), ko, refs))
    return ops


def make_pool(plans):
    pool = bytearray(); refs = {}
    for ops in plans.values():
        for op in ops:
            if op[0] == 'pool' and op[2] not in refs:
                refs[op[2]] = len(pool); pool += op[2] + b'\x00'
    while len(pool) % 4:
        pool += b'\x00'
    return bytes(pool), refs


def apply(d, ops, pool_refs, pool_base, load):
    nin = npool = 0
    for op in ops:
        if op[0] in ('in', 'names'):
            d[op[1]:op[1] + len(op[2])] = op[2]; nin += 1
        else:
            for a in op[3]:
                struct.pack_into('>I', d, a, pool_base + pool_refs[op[2]])
            npool += 1
    return nin, npool
