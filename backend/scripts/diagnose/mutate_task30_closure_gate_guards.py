# -*- coding: utf-8 -*-
"""Task 30 关门守卫的变异检验（跨行锚点 + sha256 还原自证）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 2 Task 30

═══ 覆盖面声明（诚实边界）═══

Task 30 正文点名的变异分两类：

* **本门自己的判据能捕获的** —— 逐条在这里，预测的红都落在
  `test_task30_closure_gate.py` / `test_task30_closure_gate_pg.py`；
* **归属 Task 21/22/24 判据的** —— 本脚本仍然跑它们（把那三个守卫文件纳入选择集），
  但预测的红明确落在那些文件里。这不是借用别人的绿：变异注入的是**生产代码**，
  哪个守卫先红是事实而不是声明。

正文点名而**本轮未覆盖**的（cache-before-auth、numeric revision 作 route key、
merged≠incoming 仍放行、route participant 当唯一作者、直接发布 candidate、
跳过 transition event、允许 null close initiator）落在 Task 25~28 的 router/coordinator
判据面上，本门的集成半没有复现那些入口，故**不在**本脚本的清单里 —— 见
`evidence/task30-closure-gate/README.md` 的覆盖矩阵，那里逐条写明由谁验。

用法（仓库根，前台分批跑；`--run all` 约 25 分钟，被 kill 会留下变异态）::

    py -3 backend/scripts/diagnose/mutate_task30_closure_gate_guards.py --list
    py -3 backend/scripts/diagnose/mutate_task30_closure_gate_guards.py --check-anchors
    py -3 backend/scripts/diagnose/mutate_task30_closure_gate_guards.py --run M01,M02,M03
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO / "backend" / "scripts") not in sys.path:  # pragma: no cover - 自举
    sys.path.insert(0, str(_REPO / "backend" / "scripts"))

from _mutation_kit.span import SpanMutation, run_cli  # noqa: E402

T30 = "test_task30_closure_gate.py"
T30PG = "test_task30_closure_gate_pg.py"
T21 = "test_task21_room_service.py"
T22 = "test_task22_callback_claim.py"
T24 = "test_task24_close_intent.py"

MODELS = "backend/app/services/workpaper_sync/models.py"
REPO = "backend/app/services/workpaper_sync/repository.py"
DELIVERY = "backend/app/services/workpaper_sync/callback_delivery.py"
ROOMS = "backend/app/services/workpaper_sync/rooms.py"
GATE = "backend/scripts/check/check_workpaper_writer_revision_gate.py"
MATRIX = "backend/data/workpaper_resolver_migration_matrix.json"
TASKS_MD = (
    ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/tasks.md"
)

MUTATIONS: list[SpanMutation] = [
    # ═══ A. shell / correlation / duplicate 收敛 ═══════════════════════════
    SpanMutation(
        id="M01",
        path=MODELS,
        anchor=(
            "    if application_id is not None:\n"
            "        return OperationShape.primary\n"
            "    return OperationShape.pre_correlation"
        ),
        new="    return OperationShape.primary",
        want=(
            f"{T30PG}::test_accepted_creates_a_shell_with_both_links_null_and_zero_applications"
        ),
        wants=(f"{T30PG}::test_no_phase_crashed_during_collection",),
        why="漏 normal shell：把「两个 link 都空」的形态直接报成 primary。accepted 之后本该有一个"
            "两 link 皆空的 pre-correlation shell，形态判定塌掉后 correlation 入口会拒绝它"
            "（只接 pre-correlation），于是 durable 回调无处可挂。",
    ),
    SpanMutation(
        id="M02", path=REPO,
        anchor="            op.duplicate_of_operation_id = primary.id\n            op.state = OperationState.duplicate.value",
        new="            op.state = OperationState.duplicate.value",
        want=f"{T30PG}::test_the_race_yields_one_primary_and_n_minus_one_direct_terminal_duplicates",
        wants=(f"{T30PG}::test_the_race_leaves_no_stranded_chained_or_cyclic_shell",),
        why="删除 duplicate pointer：loser 只落 terminal state 而不指向 primary ⇒ 变成 stranded "
            "shell（state=duplicate 但无指针），用户侧的 requested operation 再也 canonicalize "
            "不到 primary。",
    ),
    SpanMutation(
        id="M03", path=REPO,
        anchor="            op.duplicate_of_operation_id = primary.id\n            op.state = OperationState.duplicate.value",
        new="            op.duplicate_of_operation_id = op.id\n            op.state = OperationState.duplicate.value",
        want=f"{T30PG}::test_the_race_leaves_no_stranded_chained_or_cyclic_shell",
        wants=(f"{T30PG}::test_the_race_yields_one_primary_and_n_minus_one_direct_terminal_duplicates",),
        why="环化 duplicate pointer：指向自己。canonicalize 会自环，前端「requested → canonical」"
            "跳转永远回到自己。",
    ),
    SpanMutation(
        id="M04", path=REPO,
        anchor="            op.duplicate_of_operation_id = primary.id\n            op.state = OperationState.duplicate.value",
        new="            op.application_id = app.id\n            op.duplicate_of_operation_id = primary.id\n            op.state = OperationState.duplicate.value",
        want=f"{T30PG}::test_the_race_yields_one_primary_and_n_minus_one_direct_terminal_duplicates",
        wants=(f"{T30PG}::test_no_phase_crashed_during_collection",),
        why="duplicate 再绑 application：primary/duplicate 不再互斥，于是「恰一个 primary」失效，"
            "同一 application 会有 N 个自称 primary 的 operation。",
    ),
    # ═══ B. same-application sequence fold ════════════════════════════════
    SpanMutation(
        id="M05", path=MODELS,
        anchor='        raise IdentityError(f"request sequence 必须 >= 1，实得 existing={existing} incoming={incoming}")\n    return max(existing, incoming)',
        new='        raise IdentityError(f"request sequence 必须 >= 1，实得 existing={existing} incoming={incoming}")\n    return existing',
        want=f"{T30PG}::test_the_fold_path_actually_executed",
        wants=(f"{T30PG}::test_fold_keeps_origin_immutable_and_never_self_supersedes",),
        why="fold 恒不推进：同 application 命中更高 sequence 时 effective 不动 ⇒ room 的 durable "
            "fence 永远指向旧 request，后到的更新会被判 stale。",
    ),
    SpanMutation(
        id="M06", path=REPO,
        anchor='            if app.superseded_by_application_id == app.id:\n                raise DuplicateLinkError("同 canonical application 不得 self-supersede")',
        new="            app.superseded_by_application_id = app.id",
        want=f"{T30PG}::test_fold_keeps_origin_immutable_and_never_self_supersedes",
        why="same-app raw sequence 自我 supersede：把「禁止自我 supersede」改成「就这么干」。"
            "自我 supersede 后 canonical application 自称已作废，resolve 会把 primary 显示成 stale。",
    ),
    SpanMutation(
        id="M07", path=REPO,
        anchor="                app.effective_request_sequence = folded\n                await self._flush()",
        new="                app.effective_request_sequence = folded\n                app.origin_request_sequence = folded\n                await self._flush()",
        want=f"{T30PG}::test_fold_keeps_origin_immutable_and_never_self_supersedes",
        wants=(f"{T30PG}::test_no_phase_crashed_during_collection",),
        why="origin 可变：`origin_request_sequence` 本是 immutable 的 application 身份，"
            "跟着 fold 一起动之后「这个 application 由哪个 request 发起」不可追。",
    ),
    # ═══ C. frozen identity / 幂等 ════════════════════════════════════════
    SpanMutation(
        id="M08", path=MODELS,
        anchor='        _require_digest("incoming_sha256", incoming_sha256),\n        _require_digest("definition_bundle_sha256", definition_bundle_sha256),',
        new='        _require_digest("definition_bundle_sha256", definition_bundle_sha256),',
        want=f"{T30PG}::test_application_key_is_the_frozen_identity_digest",
        why="application key 丢掉 incoming digest ⇒ 两次内容不同的 durable incoming 撞同一 key，"
            "第二次被当成重放丢弃。判据侧的期望 key 由测试自己 sha256 重算，故不会随生产函数"
            "一起变（否则这条变异会自证成 GREEN）。",
    ),
    SpanMutation(
        id="M09", path=MODELS,
        anchor='        str(client_edit_epoch),\n        str(write_fence_epoch),',
        new='        str(write_fence_epoch),',
        want=f"{T30PG}::test_reusing_one_idempotency_key_conflicts_without_leaking_prior_ids[payload_differs]",
        why="fingerprint 丢掉 client edit epoch ⇒ 同 Idempotency-Key 但 payload 不同的请求变成"
            "cache hit，用户第二次编辑被静默当成第一次的重放。",
    ),
    SpanMutation(
        id="M10", path=MODELS,
        anchor='        _require_digest("contributor_snapshot_digest", contributor_snapshot_digest),\n        str(client_edit_epoch),',
        new='        str(client_edit_epoch),',
        want=f"{T30PG}::test_reusing_one_idempotency_key_conflicts_without_leaking_prior_ids[contributors_differ]",
        why="fingerprint 丢掉 contributor 快照 ⇒ 换了协作者集合仍算等值重放，聚合内容作者归属错。",
    ),
    SpanMutation(
        id="M11", path=REPO,
        anchor='                raise IdempotencyConflictError(\n                    "Idempotency-Key 被另一个 participant 或另一种 kind 复用 —— "',
        new='                raise IdempotencyConflictError(\n                    f"prior={prior.id} operation 已存在 —— "',
        want=f"{T30PG}::test_reusing_one_idempotency_key_conflicts_without_leaking_prior_ids[cross_participant]",
        why="跨 participant 冲突时把旧 request id 写进错误文案 ⇒ 别人的 operation 标识泄露给"
            "第二个 participant，AC 4.1「不得返回旧标识」被违反。",
    ),
    # ═══ D. delivery owner / quarantine ══════════════════════════════════
    SpanMutation(
        id="M12", path=DELIVERY,
        anchor="    probe = (\n        st,\n        bool(durable_at_is_set),",
        new="    probe = (\n        st,\n        st in (DeliveryState.durable, DeliveryState.acknowledged, DeliveryState.unmatched),",
        want=f"{T30}::test_delivery_ownership_is_decided_by_durable_at_not_by_terminal_state",
        why="把 delivery gate 改回按 terminal state 判 owner：`durable_at` 未置但 state 已是 "
            "`durable` 的那一行（pre-durable 失败）会被当成合法 owner ⇒ 文件还没耐久就宣布"
            "内容已归属某个 application。",
    ),
    SpanMutation(
        id="M13", path=DELIVERY,
        anchor='QUARANTINE_ALLOWED_OPERATIONS: Final[frozenset[str]] = frozenset(\n    {"download_only", "expire", "retention"}',
        new='QUARANTINE_ALLOWED_OPERATIONS: Final[frozenset[str]] = frozenset(\n    {"download_only", "expire", "retention", "application"}',
        want=f"{T30}::test_the_quarantine_boundary_itself_is_verified_not_deferred",
        wants=(f"{T30PG}::test_quarantined_incoming_is_refused_at_the_application_entry",),
        why="quarantined 进 application：AC 5.6 明文禁止。放开后被隔离的可疑 OOXML 会成为一次"
            "业务内容应用的 substrate。",
    ),
    SpanMutation(
        id="M14", path=DELIVERY,
        anchor='QUARANTINE_ALLOWED_OPERATIONS: Final[frozenset[str]] = frozenset(\n    {"download_only", "expire", "retention"}',
        new='QUARANTINE_ALLOWED_OPERATIONS: Final[frozenset[str]] = frozenset(\n    {"download_only", "expire", "retention", "release"}',
        want=f"{T30}::test_the_quarantine_boundary_itself_is_verified_not_deferred",
        why="quarantined release：允许解除隔离 ⇒ 隔离变成可撤销的建议，AC 5.6 的「永不」失效。",
    ),
    SpanMutation(
        id="M15", path=REPO,
        anchor='        if art.state == ArtifactState.quarantined.value:\n            raise QuarantinedIncomingError(',
        new='        if False:\n            raise QuarantinedIncomingError(',
        want=f"{T30PG}::test_quarantined_incoming_is_refused_at_the_application_entry",
        why="库层那道 quarantine 门短路：`state != durable` 那条兜底仍会拒，但错误类型漂成"
            "`IncomingNotDurableError` ⇒ 「隔离永不解除」这条判据本身不可达（本 spec 已为"
            "「两分支共享异常类型」形态付过代价，此处正是它的反面验证）。",
    ),
    # ═══ E. close exactly-one ════════════════════════════════════════════
    SpanMutation(
        id="M16", path="backend/app/services/workpaper_sync/close_intent.py",
        anchor="    return (int(intent.intent_sequence), str(intent.intent_id))",
        new="    return (0, str(intent.intent_id))",
        want=f"{T24}::test_leader_is_highest_sequence_even_when_it_is_neither_first_nor_last_inserted",
        wants=(f"{T24}::test_equal_sequence_falls_back_to_highest_id",),
        why="close comparator 丢掉 sequence（等价于按插入/时间序）：AC 4.10 要求按最高 "
            "`(intent_sequence, id)` 选 leader；退化成只看 id 后，双跑账会在 tiebreak 上分叉。",
    ),
    SpanMutation(
        id="M17", path=REPO,
        anchor="            if p.revoked_at is not None:\n                return False",
        new="            if False:\n                return False",
        want=f"{T30PG}::test_leader_revoked_before_promotion_yields_a_legitimate_successor",
        why="撤权不再使 leader 失格 ⇒ 已被撤权的用户仍能被提升为 close leader 并发出 forcesave，"
            "`authorization_stale` 审计一条都不写。",
    ),
    SpanMutation(
        id="M18", path=REPO,
        anchor="            if ParticipantState(p.state) is not ParticipantState.closing:\n                return False",
        new="            if False:\n                return False",
        want=f"{T30PG}::test_a_non_closing_participant_is_not_a_leader_candidate",
        wants=(f"{T30PG}::test_no_phase_crashed_during_collection",),
        why="closing 仍计 active：不再要求 participant 处于 `closing` ⇒ 一个又回到 `active` 的"
            "编辑者的 intent 也算合格候选，close barrier 的语义塌掉。"
            "对应场景（`not_closing`）**只**触发这一条失格判据（未撤权、未过期），"
            "否则三条判据共享结果时删任一条都抓不到（M17 首轮实测 GREEN 正是这个形态）。",
    ),
    SpanMutation(
        id="M30", path=REPO,
        anchor="            if p.expires_at is not None and p.expires_at <= _now():\n                return False",
        new="            if False:\n                return False",
        want=f"{T30PG}::test_no_successor_lands_recovery_required_with_zero_capture",
        wants=(f"{T30PG}::test_no_phase_crashed_during_collection",),
        why="lease 过期不再使候选失格 —— 三条失格判据的第三条。对应场景（`no_successor`）"
            "只把 `expires_at` 拨到过去，不动 state、不置 revoked_at。",
    ),
    SpanMutation(
        id="M19", path=REPO,
        anchor="        if already_promoted is not None:\n            # 已 promotion：授权失效只能由最终 fence 走 recovery，绝不再选 successor",
        new="        if False:\n            # 已 promotion：授权失效只能由最终 fence 走 recovery，绝不再选 successor",
        want=f"{T30PG}::test_reconciler_is_reentrant_and_keeps_the_same_leader[order_ab]",
        wants=(
            f"{T30PG}::test_reconciler_is_reentrant_and_keeps_the_same_leader[single]",
            f"{T30PG}::test_reconciler_is_reentrant_and_keeps_the_same_leader[order_ba]",
            f"{T30PG}::test_close_yields_exactly_one_capture[order_ab]",
            f"{T30PG}::test_no_phase_crashed_during_collection",
        ),
        why="reconciler 不再幂等：已 promoted 时不短路 ⇒ 重入会再选一次 leader / 再建一条 capture，"
            "「最终 exactly-one」变成「每次调用一条」。",
    ),
    SpanMutation(
        id="M20", path=REPO,
        anchor="            intent.state = CloseIntentState.recovery_required.value",
        new="            intent.state = CloseIntentState.superseded.value",
        want=f"{T30PG}::test_no_successor_lands_recovery_required_with_zero_capture",
        wants=(f"{T30PG}::test_no_phase_crashed_during_collection",),
        why="无 successor 的显式终态缺失：改成 `superseded` 后前端看不到 `close_recovery_required`，"
            "只会看到「已作废」⇒ 用户的关闭动作既没保存也没告知需要恢复。",
    ),
    # ═══ F. scope tombstone ══════════════════════════════════════════════
    SpanMutation(
        id="M21", path=REPO,
        anchor="        if row.retired_at is None:\n            row.retired_at = _now()",
        new="        if False:\n            row.retired_at = _now()",
        want=f"{T30PG}::test_retiring_a_scope_row_keeps_the_tombstone_physically",
        why="退役不再落 `retired_at` ⇒ tombstone 与活行无法区分，已退役资源的访问不会走统一 404。",
    ),
    SpanMutation(
        id="M22", path=REPO,
        anchor="        if existing is not None:\n            same_scope = (",
        new="        if False:\n            same_scope = (",
        want=f"{T30PG}::test_a_retired_resource_id_cannot_be_reused",
        why="域层不再拒绝 id 复用。库层唯一索引仍会拒，所以只断言「被拒」的判据会 GREEN ——"
            "本门因此额外要求拒绝类型必须是域异常（`is_domain_refusal`），这条变异正是它的验证。",
    ),
    # ═══ G. incoming 不得背书 representation ═════════════════════════════
    SpanMutation(
        id="M23", path=REPO,
        anchor=(
            '        """finalize 一个 immutable representation generation（强制 approved 非空 bundle）。"""\n'
            "        bundle = await self.assert_bundle_usable(definition_bundle_id)\n"
            "        if bundle.authority_model_definition_id != authority_model_definition_id:"
        ),
        new=(
            '        """finalize 一个 immutable representation generation（强制 approved 非空 bundle）。"""\n'
            "        bundle = (\n"
            "            await self._session.execute(\n"
            "                sa.select(WorkpaperSyncDefinitionBundle).where(\n"
            "                    WorkpaperSyncDefinitionBundle.id == definition_bundle_id\n"
            "                )\n"
            "            )\n"
            "        ).scalar_one()\n"
            "        if bundle.authority_model_definition_id != authority_model_definition_id:"
        ),
        want=f"{T30}::test_the_unified_resolver_really_requires_a_published_approved_substrate",
        why="published representation 不再要求 approved 非空 bundle：换成裸 select 直接取行（语法"
            "有效、运行时照常拿到 bundle 对象），只是 approved/typed-slot 校验没了。"
            "「统一 resolver 只接受 published representation + approved bundle」这条前提正是 "
            "Task 30 那 4 条 resolver 行迁不了零的依据 —— 前提一旦被放宽，deferral 理由必须重评。",
    ),
    # ═══ H. 门本身仍在评估被移交的 criterion ══════════════════════════════
    SpanMutation(
        id="M24", path=GATE,
        anchor='        if verdicts.get("multi_resolver"):\n            issues["multi_resolver"].append(writer_id)',
        new='        if False:\n            issues["multi_resolver"].append(writer_id)',
        want=f"{T30}::test_the_gate_still_counts_the_criterion_its_owner_verifies_zero_with",
        wants=(
            f"{T30}::test_recomputation_and_the_gate_agree_on_the_multi_resolver_rows",
            f"{T30}::test_owner_named_rows_match_the_gate_report",
        ),
        why="把已移交出去的 criterion 短路成 `if False`：key 还在、计数恒为零，报告与"
            "「已清零」逐字相同。这是本 spec 反复付过代价的 fail-open 形态，必须由行为级判据"
            "（真喂一条多 resolver 行）而不是「键是否存在」抓到。裁决归属两跳"
            "（Task 20 → 30 → 71）都不改变这一点 —— 归属换人，计算不能离场。",
    ),
    SpanMutation(
        id="M25", path=MATRIX,
        anchor='"blocking_task": "21,25,26,36"',
        new='"blocking_task": "998,999"',
        want=f"{T30}::test_the_registered_blocker_points_at_a_task_that_really_gates_publication",
        why="把阻塞登记指向不存在的任务号。没有这条判据时，`blocking_task` 可以是任意数字、"
            "`reason` 可以是任意散文，「为什么这 4 行迁不了」下一轮又要从头查。",
        allow_multi=True,
        multi_reason="矩阵里 8 条 oo_room 行共享同一模块级裁决，8 处必须一起改才是同一条判据",
    ),
    # ═══ H2. 裁决归属（Task 20 → 30 → 71）的两个新判据 ═════════════════════
    SpanMutation(
        id="M31", path=MATRIX,
        anchor='"adjudication_owner_task": "71"',
        new='"adjudication_owner_task": "30"',
        want=f"{T30}::test_the_criterion_is_either_cleared_or_its_blocker_is_registered",
        why="把矩阵登记的**裁决归属**改回上一跳（Task 30），而 tasks.md 已把它交给 Task 71。"
            "没有这条变异，`adjudication_owner_task` 就是一个无人消费的新字段（本 spec 的假绿"
            "第①源：additive 注入即死代码）—— 加了字段、守卫全绿、doc 与登记可以各说各话。"
            "判据必须把 doc 派生的归属与矩阵登记双向锁死。",
        allow_multi=True,
        multi_reason="8 条 oo_room 行共享同一模块级裁决，归属是模块级的一件事，8 处同改",
    ),
    SpanMutation(
        id="M32", path=TASKS_MD,
        anchor='    "bulk_adapters": ["20", "30", "44"],',
        new='    "bulk_adapters": ["20", "30", "44", "71"],',
        want=f"{T30}::test_relocating_the_criterion_did_not_invert_the_wave_order",
        why="把 criterion 的归属方（Wave 7 的 Task 71）挂进 `bulk_adapters` gate —— 这正是"
            "「把 Task 30 原文那句『bulk_adapters gate 亦不得放行 bulk adapter 迁移』原样搬到"
            "Task 71」的结构后果：Wave 5 的 bulk adapter 迁移会依赖 Wave 7，与它要修的那个环"
            "同形。移交方向的安全性必须是按依赖图算出来的事实，而不是散文里那句「方向不成环」。",
    ),
    # ═══ I. 两条被修好的守卫（Task 21 / Task 22）══════════════════════════
    SpanMutation(
        id="M26", path=ROOMS,
        anchor="logger = logging.getLogger(__name__)",
        new="logger = logging.getLogger(__name__)\n\nFORCESAVE_CALLBACK_WAIT_TIMEOUT_SECONDS = 120",
        want=f"{T21}::TestCallbackContractHasProductionConsumer::test_contract_numbers_have_single_source_in_oo_contract",
        why="真正的「另写常量」：把契约里的 120 秒抄成模块常量。原判据（剥字符串后扫子串）"
            "**抓不到**它（子串不在、数值不在名单里），只会去打红正确的属性读取。修好后的"
            "判据必须在这里红。",
    ),
    SpanMutation(
        id="M27", path=ROOMS,
        anchor="logger = logging.getLogger(__name__)",
        new='logger = logging.getLogger(__name__)\n\n\ndef _reparse_timeout(raw: dict) -> int:\n    return int(raw["timers"]["forcesave_callback_wait_timeout_seconds"])',
        want=f"{T21}::TestCallbackContractHasProductionConsumer::test_contract_numbers_have_single_source_in_oo_contract",
        why="真正的「另写解析」：绕过 `oo_contract` 的 loader，自己按字符串键从 JSON 取值 ⇒"
            "契约换版时这一处不会跟着走。原判据同样抓不到（字符串被剥掉了）。",
    ),
    SpanMutation(
        id="M28", path=DELIVERY,
        anchor="logger = logging.getLogger(__name__)",
        new='logger = logging.getLogger(__name__)\n\n\ndef _peek_callback_claims(token: str, secret: str) -> dict:\n    from jose import jwt as _jwt\n\n    return _jwt.decode(token, secret, algorithms=["HS256"])',
        want=f"{T22}::test_jwt_decoding_lives_only_in_callback_route",
        why="在 delivery 里新增第二处 callback token 解码 —— Task 22 要求校验只有一处实现。"
            "改成 AST 判据后这条必须红；原判据（扫 `^from jose`）在本文件已经因为 Task 24 的"
            "签发而恒红，新缺陷混不出来。",
    ),
    SpanMutation(
        id="M29", path=ROOMS,
        anchor="logger = logging.getLogger(__name__)",
        new="logger = logging.getLogger(__name__)\n\nTASK30_MUTATION_CONTROL_PROBE = 7",
        want="*",
        expect_green=True,
        why="对照项（预期 GREEN）：往同一个文件加一个与契约数值无关的模块常量。它证明 M26/M27 "
            "的判据不是「这个文件一改就红」，而是真的在看「绑的是不是契约数量」。",
    ),
]

GUARD_FILES = {
    "test_task30_closure_gate.py": "Task 30 关门离线判据（multi_resolver / 阻塞前提 / 登记债）",
    "test_task30_closure_gate_pg.py": "Task 30 关门集成判据（durable/application/close/recovery）",
    "test_task21_room_service.py": "Task 21 契约数值单一真源（本门修好了它的判据形态）",
    "test_task22_callback_claim.py": "Task 22 token 解码单一实现（本门修好了它的判据形态）",
    "test_task24_close_intent.py": "Task 24 close leader comparator / eligibility 分支",
}

PYTEST_ARGS = [
    "backend/tests/workpaper_sync/test_task30_closure_gate.py",
    "backend/tests/workpaper_sync/test_task30_closure_gate_pg.py",
    "backend/tests/workpaper_sync/test_task21_room_service.py",
    "backend/tests/workpaper_sync/test_task22_callback_claim.py",
    "backend/tests/workpaper_sync/test_task24_close_intent.py",
    "-q",
    "--no-header",
    "-p",
    "no:cacheprovider",
    "-p",
    "no:randomly",
]


if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=_REPO,
            pytest_args=PYTEST_ARGS,
            description="Task 30 关门守卫变异检验",
            # 冻结基线来源（改基线必须写来源）：2026-08-28 首轮 322 → 关门期间新增判据后 324。
            # 2026-08-29 `multi_resolver` 裁决归属移交 Task 71 时实测 **324**：本轮新增 1 条
            # （`test_relocating_the_criterion_did_not_invert_the_wave_order`，离线文件 9 → 10），
            # 而 task21/22/24 侧被并发会话减少 1 条（逐文件实测 10 + 39 + 97 + 90 + 88 = 324），
            # 两者恰好相抵。故数字与上一轮相同**不是**没变，逐文件计数才是判据。
            baseline_passed=324,
        )
    )
