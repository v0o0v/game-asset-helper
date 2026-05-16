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
| M1 — 워처 + Pack Manager + DB | 다음 | — | — | watchdog·pack_manager·SQLite 스키마(packs/assets/tags) |
| M2 — 분석 파이프라인 | 대기 | — | — | Pillow·librosa·Ollama 클라이언트·임베딩 |
| M3 — 검색 + 통일성 + MCP | 대기 | — | — | FTS5·코사인·MCP stdio·suggest_packs·find_asset |
| M4 — 시트 분석 + 애니메이션 | 대기 | — | — | 격자 자동 분할·suggest_animation_frames |
| M5 — Unity Asset Store 임포트 | 대기 | — | — | .unitypackage 파서·캐시 스캐너 |
| M6 — GUI 마감 + 패키징 | 대기 | — | — | 라이브러리/팩/프로젝트/설정 탭·PyInstaller |

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
