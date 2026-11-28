#!/bin/bash
# 前置链修复：V186 建的表在本库也缺失（同款账实漂移）→ 重放 V186 再 V202；
# V205 的 snapshot_id 由 export_jobs_v2 的更早迁移建（先查哪张表报错）
cd /opt/gt-new-plan/backend/migrations
echo "--- 重放 V186 ---"
sudo -u postgres psql -d audit_platform -v ON_ERROR_STOP=0 -q -f V186__consol_note_detail_template_and_mapping.sql 2>&1 | grep "ERROR" | head -5
echo "--- V186 后核对 ---"
sudo -u postgres psql -d audit_platform -Atc "SELECT to_regclass('consol_note_detail_template_version'), to_regclass('consol_note_structure_lock'), to_regclass('consol_note_mapping_rule')"
echo "--- V202 重放 ---"
sudo -u postgres psql -d audit_platform -v ON_ERROR_STOP=0 -q -f V202__consol_note_mapping_reuse_and_reference.sql 2>&1 | grep -c "ERROR" || true
echo "--- V205：export_jobs_v2 表有 snapshot_id 吗 ---"
sudo -u postgres psql -d audit_platform -Atc "SELECT column_name FROM information_schema.columns WHERE table_name='export_jobs_v2' AND column_name LIKE '%snapshot%'"
sudo -u postgres psql -d audit_platform -Atc "SELECT column_name FROM information_schema.columns WHERE table_name='export_jobs_v2' ORDER BY ordinal_position LIMIT 12" | tr '\n' ' '
echo
