# -*- coding: utf-8 -*-
"""설정 화면(`FIELD_CNFIG.BIN`) 한글화 — 오프셋 직접 지정 방식.

널 워크를 쓰지 않는다(2바이트 토큰 둘째 바이트가 0x00 인 문자열이 있다).
전각 복귀 `0x04` 를 가능하면 붙이고, 자리가 없으면 **첫 글자가 2바이트 토큰인지**
확인해서(모드 무관) 통과시킨다. 둘 다 안 되면 실패로 보고한다.
"""
import os
import sys

sys.path.insert(0, 'tools')
sys.path.insert(0, 'work/trans')
import sysmenu2 as S2
import config_ko as K

SRC, DST, NAME = 'work/dm', 'work/build', 'FIELD_CNFIG.BIN'


def enc(t):
    """`` 뒤는 반각 모드 — ASCII 를 바이트 그대로(반각 글리프 = 바이트 − 0x20)."""
    full, _, half = t.partition('')
    e = S2.encode_ko(full)
    if _:
        assert all(0x20 <= ord(c) < 0x7F for c in half), half
        e += b'' + half.encode('ascii')
    return e


def main():
    src = open(os.path.join(SRC, NAME), 'rb').read()
    base = os.path.join(DST, NAME)
    d = bytearray(open(base if os.path.exists(base) else os.path.join(SRC, NAME), 'rb').read())
    ok = fail = 0
    for off, slot, ko_text in K.CONFIG:
        e = enc(ko_text)
        if len(e) + 1 <= slot:
            e = b'\x04' + e                     # 전각 복귀 명시(여유 있을 때)
        elif len(e) <= slot:
            if not (0x10 <= e[0] <= 0x1F):      # 2바이트 토큰이면 모드 무관
                print('  X 0x%05X %r: 0x04 넣을 자리 없고 첫 글자가 1바이트'
                      % (off, ko_text))
                fail += 1
                continue
        else:
            print('  X 0x%05X %r: 바이트초과 %d>%d' % (off, ko_text, len(e), slot))
            fail += 1
            continue
        d[off:off + slot] = e + b'\x20' * (slot - len(e))
        ok += 1

    newb = bytes(d)
    assert len(newb) == len(src)
    os.makedirs(DST, exist_ok=True)
    open(base, 'wb').write(newb)

    # 되읽기
    bad = 0
    for off, slot, ko_text in K.CONFIG:
        e = enc(ko_text)
        pre = b'\x04' if len(e) + 1 <= slot else b''
        want = pre + e + b'\x20' * (slot - len(pre) - len(e))
        if newb[off:off + slot] != want:
            bad += 1
            print('  ★불일치 0x%05X' % off)
    # 대상 밖 변경 0 확인
    touched = bytearray(len(newb))
    for off, slot, _ in K.CONFIG:
        for i in range(off, off + slot):
            touched[i] = 1
    leak = sum(1 for i in range(len(newb)) if not touched[i] and newb[i] != src[i])
    print('%s  반영 %d  실패 %d  불일치 %d  대상밖변경 %d'
          % (NAME[6:], ok, fail, bad, leak))


if __name__ == '__main__':
    main()
