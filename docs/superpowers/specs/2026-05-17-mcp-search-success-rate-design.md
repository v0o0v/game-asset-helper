# MCP 검색 성공률 설계

**한 줄 요약** — 콜드 스타트엔 dialog(top-N + axis-wise 비교 + 자연어 다듬기) 로 학습 신호(채택 + 거부 + axis 피드백)를 쌓고, GAH 의 ambiguity/lock_in 수치 + Claude LLM 판단이 함께 자율 모드 진입을 결정한다. 사용자가 원하면 콜드 스타트 시점에 프로필·팩 정책 한 줄로 시드 가속.

**작성일** — 2026-05-17  
**관련 마일스톤** — M3 (검색 백엔드 + 통일성 + MCP)  
**상위 문서** — `DESIGN.md` §4.3 / §4.5 / §4.6 / §6 / §13, `docs/MCP_USAGE_GUIDE.md`

---

## 1. 배경

M2 가 끝나 라벨 24축 ≈ 316개 시드, 자기 기술 라벨 description, `label_catalog_signature`, `searchable.for_fts/for_embed` 분리, 분석 큐가 모두 갖춰진 상태다. M3 에선 이 데이터 위에 검색 백엔드와 MCP 도구를 올린다.

GAH 의 핵심 가치는 *Claude Code 가 사용자 자연어를 받아 적합한 에셋을 자동으로 찾아주는 것*. 그러나 다음 어려움이 동시에 존재한다.

- 자연어 → 라벨 매핑 손실 (의미적 미스매치)
- 콜드 스타트(이력 0건)에서 통일성 가중치가 무력
- 한 프로젝트가 점차 굳어 가는 통일성 누적이 자동화돼야 함
- 사용자가 "이 팩만 쓰겠다" 같은 강한 의도를 가질 수 있음
- Claude 의 LLM 추론은 비결정적 — 단순히 도구만 노출하면 일관성 깨짐

본 spec 은 이 어려움들을 두 레이어(GAH 결정적 코드 + Claude LLM 추론) 의 책임 경계로 풀고, 모드 전이 상태 머신과 학습 신호 흐름으로 정리한다.

## 2. 합의된 5개 결정사항

| # | 결정 |
|---|---|
| Q1 | 사용 시나리오 = 콜드 (c) dialog → 점진 (d) 자율 그라데이션 |
| Q2 | 모호함 신호 = GAH 수치(ambiguity/lock_in) + Claude LLM 판단 둘 다 |
| Q3 | dialog 모드 형태 = top-N 리스트 + axis-wise 비교 표 + 자연어 다듬기 혼합 |
| Q4 | 학습 신호 = 채택 + 명시·암묵 거부 + axis 별 자연어 피드백 전부 |
| Q5 | 콜드 스타트 = 사용자 명시 프로필 + 첫 N 라운드 강제 dialog 둘 다 |
| Q5b | 팩 범위 정책(allowed/blocked/pinned) 도 콜드 스타트에서 명시 가능 |

구현 방식은 **C. 하이브리드** — GAH 가 결정적 신호·저장·필터, Claude 가 LLM 자연어 처리·모드 결정·표현 생성.

## 3. 아키텍처 + 책임 경계

```
 ┌───────────────────────────────┐
 │  Claude Code (MCP client)     │   ── LLM 추론 ──
 │  · 자연어 → MCP 인자 분해      │
 │  · 자연어 다듬기 → axis 신호    │
 │  · 모드 결정 (dialog vs auto)  │
 │  · 사용자 표현 생성             │
 └──────────────┬────────────────┘
                │   MCP tools (JSON in/out)
 ┌──────────────▼────────────────┐
 │  GAH MCP server (stdio + SSE) │   ── 결정적 코드 ──
 │  · find_asset 검색 + 가중합    │
 │  · differentiating_axes 추출   │
 │  · ambiguity / lock_in 수치    │
 │  · 학습 신호 영속 저장          │
 │  · 통일성 가중치 갱신           │
 │  · 팩 정책 하드 필터            │
 └──────────────┬────────────────┘
                │
 ┌──────────────▼────────────────┐
 │  SQLite (assets / labels /     │
 │  usage / rejection /            │
 │  axis_preference / projects)    │
 └───────────────────────────────┘
```

**책임 분할 규칙**: *결정적 코드로 표현 가능한 건 GAH 가 한다. LLM 추론이 필요한 건 Claude 가 한다.*

| 영역 | GAH 책임 | Claude 책임 |
|---|---|---|
| 검색 정확도 | FTS5 + 코사인 + 라벨 점수 + 통일성 가중합 | — |
| 후보 차이 추출 | `differentiating_axes` 결정적 추출 | — |
| 모호함 신호 | `ambiguity_score`, `lock_in_score`, `recommended_mode` 계산 | 세션 컨텍스트와 종합해 최종 모드 결정 |
| 학습 신호 저장 | `asset_usage` / `asset_rejection` / `axis_preference` 영속 | 자연어 → 도구 호출로 변환 |
| 자연어 → axis | — | `"좀 더 어둡게"` → `axis="mood", suppress=["bright","light"]` |
| 팩 정책 | DB 저장 + 검색 시 하드 필터 | 사용자 자연어를 `set_project_pack_policy` 호출로 변환 |
| 사용자 표현 | — | 후보 표·비교 표·사후 통보 메시지 작성 |

**안전망**: Claude 가 모드 결정을 잘못해도 GAH 가 `recommended_mode` 를 응답에 같이 실어 줘 그대로 따르면 안전.

## 4. 데이터 모델 + MCP 도구 시그니처

### 4.1 SQLite 신규 / 확장 테이블

DESIGN §5.1 의 `projects` / `asset_usage` / `search_queries` 위에 다음 추가:

```sql
-- 확장: 콜드 스타트 명시 프로필 + 팩 정책 컬럼
CREATE TABLE projects (
  id              INTEGER PRIMARY KEY,
  external_id     TEXT NOT NULL UNIQUE,
  display_name    TEXT,
  first_seen      INTEGER NOT NULL,
  last_seen       INTEGER NOT NULL,
  pinned_pack_id  INTEGER REFERENCES packs(id) ON DELETE SET NULL,
  blocked_packs   TEXT,                  -- JSON array of pack_id
  allowed_pack_ids TEXT,                 -- JSON array, NULL=무제한 (신규)
  style_hint      TEXT,                  -- 'pixel_art' 같은 시드 라벨 (신규)
  domain_hint     TEXT,                  -- 'fantasy' 등 (신규)
  mood_hint       TEXT,                  -- 'dark' 등 (신규)
  profile_set_at  INTEGER                -- NULL=미명시 (신규)
);

CREATE TABLE asset_usage (
  id          INTEGER PRIMARY KEY,
  project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  asset_id    INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
  pack_id     INTEGER NOT NULL,
  used_at     INTEGER NOT NULL,
  source      TEXT NOT NULL,             -- 'explicit'|'implicit_top1'|'manual'
  query_id    TEXT,
  context     TEXT
);
CREATE INDEX idx_usage_project ON asset_usage(project_id, used_at);
CREATE INDEX idx_usage_pack    ON asset_usage(project_id, pack_id);

-- 신규: 거부 신호 (Q4)
CREATE TABLE asset_rejection (
  id          INTEGER PRIMARY KEY,
  project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  asset_id    INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
  query_id    TEXT,
  rejected_at INTEGER NOT NULL,
  reason      TEXT                       -- 'implicit_other_chosen'|'explicit'|'changed_later'
);
CREATE INDEX idx_rejection_project ON asset_rejection(project_id, rejected_at);

-- 신규: axis 별 누적 가중치 (Q4)
CREATE TABLE axis_preference (
  project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  axis        TEXT NOT NULL,             -- 24축 중 하나
  label       TEXT NOT NULL,
  delta       REAL NOT NULL,             -- 양수 boost / 음수 suppress (누적)
  updated_at  INTEGER NOT NULL,
  PRIMARY KEY (project_id, axis, label)
);

CREATE TABLE search_queries (
  id           TEXT PRIMARY KEY,         -- 'q_2026_05_17_001' 형식
  project_id   INTEGER REFERENCES projects(id) ON DELETE CASCADE,
  query_text   TEXT NOT NULL,
  results_json TEXT NOT NULL,
  ambiguity    REAL,
  lock_in      REAL,
  recommended_mode TEXT,
  created_at   INTEGER NOT NULL
);
```

### 4.2 팩 정책 세 컬럼의 평가 순서

`pinned_pack_id` > `allowed_pack_ids` > `blocked_packs`. 평가:

1. `pinned_pack_id` 가 NULL 이 아니면 → 검색 결과는 그 팩 안의 에셋만.
2. 그렇지 않으면 `allowed_pack_ids` 가 NULL 이 아니고 비어 있지 않으면 → 그 배열 안의 팩들로만.
3. 그 위에 `blocked_packs` 의 팩들을 제외.
4. 모두 비어 있으면 전체 라이브러리.

세 컬럼은 *하드 필터* — 통일성 가중치(소프트)와 별개. AUTO 모드여도 정책은 깨지지 않는다.

### 4.3 MCP 도구 — 신규 4개 + `find_asset` 확장

**신규**

```jsonc
// set_project_profile  — 콜드 스타트 명시 입력 (Q5)
input  : { "project_id", "style_hint"?, "domain_hint"?, "mood_hint"? }
output : { "ok": true, "profile_set_at": <epoch> }
// 동작: 세 hint 가 들어오면 axis_preference 에 delta=+0.15 로 시드.
// 자동 학습 클램프 ±0.3 의 절반 — 잘못 입력해도 사용 누적이 덮어쓸 여지를 둠.

// record_asset_rejection  — 후보 거부 (Q4)
input  : { "project_id", "asset_ids": [int], "query_id"?, "reason" }
output : { "ok": true, "rejection_ids": [int] }

// report_axis_preference  — axis 별 boost/suppress (Q4)
input  : { "project_id", "axis", "boost": [str], "suppress": [str] }
output : { "ok": true }
// 동작: 각 label 에 대해 delta ±0.5 누적, 클램프 [-0.3, +0.3] (소프트 가중)

// set_project_pack_policy  — 팩 정책 (Q5b)
input  : {
  "project_id",
  "pinned_pack_id"?,        // null 로 보내면 해제
  "allowed_pack_ids"?,      // null 로 보내면 해제, [] 면 모든 팩 차단(권장 X)
  "blocked_pack_ids"?       // null 로 보내면 해제
}
output : { "ok": true }
// 호환: 기존 set_project_pin(pinned_pack_id) 도 alias 로 유지
```

**`find_asset` 입력**

```jsonc
{
  "query": "전투 시 깔릴 빠르고 어두운 오케스트라 BGM",
  "kind": "sound",
  "count": 5,
  "project_id": "D:/Unity/MyGame",
  "labels_any":  [{"axis":"sound_mood","label":"dark"}],
  "labels_all":  [{"axis":"sound_category","label":"bgm"}],
  "labels_none": [],
  "filters": { "max_duration_ms": 60000, "loopable": true },
  // 한 번성 오버라이드 — 프로젝트 정책 위에 즉시 덧붙임
  "prefer_pack_id": null,
  "force_pack_id":  null,
  "exclude_pack_ids": []
}
```

**`find_asset` 응답** (M3 전체)

```jsonc
{
  "query_id": "q_2026_05_17_001",
  "results": [
    {
      "asset_id": 142, "pack_id": 7, "path": "...",
      "score": 0.87,
      "score_breakdown": {
        "semantic": 0.41, "keyword": 0.18,
        "label_match": 0.18, "consistency": 0.10
      },
      "matched_labels": [
        {"axis":"sound_mood","label":"dark","source":"gemma","score":0.78}
      ],
      "why": "...",
      "preview_blurb": "...",
      "thumbnail_path": null
    }
  ],
  // 모드 결정 신호
  "ambiguity_score": 0.12,
  "lock_in_score": 0.61,
  "recommended_mode": "dialog",
  // dialog 비교 표
  "differentiating_axes": [
    { "axis": "sound_tempo",
      "values": [{"asset_id":142,"label":"medium"},
                  {"asset_id":143,"label":"fast"}] }
  ],
  // 팩 정책 메타
  "policy_filtered_out": 23,
  "policy_applied": {
    "pinned_pack_id": null,
    "allowed_pack_ids": [7, 11],
    "blocked_pack_ids": []
  }
}
```

### 4.4 결정적 알고리즘 (GAH 내부)

- **`ambiguity_score`** = `1 - (results[0].score - results[1].score) / max(results[0].score, 1e-6)`. 단일 결과면 0.
- **`lock_in_score`** = `max_pack_share × min(usage_count / 8, 1.0)` — 한 팩 사용 비율 × 누적 채택 saturation.
- **`recommended_mode`** = `"auto"` if `ambiguity < 0.20 AND lock_in > 0.50` else `"dialog"`. 두 임계는 `Config` 노출.
- **`differentiating_axes`** — 후보 N개 라벨 분포에서 axis 별 distinct label 수 ≥ 2 인 axis 만 → distinct 내림차순 → top-3. 결정적, O(N×24).
- **통일성 가중합** — DESIGN §4.6 공식 위에 axis_preference 항 추가:
  ```
  consistency_score = base_consistency
                    + clamp(sum(axis_preference.delta for asset.labels), -0.3, +0.3)
  ```

## 5. 모드 전이 상태 머신

```
사용자 자연어
    ▼
[S0. ANALYZE_QUERY]  Claude 가 query/labels/filters 분해
    │
    ├─ 첫 진입 && profile 없음 && usage=0 → [S0a. PROMPT_PROFILE]
    │                                       사용자 명시 답 → set_project_profile + set_project_pack_policy
    ▼
[S1. FIND_ASSET]
    ▼
[S1.5 POLICY_CHECK]
    │
    ├─ results 0 && policy_filtered_out > 0 → [S_POLICY_PROMPT]
    │     사용자 "응" → set_project_pack_policy(해제) → S1 재호출
    │     사용자 "아니" → 다듬기 라운드 (다른 자연어)
    ▼
[S2. DECIDE_MODE]  GAH recommended_mode + Claude LLM 판단
    │
    ├─ AUTO ───────────────────────────────────────────┐
    │   [S3a. APPLY_TOP1]  사용자에게 1줄 통보 + 채택  │
    │     사용자 다음 메시지:                            │
    │       · 새 요청      → record_asset_use(implicit_top1)
    │       · 거부 표현     → record_asset_rejection(changed_later)
    │                       + recently_explicit_rejected=True (1회 dialog 폴백)
    │
    └─ DIALOG
        [S3b. SHOW_CANDIDATES]  top-N + matched_labels + differentiating_axes 표
            사용자 응답:
              · 번호 선택      → [S4_PICK]
              · 자연어 다듬기  → [S4_REFINE]

[S4_PICK]
  · record_asset_use(asset_id, source="explicit")
  · record_asset_rejection(others, reason="implicit_other_chosen")

[S4_REFINE]
  · Claude axis 파싱
  · report_axis_preference(...)
  · S1 로 루프
```

### 5.1 Claude 의 모드 결정 로직 (시스템 프롬프트)

```python
def decide_mode(response, session, query):
    if response.recommended_mode == "dialog":   # GAH 안전망
        return DIALOG
    if session.recently_explicit_rejected:      # 1회 dialog 폴백
        return DIALOG
    if Claude_judges_info_too_thin(query):      # 자연어 1-2 단어
        return DIALOG
    return AUTO
```

### 5.2 AUTO 사후 통보 메시지 템플릿

```
"<pack>의 <path> 채택했습니다.
 (axis:label · axis:label · ..., 짧은 메트릭)
 다른 게 좋으면 알려 주세요."
```

## 6. Claude-side 가이드라인

### 6.1 MCP 서버 `instructions` 필드 (자동 송신)

GAH MCP 서버가 client 에게 자동 전달. 100~200 줄. 핵심 골자:

- 세션 부트스트랩: `list_label_axes` + `list_labels(with_description=true)` + `list_packs`, signature 캐싱
- 콜드 스타트 프롬프트 2단계 (스타일 + 팩 범위)
- 요청당 처리: query 분해 → `find_asset` → 모드 결정 → branch
- AUTO/DIALOG 각 사후 처리 매트릭스
- 자연어 → axis 매핑 표 (mood/tempo/genre 5~10 패턴)
- 자연어 → 팩 정책 매핑 표 (`"Kenney만"` / `"이 팩 말고"` / `"범위 풀어"` 등)
- `signature` 캐시 무효화 규약

### 6.2 자연어 → axis 매핑

| 사용자 자연어 | axis | boost | suppress |
|---|---|---|---|
| `"어둡게"` | `mood` | `[dark, ominous]` | `[bright, cheerful]` |
| `"밝게"` | `mood` | `[bright, cheerful]` | `[dark, ominous]` |
| `"빠르게"` | `sound_tempo` | `[fast, very_fast]` | `[slow, very_slow]` |
| `"느리게"` | `sound_tempo` | `[slow, very_slow]` | `[fast, very_fast]` |
| `"신스/일렉트로닉"` | `sound_genre` | `[electronic, synthwave]` | `[orchestral, classical]` |
| `"오케스트라"` | `sound_genre` | `[orchestral]` | `[electronic, synthwave]` |
| `"다른 분위기"` | `mood` | — | `[현재 결과 mood 라벨]` |

axis 확신이 없으면 사용자에게 되묻기 — silent 추측 금지.

### 6.3 자연어 → 팩 정책 매핑

| 사용자 자연어 | 도구 호출 |
|---|---|
| `"Kenney만 써"` | `set_project_pack_policy(allowed=[<kenney 모든 pack>])` |
| `"이 팩 말고"` | `set_project_pack_policy(blocked=[<현재 결과 pack>])` |
| `"Kaykit + Kenney 만"` | `set_project_pack_policy(allowed=[<두 벤더 pack 합>])` |
| `"범위 풀어 / 다 써"` | `set_project_pack_policy(pinned=null, allowed=null, blocked=null)` |
| `"이 팩 고정"` | `set_project_pack_policy(pinned=<현재 pack>)` |

### 6.4 콜드 스타트 부트스트랩 메시지 (Claude → 사용자)

```
1단계 (스타일):
  "이 프로젝트의 스타일을 한 줄로 알려 주세요.
   예: `pixel art, fantasy RPG, dark mood`
   모르면 `잘 모름`."

2단계 (팩 범위):
  "사용할 팩 범위가 정해져 있나요?
   예: `Kenney Platformer만`, `Kenney 시리즈만`, `전부 사용`."
```

답이 `잘 모름` / `전부` / 빈 답이면 해당 호출 skip — 무제한 + 자동 학습 트랙(Q5 b).

### 6.5 `docs/MCP_USAGE_GUIDE.md` 본격화

M2 의 stub 을 M3 끝에서 다음 내용으로 풀어쓴다:

- 실제 `find_asset` 응답 JSON 예시 — ambiguity 0.05/0.5/0.9 케이스 각각
- Cold-start (이력 0) → warm (이력 5) → locked (이력 20) 비교
- 자연어 다듬기 1회 vs 3회 라운드 비교
- `signature` 변경 시 캐시 무효화 흐름
- `score_breakdown` / `matched_labels` 읽는 법
- `policy_filtered_out` 시 사용자 안내 흐름

## 7. 테스트 / 검증 전략

### 7.1 GAH 결정적 단위 테스트 (M3 plan)

신규 60~70 케이스. 묶음:

```
test_search.py                  검색 가중합 + 응답 모양
test_mode_decision.py           ambiguity/lock_in/recommended_mode
test_differentiating_axes.py    distinct 추출 알고리즘
test_axis_preference.py         delta 누적·클램프·검색 영향
test_consistency.py             통일성 + axis_preference 통합
test_pack_policy.py             pinned/allowed/blocked 평가 순서, 호환성
test_mcp_tools_m3.py            신규 도구 4개 + find_asset 확장
test_mcp_server_stdio.py        stdio 서버 + instructions 송신
```

### 7.2 Claude 가이드라인 — 수동 시나리오 (M3 verification)

7개 시나리오. 사용자가 Claude Code 채팅 + `gah.log` + sqlite 로 검증:

1. **콜드 스타트 부트스트랩** — 새 project_id 첫 진입, Claude 2단계 질문, `set_project_profile` + `set_project_pack_policy` 호출
2. **DIALOG → 다듬기 라운드** — 자연어 다듬기 → `report_axis_preference` → 재검색 결과가 다름
3. **워밍업 → AUTO 도달** — 8~10회 채택 후 lock_in 상승, AUTO 진입
4. **AUTO 거부 → DIALOG 폴백** — `record_asset_rejection(changed_later)` + 다음 요청 1회 DIALOG
5. **signature 캐시 무효화** — 라벨 관리에서 추가/비활 후 signature 변경, Claude 가 `list_labels` 재호출
6. **콜드 스타트 "잘 모름"** — 명시 입력 skip 후 첫 N 라운드 강제 DIALOG
7. **팩 정책** — `"Kenney만 써"` → `set_project_pack_policy(allowed)`, 이후 검색이 해당 팩 안에서만, `policy_filtered_out > 0` 시 사용자 안내

### 7.3 메트릭 대시보드 (선택)

```sql
-- DIALOG vs AUTO 비율
SELECT recommended_mode, COUNT(*) FROM search_queries GROUP BY recommended_mode;

-- AUTO 모드 오판 비율
SELECT COUNT(*) FROM asset_rejection WHERE reason='changed_later';

-- 평균 자연어 다듬기 라운드 (같은 prefix query_id 묶기)
-- ... (정확 쿼리는 M3 끝에 풀어쓰기)
```

M3 verification 끝에 수동 sqlite 쿼리로 측정. GUI 노출은 M4 검토.

## 8. M2.1 동시성 패치와의 관계

M2.1 의 `Store.write_lock` 이 M3 신규 도구(`record_asset_use` / `record_asset_rejection` / `report_axis_preference` / `set_project_profile` / `set_project_pack_policy`) 도 자연스럽게 보호한다. M3 코드는 동시성을 의식할 필요 없음 — 그냥 store 메서드 호출하면 lock 이 처리. 이 디커플링이 M2.1 을 먼저 분리한 이유 중 하나.

## 9. 결정 보류 / 미래 검토

| 항목 | 현재 결정 | 미래 검토 시점 |
|---|---|---|
| 자연어 → axis 매핑 정확도 측정 | 시스템 프롬프트 가이드 + 수동 시나리오 | 사용자 피드백 누적 후 M4 |
| 메트릭 대시보드 GUI | sqlite 쿼리 (수동) | M4 검색 UX 풍부화에 통합 |
| 다국어 자연어 처리 | 영어/한국어 매핑 가이드 우선 | 다국어 사용 패턴 확인 후 |
| Cross-encoder rerank | 미도입 — 결정적 가중합으로 충분 가정 | 검색 품질 측정 후 검토 |
| 사용자 negative 피드백 학습 (axis_preference 감쇠) | 누적 만 — 시간에 따른 감쇠 없음 | 6개월 이상 사용 후 |
| AUTO 모드의 멀티스텝 (한 번에 N개 에셋 채택) | 단일 채택만 — 1 요청 = 1 에셋 | 사용자 요청 누적 후 |
| 라벨 어휘 영어 외 다국어 description | 영어 권장, 한국어 description 허용은 자유 | 다국어 라벨 추가 요청 시 |

## 10. 다음 단계

본 spec 이 확정되면 [`milestones/M3_plan.md`](../../../milestones/M3_plan.md) 작성으로 들어간다. plan 의 §3 작업 단위 + §5 테스트 전략은 본 spec 의 §4~§7 을 그대로 코드 모양으로 풀어쓰는 일.
