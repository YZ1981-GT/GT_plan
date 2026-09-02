# -*- coding: utf-8 -*-
"""Task 44 守卫变异检验 —— 真实 OnlyOffice 9.4 Excel pilot gate。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 4 Task 44

覆盖面分母 = 本任务新建的守卫文件；变异目标 = gate 脚本 + 生成的 probe 注册表数据文件
+ 注册表生成器（三处产物各自都有守卫）。

用法（仓库根）::

    py -3 backend/scripts/diagnose/mutate_task44_oo94_excel_pilot_gate_guards.py --list
    py -3 backend/scripts/diagnose/mutate_task44_oo94_excel_pilot_gate_guards.py --check-anchors
    py -3 backend/scripts/diagnose/mutate_task44_oo94_excel_pilot_gate_guards.py --run all \
        --out .kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/\
evidence/task44-oo94-excel-pilot-gate/mutation_report.json

🔴 本脚本遵守的踩坑清单（都是平台实测出来的）
--------------------------------------------

* `want` 用**短 nodeid**（`file.py::Class::test`），`Mutation.want` 是必填字段；
* 锚点**只能单行**（工作树 CRLF 下跨行锚点必 MISS），同形锚点用 `scope`+`offset`；
* 替换后必须**语法合法**（`if False and <expr>:` / `return True or <expr>`）；
* `insert` 的 `new` 不得重复 `if`/`def` 头（空函数体 ⇒ IndentationError ⇒ collection
  error ⇒ 被误判成 WRONG-TEST）；
* **数据文件**变异必带 `scope_check`，且 `scope_check` 回调必须与 `path` 后缀相容 ——
  把 JSON 族回调（内部 `json.loads`）喂给 `.py` 目标会抛 `JSONDecodeError`，被
  `cli._run_one` 的宽 `except` 记成 `verdict=ERROR` + `hit=None`（**pytest 从未跑过**），
  Task 43 的 M31 正是这个形态。Python 源码用整行逐字计数式 `scope_check`；
* **声明数必须等于执行数** —— 「已跑的全 RED」不得冒充全量（Task 43 声明 74 只跑 39）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

GATE = "backend/scripts/check/check_task44_oo94_excel_pilot_gate.py"
GEN = "backend/scripts/gen/generate_workpaper_task44_pilot_probe_registry.py"
DATA = "backend/data/workpaper_task44_pilot_gate_probes.json"

T44 = "test_task44_oo94_excel_pilot_gate.py"
_LOCK = f"{T44}::TestProbeRegistryIsLockedToTaskText"
_DEN = f"{T44}::TestScenarioDenominatorIsBidirectional"
_FIN = f"{T44}::TestFinalizeStateIsReadFromProduction"
_ORD = f"{T44}::TestOrderingIsNotCommutable"
_DOC = f"{T44}::TestNoDocumentaryPass"
_VAL = f"{T44}::TestValidatorsAreBidirectionallyReachable"
_BLK = f"{T44}::TestGateBlocksWave5"
_REP = f"{T44}::TestReportIsClosedAndMeasured"
_PROP = f"{T44}::TestPropertyLandings"


# ═══════════════════════════════════════════════════════════════════════════
# 作用域自证回调
# ═══════════════════════════════════════════════════════════════════════════


def _py_line_counts(expected: dict[str, int]):
    """**Python 源码**变异的作用域自证：整行逐字计数必须恰好等于期望。

    🔴 不得把 JSON 族回调喂给 `.py` 目标（`json.loads` 会抛 → verdict=ERROR，pytest 根本
    没跑）。这里比的是**源码字面量**（`True` 而非 `true`）。
    """

    def check(data: bytes) -> bool:
        lines = data.decode("utf-8").splitlines()
        for needle, count in expected.items():
            if sum(1 for line in lines if needle in line) != count:
                return False
        return True

    return check


def _json_field_is(path: tuple[str, ...], expected: object):
    """**数据文件**变异的作用域自证：JSON 里某条路径的值必须恰好是 `expected`。"""

    def check(data: bytes) -> bool:
        cursor: object = json.loads(data.decode("utf-8"))
        for part in path:
            if not isinstance(cursor, dict):
                return False
            cursor = cursor.get(part)
        return cursor == expected

    return check


def _json_probe_anchor_is(probe_id: str, expected: str):
    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        for probe in payload["probes"]:
            if probe["probe_id"] == probe_id:
                return probe["anchor"] == expected
        return False

    return check


MUTATIONS: list[Mutation] = [
    # ── ① tasks.md / design.md 真源锁 ────────────────────────────────────
    Mutation(
        id="M01",
        side="be",
        path=GATE,
        kind="replace",
        anchor="        if hits == 0:",
        new="        if False and hits == 0:",
        want=f"{_LOCK}::test_removing_one_enumerated_item_from_the_task_text_fails_the_gate",
        why="锚点缺失不再抛 ⇒ 正文枚举项被删也不会被发现（分母静默缩小）",
        scope_check=_py_line_counts({"if False and hits == 0:": 1}),
    ),
    Mutation(
        id="M02",
        side="be",
        path=GATE,
        kind="replace",
        anchor=r'    r"^- \[[ x~\-]\] (\d+)\. ", flags=re.MULTILINE',
        new=r'    r"^- \[ \] (\d+)\. ", flags=re.MULTILINE',
        want=(
            f"{_LOCK}::"
            "test_task_body_is_located_by_number_not_line_and_survives_a_ticked_checkbox"
        ),
        why="只认未勾选的 checkbox ⇒ Task 44 一被勾选本门立刻与正文脱钩",
        scope_check=_py_line_counts({r'r"^- \[ \] (\d+)\. "': 1}),
    ),
    Mutation(
        id="M03",
        side="be",
        path=GATE,
        kind="replace",
        anchor='    if payload["requirements_without_probe"]:',
        new='    if False and payload["requirements_without_probe"]:',
        want=f"{_LOCK}::test_an_unclaimed_requirement_is_a_structural_failure",
        why="AC 没有 probe 认领时不再抛 ⇒ 22 条 AC 可以少认领而门仍绿",
        scope_check=_py_line_counts(
            {'if False and payload["requirements_without_probe"]:': 1}
        ),
    ),
    Mutation(
        id="M04",
        side="be",
        path=GATE,
        kind="replace",
        anchor="    if missing:",
        new="    if False and missing:",
        scope="        out[prop] = match.group(1).strip()",
        offset=1,
        want=f"{_LOCK}::test_a_property_missing_from_design_md_is_a_structural_failure",
        why="design.md 里查不到 Property 定义时不再抛 ⇒ 「独立验证 16 条」可以名存实亡",
        scope_check=_py_line_counts({"if False and missing:": 1}),
    ),
    Mutation(
        id="M05",
        side="be",
        path=GATE,
        kind="replace",
        anchor="        if not hasattr(module, attr):",
        new="        if False and not hasattr(module, attr):",
        want=f"{_LOCK}::test_a_vanished_production_symbol_fails_the_probe",
        why="生产符号消失不再抛 ⇒ probe 声明还在、被测对象早已不在（fail-open 掩盖接线断裂）",
        scope_check=_py_line_counts({"if False and not hasattr(module, attr):": 1}),
    ),
    # ── ② scenario 分母双向锁 ───────────────────────────────────────────
    Mutation(
        id="M06",
        side="be",
        path=GATE,
        kind="replace",
        anchor="    if unclaimed:",
        new="    if False and unclaimed:",
        want=f"{_DEN}::test_dropping_one_scenario_probe_makes_the_denominator_shrink_detectable",
        why="required set 里的场景没人声明 probe 时不再抛 ⇒ 分母可以悄悄缩小（假绿第①源）",
        scope_check=_py_line_counts({"if False and unclaimed:": 1}),
    ),
    Mutation(
        id="M07",
        side="be",
        path=GATE,
        kind="replace",
        anchor="    if unknown:",
        new="    if False and unknown:",
        want=f"{_DEN}::test_a_scenario_probe_without_a_production_oracle_is_rejected",
        why="scenario probe 指向不存在的 oracle 时不再抛 ⇒ probe 表可追加自由项",
        scope_check=_py_line_counts({"if False and unknown:": 1}),
    ),
    Mutation(
        id="M08",
        side="be",
        path=GATE,
        kind="replace",
        anchor="        if other.pilot_class == facts.ref.pilot_class:",
        new="        if True:",
        want=f"{_DEN}::test_missing_dynamic_scenario_maps_to_a_registered_upstream_debt",
        why="跨 pilot 沿用已注册欠账名的通路被掐断 ⇒ Task 40 的缺场景会退化成「没有 owner」",
        scope_check=_py_line_counts({"        if True:": 1}),
    ),
    Mutation(
        id="M09",
        side="be",
        path=GATE,
        kind="replace",
        anchor='        capability == "bidirectional" or room_model == "shared"',
        new='        capability == "bidirectional" and room_model == "shared"',
        want=f"{_DEN}::test_close_predicate_is_cross_checked_against_the_raw_manifest",
        why="close 谓词的析取写成合取 ⇒ 179 个 editable+shared entry 全部漏掉 8 条 close 场景",
        scope_check=_py_line_counts(
            {'capability == "bidirectional" and room_model == "shared"': 1}
        ),
    ),
    # ── ③ finalize 真实反读（本门最容易被写成硬编码的一段）────────────
    Mutation(
        id="M10",
        side="be",
        path=GATE,
        kind="replace",
        anchor='        capability_enabled, capability_reject = False, f"{type(exc).__name__}: {exc}"',
        new='        capability_enabled, capability_reject = True, ""',
        want=f"{_FIN}::test_all_four_pilots_are_blocked_before_task_36_finalize",
        why="capability 断言抛异常却记成「已启用」 ⇒ 未 finalize 的 entry 被判准入",
        scope_check=_py_line_counts(
            {'capability_enabled, capability_reject = True, ""': 1}
        ),
    ),
    Mutation(
        id="M11",
        side="be",
        path=GATE,
        kind="replace",
        # 🔴 Task 75 重指锚点 + 重指 want：观测器已交付，探针从二态改成**按异常类型分型**
        #    的三态（shape 错误 ⇒ available；其它异常 ⇒ unavailable），原锚点
        #    `observer_state = "unavailable"` 与原 want
        #    `test_observer_detail_names_the_registered_upstream_debt` 双双 0 命中。
        #    判据强度不放宽而是**加强**：变异改为抹掉分型（无条件 available），于是
        #    「换成抛非 shape 异常必须退回 unavailable」这条正向判据打红 —— 它比原来那条
        #    「detail 里要提到某个欠账名」的字符串判据更强（后者是登记态，前者是行为）。
        anchor='        observer_state = "available" if implemented else "unavailable"',
        new='        observer_state = "available"',
        want=f"{_FIN}::test_each_signal_flips_independently_under_substitution",
        wants=(f"{_FIN}::test_the_four_pilots_short_circuit_at_different_gates",),
        why="观测器抛任意异常都记成 available ⇒ 三态分型退化成装饰，「观测器坏了」与"
            "「观测器已交付」不再可分辨（fail-open 掩盖接线错误）",
        scope_check=_py_line_counts(
            {
                '        observer_state = "available"': 1,
                'if implemented else "unavailable"': 0,
            }
        ),
    ),
    Mutation(
        id="M12",
        side="be",
        path=GATE,
        kind="replace",
        anchor="        adapter_registered=adapter_id in registered,",
        new="        adapter_registered=True,",
        want=f"{_FIN}::test_all_four_pilots_are_blocked_before_task_36_finalize",
        why="adapter 注册状态写死为 True ⇒ registry 里一个 adapter 都没有也算已注册",
        scope_check=_py_line_counts({"adapter_registered=True,": 1}),
    ),
    Mutation(
        id="M13",
        side="be",
        path=GATE,
        kind="replace",
        anchor="        attach_session_reads=empty_session.calls,",
        new="        attach_session_reads=1,",
        want=f"{_FIN}::test_the_four_pilots_short_circuit_at_different_gates",
        why="读库次数写死 ⇒ 「41/42/43 在 capability 门就 return 不读库」这条实测差异丢失",
        scope_check=_py_line_counts({"attach_session_reads=1,": 1}),
    ),
    Mutation(
        id="M14",
        side="be",
        path=GATE,
        kind="replace",
        anchor="            self.capability_enabled",
        new="            True",
        scope="            and bool(self.attach_without_representation)",
        offset=-3,
        want=f"{_FIN}::test_admitted_requires_all_four_signals",
        why="准入合取的第一项恒真 ⇒ capability 未启用也能准入（合取退化）",
        scope_check=_py_line_counts({"            self.capability_enabled": 0}),
    ),
    Mutation(
        id="M15",
        side="be",
        path=GATE,
        kind="replace",
        anchor="            and bool(self.attach_without_representation)",
        new="            and True",
        want=f"{_FIN}::test_admitted_requires_all_four_signals",
        why="准入不再要求生产接线点真返回 adapter_id ⇒ resolver 无 published representation 也算准入",
        scope_check=_py_line_counts({"            and True": 1}),
    ),
    Mutation(
        id="M16",
        side="be",
        path=GATE,
        kind="replace",
        # 🔴 重指锚点：状态敏感性判据的实现已是「任一方向翻转即算敏感」
        #    （`real.admitted != substituted.admitted`），原锚点 0 命中。变异形态与 want
        #    一字不改：把它写成恒真 `True`，硬编码 admitted 就能骗过敏感性探针。
        anchor="        flipped = real.admitted != substituted.admitted",
        new="        flipped = True",
        want=f"{_FIN}::test_a_hardcoded_admission_would_fail_the_state_sensitivity_probe",
        why="状态敏感性判据恒真 ⇒ 硬编码的 admitted 也能让 gate.admission_is_state_sensitive 变绿",
        scope_check=_py_line_counts({"        flipped = True": 1}),
    ),
    # ── ④ 判定顺序不可交换 ─────────────────────────────────────────────
    Mutation(
        id="M17",
        side="be",
        path=GATE,
        kind="replace",
        anchor="    if debt is not None:",
        new="    if False and debt is not None:",
        want=f"{_ORD}::test_upstream_gap_is_failed_not_unverifiable",
        wants=(
            f"{_ORD}::test_crossing_shape_debt_and_black_box_together_still_lands_on_upstream_gap",
            f"{_ORD}::test_counterfactual_without_debt_changes_the_verdict",
        ),
        why="upstream-gap 分支被跳过 ⇒ 缺实现的场景落 unverifiable，接上真实 OO 会自动刷绿",
        scope_check=_py_line_counts({"if False and debt is not None:": 1}),
    ),
    Mutation(
        id="M18",
        side="be",
        path=GATE,
        kind="replace",
        anchor='            scenario_id, spec.anchor, RESULT_FAILED, "upstream_gap",',
        new='            scenario_id, spec.anchor, RESULT_UNVERIFIABLE, "upstream_gap",',
        want=f"{_ORD}::test_upstream_gap_is_failed_not_unverifiable",
        why="upstream-gap 判成 unverifiable ⇒ 「缺的是实现不是环境」这条区分消失",
        scope_check=_py_line_counts(
            {'RESULT_UNVERIFIABLE, "upstream_gap",': 1}
        ),
    ),
    Mutation(
        id="M19",
        side="be",
        path=GATE,
        kind="replace",
        anchor='    if "pilot_not_admitted" in blocking:',
        new='    if False and "pilot_not_admitted" in blocking:',
        want=f"{_VAL}::test_no_probe_can_pass_on_the_real_unadmitted_pilots",
        why="准入门被跳过 ⇒ 未 finalize 的 pilot 只要给齐记录就能判 passed（任务正文第一句被绕过）",
        scope_check=_py_line_counts(
            {'if False and "pilot_not_admitted" in blocking:': 1}
        ),
    ),
    Mutation(
        id="M20",
        side="be",
        path=GATE,
        kind="replace",
        anchor='        blocking.append("real_black_box_not_executed")',
        new='        blocking.append("real_black_box_not_executed_typo")',
        want=f"{_REP}::test_blocking_conditions_keep_the_black_box_fact_visible",
        why="黑盒未执行这条事实的键被改名 ⇒ 计数丢失（判定只给一个 error_code，事实必须仍可计数）",
        scope_check=_py_line_counts({'"real_black_box_not_executed_typo"': 1}),
    ),
    Mutation(
        id="M21",
        side="be",
        path=GATE,
        kind="replace",
        anchor="        return self.onlyoffice_build != _not_executed()",
        new="        return True",
        want=f"{_REP}::test_environment_is_the_not_executed_sentinel_by_default",
        wants=(f"{_ORD}::test_black_box_probes_stay_unverifiable_even_when_the_pilot_is_admitted",),
        why="哨兵判定恒真 ⇒ 没有真实 OO 也被当成「已执行」，黑盒场景会自动刷绿",
        scope_check=_py_line_counts(
            {"        return True": 2, "return self.onlyoffice_build != _not_executed()": 0}
        ),
    ),
    # ── ⑤ 不得以文档声明通过 ───────────────────────────────────────────
    Mutation(
        id="M22",
        side="be",
        path=GATE,
        kind="replace",
        anchor="            if str(key).lower() in FORBIDDEN_RECORD_KEYS:",
        new="            if False and str(key).lower() in FORBIDDEN_RECORD_KEYS:",
        want=f"{_DOC}::test_every_burial_form_of_a_result_claim_is_rejected",
        wants=(f"{_DOC}::test_load_execution_records_rejects_a_claiming_file",),
        why="结果声明字段不再被拒 ⇒ 「我宣布这条过了」直接生效（AC 14.9 被绕过）",
        scope_check=_py_line_counts(
            {"if False and str(key).lower() in FORBIDDEN_RECORD_KEYS:": 1}
        ),
    ),
    Mutation(
        id="M23",
        side="be",
        path=GATE,
        kind="replace",
        anchor='            assert_records_carry_no_claim(value, where=f"{where}.{key}")',
        new="            pass",
        want=f"{_DOC}::test_every_burial_form_of_a_result_claim_is_rejected",
        why="不再递归进 dict ⇒ 深埋一层的 result 声明可以绕过（只测顶层的守卫会照绿）",
        scope_check=_py_line_counts(
            {"            pass": 2, 'assert_records_carry_no_claim(value, where=f"{where}.{key}")': 0}
        ),
    ),
    Mutation(
        id="M24",
        side="be",
        path=GATE,
        kind="replace",
        anchor='            assert_records_carry_no_claim(value, where=f"{where}[{index}]")',
        new="            continue",
        want=f"{_DOC}::test_every_burial_form_of_a_result_claim_is_rejected",
        why="不再递归进 list ⇒ 藏在数组里的 aggregate_result 可以绕过",
        scope_check=_py_line_counts(
            {
                "            continue": 6,
                'assert_records_carry_no_claim(value, where=f"{where}[{index}]")': 0,
            }
        ),
    ),
    Mutation(
        id="M25",
        side="be",
        path=GATE,
        kind="replace",
        anchor='    {"result", "verdict", "passed", "aggregate_result", "status", "outcome"}',
        new='    {"result", "verdict", "passed", "aggregate_result", "status"}',
        want=f"{_DOC}::test_forbidden_keys_cover_the_result_vocabulary",
        wants=(f"{_DOC}::test_every_burial_form_of_a_result_claim_is_rejected",),
        why="禁用键少一个 ⇒ `outcome: ok` 这种声明可以合法入库",
        scope_check=_py_line_counts({'"status", "outcome"}': 0}),
    ),
    Mutation(
        id="M26",
        side="be",
        path=GATE,
        kind="replace",
        anchor='    ok = all(v.startswith("rejected") for v in observed.values())',
        new="    ok = True",
        want=f"{_DOC}::test_the_probe_would_fail_if_the_refusal_stopped_working",
        why="拒绝自检恒真 ⇒ gate.no_documentary_pass 变成一句声明而不是真跑",
        scope_check=_py_line_counts({"    ok = True": 1}),
    ),
    # ── ⑥ validator 真判据（逐条） ─────────────────────────────────────
    Mutation(
        id="M27",
        side="be",
        path=GATE,
        kind="replace",
        anchor='        if str((m or {}).get("level", "")).lower() in {"error", "severe"}',
        new='        if str((m or {}).get("level", "")).lower() in {"severe"}',
        want=f"{_VAL}::test_a_broken_record_reaches_failed",
        why="console error 不再算失败 ⇒ 浏览器报错的 pilot 也能过（AC 14.8 的 console 通道失效）",
        scope_check=_py_line_counts({'in {"severe"}': 1}),
    ),
    Mutation(
        id="M28",
        side="be",
        path=GATE,
        kind="replace",
        anchor='    if str(record["clock_source"]) != "server":',
        new='    if False and str(record["clock_source"]) != "server":',
        want=f"{_VAL}::test_a_broken_record_reaches_failed",
        why="客户端时钟被接受 ⇒ AC 14.8 要求的「数据库时间」退化成任意时间源",
        scope_check=_py_line_counts(
            {'if False and str(record["clock_source"]) != "server":': 1}
        ),
    ),
    Mutation(
        id="M29",
        side="be",
        path=GATE,
        kind="replace",
        anchor="        if parsed.tzinfo is None:",
        new="        if False and parsed.tzinfo is None:",
        want=f"{_VAL}::test_naive_timestamps_are_rejected",
        why="naive 时间戳被接受 ⇒ 服务端时钟与客户端时钟无法区分",
        scope_check=_py_line_counts({"if False and parsed.tzinfo is None:": 1}),
    ),
    Mutation(
        id="M30",
        side="be",
        path=GATE,
        kind="replace",
        anchor='    if str(record["projection_sha256"]) != str(record["extracted_projection_sha256"]):',
        new='    if False and str(record["projection_sha256"]) != str(record["extracted_projection_sha256"]):',
        want=f"{_VAL}::test_a_broken_record_reaches_failed",
        why="materialize→extract 往返等值不再校验 ⇒ Property 29 的判据消失",
        scope_check=_py_line_counts(
            {'if False and str(record["projection_sha256"])': 1}
        ),
    ),
    Mutation(
        id="M31",
        side="be",
        path=GATE,
        kind="replace",
        anchor='    if str(record["authority_model_definition_sha256"]) != facts.authority_model_definition_sha256:',
        new='    if False and str(record["authority_model_definition_sha256"]) != facts.authority_model_definition_sha256:',
        want=f"{_VAL}::test_a_broken_record_reaches_failed",
        why="authority model digest 不再与现算值比对 ⇒ stale evidence 可以通过（AC 14.16 失效）",
        scope_check=_py_line_counts(
            {'if False and str(record["authority_model_definition_sha256"])': 1}
        ),
    ),
    Mutation(
        id="M32",
        side="be",
        path=GATE,
        kind="replace",
        anchor='        if str(got.get("type")) != "definition":',
        new='        if False and str(got.get("type")) != "definition":',
        want=f"{_VAL}::test_a_broken_record_reaches_failed",
        why="typed slot 的 type 不再校验 ⇒ marker 可以冒充 definition（AC 12.10 的 substrate 政策失效）",
        scope_check=_py_line_counts(
            {'if False and str(got.get("type")) != "definition":': 1}
        ),
    ),
    Mutation(
        id="M33",
        side="be",
        path=GATE,
        kind="replace",
        anchor='    if str(inventory["metadata_sheet"]) != ei.GT_SYNC_SHEET_NAME:',
        new='    if False and str(inventory["metadata_sheet"]) != ei.GT_SYNC_SHEET_NAME:',
        want=f"{_VAL}::test_a_broken_record_reaches_failed",
        why="metadata sheet 名不再与生产常量比对 ⇒ identity inventory 可以指向任意 sheet",
        scope_check=_py_line_counts(
            {'if False and str(inventory["metadata_sheet"])': 1}
        ),
    ),
    Mutation(
        id="M34",
        side="be",
        path=GATE,
        kind="replace",
        anchor="        ph.assert_no_reuse_within_run(observation=observation, recorded=recorded)",
        new="        recorded = recorded",
        want=f"{_VAL}::test_reused_application_ids_across_scenarios_are_rejected_by_production",
        why="不再委派生产的复用判据 ⇒ 一条 application 冒充多个 scenario 变成合法（Property 69/70）",
        scope_check=_py_line_counts({"        recorded = recorded": 1}),
    ),
    Mutation(
        id="M35",
        side="be",
        path=GATE,
        kind="replace",
        anchor="    if not before:",
        new="    if False and not before:",
        want=f"{_VAL}::test_a_broken_record_reaches_failed",
        why="空计数比对被放行 ⇒ 「完整复原」可以用零表证明（零场景全过的经典假绿）",
        scope_check=_py_line_counts({"if False and not before:": 1}),
    ),
    Mutation(
        id="M36",
        side="be",
        path=GATE,
        kind="replace",
        anchor="    if len(contributors) < 2:",
        new="    if len(contributors) < 1:",
        want=f"{_VAL}::test_a_broken_record_reaches_failed",
        why="一个 contributor 也算聚合 ⇒ AC 10.9 的「聚合 artifact」失去含义",
        scope_check=_py_line_counts({"if len(contributors) < 1:": 1}),
    ),
    Mutation(
        id="M37",
        side="be",
        path=GATE,
        kind="replace",
        anchor="    if initiator == route:",
        new="    if False and initiator == route:",
        want=f"{_VAL}::test_a_broken_record_reaches_failed",
        why="initiator 与 route credential 同值被放行 ⇒ route 被当成授权主体（AC 10.2 明禁）",
        scope_check=_py_line_counts({"if False and initiator == route:": 1}),
    ),
    Mutation(
        id="M38",
        side="be",
        path=GATE,
        kind="replace",
        anchor="    if not (fence_advanced and rotated):",
        new="    if False and not (fence_advanced and rotated):",
        want=f"{_VAL}::test_a_broken_record_reaches_failed",
        why="无法取证 OO drop 时不再要求 fence 提升 + generation 旋转（AC 10.4 原文）",
        scope_check=_py_line_counts(
            {"if False and not (fence_advanced and rotated):": 1}
        ),
    ),
    Mutation(
        id="M39",
        side="be",
        path=GATE,
        kind="replace",
        anchor="    if set(observed) != set(expected):",
        new="    if False and set(observed) != set(expected):",
        want=f"{_VAL}::test_a_broken_record_reaches_failed",
        why="close-capture 观测覆盖不全被放行 ⇒ 只测一条 close 路径也算 exactly-one 成立",
        scope_check=_py_line_counts({"if False and set(observed) != set(expected):": 1}),
    ),
    # ── ⑦ 阻断与报告闭合 ───────────────────────────────────────────────
    Mutation(
        id="M40",
        side="be",
        path=GATE,
        kind="replace",
        anchor="    return 0 if all(row.passed for row in rows) else 1",
        new="    return 0",
        want=f"{_BLK}::test_exit_code_helper_is_derived_from_rows_not_from_a_flag",
        wants=(f"{_BLK}::test_main_exits_non_zero_today",),
        why="退出码恒 0 ⇒ 有 probe 未通过也不阻断 Wave 5（本任务的核心交付被抽空）",
        scope_check=_py_line_counts(
            {"return 0 if all(row.passed for row in rows) else 1": 0}
        ),
    ),
    Mutation(
        id="M41",
        side="be",
        path=GATE,
        kind="replace",
        anchor="        return 2",
        new="        return 1",
        scope='        print(f"[FATAL] 门自身失效：{exc}")',
        offset=1,
        want=f"{_BLK}::test_structural_failure_exits_two_not_one",
        why="门自身失效与「有 probe 没通过」混为一码 ⇒ 「量不准了」被当成普通阻断",
        scope_check=_py_line_counts({"        return 1": 1, "        return 2": 1}),
    ),
    Mutation(
        id="M42",
        side="be",
        path=GATE,
        kind="replace",
        anchor="                if all(row.passed for row in pilot_rows)",
        new="                if True",
        want=f"{_REP}::test_no_pilot_is_verified_and_all_four_are_unverifiable",
        why="pilot 状态恒 verified ⇒ 四类 pilot 未 finalize 也宣称已验证（Property 49 反面）",
        scope_check=_py_line_counts({"                if True": 1}),
    ),
    Mutation(
        id="M43",
        side="be",
        path=GATE,
        kind="replace",
        anchor="                if results == {RESULT_PASSED}",
        new="                if RESULT_PASSED in results",
        want=f"{_PROP}::test_no_property_is_reported_as_passed_today",
        wants=(f"{_PROP}::test_property_verdict_is_the_worst_of_its_rows",),
        why="Property 结论取「有一条过就算过」⇒ 16 条 Property 会被部分刷绿",
        scope_check=_py_line_counts({"if RESULT_PASSED in results": 1}),
    ),
    Mutation(
        id="M44",
        side="be",
        path=GATE,
        kind="replace",
        anchor="    all_red = bool(report) and verdicts.get(\"RED\", 0) == len(report)",
        new="    all_red = bool(report)",
        want=f"{_PROP}::test_mutation_probe_rejects_a_non_red_verdict",
        why="变异四态里 GREEN/WRONG-TEST/ANCHOR-MISS 不再拦 ⇒ AC 14.7 的后三态失效",
        scope_check=_py_line_counts({"    all_red = bool(report)": 1}),
    ),
    Mutation(
        id="M45",
        side="be",
        path=GATE,
        kind="replace",
        anchor="    ok = declared > 0 and declared == executed and all_red",
        new="    ok = declared > 0 and all_red",
        want=f"{_PROP}::test_mutation_probe_requires_declared_equals_executed",
        why="declared != executed 不再拦 ⇒ 「已跑的全 RED」可以冒充全量（Task 43 的实测教训）",
        scope_check=_py_line_counts({"    ok = declared > 0 and all_red": 1}),
    ),
    Mutation(
        id="M46",
        side="be",
        path=GATE,
        kind="replace",
        anchor="    _ADMISSION_PROBES + _SCENARIO_PROBES + _CLOSE_ASPECT_PROBES + _CHANNEL_PROBES",
        new="    _ADMISSION_PROBES + _SCENARIO_PROBES + _CHANNEL_PROBES",
        want=f"{_LOCK}::test_probe_row_count_is_the_declared_product",
        wants=(f"{_LOCK}::test_generated_registry_data_file_is_fresh",),
        why="close 族的四条「同时核对」probe 被摘掉 ⇒ 42/pilot 缩成 38，分母静默缩小",
        scope_check=_py_line_counts(
            {"_ADMISSION_PROBES + _SCENARIO_PROBES + _CHANNEL_PROBES": 1}
        ),
    ),
    # ── ⑧ 生成数据文件与生成器 ─────────────────────────────────────────
    Mutation(
        id="M47",
        side="be",
        path=DATA,
        kind="replace",
        anchor='  "total_probe_rows": 173',
        new='  "total_probe_rows": 172',
        want=f"{_LOCK}::test_generated_registry_data_file_is_fresh",
        why="数据文件里的 probe 行数被改小 ⇒ 分母漂移必须被 --check 逐字节抓住",
        scope_check=_json_field_is(("total_probe_rows",), 172),
    ),
    Mutation(
        id="M48",
        side="be",
        path=DATA,
        kind="replace",
        anchor='      "anchor": "download-only 三实体为 0",',
        new='      "anchor": "download-only",',
        want=f"{_LOCK}::test_generated_registry_data_file_is_fresh",
        why="数据文件里的锚点被改宽 ⇒ 与 tasks.md 的逐字锁被削弱（改宽后正文改写也能命中）",
        scope_check=_json_probe_anchor_is(
            "scenario.download_only_zero_three_entities", "download-only"
        ),
    ),
    Mutation(
        id="M49",
        side="be",
        path=GEN,
        kind="replace",
        anchor="    if path.read_bytes() != data:",
        new="    if False and path.read_bytes() != data:",
        want=f"{_LOCK}::test_generated_registry_data_file_is_fresh",
        why="生成器 --check 不再比字节 ⇒ 数据文件可以任意漂移而门仍绿",
        scope_check=_py_line_counts({"if False and path.read_bytes() != data:": 1}),
    ),
]


def main() -> int:
    return run_cli(
        mutations=MUTATIONS,
        guard_files={
            T44: "Task 44 gate 守卫（probe 分母 / finalize 反读 / 顺序 / validator / 阻断）",
        },
        repo=REPO,
        description="Task 44 真实 OO 9.4 Excel pilot gate 守卫变异检验",
        backend_args=[
            f"backend/tests/workpaper_sync/{T44}",
            "-q",
            "-rfE",
            "-p",
            "no:randomly",
        ],
        baseline_backend_passed=111,
    )


if __name__ == "__main__":
    raise SystemExit(main())
