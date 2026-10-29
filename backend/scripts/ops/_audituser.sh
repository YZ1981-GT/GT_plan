#!/bin/bash
sudo -u postgres psql -d audit_platform -Atc "SELECT schemaname, tablename FROM pg_tables WHERE tablename IN ('formula_setting','consol_note_detail_template_version')"
echo "--- audit 用户视角 ---"
PGPASSWORD=Audit2026Db psql -h 127.0.0.1 -U audit -d audit_platform -Atc "SELECT to_regclass('formula_setting'), to_regclass('consol_note_detail_template_version'), current_schema()" 2>&1 | head -2
echo "--- audit 用户权限 ---"
sudo -u postgres psql -d audit_platform -Atc "SELECT has_table_privilege('audit','formula_setting','SELECT')"
