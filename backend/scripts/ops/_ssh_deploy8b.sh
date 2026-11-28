#!/bin/bash
# V208 修正重放 + 失败账清理（version 是 varchar）+ runner 校验 + 重启
cd /opt/gt-new-plan/backend/migrations
echo "--- V208 错误详情 ---"
sudo -u postgres psql -d audit_platform -v ON_ERROR_STOP=1 -f V208__seed_gt_qwen37_max_preset.sql 2>&1 | grep -B2 "ERROR" | head -8
echo "--- provider 枚举值 ---"
sudo -u postgres psql -d audit_platform -Atc "SELECT enum_range(NULL::ai_provider_enum)" | tr ',' ' '
