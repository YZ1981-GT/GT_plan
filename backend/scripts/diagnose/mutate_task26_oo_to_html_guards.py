# -*- coding: utf-8 -*-
"""Task 26 变异检验：substrate 来源、最终授权 fence、双基线裁决与 rematerialize 顺序。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 2 Task 26
Requirements: 2.9, 4.2, 4.3, 4.5, 4.6, 4.11, 4.12, 5.8, 6.8, 6.9, 6.11,
8.9, 8.10, 8.11, 8.12, 10.10
Properties: P14 / P19 / P25 / P26 / P27 / P29 / P38 / P43 / P62 / P65

用法（仓库根目录）::

    py -3 backend/scripts/diagnose/mutate_task26_oo_to_html_guards.py --list
    py -3 backend/scripts/diagnose/mutate_task26_oo_to_html_guards.py --check-anchors
    py -3 backend/scripts/diagnose/mutate_task26_oo_to_html_guards.py --run all \\
        --report-path .kiro/specs/.../evidence/task26-oo-to-html/mutation_report.json

═══ 为什么用 `_mutation_kit.span` 而不是 `_mutation_kit.cli` ═══

两条理由，都是实测出来的：

1. **并发安全**。`cli.run_cli` 用 `stale_backups(repo)` 全仓扫 `*.mutbak`，任何一条残留
   就 `[ABORT] 先 --restore`。本任务执行期间**另一个会话正在对
   `workpaper_sync/materialize_coordinator.py` 跑变异**（Task 25 的交付物，实测 mtime
   逐秒更新、`.mutbak` 与源文件同时存在）。跑 `--restore` 会当场把它的在途变异冲掉。
   `span.run_cli` 不落 `.mutbak`：它在内存里持有变异前字节，退出时按 **sha256** 逐文件
   核验还原，因此与并发会话互不干扰。
2. **锚点表达力**。本任务有多条判据的**本体就是相邻两行的组合**（`fence.before_publish`
   与 `publish_representation` 的先后、`assert_expected_revision` 与
   `bump_content_revision` 之间的那一段）。单行锚点在这些位置全都多处命中，只能靠
   绝对行号或 `scope+offset` 消歧 —— 前者一改文件就失效，后者在本文件实测指错了行。
   跨行锚点直接把「组合」写成锚点，一次命中。

═══ 六类落点 ═══

1. **substrate 来源与准入**（`assert_coordinator_substrate_admissible` 的六条判据 +
   `open_substrate` 的次序）—— 每条一个异常类型，逐条短路。
2. **最终授权 fence**（`assert_final_authorization` 的十条）—— 逐条短路；`compared`
   序列也是判据，因此「把某条挪走」同样打红。
3. **双基线裁决**（`settlement_digest_pair` 与 `_settle_baseline`）—— 翻转裁决口径、
   删掉 refresh 分支的 supersede、把 client-confirmed 推进结果写死。
4. **顺序**（`ApplyJournal` 的前置断言 + Task 15 里三个 hook 的挂点）—— 把
   `fence.before_publish` 挪到 `publish_representation` **之后**是最贵的一类缺陷：
   它让 fence 名存实亡，而所有终态断言照常通过。
5. **incoming 不晋升 + result digest 不被偷换**。
6. **回归类** —— 本任务开发过程中**实际修掉**的缺陷重新注入：
   * R01 `json_safe` 缺失 ⇒ 金额字段冲突算 `conflict_set_digest` 时 `TypeError`
     （真库实测抓到；Task 14 的离线守卫只用文本值，全绿）；
   * R02 `_walk_application` 退回直写整条 pipeline ⇒ retry 撞 `error → validating`
     非法边（P38 在真库上根本不成立）；
   * R03 coordinator 的 substrate 准入排在 `assert_incoming_durable` **之后** ⇒
     本层 quarantine 分支 provably-dead；
   * R04 `_observed_contributor_digest` 退回「读冻结值跟自己比」的重言式；
   * R05 `assert_no_command_service_reference` 退回子串匹配 ⇒ 判据恒红。

═══ 刻意避开的无效变异形态 ═══

* 改注释/docstring —— 不在判据作用域内（唯一例外是两条 `control` 项，它们**预期
  GREEN**，用来证明判定不是「只要改了文件就红」）；
* 锚定 `try:` 行 —— 会把整个异常块的语义一起改掉，判定不可归因；
* 短路那些在正确实现下**恒不触发**的内嵌断言 —— 单独短路必判 GREEN。这就是为什么
  四条轨迹断言都被抽成 `ApplyJournal` 的公开方法并用合成轨迹喂。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts
from _mutation_kit.span import SpanMutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

OH = "backend/app/services/workpaper_sync/oo_to_html.py"
CM = "backend/app/services/workpaper_sync/content_mutation.py"
CF = "backend/app/services/workpaper_sync/conflicts.py"

ME = "backend/app/services/workpaper_sync/merge.py"
AR = "backend/app/services/workpaper_sync/artifacts.py"

OFF = "test_task26_oo_to_html"
PG = "test_task26_oo_to_html_pg"
#: 共享登记表 `merge.RETIRED_DEFERRALS` 的第二个消费方守卫（本任务改为归因型判据）。
T15_FILE = "test_task15_content_mutation"


def _off(node: str) -> str:
    return f"{OFF}.py::{node}"


def _pg(node: str) -> str:
    return f"{PG}.py::{node}"


def T15(node: str) -> str:
    return f"{T15_FILE}.py::{node}"


MUTATIONS: list[SpanMutation] = [
    # ═══════════════════════════════════════════════════════════════════
    # 一、substrate 来源与准入（AC 4.3 / 8.10）
    # ═══════════════════════════════════════════════════════════════════
    SpanMutation(
        id="M01", path=OH,
        anchor="    if o is not LEGAL_SUBSTRATE_ORIGIN:",
        new="    if False:",
        want=_off("TestSubstrateAdmission::test_every_forbidden_origin_is_rejected[room_pointer]"),
        why="不再校验 substrate 来源 ⇒ callback 到达时的 room pointer / registry alias / "
            "upgrade candidate / operation path 都能当 substrate（AC 4.3 明令禁止）。"
            "四种形态各自参数化，删掉判据时四条同时红",
        wants=(
            _off("TestSubstrateAdmission::test_every_forbidden_origin_is_rejected[registry_alias]"),
            _off("TestSubstrateAdmission::test_every_forbidden_origin_is_rejected[upgrade_candidate]"),
            _off("TestSubstrateAdmission::test_every_forbidden_origin_is_rejected[operation_path]"),
        ),
    ),
    SpanMutation(
        id="M02", path=OH,
        anchor="    if resolved_artifact_id != declared_incoming_artifact_id:",
        new="    if False:",
        want=_off("TestSubstrateAdmission::test_legal_origin_but_different_artifact_id_is_rejected"),
        why="只查「声明的来源」不查「事实上取到的是不是那一个」⇒ 从 room pointer 查到一个 "
            "artifact 再把 origin 写成 application_incoming_fk 就能过关。"
            "与 M01 分开：声明是意图，id 相等才是事实",
    ),
    SpanMutation(
        id="M03", path=OH,
        anchor="    if state is ArtifactState.quarantined:\n        raise SubstrateQuarantinedError(",
        new="    if False:\n        raise SubstrateQuarantinedError(",
        want=_off("TestSubstrateAdmission::test_quarantined_is_rejected_with_coordinator_specific_type"),
        why="coordinator 入口不再拒绝 quarantined ⇒ 三层拒绝少一层。真库侧同时红："
            "PG 守卫断言 `open_substrate` 报的是 coordinator 自己的 error_code",
        wants=(
            _pg("TestQuarantinedThreeLayerRefusal::test_coordinator_layer_is_not_shadowed_by_the_db_layer"),
        ),
    ),
    SpanMutation(
        id="M04", path=OH,
        anchor="    if kind is not ArtifactKind.incoming:\n        raise SubstrateNotIncomingError(",
        new="    if False:\n        raise SubstrateNotIncomingError(",
        want=_off("TestSubstrateAdmission::test_non_incoming_kind_is_rejected"),
        why="不再要求 substrate 是 incoming ⇒ published representation 也能被当 OO→HTML 的"
            "只读基底，于是「客户端刚回写的字节」与「服务器现状」混成一份",
    ),
    SpanMutation(
        id="M05", path=OH,
        anchor="    if state is not ArtifactState.durable or durable_at is None:",
        new="    if state is not ArtifactState.durable:",
        want=_off("TestSubstrateAdmission::test_durable_state_without_durable_at_is_rejected"),
        why="只看 state 不看 `durable_at` ⇒ 半写入态（state 已改而 durable fact 未落）也能"
            "进 engine。AC 5.4 明确 ownership 只以 immutable `durable_at` 判定",
    ),
    SpanMutation(
        id="M06", path=OH,
        anchor="    if published_at is not None:",
        new="    if False:",
        want=_off("TestSubstrateAdmission::test_incoming_with_published_at_is_rejected"),
        why="不再拒绝带 `published_at` 的 incoming ⇒ 「有人试过晋升它」这条痕迹被忽略"
            "（Property 65：incoming 永不 published/current/resolver-visible）",
    ),
    SpanMutation(
        id="M07", path=OH,
        anchor='    {"download_only", "expire", "retention"}',
        new='    {"download_only", "expire", "retention", "release"}',
        want=_off("TestQuarantineWhitelist::test_whitelist_is_exactly_the_three_allowed_actions"),
        why="白名单被悄悄加一项 `release` ⇒ Requirement 5.6「永不 release、永不转 durable」"
            "被放开。白名单必须与需求原文三项逐字锁死",
        wants=(_off("TestQuarantineWhitelist::test_everything_else_is_refused[release]"),),
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 二、projection-based result 立即要求 approved contract child（AC 8.12）
    # ═══════════════════════════════════════════════════════════════════
    SpanMutation(
        id="M08", path=OH,
        anchor="    if not slot.is_definition:",
        new="    if False:",
        want=_off("TestApprovedContractChild::test_typed_null_marker_contract_slot_fails_immediately"),
        why="typed null marker 冒充 per-entry contract 时不再失败 ⇒ projection-based result "
            "会在没有 approved contract 的情况下发布（AC 8.12 末句）",
    ),
    SpanMutation(
        id="M09", path=OH,
        anchor="    if bundle.authority_model is not AuthorityModel.projection_contract:\n        return",
        new="    if bundle.authority_model is AuthorityModel.projection_contract:\n        return",
        want=_off("TestApprovedContractChild::test_typed_null_marker_contract_slot_fails_immediately"),
        why="把适用范围反过来 ⇒ custom/opaque 入口（contract slot 本就该是 typed null "
            "marker）恒失败，而 projection-based 的真正判据被跳过。两侧都必须钉住，否则"
            "「对所有 authority model 都要求 approved contract」会反过来违反 "
            "Requirement 6.19",
        wants=(
            _off("TestApprovedContractChild::test_custom_authority_model_is_out_of_scope_and_passes"),
        ),
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 三、最终授权 fence 的十条（AC 10.10 / Property 43）
    # ═══════════════════════════════════════════════════════════════════
    SpanMutation(
        id="M10", path=OH,
        anchor="    if not observed.project_visible:",
        new="    if False:",
        want=_off("TestFinalAuthorizationFence::test_each_branch_rejects_independently[project_revoked]"),
        why="打开后撤销 project 可见性仍放行 ⇒ Property 43 的第一条直接失效。"
            "真库两个 fence 场景一并红",
        wants=(
            _pg("TestFinalAuthorizationFence::test_each_revocation_shape_blocks_the_commit[revoked_before_publish]"),
            _pg("TestFinalAuthorizationFence::test_each_revocation_shape_blocks_the_commit[revoked_before_write]"),
        ),
    ),
    SpanMutation(
        id="M11", path=OH,
        anchor="    if observed.workflow_locked:",
        new="    if False:",
        want=_off("TestFinalAuthorizationFence::test_each_branch_rejects_independently[workflow_locked]"),
        why="复核锁定/归档后仍可提交内容。与 M10 分开：合成一条 `all([...])` 时删掉任一条"
            "都会被其余遮蔽",
    ),
    SpanMutation(
        id="M12", path=OH,
        anchor="    if int(observed.room_generation) != int(frozen.generation):",
        new="    if False:",
        want=_off("TestFinalAuthorizationFence::test_each_branch_rejects_independently[generation_superseded]"),
        why="generation 已 supersede 的旧 application 仍可提交 ⇒ 撤销 writer 后旋转 "
            "generation 这条保护形同虚设（AC 2.8 / 4.7）",
    ),
    SpanMutation(
        id="M13", path=OH,
        anchor="    if int(observed.room_write_fence_epoch) != int(frozen.frozen_write_fence_epoch):",
        new="    if False:",
        want=_off("TestFinalAuthorizationFence::test_each_branch_rejects_independently[write_fence_advanced]"),
        why="write fence 提升后旧会话仍可提交 ⇒ 「期间有 participant 被撤销」的内容会被"
            "合进去（AC 10.10）",
    ),
    SpanMutation(
        id="M14", path=OH,
        anchor="    if frozen.frozen_initiator_participant_id is None:",
        new="    if False:",
        want=_off("TestFinalAuthorizationFence::test_frozen_side_null_initiator_has_its_own_error_code"),
        why="frozen 侧 null initiator 放行 ⇒ system/route identity 冒充用户授权（AC 10.10 "
            "明令禁止）。首轮实测判 GREEN：它与 observed 侧共用 `InitiatorMissingError`，"
            "删掉后被后者遮蔽 ⇒ 已拆成 `FrozenInitiatorMissingError` + 独立 error_code",
    ),
    SpanMutation(
        id="M15", path=OH,
        anchor="    if observed.initiator_participant_id != frozen.frozen_initiator_participant_id:",
        new="    if False:",
        want=_off("TestFinalAuthorizationFence::test_each_branch_rejects_independently[initiator_replaced]"),
        why="换了个人当 initiator 也放行 ⇒ 冻结的发起人身份可被替换。与 M14 分开："
            "「没有人」与「换了人」是两条独立判据",
    ),
    SpanMutation(
        id="M16", path=OH,
        anchor="    if int(observed.initiator_permission_epoch) != int(\n        frozen.frozen_initiator_permission_epoch\n    ):",
        new="    if False:",
        want=_off("TestFinalAuthorizationFence::test_each_branch_rejects_independently[permission_epoch_changed]"),
        why="initiator 的权限 epoch 变了仍放行 ⇒ 降权用户的编辑照样落库",
    ),
    SpanMutation(
        id="M17", path=OH,
        anchor="    if initiator_state not in _INITIATOR_LIVE_STATES:",
        new="    if False:",
        want=_off("TestFinalAuthorizationFence::test_each_branch_rejects_independently[initiator_revoked]"),
        why="被撤销/过期/离开的 participant 仍可为本次 application 背书。真库 S12 一并红",
        wants=(
            _pg("TestFinalAuthorizationFence::test_each_revocation_shape_blocks_the_commit[initiator_revoked]"),
        ),
    ),
    SpanMutation(
        id="M18", path=OH,
        anchor="    {ParticipantState.active, ParticipantState.closing}",
        new="    {ParticipantState.active}",
        want=_off("TestFinalAuthorizationFence::test_closing_initiator_is_still_live"),
        why="把 `closing` 从合法 initiator 状态里剔除 ⇒ clean close 的 predecessor forcesave "
            "恒失败（AC 4.10 要求 intent 创建时把 participant 原子转 `closing`，此后它的 "
            "forcesave 才回调）。这是「加严也是缺陷」的一类",
    ),
    SpanMutation(
        id="M19", path=OH,
        anchor="    if observed.contributor_snapshot_digest.strip() != (",
        new="    if False and observed.contributor_snapshot_digest.strip() != (",
        want=_off("TestFinalAuthorizationFence::test_each_branch_rejects_independently[contributor_drift]"),
        why="contributor 集合在期间变化（有人被撤销）仍放行 ⇒ 归属无法判定却照样提交"
            "（AC 10.10 点名 contributor snapshot）",
    ),
    SpanMutation(
        id="M20", path=OH,
        anchor="        observed.current_definition_bundle_id != frozen.definition_bundle_id",
        new="        False",
        want=_off("TestFinalAuthorizationFence::test_each_branch_rejects_independently[bundle_replaced_id]"),
        why="current approved bundle 被换成另一个 approved bundle 仍放行 ⇒ 历史 application "
            "会按新 bundle 发布（Property 43 点名这一种）。真库 S11 一并红",
        wants=(
            _pg("TestFinalAuthorizationFence::test_each_revocation_shape_blocks_the_commit[bundle_replaced]"),
        ),
    ),
    SpanMutation(
        id="M21", path=OH,
        anchor='    compared.append("project_visible")',
        new='    compared.append("__reordered__")',
        want=_off("TestFinalAuthorizationFence::test_matching_facts_pass_and_report_every_compared_item"),
        why="`compared` 序列本身是判据（AC 10.10 逐项列举）。只断言「抛了 FinalFenceError」"
            "时，删掉其中九条守卫照常绿 —— 剩下那条会顶上来。本条证明项名与顺序真的被钉住",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 四、双基线裁决口径唯一（Property 62 / AC 2.9 / 4.11）
    # ═══════════════════════════════════════════════════════════════════
    SpanMutation(
        id="M22", path=OH,
        anchor="    if merge.requires_client_refresh(incoming):",
        new="    if merged_digest != incoming_digest:",
        want=_off("TestSettlementDigestPair::test_managed_equal_reports_equality_to_room_service"),
        why="把裁决口径从 Task 14 的 managed 比较换成整份 digest 字节比较 ⇒ Word 底稿的 "
            "`word_only` 字段一变就判 refresh，于是 Task 15 的 `_advance_room`（用 "
            "`requires_client_refresh`）与 Task 21 的 `settle_client_baseline` 给出**两个**"
            "结论，出现「服务端没标 refresh 而 room 标了」的半状态",
        wants=(
            _off("TestSettlementDigestPair::test_translation_preserves_the_verdict_in_both_directions"),
        ),
    ),
    SpanMutation(
        id="M23", path=OH,
        anchor="    return merged_digest, merged_digest",
        new="    return merged_digest, incoming_digest",
        want=_off("TestSettlementDigestPair::test_managed_equal_reports_equality_to_room_service"),
        why="等值裁决时不再如实告知 `settle_client_baseline`「两侧相同」⇒ 受管字段完全等值"
            "的 Word 底稿也会被判 refresh-required，编辑器被无谓地强制重开",
    ),
    SpanMutation(
        id="M24", path=OH,
        anchor="        if settlement.refresh_required:",
        new="        if False:",
        want=_pg("TestRefreshRequired::test_room_is_refresh_required_and_superseded"),
        why="merged ≠ incoming 时不再 supersede generation ⇒ AC 4.11「supersede/reopen 后再"
            "接受下一次 request」失效，live OO 会拿旧 incoming 把服务器合并值回退掉",
        wants=(_pg("TestRefreshRequired::test_next_forcesave_is_rejected"),),
    ),
    SpanMutation(
        id="M25", path=OH,
        anchor="        state.client_baseline_advanced = settlement.client_baseline_advanced",
        new="        state.client_baseline_advanced = True",
        want=_pg("TestRefreshRequired::test_server_last_applied_advances_but_client_confirmed_does_not"),
        why="把 client-confirmed 推进结果写死为 True ⇒ 服务器结果被冒充成「编辑器已确认"
            "基线」（Property 62 的核心禁令）",
    ),
    SpanMutation(
        id="M26", path=CM,
        anchor="                        requires_client_refresh=requires_refresh,",
        new="                        requires_client_refresh=False,",
        want=_pg("TestRefreshRequired::test_application_and_operation_are_refresh_required"),
        why="同事务落 application 结果时把 `requires_client_refresh` 写死 False ⇒ "
            "merged ≠ incoming 的 application 会被记成 `applied`，编辑器再也收不到"
            "「需重开确认新基线」（AC 4.12 要求四态分别可见）",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 五、顺序：三个 fence 挂点与轨迹断言
    # ═══════════════════════════════════════════════════════════════════
    SpanMutation(
        id="M27", path=CM,
        anchor=(
            "        if fence is not None:\n"
            "            await fence.before_publish(\n"
            "                artifact_sha256=materialized.artifact_sha256,\n"
            "                structure_hash=materialized.structure_hash,\n"
            "                identity_inventory_sha256=materialized.identity_inventory_sha256,\n"
            "                extracted_key_count=len(extracted.values),\n"
            "            )\n"
            "\n"
            "        staged_rep = self._artifacts.stage_stream("
        ),
        new="        staged_rep = self._artifacts.stage_stream(",
        want=_off("TestCommitFenceHookWiring::test_before_publish_is_called_between_unmanaged_check_and_publish"),
        why="删掉 publish 前的 fence 挂点 ⇒ fence 名存实亡（artifact 直接进入不可变 "
            "`.versions` 命名空间，回滚只能留 orphan），而所有终态断言照常通过。"
            "这是本任务最贵的一类缺陷：撤权后的内容会被发布出去",
        wants=(
            _pg("TestFinalAuthorizationFence::test_publish_fence_fires_before_any_file_is_published"),
            _pg("TestAppliedHappyPath::test_both_fences_ran_and_in_order"),
        ),
    ),
    SpanMutation(
        id="M28", path=CM,
        anchor=(
            "            if fence is not None:\n"
            "                await fence.before_write(current_revision=current)\n"
            "            new_revision = await self._repo.bump_content_revision(plan.wp_id, current)"
        ),
        new="            new_revision = await self._repo.bump_content_revision(plan.wp_id, current)",
        want=_off("TestCommitFenceHookWiring::test_before_write_is_called_after_lock_and_before_any_write"),
        why="删掉写库前的 fence ⇒ OO→HTML 只剩一道 fence。它与第一道不是冗余：中间隔着 "
            "`publish_representation`（可能几十 MB 的文件 IO），撤权完全可能落在那段时间里。"
            "真库判据：探针必须被调两次",
        wants=(
            _pg("TestAppliedHappyPath::test_probe_actually_executed_twice"),
            _pg("TestFinalAuthorizationFence::test_write_fence_fires_after_publish_and_before_revision_bump"),
        ),
    ),
    SpanMutation(
        id="M29", path=CM,
        anchor=(
            "            # ⑥b Task 26：application result + operation timeline 与上面各行**同事务**\n"
            "            if fence is not None:\n"
            "                await fence.after_pointers("
        ),
        new=(
            "            # ⑥b Task 26：application result + operation timeline 与上面各行**同事务**\n"
            "            if False:\n"
            "                await fence.after_pointers("
        ),
        want=_pg("TestAppliedHappyPath::test_application_and_operation_reached_applied_terminal"),
        why="application result 与 operation timeline 不再与 pointer/outbox 同事务落库 ⇒ "
            "出现「pointer 已发布而 application 还停在 rematerializing」的半成功态"
            "（AC 8.12 / 10.11 要求同一事务）",
        wants=(_pg("TestAppliedHappyPath::test_p65_merged_projection_digest_equals_published_projection_artifact"),),
    ),
    SpanMutation(
        id="M30", path=OH,
        anchor="        state.journal.assert_publish_precondition()",
        new="        pass",
        want=_off("TestStructuralPredicates::test_fence_callbacks_assert_trace_order_as_their_first_statement"),
        why="publish 前不再断言「三方 extract 与 merge 真的发生过」⇒ 「只 extract 了 "
            "incoming 就直接发布」这条缺陷（base/current 没读 ⇒ 三方 merge 退化成整表覆盖）"
            "不再被拦。首轮实测判 GREEN：该断言在 happy path 上恒不触发，运行期观察不到 "
            "⇒ 已补形态判据 `assert_fence_callbacks_assert_order_first()`",
    ),
    SpanMutation(
        id="M31", path=OH,
        anchor="        if not self.has(ApplyStage.fence_verified_before_publish):",
        new="        if False:",
        want=_off("TestApplyJournal::test_write_fence_must_come_after_publish_fence"),
        why="不再要求「写库前的 fence 晚于 publish 前的 fence」⇒ 两道 fence 可以对调，"
            "于是「先写库再验授权」在轨迹上合法",
    ),
    SpanMutation(
        id="M32", path=OH,
        anchor="            if self.has(later) and self.index_of(later) > idx:",
        new="            if False:",
        want=_off("TestApplyJournal::test_conflict_forbids_any_later_publish_or_commit"),
        why="冲突已登记却仍走到 publish/commit 时不再打红 ⇒ AC 8.11「未裁决冲突不得提交"
            "内容、指针一律不动」失去轨迹侧保护",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 六、incoming 不晋升 + result digest 不被偷换
    # ═══════════════════════════════════════════════════════════════════
    SpanMutation(
        id="M33", path=OH,
        anchor='    if observed_published_at is not None:\n        drift.append(f"published_at 被写成 {observed_published_at!r}")',
        new='    if False:\n        drift.append(f"published_at 被写成 {observed_published_at!r}")',
        want=_off("TestIncomingRowUnchanged::test_every_drift_shape_is_detected[published_at_set]"),
        why="commit 后不再核对 incoming 的 `published_at` 仍为空 ⇒ 「incoming 被复制标记为 "
            "published/current」这条禁令失去判据（Property 65）。首轮实测判 GREEN："
            "这条在 happy path 上恒不触发 ⇒ 已把 `_assert_incoming_untouched` 的五条判据"
            "抽成模块级纯函数 `assert_incoming_row_unchanged` 并逐条参数化喂",
    ),
    SpanMutation(
        id="M33B", path=OH,
        anchor='    if observed_state != ArtifactState.durable.value:',
        new="    if False:",
        want=_off("TestIncomingRowUnchanged::test_every_drift_shape_is_detected[promoted_state]"),
        why="incoming 的 state 被改成 published 也不再打红 ⇒ 「原地晋升」这条最直接的形态"
            "失去判据。与 M33 分开：五条 drift 判据合成一条时删掉任一条都会被其余遮蔽",
    ),
    SpanMutation(
        id="M34", path=OH,
        anchor="    if published_sha256.strip() != approved_sha256.strip():",
        new="    if False:",
        want=_off("TestPublishedDigestWasApproved::test_swapped_digest_is_detected"),
        why="不再比对「落库的 artifact digest」与「fence 放行的那一份」⇒ publish 与 fence "
            "之间被偷换也检不出来（AC 8.10 的 artifact/bundle digest 重验）。首轮实测判 "
            "GREEN（happy path 恒相等）⇒ 已抽成纯函数 "
            "`assert_published_digest_was_approved`",
    ),
    SpanMutation(
        id="M34B", path=OH,
        anchor="    if approved_sha256 is None:",
        new="    if False:",
        want=_off("TestPublishedDigestWasApproved::test_missing_approval_is_an_order_violation_not_a_digest_mismatch"),
        why="「fence 根本没跑过」与「digest 被偷换」共用一条判据 ⇒ 前者会退化成 "
            "`None.strip()` 的 AttributeError（第三种、不可诊断的失败）。两条必须分型",
    ),
    SpanMutation(
        id="M35", path=OH,
        anchor="    if advanced_application_id != expected_application_id:",
        new="    if False:",
        want=_off("TestCanonicalFencePointsAt::test_desynchronized_fence_is_detected[fence_points_elsewhere]"),
        why="不再核对 room canonical fence 指向本次 application ⇒ 出现「server 已推进、"
            "canonical fence 还指着上一个 application」的中间态，而 Task 27 的 resolve 先比 "
            "canonical application identity，读到它会把合法 resolve 判成 stale（AC 10.11）。"
            "首轮实测判 GREEN（happy path 恒相等）⇒ 已抽成纯函数",
        wants=(
            _off("TestCanonicalFencePointsAt::test_desynchronized_fence_is_detected[fence_never_advanced]"),
        ),
    ),
    SpanMutation(
        id="M36", path=OH,
        anchor="            app, (ApplicationState.applying,), actor_id=state.actor_id",
        new="            app, (), actor_id=state.actor_id",
        want=_pg("TestAppliedHappyPath::test_application_and_operation_reached_applied_terminal"),
        why="application 不再经 `applying` ⇒ `rematerializing → applied` 是非法边，整条 "
            "applied 路径在真库上崩掉。用它证明 state 机不是装饰",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 七、无 fail-open
    # ═══════════════════════════════════════════════════════════════════
    SpanMutation(
        id="M37", path=OH,
        anchor=(
            "        except Exception as exc:  # noqa: BLE001 - 立即重抛为可诊断类型，不降级\n"
            "            raise AuthorizationProbeFailedError("
        ),
        new=(
            "        except Exception as exc:  # noqa: BLE001 - 立即重抛为可诊断类型，不降级\n"
            "            external = {\"project_visible\": True, \"workflow_locked\": False}\n"
            "            _ = exc\n"
            "        if False:\n"
            "            raise AuthorizationProbeFailedError("
        ),
        want=_pg("TestPreBindAndProbe::test_broken_probe_fails_visibly_and_commits_nothing"),
        why="探针异常被吞成「无此限制」⇒ 接线错误（函数名写错、列名写错、单参调用 async "
            "签名）表现成授权通过，而 Volar/vitest/get_diagnostics/HEAD-swap 四层全绿"
            "（Requirement 5.12 点名禁止这种降级）。离线的 AST 判据同时红",
        wants=(_off("TestNoFailOpen::test_coordinator_source_has_no_bare_warning_swallow"),),
    ),
    SpanMutation(
        id="M38", path=OH,
        anchor="            if key not in external:",
        new="            if False:",
        want=_pg("TestPreBindAndProbe::test_incomplete_probe_response_is_refused_not_treated_as_allowed"),
        why="探针返回值缺字段时不再拒绝 ⇒ 「缺字段视为放行」这条经典 fail-open 复活。"
            "首轮实测判 GREEN：当时唯一的探针场景是「抛异常」，走不到这条 ⇒ 已补 S14 "
            "`probe_incomplete`（探针正常返回但少 `project_visible` 键）",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 八、对照项（**预期 GREEN**）—— 证明判定不是「只要改了文件就红」
    # ═══════════════════════════════════════════════════════════════════
    SpanMutation(
        id="C01", path=OH,
        anchor='        f"application 固定的 incoming artifact {artifact_id} 行不存在 —— "',
        new='        f"placeholder {artifact_id}"',
        want="*",
        why="对照项：只改诊断文案、不动任何判据 ⇒ 预期 GREEN。用它证明本脚本不会把"
            "「改了字符串」误判成 RED（否则全 RED 的报告说明不了任何事）",
        expect_green=True,
    ),
    SpanMutation(
        id="C02", path=OH,
        anchor="    compared: list[str] = []",
        new="    compared: list[str] = list()",
        want="*",
        why="对照项：`list()` 与 `[]` 等价 ⇒ 预期 GREEN。第二条对照落在 fence 函数体内部，"
            "证明「在被测函数里改一行也不会自动变红」",
        expect_green=True,
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 九、回归类：本任务实际修掉的缺陷重新注入
    # ═══════════════════════════════════════════════════════════════════
    SpanMutation(
        id="R01", path=CF,
        anchor='        return {"present": True, "value": json_safe(self.value)}',
        new='        return {"present": True, "value": self.value}',
        want=_pg("TestConflictLeavesEverythingUntouched::test_p27_only_the_touched_row_conflicts"),
        why="R01 回归：`ValueEnvelope.to_jsonb()` 不再过 `json_safe` ⇒ 任何 amount/date 字段"
            "的同字段异值冲突在算 `ConflictSet.digest`（AC 8.5 的 `conflict_set_digest`）时"
            "直接 `TypeError: Object of type Decimal is not JSON serializable`。本任务在"
            "真库上实测抓到 —— D2 应收账款的行金额冲突整条路径崩溃，而 Task 14 的离线守卫"
            "只用文本值，全绿",
    ),
    SpanMutation(
        id="R02", path=OH,
        anchor="            if target not in APPLICATION_EDGES.get(current, frozenset()):",
        new="            if False:",
        want=_pg("TestDurablePostFailureAndRetry::test_p38_retry_succeeds_and_produces_exactly_one_revision"),
        why="R02 回归：pipeline 不再「从当前状态可达的第一站进入」而是直写整条 ⇒ retry 时撞 "
            "`error → validating` 非法边（`APPLICATION_EDGES` 没有这条），于是 Property 38"
            "「durable incoming 可无 forcesave 重试」在真库上根本不成立。首次执行照常绿，"
            "只有 retry 场景暴露",
        wants=(
            _pg("TestDurablePostFailureAndRetry::test_p38_retry_appends_to_the_same_timeline"),
        ),
    ),
    SpanMutation(
        id="R03", path=OH,
        anchor=(
            "        assert_coordinator_substrate_admissible(\n"
            "            origin=LEGAL_SUBSTRATE_ORIGIN,\n"
            "            artifact_kind=row.kind,\n"
            "            artifact_state=row.state,\n"
            "            durable_at=row.durable_at,\n"
            "            published_at=row.published_at,\n"
            "            declared_incoming_artifact_id=artifact_id,\n"
            "            resolved_artifact_id=row.id,\n"
            "        )\n"
            "        await self._repo.assert_incoming_durable(artifact_id)"
        ),
        new=(
            "        await self._repo.assert_incoming_durable(artifact_id)\n"
            "        assert_coordinator_substrate_admissible(\n"
            "            origin=LEGAL_SUBSTRATE_ORIGIN,\n"
            "            artifact_kind=row.kind,\n"
            "            artifact_state=row.state,\n"
            "            durable_at=row.durable_at,\n"
            "            published_at=row.published_at,\n"
            "            declared_incoming_artifact_id=artifact_id,\n"
            "            resolved_artifact_id=row.id,\n"
            "        )"
        ),
        want=_pg("TestQuarantinedThreeLayerRefusal::test_coordinator_layer_is_not_shadowed_by_the_db_layer"),
        why="R03 回归：把 coordinator 的 substrate 准入排到 `assert_incoming_durable` **之后**"
            " ⇒ DB 层先抛 `QuarantinedIncomingError`，本层的 quarantine 分支变成 "
            "provably-dead，「删掉 coordinator 这一层」在变异检验里判 GREEN。首轮实测正是如此",
    ),
    SpanMutation(
        id="R04", path=OH,
        anchor="        return compute_contributor_snapshot_digest(",
        new="        return frozen.contributor_snapshot_digest\n        return compute_contributor_snapshot_digest(",
        want=_pg("TestContributorSnapshotIsRecomputed::test_contributor_revocation_blocks_the_commit"),
        why="R04 回归：`_observed_contributor_digest` 退回「读冻结值再跟自己比」的重言式 ⇒ "
            "无论谁被撤销两边永远相等，contributor 重验 provably-dead。"
            "首轮实测判 GREEN：当时的判别输入是「撤销 initiator」，那会先在 "
            "`initiator_state` 那条失败、走不到 contributor 比对 ⇒ 已补 S15 "
            "`contributor_revoked`（initiator 保持 active，只撤销另一位 contributor，"
            "于是十条 fence 里只有 contributor digest 那条不等值）",
    ),
    SpanMutation(
        id="M39", path="backend/app/services/workpaper_sync/merge.py",
        anchor='        "expected_consumer_module": "app/services/workpaper_sync/oo_to_html.py",',
        new='        "expected_consumer_module": "app/services/workpaper_sync/resolution.py",',
        want="test_task14_merge_conflicts.py::TestTask14ScopeBoundary::test_merge_domain_consumers_match_the_retirement_registry_exactly",
        why="退役登记声明的 merge 消费方与事实脱钩（登记成 `resolution.py`，实际是 "
            "`oo_to_html.py`）⇒ 「登记表 ↔ 事实双向等值」这条判据必须打红。"
            "本条同时覆盖三种偏离里的两种：出现未登记的消费方 + 登记了却不消费。"
            "Task 26 把这条判据从「恰一个消费方」升级为双向锁死，因此必须有一条变异证明"
            "升级后的版本仍可证伪（否则升级就等于放宽）",
    ),
    SpanMutation(
        id="M40", path=ME,
        # 🔴 锚点必须跨行：Task 27 往 `RETIRED_DEFERRALS` 追加了自己那条登记后，
        #    `"commits_through": ".../content_mutation.py",` 在本文件里出现**两次**
        #    ⇒ 单行锚点 ANCHOR-MISS（命中 2 处）。用本条登记独有的前一行注释消歧，
        #    钉住的仍然是 Task 26 那条（编排层）而不是 Task 27 那条。
        anchor="        # 必须经由下面这个模块落库。守卫按这一列反查该模块真的被 import。\n"
               '        "commits_through": "app/services/workpaper_sync/content_mutation.py",',
        new="        # 必须经由下面这个模块落库。守卫按这一列反查该模块真的被 import。\n"
            '        "commits_through": "app/services/workpaper_sync/retention.py",',
        want="test_task14_merge_conflicts.py::TestTask14ScopeBoundary::test_merge_domain_consumers_match_the_retirement_registry_exactly",
        why="编排层声明「经由 retention.py 落库」⇒ 唯一 commit 边界的反查失效。"
            "`commits_through` 正是「coordinator 允许跑 merge 但不得自己 commit」这条"
            "不变量的载体（Property 61）；它若指向任意模块，边界就只剩注释",
    ),
    SpanMutation(
        id="R05", path=OH,
        anchor="    hits = sorted(set(_COMMAND_SERVICE_SYMBOLS) & identifiers)",
        new="    hits = sorted({s for s in _COMMAND_SERVICE_SYMBOLS if s in str(identifiers)})",
        want=_off("TestStructuralPredicates::test_command_service_symbol_list_is_matched_as_whole_identifier"),
        why="R05 回归：判据退回子串包含 ⇒ 本模块自己的 `next_forcesave_allowed` 与 "
            "`assert_no_command_service_reference` 都含被禁子串，判据恒红。恒红的守卫和恒绿"
            "一样没用 —— 下一个人会直接把它删掉",
        wants=(_off("TestStructuralPredicates::test_module_never_references_command_service"),),
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 七、按 Property 补齐的定向变异
    # ═══════════════════════════════════════════════════════════════════
    #
    # 收口审计（`--check-anchors` 全 OK、49 条全 RED 之后）用「report 里的 `added` 列表」
    # 反查每条 Property：**P19 / P26 / P29 的测试从未被任何一条变异打红过**。
    # 「测试存在」与「测试有牙」是两件事 —— 前 49 条打红的是同一守卫的**别的**消费方，
    # 于是这三条 Property 的断言到底能不能证伪，始终没有证据。本任务要求「验证
    # Property 19/26/29」，因此逐条补一条最小落点，且刻意选**互不遮蔽**的分支。
    SpanMutation(
        id="N01", path=OH,
        anchor="            else ApplicationState.error\n        )",
        new="            else ApplicationState.authorization_stale\n        )",
        want=_pg("TestDurablePostFailureAndRetry::test_p19_application_and_operation_are_retryable_error"),
        why="P19：durable 后 extract 失败必须落**可重试**的 `error`，而不是 "
            "`authorization_stale`。两者混同的后果很具体 —— `authorization_stale` 只能走 "
            "supersede/recovery，于是「durable incoming 可无 forcesave 重试」（P38）在真库上"
            "直接失效。刻意只改 application 侧、不改 operation 侧：`logical_result_code` 与 "
            "`result` 都取自 `result` 形参、不受本条影响，因此打红的只能是 `app_state` 那条"
            "断言，归因唯一。这也是「两个终态共用一条赋值」这类缺陷的最小复现",
    ),
    SpanMutation(
        id="N02", path="backend/app/services/workpaper_sync/merge.py",
        anchor="        _put(merged_values, locator, c)\n\n    merged = Projection(",
        new="        _put(merged_values, locator, i)\n\n    merged = Projection(",
        want=_off("TestThreeWayMergeSemantics::test_p26_same_field_three_values_conflicts_and_keeps_all_three"),
        why="P26：同字段三值冲突时 `merged` 必须 hold 在 **current**。改成 hold incoming 后 "
            "`conflict_count` 仍为 1、三值仍完整 —— 只有「merged 是什么」这一条会红，"
            "而它恰恰是最危险的那条：未裁决的 merged 若已经是 incoming，"
            "上层任何「无冲突就提交 merged」的分支都会把未裁决冲突当成 incoming 获胜提交"
            "（AC 6.8 明确三方规则不选边）。锚点带 `merged = Projection(` 尾随上下文，"
            "因为 `_put(merged_values, locator, c)` 在 continue 分支里另有多处",
        wants=(
            _pg("TestConflictLeavesEverythingUntouched::test_p27_only_the_touched_row_conflicts"),
            _off("TestThreeWayMergeSemantics::test_p27_delete_vs_update_conflicts_only_that_row"),
        ),
    ),
    SpanMutation(
        id="N03", path=CM,
        anchor='        if missing:\n            raise RoundtripEquivalenceError(\n'
               '                f"staged representation ',
        new='        if False:\n            raise RoundtripEquivalenceError(\n'
            '                f"staged representation ',
        want=_off("TestRoundtripEquivalence::test_dropped_managed_field_is_detected_by_the_platform_predicate"),
        why="P29/AC 6.11：materialize **漏写**一个受管字段必须被平台判据抓到。与 N04 分成两条，"
            "因为两个分支抛的是**同一个** `RoundtripEquivalenceError` —— 合成一条变异时靠前的 "
            "`missing` 分支被短路后，靠后的 `values_equal` 分支会顶上来抛同一类型，"
            "守卫看不出差别而判 GREEN（本 spec 已为「两分支共用 error_code」付过三次代价）。"
            "逐条短路才能证明两个分支各自都不是 provably-dead",
    ),
    SpanMutation(
        id="N04", path=CM,
        anchor="            if not values_equal(mine.value, theirs.value, mine.value_type):",
        new="            if False:",
        want=_off("TestRoundtripEquivalence::test_corrupted_value_is_detected"),
        why="P29/AC 6.11：受管字段反读**值被改**必须抓到（字段集合齐全、值不等值）。"
            "这条与 N03 互不遮蔽：N03 的判别输入少一个字段、本条的判别输入字段集合完整，"
            "因此短路本条时 `missing`/`extra` 两条都不触发，只有本条会红。"
            "同时它钉死「比较口径复用 `merge.values_equal`」—— 换成 `==` 会让 "
            "Decimal('1') 与 Decimal('1.00')、CRLF 与 LF 判不等值",
    ),
    SpanMutation(
        id="N05", path=CM,
        anchor="                kind=ArtifactKind.canonical,\n"
               "                state=ArtifactState.published,",
        new="                kind=ArtifactKind.incoming,\n"
            "                state=ArtifactState.published,",
        want=_pg("TestAppliedHappyPath::test_p65_incoming_is_never_promoted"),
        why="P65/AC 8.10：证明 `test_p65_incoming_is_never_promoted` 里**新补的**四条断言"
            "（result artifact 与 incoming 非同一行 / 不在 `.incoming/` 下 / kind 非 "
            "incoming / state=published）不是重言式。上一版这里写的是 "
            "`assert result_rep_artifact_sha != incoming_sha or True` —— `X or True` 结构上"
            "永真，等于把 Property 65 最贵的那半句「不得复制后标记为 published/current」"
            "整条放空。本变异把 result representation 的 artifact **行**标成 `incoming` kind，"
            "sha256 一字不变，因此只有新断言会红、归因唯一。"
            "🔴 首版锚在 `artifacts.py::_publish` 的 `kind=ArtifactKind.canonical`，实测 GREEN："
            "那里只决定返回的 `PublishedArtifact` 值对象，**DB 行的 kind/state 是 "
            "`content_mutation` 这里另写一遍的**（同一事实两处声明）。"
            "GREEN 当时不是守卫缺陷而是变异无效 —— 记在这里，免得下一个人据此去放宽断言",
    ),
    # ── 共享登记表的第二个消费方：Task 15 的守卫（本任务改动，故纳入本任务变异面）──
    #
    # `merge.RETIRED_DEFERRALS` 是**跨任务共享**的登记表。Task 26 合法追加了自己那条
    # （编排层跑 merge、经 `commits_through` 落库），于是 Task 15 那条写
    # `len(retired) == 1` 的**全局等值**判据被打红。这不是 Task 15 的错、也不该靠删断言
    # 解决：已改为归因型（我的那条唯一 + 其余条目必须声明经唯一 commit 边界落库）。
    # 既然本任务动了那条守卫，就必须由本任务证明它改完仍可证伪。
    SpanMutation(
        id="N06", path=ME,
        # 与 M40 同因跨行消歧（Task 27 追加登记后该行出现两次）；两条共用同一锚点、
        # 不同 `new`，钉住的都是 Task 26 那条编排层登记。
        anchor="        # 必须经由下面这个模块落库。守卫按这一列反查该模块真的被 import。\n"
               '        "commits_through": "app/services/workpaper_sync/content_mutation.py",',
        new="        # 必须经由下面这个模块落库。守卫按这一列反查该模块真的被 import。\n"
            '        "commits_through": None,',
        want=T15("TestTask15ScopeBoundary::test_merge_domain_deferral_is_retired"),
        why="Task 26 这条消费方不再声明「经 content_mutation 落库」⇒ 编排层可以自己 commit，"
            "Property 61 的唯一 commit 边界只剩注释。这正是归因型判据比旧版 "
            "`len(retired) == 1` 强的地方：旧版对「新增一条不经 commit 边界的消费方」"
            "只会报 `2 == 1`，说不出问题在哪；新版直接点出是哪个模块、缺了什么",
        wants=(
            "test_task14_merge_conflicts.py::TestTask14ScopeBoundary"
            "::test_merge_domain_consumers_match_the_retirement_registry_exactly",
        ),
    ),
    SpanMutation(
        id="N07", path=ME,
        anchor='        "expected_consumer_module": "app/services/workpaper_sync/content_mutation.py",',
        new='        "expected_consumer_module": "app/services/workpaper_sync/retention.py",',
        want=T15("TestTask15ScopeBoundary::test_merge_domain_deferral_is_retired"),
        why="Task 15 自己那条登记指错模块 ⇒ 「退役登记指向本任务的模块」这句话失效。"
            "与 N06 分开：N06 打的是**其他**消费方的 `commits_through`，本条打的是"
            "**我自己那条**的归属。两条共用一个断言块时，靠前的失败会遮蔽靠后的，"
            "于是分别短路才能证明两段各自都有牙",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 八、收口审计（2026-08-27 第二轮）抓到的三个真实生产缺陷的回归变异
    # ═══════════════════════════════════════════════════════════════════
    #
    # 前 56 条全 RED 之后按「Task 26 正文的每个承诺是否都有一条判据」反查，抓到三处
    # 缺陷：①「再重验 eligibility」是重言式；②「同一 frozen application 只应用一次」
    # 没有任何判据、状态机反而成了掩护；③ AC 10.10 末句「并 supersede/recovery」缺失。
    # 下面每条变异都把生产代码**精确退回缺陷形态**，因此它们同时是「缺陷曾真实存在」的
    # 证据 —— 修前的行为就写在各条 `why` 里。
    SpanMutation(
        id="D01", path=OH,
        anchor="        assert_application_state_admits_apply(\n"
               "            frozen.state, application_id=application_id, attempt=attempt\n"
               "        )",
        new="        _ = frozen.state",
        want=_pg("TestReapplyIsRefused::test_second_apply_is_refused_with_its_own_error_code"),
        why="缺陷②的精确复现（修前形态：`FrozenApplicationIdentity.state` 被逐列冻结却"
            "**从未被消费**）。修前真库实测（本条变异下 `_pg::TestReapplyIsRefused` 的"
            "实际输出）：对已 `applied` 的 application 再调一次 `apply_durable_incoming` "
            "会**跑完整条 pipeline** —— 三侧 extract + materialize 写出新的 staged result + "
            "未管理区域比对（adapter 调用实测 6 次），直到写库阶段才撞出 "
            "`StateTransitionError:illegal_state_transition`；而 `_record_post_durable_"
            "failure` 自己也要走 `applied → error`（同样非法）⇒ 异常穿透入口，"
            "application/operation timeline 零 event。"
            "🔴 **没有**观测到第二个 business revision：`APPLICATION_EDGES[applied]` 是空集，"
            "状态机在写库前偶然拦住了它，所以 `test_nothing_moved_on_the_second_attempt` "
            "在本条变异下仍是绿的（它不是本缺陷的证人，而是「拒绝本身不得损坏状态」的"
            "互补判据）。这份保护是偶然的 —— 它依赖一个与 AC 4.3 无关的事实，"
            "所以 AC 4.3「同一 frozen application 才能应用一次」必须有自己的判据",
        wants=(
            _pg("TestReapplyIsRefused::test_refusal_happens_before_any_adapter_or_probe_call"),
        ),
    ),
    SpanMutation(
        id="D02", path=OH,
        anchor="    {ApplicationState.applied, ApplicationState.refresh_required}\n"
               ")\n\n"
               "#: 已作废、不可重试 ⇒ :class:`ApplicationTerminalStaleError`。\n"
               "_STALE_TERMINAL_STATES: Final[frozenset[ApplicationState]] = frozenset(\n"
               "    {ApplicationState.superseded, ApplicationState.authorization_stale}\n"
               ")",
        new="    {ApplicationState.applied}\n"
            ")\n\n"
            "#: 已作废、不可重试 ⇒ :class:`ApplicationTerminalStaleError`。\n"
            "_STALE_TERMINAL_STATES: Final[frozenset[ApplicationState]] = frozenset(\n"
            "    {\n"
            "        ApplicationState.superseded,\n"
            "        ApplicationState.authorization_stale,\n"
            "        ApplicationState.refresh_required,\n"
            "    }\n"
            ")",
        want=_off(
            "TestApplyStateAdmission::"
            "test_every_inadmissible_state_is_refused_with_its_own_code[refresh_required]"
        ),
        why="把 `refresh_required` 从「已应用过」误归到「已作废」。刻意保持 partition 成立"
            "（否则 import 期的双向锁死会先抛，全文件变 collection error ⇒ 归因不唯一）。"
            "两类后续动作完全不同：`refresh_required` 的内容**已经落库**，前端要做的是"
            "重开编辑器确认新基线；`superseded/authorization_stale` 的内容根本没落库，"
            "只能走 supersede/recovery。共用一个 error_code 时前端无从分辨",
    ),
    SpanMutation(
        id="D03", path=OH,
        anchor="        if int(observed.close_leader_eligibility_epoch) != int(\n"
               "            frozen.frozen_close_leader_eligibility_epoch\n"
               "        ):",
        new="        if int(observed.close_leader_eligibility_epoch) < 0:",
        want=_pg(
            "TestCloseCaptureEligibilityFence::"
            "test_epoch_advance_after_promotion_blocks_the_commit"
        ),
        why="缺陷①的精确复现（修前形态：`if int(observed.close_leader_eligibility_epoch) "
            "< 0`）。`room.close_leader_eligibility_epoch` 是 bigint、server_default 0、"
            "全仓库唯一写入点只做 `+1`（`repository.reconcile_close_intents`）⇒ **永远非负** "
            "⇒ `EligibilityEpochAdvancedError` provably-dead，而 `compared` 返回值里却报着 "
            "`close_leader_eligibility_epoch`，向调用方宣称「eligibility 已重验」。"
            "修前 S17 的结果是 `applied`：leader 在 promotion 之后失格，内容照样提交"
            "（AC 10.10 末句要求它进 authorization_stale）",
        wants=(
            _off(
                "TestFinalAuthorizationFence::"
                "test_each_branch_rejects_independently[close_capture_eligibility_advanced]"
            ),
        ),
    ),
    SpanMutation(
        id="D04", path=OH,
        anchor="        if frozen.frozen_close_leader_eligibility_epoch is None:\n"
               "            raise CloseCaptureEligibilityUnprovenError(",
        new="        if False:\n"
            "            raise CloseCaptureEligibilityUnprovenError(",
        want=_off(
            "TestFinalAuthorizationFence::"
            "test_each_branch_rejects_independently[close_capture_eligibility_unproven]"
        ),
        why="「无从证明 leader 曾合法」与「曾合法但已失效」必须分型。短路前者后 "
            "`int(None)` 抛 `TypeError` —— 第三种、不可诊断的失败形态（fence 的 "
            "`except FinalFenceError` 接不住它，落到通用 `except Exception` ⇒ "
            "结果从 `authorization_stale` 变成 `error`，于是撤权 application 进了普通 retry "
            "队列）。这正是 `assert_published_digest_was_approved` 当初分型的同一理由",
    ),
    SpanMutation(
        id="D05", path=OH,
        anchor="    if frozen.frozen_request_kind is RequestKind.close_capture:",
        new="    if frozen.frozen_request_kind is not RequestKind.close_capture:",
        want=_off(
            "TestFinalAuthorizationFence::"
            "test_eligibility_is_not_compared_for_ordinary_forcesave"
        ),
        why="把 eligibility 判据张冠李戴到普通 forcesave 上。普通 forcesave 从不经 leader "
            "仲裁，拿 room 的 leader 资格 epoch 跟它比就是拿无关量当判据；别人的 close "
            "leader 失格会推进 room epoch，那时正在飞的普通 forcesave 会被误杀"
            "（真正该拦它的是 `write_fence_epoch` —— 撤销 writer 必提升 write fence）。"
            "反过来 close-capture 则再也不比 ⇒ 缺陷①原地复活",
        wants=(
            _off(
                "TestFinalAuthorizationFence::"
                "test_close_capture_reports_a_real_eligibility_comparison"
            ),
        ),
    ),
    SpanMutation(
        id="D06", path=OH,
        anchor="                sa.select(WorkpaperOoCloseIntentEvent.eligibility_epoch)",
        new="                sa.select(WorkpaperOoCloseIntent.eligibility_epoch)",
        want=_pg(
            "TestCloseCaptureEligibilityFence::"
            "test_frozen_side_reads_the_promotion_event_not_the_intent_row"
        ),
        why="冻结侧改读 `close_intent.eligibility_epoch`（**intent 创建时**的值）而不是 "
            "append-only 的 promotion event。真实世界里两者必然分叉：前任 leader 在 "
            "promotion 前失格会让 room epoch +1，successor 在新 epoch 被 promote，而它的 "
            "intent 行还记着创建时的旧值 ⇒ 合法 successor 的 clean close 被误判成 stale。"
            "🔴 这条变异只有在 S18 摆出「intent 行 7 / promotion event 0 / room 0」的"
            "判别性输入后才能被证伪 —— 单人 close 下两值都是 0，读哪一列都判等值，"
            "于是这个区分写了也无人能证伪（`test_the_desync_..._was_staged` 是那条输入"
            "自身的自证）",
    ),
    SpanMutation(
        id="D07", path=OH,
        anchor="            await self._terminate_stale_close_capture(state, error_code=error_code)",
        new="            pass",
        want=_pg(
            "TestCloseCaptureEligibilityFence::"
            "test_generation_is_superseded_so_the_close_is_not_blocked_forever"
        ),
        why="缺陷③的精确复现（修前形态：`_record_post_durable_failure` 只写 application/"
            "operation 终态就返回）。AC 10.10 末句是「进入 `authorization_stale` **并** "
            "supersede/recovery」，Property 63 另有「不能永久 blocked」。"
            "reconciler 见到 `state=promoted` 就提前返回并把这条路交给最终 fence"
            "（`repository.reconcile_close_intents` 源码注释原文），所以 fence 不 supersede "
            "就没有第二个人会做：room 停在 `close_barrier`，clean close 永远等不到内容，"
            "UI 只能显示无限 loading",
    ),
    SpanMutation(
        id="D08", path=OH,
        anchor="        room = await self._repo.lock_room(state.frozen.room_id)\n"
               "        if room.superseded_at is not None:\n"
               "            state.room_superseded = True\n"
               "            return",
        new="        room = await self._repo.lock_room(state.frozen.room_id)\n"
            "        if room.superseded_at is None:\n"
            "            state.room_superseded = True\n"
            "            return",
        want=_pg(
            "TestCloseCaptureEligibilityFence::"
            "test_generation_is_superseded_so_the_close_is_not_blocked_forever"
        ),
        why="幂等分支的条件取反 ⇒ 「已 superseded 就不再推进」变成「还没 supersede 就直接"
            "返回」。与 D07 分开：D07 短路的是**调用**，本条短路的是 supersede 自身的"
            "幂等守卫。两条共用一个判据时，靠前的失败会遮蔽靠后的，于是分别注入才能"
            "证明两段各自都有牙 —— 而 `room_superseded=True` 仍会被写上，"
            "所以只看 outcome 字段的守卫会漏掉本条（判据必须落在 room **行**的 "
            "`state`/`refresh_reason` 上）",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 十、第三轮收口审计（2026-08-27 晚）抓到的第四个真实缺陷：
    #     人工裁决被「校验覆盖率后丢弃」
    # ═══════════════════════════════════════════════════════════════════
    #
    # 缺陷④的原始形态（两处一起才构成缺陷）：
    #   a) 分派写 `if merge.has_conflicts and not resolutions:` ⇒ 带裁决时走**无冲突分支**；
    #   b) 无冲突分支提交 `merge.merged` ⇒ 每个冲突字段保留 **current 侧**值。
    # 而 `merge.apply_resolutions` 在本模块**从未被 import**，Task 15 的
    # `_settle_projection` 又只校验裁决**覆盖**了每条冲突。于是「审计师点了取 incoming，
    # 落库的是 current」，且 `requires_client_refresh`（同样读 `self.merged`）连 refresh
    # 裁决都算错。四道关全绿：覆盖率校验过、extract 等值两边同为错值必等、
    # 未管理区域无关、最终 fence 只看授权与身份。
    #
    # ═══ 2026-08-27 Task 27 接线后本块整体翻转 ═══
    #
    # Task 26 的形态是「零接线 + fail-closed 闸门 + `deferred` 登记」；Task 27 落地了
    # 三层修法（`settle_adjudicated_projection` 折叠 → Task 15 独立重算 → refresh 判据
    # 改读 settled），登记随之翻成 `retired`。本块的六条因此**改判据而不是删掉**：
    # 从「证明闸门有牙」变成「证明接线有牙 + 闸门不会偷偷回来」。
    #
    # 与 `mutate_task27_conflict_resolution_guards.py` 的 A 块有意重叠：那份脚本证明
    # **Task 27 的**守卫有牙，本块证明**Task 26 的**守卫在翻转后仍然有牙。同一处生产
    # 代码被两份脚本各自钉住，是跨任务共享判据的正常形态（`merge.RETIRED_DEFERRALS`
    # 同理）。删掉本块会让 Task 26 的四文件面失去对这处接线的全部覆盖。
    SpanMutation(
        id="D09", path=OH,
        anchor="        merged = settle_adjudicated_projection(\n"
               "            merge=merge, resolutions=state.resolutions, contract=state.contract\n"
               "        )",
        new="        merged = merge.merged",
        want=_off(
            "TestManualAdjudicationIsWired::"
            "test_settle_branches_are_the_single_decision_point"
        ),
        why="绕过唯一决策点、直接发布未收敛快照 ⇒ 缺陷④的 (b) 半原样复活。"
            "真库侧同时红：落库 projection digest 变成 `merge.merged` 的那个，"
            "于是「审计师点了取 incoming，落库的是 current」",
        wants=(
            _pg(
                "TestManualAdjudicationIsAppliedOnRealDb::"
                "test_the_published_projection_is_the_folded_one"
            ),
        ),
    ),
    SpanMutation(
        id="D10", path=ME,
        anchor="    by_key = assert_all_conflicts_resolved(outcome.conflicts, choices)",
        new="    by_key = {}\n"
            "    assert_all_conflicts_resolved(outcome.conflicts, choices)",
        want=_off(
            "TestManualAdjudicationIsWired::test_adjudication_is_folded_not_discarded"
        ),
        why="折叠函数本体：覆盖率照常校验，但裁决**一条都不落进 values** ⇒ 返回的就是"
            "`merged` 的等价物。与 D09 分层：D09 打的是**调用点**（绕过决策点），"
            "本条打的是**判据体**（决策点在、但它不干活）。行为上两者都只表现为"
            "「落库值是 current」，因此必须各自可证伪",
        wants=(
            _pg(
                "TestManualAdjudicationIsAppliedOnRealDb::"
                "test_the_published_projection_is_the_folded_one"
            ),
        ),
    ),
    SpanMutation(
        id="D11", path=OH,
        anchor="            resolution_choices=state.resolutions,",
        new="",
        want=_off(
            "TestManualAdjudicationIsWired::test_resolutions_reach_the_commit_boundary"
        ),
        why="裁决不再交到唯一 commit 边界 ⇒ Task 15 的**独立重算**（第二把锁）恒不触发："
            "它只在 `resolution_choices` 非空时才校验折叠。**行为完全不变** —— 这正是"
            "「第二把锁被悄悄摘掉」的形态，只有形态判据会红。"
            "本条取代了旧 D11（闸门位置判据），因为闸门本身已随接线撤除",
    ),
    SpanMutation(
        id="D12", path=OH,
        anchor='    "intended_status": "retired",\n'
               '    "retired_by_task": "27",',
        new='    "intended_status": "deferred",\n'
            '    "retired_by_task": "27",',
        want=_off(
            "TestManualAdjudicationIsWired::test_retirement_registration_is_complete"
        ),
        why="「登记 ↔ 事实」双向锁死的**第一个方向**：接线在、登记却退回 deferred ⇒ "
            "下一个人核对欠账时会以为它还没还，可能再加一道 fail-closed 闸把 resolve "
            "端点整条掐死。同时打红 AST 侧那条（它断言 `intended_status == 'retired'`）",
        wants=(
            _off(
                "TestManualAdjudicationIsWired::"
                "test_coordinator_really_imports_and_calls_apply_resolutions"
            ),
        ),
    ),
    SpanMutation(
        id="D13", path=OH,
        anchor="from app.services.workpaper_sync.merge import (\n"
               "    MergeOutcome,\n"
               "    apply_resolutions,\n"
               "    merge_projections,\n"
               ")",
        new="from app.services.workpaper_sync.merge import MergeOutcome, merge_projections",
        want=_off(
            "TestManualAdjudicationIsWired::"
            "test_coordinator_really_imports_and_calls_apply_resolutions"
        ),
        why="双向锁死的**第二个方向**：登记写着 retired 而接线消失（`apply_resolutions` "
            "既不在 imported 也不在 called）。与 D12 反向，两条都打同一批守卫但断言消息里的"
            "`imported=`/`called=` 列表可区分。🔴 判据必须走 AST：docstring 里逐处解释"
            "接线来历时逐字写着这个符号名，子串匹配版本首轮实测直接假红",
    ),
    SpanMutation(
        id="D14", path=OH,
        anchor="            if merge.has_conflicts and not state.resolutions:\n"
               "                return await self._record_conflict(state)",
        new="            if merge.has_conflicts:\n"
            "                return await self._record_conflict(state)",
        want=_off(
            "TestManualAdjudicationIsWired::"
            "test_entry_dispatch_routes_adjudication_away_from_conflict_branch"
        ),
        why="缺陷④的 (a) 半反向复活：分派不再看裁决 ⇒ 带裁决的调用被登记成「仍有冲突」"
            "并冻结指针，resolve 端点整条失效（审计师提交裁决后什么都没发生）。"
            "真库侧同时红：带裁决的调用不再 applied",
        wants=(
            _pg(
                "TestManualAdjudicationIsAppliedOnRealDb::"
                "test_call_with_resolutions_succeeds"
            ),
        ),
    ),
    SpanMutation(
        id="D15", path=OH,
        anchor="def settle_adjudicated_projection(",
        new="def assert_manual_adjudication_not_wired(resolutions) -> None:\n"
            "    if resolutions:\n"
            "        raise ApprovedContractChildMissingError(\"gate is back\")\n"
            "\n"
            "\n"
            "def settle_adjudicated_projection(",
        want=_off(
            "TestManualAdjudicationIsWired::test_the_fail_closed_gate_did_not_come_back"
        ),
        why="回退判据：把 Task 26 的 fail-closed 闸门函数重新加回来。只加定义、不加调用，"
            "因此**行为完全不变** —— 而登记里保留的 `retired_fail_closed_gate` 字段让"
            "「闸门又回来了」有一个机器可核对的锚点。没有这条，Task 27 的接线被"
            "「先加回闸门、再逐步接上调用」这种半回退悄悄撤销时没人会发现",
    ),
]

#: 覆盖面分母：本任务新增/改动的守卫文件。
GUARD_FILES = {
    f"{OFF}.py": "Task 26 新建（纯判据 / 结构判据 / 轨迹 / merge 语义 / roundtrip）",
    f"{PG}.py": "Task 26 新建（真库：rematerialize / fence / 双基线 / retry / 三层拒绝）",
    "test_task14_merge_conflicts.py": "Task 26 改动（merge 消费方登记表↔事实双向锁死）",
    f"{T15_FILE}.py": "Task 26 改动（共享登记表的第二个消费方：全局等值判据 → 归因型）",
}

PYTEST_ARGS = [
    f"backend/tests/workpaper_sync/{OFF}.py",
    f"backend/tests/workpaper_sync/{PG}.py",
    "backend/tests/workpaper_sync/test_task14_merge_conflicts.py",
    # 🔴 `merge.RETIRED_DEFERRALS` 是跨任务共享登记表，Task 26 往里加了自己那条，
    # 因此它的**另一个**消费方守卫（Task 15）也进入本任务的变异面 —— 否则 N06/N07
    # 无从判定，而那条守卫恰恰是被本任务的合法改动打红过的。
    f"backend/tests/workpaper_sync/{T15_FILE}.py",
    "-q",
    "--tb=no",
    "-rf",
    "-p",
    "no:randomly",
]

if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            pytest_args=PYTEST_ARGS,
            description="Task 26 OO→HTML coordinator 守卫变异检验（跨行锚点）",
            # 冻结基线来源：2026-08-27 **第三轮**收口实测。四文件合并跑
            # （`py -3 -m pytest <四文件> -q -p no:randomly`）得 `482 passed`，
            # 且逐文件单跑相加同为 482 —— 两种口径一致才写进来：
            #   `test_task26_oo_to_html.py`      129（117 + 本轮补 12）
            #   `test_task26_oo_to_html_pg.py`    96（ 90 + 本轮补  6）
            #   `test_task14_merge_conflicts.py` 178
            #   `test_task15_content_mutation.py` 79
            # 本轮新增的 18 条全部围绕缺陷④（人工裁决被丢弃）与 P43 的显式覆盖率判据。
            # 🔴 上一版写 431 而实测 352，是「把错值当基线锁死」：同目录
            # `mutation_report.json` 里每条 summary 都是「1 failed, 351 passed」，
            # 冻结值从第一天起就没对上过。`run_cli` 只对不符发 `[WARN]`
            # （verdict 走失败名集合差集，不依赖这个数），所以错值不污染判定，
            # 但会让「基线是否漂移」这条自检恒响 ⇒ 下一个人学会忽略它。
            # 改这个数必须同时说明来源与核对口径。
            #
            # 2026-08-27 Task 27 接线后**实测重取**（两种口径一致才写进来）：
            # 四文件合并跑 `491 passed`；逐文件单跑相加同为 491 ——
            #   test_task26_oo_to_html.py      133（131 + 本轮 D 块翻转补 2）
            #   test_task26_oo_to_html_pg.py    99（S19 由「拒绝」改「折叠后发布」，净 -1）
            #   test_task14_merge_conflicts.py 178
            #   test_task15_content_mutation.py  81（79 + Task 27 补的折叠重算判据 2）
            baseline_passed=491,
        )
    )
