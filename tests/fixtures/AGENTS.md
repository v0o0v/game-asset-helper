<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-22 | Updated: 2026-05-22 -->

# fixtures

## Purpose
테스트용 결정론 fixture. 두 종류:
1. **conftest `fixture_dir` 가 lazy 생성하는 sprite/sound 파일** (`tiny_pixel_32.png`, `tiny_vector_256.png`, `transparent_alpha.png`, `short_sfx_1s.wav`, `medium_sfx_5s.wav`, `long_bgm_45s.wav`, `mel_sample.png`). 첫 pytest 실행 시 한 번 만들고 이후 재사용. **`.gitignore` 되며 `.gitkeep` 만 트래킹**.
2. **고정 fixture** — `sheets/` (spritesheet 정밀 검증용 사이드카 JSON) + `unity/` (Unity `.unitypackage` 동적 빌더 + 실 fixture).

레포 크기를 줄이고 머신 간 byte-identical 재현을 유지하기 위해 binary blob 대신 결정론 generator 를 쓴다.

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `sheets/` | spritesheet 검출/격자 추정 회귀용 PNG + JSON 사이드카 fixture. `scripts/make_complex_sheets.py` 로 일부 생성 |
| `unity/` | Unity `.unitypackage` 파서 회귀 — `__init__.py` + `make_unitypackage.py` (`tarfile.gzip` 으로 임의 패키지 동적 생성) |

## For AI Agents

### Working In This Directory
- **이 디렉터리의 PNG/WAV 는 commit 하지 않는다** — `.gitignore` 가 `.gitkeep` 만 트래킹. `tests/conftest.py._FIXTURE_BUILDERS` 가 첫 실행 시 빌드. 새 generator 추가 시 `_FIXTURE_BUILDERS` dict 에도 키 등록.
- **sheets/** 의 사이드카 JSON 은 검증 ground-truth — 수동 편집 가능. PNG 는 `scripts/make_complex_sheets.py` 로 재생성.
- **unity/make_unitypackage.py** — `tarfile.gzip` 으로 임의 GUID + asset path 조합의 `.unitypackage` 를 빌드. `unity_import` 회귀에서 fixture 별로 함수 호출.
- **재현성** — 모든 generator 는 `np.random.default_rng(seed=N)` 로 시드 고정. 시드 바꾸면 회귀 단언이 깨질 수 있으니 신중.

### Testing Requirements
- fixture 자체에는 테스트 없음. `tests/test_analyzer_*.py` / `tests/test_unity_*.py` 가 소비처.

### Common Patterns
- generator 함수는 항상 `(path: Path) -> None` 시그니처 — `_FIXTURE_BUILDERS` dict 가 동일하게 dispatch.
- 시드 값은 fixture 이름별로 다르게 (`seed=42`, `seed=7`, `seed=99`) — 같은 시드 재사용 시 우연한 일치로 회귀 false positive 위험.

## Dependencies

### Internal
- `tests/conftest.py` — `_FIXTURE_BUILDERS` + `fixture_dir` fixture.
- `src/assetcache/core/analyzer/` — fixture 소비자 (sprite/sound).
- `src/assetcache/core/unity_import/` — fixture 소비자.
- `scripts/make_complex_sheets.py` — sheets fixture 빌더.

### External
- numpy, Pillow, soundfile (결정론 generator).
- tarfile + gzip (Unity 패키지 빌더).

<!-- MANUAL: fixture PNG/WAV 가 commit 으로 새 나가지 않도록 .gitignore 확인 (.gitkeep 만 트래킹). -->
