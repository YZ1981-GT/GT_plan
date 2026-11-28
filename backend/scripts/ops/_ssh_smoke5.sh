#!/bin/bash
# 1) review-inbox 500 定位  2) 正确的项目创建端点探测
B=http://127.0.0.1:9980
LOGIN=$(curl -s -X POST $B/api/auth/login -H 'Content-Type: application/json' -d '{"username":"admin","password":"admin123"}')
TOKEN=$(echo "$LOGIN" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('data',{}).get('access_token',''))")
AUTH="Authorization: Bearer $TOKEN"
echo "=== review-inbox 500 响应体 ==="
curl -s -H "$AUTH" "$B/api/review-inbox" | head -c 300; echo
echo "=== 服务器日志里 review-inbox 的栈 ==="
journalctl -u gt-backend --since '3 minutes ago' --no-pager 2>/dev/null | grep -A8 "review.inbox\|review_inbox" | head -14
echo "=== projects 列表响应（拿真实可用端点形态）==="
curl -s -H "$AUTH" "$B/api/projects" | head -c 200; echo
