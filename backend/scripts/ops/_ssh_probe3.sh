#!/bin/bash
# 勘察第三轮：现有 GT 部署的细节
echo "--- gt-backend.service 定义 ---"
cat /etc/systemd/system/gt-backend.service 2>/dev/null
echo
echo "--- /opt/gt-new-plan 目录 ---"
ls /opt/gt-new-plan/ 2>/dev/null | head -20
echo "--- 当前部署的分支/提交 ---"
cd /opt/gt-new-plan 2>/dev/null && git branch --show-current && git log --oneline -1 && git remote -v | head -2
echo "--- backend venv ---"
ls /opt/gt-new-plan/.venv/Scripts 2>/dev/null | head -3 || ls /opt/gt-new-plan/.venv/bin 2>/dev/null | head -3 || ls /opt/venv*/bin 2>/dev/null | head -3
echo "--- 前端是否构建过 ---"
ls /opt/gt-new-plan/audit-platform/frontend/dist 2>/dev/null | head -5
ls /opt/gt-new-plan/frontend/dist 2>/dev/null | head -5
echo "--- nginx default 站点内容（前 40 行）---"
head -40 /etc/nginx/sites-enabled/default 2>/dev/null
echo "--- 磁盘上 9980 进程 cwd ---"
ls -l /proc/452386/cwd 2>/dev/null
cat /proc/452386/cmdline 2>/dev/null | tr '\0' ' '; echo
