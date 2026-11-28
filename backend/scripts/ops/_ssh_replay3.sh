#!/bin/bash
# V202 前置表（consol_note_detail_template_version 等）由哪个迁移建？
cd /opt/gt-new-plan/backend/migrations
grep -l "CREATE TABLE.*consol_note_detail_template_version\|CREATE TABLE IF NOT EXISTS consol_note_detail_template_version" V*.sql 2>/dev/null
grep -l "consol_note_structure_lock" V*.sql 2>/dev/null | head -3
grep -l "consol_note_mapping_rule" V*.sql 2>/dev/null | head -3
echo "--- V205 snapshot_id 前置 ---"
grep -B3 "snapshot_id" V205__fix_export_schema_drift.sql | head -6
