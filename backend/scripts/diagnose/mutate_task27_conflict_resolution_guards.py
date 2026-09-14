# -*- coding: utf-8 -*-
"""Task 27 变异检验：resolve fence 接线、裁决折叠、retry 准入与 opaque-version rollback。
spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 2 Task 27
Requirements: 6.18, 8.1~8.12, 10.10
Properties: P35 / P36 / P37 / P38 / P43 / P65 / P67

用法（仓库根目录）::

    py -3 backend/scripts/diagnose/mutate_task27_conflict_resolution_guards.py --list
    py -3 backend/scripts/diagnose/mutate_task27_conflict_resolution_guards.py --check-anchors
    py -3 backend/scripts/diagnose/mutate_task27_conflict_resolution_guards.py --run all \\
        --report-path .kiro/specs/.../evidence/task27-conflict-resolution/mutation_report.json

═══ 为什么用 `_mutation_kit.span` ═══

与 Task 26 同两条理由：①`span.run_cli` 不落 `.mutbak`（内存持有变异前字节 + sha256 还原
自证），与并发会话互不干扰；②本任务多条判据的**本体就是相邻两行的组合**（准入判据与
resolver 调用的先后、fence 判定分支与 coordinator 调用的先后），单行锚点在这些位置多处
命中，只能靠绝对行号消歧 —— 而那一改文件就失效。

═══ 六类落点 ═══

1. **接线本体**（`settle_adjudicated_projection` 的四条分支 + Task 15 的独立重算）——
   这是 Task 26 登记、Task 27 退役的那笔欠账，也是本任务最贵的一处。逐条短路。
2. **refresh 判据的落点**（`_advance_room` 读 settled 还是 `merge.merged`）—— 缺陷的第二半。
3. **fence 接线**（读的是不是**服务端真值**、五种判定有没有各自的出口）。
4. **顺序**（准入判据在 resolver 之前、fence 拒绝在 coordinator 之前、
   闸门在 coordinator 之前）—— 顺序错时行为往往不变，只有形态判据会红。
5. **统一 404**（跨 scope 与不存在共用一个类型）与**封闭映射**（decision→HTTP）。
6. **回归类** —— 本任务开发过程中**真库实测**修掉的三个缺陷重新注入：
   * R01 `_frozen_fence` 读不存在的列名（`frozen_write_fence_epoch`）⇒ resolve 直接崩；
   * R02 rollback 的 artifact 路径与历史那一份逐字节相同 ⇒ 撞 `uq_wpa_relative_path`；
   * 第三个缺陷「准入判据排在 canonical resolver 之后 ⇒ 在所有可达输入上被遮蔽
     （provably dead）」的回归变异按落点归在 rollback 块里，就是 **D03**（它的 `why`
     写着「R03 回归」）—— 不另起一个 R03 id，避免同一条判据挂两个编号。
7. **canonicalize 之后的 id 归属**（G01/G02）—— requested 是 terminal duplicate 时，
   读冲突与回写轨迹都必须用 canonical primary 的 id。这一类缺陷 HTTP 仍是 200，
   只有真库 duplicate 场景能证伪。

═══ 刻意避开的无效变异形态 ═══

* 改注释/docstring —— 不在判据作用域内；
* 锚定 `try:` 行 —— 会把整个异常块的语义一起改掉，判定不可归因；
* 短路在正确实现下**恒不触发**的内嵌断言 —— 单独短路必判 GREEN。这就是为什么四条
  准入/折叠判据都被抽成模块级纯函数并用合成输入喂。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit.span import SpanMutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
CR = "backend/app/services/workpaper_sync/conflict_resolution.py"
OH = "backend/app/services/workpaper_sync/oo_to_html.py"
CM = "backend/app/services/workpaper_sync/content_mutation.py"
ME = "backend/app/services/workpaper_sync/merge.py"
AR = "backend/app/services/workpaper_sync/repository.py"

OFF = "test_task27_conflict_resolution"
PG = "test_task27_conflict_resolution_pg"
T26 = "test_task26_oo_to_html"
T26PG = "test_task26_oo_to_html_pg"
T15 = "test_task15_content_mutation"


def _off(node: str) -> str:
    return f"{OFF}.py::{node}"


def _pg(node: str) -> str:
    return f"{PG}.py::{node}"


def _t26(node: str) -> str:
    return f"{T26}.py::{node}"


def _t26pg(node: str) -> str:
    return f"{T26PG}.py::{node}"


def _t15(node: str) -> str:
    return f"{T15}.py::{node}"


MUTATIONS: list[SpanMutation] = [
    # ═══════════════════════════════════════════════════════════════════
    # 一、裁决折叠（Task 26 欠账的接线本体）
    # ═══════════════════════════════════════════════════════════════════
    SpanMutation(
        id="A01", path=OH,
        anchor="    return apply_resolutions(merge, resolutions, contract=contract)",
        new="    return merge.merged",
        want=_t26(
            "TestManualAdjudicationIsWired::test_adjudication_is_folded_not_discarded"
        ),
        why="把折叠退回 `merge.merged` —— 这**正是** Task 26 收口审计抓到的静默错值路径："
            "`merged` 对每个冲突字段保留 current 侧值，于是「审计师点了取 incoming，"
            "落库的是 current」。真库侧同时红：落库 projection digest 变成 merged 的那个。"
            "还会连带打红 Task 15 的独立重算（重算结果与提交值不再相等）",
        wants=(
            _t26pg(
                "TestManualAdjudicationIsAppliedOnRealDb::"
                "test_the_published_projection_is_the_folded_one"
            ),
            _pg("TestResolveProceeds::test_the_published_projection_is_the_folded_one"),
        ),
    ),
    SpanMutation(
        id="A02", path=OH,
        anchor="    if resolutions and not merge.has_conflicts:\n"
               "        raise AdjudicationWithoutConflictError(",
        new="    if False:\n"
            "        raise AdjudicationWithoutConflictError(",
        want=_t26(
            "TestManualAdjudicationIsWired::"
            "test_adjudication_without_conflict_is_refused"
        ),
        why="零冲突却带裁决时静默忽略 ⇒ 一次 resolve 请求被当成普通 apply 处理，"
            "审计师看到「裁决成功」而他选的字段根本没参与本次发布（conflict set 已被 "
            "rebase/supersede）。与 A03 分两条：两者共用类型时靠前的永久不可达",
    ),
    SpanMutation(
        id="A03", path=OH,
        anchor="    if merge.has_conflicts and not resolutions:\n"
               "        raise UnresolvedConflictError(",
        new="    if False:\n"
            "        raise UnresolvedConflictError(",
        want=_t26(
            "TestManualAdjudicationIsWired::test_unresolved_conflict_never_settles"
        ),
        why="有冲突却零裁决时回落到 `merge.merged` = **自动选 current**（AC 4.6 明令禁止）。"
            "判据复用冲突域既有类型而不是本模块再造一个同义类",
    ),
    SpanMutation(
        id="A04", path=OH,
        anchor="    if contract is None:\n"
               "        raise AdjudicationContractRequiredError(",
        new="    if False:\n"
            "        raise AdjudicationContractRequiredError(",
        want=_t26(
            "TestManualAdjudicationIsWired::"
            "test_adjudication_without_contract_is_refused"
        ),
        why="缺 contract 时无法按行身份/保护策略折叠（「整行删除」与「受保护字段只许 "
            "keep_current」都判不出来），静默继续会让 `apply_resolutions` 拿 None 崩在更深处",
    ),
    SpanMutation(
        id="A05", path=OH,
        anchor="        merged = settle_adjudicated_projection(\n"
               "            merge=merge, resolutions=state.resolutions, contract=state.contract\n"
               "        )",
        new="        merged = merge.merged",
        want=_t26(
            "TestManualAdjudicationIsWired::"
            "test_settle_branches_are_the_single_decision_point"
        ),
        why="绕过唯一决策点直接取未收敛快照。与 A01 分层：A01 打的是**判据体**、"
            "本条打的是**调用点**。形态判据（发布分支不得出现 `merge.merged`）与行为判据"
            "各自可证伪 —— 只有行为判据时，把决策点搬走再原地算一次同样的东西也算通过",
        wants=(
            _t26pg(
                "TestManualAdjudicationIsAppliedOnRealDb::"
                "test_the_published_projection_is_the_folded_one"
            ),
        ),
    ),
    SpanMutation(
        id="A06", path=OH,
        anchor="            if merge.has_conflicts and not state.resolutions:\n"
               "                return await self._record_conflict(state)",
        new="            if merge.has_conflicts:\n"
            "                return await self._record_conflict(state)",
        want=_t26(
            "TestManualAdjudicationIsWired::"
            "test_entry_dispatch_routes_adjudication_away_from_conflict_branch"
        ),
        why="分派不再看裁决 ⇒ 带裁决的调用被登记成「仍有冲突」并冻结指针，resolve 端点"
            "整条失效（审计师提交裁决后什么都没发生，而返回的是 conflict）。"
            "真库侧同时红：resolve 的 decision 是 proceed 但 revision 不动",
        wants=(
            _pg("TestResolveProceeds::test_revision_advanced_exactly_once"),
            _t26pg(
                "TestManualAdjudicationIsAppliedOnRealDb::test_call_with_resolutions_succeeds"
            ),
        ),
    ),
    SpanMutation(
        id="A07", path=OH,
        anchor="            resolution_choices=state.resolutions,",
        new="",
        want=_t26(
            "TestManualAdjudicationIsWired::test_resolutions_reach_the_commit_boundary"
        ),
        why="裁决不再交到唯一 commit 边界 ⇒ Task 15 的**独立重算**恒不触发"
            "（它只在 `resolution_choices` 非空时校验折叠）。行为完全不变 —— 这正是"
            "「第二把锁被悄悄摘掉」的形态，只有形态判据会红",
    ),
    SpanMutation(
        id="A08", path=CM,
        anchor="        folded = apply_resolutions(\n"
               "            mutation.merge, mutation.resolution_choices, contract=plan.contract\n"
               "        )",
        new="        folded = mutation.merge.merged",
        want=_t15(
            "TestConflictGate::test_unfolded_projection_is_rejected_even_with_full_coverage"
        ),
        why="唯一 commit 边界的独立重算退化成「拿 merged 跟自己比」= 重言式 ⇒ 任何调用方"
            "提交未折叠 projection 都能过关。这是「把错值当基线锁死」的镜像形态：判据在、"
            "但比的是同一个错值",
    ),
    SpanMutation(
        id="A09", path=OH,
        anchor='    "capability": "apply_resolutions（人工裁决 → merged projection）",',
        new='    "capability": "apply_resolutions（人工裁决 -> merged projection）",',
        want="*",
        why="对照项：只改共享登记表里一条 capability 文案的**措辞**（不改状态、不改接线），"
            "应当**不**打红。它证明本轮判定不是「只要碰了文件就红」——"
            "没有这条对照，全红的矩阵无法排除「判定过于敏感」这一解释",
        expect_green=True,
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 二、refresh 判据落点（缺陷的第二半）
    # ═══════════════════════════════════════════════════════════════════
    SpanMutation(
        id="B01", path=CM,
        anchor="            requires_refresh = projection_requires_client_refresh(\n"
               "                settled=settled,",
        new="            requires_refresh = projection_requires_client_refresh(\n"
            "                settled=mutation.merge.merged,",
        want=_off(
            "TestTask26DebtIsSettled::test_the_refresh_verdict_no_longer_reads_merge_merged"
        ),
        why="refresh 判据退回读 `merge.merged`。带裁决时两者不同：`merged` 与 incoming "
            "等值 ⇒ 判「不必重载」⇒ client-confirmed 基线被推进到客户端**从未见过**的内容上"
            "（AC 8.12 末句明令禁止）。行为在零冲突路径上完全不变，所以判据必须是形态",
    ),
    SpanMutation(
        id="B02", path=ME,
        anchor="        return projection_requires_client_refresh(\n"
               "            settled=self.merged, incoming=incoming, "
               "word_only_keys=self.word_only_keys\n"
               "        )",
        new="        return False",
        want=_t26pg(
            "TestRefreshRequired::test_server_last_applied_advances_but_client_confirmed_does_not"
        ),
        why="把「要不要重载」写死成 False ⇒ merged≠incoming 时 client-confirmed 仍然推进，"
            "room 不进 refresh_required，下一次 forcesave 带着错基线继续。"
            "本条打的是 merge 域的委托口径，与 B01 的调用侧分层",
        wants=(
            _t26("TestSettlementDigestPair::test_pair_is_asymmetric_when_word_only_differs"),
        ),
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 三、fence 接线：读的是不是服务端真值 + 五种判定各有出口
    # ═══════════════════════════════════════════════════════════════════
    SpanMutation(
        id="C01", path=CR,
        anchor="            write_fence_epoch=int(row[0]),\n"
               "            initiator_permission_epoch=int(row[1]),",
        new="            write_fence_epoch=0,\n"
            "            initiator_permission_epoch=0,",
        want=_pg("TestResolveProceeds::test_decision_is_proceed_and_maps_to_200"),
        why="frozen 侧 fence 写死成 0 ⇒ 与 room 现值恒不相等，所有 resolve 一律被拒"
            "（resolve 端点整条失效）。反向的危险形态由 C02 覆盖",
    ),
    SpanMutation(
        id="C02", path=CR,
        anchor="        return -1 if row is None else int(row[0])",
        new="        return int(\n"
            "            (\n"
            "                await self._session.execute(\n"
            "                    sa.select(\n"
            "                        WorkpaperForcesaveRequest.initiator_permission_epoch\n"
            "                    ).where(\n"
            "                        WorkpaperForcesaveRequest.id == app.origin_request_id\n"
            "                    )\n"
            "                )\n"
            "            ).scalar_one()\n"
            "        )",
        want=_pg("TestResolveFenceRejections::test_revoked_initiator_blocks_the_resolve"),
        why="把「当下仍然合法的发起人 epoch」退化成**读 request 上那个冻结值** ⇒ 观测侧与"
            "冻结侧永远相等 = 重言式，无论谁被撤销 fence 都判「授权仍有效」，撤销后的裁决"
            "照样落库（AC 10.10 明令禁止）。这与 Task 26 的 `_observed_contributor_digest` "
            "吃过的教训是同一形态。"
            "🔴 首版把哨兵 -1 改成 0（再改成 client_edit_epoch）都实测判 GREEN —— 因为那两个"
            "值仍然不等于冻结的 5，fence 照样拒绝。真正要证伪的是「观测口径」而不是「哨兵值」",
    ),
    SpanMutation(
        id="C05", path=CR,
        anchor="        if evaluation.decision is FenceDecision.rejected:\n"
               "            raise ResolveFenceRejectedError(",
        new="        if False:\n"
            "            raise ResolveFenceRejectedError(",
        want=_pg(
            "TestResolveFenceRejections::"
            "test_generation_change_is_rejected_with_its_own_reason"
        ),
        why="rejected 判定不再抛 ⇒ generation 已轮转/write fence 已提升/权限 epoch 已变的"
            "请求继续往下跑并真的发布内容。三条拒绝出口各自一条变异（C05/C06/C07），"
            "因为它们共用一个 `if` 链时靠前的失败会遮蔽靠后的",
        wants=(
            _pg("TestResolveFenceRejections::test_rejection_has_zero_side_effects"),
        ),
    ),
    SpanMutation(
        id="C06", path=CR,
        anchor="        if evaluation.decision is FenceDecision.superseded:\n"
               "            raise ResolveSupersededError(",
        new="        if False:\n"
            "            raise ResolveSupersededError(",
        want=_pg(
            "TestResolveFenceRejections::test_newer_different_application_supersedes"
        ),
        why="旧 conflict set 已被更新的 canonical application supersede 却仍被应用 ⇒ "
            "把过期裁决写进当前内容。与 C05 分型的理由是补救动作不同："
            "superseded 要「对最新 operation 重建裁决」，rejected 要「重开编辑器」",
    ),
    SpanMutation(
        id="C07", path=CR,
        anchor="        if evaluation.decision is FenceDecision.rebase:\n"
               "            rebased = await self._coordinator.apply_durable_incoming(",
        new="        if False:\n"
            "            rebased = await self._coordinator.apply_durable_incoming(",
        want=_pg(
            "TestResolveFenceRejections::"
            "test_current_revision_change_rebases_and_rebuilds_conflicts"
        ),
        why="current revision 已推进却不 rebase ⇒ 按**过期 current** 算出来的裁决被发布，"
            "服务端在这期间的改动被静默覆盖（AC 8.5 要求返回按原 frozen bundle 重建的 "
            "rebased conflict）",
    ),
    SpanMutation(
        id="C08", path=CR,
        anchor="    FenceDecision.fold: 200,",
        new="    FenceDecision.fold: 409,",
        want=_off("TestFenceJudgementHasASingleSource::test_fold_is_not_mapped_to_a_rejection"),
        why="把 fold 映射成 409 = 「同一 canonical application 因 same-key duplicate 抬高 "
            "effective sequence 时判自己 stale」—— AC 5.5 明令禁止的 self-supersede 与 "
            "duplicate→primary→stale 循环。真库侧同时红：fold 场景不再继续同一 conflict set",
        wants=(
            _off("TestDecisionMappingIsClosed::test_only_proceed_and_fold_are_success"),
        ),
    ),
    SpanMutation(
        id="C09", path=CR,
        anchor="    try:\n        return RESOLVE_DECISION_STATUS[decision]",
        new="    try:\n        return RESOLVE_DECISION_STATUS.get(decision, 200)",
        want=_off(
            "TestDecisionMappingIsClosed::"
            "test_unmapped_decision_raises_instead_of_defaulting"
        ),
        why="给未映射的判定一个 200 默认值 ⇒ 新增的**拒绝**判定被静默翻译成成功。"
            "这是 fail-open 掩盖接线错误的教科书形态：静态工具全绿、行为在现有枚举上不变",
    ),
    SpanMutation(
        id="C10", path=CR,
        anchor="        if not resolutions:\n"
               "            raise ResolveWithoutConflictError(",
        new="        if False:\n"
            "            raise ResolveWithoutConflictError(",
        want=_pg("TestResolveFenceRejections::test_empty_resolutions_are_refused"),
        why="零裁决的 resolve 被当成普通 apply ⇒ 「裁决成功」的审计事实落在一次没有任何"
            "人工选择的应用上（AC 8.6 的 actor/选择结果都成了空话）",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 四、顺序（行为往往不变，只有形态判据会红）
    # ═══════════════════════════════════════════════════════════════════
    SpanMutation(
        id="D01", path=CR,
        anchor="        confirmed = assert_retry_operation_eligible(operation_id)\n"
               "        return await self._coordinator.apply_durable_incoming(\n"
               "            operation_id=confirmed,",
        new="        assert_retry_operation_eligible(operation_id)\n"
            "        return await self._coordinator.apply_durable_incoming(\n"
            "            operation_id=operation_id,  # type: ignore[arg-type]",
        want=_off(
            "TestRetryEligibilityGate::"
            "test_the_gate_returns_the_id_so_the_call_cannot_be_dropped"
        ),
        why="闸门退化成「查了却不用」：返回值不再被消费，于是**删掉整行调用**不会有任何"
            "类型错误，下一个人重构时很自然就把它删了。行为此刻不变 —— 判据必须是形态",
    ),
    SpanMutation(
        id="D02", path=CR,
        anchor="    if operation_id is None:\n"
               "        raise RecoveryCaseRetryForbiddenError(",
        new="    if False:\n"
            "        raise RecoveryCaseRetryForbiddenError(",
        want=_off("TestRetryEligibilityGate::test_none_is_refused_with_its_own_code"),
        why="claim 之前的 unmatched/ambiguous recovery case 被当成普通 operation 重试 ⇒ "
            "伪造出一条 claim 之前不该存在的 operation timeline（AC 5.8 / 8.9 / 14.3）。"
            "真库侧同时红",
        wants=(
            _pg(
                "TestRetry::"
                "test_nullable_operation_retry_is_refused_with_zero_side_effects"
            ),
        ),
    ),
    SpanMutation(
        id="D03", path=CR,
        anchor="        artifact_kind, artifact_state = await self._artifact_kind_state(\n"
               "            source_rep.artifact_id\n"
               "        )\n"
               "        assert_rollback_source_publishable(\n"
               "            artifact_kind=artifact_kind, artifact_state=artifact_state\n"
               "        )\n"
               "        resolved = await self._resolution.resolve(",
        new="        resolved = await self._resolution.resolve(",
        want=_pg(
            "TestRollback::test_unpublished_canonical_artifact_is_refused_by_the_service"
        ),
        why="R03 回归：删掉准入判据后 resolver 的通用 `ArtifactNotPublishedError` 会接住"
            "同一个输入 —— **行为上仍然拒绝**，但原因从「这个版本不能作回滚源」变成"
            "「artifact 未发布」，而且本域判据在所有可达输入上都不可达（provably dead）。"
            "这正是本任务真库实测踩到并修掉的形态：判据在、却永远轮不到它",
    ),
    SpanMutation(
        id="D04", path=CR,
        anchor="        if expected_current_revision != current_revision:\n"
               "            raise RollbackRevisionRewindError(",
        new="        if False:\n"
            "            raise RollbackRevisionRewindError(",
        want=_pg("TestRollback::test_stale_expected_revision_is_refused"),
        why="rollback 的乐观锁被短路 ⇒ 客户端手里还是旧 revision（期间已有别人应用了内容）"
            "时仍然按旧值创建新版本，那一次应用被静默覆盖。"
            "🔴 本条的**第一版**锚在 `version.revision > current_revision` 上，实测判 GREEN："
            "content version 与 `content_revision` 同事务推进，那条分支在任何可达状态下都"
            "不成立 = provably dead。按项目规则该分支已被**删除**（而不是留着配一条恒 GREEN "
            "的变异），判据改钉真正有牙的这一条",
    ),
    SpanMutation(
        id="D05", path=CR,
        anchor="        if current_projection_sha256 == target_digest:",
        new="        if False:",
        want=_pg("TestRollback::test_unchanged_projection_means_zero_writes"),
        why="业务 projection 未变化时仍然创建新 content version ⇒ 制造**伪业务 revision**"
            "（AC 6.18 / 9.10 / Property 67 明令 revision 保持不变）。伪 revision 会污染"
            "evidence、双基线与全部历史读取的定位",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 五、统一 404 与 frozen contract 锁
    # ═══════════════════════════════════════════════════════════════════
    SpanMutation(
        id="E01", path=CR,
        anchor="        if scope is None or (\n"
               "            scope.project_id != declared_project_id\n"
               "            or scope.wp_id != declared_wp_id\n"
               "        ):",
        new="        if scope is None:",
        want=_pg("TestOpaqueVersionScope::test_the_scope_index_door_is_the_one_that_refuses"),
        why="跨 scope 的 version UUID 不再被 scope 门拦住 ⇒ authorization-before-resource "
            "被破：业务行**先被读了**才拒（AC 10.5 严禁先查资源反推 scope）。"
            "🔴 本条的**第一版** want 是「两个 404 共用一个 code」，实测判 GREEN —— "
            "业务行那道门会接住同一输入并抛同一类型。修法是给两道门各自一个**内部** "
            "`refused_at` 标记（不进 error_code、不进响应信封，因此不泄露存在性），"
            "判据改断言「拒绝发生在 scope_index 那一道」",
    ),
    SpanMutation(
        id="E02", path=CR,
        anchor="                sa.select(WorkpaperContentVersion).where(\n"
               "                    WorkpaperContentVersion.id == version_id,\n"
               "                    WorkpaperContentVersion.wp_id == declared_wp_id,\n"
               "                )",
        new="                sa.select(WorkpaperContentVersion).where(\n"
            "                    WorkpaperContentVersion.id == version_id,\n"
            "                )",
        want=_off(
            "TestAuthorizationFirstShape::test_the_business_row_query_filters_by_workpaper"
        ),
        why="业务行不再按 wp 过滤 ⇒ scope index 与 content version 行之间失去二次核对"
            "（scope row 被错写/被 retire 后就能跨 wp 定位）。"
            "🔴 这道门在 scope 门仍在时是**冗余**的，因此行为上不可证伪（任何跨 wp UUID 都"
            "先被 scope 门拦住）。冗余的第二道门只能用形态判据钉住 —— 首版 want=\"*\" 实测"
            "判 GREEN 正是因为没有形态判据",
    ),
    SpanMutation(
        id="E04", path=CR,
        anchor="                refused_at=REFUSED_AT_BUSINESS_ROW,",
        new="                refused_at=REFUSED_AT_SCOPE_INDEX,",
        want=_off(
            "TestAuthorizationFirstShape::"
            "test_the_two_404_doors_carry_distinguishable_internal_markers"
        ),
        why="两道门用同一个标记 ⇒ 「是哪一道门在拒」重新变得不可分辨，E01 又会退回 GREEN。"
            "本条守的是**判据本身的可分辨性**（元判据）：没有它，标记机制可以被悄悄合并掉",
    ),
    SpanMutation(
        id="E03", path=CR,
        anchor="    if (contract.canonical_sha256 or \"\").strip() != (slot_digest or \"\").strip():",
        new="    if False:",
        want=_off("TestFrozenContractLock::test_drifted_digest_is_refused"),
        why="按 registry **当前 alias** 渲染历史 operation 的预览/折叠 ⇒ 审计师看到的业务"
            "标签、单元格地址与 value_type 可能已漂移到新模板上（AC 6.2 / 7.10）。"
            "真库侧同时红",
        wants=(
            _pg("TestConflictPreview::test_a_drifted_contract_is_refused"),
        ),
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 六、冲突落行与裁决轨迹（AC 8.1 / 8.6）
    # ═══════════════════════════════════════════════════════════════════
    SpanMutation(
        id="F01", path=OH,
        anchor="        write = await self._repo.record_conflicts(",
        new="        write = await self._skip_record_conflicts(",
        want=_pg("TestConflictPreview::test_conflict_rows_were_really_persisted"),
        why="冲突不再落行 ⇒ 只剩 `conflict_count/digest` 两个标量：预览没有数据可读"
            "（AC 8.1 的九个要素全部丢失），裁决轨迹也无处可写（AC 8.6）。"
            "改成一个不存在的方法名而不是删整段：删整段会连带让 `write.inserted` "
            "NameError，归因变成「语法层错误」而不是「判据缺失」",
    ),
    SpanMutation(
        id="F02", path=AR,
        anchor="            if key in seen or row.superseded_at is not None:\n"
               "                continue\n"
               "            row.superseded_at = stamp",
        new="            if key in seen or row.superseded_at is not None:\n"
            "                continue\n"
            "            row.superseded_at = None",
        want=_pg(
            "TestConflictRowLifecycle::"
            "test_disappeared_conflicts_are_superseded_not_deleted"
        ),
        why="rebase 后消失的旧冲突不再被打 `superseded_at` ⇒ 预览把已经不存在的冲突"
            "继续展示给审计师，而它的三方值早已过期。"
            "🔴 首版 want 指向「冲突落行」那条，实测判 GREEN —— happy path 的冲突集从不缩小，"
            "所以这条分支恒不触发。补了直接喂仓储方法的合成场景（第二轮 rows=[]）之后才可证伪",
    ),
    SpanMutation(
        id="F03", path=CR,
        anchor="        marked = await self._repo.mark_conflicts_resolved(",
        new="        marked = 0 if True else await self._repo.mark_conflicts_resolved(",
        want=_pg("TestResolveProceeds::test_the_resolution_trail_was_written"),
        why="AC 8.6 的裁决轨迹（actor / 时间 / 选择结果 / 落地值）不再落库 ⇒ 事后无法回答"
            "「谁在什么时候选了什么」。内容照常发布，因此只有查冲突行的判据会红",
    ),
    SpanMutation(
        id="F04", path=CR,
        anchor="                \"resolved_value\": resolved_value_for(records[key], choice).to_jsonb(),",
        new="                \"resolved_value\": records[key].current.to_jsonb(),",
        want=_pg("TestResolveProceeds::test_the_resolution_trail_was_written"),
        why="轨迹里的落地值退回 current 侧 ⇒ 审计轨迹与实际发布内容不一致（轨迹说保留了"
            "current，内容里是 incoming）。与 F03 分层：F03 打的是「有没有写」，"
            "本条打的是「写的是不是对的值」",
    ),
    SpanMutation(
        id="F05", path=AR,
        anchor="            if row is None:\n"
               "                raise ScopeIntegrityError(\n"
               "                    f\"裁决 {key} 在 operation {operation_id} 的冲突行里不存在",
        new="            if row is None:\n"
            "                continue\n"
            "            if False:\n"
            "                raise ScopeIntegrityError(\n"
            "                    f\"裁决 {key} 在 operation {operation_id} 的冲突行里不存在",
        want=_pg(
            "TestConflictRowLifecycle::"
            "test_a_resolution_for_an_unknown_conflict_is_refused"
        ),
        why="裁决找不到对应冲突行时静默跳过 ⇒ 「裁决记录不全」变成静默失败，"
            "而轨迹的全部价值就在于完整。"
            "🔴 首版 want 指向 happy path 的轨迹断言，实测判 GREEN —— 正常裁决的 key 恒命中，"
            "这条分支不触发。补了「喂一个不存在的 key」合成场景之后才可证伪",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 七、回归：真库实测修掉的缺陷重新注入
    # ═══════════════════════════════════════════════════════════════════
    SpanMutation(
        id="R01", path=CR,
        anchor="                sa.select(\n"
               "                    WorkpaperForcesaveRequest.write_fence_epoch,\n"
               "                    WorkpaperForcesaveRequest.initiator_permission_epoch,\n"
               "                ).where(WorkpaperForcesaveRequest.id == app.origin_request_id)",
        new="                sa.text(\n"
            "                    \"SELECT frozen_write_fence_epoch, "
            "frozen_initiator_permission_epoch \"\n"
            "                    \"FROM working_paper_forcesave_request WHERE id = :rid\"\n"
            "                ).bindparams(rid=app.origin_request_id)",
        want=_pg("TestResolveProceeds::test_decision_is_proceed_and_maps_to_200"),
        why="R01 回归：把 fence 读取退回**手写 SQL 的错列名**（`frozen_write_fence_epoch` "
            "并不存在）。这是本任务真库实测抓到的第一个缺陷 —— 离线守卫、`get_diagnostics`、"
            "vitest 全绿，只有真库执行会 `UndefinedColumnError`。改用 ORM 列引用之后"
            "列名错误在 import 期就暴露",
    ),
    SpanMutation(
        id="R02", path=AR,
        anchor="        if existing is not None:\n"
               "            if (\n"
               "                existing.project_id != project_id",
        new="        if False:\n"
            "            if (\n"
            "                existing.project_id != project_id",
        want=_pg("TestRollback::test_rollback_creates_a_new_version_and_never_rewinds"),
        why="R02 回归：artifact 登记不再做内容寻址幂等 ⇒ rollback 重新 materialize 出"
            "**逐字节相同**的 representation（文件名 `{generation:09d}-{sha12}`、新 content "
            "version 的 generation 又从 1 起）时撞 `uq_wpa_relative_path`。"
            "这是回滚的**正常**路径而不是边缘情况",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 八、canonicalize **之后**的 id 归属（本轮补齐的覆盖空洞）
    # ═══════════════════════════════════════════════════════════════════
    #
    # 🔴 为什么这两条不能靠既有判据代替：四步读路径的**形态**由 AST 判据钉住
    # （`TestAuthorizationFirstShape`），duplicate 的跟随行为由 Task 23 的真库判据钉住。
    # 但两者都不覆盖「本模块拿到 `CanonicalRead` 之后用的是哪个 id」—— 其余 13 个真库
    # 场景里 requested 恒等于 canonical，于是把 canonical 换成 requested 时**一条都不红**
    # （本轮实测：补场景之前 G01/G02 双双 GREEN）。表现是静默错值：空预览 / 轨迹标 0 行，
    # 而 HTTP 仍然 200。
    SpanMutation(
        id="G01", path=CR,
        anchor="        rows = await self._repo.load_conflicts(\n"
               "            operation_id=canonical.canonical_operation.id,",
        new="        rows = await self._repo.load_conflicts(\n"
            "            operation_id=operation_id,",
        want=_pg(
            "TestDuplicateRequestedOperation::"
            "test_preview_through_the_duplicate_returns_the_primary_conflicts"
        ),
        why="冲突改按 **requested** id 读 ⇒ requested 是合法 terminal duplicate 时预览"
            "恒空（冲突行挂在 canonical primary 上），而响应仍是 200 + "
            "`conflict_count=0`：审计师看到「没有冲突」，于是那些冲突永远不会被裁决，"
            "下一次 forcesave 又被 refresh-required 挡住。AC 8.5 末段明令只要求 canonical "
            "primary 绑定 application，正是为了让 duplicate 也能读到同一份冲突集",
    ),
    SpanMutation(
        id="G02", path=CR,
        anchor="        marked = await self._record_resolution_trail(\n"
               "            operation_id=outcome.canonical_operation_id,",
        new="        marked = await self._record_resolution_trail(\n"
            "            operation_id=outcome.requested_operation_id,",
        want=_pg(
            "TestDuplicateRequestedOperation::"
            "test_the_resolution_trail_lands_on_the_primary_conflict_rows"
        ),
        why="裁决轨迹改按 **requested** id 回写 ⇒ duplicate 提交时冲突行一条都匹配不上。"
            "实测形态（2026-08-28）：内容**已经**经唯一 commit 边界发布、revision 已 +1，"
            "随后 `mark_conflicts_resolved` 抛 `ScopeIntegrityError` ——「内容进去了、"
            "AC 8.6 的轨迹（actor/时间/选择结果/落地值）没进去」，冲突行永远停在未裁决态，"
            "而调用方看到的是一个与裁决无关的完整性错误。与 G01 分两条：一条打读侧、"
            "一条打写侧，两者可以独立退化（G01 是静默空预览，本条是 commit 后失败）",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 九、裁决「真的落地了吗」（本轮真库实测抓到的生产缺陷 + 其守卫）
    # ═══════════════════════════════════════════════════════════════════
    #
    # 缺陷原文：Task 26 的 `apply_durable_incoming` 在 incoming **已 durable** 之后刻意
    # **不抛异常** —— 失败落成 `authorization_stale`/`error` 终态并保留 incoming
    # （AC 5.7/5.8：durable 之后返回非零 ack 等于静默丢件）。`resolve` 因此拿到一个
    # 「长得像成功」的 outcome，不看 `result` 就写裁决轨迹并回 200。
    # 实测（`workflow_locked=True`）：`conflict_rows_marked=1`、revision/version/pointer
    # 一个都没动 ⇒ 审计师看到「裁决成功」，而内容一个字都没发布。
    # 触发面是 AC 8.4 的复核锁定/归档与项目可见性 —— 这三样只活在 `AuthorizationProbe`
    # 后面，room fence 读不到，所以 resolve 自己那道 fence 拦不住。
    SpanMutation(
        id="H01", path=CR,
        anchor="        assert_resolve_apply_landed(\n"
               "            result=outcome.result.value,",
        # 🔴 替换体必须**语法合法**：首版写成 `_skipped = (` 时后续的 `error_code=...`
        # 成了元组里的关键字实参 ⇒ 模块 import 失败 ⇒ pytest 报 collection error 而不是
        # 测试失败，`judge` 的失败名差集为空 ⇒ 判 GREEN（4.2s 的运行时长是它的指纹）。
        # 那是**变异声明**的缺陷，不是守卫的缺陷。`dict(...)` 接受同一批关键字。
        new="        _skipped = dict(\n"
            "            result=outcome.result.value,",
        want=_pg(
            "TestWhoMaySubmitAdjudications::"
            "test_review_lock_or_archive_blocks_the_adjudication"
        ),
        why="把落地自证摘掉（保留表达式求值，因此不是「删掉一行就语法错」的无效变异）⇒ "
            "缺陷原样复活：复核锁定/归档/项目不可见时裁决轨迹照写、resolve 照回 200。"
            "离线侧同时红（顺序判据找不到这个调用）",
        wants=(
            _off(
                "TestResolveApplyLandedGate::"
                "test_the_gate_runs_before_the_adjudication_trail_is_written"
            ),
            _pg(
                "TestWhoMaySubmitAdjudications::"
                "test_none_of_the_refusals_wrote_an_adjudication_trail"
            ),
        ),
    ),
    SpanMutation(
        id="H02", path=CR,
        anchor='RESOLVE_LANDED_RESULTS: Final[frozenset[str]] = frozenset(\n'
               '    {"applied", "refresh_required"}\n'
               ')',
        new='RESOLVE_LANDED_RESULTS: Final[frozenset[str]] = frozenset(\n'
            '    {"applied", "refresh_required", "authorization_stale"}\n'
            ')',
        want=_off(
            "TestResolveApplyLandedGate::"
            "test_the_admissible_set_is_exactly_the_two_landed_states"
        ),
        why="把授权失效塞进「视为落地」的白名单 —— 这是判据在、集合被放宽的形态："
            "函数照样调、异常类型照样在，只是那条终态被静默放行。真库侧同时红",
        wants=(
            _pg(
                "TestWhoMaySubmitAdjudications::"
                "test_review_lock_or_archive_blocks_the_adjudication"
            ),
        ),
    ),
    SpanMutation(
        id="H03", path=CR,
        anchor='    if result == "authorization_stale":\n'
               "        raise ResolveAuthorizationStaleError(",
        new="    if False:\n"
            "        raise ResolveAuthorizationStaleError(",
        want=_pg(
            "TestWhoMaySubmitAdjudications::"
            "test_review_lock_or_archive_blocks_the_adjudication"
        ),
        why="不可重试（授权失效）与可重试（解析/发布失败）合流到同一个类型 ⇒ 前端只能给"
            "同一句话，而两者的补救路径相反（supersede/recovery vs 修因后 retry）。"
            "离线侧的逐终态参数化同时红",
        wants=(
            _off(
                "TestResolveApplyLandedGate::"
                "test_each_terminal_state_lands_on_its_own_verdict"
            ),
        ),
    ),
    SpanMutation(
        id="H04", path=CR,
        anchor="                where=f\"rebase of application {application_id}\",\n"
               "                landed=REBASE_ADMISSIBLE_RESULTS,",
        new="                where=f\"rebase of application {application_id}\",",
        want=_pg(
            "TestResolveFenceRejections::"
            "test_current_revision_change_rebases_and_rebuilds_conflicts"
        ),
        why="rebase 探测的**正常**结果是 `conflict`；不传宽一格的 `landed` 就会把它判成"
            "「落地失败」⇒ 409 rebase-required 变成 `resolve_apply_failed`，"
            "客户端拿不到重建后的冲突集。反向证明这个参数不是装饰",
        wants=(
            _off(
                "TestResolveApplyLandedGate::test_the_rebase_branch_also_asserts_landing"
            ),
        ),
    ),
    SpanMutation(
        id="H05", path=CR,
        anchor="            apply_result=result,\n"
               "            apply_error_code=error_code,\n"
               "        )",
        new="            apply_result=result,\n"
            "            apply_error_code=None,\n"
            "        )",
        want=_pg(
            "TestWhoMaySubmitAdjudications::"
            "test_review_lock_or_archive_blocks_the_adjudication"
        ),
        why="丢掉内层归因（是十条 fence 里的哪一条）⇒ 运维只看到「授权失效」，"
            "得自己猜是复核锁定、归档、项目不可见、generation supersede 还是 contributor "
            "漂移（AC 10.10 要求逐条可分辨）。缩进 12 空格的那一处是 "
            "`ResolveAuthorizationStaleError`，与末尾 8 空格的 `ResolveApplyFailedError` "
            "不同锚点，因此唯一命中",
        wants=(
            _off(
                "TestResolveApplyLandedGate::"
                "test_the_two_verdicts_are_separate_types_and_carry_the_inner_cause"
            ),
            _pg(
                "TestWhoMaySubmitAdjudications::"
                "test_project_invisibility_is_a_separate_refusal"
            ),
        ),
    ),
]

#: 覆盖面分母：本任务新增/改动的守卫文件。
GUARD_FILES = {
    f"{OFF}.py": "Task 27 新建（纯判据 / 封闭映射 / 结构形态 / 欠账退役双向锁）",
    f"{PG}.py": "Task 27 新建（真库：预览、fence 五判定、retry、rollback）",
    f"{T26}.py": "Task 27 改动（裁决闸门 → 接线，判据翻转）",
    f"{T26PG}.py": "Task 27 改动（真库 S19：拒绝 → 折叠后发布）",
    f"{T15}.py": "Task 27 改动（唯一 commit 边界的独立重算）",
}

PYTEST_ARGS = [
    f"backend/tests/workpaper_sync/{OFF}.py",
    f"backend/tests/workpaper_sync/{PG}.py",
    f"backend/tests/workpaper_sync/{T26}.py",
    f"backend/tests/workpaper_sync/{T26PG}.py",
    f"backend/tests/workpaper_sync/{T15}.py",
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
            description="Task 27 冲突预览 / resolve fence / retry / rollback 守卫变异检验",
            # 冻结基线来源：2026-08-27 Task 27 收口实测（补齐六条 GREEN 的覆盖之后）。
            # 五文件合并跑（`py -3 -m pytest <五文件> -q -p no:randomly`）得 `405 passed`。
            # 首轮全量变异时是 398 —— 差 7 条正是为了让 C02/D04/E01/E02/F02/F05 六条
            # 由 GREEN 翻 RED 而补的场景与形态判据（+1 条 E04 元判据）。
            #
            # 2026-08-28 收口复核**实测重取** `428 passed`。逐文件单跑相加同为 428：
            #   test_task27_conflict_resolution.py     59（48 + 11 H 块落地自证，
            #                                          含 parametrize 展开）
            #   test_task27_conflict_resolution_pg.py  56（44 + 5 duplicate + 6 AC 8.4
            #                                          + 1 载体字节确定性）
            #   test_task26_oo_to_html.py             133
            #   test_task26_oo_to_html_pg.py           99
            #   test_task15_content_mutation.py        81
            # 两批新增判据各自对应一处**真实缺陷**：
            #   * G01/G02 —— canonicalize 之后回头用 requested id（补场景前不可证伪）;
            #   * H01~H05 —— `resolve` 不看 `outcome.result` ⇒ 授权失效时轨迹照写、回 200。
            # 另 +1 条守「载体替身的 zip 不带现场时钟」：不固定时间戳时 R02 只在「两次
            # materialize 恰好同秒」时打红（实测同一份代码快跑 RED、慢跑 GREEN）。
            # 改这个数必须同时说明来源与核对口径。
            baseline_passed=428,
        )
    )
