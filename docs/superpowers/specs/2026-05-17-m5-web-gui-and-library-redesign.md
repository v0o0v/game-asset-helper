# M5 — 웹 GUI 전환 + 라이브러리 탭 리디자인 + Claude 사용자 선택 인터랙션

**한 줄 요약** — Qt 데스크톱 UI 를 폐기하고 FastAPI + HTMX + Alpine.js 기반 로컬 웹 GUI 로 전환. 라이브러리 탭은 "검색 영역 + 결과 영역 + 우측 슬라이드 고급 패널(B/C/D 탭)" 로 리디자인. 신규 MCP 도구 `request_user_pick` 으로 Claude Code 가 사용자에게 후보 중 선택을 요청하면 GAH 웹 UI 에서 사용자가 클릭 → Claude 가 동기 응답으로 받음 (5분 long-poll).

**작성일** — 2026-05-17
**관련 마일스톤** — M5 (신규)
**상위 문서** — `DESIGN.md` §3 / §4.5 / §4.8, `HANDOFF.md`, `milestones/M4_plan.md`

---

## 1. 배경

M4 까지 — 라이브러리 탭이 PySide6 Qt QSplitter 3 분할 (좌 LabelChipPanel + FilterBar / 중 검색박스 + QTableWidget / 우 SearchSidePanel) 로 동작. 사용자 검증 (2026-05-17) 결과 4 가지 페인:

1. **정보 과부하** — 한 화면에 너무 많은 위젯 동시 노출 (칩 ~316개 + 6 슬라이더 + 저장된 검색 + 다축 필터)
2. **좌우 스크롤로 가려진 콘텐츠** — 좁은 사이드 패널에 칩이 가로 흐름
3. **섹션 역할 불명** — 어느 영역이 뭐 하는지 한눈에 안 보임
4. **가중치 슬라이더 의미 모름** — "이 값을 올리면 무엇이 바뀌는지" 인지 부담

또한 추가 요구 — Claude Code 가 "이 후보들 중 골라줘" 라고 사용자에게 직접 요청해서 사용자가 GAH 화면에서 선택할 수 있게 만들고 싶음.

본 spec 은 4 페인 + Claude 인터랙션 요구를 동시에 해결하기 위해 **GUI 스택 전체를 웹으로 전환** 하면서 **라이브러리 탭을 처음부터 다시 디자인** 한다. M4 의 백엔드 (검색 6채널, 다양성, label_query, saved_searches, feedback_records, 16 MCP 도구) 는 그대로 보존, Qt UI 위젯 4개와 그 테스트만 폐기.

## 2. 합의된 10 개 결정사항 (브레인스토밍 2026-05-17)

| # | 결정 | 근거 |
|---|---|---|
| Q1 | 페인 = 정보 과부하 / 좌우 스크롤 / 섹션 불명 / 가중치 불가해 | 사용자 검증 보고 |
| Q2 | 큰 레이아웃 = **C** — 상단 자연어 검색 + ⚙ 고급 버튼 + 우측 슬라이드 패널 (B/C/D 탭) | 결과 풀폭 우선 + 고급 옵션 시각화 |
| Q3 | B 탭 (정밀 필터) = **안 1** 평탄 노출 + 칩 검색 + FlowLayout wrap | 좌우 스크롤 금지 명시 |
| Q4 | C 탭 (둘러보기) = **안 1** 결과 표시 옵션 (그리드/리스트 토글 + 카드 크기 + 정렬 + 카드 메타 토글) | 결과 영역에 의존하는 자연스러운 컨트롤 |
| Q5 | 결과 카드 = **안 3** 와이드 (썸네일 60×60 좌 + 텍스트 우, 사운드 인라인 ▶ 클릭) | 정보량 + 텍스트 가독성 우선 |
| Q6 | D 탭 (고급 조정) = **안 1** 프리셋 우선 (슬라이더 접힘) + 저장된 검색 + 통일성/페널티 요약 | 가중치 의미 불가해 페인 해결 — 프리셋만으로도 사용 가능 |
| Q7 | 웹 GUI 호스팅 = **안 1** 로컬 웹서버 (FastAPI) + 시스템 기본 브라우저 | Python 백엔드와 자연스러운 통합 + PyInstaller 단순 |
| Q8 | Claude → GAH 사용자 선택 흐름 = **안 1** 동기 long-poll (5분 timeout) | Claude 가 응답 받아 즉시 후속 액션 |
| Q9 | 프런트엔드 스택 = **A** HTMX + Alpine.js | GAH 인터랙션 = 거의 모두 서버 쿼리 → 부분 갱신 패턴 |
| Q10 | M4 처리 = **안 1** 그대로 머지 → M5 가 Qt 위젯 4개 + 테스트 폐기 + 웹 신규 구현 | git history 에 reference 남음, M4 PR 처리 단순 |

## 3. 아키텍처

### 3.1 프로세스 / 스택

```
┌──────────────────────────────────────────────────────────────┐
│ Qt 트레이 (PySide6, 백그라운드)                                │
│  - 트레이 아이콘 + 메뉴 ("메인 창 열기" → 브라우저 URL)        │
│  - 분석 큐 진행률 툴팁 (M2.1 유지)                              │
│  - 라벨 관리 다이얼로그는 폐기 — 웹 UI 의 axis 관리 페이지로     │
└──────────────────────────────┬───────────────────────────────┘
                                │ embedded process
┌──────────────────────────────▼───────────────────────────────┐
│ FastAPI 웹서버 (uvicorn, localhost:9874)                      │
│  - REST: /api/search, /api/library, /api/saved_searches, ...  │
│  - HTML fragments: /ui/search-results, /ui/chip-panel, ...    │
│  - WebSocket /ws/notifications: Claude pick 요청 push, 분석    │
│    진행률 push                                                  │
│  - 정적: /static/htmx.min.js + alpine.min.js + 자체 CSS         │
└──────────────────────────────┬───────────────────────────────┘
                                │ in-process
┌──────────────────────────────▼───────────────────────────────┐
│ 기존 Python 백엔드 (M3/M4 그대로)                              │
│  - Store / HybridSearcher / ConsistencyScorer / UsageTracker  │
│  - LabelRegistry / AnalysisQueue / Embedding / CLIP / Ollama  │
│  - MCP server (별 프로세스 그대로) — 새 도구 추가              │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ Claude Code (별 프로세스)                                      │
│  - stdio JSON-RPC 로 gah --mcp 와 통신                         │
│  - request_user_pick(candidates, reason, timeout=300)         │
│    → GAH 가 WebSocket 으로 웹 UI 에 push                       │
│    → 사용자 클릭 대기 → 응답                                    │
└──────────────────────────────────────────────────────────────┘
```

### 3.2 통신 경계

| 경계 | 방식 | 사용처 |
|---|---|---|
| 트레이 → 웹서버 | 같은 프로세스 (또는 subprocess) | 부팅 시 uvicorn 시작 |
| 트레이 → 브라우저 | `webbrowser.open(url)` | "메인 창 열기" 메뉴 |
| 브라우저 → FastAPI | HTTP GET/POST (HTMX hx-get/hx-post) | UI 인터랙션 |
| 브라우저 → FastAPI | WebSocket | 실시간 알림 (Claude pick, 분석 진행) |
| FastAPI → Python 백엔드 | 함수 호출 (in-process) | 검색, 라벨, 저장된 검색 등 |
| MCP server → FastAPI | HTTP POST (localhost) 또는 in-process 공유 | `request_user_pick` 시 WebSocket push 트리거 |

### 3.3 포트 / 보안

- **포트** — `Config.web_port` (기본 9874, 사용 중이면 +1 씩 시도). MCP `Config.mcp_port` (9874) 와 분리 검토 필요 — M5 plan 단계에서 확정.
- **바인딩** — `127.0.0.1` 만 (외부 노출 X). `Config.web_host` 로 override 가능 (LAN 모바일 접속 시).
- **인증** — 로컬 단일 사용자라 인증 없음. (LAN 확장 시 토큰 옵션 검토 — M5+)
- **CORS** — same-origin 만 허용.

## 4. 라이브러리 탭 리디자인

### 4.1 전체 레이아웃 (옵션 C)

```
┌──────────────────────────────────────────────────────────────────┐
│ 🔍 [자연어 검색…                            ] [⚙ 고급]            │ ← 상단 검색바
├──────────────────────────────────────────────────────────────────┤
│ ┌──────────────────────────────────────┐ ┌─────────────────────┐ │
│ │ [🖼 그리드][≡ 리스트] [S][M][L] [정렬▼] │ │ ┌─B────C────D───┐ │ │
│ │ 총 199 자산                            │ │ │ B 필터 (선택됨) │ │ │
│ │ ┌────────┐ ┌────────┐                  │ │ ├─────────────────┤ │ │
│ │ │🖼 hero  │ │🪙 coin  │                  │ │ │ AND/OR/NOT      │ │ │
│ │ │name 0.92│ │name 0.87│                  │ │ │ 🔍 라벨 검색…   │ │ │
│ │ │meta 1줄 │ │meta 1줄 │                  │ │ │ [스프][시트][사] │ │ │
│ │ └────────┘ └────────┘                  │ │ │ axis chips wrap │ │ │
│ │ ┌────────┐ ┌────────┐                  │ │ │ 다축 필터       │ │ │
│ │ │🔊 jump  │ │🌌 bg    │                  │ │ │                 │ │ │
│ │ │ ▶ 재생 │ │name 0.78│                  │ │ │                 │ │ │
│ │ └────────┘ └────────┘                  │ │ └─────────────────┘ │ │
│ │ (페이지네이션)                          │ │                     │ │
│ └──────────────────────────────────────┘ └─────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
   결과 영역 (메인)                          우측 슬라이드 (⚙ 클릭 시)
```

⚙ 고급 버튼 닫힘 → 결과 영역 풀폭. 펼침 → 우측 320px 사이드 패널 슬라이드 인. 사이드 폭은 사용자가 드래그 조절 (`Alpine.js` resize handle).

### 4.2 상단 검색 영역

- **자연어 검색박스** — 항상 노출. placeholder `자연어 검색…  (예: 어두운 BGM 짧은 거)`.
- **디바운스** — 입력 후 300ms (HTMX `hx-trigger="keyup changed delay:300ms"`).
- **검색 동작** — `hx-post="/ui/search-results"` 로 결과 영역 부분 갱신.
- **고급 토글** — `⚙ 고급` 버튼. Alpine state `advancedOpen` 토글. 펼쳐지면 ✕ 표시.
- **label_query 통합** — 검색박스 텍스트가 query + label_query 양쪽으로 전달 (M4 와 동일).

### 4.3 결과 영역

#### 4.3.1 툴바 (한 줄)
```
[🖼 그리드 ⬛ 리스트]  [S M L]  [정렬: 추가일↓▼]    총 N 자산
```
- **그리드/리스트 토글** — Alpine state `viewMode`. 그리드 = 카드 2~4 열, 리스트 = 1 열 풀폭.
- **카드 크기** — S/M/L (썸네일 40/60/96px). Alpine state `cardSize`.
- **정렬** — score↓ / 추가일↓ / 추가일↑ / 이름↑ / 이름↓ / 크기↓ / 크기↑.
- **총 자산 카운트** — 서버 응답에서.

#### 4.3.2 와이드 카드 (안 3 확정)
```
┌─────────────────────────────────────────────┐
│ ┌────┐  hero.png                   [0.92]  │
│ │ 🦸 │  character · pixel_art · heroic     │
│ │60px│  pack_a · 64×64 · 12KB              │
│ └────┘                                       │
└─────────────────────────────────────────────┘
```
- **스프라이트** — 썸네일 60×60 (lazy 256×256 PNG 캐시 — M4 `thumbnails.py` 재사용, frontend 가 `<img src="/api/thumbnail/{asset_id}">`).
- **사운드** — 썸네일 자리에 🔊 아이콘 + 카테고리 색 그라데이션. 텍스트 옆 `▶ 재생` 인라인 버튼 — 클릭 시 HTMX 가 `<audio>` 요소 swap.
- **스프라이트시트** — M5 는 일반 sprite 와 동일하게 표시 (분할 전 원본 PNG). M6 가 `sprite_meta.frame_count` 를 채우면 그 후 카드 우상단에 `🎞 N frames` 배지 추가 — 같은 카드 컴포넌트가 옵셔널 메타 노출.
- **클릭 동작** — 카드 클릭 시 상세 모달 (HTMX `hx-get="/ui/asset-detail/{id}"` → `<dialog>` swap). 채택 버튼은 모달 안.

#### 4.3.3 디폴트 상태 (검색 없음)

검색박스 비어 + 칩 선택 0 → 결과 영역에 **라이브러리 전체** 노출 (정렬 = 추가일↓ 디폴트). 페이지 50개 단위 + "더 보기" 버튼 또는 무한 스크롤 (HTMX `hx-trigger="revealed"`). v1 은 더 보기 버튼.

### 4.4 우측 사이드 패널 (B/C/D 탭)

탭 헤더 3 개 — `B 필터` / `C 표시` / `D 조정`. 클릭으로 전환 (Alpine state `activeTab`).

#### 4.4.1 B 탭 — 정밀 필터

```
┌─────────────────────────────────────┐
│ 매칭 모드: ● AND  ○ OR  ○ NOT       │
├─────────────────────────────────────┤
│ 🔍 라벨 검색…              [dark]    │
├─────────────────────────────────────┤
│ [스프라이트] [시트] [사운드]          │  ← 종류 탭 (axis 분류)
├─────────────────────────────────────┤
│ category                              │
│ [character] [creature] [tile] [ui]    │  ← FlowLayout wrap
│ [icon] [effect] [prop] [item] ...     │
│                                       │
│ style                                 │
│ [pixel_art] [vector_flat] [anime]     │
│ [hand_drawn] [painterly] ...          │
│                                       │
│ mood                                  │
│ [heroic] [dark★] [epic] [hopeful] ...│  ← "dark" 매칭 강조
│                                       │
│ (axis 14개 모두 펼침, 세로 스크롤)   │
├─────────────────────────────────────┤
│ 다축 필터                             │
│ [팩▼] [상태▼] [라이선스▼] [벤더▼]   │
└─────────────────────────────────────┘
```

- **매칭 모드** — 패널 전체 단위. M4 와 동일.
- **라벨 검색** — substring case-insensitive 매칭. 매칭 칩은 노란 강조 (선택과 별개 시각화).
- **종류 탭** — sprite / spritesheet / sound 분류 (axis 이름 prefix 기반: `sound_*` → 사운드, `sheet_*` → 시트, 나머지 → 스프라이트). M4 분류 그대로 재사용.
- **칩 wrap** — CSS `display: flex; flex-wrap: wrap;` 로 자연스럽게 줄바꿈. Qt FlowLayout 자체 구현 없이 CSS 만으로 해결.
- **칩 클릭** — HTMX `hx-post="/ui/filter-changed"` → 결과 영역 갱신 + 칩 상태 갱신.
- **다축 필터** — 드롭다운 4개 (팩 다중, 상태, 라이선스, 벤더). 정렬은 결과 툴바로 이동 (C 탭이 아닌 결과 영역 위).

#### 4.4.2 C 탭 — 표시 옵션

```
┌─────────────────────────────────────┐
│ 결과 표시 형식                       │
│ [🖼 그리드 (선택)] [≡ 리스트]        │
├─────────────────────────────────────┤
│ 카드 크기                             │
│ [S] [M (선택)] [L]                    │
├─────────────────────────────────────┤
│ 정렬                                  │
│ [점수↓] [추가일↓ (선택)] [이름↑] ... │
├─────────────────────────────────────┤
│ 카드에 표시                           │
│ [✓ 라벨] [✓ 팩] [□ 점수] [□ 크기]    │
└─────────────────────────────────────┘
```

- **그리드/리스트 토글, 카드 크기, 정렬** — 결과 영역 툴바와 동기 (양방향 바인딩).
- **카드 메타 토글** — 카드 한 줄에 무엇을 표시할지 (Alpine state, 즉시 결과 영역 재렌더).

#### 4.4.3 D 탭 — 고급 조정

```
┌─────────────────────────────────────┐
│ 검색 스타일                           │
│ [균형 (선택)] [통일성 우선] [참신성]  │
│ ● 균형 — 의미·통일성·최신성을 골고루.│
│ ⓘ 같은 프로젝트에서 채택한 팩 우선.  │
│                                       │
│ ▶ 슬라이더 직접 조정…                │
├─────────────────────────────────────┤
│ 저장된 검색                           │
│ ┌─────────────────────────────────┐ │
│ │ 전투 BGM 다크          2시간 전  │ │  ← 우클릭 메뉴 (수정/삭제)
│ │ UI 아이콘 픽셀         어제      │ │
│ └─────────────────────────────────┘ │
│ [+ 현재 검색 저장]                    │
├─────────────────────────────────────┤
│ 통일성 / 페널티 학습                  │
│ • 채택 팩: pack_a (12회)             │
│ • 거부: 2개 (지난 30일)               │
│ [상세 보기…]                          │
└─────────────────────────────────────┘
```

- **프리셋** — 3 버튼 (균형/통일성/참신성). 클릭 시 6 슬라이더 + Config 즉시 갱신. 1줄 설명 + ⓘ 효과 안내.
- **슬라이더 펼침** — "▶ 슬라이더 직접 조정…" 클릭 시 6 슬라이더 표시. 각 슬라이더 옆 한 줄 설명 (M4 안 2 의 단순화 버전).
- **저장된 검색** — M4 와 동일 (이름 수정 / 삭제 / 덮어쓰기 / 중복 방지). 우클릭 메뉴는 HTMX 가 아니라 Alpine + native context menu API (또는 메뉴 버튼).
- **통일성 / 페널티 요약** — 현재 프로젝트 (또는 global) 의 사용 분포. 정적 텍스트 (서버 렌더). "상세 보기" → 모달.

### 4.5 CSS 테마

- **다크 모드 / 라이트 모드** — Tailwind CSS 또는 CSS 변수 기반. OS prefers-color-scheme 자동 + 토글 옵션.
- **반응형** — 사이드 패널은 화면 폭 ≤ 768px 시 자동 닫힘 + 모달로 전환.
- **i18n** — 모든 사용자 노출 문자열을 `i18n.ko.json` / `i18n.en.json` 분리. Alpine `x-text` 또는 서버 렌더 시 `{{ _("...") }}`. M4 의 `tr()` 패턴을 웹용으로 재구현.

## 5. Claude → GAH 사용자 선택 인터랙션 (`request_user_pick`)

### 5.1 신규 MCP 도구

```jsonc
// input
{
  "candidates": [142, 158, 203, 311, 425],     // asset_id 5개 (최대 10)
  "reason": "전투 BGM 다크한 거 5개 후보 — 사용자가 골라줘",  // optional, 사용자에게 노출
  "project_id": "D:/Unity/MyGame",              // optional
  "timeout_seconds": 300                        // 기본 300 (5분)
}

// output (사용자 응답 후)
{
  "picked_asset_id": 158,
  "picked_at": 1747500900,                      // unix timestamp
  "user_note": "이게 가장 어울려요"                // optional, 사용자 메모
}

// timeout 응답
{ "error": { "code": "408_timeout", "message": "..." } }

// 사용자 거부 응답
{ "error": { "code": "499_user_cancelled", "message": "..." } }
```

### 5.2 흐름

```
[1] Claude → MCP stdio → GAH MCP server
    request_user_pick(candidates, reason, timeout)

[2] GAH MCP server → in-process queue
    pending_picks[request_id] = {candidates, reason, asyncio.Future()}
    + FastAPI 가 같은 in-process 큐 참조

[3] FastAPI → WebSocket → 브라우저
    {
      type: "user_pick_request",
      request_id: "rq_42",
      candidates: [...asset 메타...],
      reason: "..."
    }

[4] 브라우저 알림
    - 헤더에 "🤖 Claude 요청 (1)" 배지
    - 결과 영역 상단에 "Claude 요청 카드" 강조 표시
    - OS 알림 옵션 (선택)
    - 트레이 아이콘 깜빡임 (Qt)

[5] 사용자가 후보 카드 중 하나 클릭 + [채택] 버튼
    → HTMX POST /api/user-pick/{request_id} {picked: 158}

[6] FastAPI → in-process queue
    pending_picks[request_id].future.set_result({picked: 158, ...})

[7] GAH MCP server (Claude 가 await 중)
    → MCP 응답 반환

[8] GAH 자동으로 record_asset_use(project_id, 158, query_id=None,
    context=reason) 호출  ─ query_id 는 request_user_pick 가 발급 안 함 (검색
    이력 없음). 추적은 context (reason) + 신규 source='claude_pick' 으로.

[9] Claude 응답 받아 후속 액션 (파일 복사 등)
```

### 5.3 사용자 거부 / Timeout

- **사용자 거부** — "Claude 요청 카드" 옆 [✕ 거부] 버튼 → `499_user_cancelled`.
- **Timeout** — 5분 후 asyncio Future 미해결 → MCP 응답 `408_timeout`. 사용자 UI 의 요청 카드는 회색 처리 + "시간 초과" 라벨.
- **사용자 자리비움 감지** — 옵션 (M5+ 검토). v1 은 단순 timeout.

### 5.4 동시 요청

- 큐는 list — 여러 Claude 세션 또는 같은 세션의 여러 요청 동시 가능.
- 헤더 배지에 카운트 (`🤖 Claude 요청 (3)`).
- 사용자 UI 에선 새로운 요청부터 위에 노출 (LIFO).

### 5.5 MCP 모델

```python
class RequestUserPickRequest(_BaseModel):
    candidates: list[int] = Field(min_length=1, max_length=10)
    reason: str | None = None
    project_id: str | None = None
    timeout_seconds: int = Field(default=300, ge=10, le=1800)

class RequestUserPickResult(_BaseModel):
    picked_asset_id: int
    picked_at: int
    user_note: str | None = None
```

### 5.6 디스플레이 정책

- 후보 자산은 결과 영역 최상단에 "Claude 요청" 섹션으로 표시 (기존 검색 결과는 그 아래 그대로).
- 후보 카드 디자인 = 일반 와이드 카드 + 좌측 보라색 띠 + 우상단 `🤖 Claude 요청` 배지.

## 6. M4 Qt 위젯 폐기 + 보존 경계

### 6.1 폐기 대상 (M5 가 제거)

| 파일 | 라인 수 | 비고 |
|---|---:|---|
| `src/gah/ui/library_view.py` | ~330 | QSplitter 3 분할 + setter |
| `src/gah/ui/label_chip_panel.py` | ~170 | QTabWidget + axis 칩 |
| `src/gah/ui/search_side_panel.py` | ~260 | 6 슬라이더 + 저장된 검색 |
| `src/gah/ui/filter_bar.py` | ~170 | 다축 필터 |
| `tests/test_library_search_ui.py` | ~100 | M3 검색 박스 디바운스 |
| `tests/test_library_search_ui_rich.py` | ~560 | M4 풍부 UX 테스트 17 케이스 |

### 6.2 보존 대상 (그대로 유지)

| 모듈 | 책임 | 웹 UI 가 호출 |
|---|---|---|
| `core/store.py` | SQLite + M4 schema (saved_searches, feedback_records) | ✓ |
| `core/search.py` (HybridSearcher) | 6채널 가중합 + diversity + label_query | ✓ |
| `core/consistency.py` | 통일성 점수 | ✓ |
| `core/usage_tracker.py` | 사용 이력 | ✓ |
| `core/label_query.py` | 자연어 라벨 부울 파서 | ✓ |
| `core/labels.py` (LabelRegistry) | 24축 316 라벨 | ✓ |
| `core/thumbnails.py` | lazy 256×256 PNG | ✓ (HTTP endpoint 추가) |
| `core/suggest_packs.py` | 풍부 samples | ✓ |
| `core/analysis_queue.py` 등 분석 파이프라인 | M2/M2.1 그대로 | ✓ |
| `mcp/*` | 16 도구 + 신규 17번째 `request_user_pick` | ✓ (도구 추가) |
| `tray.py` | 트레이 아이콘 + 메뉴 (메인 창 열기 → 브라우저) | 변경 |
| `app.py` (`run_tray`) | 부팅 흐름 — uvicorn 시작 + 트레이 wiring | 변경 |
| `ui/main_window.py`, `ui/pack_view.py` | Pack 탭 + 메인 윈도우 | **폐기 검토** — 웹 UI 가 전체 대체 |

`main_window.py` / `pack_view.py` 도 폐기 대상 후보. M1 의 Pack 탭은 단순 리스트라 웹으로 즉시 옮길 수 있음. **M5 plan 단계에서 확정** (§13 Q3 참조).

### 6.3 트레이 변경

- 트레이 아이콘 + 분석 큐 툴팁 — 그대로.
- 메뉴 항목 — `메인 창 열기` → `webbrowser.open("http://localhost:9874")`. 나머지 (`라이브러리 폴더 열기`, `재스캔`, `종료`) 유지.
- 부팅 시 uvicorn 서브프로세스 또는 같은 프로세스 thread 로 FastAPI 시작 — M5 plan 에서 확정.

## 7. 신규 의존성

| 패키지 | 용도 |
|---|---|
| `fastapi>=0.110` | 웹서버 프레임워크 |
| `uvicorn[standard]>=0.27` | ASGI 서버 |
| `jinja2>=3.1` | HTML 템플릿 |
| `python-multipart>=0.0.9` | form 데이터 (HTMX POST) |
| `websockets>=12` | WebSocket 지원 (uvicorn 의존성에 이미 포함 가능) |

정적 JS (HTMX + Alpine) 는 vendoring (`static/vendor/htmx.min.js`, `alpine.min.js`) — 외부 CDN 의존 X (오프라인 사용 가능).

기존: pydantic / httpx / Pillow / numpy / mcp 모두 재사용.

## 8. 테스트 전략

### 8.1 백엔드 테스트 (pytest)

- **FastAPI 라우트 단위** — `httpx.AsyncClient` 로 `/api/*` 엔드포인트 검증. 응답 JSON / HTML fragment 형태.
- **WebSocket** — `httpx_ws` 또는 `websockets` 로 push 시나리오 검증 (Claude pick request push, 분석 진행률).
- **MCP `request_user_pick`** — asyncio mock 큐 + future. timeout 케이스 + 사용자 거부 케이스 + 정상 응답 케이스.
- **기존 백엔드 테스트** — `test_store_m4` / `test_search_m4` / `test_label_query` 등 모두 그대로 통과해야 (M4 백엔드 보존 확인).

### 8.2 프런트엔드 테스트 (별 전략)

- **단위 (Alpine 컴포넌트)** — Vitest 없이도 가능. Jest/Playwright 등은 도입 안 함 (빌드 도구 없이 가는 방침).
- **e2e (옵션 — `playwright_integration` 마크로 deselect)** — Playwright 로 실 브라우저 시나리오. 클릭/타이핑/렌더 검증. v1 은 1~2 핵심 시나리오만 (검색 → 결과 갱신, Claude pick 흐름).
- **수동 시각 검증** — 사용자가 검증 단계에서 직접 확인 (M4 패턴 유지).

### 8.3 회귀

- M3/M4 의 `pytest -m mcp_integration` (16 도구 → 17 도구) 갱신.
- 폐기되는 Qt UI 테스트 (`test_library_search_ui*.py`) 는 삭제 — 회귀 X (Qt 위젯 자체가 없어졌으므로).

## 9. 일정 추정

| 단계 | 일정 |
|---|---:|
| FastAPI + HTMX/Alpine 스캐폴딩 + 트레이 통합 | 1주 |
| 라이브러리 탭 — 검색 영역 + 결과 영역 (와이드 카드 그리드/리스트) | 1주 |
| B 탭 (정밀 필터) + C 탭 (표시 옵션) + D 탭 (프리셋/저장된 검색) | 1.5주 |
| Claude `request_user_pick` MCP 도구 + WebSocket push + UI 큐 | 1주 |
| Qt 위젯 폐기 + Pack 탭 웹 이식 + 라벨 관리 페이지 | 0.5주 |
| 마감 + 사용자 검증 사이클 | 0.5주 |
| **합계** | **~5.5주** |

기존 M4 (1.5주) 대비 큰 마일스톤. M5 가 끝나야 M6 (시트 분석) 으로 진행.

## 10. 마일스톤 재정렬

| 신규 # | 이름 | 일정 | 기존 # |
|---:|---|---:|---:|
| M0~M3 | (변경 없음) | — | — |
| M4 | 검색 UX 풍부화 (Qt 위젯) | (완료, 머지 후 폐기 예정) | M4 |
| **M5** | **웹 GUI 전환 + 라이브러리 리디자인 + Claude pick 인터랙션** | **~5.5주** | **신규** |
| M6 | 시트 분석 + 애니메이션 | 1주 | M5 |
| M7 | Unity Asset Store 임포트 | 1주 | M6 |
| M8 | 패키징 + i18n (PyInstaller / Tauri 등) | 1주 | M7 |

CLAUDE.md §2 진행 현황 표 / HANDOFF.md §5 / milestones/README.md / DESIGN.md §11 모두 M5 plan 작성 시 갱신.

## 11. 보안 / 운영

- **로컬 단일 사용자 가정** — localhost 바인딩, 인증 없음.
- **CORS** — same-origin only.
- **포트 충돌** — 9874 사용 중이면 자동 +1 시도 (최대 9884).
- **종료** — 트레이 종료 시 uvicorn graceful shutdown + 분석 큐 stop.
- **세션** — 서버 상태 = 단일 사용자 가정. WebSocket 연결 = 활성 브라우저 탭 (여러 탭 가능, 모두 같은 알림 받음).

## 12. 의도적으로 미룬 항목 (M5+ / M6+ / M7+)

- **다크 모드 토글 UI** — CSS 변수 + OS prefers-color-scheme 자동만 v1. 사용자 토글은 M6+.
- **모바일 / 반응형** — 768px 이하 사이드 패널 자동 닫힘만. 전반적 모바일 최적화는 M7+.
- **인증 / 멀티 사용자** — v1 단일 사용자. LAN 멀티 접속은 M7+ (토큰 옵션).
- **e2e 자동화 테스트 (Playwright)** — 옵트인 마크로 1~2 시나리오만. 풍부한 e2e 는 M6+.
- **Pack 탭 / 라벨 관리 / 프로젝트 탭 풍부 UX** — M5 는 최소 이식 (Pack 리스트 + 라벨 어드민 폼). 풍부 UX 는 M7 (패키징 마감 단계).
- **사용자 자리비움 감지 → 자동 timeout 연장** — 단순 5분 timeout 만 v1.
- **request_user_pick 의 batch 모드** (한 번에 여러 후보 그룹 선택) — v1 은 단일 선택만.

## 13. 열린 질문 / 결정 보류

1. **FastAPI 가 트레이와 같은 프로세스 vs subprocess** — 같은 프로세스가 단순 (queue 공유 자연스러움) 하지만 PySide6 + asyncio 통합 까다로움. M5 plan §3.x 에서 확정.
2. **WebSocket vs Server-Sent Events** — push only 라 SSE 로 충분할 수도. WebSocket 은 양방향이지만 GAH 는 한쪽만 사용. 단순성 vs 일관성.
3. **Pack 탭 / 라벨 관리 페이지 폐기 시점** — M5 안에서 다 폐기 + 웹 이식 vs M5 는 라이브러리 탭만 + Pack 은 M6+.
4. **Claude `request_user_pick` 응답 후 자동 record_asset_use 호출 vs Claude 가 명시 호출** — 자동이 단순하지만 Claude 의 의도와 어긋날 수 있음. v1 자동.
5. **i18n 백엔드 (Jinja2 + babel)** — Python 표준 gettext 통합 또는 단순 JSON 변환기. v1 단순.

---

## 자기 검토 메모

- §2 결정사항 10개 ↔ §3~§6 디자인 매핑 — 모든 결정이 디자인에 반영됨 ✓
- §4.4 의 B/C/D 탭 컨트롤이 §3 의 보존 백엔드 (HybridSearcher / saved_searches / feedback_records) 와 1:1 매핑 ✓
- §5.5 의 MCP 모델이 기존 `mcp/models.py` 패턴 (`_BaseModel` + `extra="forbid"`) 과 일관 ✓
- §6 폐기/보존 경계 — 백엔드 보존 100%, UI 위젯 100% 폐기 ✓
- §9 일정 5.5주 ↔ §10 마일스톤 표 — 일치 ✓
- §11 보안 — 로컬 단일 사용자 기준, LAN 확장 미룸 ✓
- §13 열린 질문 5개 모두 M5 plan §3.x 또는 §6 에서 확정 표시 ✓
- 한국어 spec / 영어 파일·폴더명 — 준수 ✓
- 메모리 `feedback_korean_for_pr_and_commits.md` — GitHub 노출 spec 이라 한국어 ✓
- 메모리 `feedback_milestone_manual_verification_format.md` — M5 끝에 단계별 체크리스트로 시각 검증 항목 별도 제시 예정 ✓

검토 끝.
