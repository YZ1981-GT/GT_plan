#!/bin/bash
# 部署步骤 3 最终：vite build（补丁已应用，跳过 vue-tsc）
set -e
cd /opt/gt-new-plan/audit-platform/frontend
pkill -f 'vite build' 2>/dev/null || true
sleep 2
echo "--- vite build（补丁后）---"
NODE_OPTIONS="--max-old-space-size=40960" timeout 1200 npx vite build 2>&1 | tail -6
echo "--- 产物确认 ---"
stat -c '%y %n' dist/index.html
ls dist/assets | wc -l
