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
EXIT_USAGE = 64


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="assetcache")
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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    # --version 도 data-dir 우선순위(--data-dir > GAH_DATA_DIR > platformdirs)
    # 를 트리거하고 config 를 보장한다 (M3 회귀: 이전엔 --mcp 빠른 exit 으로 검증).
    paths = default_app_paths(args.data_dir)
    paths.ensure_dirs()
    config = load_config(paths.config_path)

    if args.version:
        print(f"assetcache-mcp {__version__}")
        return EXIT_OK

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


def main_mcp(argv: list[str] | None = None) -> int:
    """`assetcache-mcp` console script — 직접 MCP stdio 진입.

    `pyproject.toml` 의 `[project.scripts]` 에서 `assetcache-mcp` 엔트리가
    이 함수를 호출한다. 인자는 무시하고 `main(["--mcp"])` 로 forwarding 해서
    MCP stdio 서버 모드로 진입한다 — Claude Code 가 child process 로
    spawn 할 때 추가 인자 없이 즉시 stdio 핸드셰이크 가능.
    """
    return main(["--mcp"])


if __name__ == "__main__":
    raise SystemExit(main())
