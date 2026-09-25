# -*- coding: utf-8 -*-
"""전 빌더를 **정해진 순서로** 한 번에 돌린다. ISO 빌드는 하지 않는다.

★왜 필요한가 (2026-08-08 사고):
  `그래피크`→`그래픽` 오타 하나 고치려고 관련 빌더만 골라 돌렸는데,
  `propagate_ui_dup.py` 가 `FIELD_CMDMN.BIN` 도 건드린다는 걸 잊고
  `build_sysmenu2.py` **뒤에** 실행해 필드 메뉴 라벨을 통째로 덮어썼다
  (실기: `도구/장비` → `령또/심름`).
  → 부분 재빌드 금지. 무엇을 고쳤든 이 스크립트로 **처음부터 전부** 돌린다.

의존 순서에서 놓치기 쉬운 것:
  · `patch_missed`  는 `runs_build` **뒤** (먼저 돌면 덮어써진다)
  · `build_sysmenu2` 는 `propagate_ui_dup` **뒤** (propagate 가 CMDMN 을 건드린다)
  · `build_halfmenu` 는 `build_sysmenu2` **뒤**
  · `font_apply`    는 kocodes 를 건드렸으면 **맨 앞**
"""
import os
import shutil
import subprocess
import sys

STEPS = [
    # ★맨 앞 — 명장면 목록이 쓰는 한글이 허프만 트리에 들어가도록 kocodes 를 교환한다.
    #   kocodes 가 바뀌므로 반드시 `font_apply` **앞**이어야 한다.
    ('kocodes 교환', ['tools/make_swap.py']),
    ('폰트', ['tools/font_apply.py']),
    ('MDT 대사', ['tools/runs_build.py']),
    ('  └ 런 우회 패처', ['tools/patch_missed.py']),
    ('  └ 배너 へ 제거', ['tools/strip_he.py']),
    ('UI FIELD', ['tools/ui_build.py', 'work/trans/ui_full_field.tsv', 'FIELD_TEXT2.BIN']),
    ('UI BATLE', ['tools/ui_build.py', 'work/trans/ui_full_batle.tsv', 'BATLE_TEXT2.BIN']),
    ('시스템메뉴 v1', ['tools/build_sysmenu.py']),
    ('37사본 전파', ['tools/propagate_ui_dup.py']),
    # ★`propagate_ui_dup`·`ui_build` **뒤**에 둔다 — 둘 다 TEXT2/BBG 를 원본에서
    #   새로 쓰므로 먼저 돌면 전투 설명문이 통째로 사라진다
    ('전투 설명문', ['tools/build_batle.py']),
    ('전투 적·기술명', ['tools/build_mdat.py']),
    ('시스템메뉴 v2', ['tools/build_sysmenu2.py']),
    ('반각 메뉴', ['tools/build_halfmenu.py']),
    ('설정 화면', ['tools/build_config.py']),
    ('박물관', ['tools/build_museum.py']),
    # ★`build_museum` **뒤**에 둔다 — 같은 MTOUT.DAT 의 다른 구간(압축 스프라이트)
    ('설정자료집 그림', ['tools/build_mtout_gfx.py']),
    # ★`build_museum`(DICDT 텍스트) 와 `build_mtout_gfx`(한글 상자 원본) **뒤**에 둔다
    ('도감 예/아니오 상자', ['tools/build_dicdt_gfx.py']),
    ('FACE2/DORAM', ['tools/patch_extra.py']),
    ('필드 장비표', ['tools/build_wdata.py']),
    # ★`patch_extra` **뒤**에 둔다 — DORAM.BIN·FACE2.DAT 를 둘 다 건드린다
    ('예/아니오 상자', ['tools/build_yesno.py']),
    # 명장면 목록 — 허프만 스트림 재인코딩(`SVRDT.DAT` 는 다른 빌더가 안 건드린다)
    ('명장면 목록', ['tools/build_scene.py']),
]

CHECKS = [
    ('runs 되읽기', ['tools/runs_verify.py']),
    ('37사본 검증', ['tools/verify_ui_dup.py']),
    ('★미번역 전수', ['tools/final_check.py']),
]


def run(name, argv):
    print('\n=== %s : %s' % (name, ' '.join(argv[1:]) or argv[0]))
    r = subprocess.run([sys.executable] + argv, capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    tail = [l for l in (r.stdout or '').rstrip().split('\n') if l.strip()][-3:]
    for l in tail:
        print('   ' + l)
    if r.returncode != 0:
        print('   ★실패 (exit %d)' % r.returncode)
        print((r.stderr or '')[-800:])
        raise SystemExit(1)


def main():
    if '--keep' not in sys.argv:
        shutil.rmtree('work/build', ignore_errors=True)
        os.makedirs('work/build', exist_ok=True)
        print('work/build 비움')
    for name, argv in STEPS:
        run(name, argv)
    print('\n' + '=' * 40 + '\n검사')
    for name, argv in CHECKS:
        run(name, argv)
    print('\n빌드 완료 — work/build %d파일' % len(os.listdir('work/build')))
    print('★ISO 는 사용자 허락 후 `python tools/build_iso.py`')


if __name__ == '__main__':
    main()
