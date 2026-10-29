#!/bin/bash
# V199 重放：改用 psql 逐条执行（-c 单命令 autocommit，且 psql 自己解析分号语句正确）
set -e
cd /opt/gt-new-plan/backend/migrations
sudo -u postgres psql -d audit_platform -v ON_ERROR_STOP=0 -f V199__formula_global_settings_and_templates.sql 2>&1 | grep -cE "ERROR" || true
echo "--- V198 重放 ---"
sudo -u postgres psql -d audit_platform -v ON_ERROR_STOP=0 -f V198__knowledge_documents_background_ocr.sql 2>&1 | grep -E "ERROR" | head -5 || true
echo "--- 核对 ---"
sudo -u postgres psql -d audit_platform -Atc "SELECT to_regclass('formula_template')"
sudo -u postgres psql -d audit_platform -Atc "SELECT column_name FROM information_schema.columns WHERE table_name='knowledge_documents' AND column_name='ocr_status'"
