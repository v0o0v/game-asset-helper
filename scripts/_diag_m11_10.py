"""M11.10 LIVE 진단 — DB 상태 dump.

격리 data-dir 의 metadata.db 를 직접 query 해 batch path 가 어디서 막혔는지 파악.
일회용 스크립트 — 본 파일은 .gitignore 또는 verification 후 삭제.
"""

import os
import sqlite3
import sys

db_path = os.path.join(
    os.environ["TEMP"], "assetcache-test-m11-10-live-data", "metadata.db"
)
if not os.path.exists(db_path):
    print(f"DB 없음: {db_path}")
    sys.exit(1)

conn = sqlite3.connect(db_path)
c = conn.cursor()

def row_print(label, sql, params=()):
    print(f"=== {label} ===")
    for r in c.execute(sql, params):
        print(r)
    print()

row_print("packs", "SELECT id, name, display_name FROM packs")
row_print("assets state x batch_state",
          "SELECT analysis_state, batch_state, COUNT(1) FROM assets GROUP BY analysis_state, batch_state")
row_print("backend_image 분포",
          "SELECT backend_image, COUNT(1) FROM assets GROUP BY backend_image")
row_print("backend_embed 분포",
          "SELECT backend_embed, COUNT(1) FROM assets GROUP BY backend_embed")
row_print("kind 분포",
          "SELECT kind, COUNT(1) FROM assets GROUP BY kind")
row_print("batch_jobs (최신 10)",
          "SELECT id, modality, state, asset_count, success_count, failure_count, "
          "COALESCE(error, '') FROM batch_jobs ORDER BY id DESC LIMIT 10")
row_print("asset_embeddings (dim>0)",
          "SELECT COUNT(1) FROM asset_embeddings WHERE dim > 0")
row_print("asset_embeddings (전체)",
          "SELECT COUNT(1) FROM asset_embeddings")
row_print("최근 분석 실패 (analysis_state='failed')",
          "SELECT id, path, COALESCE(analysis_error, '') FROM assets "
          "WHERE analysis_state = 'failed' LIMIT 10")
row_print("샘플 assets (5개)",
          "SELECT id, path, kind, analysis_state, batch_state, "
          "backend_image, backend_embed FROM assets LIMIT 5")
