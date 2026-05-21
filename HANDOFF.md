# HANDOFF — Cowork → Claude Code (또는 다음 세션)

**마지막 인계 시각**: 2026-05-22 (M11.6 [PR #26](https://github.com/v0o0v/assetcache-mcp/pull/26) main 머지 (`da4f169`) + M11.7 [PR #27](https://github.com/v0o0v/assetcache-mcp/pull/27) main 머지 (`04c205e`) + M11.8 starter 작성)
**마지막 완료 작업**: **M11.6 + M11.7 main 머지 + M11.8 starter** — M11.6 (PR #26) 가 M11.5 LIVE 의 별도 발견 2건 (시트 5/5 palette 라벨 부재 + animation='other' fallback) 을 BATCH_SPRITESHEET_PROMPT palette tone group enum + 두 prompt 의 "do NOT use 'other'" 가이드로 해소 — LIVE 결과 시트 palette 5/5 + 'other' 0/6 완전 차단.  M11.7 (PR #27) 가 M11.6 LIVE 의 mood 노이즈 2건 (crown 에 mood=heroic/playful + 시트 5/5 일률 mood=minimalist/neutral) 을 mood OPTIONAL + category 별 mood 차단으로 해소 — LIVE 결과 crown mood 2→0 (A2 완벽), 시트 mood 10→5 (58% 감소, A1 부분).  회귀 **1601 passed + 1 skipped + 63 deselected** + 옵트인 6/6 PASSED (M11.5 strict 2 + M11.6 신규 2 + M11.7 신규 2).  M11.7 한계: catch-all 'neutral' 시트 4/5 잔존 → **M11.8 spec/plan starter 작성됨** ([spec](./docs/superpowers/specs/2026-05-22-m11-8-mood-seed-disable.md) / [plan](./milestones/M11_8_plan.md)) — LabelRegistry 시드 `mood.neutral` + `mood.minimalist` `is_enabled=0` 마이그 (v0.2.7 candidate).  ⚠️ `palette.neutral` 은 절대 유지 (M11.6 tone group 핵심).

**M11.3 PR #20 산출물** (squash 후 `7ad0f3d`):
- `core/batch/sheet_classifier.py` — `classify_image_assets` 에 `cache` + `save_sprite_meta` 인자 추가 (시트 hit 시 자동 sprite_meta enrich+save)
- `core/batch/manager.py` — `_BoundedLRUCache(OrderedDict)` + `BatchManager._detection_cache` (max 1024 LRU)
- `core/batch/poller.py` — `_try_enrich_with_sheet` 가 `store.get_sprite_meta` 우선 확인 후 cache hit 시 `detect_sheet` 우회
- `core/analyzer/spritesheet_meta.py` — `animations_json_to_specs` helper 신설
- `core/sheet/detect.py` — D-2: FrameSpec.w/h 가 `stride_x/y` (slot 크기) 사용
- `core/analyzer/payload_parser.py` — B: `_coerce_to_dict` (list/None graceful)
- `core/llm/backends/gemini.py` — C: `batch_embed inlined_requests` 가 `{"contents":[...]}` 단일 dict
- `web/templates/settings.html` + ko/en `.po/.mo` — A: modalityOrder + chainAdd + i18n "Spritesheet chain"
- LIVE 검증 결과 `milestones/M11_3_verification.md`

**M11.4 산출물** (이번 세션, PR #21 squash 머지 `7794d48`):
- `core/sheet/grid_detect.py` — 2-path (alpha valley + color-edge fallback) + `Config.grid_detect_alpha_color_weight=0.5` 전파 wiring (detect_sheet → BatchManager / BatchPoller / SpritesheetAnalyzer)
- `core/labels.py` seed 확장 — category `inventory_item`/`ui_icon`, mood `minimalist`/`neutral`, palette `high_contrast`
- `core/analyzer/messages.py` — BATCH_IMAGE_PROMPT 재작성 (category enum + palette tone group + hex 금지 + inventory_item 가이드)
- `core/analyzer/payload_parser.py` — `_PAYLOAD_HEX_RE` 신설 + multi axis (palette/mood/animation) 모두 `{axis}_hex={value}` 명시 violation
- `core/analyzer/sprite.py` — sync `_build_system_prompt` parity + guidance 가 registry 라벨 enabled 일 때만 포함 (동적)
- `milestones/M11_4_verification.md` — auto 1592 + 옵트인 Gemini + 수동 synthetic + LIVE 시나리오 + 한계
- 신규 test: 9 grid_detect color-edge + 3 seed + 9 payload/prompt + 5 sync (3 + 2 옵트인 llm_integration) + 5 wiring + 2 hex 일관성 + 2 guidance 동적화 = **+33**

**현재 브랜치**: `main` (PR #27 squash 머지 완료, feat 브랜치 자동 삭제 + remote prune 완료)

**다음 세션 작업**:
1. **M11.8 implement** — `milestones/M11_8_plan.md` 의 Phase 1 (시드 비활성화 + migration TDD) 부터.
   - 신규 모듈/함수: `core/labels.py` `DISABLED_BY_DEFAULT` 상수 + `core/store.py` `set_label_enabled_if_unchanged` helper + `meta.disabled_by_default_signature` 마커
   - ⚠️ **핵심 주의**: `palette.neutral` 은 절대 비활성화 X (M11.6 tone group enum 핵심 토큰).  `mood.neutral` + `mood.minimalist` 만 대상
   - LIVE 검증: `scripts/drive_live_batch.py` 그대로 재사용
2. (선택, M11.8 머지 후) v0.2.7 publish — `pyproject.toml` + `__init__.py` 0.2.2 → 0.2.7 bump + tag → Trusted Publishing 6회째 자동 (M11.4~M11.7 의 v0.2.3~v0.2.6 결번 누적 deliver).

이 문서는 작업이 중단될 때 다음 세션이 "현재 어디까지 와 있는가"를 한 번에 파악하도록 작성된 스냅샷이다.

## 1. 한 줄 요약

**v0.2.x patches PR #18 머지 완료** (main `12ebc42`). M11.1 batch 의 "stub persist" 한계를 3 단계로 해결 (payload_parser / tech_meta / spritesheet_meta + BatchPoller registry/library_dir 주입). 회귀 **1490 passed + 3 skipped + 56 deselected** (+66 신규, 회귀 0). 신규 의존성 0. MCP 20 도구 그대로. **M11.2 spec 작성됨** (batch spritesheet modality `chat_spritesheet` 신설로 grid-only 시트 animation 라벨 해소). 다음 세션 첫 작업: M11.2 spec 읽고 plan 확장 → TDD.

## 2. 검증된 사실 (M10 완료 시점)

자동 — `pytest -q` 결과 **1103 passed + 1 skipped + 40 deselected** (M10 +57, baseline 1046)

| Phase | 핵심 산출물 | 신규 테스트 |
|---|---|---:|
| 0 — rename mechanical | `src/gah/` → `src/assetcache/` + 모든 import / config / babel.cfg / spec / docs / `.po` 경로 | 0 (회귀만) |
| 1 — 마이그레이션 helper | `core/migration.py` (detect + MigrationRunner async copy/move + rollback + 디스크 검사) + `web/routers/migration.py` + SSE + `_migration_banner.html` + CLI `--migrate=copy\|move` + i18n msgid 10건 (**v0.1.1 yagni-clean 됨**) | +21 |
| 2 — PyPI 알림 (M9 cherry-pick) | `core/updater/version.py` (semver + classmethod + ordering) + `checker.py` (PyPI JSON API + ETag 캐시 + 24h PollingLoop) + `pip_command.py` (pipx/uv/pip 분기) + `web/routers/updates.py` 단순화 + `_pypi_update_banner.html` + `tray.TrayController` + `_TrayBridge` Qt Signal cross-thread + i18n msgid 4건 | +17 |
| 3 — docs + i18n catalog + verification | README/CLAUDE/HANDOFF/DESIGN 표기 일괄 갱신 + `tests/test_locale_assetcache_msgid.py` (5 msgid × 2 lang = 10 instance) + `milestones/M10_verification.md` (수동 시나리오 7건) | +10 |
| 4 — PyPI 패키지 + 빌드 + 배포 | `pyproject.toml` name=`assetcache-mcp` + version=0.1.0 + scripts + classifiers + package-data + `main_mcp()` entry + `python -m build` + TestPyPI + 정식 PyPI + Trusted Publishing (OIDC) + GitHub Actions workflow | 0 (배포 검증) |
| 5 — 마일스톤 wrap-up | PR #11 머지 + v0.1.0 GitHub release publish + repo rename + token revoke + cleanup PR | 0 |
| 후속 fix | workflow Node.js 24 호환 (`actions/checkout@v6` + `actions/setup-python@v6`, PR #12) | 0 |
| **M10 전체** | **MCP 20 도구 그대로, 신규 의존성 0 (run-time), dev `build` + `twine` 추가** | **+57** |

수동 — 시나리오 1~7 의 자동 가능 부분 (rename 회귀 / wheel local smoke / TestPyPI / 정식 PyPI install / Trusted Publishing workflow) 검증 통과. 시나리오 1~5 의 사용자 직접 부분 (트레이 + 배너) 은 [`milestones/M10_verification.md`](./milestones/M10_verification.md) §2 참고.

## 3. 환경 (재현용)

| 항목 | 값 |
|---|---|
| OS | Windows 10 (Mac/Linux 정식 검증은 M11 또는 별도 마일스톤) |
| Python | python.org 3.12 (`C:\Users\v0o0v\AppData\Local\Programs\Python\Python312\python.exe`) |
| venv | `C:\Users\v0o0v\.venvs\gah\` (이름은 그대로 유지 — 새 이름 `.venvs\assetcache` 로 마이그레이션은 향후 옵션) |
| 작업 폴더 | `D:\ClaudeCowork\game-asset-helper\game-asset-helper\` (main 저장소) |
| 사용자 런타임 데이터 | `C:\Users\v0o0v\AppData\Roaming\AssetCacheMCP\` (M10 rename 후) |
| 라이브러리 루트 | `%APPDATA%\AssetCacheMCP\library\` |
| 메타 DB | `%APPDATA%\AssetCacheMCP\metadata.db` (WAL, M7 `unity_imports` / `projects` / `asset_usage` 확장 유지) |
| **MCP 도구 수** | 20 도구 (M10 신규 0) |
| PyPI 패키지 | `assetcache-mcp` 0.1.2 (https://pypi.org/project/assetcache-mcp/0.1.2/) |
| CLI 콘솔 스크립트 | `assetcache` (트레이/MCP 통합) + `assetcache-mcp` (MCP stdio 전용, `main_mcp` entry) |

**금기**: Microsoft Store Python, Cowork 작업 폴더 내부 venv.

M10 신규 의존성: 0 (run-time). dev 만 +2 (`build`, `twine`).

## 4. 새 세션에서 바로 이어가는 방법

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\Activate.ps1"
```

```powershell
cd D:\ClaudeCowork\game-asset-helper\game-asset-helper
```

```powershell
git checkout main
```

```powershell
git pull
```

```powershell
pytest -q
```

→ main 기준 (PR #27 머지 후): **`1601 passed, 1 skipped, 63 deselected`** + 옵트인 6 PASSED (llm_integration).

**현재 브랜치 = `main`** (PR #27 squash merge `04c205e`, feat/m11-7-mood-noise-cleanup 자동 삭제 + remote prune 완료).

## 5. 다음 세션 진입 절차 (PR #27 머지 — M11.8)

### 5.0 v0.2.2 이후 publish 누적 보류

M11.3 의 v0.2.2 publish 이후 M11.4 (v0.2.3) / M11.5 (v0.2.4) / M11.6 (v0.2.5) / M11.7 (v0.2.6) 4 마일스톤 publish 모두 보류 누적.  M11.8 머지 후 `pyproject.toml` + `src/assetcache/__init__.py` 0.2.2 → 0.2.7 직접 bump + tag v0.2.7 push → Trusted Publishing OIDC 자동 (6회째) 권장.

### 5.1 M11.8 implement (mood 시드 `neutral`/`minimalist` 비활성화)

**spec 읽기**:

```powershell
code docs/superpowers/specs/2026-05-22-m11-8-mood-seed-disable.md
```

```powershell
code milestones/M11_8_plan.md
```

**브랜치 생성 + baseline 확인**:

```powershell
git checkout -b feat/m11-8-mood-seed-disable
```

```powershell
pytest -q
```

→ 1601 passed 확인 후 Phase 1 (시드 비활성화 + migration TDD) red→green 부터.

⚠️ **핵심 주의**: `palette.neutral` 은 절대 비활성화 X (M11.6 tone group enum 핵심).  `mood.neutral` + `mood.minimalist` 만 대상.

### 5.0.1 v0.2.x reactive patch backlog (M11.2 외 잔존)

PR #18 (patch A/B/C) 머지 완료로 backlog 정리됨. 남은 후보:

| # | 항목 | 영향 | 시간 |
|---|---|---|---|
| ~~A~~ | ~~image/audio Gemini batch 결과 → label parsing~~ | ✅ **PR #18 patch A 완료** | — |
| B | **`BatchPoller polling silent fail` root cause 조사** (M11.1 manual 검증 중 사용자 첫 tray 가 polling 안 한 이유 — silent crash 의심, thread-local SQLite connection 가능성) | reproducibility | ~수시간 |
| C | **`store.list_labels_raw` race condition 진짜 원인** + thread-safe enforce | rare 발생 (defensive skip 이미 `4a798fd` patch) | ~수시간 |
| D | **OpenAI Batch API** + **Anthropic Batch API** | 다중 backend batch | 1~2일 |
| E | **file destination batch** (>20MB inline 우회) | 큰 batch 지원 | 1일 |

M11.2 implement 후 사용자 결정 — backlog B/C/D/E 중 우선순위 또는 M12 (C4 측정) 진행.

### 5.1 로드맵 (2026-05-20 brainstorm + M11.2 추가)

상세 spec: [`docs/superpowers/specs/2026-05-20-roadmap-design.md`](docs/superpowers/specs/2026-05-20-roadmap-design.md) (main `b3f8fe8`).

| Tier | M# | 마일스톤 | 의존 |
|---|---|---|---|
| **0** (완료) | M11 | Multi-backend LLM Architecture | ✅ v0.2.0 |
| **0** (완료) | M11.1 | Gemini Batch API + /analyzing dashboard | ✅ v0.2.1 |
| **0** (다음) | **M11.2** | **Batch Spritesheet Modality** (`chat_spritesheet` 신설) — PR #18 한계 (grid-only 시트 animation 라벨) 해소 | M11.1 + PR #18 |
| **1** | M12 | C4 측정 / 학습 / 벤치마크 (6 backend 정확도 비교) | M11 |
| 1 | M13 | Mac/Linux 검증 + M11 cross-platform | M11 |
| **2** (큰 새 기능) | M14 | MCP 원격 통신 (HTTP/SSE + 인증) | 독립 |
| 2 | M15 | Unity Editor 통합 (drag-drop / 자동 import) | 독립 |
| **3** | M16 | C2 이미지/사운드 유사 검색 | M11 |
| 3 | M17 | 성능 (대량 라이브러리) | 독립 |
| 3 | M18 | 분산 분석 (여러 PC 공유) | **M14 필수** |

권장 다음: **M11.2 implement** → PR → main → tag v0.2.2 → Trusted Publishing 자동 publish (5회째).

### 5.2 Reactive backlog (별도 트리거 시)

| 항목 | 트리거 |
|---|---|
| 사용자 피드백 수집 | [PyPI download 통계](https://pypistats.org/packages/assetcache-mcp) + [GitHub Issues](https://github.com/v0o0v/assetcache-mcp/issues) |
| v0.2.x patch 누적 | bug fix 발견 시 — tag push 한 줄로 자동 publish (Trusted Publishing 30초 패턴, 4회 검증) |
| 코드 서명 + 자동 업데이트 (M9 복귀) | SignPath 채택 결정 시 — spec/plan 보존됨, feat/m9 브랜치는 deleted |

### 5.3 worktree 상태

✅ `git worktree list` → main 만 출력. memory feedback `feedback_no_worktrees` 적용.

### 5.4 다음 세션이 자동 로드하는 메모리

자동 — `MEMORY.md` 의 `project_pr18_batch_persist_patches_merged` (이번 세션 신규) 가 최신 스냅샷. `project_m11_2_starter` (이번 세션 신규) 가 M11.2 진입 가이드. 이전 `project_m11_1_v021_publish` / `project_m10_complete` / `project_m11_phase0_progress` 는 historical (PR #18 머지로 supersede).

## 6. 마일스톤 정렬

| # | 이름 | 상태 |
|---:|---|---|
| M0~M8 | v1 (뼈대 ~ 패키징 + i18n) | ✅ 완료 (main 머지) |
| M9 | 코드 서명 + 자동 업데이트 | ⚠️ implementation 완료 / path pivot (feat/m9 deleted, spec/plan 만 보존) |
| M10 | PyPI 배포 + AssetCacheMCP rename | ✅ 완료 (PR #11/#12 main 머지) |
| v0.1.1 | yagni-clean + 첫 Trusted Publishing OIDC | ✅ ([PR #14](https://github.com/v0o0v/assetcache-mcp/pull/14)) |
| v0.1.2 | PyPI 페이지 정직성 patch | ✅ ([PR #15](https://github.com/v0o0v/assetcache-mcp/pull/15)) |
| 로드맵 brainstorm | M11~M18 8 마일스톤 design | ✅ (main `b3f8fe8`) |
| M11 | Multi-backend LLM Architecture | ✅ v0.2.0 ([PR #16](https://github.com/v0o0v/assetcache-mcp/pull/16) `f68ef88`, [PyPI](https://pypi.org/project/assetcache-mcp/0.2.0/)) |
| M11.1 | Gemini Batch API + /analyzing dashboard | ✅ v0.2.1 ([PR #17](https://github.com/v0o0v/assetcache-mcp/pull/17) `782a047`, [PyPI](https://pypi.org/project/assetcache-mcp/0.2.1/)) |
| **v0.2.x patches** | batch persist 보강 (label/meta/spritesheet) | ✅ ([PR #18](https://github.com/v0o0v/assetcache-mcp/pull/18) main 머지 `12ebc42`, 회귀 1424 → 1490) |
| **M11.2** | Batch Spritesheet Modality (`chat_spritesheet` 신설) | ✅ ([PR #19](https://github.com/v0o0v/assetcache-mcp/pull/19) main 머지 `d34f1dd`, +38 신규, 회귀 1528) |
| **M11.3** | **Detection Cache + 부수 patch 4건** (옵션 B+C, A/B/C/D-2) | ✅ ([PR #20](https://github.com/v0o0v/assetcache-mcp/pull/20) main 머지 `7ad0f3d`, +30 신규, 회귀 1559). **[v0.2.2 PyPI publish 완료](https://pypi.org/project/assetcache-mcp/0.2.2/)** (main `10c3add` bump + tag) |
| **M11.4** | **grid_detect 강화 + LLM 분류 정확도** (v0.2.3 candidate) | ✅ ([PR #21](https://github.com/v0o0v/assetcache-mcp/pull/21) main squash `7794d48`, +33 신규, 회귀 1592). v0.2.3 publish 보류 |
| **M11.5** | **LIVE validation + acceptable set strict** (v0.2.4 candidate) | ✅ ([PR #23](https://github.com/v0o0v/assetcache-mcp/pull/23) main squash `ed47403` + [PR #24](https://github.com/v0o0v/assetcache-mcp/pull/24) `1be53ae` docs cleanup, 회귀 1592). v0.2.4 publish 보류. LIVE Gemini batch 통과 (D-1 + LLM #3) + acceptable set strict |
| **M11.6** | **BATCH_SPRITESHEET_PROMPT palette + 'other' fallback 정리** (v0.2.5 candidate) | ✅ ([PR #26](https://github.com/v0o0v/assetcache-mcp/pull/26) main squash `da4f169`, +7 신규 4 옵트인, 회귀 1597). v0.2.5 publish 보류. 시트 palette 5/5 + 'other' 0/6 |
| **M11.7** | **mood OPTIONAL + category 별 mood 차단** (v0.2.6 candidate) | ✅ ([PR #27](https://github.com/v0o0v/assetcache-mcp/pull/27) main squash `04c205e`, +6 신규 2 옵트인, 회귀 1601). v0.2.6 publish 보류. crown mood 2→0 + 시트 mood 10→5 |
| **M11.8** | **mood 시드 `neutral`/`minimalist` 비활성화** (v0.2.7 candidate) | 📋 spec/plan starter 작성됨, **다음 세션 implement 대상**. ⚠️ palette.neutral 절대 유지. [spec](./docs/superpowers/specs/2026-05-22-m11-8-mood-seed-disable.md) / [plan](./milestones/M11_8_plan.md) |
| M12~M18 | 측정/Mac-Linux/원격 통신/Unity Editor/유사 검색/성능/분산 | 📋 미정 |

## 7. 후속 정리거리 (해결됨/잔존)

### 7.1 PR #18 (이번 세션) 직접 정리

- ✅ M11.1 v0.2.1 의 batch stub persist 한계 3건 모두 해소 (label/meta/spritesheet) — verification [§ "알려진 한계"](./milestones/M11_1_verification.md) 표시
- ✅ `core/analyzer/payload_parser.py` / `tech_meta.py` / `spritesheet_meta.py` 신설 — sync/batch 공유 패턴 정착 (sound 만 비대칭 — librosa.load 2회 비용 회피)
- ✅ BatchPoller 가 `registry` + `library_dir` 모두 주입 받음 (graceful fallback 유지)
- ✅ 회귀 1424 → 1490 (+66 신규 테스트, 회귀 0), 신규 의존성 0
- 📋 **v0.2.2 publish** — M11.2 와 묶을지 별도일지 사용자 결정. 별도라면 지금 `git tag v0.2.2 && git push origin v0.2.2` 한 줄로 Trusted Publishing 자동 (5회째 패턴 검증)

### 7.2 잔존 (M11.2 대상)

- 📋 **batch 경로 grid-only 시트 animation 라벨 부재** — Aseprite/TexturePacker frameTags 없는 시트는 frame 차원만 채워지고 animation 라벨은 비어 있음. M11.2 spec 작성됨 → 다음 세션 implement.

### 7.3 historical (참고용)

- ✅ M0~M11.1 모두 main 머지 + PyPI publish 완료 (v0.1.0~v0.2.1, Trusted Publishing 4회 자동)
- ✅ M9 path pivot — feat/m9 브랜치 deleted, spec/plan 만 `docs/superpowers/{plans,specs}/2026-05-19-m9-*.md` 보존
- ✅ M10~v0.1.2 cleanup — TestPyPI/PyPI token revoke, GitHub Actions Node.js 24 호환 (v6)

자세한 plan / spec / verification:

- [`docs/superpowers/specs/2026-05-21-m11-2-batch-spritesheet-modality.md`](./docs/superpowers/specs/2026-05-21-m11-2-batch-spritesheet-modality.md) — **M11.2 spec (다음 세션 implement 대상)**
- [`milestones/M11_2_plan.md`](./milestones/M11_2_plan.md) — **M11.2 plan starter**
- [`milestones/M11_1_verification.md`](./milestones/M11_1_verification.md) — M11.1 + PR #18 patches 의 한계/해소 표시
- [`docs/superpowers/specs/2026-05-20-gemini-batch-api-design.md`](./docs/superpowers/specs/2026-05-20-gemini-batch-api-design.md) — M11.1 spec (전제)
- [`docs/superpowers/specs/2026-05-20-roadmap-design.md`](./docs/superpowers/specs/2026-05-20-roadmap-design.md) — 전체 로드맵
