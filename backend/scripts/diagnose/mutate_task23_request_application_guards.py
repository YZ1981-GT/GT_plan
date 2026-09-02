# -*- coding: utf-8 -*-
"""Task 23 变异检验：frozen request、application 去重、sequence 收敛与读路径守卫。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 2 Task 23
Requirements: 2.9, 4.1, 4.3, 4.10, 4.11, 5.4, 5.5, 5.10, 8.5, 10.5, 10.11, 14.3
Properties: P18 / P36 / P56 / P62 / P64

用法（仓库根目录）::

    py -3 backend/scripts/diagnose/mutate_task23_request_application_guards.py --list
    py -3 backend/scripts/diagnose/mutate_task23_request_application_guards.py --check-anchors
    py -3 backend/scripts/diagnose/mutate_task23_request_application_guards.py --run all --out report.json

═══ 五类落点，缺一类就有判据盲区 ═══

1. **裁决顺序**（`arbitrate_resolve`）—— 每条 fence/identity/sequence 判据各一条，
   外加一条把 identity 比较整条短路的「顺序调换」变异。后者是 Property 36 的核心：
   同 canonical application 因 same-key duplicate 抬高 sequence 时若先比 sequence，
   就会 self-supersede。
2. **纯判定函数**（`assert_correlation_convergence` / `assert_recovery_claim_shape` /
   `assert_dispatchable`）—— 这些分支在真库 happy path 里一条都触发不到，
   判据只能是合成输入；变异逐条短路它们。
3. **接线顺序**（AST 判据）—— 把 ① 授权挪到 ③ 落库之后、删掉 ④ 自证调用，
   两者在 happy path 上**没有任何行为差异**，只有源码顺序判据会红。
   这是 AC 4.1「先落库再调 Command Service」在本模块能给到的最强判据。
4. **V151 约束逐条削** —— 归属表 `_CONSTRAINT_EXPECT` 里每个执法点单独削掉，
   看**且只看**声明它的那一行翻。这是「归因不是抄的」的唯一判据形态。
5. **仓储侧收敛与幂等** —— 并发 create-or-hit、GREATEST fold、room fence 推进、
   fingerprint 比对、409 不泄露旧标识。最后一条属「负向承诺注入反例」：
   把旧 id 塞回异常文本，`leaks_prior_request` 必须打红。

═══ 无效变异的已知形态（本脚本刻意避开）═══

* 改注释/docstring —— 不在判据作用域内，判定必 GREEN 而与守卫无关；
* 同时违反两条判据 —— 打红了但分不清是哪条在工作（WRONG-TEST 的温床）。
  V151 那批尤其要小心：本任务的 PG 探针已经逐条构造成「只违反自己那一条」
  （见 `_forbidden` 各处注释：4 条首轮被别的约束遮蔽，全部改成 INSERT 路径或
  换列才单独可证），所以这批变异可以逐条归因。
* 绝对 `line=` 定位 —— 行号会随上游补类/补注释整体漂移（Task 22 的 M02 实测
  ANCHOR-MISS）。本脚本一律用唯一文本或 `scope`+`offset`。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts
from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

RA = "backend/app/services/workpaper_sync/request_application.py"
REPOSITORY = "backend/app/services/workpaper_sync/repository.py"
V151 = "backend/migrations/V151__workpaper_sync_content_application_bundle_scope.sql"

MUTATIONS: list[Mutation] = [
    # ═══════════════════════════════════════════════════════════════════
    # 一、裁决顺序（Property 36 / AC 8.5）
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M01", side="be", path=RA, kind="replace",
        anchor="    if not same_canonical:",
        new="    if True:",
        want="test_identity_must_be_compared_before_sequence",
        why="identity 比较被短路 ⇒ 同 canonical application 也走「按 sequence 判 supersede」"
            "分支 ⇒ same-key duplicate 抬高 effective sequence 时自我 supersede"
            "（AC 5.5 明令禁止的 duplicate→primary→stale 循环）。"
            "这是本任务最重要的一条变异：它对应的输入是**判别性**的 —— "
            "两种比较顺序给出不同结论",
        wants=(
            "test_same_application_with_higher_sequence_only_folds",
            "test_self_supersede_is_impossible_for_every_higher_sequence",
        ),
    ),
    Mutation(
        id="M02", side="be", path=RA, kind="replace",
        anchor="        if int(room_latest_durable_sequence) > int(canonical_effective_request_sequence):",
        new="        if True:",
        want="test_different_but_not_newer_application_does_not_supersede",
        why="「只有较新且不同的 durable snapshot 才可 supersede」中的「较新」被删 ⇒ "
            "只要 canonical application 不同就 supersede，旧 conflict 被无故作废",
        wants=("test_equal_sequence_on_different_application_does_not_supersede",),
    ),
    Mutation(
        id="M03", side="be", path=RA, kind="replace",
        anchor="        if int(room_latest_durable_sequence) > int(canonical_effective_request_sequence):",
        new="        if int(room_latest_durable_sequence) >= int(canonical_effective_request_sequence):",
        want="test_equal_sequence_on_different_application_does_not_supersede",
        why="`>` 松成 `>=` ⇒ sequence **相等**的不同 application 也 supersede。"
            "与 M02 分开：M02 删掉整条比较，本条只挪动边界 —— 单点断言容易刚好落在正确侧，"
            "所以守卫用区间穷举 + 相等边界两条各自覆盖",
    ),
    Mutation(
        id="M04", side="be", path=RA, kind="replace",
        anchor="    if int(fence.room_generation) != int(current_room_generation):",
        new="    if False:",
        want="test_fence_changes_are_refused_before_anything_else[generation]",
        why="generation 变化不再拒 ⇒ 旧 generation 的裁决落到新基线上",
    ),
    Mutation(
        id="M05", side="be", path=RA, kind="replace",
        anchor="    if int(request_write_fence_epoch) != int(current_write_fence_epoch):",
        new="    if False:",
        want="test_fence_changes_are_refused_before_anything_else[write_fence]",
        why="write fence 变化不再拒 ⇒ 被撤销的会话仍可裁决（AC 4.7）。"
            "三条 fence 判据共用一个 `fence_changed` verdict，故必须逐条变异："
            "合成一条时删掉任一条都会被另两条遮蔽（Task 22 M04/M10 的同一形态）",
    ),
    Mutation(
        id="M06", side="be", path=RA, kind="replace",
        anchor="    if int(fence.client_edit_epoch) != int(current_client_edit_epoch):",
        new="    if False:",
        want="test_fence_changes_are_refused_before_anything_else[client_epoch]",
        why="client edit epoch 变化不再拒 ⇒ 编辑器已换轮次却按旧轮次裁决",
    ),
    Mutation(
        id="M07", side="be", path=RA, kind="replace",
        anchor="    if fence.conflict_set_digest.strip() != current_conflict_set_digest.strip():",
        new="    if False:",
        want="test_conflict_digest_mismatch_is_refused_before_identity",
        why="conflict set digest 不再比对 ⇒ 客户端按旧冲突集裁决新冲突集",
    ),
    Mutation(
        id="M08", side="be", path=RA, kind="replace",
        anchor="    if int(fence.expected_current_revision) != int(current_revision):",
        new="    if False:",
        want="test_current_revision_change_without_newer_application_rebases",
        why="current revision 变化不再 rebase ⇒ 裁决基于已过期的 current",
    ),
    Mutation(
        id="M09", side="be", path=RA, kind="replace",
        anchor="    folded = fold_effective_sequence(",
        new="    folded = min(",
        want="test_fold_never_lowers_the_normalized_sequence",
        why="GREATEST 换成 min ⇒ effective sequence 回退，同 app 的更高 request 被降级。"
            "不用「交换两个实参」：`fold_effective_sequence` 是 max，交换实参是恒等变换"
            "（那属无效变异）",
        wants=("test_same_application_with_higher_sequence_only_folds",),
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 二、纯判定函数（合成输入才能覆盖的分支）
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M10", side="be", path=RA, kind="replace",
        anchor="        if self.operation_shape is not OperationShape.pre_correlation:",
        new="        if False:",
        want="test_receipt_refuses_to_dispatch_when_application_already_exists[primary_shape]",
        why="accepted 凭据不再检查 shell 形态 ⇒ 已 correlate 的 shell 也能拿去调 Command Service",
        wants=(
            "test_receipt_refuses_to_dispatch_when_application_already_exists[duplicate_shape]",
        ),
    ),
    Mutation(
        id="M11", side="be", path=RA, kind="replace",
        anchor="        if self.application_count != 0:",
        new="        if False:",
        want="test_receipt_refuses_to_dispatch_when_application_already_exists[precreated_application]",
        why="「accepted 前零 application」的真查库结果不再校验 ⇒ AC 4.1 的预建禁令失效。"
            "与 M10 分开：shape 与 count 覆盖的是两种不同失效（自己建过 / 别人并发建过）",
        wants=("test_dispatch_guard_rejects_precreated_application",),
    ),
    Mutation(
        id="M12", side="be", path=RA, kind="replace",
        anchor="    if shape is not reported_shape:",
        new="    if False:",
        want="test_convergence_refuses_each_broken_shape[shape_mismatch]",
        why="correlation 报告的 shape 与行实际形态不再核对 ⇒ 「报 primary 实为 duplicate」"
            "可以一路传到 Task 26 的 engine",
    ),
    Mutation(
        id="M13", side="be", path=RA, kind="replace",
        anchor="        if application_id != canonical_application_id:",
        new="        if False:",
        want="test_convergence_refuses_each_broken_shape[primary_wrong_application]",
        why="primary 绑的不是本次 canonical application 时不再拒 ⇒ 跨 application 串数据",
    ),
    Mutation(
        id="M14", side="be", path=RA, kind="replace",
        anchor="        if duplicate_of_operation_id != canonical_primary_operation_id:",
        new="        if False:",
        want="test_convergence_refuses_each_broken_shape[duplicate_not_direct]",
        why="duplicate 不再要求**直指** canonical primary ⇒ 链/环的入口"
            "（Property 18 的「no chains, no cycles」）",
    ),
    Mutation(
        id="M15", side="be", path=RA, kind="replace",
        anchor="    if int(effective_request_sequence) < int(origin_request_sequence):",
        new="    if False:",
        want="test_convergence_refuses_each_broken_shape[effective_below_origin]",
        why="`effective >= origin` 不再自证 ⇒ GREATEST fold 语义被破坏时服务层静默放过",
    ),
    Mutation(
        id="M16", side="be", path=RA, kind="replace",
        anchor="    if operation_shape not in (OperationShape.primary, OperationShape.duplicate):",
        new="    if False:",
        want="test_recovery_claim_shape_refuses_each_broken_case[pre_correlation]",
        why="recovery claim 的 shell 停在 pre-correlation 时不再拒 ⇒ "
            "claim 之后仍是 nullable-operation，会被普通 retry 捡走（AC 5.8）",
    ),
    Mutation(
        id="M17", side="be", path=RA, kind="replace",
        anchor="    if case_application_id != application_id:",
        new="    if False:",
        want="test_recovery_claim_shape_refuses_each_broken_case[case_binds_another_application]",
        why="case 与 claim 得到的 application 不再要求同一个 ⇒ "
            "case/delivery 指向不同 canonical application（AC 5.4 末段）",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 三、接线顺序（AST 判据；happy path 上零行为差异）
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M18", side="be", path=RA, kind="delete",
        anchor="        accepted.assert_dispatchable()",
        want="test_freeze_and_persist_calls_the_four_steps_in_order",
        why="删掉落库后的自证调用。**happy path 上没有任何行为差异**"
            "（计数本来就是 0），所以只有 AST 顺序判据会红 —— 这正是它存在的理由。"
            "M11 削的是断言体，本条删的是调用点：两者缺一，「凭据自证」就有一半是死代码",
    ),
    Mutation(
        id="M19", side="be", path=RA, kind="swap",
        anchor="        room, participant, confirmation = await self._rooms.assert_can_initiate_request(",
        anchor2="        outcome = await self._repo.create_forcesave_request_with_shell(",
        # 两个块的块首标记（`block_range` 从锚点向上找它；两条锚点行自身即块首）
        block_open="= await self.",
        want="test_freeze_and_persist_calls_the_four_steps_in_order",
        why="把 ① authorization-first 整块挪到 ③ 落库之后。这是 AC 4.1 的核心顺序，"
            "而 happy path 下两种顺序的**结果完全相同** ⇒ 全部行为守卫都不会红，"
            "只有 AST 顺序判据能看见",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 四、读路径与 authorization-first（AC 5.5 末段 / 10.5）
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M20", side="be", path=RA, kind="replace",
        anchor="        if not isinstance(ref, AuthorizedOperationRef):",
        new="        if False:",
        want="test_canonicalize_requires_an_authorized_reference",
        why="canonicalize 接受任意对象 ⇒ 「authorization-first 由参数类型强制」失效",
    ),
    Mutation(
        id="M21", side="be", path=RA, kind="replace",
        anchor="        if ReadStage.requested_action_authorized not in ref.stages:",
        new="        if False:",
        want="test_canonicalize_requires_an_authorized_reference",
        why="只完成 scope 解析、未过当前权限重验的 ref 也能 canonicalize ⇒ "
            "撤权后的重放拿到 canonical primary 的结果。与 M20 分开："
            "M20 拦「不是 ref」，本条拦「是 ref 但没授权」",
    ),
    # 🔴 scope 比对拆成两条单维变异（project / entry）。
    # 三个维度写在一个 `or` 链里，整条短路会让「哪一维在工作」无法归因；
    # 而 `or` 链下只短路其中一维时，另两维仍能挡住 —— 所以每条变异必须配一个
    # **只违反那一维**的场景（守卫里 `cross_scope_project` / `cross_scope_entry`
    # 正是这么构造的）。
    Mutation(
        id="M22", side="be", path=RA, kind="replace",
        anchor="            row.project_id != declared_project_id",
        new="            False and row.project_id != declared_project_id",
        want="test_scope_mismatch_and_unknown_id_share_one_404_envelope[cross_scope_project]",
        why="project 维不再比对 ⇒ 跨 project 拿别人的 operation。"
            "只短路这一维（其余 `or` 分支保留）才能证明是这一维在工作",
    ),
    Mutation(
        id="M50", side="be", path=RA, kind="replace",
        anchor="            or str(row.entry_id) != str(declared_entry_id)",
        new="            or False",
        want="test_scope_mismatch_and_unknown_id_share_one_404_envelope[cross_scope_entry]",
        why="entry 维不再比对 ⇒ 同 wp 下跨 entry 拿别人的 operation",
    ),
    Mutation(
        id="M23", side="be", path=RA, kind="replace",
        anchor="            if not verdict:",
        new="            if False:",
        want="test_authorization_fires_before_any_business_row_is_loaded",
        why="`authorize` 返回 False 也放行 ⇒ 403 语义消失。"
            "守卫用「只在 scope index 登记、无业务行」的 ghost id 判定："
            "删掉这道门后它会落到 404，而不是 403",
    ),
    Mutation(
        id="M24", side="be", path=RA, kind="replace",
        anchor="                raise ScopeAuthorizationDeniedError(",
        # `raise ScopeAuthorizationDeniedError(` 在本文件出现多次，用相对定位消歧：
        # `if not verdict:` 是它上方唯一且语义稳定的一行（绝对 line= 会随补类漂移）。
        scope="            if not verdict:",
        offset=1,
        new="                raise OperationScopeNotVisibleError(",
        want="test_authorization_fires_before_any_business_row_is_loaded",
        why="把 403 换成 404 类型 ⇒ 「可见但不允许」与「不存在」混为一谈（AC 10.5 要求分型）。"
            "这条与 M23 的区别：M23 是**不拒**，本条是**拒错类型** —— "
            "两者共用一条守卫时，只有守卫同时断言了 403 与 404 两态才都能红",
    ),
    Mutation(
        id="M25", side="be", path=RA, kind="replace",
        anchor="            if app_id is None:",
        new="            if False:",
        want="test_pre_correlation_shell_is_readable_but_not_as_a_bound_operation",
        why="canonical primary 未绑定 application 时不再拒 ⇒ "
            "「只要求 canonical primary 唯一绑定 application」这条要求被削成零要求",
    ),
    Mutation(
        id="M26", side="be", path=RA, kind="replace",
        anchor="            if bound != 1:",
        new="            if False:",
        want="test_service_rejects_a_double_bound_primary_when_the_unique_index_is_gone",
        why="「唯一绑定」的那个 1 不再校验。这条分支被 `uq_wpso_application` 遮蔽成"
            "**不可达**，守卫因此在事务内 DROP 唯一约束把它变成可证的 —— "
            "没有那个探针，本条必判 GREEN（不可达分支的「已锁住」只是自述）",
    ),
    Mutation(
        id="M27", side="be", path=RA, kind="replace",
        anchor="        if requested_shape is OperationShape.duplicate:",
        new="        if False:",
        want="test_duplicate_read_verifies_direct_primary_before_canonicalizing",
        why="duplicate 读路径不再记 `direct_primary_verified` 阶段 ⇒ "
            "「先验 direct-primary 再 canonicalize」这条顺序无法被观测",
    ),
    Mutation(
        id="M28", side="be", path=RA, kind="replace",
        anchor="        row = await self._repo.resolve_scope(",
        new="        row = await self._repo.lock_room(room_id) or await self._repo.resolve_scope(",
        want="test_authorization_stage_reads_only_the_scope_index",
        why="**回插禁止形态**：在授权阶段先查 room 反推 scope（AC 10.5 明令禁止）。"
            "行为上多半看不出差别（结果一样），只有源码形态判据会红 —— "
            "这正是 `assert_authorization_first_source_shape` 存在的理由",
    ),
    Mutation(
        id="M29", side="be", path=RA, kind="replace",
        anchor="        return operation_id is not None",
        new="        return True",
        want="test_nullable_operation_recovery_case_never_enters_ordinary_retry",
        why="`retry_eligibility` 恒真 ⇒ claim 前的 nullable-operation recovery case "
            "被普通 retry 捡走，伪造出一条不该存在的 operation timeline（AC 5.8 / 14.3）",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 五、仓储侧收敛与幂等（真并发才暴露）
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M30", side="be", path=REPOSITORY, kind="replace",
        anchor='                .on_conflict_do_nothing(index_elements=["application_key"])',
        new='                .on_conflict_do_nothing(index_elements=["id"])',
        want="test_race_used_real_concurrency_not_a_serial_loop",
        why="create-or-hit 的冲突目标换成 `id` ⇒ 并发 loser 的 INSERT 不再被 DO NOTHING "
            "吸收，直接撞 `application_key` 唯一约束 ⇒ 事务失败。"
            "**只有真并发能打红**：串行下第二次调用同样命中 DO NOTHING 失效，"
            "但那时唯一约束也一样会拦 —— 差别在于串行路径本来就走 fold 分支",
        wants=(
            "test_race_yields_one_primary_and_n_minus_one_direct_duplicates",
            "test_fold_race_used_real_concurrency",
        ),
    ),
    Mutation(
        id="M31", side="be", path=REPOSITORY, kind="replace",
        anchor="            folded = fold_effective_sequence(previous, int(req.request_sequence))",
        new="            folded = previous",
        want="test_fold_race_converges_effective_to_max_without_self_supersede",
        why="同 key 后续 request 不再 fold ⇒ `effective_request_sequence` 停在 origin，"
            "room canonical fence 指向过时 sequence。"
            "守卫的确定性 fold 场景（origin 播种成最低 sequence）就是为这条准备的："
            "全并发场景下 winner 可能恰好是最高 sequence，那时本条不会红",
        wants=("test_fold_race_writes_fold_events_carrying_the_room_fence",),
    ),
    Mutation(
        id="M32", side="be", path=REPOSITORY, kind="replace",
        anchor="        if effective_request_sequence < int(room.latest_durable_sequence):",
        new="        if True:",
        want="test_fold_race_converges_effective_to_max_without_self_supersede",
        why="room durable fence 永不推进 ⇒ canonical fence 不指向本次 application"
            "（AC 2.9 / 10.11 要求与 fold 同事务原子推进）",
        wants=("test_race_folds_to_max_sequence_without_self_supersede",),
    ),
    Mutation(
        id="M33", side="be", path=REPOSITORY, kind="replace",
        anchor="            if prior.frozen_request_fingerprint.strip() != frozen_request_fingerprint.strip():",
        new="            if False:",
        want="test_idempotency_conflict_returns_409_without_old_identifiers[payload_differs]",
        why="frozen fingerprint 不再比对 ⇒ 同 key 但 payload/contributor/fence 不同的重放"
            "拿回旧 request（AC 4.1「全部冻结字段等值才可返回旧 ID」被削）",
        wants=(
            "test_idempotency_conflict_returns_409_without_old_identifiers[contributors_differ]",
        ),
    ),
    Mutation(
        id="M34", side="be", path=REPOSITORY, kind="replace",
        anchor="            if not same_slot:",
        new="            if False:",
        want="test_idempotency_conflict_returns_409_without_old_identifiers[cross_participant]",
        why="唯一范围退化成 `(room, generation, key)` ⇒ 另一 participant / 另一 kind "
            "复用同 key 时返回**别人**的 request/operation id",
        wants=(
            "test_idempotency_conflict_returns_409_without_old_identifiers[cross_kind]",
        ),
    ),
    Mutation(
        id="M35", side="be", path=REPOSITORY, kind="replace",
        anchor='                    "Idempotency-Key 被另一个 participant 或另一种 kind 复用 —— "',
        new='                    f"Idempotency-Key 冲突（既有 request {prior.id}）—— "',
        want="test_idempotency_conflict_returns_409_without_old_identifiers[cross_participant]",
        why="**回插缺陷**：把旧 request id 塞进 409 的异常文本。"
            "AC 4.1 要求「409 且不得返回旧标识」，而「不返回」是一条负向承诺 —— "
            "只断言真实实现没泄露是不够的（它本来就没泄露），必须有一条把泄露插回去的"
            "变异，否则 `leaks_prior_request is False` 这个断言永远无法被证明有效",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 六、V151 约束逐条削（归属表 `_CONSTRAINT_EXPECT` 的唯一判据形态）
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M36", side="be", path=V151, kind="replace",
        anchor="    CONSTRAINT ck_wpca_effective_ge_origin CHECK (effective_request_sequence >= origin_request_sequence),",
        new="    CONSTRAINT ck_wpca_effective_ge_origin CHECK (true),",
        want="test_sequence_rule_is_enforced_by_its_declared_constraint[effective_below_origin]",
        why="削成恒真后，`effective < origin` 的 INSERT 必须变成 accepted。"
            "探针刻意走 INSERT 而不是 UPDATE：UPDATE 路径上本条被 BEFORE UPDATE 的"
            "mutation trigger 完全遮蔽（首轮实测），那样归因就是错的",
    ),
    Mutation(
        id="M37", side="be", path=V151, kind="replace",
        anchor="    CONSTRAINT ck_wpca_no_self_supersede CHECK (",
        new="    CONSTRAINT ck_wpca_no_self_supersede CHECK (true OR",
        want="test_sequence_rule_is_enforced_by_its_declared_constraint[self_supersede]",
        why="削成恒真后 `superseded_by_application_id = id` 必须 accepted（Property 18 的"
            "「同 canonical application 不得因自己的更高 sequence 被 supersede」）",
    ),
    Mutation(
        id="M38", side="be", path=V151, kind="replace",
        anchor="    CONSTRAINT uq_wpso_application UNIQUE (application_id),",
        new="    CONSTRAINT uq_wpso_application CHECK (true),",
        want="test_sequence_rule_is_enforced_by_its_declared_constraint[second_primary_for_application]",
        why="唯一约束换成恒真 CHECK（保留同名以免其他判据按名字找不到）⇒ "
            "一个 application 可被两个 operation 绑定 ⇒ 「唯一 primary」失效",
    ),
    Mutation(
        id="M39", side="be", path=V151, kind="replace",
        anchor="    CONSTRAINT ck_wpso_duplicate_shape CHECK (",
        new="    CONSTRAINT ck_wpso_duplicate_shape CHECK (true OR",
        want="test_sequence_rule_is_enforced_by_its_declared_constraint[stranded_duplicate_state]",
        why="削成恒真后 stranded duplicate（`state='duplicate'` 但无 duplicate 指针）"
            "必须 accepted",
        wants=("test_not_both_owners_is_shadowed_but_alive",),
    ),
    Mutation(
        id="M40", side="be", path=V151, kind="replace",
        anchor="    CONSTRAINT ck_wpso_not_both_owners CHECK (",
        new="    CONSTRAINT ck_wpso_not_both_owners CHECK (true OR",
        want="test_not_both_owners_is_shadowed_but_alive",
        why="削掉被遮蔽的那条纵深防御。守卫在事务内 DROP 遮蔽者 "
            "`ck_wpso_duplicate_shape` 之后再插 app+dup 行，此时**只有**本条能挡 ⇒ "
            "削掉它必须 accepted。没有那个 DROP 探针，本条永远判 GREEN",
    ),
    Mutation(
        id="M41", side="be", path=V151, kind="replace",
        anchor="    WHERE event_type = 'sequence_folded';",
        new="    WHERE event_type = 'never_matches';",
        want="test_sequence_rule_is_enforced_by_its_declared_constraint[fold_event_twice_same_request]",
        why="partial unique 的 WHERE 改成永不匹配 ⇒ 同一 request 对同一 application 可以"
            "写两条 fold event（幂等重放产生第二条审计记录）",
    ),
    Mutation(
        id="M42", side="be", path=V151, kind="replace",
        anchor="    CONSTRAINT ck_wpcae_fold_requires_room_fence CHECK (",
        new="    CONSTRAINT ck_wpcae_fold_requires_room_fence CHECK (true OR",
        want="test_sequence_rule_is_enforced_by_its_declared_constraint[fold_event_without_room_fence]",
        why="削成恒真后 fold event 可以不带 room durable fence ⇒ "
            "AC 10.11「fold 与 room fence 同事务原子决定」失去可测投影",
    ),
    Mutation(
        id="M43", side="be", path=V151, kind="replace",
        anchor="    WHERE to_state = 'application_bound';",
        new="    WHERE to_state = 'never_matches';",
        want="test_sequence_rule_is_enforced_by_its_declared_constraint[second_application_bound_event]",
        why="`application_bound` 在同 operation 内不再唯一 ⇒ 重放会写第二条 event"
            "（AC 5.10 要求「同事务落唯一 event」）",
    ),
    Mutation(
        id="M44", side="be", path=V151, kind="replace",
        anchor="    application_key CHAR(64) NOT NULL UNIQUE,",
        new="    application_key CHAR(64) NOT NULL,",
        want="test_sequence_rule_is_enforced_by_its_declared_constraint[duplicate_application_key]",
        why="application key 不再唯一 ⇒ 同 frozen identity + 同 incoming 可产生两个 "
            "application（Property 18 的「恰好一次」失效）",
        wants=("test_application_key_is_unique",),
    ),
    Mutation(
        id="M45", side="be", path=V151, kind="replace",
        anchor="    IF NEW.application_key IS DISTINCT FROM OLD.application_key",
        new="    IF false",
        want="test_sequence_rule_is_enforced_by_its_declared_constraint[application_key_immutable]",
        why="identity 不可变链里去掉 `application_key` 那一项 ⇒ key 可被改写。"
            "只削这一项（其余 OR 分支保留）是刻意的：探针只改 key，因此**只有**这一项"
            "能挡它 —— 一次削掉整条会同时让另外十几项无判据",
    ),
    Mutation(
        id="M46", side="be", path=V151, kind="replace",
        anchor="    IF v_req_sequence <> NEW.origin_request_sequence THEN",
        new="    IF false THEN",
        want="test_sequence_rule_is_enforced_by_its_declared_constraint[origin_sequence_immutable]",
        why="identity trigger 不再把 `origin_request_sequence` 与 origin request 行"
            "**跨行**比对。此时改 origin 会落到 mutation trigger 的 identity-列 分支，"
            "报文片段随之改变 ⇒ 守卫对「执法点是 identity trigger」的归因必须打红。"
            "这条同时证明了归因的精确性：不是「随便哪个 trigger 拦住就算」",
    ),
    Mutation(
        id="M47", side="be", path=V151, kind="replace",
        anchor="    IF v_t_application IS NULL OR v_t_duplicate IS NOT NULL OR v_t_state = 'duplicate' THEN",
        new="    IF false THEN",
        want="test_sequence_rule_is_enforced_by_its_declared_constraint[duplicate_chain]",
        why="direct-primary invariant 的库内执法点被削 ⇒ duplicate 可以指向另一个 "
            "duplicate（链/环）。探针刻意用 INSERT 造一行「行级 CHECK 全合法、只是目标是 "
            "duplicate」的行：首轮用 UPDATE 改 primary 时被 `ck_wpso_duplicate_shape` "
            "抢先挡住，被测 trigger 一次都没跑到（WRONG-TEST）",
    ),
    Mutation(
        id="M48", side="be", path=V151, kind="replace",
        anchor="    IF OLD.duplicate_of_operation_id IS NOT NULL",
        # 该 IF 的条件跨两行且是 AND 链：短路第一个合取项即整条为假
        # （跨行锚点在 CRLF 工作树下必 ANCHOR-MISS，故只锚单行）
        new="    IF false AND OLD.duplicate_of_operation_id IS NOT NULL",
        want="test_sequence_rule_is_enforced_by_its_declared_constraint[duplicate_pointer_removed]",
        why="duplicate 指针可被删除/改指 ⇒ Property 18 的「删除 duplicate pointer 必须失败」失效",
    ),
    Mutation(
        id="M49", side="be", path=V151, kind="replace",
        anchor="    IF OLD.application_id IS NOT NULL AND NEW.application_id IS DISTINCT FROM OLD.application_id THEN",
        new="    IF false THEN",
        want="test_sequence_rule_is_enforced_by_its_declared_constraint[primary_rebound]",
        why="已绑定 application 的 operation 可改绑 ⇒ duplicate→primary 重定向的入口"
            "（AC 5.5 明令禁止）",
    ),
]

GUARD_FILES = {
    "test_task23_request_application.py": "Task 23 离线守卫（裁决顺序 / 凭据 / 收敛形态 / 结构判据）",
    "test_task23_request_application_pg.py": "Task 23 真实 PostgreSQL 行为守卫（真并发收敛 / 约束归因 / 读路径）",
}

if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="Task 23 frozen request / application 去重 / sequence 收敛守卫变异检验",
            backend_args=[
                "backend/tests/workpaper_sync/test_task23_request_application.py",
                "backend/tests/workpaper_sync/test_task23_request_application_pg.py",
                "-q",
                "--tb=no",
                "-rf",
                "-p",
                "no:cacheprovider",
            ],
            baseline_backend_passed=117,
        )
    )
