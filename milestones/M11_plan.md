# M11 — Multi-backend LLM Architecture (마일스톤 plan)

> 본 문서는 [`docs/superpowers/plans/2026-05-20-m11-multi-backend-llm.md`](../docs/superpowers/plans/2026-05-20-m11-multi-backend-llm.md) 의 마일스톤 사이클 표지다. 실제 구현 task 는 superpowers plan 참조.
>
> spec: [`docs/superpowers/specs/2026-05-20-m11-multi-backend-llm-design.md`](../docs/superpowers/specs/2026-05-20-m11-multi-backend-llm-design.md)
> 상위 roadmap: [`docs/superpowers/specs/2026-05-20-roadmap-design.md`](../docs/superpowers/specs/2026-05-20-roadmap-design.md) §4 M11

## 목표

- **modality 별 backend chain** — `chat_image` / `chat_audio` / `text_embed` 독립 chain + 자동 fallback (transient 만, hard 는 중단)
- **6 backend 1차 세트** — Ollama (현, local) + Gemini (무료+paid) + Claude (paid image) + OpenAI (paid full) + OpenRouter (무료 routing) + HuggingFace (월 small quota)
- **/settings UI** — 6 backend 카드 (활성/API key/모델/연결 테스트) + drag-drop chain 우선순위
- **per-asset 가시화** — `backend_image` / `backend_audio` / `backend_embed` 컬럼 + MCP find_asset 응답 + 검색 카드 배지
- **회귀 보장** — Phase 0 (Ollama wrap) 끝에서 1079 baseline 유지 (+22 신규)

## 산출물

| Phase | Task | 산출물 | 신규 테스트 |
|---|---|---|---:|
| 0 | 0.0~0.8 | `core/llm/` 패키지 (base + chain + registry + backends/ollama) + Config 마이그레이션 + analyzer/embedder 시그니처 변경 | +22 |
| 1 | 1.0~1.2 | `GeminiBackend` + `google-genai` 의존성 + registry factory + integration 옵트인 | +6 + 3 옵트인 |
| 2 | 2.0~2.2 | `ClaudeBackend` (image only, audio 미지원 검증) + `anthropic` 의존성 | +5 + 2 옵트인 |
| 3 | 3.0~3.1 | `OpenAIBackend` (full modality) + `openai` 의존성 | +5 + 3 옵트인 |
| 4 | 4.0~4.3 | `OpenRouterBackend` (OpenAI specialization) + `HuggingFaceBackend` + `huggingface_hub` 의존성 | +10 + 4 옵트인 |
| 5 | 5.1~5.6 | `/settings` 페이지 backend 카드 + chain drag-drop + "테스트" + 라우터 + i18n msgid 8건 + e2e 1건 | +10 + 1 e2e |
| 6 | 6.1~6.3 | DB `backend_image/audio/embed` 컬럼 + MCP find_asset 응답 + 검색 카드 배지 | +8 |
| 7 | 7.1~7.6 | cross-backend integration 테스트 + DESIGN/README/HANDOFF/CLAUDE.md 갱신 + `M11_verification.md` + PR | +5 |
| **합계** | | **MCP 20 도구 그대로, 신규 런타임 의존성 4 (google-genai/anthropic/openai/huggingface_hub)** | **+71 (1079 → ~1150)** + ~14 옵트인 |

## 완료 조건

- [ ] `pytest -q` ~1150 passed + 1 skipped + 40 + 14 deselected, 회귀 0
- [ ] Phase 0 commit 시점에 `pytest -q` 1101 passed 검증 (회귀 1079 baseline 보장)
- [ ] 6 backend 의 mock 테스트 모두 green
- [ ] `pytest -m llm_integration` 옵트인 — 실 API key 환경변수 셋업 후 사용자 직접 검증
- [ ] `/settings` 페이지 backend 카드 6개 표시 + drag-drop 동작 (수동 검증)
- [ ] 새 에셋 드롭 시 `backend_image/audio/embed` 컬럼 채워짐 (수동 검증)
- [ ] MCP `find_asset` 응답에 `backend_used` 필드 (수동 + 자동)
- [ ] M11_verification.md 시나리오 6건 모두 수동 검증 통과
- [ ] DESIGN.md §3/§4.5/§10/§11 갱신, README.md "Multi-backend LLM" 섹션 추가

## 일정 추정

- ~10일 (Phase 0~7 + PR/머지)
- Phase 0 가 critical — 회귀 1079 유지 확인 후 다음 phase 진행
- Phase 1~4 는 backend 별 독립 → subagent 병렬 dispatch 가능
- Phase 5 (/settings UI) + Phase 6 (metadata 가시화) 는 Phase 0~4 완료 후 순차
- Phase 7 (문서 + PR) 은 wrap-up

## 의존성

런타임 신규 4건:
- `google-genai>=0.1` (Gemini)
- `anthropic>=0.40` (Claude)
- `openai>=1.50` (OpenAI + OpenRouter)
- `huggingface_hub>=0.24` (HF)

dev 신규 0건 (`respx` 이미 있음 — M9 패턴 활용).

## 브랜치

`feat/m11-multi-backend-llm` — main 위에서 직접 checkout (워크트리 금지, CLAUDE.md §4.5).

## TDD 순서

1. **테스트 먼저** (red) — 각 Phase 의 Task 별로 failing test 작성 → `pytest` 실패 확인.
2. **구현** (green) — 최소 구현으로 통과.
3. **회귀** — `pytest -q` 전체 통과 확인.
4. **commit** — Task 단위.
5. **Phase 끝에** — 회귀 + verification.md 항목 체크 + PR comment.

## 알려진 한계 (M11 scope 밖)

- embedding dim 일치성 자동 처리 (chain 변경 시 자동 re-embed) — M12 candidate
- OS keyring (API key 평문 vs 암호화) — reactive backlog
- rate limit token bucket / quota tracking — M17 candidate
- per-asset 사용자 backend override — M12 candidate
