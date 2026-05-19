"""CLI entrypoint for AssetCacheMCP.

Boot order (DESIGN §4.5):
    1. parse args
    2. resolve AppPaths (--data-dir > env > platformdirs)
    3. ensure runtime directories exist
    4. load (or create) config.toml
    5. install logging
    6. acquire single-instance lock
    7. branch to tray / mcp / version
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Sequence

# PyInstaller windowed (--noconsole) 빌드는 sys.stdout / sys.stderr 가 None.
# logging.StreamHandler / uvicorn print 가 None.write() 호출 시 AttributeError
# 또는 hang 으로 부팅 차단. dev 환경 + console 빌드는 영향 없음.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115

from assetcache import __version__
from assetcache.config import default_app_paths, load_config
from assetcache.logging_setup import setup_logging
from assetcache.platform.single_instance import AlreadyRunning, SingleInstance


EXIT_OK = 0
EXIT_ALREADY_RUNNING = 0  # benign — second launch should be silent
EXIT_NOT_IMPLEMENTED = 2
EXIT_MIGRATION_FAILED = 3
EXIT_USAGE = 64


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="game-asset-helper")
    parser.add_argument("--version", action="store_true", help="버전 출력 후 종료")
    parser.add_argument("--tray", action="store_true", help="트레이 모드 (기본)")
    parser.add_argument(
        "--mcp",
        action="store_true",
        help="MCP stdio 서버 모드 — Claude Code 가 child process 로 spawn",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="런타임 데이터 디렉터리 오버라이드 (환경변수 GAH_DATA_DIR 보다 우선)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="로그 레벨 (DEBUG/INFO/WARNING/ERROR)",
    )
    parser.add_argument(
        "--migrate",
        choices=["copy", "move"],
        default=None,
        help="v0.0.1 (GameAssetHelper) 데이터 폴더를 헤드리스로 마이그레이션. "
             "copy 는 원본 보존, move 는 원본 제거.",
    )
    parser.add_argument(
        "--legacy-data-dir",
        type=Path,
        default=None,
        help="--migrate 와 함께 — legacy(구 v0.0.1) data_dir 명시. "
             "지정하지 않으면 platformdirs(GameAssetHelper) 로 자동 검출.",
    )
    return parser


def _run_migration_cli(
    paths,
    mode: str,
    legacy_override: Path | None,
) -> int:
    """헤드리스 마이그레이션 — `python -m assetcache --migrate=copy|move`.

    detect_v001_candidate 가 후보를 못 찾으면 EXIT_OK + 안내 메시지로 종료한다
    (사용자가 이미 마이그레이션 완료했거나 v0.0.1 데이터가 없는 정상 시나리오).
    legacy_override 가 주어지면 paths.legacy_data_dir 을 강제로 교체해 검출에
    사용한다 — explicit --data-dir 흐름에서 default_app_paths 가 legacy 를
    None 으로 두는 동작을 우회하기 위함.
    """
    from dataclasses import replace
    from assetcache.core.migration import (
        MigrationRunner,
        MigrationState,
        detect_v001_candidate,
    )

    if legacy_override is not None:
        paths = replace(paths, legacy_data_dir=legacy_override.expanduser().resolve())

    candidate = detect_v001_candidate(paths)
    if candidate is None:
        print(
            "마이그레이션 후보가 없습니다 — v0.0.1 데이터 폴더가 발견되지 "
            "않았거나 이미 마이그레이션이 완료되었습니다.",
        )
        return EXIT_OK

    print(
        f"마이그레이션 시작 (mode={mode}): "
        f"{candidate.source} → {candidate.target} "
        f"({candidate.total_files} 파일, {candidate.total_bytes:,} bytes)"
    )

    import asyncio
    runner = MigrationRunner()
    asyncio.run(runner.run(candidate, mode=mode))  # type: ignore[arg-type]

    if runner.state == MigrationState.DONE:
        print("마이그레이션 완료.")
        return EXIT_OK

    print(f"마이그레이션 실패: {runner.error}", file=sys.stderr)
    return EXIT_MIGRATION_FAILED


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    # --version 도 data-dir 우선순위(--data-dir > GAH_DATA_DIR > platformdirs)
    # 를 트리거하고 config 를 보장한다 (M3 회귀: 이전엔 --mcp 빠른 exit 으로 검증).
    paths = default_app_paths(args.data_dir)
    paths.ensure_dirs()
    config = load_config(paths.config_path)

    if args.version:
        print(f"game-asset-helper {__version__}")
        return EXIT_OK

    if args.migrate:
        # 헤드리스 마이그레이션 — single_instance lock 안 잡음 (1회성 단독 실행).
        # setup_logging 보다 먼저 분기 — 그래야 logs/assetcache.log 가
        # data_dir 안에 file handle 로 잡힌 상태에서 _do_transfer 의
        # rmtree(target) 가 Windows file lock 으로 깨지지 않는다.
        # 진행 출력은 stdout/stderr 만 사용 (1회성 헤드리스 흐름).
        return _run_migration_cli(paths, args.migrate, args.legacy_data_dir)

    level = getattr(logging, str(args.log_level).upper(), logging.INFO)
    setup_logging(paths.log_path, level=level)
    log = logging.getLogger("assetcache.main")
    log.info("GAH starting (version=%s, data_dir=%s)", __version__, paths.data_dir)

    if args.mcp:
        # MCP stdio 진입 — 단독 프로세스. GUI 인스턴스가 떠 있어도 OK
        # (SQLite WAL + busy_timeout=5000 + write_lock 이 동시 write 흡수).
        # single_instance 락은 안 잡음 — stdio 서버는 GUI 와 무관한 별 프로세스.
        from assetcache.mcp.server import run_stdio

        run_stdio()
        return EXIT_OK

    # Default mode: tray
    try:
        with SingleInstance(paths.lock_path):
            from assetcache.app import run_tray

            rc = run_tray(paths, config)
            log.info("GAH exiting (rc=%s)", rc)
            return rc
    except AlreadyRunning as exc:
        log.info("Another instance is already running: %s", exc)
        print(
            "AssetCacheMCP가 이미 실행 중입니다 (트레이 아이콘을 확인하세요).",
            file=sys.stderr,
        )
        return EXIT_ALREADY_RUNNING


if __name__ == "__main__":
    raise SystemExit(main())
