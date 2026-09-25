# GDM 한글패치 — 빌드 순서 (2026-08-08 기준)

⚠️ **ISO 빌드는 매번 사용자 허락을 받고 실행한다.**

## 0. 원본

* `work/dm/` — 세션1~7에 뽑은 104개
* `work/dm_all/` — **디스크 전량 351개** (세션8에 추가. 신규 조사는 여기서)

## 1. 빌드 — **항상 이걸로**

```
python tools/build_all.py      # 전 빌더를 정해진 순서로 + 검사까지
python tools/build_iso.py      # ★사용자 허락 후
```

⛔**부분 재빌드 금지.** 오타 하나를 고쳐도 `build_all.py` 로 처음부터 돌린다.
  2026-08-08에 `그래피크`→`그래픽` 하나 고치려고 일부만 돌렸다가,
  `propagate_ui_dup.py` 가 `CMDMN.BIN` 도 건드린다는 걸 잊고 `build_sysmenu2` 뒤에
  실행해 필드 메뉴가 통째로 깨졌다(`도구/장비` → `령또/심름`).

### 내부 순서 (참고 — 직접 돌릴 일 없음)

```
python tools/font_apply.py                                    # ★kocodes 바뀌면 반드시 먼저
python tools/runs_build.py                                    # MDT 대사(런 단위)
python tools/patch_missed.py                                  # ★런 우회 직접 패처 — runs_build 뒤
python tools/strip_he.py                                      # 장소 배너 끝 `へ` 제거
python tools/ui_build.py work/trans/ui_full_field.tsv FIELD_TEXT2.BIN
python tools/ui_build.py work/trans/ui_full_batle.tsv BATLE_TEXT2.BIN
python tools/build_sysmenu.py                                 # v1
python tools/propagate_ui_dup.py                              # 37개 사본 전파
python tools/build_sysmenu2.py                                # v2(세그먼트 인식) — v1 뒤
python tools/build_halfmenu.py                                # build_sysmenu2 뒤
python tools/build_config.py
python tools/build_museum.py                                  # DICDT/MTMES/MTOUT
python tools/patch_extra.py                                   # FACE2/DORAM
python tools/build_wdata.py                                   # 필드 장비·도구·마법
python tools/build_iso.py                                     # ★허락 후
```

★`kocodes.tsv` 를 건드렸으면 `work/build` 를 지우고 **처음부터 전부** 다시 돌린다
([[feedback_slot_reassign_all_builders]]).

## 2. 검사

```
python tools/runs_verify.py       # runs.tsv 되읽기
python tools/verify_ui_dup.py     # 37사본
python tools/final_check.py       # ★전 파일 미번역 (바이트 차분 기준)
python tools/sweep_diff.py 3      # MDT 전용 상세
```

## 3. 새 미번역이 나왔을 때

1. `tools/unbreak.py "깨진한글"` — 원문 역추적
2. `tools/unbreak.py --find "원문"` — 어느 파일인지 (`work/dm_all` 전량 대상)
3. 파일에 BE32 섹션표가 있으면 `museum.py` 모델, 아니면 `patch_extra.py` 구간 지정
4. 반영 뒤 `final_check.py` 로 0건 확인

⛔ **반각(JIS X0201) 표는 대상이 아니다** — `ITGET.BIN`, `WDATA.DAT` sec2/sec6.
   장비·도구 이름과 상태창 초록 라벨. 화면에서 탁점이 따로 찍히면 그것이다.
   사용자 결정(2026-08-08), 다시 꺼내지 말 것.
