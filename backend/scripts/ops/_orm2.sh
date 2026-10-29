#!/bin/bash
# 剩余 orm_extra 2 条明细 + 检测器判级逻辑（为什么 orm_extra 2 条也算 42 critical？40 checksum 也计入 critical？）
B=http://127.0.0.1:9980
curl -s $B/api/health | python3 -c "
import sys, json
items = json.load(sys.stdin)['data']['schema_drift'].get('items') or []
for i in items:
    if i.get('drift_type') == 'orm_extra':
        print('ORM_EXTRA:', str(i.get('detail'))[:110])
"
echo "--- 检测器 critical 判级来源 ---"
grep -n "critical" /opt/gt-new-plan/backend/app/services/schema_drift*.py 2>/dev/null | head -6
ls /opt/gt-new-plan/backend/app/services/ | grep -i drift
