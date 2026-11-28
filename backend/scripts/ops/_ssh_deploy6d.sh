#!/bin/bash
# schema 漂移全面体检：找出 ORM/迁移预期但 DB 缺失的关键对象
echo "--- formula_template 相关迁移 ---"
cd /opt/gt-new-plan/backend
grep -l "formula_template" migrations/V*.sql 2>/dev/null | tail -3
echo "--- knowledge_documents ocr 列的迁移 ---"
grep -l "ocr_status" migrations/V*.sql 2>/dev/null | tail -2
echo "--- linkage_audit_log ---"
sudo -u postgres psql -d audit_platform -Atc "SELECT to_regclass('linkage_audit_log')"
echo "--- 试跑 ORM 全表 vs DB 的漂移检测（启动时已有报告，取 critical 数）---"
../.venv/bin/python - <<'EOF'
import asyncio

async def main():
    import os
    os.environ.setdefault("DATABASE_URL", "")
    from app.core.database import async_engine
    from app.services.schema_drift_detector import detect_schema_drift
    report = await detect_schema_drift(async_engine)
    print("critical:", report.get("critical_count"))
    for item in (report.get("issues") or [])[:12]:
        print(" ", item.get("type"), item.get("detail", "")[:80])

asyncio.run(main())
EOF
