## 🎮 Game Asset Helper v0.0.1 — 초기 공개 빌드

Unity 게임 개발 중 Claude Code 가 보유 에셋(스프라이트, 스프라이트 시트, 사운드)을 자연어로 찾을 수 있게 해 주는 **MCP 서버 + Windows 트레이 상주 앱**의 첫 공개 빌드입니다.

### ✨ 핵심 기능

- **자연어 검색** — 의미 / 키워드 / 라벨 / 통일성 / 피드백 / 보조 6채널 하이브리드. 300ms 디바운스로 즉시 결과.
- **AI 라벨링** — Ollama Gemma 4 (`gemma4:e4b`) 가 이미지·오디오를 직접 보고 24 axis 의미 라벨 생성. CLIP zero-shot 이 객관 0-1 점수 추가.
- **통일성 유지** — 한 프로젝트에서 채택한 팩·벤더를 이후 검색에서 우선 추천.
- **Unity Asset Store 임포트** — 로컬 `.unitypackage` 캐시 자동 감지 + 선택적 임포트.
- **시트 분할 + 애니메이션** — 격자 자동 분할 + `suggest_animation_frames` MCP 도구.
- **Claude pick 인터랙션** — Claude 가 후보를 고르면 브라우저에 보라색 카드로 등장, 사용자 클릭 한 번에 채택.
- **웹 UI** — FastAPI + HTMX + Alpine.js. 라이브러리 / 팩 / 라벨 / 설정 페이지.
- **한국어 / 영어 i18n + 다크모드 + Windows 자동 시작**.
- **MCP 20 도구** — Claude Code 와 직결.

### 💻 시스템 요구사항

- **OS**: Windows 10 / 11 (64-bit)
- **디스크**: 약 4~5 GB 여유 공간
  - `GameAssetHelper.exe` ≈ 308 MB
  - CLIP 모델 가중치 ≈ 600 MB (첫 부팅 시 자동 다운로드)
  - Ollama 모델 ≈ 3.3 GB (`gemma4:e4b` 3 GB + `nomic-embed-text` 270 MB)
- **메모리**: 8 GB RAM 이상 권장
- **GPU (선택)**: NVIDIA GPU 가 있으면 PyTorch 가 자동 활용 (CUDA), 없어도 CPU 로 동작
- **외부 의존**: [Ollama](https://ollama.com) (아래 1단계 참고)

---

## 🚀 설치 (3단계)

### 1단계 — Ollama 설치 + 모델 다운로드

**1.1** [https://ollama.com/download/windows](https://ollama.com/download/windows) 에서 **OllamaSetup.exe** 다운로드 → 실행 → 설치 마법사 따라 진행.

**1.2** 설치 후 Ollama 가 시스템 트레이에 라마 🦙 아이콘으로 자동 상주합니다. (없으면 시작 메뉴에서 "Ollama" 실행)

**1.3** PowerShell 또는 명령 프롬프트를 열고 두 개의 모델을 pull:

```powershell
ollama pull gemma4:e4b
```

```powershell
ollama pull nomic-embed-text
```

다운로드 크기 합계 약 3.3 GB. 회선에 따라 5~30분.

**1.4** (선택) 설치 확인:

```powershell
ollama list
```

`gemma4:e4b` 와 `nomic-embed-text` 두 모델이 보이면 성공.

> 💡 **참고**: Ollama 가 보통 `http://127.0.0.1:11434` 에서 자동 서비스됩니다. GAH 가 같은 주소를 기본값으로 씁니다 (변경하려면 `/settings`).

### 2단계 — Game Asset Helper 다운로드 + 실행

**2.1** 이 페이지 아래 **Assets** 섹션에서 `GameAssetHelper.exe` 다운로드 (308 MB).

**2.2** ⚠️ **Windows SmartScreen 경고 회피** — 코드 서명 인증서가 아직 적용되지 않아 처음 실행 시 "**Windows에서 PC 보호**" 경고가 뜰 수 있습니다. 둘 중 하나로 해결:

- **방법 A (권장)**: 다운로드한 파일에 마우스 오른쪽 클릭 → **속성** → 하단 "**차단 해제**" 체크 → **적용**
- **방법 B**: 첫 실행 시 경고 창에서 "**추가 정보**" → "**실행**" 클릭

**2.3** `GameAssetHelper.exe` 더블 클릭. 다음 두 가지가 일어납니다:
- 시스템 트레이에 GAH 아이콘 등장
- 기본 브라우저에서 `http://127.0.0.1:9874/library` 자동 열림

**2.4** 첫 실행 시 CLIP 모델 가중치 (~600 MB) 가 `%APPDATA%\GameAssetHelper\cache\clip\` 로 자동 다운로드됩니다. **1~2분 소요**. 진행 상황은 트레이 메뉴 또는 로그 (`%APPDATA%\GameAssetHelper\logs\gah.log`) 에서 확인 가능합니다.

### 3단계 — 에셋 팩 추가 + 검색

**3.1** 탐색기에서 `%APPDATA%\GameAssetHelper\library\` 폴더 열기 (주소창에 그대로 붙여넣기).

**3.2** 에셋 팩 폴더를 통째로 드롭. 예:

```
library\
  my-character-pack\
    sprites\
      idle.png
      run.png
    sounds\
      jump.wav
  pixel-explosion-fx\
    ...
```

**3.3** 자동 인덱싱 시작 (Pillow 기술 특성 → Ollama 라벨링 → CLIP 점수). 큰 팩은 분 단위 소요.

**3.4** 웹 UI (`http://127.0.0.1:9874/library`) 에서 자연어 검색 시도:
- "주황색 폭발 이펙트"
- "픽셀 아트 횃불"
- "8비트 사운드 점프"

---

## 🤖 Claude Code (또는 Claude Desktop) 연동 (MCP)

GAH 의 진짜 가치는 Claude 가 직접 에셋을 검색·추천하는 것입니다.

**A** Claude Desktop 설정 파일 열기:
- 경로: `%APPDATA%\Claude\claude_desktop_config.json`
- 또는 Claude Desktop 메뉴 → **Developer → Edit Config**
- 파일이 없으면 새로 만들기

**B** `mcpServers` 항목에 GAH 추가 (이미 다른 mcpServers 가 있으면 그 안에 항목 추가):

```json
{
  "mcpServers": {
    "game-asset-helper": {
      "command": "C:\\Users\\<사용자명>\\Downloads\\GameAssetHelper.exe",
      "args": ["--mcp"]
    }
  }
}
```

⚠️ `command` 경로는 본인이 `GameAssetHelper.exe` 를 저장한 실제 위치로 바꾸세요. 경로 구분자는 `\\` (이중 역슬래시).

**C** Claude Desktop 완전 종료 후 재시작.

**D** 새 대화에서 다음과 같이 사용해 보세요:

| 자연어 요청 | Claude 가 호출하는 MCP 도구 |
|---|---|
| "캐릭터 점프 사운드 찾아 줘" | `find_asset` |
| "이 폭발 이펙트랑 어울리는 팩 추천해 줘" | `suggest_packs` |
| "이 스프라이트 시트의 idle 애니메이션 프레임 추려 줘" | `suggest_animation_frames` |
| (후보가 여러 개일 때) | `request_user_pick` → 브라우저에 보라색 카드 |

자세한 MCP 20 도구 사용법은 [`docs/MCP_USAGE_GUIDE.md`](https://github.com/v0o0v/game-asset-helper/blob/main/docs/MCP_USAGE_GUIDE.md).

---

## ⚙️ 트레이 메뉴 / 설정

**시스템 트레이 GAH 아이콘 우클릭**
- **메인 창 열기** — 브라우저에 라이브러리 페이지
- **윈도 시작 시 자동 실행** — 체크하면 부팅 시 GAH 자동 시작 (`HKCU\...\Run` 등록)
- **종료**

**웹 UI `/settings`** (`http://127.0.0.1:9874/settings`)
- **언어** — 한국어 / 영어 / 자동 (브라우저 따라감)
- **테마** — 라이트 / 다크 / 자동 (OS `prefers-color-scheme`)
- **Ollama URL** — 기본 `http://127.0.0.1:11434`. 다른 머신/포트로 바꿀 수 있음
- **모델 변경** — 다른 멀티모달 모델 (예: `llava`, `bakllava`) 시도 가능

---

## 🎯 Unity Asset Store 캐시 자동 임포트

이미 Unity Asset Store 에서 받아 둔 `.unitypackage` 파일이 있다면 자동 감지됩니다:

1. 웹 UI 좌측 사이드바 → **Unity 캐시** 탭
2. 발견된 `.unitypackage` 목록에서 "임포트" 버튼 클릭
3. 자동으로 `library/<vendor>__<pack>/` 형태로 풀어 인덱싱

기본 캐시 경로: `%APPDATA%\Unity\Asset Store-5.x\`. 다른 위치는 v2 지원 예정.

---

## 🐛 알려진 한계 / 트러블슈팅

| 증상 | 원인 / 해결 |
|---|---|
| SmartScreen 경고 | 코드 서명 인증서 미적용 (v2 예정). 위 2.2 안내 참고 |
| 첫 부팅 시 1~2분 멈춤 | CLIP 모델 가중치 다운로드 + Ollama cold-start. 정상 동작 |
| 라벨링이 너무 느림 | CPU 환경에서 Ollama gemma4:e4b 1 청크 ≈ 36초 (실측). GPU 있으면 5배 이상 빠름 |
| "Connection refused" 로그 | Ollama 가 실행되지 않음. 시스템 트레이에 🦙 아이콘 확인 |
| 포트 9874 점유 | 자동으로 9875~9883 중 빈 포트 선택. 실제 사용 포트는 로그에 출력 |
| 트레이 아이콘이 안 보임 | Windows 시스템 트레이 "숨겨진 아이콘" 패널 (∧ 화살표) 확인 |
| MCP 서버가 Claude 에 안 잡힘 | `claude_desktop_config.json` 의 `command` 경로 / `\\` 이중 역슬래시 확인. Claude Desktop 완전 종료 후 재시작 |
| MSI / NSIS 인스톨러 미제공 | v2 예정 (현재 단일 exe 만) |
| 자동 업데이트 미지원 | v2 예정 (수동 다운로드만) |
| 추가 언어 (ja / zh) | v2 예정 (현재 ko / en) |

문제 발생 시 로그 첨부 부탁드립니다: `%APPDATA%\GameAssetHelper\logs\gah.log`

---

## 📚 더 보기

- [`README.md`](https://github.com/v0o0v/game-asset-helper/blob/main/README.md) — 프로젝트 전체 안내
- [`docs/WEB_UI_GUIDE.md`](https://github.com/v0o0v/game-asset-helper/blob/main/docs/WEB_UI_GUIDE.md) — 웹 UI 사용법
- [`docs/MCP_USAGE_GUIDE.md`](https://github.com/v0o0v/game-asset-helper/blob/main/docs/MCP_USAGE_GUIDE.md) — MCP 20 도구 사용 예시
- [`DESIGN.md`](https://github.com/v0o0v/game-asset-helper/blob/main/DESIGN.md) — 아키텍처

---

🤖 빌드: PyInstaller 6.x `--onefile --noconsole`, Python 3.12, Windows 10
