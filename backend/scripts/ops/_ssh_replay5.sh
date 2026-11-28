#!/bin/bash
# V205 重放（V186/V202 修好后）+ consol_note_structure_lock 缺失核对 + 最终 runner 校验 + 重启
cd /opt/gt-new-plan/backend/migrations
echo "--- V205 重放 ---"
sudo -u postgres psql -d audit_platform -v ON_ERROR_STOP=0 -q -f V205__fix_export_schema_drift.sql 2>&1 | grep "ERROR" | head -3
echo "--- structure_lock（V202 建了吗）---"
sudo -u postgres psql -d audit_platform -Atc "SELECT to_regclass('consol_note_structure_lock'), to_regclass('consol_note_structure_lock_entity')"
echo "--- runner 终验 ---"
cd /opt/gt-new-plan/backend
set -a; source .env; set +a
../.venv/bin/python - <<'EOF'
import asyncio, os

async def main():
    from app.core.migration_runner import MigrationRunner
    runner = MigrationRunner(os.environ["DATABASE_URL"])
    result = await runner.run_pending()
    print("executed:", len(result.executed), "failed:", len(result.failed))

asyncio.run(main())
EOF
echo "--- 重启 ---"
systemctl restart gt-backend
sleep 14
systemctl is-active gt-backend
