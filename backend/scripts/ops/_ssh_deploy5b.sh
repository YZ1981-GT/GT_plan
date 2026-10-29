#!/bin/bash
# 部署步骤 5b：用 MigrationRunner 跑 pending 迁移
set -e
cd /opt/gt-new-plan/backend
../.venv/bin/python - <<'EOF'
import asyncio

async def main():
    from app.core.migration_runner import MigrationRunner
    runner = MigrationRunner()
    result = await runner.run_pending()
    print("executed:", len(result.executed))
    for e in result.executed:
        print("  +", e)
    print("failed:", len(result.failed))
    for f in result.failed:
        print("  -", getattr(f, "version", f))

asyncio.run(main())
EOF
