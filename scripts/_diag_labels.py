"""라벨 분포 진단 — asset 별 라벨 개수 + axis 별 카운트."""

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


dump("asset 별 라벨 개수 (오름차순)",
     "SELECT a.id, a.path, COUNT(l.label) AS label_count "
     "FROM assets a LEFT JOIN asset_labels l ON l.asset_id = a.id "
     "GROUP BY a.id ORDER BY label_count")

dump("axis 별 라벨 카운트 (소스별)",
     "SELECT axis, source, COUNT(1) FROM asset_labels GROUP BY axis, source ORDER BY axis, source")

dump("label_count 분포 (몇개 라벨 가진 asset 이 몇 명)",
     "SELECT label_count, COUNT(1) AS asset_count FROM ("
     "  SELECT a.id, COUNT(l.label) AS label_count FROM assets a "
     "  LEFT JOIN asset_labels l ON l.asset_id = a.id GROUP BY a.id"
     ") GROUP BY label_count ORDER BY label_count")

dump("샘플 — 라벨 풍부한 asset 1개",
     "SELECT axis, label, score, source FROM asset_labels "
     "WHERE asset_id = (SELECT a.id FROM assets a "
     "  LEFT JOIN asset_labels l ON l.asset_id = a.id "
     "  GROUP BY a.id ORDER BY COUNT(l.label) DESC LIMIT 1) "
     "ORDER BY axis, source")

dump("샘플 — 라벨 빈약한 asset 1개",
     "SELECT axis, label, score, source FROM asset_labels "
     "WHERE asset_id = (SELECT a.id FROM assets a "
     "  LEFT JOIN asset_labels l ON l.asset_id = a.id "
     "  GROUP BY a.id ORDER BY COUNT(l.label) ASC LIMIT 1) "
     "ORDER BY axis, source")
