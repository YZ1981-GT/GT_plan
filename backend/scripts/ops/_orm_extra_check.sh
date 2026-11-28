#!/bin/bash
# orm_extra 还有 21 条 —— 看具体缺什么（已补过一轮，可能这 21 是重放时被语句错误吞掉的部分）
B=http://127.0.0.1:9980
curl -s $B/api/health | python3 -c "
import sys, json
items = json.load(sys.stdin)['data']['schema_drift'].get('items') or []
for i in items:
    if i.get('drift_type') == 'orm_extra':
        print(str(i.get('detail'))[:110])
" | head -22
