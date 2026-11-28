#!/bin/bash
# 补最后 2 列（export_jobs_v2.readiness / word_export_task_versions.file_sha256）
sudo -u postgres psql -d audit_platform <<'SQL'
ALTER TABLE export_jobs_v2 ADD COLUMN IF NOT EXISTS readiness VARCHAR(16);
ALTER TABLE word_export_task_versions ADD COLUMN IF NOT EXISTS file_sha256 CHAR(64);
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO audit;
SQL
echo "--- 重启重测 ---"
systemctl restart gt-backend
sleep 18
B=http://127.0.0.1:9980
curl -s $B/api/health | python3 -c "
import sys, json
d = json.load(sys.stdin)['data']
sd = d.get('schema_drift', {})
print('status:', d.get('status'))
print('drift critical:', sd.get('critical_count'), 'total:', sd.get('count'))
from collections import Counter
print('构成:', dict(Counter(i.get('drift_type') for i in (sd.get('items') or []))))
"
