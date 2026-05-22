"""kind='sprite' 인데 width/height 가 시트 같은 (가로 또는 세로 N×frame) asset 찾기."""

import os
import sqlite3

db_path = os.path.join(
    os.environ["TEMP"], "assetcache-test-m11-10-live-data", "metadata.db"
)
conn = sqlite3.connect(db_path)
c = conn.cursor()

print("=== sprite kind 인데 width/height >= 2.5 또는 height/width >= 2.5 (sheet 의심) ===")
for r in c.execute(
    "SELECT a.id, a.path, sm.width, sm.height, "
    "ROUND(CAST(sm.width AS FLOAT) / sm.height, 2) AS ratio "
    "FROM assets a JOIN sprite_meta sm ON sm.asset_id = a.id "
    "WHERE a.kind = 'sprite' "
    "AND (sm.width >= sm.height * 2.5 OR sm.height >= sm.width * 2.5) "
    "ORDER BY ratio DESC LIMIT 50"
):
    print(r)

print()
print("=== sprite kind 인데 width 또는 height 가 큰 (>=400px) — sheet 가능성 있음 ===")
for r in c.execute(
    "SELECT a.id, a.path, sm.width, sm.height "
    "FROM assets a JOIN sprite_meta sm ON sm.asset_id = a.id "
    "WHERE a.kind = 'sprite' AND (sm.width >= 400 OR sm.height >= 400) "
    "ORDER BY sm.width * sm.height DESC LIMIT 30"
):
    print(r)

print()
print("=== sprite kind 전체 width/height 분포 (sample 10) ===")
for r in c.execute(
    "SELECT a.path, sm.width, sm.height FROM assets a "
    "JOIN sprite_meta sm ON sm.asset_id = a.id "
    "WHERE a.kind = 'sprite' ORDER BY a.id LIMIT 10"
):
    print(r)
