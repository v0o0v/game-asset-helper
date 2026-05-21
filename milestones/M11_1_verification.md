# M11.1 verification

## 자동 검증

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\Activate.ps1"
```

```powershell
cd D:\ClaudeCowork\game-asset-helper\game-asset-helper
```

```powershell
pytest -q
```

예상: **1426 passed, 1 skipped, 56 deselected** (약 80초 소요)

### 옵트인 Gemini Batch integration 검증 (실 GEMINI_API_KEY 필요)

```powershell
$env:GEMINI_API_KEY = "AIza..."
```

```powershell
pytest -m llm_integration tests/test_llm_backend_gemini_batch_integration.py -v
```

예상: **3 PASS**
- `test_batch_chat_submit_and_cancel` — 실 batch job 제출 후 취소
- `test_batch_embed_submit_and_cancel` — 실 embed batch 제출 후 취소
- `test_batch_get_unknown_returns_error` — 존재하지 않는 batch_id 조회 → 에러 반환 확인

## 수동 검증 시나리오

### 시나리오 1: /settings 의 batch 카드 렌더링

1. `python -m assetcache --tray` 실행
2. 트레이 → 메인 창 열기 → `http://127.0.0.1:9874/settings`
3. 페이지 하단에 **Batch analysis** 섹션 표시 확인:
   - Threshold input (기본 30)
   - 3개 radio 버튼: Auto / Forced on / Forced off
   - Polling interval input (기본 30분)
   - Save 버튼
   - "In-progress batch jobs" 리스트 (없으면 빈 목록)

### 시나리오 2: /analyzing dashboard 렌더링

1. nav 의 "Analysis progress" 링크 클릭 → `/analyzing`
2. 다음 섹션 표시 확인:
   - **Summary** — interactive 큐 카운트 + batch image/audio 카운트 + 전체 ETA
   - **Interactive queue** — 큐 비어있으면 "Queue empty" 메시지
   - **Batch jobs** — 없으면 "No active batch jobs" 메시지
   - **Recent failures** — 없으면 "No recent failures" 메시지
3. 5초마다 자동 새로고침 확인 (브라우저 네트워크 탭에서 `/analyzing/partial` GET 요청)

### 시나리오 3: tray batch toggle 순환

1. tray icon 우클릭 → **"Batch: auto"** 메뉴 항목 표시 확인
2. 클릭 → **"Batch: forced_on"** 으로 변경 확인
3. `%APPDATA%\AssetCacheMCP\config.toml` 파일에서 `[batch] toggle = "forced_on"` 갱신 확인
4. 다시 클릭 → **"Batch: forced_off"** 로 변경 확인
5. 다시 클릭 → **"Batch: auto"** 로 순환 확인

### 시나리오 4: 자동 batch 진입 (실 GEMINI_API_KEY 환경)

1. `/settings` → Gemini backend 활성화 + API key 입력 + Save
2. `/settings` → image chain 1순위를 Gemini 로 설정 + Save
3. `/settings` → Batch Threshold = 30, Toggle = Auto + Save
4. `%APPDATA%\AssetCacheMCP\library\<pack>\` 에 30개 이상 sprite PNG 드롭
5. tray 재시작 (`python -m assetcache --tray`)
6. `/analyzing` 에서 batch jobs 섹션에 **"image" modality** job 1개 표시 확인
7. job 상태 → `submitted` → (24h 이내) `succeeded` 확인
8. DB 에서 `SELECT backend_image, analysis_state FROM assets WHERE batch_job_id IS NOT NULL` 으로 `backend_image='gemini'`, `analysis_state='ok'` 확인

### 시나리오 5: 부분 실패 fallback

1. 시나리오 4 와 동일 환경에서 Gemini 응답 중 일부 실패 발생 시
2. `/analyzing` → **Recent failures** 섹션에 실패 항목 표시 확인
3. 실패 항목이 chain 의 다음 backend(예: Ollama)로 interactive 재시도 진입 확인

### 시나리오 6: chain 1순위 != Gemini 일 때

1. `/settings` → image chain 1순위를 Ollama 로 설정 + Save
2. library 에 30+ asset 드롭
3. `/analyzing` → batch jobs = 0 (chain 1순위가 Gemini 아니라 batch 진입 안 함) 확인
4. Interactive queue 에 정상 진입 확인

### 시나리오 7: toggle forced_off

1. tray → **Batch: forced_off** 로 설정
2. library 에 30+ asset 드롭
3. `/analyzing` → batch jobs = 0, Interactive queue 만 표시 확인

## 자동 검증 결과 (2026-05-21)

```
1426 passed, 1 skipped, 56 deselected in 79.58s (0:01:19)
```

SKIPPED 1건 — `tests/test_web_routers_sse.py:140: heartbeat 15초 타이밍 결정론적 테스트 어려움 — Phase 4 마감 흡수` (M4 이후 지속 유지, 의도된 skip)

## 알려진 한계

| 항목 | 우선순위 | 후속 |
|---|---|---|
| ~~Image/audio Gemini 결과 → labels 실제 파싱 미구현 (empty labels + mark ok)~~ | ~~중~~ | **✅ v0.2.x patch A — `core/analyzer/payload_parser.py` 분리 + BatchPoller registry 주입으로 sync 와 동등한 라벨 추출** |
| ~~batch 경로는 sprite_meta / sound_meta (width/height/duration_ms 등) 채우지 않음~~ | ~~낮~~ | **✅ v0.2.x patch B — `core/analyzer/tech_meta.py` 분리 + BatchPoller library_dir 주입으로 sprite_meta/sound_meta 충전** |
| ~~batch 경로의 spritesheet 미지원 (frame_w/h/count/animation_tags/animations_json 비어 있음)~~ | ~~낮~~ | **✅ v0.2.x patch C — `core/analyzer/spritesheet_meta.py` + BatchPoller 가 `detect_sheet` 호출 → Aseprite/TexturePacker JSON 사이드카 또는 grid 검출로 frame meta 채움 + frameTags → animation 라벨 + kind='spritesheet' promote. 한계: batch prompt 가 시트 unaware 라 Gemma 의 `animation_hint` 추측은 sync 만의 기능 — frameTags 없는 grid-only 시트는 animation 라벨 비어 있음** |
| 파일 크기 > 20MB inline 제한 (file destination batch) | 낮 | v0.2.x |
| OpenAI/Anthropic Batch API | 낮 | v0.3.0 candidate |
| 비용 가시화 (실 절감 추적) | 낮 | M12 |
| Embedding dim 변경 시 자동 re-embed | 낮 | M12 |
| 사용자가 진행 중 batch job 의 부분 cancel (asset 단위) | 낮 | v0.2.x |
