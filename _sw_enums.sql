-- 从 dev1.0 (audit_platform) 导出 102 个枚举类型
-- 幂等：已存在则跳过

DO $$ BEGIN
    CREATE TYPE account_category AS ENUM ('asset','liability','equity','revenue','expense');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE account_direction AS ENUM ('debit','credit');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE account_source AS ENUM ('standard','client');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE accountcategory AS ENUM ('asset','liability','equity','revenue','expense');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE activation_type AS ENUM ('activate','rollback','force_unbind');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE adjustment_type AS ENUM ('aje','rje','cf');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE ai_confirmation_status_enum AS ENUM ('pending','accepted','modified','rejected','regenerated');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE ai_content_type_enum AS ENUM ('data_fill','analytical_review','risk_alert','test_summary','note_draft','review_finding');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE ai_model_type_enum AS ENUM ('chat','embedding','ocr');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE ai_provider_enum AS ENUM ('ollama','openai_compatible','paddleocr','deepseek','zhipu','qwen','azure_openai','custom');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE analysis_report_status_enum AS ENUM ('pending','analyzing','completed','failed');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE applicable_scenario AS ENUM ('control_test','substantive_test');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE approval_status_enum AS ENUM ('pending','approved','rejected');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE artifact_status AS ENUM ('active','expired','consumed');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE assertion_level AS ENUM ('existence','completeness','accuracy','cutoff','classification','occurrence','rights_obligations','valuation');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE audit_plan_status AS ENUM ('draft','approved','revised');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE cash_flow_category AS ENUM ('operating','investing','financing','supplementary');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE chain_match_status_enum AS ENUM ('matched','mismatched','missing');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE chat_role_enum AS ENUM ('user','assistant','system');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE check_status_enum AS ENUM ('pending','pass_','fail','na');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE clause_type_enum AS ENUM ('amount','payment_terms','delivery_terms','penalty','guarantee','pledge','related_party','special_terms','pricing','duration');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE company_type AS ENUM ('listed','non_listed');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE competencerating AS ENUM ('reliable','additional_procedures_needed','unreliable');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE confidence_level_enum AS ENUM ('high','medium','low');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE confirmation_check_type_enum AS ENUM ('address_verify','reply_ocr','amount_compare','seal_check');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE confirmation_list_status AS ENUM ('draft','approved','sent','received','reconciled');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE confirmation_result_status AS ENUM ('confirmed','discrepancy','no_response','alternative_procedures');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE confirmation_risk_level_enum AS ENUM ('high','medium','low','pass_');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE confirmation_type_enum AS ENUM ('bank','customer','vendor','lawyer','other');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE consolmethod AS ENUM ('full','equity','proportional');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE content_type AS ENUM ('table','text','mixed');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE contract_analysis_status_enum AS ENUM ('pending','analyzing','completed','failed');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE contract_link_type_enum AS ENUM ('revenue_recognition','cutoff_test','contingent_liability','related_party','guarantee');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE contract_type_enum AS ENUM ('sales','purchase','service','lease','loan','guarantee','other');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE dataset_status AS ENUM ('staged','active','superseded','failed','rolled_back');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE document_type_enum AS ENUM ('sales_invoice','purchase_invoice','bank_receipt','bank_statement','outbound_order','inbound_order','logistics_order','voucher','expense_report','toll_invoice','contract','customs_declaration','unknown');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE eliminationentrytype AS ENUM ('equity','internal_trade','internal_ar_ap','unrealized_profit','other');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE evaluationstatusenum AS ENUM ('pending','accepted','requires_followup');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE evidence_chain_type_enum AS ENUM ('revenue','purchase','expense');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE execution_status_enum AS ENUM ('not_started','in_progress','completed','not_applicable');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE export_task_status AS ENUM ('queued','processing','completed','failed');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE export_task_type AS ENUM ('single_document','full_archive');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE final_treatment_enum AS ENUM ('adjusted','unadjusted','disclosed','no_action');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE financial_report_type AS ENUM ('balance_sheet','income_statement','cash_flow_statement','equity_statement','cash_flow_supplement','impairment_provision');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE follow_up_status_enum AS ENUM ('open','in_progress','resolved','accepted_risk');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE going_concern_conclusion AS ENUM ('no_material_uncertainty','material_uncertainty_disclosed','qualified','adverse');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE gt_wp_type AS ENUM ('preliminary','risk_assessment','control_test','substantive','completion','specific','general','permanent');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE import_event_outbox_status AS ENUM ('pending','published','failed','processing');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE import_status AS ENUM ('pending','processing','completed','failed','rolled_back');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE inclusionreason AS ENUM ('subsidiary','associate','joint_venture','special_purpose');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE instructionstatus AS ENUM ('draft','sent','acknowledged');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE issue_type_enum AS ENUM ('control_deficiency','process_improvement','compliance','other');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE job_status_enum AS ENUM ('pending','queued','running','validating','writing','activating','completed','failed','canceled','timed_out','interrupted');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE knowledge_access_level AS ENUM ('public','project_group','private');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE knowledge_source_type_enum AS ENUM ('trial_balance','journal','auxiliary','contract','document_scan','workpaper','adjustment','elimination','confirmation','review_comment','prior_year_summary','knowledge_doc','address_coordinate');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE mapping_type AS ENUM ('auto_exact','auto_fuzzy','manual');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE match_result_enum AS ENUM ('matched','mismatched','unmatched');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE milestone_type_enum AS ENUM ('PLANNING','FIELDWORK','REVIEW','REPORT','COMPLETION');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE misstatement_type AS ENUM ('factual','judgmental','projected');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE modification_type_enum AS ENUM ('addition','deletion','replacement');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE note_status AS ENUM ('draft','confirmed');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE opinion_type AS ENUM ('unqualified','qualified','adverse','disclaimer');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE opiniontypeenum AS ENUM ('unqualified','qualified','adverse','disclaimer');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE pbc_status_enum AS ENUM ('PENDING','RECEIVED','REVIEWED','REJECTED');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE permissionlevel AS ENUM ('edit','review','readonly');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE procedure_type_enum AS ENUM ('risk_assessment','control_test','substantive');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE projectstatus AS ENUM ('created','planning','execution','completion','reporting','archived');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE projecttype AS ENUM ('annual','special','ipo','internal_control','capital_verification','tax_audit','enterprise_income_tax_settlement');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE projectuserrole AS ENUM ('partner','manager','auditor','qc','eqcr','readonly');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE recognition_status_enum AS ENUM ('pending','processing','completed','failed');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE reconciliationstatus AS ENUM ('matched','unmatched','adjusted');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE region_type AS ENUM ('formula','manual','ai_fill','conclusion','cross_ref');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE report_line_mapping_type AS ENUM ('ai_suggested','manual','reference_copied');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE report_status AS ENUM ('draft','review','eqcr_approved','final');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE report_type AS ENUM ('balance_sheet','income_statement','cash_flow');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE review_comment_status AS ENUM ('open','replied','resolved');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE review_status AS ENUM ('draft','pending_review','approved','rejected');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE review_status_enum AS ENUM ('draft','pending_review','approved','rejected');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE reviewstatusenum AS ENUM ('draft','pending_review','approved','rejected');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE risk_level AS ENUM ('high','medium','low');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE risk_level_enum AS ENUM ('high','medium','low');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE sampling_method AS ENUM ('mus','attribute','random','systematic','stratified');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE sampling_type AS ENUM ('statistical','non_statistical');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE scopechangetype AS ENUM ('none','new_inclusion','exclusion','method_change');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE scopecompanytype AS ENUM ('parent','subsidiary','associate','joint_venture');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE session_type_enum AS ENUM ('general','contract','workpaper','confirmation');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE severity_level AS ENUM ('high','medium','low');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE source_template AS ENUM ('soe','listed');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE source_type_enum AS ENUM ('workpaper','contract','confirmation','document','report');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE subsequent_event_type AS ENUM ('adjusting','non_adjusting','ADJUSTING','NON_ADJUSTING');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE sync_status_enum AS ENUM ('IDLE','SYNCING','SYNCED','CONFLICT','ERROR');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE sync_type_enum AS ENUM ('UPLOAD','DOWNLOAD','CONFLICT_RESOLUTION','LOCK','UNLOCK','EXPORT','IMPORT');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE template_level_enum AS ENUM ('firm_default','group_custom','project');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE template_type_enum AS ENUM ('report_soe','report_listed','workpaper_preset','workpaper_custom');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE tradetype AS ENUM ('goods','services','assets','other');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE userrole AS ENUM ('admin','partner','manager','auditor','qc','eqcr','readonly','site_lead');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE workpaper_task_status_enum AS ENUM ('PENDING','PROCESSING','COMPLETED','FAILED');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE wp_file_status AS ENUM ('draft','edit_complete','under_review','revision_required','review_passed','archived','review_level1_passed','review_level2_passed');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE wp_review_status AS ENUM ('not_submitted','pending_level1','level1_in_progress','level1_passed','level1_rejected','pending_level2','level2_in_progress','level2_passed','level2_rejected','pending_level3','level3_in_progress','level3_passed','level3_rejected','pending_level4','level4_in_progress','level4_passed','level4_rejected');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE wp_source_type AS ENUM ('template','manual','imported');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE wp_status AS ENUM ('not_started','in_progress','draft_complete','review_passed','archived');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    CREATE TYPE wp_template_status AS ENUM ('draft','published','deprecated');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
