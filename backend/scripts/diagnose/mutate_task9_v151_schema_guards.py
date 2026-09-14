"""Task 9 变异检验：证明 V151 的每条约束都真的被守卫锁死（RED/GREEN/ANCHOR-MISS/WRONG-TEST）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 9
Requirements: 2.1, 2.3, 2.4, 2.5, 2.6, 3.1, 3.6, 3.7, 4.1, 4.11, 5.4, 5.5, 5.10, 8.1, 12.10, 12.11, 13.5
Properties: P4 / P5 / P10 / P11 / P18 / P62 / P64 / P68 / P69

═══ 为什么每条变异都改 `V151__*.sql` 本身而不是改守卫 ═══

守卫（`backend/tests/workpaper_sync/test_v151_schema_contract.py`）把真实迁移文本
应用到 scratch schema 后跑 148 条违规写入，逐条要求被数据库拒绝。因此：

  * 把某条 CHECK 放宽成 `true`、把 partial unique 的键加宽、把 trigger 的
    `BEFORE UPDATE` 改成 `BEFORE DELETE`（= 该守卫不再触发）⇒ 对应负控制变成
    「未被拒绝」⇒ 守卫必须打红。
  * 打红=RED（守卫有效）；不红=GREEN（守卫缺陷）；红了但不是预期那条=WRONG-TEST；
    锚点没命中/命中多处=ANCHOR-MISS（脚本缺陷）。

**变异一律保持 SQL 合法**：若变异让迁移语法错误，全部 19 条测试都会因
`test_migration_applies_and_is_idempotent` 连带打红 ⇒ 判定退化成 WRONG-TEST，
证明不了「这一条约束」被锁死。故不采用「删掉 RAISE 语句」这类会破坏
plpgsql 结构的手法，而是：
  - CHECK：整行替换成恒真式（`CHECK (true)` / `CHECK (true OR ...`）
  - UNIQUE：把键加宽（加 `, id`）使其恒不冲突
  - trigger：把触发时机改成不覆盖被测操作（UPDATE 守卫改成 DELETE 时机）
  - plpgsql 分支：把 `IF <cond> THEN` 整行改成 `IF false THEN`

M27 是**回归变异**：删掉 `authority_model_type IS NOT NULL` 一行，把 CHECK 退回
三值逻辑漏放 NULL 的形态 —— 这正是本任务靠行为守卫（而非 grep 守卫）抓出的真实 bug。

用法（仓库根）:
    python backend/scripts/diagnose/mutate_task9_v151_schema_guards.py --list
    python backend/scripts/diagnose/mutate_task9_v151_schema_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_task9_v151_schema_guards.py --run all \
        --out .kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/task9-v151-schema/mutation_report.json
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
MIG = "backend/migrations/V151__workpaper_sync_content_application_bundle_scope.sql"

#: 覆盖面分母：本任务只有一个守卫文件（纯 schema 层，无生产 Python 代码）。
GUARD_FILES = {
    "test_v151_schema_contract.py": "Task 9 新建：V151 约束行为守卫（真实 PG scratch schema）",
}

MUTATIONS: list[Mutation] = [
    # ── Property 4 ─────────────────────────────────────────────────────
    Mutation(
        id="M01", side="be", path=MIG, kind="replace",
        anchor="    CONSTRAINT uq_wpcv_wp_revision UNIQUE (wp_id, revision),",
        new="    CONSTRAINT uq_wpcv_wp_revision UNIQUE (wp_id, revision, id),",
        want="test_property_4_business_revision_orthogonal_to_representation",
        why="把 (wp_id,revision) 唯一键加宽成含 id ⇒ 同 wp 可插两条 revision=1，"
            "业务 revision 不再单调唯一；不能直接删约束行（下方还有多条 CONSTRAINT，"
            "删行不影响语法但会让 P4-dup-revision 与 uq 名断言同时红，判据不清）",
    ),
    Mutation(
        id="M02", side="be", path=MIG, kind="replace",
        anchor="    BEFORE UPDATE ON working_paper_content_version",
        new="    BEFORE DELETE ON working_paper_content_version",
        want="test_property_4_business_revision_orthogonal_to_representation",
        why="把 immutable 守卫的触发时机从 UPDATE 改成 DELETE ⇒ 历史 content version 可被"
            "原地改写（P4-content-version-immutable 不再被拒）。改时机而不是改函数体，"
            "是为了保持 plpgsql 合法、不牵连迁移应用失败",
    ),
    Mutation(
        id="M03", side="be", path=MIG, kind="replace",
        anchor="    CONSTRAINT uq_wpcr_generation UNIQUE (wp_id, entry_id, content_version_id, generation),",
        new="    CONSTRAINT uq_wpcr_generation UNIQUE (wp_id, entry_id, content_version_id, generation, id),",
        want="test_property_4_business_revision_orthogonal_to_representation",
        why="representation generation 唯一键加宽 ⇒ 同 (wp,entry,version,generation) 可重复，"
            "representation 代际不再确定（P4-dup-generation 不再被拒）",
    ),
    Mutation(
        id="M04", side="be", path=MIG, kind="replace",
        anchor="    CONSTRAINT ck_wpcrbl_revision_zero CHECK (backfilled_content_revision = 0),",
        new="    CONSTRAINT ck_wpcrbl_revision_zero CHECK (true),",
        want="test_property_4_business_revision_orthogonal_to_representation",
        why="回填台账允许非 0 revision ⇒ 回填可伪造历史业务版本（P4-backfill-ledger-non-zero 不再被拒）",
    ),

    # ── Property 5 ─────────────────────────────────────────────────────
    Mutation(
        id="M05", side="be", path=MIG, kind="replace",
        anchor="        kind <> 'incoming' OR state IN ('staged', 'durable', 'quarantined', 'orphan', 'deleted')),",
        new="        kind <> 'incoming' OR state IN ('staged', 'durable', 'quarantined', 'orphan', 'deleted', 'published')),",
        want="test_property_5_no_dangling_visible_state",
        why="放开 incoming 可 published ⇒ resolver 能解析到 incoming、incoming 可直接晋升为"
            "可见 artifact（P5-incoming-published 不再被拒）",
    ),
    Mutation(
        id="M06", side="be", path=MIG, kind="replace",
        anchor="    IF position(v_expected in NEW.relative_path) = 0 THEN",
        new="    IF false THEN",
        want="test_property_5_no_dangling_visible_state",
        why="关掉 `.incoming/{wp}/{delivery}/` 路径 sealing 校验 ⇒ incoming 路径可绑到任意"
            "目录/任意实体（P5-incoming-path-not-sealed 不再被拒）",
    ),
    Mutation(
        id="M07", side="be", path=MIG, kind="replace",
        anchor="    IF v_artifact_state <> 'published' THEN",
        new="    IF false THEN",
        want="test_property_5_no_dangling_visible_state",
        why="entry current pointer 不再要求 published artifact ⇒ 出现「pointer 指向未发布/"
            "候选 artifact」的悬空可见态（P5-entry-pointer-to-staged-artifact 不再被拒）",
    ),
    Mutation(
        id="M08", side="be", path=MIG, kind="replace",
        anchor="    IF OLD.kind = 'incoming' THEN",
        new="    IF false THEN",
        want="test_property_5_no_dangling_visible_state",
        why="关掉 incoming 的 durable/quarantined 互转禁令 ⇒ quarantined 可被 release 成 durable "
            "并进入 engine（P5-incoming-quarantined-to-durable / -durable-to-quarantined 不再被拒）",
    ),

    # ── Property 10 ────────────────────────────────────────────────────
    Mutation(
        id="M09", side="be", path=MIG, kind="replace",
        anchor="    CONSTRAINT uq_wppm_idempotency UNIQUE (wp_id, entry_id, user_id, idempotency_key),",
        new="    CONSTRAINT uq_wppm_idempotency UNIQUE (wp_id, entry_id, user_id, idempotency_key, id),",
        want="test_property_10_single_commit_and_representation_idempotency",
        why="pending mutation 幂等键加宽 ⇒ 同 token 可重复创建，flush→commit 会二次提交"
            "（P10-pending-mutation-dup-key 不再被拒）",
    ),
    Mutation(
        id="M10", side="be", path=MIG, kind="replace",
        anchor="    application_key CHAR(64) NOT NULL UNIQUE,",
        new="    application_key CHAR(64) NOT NULL,",
        want="test_property_10_single_commit_and_representation_idempotency",
        why="去掉 application_key 唯一性 ⇒ 同一 frozen identity 可产生多个 application，"
            "「frozen application 恰好一次」失效（P10-duplicate-application-key 不再被拒）",
    ),
    Mutation(
        id="M11", side="be", path=MIG, kind="replace",
        anchor="        state = 'committed'",
        new="        true",
        want="test_property_10_single_commit_and_representation_idempotency",
        why="未 committed 也可预留 result_operation/result_version ⇒ 重放会返回尚未提交的"
            "伪结果（P10-pending-uncommitted-with-result 不再被拒）",
    ),

    # ── Property 11 ────────────────────────────────────────────────────
    Mutation(
        id="M12", side="be", path=MIG, kind="replace",
        anchor="    ON working_paper_oo_client_confirmation (room_id, participant_id, generation)",
        new="    ON working_paper_oo_client_confirmation (room_id, participant_id, generation, id)",
        want="test_property_11_unique_descriptor_and_ready_confirmation",
        why="active confirmation 的 partial unique 键加宽 ⇒ 同 (room,participant,generation) 可有"
            "多个有效 descriptor 确认，「唯一 descriptor」失效（P11-duplicate-active-confirmation 不再被拒）",
    ),
    Mutation(
        id="M13", side="be", path=MIG, kind="replace",
        anchor="    BEFORE INSERT OR UPDATE ON working_paper_oo_client_confirmation",
        new="    BEFORE DELETE ON working_paper_oo_client_confirmation",
        want="test_property_11_unique_descriptor_and_ready_confirmation",
        why="关掉 confirmation 的 identity 校验触发器 ⇒ 陈旧 generation/错 bundle 的 descriptor "
            "也能确认（P11-confirmation-stale-generation / -bundle-not-locked 不再被拒）",
    ),

    # ── Property 18 ────────────────────────────────────────────────────
    Mutation(
        id="M14", side="be", path=MIG, kind="replace",
        anchor="    CONSTRAINT uq_wpso_application UNIQUE (application_id),",
        new="    CONSTRAINT uq_wpso_application UNIQUE (application_id, id),",
        want="test_property_18_many_deliveries_one_frozen_application",
        why="operation.application_id 不再唯一 ⇒ 一个 application 可被多个 primary 绑定，"
            "「1 primary + N-1 duplicates」失效（P18-two-primaries-same-application 不再被拒）",
    ),
    Mutation(
        id="M16", side="be", path=MIG, kind="replace",
        anchor="        OR (duplicate_of_operation_id IS NOT NULL AND state = 'duplicate' AND application_id IS NULL)),",
        new="        OR duplicate_of_operation_id IS NOT NULL),",
        want="test_property_18_many_deliveries_one_frozen_application",
        why="duplicate 不再强制 terminal + application 空 ⇒ loser shell 可继续流转甚至绑定"
            "application（P18-duplicate-state-not-terminal 不再被拒）",
    ),
    Mutation(
        id="M17", side="be", path=MIG, kind="replace",
        anchor="        OR ((application_id IS NOT NULL) <> (callback_recovery_case_id IS NOT NULL))),",
        new="        OR true),",
        want="test_property_18_many_deliveries_one_frozen_application",
        why="durable delivery 不再要求恰一个 owner ⇒ durable incoming 可成为无所有者死路"
            "（P18-durable-delivery-zero-owner 不再被拒）",
    ),
    Mutation(
        id="M18", side="be", path=MIG, kind="replace",
        anchor="    WHERE kind = 'close_capture' AND state IN ('frozen', 'pending', 'accepted', 'correlated');",
        new="    WHERE kind = 'close_capture' AND state IN ('nonexistent_state');",
        want="test_property_18_many_deliveries_one_frozen_application",
        why="close-capture partial unique 的 open-state 集合被换空 ⇒ 同 generation 可有多个 open "
            "close_capture，at-most-one 失效（P18-two-open-close-captures 不再被拒）",
    ),
    Mutation(
        id="M19", side="be", path=MIG, kind="replace",
        anchor="        OR (recovery_request_id IS NULL AND application_id IS NULL AND operation_id IS NULL)),",
        new="        OR true),",
        want="test_property_18_many_deliveries_one_frozen_application",
        why="recovery case claim 前可携带 operation/application/request ⇒ 「claim 前零三实体」"
            "与 download-only 恒空失效（P18-recovery-pre-claim-has-operation 不再被拒）",
    ),

    # ── Property 62 ────────────────────────────────────────────────────
    Mutation(
        id="M20", side="be", path=MIG, kind="replace",
        anchor="    BEFORE UPDATE ON working_paper_oo_room",
        new="    BEFORE DELETE ON working_paper_oo_room",
        want="test_property_62_server_last_applied_not_conflated_with_client_base",
        why="关掉 room 单调 fence 守卫 ⇒ durable/request sequence、write fence、eligibility epoch "
            "可回退，旧会话能覆盖新内容（P62-room-durable-sequence-regress 等不再被拒）",
    ),
    Mutation(
        id="M21", side="be", path=MIG, kind="replace",
        anchor="    CONSTRAINT ck_wpoor_client_confirmed_group CHECK (",
        new="    CONSTRAINT ck_wpoor_client_confirmed_group CHECK (true OR",
        want="test_property_62_server_last_applied_not_conflated_with_client_base",
        why="client-confirmed 快照可半缺（bundle id 有、digest 无）⇒ 服务端会按 revision 猜"
            "客户端内容，两套指针混同（P62-room-partial-client-confirmed 不再被拒）",
    ),

    # ── Property 64 ────────────────────────────────────────────────────
    Mutation(
        id="M22", side="be", path=MIG, kind="replace",
        anchor="    BEFORE UPDATE ON working_paper_content_application",
        new="    BEFORE DELETE ON working_paper_content_application",
        want="test_property_64_application_identity_uses_frozen_bundle_without_status",
        why="关掉 application identity 不可变 + effective sequence 单调守卫 ⇒ application_key/"
            "origin sequence 可被改写、effective sequence 可回退（P64-application-key-mutated 等不再被拒）",
    ),
    Mutation(
        id="M23", side="be", path=MIG, kind="replace",
        anchor="    CONSTRAINT uq_wpfr_idempotency UNIQUE (room_id, generation, initiated_by_participant_id, kind, idempotency_key),",
        new="    CONSTRAINT uq_wpfr_idempotency UNIQUE (room_id, generation, initiated_by_participant_id, kind, idempotency_key, id),",
        want="test_property_64_application_identity_uses_frozen_bundle_without_status",
        why="forcesave 复合幂等键加宽 ⇒ 同 (room,generation,initiator,kind,key) 可重复创建 request，"
            "重放不再返回同一 request/operation（P64-request-idempotency-reuse-same-participant 不再被拒）",
    ),
    Mutation(
        id="M24", side="be", path=MIG, kind="replace",
        anchor="    IF v_state <> 'durable' THEN",
        new="    IF false THEN",
        want="test_property_64_application_identity_uses_frozen_bundle_without_status",
        why="application 的 incoming 不再要求 state=durable ⇒ quarantined incoming 可创建 application "
            "并进入 engine（P64-application-on-quarantined-incoming 不再被拒）",
    ),

    # ── Property 68 ────────────────────────────────────────────────────
    Mutation(
        id="M25", side="be", path=MIG, kind="replace",
        anchor="    CONSTRAINT uq_wpsoe_sequence UNIQUE (operation_id, sequence_no),",
        new="    CONSTRAINT uq_wpsoe_sequence UNIQUE (operation_id, sequence_no, id),",
        want="test_property_68_timeline_complete_and_append_only",
        why="operation timeline 的 (operation_id,sequence_no) 不再唯一 ⇒ 同一 sequence 可写多条"
            "伪 event，timeline 不再单调（P68-operation-event-dup-sequence 不再被拒）",
    ),
    Mutation(
        id="M26", side="be", path=MIG, kind="replace",
        anchor="    BEFORE UPDATE OR DELETE ON working_paper_sync_operation_event",
        new="    BEFORE DELETE ON working_paper_sync_operation_event",
        want="test_property_68_timeline_complete_and_append_only",
        why="operation timeline 的 append-only 守卫不再覆盖 UPDATE ⇒ 既有 event 可被改写，"
            "「current state 只是 timeline 投影」失效（P68-operation-event-update 不再被拒）",
    ),
    Mutation(
        id="M27", side="be", path=MIG, kind="replace",
        anchor="    ON working_paper_content_application_event (application_id, folded_request_id)",
        new="    ON working_paper_content_application_event (application_id, folded_request_id, sequence_no)",
        want="test_property_68_timeline_complete_and_append_only",
        why="同 request 对同 application 可 fold 多次 ⇒ 幂等重放会产生第二个 sequence_folded event"
            "（P68-fold-same-request-twice 不再被拒）",
    ),
    Mutation(
        id="M28", side="be", path=MIG, kind="replace",
        anchor="    CONSTRAINT ck_wpoci_promoted_pair CHECK ((state = 'promoted') = (promoted_request_id IS NOT NULL))",
        new="    CONSTRAINT ck_wpoci_promoted_pair CHECK (true)",
        want="test_property_68_timeline_complete_and_append_only",
        why="close intent 可声称 promoted 而不携带 close_capture request ⇒ leader 提升不再"
            "exactly-once 可审计（P68-close-intent-promoted-without-request 不再被拒）",
    ),

    # ── Property 69 ────────────────────────────────────────────────────
    Mutation(
        id="M29", side="be", path=MIG, kind="replace",
        anchor="    CONSTRAINT ck_wpees_download_only_zero_entities CHECK (",
        new="    CONSTRAINT ck_wpees_download_only_zero_entities CHECK (true OR",
        want="test_property_69_evidence_closed_by_per_scenario_entities",
        why="download-only scenario 可携带 operation/application ⇒ 「download-only 零三实体」"
            "判据失效，evidence 可用一条 applied operation 冒充全部场景（P69-download-only-with-operation 不再被拒）",
    ),
    Mutation(
        id="M30", side="be", path=MIG, kind="replace",
        anchor="    CONSTRAINT uq_wpees_scenario UNIQUE (run_id, scenario_id, ordinal),",
        new="    CONSTRAINT uq_wpees_scenario UNIQUE (run_id, scenario_id, ordinal, id),",
        want="test_property_69_evidence_closed_by_per_scenario_entities",
        why="scenario 的 (run,scenario,ordinal) 不再唯一 ⇒ 同一场景可被替换/重复登记"
            "（P69-scenario-dup-ordinal 不再被拒）",
    ),
    Mutation(
        id="M31", side="be", path=MIG, kind="replace",
        anchor="    CONSTRAINT ck_wpstr_room_model CHECK (room_model IN ('shared', 'exclusive', 'none')),",
        new="    CONSTRAINT ck_wpstr_room_model CHECK (true),",
        want="test_property_69_evidence_closed_by_per_scenario_entities",
        why="room_model 退回自由文本 ⇒ scenario profile 可被人手写覆盖，required scenario set "
            "推导失去机器真源（P69-test-run-free-text-room-model 不再被拒）",
    ),

    # ── bundle typed slots ─────────────────────────────────────────────
    Mutation(
        id="M32", side="be", path=MIG, kind="replace",
        anchor="       AND p_value <> repeat('0', 64);",
        new="       AND true;",
        want="test_definition_bundle_typed_slots_are_locked",
        why="digest 单一真源放开全零 hash ⇒ 全零 hash 可充当 bundle/authority/application 身份"
            "（BUNDLE-zero-slot-digest 等不再被拒）",
    ),
    Mutation(
        id="M33", side="be", path=MIG, kind="replace",
        anchor="        IF v_state <> 'approved' THEN",
        new="        IF false THEN",
        want="test_definition_bundle_typed_slots_are_locked",
        why="bundle 的 definition child 不再要求 approved ⇒ candidate child 可组成 approved bundle "
            "并 finalize representation（BUNDLE-slot-child-not-approved 不再被拒）",
    ),
    Mutation(
        id="M34", side="be", path=MIG, kind="replace",
        anchor="    IF v_authority_model = 'projection_contract' THEN",
        new="    IF false THEN",
        want="test_definition_bundle_typed_slots_are_locked",
        why="projection_contract 不再强制三 child 全为 approved definition ⇒ 可用 typed null marker "
            "冒充 per-entry contract（BUNDLE-projection-contract-with-marker 不再被拒）",
    ),
    Mutation(
        id="M35", side="be", path=MIG, kind="replace",
        anchor="    IF v_marker_sha <> p_slot_digest THEN",
        new="    IF false THEN",
        want="test_definition_bundle_typed_slots_are_locked",
        why="marker digest 不再与 registry 比对 ⇒ 可伪造 typed null digest 进入 bundle canonical bytes"
            "（BUNDLE-marker-digest-forged 不再被拒）",
    ),
    Mutation(
        id="M36", side="be", path=MIG, kind="delete",
        anchor="            AND authority_model_type IS NOT NULL",
        want="test_definition_bundle_typed_slots_are_locked",
        why="回归变异：删掉显式 IS NOT NULL 后 CHECK 退回三值逻辑形态 —— kind='authority_model' 而 "
            "type=NULL 时 `NULL IN (...)` 使整条 CHECK 求值为 NULL（= 视为满足）而被静默放行。"
            "这条 bug 正是本任务用行为守卫抓出来的，grep 式守卫（只查 CHECK 存在）永远看不见",
    ),

    # ── scope index / conflict ─────────────────────────────────────────
    Mutation(
        id="M37", side="be", path=MIG, kind="replace",
        anchor="    CONSTRAINT ck_wpssi_opaque_resource_id CHECK (wpsync_is_opaque_resource_id(resource_id)),",
        new="    CONSTRAINT ck_wpssi_opaque_resource_id CHECK (true),",
        want="test_scope_index_is_authorization_only_and_tombstoned",
        why="scope key 放开纯数字 ⇒ numeric revision 可作 resource_id，不同 wp 的 revision 1 会"
            "在 authorization 索引里碰撞（SCOPE-numeric-revision-as-resource-id 不再被拒）",
    ),
    Mutation(
        id="M38", side="be", path=MIG, kind="replace",
        anchor="    IF OLD.retired_at IS NOT NULL AND NEW.retired_at IS NULL THEN",
        new="    IF false THEN",
        want="test_scope_index_is_authorization_only_and_tombstoned",
        why="tombstone 可被清空 ⇒ retired 的 resource id 能复活并被跨 scope 复用"
            "（SCOPE-tombstone-cleared 不再被拒）",
    ),
    Mutation(
        id="M39", side="be", path=MIG, kind="replace",
        anchor="    BEFORE DELETE ON working_paper_sync_scope_index",
        new="    AFTER TRUNCATE ON working_paper_sync_scope_index",
        want="test_scope_index_is_authorization_only_and_tombstoned",
        why="物理删除禁令的触发时机换成 TRUNCATE（FOR EACH ROW 在 TRUNCATE 下不触发）⇒ "
            "scope row 可被 DELETE，防 id 复用的 tombstone 机制失效（SCOPE-physical-delete 不再被拒）",
    ),
    Mutation(
        id="M40", side="be", path=MIG, kind="replace",
        anchor="    CONSTRAINT uq_wpsc_field UNIQUE (operation_id, stable_field_key, row_key, oo_location),",
        new="    CONSTRAINT uq_wpsc_field UNIQUE (operation_id, stable_field_key, row_key, oo_location, id),",
        want="test_conflict_and_participant_lease_constraints",
        why="冲突唯一键加宽 ⇒ 重复 callback 会为同一字段生成重复冲突记录"
            "（R81-conflict-duplicate-field 不再被拒）",
    ),
    Mutation(
        id="M41", side="be", path=MIG, kind="replace",
        anchor="    ON working_paper_oo_participant (room_id, user_id)",
        new="    ON working_paper_oo_participant (room_id, user_id, id)",
        want="test_conflict_and_participant_lease_constraints",
        why="active lease 的 partial unique 键加宽 ⇒ 同 room 同 user 可有多个未终结 lease，"
            "逐人授权租约失效（R26-duplicate-active-lease 不再被拒）",
    ),

    Mutation(
        id="M43", side="be", path=MIG, kind="replace",
        anchor="    IF v_t_application IS NULL OR v_t_duplicate IS NOT NULL OR v_t_state = 'duplicate' THEN",
        new="    IF false THEN",
        want="test_property_18_many_deliveries_one_frozen_application",
        why="关掉「duplicate 目标必须是 direct primary」的唯一断言 ⇒ loser shell 可指向另一个 "
            "duplicate（链/环）或指向未绑定 application 的 shell（stranded），"
            "P18-duplicate-chain 与 P18-duplicate-target-unbound 同时不再被拒。"
            "该断言在迁移里刻意合并成一条：行级 CHECK 已强制「凡 duplicate 必 application 空」，"
            "拆成两条会让其中一条永远被另一条遮蔽而成为不可达分支（实测判 GREEN）",
    ),

    # ── 回填与回滚 ─────────────────────────────────────────────────────
    Mutation(
        id="M42", side="be", path=MIG, kind="replace",
        anchor="        content_version_created = false AND representation_created = false),",
        new="        true),",
        want="test_property_4_business_revision_orthogonal_to_representation",
        why="回填台账可声称创建了 content version/representation ⇒ 回填能伪造历史业务版本"
            "（P4-backfill-ledger-claims-entities 不再被拒）",
    ),
]

if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="Task 9 V151 schema 约束守卫变异检验",
            backend_args=[
                "backend/tests/workpaper_sync/test_v151_schema_contract.py",
                "-q", "--tb=no", "-rf",
            ],
            baseline_backend_passed=19,
        )
    )
