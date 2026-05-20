# 2026-05-20 — AssetCacheMCP 로드맵 (M11~M18) Design

## 1. 한 줄 요약

v1 (M0~M8) + v2 PyPI 배포 + AssetCacheMCP rename (M10) + v0.1.1 yagni-clean + v0.1.2 페이지 정직성 patch 가 모두 sealed (PyPI v0.1.2 Latest, 회귀 1079). 본 spec 은 이후 진행할 **새 기능 마일스톤 8개 (M11~M18)** + **reactive backlog** 정리.

## 2. 컨텍스트

브레인스토밍 세션 (2026-05-20) 에서 사용자 입력 + Claude 의 web research 비교 검증을 통해 결정:

- 새 기능 카테고리 6개 중 사용자가 **C. AI workflow / 검색 정확도** 를 1차 관심 → 발전해서 M11 (Multi-backend LLM) 의 상세 design 까지 도달
- M11 의 자연 follow-up + 사용자가 추가 선택한 후보 5개 (Mac/Linux, MCP 원격, Unity Editor, 측정/벤치마크, 유사 검색) + 사용자가 추가 제안한 성능 개선 (대량 라이브러리, 메모리/시작 시간, 분산 분석) → **총 M11~M18 8개**
- 외부 트리거 의존 후보 (Mac/Linux 검증 본인 환경 / 사용자 피드백 수집 / v0.1.x patch / 코드 서명 복귀) 는 별도 reactive 항목으로

## 3. 마일스톤 정렬

| Tier | M# | 마일스톤 | 의존 | 추정 크기 |
|---|---|---|---|---|
| **0** (1차 implement 대상) | **M11** | Multi-backend LLM Architecture | — | 큼 (7 phase) |
| **1** (M11 직속 follow-up) | M12 | C4 측정 / 학습 / 벤치마크 | M11 | 중 |
| 1 | M13 | Mac/Linux 검증 + M11 cross-platform | M11 | 중-큼 |
| **2** (큰 새 기능) | M14 | MCP 원격 통신 (HTTP/SSE + 인증) | 독립 | 중-큼 |
| 2 | M15 | Unity Editor 통합 (drag-drop / 자동 import) | 독립 | 큼 |
| **3** (검색 확장 / 성능) | M16 | C2 이미지/사운드 유사 검색 | M11 (embedding 활용) | 중 |
| 3 | M17 | 성능 개선 (대량 라이브러리 처리량 + 메모리/시작 시간) | 독립 | 중-큼 |
| 3 | M18 | 분산 분석 (여러 PC 라이브러리 공유 + 분석 분담) | **M14 의존** | 큼 |

권장 순서: M11 → M12 → M13 → (병행 또는 순차) M14/M15/M16/M17 → M18 (M14 후). Tier 안에서 정확한 순서는 사용자가 implementation 시작 시 결정.

## 4. 각 마일스톤의 핵심 의도 + scope

### M11 — Multi-backend LLM Architecture (1차 implement 대상)

**의도**: 현재 Ollama `gemma4:e4b` 가 image+audio 둘 다 처리. modality 별 backend 분리 + 외부 LLM 옵션 추가 + 사용자 선택/우선순위 chain → 정확도 ↑, 비용 통제권, 오프라인 fallback 모두 확보.

**핵심 architecture**:
- modality 별 backend chain (`image_chain` / `audio_chain` 각각 독립)
- 자동 fallback (1순위 실패 → 자동 2순위)
- 1차 backend 세트 6개 — Ollama (현, 로컬/무료) + Gemini (무료+paid, 통합) + Claude (paid, image only) + OpenAI (paid, image+audio) + OpenRouter (무료 라우팅) + HuggingFace (월 크레딧)
- modality 통합 모델 (Gemini, Ollama gemma4, GPT-4o) 은 두 chain 에 등록 가능; modality 한쪽만 지원 (Claude) 은 해당 chain 에만

**산출물**: `core/llm/` 패키지 (base/chain/registry + 6 backend), `/settings` 페이지 backend 섹션 (drag-drop + API key 입력 + "테스트"), `config.toml` `[backends.*]` 섹션, per-asset `backend_used` metadata.

**의존성**: 신규 3개 (`google-genai`, `anthropic`, `openai`) — all-included 설치 패턴.

**Phase 분할** (M11_plan.md 작성 시 정확화): Phase 0 framework + Ollama migrate → 1 Gemini → 2 Claude → 3 OpenAI → 4 OpenRouter+HF → 5 설정 UI → 6 fallback + 가시화 → 7 테스트+문서.

**회귀 보장**: Phase 0 완료 시 1079 baseline 그대로. 각 backend phase 마다 mock + `@pytest.mark.llm_integration` 옵트인.

**Research 출처**: 2026-05-20 brainstorming 세션의 web research 결과 (Image LLM 비교 표 / Audio LLM 비교 표 / 통합 multimodal 표 / 사용 케이스별 추천 / 알려진 한계) — M11_design.md 작성 시 부록으로 수록.

### M12 — C4 측정 / 학습 / 벤치마크

**의도**: M11 의 6 backend 정확도/속도/비용 객관적 측정. 사용자 피드백 학습 강화. "왜 이 결과가 top?" explainability.

**scope**:
- gold-standard 검색 케이스 세트 (수십~수백 쿼리 + 정답 에셋)
- 각 backend 의 정확도 점수 + ranking 차이 정량화
- 사용자 보정 (`feedback_records`) → backend 별 가중치 학습 강화
- `find_asset` 결과에 "왜 top?" tooltip (사용한 backend, 매칭된 axis/label, 통일성 점수 등)

**M11 가치 측정 핵심** — M11 이 완료된 직후 자연 follow-up.

### M13 — Mac/Linux 검증 + M11 cross-platform

**의도**: PyPI 패키지의 cross-platform 호환 정식 검증 + macOS/Linux 트레이 동작 확인 + 문서 정직성 회복 (현 README "Windows 1차 지원, Mac/Linux 미검증" 지움).

**scope**:
- M11 의 새 backend 6개 cross-platform 검증 (Ollama macOS/Linux + 외부 API 의 모든 OS 호환)
- PySide6 트레이 macOS / Linux 동작 확인 + 발견 시 fix
- Windows-only `%APPDATA%` 같은 path 의 platformdirs cross-platform 동작 확인
- pyproject.toml classifiers 보강 (`Operating System :: MacOS :: MacOS X`, `Operating System :: POSIX :: Linux`)
- README / DESIGN / docs 의 OS 안내 갱신

**의존**: M11 (새 backend 들의 OS 별 동작 확인 같이).

### M14 — MCP 원격 통신 (HTTP/SSE + 인증)

**의도**: MCP server (AssetCacheMCP) 와 Claude Code 클라이언트가 다른 머신에서 동작할 수 있도록. 현재 stdio child process 모델 → HTTP/SSE transport 추가.

**scope**:
- MCP server HTTP/SSE 모드 추가 (`assetcache --mcp-http <port>` 또는 자동 옵션)
- 인증 (API key 또는 token 기반)
- TLS 옵션 (HTTPS — self-signed 또는 reverse proxy 안내)
- Claude Desktop config 안내 — `"command": "http"` + URL
- 보안 가이드 (방화벽 / 포트 / 인증 키 관리)

**사용자 use-case**: 집에 서버 PC 가동 / 회사에서 Claude Code 로 접근. 또는 팀 워크 (M18 분산 분석의 기반).

**의존**: 독립 (M11 무관).

### M15 — Unity Editor 통합 (drag-drop / 자동 import)

**의도**: AssetCacheMCP 의 검색 결과를 Unity Editor 로 drag-drop 또는 Claude 가 자동 import. 게임 개발 workflow 핵심 가치.

**scope**:
- Unity Editor extension (C# script) — AssetCacheMCP 검색 UI in-Editor 또는 검색 결과 노출
- 또는 MCP 도구 추가 — Claude 가 `import_to_unity(asset_id, project_path)` 호출 → Unity Editor 가 자동 import
- 활성 프로젝트 (M7) 통합 — 현재 활성 Unity 프로젝트에 직접 import
- 검증: Unity 2022 LTS / 2023.x / 6.x 호환

**의존**: 독립 (M11 무관, M7 활성 프로젝트는 이미 main).

### M16 — C2 이미지/사운드 유사 검색

**의도**: "이 에셋과 비슷한 거" use-case. image-to-image 검색 (CLIP image embedding 활용) + sound-to-sound 검색 (audio embedding).

**scope**:
- CLIP image embedding → 라이브러리 전체에 대해 cosine similarity 검색
- audio embedding (CLAP / Qwen-Omni / Gemini audio embedding 등) → 유사 사운드 검색
- MCP 도구 추가 — `find_similar_asset(asset_id, kind, top_k)`
- 웹 UI — 에셋 상세 패널에 "유사한 에셋" 섹션
- ANN index (faiss / hnswlib) — 큰 라이브러리에서도 빠른 검색

**의존**: M11 (backend 의 image/audio embedding 추출 능력).

### M17 — 성능 개선 (대량 라이브러리 + 메모리/시작 시간)

**의도**: 사용자가 1k~10k 에셋 팩 드롭 시 수시간 이내 완료. 트레이 부팅 수십 초 → 수초.

**scope (Phase A — 대량 처리량)**:
- batch 분석 — Ollama / 외부 API 의 batch endpoint 활용 가능 시
- GPU 활용 — 사용자 GPU 가 있을 때 (CLIP / 로컬 분석 가속)
- 분석 큐 priority — 사용자가 검색 중인 카테고리 우선 분석
- Ollama parallel 더 (현재 semaphore 2 → 4+)
- 백그라운드 분석의 idle CPU/GPU 활용 강화

**scope (Phase B — 메모리/시작 시간)**:
- lazy import — CLIP / PySide6 / FastAPI 등 무거운 모듈을 첫 사용 시 import
- CLIP 모델 분리 다운로드 옵션 (이미 사용 중이지만 로컬 cache 검증 강화)
- 트레이 부팅 시 web 서버를 background thread 로 즉시 분리

**의존**: 독립.

### M18 — 분산 분석 (M14 의존)

**의도**: 여러 PC 가 라이브러리 공유 + 분석 분담. 팀 워크스테이션 / 파워유저 다중 PC 환경.

**scope**:
- 분석 마스터 + 워커 노드 (워커는 분석 결과를 마스터 DB 에 push)
- 마스터/워커 인증 (M14 의 HTTP/SSE + 인증 활용)
- 라이브러리 공유 — 파일 시스템 공유 (NAS / SMB / NFS) 가정 또는 별도 sync 메커니즘
- 분석 결과 동기화 (`metadata.db` 또는 별도 sync 프로토콜)

**의존**: **M14 필수** (인증 + 원격 통신 기반).

## 5. Reactive backlog (별도 트리거 시)

마일스톤 형식이 아닌 reactive 작업:

| 항목 | 트리거 | 처리 |
|---|---|---|
| **사용자 피드백 수집** | 발견 시 (1주 후부터 모니터링) | [PyPI download 통계](https://pypistats.org/packages/assetcache-mcp) + [GitHub Issues](https://github.com/v0o0v/assetcache-mcp/issues). 사용자 발견 bug 누적 시 v0.1.x patch |
| **v0.1.x patch 누적** | bug fix / 작은 docs 갱신 | `git tag vX.Y.Z; git push origin vX.Y.Z` 한 줄로 자동 publish (Trusted Publishing 검증된 30초 패턴) |
| **코드 서명 + 자동 업데이트** (M9 복귀) | SignPath 채택 결정 시 | spec/plan 은 `docs/superpowers/{plans,specs}/2026-05-19-m9-*.md` 에 보존, branch `feat/m9` 는 deleted (reflog 30일 또는 spec 기반 redo) |

## 6. 의존성 그래프

```
M11 ──────┬──── M12 (측정/벤치마크)
          ├──── M13 (Mac/Linux + cross-platform)
          └──── M16 (유사 검색 — embedding 활용)

M14 ──── M18 (분산 분석)

M15, M17 — 독립
```

## 7. 본 spec 의 의도 + 다음 step

- 본 spec 은 **brainstorming session 결과의 fact 정리**. 각 마일스톤의 상세 design 은 implementation 시작 시 별도 `docs/superpowers/specs/YYYY-MM-DD-m{N}-*-design.md` 로 작성.
- **다음 step**: M11 implementation 시작 시 — `docs/superpowers/specs/YYYY-MM-DD-m11-multi-backend-llm-design.md` 작성 (brainstorming 결과 + research 비교 표 포함) → writing-plans skill 로 `milestones/M11_plan.md` 작성 → TDD cycle 시작.

## 8. 관련 출처

### 본 spec 작성 시 사용한 fact

- 2026-05-20 brainstorming 세션의 web research (general-purpose agent 결과) — 무료 / 본인 key / 저렴 paid LLM (image + audio) 비교 표
- HANDOFF.md §5.1 의 외부 의존 후보 표
- memory `m10_complete` 의 "다음 마일스톤 후보" 섹션
- DESIGN.md §3 (아키텍처) + §4.5 (MCP 도구) — 현재 상태 fact

### 관련 historical record (drop 안 됨)

- [M9 spec](./2026-05-19-m9-code-signing-and-auto-update-design.md) — 코드 서명 복귀 시 starting point
- [M10 spec](./2026-05-19-m10-pypi-and-rename-design.md) — PyPI 배포 패턴

### 향후 참고

- [Gemini API Pricing](https://ai.google.dev/gemini-api/docs/pricing) — M11 Phase 1 작성 시
- [Anthropic Claude API](https://docs.claude.com/en/docs/about-claude/pricing) — M11 Phase 2
- [OpenAI API Pricing](https://openai.com/api/pricing/) — M11 Phase 3
- [OpenRouter Free Models](https://openrouter.ai/collections/free-models) — M11 Phase 4
