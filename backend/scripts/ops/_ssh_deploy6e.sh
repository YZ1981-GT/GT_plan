#!/bin/bash
# schema 漂移体检（带 .env）
set -a; source /opt/gt-new-plan/backend/.env; set +a
cd /opt/gt-new-plan/backend
echo "--- 待补对象对应的迁移文件 ---"
grep -l "formula_template" migrations/V*.sql 2>/dev/null | tail -3
grep -l "ocr_status" migrations/V*.sql 2>/dev/null | tail -2
echo "--- ORM vs DB 漂移检测 ---"
../.venv/bin/python - <<'EOF'
import asyncio

async def main():
    from app.core.database import async_engine
    try:
        from app.services.schema_drift_detector import detect_schema_drift
        report = await detect_schema_drift(async_engine)
    except TypeError:
        from app.services.schema_drift_detector import detect_drift
        report = await detect_drift(async_engine)
    if isinstance(report, dict):
        print("critical:", report.get("critical_count"))
        for item in (report.get("issues") or report.get("orm_extra") or [])[:15]:
            print(" ", str(item)[:110])
    else:
        print(str(report)[:400])

asyncio.run(main())
EOF
