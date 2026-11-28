#!/bin/bash
# 启动确认（多等一会）
sleep 15
systemctl is-active gt-backend
echo "--- 最近日志 ---"
journalctl -u gt-backend --since '2 minutes ago' --no-pager 2>/dev/null | grep -viE 'mineru|guidance_extract|note_validation|GIN index|LibreOffice' | tail -12
echo "--- Ready 计数 ---"
journalctl -u gt-backend --since '3 minutes ago' --no-pager 2>/dev/null | grep -c "Ready on port 9980" || true
