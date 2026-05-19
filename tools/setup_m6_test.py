"""M6 (시트 분석 + 애니메이션) 수동 테스트 셋업 helper.

비균일 sprite sheet PNG 를 받아:
  1. 알파 채널 연결 구간 분석으로 프레임 박스 자동 검출
  2. 행별로 그룹화 (행 = 같은 y-range, 열 = 가로 정렬)
  3. Aseprite "Array" 형식 JSON 사이드카 생성 (frameTags 포함)
  4. `%APPDATA%\\AssetCacheMCP\\library\\<pack>\\` 에 PNG + JSON + pack.json 배치
  5. 다음 트레이 부팅 시 워처 + 분석 큐가 자동 픽업 → `kind="spritesheet"` promote
     + `🎞 N frames` 배지 + `suggest_animation_frames` MCP 응답 활성

사용법:
    & "C:\\Users\\v0o0v\\.venvs\\gah\\Scripts\\python.exe" tools\\setup_m6_test.py <PNG 경로>

옵션:
    --pack-name NAME     팩 폴더 이름 (디폴트 = PNG basename + "_pack")
    --force              기존 팩 폴더 덮어쓰기

예:
    python tools\\setup_m6_test.py D:\\Downloads\\hero.png
    python tools\\setup_m6_test.py "C:\\Users\\v0o0v\\Pictures\\hero_sheet.png" --pack-name m6_test_hero
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

# 한국어 Windows 콘솔 (cp949) 에서도 이모지 출력 가능하도록 utf-8 강제
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# 행 순서대로 매핑할 애니메이션 이름 (LabelRegistry 의 "animation" axis 와 일치)
_ROW_LABELS = [
    "idle",     # row 0
    "walk",     # row 1
    "run",      # row 2
    "jump",     # row 3
    "crouch",   # row 4
    "cast",     # row 5
    "attack",   # row 6
    "hurt",     # row 7
    "death",    # row 8 (혹시 9 행 있으면)
]


def _appdata_library_dir() -> Path:
    """%APPDATA%\\AssetCacheMCP\\library 경로 반환."""
    base = os.environ.get("APPDATA")
    if not base:
        # %APPDATA% 가 없으면 (테스트 환경 등) 사용자 홈 폴백
        base = str(Path.home() / "AppData" / "Roaming")
    return Path(base) / "AssetCacheMCP" / "library"


def _find_runs(flags: np.ndarray) -> list[tuple[int, int]]:
    """1D bool 배열에서 True 연속 구간 [(start, end_exclusive), ...] 추출."""
    runs: list[tuple[int, int]] = []
    in_run = False
    start = 0
    for i, v in enumerate(flags):
        if v and not in_run:
            in_run = True
            start = i
        elif not v and in_run:
            in_run = False
            runs.append((start, i))
    if in_run:
        runs.append((start, len(flags)))
    return runs


def detect_frames(img: Image.Image) -> list[list[tuple[int, int, int, int]]]:
    """PNG 의 알파 채널에서 프레임 박스를 검출해 [행][열] 2차원 리스트로 반환.

    각 항목은 (x, y, w, h) 픽셀 박스. 행은 y 좌표 오름차순, 열은 x 좌표 오름차순.
    """
    rgba = img.convert("RGBA")
    arr = np.asarray(rgba)
    alpha = arr[:, :, 3]
    mask = alpha > 0

    # 1. 행별 비어있지 않은 row 검출 → 연속 구간 묶음 = 한 시트 행
    row_has = mask.any(axis=1)
    row_runs = _find_runs(row_has)

    rows: list[list[tuple[int, int, int, int]]] = []
    for y0, y1 in row_runs:
        band = mask[y0:y1, :]
        col_has = band.any(axis=0)
        col_runs = _find_runs(col_has)
        frames: list[tuple[int, int, int, int]] = []
        for x0, x1 in col_runs:
            # 이 (행, 열) 구간 안에서 tight y bbox 재계산
            sub = mask[y0:y1, x0:x1]
            row_in_sub = sub.any(axis=1)
            ys = np.where(row_in_sub)[0]
            if len(ys) == 0:
                continue
            tight_y0 = y0 + int(ys[0])
            tight_y1 = y0 + int(ys[-1]) + 1
            frames.append((x0, tight_y0, x1 - x0, tight_y1 - tight_y0))
        if frames:
            rows.append(frames)
    return rows


def build_aseprite_json(
    rows: list[list[tuple[int, int, int, int]]],
    sheet_w: int,
    sheet_h: int,
    frame_duration_ms: int = 100,
) -> dict:
    """검출된 행/열 구조를 Aseprite "Array" 형식 JSON 으로 변환."""
    flat_frames: list[dict] = []
    frame_tags: list[dict] = []

    cursor = 0
    for row_idx, row in enumerate(rows):
        start = cursor
        for col_idx, (x, y, w, h) in enumerate(row):
            flat_frames.append({
                "filename": f"frame_{row_idx:02d}_{col_idx:02d}",
                "frame": {"x": int(x), "y": int(y), "w": int(w), "h": int(h)},
                "duration": frame_duration_ms,
            })
            cursor += 1
        end = cursor - 1
        if end >= start:
            label = (
                _ROW_LABELS[row_idx]
                if row_idx < len(_ROW_LABELS)
                else f"animation_{row_idx}"
            )
            frame_tags.append({
                "name": label,
                "from": start,
                "to": end,
                "direction": "forward",
            })

    return {
        "frames": flat_frames,
        "meta": {
            "app": "https://www.aseprite.org/ (synthesized by setup_m6_test.py)",
            "version": "1.0",
            "image": "(generated)",
            "format": "RGBA8888",
            "size": {"w": int(sheet_w), "h": int(sheet_h)},
            "scale": "1",
            "frameTags": frame_tags,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("png_path", type=Path, help="입력 PNG 경로")
    parser.add_argument("--pack-name", default=None,
                        help="팩 폴더 이름 (디폴트 = <basename>_pack)")
    parser.add_argument("--force", action="store_true",
                        help="기존 팩 폴더 덮어쓰기")
    parser.add_argument("--frame-duration-ms", type=int, default=100,
                        help="각 프레임의 duration (ms). 기본 100 = ~10fps")
    args = parser.parse_args(argv)

    src_png: Path = args.png_path
    if not src_png.exists():
        print(f"error: PNG not found: {src_png}", file=sys.stderr)
        return 2
    if src_png.suffix.lower() not in (".png", ".webp"):
        print(f"warning: input is not .png/.webp (got {src_png.suffix})", file=sys.stderr)

    pack_name = args.pack_name or f"{src_png.stem}_pack"
    library_root = _appdata_library_dir()
    pack_dir = library_root / pack_name

    if pack_dir.exists():
        if not args.force:
            print(f"error: pack directory already exists: {pack_dir}", file=sys.stderr)
            print(f"       use --force to overwrite", file=sys.stderr)
            return 2
        shutil.rmtree(pack_dir)
    pack_dir.mkdir(parents=True, exist_ok=False)

    # 1. PNG 복사
    target_png = pack_dir / src_png.name
    shutil.copy2(src_png, target_png)
    print(f"[1/4] PNG 복사 → {target_png}")

    # 2. 알파 분석 → 프레임 박스 검출
    img = Image.open(src_png)
    rows = detect_frames(img)
    total_frames = sum(len(r) for r in rows)
    print(f"[2/4] 프레임 검출 → {len(rows)}행 / 총 {total_frames}개")
    for i, r in enumerate(rows):
        label = _ROW_LABELS[i] if i < len(_ROW_LABELS) else f"animation_{i}"
        print(f"       행 {i} ({label}): {len(r)} 프레임")

    if total_frames < 2:
        print("error: 시트로 보이지 않습니다 (프레임 < 2). 단일 sprite 인 듯.",
              file=sys.stderr)
        shutil.rmtree(pack_dir)
        return 3

    # 3. Aseprite JSON 사이드카 생성
    data = build_aseprite_json(
        rows, sheet_w=img.size[0], sheet_h=img.size[1],
        frame_duration_ms=args.frame_duration_ms,
    )
    data["meta"]["image"] = src_png.name
    target_json = pack_dir / f"{src_png.stem}.json"
    target_json.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"[3/4] Aseprite JSON 사이드카 → {target_json}")

    # 4. pack.json 매니페스트 생성
    pack_manifest = {
        "name": "M6 Test Hero Sheet",
        "vendor": "test",
        "license": "test (internal verification only)",
        "description": "M6 마일스톤 (시트 분석 + 애니메이션) 수동 테스트용 비균일 시트",
    }
    (pack_dir / "pack.json").write_text(
        json.dumps(pack_manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"[4/4] pack.json 매니페스트 → {pack_dir / 'pack.json'}")

    print()
    print("=" * 60)
    print("M6 테스트 셋업 완료")
    print("=" * 60)
    print(f"팩 위치: {pack_dir}")
    print(f"애니메이션: {[_ROW_LABELS[i] if i < len(_ROW_LABELS) else f'animation_{i}' for i in range(len(rows))]}")
    print()
    print("다음 단계:")
    print(f"  1. python -m gah --tray  → 브라우저 자동 열림")
    print(f"  2. 라이브러리 페이지에서 '{src_png.stem}' 카드 찾기")
    print(f"     → 카드에 '🎞 {total_frames} frames' 배지 노출 확인")
    print(f"  3. 카드 클릭 → 자산 상세 모달 → asset_id 확인")
    print(f"  4. MCP 도구 호출 (예시):")
    print(f"     suggest_animation_frames(asset_id=<id>, animation='walk')")
    print(f"     → frame_indices + fps_hint 응답 확인")
    return 0


if __name__ == "__main__":
    sys.exit(main())
