# LIVE 검증용 격리 data-dir 트레이 부팅 헬퍼.
#
# prod `%APPDATA%\AssetCacheMCP\config.toml` (API key / backend chains / 가중치 /
# 언어 / 테마 등 모든 설정) 만 fresh data-dir 로 복사 → 사용자 실 DB·라이브러리 안
# 건드리고 매번 설정 재입력 없이 트레이 부팅.  라이브러리 / metadata.db 는 격리.
#
# 사용:
#   .\scripts\launch-tray-test.ps1 clip-fix
#   .\scripts\launch-tray-test.ps1 mood-live
#
# data-dir 위치: `$env:TEMP\assetcache-test-<scenario>-data`.  같은 scenario 이름으로
# 다시 부르면 이전 데이터 그대로 계속 사용 (config.toml 만 prod 최신으로 덮어씀).
# scenario 완전 리셋은 `Remove-Item -Recurse "$env:TEMP\assetcache-test-<scenario>-data"`.

param(
    [Parameter(Mandatory)]
    [string]$Scenario
)

$ErrorActionPreference = "Stop"

$ProdConfig = "$env:APPDATA\AssetCacheMCP\config.toml"
if (-not (Test-Path $ProdConfig)) {
    Write-Error "prod config 없음: $ProdConfig — 트레이 한번 부팅해서 설정 저장 먼저 필요"
    exit 1
}

$VenvPython = "$env:USERPROFILE\.venvs\gah\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Error "venv python 없음: $VenvPython — README.md / docs/SETUP.md 의 venv 셋업 절차 확인"
    exit 1
}

$DataDir = "$env:TEMP\assetcache-test-$Scenario-data"
New-Item -ItemType Directory -Force $DataDir | Out-Null
Copy-Item $ProdConfig "$DataDir\config.toml" -Force

Write-Host "data-dir: $DataDir"
Write-Host "config: prod 에서 복사 완료 (API key / backends / chains / 가중치 유지)"
Write-Host "library: $DataDir\library (격리 — sprite asset drop 필요 시 직접 복사)"
Write-Host ""

& $VenvPython -m assetcache --tray --data-dir $DataDir
