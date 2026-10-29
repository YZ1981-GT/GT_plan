#!/bin/bash
# 部署步骤 3 重试：vite build 带 40GB 堆（OOM 是默认堆不够，本仓库已知问题）
set -e
cd /opt/gt-new-plan/audit-platform/frontend
echo "--- vite build（NODE_OPTIONS=--max-old-space-size=40960）---"
export NODE_OPTIONS="--max-old-space-size=40960"
timeout 1200 npm run build 2>&1 | tail -10
echo "--- 产物确认 ---"
stat -c '%y %n' dist/index.html
ls dist/assets | wc -l
