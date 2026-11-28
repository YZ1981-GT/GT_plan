#!/bin/bash
# critical 61 的构成（orm_extra 缺表/缺列已补完的话，剩下的 type_mismatch 应该不判 critical？看探测器判级与明细）
B=http://127.0.0.1:9980
curl -s $B/api/health | python3 -c "
import sys, json
d = json.load(sys.stdin)['data']['schema_drift']
items = d.get('items') or []
from collections import Counter
c = Counter(i.get('drift_type') for i in items)
print('明细分布:', dict(c))
for i in items[:8]:
    print(' ', i.get('drift_type'), str(i.get('detail'))[:90])
"
