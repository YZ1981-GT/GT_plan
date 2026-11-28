#!/bin/bash
cd /opt/gt-new-plan/backend/migrations
sudo -u postgres psql -d audit_platform -v ON_ERROR_STOP=0 -f V004__add_review_priority.sql 2>&1 | grep -A1 "ERROR" | head -4
echo "--- 本地对照 V004 内容 ---"
