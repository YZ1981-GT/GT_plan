#!/bin/bash
# V208 修正重放：DB 枚举缺 custom 等新成员（V192 加的）—— 补枚举成员再播种
set -e
cd /opt/gt-new-plan/backend/migrations
echo "--- 补枚举成员（幂等：存在会报 duplicate_object，吸收）---"
sudo -u postgres psql -d audit_platform -Atc "ALTER TYPE ai_provider_enum ADD VALUE IF NOT EXISTS 'custom'" 2>&1 | head -1 || true
sudo -u postgres psql -d audit_platform -Atc "ALTER TYPE ai_provider_enum ADD VALUE IF NOT EXISTS 'qwen'" 2>&1 | head -1 || true
sudo -u postgres psql -d audit_platform -Atc "ALTER TYPE ai_provider_enum ADD VALUE IF NOT EXISTS 'azure_openai'" 2>&1 | head -1 || true
sudo -u postgres psql -d audit_platform -Atc "SELECT enum_range(NULL::ai_provider_enum)"
echo "--- V208 重放 ---"
sudo -u postgres psql -d audit_platform -v ON_ERROR_STOP=1 -f V208__seed_gt_qwen37_max_preset.sql 2>&1 | tail -2
echo "--- 清失败账（version varchar）---"
sudo -u postgres psql -d audit_platform -c "DELETE FROM schema_migration_failures WHERE version='208'"
echo "--- runner 校验干净 ---"
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
echo "--- 重启后端 ---"
systemctl restart gt-backend
sleep 12
systemctl is-active gt-backend
echo "undefined-errors(应为0):"
journalctl -u gt-backend --since '30 seconds ago' --no-pager 2>/dev/null | grep -ciE 'undefinedtable|undefinedcolumn' || true
echo "ready(应为1):"
journalctl -u gt-backend --since '40 seconds ago' --no-pager 2>/dev/null | grep -c "Ready on port 9980" || true
