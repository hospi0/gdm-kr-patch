# -*- coding: utf-8 -*-
"""박물관 텍스트용 «비트 트리(허프만)» 디코더 — 실기 코드에서 그대로 옮김.

## 출처

쓰기 워치포인트(`0x002E40A0`)로 잡은 루프를 세이브스테이트 RAM에서 역어셈블했다.

    0x06015E5A  MOV   R5, R0          ; 루트 노드 오프셋
    0x06015E5C  TST   R8, R11         ; R11=비트버퍼, R8=회전 마스크
    0x06015E5E  BT/S  0x06015E68
    0x06015E60    ADD R4, R0          ; (지연슬롯, 항상 실행) 노드주소 = R4 + 노드값
    0x06015E64    MOV.W @(6,R0), R0   ; 비트=1 → +6 자식
    0x06015E68  MOV.W @(4,R0), R0     ; 비트=0 → +4 자식
    0x06015E6A  ROTR  R8              ; 마스크 회전, 넘치면 T=1
    0x06015E6C  BT    0x06015EEC      ;   → 0x06015EEE  MOV.L @R13+, R11  (리필)
    0x06015E6E  CMP/HI R6, R0         ; 노드값 > 임계 → 계속 내려간다
    0x06015E74  CMP/EQ R6, R0         ; == 임계 → 종료
    0x06015E78  SHLR R0 / SHLR2 R0    ; 리프: 노드값 >> 3
    0x06015E7E  EXTU.B R9, R9         ; 그 하위 1바이트가 «해독된 문자»
    0x06015E80  SHLL8 R2 / OR R9, R2  ; 4바이트 모아
    0x06015E8A  MOV.L R2, @R14        ; 롱 단위로 기록

브레이크 시점 레지스터:
    R4 = 0x06028800 (트리 베이스)  R5 = 0x0E00 (루트)  R6 = 0x0800 (임계)
    R8 = 0x40000000               R11 = 0x39FB0D87    R13 = 0x00216B98
    R12 = 0 (리프 값에 더하는 오프셋 — 이 호출에서는 0)

`R13` 이 가리키던 곳 = `FIELD/SVRDT.DAT` + 0x6B94 (이 파일은 RAM 0x00210000 에
**전체 바이트 일치**로 통째 적재된다).
"""
import struct


class Tree:
    """16비트 BE 노드 배열. 노드값 v → 주소 base+v, 자식은 +4(비트0) / +6(비트1)."""

    def __init__(self, mem, base, root, leaf_thr):
        self.m = mem
        self.b = base
        self.root = root
        self.thr = leaf_thr

    def word(self, a):
        return struct.unpack_from('>H', self.m, a)[0]


def decode(tree, stream, pos, out_len=None, max_out=1 << 20):
    """stream[pos:] 를 풀어 bytes 를 낸다. `thr` 노드를 만나면 종료."""
    node = tree.root
    mask = 0x80000000
    buf = struct.unpack_from('>I', stream, pos)[0]
    pos += 4
    out = bytearray()
    while len(out) < max_out:
        addr = tree.b + node
        bit = (buf & mask) != 0
        node = tree.word(addr + (6 if bit else 4))
        mask = ((mask >> 1) | ((mask & 1) << 31)) & 0xFFFFFFFF
        if mask == 0x80000000:                 # 한 바퀴 돌았다 → 리필
            if pos + 4 > len(stream):
                break
            buf = struct.unpack_from('>I', stream, pos)[0]
            pos += 4
        if node > tree.thr:
            continue                            # 내부 노드
        if node == tree.thr:
            break                               # 종료 표지
        out.append((node >> 3) & 0xFF)
        node = tree.root
        if out_len is not None and len(out) >= out_len:
            break
    return bytes(out), pos
