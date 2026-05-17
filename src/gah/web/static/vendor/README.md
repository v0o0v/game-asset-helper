# Vendored frontend libraries

GAH 의 웹 GUI (M5) 는 HTMX + Alpine.js 를 정적 자원으로 번들링한다. CDN 의존 없이 오프라인 사용 가능. PyInstaller 빌드 (M8) 시 wheel 안에 포함.

| 파일 | 버전 | 출처 | SHA256 |
|---|---|---|---|
| `htmx.min.js` | 1.9.12 | https://unpkg.com/htmx.org@1.9.12/dist/htmx.min.js | `449317ADE7881E949510DB614991E195C3A099C4C791C24DACEC55F9F4A2A452` |
| `htmx-sse.min.js` | 1.9.12 | https://unpkg.com/htmx.org@1.9.12/dist/ext/sse.js | `BE05B2E2265279F035271ADBEA0B72A356F20CE4DFA5870481BFE9C51B822FC1` |
| `alpine.min.js` | 3.13.10 | https://unpkg.com/alpinejs@3.13.10/dist/cdn.min.js | `FB9B146B7FBD1BBF251FB3EF464F2E7C5D33A4A83AEB0FCF21E92CA6A9558C4B` |

## 업데이트 절차

1. 버전 번호 갱신.
2. `Invoke-WebRequest` 로 새 파일 다운로드 (URL 의 버전 부분만 교체).
3. `Get-FileHash -Algorithm SHA256` 로 새 해시 추출.
4. 본 README 표 갱신 + 커밋.
