# 마일스톤 전체 로드맵

이 파일은 [CLAUDE.md](../CLAUDE.md) §8.3 에서 분리된 **전체 마일스톤 정렬 + future 후보**.  
완료 마일스톤 상세는 [`HISTORY.md`](./HISTORY.md).

| # | 이름 | 상태 |
|---:|---|---|
| M0~M8 | v1 (뼈대 ~ 패키징 + i18n) | ✅ 완료 (main 머지) — [HISTORY.md](./HISTORY.md) |
| M9 | 코드 서명 + 자동 업데이트 | ⚠️ path pivot (feat/m9 deleted, spec/plan 만 보존) |
| M10 | PyPI 배포 + AssetCacheMCP rename | ✅ (PR #11 + #12 머지) |
| v0.1.1 | yagni-clean + 첫 Trusted Publishing OIDC | ✅ ([PR #14](https://github.com/v0o0v/assetcache-mcp/pull/14)) |
| v0.1.2 | PyPI 페이지 정직성 patch | ✅ ([PR #15](https://github.com/v0o0v/assetcache-mcp/pull/15)) |
| 로드맵 brainstorm | M11~M18 design ([roadmap-design.md](../docs/superpowers/specs/2026-05-20-roadmap-design.md)) | ✅ (main `b3f8fe8`) |
| **M11** | Multi-backend LLM Architecture | ✅ v0.2.0 ([PR #16](https://github.com/v0o0v/assetcache-mcp/pull/16) `f68ef88`) |
| **M11.1** | Gemini Batch API + /analyzing dashboard | ✅ v0.2.1 ([PR #17](https://github.com/v0o0v/assetcache-mcp/pull/17) `782a047`) |
| **v0.2.x patches** | batch persist 보강 (label/meta/spritesheet) | ✅ ([PR #18](https://github.com/v0o0v/assetcache-mcp/pull/18) `12ebc42`, 회귀 1490) |
| **M11.2** | Batch Spritesheet Modality (`chat_spritesheet` 신설) | ✅ ([PR #19](https://github.com/v0o0v/assetcache-mcp/pull/19) main `d34f1dd`, +38 신규, 회귀 1528) |
| **M11.3** | Detection Cache + 부수 patch 4건 | ✅ ([PR #20](https://github.com/v0o0v/assetcache-mcp/pull/20) main `7ad0f3d`, +30 신규, 회귀 1559, [v0.2.2 publish](https://pypi.org/project/assetcache-mcp/0.2.2/) 완료) |
| **M11.4** | grid_detect 강화 + LLM 분류 정확도 (v0.2.3 candidate) | ✅ ([PR #21](https://github.com/v0o0v/assetcache-mcp/pull/21) main `7794d48`, +33 신규, 회귀 1592) — publish 보류 |
| **M11.5** | LIVE validation + acceptable set strict (v0.2.4 candidate) | ✅ ([PR #23](https://github.com/v0o0v/assetcache-mcp/pull/23) main `ed47403` + [PR #24](https://github.com/v0o0v/assetcache-mcp/pull/24) `1be53ae` docs, 회귀 1592, 옵트인 strict 2) — publish 보류 |
| **M11.6** | BATCH_SPRITESHEET_PROMPT palette + 'other' fallback 정리 (v0.2.5 candidate) | ✅ ([PR #26](https://github.com/v0o0v/assetcache-mcp/pull/26) main `da4f169`, +5 신규 + 2 옵트인, 회귀 1597) — publish 보류 |
| **M11.7** | mood OPTIONAL + category 별 mood 차단 (v0.2.6 candidate) | ✅ ([PR #27](https://github.com/v0o0v/assetcache-mcp/pull/27) main `04c205e`, +4 신규 + 2 옵트인, 회귀 1601) — publish 보류 |
| **M11.8** | mood 시드 `neutral`/`minimalist` `is_enabled=0` 마이그 (v0.2.7 candidate) | 📋 spec/plan 작성됨, **다음 세션 implement** — ⚠️ palette.neutral 절대 유지 |
| M12 | C4 측정/학습/벤치마크 (6 backend 정확도) | 📋 미정 (M11 의존) |
| M13 | Mac/Linux 검증 | 📋 미정 (M11 의존) |
| M14 | MCP 원격 통신 (HTTP/SSE + 인증) | 📋 미정 |
| M15 | Unity Editor 통합 | 📋 미정 |
| M16 | C2 이미지/사운드 유사 검색 | 📋 미정 (M11 embedding) |
| M17 | 성능 (대량 라이브러리) | 📋 미정 |
| M18 | 분산 분석 | 📋 미정 (M14 필수) |

## 참고 DESIGN 섹션 매핑

- §3 — 아키텍처 전체
- §4.5 — MCP 20 도구
- §4.6 — ConsistencyScorer
- §4.8 — 트레이 + 웹 UI
- §4.9 — Unity Asset Store Importer (M7)
- §4.10 — 활성 프로젝트 / 프로젝트 페이지 (M7)
- §11 — 로드맵 (이 파일의 source)
- §14 — 외부 출처 정리
