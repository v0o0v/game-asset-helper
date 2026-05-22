"""스프라이트시트 분석 진단 — kind / sprite_meta / animation labels."""

import os
import sqlite3

db_path = os.path.join(
    os.environ["TEMP"], "assetcache-test-m11-10-live-data", "metadata.db"
)
conn = sqlite3.connect(db_path)
c = conn.cursor()


def dump(label, sql, params=()):
    print(f"=== {label} ===")
    for r in c.execute(sql, params):
        print(r)
    print()


dump("kind 분포",
     "SELECT kind, COUNT(1) FROM assets GROUP BY kind")

dump("spritesheet asset 별 sprite_meta",
     "SELECT a.id, a.path, sm.frame_w, sm.frame_h, sm.frame_count, "
     "       CASE WHEN sm.animations_json IS NULL THEN 'NULL' "
     "            ELSE SUBSTR(sm.animations_json, 1, 80) END AS anim_preview "
     "FROM assets a JOIN sprite_meta sm ON sm.asset_id = a.id "
     "WHERE a.kind = 'spritesheet' ORDER BY a.id")

dump("spritesheet asset 의 animation 라벨 카운트",
     "SELECT a.id, a.path, COUNT(l.label) AS anim_label_count "
     "FROM assets a "
     "LEFT JOIN asset_labels l ON l.asset_id = a.id AND l.axis = 'animation' "
     "WHERE a.kind = 'spritesheet' GROUP BY a.id "
     "ORDER BY anim_label_count, a.id")

dump("spritesheet 인데 sprite_meta 없음 (검증 누락)",
     "SELECT a.id, a.path FROM assets a "
     "LEFT JOIN sprite_meta sm ON sm.asset_id = a.id "
     "WHERE a.kind = 'spritesheet' AND sm.asset_id IS NULL")

dump("sprite_meta 에 frame_count NULL 인 spritesheet (sheet detect 실패)",
     "SELECT a.id, a.path FROM assets a "
     "JOIN sprite_meta sm ON sm.asset_id = a.id "
     "WHERE a.kind = 'spritesheet' AND sm.frame_count IS NULL")
