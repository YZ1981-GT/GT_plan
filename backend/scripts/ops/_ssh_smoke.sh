#!/bin/bash
# 冒烟测试（服务器本机视角）
B=http://127.0.0.1:9980
echo "=== 1. healthz ==="
curl -s -o /dev/null -w "%{http_code}\n" $B/api/health
echo "=== 2. readyz ==="
curl -s -o /dev/null -w "%{http_code}\n" $B/readyz
echo "=== 3. 登录（admin/admin123）==="
LOGIN=$(curl -s -X POST $B/api/auth/login -H 'Content-Type: application/json' -d '{"username":"admin","password":"admin123"}')
echo "$LOGIN" | head -c 120; echo
TOKEN=$(echo "$LOGIN" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('data',{}).get('access_token',''))" 2>/dev/null)
if [ -z "$TOKEN" ]; then echo "!! 登录失败"; exit 1; fi
echo "token: ${TOKEN:0:20}..."
AUTH="Authorization: Bearer $TOKEN"
echo "=== 4. 项目列表 ==="
curl -s -o /dev/null -w "%{http_code}\n" -H "$AUTH" "$B/api/projects"
echo "=== 5. wp-classifications（此前 404 的接口）==="
PID=$(sudo -u postgres psql -d audit_platform -Atc "SELECT id FROM projects LIMIT 1")
echo "project=$PID"
curl -s -H "$AUTH" "$B/api/wp-classifications?wp_code=A1&project_id=$PID" -o /tmp/cls.json -w "%{http_code}\n"
head -c 200 /tmp/cls.json; echo
echo "=== 6. 前端 dist ==="
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1/
echo "=== 7. 前端经 nginx 拿 index.html 内容头 ==="
curl -s http://127.0.0.1/ | head -c 150; echo
echo "=== 8. nginx 反代 /api ==="
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1/api/health
echo "=== 9. render-config 冒烟（D4 底稿）==="
WPID=$(sudo -u postgres psql -d audit_platform -Atc "SELECT w.id FROM working_paper w JOIN wp_index i ON i.id=w.wp_index_id WHERE i.wp_code='D4' AND w.is_deleted=false LIMIT 1")
curl -s -o /dev/null -w "%{http_code}\n" -H "$AUTH" "$B/api/workpapers/$WPID/render-config"
