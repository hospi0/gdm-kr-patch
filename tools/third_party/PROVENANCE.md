# 외부 구성요소 출처 (third_party)

우리 도구(`tools/*.py`)와 **섞지 않는다**. 여기 있는 것은 전부 외부 저작물이며,
우리 빌드 경로에 넣을 때는 이 파일에 기록한 버전·라이선스·전제를 함께 확인한다.

---

## new-parm-archives-tools

| 항목 | 값 |
|------|-----|
| 출처 | https://github.com/AngelouCurator/new-parm-archives-tools |
| 커밋 | `1453906aef0e87eefe240ee976fbf6d53a071e63` (2026-07-06, "Populate tools repo: original pipeline, harness drivers, methods docs") |
| 가져온 날 | 2026-08-17 |
| 라이선스 | MIT (원저작 코드·문서에 한함). `NOTICE` 참조 |
| 편입 범위 | `.git` 제외 전량 138파일 / 약 1.30 MB |

**무엇인가** — 같은 게임 *Grandia: Digital Museum* 의 **영문 번역 패치**
([new-parm-archives-patch](https://github.com/AngelouCurator/new-parm-archives-patch))를
만든 원본 파이프라인과 역공학 기록이다. 우리 프로젝트와 대상 게임·대상 파일이 겹친다.

**게임 데이터는 들어 있지 않다** (설계상 의도). 디스크 이미지·추출 스크립트·수정 자산·
사전 데이터 없음. 상위 Java 도구(TrekkiesUnite118 `GrandiaTranslation`)도 **번들되어 있지 않고**
`tools/setup.sh` 가 빌드 시점에 clone 한다(그 저작물은 unlicensed — 우리 빌드 경로에
넣으려면 별도 판정 필요).

**저작자 표시 의무** — MIT + `NOTICE`. 역공학 방법·포맷 문서의 원류는
TrekkiesUnite118 이며, 그 사실을 명시하라고 `NOTICE` 가 요구한다.
우리 배포물에 이 도구의 산출물이 들어가면 두 곳 모두 크레딧에 넣는다.

### 우리 미해결 항목과의 대응

⚠️ 아래는 **저쪽 문서의 주장**이다. 우리 리비전에서 재현하기 전에는 사실로 승격하지 않는다.
(우리 원본은 `Grandia - Digital Museum (Japan) (Rev A) (10M)` — 같은 판인지 미확인)

| 우리 미해결 | 저쪽 자료 | 비고 |
|---|---|---|
| **타이틀 화면 `新しく始める`** — 「블롭마다 다른 트리」에서 막힘 | `docs/mgame-format.md` §"Static tree-builder — SOLVED", `tools/mg_tree.py` + `tools/sh2emu.py` + `tools/mg_codec.py` | **디코더 주소 `0x06015DF0` 이 우리가 짚은 진입점과 동일하다.** 트리 생성 루틴 `0x0601401A`(길이표+필터모드) / `0x060144EE`(노드+루트)를 SH-2 인터프리터로 **오프라인 실행**해 트리를 정적 생성한다 |
| 명장면(극장) | `docs/theater-captioning.md`, `docs/theater-gfx.md`, `docs/theater-caption-tuning.md`, `src/theater/` | 자막을 **엔진 훅**으로 넣는 경로. 우리는 목록만 한글화했고 자막은 안 했다 |
| 몬스터 도감 상자 | `docs/museum-viewers-format.md` §"Monster-Encyclopedia BLACK SCREEN — root cause", §"Monster names — DICDT.DAT" | 우리 `DICDT.DAT` 작업과 같은 파일 |
| 설정자료집 | 같은 문서 §"Design Materials (設定資料集, MATER.BIN)" | 저쪽은 `MATER.BIN`, 우리는 `MTOUT.DAT` 0x13E00 블록으로 처리했다 — **같은 것인지 대조 필요** |
| 예산(길이) 벽 | `docs/dialogue-growth-SOLVED.md`, `docs/event-op-desync-fix.md`, `docs/step1-injection.md`, `docs/step1-limits.md` | 상자 **성장**(임의 길이 삽입) 경로. 우리는 등길이 제자리 교체로만 해왔다 |
| 반각/폰트 상자 | `docs/grandia1-scnrl-fontbox-patches.md`, `docs/style-guide.md` | ⛔ 우리 범위에서 반각표는 제외 대상([[feedback_gdm_no_halfwidth_table]]) |

### 바로 쓰려면 필요한 전제

- `tools/mg_tree.py` 는 **HWRAM 이미지**를 요구한다 — 기본 경로 `work/mgame/hwram.bin`
  (상주 엔진 코드). 게임 데이터라 저장소에 없다. **우리 세이브스테이트에서 직접 떠야 한다**
  (⚠️ Work RAM 은 swap16 — [[feedback_saturn_read_prior_projects_first]]).
- `tools/*.py` 는 서로를 평평한 이름으로 import 한다(`import iso`, `import dicdt`,
  `import sh2emu` 등). 실행할 때 그 디렉터리를 `sys.path` 에 넣어야 하고,
  **우리 `tools/` 와 이름이 겹치지 않게** 반드시 이 하위 디렉터리 안에서 돌린다.
- 선택 의존: `numpy`, `PIL` (일부 그래픽 도구).
- 경로 기본값·`GDM_BIOS`/`GDM_STATE`/`GDM_MG_STATEDIR` 환경변수는 저쪽 환경 기준의
  자리표시자다. 우리 경로로 다시 지정해야 한다.

---

## 여기 두지 않은 것 — 세가 CMP 코덱

MrConan1 의 `CMP_CMPRESS`/`CMP_DECMPRESS` 는 **새턴 범용 도구**라 프로젝트 안이 아니라
`C:\claude\utils\sega-cmp\` 에 등록돼 있다(그 폴더 `README.md` 참조).
