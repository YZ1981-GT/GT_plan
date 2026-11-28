#!/bin/bash
# V202/V205 的 7 个错误详情（判定是否良性：多为对象已存在/数据已迁移）
cd /opt/gt-new-plan/backend/migrations
echo "=== V202 错误 ==="
sudo -u postgres psql -d audit_platform -v ON_ERROR_STOP=0 -q -f V202__consol_note_mapping_reuse_and_reference.sql 2>&1 | grep "ERROR" | head -6
echo "=== V205 错误 ==="
sudo -u postgres psql -d audit_platform -v ON_ERROR_STOP=0 -q -f V205__fix_export_schema_drift.sql 2>&1 | grep "ERROR" | head -3
