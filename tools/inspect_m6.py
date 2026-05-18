"""M6 수동 테스트 진단 — DB 의 시트 자산 상태 출력 + (옵션) 재분석 reset.

사용법:
    & "C:\\Users\\v0o0v\\.venvs\\gah\\Scripts\\python.exe" tools\\inspect_m6.py
    & "..." tools\\inspect_m6.py --path-like "%hero2%"
    & "..." tools\\inspect_m6.py --reset           # 재분석 트리거

출력:
  - 매칭 자산의 id, kind, analysis_state, analyzed_at, path
  - asset_labels 행 (axis/label/score/source)
  - sprite_meta 의 frame_w/h/count + animation_tags + animations_json
"""

from __future__ import annotations

import argparse
import sys

from gah.config import default_app_paths
from gah.core.store import Store

# 한국어 Windows 콘솔 (cp949) 에서도 이모지/특수문자 출력 가능하도록
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--path-like", default="%hero%",
                   help="자산 path LIKE 패턴 (디폴트 '%%hero%%')")
    p.add_argument("--reset", action="store_true",
                   help="kind='sprite' + analysis_state='pending' 으로 reset (재분석 트리거)")
    args = p.parse_args()

    paths = default_app_paths()
    store = Store(paths.db_path)
    store.initialize()
    try:
        rows = store.conn.execute(
            "SELECT id, path, kind, analysis_state, analyzed_at"
            " FROM assets WHERE path LIKE ?",
            (args.path_like,),
        ).fetchall()
        print(f"matched {len(rows)} asset(s) for pattern '{args.path_like}':")
        for r in rows:
            print(f"  id={r[0]:<4} kind={r[2]:<12} state={r[3]:<10}"
                  f" analyzed_at={r[4]}  path={r[1]}")
        print()
        for r in rows:
            aid = r[0]
            labels = store.conn.execute(
                "SELECT axis, label, score, source"
                " FROM asset_labels WHERE asset_id = ?"
                " ORDER BY axis, label",
                (aid,),
            ).fetchall()
            print(f"asset_id={aid} labels ({len(labels)}):")
            for axis, lbl, score, src in labels:
                print(f"  {axis:<12} {lbl:<12} score={score:.2f} source={src}")
            sm = store.conn.execute(
                "SELECT frame_w, frame_h, frame_count, animation_tags, animations_json"
                " FROM sprite_meta WHERE asset_id = ?",
                (aid,),
            ).fetchone()
            if sm:
                print(f"  sprite_meta:")
                print(f"    frame_w={sm[0]} frame_h={sm[1]} frame_count={sm[2]}")
                print(f"    animation_tags = {sm[3]}")
                print(f"    animations_json = {sm[4]}")
            else:
                print(f"  (sprite_meta 행 없음)")
            print()

        if args.reset and rows:
            ids = [r[0] for r in rows]
            placeholders = ",".join(["?"] * len(ids))
            with store.write_lock:
                cur = store.conn.execute(
                    f"UPDATE assets SET analysis_state='pending', kind='sprite'"
                    f" WHERE id IN ({placeholders})",
                    ids,
                )
            print(f"reset {cur.rowcount} 행 → (analysis_state=pending, kind=sprite)")
            print("다음 트레이 부팅 시 자동 재분석됨.")
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
