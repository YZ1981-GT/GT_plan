#!/bin/bash
# 部署步骤 7：重放账实漂移的迁移（幂等 DDL）—— V198 / V199 / V172 核心对象
set -e
cd /opt/gt-new-plan/backend
set -a; source .env; set +a
../.venv/bin/python - <<'EOF'
import asyncio, re
from pathlib import Path

async def main():
    from app.core.migration_runner import MigrationRunner
    import os
    runner = MigrationRunner(os.environ["DATABASE_URL"])

    # 直接对 DB 执行这几个迁移的完整 SQL（它们全是幂等 IF NOT EXISTS 风格）
    for vfile in ["V198__knowledge_documents_background_ocr.sql",
                  "V199__formula_global_settings_and_templates.sql"]:
        sql = Path("migrations") / vfile
        print(f"--- replay {vfile} ---")
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine
        engine = create_async_engine(os.environ["DATABASE_URL"], connect_args={"ssl": False} if "sslmode" not in os.environ["DATABASE_URL"] and os.environ.get("DB_DISABLE_SSL") else {})
        async with engine.begin() as conn:
            raw = sql.read_text(encoding="utf-8")
            # 按分号切分执行（迁移文件不含存储过程）
            for stmt in [s.strip() for s in raw.split(";") if s.strip() and not s.strip().startswith("--")]:
                try:
                    await conn.exec_driver_sql(stmt)
                except Exception as exc:
                    msg = str(exc)[:140]
                    print("   skip:", msg.split("\n")[0])
        await engine.dispose()
        print("   done")

asyncio.run(main())
EOF
echo "--- 核对 ---"
sudo -u postgres psql -d audit_platform -Atc "SELECT to_regclass('formula_template'); SELECT column_name FROM information_schema.columns WHERE table_name='knowledge_documents' AND column_name='ocr_status'"
