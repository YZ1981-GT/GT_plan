#!/bin/bash
# 根因找到：新建表没授权给 audit 用户（历史迁移里用 postgres 建表没 GRANT）→ 探测器（audit 用户）看不见这些表 ⇒ 全量授权收口
sudo -u postgres psql -d audit_platform <<'SQL'
GRANT USAGE ON SCHEMA public TO audit;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO audit;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO audit;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO audit;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO audit;
SQL
echo "--- 验证 ---"
PGPASSWORD=Audit2026Db psql -h 127.0.0.1 -U audit -d audit_platform -Atc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"
sudo -u postgres psql -d audit_platform -Atc "SELECT has_table_privilege('audit','formula_setting','SELECT')"
echo "--- 重启后端让探测重跑 ---"
systemctl restart gt-backend
sleep 16
systemctl is-active gt-backend
