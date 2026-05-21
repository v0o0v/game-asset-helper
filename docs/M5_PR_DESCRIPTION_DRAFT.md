# M5 PR 설명 (최종)

> 본 문서는 PR 본문으로 직접 사용된다. 수동 검증 완료 + 검증 중 발견된 14 fix + Playwright e2e (36 케이스) 반영.

---

## PR 제목

```
M5: 웹 GUI 전환 + 라이브러리 리디자인 + Claude pick (17 MCP 도구) + Playwright e2e
```

---

## PR 본문

```markdown
## 요약

- Qt 데스크톱 UI (8 파일) 를 FastAPI + HTMX + Alpine.js 로컬 웹 GUI 로 완전 교체. 트레이 부팅 시 시스템 브라우저가 `http://127.0.0.1:9874/library` 로 자동 진입.
- 라이브러리 페이지를 4 페인 (자연어 검색 + ⚙ 고급 사이드 패널 B/C/D 탭 + 결과 카드 그리드 + 모달) 으로 리디자인. B 탭 = 정밀 필터 (axis 칩 + 다축 드롭다운), C 탭 = 표시 옵션, D 탭 = 가중치 프리셋 + 저장된 검색 + 통일성 요약.
- 신규 MCP 17번째 도구 `request_user_pick` — Claude 가 후보 자산 중 사용자가 직접 고르도록 요청하면 SSE push → 보라색 pick 카드 → 채택/거부 → 자동 `record_asset_use(source="claude_pick")`.
- **Playwright e2e 36 케이스** + 사용자 수동 검증 8 시나리오 (Claude pick 채택/거부/timeout / 사운드 재생 / 다크모드 / 반응형 / SSE 토스트 / 트레이 graceful shutdown) 통과.

## 주요 변경

### Phase 별 산출물

| Phase | 핵심 산출물 |
|---|---|
| Phase 0 — 의존성 + Config | FastAPI 5 의존성 + Config 7 신규 필드 + `UsageSource` enum + HTMX/Alpine vendoring |
| Phase 1 — 인프라 | `WebServer` (uvicorn 별도 스레드), `PendingPickQueue` (asyncio.Future + TTL), `web.port` 파일 R/W, SSE bus, 트레이 → 브라우저 |
| Phase 2 — 검색 + 결과 + 카드 | `/api/search`, `/ui/search-results`, 와이드/리스트 카드 partial, 모달, `/api/audio` Range, Jinja2 base 레이아웃, CSS 변수 light/dark |
| Phase 3 — 사이드 패널 B/C/D | ⚙ 슬라이드 + 리사이즈 핸들 (240~640) + B 탭 (match_mode·axis 칩·다축 필터) + C 탭 (표시 옵션·카드 메타) + D 탭 (프리셋·슬라이더·저장된 검색·통일성 모달) + ≤768px 반응형 |
| Phase 4 — Claude pick | `/internal/user-pick` long-poll + SSE `user_pick_request` + `_pick_card.html` + MCP `request_user_pick` + `TrayBridge(QObject)` |
| Phase 5 — Pack/라벨 + Qt 폐기 | `/packs` + `/labels/admin` (24 axis CRUD + import/export) + Qt UI 8 파일 + 폐기 테스트 7 파일 삭제 |
| Phase 6 — 마감 | 404/500 커스텀 에러 페이지 + `labels_signature_changed` SSE 토스트 + `WEB_UI_GUIDE.md` + `M5_verification.md` + DESIGN/README/CLAUDE/HANDOFF 갱신 |
| **Playwright e2e** | **`pytest-playwright` + chromium binary + 36 케이스** (라이브러리/팩/라벨/기타 페이지의 클릭·키보드·뷰모드 회귀 가드) |
| **수동 검증 단계 fix** | **14 production 버그 fix** (아래 표) |

### 수동 검증 단계에서 발견된 14 production fix

| commit | 영역 | 내용 |
|---|---|---|
| `060f570` | thumbnail | `assets.path` 상대→절대 (썸네일 / 오디오 endpoint FileNotFoundError) |
| `068cdde` | search | `hx-trigger keyup→input` + `from:` filter 제거 (한국어 IME 호환) |
| `b8095c9` | search | Ollama 미가용 graceful degradation (200 친화 fragment + 503 JSON) |
| `5b5c60a` | search | 자동 디바운스 제거 + 명시적 🔍 검색 버튼 |
| `3ebc6f8` | result | `ResultRow.kind` 누락 (모든 카드가 generic 아이콘으로 빠지던 버그) |
| `68b7412` | template | `&middot;` → unicode `·` (Jinja2 autoescape) |
| `5ba123a` | SSE | htmx-sse 우회 → native EventSource (event 이름 mismatch) |
| `9fc7dde` | nav | `_nav.html` `x-data` 추가 (배지 reactivity) |
| `25e6f1d` | tray | `_notify_tray_pick_count` status=pending 만 카운트 |
| `6e2a40f` | pick card | 채택/거부 `hx-swap=delete` (raw JSON `{"ok":true}` 노출) |
| `1f5ae76` | list card | 리스트 뷰 sound 카드 ▶ 재생 버튼 추가 |
| `fd5e071` | view toggle | `x-if` → `x-show` (뷰 토글 후 htmx 깨짐) |
| `5672432` | list card audio | `.card-list-body` flex-wrap + audio-slot 풀폭 |
| `61107cd` | grid card audio | sound 카드 grid-column span 2 (timeline 폭) |
| `cebec6d` + `624e6c4` | side panel | ✕ 닫기 버튼 + ESC + absolute corner (좁은 화면 dead-end 해소) |

### 신규 의존성 (pyproject.toml)

- `fastapi>=0.110`, `uvicorn[standard]>=0.27`, `jinja2>=3.1`, `python-multipart>=0.0.9`, `sse-starlette>=2`
- `httpx` (MCP server → FastAPI loopback)
- `pytest-playwright>=0.4` (dev — Playwright e2e)

### 폐기

- `src/gah/ui/` 디렉터리 전체 (8 파일)
- 폐기 테스트 7 파일

## 자동 검증

```
pytest -q
805 passed, 1 skipped, 40 deselected
```
- skipped 1: SSE heartbeat 결정론 어려움 (Phase 4 마감 흡수)
- deselected 40: e2e 36 + mcp_integration 4 (opt-in 마커)

```
pytest -m e2e -v
36 passed
```
Playwright chromium 헤드리스 — library/packs/labels admin/error/dark/responsive 회귀 가드.

```
pytest -m mcp_integration -v
2 passed (17 tools)
```

M0~M4 베이스라인 452 케이스 회귀 없음. M5 신규 ~353 케이스 추가.

## 수동 검증 결과

`milestones/M5_verification.md §4` 의 36 단계 중 자동화 가능 항목은 e2e 가 커버. 사용자 cross-process / Qt / 시각 디테일 8 시나리오 모두 통과:

1. ✅ Claude pick 채택 (카드 + 배지 + 트레이 툴팁 + 응답)
2. ✅ Claude pick 거부 (499 + 카드 제거)
3. ✅ Claude pick timeout (408)
4. ✅ 사운드 카드 ▶ 인라인 재생 (그리드 + 리스트 둘 다)
5. ✅ OS 다크 모드 토글 (prefers-color-scheme)
6. ✅ 반응형 ≤768px (사이드 패널 자동 닫힘 + ✕/ESC 로 dead-end 회피)
7. ✅ 라벨 어휘 변경 SSE 토스트 (cross-tab)
8. ✅ 트레이 graceful shutdown (포트 해제)

## 알려진 한계

- **timeout 시 pick 카드 DOM 잔존** — broadcast 없음. 후속 phase.
- **트레이 cleanup_loop sweep 후 카운트 emit 없음** — minor stale state.
- **페이지 새로고침 시 pending pick 미표시** — SSE 재구독 이후 신규만. v2.
- **axis 추가 불가** — `SEED_LABELS.keys()` 24개 고정.
- **PATCH endpoint HTML fragment 반환** — 비-HTMX 클라이언트 부적합.
- **Config 변경 디스크 미저장** — 프리셋/슬라이더 재시작 시 초기화. M8.

## 참조

- spec: `docs/superpowers/specs/2026-05-17-m5-web-gui-and-library-redesign.md`
- plan: `milestones/M5_plan.md`
- verification: `milestones/M5_verification.md`
- 사용자 가이드: `docs/WEB_UI_GUIDE.md`
- MCP 가이드: `docs/MCP_USAGE_GUIDE.md`

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```
</content>
</invoke>