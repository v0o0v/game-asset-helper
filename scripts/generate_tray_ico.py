"""M8 — tray._build_app_icon() 결과 QPixmap 을 ICO 로 export.

PyInstaller 빌드 사전 1회 실행:
    python scripts/generate_tray_ico.py

산출: assets/tray.ico (멀티 사이즈 16/32/48/64/256).
이 ICO 는 gah.spec 의 EXE(icon=...) 에 참조된다.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

# PySide6 가 import 필요 — 빌드 환경에서만 실행 (런타임 빌드 절차).
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from gah.tray import _build_app_icon  # noqa: E402

SIZES = (16, 32, 48, 64, 256)


def _pixmap_to_pil_exact(pixmap, target_size: int):
    """QPixmap → PIL Image (RGBA), target_size × target_size 정확한 크기.

    Qt scaled() 로 SmoothTransformation 다운/업스케일 후 PIL resize 로
    정확한 정수 크기를 보장한다.
    """
    from PIL import Image  # type: ignore[import-not-found]

    scaled = pixmap.scaled(
        target_size, target_size,
        Qt.IgnoreAspectRatio,   # 정사각형 원본이므로 IgnoreAspectRatio 사용
        Qt.SmoothTransformation,
    )
    img = scaled.toImage().convertToFormat(QImage.Format_RGBA8888)
    buf = img.bits().tobytes()
    pil = Image.frombuffer(
        "RGBA", (img.width(), img.height()), buf, "raw", "RGBA", 0, 1
    )
    # PIL resize 로 정확한 크기 보장 (Qt 고DPI 환경에서 +1 오프셋 방지)
    if pil.size != (target_size, target_size):
        pil = pil.resize((target_size, target_size), Image.Resampling.LANCZOS)
    return pil


def main() -> None:
    app = QApplication.instance() or QApplication([])
    _ = app  # keep ref
    icon = _build_app_icon()

    out_dir = REPO_ROOT / "assets"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "tray.ico"

    # 원본 QPixmap 은 64×64. icon.pixmap(64, 64) 으로 원본 추출.
    # 각 target_size 로 정확히 스케일 후 PIL ICO 로 멀티 사이즈 저장.
    source_pm = icon.pixmap(64, 64)

    try:
        from PIL import Image  # type: ignore[import-not-found]

        # 각 사이즈별 PIL Image 생성 (정확한 NxN 보장)
        pil_images: list = [_pixmap_to_pil_exact(source_pm, s) for s in SIZES]

        # Pillow _save 는 "if size[0] > width" 체크에서 첫 이미지(im) 의 width 를
        # 기준으로 사용 — 첫 이미지보다 큰 사이즈는 skip 됨.
        # 따라서 가장 큰 이미지(256×256) 를 primary 로, 나머지를 append_images 로.
        # sizes= 에는 모든 타겟 사이즈 포함.
        largest = pil_images[-1]   # 256×256
        rest = pil_images[:-1]     # 16/32/48/64
        largest.save(
            out_path,
            format="ICO",
            sizes=[(s, s) for s in SIZES],
            append_images=rest,
        )

        # 저장 결과 확인
        saved = Image.open(out_path)
        saved_sizes = sorted(saved.ico.sizes())
        print(f"ICO written: {out_path}")
        print(f"  sizes: {saved_sizes}")
        import os
        print(f"  file size: {os.path.getsize(out_path):,} bytes")

    except ImportError:
        # Pillow 없을 때 폴백 — 단일 256 사이즈만 (Qt native ICO 저장)
        pm = source_pm.scaled(256, 256, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        pm.save(str(out_path), "ICO")
        print(f"ICO written (fallback, single-size 256): {out_path}")


if __name__ == "__main__":
    main()
