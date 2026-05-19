"""`python -m assetcache --migrate=copy|move` 헤드리스 마이그레이션 CLI 테스트.

CLI 흐름이 detect_v001_candidate 호출 → MigrationRunner.run → 마커/path
rewrite 까지 한 호출에 완성되는지를 main() 직접 호출 + capsys 캡처로 검증.
subprocess 까지 가지 않는다 (분 단위 분석 큐가 없고, 실행 빠름).
"""
from __future__ import annotations

from pathlib import Path

from assetcache.__main__ import EXIT_OK, EXIT_MIGRATION_FAILED, main


def _seed_legacy(legacy: Path) -> None:
    legacy.mkdir(parents=True)
    (legacy / "metadata.db").write_text("fake-db-bytes", encoding="utf-8")
    (legacy / "library").mkdir()
    (legacy / "library" / "pack_a").mkdir()
    (legacy / "library" / "pack_a" / "asset.png").write_bytes(b"\x89PNG" + b"\x00" * 100)
    (legacy / "config.toml").write_text(
        f'[library]\nlibrary_root = "{legacy / "library"}"\n',
        encoding="utf-8",
    )


def test_cli_migrate_copy_completes(tmp_path, capsys):
    """--migrate=copy 가 legacy → new 복사 + 마커 + config rewrite 까지 마친다."""
    legacy = tmp_path / "legacy"
    new = tmp_path / "new"
    _seed_legacy(legacy)

    rc = main([
        "--migrate=copy",
        f"--data-dir={new}",
        f"--legacy-data-dir={legacy}",
    ])

    assert rc == EXIT_OK
    captured = capsys.readouterr()
    assert "마이그레이션 시작" in captured.out
    assert "마이그레이션 완료" in captured.out

    # 복사 결과
    assert (new / "metadata.db").exists()
    assert (new / "library" / "pack_a" / "asset.png").exists()
    # 마커
    assert (new / ".migrated_from_v001").exists()
    # config.toml path rewrite (forward-slash 정규화 후 새 base 가 들어있어야)
    content = (new / "config.toml").read_text(encoding="utf-8").replace("\\", "/")
    assert str(new / "library").replace("\\", "/") in content
    # 원본 보존 (copy 모드)
    assert legacy.exists()
    assert (legacy / "metadata.db").exists()


def test_cli_migrate_no_candidate_exits_ok(tmp_path, capsys):
    """legacy 가 없으면 EXIT_OK + 안내 메시지로 즉시 종료."""
    new = tmp_path / "new"
    nonexistent_legacy = tmp_path / "does_not_exist"

    rc = main([
        "--migrate=copy",
        f"--data-dir={new}",
        f"--legacy-data-dir={nonexistent_legacy}",
    ])

    assert rc == EXIT_OK
    captured = capsys.readouterr()
    assert "마이그레이션 후보가 없습니다" in captured.out
