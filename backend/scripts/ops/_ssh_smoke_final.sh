#!/bin/bash
# 最终冒烟（迁移全补齐后）
B=http://127.0.0.1:9980
LOGIN=$(curl -s -X POST $B/api/auth/login -H 'Content-Type: application/json' -d '{"username":"admin","password":"admin123"}')
TOKEN=$(echo "$LOGIN" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('data',{}).get('access_token',''))")
AUTH="Authorization: Bearer $TOKEN"
PID=36bf8262-1ebb-4a0a-8cf6-cf9c463cdc01
pass=0; fail=0
check() { local name="$1" code="$2"; if [ "$code" = "200" ]; then echo "PASS $name ($code)"; pass=$((pass+1)); else echo "FAIL $name ($code)"; fail=$((fail+1)); fi; }

c=$(curl -s -o /dev/null -w '%{http_code}' $B/api/health); check "healthz" $c
c=$(curl -s -o /dev/null -w '%{http_code}' $B/readyz); check "readyz" $c
c=$(curl -s -o /dev/null -w '%{http_code}' -X POST $B/api/auth/login -H 'Content-Type: application/json' -d '{"username":"admin","password":"admin123"}'); check "login" $c
c=$(curl -s -o /dev/null -w '%{http_code}' -H "$AUTH" "$B/api/projects"); check "projects" $c
c=$(curl -s -o /dev/null -w '%{http_code}' -H "$AUTH" "$B/api/wp-classifications?wp_code=A1&project_id=$PID"); check "wp-classifications" $c
c=$(curl -s -o /dev/null -w '%{http_code}' -H "$AUTH" "$B/api/review-inbox"); check "review-inbox(此前500)" $c
c=$(curl -s -o /dev/null -w '%{http_code}' -H "$AUTH" "$B/api/formula-catalog/check-rules"); check "formula-catalog" $c
c=$(curl -s -o /dev/null -w '%{http_code}' -H "$AUTH" "$B/api/notifications/unread-count"); check "notifications" $c
c=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1/); check "frontend(nginx)" $c
c=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1/api/health); check "nginx反代/api" $c
echo "-----"
echo "PASS=$pass FAIL=$fail"
