# -*- coding: utf-8 -*-
r"""★전프로젝트 규칙: 문장부호 뒤 공백 1칸(반각·전각) 삭제 — 블루 시드 tools/build.py squeeze() 표준 목록 그대로 (2026-10-14 적용).
  인코더 입구(runs_build.encode · bintext.encode)에서 건다 → 대사·UI·전투·박물관·명장면 등 모든 번역에 적용.
  한글이 든 문자열에만(일본어 원문 검색용 인코딩은 그대로).
"""
import re

PUNCT = (",.!?:;)]}'\"~"
         '、。，．！？：；）］｝」』】〉》”’…‥・·～〜♪♥')
_RX = re.compile('([' + re.escape(PUNCT) + '])[ 　](?=[^ 　])')   # 뒤에 글자가 올 때만 — 끝 공백(표시 폭 채움)은 둠


def squeeze(t):
    if not any('가' <= c <= '힣' for c in t):
        return t
    return _RX.sub(r'\1', t)
