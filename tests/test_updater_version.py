"""M9 Task 3: semver-lite parser + comparator.

GitHub release tag 형식: "v0.0.1", "v0.0.2", "v0.1.0", "v1.0.0".
Pre-release tag ("v1.0.0-beta", "v1.0.0-rc1") 는 latest API 가 자동 제외라
파싱은 받지만 자동 업데이트 대상은 아님 (release_latest 가 stable 만 반환).
"""

from __future__ import annotations

import pytest

from assetcache.core.updater.version import Version, parse, compare


def test_parse_simple() -> None:
    v = parse("0.0.1")
    assert v == Version(major=0, minor=0, patch=1, pre=None)


def test_parse_with_v_prefix() -> None:
    assert parse("v0.0.1") == Version(0, 0, 1, None)
    assert parse("V1.2.3") == Version(1, 2, 3, None)


def test_parse_with_pre_release() -> None:
    assert parse("v1.0.0-beta") == Version(1, 0, 0, "beta")
    assert parse("v1.0.0-rc1") == Version(1, 0, 0, "rc1")


def test_parse_rejects_malformed() -> None:
    with pytest.raises(ValueError):
        parse("not-a-version")
    with pytest.raises(ValueError):
        parse("1.2")  # 세 segment 필수


def test_compare_equal() -> None:
    assert compare(parse("0.0.1"), parse("0.0.1")) == 0
    assert compare(parse("v0.0.1"), parse("0.0.1")) == 0  # v prefix normalize


def test_compare_patch_increment() -> None:
    assert compare(parse("0.0.2"), parse("0.0.1")) > 0
    assert compare(parse("0.0.1"), parse("0.0.2")) < 0


def test_compare_minor_increment() -> None:
    assert compare(parse("0.1.0"), parse("0.0.99")) > 0


def test_compare_major_increment() -> None:
    assert compare(parse("1.0.0"), parse("0.99.99")) > 0


def test_pre_release_less_than_release() -> None:
    """SemVer 표준: 1.0.0-beta < 1.0.0."""
    assert compare(parse("1.0.0-beta"), parse("1.0.0")) < 0


# ─────────────────────────────────────────────────────────────────────
# M10 Phase 2: Version.parse classmethod + ordering dunders
# checker.py 의 `Version.parse("0.1.0")` + `latest > self.current` 사용을 위해
# 추가. 모듈 레벨 parse()/compare() API 는 그대로 보존.
# ─────────────────────────────────────────────────────────────────────


def test_version_parse_classmethod() -> None:
    """Version.parse(text) classmethod 는 module-level parse() 와 동일한 결과."""
    assert Version.parse("0.0.1") == Version(0, 0, 1, None)
    assert Version.parse("v1.2.3") == parse("v1.2.3")
    assert Version.parse("v1.0.0-beta") == Version(1, 0, 0, "beta")


def test_version_ordering_dunders() -> None:
    """Version 인스턴스는 < > <= >= 비교 연산자 지원."""
    v_low = Version.parse("0.0.1")
    v_high = Version.parse("0.0.2")
    assert v_low < v_high
    assert v_high > v_low
    assert v_low <= v_high
    assert v_high >= v_low
    assert v_low <= Version.parse("0.0.1")
    assert v_low >= Version.parse("0.0.1")
    # pre-release < release (compare() 정책 그대로)
    assert Version.parse("1.0.0-beta") < Version.parse("1.0.0")
