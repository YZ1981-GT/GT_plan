#!/bin/bash
# 勘察第四轮：.env 与 git 状态
echo "--- backend/.env（隐藏值）---"
sed 's/=.*/=<set>/' /opt/gt-new-plan/backend/.env 2>/dev/null | grep -vE '^#|^$'
echo
echo "--- git remotes ---"
cd /opt/gt-new-plan && git remote -v
echo "--- git 状态 ---"
git status --short | head -10
echo "--- 当前分支与 dev1.0 的关系（若 GitHub 可达）---"
timeout 30 git ls-remote https://github.com/YZ1981-GT/GT_plan.git dev1.0 2>&1 | head -2
echo "--- node/npm 版本 ---"
node --version; npm --version
echo "--- venv python ---"
/opt/gt-new-plan/.venv/bin/python --version 2>&1
echo "--- 迁移目录最高版本（当前代码）---"
ls /opt/gt-new-plan/backend/migrations/ 2>/dev/null | grep -oE '^V[0-9]+' | sort -V | tail -3
echo "--- 数据库规模 ---"
sudo -u postgres psql -d audit_platform -Atc "SELECT count(*) FROM projects" 2>/dev/null
sudo -u postgres psql -d audit_platform -Atc "SELECT count(*) FROM working_paper" 2>/dev/null
