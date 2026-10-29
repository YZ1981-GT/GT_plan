#!/bin/bash
# 该项目 0 底稿 —— 这批库是“干净库”（只有项目行，没有生成底稿）。核对全库数据分布：
B=http://127.0.0.1:9980
echo "=== 各项目底稿数 ==="
sudo -u postgres psql -d audit_platform -c "SELECT p.name, count(w.id) AS wps FROM projects p LEFT JOIN working_paper w ON w.project_id=p.id AND w.is_deleted=false GROUP BY p.name ORDER BY wps DESC LIMIT 8"
echo "=== 有底稿的项目 ==="
PID2=$(sudo -u postgres psql -d audit_platform -Atc "SELECT w.project_id FROM working_paper w WHERE w.is_deleted=false GROUP BY w.project_id ORDER BY count(*) DESC LIMIT 1")
echo "picked=$PID2"
echo "=== 用有底稿的项目重测 render-config + wp-classifications ==="
LOGIN=$(curl -s -X POST $B/api/auth/login -H 'Content-Type: application/json' -d '{"username":"admin","password":"admin123"}')
TOKEN=$(echo "$LOGIN" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('data',{}).get('access_token',''))")
AUTH="Authorization: Bearer $TOKEN"
WPID=$(sudo -u postgres psql -d audit_platform -Atc "SELECT w.id FROM working_paper w JOIN wp_index i ON i.id=w.wp_index_id WHERE w.project_id='$PID2' AND w.is_deleted=false AND i.wp_code LIKE 'D%' LIMIT 1")
CODE=$(sudo -u postgres psql -d audit_platform -Atc "SELECT i.wp_code FROM working_paper w JOIN wp_index i ON i.id=w.wp_index_id WHERE w.id='$WPID'")
echo "wpid=$WPID code=$CODE"
echo "--- render-config ---"
curl -s -o /dev/null -w "%{http_code}\n" -H "$AUTH" "$B/api/workpapers/$WPID/render-config"
echo "--- wp-classifications ---"
curl -s -H "$AUTH" "$B/api/wp-classifications?wp_code=$CODE&project_id=$PID2" -o /tmp/c2.json -w "%{http_code}\n"
head -c 160 /tmp/c2.json; echo
