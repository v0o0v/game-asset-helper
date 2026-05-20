# M11 — Multi-backend LLM Architecture 검증

브랜치: `feat/m11-multi-backend-llm` (main 머지 대기)
spec: [`docs/superpowers/specs/2026-05-20-m11-multi-backend-llm-design.md`](../docs/superpowers/specs/2026-05-20-m11-multi-backend-llm-design.md)
plan: [`docs/superpowers/plans/2026-05-20-m11-multi-backend-llm.md`](../docs/superpowers/plans/2026-05-20-m11-multi-backend-llm.md)

## 자동 검증

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\Activate.ps1"
cd D:\ClaudeCowork\game-asset-helper\game-asset-helper
pytest -q
```

기대 결과: `1239 passed + 1 skipped + 53 deselected` (M11 implementation 후 baseline).

| 단계 | 회귀 | Δ | 비고 |
|---|---:|---:|---|
| Phase 0 시작 | 1079 | — | v0.1.2 baseline |
| Phase 0 (framework + Ollama wrap + Config migration) | 1119 | +40 | analyzer 통합 완료 |
| Phase 1 (Gemini) | 1134 | +15 | + 3 옵트인 |
| Phase 2 (Claude image only) | 1154 | +20 | chain audio skip 실 backend 검증 포함, + 3 옵트인 |
| Phase 3 (OpenAI full modality) | 1173 | +19 | + 3 옵트인 |
| Phase 4 (OpenRouter + HuggingFace) | 1203 | +30 | + 4 옵트인 |
| Phase 5 (/settings UI + i18n) | 1222 | +19 | 14 router + 3 UI smoke + 2 i18n |
| Phase 6 (DB schema + find_asset backend_used) | 1234 | +12 | 8 store + 4 find_asset |
| Phase 7 (cross-backend integration) | 1239 | +5 | mock 시나리오 |
| **합계** | **1239** | **+160** | + 13 `llm_integration` 옵트인 |

### 옵트인 검증 (실 API key)

```powershell
$env:GEMINI_API_KEY = "AIza..."
$env:ANTHROPIC_API_KEY = "sk-ant-..."
$env:OPENAI_API_KEY = "sk-..."
$env:OPENROUTER_API_KEY = "sk-or-..."
$env:HF_TOKEN = "hf_..."

pytest -m llm_integration
```

키 없는 backend 의 테스트는 fixture 에서 `pytest.skip`. 전체 13 케이스 (Gemini 3 + Claude 3 + OpenAI 3 + OpenRouter 2 + HuggingFace 2).

## 수동 검증 (사용자 직접 점검)

### 시나리오 1: /settings 페이지 backend 카드 렌더링
1. `python -m assetcache --tray` 실행
2. 트레이에서 "메인 창 열기" → 우상단 ⚙️ → **/settings** 페이지
3. **확인**: 페이지 하단에 "백엔드" 섹션 + 6 backend 카드 표시
4. **확인**: 각 카드에 enabled checkbox / API key input / 모델 input / Save / Test 버튼

### 시나리오 2: Gemini backend 활성화 + 연결 테스트
1. /settings 의 gemini 카드에서:
   - enabled 체크
   - API key 입력 (`GEMINI_API_KEY`)
   - "Save" 클릭 → 즉시 cfg 저장
   - "Test connection" 클릭 → "✅ Connection succeeded" 표시 (실 API key 인 경우)
2. **확인**: `%APPDATA%\AssetCacheMCP\config.toml` 의 `[backends.gemini]` 섹션에 `enabled = true` + `api_key = "AIza..."`

### 시나리오 3: Chain 우선순위 변경 (drag-drop 대체로 ▲/▼ 버튼)
1. /settings 의 "모달리티 체인" 섹션에서:
   - "이미지 체인" 의 "Add backend" dropdown 에서 "gemini" 선택 → "Add"
   - gemini 가 ollama 위로 가도록 ▲ 클릭
2. "체인 저장" 클릭
3. **확인**: `config.toml` 의 `[chains]` 의 `chat_image = ["gemini", "ollama"]`

### 시나리오 4: 새 에셋 분석 (실 backend 호출)
1. 시나리오 2/3 완료 후 트레이 재시작 (cfg 갱신 반영)
2. 새 `.png` 파일을 `library/<pack>/` 에 드롭
3. **확인**: 분석 로그에 "backend gemini chat success" 또는 비슷한 메시지
4. **알려진 한계**: per-asset `backend_image/audio/embed` 컬럼 write path 는 후속 patch (v0.2.x). 현재는 schema 만 준비, AnalysisQueue 가 자동 채워주지 않음

### 시나리오 5: MCP find_asset 응답에 backend_used
1. `python -m assetcache --mcp` (MCP stdio 모드)
2. Claude Desktop 또는 다른 MCP client 에서 `find_asset(query="hero")` 호출
3. **확인**: 응답의 각 result 에 `backend_used: {"image": null, "audio": null, "embed": null}` (legacy NULL — write path 후속 patch 이후 채워짐)
4. **수동 마킹 후 재확인**: SQL 로 직접 `UPDATE assets SET backend_image = 'gemini' WHERE id = ?` 한 뒤 find_asset 호출 → `backend_used.image == "gemini"` 표시

### 시나리오 6: 검색 카드 backend 배지
1. 시나리오 5 의 수동 마킹 후
2. `/library?q=hero` 페이지에서 해당 asset 의 카드에:
3. **확인**: 와이드/리스트 카드 모두 `🤖 gemini` 배지 표시 (image 우선)
4. **확인**: 배지 hover 시 tooltip 으로 modality 별 backend 전체 표시 (`image: gemini · audio: null · embed: null`)

## 알려진 한계

| 항목 | 상태 | 후속 milestone |
|---|---|---|
| AnalysisQueue → mark_asset_backends write hook | ⚠️ schema 만 준비, write path 미구현 | v0.2.x patch |
| /settings backend 카드 의 enabled/api_key 변경이 running analyzer 에 즉시 반영 | 재시작 필요 (UI 안내 문구) | M12 (per-request registry rebuild) |
| API key 평문 저장 (config.toml) | OS keyring 미사용 | Reactive backlog |
| embedding dim 일관성 자동 처리 (chain 변경 시 자동 re-embed) | 사용자 수동 cleanup 필요 | M12 candidate |
| rate limit token bucket / quota tracking | 없음 (HF 월 quota 작음 등) | M17 candidate |
| per-asset 사용자 backend override (특정 asset 만 다른 backend) | 없음 | M12 candidate |
| Gemini Batch API 활용 (50% 비용 절감, 24h SLO) | interactive 만 사용 — 대량 import 시 비용 비효율 | M11.1 또는 M12 candidate ([Batch API docs](https://ai.google.dev/gemini-api/docs/batch-api)). assetcache 적합 시나리오: library 초기 import / Unity Asset Store 80+ / failed bulk 재분석. drop 1장은 interactive 유지 (즉시 UX) — hybrid 정책 spec 필요 |

## 신규 의존성 (런타임 4건)

- `google-genai>=0.1` (Gemini)
- `anthropic>=0.40` (Claude)
- `openai>=1.50` (OpenAI + OpenRouter specialization)
- `huggingface_hub>=0.24` (HuggingFace — `open_clip_torch` transitive 로 이미 설치돼 있어 추가 다운로드 0건)

설치 결과 (`pip install -e .`):
- google-genai 2.4.0 + google-auth 2.53 + tenacity 9.1 + sniffio 1.3 + distro 1.9 + pyasn1/pyasn1-modules
- anthropic 0.103.1 + docstring-parser 0.18 + jiter 0.15
- openai 2.37.0
- huggingface_hub 1.15 (이미 있음)

## MCP 도구 수 변동 0

M11 은 기존 20 도구의 응답 schema 만 확장 (`find_asset` 의 `backend_used`). 신규 도구 추가 안 함. 호환성 보장.

## PR

```powershell
git push -u origin feat/m11-multi-backend-llm
gh pr create --title "M11 — Multi-backend LLM Architecture (Ollama+Gemini+Claude+OpenAI+OpenRouter+HuggingFace)"
```

PR body 는 사용자가 직접 review 후 생성 권장.
