#!/bin/bash
# 部署步骤 5c：MigrationRunner 带 DATABASE_URL（从 .env 读）
set -e
cd /opt/gt-new-plan/backend
set -a; source .env; set +a
../.venv/bin/python - <<'EOF'
import asyncio, os

async def main():
    from app.core.migration_runner import MigrationRunner
    url = os.environ["DATABASE_URL"]
    runner = MigrationRunner(url)
    result = await runner.run_pending()
    print("executed:", len(result.executed))
    for e in result.executed:
        print("  +", e)
    print("failed:", len(result.failed))
    for f in result.failed:
        print("  -", getattr(f, "version", f))

asyncio.run(main())
EOF
