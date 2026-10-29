#!/bin/bash
# 收官终验：health 状态 + 全量冒烟 + 后端日志干净度
B=http://127.0.0.1:9980
sleep 6
LOGIN=$(curl -s -X POST $B/api/auth/login -H 'Content-Type: application/json' -d '{"username":"admin","password":"admin123"}')
TOKEN=$(echo "$LOGIN" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('data',{}).get('access_token',''))")
AUTH="Authorization: Bearer $TOKEN"
PID=36bf8262-1ebb-4a0a-8cf6-cf9c463cdc01
pass=0; fail=0
check() { local name="$1" code="$2"; if [ "$code" = "200" ]; then pass=$((pass+1)); echo "PASS $name"; else fail=$((fail+1)); echo "FAIL $name ($code)"; fi; }
check "healthz" "$(curl -s -o /dev/null -w '%{http_code}' $B/api/health)"
check "readyz" "$(curl -s -o /dev/null -w '%{http_code}' $B/readyz)"
check "login" "$(curl -s -o /dev/null -w '%{http_code}' -X POST $B/api/auth/login -H 'Content-Type: application/json' -d '{"username":"admin","password":"admin123"}')"
check "projects" "$(curl -s -o /dev/null -w '%{http_code}' -H "$AUTH" "$B/api/projects")"
check "wp-classifications" "$(curl -s -o /dev/null -w '%{http_code}' -H "$AUTH" "$B/api/wp-classifications?wp_code=A1&project_id=$PID")"
check "review-inbox" "$(curl -s -o /dev/null -w '%{http_code}' -H "$AUTH" "$B/api/review-inbox")"
check "formula-catalog" "$(curl -s -o /dev/null -w '%{http_code}' -H "$AUTH" "$B/api/formula-catalog/check-rules")"
check "notifications" "$(curl -s -o /dev/null -w '%{http_code}' -H "$AUTH" "$B/api/notifications/unread-count")"
check "frontend" "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1/)"
check "nginx-api" "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1/api/health)"
echo "PASS=$pass FAIL=$fail"
echo "--- health degraded 剩余 critical ---"
curl -s $B/api/health | python3 -c "import sys,json; d=json.load(sys.stdin)['data']; sd=d.get('schema_drift',{}); print('status:', d.get('status')); print('critical:', sd.get('critical_count'), 'total:', sd.get('count')); print('migration failures:', d.get('migration',{}).get('failures'))"
echo "--- 近 2 分钟异常日志 ---"
journalctl -u gt-backend --since '2 minutes ago' --no-pager 2>/dev/null | grep -ciE 'traceback|undefined' || true
