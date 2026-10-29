#!/bin/bash
# 部署步骤 3 第三轮：跳过 vue-tsc 直接 vite build（部署产物不需要类型检查，本地 CI 已把过关）
set -e
cd /opt/gt-new-plan/audit-platform/frontend
pkill -f 'vite build' 2>/dev/null || true
pkill -f vue-tsc 2>/dev/null || true
sleep 2
echo "--- 直接 vite build（跳过 vue-tsc 类型检查）---"
NODE_OPTIONS="--max-old-space-size=40960" timeout 1200 npx vite build 2>&1 | tail -10
echo "--- 产物确认 ---"
stat -c '%y %n' dist/index.html
ls dist/assets | wc -l
