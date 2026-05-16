"""CLI entrypoint for Game Asset Helper.

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
import sys
from pathlib import Path
from typing import Sequence

from . import __version__
from .config import default_app_paths, load_config
from .logging_setup import setup_logging
from .platform.single_instance import AlreadyRunning, SingleInstance


EXIT_OK = 0
EXIT_ALREADY_RUNNING = 0  # benign — second launch should be silent
EXIT_NOT_IMPLEMENTED = 2
EXIT_USAGE = 64


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="game-asset-helper")
    parser.add_argument("--version", action="store_true", help="버전 출력 후 종료")
    parser.add_argument("--tray", action="store_true", help="트레이 모드 (기본)")
    parser.add_argument(
        "--mcp",
        action="store_true",
        help="MCP 서버 모드 (M3에서 활성화 예정)",
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

    if args.version:
        print(f"game-asset-helper {__version__}")
        return EXIT_OK

    paths = default_app_paths(args.data_dir)
    paths.ensure_dirs()

    config = load_config(paths.config_path)

    level = getattr(logging, str(args.log_level).upper(), logging.INFO)
    setup_logging(paths.log_path, level=level)
    log = logging.getLogger("gah.main")
    log.info("GAH starting (version=%s, data_dir=%s)", __version__, paths.data_dir)

    if args.mcp:
        log.warning("--mcp is not implemented yet (planned for M3)")
        print("MCP mode is not implemented yet (planned for M3).", file=sys.stderr)
        return EXIT_NOT_IMPLEMENTED

    # Default mode: tray
    try:
        with SingleInstance(paths.lock_path):
            from .app import run_tray

            rc = run_tray(paths, config)
            log.info("GAH exiting (rc=%s)", rc)
            return rc
    except AlreadyRunning as exc:
        log.info("Another instance is already running: %s", exc)
        print(
            "Game Asset Helper가 이미 실행 중입니다 (트레이 아이콘을 확인하세요).",
            file=sys.stderr,
        )
        return EXIT_ALREADY_RUNNING


if __name__ == "__main__":
    raise SystemExit(main())
