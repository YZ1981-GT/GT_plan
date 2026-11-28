#!/bin/bash
# 全面重放 V190~V207 的 DDL 迁移（psql 幂等风格，账实漂移修复）
cd /opt/gt-new-plan/backend/migrations
TOTAL_ERR=0
for f in V190__add_missing_columns_fix_orm_drift.sql \
         V191__deliverable_edit_and_writeback_integrity.sql \
         V192__ai_model_config_add_api_key_and_expand_provider.sql \
         V193__ai_model_runtime_options_and_remote_ocr.sql \
         V194__seed_gt_enterprise_ai_model_presets.sql \
         V195__gt_qwen38_reasoning_effort_user_selectable.sql \
         V196__ai_model_reasoning_effort_add_xhigh.sql \
         V197__ai_model_config_deployment_local_first_routing.sql \
         V198__knowledge_documents_background_ocr.sql \
         V199__formula_global_settings_and_templates.sql \
         V202__consol_note_mapping_reuse_and_reference.sql \
         V203__partner_manager_edit_level_backfill.sql \
         V204__consol_note_template_push_log.sql \
         V205__fix_export_schema_drift.sql \
         V206__consol_scope_version_auto_record.sql \
         V207__restore_tb_aux_balance_summary.sql; do
  ERRS=$(sudo -u postgres psql -d audit_platform -v ON_ERROR_STOP=0 -q -f "$f" 2>&1 | grep -c "ERROR" || true)
  echo "$f: errors=$ERRS"
  TOTAL_ERR=$((TOTAL_ERR + ERRS))
done
echo "TOTAL_ERRORS=$TOTAL_ERR"
echo "--- 关键对象核对 ---"
sudo -u postgres psql -d audit_platform -Atc "SELECT column_name FROM information_schema.columns WHERE table_name='working_paper' AND column_name IN ('quality_score','procedure_completion_rate','workflow_status')" | tr '\n' ' '
echo
sudo -u postgres psql -d audit_platform -Atc "SELECT to_regclass('formula_setting'), to_regclass('formula_template'), to_regclass('formula_sync_item')"
