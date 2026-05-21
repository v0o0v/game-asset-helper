# AssetCacheMCP 설계 문서

## 1. 개요

AssetCacheMCP(PyPI 패키지 `assetcache-mcp`, CLI `assetcache`. M10 이전 명칭: Game Asset Helper / `gah`)는 Unity 게임 개발 중 Claude Code(또는 다른 MCP 클라이언트)가 "필요한 에셋"을 자연어로 요청하면 로컬에 보관된 에셋 라이브러리에서 가장 적합한 것을 찾아 돌려주는 **MCP 서버 + 트레이 상주 데스크톱 앱**이다.

> **배포 (M10)** — 1차 채널은 **PyPI** (`pipx install assetcache-mcp` / `uv tool install assetcache-mcp`) 로 Windows + Mac + Linux 동시 지원. 2차 채널은 단일 `.exe` (PyInstaller `--onefile`) 로 GitHub Releases.

핵심 흐름은 다음과 같다.

1. 사용자가 **에셋 팩(asset pack) 폴더 자체를** `library/` 아래에 통째로 드롭한다. 예: `library/kenney_platformer_redux/`, `library/my_custom_sfx/`. 팩 내부 폴더 구조는 임의(스프라이트·사운드가 어느 깊이에 어떤 이름의 하위 폴더로 있어도 무방).
2. 백그라운드 워처가 새 팩과 그 안의 파일을 재귀로 감지하고, 파일 확장자·내용으로 종류(스프라이트/시트/사운드)를 판별해 메타데이터 추출 파이프라인에 넣는다.
3. 파이프라인은 기술적 특성(해상도, 길이, 채널 수 등)을 추출하고, Ollama로 실행 중인 **Gemma 4**(멀티모달, 이미지·오디오 입력 모두 지원) 모델에게 의미적 라벨(분위기, 카테고리, 가능한 애니메이션 종류 등)을 받아 SQLite에 저장한다. 팩 단위의 집계 메타(주요 스타일, 도미넌트 팔레트, 픽셀 아트 비율 등)도 함께 계산한다.
4. Claude Code는 두 단계로 에셋을 가져온다.
   - **(a) 팩 선택 단계** — `suggest_packs("스테이지 클리어 효과음, 짧고 경쾌한", project_id="...", kind="sound")`을 호출해 적합한 팩 후보 리스트(샘플 미리보기·라이선스·이 프로젝트의 사용 이력 포함)를 받는다. Claude Code는 이 리스트를 사용자에게 보여주고 어느 팩을 쓸지 선택하게 한다. 이미 이 프로젝트에서 굳어진 팩이 있다면 그 팩이 상단에 강조돼 올라온다.
   - **(b) 에셋 선택 단계** — 사용자가 팩을 고른 뒤(또는 명시 선택 없이 자동 진행), `find_asset(..., force_pack_id=<선택한 팩>)`으로 그 팩 안에서 구체 에셋 후보를 받는다. 사용자가 빠른 진행을 원해 팩 선택을 생략하면 `find_asset` 단독으로도 동작하며, 이때는 통일성 가중치만으로 단일 최적 결과를 돌려준다.
5. Claude Code가 에셋을 채택해 Unity 프로젝트에 복사하면 `record_asset_use`로 GAH에 통보해 이력이 누적된다. 이력은 이후 `suggest_packs` 결과의 정렬 가중치를 더 강하게 만든다.
6. 사용자는 트레이 아이콘에서 GUI를 열어 어떤 팩과 에셋이 등록됐는지, 메타데이터가 무엇인지, 분류가 맞는지 검토하고 수정할 수 있다.

> **모델 선택** — Google이 2026년 4월 2일에 공개한 **Gemma 4** 계열을 사용한다. 패밀리는 `E2B`, `E4B`, `26B A4B (MoE)`, `31B (Dense)` 네 가지이며, 본 프로젝트는 다음 두 모델을 활용한다.
> - **`gemma4:e4b`** — 이미지 + 오디오 입력을 모두 지원하는 엣지용 멀티모달 모델. 사용자 PC(소비자 GPU/CPU)에서 돌리는 게 목표이므로 기본값으로 채택. Ollama 라이브러리에서 `ollama pull gemma4:e4b` 로 받는다.
> - **`gemma4:e2b`** — VRAM이 부족한 환경의 폴백.
> 더 큰 26B/31B는 사용자 옵션으로 노출하되 기본은 아니다.
>
> Gemma 4의 오디오 입력은 conformer 기반 인코더로 ASR/이해를 직접 처리하며, 클립당 최대 30초, 단일 채널, 1초당 25 토큰을 사용한다. 따라서 30초가 넘는 BGM은 청크로 잘라서 보내거나 librosa로 대표 구간만 추출해 보내는 전략이 필요하다(§8.2 참고). 또한 2026-05 시점 기준 Ollama 런너에서 `gemma4:e4b` 오디오 추론 중 간헐적 GGML assertion 크래시가 보고돼 있다([ollama/ollama#15333](https://github.com/ollama/ollama/issues/15333)). 이에 대비해 오디오 분석은 항상 폴백 경로(librosa 기술 특성 + 멜 스펙트로그램 비전 입력)를 함께 갖추도록 설계한다.
>
> **백엔드 추상화** — 분석 클라이언트는 Ollama 의 `/api/chat` 만 호출하지 않고, OpenAI 호환 `/v1/chat/completions` 을 우선 시도해 LM Studio·llama-server 등 다른 백엔드로 교체 가능하게 둔다(§4.2.4 ADR). llama.cpp/llama-server 의 오디오 입력은 2026-04 시점 미구현이라 현재는 후보에서 빠지지만, 패치되면 base URL 한 줄로 옮길 수 있도록.


## 2. 목표 및 범위

### 2.1 In-scope (이번 프로젝트가 직접 책임지는 것)

- 윈도우즈에서 백그라운드로 동작하는 **트레이 상주 앱**
- 윈도우 시작 시 자동 실행 옵션
- 지정 폴더 감시 → 신규/변경/삭제 이벤트 처리, **팩 단위 인식** (top-level 하위 폴더 1개 = 1 팩)
- **Unity Asset Store 로컬 캐시 자동 임포트** — 사용자가 Unity Hub/Editor로 이미 받은 `.unitypackage` 파일을 추출해 AssetCacheMCP 라이브러리에 팩으로 자동 등록
- 2D 스프라이트(PNG/WebP 단일 이미지) 메타데이터 추출
- 2D 스프라이트 시트(여러 프레임이 격자로 배치된 PNG, 또는 Aseprite/TexturePacker JSON 동반) 분석
- 사운드(WAV/OGG/MP3) 길이·BPM·기본 분위기 분석
- Gemma 4(Ollama, `gemma4:e4b` 기본)로 의미 라벨링 (카테고리, 분위기 키워드, 가능한 애니메이션 등). 사운드는 네이티브 오디오 입력을 직접 사용.
- 팩 단위 집계 메타(스타일/팔레트/픽셀아트 비율) 산출
- **프로젝트별 사용 이력 추적과 통일성 가중 검색** — Claude Code가 `project_id`를 보내면, 그 프로젝트가 이미 채택한 팩의 에셋을 우선 추천
- 텍스트 임베딩 기반 검색
- MCP 서버(stdio + 선택적으로 SSE/HTTP)
- 에셋·메타데이터·팩을 보고 수정할 수 있는 GUI

### 2.2 Out-of-scope (이번 프로젝트가 책임지지 않는 것)

- Unity 에디터 플러그인으로의 **양방향** 통합 (Unity 안에서 직접 import하는 동작은 클라이언트인 Claude Code가 처리; v2에서 보조용 에디터 스크립트는 검토)
- Unity Asset Store의 **클라우드 라이선스 다운로드** — 공식 API가 없어 v1에서는 로컬 캐시만 사용. 비공식 publisher 패널 API 경유 다운로드는 옵트인 실험 기능으로만 제공(§4.9)
- 3D 모델·셰이더·머티리얼 분석 (구조상 확장 가능하지만 v1에는 미포함)
- 클라우드 동기화, 다중 사용자 공유 (v1은 단일 사용자·로컬 한정)
- 라이선스 자동 추적 (메타데이터 필드만 제공, 검증은 사용자 몫)


## 3. 시스템 아키텍처

### 3.1 컴포넌트 구성

> **M5 갱신 (2026-05-18)** — Qt 데스크톱 UI가 FastAPI 기반 로컬 웹 서버로 교체됐다. 트레이는 Qt로 유지되고, 사용자 UI는 시스템 기본 브라우저가 담당한다. MCP server → FastAPI HTTP loopback으로 `request_user_pick` 장기 폴링이 추가됐다.

```
+---------------------- AssetCacheMCP (Python) --------------------------+
|                                                                        |
|  +---------------+      +-----------------+      +------------------+  |
|  | Tray App      |<---->|  Core Service   |<---->|  MCP Server      |  |
|  | (PySide6 트레이|signal|  (asyncio)      | API  |  (stdio)         |  |
|  |  + TrayBridge)|      +--------+--------+      +--------+---------+  |
|  +-------+-------+               |                        |            |
|          |                       |               HTTP loopback         |
|          | spawn                 |               (request_user_pick)   |
|          v                       |                        |            |
|  +---------------+               |               +--------v---------+  |
|  | Web Server    |<--------------+               | FastAPI app      |  |
|  | (uvicorn      |  shared WebDeps (Store, Config)|  /library        |  |
|  |  별 스레드)   |               |               |  /packs           |  |
|  +-------+-------+               |               |  /labels/admin    |  |
|          |                       |               |  /sse/notifications|  |
|          | SSE push              |               |  /internal/pick   |  |
|          v                       |               +------------------+  |
|  [Browser: http://127.0.0.1:9874]|                                     |
|                                  |                                     |
|              +-------------------+--------------------+                |
|              |                   |                    |                |
|     +--------v-------+  +--------v---------+  +-------v-------+        |
|     | Folder Watcher |  | Asset Analyzer   |  | Search Engine |        |
|     | (watchdog)     |  | (Pillow/librosa  |  | (SQLite FTS5  |        |
|     |                |  |  + Ollama Gemma4)|  |  + embeddings)|        |
|     +--------+-------+  +--------+---------+  +-------+-------+        |
|              |                   |                    |                |
|              +-------------------+--------------------+                |
|                                  |                                     |
|                         +--------v---------+                           |
|                         | Metadata Store   |                           |
|                         | (SQLite, WAL)    |                           |
|                         +------------------+                           |
+------------------------------------------------------------------------+
                                  |
                                  | HTTP (localhost:11434)
                                  v
                         +------------------+
                         | Ollama (gemma4,  |
                         | nomic-embed-text)|
                         +------------------+
```

### 3.2 프로세스 모델

단일 프로세스(파이썬) 안에 다음이 공존한다.

- **Tray GUI 스레드** — PySide6의 `QApplication` 이벤트 루프. 트레이 아이콘만 담당 (M5에서 메인 윈도우 Qt 위젯 폐기). `TrayBridge(QObject)` 가 uvicorn 워커 스레드 → Qt main thread 로 시그널을 안전하게 디스패치한다.
- **Web Server 스레드** — `threading.Thread` 위에서 uvicorn이 FastAPI 앱을 실행. Qt main thread와 분리. 브라우저를 통해 사용자 UI를 제공한다. SSE(`/sse/notifications`)로 실시간 이벤트를 푸시한다.
- **Core asyncio 루프** — 별도의 `QThread`에서 `asyncio.run`. 워처 이벤트 처리, 분석 큐, MCP 서버를 모두 여기서 돌린다.
- **분석 워커 풀** — CPU·GPU 바운드 작업(이미지 디코딩, Ollama 호출)은 `concurrent.futures.ThreadPoolExecutor`로 오프로드한다.

MCP 클라이언트(Claude Code)와의 통신은 **stdio** 가 기본이다. Claude Code 설정 파일에 stdio 명령(`assetcache --mcp` 또는 콘솔 스크립트 `assetcache-mcp`)을 등록하면 자식 프로세스가 GUI 인스턴스의 DB를 lock-free로 읽도록 한다(WAL 모드). MCP 서버는 `request_user_pick` 도구 호출 시 `web.port` 파일에서 포트를 읽어 FastAPI의 `/internal/user-pick` 엔드포인트로 HTTP loopback 요청을 보낸다(§4.8).

**웹 서버 포트 관리**: `Config.web_port` (기본 9874) 부터 `web_port_max_attempts` (기본 10) 회 순서대로 빈 포트를 탐색해 바인딩한다. 바인딩 성공 포트 번호를 `%APPDATA%\AssetCacheMCP\web.port` 파일에 기록해 MCP stdio 프로세스와 공유한다.


## 4. 컴포넌트 상세

### 4.1 Folder Watcher & Pack Manager

라이브러리는 **팩(pack) 단위**로 관리한다. `library/` 바로 아래의 각 디렉터리가 1개의 팩이고, 팩 내부 구조는 자유다.

```
library/
├── kenney_platformer_redux/         <- 팩 1
│   ├── PNG/
│   │   ├── Characters/
│   │   └── Tiles/
│   ├── Sounds/
│   └── pack.json                    <- 선택적 매니페스트
├── kenney_ui_pack/                  <- 팩 2
└── my_custom_sfx/                   <- 팩 3
```

#### Folder Watcher
- 라이브러리: `watchdog`, 재귀 감시.
- 감시 대상: `%APPDATA%/AssetCacheMCP/library/`
- 동작
  - `on_created`/`modified`/`moved`/`deleted` 이벤트를 모두 받는다.
  - **이벤트 위치로 팩 식별**: 경로의 첫 번째 세그먼트가 팩 이름. 새 top-level 디렉터리가 생기면 `PackIntakeTask`를 큐에 넣어 팩 단위 인테이크(스캔 + 집계)를 먼저 수행하고, 그 후 개별 파일들을 `AssetTask`로 풀어낸다.
  - 디바운스: 압축 해제·복사 중에는 수십~수백 개의 이벤트가 몰리므로, 팩 루트 기준 2초 윈도우로 이벤트를 모아 한 번에 처리한다.
  - 부팅 직후 풀 리컨실: `library/` 의 현재 상태와 DB를 diff해 추가/삭제된 팩을 식별.
- 큐: `asyncio.Queue[PackIntakeTask | AssetTask]` — 인테이크 태스크가 먼저 처리되도록 우선순위 큐로 구현.

#### Pack Manager
- 팩 디렉터리를 발견하면 다음을 수행:
  1. **매니페스트 읽기** — 팩 루트의 `pack.json`(또는 `pack.toml`)이 있으면 파싱. 없으면 폴더명으로부터 추정. 매니페스트 스키마는 §5.3.
  2. **벤더 추정 휴리스틱** — 폴더명 패턴(`kenney_*`, `kaykit_*`, `craftpix_*`) + 매니페스트의 `author` 필드로 벤더 라벨 부여. 통일성 검색에서 같은 벤더 팩 간 약한 보너스를 줄 때 활용.
  3. **파일 인덱싱** — `**/*.{png,webp,wav,ogg,mp3}`를 재귀로 수집해 각 파일에 대해 `AssetTask` 생성. 파일 종류는 확장자 + 시그니처로 결정(시트 vs 단일 이미지는 분석기가 정함, §4.2.2).
  4. **팩 집계 메타 산출** — 모든 파일 분석이 끝나면 팩 레벨 메타(주 스타일, 도미넌트 팔레트, 픽셀아트 비율, 카테고리 분포, 평균 해상도/길이)를 계산해 `packs.aggregate_meta`에 저장. 이 값이 §4.7 통일성 스코어러의 입력이 된다.
- 팩 삭제: 폴더가 사라지면 해당 팩의 모든 에셋과 임베딩을 `ON DELETE CASCADE`로 함께 제거(단 `asset_usage` 이력은 보존해 분석용으로 남긴다).

### 4.2 Asset Analyzer

분석기는 파일 종류별로 다른 파이프라인을 탄다.

#### 4.2.1 단일 스프라이트 (`sprites/*.png`)
1. Pillow로 열기 → 해상도, 알파 채널, 도미넌트 컬러 5개 추출.
2. 픽셀 아트 여부 판정 (인접 픽셀 분산 + 색상 유니크 카운트로 휴리스틱).
3. **원본 PNG를 그대로** Gemma 4 멀티모달에 첨부 → JSON 응답 요청. 프롬프트는 §6.1 참고.
4. 응답을 검증(스키마 일치, 카테고리 화이트리스트) 후 메타에 저장.

> Gemma 4는 OCR, 객체 검출, UI/차트 이해 같은 능력을 모델 카드에 명시한다. 게임 아이콘처럼 텍스트가 박힌 스프라이트의 라벨 인식에 그대로 활용 가능하다.

#### 4.2.2 스프라이트 시트 (`spritesheets/*.png`) ✅ M6 완료

1. 동명 `.json` 이 있으면 우선 사용 — `core/sheet/json_parser.py` 가 Aseprite Array/Hash + TexturePacker 자동 형식 판별.
2. 없으면 격자 추정 — `core/sheet/grid_detect.py` 가 Pillow alpha 채널 행/열 합으로 균일 격자 검출. 실패 시 일반 `sprite` 로 폴백 (사용자 frame size 입력 GUI 는 M7+ v2).
3. 프레임을 가로 8칸 그리드로 합성 (`core/sheet/preview.py`, 8 이하 그대로, 그 이상 선형 stride 샘플링) → Gemma 4 호출 → `animation_hint` 받음.
4. 결과는 시트 단위 + Aseprite frameTags 가 있으면 frame range 단위로도 `sprite_meta.animations_json` 에 저장.

#### 4.2.3 사운드 (`sounds/*.{wav,ogg,mp3}`)

Gemma 4의 E2B/E4B는 conformer 기반 오디오 인코더를 내장해 **원본 오디오를 직접 모델에 넘길 수 있다**. 따라서 v1은 멜 스펙트로그램 우회 없이 네이티브 경로를 기본으로 쓰고, 모델/런너 이슈에 대비해 폴백을 둔다.

1. `librosa` / `soundfile`로 기술 특성 추출: sample rate, 길이, 채널, RMS(loudness), spectral centroid, BPM(타악기성 있을 때만).
2. **클립 선택 (≤ 30초)** — Gemma 4 오디오 입력은 클립당 최대 30초·단일 채널 제약이 있다([Gemma audio docs](https://ai.google.dev/gemma/docs/capabilities/audio)).
   - 30초 이하: 원본 그대로 (모노 다운믹스, 16kHz 리샘플).
   - 30초 초과(주로 BGM): 시작 5초 + 중앙 15초 + 끝 5초의 세 청크를 따로 만들어 각각 분석하고, 결과를 머지. 또는 RMS 상위 30초 구간 1개만 보내는 빠른 옵션도 설정으로 제공.
3. **1차 경로 — 네이티브 오디오** : 오디오 청크 + 파일명/폴더명 컨텍스트를 함께 `gemma4:e4b`에 보내 다음 필드를 JSON으로 받는다. `category` (`sfx`/`bgm`/`voice`/`ui`/`ambient`), `mood` (다중 라벨), `instruments`, `loopable`, `transcript` (voice일 때만), `description`.
4. **2차 폴백 경로 — 멜 스펙트로그램 비전** : 1차 경로가 실패하면(런너 크래시·타임아웃·JSON 검증 실패) librosa로 멜 스펙트로그램 PNG를 만들어 같은 모델의 비전 입력으로 재시도. Ollama gemma4:e4b 오디오 추론에서 GGML assertion이 간헐적으로 보고된 상태([ollama/ollama#15333](https://github.com/ollama/ollama/issues/15333))이므로 이 폴백은 반드시 유지한다.
5. **3차 최후 폴백** : 위 둘 다 실패하면 기술 특성(길이/RMS/BPM)과 파일명만으로 휴리스틱 분류 (예: 파일명에 `bgm`·`loop`·`music` 포함 시 BGM 추정). `analysis_state='partial'`로 마킹해 GUI에서 사용자가 보정하도록.

> 1·2차 경로 모두 같은 JSON 스키마를 따르므로, 검색 단계에서는 어떤 경로로 분석됐는지 구분 없이 동일하게 다뤄도 된다.

#### 4.2.4 분석 클라이언트의 백엔드 추상화 (ADR, 2026-05-16)

v1은 Ollama 를 1차 백엔드로 채택하지만, 분석 클라이언트(`assetcache.core.ollama_client`)는 **얇은 HTTP 래퍼**로만 짜서 백엔드를 갈아끼울 수 있게 둔다. 이유:

- **llama.cpp / llama-server 는 2026-04 시점 오디오 입력 미구현** 이라 우리 1차 경로(네이티브 오디오)를 못 탄다. 이미지·텍스트만 안정이라 후보에서 탈락.
- **LM Studio**는 데몬 모드(`lms daemon up`, `lms server start`) + OpenAI 호환 엔드포인트를 제공하고 모델 페이지에서도 오디오 지원을 표기하지만, 2026-05 시점 공식 developer docs 에는 **오디오 입력 요청 스키마가 명시되지 않았다**. 의존하면 비공개 동작에 종속된다.
- **Ollama 의 GGML assertion 크래시([#15333])** 는 자동 재시작 6~8초로 부분 회복되고, §4.2.3 의 1·2·3차 폴백이 정확히 이 시나리오를 흡수한다. 즉 우리 분석 큐 입장에선 "한 항목 실패 → 다음 항목"으로 자연 진행.

규약:

- 호출은 `POST {base_url}/v1/chat/completions` (OpenAI 호환) 우선. 실패하면 `POST {base_url}/api/chat` (Ollama 네이티브) 폴백. LM Studio·llama-server 도 `/v1/...` 을 따르므로 base URL 한 줄 변경으로 백엔드 교체가 끝나야 한다.
- 모델명·base URL·타임아웃·동시성은 전부 `Config` 필드에서 주입 (이미 있는 `ollama_url`, `model_image`, `model_audio`, `model_embed` 외에 M2 에서 `analysis_timeout_seconds`, `analysis_concurrency` 추가 예정).
- **Ollama 네이티브 `/api/chat` 의 멀티모달 입력은 `images: [base64, ...]` 단일 필드로 통합돼 있다** — 이미지든 오디오든 base64 바이트를 그 배열에 넣으면 모델이 modality 를 자동 추론한다. 공식 문서는 2026-05 시점 미공개 ([ollama/ollama#15427](https://github.com/ollama/ollama/issues/15427)) 이지만 2026-05-16 AssetCacheMCP 에서 실측 검증 완료(이미지=Windows 로고 식별, 오디오=Alarm01.wav "bouncy rhythmic synth beat" 묘사, 한국어+`format:"json"` JSON 강제 출력 모두 정상). OpenAI 호환 `/v1/chat/completions` 경로는 `input_audio.{data,format}` / `image_url` 등 분리 스키마를 따르므로 어댑터에서 두 형식을 모두 받게 둔다.
- LM Studio·llama-server 가 향후 오디오를 추가하면 그쪽 스키마(통상 OpenAI 호환)를 어댑터 한쪽에서 흡수.

이 결정은 **언제 다시 볼지** 기준선:

- Ollama #15333 이 닫혀 안정성이 회복되면 추상화는 그대로 두고 단순 Ollama 호출로 회귀해도 된다.
- 추상화가 짐이 될 만큼 무거워지면(예: 분기 로직이 클라이언트 코드의 30% 초과) 백엔드를 한쪽으로 고정한다.

### 4.3 Embedding 인덱스

Ollama의 `nomic-embed-text` 모델로 각 에셋의 "검색 가능한 텍스트"(파일명 + 카테고리 + 태그 + Gemma 4가 만든 한 줄 설명)를 768차원 벡터로 인코딩해 SQLite에 BLOB으로 보관한다. 검색 시에는 쿼리도 같은 모델로 임베딩 후 코사인 유사도 상위 N개를 뽑고, **FTS5 키워드 매칭 점수**와 가중합해 최종 순위를 결정한다.

### 4.4 Metadata Store

- 엔진: SQLite (단일 파일, `metadata.db`)
- 모드: WAL (`PRAGMA journal_mode=WAL`), `synchronous=NORMAL`
- 위치: `%APPDATA%/AssetCacheMCP/metadata.db`
- ORM: `sqlite3` 직접 + 얇은 래퍼. SQLAlchemy까지는 과하다.
- 스키마는 §5 참고.

### 4.5 MCP Server

- 라이브러리: 공식 `mcp` (파이썬 SDK) 사용.
- 실행 모드: **stdio 모드** 단일(`assetcache --mcp`). Claude Code가 자식 프로세스로 띄움. (M5 이전 계획에 있던 HTTP/SSE MCP 모드는 FastAPI 웹 서버로 대체됐고 MCP 자체는 stdio 전용으로 단순화됨.)
- stdio 인스턴스는 같은 DB 파일을 WAL 모드로 읽는다. GUI/웹 서버 인스턴스가 워처·분석 큐를 소유하고 stdio 인스턴스는 read-only가 기본이다.
- **등록 도구 수: 17개** (M3: 12, M4: 16, M5 Phase 4C: 17). 도구 목록:

| # | 도구 이름 | 마일스톤 |
|--:|---|---|
| 1 | `find_asset` | M3 |
| 2 | `get_asset` | M3 |
| 3 | `list_assets` | M3 |
| 4 | `list_packs` | M3 |
| 5 | `suggest_packs` | M3 |
| 6 | `get_asset_thumbnail` | M3 |
| 7 | `record_asset_use` | M3 |
| 8 | `set_project_pin` | M3 |
| 9 | `request_rescan` | M3 |
| 10 | `report_feedback` | M3 |
| 11 | `get_label_registry` | M3 |
| 12 | `get_analysis_status` | M3 |
| 13 | `save_search` | M4 |
| 14 | `list_saved_searches` | M4 |
| 15 | `delete_saved_search` | M4 |
| 16 | `run_saved_search` | M4 |
| 17 | `request_user_pick` | M5 Phase 4C |

`request_user_pick` 상세 명세는 §6.13 (M5 신규), 사용 예시는 [`docs/MCP_USAGE_GUIDE.md`](./docs/MCP_USAGE_GUIDE.md).

### 4.6 Consistency Scorer (통일성 스코어러)

검색 결과에 "이 프로젝트와 어울리는 정도"를 반영해 한 프로젝트가 점점 한 팩(또는 같은 벤더의 팩들)으로 수렴하게 만든다.

**입력**

- 쿼리에 포함된 `project_id` (Claude Code가 보냄, 예: Unity 프로젝트 절대 경로 또는 사용자가 정한 별칭)
- 각 후보 에셋의 `pack_id`, `vendor`, 스타일 메타(픽셀아트 여부, 팔레트, 카테고리)
- `asset_usage` 테이블의 해당 프로젝트 사용 이력

**점수 공식 (가중치는 설정으로 조절 가능)**

```
final_score =
    0.50 * semantic_score        # 임베딩 코사인
  + 0.20 * keyword_score         # FTS5 BM25 정규화
  + 0.20 * consistency_score     # ← 새로 들어가는 항
  + 0.10 * recency_score         # 최근 분석/수정된 에셋에 살짝 가중
```

`consistency_score`(0..1)는 다음을 합산해 클램프한다.

| 신호 | 가중 | 설명 |
|---|---|---|
| 같은 팩 사용 이력 있음 | +0.6 | 해당 프로젝트가 이 `pack_id`의 에셋을 이전에 채택한 적이 있음 |
| 같은 벤더 사용 이력 있음 | +0.3 | 다른 팩이지만 같은 벤더(예: 둘 다 Kenney) |
| 스타일 일치 | +0.2 | 프로젝트가 주로 쓴 스타일(pixel_art / vector / hand_drawn)과 일치 |
| 팔레트 근접 | +0.1 | 프로젝트 도미넌트 팔레트와 ΔE 평균 임계 이하 |
| 처음 보는 팩 + 첫 요청 | 0 | 페널티 없음 (첫 채택은 자유롭게) |
| 처음 보는 팩 + 이미 다른 팩으로 굳음 | −0.2 | 강하게 굳은 프로젝트에 이질적 팩이 들어오는 것을 약하게 억제 |

"굳음" 판정은 단순히 `해당 프로젝트가 사용한 distinct pack_id 수`가 N개 이하이면서 누적 사용 횟수가 임계 이상일 때 켠다.

**노출**

- 검색 응답에 `consistency_score`와 `why` 문구를 함께 돌려준다. 예: `"이 프로젝트가 Kenney Platformer Redux를 12회 채택했음"`. Claude Code가 사용자에게 추천 근거를 설명할 수 있게.
- `find_asset` 입력에 `prefer_pack_id`나 `force_pack_id`를 명시할 수도 있다(사용자가 명시적으로 통일성을 깨고 싶을 때).
- 사용자가 GUI 설정에서 통일성 가중치를 0으로 낮추면 순수 의미 검색으로 회귀.

### 4.7 Usage Tracker

Claude Code가 추천 결과 중 어떤 것을 실제로 채택했는지가 다음 추천 품질의 핵심 신호다.

- MCP에 `record_asset_use(asset_id, project_id, context?)` 도구를 두고, Claude Code가 Unity 프로젝트에 에셋을 복사한 직후 호출하게 한다 (시스템 프롬프트 가이드라인으로 권장).
- 명시적 호출이 없을 때를 대비한 **암묵 기록** — `find_asset` 응답 시점에 `query_id`를 발급하고, 이후 같은 세션에서 같은 `project_id`로 추가 요청이 들어오면 직전 응답의 1순위가 채택된 것으로 간주(설정으로 끌 수 있음). 정확도는 떨어지지만 0보다 낫다.
- 이력은 `asset_usage` 테이블에 누적(§5.1).

### 4.8 트레이 + 웹 UI (M5 갱신)

> **M5 변경사항** — Qt 메인 윈도우(`src/assetcache/ui/`) 및 모든 Qt 위젯이 **완전 폐기**됐다(Phase 5C, 2026-05-18). 사용자 인터페이스는 FastAPI + HTMX + Alpine.js 기반 로컬 웹 서버로 전환됐다. PySide6는 트레이 아이콘과 `TrayBridge` 시그널 디스패치 용도로만 유지된다.

**트레이 앱 역할**

- 프레임워크: PySide6 (트레이 아이콘 전용)
- 기본 동작: `python -m assetcache --tray` 로 구동. 창 없이 트레이에 상주.
- 시작 시 uvicorn 웹 서버를 별도 스레드에서 구동 + 기본 브라우저로 `/library` 자동 열기.
- 트레이 메뉴: `메인 창 열기` (→ 브라우저 열기), `종료`.
- **TrayBridge** — `web/tray_bridge.py`. uvicorn 워커 스레드에서 발생한 이벤트(픽 요청 대기 수 갱신 등)를 `QObject` 시그널로 Qt main thread에 안전하게 전달. 트레이 아이콘 툴팁 갱신 담당.
- 윈도우 시작 시 자동 실행 — 레지스트리 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`.

**웹 서버 (`src/assetcache/web/`)**

FastAPI 앱을 uvicorn이 별도 `threading.Thread`에서 실행한다.

```
src/assetcache/web/
├── app.py              # build_app() — FastAPI 팩토리 + lifespan
├── server.py           # WebServer (threading.Thread + 포트 폴백)
├── deps.py             # WebDeps (Store, Config, SSE bus, PendingPickQueue)
├── sse_bus.py          # 스레드 안전 broadcast (asyncio 큐)
├── tray_bridge.py      # TrayBridge(QObject) — uvicorn→Qt 시그널
├── i18n.py             # _t() passthrough (M8에서 본격화)
├── routers/
│   ├── library.py      # GET /library, POST /api/search, /ui/search-results
│   ├── assets.py       # GET /api/thumbnail, /ui/asset-detail, /api/audio
│   ├── packs.py        # GET /packs, GET/PATCH /api/packs/{id}
│   ├── labels.py       # GET /labels/admin, /api/labels CRUD
│   ├── picks.py        # POST /internal/user-pick, PUT /api/user-pick/{rid}
│   ├── sse.py          # GET /sse/notifications
│   ├── weights.py      # POST /api/weights, /api/preset/{name}
│   ├── saved_searches.py # /api/saved-searches CRUD
│   ├── usage.py        # GET /api/usage/summary, /ui/usage/detail
│   └── feedback.py     # POST /api/record-use, /api/feedback (stub)
├── templates/
│   ├── base.html
│   ├── library.html
│   ├── packs.html
│   ├── labels_admin.html
│   └── partials/       # _card_wide.html, _pick_card.html 등
└── static/
    ├── css/
    ├── js/app.js       # SSE 이벤트 핸들러 + Alpine pickQueue 초기화
    └── vendor/         # htmx.min.js, alpine.min.js, htmx-sse.min.js, htmx-json-enc.js
```

**웹 UI 페이지 구성**

| URL | 설명 |
|---|---|
| `/library` | 에셋 검색 + 결과 카드 + 사이드 패널 (B/C/D 탭) + pick 카드 |
| `/packs` | 팩 카드 그리드 + enable/disable 토글 |
| `/labels/admin` | 24 axis 탭 + 라벨 CRUD + JSON import/export |

**Claude pick 인터랙션 흐름 (§4.8.1)**

1. Claude Code가 MCP `request_user_pick(candidates, reason, timeout_seconds)` 호출.
2. MCP server(`src/assetcache/mcp/tools.py`)가 `web.port` 파일에서 포트 읽기 → `POST /internal/user-pick` HTTP loopback (httpx).
3. FastAPI가 `PendingPickQueue`에 Future 등록 + SSE bus로 `pick_requested` 이벤트 브로드캐스트.
4. 브라우저가 SSE 수신 → HTMX가 `/ui/pick-card/{rid}` 요청 → 보라색 pick 카드 그룹 렌더링.
5. 사용자가 [채택] 클릭 → `PUT /api/user-pick/{rid}` (accepted, asset_id) → Future 해결 → MCP loopback 응답 반환 → 자동 `record_asset_use(source="claude_pick")`.
6. 사용자가 [✕ 거부] → Future 해결 (user_cancelled) → MCP `McpToolError("499_user_cancelled")`.
7. timeout_seconds 초과 → Future 만료 → MCP `McpToolError("408_timeout")`.

**윈도우 시작 시 자동 실행**

레지스트리 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`에 `AssetCacheMCP` 키 등록/해제 토글(M8 에 GUI 설정 제공 완료, M10 이전 키 이름은 `GameAssetHelper`).

### 4.9 Unity Asset Store Importer ✅ M7 구현 완료

사용자가 Unity Asset Store에서 받은 에셋을 AssetCacheMCP 라이브러리에 자동 등록한다. Unity는 보유 에셋 다운로드용 공식 API를 제공하지 않으므로([Asset Store 공식 안내](https://docs.unity3d.com/Manual/AssetStore.html)) v1은 **로컬 캐시 스캔**을 1차 경로로 삼고, 비공식 다운로드는 옵트인 부가 기능으로만 둔다.

#### 4.9.1 1차 경로 — 로컬 캐시 스캔 (기본 활성)

- **캐시 위치**: 기본 `%APPDATA%\Unity\Asset Store-5.x\` ([Unity 매뉴얼](https://docs.unity3d.com/Manual/upm-config-cache-as.html)). 사용자가 Unity Preferences에서 변경했거나 `ASSETSTORE_CACHE_PATH` 환경변수를 설정한 경우 그 값을 우선 사용한다. 두 경로가 모두 비어 있으면 AssetCacheMCP 설정 화면에서 사용자에게 직접 경로를 묻는다.
- **구조**: `Asset Store-5.x/<Publisher>/<Category>/<AssetName>.unitypackage`
- **파일 형식**: `.unitypackage` = gzip된 tar. 내부 구조는 GUID 폴더마다 다음 파일 3개:
  - `<guid>/asset` — 실제 바이트
  - `<guid>/asset.meta` — Unity 메타(YAML)
  - `<guid>/pathname` — 원본 경로(예: `Assets/Sprites/Hero/idle.png`)
- **추출 로직** (Python 표준 `tarfile` + `gzip`):
  1. `.unitypackage`를 열어 모든 `pathname` 텍스트를 먼저 읽음.
  2. 그 중 확장자가 `.png`, `.jpg`, `.webp`, `.wav`, `.ogg`, `.mp3` 인 항목만 골라 GUID 매핑 테이블 구성.
  3. 해당 GUID 디렉터리의 `asset` 파일만 추출하고 `pathname` 의 원본 경로를 그대로 복원해 `library/<pack_name>/...` 아래에 풀어 둔다.
  4. 위 작업이 끝나면 일반 워처가 새 팩으로 인식해 §4.1 의 정상 인테이크 흐름을 탄다.
- **팩 매핑**:
  - `pack_name` = 정규화된 `AssetName` (공백·특수문자 → `_`)
  - 매니페스트(`pack.json`)를 자동 생성:
    ```json
    {
      "name": "Mega Platformer Pack",
      "vendor": "<Publisher>",
      "license": "Unity Asset Store EULA",
      "source": "unity_asset_store_cache",
      "source_path": "C:/Users/.../Asset Store-5.x/Pixel Studios/Sprites/MegaPlatformerPack.unitypackage",
      "imported_at": 1747000000,
      "package_mtime": 1740000000
    }
    ```
- **증분 동기화**: 캐시 디렉터리의 `.unitypackage` 파일 mtime/size를 DB에 기록(`unity_imports` 테이블, §5.4). 다음 스캔 때 변경된 것만 재추출. 캐시에서 사라진 패키지는 사용자 확인 후 라이브러리에서도 제거(기본은 보존, GUI 토글로 정책 변경).
- **트리거**:
  - GUI "Unity Asset Store" 탭의 "지금 동기화" 버튼.
  - 트레이 메뉴에서 "Unity Asset Store 동기화".
  - 설정에서 "윈도우 시작 직후 / 매일 1회 자동 동기화" 옵션.
  - MCP 도구 `sync_unity_asset_store` (§6.11) — Claude Code가 `"내가 가진 Unity 에셋 다 끌어와줘"` 같은 요청을 처리할 때 사용.

#### 4.9.2 2차 경로(옵트인) — 비공식 Publisher 패널 API

사용자가 보유한 에셋 중 **아직 다운로드한 적이 없는 것까지** GAH가 직접 가져오려면 Unity Hub/Editor가 내부적으로 쓰는 publisher 패널 엔드포인트(`kharma_session` 쿠키 기반)에 접근해야 한다([UnityAssetstoreAPI](https://github.com/se0kjun/UnityAssetstoreAPI), [unity-asset-store-api](https://github.com/mukaschultze/unity-asset-store-api) 같은 비공식 클라이언트가 이 방식을 쓴다).

- **v1 기본값: 비활성.** Unity ToS 회색지대이고 엔드포인트가 예고 없이 깨질 수 있다.
- **활성화 조건**: 설정에서 사용자가 명시적으로 켜고, `kharma_session` 쿠키 값을 입력해야 한다. GUI는 활성화 화면에 "Unity 공식 API가 아니며 약관 위반 위험과 갑작스러운 동작 중단 가능성이 있음" 경고를 띄운다.
- **동작**: 
  1. 비공식 엔드포인트로 보유 에셋 목록 조회.
  2. 캐시에 없는 항목을 다운로드해 캐시에 저장(Unity Hub가 받은 것과 동일한 위치).
  3. 그 다음은 1차 경로(캐시 스캔)에 위임.
- **결과적으로 1차 경로의 코드 경로 하나로 통일**된다. 2차 경로는 단지 "캐시 채우기"만 담당.

#### 4.9.3 미래 옵션(v2+) — Unity Editor 헬퍼 스크립트

사용자가 AssetCacheMCP가 제공하는 `.unitypackage`(작은 Editor 스크립트 + 메뉴 항목) 하나를 Unity 프로젝트에 임포트하면, "Tools → AssetCacheMCP → Export My Assets" 메뉴로 Unity의 `AssetDatabase`/`PackageManager` API를 통해 보유 에셋을 AssetCacheMCP 라이브러리로 안전하게 내보내는 흐름. 공식 API만 쓰므로 가장 신뢰성이 높지만, 사용자가 Unity를 열고 한 번 임포트해야 하는 수동 부담이 있다. v1에는 포함하지 않고 v2 검토.

#### 4.9.4 라이선스/사용 제약

- `.unitypackage` 내용은 Unity Asset Store EULA의 범위 안에서 GAH가 "사용자 본인의 로컬 라이브러리 인덱싱"으로만 사용한다. 외부로 전송하지 않으며, MCP를 통한 응답에 포함되는 것은 **사용자 본인의** Claude Code 세션에 한정된다.
- GAH는 임포트한 팩의 라이선스 필드를 `Unity Asset Store EULA`로 자동 설정한다. 사용자가 작업물 배포 시 라이선스 조건을 따로 검토해야 한다는 안내를 GUI 상세 화면에 노출.


### 4.10 활성 프로젝트 + 프로젝트 페이지 + 자산별 선호도 ✅ M7 구현 완료

> M7에서 신설된 cross-cutting 기능이다. Unity Asset Store 임포트와 독립적이지만 같은 마일스톤에서 구현됐다.

#### 4.10.1 활성 프로젝트 (active project)

GAH는 한 번에 하나의 **활성 프로젝트**를 기억한다.

- 글로벌 헤더 우상단 드롭다운에서 선택/생성/변경.
- `Config.active_project_id` 에 저장돼 재시작 후에도 유지.
- 활성 프로젝트가 없으면 라이브러리 카드의 "채택" 버튼이 비활성화된다.
- MCP 도구 `find_asset` / `suggest_packs` 는 `project_id` 파라미터로 명시적으로 전달하는 방식을 유지한다. 활성 프로젝트는 웹 UI 중심 개념이다.

프로젝트 생성 API:
- `POST /api/projects` — `{external_id, display_name}` → `{id, ...}`
- 성공 시 자동으로 활성 프로젝트로 설정.

활성 프로젝트 관리 API:
- `GET /api/active-project` — 현재 활성 프로젝트 조회
- `POST /api/active-project` — `{project_id}` 로 변경
- `DELETE /api/active-project` — 활성 프로젝트 해제

#### 4.10.2 자산 채택 (adopt)

라이브러리 카드 하단에 "채택" 버튼이 있다. 클릭 시:
1. 활성 프로젝트 없음 → 버튼 disabled (툴팁: "프로젝트를 먼저 선택하세요")
2. `POST /api/library/assets/{id}/adopt` → `asset_usage` 에 `source="user_web"` 행 INSERT.
3. 응답 후 카드 UI에 채택 표시.

#### 4.10.3 프로젝트 목록 페이지 (`/projects`)

- 모든 프로젝트를 `first_seen DESC` 로 나열.
- 활성 프로젝트는 상단 강조 + 별 아이콘.
- 각 카드에 총 사용 자산 수, 최다 사용 팩 이름 표시.

#### 4.10.4 프로젝트 상세 페이지 (`/projects/<id>`)

세 패널로 구성:

1. **사용 이력 표** — `asset_usage` JOIN assets/packs. `used_at DESC`. 페이지네이션 25개씩.
2. **채택 팩 분포** — `asset_usage GROUP BY pack_id`. 도넛 차트 없이 막대 목록으로 표현.
3. **자산별 선호도 패널** — `get_project_asset_preferences()` 결과:
   - `composite_score` = `SUM(feedback.weight) + 0.1 × usage_count`
   - 정렬: score_desc (기본) / score_asc / usage_desc / name_asc
   - 인라인 검색 (JS 클라이언트 사이드 필터)
   - 페이지네이션 50개씩

#### 4.10.5 격리 불변식 (I-1~I-5)

라이브러리(검색/분석 도메인)와 Unity 후보(임포트 도메인) 간 격리를 보장하는 5 불변식이 `tests/test_isolation_invariants.py` 에 회귀 테스트로 고정돼 있다.

| 불변식 | 설명 |
|---|---|
| I-1 | `discovered/previewed` 패키지의 자산은 `assets` 테이블에 없음 |
| I-2 | preview 는 `unity_imports.preview_*` 만 갱신 — library/assets 부작용 없음 |
| I-3 | library 라우터가 `unity_imports` 테이블을 조회하지 않음 |
| I-4 | Unity 라우터가 `list_assets`/`find_asset` 같은 library API를 호출하지 않음 |
| I-5 | project_A 의 feedback/usage 가 project_B 점수에 반영되지 않음 |


### 4.11 Batch processing — Gemini Batch API ✅ M11.1 구현 완료

> M11.1 에서 신설. 대량 에셋 분석을 50% 비용으로 처리하는 hybrid 정책 + `/analyzing` dashboard.

#### 4.11.1 Hybrid 정책

| 상황 | 처리 경로 |
|---|---|
| 1장 드롭 / 소수 drop | interactive (Ollama/Gemini realtime) — 즉시 카드 반영 |
| 30+ 장 동시 drop + chain 1순위 = Gemini + toggle = auto | Gemini Batch API 자동 진입 |
| toggle = forced_on | 수량 무관 Gemini Batch API 강제 |
| toggle = forced_off | 수량 무관 interactive 유지 |
| chain 1순위 != Gemini | toggle 무관하게 interactive 유지 |

임계값(기본 30)과 toggle 은 `/settings` Batch 패널 + tray 우클릭 메뉴에서 사용자 조정 가능.

#### 4.11.2 아키텍처

```
AnalysisQueue
    │  pending 30+ 감지 (_try_batch_submit hook)
    ▼
BatchManager.try_submit(modality, chain, store, config)
    │  toggle/chain/threshold 결정 + race lock
    │  dequeue_assets → Gemini Batch API JSONL submit
    ▼
    DB: batch_jobs INSERT (state=submitted) + assets.batch_job_id/batch_state 갱신
    │
    ▼
BatchPoller (daemon Thread, 기본 30분 interval)
    │  list_active_batch_jobs → batch_get 상태 확인
    │  succeeded → JSONL 결과 파싱 → modality 별 persist + mark_asset_backends
    │  terminal_failure → assets interactive fallback 재투입
    ▼
    DB: analysis_state='ok' + backend_image/audio/embed = 'gemini'
```

#### 4.11.3 신설 모듈

```
src/assetcache/core/batch/
├── __init__.py
├── types.py       # BatchJob, BatchState, BatchJobRecord dataclass
├── manager.py     # BatchManager — try_submit + _do_submit + cancel
└── poller.py      # BatchPoller — daemon Thread + poll/handle_succeeded/terminal_failure
src/assetcache/core/analyzer/
└── messages.py    # 분석기 공통 메시지 빌더 (Gemini chat 요청 생성)
```

#### 4.11.4 DB 추가 컬럼/테이블 (§5.1 갱신)

- `batch_jobs` 테이블 (신설): `id`, `backend`, `modality`, `backend_job_id` (UNIQUE), `asset_count`, `submitted_at`, `expires_at`, `state`, `completed_at`, `success_count`, `failure_count`, `error`, `display_name`
- `assets` 테이블 추가 컬럼: `batch_job_id INTEGER REFERENCES batch_jobs(id)`, `batch_state TEXT NOT NULL DEFAULT 'none'` (`none`/`queued`/`submitted`/`completed`/`failed`/`expired`)

#### 4.11.5 웹 UI 신규 페이지 및 엔드포인트

| 경로 | 설명 |
|---|---|
| `GET /analyzing` | 분석 진행 상황 dashboard (interactive 큐 + batch jobs + 최근 실패) |
| `GET /analyzing/partial` | 5초 주기 auto-refresh 대상 partial HTML |
| `POST /analyzing/batch/<id>/cancel` | 진행 중 batch job 취소 |
| `POST /settings/batch` | BatchConfig 저장 (threshold/toggle/polling_interval) |
| `POST /settings/batch/jobs/<id>/cancel` | /settings 에서 batch job 취소 |

#### 4.11.6 알려진 한계

- Image/audio Gemini 결과 → labels 실제 파싱 미구현 (empty labels + mark ok). M12 candidate.
- 파일 크기 > 20MB inline 제한 — file destination batch 방식은 v0.2.x 후속.
- OpenAI/Anthropic Batch API — v0.3.0 candidate.


## 5. 데이터 스키마

### 5.1 SQLite 테이블

```sql
-- 에셋 팩 (library 직속 하위 디렉터리 하나당 1행)
CREATE TABLE packs (
  id              INTEGER PRIMARY KEY,
  name            TEXT NOT NULL UNIQUE,    -- 팩 폴더명. 표시명은 매니페스트가 우선
  display_name    TEXT,
  vendor          TEXT,                    -- 'kenney', 'kaykit', ... 추정
  source_url      TEXT,
  license         TEXT,
  description     TEXT,
  enabled         INTEGER NOT NULL DEFAULT 1,
  added_at        INTEGER NOT NULL,
  scanned_at      INTEGER,
  aggregate_meta  TEXT                     -- JSON: 주 스타일, 도미넌트 팔레트, 카테고리 분포 등
);

-- 모든 에셋의 공통 메타
CREATE TABLE assets (
  id              INTEGER PRIMARY KEY,
  pack_id         INTEGER NOT NULL REFERENCES packs(id) ON DELETE CASCADE,
  path            TEXT NOT NULL UNIQUE,    -- 라이브러리 루트로부터의 상대 경로 (팩 폴더명 포함)
  kind            TEXT NOT NULL,           -- 'sprite' | 'spritesheet' | 'sound'
  file_hash       TEXT NOT NULL,           -- xxhash64, 재분석 트리거용
  file_size       INTEGER NOT NULL,
  added_at        INTEGER NOT NULL,        -- unix epoch
  analyzed_at     INTEGER,                 -- NULL이면 미분석
  analysis_state  TEXT NOT NULL,           -- 'pending' | 'analyzing' | 'ok' | 'partial' | 'failed'
  analysis_error  TEXT,
  manual_override INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_assets_pack ON assets(pack_id);

-- 스프라이트/시트 전용
CREATE TABLE sprite_meta (
  asset_id        INTEGER PRIMARY KEY REFERENCES assets(id) ON DELETE CASCADE,
  width           INTEGER NOT NULL,
  height          INTEGER NOT NULL,
  has_alpha       INTEGER NOT NULL,
  is_pixel_art    INTEGER NOT NULL,
  dominant_colors TEXT,                    -- JSON array of hex
  -- 시트일 때만
  frame_w         INTEGER,
  frame_h         INTEGER,
  frame_count     INTEGER,
  animation_tags  TEXT                     -- JSON array, e.g. ["walk","run"]
);

-- 사운드 전용
CREATE TABLE sound_meta (
  asset_id        INTEGER PRIMARY KEY REFERENCES assets(id) ON DELETE CASCADE,
  duration_ms     INTEGER NOT NULL,
  sample_rate     INTEGER NOT NULL,
  channels        INTEGER NOT NULL,
  loudness_db     REAL,
  bpm             REAL,                    -- nullable
  category        TEXT,                    -- 'sfx'|'bgm'|'voice'|'ui'|'ambient'
  loopable        INTEGER,
  instruments     TEXT                     -- JSON array
);

-- 검색용 텍스트(카테고리/태그/Gemma 한 줄 설명/파일명 등을 합친 것)
CREATE VIRTUAL TABLE assets_fts USING fts5(
  asset_id UNINDEXED,
  searchable_text,
  tokenize = 'porter unicode61'
);

-- 임베딩
CREATE TABLE asset_embeddings (
  asset_id   INTEGER PRIMARY KEY REFERENCES assets(id) ON DELETE CASCADE,
  model      TEXT NOT NULL,                -- 예: 'nomic-embed-text:v1.5'
  dim        INTEGER NOT NULL,
  vector     BLOB NOT NULL                 -- float32 little-endian, dim*4 바이트
);

-- 자유 태그 (다대다)
CREATE TABLE tags (
  id   INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE
);
CREATE TABLE asset_tags (
  asset_id INTEGER REFERENCES assets(id) ON DELETE CASCADE,
  tag_id   INTEGER REFERENCES tags(id) ON DELETE CASCADE,
  source   TEXT NOT NULL,                  -- 'gemma' | 'user' | 'heuristic'
  PRIMARY KEY (asset_id, tag_id)
);

-- 프로젝트 (Claude Code가 보내는 project_id로 식별)
CREATE TABLE projects (
  id              INTEGER PRIMARY KEY,
  external_id     TEXT NOT NULL UNIQUE,    -- 예: Unity 프로젝트 절대경로 또는 사용자 별칭
  display_name    TEXT,
  first_seen      INTEGER NOT NULL,
  last_seen       INTEGER NOT NULL,
  pinned_pack_id  INTEGER REFERENCES packs(id) ON DELETE SET NULL,
  blocked_packs   TEXT                     -- JSON array of pack_id
);

-- 에셋 사용 이력 (통일성 가중치 계산의 핵심 입력)
CREATE TABLE asset_usage (
  id          INTEGER PRIMARY KEY,
  project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  asset_id    INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
  pack_id     INTEGER NOT NULL,            -- 비정규화: 에셋이 삭제돼도 팩 선호는 유지
  used_at     INTEGER NOT NULL,
  source      TEXT NOT NULL,               -- 'explicit' | 'implicit_top1' | 'manual'
  context     TEXT                         -- 자유 메모(예: "platformer level1 BGM")
);
CREATE INDEX idx_usage_project ON asset_usage(project_id, used_at);
CREATE INDEX idx_usage_pack    ON asset_usage(project_id, pack_id);

-- 검색 쿼리 로그 (암묵 채택 추정 + 피드백용)
CREATE TABLE search_queries (
  id           INTEGER PRIMARY KEY,
  project_id   INTEGER REFERENCES projects(id) ON DELETE CASCADE,
  query_text   TEXT NOT NULL,
  results_json TEXT NOT NULL,              -- 상위 N개의 asset_id와 점수
  created_at   INTEGER NOT NULL
);

-- Unity Asset Store 임포트 추적 (M7 갱신)
CREATE TABLE unity_imports (
  id                    INTEGER PRIMARY KEY,
  package_path          TEXT NOT NULL UNIQUE,    -- .unitypackage 절대 경로
  publisher             TEXT,
  category              TEXT,
  asset_name            TEXT NOT NULL,
  package_size          INTEGER NOT NULL,
  package_mtime         INTEGER NOT NULL,        -- 변경 감지용
  preview_asset_count   INTEGER,                 -- 미리보기: 전체 지원 자산 수
  preview_image_count   INTEGER,                 -- 미리보기: 이미지 수
  preview_sound_count   INTEGER,                 -- 미리보기: 사운드 수
  preview_inspected_at  INTEGER,                 -- 미리보기 마지막 수행 시각
  pack_id               INTEGER REFERENCES packs(id) ON DELETE SET NULL,
  import_state          TEXT NOT NULL,           -- 'discovered' | 'previewed' | 'import_pending' | 'imported' | 'failed' | 'skipped'
  import_error          TEXT,
  imported_at           INTEGER,
  first_seen_at         INTEGER NOT NULL,        -- 캐시에서 처음 발견된 시각
  last_scanned_at       INTEGER                  -- 마지막 스캔에서 존재 확인된 시각
);
CREATE INDEX idx_unity_imports_pack ON unity_imports(pack_id);

-- M4: 저장된 검색 (UI/MCP 둘 다 공유)
CREATE TABLE saved_searches (
  id              INTEGER PRIMARY KEY,
  project_id      INTEGER REFERENCES projects(id) ON DELETE CASCADE,
  name            TEXT NOT NULL,
  query_json      TEXT NOT NULL,          -- SearchRequest 직렬화 (project_id 제외, _schema_version 메타 포함)
  created_at      INTEGER NOT NULL,
  last_used_at    INTEGER,
  UNIQUE(project_id, name)                 -- 같은 프로젝트 안에서 이름 unique (project_id NULL = global)
);
CREATE INDEX idx_saved_searches_project ON saved_searches(project_id, last_used_at);

-- M4: report_feedback 페널티 학습 — signed weight 누적
CREATE TABLE feedback_records (
  id              INTEGER PRIMARY KEY,
  project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  asset_id        INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
  query_id        INTEGER REFERENCES search_queries(id) ON DELETE SET NULL,
  reason          TEXT NOT NULL,           -- 'negative' | 'positive' | 'irrelevant'
  weight          REAL NOT NULL,           -- Config.feedback_*_weight 적용 결과 (signed)
  created_at      INTEGER NOT NULL
);
CREATE INDEX idx_feedback_project_asset
  ON feedback_records(project_id, asset_id, created_at);
CREATE INDEX idx_feedback_project_pack_asset
  ON feedback_records(project_id, asset_id);
```

### 5.2 팩 매니페스트 (`pack.json`)

선택적이지만 있으면 우선 사용한다. 없으면 폴더명·휴리스틱으로 추정.

```json
{
  "name": "Kenney Platformer Pack Redux",
  "vendor": "kenney",
  "source_url": "https://kenney.nl/assets/platformer-pack-redux",
  "license": "CC0",
  "description": "측면 스크롤 플랫포머용 타일·캐릭터·아이템 세트",
  "style_hint": ["vector", "cartoon"],
  "tags": ["platformer", "tiles", "characters"]
}
```

### 5.3 Gemma 4 응답 JSON 스키마(스프라이트 예)

스키마는 **듀얼 언어 구조** — 검색·통일성·임베딩 정렬을 위해 정규(canonical) 필드는 영어 화이트리스트로 고정하고, 사용자에게 노출되는 자연어(`description`, `subject`)만 호출 시 지정한 언어로 출력한다.

```json
{
  "category": "character",
  "subject": "검을 든 중세 기사",
  "style": "pixel_art",
  "mood": ["heroic", "serious"],
  "palette": ["warm", "muted"],
  "animation_hint": ["idle", "walk", "attack"],
  "description": "검을 든 중세 기사 캐릭터의 측면 도트 스프라이트",
  "confidence": 0.82
}
```

| 필드 | 언어 정책 | 비고 |
|---|---|---|
| `category` / `style` / `mood` / `palette` / `animation_hint` | 영어 enum 화이트리스트 고정 | 검색·통일성·임베딩의 어휘 공간 통일. 한국어로 받지 않는다. |
| `description` / `subject` | 호출 시 `language` 인자(`"ko"`/`"en"`, 기본 `"ko"`)에 따른 자연어 | M2 의 시스템 프롬프트가 이 인자에 따라 출력 언어를 지시. |
| `confidence` | 숫자 | 언어 무관. |

Pydantic 모델로 검증하고, `category`/`style`/`mood`/`palette`/`animation_hint`는 화이트리스트로 강제한다. 화이트리스트 밖이면 `other`로 강등하고 원문은 `description`에 보존한다. 사운드 응답(`sfx`/`bgm`/`voice`/`ui`/`ambient` 등)도 같은 듀얼 구조를 따른다 — `category`/`mood`/`instruments` 는 영어 enum, `description`/`transcript` 는 호출 언어.

GUI 텍스트(메뉴·탭·컬럼 헤더·에러)는 Qt i18n(`.ts/.qm`) 으로 별도 관리하며 v1 에서는 한국어 단일로 출발해 M6 마감 시점에 영어 번역 추가(§12 #4 참고).


## 6. MCP 도구 명세

MCP 클라이언트(Claude Code)에게 노출하는 도구 목록. 모든 도구는 JSON 입출력이며, 파일 응답은 절대 경로로 돌려준다(Claude Code가 Unity 프로젝트로 복사하기 위함).

### 6.1 `find_asset`

자연어 쿼리로 가장 적합한 에셋 후보를 돌려준다. `project_id`가 있으면 통일성 가중치를 적용한다(§4.6).

```jsonc
// input
{
  "query": "어두운 동굴 BGM, 루프 가능, 1분 이내",
  "kind": "sound",                  // optional, "sprite"|"spritesheet"|"sound"
  "count": 5,                       // optional, default 5
  "project_id": "D:/Unity/MyGame",  // 권장. 통일성 가중치의 근거가 된다.
  "prefer_pack_id": null,           // optional. 명시되면 점수 +0.3 보너스.
  "force_pack_id": null,            // optional. 명시되면 그 팩 안에서만 검색.
  "exclude_pack_ids": [],           // optional. 통일성 검사 위반 시 사용자가 제외 가능.
  "consistency_weight": null,       // optional 0..1, 기본은 설정값(통상 0.2)을 따른다.
  "filters": {                      // optional
    "tags_any": ["dark", "cave"],
    "min_duration_ms": 30000,
    "max_duration_ms": 60000,
    "loopable": true
  }
}

// output
{
  "query_id": "q_2026_05_16_001",          // record_asset_use에서 참조 가능
  "results": [
    {
      "asset_id": 142,
      "pack_id": 7,
      "pack_name": "Kenney Platformer Pack Redux",
      "path": "C:/Users/.../library/kenney_platformer_redux/Sounds/cave_loop_01.ogg",
      "score": 0.87,
      "score_breakdown": {
        "semantic": 0.41, "keyword": 0.18, "consistency": 0.24, "recency": 0.04
      },
      "why": "어두움/동굴 분위기 일치, 47초 루프 가능. 이 프로젝트가 Kenney Platformer Redux를 12회 채택했음.",
      "meta": { /* 해당 에셋의 전체 메타 */ }
    }
  ]
}
```

### 6.2 `get_asset`

ID 또는 경로로 단일 에셋의 메타데이터를 가져온다.

### 6.3 `list_assets`

페이지네이션과 필터로 라이브러리 전체를 나열한다. `pack_id` 필터 지원. 디버깅·탐색 용.

### 6.4 `list_packs`

등록된 팩 목록과 각 팩의 집계 메타(파일 수, 주 스타일, 도미넌트 팔레트, 라이선스)를 단순 나열한다. 쿼리·정렬 가중치를 적용하지 않는 "전체 카탈로그 보기"용. 디버깅/탐색·GUI 동기화용.

### 6.5 `suggest_packs` (팩 선택 단계의 핵심)

Claude Code가 사용자에게 "어느 팩을 쓸지" 고르게 하려고 호출하는 도구. 쿼리 의미 유사도, 통일성 가중치, 라이선스/스타일 메타를 종합해 **팩을 정렬한 후보 리스트**를 돌려준다. 각 팩 항목에는 사용자가 한눈에 비교·결정할 수 있도록 다음이 포함된다.

```jsonc
// input
{
  "query": "스테이지 클리어 효과음, 짧고 경쾌한",  // optional. 없으면 통일성/벤더 가중만으로 정렬
  "project_id": "D:/Unity/MyGame",                  // optional. 있으면 사용 이력 가중치 반영
  "kind": "sound",                                  // optional. "sprite"|"spritesheet"|"sound"
  "count": 5,                                       // optional, default 5
  "include_samples": true,                          // optional, default true. 각 팩에서 쿼리와 가장 잘 맞는 상위 3개 에셋을 같이 보여줄지
  "include_thumbnails": true,                       // optional, default true. 캐시된 썸네일 경로 포함
  "min_matching_assets": 1                          // 매칭 0개 팩은 제외
}

// output
{
  "query_id": "qp_2026_05_16_007",                  // 이후 find_asset/record_asset_use에서 참조 가능
  "project_context": {
    "project_id": "D:/Unity/MyGame",
    "pack_usage": [
      { "pack_id": 7, "pack_name": "Kenney Platformer Pack Redux", "uses": 12 },
      { "pack_id": 11, "pack_name": "Kenney UI Pack", "uses": 4 }
    ],
    "pinned_pack_id": null
  },
  "packs": [
    {
      "pack_id": 7,
      "name": "Kenney Platformer Pack Redux",
      "vendor": "kenney",
      "license": "CC0",
      "source_url": "https://kenney.nl/...",
      "description": "측면 스크롤 플랫포머용 타일·캐릭터·아이템 세트",
      "style_summary": { "is_pixel_art": false, "style": "vector_cartoon", "palette": ["#f4a261", "#264653", "#e76f51"] },
      "asset_counts": { "sprite": 312, "spritesheet": 28, "sound": 64, "total": 404 },
      "matching_asset_count": 6,                    // 이 팩에서 쿼리와 의미적으로 맞는 후보 수
      "project_usage_in_this_project": 12,          // 같은 project_id가 이 팩을 채택한 횟수
      "score": 0.91,
      "score_breakdown": {
        "semantic_top1": 0.62,                      // 팩 내 최상위 에셋의 의미 유사도
        "semantic_mean_top3": 0.55,                 // 상위 3개 평균
        "consistency": 0.24,                        // 이 프로젝트와의 통일성
        "vendor_familiarity": 0.05                  // 같은 벤더 사용 이력
      },
      "why": "쿼리와 일치하는 짧은 클리어 SFX 6개 보유. 이 프로젝트가 Kenney 팩을 12회 채택해 통일성에 유리.",
      "samples": [
        {
          "asset_id": 142,
          "path": "C:/.../kenney_platformer_redux/Sounds/coin1.wav",
          "thumbnail_path": null,                   // 사운드는 썸네일 없음
          "preview_blurb": "0.4초 코인 띠링, 밝음/경쾌"
        },
        {
          "asset_id": 158,
          "path": "C:/.../kenney_platformer_redux/Sounds/jingle_win.ogg",
          "thumbnail_path": null,
          "preview_blurb": "1.2초 승리 징글, 메이저 코드"
        }
        // 최대 3개
      ]
    }
    // ... 다음 팩들
  ]
}
```

**스코어 공식**

```
pack_score =
    0.45 * semantic_top1
  + 0.20 * semantic_mean_top3
  + 0.25 * consistency             # §4.6의 0..1 점수
  + 0.05 * vendor_familiarity
  + 0.05 * recency                 # 팩 추가/업데이트 최근성
```

가중치는 설정으로 조절 가능하며, 사용자가 `pinned_pack_id`를 지정해둔 프로젝트에서는 해당 팩이 무조건 1순위로 올라간다(차이는 응답의 `why`에 명시).

**썸네일/샘플 처리**

- 스프라이트 샘플은 `cache/thumbnails/<asset_id>.png` (256×256 사전 생성)을 가리키는 절대 경로를 돌려준다. Claude Code는 이 파일을 읽어 사용자에게 보여줄 수 있다.
- 사운드 샘플은 `preview_blurb`(Gemma 4가 만든 한 줄 요약) + `path`를 돌려주고, Claude Code가 OS 기본 재생기로 미리듣기 액션을 제안할 수 있게 한다.
- 응답 크기 절약을 위해 `include_thumbnails=false`로 호출하면 경로 필드를 비운다.

### 6.6 `suggest_animation_frames` ✅ M6 완료

스프라이트 시트의 특정 애니메이션(예: `walk`)에 해당하는 프레임 인덱스 배열 + `fps_hint` 를 돌려준다. Unity의 `AnimationClip` 을 만들 때 직접 쓰일 데이터.

```jsonc
// input
{ "asset_id": 88, "animation": "walk" }

// output (Aseprite frameTags 기반, 평균 duration 90ms 에서 역산)
{ "frame_indices": [0,1,2,3,4,5,6,7], "fps_hint": 11 }
```

에러:
- `404_not_found` — `asset_id` 없음, `sprite_meta` 없음, animation 미존재 (응답 메시지에 available 목록 포함).
- `400_invalid_input` — `kind != "spritesheet"`.

### 6.7 `record_asset_use`

Claude Code가 추천 결과 중 실제로 채택해 Unity 프로젝트에 복사한 에셋을 기록한다. 이 기록이 누적될수록 같은 프로젝트의 후속 `find_asset` 결과가 그 팩으로 수렴한다(§4.6, §4.7).

```jsonc
// input
{
  "project_id": "D:/Unity/MyGame",
  "asset_id": 142,
  "query_id": "q_2026_05_16_001",   // optional, 직전 find_asset 결과와 연결
  "context": "Stage1 ambient loop"  // optional
}

// output
{ "ok": true, "usage_id": 3391 }
```

### 6.8 `set_project_pin`

프로젝트에 특정 팩을 "고정"하거나 차단한다. Claude Code 또는 사용자가 "이 프로젝트는 무조건 Kenney만 써" 같은 강한 선호를 설정할 때.

```jsonc
// input
{ "project_id": "...", "pinned_pack_id": 7, "blocked_pack_ids": [12, 19] }
```

### 6.9 `request_rescan`

특정 경로/팩(또는 전체)을 강제 재분석. 사용자가 메타를 수정한 뒤 다시 라벨링하고 싶을 때 사용.

### 6.10 `report_feedback`

Claude Code가 "이 에셋이 잘 안 맞았다"는 신호를 보낼 수 있게 한다. M4 부터 페널티 학습이 활성 — 자세한 동작은 §6.10.1.

#### 6.10.1 M4 페널티 학습 알고리즘

- `reason` 화이트리스트: `Literal["negative", "positive", "irrelevant"]`. 자유 문자열은 ValidationError.
- 호출 시 Config 의 `feedback_*_weight` (`negative=-0.5`, `positive=+0.3`, `irrelevant=-0.3` 기본) 로 signed weight 변환 후 `feedback_records` 테이블 INSERT.
- `HybridSearcher.hybrid()` 가 검색 시 같은 `project_id` 의 윈도우 (30일 기본) 내 행을 두 단위로 합산:
  1. **asset-level** — `feedback_records_for_project(pid, [aid], window)` 의 weight 합. [-1, +1] 클램프.
  2. **pack-level** — `pack_feedback_count(pid, [pid], window)` 의 음수 가중치 카운트가 `feedback_pack_threshold=3` 이상이면 그 팩 전체에 `feedback_pack_penalty=-0.1` 추가.
- 합산 결과에 `Config.weight_feedback` (기본 0.10) 을 곱해 `score_breakdown.feedback` 채널로 노출.
- `Config.weight_feedback=0` 시 채널 키는 보존되되 값 0 (회귀 안전).

### 6.12 `save_search` / `list_saved_searches` / `delete_saved_search` / `run_saved_search` (M4 신규)

저장된 검색 4 도구. UI 사이드 패널 + MCP 양쪽이 같은 `saved_searches` 테이블 공유.

```jsonc
// save_search 입력
{
  "project_id": "D:/Unity/MyGame",
  "name": "전투 BGM 다크",
  "query": "전투 BGM",
  "label_query": "sound_mood:dark AND sound_use:combat",
  "kind": "sound",
  "diversity": "mmr",
  "diversity_lambda": 0.7,
  "count": 10
}
// 출력
{ "ok": true, "saved_search_id": 17 }
```

- **중복 (project_id, name)** → `400_invalid_input`. 덮어쓰기는 `delete_saved_search` 후 다시 호출.
- `list_saved_searches(project_id)` → `last_used_at DESC NULLS LAST, created_at DESC`.
- `run_saved_search(project_id, name, overrides={...})` → 저장된 query_json 을 FindAssetRequest 로 재구성 후 `tool_find_asset` 위임. `overrides` 로 일부 필드 (예: `count`) 만 덮어쓰기 가능.
- `query_json` 에는 `_schema_version: 1` 박혀 있어 M5+ 마이그레이션 시 신호로 사용.

### 6.11 `scan_unity_asset_store_cache` / `list_unity_packages` ✅ M7 구현 완료

> **설계 변경 (M7)**: 원래 단일 `sync_unity_asset_store` 도구(historical reference — 아래 "이전 설계" 참고)를 **2개 도구**로 분리했다. 임포트(추출)는 사용자 통제 보존을 위해 웹 UI 전용으로 남겨 MCP 도구로 노출하지 않는다.

#### 19. `scan_unity_asset_store_cache`

Unity Asset Store 캐시 디렉터리를 스캔해 `unity_imports` 테이블을 갱신한다. 임포트(추출)는 수행하지 않는다.

```jsonc
// input
{
  "force": false,                   // true면 mtime 변화 없어도 전부 재스캔
  "filter": {                       // optional
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

#### 20. `list_unity_packages`

`unity_imports` 테이블을 조회해 패키지 목록을 돌려준다. Claude Code가 "내가 가진 Unity 에셋" 질의에 응답할 때 사용.

```jsonc
// input
{
  "state": "discovered",            // optional: "discovered"|"previewed"|"imported"|"skipped"|null(=전체)
  "filter": {
    "publisher_glob": "Kenney*",
    "asset_name_glob": "*character*"
  },
  "include_preview": false,         // true면 preview_asset_count 등 포함
  "offset": 0,
  "limit": 20
}

// output
{
  "total": 132,
  "items": [
    {
      "id": 7,
      "asset_name": "Kenney Platformer Pack",
      "publisher": "Kenney",
      "import_state": "discovered",
      "package_size": 1048576,
      "import_url": "http://localhost:37520/unity-asset-store"
    }
  ]
}
```

`import_url` 은 웹 UI의 Unity Asset Store 페이지 URL이다. Claude Code는 이를 사용자에게 안내해 임포트 여부를 결정하게 한다.

---

> **이전 설계 (historical reference)**: 단일 `sync_unity_asset_store` 도구가 스캔 + 추출을 모두 수행하도록 설계됐었다. M7 구현 과정에서 임포트는 사용자 확인이 필요한 조작(파일 복사, 라이브러리 변경)이므로 MCP 도구로 노출하지 않고 웹 UI에만 남기는 것으로 결정이 변경됐다.


## 7. 폴더 / 파일 구조

런타임 데이터(에셋 라이브러리 + DB)는 다음 경로에 둔다. 경로는 모두 영어로 통일한다.

```
%APPDATA%/AssetCacheMCP/
├── library/
│   ├── kenney_platformer_redux/          # 팩 1: 폴더 통째로 드롭한 그대로
│   │   ├── PNG/Characters/...
│   │   ├── Sounds/...
│   │   └── pack.json                     # 선택적 매니페스트
│   ├── kenney_ui_pack/                   # 팩 2
│   │   └── ...
│   └── my_custom_sfx/                    # 팩 3 (사용자 직접 만든 묶음도 가능)
│       └── ...
├── cache/
│   ├── thumbnails/        # GUI에서 빠르게 보여줄 256x256 PNG
│   └── spectrograms/      # 사운드 분석 시 생성한 멜 스펙트로그램 (폴백용)
├── metadata.db
├── config.toml
└── logs/
    └── assetcache.log
```

> 팩 내부 폴더 구조는 자유다. 워처가 재귀로 스프라이트/시트/사운드를 탐색한다. 같은 파일이 여러 팩에 중복돼 있어도 각각 별개 에셋으로 등록되며, `file_hash`로 동일성을 알아낼 수 있다.

소스 코드 레이아웃(개발 리포지토리):

```
assetcache-mcp/                # M10 에서 game-asset-helper → assetcache-mcp 로 GitHub repo rename (구 URL 은 GitHub 자동 redirect)
├── pyproject.toml             # name = "assetcache-mcp" (M10)
├── DESIGN.md                  # 이 문서
├── README.md
├── src/
│   └── assetcache/            # M10 에서 src/gah/ → src/assetcache/
│       ├── __init__.py
│       ├── __main__.py        # CLI 엔트리포인트 (--tray / --mcp / --version)
│       ├── app.py             # PySide6 QApplication
│       ├── tray.py            # 트레이 아이콘 + 메뉴 + PyPI 업데이트 메뉴 (M10 Phase 2)
│       ├── updater/           # M10 Phase 2 — PyPI 알림 (M9 cherry-pick)
│       │   ├── version.py     # 현재 설치 버전
│       │   ├── checker.py     # PyPI JSON API + 캐시
│       │   └── pip_command.py # pipx/uv/pip 분기 → upgrade 명령 문자열
│       ├── core/
│       │   ├── watcher.py
│       │   ├── pack_manager.py
│       │   ├── analyzer/
│       │   │   ├── base.py
│       │   │   ├── sprite.py
│       │   │   ├── spritesheet.py
│       │   │   └── sound.py
│       │   ├── ollama_client.py
│       │   ├── embedding.py
│       │   ├── store.py
│       │   ├── search.py
│       │   ├── consistency.py
│       │   ├── usage_tracker.py
│       │   └── unity_import/
│       │       ├── cache_scanner.py
│       │       ├── unitypackage.py
│       │       └── remote_optin.py
│       ├── web/               # M5 — FastAPI / HTMX / Alpine.js
│       ├── mcp/
│       │   ├── server.py
│       │   └── tools.py
│       ├── platform/
│       │   ├── autostart_win.py
│       │   └── single_instance.py
│       └── config.py
└── tests/
    ├── fixtures/
    ├── test_analyzer_sprite.py
    ├── test_analyzer_sound.py
    ├── test_search.py
    ├── test_mcp_tools.py
    ├── test_updater_*.py      # M10 Phase 2
    └── test_locale_assetcache_msgid.py  # M10 Phase 3
```


## 8. 분석 파이프라인 세부

### 8.1 트리거 → 분석 흐름

```
watcher.on_event(path)
  └─> dedupe(2s window per pack root)
        ├─ new top-level dir?
        │    └─> PackIntakeTask(pack_root)
        │          ├─ pack_manager.register_pack(...)
        │          ├─ glob **/*.{png,webp,wav,ogg,mp3}
        │          └─ enqueue AssetTask per file
        │
        └─ existing pack의 파일 변경?
             └─> AssetTask(path, pack_id, kind=auto_detect_kind(path))
                   └─> analyzer.submit(task)
                         ├─ Pillow/librosa로 기술 특성 추출
                         ├─ Gemma 4 호출 (재시도 3회, 지수 백오프, 오디오는 1·2·3차 폴백 체인)
                         ├─ Pydantic으로 응답 검증
                         ├─ embedding 생성
                         └─ store.upsert(asset_id, meta, embedding)
                               ├─ fts.update(searchable_text)
                               └─ pack_manager.update_aggregate(pack_id)
```

검색 흐름은 다음과 같다.

```
[2단계 권장 흐름 — 사용자에게 팩 선택권을 주는 경우]

mcp.suggest_packs(query, project_id, kind, ...)
  ├─ project = projects.upsert(project_id)
  ├─ candidates = search.hybrid(query, filters)        # 에셋 단위 hybrid
  ├─ grouped = group_by_pack(candidates)
  ├─ for each pack:
  │    semantic_top1, semantic_mean_top3 from grouped[pack]
  │    consistency = consistency_scorer.score(project, pack)
  │    pack_score = 0.45*top1 + 0.20*mean3 + 0.25*consistency + ...
  │    pinned/blocked overrides applied
  ├─ sort packs, top N
  ├─ attach samples(top3 assets per pack) + thumbnail paths
  ├─ search_queries.insert(query, packs+top assets, query_id)
  └─ return pack list with `why` and `score_breakdown`

      ▼ Claude Code가 사용자에게 팩 선택을 요청
      ▼ 사용자가 pack_id를 고름

mcp.find_asset(query, project_id, force_pack_id=<선택>, ...)
  ├─ candidates = search.hybrid(query, filters, scope=pack)
  ├─ 통일성 가중치는 같은 팩 안에서 거의 영향 없음 → semantic/keyword 위주
  ├─ sort, top N
  └─ return results


[1단계 빠른 흐름 — 팩 선택을 생략하는 경우]

mcp.find_asset(query, project_id, ...)
  ├─ project = projects.upsert(project_id)
  ├─ candidates = search.hybrid(query, filters)
  ├─ for each candidate:
  │    consistency = consistency_scorer.score(project, asset)
  │    final = w_sem*sem + w_kw*kw + w_cons*consistency + w_rec*recency
  ├─ sort, top N
  ├─ search_queries.insert(query, results, query_id)
  └─ return results with `why` and `score_breakdown`
```

`suggest_packs`가 발급한 `query_id`는 이어지는 `find_asset`/`record_asset_use`에 그대로 전달돼 같은 쿼리 컨텍스트로 묶인다(피드백 학습용).

### 8.2 Gemma 4 호출 신뢰성

- Ollama 미기동 시: 분석 상태를 `pending`으로 두고 1분 주기로 헬스체크. GUI에는 노란 배너로 알린다.
- 응답이 JSON 파싱 실패 시: 시스템 프롬프트에 `Respond ONLY with valid JSON. No prose.`를 넣고 최대 3회 재시도. 그래도 실패면 `analysis_state='failed'`로 마킹.
- 응답 카테고리가 화이트리스트 밖이면: 가장 가까운 화이트리스트 값에 매핑하거나 `other`로 강등(원문은 `description`에 보존).
- **오디오 입력 안전망** — 1차(네이티브 오디오) 호출은 30초 wall-clock 타임아웃 + 프로세스/HTTP 에러를 모두 잡아 2차(스펙트로그램 비전)로 자동 강등한다. 이 강등은 메타에 `audio_path_used = 'native' | 'spectrogram' | 'heuristic'` 으로 기록해 추적 가능하게 한다.
- **모달리티별 토큰 비용 인지** — 오디오는 1초당 25 토큰을 소모한다([Gemma audio docs](https://ai.google.dev/gemma/docs/capabilities/audio)). 30초 클립 3개 보내면 ~2,250 토큰. E4B의 128K 컨텍스트 안에서 충분히 여유 있지만, 배치 분석 시 RAM/VRAM은 신경 써야 한다.

### 8.3 성능 가드레일

- 한 번에 Gemma 4에 보내는 이미지는 1MB 이하로 리샘플(긴 변 768px). Gemma 4가 가변 종횡비/visual token budget을 지원하므로 강제 정방형 패딩은 하지 않는다.
- 오디오 클립은 16kHz mono, 30초 이하로 제한.
- 분석 동시성은 기본 1(소비자 GPU 부담 고려), 설정에서 조절 가능.
- 큐 길이가 임계(예: 500개) 넘으면 트레이 알림.


## 9. 보안 / 프라이버시 / 운영

- 모든 데이터는 **로컬**에만 머문다. 사용자가 명시적으로 비활성화하지 않는 한 어떤 텔레메트리도 외부로 보내지 않는다.
- Ollama 엔드포인트도 기본은 `http://127.0.0.1:11434`. 원격 Ollama를 쓰려면 설정에서 변경하고, 그 경우 GUI 설정 화면에 "에셋 이미지가 외부 서버로 전송됩니다" 경고를 띄운다.
- 로그(`assetcache.log`)는 회전 핸들러로 10MB × 5개 한정.
- 단일 인스턴스 보장: `%APPDATA%/AssetCacheMCP/assetcache.lock` 파일 lock으로 중복 실행 방지. 두 번째 실행은 트레이의 기존 인스턴스에게 "show window" IPC만 보내고 종료.


## 10. 기술 스택 / 의존성

| 영역 | 선택 | 비고 |
|---|---|---|
| 언어 | Python 3.10+ | `match`/타입힌트 활용. `tomllib`는 3.11+ 표준, 3.10에서는 `tomli` 백포트 사용 |
| MCP | `mcp` (공식 SDK) | stdio + SSE |
| GUI | `PySide6` | 트레이, 윈도우 |
| 이미지 | `Pillow`, `numpy` | 픽셀아트 판정 등 |
| 오디오 | `librosa`, `soundfile` | mel-spectrogram 포함 |
| 파일 감시 | `watchdog` | NTFS USN 기반 |
| LLM | `httpx` + Ollama REST | `gemma4:e4b` 기본 (이미지+오디오), `gemma4:e2b` 폴백. 클라이언트는 OpenAI 호환 `/v1/chat/completions` 우선 + Ollama 네이티브 `/api/chat` 폴백 (§4.2.4) |
| 임베딩 | Ollama `nomic-embed-text` | 검색용 의미 벡터 |
| 라벨 스코어러 | `open_clip_torch` + `torch` | CLIP zero-shot 으로 라벨 화이트리스트별 객관 0~1 점수. M2 도입 (이미지 전용, 사운드 라벨링은 Gemma) |
| DB | `sqlite3` (표준) | FTS5, JSON1 사용 |
| 검증 | `pydantic v2` | LLM 응답 |
| 패키징 | `pyinstaller` or `briefcase` | 단일 exe |
| 자동시작 | `winreg` (표준) | `HKCU\...\Run` |
| 테스트 | `pytest`, `pytest-asyncio` | |


## 11. 개발 로드맵 (제안)

### Milestone 0 — 뼈대 (1주)
- 프로젝트 스캐폴딩, `pyproject.toml`, 로깅, 설정 로딩, 단일 인스턴스 보장.
- 비어 있는 트레이 앱이 뜨고 종료된다.

### Milestone 1 — 워처 + Pack Manager + DB (1.5주)
- 폴더 감시, 팩 단위 디바운스, SQLite 스키마 생성, 부팅 시 풀스캔 diff.
- `pack.json` 파싱, 벤더 휴리스틱, 팩 단위 enable/disable.
- GUI 팩 탭과 라이브러리 탭(메타 없이 단순 리스트).

### Milestone 2 — 분석 파이프라인 (3주, 2026-05-16 CLIP 편입으로 +1주)
- Pillow/librosa 기술 특성.
- Ollama 클라이언트 + Gemma 4 멀티모달 호출 (이미지 입력 우선). **Gemma 라벨링은 많은 라벨 + 이산 가중치 3단계**(`primary`/`secondary`/`tertiary`) JSON 으로.
- 사운드 네이티브 오디오 경로 + 스펙트로그램 폴백 + 휴리스틱 최후 폴백 체인 (사운드는 Gemma only).
- **CLIP zero-shot 라벨 스코어러** — `open_clip` (또는 transformers CLIPModel) + PyTorch 도입. 라벨 화이트리스트(100~300개) 텍스트 임베딩 사전 계산 + 이미지당 라벨별 0~1 점수 산출.
- DB 새 테이블 `asset_labels(asset_id, label, score REAL, source)` — `source` 는 `'gemma'`/`'clip'`/`'user'`.
- Pydantic 검증, 영어 enum 화이트리스트, 자연어 description 호출 언어(기본 `ko`).
- 임베딩 생성 및 저장 (`nomic-embed-text`).
- GUI 문자열 일괄 `tr()` 래핑(M6 i18n 준비).

### Milestone 3 — 검색 백엔드 + 통일성 + MCP (2주)
- FTS5 + 벡터 코사인 + 라벨 점수 결합 검색.
- Consistency Scorer, Usage Tracker (명시 + 암묵 top-1 추정).
- MCP 서버(stdio) `find_asset`(project_id 포함), `get_asset`, `list_assets`, `list_packs`, `record_asset_use`, `set_project_pin`, `request_rescan`.
- GUI 라이브러리 탭은 **최소 동작**(쿼리 박스 + 결과 그리드 + 팩 드롭다운)만. 풍부 UX 는 M4 책임.
- Claude Code에서 실제로 붙여 보고 프롬프트 튜닝. 같은 프로젝트에서 여러 번 요청해 팩이 점점 굳는지 검증.

### Milestone 4 — 검색 UX (라이브러리 탭 풍부화) (1.5주, 2026-05-16 신설, 2026-05-17 완료)
**완료 항목**:
- `core/label_query.py` — `AND`/`OR`/`NOT` 대문자 키워드 + `()` 그룹 + `axis:label` + bare label 자동 매칭 파서. 순수 AND 또는 순수 OR 만 정확 매핑 (혼합은 `UnsupportedExpression`).
- `HybridSearcher` 6 채널 확장 — semantic 0.35 / keyword 0.10 / label 0.20 / consistency 0.20 / recency 0.05 / **feedback 0.10** (합 1.00).
- `diversity` 옵션 — `none` (M3 호환) / `mmr` (λ=0.7 권장) / `round_robin`.
- `saved_searches` 테이블 + 4 MCP 신규 도구 (`save_search`/`list_saved_searches`/`delete_saved_search`/`run_saved_search`) — MCP 총 12 → 16.
- `feedback_records` 테이블 + signed weight 페널티 학습 — asset-level + pack-level (≥3 negative → -0.1).
- `suggest_packs.samples` 풍부화 — sprite `thumbnail_path` (lazy 256×256 PNG) + `preview_blurb` (top-2 라벨).
- GUI 라이브러리 탭 — `LabelChipPanel` (24 axis 칩 + AND/OR/NOT 라디오) + `SearchSidePanel` (6 슬라이더 + 3 프리셋 + 저장된 검색) + `FilterBar` (pack 다중 + kind/state/license/vendor + 정렬).
- 모든 신규 GUI 문자열은 `tr()` 래핑 (M7 i18n 준비).

**M7 (또는 M5+) 으로 미룬 항목**:
- 그리드 ↔ 리스트 뷰 토글 / hover 미리보기 / 사운드 인라인 재생 / 결과 비교 보기 / 키보드 단축키 — GUI 마감 (M7) 의 범위.
- `cleanup_feedback_records` 잡 (윈도우 만료 행 정리) — v1 은 검색 시 윈도우 필터만.
- `label_query` 한국어 키워드 (`그리고`/`또는`/`제외`) — v1 영어만. 사용자 피드백 기반 결정.
- `label_query` 혼합 AND/OR (OR-of-AND DNF) — v1 순수형만.
- Gemma description 통합한 풍부 `preview_blurb` — v1 은 top-2 라벨만. `assets.description` 컬럼 추가가 선행 필요.

### Milestone 5 — 웹 GUI 전환 + 라이브러리 리디자인 + Claude pick 인터랙션 (5.5주) ✅ 완료 (2026-05-18)

**배경** — M4 의 사용자 GUI 검증 후 4 페인(정보 과부하 / 좌우 스크롤 가림 / 섹션 불명 / 가중치 불가해) + Claude → AssetCacheMCP 사용자 선택 인터랙션 요구를 동시 해결.

**핵심 산출물**:
- Qt 데스크톱 UI 전면 폐기 → FastAPI + HTMX + Alpine.js 로컬 웹 UI (포트 9874). `src/assetcache/ui/` 8 파일 삭제 완료.
- 라이브러리 페이지 — 자연어 검색 바 + ⚙ 사이드 패널 (B/C/D 탭) + 카드 그리드/리스트 + 상세 모달 + 사운드 인라인 재생.
- Pack 관리 페이지 (`/packs`) + 라벨 admin 페이지 (`/labels/admin`).
- MCP 17번째 도구 `request_user_pick` — SSE push + 브라우저 보라색 pick 카드 + 자동 `record_asset_use(source="claude_pick")`.
- TrayBridge(QObject) — uvicorn→Qt 시그널 안전 디스패치 + 트레이 툴팁 갱신.

**Phase 요약**:

| Phase | 핵심 내용 | 누적 테스트 |
|---|---|---|
| 0 (의존성/Config/vendoring) | fastapi/uvicorn/jinja2/sse-starlette + HTMX/Alpine vendoring | 506 |
| 1 (FastAPI 스캐폴딩 + WebServer + SSE bus) | build_app, uvicorn 별 스레드, 포트 폴백, PendingPickQueue, SSE bus | 506 |
| 2 (라이브러리 페이지) | 검색/결과/카드/모달/사운드/페이지네이션 | 506 |
| 3 (사이드 패널 B/C/D) | B 탭 (라벨/다축 필터) + C 탭 (표시 옵션) + D 탭 (프리셋/슬라이더/저장된 검색/통일성) + 반응형 | 692 |
| 4 (request_user_pick + SSE) | MCP 17도구 + SSE pick 카드 + TrayBridge + MCP_USAGE_GUIDE 갱신 | 746 |
| 5 (Pack/라벨 admin + Qt 폐기) | `/packs` + `/labels/admin` + Qt UI 8 파일 + 폐기 테스트 7 파일 삭제 | 783 |
| 6A (에러 페이지 + 다크모드) | 404/500 커스텀 페이지 + M5_verification.md | 796 |
| 6B (문서 마감) | WEB_UI_GUIDE.md + DESIGN.md/README.md/CLAUDE.md/HANDOFF.md 갱신 | 796 |

**M5가 다음 마일스톤으로 미룬 항목**:
- 다크/라이트 모드 수동 토글 버튼 — M8
- 모바일/태블릿 최적화 — M8
- Playwright E2E 테스트 — M8
- Pack/라벨 페이지 내 검색 기능 — v2
- `_card_list.html` cardMeta x-show 바인딩 (현재 와이드 카드만) — v2
- 새 axis 추가 UI — v2
- 슬라이더 설정 영속화 — M8

**신규 의존성** — `fastapi>=0.110`, `uvicorn[standard]>=0.27`, `jinja2>=3.1`, `python-multipart>=0.0.9`, `sse-starlette>=2`, `httpx`. 정적 JS는 `src/assetcache/web/static/vendor/` vendoring.

**spec**: [`docs/superpowers/specs/2026-05-17-m5-web-gui-and-library-redesign.md`](./docs/superpowers/specs/2026-05-17-m5-web-gui-and-library-redesign.md)

### Milestone 6 — 시트 분석 + 애니메이션 (1주) ✅ 완료

- 격자 자동 분할, Aseprite/TexturePacker JSON 지원.
- `suggest_animation_frames` 도구 (17 → 18).
- 와이드/리스트 카드 우상단에 `🎞 N frames` 배지.
- v1 알려진 한계: 알파 없는 시트는 JSON 사이드카 필수, 비균일 atlas v2.

### Milestone 7 — Unity Asset Store 임포트 (1주, 기존 M6) ✅ 완료 (2026-05-18)
- 캐시 경로 자동 검출(환경변수 + Preferences 폴백) + 사용자 오버라이드.
- `.unitypackage` 파서, 선택적 추출(이미지/사운드만), 매니페스트 자동 생성.
- 증분 동기화, `unity_imports` 테이블(preview 컬럼 4개 + first_seen_at + last_scanned_at 포함), 2 MCP 도구(`scan_unity_asset_store_cache` + `list_unity_packages`).
- 웹 UI 의 Unity Asset Store 페이지 (미리보기/임포트/건너뜀/되돌리기).
- 활성 프로젝트 + 프로젝트 페이지 + 자산별 선호도 (§4.10).
- 비공식 publisher 패널 경로는 스켈레톤만(기본 비활성), 안정성 모니터링 후 별도 마일스톤에서 본 구현.
- **신규 의존성 없음**. 1011 passed (baseline 887 + 신규 +124).

### Milestone 8 — 패키징 + i18n (1주) ✅ 완료 (2026-05-19)

- Babel gettext (`ko`/`en`) — `_t()` + LocaleMiddleware 5단계 (URL > 쿠키 > Config > Accept-Language > ko), 159건 msgid 영어화, ko.po + en.po + .mo 컴파일.
- `/settings` 페이지 — 언어 라디오 + 다크모드 토글, `POST /api/settings`.
- 다크/라이트 모드 수동 토글 (Alpine + localStorage + `data-theme`) — M5 의 자동 모드에서 수동 추가.
- Windows autostart — `winreg HKCU\...\Run` + 트레이 메뉴 체크박스 + `/api/autostart` endpoint.
- PyInstaller `--onefile` 빌드 (`assetcache.spec`, M8 까지는 `gah.spec`) — CLIP 가중치 포함, `dist/AssetCacheMCP.exe` (M8 까지는 `dist/GameAssetHelper.exe`). exe 연기 시 첫 실행 자동 다운로드 폴백. M10 부터 PyPI 가 1차 배포 채널이고 exe 는 2차.
- **신규 의존성**: `Babel>=2.14` (런타임), `pyinstaller>=6` (dev). **1046 passed** (baseline 1002 + M8 +44).

**v2 로 미룬 항목**:
- Pack/프로젝트 탭 풍부 UX (메타 수정, manual_override, 프로젝트 pin/block, 사용 분포 차트)
- Playwright E2E, 모바일 최적화, 추가 언어 (ja/zh), MSI/NSIS 인스톨러, 트레이 알림, 자동 동기화 스케줄러
- 코드 서명 (M9 implementation `feat/m9` 에 보존, PyPI 채택으로 머지 보류)

### Milestone 10 — PyPI 배포 + AssetCacheMCP rename ✅ (2026-05-20 완료)

**배경** — v0.0.1 GitHub release (`GameAssetHelper.exe` 323MB) 의 SmartScreen 차단 + Mac/Linux 사용자 + 비용 최소화 관점에서 **PyPI 1순위** + 앱 rename 결정.

**핵심 산출물 (Phase 0~5 완료)**:
- **Phase 0** — rename mechanical: `Game Asset Helper` → `AssetCacheMCP`, `gah` → `assetcache`, `src/gah/` → `src/assetcache/`, 모든 import / config 키 / babel.cfg / spec / docs 경로 갱신
- **Phase 1** — 마이그레이션 helper (v0.0.1 compat): `migration/detect.py` + `migration/migrate.py` (copy/move + `.migrated_from_v001` idempotent 마커) + 웹 배너 + SSE 진행률 + CLI `--migrate=copy|move` + i18n msgid 10건

  > **2026-05-20 후기 (v0.1.1)**: Phase 1 의 v0.0.1 데이터 폴더 마이그레이션 helper 는 v0.1.1 (`chore/v011-yagni-clean`) 에서 yagni-clean 됐다. v0.0.1 외부 사용자·다운로드 0 확인 후, 관련 코드 + 테스트 + i18n msgid + 문서 안내 일괄 제거. 본 문서의 Phase 1 본문은 historical record 로 보존.

- **Phase 2** — PyPI 알림 (M9 cherry-pick): `updater/version.py` + `updater/checker.py` (PyPI JSON API + 캐시) + `updater/pip_command.py` (pipx/uv/pip 환경 분기) + `web/routers/updates.py` 단순화 + `_pypi_update_banner.html` + tray 동적 메뉴 + Qt Signal cross-thread + i18n msgid 4건
- **Phase 3** — docs 일괄 갱신 (README/CLAUDE/HANDOFF/DESIGN) + i18n catalog 정합성 test (5 msgid × 2 lang) + `milestones/M10_verification.md` 수동 검증 시나리오 7건
- **Phase 4** — `pyproject.toml` 최종 확정 + `assetcache-mcp` console_script entry point + `python -m build` (sdist + wheel) + TestPyPI 업로드 + 정식 PyPI 업로드 + GitHub Actions workflow (Node.js 24 호환)
- **Phase 5** — 최종 문서 정정 (v0.0.1 compat 안내 제거 from live docs)

**최종 누적**: **1103 passed + 1 skipped + 40 deselected** (baseline 1046 + M10 +57). **MCP 20 도구 그대로**, 신규 의존성 0. **PyPI v0.1.0 publish 완료** ([Latest](https://pypi.org/project/assetcache-mcp/0.1.0/)), **Trusted Publishing (OIDC) 활성** → 향후 tag push 한 줄로 자동 publish.

**M9 retain/drop**: version / checker / web banner / tray Signal 재사용 (Phase 2). Installer / swap / `--complete-update` / SignPath 신청은 drop (PyPI 흐름에서 `pipx upgrade assetcache-mcp` 가 대체).

**plan**: [`docs/superpowers/plans/2026-05-19-m10-pypi-and-rename.md`](./docs/superpowers/plans/2026-05-19-m10-pypi-and-rename.md)

총 v1 일정 ≈ 17.5주 (M2 CLIP +1주 + M4 검색 UX +1.5주 + M5 웹 GUI +5.5주). M5는 2026-05-18 완료. M10 (M9 후속, PyPI rename) 는 2026-05-19 in-flight. 각 마일스톤 끝에 Claude Code에서 직접 써보며 검증한다.


## 12. 열린 질문 / 결정 보류

1. **시트 메타데이터 입력 UX** — JSON이 없는 시트는 자동 분할 실패 가능성이 있다. 사용자가 frame size를 입력하는 다이얼로그를 매번 띄울지, 일괄 처리 큐로 모아둘지.
2. **임베딩 차원 선택** — `nomic-embed-text`는 768. 라이브러리가 작으면 굳이 임베딩 없이 FTS만으로도 충분할 수도 있다. 임베딩 on/off 토글이 필요할지 v1에서 정한다.
3. **에셋 라이선스 필드** — 메타에 `license`, `source_url` 같은 자유 필드를 두긴 하지만, MCP 응답에 포함해서 Claude Code가 라이선스 표기를 권유하게 할지.
4. **GUI 언어 / 모델 출력 언어** — 결정(2026-05-16): **모델 출력은 M2 부터 듀얼 구조**(정규 enum 영어 고정 + 자연어 description 호출 언어). v1 기본 description 언어는 한국어. **GUI Qt i18n 은 M6 마감에서 도입** — `.ts/.qm` 파일 + `Config.ui_language`(`"ko"`/`"en"`/`"auto"`) 필드. M2~M5 의 GUI 문자열은 한국어 그대로 두되 사용자 노출 문자열을 모두 `tr("...")` 으로 감싸 두면 M6 작업이 단순 번역 추가로 끝난다.
5. **사운드 의미 라벨 정확도** — Gemma 4 네이티브 오디오 경로의 실제 분류 정확도(특히 SFX vs BGM, 분위기 다중 라벨)를 측정해보고, 부족하면 v2에서 CLAP/PANNs 같은 전용 오디오 임베딩 모델을 보조로 추가.
6. **Ollama 오디오 안정성 모니터링** — `gemma4:e4b` 오디오 추론 GGML assertion 이슈([ollama/ollama#15333](https://github.com/ollama/ollama/issues/15333))가 패치될 때까지 1차 경로 실패율을 메트릭으로 수집한다. 실패율이 X% 이상이면 사용자 환경에서는 자동으로 스펙트로그램 폴백을 기본 경로로 승격하는 옵션을 검토.
7. **암묵 채택의 정확도와 위험** — `record_asset_use` 명시 호출 없이 직전 응답의 top-1을 자동 채택 처리하는 휴리스틱은 잘못된 학습을 만들 위험이 있다. v1에서는 명시 호출만 신뢰하고, 암묵 추정은 옵트인으로 둔다. 시스템 프롬프트로 Claude Code에게 `record_asset_use` 호출을 강하게 권장하는 문구를 README에 정리.
8. **project_id 식별 정책** — Unity 프로젝트의 절대 경로를 그대로 쓰면 사용자가 폴더를 옮길 때 통일성 이력이 끊긴다. 대안: 프로젝트 루트의 `ProjectSettings/ProjectSettings.asset`에서 GUID를 뽑거나, `.gah-project` 빈 파일에 UUID를 적어두는 방식. v1에서는 절대 경로 + 사용자가 GUI에서 별칭 매핑 가능으로 시작.
9. **통일성과 다양성의 균형** — 한 팩으로 너무 강하게 굳으면 사용자가 "다양한 후보를 보고 싶은" 경우가 막힌다. `count > 1`일 때는 상위는 통일성 우선이지만 마지막 1~2개는 의도적으로 다른 팩에서 뽑아 보여주는 "diversity slot" 도입을 검토.
10. **팩 간 중복 검출** — 같은 Kenney 팩을 두 번 받아 폴더명만 다르게 둘 경우를 대비해 `file_hash` 기준 중복 통계를 GUI에 노출하고, 한쪽 팩 비활성화를 추천.
11. **Unity Asset Store 캐시 다중 경로** — 사용자가 회사 계정·개인 계정을 분리해 캐시 폴더를 둘 이상 운영할 수 있다. v1은 단일 경로지만 GUI에서 캐시 경로 N개를 더할 수 있게 확장하는 것을 검토.
12. **`.unitypackage` 외 형식** — Unity Asset Store에 UPM 패키지 형식(`.tgz`/scoped registry)으로 배포되는 항목이 늘고 있다. v1은 `.unitypackage`만 다루고, UPM 패키지는 v2에서 검토(이 경우 보통 프로젝트 `Library/PackageCache/`에 자리 잡으므로 캐시 출처가 다르다).
13. **비공식 publisher 패널 의존성** — `kharma_session` 기반 엔드포인트는 Unity가 언제든지 변경할 수 있다. 옵트인 모드를 켠 사용자에게는 동작 실패 시 빠르게 알리고 1차 경로(캐시 스캔)로 자연스럽게 강등되도록 설계한다.


## 13. Claude Code 에이전트 가이드라인

GAH가 Claude Code에 노출하는 MCP 도구들은 단독으로 써도 동작하지만, 다음 패턴을 따를 때 사용자 경험과 통일성이 가장 좋다. 이 가이드라인은 README와 MCP 서버의 `instructions` 필드에 같은 내용을 적어 클라이언트가 자동 인지하도록 한다.

### 13.1 표준 워크플로 (권장)

1. **세션 시작 시** — 사용자가 새 Unity 프로젝트 작업을 시작하면 Claude Code는 그 프로젝트 절대 경로(또는 사용자 별칭)를 `project_id`로 정해두고, 이후 모든 호출에 그대로 전달한다. 가능하면 한 번 `list_packs`로 카탈로그 개요를, `get_asset`이나 `suggest_packs(query=null, project_id)`로 이 프로젝트의 사용 이력 요약을 미리 받아둔다.
2. **에셋 요청이 들어오면 — 팩 선택 단계** — 사용자가 "어두운 동굴 BGM 깔아줘" 같은 요청을 하면 Claude Code는 먼저 `suggest_packs(query, project_id, kind)`를 호출한다. 응답의 상위 N개 팩을 사용자에게 다음 형태로 제시한다.

   - 팩 이름과 한 줄 설명
   - 라이선스 (특히 CC0/Free vs 유료)
   - 이 프로젝트에서 이미 몇 번 채택했는지
   - 매칭 후보 수와 샘플 2~3개 (썸네일/미리듣기 가능하면 함께)
   - GAH가 적어준 `why` (왜 추천했는지)

   사용자가 명시적으로 "그냥 알아서 골라줘"라고 하거나, 응답에 `pinned_pack_id`가 있거나, 점수 1위 팩이 2위 대비 매우 우세할 때(예: `score` 격차 0.2 초과)에는 이 단계를 건너뛰어도 된다.
3. **에셋 선택 단계** — 사용자가 팩을 고르면 `find_asset(query, project_id, force_pack_id=<선택한 팩>, count=N)`. 사용자가 팩 선택을 생략하면 `force_pack_id` 없이 호출. 두 경우 모두 같은 `query_id`를 이어붙이는 게 권장이다(없으면 GAH가 새로 발급).
4. **채택 직후** — Claude Code가 결정한 에셋 파일을 Unity 프로젝트의 `Assets/` 폴더로 복사한 직후, **반드시** `record_asset_use(project_id, asset_id, query_id, context)`를 호출한다. 이 호출이 다음 추천의 통일성을 만든다. 호출을 빼먹으면 같은 프로젝트에서도 매번 팩이 흔들린다.
5. **사용자가 결과를 거절했을 때** — `report_feedback(query_id, asset_id, reason)`을 호출. 다음 검색에서 그 에셋과(필요하면 팩)에 페널티가 들어간다.

### 13.2 사용자 경험 예시 (Claude Code 측 응답 톤)

> 사용자: 메인 메뉴 BGM 하나 깔아줘.
>
> Claude Code (suggest_packs 호출 후): "GAH에서 어울리는 팩 3개를 찾았어요. 어떤 걸 쓰실래요?
>   1. **Kenney Audio Pack** (CC0) — 이 프로젝트가 이미 12회 채택. 매칭 4개. 샘플: `menu_loop_calm.ogg`, `title_theme.ogg`
>   2. **Free Music Vol.3** (CC-BY) — 매칭 6개. 좀 더 영화적 톤. 샘플: `epic_intro.mp3`
>   3. **My Custom BGM** (사용자 폴더) — 매칭 1개. 샘플: `myhand_theme.wav`
>
>   1번이 통일성 측면에서 가장 자연스럽습니다. 어떻게 할까요?"

이런 형태로 정리해 보여주면, 사용자는 한 번의 선택으로 통일성·라이선스·청취감 세 가지를 동시에 결정한다.

### 13.3 안티패턴

- `record_asset_use` 미호출 — 통일성 신호가 누적되지 않음.
- `project_id` 누락 — 모든 요청이 글로벌 비프로젝트 풀로 계산돼 통일성이 사라짐.
- `suggest_packs` 없이 매번 `find_asset` 단독 — 사용자에게 선택 기회가 사라지고, Claude Code가 자의적으로 팩을 바꿔버릴 위험이 있음. 첫 요청과 강한 굳음 상태에서는 괜찮지만, 새 카테고리의 에셋을 처음 가져올 때는 반드시 팩 선택 단계를 권장.


## 14. 참고 자료

Gemma 4 관련 사실 확인에 사용한 1차 출처.

- [Gemma 4 — Google DeepMind](https://deepmind.google/models/gemma/gemma-4/) — 모델 패밀리 소개
- [Gemma 4 model overview | Google AI for Developers](https://ai.google.dev/gemma/docs/core) — E2B/E4B/26B/31B 사양, 컨텍스트 윈도우
- [Audio understanding | Gemma | Google AI for Developers](https://ai.google.dev/gemma/docs/capabilities/audio) — 오디오 입력 제약(30초, 25 tokens/sec, mono)
- [Welcome Gemma 4: Frontier multimodal intelligence on device — Hugging Face](https://huggingface.co/blog/gemma4) — 멀티모달 능력 개요
- [gemma4:e4b · Ollama](https://ollama.com/library/gemma4:e4b) — Ollama 라이브러리 모델 페이지
- [ollama/ollama#15333 — Gemma 4 E4B intermittent GGML assertion crash during audio inference](https://github.com/ollama/ollama/issues/15333) — 알려진 오디오 추론 안정성 이슈
- [Google Pushes Multimodal AI Further Onto Edge Devices with Gemma 4 — Edge AI and Vision Alliance (2026-04)](https://www.edge-ai-vision.com/2026/04/google-pushes-multimodal-ai-further-onto-edge-devices-with-gemma-4/) — 공개일 및 엣지 디바이스 배포 맥락

Unity Asset Store 임포트 관련 1차 출처.

- [Unity Manual — Asset Store 개요](https://docs.unity3d.com/Manual/AssetStore.html) — 공식 사용 흐름
- [Unity Manual — Customize the Asset Store cache location](https://docs.unity3d.com/Manual/upm-config-cache-as.html) — 캐시 경로 및 `ASSETSTORE_CACHE_PATH` 환경변수
- [UnityCommunity wiki — Move Unity caches and asset store files](https://github.com/UnityCommunity/UnityLibrary/wiki/Move-Unity-caches-and-asset-store-files-into-another-drive) — 캐시 디렉터리 구조 보충
- [UnityAssetstoreAPI (비공식, C#)](https://github.com/se0kjun/UnityAssetstoreAPI) — `kharma_session` 기반 비공식 API 참조 구현
- [unity-asset-store-api (비공식, JS/npm)](https://www.npmjs.com/package/unity-asset-store-api) — 비공식 엔드포인트 동일 패턴
- [Unity Discussions — Automating the download and import of assets](https://discussions.unity.com/t/automating-the-download-and-import-of-assets-bought-on-assetstore/819926) — 공식 API 부재 확인
