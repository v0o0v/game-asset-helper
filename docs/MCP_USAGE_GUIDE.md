# MCP 활용 가이드

이 문서는 **Claude Code(또는 다른 MCP 클라이언트)가 GAH MCP 서버를 어떻게 사용하면 좋은지** 알려 주는 가이드. M3 가 MCP stdio 서버를 구현하면서 채워 졌다.

서버 진입:

```powershell
python -m gah --mcp
```

→ JSON-RPC over stdio. Claude Code 는 이 명령을 child process 로 spawn 하고 `tools/list` 로 **20 개** 도구를 발견한다 (M3 의 12 + M4 의 saved_searches 4 + M5 의 request_user_pick 1 + M6 의 suggest_animation_frames 1 + **M7 의 scan_unity_asset_store_cache + list_unity_packages 2**).

## 1. 라벨 어휘는 "자기 기술" 한다

GAH 의 라벨 어휘는 24축 ≈ 316개의 영어 enum 토큰으로 구성된다. 각 라벨은 영어 한 줄 description 을 동봉하므로, Claude Code 는 사용자 자연어 쿼리를 **라벨 어휘에 매핑**할 수 있다.

M3 가 추가할 메타 도구:

- `list_label_axes() -> { axes: ["category", "style", ..., "sound_voice_type"] }`
- `list_labels(axis, enabled_only=true, with_description=true) -> { labels: [...], signature: "..." }`
- `describe_label(axis, label) -> { axis, label, description, sample_assets: [...] }`

권장 흐름:
1. **세션 시작 시** `list_labels(with_description=true)` 한 번 호출 → 응답의 `signature` 와 함께 캐시.
2. 이후 호출에서 `signature` 가 동일하면 캐시 재사용. 사용자가 GUI 라벨 관리에서 라벨을 추가/비활/편집하면 signature 가 바뀌므로 다음 호출에서 자동 새로고침.

## 2. 자연어 쿼리는 그대로 + 라벨 부울 필터 권장

사용자가 `"전투 시 깔릴 빠르고 어두운 오케스트라 BGM, 1분 이내, 루프"` 같은 자연어로 요청하면 Claude Code 는:

1. 자연어 쿼리를 그대로 `find_asset` 에 `query` 로 전달.
2. 동시에 라벨 어휘를 활용해 **부울 필터**를 같이 보낸다:

   ```jsonc
   {
     "query": "전투 시 깔릴 빠르고 어두운 오케스트라 BGM",
     "kind": "sound",
     "filters": { "max_duration_ms": 60000, "loopable": true },
     "labels_all": [{"axis": "sound_category", "label": "bgm"}],
     "labels_any": [
       {"axis": "sound_mood",       "label": "dark"},
       {"axis": "sound_use",        "label": "combat"},
       {"axis": "sound_tempo",      "label": "fast"},
       {"axis": "sound_genre",      "label": "orchestral"},
       {"axis": "sound_instrument", "label": "strings"}
     ],
     "project_id": "D:/Unity/MyGame",
     "count": 5
   }
   ```

3. 서버는 임베딩 코사인 + FTS5 BM25 + `asset_labels.score` + 통일성 가중치를 합산해 top-N 을 돌려준다.

## 3. 응답의 `matched_labels` 가 추천 근거다

응답에는 각 결과의 매칭된 라벨이 들어온다:

```jsonc
{
  "asset_id": 142,
  "score": 0.91,
  "matched_labels": [
    {"axis": "sound_category", "label": "bgm",        "source": "gemma", "score": 0.85},
    {"axis": "sound_mood",     "label": "dark",       "source": "gemma", "score": 0.78},
    {"axis": "sound_tempo",    "label": "fast",       "source": "gemma", "score": 0.78},
    {"axis": "sound_genre",    "label": "orchestral", "source": "gemma", "score": 0.78},
    {"axis": "sound_use",      "label": "combat",     "source": "gemma", "score": 0.78}
  ],
  "score_breakdown": {
    "semantic": 0.42, "keyword": 0.15,
    "label_match": 0.20, "consistency": 0.14
  },
  "why": "…",
  "path": "C:/.../battle_dark_01.ogg"
}
```

Claude Code 는 이 정보를 사용자에게 그대로 풀어쓸 수 있어 **추천 근거가 자동 생성**된다.

## 4. 표준 워크플로 (DESIGN §13 참조)

세션 흐름:

1. `list_packs` + `list_labels(with_description=true)` → 카탈로그/어휘 캐시.
2. 사용자 요청 → `suggest_packs(query, project_id, kind)` → 사용자에게 팩 후보 제시.
3. 사용자가 팩 선택 → `find_asset(force_pack_id=<선택>, ...)`.
4. Unity 프로젝트로 복사 후 → `record_asset_use(asset_id, project_id, query_id)`.

`project_id` 는 매 호출에 그대로 전달. 통일성 가중치가 이력 기반으로 같은 프로젝트를 같은 팩 쪽으로 수렴시킨다.

## 5. M3 작업 시 참조

- 본 stub 의 입력·응답 모양을 그대로 `gah.mcp.server` / `gah.mcp.tools` 에 구현.
- `list_labels` 의 `signature` 는 `LabelRegistry.label_catalog_signature()` 직접 위임.
- `labels_all` / `labels_any` / `labels_none` 필터는 `assets_fts MATCH 'label:...'` + `asset_labels` JOIN 로 풀어낸다 (M3 plan 에서 정확 SQL 결정).
- `matched_labels` 는 `asset_labels` 의 행을 `LabelScore` 그대로 반환.
- MCP 서버 `instructions` 필드에 본 문서 §1 ~ §4 요지를 한 문단으로 압축해 박아 둔다.

## 6. 12 도구 명세 (실응답 JSON)

### 6.1 `find_asset`

```jsonc
// 입력
{
  "query": "전투 시 깔릴 빠르고 어두운 오케스트라 BGM",
  "kind": "sound",
  "count": 5,
  "project_id": "D:/Unity/MyGame",
  "filters": { "max_duration_ms": 60000, "loopable": true },
  "labels_all": [{"axis": "sound_category", "label": "bgm"}],
  "labels_any": [
    {"axis": "sound_mood", "label": "dark"},
    {"axis": "sound_use",  "label": "combat"}
  ]
}

// 출력
{
  "query_id": 17,
  "results": [
    {
      "asset_id": 142,
      "pack_id": 7,
      "pack_name": "Kenney Audio Pack",
      "path": "C:/.../kenney_audio/Sounds/battle_dark_01.ogg",
      "score": 0.87,
      "score_breakdown": {
        "semantic": 0.32, "keyword": 0.12, "label_match": 0.18,
        "consistency": 0.20, "recency": 0.05
      },
      "matched_labels": [
        {"axis": "sound_category", "label": "bgm",    "source": "gemma", "score": 0.91},
        {"axis": "sound_mood",     "label": "dark",   "source": "gemma", "score": 0.78}
      ],
      "why": "이 프로젝트가 Kenney Audio Pack 을 12회 채택했음 · 매칭 라벨: sound_category=bgm, sound_mood=dark",
      "meta": { "duration_ms": 47000, "loopable": true }
    }
  ]
}
```

### 6.2 `suggest_packs`

쿼리에 어울리는 팩 후보를 정렬한다 (사용자에게 팩 선택권 제공). 응답에 `samples` (상위 3 자산) + `score_breakdown` 포함.

### 6.3 `record_asset_use`

```jsonc
// 입력
{ "project_id": "D:/Unity/MyGame", "asset_id": 142, "query_id": 17, "context": "Stage1 BGM" }
// 출력
{ "ok": true, "usage_id": 88 }
```

이 호출이 누적될수록 같은 프로젝트의 후속 `find_asset` 의 `consistency` 채널 점수가 올라간다.

### 6.4 `list_labels`

```jsonc
// 입력
{ "axis": "sound_mood", "enabled_only": true, "with_description": true }
// 출력
{
  "labels": [
    {"axis": "sound_mood", "label": "dark",     "source": "seed", "description": "Ominous, low, somber tone."},
    {"axis": "sound_mood", "label": "uplifting","source": "seed", "description": "Bright, energetic, hopeful."}
  ],
  "signature": "9b3f...c1a2"
}
```

### 6.5 `describe_label`

```jsonc
// 입력
{ "axis": "category", "label": "character" }
// 출력
{
  "axis": "category", "label": "character",
  "description": "A playable or NPC figure (humanoid, creature, mascot).",
  "sample_assets": [
    {"asset_id": 33, "pack_id": 7, "pack_name": "Kenney Platformer", "path": ".../hero.png"}
  ]
}
```

### 6.6 나머지 7 개 도구 요약

- `get_asset(asset_id|path)` — 단일 자산 조회
- `list_assets(pack_id?, kind?, page, page_size)` — 페이지네이션
- `list_packs()` — 팩 카탈로그 + asset_counts + aggregate_meta
- `set_project_pin(project_id, pinned_pack_id?, blocked_pack_ids[])` — 강한 선호 지정
- `request_rescan(pack_id|asset_id|all)` — 강제 재분석 (워커 없으면 warnings 포함 OK)
- `report_feedback(query_id, asset_id, reason)` — **M4: 페널티 학습 활성**. reason ∈ `negative|positive|irrelevant`.
- `list_label_axes()` — 24 축 목록

### 6.7 M4 신규 4 도구 — saved_searches

```jsonc
// save_search 입력
{
  "project_id": "D:/Unity/MyGame",
  "name": "전투 BGM 다크",
  "query": "전투 BGM",
  "label_query": "sound_mood:dark AND sound_use:combat NOT sound_genre:chiptune",
  "kind": "sound",
  "diversity": "mmr",
  "diversity_lambda": 0.7,
  "count": 10
}
// save_search 출력
{ "ok": true, "saved_search_id": 17 }

// list_saved_searches 입력 — project_id 만 (없으면 global)
"D:/Unity/MyGame"
// list_saved_searches 출력 — last_used_at DESC
{
  "saved_searches": [
    {"id": 17, "name": "전투 BGM 다크", "query_json": "{...}",
     "created_at": 1747500000, "last_used_at": 1747500900}
  ]
}

// delete_saved_search 입력 — 미존재 시 404
{ "project_id": "D:/Unity/MyGame", "name": "전투 BGM 다크" }
// → { "ok": true } 또는 404_not_found

// run_saved_search 입력 — overrides 로 일부 필드 덮어쓰기
{ "project_id": "D:/Unity/MyGame", "name": "전투 BGM 다크",
  "overrides": { "count": 5 } }
// → tool_find_asset 결과 (FindAssetResult)
```

### 6.8 M5 신규 1 도구 — `request_user_pick`

후보 자산들 중 사용자가 직접 고르도록 요청하는 long-poll 도구 (5분 기본 대기).
GAH 웹 UI 가 열려 있어야 동작한다.

```jsonc
// 입력
{
  "candidates": [42, 99, 130],        // 필수. 1~10개 asset_id
  "reason": "스타일이 비슷해서 주관적 선택이 필요합니다",  // 선택적
  "project_id": "D:/Unity/MyGame",   // 선택적. 있으면 채택 후 자동 record_asset_use
  "timeout_seconds": 300             // 선택적. 기본 300 (10~1800 범위)
}

// 출력 — 사용자 채택 시
{
  "picked_asset_id": 42,
  "picked_at": 1747512000,
  "user_note": "왼쪽 것이 더 어두워서 좋아요"  // 사용자가 메모를 입력하면
}
```

에러 코드:

| 코드 | 의미 |
|---|---|
| `503_no_ui_available` | GAH 트레이 앱 미실행 또는 웹 포트 미기록 |
| `408_timeout` | `timeout_seconds` 내에 사용자 응답 없음 |
| `499_user_cancelled` | 사용자가 [✕ 거부] 클릭 |
| `503_too_many_pending` | 동시 요청 20건 한도 초과 (정상 흐름에서는 발생 안 함) |

### 6.9 M6 신규 1 도구 — `suggest_animation_frames`

스프라이트 시트 자산의 애니메이션 → 프레임 인덱스 매핑.

```jsonc
// input
{ "asset_id": 88, "animation": "walk" }

// output
{ "frame_indices": [0,1,2,3,4,5,6,7], "fps_hint": 11 }
```

사용 예시 (Claude Code 가 Unity AnimationClip 생성):

```csharp
// Unity Editor 스크립트
var clip = new AnimationClip { frameRate = 11 };
// frame_indices = [0,1,2,3,4,5,6,7]
// sprite_w=32, sprite_h=32 → 각 프레임의 Rect 계산
```

에러:
- `404_not_found` — asset 없음 / sprite_meta 없음 / animation 미존재 (응답 메시지에 available 목록 포함).
- `400_invalid_input` — `kind != "spritesheet"`.

## 7. `signature` 캐시 무효화 시나리오

`list_labels` 응답의 `signature` 는 활성 라벨 어휘의 sha256(16 hex). 사용자가 GUI 라벨 다이얼로그에서 라벨 추가/비활성화/description 편집을 하면 다음 호출의 `signature` 가 달라진다 — Claude Code 는 이를 캐시 미스 신호로 받아 라벨 카탈로그를 새로고침한다.

```
세션 1: list_labels() → signature=A123  → 캐시
세션 1: find_asset()  → 정상
사용자: GUI 에서 라벨 추가
세션 1: list_labels() → signature=B456  → 캐시 무효, 새로 받음
```

## 8. 에러 코드

| 코드 | 의미 | 발생 |
|---|---|---|
| `400_invalid_input` | Pydantic 검증 실패 또는 label_query 모호/혼합 표현 | 모든 도구 + M4 `find_asset(label_query=...)` / `save_search(name=중복)` |
| `404_not_found` | `asset_id`/`path`/`pack_id` 미존재, M4 saved_search 미존재 | get_asset 등 + M4 `delete_saved_search` / `run_saved_search` |
| `403_remote_disabled` | 비공식 경로 비활성 | scan_unity_asset_store_cache (remote_optin 미활성 시) |
| `408_timeout` | 사용자가 `timeout_seconds` 내에 응답하지 않음 | M5 `request_user_pick` |
| `499_user_cancelled` | 사용자가 [✕ 거부] 클릭 | M5 `request_user_pick` |
| `503_no_ui_available` | GAH 웹 UI 미실행 또는 포트 미기록 | M5 `request_user_pick` |
| `503_too_many_pending` | 동시 pending pick 20건 한도 초과 | M5 `request_user_pick` |
| `503_busy` | SQLite busy_timeout 초과 | 모든 write 도구 |

`request_rescan` 의 "워커 없음" 케이스는 에러가 아니라 OK + `warnings: ["no live worker; ..."]` — 트레이 GUI 가 다음에 부팅될 때 자동 픽업.

### 8.1 M4 `400_invalid_input` 의 새 변형

- **모호 라벨** — `label_query="dark"` 인데 `dark` 가 `sound_mood` + `sprite_palette` 양쪽에 등록 → 메시지: `"라벨 'dark' 모호 — 가능한 axis: sound_mood, sprite_palette"`. 사용자는 `sound_mood:dark` 같은 명시 형태로 재시도.
- **혼합 표현** — `label_query="(a AND b) OR c"` → v1 파서 한계. `"v1 한계 — 순수 AND 또는 순수 OR 표현만 지원합니다"`.

## 9. 통일성 가중치 튜닝

가중합 공식 (M4 — 6 채널 Config 디폴트):

```
final = 0.35·semantic + 0.10·keyword + 0.20·label_match + 0.20·consistency
      + 0.05·recency + 0.10·feedback
```

- **per-call 오버라이드** — `find_asset(consistency_weight_override=0.5)` / `label_match_weight_override=0.3` / **M4** `weight_feedback_override=0.2` 등으로 한 번의 검색만 튜닝.
- **Config 슬라이더** — `Config.weight_*` 6 채널 합 1.00 유지. 사용자가 GUI 우측 사이드패널 슬라이더로 조절 (M4: 양방향 바인딩).
- **`pinned_pack_id`** — `set_project_pin` 으로 강제 1순위. consistency 가중치를 무시하는 강한 선호.
- **`blocked_pack_ids`** — 검색 후보에서 완전 제외.

### 9.1 M4 — `diversity` 옵션

`find_asset(diversity=...)` 가 결과 순위에 다양성 보정을 적용. score_breakdown 의 채널 값은 변경 없음 — 순위만 영향.

| 값 | 의미 |
|---|---|
| `none` (default, M3 호환) | pure top-N |
| `mmr` | `mmr_i = λ·score_i - (1-λ)·max_sim_to_picked`, sim = 1 if same_pack else 0. λ 는 `diversity_lambda` (None → `Config.diversity_mmr_lambda=0.7`). |
| `round_robin` | 팩별 큐 → 라운드 교대 (top score 팩 순서). 한 팩만 후보면 score 폴백. |

### 9.2 M4 — `label_query` 문법

자연어 라벨 부울 — `find_asset(label_query=...)` 가 파서 후 labels_all/any/none 으로 분해.

```
expr     = or_expr
or_expr  = and_expr ('OR' and_expr)*
and_expr = not_expr (('AND' | implicit_and) not_expr)*
not_expr = 'NOT'? atom
atom     = '(' or_expr ')' | axis_label | bare_label | free_token
axis_label = IDENT ':' IDENT     -- ex) sound_mood:dark
bare_label = IDENT               -- LabelRegistry 자동 매칭
```

- 키워드 `AND`/`OR`/`NOT` 은 **대문자 전체 일치만**. `and` (소문자) 는 라벨 토큰으로 해석.
- bare label 이 여러 axis 에 등록되면 `400_invalid_input (모호)` — 명시 `axis:label` 로 재시도.
- v1 한계 — **순수 AND 또는 순수 OR 만 정확 매핑**. `(a AND b) OR c` 같은 혼합은 `400_invalid_input (UnsupportedExpression)`.
- 미지 토큰은 `free_text` 로 분리되어 semantic 쿼리에 합쳐짐.

### 9.3 M4 — `report_feedback` 페널티 학습

`report_feedback(query_id, asset_id, reason)` 호출이 누적될수록 같은 프로젝트의 다음 검색에서 해당 자산/팩이 밀린다.

- **reason 화이트리스트** — `Literal["negative", "positive", "irrelevant"]` (M4 부터).
- **signed weight** — Config 의 `feedback_*_weight` 값 (`negative=-0.5` / `positive=+0.3` / `irrelevant=-0.3`) 으로 변환되어 `feedback_records` 테이블에 누적.
- **asset-level** — 윈도우 (30일 기본) 내 같은 (project, asset) 의 weight 합이 `score_breakdown.feedback` 채널에 반영. clamp [-1, +1].
- **pack-level** — 같은 (project, pack) 에 negative 자산이 임계 (`feedback_pack_threshold=3` 기본) 이상이면 그 팩의 모든 자산에 추가 페널티 (`feedback_pack_penalty=-0.1`).
- **윈도우 밖** 행은 무시. **다른 project** 의 행은 영향 없음.
- `Config.weight_feedback=0` 시 효과 없음 (breakdown 키는 보존).

## 10. 표준 워크플로 (DESIGN §13.1 + M4 갱신)

1. **세션 시작** — `list_labels(with_description=true)` 1 회 → `signature` 와 함께 캐시.
2. **사용자 요청** — `suggest_packs(query, project_id, kind)` → 응답의 `samples[].thumbnail_path` (sprite) + `preview_blurb` 을 사용자에게 노출 → 팩 선택권 제공.
3. **사용자 선택** — `find_asset(query, project_id, label_query="axis:label AND ...", diversity="mmr", force_pack_id=<선택>, count=N)`.
4. **채택 직후** — Unity 프로젝트 `Assets/` 로 복사 후 **반드시** `record_asset_use(project_id, asset_id, query_id)`.
5. **거절 시** — `report_feedback(query_id, asset_id, reason="negative")` — **M4 부터 페널티 학습 활성**.
6. **재사용** — `save_search(project_id, name, ...)` 로 저장 → `run_saved_search(project_id, name)` 으로 한 번에 재호출.

`project_id` 는 매 호출에 동일. 통일성 + feedback 페널티가 같은 프로젝트를 같은 팩 쪽으로 수렴 + 한 번 거부한 자산을 다음 검색에서 밀어낸다.

## 11. 안티패턴

- `record_asset_use` 미호출 — 통일성 신호 누적 안 됨. 매 검색마다 팩이 흔들림.
- `project_id` 누락 — 글로벌 풀로 계산 → 통일성 + feedback 모두 0.
- `suggest_packs` 없이 매번 `find_asset` 단독 — 새 카테고리의 첫 채택 시 사용자에게 선택 기회를 빼앗음. 강한 굳음 상태나 명시 "알아서 골라줘" 일 때만 OK.
- 라벨 부울 필터를 자유 쿼리 안에 박기 (`"pixel art AND dark"`) — M3 까지는 안 됐지만 **M4 부터 `label_query` 필드로 가능**. 단 순수 AND / 순수 OR 만 (혼합 미지원).
- `report_feedback(reason="bogus")` — M4 부터 `Literal["negative","positive","irrelevant"]` 만 허용. 자유 문자열은 ValidationError.
- 같은 (project_id, name) 으로 `save_search` 두 번 — UNIQUE 충돌 → `400_invalid_input`. 덮어쓰기는 `delete_saved_search` 후 다시 `save_search`.
- `request_user_pick` 을 후보가 1개뿐일 때 호출 — 의미 없는 사용자 개입. 단일 후보는 Claude 가 직접 채택 후 `record_asset_use` 를 호출.
- `request_user_pick` 후 `record_asset_use` 를 수동 호출 — `project_id` 가 있으면 성공 시 자동 기록됨 (`source="claude_pick"`). 중복 기록하지 말 것.

## 12. M5 — `request_user_pick` Claude 의사 결정 흐름

### 12.1 언제 호출할까

다음 조건을 모두 충족할 때 `request_user_pick` 을 호출한다.

1. **후보가 2~10개** — `find_asset` 결과가 여러 개이고 점수 차가 작아 Claude 가 자신 없을 때.
2. **주관적 선택 요소가 있을 때** — 스타일, 색감, 분위기처럼 사용자 취향에 따라 달라지는 선택.
3. **GAH 웹 UI 가 열려 있을 때** — 트레이 앱이 실행 중이고 `web.port` 파일이 존재해야 한다.
4. **`project_id` 를 알고 있을 때** (권장) — 성공 시 `record_asset_use(source="claude_pick")` 가 자동으로 호출되어 통일성 신호를 쌓는다.

### 12.2 언제 호출하지 말까

- 후보가 1개뿐인 경우 — Claude 가 직접 채택.
- 모든 후보가 동일하게 잘 맞는 경우 — 첫 번째 후보를 채택.
- 사용자가 "알아서 골라줘" 처럼 자율 선택을 허락한 경우.
- `project_id` 를 모르는 경우 — 자동 기록이 안 되므로 직접 `record_asset_use` 를 호출해야 하는 부담이 생긴다.

### 12.3 호출 후 UI 동작

GAH 웹 UI 의 라이브러리 페이지 상단에 **보라색 줄무늬 카드 그룹** 이 나타난다. 각 카드에는 후보 에셋 이름, 팩, 크기, 썸네일이 표시된다.

- 사용자가 [채택] 버튼 클릭 → MCP 에 `picked_asset_id` 반환 → Claude 는 선택된 에셋을 안내하고 마무리.
- 사용자가 [✕ 거부] 클릭 → `499_user_cancelled` → Claude 는 다른 후보 세트로 재검색하거나 자동 선택으로 폴백.

트레이 아이콘 툴팁에는 **"Game Asset Helper — Claude 요청 N건"** 이 표시되어 사용자가 대기 중인 요청 수를 알 수 있다.

### 12.4 실패 시나리오별 폴백 전략

| 에러 코드 | 원인 | 권장 폴백 |
|---|---|---|
| `503_no_ui_available` | GAH 트레이 앱 미실행 또는 포트 파일 없음 | 자동 top-1 픽 + 사용자에게 GAH 앱 실행 안내 |
| `408_timeout` | 5분(`timeout_seconds`) 내 응답 없음 | 자동 top-1 픽 또는 "시간이 지났어요, 나중에 다시 시도하세요" 안내 |
| `499_user_cancelled` | 사용자 명시 거부 | 나머지 후보에서 재시도 또는 쿼리 변경 후 재검색 |
| `503_too_many_pending` | 동시 20건 한도 초과 | 잠시 후 재시도 (정상 단일 사용 환경에서는 사실상 발생하지 않음) |

## 13. M7 신규 2 도구 — Unity Asset Store 탐색

M7에서 MCP 18 → **20 도구**로 확장됐다. 핵심 원칙: **임포트(파일 복사)는 사용자가 웹 UI에서 직접 수행** — MCP 도구는 탐색과 안내만 담당한다.

### 13.1 `scan_unity_asset_store_cache` (도구 #19)

Unity Asset Store 캐시 디렉터리를 스캔해 `unity_imports` 테이블을 갱신한다.

```jsonc
// input
{
  "force": false,
  "filter": {
    "publisher_glob": "Kenney*",
    "asset_name_glob": "*platformer*"
  }
}

// output
{
  "scanned": 132,
  "new": 4,
  "updated": 1,
  "unchanged": 127,
  "removed": 0,
  "cache_path": "C:/Users/.../Asset Store-5.x",
  "warnings": []
}
```

에러:
- `404_not_found` — 캐시 경로를 찾을 수 없음 (사용자에게 Unity 설치 여부/경로 확인 안내).
- `403_remote_disabled` — remote_optin 미활성화 상태에서 remote 스캔 시도.

### 13.2 `list_unity_packages` (도구 #20)

`unity_imports` 테이블을 조회해 패키지 목록과 `import_url` 을 돌려준다.

```jsonc
// input
{
  "state": "discovered",
  "filter": { "asset_name_glob": "*character*" },
  "include_preview": true,
  "offset": 0,
  "limit": 20
}

// output
{
  "total": 5,
  "items": [
    {
      "id": 7,
      "asset_name": "Kenney Character Pack",
      "publisher": "Kenney",
      "import_state": "discovered",
      "package_size": 2097152,
      "preview_asset_count": 45,
      "preview_image_count": 42,
      "preview_sound_count": 3,
      "import_url": "http://localhost:37520/unity-asset-store"
    }
  ]
}
```

`import_url` 은 웹 UI의 Unity Asset Store 페이지 URL이다. Claude Code는 이 URL을 사용자에게 안내해 임포트 여부를 결정하게 한다.

### 13.3 Claude Code 워크플로 예시 — "Unity 에셋 보유 안내"

```
사용자: "내 Unity 에셋 중에 캐릭터 있어?"
Claude:
  1. scan_unity_asset_store_cache() — 캐시 재스캔 (빠름, 임포트 없음)
  2. list_unity_packages(state="discovered", filter={asset_name_glob: "*character*"})
     → 발견된 패키지들의 asset_name, publisher, preview 카운트 확인
  3. 결과를 사용자에게 안내:
     "Kenney Character Pack (42 이미지, 3 사운드)를 발견했어요.
      아직 GAH 라이브러리에 임포트되지 않았습니다.
      임포트하려면 이 링크를 열어 '임포트' 버튼을 클릭하세요:
      http://localhost:37520/unity-asset-store"
  4. 사용자가 웹 UI에서 임포트 완료 후:
     find_asset("character sprite", project_id="...", kind="sprite")
     → 방금 임포트된 팩의 에셋이 검색 결과에 포함됨
```

임포트 완료 여부는 `list_unity_packages(state="imported")` 로 확인할 수 있다.
