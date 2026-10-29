#!/bin/bash
sleep 20
B=http://127.0.0.1:9980
curl -s $B/api/health | python3 -c "
import sys, json
d = json.load(sys.stdin)['data']
sd = d.get('schema_drift', {})
print('status:', d.get('status'))
print('drift critical:', sd.get('critical_count'), 'total:', sd.get('count'))
print('migration failures:', d.get('migration',{}).get('failures'))
from collections import Counter
c = Counter(i.get('drift_type') for i in (sd.get('items') or []))
print('构成:', dict(c))
"
