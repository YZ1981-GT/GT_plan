#!/bin/bash
# 部署步骤 4：迁移已在启动时自动跑（MigrationRunner），先空跑确认导入健康，然后重启服务
set -e
cd /opt/gt-new-plan
echo "--- 后端导入健康检查（离线 import app.main）---"
cd backend && ../.venv/bin/python -c "import app.main; print('import OK')" 2>&1 | tail -3
cd /opt/gt-new-plan
echo "--- 重启 gt-backend ---"
systemctl restart gt-backend
sleep 6
systemctl is-active gt-backend
echo "--- 迁移状态（启动日志尾部）---"
sleep 6
journalctl -u gt-backend --since '1 minute ago' --no-pager 2>/dev/null | grep -iE 'migration|error|ready|started' | tail -8
