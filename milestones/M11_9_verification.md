# M11.9 Verification

## 1. 자동 검증

### 1.1 회귀 (Phase 2-I + Phase 4-A)

| 시점 | Command | 결과 |
|---|---|---|
| Phase 1-A baseline | `pytest -q` (main `a5c8dbb` + `feat/m11-9-backend-cleanup` 브랜치) | `1612 passed, 1 skipped, 64 deselected` |
| Phase 1-B red 단독 | `pytest tests/test_m11_9_backend_purge.py -v` | **8 failed + 1 passed** (chains default 자연 PASSED) |
| Phase 1-C green 부분 | `pytest tests/test_m11_9_backend_purge.py -k "known_backends or default_backends or chains or registry or backends_package" -q` | **5 passed** |
| Phase 2-I 광역 | `pytest -q` (Phase 2 cleanup 후) | `1560 passed, 1 skipped, 57 deselected` |
| Phase 4-A 최종 | `pytest -q` (pip uninstall 후) | `1560 passed, 1 skipped, 57 deselected` |

**회귀 카운트 변화** — baseline `1612` → final `1560` (-52). plan AC #15 band `~1555-1569` 정확 적중.

**deselected 변화** — `64` → `57` (-7) = claude/openrouter/huggingface integration 3 + cross-backend 4 (claude/openrouter/huggingface integration + supports_batch claude/openrouter/huggingface).

**`1 skipped`** 유지 — 기존 `test_web_routers_sse.py:140` heartbeat skip 그대로.

### 1.2 Red → Green 케이스 추적 (`tests/test_m11_9_backend_purge.py`, 9 케이스)

| # | 케이스 | 1-B (red) | 1-C 후 | 2-I 후 |
|---|---|:-:|:-:|:-:|
| 1 | `test_known_backends_is_three` | ❌ | ✅ | ✅ |
| 2 | `test_default_backends_keys_three` | ❌ | ✅ | ✅ |
| 3 | `test_default_chains_no_removed_refs` | ✅ (자연) | ✅ | ✅ |
| 4 | `test_registry_no_removed_factories` | ❌ | ✅ | ✅ |
| 5 | `test_backends_package_no_removed_modules` | ❌ | ✅ | ✅ |
| 6 | `test_settings_template_backend_order_is_three` | ❌ | ❌ | ✅ |
| 7 | `test_locale_po_no_removed_backend_strings` | ❌ | ❌ | ✅ |
| 8 | `test_help_partials_three_backends_only` | ❌ | ❌ | ✅ |
| 9 | `test_no_backend_module_imports_in_tests` | ❌ | ❌ | ✅ |

### 1.3 의존성 absence (AC #17)

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\python.exe" -m pip list | Select-String "anthropic|huggingface|openrouter"
```
→ **출력 0 라인** (anthropic 0.103.1 + huggingface_hub 1.15.0 uninstall 완료).

### 1.4 라이브 docs grep (AC #15 ~ Verification metric)

```powershell
git grep -nE "6 backend|6 백엔드" -- ":!milestones/HISTORY.md" ":!milestones/M11_*.md" ":!docs/superpowers/**"
```
→ **0 라인** (라이브 docs 매칭 부재).

```powershell
git grep -nE "ClaudeBackend|OpenRouterBackend|HuggingFaceBackend" -- ":!milestones/HISTORY.md" ":!docs/superpowers/**" ":!tests/test_m11_9_backend_purge.py"
```
→ **0 라인** (M11.9 red test 본문은 검증 의도 정상 참조라 제외).

```powershell
python -c "import assetcache.core.llm.backends.claude"
```
→ `ModuleNotFoundError`.

### 1.5 옵트인 LIVE (Phase 4-B)

```powershell
pytest -m llm_integration tests/test_llm_backend_gemini_integration.py tests/test_llm_backend_openai_integration.py -v
```
→ Claude 세션에서 자동 실행 결과 **6 skipped** — 모두 `GEMINI_API_KEY`/`OPENAI_API_KEY` env 미설정 (PowerShell child 가 user shell env 상속 안 함).  사용자 PowerShell 에서 env 설정 + 직접 재실행 필요 — `§4. 수동 검증 항목` 참조.

### 1.6 babel pot/mo 처리

⚠️ **babel pot 재추출은 skip** — `babel.cfg` 의 `src/assetcache/**.py` 패턴이 babel `pathmatch` 에서 recurse 안 해, `pybabel extract -F babel.cfg` 출력이 `src/assetcache` 직속 .py 만 스캔 (`{config,app,tray,__main__,logging_setup}.py` 만 ~5개). 결과 pot 가 active msgid 1개 (헤더만), .po 의 모든 기존 msgid 가 `#~ obsolete` 처리되는 회귀가 즉시 검출됨.

**해결책**: 직접 `messages.po` (ko/en) 편집 + `pybabel compile -d ...` 만 진행.  `.pot` 는 git restore 로 HEAD 상태 유지 (3 msgid 부재 — 원래부터 stale, hand-maintained .po 로 보강돼 있던 흔적).

**Follow-up (M11.9 범위 외)**: `babel.cfg` 패턴을 `src/assetcache/**/*.py` 로 교정 + pot 재생성 시 모든 .py / .html 정확 스캔되는지 확인 — 별 마일스톤 / chore 작업.

## 2. 산출물 요약 (8 표면)

| 표면 | 변경 |
|---|---|
| 1. 코드 모듈 | `src/assetcache/core/llm/backends/{claude,openrouter,huggingface}.py` 3 파일 삭제 |
| 2. registry | `_default_{claude,openrouter,huggingface}_factory` 3 + `from_config` 6 kwargs (3 factory + 3 default assign) + factory dict 3 + `:70` stale comment 제거 |
| 3. config | `_KNOWN_BACKENDS` 6→3 + `_default_backends()` 6→3 키 + docstring `6 backend` → `3 backend` |
| 4. tests | 7 파일 삭제 (mock 3 + LIVE 3 + cross_backend 1) + 6 파일 정리 (chain / registry / setup_url / settings_router / partials / config_migration) + supports_batch 6→3 |
| 5. 의존성 | `pyproject.toml` 의 `anthropic>=0.40` + `huggingface_hub>=0.24` 제거 + `llm_integration` marker description 갱신.  venv pip uninstall 완료 |
| 6. UI | `settings.html` 2 array (Jinja + JS) + setupUrls/setupLinkLabels 3 entries 제거 + 6 help partial 파일 삭제 |
| 7. i18n | `messages.po` (ko/en) 3 msgid 제거 + `.mo` 재컴파일 |
| 8. docs | README/AGENTS/DESIGN/HANDOFF/ROADMAP/SETUP + 5 deepinit AGENTS.md + 2 코드 comment (`openai_backend.py` + `core/llm/__init__.py`) 모두 6→3 갱신 |

## 3. 알려진 한계

- **babel.cfg pattern issue** — `**.py` 가 babel `pathmatch` 에서 recurse 안 함.  M11.9 에서는 직접 .po 편집 + compile only 로 우회, pot 재추출은 skip.  Follow-up chore PR 권장.
- **사용자 config 마이그** — 기존 `config.toml` 에 `[backends.claude]` / `[backends.openrouter]` / `[backends.huggingface]` 섹션이 있으면 registry 가 silent drop (M11.9 부터 `_KNOWN_BACKENDS` 3 키 외 부재).  v0.0.1~v0.2.7 외부 사용자 0 이라 호환성 비용 0 — backward shim 작성 없음 (CLAUDE.md `feature flags 금지` + spec Non-Goals).
- **chat_audio chain 기본** — M11 default 가 `["ollama"]` 만 사용.  M11 spec 시점에 audio 가능 backend 가 ollama / gemini / openai 3 종 — M11.9 cleanup 영향 0.

## 4. 수동 검증 항목 (사용자 확인)

다음 항목은 사용자가 직접 확인:

- [ ] **회귀 baseline 재확인** — `git checkout main && pytest -q` (M11.8 머지 후 main 의 1612 baseline 재현)
- [ ] **브랜치 회귀** — `git checkout feat/m11-9-backend-cleanup && pytest -q` 가 `1560 passed + 1 skipped + 57 deselected` 출력
- [ ] **옵트인 LIVE** — `.omc/logs/m11-9-optin-live.log` 의 PASSED 확인 (사용자 GEMINI_API_KEY + OPENAI_API_KEY 존재 전제)
- [ ] **`/settings` 페이지 UI** — 트레이/MCP 실행 후 `http://127.0.0.1:9874/settings` 에서 backend 카드 3개 (ollama/gemini/openai) 만 표시, 6 카드 부재
- [ ] **i18n 렌더링** — `/settings?ui_language=ko` 와 `?ui_language=en` 둘 다 정상 (Anthropic Console / OpenRouter / HuggingFace 문자열 부재)
- [ ] **v0.2.7+ publish 시점** — M11.9 머지 후 `git tag vX.Y.Z` (사용자 명시 — memory `feedback_commit_push_pr_auto_publish_manual`)
- [ ] **HANDOFF.md M12 row** — `:158` 의 "3 backend 정확도 비교" 표기 의도대로 갱신됐는지 (plan §3-E 의 historical / active backlog 판단 — auto 모드에서 갱신 채택)
- [ ] **babel.cfg follow-up** — `**.py` → `**/*.py` 교정 + pot 재생성 별 PR 트리거 여부 결정
