#!/bin/bash
# 整个库 0 底稿：服务器库是干净环境（分类 seed 4640 行已有但业务底稿未生成）。
# 部署验证的正确路径 = 用平台自己的初始化链路造一个【测试】项目（生成底稿），再测全链。
B=http://127.0.0.1:9980
LOGIN=$(curl -s -X POST $B/api/auth/login -H 'Content-Type: application/json' -d '{"username":"admin","password":"admin123"}')
TOKEN=$(echo "$LOGIN" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('data',{}).get('access_token',''))")
AUTH="Authorization: Bearer $TOKEN"
echo "=== 建项目向导接口探测 ==="
curl -s -o /dev/null -w "POST /api/project-wizard: %{http_code}\n" -X POST -H "$AUTH" -H 'Content-Type: application/json' -d '{}' "$B/api/project-wizard"
curl -s -o /dev/null -w "POST /api/projects: %{http_code}\n" -X POST -H "$AUTH" -H 'Content-Type: application/json' -d '{}' "$B/api/projects"
echo "=== 现有分类 seed 覆盖确认（与本地同源 4640 行）==="
sudo -u postgres psql -d audit_platform -Atc "SELECT count(DISTINCT wp_code) FROM workpaper_sheet_classification"
echo "=== 静态只读端点抽查（不依赖底稿数据）==="
for ep in "/api/wp_template" "/api/formula-catalog/check-rules" "/api/notifications/unread-count" "/api/review-inbox"; do
  printf "%-42s %s\n" "$ep" "$(curl -s -o /dev/null -w '%{http_code}' -H "$AUTH" "$B$ep")"
done
