#!/bin/bash
# 部署步骤 5：手动跑迁移（dev1.0 新增的 V206+）并核对
set -e
cd /opt/gt-new-plan/backend
echo "--- 当前 DB 迁移版本（顶层）---"
sudo -u postgres psql -d audit_platform -Atc "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 3" 2>/dev/null || sudo -u postgres psql -d audit_platform -Atc "SELECT DISTINCT version FROM migration_history ORDER BY 1 DESC LIMIT 3" 2>/dev/null || echo "（迁移账表名待探）"
echo "--- 代码侧最高迁移 ---"
ls migrations/ | grep -oE '^V[0-9]+' | sort -V | tail -3
echo "--- 用 MigrationRunner 跑 pending ---"
../.venv/bin/python -c "
from app.services.migration_runner import MigrationRunner
import inspect
# 找到 runner 的构造签名
print([n for n in dir(MigrationRunner) if not n.startswith('_')][:10])
" 2>&1 | tail -2
