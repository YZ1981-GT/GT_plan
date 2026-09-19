r"""Task 61 gate 守卫的变异检验。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 5 Task 61

被检验的守卫：`backend/tests/workpaper_sync/test_task61_oo94_word_pilot_gate.py`

## 为什么每条变异都不是无效变异

Task 61 这道门的四类最贵缺陷各自都有对应变异：

1. **分母悄悄缩小** —— 正文锚点锁、Task 44 反向锁、Word 族必声明、豁免表必须带 owner。
   把任一条锁短路，守卫必须打红（M01~M06）。
2. **判定顺序被交换** —— upstream-gap 排在黑盒之前是本门的命门：交换后"永远不会通过"
   的场景会在接上真实 OO 后自动刷绿。源码位置与反事实行为各一条变异（M07~M10）。
3. **状态被硬编码** —— 准入的五个信号、载体门的三个新鲜度输入，任一被写死即整门失效
   （M11~M17）。
4. **fail-open / 越权** —— 库读不到降级成"无数据"、`except` 吞掉、boundary probe 用
   checkbox 当判据、adapter 提前落地未被发现（M18~M24）。

## 四态判定

RED（打红且正是预期那条）/ GREEN（守卫缺陷，必修）/ ANCHOR-MISS（脚本缺陷）/
WRONG-TEST（打红了但不是预期项）。只看退出码会把后三态误判成 RED。

## 用法（仓库根；PATH 上的 `python` 可能指向坏掉的解释器）

    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task61_oo94_word_pilot_gate_guards.py --list
    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task61_oo94_word_pilot_gate_guards.py --run M01,M02
    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task61_oo94_word_pilot_gate_guards.py --check-anchors

🔴 **禁后台执行**（孤儿 python + 前台同时变异 ⇒ RestoreFailed）；**绝不 `--restore`**。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

GATE = "backend/scripts/check/check_task61_oo94_word_pilot_gate.py"

#: 🔴 kit 按**短 nodeid**（basename::类::方法）匹配新增失败集合 —— 带
#: `backend/tests/...` 前缀会让「实际打红的正是预期那条」被误判 WRONG-TEST。
_T = "test_task61_oo94_word_pilot_gate.py"

_TEXT = f"{_T}::TestTaskTextIsTheDenominator"
_DEN = f"{_T}::TestScenarioDenominatorIsThreeWay"
_CARRIER = f"{_T}::TestCarrierGateFreshnessIsMeasured"
_ADMIT = f"{_T}::TestAdmissionIsRealReadback"
_ORDER = f"{_T}::TestOrderingIsNotCommutative"
_CLAIM = f"{_T}::TestDocumentaryClaimIsRejected"
_BOUND = f"{_T}::TestBoundaryProbesMeasureNonCrossing"
_OPEN = f"{_T}::TestNoFailOpen"
_EVID = f"{_T}::TestEvidenceValidatorsAreReal"
_REPORT = f"{_T}::TestReportIsPerEntryAndPerScenario"
_PROP = f"{_T}::TestProperties"
_SELF = f"{_T}::TestGuardSelfChecks"
_BIND = f"{_T}::TestBindingConstraintIsMeasured"


MUTATIONS: list[Mutation] = [
    # ═══ 一、分母锁被短路（AC 12.3 / 12.10）══════════════════════════════════
    Mutation(
        id="M01", side="be", path=GATE, kind="replace",
        anchor="        hits = body.count(spec.anchor)",
        new="        hits = 1  # 变异：不再真数",
        want=f"{_TEXT}::test_removing_one_enumerated_item_from_the_task_text_fails_the_gate",
        wants=(
            f"{_TEXT}::test_removing_the_close_family_sentence_fails_the_gate",
            f"{_TEXT}::test_generated_registry_data_file_is_fresh",
        ),
        why="正文锚点锁是本门与 tasks.md 的唯一锁。把计数写死成 1 之后，"
            "正文枚举项被删也不会打红 —— 这正是「分母悄悄缩小」的入口。",
    ),
    Mutation(
        id="M02", side="be", path=GATE, kind="replace",
        anchor="    shrunk = sorted(task44 - declared - excused)",
        new="    shrunk = []  # 变异：放弃反向锁",
        want=f"{_DEN}::test_dropping_one_task44_scenario_probe_is_detected",
        why="反向锁（Task 44 已声明的场景在这里既无 probe 也无豁免）被放弃后，"
            "删掉任一条 scenario probe 都不会被发现。",
    ),
    Mutation(
        id="M03", side="be", path=GATE, kind="replace",
        anchor="    missing_word = sorted(word_family - declared)",
        new="    missing_word = []  # 变异：Word 族不再必须声明",
        want=f"{_DEN}::test_dropping_a_word_family_probe_is_detected",
        why="Word 族是本任务的核心。放弃这条后漏掉 word_free_body_isolation / "
            "word_sdt_tag_row_uuid_retention 都不会打红。",
    ),
    Mutation(
        id="M04", side="be", path=GATE, kind="replace",
        anchor="    overlap = sorted(excused & declared)",
        new="    overlap = []  # 变异：允许同时豁免与声明",
        want=f"{_DEN}::test_out_of_lane_and_probe_sets_are_disjoint",
        why="同一场景同时进 probe 与豁免表时，「豁免」会顶住「未通过」"
            "（教训③：判据写成集合成员会被另一个顶住）。",
    ),
    Mutation(
        id="M05", side="be", path=GATE, kind="replace",
        anchor='            if not str(row.get(field_name) or "").strip():',
        new="            if False:  # 变异：豁免行不再需要 owner/出处",
        want=f"{_DEN}::test_an_out_of_lane_row_without_owner_is_a_structural_failure",
        why="「缺场景必须有 owner 与实测出处」是防「感觉不相关就豁免」的唯一判据。",
    ),
    Mutation(
        id="M06", side="be", path=GATE, kind="replace",
        anchor="        offenders = list(payload.get(key) or ())",
        new="        offenders = []  # 变异：AC/Property 覆盖不再双向",
        want=f"{_TEXT}::test_an_unclaimed_requirement_is_a_structural_failure",
        wants=(f"{_TEXT}::test_a_property_drifting_from_the_task_text_is_a_structural_failure",),
        why="AC/Property 双向覆盖是「正文声明的每条都有落点、probe 也不得声明正文之外的」"
            "的唯一判据；放弃后加减 AC 都不会被发现。",
    ),
    # ═══ 二、判定顺序（AC 14.9）══════════════════════════════════════════════
    Mutation(
        id="M07", side="be", path=GATE, kind="swap",
        anchor='        return _row(RESULT_FAILED, "upstream_gap", [debt])',
        anchor2='        return _row(RESULT_UNVERIFIABLE, "real_onlyoffice_not_executed")',
        block_open="    if ",
        want=f"{_ORDER}::test_source_positions_put_upstream_gap_before_the_black_box",
        wants=(
            f"{_ORDER}::test_real_black_box_does_not_turn_an_upstream_gap_green",
            f"{_ORDER}::test_the_ordering_gate_probe_passes",
            f"{_REPORT}::test_no_probe_row_is_passed_for_a_scenario",
        ),
        why="🔴 本门的命门：黑盒判定排到 upstream-gap 之前后，缺实现的场景在没有真实 OO "
            "的环境里显示成 unverifiable，接上真实 OO 就会自动刷绿（本 spec 已四次实测）。",
    ),
    Mutation(
        id="M08", side="be", path=GATE, kind="replace",
        anchor="        debt = debt or supply_gap_debt(facts)",
        new="        debt = debt  # 变异：未准入不再记 upstream_gap",
        want=f"{_ORDER}::test_real_black_box_does_not_turn_an_upstream_gap_green",
        wants=(f"{_ORDER}::test_the_ordering_gate_probe_passes",),
        why="未准入时不再取供给缺口文本 ⇒ 判定从 failed 降级成 unverifiable，"
            "「缺的是实现不是环境」这条区分消失。",
    ),
    Mutation(
        id="M09", side="be", path=GATE, kind="replace",
        anchor="    if scenario_id != \"word_sdt_tag_row_uuid_retention\":",
        new="    if True:  # 变异：任何场景都能拿载体豁免",
        want=f"{_ORDER}::test_carrier_unrepresentable_outranks_upstream_gap",
        wants=(f"{_ORDER}::test_other_scenarios_never_get_the_carrier_excuse",),
        why="载体豁免只适用于 row_uuid 半边。放宽成「任何场景」后，upstream_gap 会被"
            "整体降级成 unverifiable —— 假绿。",
    ),
    Mutation(
        id="M10", side="be", path=GATE, kind="replace",
        anchor="    if facts.row_scoped_field_count > 0:",
        new="    if False:  # 变异：有行域字段也照样豁免",
        want=f"{_ORDER}::test_carrier_unrepresentable_needs_both_conditions",
        why="豁免的两个条件必须**各自**必要。去掉「本 entry 无行域字段」后，"
            "某天契约加了 repeaters 也会被继续豁免掉。",
    ),
    # ═══ 三、准入与载体门的状态敏感性（AC 12.3 / 7.6 / 14.16）═══════════════
    Mutation(
        id="M11", side="be", path=GATE, kind="replace",
        anchor="            and self.published_representation_present",
        new="            and True  # 变异：不再要求 published representation",
        want=f"{_ADMIT}::test_each_admission_condition_is_individually_necessary",
        why="Task 61 正文第一句写死了准入条件含 published representation。去掉它之后，"
            "只要别的信号齐了就能进测试范围 —— 直接违反正文。"
            "🔴 首轮判 GREEN：原 want 是「今天两个 entry 都未准入」，而今天五项**同时**"
            "为 False ⇒ 去掉任一项判断结论都不变。补的判据是「从全部就绪出发关掉恰一项」。",
    ),
    Mutation(
        id="M12", side="be", path=GATE, kind="replace",
        anchor="            and self.approved_bundle_present",
        new="            and True  # 变异：不再要求 approved bundle",
        want=f"{_ADMIT}::test_each_admission_condition_is_individually_necessary",
        why="同上，另一半：approved F2 per-entry bundle 也是正文写死的准入条件。"
            "🔴 首轮同 M11 判 GREEN，同一处补的判据。",
    ),
    Mutation(
        id="M13", side="be", path=GATE, kind="replace",
        anchor="            and self.carrier.really_passed",
        new="            and True  # 变异：载体门不再参与准入",
        want=f"{_ADMIT}::test_a_stale_carrier_gate_alone_blocks_admission",
        why="「Task 6 probe 未真实通过时保持 UNVERIFIABLE」是正文原文。载体门被摘出准入后，"
            "裁决 stale 也照样开跑。",
    ),
    Mutation(
        id="M14", side="be", path=GATE, kind="replace",
        anchor="        contract_installed=ref.contract_id in installed,",
        new="        contract_installed=False,  # 变异：写死",
        want=f"{_ADMIT}::test_contract_installed_is_derived_from_the_production_inventory",
        why="🔴 写死 False 时「两个 entry 都未准入」这句话仍然成立 ⇒ 只看今天的结论查不出。"
            "首轮判 GREEN 的原因是原 want 用 `_all_signals_ready()` 构造替身，绕过了"
            "`probe_admission_signals` 本体。补的判据把生产清册换成含本 lane 契约的集合后"
            "再真跑一次 —— 断言「真做了一次属性取值」而不是 grep 符号名（教训②）。",
    ),
    Mutation(
        id="M15", side="be", path=GATE, kind="replace",
        anchor="    if recorded_commit != seen_commit:",
        new="    if False:  # 变异：不再核对 source_commit",
        want=f"{_CARRIER}::test_source_commit_drift_alone_makes_it_stale",
        wants=(f"{_CARRIER}::test_the_gate_self_check_measures_all_three_inputs",),
        why="Task 6 contract 的 stale_policy 明写 source_commit 变化即裁决失效。"
            "三个输入**各自**一条变异 —— 写成「任一项」时短路两项也能过（教训③）。",
    ),
    Mutation(
        id="M16", side="be", path=GATE, kind="replace",
        anchor="    if recorded_build != seen_build:",
        new="    if False:  # 变异：不再核对 OO build",
        want=f"{_CARRIER}::test_oo_build_drift_alone_makes_it_stale",
        wants=(f"{_CARRIER}::test_the_gate_self_check_measures_all_three_inputs",),
        why="同上，第二个输入：OO build 换版后 Task 6 的载体结论不再适用。",
    ),
    Mutation(
        id="M17", side="be", path=GATE, kind="replace",
        anchor="            if observed != recorded:",
        new="            if False:  # 变异：不再核对模板 digest",
        want=f"{_CARRIER}::test_template_digest_drift_alone_makes_it_stale",
        wants=(f"{_CARRIER}::test_the_gate_self_check_measures_all_three_inputs",),
        why="同上，第三个输入：probe 模板被改过之后，Task 6 的 tag 计数结论全部作废。",
    ),
    Mutation(
        id="M18", side="be", path=GATE, kind="replace",
        anchor='            and self.anchors_allowed == ("w_tag",)',
        new="            and True  # 变异：锚点集合不再受限",
        want=f"{_CARRIER}::test_really_passed_requires_w_tag_to_be_the_only_admissible_anchor",
        why="Requirement 7.1 把正式协议限定为 w:tag，Task 6 把另外四个锚点判为不可用。"
            "放宽后 paragraph_index 也能算「载体门通过」—— 正文明禁的 fallback 从这里进来。",
    ),
    # ═══ 四、fail-open 与越权（AC 5.12 / 7.8 / 12.3 / 14.9）════════════════
    Mutation(
        id="M19", side="be", path=GATE, kind="replace",
        anchor="        raise DatabaseUnreadable(_DB_UNREADABLE_MESSAGE.format(detail=f\"{type(exc).__name__}: {exc}\")) from exc",
        new="        return {}  # 变异：库读不到就当没数据",
        want=f"{_OPEN}::test_unreadable_database_is_structural_not_unverifiable",
        wants=(f"{_OPEN}::test_the_cli_returns_two_when_the_database_is_unreadable",),
        why="🔴 本 spec 最贵的一类缺陷：库读不到降级成「本项目无此数据」后，退出码从 2 变成 1，"
            "读报告的人会以为「门跑过了、只是环境不足」。",
    ),
    Mutation(
        id="M20", side="be", path=GATE, kind="replace",
        anchor="        missing = [k for k in DB_SNAPSHOT_KEYS if k not in row]",
        new="        missing = []  # 变异：快照键集不再封闭",
        want=f"{_ADMIT}::test_a_db_snapshot_missing_one_key_is_a_structural_failure",
        why="少查一张表就会把缺口当成没问题 —— 封闭键集是唯一拦得住的判据。",
    ),
    Mutation(
        id="M21", side="be", path=GATE, kind="replace",
        anchor="    landed = [p for p in row.get(\"forbidden_paths\") or () if (_REPO / \"backend\" / p).exists()]",
        new="    landed = []  # 变异：不再检查 forbidden path 是否已落地",
        want=f"{_BOUND}::test_a_landed_word_adapter_flips_the_boundary_probe_red",
        why="PHASE D 的反向判据：`adapters/word.py` 提前落地必须被发现。"
            "去掉这条后 Word adapter 可以在门未过时静悄悄进来。",
    ),
    Mutation(
        id="M22", side="be", path=GATE, kind="replace",
        anchor="    if len(rows) != 1:",
        new="    if False:  # 变异：pending 登记可以有 0 行或多行",
        want=f"{_BOUND}::test_two_docx_pending_rows_flip_it_red",
        why="登记恰 1 行是「登记表与事实不脱钩」的判据。允许 0 行时把整条 pending 行删掉"
            "也不会被发现（=放行门凭空消失）。",
    ),
    Mutation(
        id="M23", side="be", path=GATE, kind="replace",
        anchor="    if str(TASK_NUMBER) not in str(row.get(\"blocking_task\") or \"\"):",
        new="    if False:  # 变异：不再要求 pending 行点名 Task 61",
        want=f"{_BOUND}::test_a_pending_row_that_stops_naming_task61_flips_it_red",
        why="放行门的 owner 是 Task 61。`blocking_task` 不再被核对时，"
            "别的任务可以悄悄把自己写成放行者。",
    ),
    Mutation(
        id="M24", side="be", path=GATE, kind="replace",
        anchor="        and not docx_delivered",
        new="        and True  # 变异：交付登记表出现 docx entry 也算未跨越",
        want=f"{_BOUND}::test_adding_a_docx_entry_to_the_delivered_registry_flips_it_red",
        why="批量迁移会往 `DELIVERED_PER_ENTRY_CONTRACTS` 加行。不看这一项时，"
            "Tasks 62–64 实际上已经动手了本门也报「仍阻塞」。",
    ),
    Mutation(
        id="M25", side="be", path=GATE, kind="replace",
        anchor="            if str(key).lower() in FORBIDDEN_RECORD_KEYS:",
        new="            if False:  # 变异：不再拒绝结果声明字段",
        want=f"{_CLAIM}::test_each_forbidden_key_is_rejected_on_its_own",
        wants=(
            f"{_CLAIM}::test_the_gate_probe_runs_the_rejection_for_real",
            f"{_CLAIM}::test_load_execution_records_rejects_a_claiming_file",
        ),
        why="AC 14.9：不得以文档声明通过。放弃这条后，一份写着 `\"result\": \"passed\"` 的"
            "记录就能让全部 scenario 变绿。",
    ),
    Mutation(
        id="M26", side="be", path=GATE, kind="replace",
        anchor="        raise GateStructuralError(_NO_CRITERION_MESSAGE.format(probe_id=spec.probe_id))",
        new="        return _row(RESULT_PASSED, None, [\"变异：无判据也判过\"])",
        want=f"{_OPEN}::test_a_probe_without_validator_or_oracle_cannot_default_to_pass",
        why="既无 validator 又无 oracle 的 probe 默认判过 = additive 死代码的最终形态"
            "（教训⑩）：声明一条 probe 就白得一个 passed。",
    ),
    Mutation(
        id="M27", side="be", path=GATE, kind="replace",
        anchor="    if drift:",
        # 🔴 `if drift:` 在本文件命中 2 处（另一处在 `validate_full_restoration`）⇒ 必须
        #    相对定位。用 `scope`+`offset` 而不是绝对 `line`：绝对行号一改文件就失效。
        scope="    if not facts.frozen_slot_digests:",
        offset=7,
        new="    if False:  # 变异：typed slot digest 漂移不再拒",
        want=f"{_EVID}::test_a_slot_digest_from_the_other_entry_is_rejected",
        why="Property 70：每个 F2 entry 保存自身 bundle digest，不交叉复用。"
            "放弃比对后 F2-23 的 evidence 可以拿去给 F2-22 充数。",
    ),
    Mutation(
        id="M28", side="be", path=GATE, kind="replace",
        anchor="    if len(per_scenario) != len(declared):",
        new="    if False:  # 变异：application id 覆盖计数不再核对",
        want=f"{_EVID}::test_partial_coverage_fails",
        why="教训⑥：任何「齐全」判据都要断言覆盖计数非空/足额。只查「两两不同」时，"
            "交 1 条 scenario 的 application id 也算「逐 scenario 独立」。",
    ),
    Mutation(
        id="M29", side="be", path=GATE, kind="replace",
        anchor="    if len(rows) != payload[\"total_probe_rows\"]:",
        new="    if False:  # 变异：probe 行数与声明脱钩也不报",
        want=f"{_REPORT}::test_a_row_count_mismatch_is_a_structural_failure",
        why="行数与声明分母脱钩是「少跑一条」的最后一道网。",
    ),
    Mutation(
        id="M30", side="be", path=GATE, kind="replace",
        anchor="    sentinel = _not_executed()",
        new="    sentinel = observed_onlyoffice_build()  # 变异：容器在跑就算真跑过",
        want=f"{_OPEN}::test_the_gate_never_treats_a_running_container_as_a_real_roundtrip",
        why="🔴「容器在跑」不等于「本次真跑了 OO 往返」。把容器版本填进默认环境后，"
            "黑盒判定自动变绿 —— 本 spec 反复点名的假绿形态。",
    ),
    # ═══ 五、绑定约束的三臂实测（gate/2 新增，M31~M41）════════════════════════
    #
    # 首版这道门把「registry 无 docx adapter」当 word_bulk 门的证据，2026-09-01 三臂实测
    # 证明那是重言式（前三条前提逐一移除后它仍恒真，顶着它的是平台级的
    # `working_paper_sync_entry_state` 全表 0 行）。以下变异逐条检验新判据不是装饰。
    Mutation(
        id="M31", side="be", path=GATE, kind="replace",
        anchor="    same_class_as_control = arm_b_reason is not None and arm_b_reason == control_reason",
        new="    same_class_as_control = arm_b_reason is not None and arm_b_reason[:20] in str(control_reason)",
        want=f"{_BIND}::test_a_substring_match_is_not_accepted_as_the_same_reason",
        why="判「arm_b 与对照是同一条原因」必须**逐字相等**。放宽成子串之后，任何"
            "前缀相同的原因都会被算成同类 —— 等于在守卫里维护第二份关键词表"
            "（原因文案的真源在 `registry._describe_entry_supply`）。",
    ),
    Mutation(
        id="M32", side="be", path=GATE, kind="replace",
        anchor="    arm_c_moved = arm_c_reason is not None and arm_c_reason != arm_b_reason",
        new="    arm_c_moved = True  # 变异：不再度量顺序",
        want=f"{_BIND}::test_arm_c_not_moving_is_a_hardcoding_signal",
        why="arm_c 是本 probe 唯一的 state-sensitivity 自检：解除供给门后原因必须改变。"
            "写死 True 之后，一个把裁决硬编码成 BP-61-1 的实现也能全绿。",
    ),
    Mutation(
        id="M33", side="be", path=GATE, kind="replace",
        anchor="    missing = [name for name in BINDING_ARMS if name not in arms]",
        new="    missing = []  # 变异：允许缺臂",
        want=f"{_BIND}::test_all_three_arms_are_required",
        why="两臂比不出「同类」与「不同类」两件事。允许缺臂后，只跑 arm_a 也能得出"
            "「绑定约束是 BP-61-1」这个结论 —— 结论正确而推理为空。",
    ),
    Mutation(
        id="M34", side="be", path=GATE, kind="replace",
        anchor='    if not arm_a["planned"]:',
        new="    if False:  # 变异：分母可以为空",
        want=f"{_BIND}::test_an_empty_planned_denominator_is_rejected",
        why="教训⑥：分母为空时「零注册」是重言式。planned==0 时 registered==0 必然成立，"
            "本 probe 会对一个什么都没跑的 registry 判过。",
    ),
    Mutation(
        id="M35", side="be", path=GATE, kind="replace",
        anchor='    if arm_a["registered_adapter_ids"]:',
        new="    if False:  # 变异：已注册也照旧判过",
        want=f"{_BIND}::test_an_already_registered_adapter_invalidates_the_premise",
        why="本门的前提是 Word lane 未注册。前提变了（真有 adapter 注册上了）而判据仍按"
            "旧裁决判过 = 把一个已经过期的结论继续输出。",
    ),
    Mutation(
        id="M36", side="be", path=GATE, kind="replace",
        anchor='    bad_ids = [i for i in ids if not re.fullmatch(r"BP-61-\\d+", i)]',
        new="    bad_ids = []  # 变异：不再锁 task-scoped 前缀",
        want=f"{_BIND}::test_a_bad_constraint_id_flips_it_red",
        why="全局 `BP-NN` 已被 Tasks 60/63/64 各自重复占用（同号不同义）。放弃前缀锁后，"
            "本任务的登记会与别人的同号冲突，`same_root_cause_as` 一类交叉引用随之失效。",
    ),
    Mutation(
        id="M37", side="be", path=GATE, kind="replace",
        anchor="        problems.append(f\"kind=='binding' 的行数 {len(binding)} ≠ 1\")",
        new="        pass  # 变异：多条 binding 也放行",
        want=f"{_BIND}::test_two_binding_rows_flip_it_red",
        why="零条 binding = 没裁决；多条 = 没收敛。放行之后「绑定约束是哪一条」重新变成"
            "读者自己去猜，而这正是本 probe 要消灭的形态。",
    ),
    Mutation(
        id="M38", side="be", path=GATE, kind="replace",
        anchor='    constraints = list(payload.get("binding_constraints") or ())',
        new='    constraints = [{"id": "BP-61-0", "kind": "binding"}]  # 变异：凭空补一条',
        want=f"{_BIND}::test_the_registry_coverage_check_rejects_an_empty_constraint_list",
        why="数据文件是「哪一条是绑定约束」的离线复核处。用兜底常量顶住之后，"
            "把 `binding_constraints` 从数据文件里整段删掉也不会被发现。",
    ),
    Mutation(
        id="M39", side="be", path=GATE, kind="replace",
        anchor="        poolclass=NullPool,",
        new="        echo=False,  # 变异：回退共享池语义",
        want=f"{_BIND}::test_the_arms_use_an_isolated_engine_not_the_shared_pool",
        why="🔴 三臂必须用独立 NullPool 引擎。复用共享池时，本门 `read_db_snapshot` 那次 "
            "`asyncio.run` 留下的连接绑在已关闭的 event loop 上，第二次取到就报 "
            "`'NoneType' object has no attribute 'send'` ⇒ 被包成 `DatabaseUnreadable` ⇒ "
            "**假 ERROR 态**（gate/2 首跑实测打成 exit 2，而库其实完全可达）。",
    ),
    Mutation(
        id="M40", side="be", path=GATE, kind="replace",
        anchor="            registry_module._describe_entry_supply = original_supply  # type: ignore[assignment]",
        new="            pass  # 变异：不复原 _describe_entry_supply 替身",
        want=f"{_BIND}::test_the_arms_do_not_mutate_the_production_registry",
        wants=(f"{_BIND}::test_the_three_arms_really_run_against_the_database",),
        why="反事实注入不复原 ⇒ 本进程后续每一条判据都在替身状态下算出来的。"
            "这条同时证明那两行复原自检有真实消费方（不是装饰）。",
    ),
    Mutation(
        id="M41", side="be", path=GATE, kind="replace",
        anchor='    synth["document_type"] = "docx"',
        new="    pass  # 变异：不改 document_type",
        want=f"{_BIND}::test_the_synthetic_docx_entry_changes_only_the_declared_fields",
        why="arm_b 的唯一变量必须真的是 BP-61-2（manifest 无 docx F2 entry）。不改 "
            "document_type 时 arm_b 与 arm_a 无差异，「原因不变」于是变成一句没有信息量"
            "的话 —— 结论照旧是 BP-61-1，但推理已经空了。",
    ),
]


#: 覆盖面分母（守卫文件名 → 归属说明）。空分母在 kit 里直接抛。
GUARD_FILES: dict[str, str] = {
    _T: "Task 61 新建：真实 OO 9.4 F2 Word pilot gate 的守卫",
}

#: 后端执行参数。🔴 只跑本守卫文件：本门是新建产物，辐射面就是它自己；
#: 跑整目录会把并发在途的既存红混进差集，让四态判定不可解读。
BACKEND_ARGS: list[str] = [
    f"backend/tests/workpaper_sync/{_T}",
    "-q",
    "--tb=no",
    "-rf",
    "-p",
    "no:randomly",
]

#: 冻结基线：本守卫文件在未变异时的 passed 数。
#: 来源 = 2026 本轮实测 `pytest backend/tests/workpaper_sync/test_task61_oo94_word_pilot_gate.py
#: -q -p no:randomly` ⇒ `160 passed`（0 failed / 0 error）。
#: 沿革：首轮 M11/M12/M14 判 GREEN 后补了 8 条守卫（五个准入条件逐项必要 + 三个信号的
#: 真实取值反读），基线 132 → 140；gate/2 追加 `TestBindingConstraintIsMeasured`
#: 20 条（三臂反事实 + BP-61-n 登记形态 + 独立引擎），140 → 160。
#: 改基线必须重跑并更新此注释。
BASELINE_BACKEND_PASSED = 160


if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="Task 61 gate 守卫变异检验",
            backend_args=BACKEND_ARGS,
            baseline_backend_passed=BASELINE_BACKEND_PASSED,
        )
    )
