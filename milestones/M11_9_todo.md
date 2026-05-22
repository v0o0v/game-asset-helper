# M11.9 TODO (TDD 체크리스트)

## Phase 0 — Discovery + AC 매핑
- [x] 6 git grep 으로 ~15 missed surface 식별
- [x] registry.py `from_config:140-158` 6 kwargs 위치 확인
- [x] settings.html `:84` / `:197` / `:217-231` (plan `:219-230` 의 off-by-2 보정 확인) 위치 확인
- [x] 7 test 파일 영향 라인 핀포인트
- [x] baseline 재측정: 1601 → **1612 passed + 1 skipped + 64 deselected** (M11.8 머지 후 +11)

## Phase 1 — TDD red → green
- [x] 1-A: `feat/m11-9-backend-cleanup` 브랜치 + baseline `pytest -q` PASSED (1612)
- [x] 1-B: `tests/test_m11_9_backend_purge.py` 9 케이스 작성 → 단독 실행 시 **8 failed + 1 passed** (chains default 자연 PASSED — plan §1.2 의 "9 failed" 의도 충족)
- [x] 1-C: 코드 3 모듈 삭제 + registry 3 factory + 6 kwargs + 3 default assign + factory dict 3 + `:70` stale comment + config `_KNOWN_BACKENDS` 3 키 + `_default_backends()` 3 키 + docstring → 5 PASSED + 4 red (UI/i18n/partial/import — Phase 2 대상)

## Phase 2 — Cleanup
- [x] 2-A: 6 mock + LIVE test 파일 + `test_llm_integration_cross_backend.py` 삭제
- [x] 2-B: cross-backend dependency 6 파일 정리
  - [x] `test_llm_chain.py` 3 cross-backend test 제거
  - [x] `test_llm_registry.py` Claude/OpenRouter/HuggingFace blocks + audio chain test 제거 (lines 180+)
  - [x] `test_backend_info_setup_url.py` scope down (3 backend 만, field test 보존)
  - [x] `test_settings_router_m11.py` claude → openai swap + 6→3 + en_partial_for_claude → en_partial_for_openai
  - [x] `test_settings_partials_exist.py` 6→3 + `_BACKENDS` tuple
  - [x] `test_config_m11_migration.py` 6→3 + 제거 backend 부재 assertion
- [x] 2-C: `test_llm_backend_supports_batch.py` 의 claude/openrouter/huggingface 3 케이스 제거
- [x] 2-D: `pyproject.toml` 의 `anthropic` + `huggingface_hub` 2 라인 + marker description 갱신 (openai 유지)
- [x] 2-E: `pip uninstall anthropic huggingface_hub -y` + `pip list` 검증 출력 0
- [x] 2-F: `settings.html` Jinja loop + JS backendOrder + setupUrls + setupLinkLabels 정리
- [x] 2-G: 6 help partial 파일 삭제
- [x] 2-H: `messages.po` (ko/en) 3 msgid 제거 + `.mo` 재컴파일 (pot 재추출 skip — babel.cfg pattern issue 로 별도 follow-up)
- [x] 2-I: pytest -q 광역 회귀 → **1560 passed + 1 skipped + 57 deselected** (plan band 정확 적중)

## Phase 3 — Docs
- [x] `README.md:46` 3 backend 갱신
- [x] `AGENTS.md:66` 3 backend LLM 갱신
- [x] `DESIGN.md:557` Anthropic Batch API 갱신 (M11.9 invalidation 명시)
- [x] `HANDOFF.md:144` backlog D Anthropic Batch 갱신 + `:158` 3 backend
- [x] `milestones/ROADMAP.md:24` M12 row 3 backend
- [x] `docs/SETUP.md:35` 옵트인 마커 description 갱신
- [x] `src/assetcache/core/AGENTS.md:37` 3 backend wrapper
- [x] `src/assetcache/core/llm/AGENTS.md` Purpose + Subdirectories + supports_batch + Testing + External 4 위치
- [x] `src/assetcache/core/llm/backends/AGENTS.md` Purpose + Key Files (3 row delete) + batch matrix + OpenAI compat note + External 4 위치
- [x] `src/assetcache/core/llm/__init__.py:3` docstring 3 backend wrappers
- [x] `src/assetcache/web/templates/AGENTS.md:49` 3 backend × ko/en = 6 파일
- [x] `src/assetcache/core/llm/backends/openai_backend.py:3` OpenRouter 참조 comment 갱신
- [x] historical (HISTORY.md / milestones/M11_*.md / docs/superpowers) 미변경 확인
- [x] `git grep "6 backend"` 라이브 docs 매칭 0 검증

## Phase 4 — 회귀 final + 옵트인 LIVE + 마일스톤 + PR
- [x] pytest -q 최종 (Phase 2-I 이후 pip uninstall 한 번 더 회귀 검증)
- [ ] 옵트인 LIVE Gemini + OpenAI PASSED
- [x] `milestones/M11_9_plan.md` 작성
- [x] `milestones/M11_9_todo.md` 작성 (본 문서)
- [ ] `milestones/M11_9_verification.md` 작성 (Phase 4 회귀 + LIVE 결과 반영)
- [ ] 커밋 분할 + push + PR draft (한글)
