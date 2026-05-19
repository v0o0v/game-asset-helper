"""MigrationRunner copy/move 동작 테스트."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from assetcache.core.migration import (
    MigrationCandidate,
    MigrationRunner,
    MigrationState,
)


def _make_candidate(tmp_path: Path) -> MigrationCandidate:
    source = tmp_path / "old"
    target = tmp_path / "new"
    source.mkdir()
    (source / "metadata.db").write_text("db data")
    (source / "library").mkdir()
    (source / "library" / "asset.png").write_bytes(b"\x00" * 50)
    return MigrationCandidate(
        source=source,
        target=target,
        total_files=2,
        total_bytes=58,
        has_db=True,
        has_library=True,
    )


@pytest.mark.asyncio
async def test_runner_copy_mode_copies_all_files(tmp_path):
    candidate = _make_candidate(tmp_path)
    runner = MigrationRunner()
    await runner.run(candidate, mode="copy")

    assert runner.state == MigrationState.DONE
    assert (candidate.target / "metadata.db").exists()
    assert (candidate.target / "library" / "asset.png").exists()
    assert (candidate.source / "metadata.db").exists()  # 원본 보존


@pytest.mark.asyncio
async def test_runner_move_mode_removes_source(tmp_path):
    candidate = _make_candidate(tmp_path)
    runner = MigrationRunner()
    await runner.run(candidate, mode="move")

    assert runner.state == MigrationState.DONE
    assert (candidate.target / "metadata.db").exists()
    assert not (candidate.source).exists()


@pytest.mark.asyncio
async def test_runner_creates_marker_on_success(tmp_path):
    candidate = _make_candidate(tmp_path)
    runner = MigrationRunner()
    await runner.run(candidate, mode="copy")

    from assetcache.core.migration import MIGRATION_MARKER
    assert (candidate.target / MIGRATION_MARKER).exists()


@pytest.mark.asyncio
async def test_runner_rollback_on_failure(tmp_path, monkeypatch):
    """copy 도중 실패하면 부분 파일 제거 + state=FAILED."""
    candidate = _make_candidate(tmp_path)

    def fail_copytree(*args, **kwargs):
        target = Path(args[1])
        target.mkdir(parents=True)
        (target / "partial.txt").write_text("partial")
        raise OSError("simulated disk full")

    # MigrationRunner 내부에서 shutil 을 어떻게 import 하는지에 따라 patch 대상 달라짐
    monkeypatch.setattr("assetcache.core.migration.shutil.copytree", fail_copytree)

    runner = MigrationRunner()
    await runner.run(candidate, mode="copy")

    assert runner.state == MigrationState.FAILED
    assert "simulated disk full" in runner.error
    # rollback: partial 파일 정리
    assert not (candidate.target / "partial.txt").exists() or not candidate.target.exists()


@pytest.mark.asyncio
async def test_runner_handles_ensure_dirs_pre_created_target(tmp_path):
    """AppPaths.ensure_dirs 가 만든 빈 target tree 와 충돌하지 않는다.

    실 부팅 흐름: paths.ensure_dirs() 로 data_dir + library + cache + logs 가
    미리 생성된 상태에서 detect_v001_candidate 가 candidate 를 반환하고,
    runner.run 이 호출된다. 기존 _do_transfer 는 dirs_exist_ok=False 라
    target 이 존재하면 FileExistsError 로 죽었다. copy/move 모두 검증.
    """
    # copy
    candidate = _make_candidate(tmp_path)
    candidate.target.mkdir(parents=True)
    (candidate.target / "library").mkdir()
    (candidate.target / "cache").mkdir()
    runner = MigrationRunner()
    await runner.run(candidate, mode="copy")
    assert runner.state == MigrationState.DONE, runner.error
    assert (candidate.target / "metadata.db").exists()
    assert (candidate.target / "library" / "asset.png").exists()
    # ensure_dirs 가 만든 빈 cache/ 는 사라지고 source 의 트리만 남는다
    assert not (candidate.target / "cache").exists()

    # move (별도 tmp 경로로)
    move_tmp = tmp_path / "move_case"
    move_tmp.mkdir()
    candidate2 = _make_candidate(move_tmp)
    candidate2.target.mkdir(parents=True)
    (candidate2.target / "library").mkdir()
    runner2 = MigrationRunner()
    await runner2.run(candidate2, mode="move")
    assert runner2.state == MigrationState.DONE, runner2.error
    assert (candidate2.target / "metadata.db").exists()
    assert not candidate2.source.exists()


@pytest.mark.asyncio
async def test_runner_disk_space_check(tmp_path, monkeypatch):
    """free space 부족하면 시작 전 실패."""
    candidate = _make_candidate(tmp_path)

    def fake_disk_usage(p):
        from collections import namedtuple
        DU = namedtuple("DU", ["total", "used", "free"])
        return DU(total=1000, used=999, free=1)  # free 1 byte

    monkeypatch.setattr("assetcache.core.migration.shutil.disk_usage", fake_disk_usage)

    runner = MigrationRunner()
    await runner.run(candidate, mode="copy")

    assert runner.state == MigrationState.FAILED
    assert "디스크" in runner.error or "space" in runner.error.lower()
