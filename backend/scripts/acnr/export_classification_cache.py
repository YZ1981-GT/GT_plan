"""Export workpaper_sheet_classification to classification_cache.json for offline use.

Usage:
    python backend/scripts/acnr/export_classification_cache.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 路径设置
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_BACKEND_ROOT = _REPO_ROOT / "backend"
sys.path.insert(0, str(_BACKEND_ROOT))

_ACNR_DATA_DIR = _BACKEND_ROOT / "data" / "acnr"
_SOURCES_DIR = _ACNR_DATA_DIR / "sources"
_CACHE_PATH = _SOURCES_DIR / "classification_cache.json"


def main() -> int:
    """Export classification records to JSON cache."""
    # 使用同步 psycopg2 直连 DB
    import psycopg2
    from dotenv import load_dotenv

    # 加载环境变量
    env_path = _REPO_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        # 构建连接串
        host = os.environ.get("DB_HOST", "localhost")
        port = os.environ.get("DB_PORT", "5432")
        user = os.environ.get("DB_USER", "postgres")
        password = os.environ.get("DB_PASSWORD", "postgres")
        database = os.environ.get("DB_NAME", "audit_platform")
        db_url = f"postgresql://{user}:{password}@{host}:{port}/{database}"

    print(f"[export_classification_cache] Connecting to DB...")

    conn = psycopg2.connect(db_url)
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT wp_code, sheet_name, class_code, functional_type, template_version_id::text
            FROM workpaper_sheet_classification
            ORDER BY wp_code, sheet_name
        """)
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()

    records = []
    for row in rows:
        records.append({
            "wp_code": row[0],
            "sheet_name": row[1],
            "class_code": row[2] or "",
            "functional_type": row[3] or "",
            "template_version_id": row[4] or "",
        })

    # 确保目录存在
    _SOURCES_DIR.mkdir(parents=True, exist_ok=True)

    # 写入缓存
    with open(_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"[export_classification_cache] Exported {len(records)} records to {_CACHE_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
