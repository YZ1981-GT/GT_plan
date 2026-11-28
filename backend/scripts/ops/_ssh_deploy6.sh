#!/bin/bash
# 迁移账探查
echo "--- 账表 ---"
sudo -u postgres psql -d audit_platform -Atc "SELECT tablename FROM pg_tables WHERE tablename LIKE '%migration%' OR tablename LIKE '%schema%'"
echo "--- 已应用版本（尾部 8）---"
sudo -u postgres psql -d audit_platform -Atc "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 8" 2>/dev/null
echo "--- ai_model_config 现有列 ---"
sudo -u postgres psql -d audit_platform -Atc "SELECT column_name FROM information_schema.columns WHERE table_name='ai_model_config' ORDER BY ordinal_position" | tr '\n' ' '
echo
echo "--- formula_template 表存在吗 ---"
sudo -u postgres psql -d audit_platform -Atc "SELECT to_regclass('formula_template')"
echo "--- knowledge_documents ocr 列 ---"
sudo -u postgres psql -d audit_platform -Atc "SELECT column_name FROM information_schema.columns WHERE table_name='knowledge_documents' AND column_name LIKE 'ocr%'" | tr '\n' ' '
echo
