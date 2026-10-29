#!/bin/bash
# 部署步骤 8：V208 + V207 检查 + 重启后端
set -e
cd /opt/gt-new-plan/backend/migrations
echo "--- V208 重放 ---"
sudo -u postgres psql -d audit_platform -v ON_ERROR_STOP=1 -f V208__seed_gt_qwen37_max_preset.sql 2>&1 | tail -2
echo "--- 清失败账并跑 runner 确认干净 ---"
sudo -u postgres psql -d audit_platform -c "DELETE FROM schema_migration_failures WHERE version=208"
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
sleep 10
systemctl is-active gt-backend
journalctl -u gt-backend --since '30 seconds ago' --no-pager 2>/dev/null | grep -ciE 'undefinedtable|undefinedcolumn' || true
echo "backend-ready:"
journalctl -u gt-backend --since '40 seconds ago' --no-pager 2>/dev/null | grep -c "Ready on port 9980" || true
