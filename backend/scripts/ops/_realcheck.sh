#!/bin/bash
# 怪异：这些表前面核对明明存在（formula_setting 等）。探测器可能连的另一个库！
echo "--- DATABASE_URL 指向哪个库 ---"
grep -E "^DATABASE_URL" /opt/gt-new-plan/backend/.env | sed 's/\(\/\/[^:]*:\)[^@]*(@/\1***@/'
echo "--- 真实直查（.env 同库）---"
sudo -u postgres psql -d audit_platform -Atc "SELECT to_regclass('formula_setting'), to_regclass('consol_note_detail_template_version')"
echo "--- 全部数据库列表 ---"
sudo -u postgres psql -Atc "SELECT datname FROM pg_database WHERE datistemplate=false"
echo "--- gt-backend 进程实际连接的库 ---"
sudo -u postgres psql -Atc "SELECT datname, count(*) FROM pg_stat_activity GROUP BY datname"
