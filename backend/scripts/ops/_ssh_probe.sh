#!/bin/bash
# 一次性勘察脚本（服务器端执行）
echo "--- 端口占用 ---"
ss -tln | tail -n +2 | sed 's/.*:\([0-9]*\).*/\1/' | sort -un | tr '\n' ' '
echo
echo "--- python ---"
python3 --version 2>&1
echo "--- 运行中的相关服务 ---"
systemctl list-units --type=service --state=running 2>/dev/null | grep -iE 'mysql|postgres|nginx|redis|docker|containerd' | head -8
echo "--- 关键端口逐一检查 ---"
for p in 80 443 5432 6379 9980 3030 8080 8000; do
  if ss -tln | grep -q ":$p "; then echo "$p: 占用"; else echo "$p: 空闲"; fi
done
echo "--- 防火墙 ---"
ufw status 2>/dev/null | head -3
echo "--- 代理/网络 ---"
curl -s -o /dev/null -w "github: %{http_code}\n" --max-time 10 https://github.com 2>&1
