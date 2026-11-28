#!/bin/bash
# 查 schema_version 账的当前版本
echo "--- schema_version 表结构 ---"
sudo -u postgres psql -d audit_platform -Atc "SELECT column_name FROM information_schema.columns WHERE table_name='schema_version' ORDER BY ordinal_position" | tr '\n' ' '
echo
echo "--- 当前版本 ---"
sudo -u postgres psql -d audit_platform -Atc "SELECT * FROM schema_version LIMIT 3"
echo "--- 失败记录 ---"
sudo -u postgres psql -d audit_platform -Atc "SELECT version, attempt_count, LEFT(error_message, 60) FROM schema_migration_failures ORDER BY version DESC LIMIT 5" 2>/dev/null
