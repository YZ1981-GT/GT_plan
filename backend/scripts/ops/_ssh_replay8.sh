#!/bin/bash
# 补 word_export_task_versions.snapshot_id（uuid）+ 修 V205 其余目标 + 孤立列清理，然后 V205 干净重放
sudo -u postgres psql -d audit_platform -v ON_ERROR_STOP=0 -q <<'SQL'
ALTER TABLE word_export_task_versions ADD COLUMN IF NOT EXISTS snapshot_id UUID;
SQL
cd /opt/gt-new-plan/backend/migrations
echo "--- V205 终重放 ---"
sudo -u postgres psql -d audit_platform -v ON_ERROR_STOP=0 -q -f V205__fix_export_schema_drift.sql 2>&1 | grep -c "ERROR" || true
echo "--- 孤立列 trigger 清了吗 ---"
sudo -u postgres psql -d audit_platform -Atc "SELECT column_name FROM information_schema.columns WHERE table_name='export_job_attempts' AND column_name IN ('trigger','trigger_source')"
echo "--- 重启后端 ---"
systemctl restart gt-backend
sleep 14
systemctl is-active gt-backend
