#!/bin/bash
# orm_extra 都是「迁移账上有但真实 schema 缺」的同款漂移。psql 幂等重放全部历史迁移做最终收口：
cd /opt/gt-new-plan/backend/migrations
ERR_TOTAL=0
for f in $(ls V*.sql | sort -V); do
  ERRS=$(sudo -u postgres psql -d audit_platform -v ON_ERROR_STOP=0 -q -f "$f" 2>&1 | grep -c "ERROR" || true)
  if [ "$ERRS" != "0" ]; then echo "$f: errors=$ERRS"; fi
  ERR_TOTAL=$((ERR_TOTAL + ERRS))
done
echo "TOTAL_ERRORS=$ERR_TOTAL"
echo "--- 关键表终核对 ---"
sudo -u postgres psql -d audit_platform -Atc "SELECT to_regclass('formula_setting'), to_regclass('formula_template_subscription'), to_regclass('note_content_template_versions'), to_regclass('formula_sync_item'), to_regclass('consol_note_structure_lock_entity'), to_regclass('formula_publish'), to_regclass('consol_note_value_confirmation'), to_regclass('consol_note_mapping_binding')"
echo "--- projecttype 枚举补值 ---"
sudo -u postgres psql -d audit_platform -Atc "ALTER TYPE projecttype ADD VALUE IF NOT EXISTS 'enterprise_income_tax_settlement'" 2>&1 | head -1
echo "--- 重启 ---"
systemctl restart gt-backend
sleep 14
systemctl is-active gt-backend
