#!/bin/bash
# word_export_task_versions 没有 snapshot_id —— 该表在本库由 V191 建的旧版本（重放时 IF NOT EXISTS 跳过了新列）。
# 查 V191/V205 对该表的期望列，补齐后重放 V205
echo "--- word_export_task_versions 现有列 ---"
sudo -u postgres psql -d audit_platform -Atc "SELECT column_name FROM information_schema.columns WHERE table_name='word_export_task_versions' ORDER BY ordinal_position" | tr '\n' ' '
echo
echo "--- V205 对该表的其余操作 ---"
cd /opt/gt-new-plan/backend/migrations
grep -A4 "word_export_task_versions" V205__fix_export_schema_drift.sql | head -8
grep "word_export_task_versions" V191__deliverable_edit_and_writeback_integrity.sql | head -4
