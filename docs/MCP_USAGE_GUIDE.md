# MCP 활용 가이드

이 문서는 **Claude Code(또는 다른 MCP 클라이언트)가 GAH MCP 서버를 어떻게 사용하면 좋은지** 알려 주는 가이드. M3 가 MCP stdio 서버를 구현하면서 채워 졌다.

서버 진입:

```powershell
python -m gah --mcp
```

→ JSON-RPC over stdio. Claude Code 는 이 명령을 child process 로 spawn 하고 `tools/list` 로 12 개 도구를 발견한다.

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
- `report_feedback(query_id, asset_id, reason)` — 페널티 학습 입력 (v1 로그만)
- `list_label_axes()` — 24 축 목록

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
| `400_invalid_input` | Pydantic 검증 실패 | 모든 도구 입력 단계 |
| `404_not_found` | `asset_id`/`path`/`pack_id` 미존재 | get_asset 등 |
| `403_remote_disabled` | 비공식 경로 비활성 (M6) | sync_unity_asset_store |
| `503_busy` | SQLite busy_timeout 초과 | 모든 write 도구 |

`request_rescan` 의 "워커 없음" 케이스는 에러가 아니라 OK + `warnings: ["no live worker; ..."]` — 트레이 GUI 가 다음에 부팅될 때 자동 픽업.

## 9. 통일성 가중치 튜닝

가중합 공식 (Config 디폴트):

```
final = 0.40·semantic + 0.15·keyword + 0.20·label_match + 0.20·consistency + 0.05·recency
```

- **per-call 오버라이드** — `find_asset(consistency_weight_override=0.5)` / `label_match_weight_override=0.3` 으로 한 번의 검색만 튜닝.
- **Config 슬라이더** — `Config.weight_*` 5 채널 합 1.00 유지. 사용자가 GUI 설정에서 조절 (M4 가 슬라이더 추가).
- **`pinned_pack_id`** — `set_project_pin` 으로 강제 1순위. consistency 가중치를 무시하는 강한 선호.
- **`blocked_pack_ids`** — 검색 후보에서 완전 제외.

## 10. 표준 워크플로 (DESIGN §13.1)

1. **세션 시작** — `list_labels(with_description=true)` 1 회 → `signature` 와 함께 캐시.
2. **사용자 요청** — `suggest_packs(query, project_id, kind)` → 사용자에게 팩 후보 제시.
3. **사용자 선택** — `find_asset(query, project_id, force_pack_id=<선택>, count=N)`.
4. **채택 직후** — Unity 프로젝트 `Assets/` 로 복사 후 **반드시** `record_asset_use(project_id, asset_id, query_id)`.
5. **거절 시** — `report_feedback(query_id, asset_id, reason)`.

`project_id` 는 매 호출에 동일. 통일성 가중치가 이력 기반으로 같은 프로젝트를 같은 팩 쪽으로 수렴시킨다.

## 11. 안티패턴

- `record_asset_use` 미호출 — 통일성 신호 누적 안 됨. 매 검색마다 팩이 흔들림.
- `project_id` 누락 — 글로벌 풀로 계산 → 통일성 0.
- `suggest_packs` 없이 매번 `find_asset` 단독 — 새 카테고리의 첫 채택 시 사용자에게 선택 기회를 빼앗음. 강한 굳음 상태나 명시 "알아서 골라줘" 일 때만 OK.
- 라벨 부울 필터를 자유 쿼리 안에 박기 (`"pixel art AND dark"`) — M3 의 `find_asset` 은 `labels_all`/`labels_any`/`labels_none` 구조화 입력만 받는다. 자연어 부울 파서는 M4 의 책임.
