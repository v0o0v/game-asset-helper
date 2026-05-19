"""semver-lite — GitHub release tag 파싱 + 비교.

GAH 의 tag 형식 (v0.0.1 / v0.0.2 / v0.1.0 / v1.0.0) 만 지원.
SemVer 완전 호환 아님. patch 까지 + 선택적 pre-release suffix 만 처리.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


_PATTERN = re.compile(
    r"^[vV]?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z][0-9A-Za-z.-]*))?$"
)


@dataclass(frozen=True)
class Version:
    major: int
    minor: int
    patch: int
    pre: str | None  # None = stable release, str = pre-release tag

    @classmethod
    def parse(cls, text: str) -> "Version":
        """module-level parse() 위임 — `Version.parse("0.1.0")` 호출 편의."""
        return parse(text)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return compare(self, other) < 0

    def __le__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return compare(self, other) <= 0

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return compare(self, other) > 0

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return compare(self, other) >= 0

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        return f"{base}-{self.pre}" if self.pre else base


def parse(text: str) -> Version:
    """Parse "v0.0.1" / "0.0.1" / "v1.0.0-beta" 형태."""
    m = _PATTERN.match(text.strip())
    if not m:
        raise ValueError(f"unrecognized version string: {text!r}")
    return Version(
        major=int(m.group(1)),
        minor=int(m.group(2)),
        patch=int(m.group(3)),
        pre=m.group(4),
    )


def compare(a: Version, b: Version) -> int:
    """-1 if a < b, 0 if equal, 1 if a > b."""
    if a.major != b.major:
        return _sign(a.major - b.major)
    if a.minor != b.minor:
        return _sign(a.minor - b.minor)
    if a.patch != b.patch:
        return _sign(a.patch - b.patch)
    # pre-release 처리: a.pre is None > a.pre is not None
    if a.pre is None and b.pre is None:
        return 0
    if a.pre is None and b.pre is not None:
        return 1  # release > pre-release
    if a.pre is not None and b.pre is None:
        return -1
    # 둘 다 pre — 사전식 비교
    assert a.pre is not None and b.pre is not None
    if a.pre < b.pre:
        return -1
    if a.pre > b.pre:
        return 1
    return 0


def _sign(n: int) -> int:
    if n > 0:
        return 1
    if n < 0:
        return -1
    return 0
