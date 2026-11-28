#!/bin/bash
# 部署步骤 1：代码切换到 dev1.0
set -e
cd /opt/gt-new-plan
echo "--- 备份当前分支指针 ---"
git rev-parse HEAD > /opt/gt-deploy-rollback-point-$(date +%Y%m%d_%H%M%S).txt
cat /opt/gt-deploy-rollback-point-*.txt | tail -1
echo "--- 丢弃 components.d.ts 生成物改动 ---"
git checkout -- audit-platform/frontend/src/components.d.ts || true
echo "--- 添加 GitHub 远端（若无）---"
git remote add github https://github.com/YZ1981-GT/GT_plan.git 2>/dev/null || true
echo "--- fetch dev1.0 ---"
timeout 300 git fetch github dev1.0
echo "--- 切换/强正 dev1.0 到 bffd4d57f ---"
git checkout -B dev1.0 bffd4d57ff6a372bb64a96e9b5f448e1e3211ac3
git log --oneline -1
echo "--- 工作树状态 ---"
git status --short | head -5
