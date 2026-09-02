-- R151: 回滚 V151（底稿 HTML ↔ OnlyOffice 双向回写的内容版本域/bundle/application/room/evidence schema）
--
-- Spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 9
--
-- ⚠️ 回滚会丢弃（整表 DROP）：
--   - 全部 content version / representation / entry pointer / upgrade candidate；
--   - 全部 definition artifact / typed null marker registry / definition bundle；
--   - 全部 room / participant / client confirmation / forcesave request / close intent（含 event）；
--   - 全部 callback delivery / recovery case（含 event）/ content application（含 event）/
--     operation（含 event、contributor）/ conflict；
--   - 全部 sync test run / 逐 scenario evidence；
--   - artifact 台账与 revision 0 回填台账。
--
-- ⚠️ **artifact 物理文件不会被删除**：DROP 掉 `working_paper_artifact` 后
--    `storage/{project}/workpapers/` 下的 `.staging/.versions/.incoming/.evidence/
--    .upgrade-candidates` 目录仍在磁盘上，且失去全部追踪（无法再判 orphan）。
--    回滚前须先导出 `SELECT relative_path, sha256, kind, state FROM working_paper_artifact`
--    作为孤儿清单，否则只能靠人工比对目录。
--
-- ⚠️ **`working_paper.content_revision` 与 `current_content_version_id` 的删除不可逆**：
--    任何已产生的业务内容 revision 计数在回滚后消失；重新前滚只会从 0 重新回填，
--    历史 content version 无法从 `parsed_data`/`file_version` 重建。
--
-- DROP 顺序 = V151 建表顺序的逆序（先删引用方，再删被引用方），
-- 并在 DROP 表之前先摘掉 working_paper 上的 FK/CHECK/列，避免 RESTRICT 依赖阻塞。

-- ── 1. 先摘 working_paper 的增量列与约束（它们引用 content_version） ──────────
ALTER TABLE working_paper DROP CONSTRAINT IF EXISTS fk_wp_current_content_version;
ALTER TABLE working_paper DROP CONSTRAINT IF EXISTS ck_wp_content_revision_non_negative;
ALTER TABLE working_paper
    DROP COLUMN IF EXISTS current_content_version_id,
    DROP COLUMN IF EXISTS content_revision;

-- ── 2. evidence / conflict / timeline 等叶子实体 ─────────────────────────────
DROP TABLE IF EXISTS working_paper_entry_evidence_scenario CASCADE;
DROP TABLE IF EXISTS working_paper_sync_test_run CASCADE;
DROP TABLE IF EXISTS working_paper_sync_conflict CASCADE;
DROP TABLE IF EXISTS working_paper_sync_operation_contributor CASCADE;
DROP TABLE IF EXISTS working_paper_sync_operation_event CASCADE;
DROP TABLE IF EXISTS working_paper_content_application_event CASCADE;
DROP TABLE IF EXISTS working_paper_oo_close_intent_event CASCADE;
DROP TABLE IF EXISTS working_paper_callback_recovery_case_event CASCADE;

-- ── 3. delivery → operation → application → recovery case → request 链 ───────
DROP TABLE IF EXISTS working_paper_callback_delivery CASCADE;
DROP TABLE IF EXISTS working_paper_sync_operation CASCADE;
DROP TABLE IF EXISTS working_paper_callback_recovery_case CASCADE;
DROP TABLE IF EXISTS working_paper_content_application CASCADE;
DROP TABLE IF EXISTS working_paper_oo_close_intent CASCADE;
DROP TABLE IF EXISTS working_paper_forcesave_request CASCADE;
DROP TABLE IF EXISTS working_paper_oo_client_confirmation CASCADE;
DROP TABLE IF EXISTS working_paper_oo_participant CASCADE;
DROP TABLE IF EXISTS working_paper_oo_room CASCADE;

-- ── 4. scope index / pending mutation / candidate / pointer / representation ──
DROP TABLE IF EXISTS working_paper_sync_scope_index CASCADE;
DROP TABLE IF EXISTS working_paper_pending_mutation CASCADE;
DROP TABLE IF EXISTS working_paper_representation_upgrade_candidate CASCADE;
DROP TABLE IF EXISTS working_paper_sync_entry_state CASCADE;
DROP TABLE IF EXISTS working_paper_content_representation CASCADE;
DROP TABLE IF EXISTS working_paper_content_version CASCADE;

-- ── 5. definition bundle / marker registry / definition artifact ─────────────
DROP TABLE IF EXISTS working_paper_sync_definition_bundle CASCADE;
DROP TABLE IF EXISTS working_paper_sync_definition_null_marker CASCADE;
DROP TABLE IF EXISTS working_paper_sync_definition_artifact CASCADE;

-- ── 6. artifact 台账与回填台账 ───────────────────────────────────────────────
DROP TABLE IF EXISTS working_paper_content_revision_backfill_ledger CASCADE;
DROP TABLE IF EXISTS working_paper_artifact CASCADE;

-- ── 7. 触发器函数（表已删，函数需单独回收） ─────────────────────────────────
DROP FUNCTION IF EXISTS wpsync_check_backfill_ledger_immutable() CASCADE;
DROP FUNCTION IF EXISTS wpsync_forbid_timeline_mutation() CASCADE;
DROP FUNCTION IF EXISTS wpsync_check_scenario_identity() CASCADE;
DROP FUNCTION IF EXISTS wpsync_check_scenario_immutable() CASCADE;
DROP FUNCTION IF EXISTS wpsync_check_test_run_immutable() CASCADE;
DROP FUNCTION IF EXISTS wpsync_check_delivery_durable_fact() CASCADE;
DROP FUNCTION IF EXISTS wpsync_check_delivery_operation_link() CASCADE;
DROP FUNCTION IF EXISTS wpsync_check_operation_binding_immutable() CASCADE;
DROP FUNCTION IF EXISTS wpsync_check_operation_application_link() CASCADE;
DROP FUNCTION IF EXISTS wpsync_check_operation_duplicate_link() CASCADE;
DROP FUNCTION IF EXISTS wpsync_check_application_mutation() CASCADE;
DROP FUNCTION IF EXISTS wpsync_check_application_identity() CASCADE;
DROP FUNCTION IF EXISTS wpsync_check_recovery_incoming() CASCADE;
DROP FUNCTION IF EXISTS wpsync_check_close_intent_promotion() CASCADE;
DROP FUNCTION IF EXISTS wpsync_check_request_identity() CASCADE;
DROP FUNCTION IF EXISTS wpsync_check_request_frozen() CASCADE;
DROP FUNCTION IF EXISTS wpsync_check_client_confirmation() CASCADE;
DROP FUNCTION IF EXISTS wpsync_check_room_monotonic() CASCADE;
DROP FUNCTION IF EXISTS wpsync_check_scope_index_update() CASCADE;
DROP FUNCTION IF EXISTS wpsync_forbid_scope_index_delete() CASCADE;
DROP FUNCTION IF EXISTS wpsync_check_upgrade_candidate() CASCADE;
DROP FUNCTION IF EXISTS wpsync_check_entry_state_pointer() CASCADE;
DROP FUNCTION IF EXISTS wpsync_check_representation_immutable() CASCADE;
DROP FUNCTION IF EXISTS wpsync_check_representation_identity() CASCADE;
DROP FUNCTION IF EXISTS wpsync_check_content_version_immutable() CASCADE;
DROP FUNCTION IF EXISTS wpsync_check_bundle_immutable() CASCADE;
DROP FUNCTION IF EXISTS wpsync_check_bundle_slots() CASCADE;
DROP FUNCTION IF EXISTS wpsync_assert_bundle_slot(uuid, text, text, text, text) CASCADE;
DROP FUNCTION IF EXISTS wpsync_check_null_marker_immutable() CASCADE;
DROP FUNCTION IF EXISTS wpsync_check_definition_immutable() CASCADE;
DROP FUNCTION IF EXISTS wpsync_check_artifact_transition() CASCADE;
DROP FUNCTION IF EXISTS wpsync_check_artifact_incoming_path() CASCADE;
DROP FUNCTION IF EXISTS wpsync_is_uuid_text(text) CASCADE;
DROP FUNCTION IF EXISTS wpsync_is_opaque_resource_id(text) CASCADE;
DROP FUNCTION IF EXISTS wpsync_is_digest(text) CASCADE;
