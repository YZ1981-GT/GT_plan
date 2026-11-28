#!/bin/bash
# 部署步骤 3：前端构建（npm ci + vite build）
set -e
cd /opt/gt-new-plan/audit-platform/frontend
echo "--- npm ci（按 lockfile，幂等）---"
timeout 900 npm ci --prefer-offline --no-audit --no-fund 2>&1 | tail -4
echo "--- vite build ---"
timeout 900 npm run build 2>&1 | tail -12
echo "--- 产物确认 ---"
ls dist/ | head -5
stat -c '%y %n' dist/index.html
