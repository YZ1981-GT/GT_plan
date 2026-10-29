#!/bin/bash
# render-config 404 定位：404 的响应体是什么？
B=http://127.0.0.1:9980
LOGIN=$(curl -s -X POST $B/api/auth/login -H 'Content-Type: application/json' -d '{"username":"admin","password":"admin123"}')
TOKEN=$(echo "$LOGIN" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('data',{}).get('access_token',''))")
AUTH="Authorization: Bearer $TOKEN"
PID=cd095388-1dd6-44dd-9d71-ce69ff51c37d

echo "=== D4 底稿 id ==="
WPID=$(sudo -u postgres psql -d audit_platform -Atc "SELECT w.id FROM working_paper w JOIN wp_index i ON i.id=w.wp_index_id WHERE i.wp_code='D4' AND w.project_id='$PID' AND w.is_deleted=false LIMIT 1")
echo "wpid=$WPID"
echo "=== render-config 响应体 ==="
curl -s -H "$AUTH" "$B/api/workpapers/$WPID/render-config" | head -c 300; echo
echo "=== 该项目 D4 的 wp_index 行 ==="
sudo -u postgres psql -d audit_platform -c "SELECT wp_code, wp_name, is_deleted FROM wp_index WHERE project_id='$PID' AND wp_code LIKE 'D4%' LIMIT 5"
echo "=== workpaper_sheet_classification 行数（seed 数据）==="
sudo -u postgres psql -d audit_platform -Atc "SELECT count(*) FROM workpaper_sheet_classification"
echo "=== 该项目底稿总数 ==="
sudo -u postgres psql -d audit_platform -Atc "SELECT count(*) FROM working_paper WHERE project_id='$PID' AND is_deleted=false"
