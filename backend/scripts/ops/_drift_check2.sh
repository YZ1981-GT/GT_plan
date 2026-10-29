#!/bin/bash
# orm_extra 22 条 = ORM 有定义但 DB 缺（critical 判级来源）。列明细：
sudo -u postgres psql -d audit_platform -Atc "SELECT detail FROM schema_drift_log WHERE drift_type='orm_extra' ORDER BY id DESC LIMIT 12" 2>/dev/null
echo "---enum_mismatch---"
sudo -u postgres psql -d audit_platform -Atc "SELECT detail FROM schema_drift_log WHERE drift_type='enum_mismatch' LIMIT 3" 2>/dev/null
