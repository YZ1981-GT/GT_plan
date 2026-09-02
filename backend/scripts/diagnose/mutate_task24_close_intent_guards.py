# -*- coding: utf-8 -*-
"""Task 24 变异检验：Command Service 出站、destroy 闸与 close-leader exactly-one 守卫。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 2 Task 24
Requirements: 4.1, 4.4, 4.7, 4.10, 5.5, 10.10
Properties: P12 / P13 / P15 / P43 / P64

用法（仓库根目录）::

    py -3 backend/scripts/diagnose/mutate_task24_close_intent_guards.py --list
    py -3 backend/scripts/diagnose/mutate_task24_close_intent_guards.py --check-anchors
    py -3 backend/scripts/diagnose/mutate_task24_close_intent_guards.py --run all --out report.json

═══ 六类落点 ═══

1. **纯仲裁**（`close_intent` 的 comparator / eligibility / prediction）——
   `created_at`、min、丢 id tiebreak、失格四条子判据、promoted 短路各一条。
2. **双记账比对**（`assert_leader_matches_prediction` 三项）—— 真库 happy path 走不到，
   判据只能是合成输入；变异逐条短路。
3. **仓储侧仲裁**（Task 24 正文点名的四条必红）—— comparator 改回 `created_at`、
   同 eligibility snapshot 换 leader、漏 `authorization_stale`、有 successor 仍 blocked。
   这批锚点落在 `repository.py`（Task 10 的实现），本脚本**不改动那些行**，只在
   变异期临时替换。
4. **出站顺序与分类**（`command_service`）—— 凭据自证、target 归属、null initiator、
   HTTP 200 语义、未知返回码、JWT fail-closed、超时取自契约。
5. **destroy 闸**（Property 13 / AC 4.4）—— 可重试先于 FSM terminal、超时保持 OO、
   崩溃恢复的合取条件。
6. **回归类**（`tags=("regression",)`）—— 把本任务开发过程中**实际修掉**的每个缺陷
   重新注入，证明修复不是一次性的：
   * R01 comparator 丢 id tiebreak（真库不可达，只能离线证）；
   * R02 promoted 短路挪到失格判定之后（post-promotion 改选 leader）；
   * R03 predecessor 转换不写 append-only 事件（当时按当前 state 断言，掩盖了它）；
   * R04 两条拒绝共用继承关系（本 spec 已付三次代价的形态）；
   * R05 `OPEN_CAPTURE_STATES` 变成第三份手抄常量。

═══ 刻意避开的无效变异形态 ═══

* 改注释/docstring —— 不在判据作用域内；
* 绝对 `line=` 定位 —— 行号随上游补类/补注释漂移（Task 22 M02 实测 ANCHOR-MISS）；
  唯一需要消歧的 `no_successor=False,`（两处）用 `scope`+`offset`。
* 短路 `assert_timer_single_source` / `_assert_at_most_one_open_capture` 的**内嵌**形态
  —— 正确实现下它们恒不触发，单独短路必判 GREEN。这就是为什么本任务把
  `assert_at_most_one_open_capture` / `assert_no_live_intent_remains` /
  `assert_frozen_identity_complete` 抽成模块级纯函数并用合成输入喂：抽出来之后
  M18/M19/M20 才是可证伪的。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts
from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

CI = "backend/app/services/workpaper_sync/close_intent.py"
CMD = "backend/app/services/workpaper_sync/command_service.py"
REPOSITORY = "backend/app/services/workpaper_sync/repository.py"
CONTRACT = "backend/data/onlyoffice_callback_state_contract.json"

OFF = "test_task24_close_intent"
PG = "test_task24_close_intent_pg"

MUTATIONS: list[Mutation] = [
    # ═══════════════════════════════════════════════════════════════════
    # 一、纯仲裁：最高 (intent_sequence, id)
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M01", side="be", path=CI, kind="replace",
        anchor="    return max(intents, key=close_leader_sort_key)",
        new="    return min(intents, key=close_leader_sort_key)",
        want=f"{OFF}.py::test_leader_is_highest_sequence_even_when_it_is_neither_first_nor_last_inserted",
        why="取最小而非最大 ⇒ leader 与 AC 4.10「最高 (intent_sequence,id)」相反。"
            "离线判据用的是**判别性**输入（最高 sequence 既非首插入、非末插入、"
            "且 id 最小），所以 min 必然选到另一条；同时服务层双记账会与仓储分叉，"
            "真库场景一并打红",
        wants=(
            f"{OFF}.py::test_leader_is_invariant_under_input_order_permutations",
            f"{PG}.py::test_no_phase_crashed_during_collection",
        ),
    ),
    Mutation(
        id="M02", side="be", path=CI, kind="replace",
        anchor="    return (int(intent.intent_sequence), str(intent.intent_id))",
        new="    return (str(intent.intent_id),)",
        want=f"{OFF}.py::test_leader_is_highest_sequence_even_when_it_is_neither_first_nor_last_inserted",
        why="排序键丢掉 sequence、只按 id ⇒ 与「按插入序」「按 sequence」全部脱钩。"
            "判别性输入里最高 sequence 那条的 id 是**最小**的，所以这条必然选错",
        tags=("regression",),
    ),
    Mutation(
        id="M03", side="be", path=CI, kind="replace",
        anchor="    return (int(intent.intent_sequence), str(intent.intent_id))",
        new="    return (int(intent.intent_sequence),)",
        want=f"{OFF}.py::test_equal_sequence_falls_back_to_highest_id",
        why="R01 回归：丢掉 id tiebreak。真库有 "
            "`uq_wpoci_sequence UNIQUE (room,generation,intent_sequence)`，"
            "同 sequence **不可达**，所以这条只能被离线合成输入抓到 —— "
            "它正是「id tiebreak 是防御性确定性」这一结论的判据",
        tags=("regression",),
    ),
    Mutation(
        id="M04", side="be", path=CI, kind="replace",
        anchor="    if p.revoked:",
        new="    if False:",
        want=f"{OFF}.py::test_eligibility_has_one_independent_branch_per_disqualifier[revoked]",
        why="被撤销的 participant 仍算合格 ⇒ 撤权用户可以当 leader 并提交其内容"
            "（AC 4.10 / 10.10）。四条失格判据必须逐条变异：合成一条 `all([...])` 时"
            "删掉任一条都会被其余遮蔽",
        wants=(f"{PG}.py::test_leader_disqualified_before_promotion_yields_a_legitimate_successor[revoked]",),
    ),
    Mutation(
        id="M05", side="be", path=CI, kind="replace",
        anchor="    if p.expired:",
        new="    if False:",
        want=f"{OFF}.py::test_eligibility_has_one_independent_branch_per_disqualifier[expired]",
        why="lease 已过期仍算合格 ⇒ 过期会话可当 leader。与 M04 分开：两者共用一条"
            "判据时，删掉任一个都会被另一个遮蔽",
        wants=(f"{PG}.py::test_leader_disqualified_before_promotion_yields_a_legitimate_successor[expired]",),
    ),
    Mutation(
        id="M06", side="be", path=CI, kind="replace",
        anchor="    if p.state is not ParticipantState.closing:",
        new="    if False:",
        want=f"{OFF}.py::test_eligibility_has_one_independent_branch_per_disqualifier[still_active]",
        why="仍 active（或已 left）的 participant 也算合格 ⇒ 没关闭的人被选成 leader，"
            "它的编辑还没结束就被 close-capture 冻结",
        wants=(f"{OFF}.py::test_eligibility_has_one_independent_branch_per_disqualifier[left]",),
    ),
    Mutation(
        id="M07", side="be", path=CI, kind="replace",
        anchor="    return intent.state in CLOSE_INTENT_LIVE_STATES",
        new="    return True",
        want=f"{OFF}.py::test_eligibility_has_one_independent_branch_per_disqualifier[terminal_intent]",
        why="已终结的 intent（含 `authorization_stale`）也算合格 ⇒ 已审计失格的 intent "
            "会被重新选成 successor，`authorization_stale` 形同虚设",
        wants=(f"{OFF}.py::test_eligibility_has_one_independent_branch_per_disqualifier[promoted_intent]",),
    ),
    Mutation(
        id="M08", side="be", path=CI, kind="replace",
        anchor="    promoted = next((i for i in rows if i.state is CloseIntentState.promoted), None)",
        new="    promoted = None",
        want=f"{OFF}.py::test_promoted_short_circuit_precedes_staleness_check",
        why="R02 回归：去掉 promoted 幂等短路 ⇒ 已 promotion 的 leader 失格后会被"
            "重新选 successor，违反 AC 10.10『promotion 后授权失效只能走 recovery，"
            "不得接任再造第二 capture』。真库侧由「promotion 后扰动不换 leader」打红",
        wants=(f"{PG}.py::test_perturbation_after_promotion_never_changes_the_leader",),
        tags=("regression",),
    ),
    Mutation(
        id="M09", side="be", path=CI, kind="replace",
        anchor="            no_successor=False,",
        scope="    if not rows:",
        offset=5,
        new="            no_successor=True,",
        want=f"{OFF}.py::test_no_successor_is_distinct_from_no_intents_at_all",
        why="「一条 intent 都没有」被当成「全部失格」⇒ 还没有人关闭的 room 也会被"
            "supersede 成 recovery_required。两者都返回 leader=None，只断言 leader "
            "为空的判据分不开它们",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 二、双记账比对（三项必须互不遮蔽）
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M10", side="be", path=CI, kind="replace",
        anchor="    if reported_leader_intent_id != prediction.leader_intent_id:",
        new="    if False:",
        want=f"{OFF}.py::test_leader_mismatch_raises_arbitration_error",
        why="服务边界不再比对 leader ⇒ 仓储 comparator 被改动时无人报警。"
            "这条与 M11/M12 一起证明三项比对各自有效",
    ),
    Mutation(
        id="M11", side="be", path=CI, kind="replace",
        anchor="    if bool(reported_no_successor) != bool(prediction.no_successor):",
        new="    if False:",
        want=f"{OFF}.py::test_no_successor_mismatch_raises_accounting_error",
        why="`no_successor` 记账不再比对 ⇒ 「有 successor 却走 supersede」不可见",
    ),
    Mutation(
        id="M12", side="be", path=CI, kind="replace",
        anchor="    if sorted(str(i) for i in reported_stale_intent_ids) != sorted(",
        new="    if False and sorted(str(i) for i in reported_stale_intent_ids) != sorted(",
        want=f"{OFF}.py::test_missing_authorization_stale_raises_accounting_error",
        why="`authorization_stale` 记账不再比对 ⇒ 漏写审计不可见。"
            "🔴 该条与 M10 必须打红**不同**的测试：首轮若把两类分歧合成一个异常类型，"
            "本条会被 M10 的断言遮蔽而判 GREEN（Task 22 M04/M10、Task 23 M25 同形态）",
    ),
    Mutation(
        id="M13", side="be", path=CI, kind="replace",
        anchor="class CloseSuccessorAccountingError(CloseIntentDomainError):",
        new="class CloseSuccessorAccountingError(CloseLeaderArbitrationError):",
        want=f"{OFF}.py::test_close_intent_refusals_are_pairwise_disjoint",
        why="R04 回归：让 accounting 成为 arbitration 的子类 ⇒ "
            "`pytest.raises(CloseLeaderArbitrationError)` 会顺手吃掉 accounting，"
            "「漏写 stale」永久不可分辨。本 spec 已为这个形态付过三次代价",
        tags=("regression",),
    ),
    Mutation(
        id="M14", side="be", path=CI, kind="replace",
        anchor="    RequestState(s) for s in _OPEN_CAPTURE_STATES",
        new='    RequestState(s) for s in ("frozen", "pending")',
        want=f"{OFF}.py::test_open_capture_states_are_locked_to_the_sql_index",
        why="R05 回归：把 open 状态集合改成手抄的第三份常量 ⇒ 与 V151 的 "
            "`uq_wpfr_open_close_capture` WHERE 子句漂移，`accepted/correlated` 状态的"
            "第二条 capture 数不到。此前**没有任何守卫**比较过 SQL 与 Python 两侧",
        tags=("regression",),
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 三、服务编排：predecessor 与 barrier
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M15", side="be", path=CI, kind="replace",
        anchor="        if remaining_active > 0:",
        new="        if False:",
        want=f"{PG}.py::test_first_closer_gets_a_predecessor_and_last_closer_does_not[order_ab__none]",
        why="仍有其他 active editor 时不再为先关闭者建普通 forcesave predecessor ⇒ "
            "该用户此前的编辑没有任何 request 承载（AC 4.10「非 leader closing "
            "participant 只执行普通 forcesave」）",
        wants=(f"{PG}.py::test_no_capture_before_predecessors_are_terminal[order_ab__none]",),
    ),
    Mutation(
        id="M16", side="be", path=CI, kind="replace",
        anchor="        intent.ordinary_forcesave_request_id = accepted.request.id",
        new="        pass  # predecessor link removed",
        want=f"{PG}.py::test_intent_records_its_predecessor_link_and_timeline",
        why="不写 `ordinary_forcesave_request_id` ⇒ intent 与它的 barrier predecessor "
            "之间没有可审计对应关系。该列在 Task 24 之前**没有任何生产代码写过**，"
            "只断言「建了一条 forcesave」的判据抓不到这条",
        wants=(f"{PG}.py::test_first_closer_gets_a_predecessor_and_last_closer_does_not[order_ab__none]",),
    ),
    Mutation(
        id="M17", side="be", path=CI, kind="replace",
        anchor="                to_state=CloseIntentState.ordinary_forcesaving,",
        new="                to_state=CloseIntentState.waiting_barrier,",
        want=f"{PG}.py::test_intent_records_its_predecessor_link_and_timeline",
        why="R03 回归：predecessor 转换不写自己的 append-only 事件（写成别的 to_state）。"
            "首轮按 intent 的**当前 state** 断言 `ordinary_forcesaving` —— 而 reconciler "
            "随后会把它推到 `waiting_barrier`，于是断言本身是错的，也就掩盖了「事件没写对」。"
            "改成断言 timeline 后这条才有判据（current state 只是 timeline 的投影，AC 5.10）",
        tags=("regression",),
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 四、exactly-one 的两个反面 + 冻结身份（纯函数，合成输入）
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M18", side="be", path=CI, kind="replace",
        anchor="    if count > 1:",
        new="    if False:",
        want=f"{OFF}.py::test_more_than_one_open_capture_is_refused[two]",
        why="服务入口不再拒绝 >1 条 open close-capture。"
            "🔴 这条之所以可证伪，是因为该判据被抽成了模块级纯函数：内嵌在服务方法里时"
            "正确实现下 `count` 恒为 0/1，短路它不会有任何测试变红（不可证伪 = 假绿入口）",
        wants=(f"{OFF}.py::test_more_than_one_open_capture_is_refused[five]",),
    ),
    Mutation(
        id="M19", side="be", path=CI, kind="replace",
        anchor="    if live_intents:",
        new="    if False:",
        want=f"{OFF}.py::test_live_intent_after_no_successor_is_refused[one_live]",
        why="no-successor 终结后仍有 live intent 时不再拒 ⇒ 「零 capture 且永久阻塞」"
            "变成可接受态。partial unique 对「一条 capture 都没有」毫无意见，"
            "这是 Task 24 正文「无 successor 仍 blocked 必须打红」的生产判据",
        wants=(f"{OFF}.py::test_live_intent_after_no_successor_is_refused[three_live]",),
    ),
    Mutation(
        id="M20", side="be", path=CI, kind="replace",
        anchor="    if permission_epoch is None:",
        new="    if not permission_epoch:",
        want=f"{OFF}.py::test_zero_permission_epoch_and_zero_fence_are_valid",
        why="把「非空」判据写成真值判断 ⇒ `permission_epoch=0`（合法值）被当成缺失，"
            "刚建 room 的正常 close 一律被拒。五条冻结身份判据里只有这一条能被"
            "「0 vs None」区分，所以它需要自己的边界用例",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 五、仓储侧仲裁（Task 24 正文点名的四条必红）
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M21", side="be", path=REPOSITORY, kind="replace",
        anchor="        leader = max(eligible_intents, key=lambda i: (int(i.intent_sequence), str(i.id)))",
        new="        leader = max(eligible_intents, key=lambda i: (i.created_at, str(i.id)))",
        want=f"{PG}.py::test_created_at_does_not_decide_the_leader[order_ab__created_reversed]",
        why="🔴 Task 24 正文点名第一条：comparator 改回 `created_at`。"
            "判别性来自扰动 —— `created_reversed` 让最先插入的 intent 拿到最晚时间戳，"
            "于是「最高 sequence」与「最晚 created_at」是不同两条。"
            "若不做这个扰动，二者恒为同一条，本变异必判 GREEN",
        wants=(
            f"{PG}.py::test_deterministic_leader_is_neither_first_inserted_nor_latest_created_at",
            f"{PG}.py::test_no_phase_crashed_during_collection",
        ),
    ),
    Mutation(
        id="M22", side="be", path=REPOSITORY, kind="replace",
        anchor="        leader = max(eligible_intents, key=lambda i: (int(i.intent_sequence), str(i.id)))",
        new="        leader = max([i for i in eligible_intents if i.id != room.close_leader_intent_id] or eligible_intents, key=lambda i: (int(i.intent_sequence), str(i.id)))",
        want=f"{PG}.py::test_repeat_reconcile_in_one_eligibility_snapshot_keeps_the_leader[revoked]",
        why="🔴 Task 24 正文点名第二条：同一 eligibility snapshot 内换 leader。"
            "注入「round-robin」形态 —— 选 leader 时把**当前** leader 排除掉（只剩它时"
            "回退到全集，以免退化成崩溃而非选错）。于是第一次 reconcile 选出 L 之后，"
            "同一 snapshot 的第二次 reconcile 必然改选另一条：eligible 集合、"
            "eligibility epoch 与 digest 全都没变，leader 却换了人。"
            "首轮此处写的是「排序键依赖 reconciler 自己写的 `reconciled_at`」，"
            "实测判 GREEN 且**归因为无效变异**：每条 intent 在它自己那次 close 的"
            "reconcile 里就成了当时的最高 sequence ⇒ 都被写上 `reconciled_at`，"
            "注入的键分量在整个 eligible 集合上恒为同值、完全不影响 max()。"
            "唯一它非空的时刻（新 intent 尚未 reconcile）那条恰好也是 sequence 最高的，"
            "两种 comparator 选同一个人 —— 不可证伪",
        wants=(
            f"{PG}.py::test_repeat_reconcile_in_one_eligibility_snapshot_keeps_the_leader[expired]",
            f"{PG}.py::test_no_phase_crashed_during_collection",
        ),
    ),
    Mutation(
        id="M23", side="be", path=REPOSITORY, kind="replace",
        anchor="        if current_leader is not None and not eligible(current_leader):",
        new="        if False:",
        want=f"{PG}.py::test_leader_disqualified_before_promotion_yields_a_legitimate_successor[revoked]",
        why="🔴 Task 24 正文点名第三条：漏写 `authorization_stale`。失格的 leader 不再"
            "被审计、eligibility epoch 不再推进 ⇒ 撤权用户的 intent 仍挂在 room 的"
            "leader 指针上，且没有任何 append-only 记录说明它为何被换掉",
        wants=(
            f"{PG}.py::test_no_successor_records_the_stale_audit_before_superseding",
            f"{PG}.py::test_leader_disqualified_before_promotion_yields_a_legitimate_successor[expired]",
        ),
    ),
    Mutation(
        id="M24", side="be", path=REPOSITORY, kind="replace",
        anchor="        if active_count > 0 or int(predecessors_open) > 0:",
        new="        if True:",
        want=f"{PG}.py::test_capture_scenario_yields_exactly_one_close_capture[order_ab__none]",
        why="🔴 Task 24 正文点名第四条：存在 successor 时仍 blocked。barrier 永不放行 ⇒ "
            "leader 永远停在 `waiting_barrier`，capture 一条都不产生。"
            "partial unique 对此毫无意见（它只防第二条），所以只有行为测试的"
            "「最终恰一条」能抓到",
        wants=(f"{PG}.py::test_capture_scenario_yields_exactly_one_close_capture[single__none]",),
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 六、出站：先落库、再调 OO；HTTP 200 只代表 accepted
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M25", side="be", path=CMD, kind="replace",
        anchor="        accepted.assert_dispatchable()",
        new="        pass  # credential self-check skipped",
        want=f"{OFF}.py::test_precreated_application_is_refused_before_any_network_call",
        why="跳过凭据自证 ⇒ 「库里已有 application」或「shell 已绑定」时照样出站，"
            "AC 4.1「accepted 前不得预建 application」失去执法点。"
            "该断言是「已落库」的唯一凭证，跳过它等于回到「先调 OO 再落库」",
        wants=(f"{OFF}.py::test_bound_shell_is_refused_before_any_network_call",),
    ),
    Mutation(
        id="M26", side="be", path=CMD, kind="replace",
        anchor="        if not isinstance(accepted, AcceptedRequest):",
        new="        if False:",
        want=f"{OFF}.py::test_non_credential_argument_is_refused_before_any_network_call",
        why="不再要求 Task 23 的凭据类型 ⇒ 「没落库就调 Command Service」在类型层重新"
            "可表达（AC 4.1 的顺序判据）",
    ),
    Mutation(
        id="M27", side="be", path=CMD, kind="replace",
        anchor="        if not same_scope:",
        new="        if False:",
        want=f"{OFF}.py::test_target_must_belong_to_the_frozen_request_generation[other_room]",
        why="doc_key 与凭据里 request 的 room/generation 不再校验 ⇒ 用 A 的 request id "
            "配 B 的 doc_key 会强存 B 的文档却记在 A 的 request 上（两个值单看都合法，"
            "DB 层也拦不住）",
        wants=(f"{OFF}.py::test_target_must_belong_to_the_frozen_request_generation[other_generation]",),
    ),
    Mutation(
        id="M28", side="be", path=CMD, kind="replace",
        anchor="        if request.initiated_by_participant_id is None:",
        new="        if False:",
        want=f"{OFF}.py::test_null_initiator_is_refused_before_the_command_service_call",
        why="null initiator 不再在出站前被拒 ⇒ system/route identity 可以冒充用户授权"
            "（AC 10.10 明令禁止）",
    ),
    Mutation(
        id="M29", side="be", path=CMD, kind="replace",
        anchor="        if int(response.status_code) != 200:",
        new="        if False:",
        want=f"{OFF}.py::test_non_200_is_a_transport_failure_not_a_return_code",
        why="非 200 不再归传输层异常 ⇒ 网关/反代返回的 502 会被送进 JSON 解析并按"
            "「返回码」处理，诊断方向完全错（契约实测 OO 9.4 恒返 200）",
    ),
    Mutation(
        id="M30", side="be", path=CMD, kind="replace",
        anchor='        if "error" not in parsed:',
        new="        if False:",
        want=f"{OFF}.py::test_unreadable_or_unknown_return_code_fails_visible[missing_error_key]",
        why="body 缺 `error` 不再拒 ⇒ 变成 `rule_for(None)`，抛的是「未知返回码」而不是"
            "「读不出 error」。两种未知的诊断动作不同（查网关 vs 补契约行），"
            "所以它们必须分型",
    ),
    Mutation(
        id="M31", side="be", path=CMD, kind="replace",
        anchor="        if isinstance(error, bool) or not isinstance(error, int):",
        new="        if not isinstance(error, int):",
        want=f"{OFF}.py::test_unreadable_or_unknown_return_code_fails_visible[error_is_bool]",
        why="`bool` 不再被拒 ⇒ `{'error': true}` 因 `True == 1` 被读成 error 1，"
            "「doc 不在线」的语义凭空出现。契约禁止按最近似码猜处理",
    ),
    Mutation(
        id="M32", side="be", path=CMD, kind="replace",
        anchor='    if not str(secret or "").strip():',
        new="    if False:",
        want=f"{OFF}.py::test_missing_jwt_secret_fails_closed_instead_of_signing_nothing",
        why="无 secret 时不再拒 ⇒ 回到平台旧实现的 fail-open（`return \"\"`，等于把鉴权"
            "降级成可选）。契约 `command_service.jwt.required=true`",
    ),
    Mutation(
        id="M33", side="be", path=CMD, kind="replace",
        anchor='        claims: dict[str, Any] = {"payload": dict(body)}',
        new="        claims: dict[str, Any] = dict(body)",
        want=f"{OFF}.py::test_outbound_request_carries_doc_key_request_id_and_signed_short_ttl_jwt",
        why="不再按契约 `platform_rule` 点名的 shape 签名：契约点名 payload_wrapped，"
            "实现却签成 flat body。Task 4 实测 OO 对 flat 也放行 ⇒ 这条在真实 OO 上"
            "**不会**报错，只能由守卫解码 JWT 并断言 `claims['payload']` 抓到。"
            "🔴 锚点刻意落在 claims 构造行而不是 `if claim_shape ==` 判定行："
            "短路后者会掉进 `else: raise`，于是每一条出站测试一起挂 —— "
            "判定仍是 RED 但「守卫是否真校验了 shape」被稀释掉了",
    ),
    Mutation(
        id="M34", side="be", path=CMD, kind="replace",
        anchor="        if not base:",
        new="        if False:",
        want=f"{OFF}.py::test_empty_onlyoffice_url_is_refused_instead_of_defaulting",
        why="`ONLYOFFICE_URL` 为空时不再拒 ⇒ 端点退化成相对路径，出站目标由环境决定。"
            "与 callback 下载同一条 Task 4 实证 gap：空配置不得回退成「放行一切」",
    ),
    Mutation(
        id="M35", side="be", path=CMD, kind="replace",
        anchor="        timeout = int(self._policy.timers.command_service_http_timeout_seconds)",
        new="        timeout = 30",
        want=f"{OFF}.py::test_outbound_request_carries_doc_key_request_id_and_signed_short_ttl_jwt",
        why="超时与 token TTL 改成代码里的字面量 ⇒ 契约 `timers.notes[0]`「实现必须从本"
            "文件读取，不得在代码里另写常量」被违反，契约调整后实现悄悄不跟",
        wants=(f"{PG}.py::test_predecessor_dispatch_carries_room_doc_key_and_frozen_request_id",),
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 七、destroy 闸 / 超时保持 OO
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M36", side="be", path=CMD, kind="replace",
        anchor="    if request.outcome is not None and request.outcome is CommandOutcome.server_error:",
        new="    if False:",
        want=f"{OFF}.py::test_retryable_error_is_checked_before_fsm_terminality",
        why="可重试错误不再先判 ⇒ `RequestState.rejected`（FSM terminal）会被读成"
            "「已终结，放心走」，可重试的失败当场丢内容。这条判据的顺序本身是判据",
        wants=(f"{OFF}.py::test_editor_destroy_gate_branches[retryable_keeps_oo]",),
    ),
    Mutation(
        id="M37", side="be", path=CMD, kind="replace",
        anchor="    if float(request.waited_seconds) >= float(",
        new="    if False and float(request.waited_seconds) >= float(",
        want=f"{OFF}.py::test_timeout_never_permits_reload_html",
        why="超时不再单独成态 ⇒ Property 13「超时保持 OO、reloadHtml 次数为 0」失去"
            "执法点，前端会把超时当成「仍在等」而无限轮询、或直接切回 HTML",
        wants=(f"{OFF}.py::test_editor_destroy_gate_branches[timeout_keeps_oo]",),
    ),
    Mutation(
        id="M38", side="be", path=CMD, kind="replace",
        anchor="        if incoming_durable and recovery_case_open:",
        new="        if incoming_durable or recovery_case_open:",
        want=f"{OFF}.py::test_editor_destroy_gate_branches[crash_durable_but_no_case_refused]",
        why="崩溃/OO 自发 close 的放行条件由合取松成析取 ⇒ incoming 已 durable 但还没建"
            "recovery case 时也允许销毁编辑器，durable incoming 成为无所有者死路"
            "（AC 5.4/5.8 明令禁止）",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 八、契约真值表
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M39", side="be", path=CONTRACT, kind="replace",
        anchor='        "platform_outcome": "no_changes",',
        new='        "platform_outcome": "server_error",',
        want=f"{OFF}.py::test_every_contract_return_code_has_a_closed_outcome",
        why="error 4「无新变更」被登记成可重试服务器错误 ⇒ 契约明写「直接放行离开；"
            "不得无限等 callback」的那条处置消失，用户会卡在等 callback",
        wants=(f"{OFF}.py::test_only_retryable_free_no_callback_codes_are_terminal_without_callback",),
    ),
    Mutation(
        id="M40", side="be", path=CONTRACT, kind="replace",
        anchor='        "platform_outcome": "server_error",',
        new='        "platform_outcome": "configuration_error",',
        want=f"{OFF}.py::test_http_200_with_nonzero_error_is_never_accepted",
        why="error 3 由「可重试、保持 OO」降级成配置故障 ⇒ 本可重试的失败被当成终态告警。"
            "与 M39 成对：证明 outcome 与 retryable 两列都真的被消费 —— "
            "M39 动 error 4 的 outcome，本条动 error 3 的 outcome。"
            "🔴 首轮此处的 want 写的是 M39 那条结构判据 "
            "`test_every_contract_return_code_has_a_closed_outcome`，实测判 **WRONG-TEST** "
            "并归因为**脚本缺陷**（want 从 M39 顺手抄来，不是守卫缺陷、也不是生产缺陷）："
            "那条结构判据对 error 3 只断言 `retryable is True`、对 error 4 才断言 "
            "`outcome is no_changes`，而本变异把 error 3 的 outcome 换成 "
            "`configuration_error` 时**没有动 retryable**，且 "
            "`callback_expected is (outcome is accepted)` 在 configuration_error 下依然成立 "
            "⇒ 该结构判据三条断言全部不受影响。真正拥有「error 3 的 outcome 列被消费」"
            "这一属性的是行为判据 `test_http_200_with_nonzero_error_is_never_accepted[error3]`"
            "（它断言 `dispatch.outcome is CommandOutcome.server_error`），故 want 改指它。"
            "want 刻意写**不带 `[error3]` 后缀**的裸方法名：kit 的 `_locate_want` 用 "
            "`want.split('::')[-1]` 去守卫文件里做子串定位，带 parametrize 后缀的字面量"
            "在源码里不存在（id 是 `ids=[...]` 另行声明的），会让 `--list` 判定「want 定位不到」",
    ),
]

GUARD_FILES = {
    "test_task24_close_intent.py": "Task 24 离线守卫（纯仲裁 / 双记账 / 出站分类 / destroy 闸 / 结构判据）",
    "test_task24_close_intent_pg.py": "Task 24 真实 PostgreSQL 行为守卫（exactly-one / barrier / successor / 真并发）",
}

if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="Task 24 Command Service 出站与 close-intent exactly-one 守卫变异检验",
            backend_args=[
                "backend/tests/workpaper_sync/test_task24_close_intent.py",
                "backend/tests/workpaper_sync/test_task24_close_intent_pg.py",
                "-q",
                "--tb=no",
                "-rf",
                "-p",
                "no:cacheprovider",
            ],
            # 冻结基线来源：2026-08-26 本机实测
            # `py -3 -m pytest backend/tests/workpaper_sync/test_task24_close_intent.py
            #  backend/tests/workpaper_sync/test_task24_close_intent_pg.py -q`
            # ⇒ `182 passed`（离线守卫 88 + 真库守卫 94）。
            # 沿革（改基线必须写来源，否则「基线过期」只会在报告里一闪而过 ——
            # 不符时 kit 只 WARN 不 ABORT）：
            #   178 → 守卫补齐前的旧值；
            #   180 → M01~M21/M23/M24 全部批次实测值（batch1~3 报告即此基线）；
            #   182 → M22 判 GREEN 后补 2 例
            #         `test_repeat_reconcile_in_one_eligibility_snapshot_keeps_the_leader`
            #         （revoked / expired）。补的原因见 M22 的 `why`：原判据只有
            #         「两次 leader 相等」一句，缺「comparator 这次真的跑了」的前置事实。
            baseline_backend_passed=182,
        )
    )
