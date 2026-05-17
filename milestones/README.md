# Milestones

이 디렉터리는 마일스톤(M0 ~ M6)마다 **3종 세트** 문서를 둔다.

```
M{N}_plan.md          # 구현 계획
M{N}_todo.md          # TDD 순서 체크리스트
M{N}_verification.md  # 자동/수동 검증 결과
```

## 사이클 (반드시 순서대로)

```
1. plan.md       — 목표·산출물·작업 단위·테스트 전략·검증 기준
   ↓
2. todo.md       — plan을 TDD 순서로 펴낸 체크리스트
   ↓
3. tests/ 작성   — 실패하는 테스트(red phase) 먼저, 한 번 돌려 모두 fail 확인
   ↓
4. src/ 구현     — 테스트가 통과(green phase)하도록 모듈 작성
   ↓
5. verification.md — pytest 결과 + 사용자 수동 검증 + 알려진 한계
```

코드 먼저 쓰고 테스트를 끼워 맞추지 않는다. plan/todo를 건너뛰고 바로 구현하지 않는다.

## 마일스톤 진행 상태

| 마일스톤 | 상태 | 자동 테스트 | 수동 검증 | 산출물 |
|---|---|---|---|---|
| [M0 — 뼈대](./M0_plan.md) | ✅ 완료 | 18/18 | ✅ 트레이·단일 인스턴스 | config·logging·single_instance·tray 셸·CLI |
| [M1 — 워처 + Pack Manager + DB](./M1_plan.md) | ✅ 완료 | 45/45 (전체 67/67) | 항목 정리 (수동 시나리오는 `M1_verification.md` §3) + 트레이 아이콘/더블클릭 폴리시 4 테스트 추가 | watchdog 어댑터+디바운서·매니페스트/벤더 휴리스틱·SQLite 4테이블·부팅 풀스캔·GUI 팩/라이브러리 탭 |
| [M2 — 분석 파이프라인 + CLIP](./M2_plan.md) | ✅ 완료 | 134/134 (전체 204/204, `clip_integration` 2 옵트인 제외) | 수동 시나리오는 `M2_verification.md` §3 | Pillow·numpy 기술 특성·librosa+soundfile·Ollama 클라이언트(OpenAI 호환+네이티브 폴백)·`nomic-embed-text`·CLIP zero-shot 라벨러·24축 ≈ 316 라벨 시드+`LabelRegistry`+라벨 관리 다이얼로그·분석 큐+ETA 상태바 |
| [M2.1 — 분석 큐 병렬화 패치](./M2.1_plan.md) | ✅ 완료 | 16/16 (전체 221/221, `clip_integration` 2 옵트인 제외) | 수동 시나리오는 `M2.1_verification.md` §3 | 동시성 1→3, Ollama semaphore(parallel=2), CLIP threading.Lock, SQLite write_lock+busy_timeout, GUI 250ms 디바운스 |
| [M3 — 검색 백엔드 + 통일성 + MCP](./M3_plan.md) | ✅ 완료 | 112/112 (전체 333/333, `clip_integration` 2 + `mcp_integration` 2 옵트인 제외) | 수동 시나리오는 `M3_verification.md` §4 (GUI 검색 박스 1 항목, 검증 중 발견된 `EmbeddingEncoder.decode_vector` 인터페이스 갭 fix + 회귀 가드 2 §3.6 참고) | HybridSearcher 가중합 0.40/0.15/0.20/0.20/0.05·ConsistencyScorer §4.6 표·UsageTracker·MCP stdio 12 도구 (mcp 1.27)·GUI 검색 박스·`docs/MCP_USAGE_GUIDE.md` 본격화 |
| M4 — 검색 UX 풍부화 (1.5주) | 다음 | — | — | 자연어 라벨 부울 파서·다축 필터 칩·가중치 슬라이더·저장된 검색·suggest_packs samples 풍부화 |
| M5 — 시트 분석 + 애니메이션 (1주) | 대기 | — | — | 격자 자동 분할·suggest_animation_frames |
| M6 — Unity Asset Store 임포트 (1주) | 대기 | — | — | .unitypackage 파서·캐시 스캐너 |
| M7 — GUI 마감 + 패키징 (1주) | 대기 | — | — | 상세/설정/프로젝트 탭·Qt i18n·PyInstaller |

## 새 마일스톤 시작 방법

`M{N-1}_plan.md` 의 구조를 그대로 본떠 `M{N}_plan.md` 를 쓴다. 절(節) 구성:

1. **목표** — 이 마일스톤이 끝나면 무엇이 가능해지는가
2. **산출물** — 만들/수정할 파일 목록과 책임
3. **작업 단위와 책임** — 각 모듈의 책임·입출력·오류 처리
4. **외부 의존성** — 새로 추가될 패키지
5. **테스트 전략** — 단위 테스트 목록과 검증 기준
6. **위험 요소와 완화**
7. **다음 마일스톤 인계점**

그 다음 `M{N}_todo.md` 를 작성한다. plan의 "테스트 전략"을 그대로 체크리스트로 펴면 된다.

마지막 단계인 `M{N}_verification.md` 는 마일스톤이 끝났을 때 작성. 다음 내용을 포함:

1. **자동 검증 결과** — `pytest -v` 출력 (전체 또는 해당 마일스톤 테스트만)
2. **검증 환경의 한계** — 샌드박스에서 못 본 항목
3. **사용자 측 수동 검증 항목** — PowerShell 명령 한 줄씩

`HANDOFF.md` 의 §2 "검증된 사실"과 §1 "한 줄 요약", §5 "M{N+1} 시작 절차" 도 함께 갱신한다.

## 마일스톤 사이의 인계

마일스톤 하나를 마칠 때마다 [`../HANDOFF.md`](../HANDOFF.md) 를 업데이트하고, [`../CLAUDE.md`](../CLAUDE.md) §2(진행 현황)와 §8(다음 작업)도 갱신한다. 이렇게 해야 새 Claude 세션이 첫 컨텍스트만 읽고도 어디서부터 이어갈지 안다.
