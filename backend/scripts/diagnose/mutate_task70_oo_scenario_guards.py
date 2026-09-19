"""任务 70 守卫的变异检验。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 7

═══ 为什么必须有这个脚本 ═══

「守卫写完就绿」不构成任何证据：本 spec 已三次实测「grep 式守卫」与「把错值当基线锁死」两类
缺陷。每写完一条守卫必须做变异检验 —— 改一字看它是否变红；**没打红 = 守卫有缺陷，不是代码
没问题**。

═══ 四态判定（只看退出码会把后三态误判成 RED）═══

* **RED** —— 打红了，且**正是**预期那条测试（`want` 命中）；
* **GREEN** —— 守卫缺陷（改了行为却没有任何判据变红）⇒ 修守卫，**不删变异**；
* **ANCHOR-MISS** —— 脚本缺陷：锚点未命中或命中 >1 处。含 `\\n` 的跨行锚点在 CRLF 文件上
  必 MISS，所以本脚本的锚点全部是**单行**片段；
* **WRONG-TEST** —— 打红了但不是预期项（污染残留或锚点错行）。

═══ 三条硬约束（各自都有实测代价）═══

1. **`want` 用短 nodeid 且目标不参数化**。BP-29：`_locate_want` 对 parametrize nodeid 恒误报。
   本脚本的每个 `want` 都指向一条无参数的测试方法。
2. **禁后台执行**。孤儿 python 进程会让复原失败（RestoreFailed rc=5）。本脚本全程前台。
3. **绝不 `--restore` 手工兜底**。复原由 `try/finally` 逐文件 md5 校验完成；收尾再全量校验一次。

用法::

    python backend/scripts/diagnose/mutate_task70_oo_scenario_guards.py --list
    python backend/scripts/diagnose/mutate_task70_oo_scenario_guards.py --run M01,M02,M03
    python backend/scripts/diagnose/mutate_task70_oo_scenario_guards.py --check-anchors
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

REPO: Final[Path] = Path(__file__).resolve().parents[3]

GATE_REL: Final[str] = "backend/scripts/check/check_task70_oo94_full_entry_scenario_gate.py"
GUARD_REL: Final[str] = "backend/tests/workpaper_sync_oo/test_task70_oo_scenario_gate.py"

CENSUS_LOCK_REL: Final[str] = "backend/scripts/_census_lock.py"
GUARD_TEST: Final[str] = GUARD_REL

#: census 判据已拆到独立守卫文件（宿主 1704 行 > 行数门禁）。它必须一起跑：那 6 条 census
#: 变异要打红的判据在那个文件里，漏掉就全变 WRONG-TEST（BP-74-4 同型：`want` 与实际位置脱钩）。
CENSUS_GUARD_REL: Final[str] = "backend/tests/workpaper_sync_oo/test_task70_census_lock.py"
TARGETS: Final[tuple[str, ...]] = (GUARD_TEST, CENSUS_GUARD_REL)


@dataclass(frozen=True)
class Mutation:
    """一条变异。

    :param scope: 锚点搜索的**函数/类名**。锚点用 `scope + offset` 定位，**禁绝对行号**
        （教训 8：绝对行号在任何一次编辑后全部失效）。
    :param anchor: 单行片段，必须在 `scope` 内**恰好命中一次**。
    :param replacement: 替换文本。
    :param want: 期望打红的**短** nodeid（不带参数化）。
    """

    mid: str
    file: str
    scope: str
    anchor: str
    replacement: str
    want: str
    why: str


MUTATIONS: Final[tuple[Mutation, ...]] = (
    # ── 分母类 ────────────────────────────────────────────────────────────
    Mutation(
        "M01",
        GATE_REL,
        "build_scenario_denominator",
        "harness.assert_oracle_registry_complete()",
        "pass  # mutated: 不再调生产双向锁",
        "TestScenarioDenominatorComesFromProduction::test_gate_really_calls_the_production_bidirectional_lock",
        "删掉对生产双向锁的真实调用 —— 分母与判定表脱钩时必须有判据变红",
    ),
    Mutation(
        "M02",
        GATE_REL,
        "build_scenario_denominator",
        '"oracle_count": len(oracles),',
        '"oracle_count": len(oracles) - 1,',
        "TestScenarioDenominatorComesFromProduction::test_oracle_count_matches_production_recomputed",
        "把 oracle 计数少报 1 —— 分母缩小必须被独立现算抓到",
    ),
    Mutation(
        "M03",
        GATE_REL,
        "build_scenario_denominator",
        '"black_box_scenario_ids": black_box,',
        '"black_box_scenario_ids": [],',
        "TestScenarioDenominatorComesFromProduction::test_black_box_set_matches_production_recomputed",
        "把黑盒场景集合清空 —— 「覆盖计数必须断言非空」（教训 6）",
    ),
    # ── 豁免互斥类 ────────────────────────────────────────────────────────
    Mutation(
        "M04",
        GATE_REL,
        "build_exemption_registry",
        "both = sorted(named & exempt)",
        "both = []  # mutated: 永不报「既点名又豁免」",
        "TestExemptionRegistryIsMutuallyExclusive::test_no_scenario_is_both_named_and_exempted",
        "短路 `both` 判据 —— 豁免变成装饰",
    ),
    Mutation(
        "M05",
        GATE_REL,
        "build_exemption_registry",
        "neither = sorted(produced - named - exempt)",
        "neither = []  # mutated: 永不报「既不点名又无豁免」",
        "TestExemptionRegistryIsMutuallyExclusive::test_no_scenario_is_neither_named_nor_exempted",
        "短路 `neither` 判据 —— 分母缩小无人管",
    ),
    Mutation(
        "M06",
        GATE_REL,
        "build_exemption_registry",
        'for field_name in ("owner_task", "why", "measured_from"):',
        'for field_name in ():  # mutated: 不再要求 owner/实测出处',
        "TestExemptionRegistryIsMutuallyExclusive::test_every_exemption_carries_owner_and_measured_source",
        "允许自由文本豁免（正文第三子条目明令禁止）",
    ),
    # ── close 门控类 ──────────────────────────────────────────────────────
    Mutation(
        "M07",
        GATE_REL,
        "build_close_gate",
        "evidence.close_scenarios_required(profile=profile, capability=capability)",
        "False  # mutated: 谓词恒假",
        "TestCloseGateIsRecomputedNotHardcoded::test_predicate_hits_recomputed_independently",
        "把 close 谓词改成恒假 —— 179 个 entry 会悄悄少八个场景",
    ),
    Mutation(
        "M08",
        GATE_REL,
        "build_close_gate",
        '"hits_missing_any_close_scenario": missing_close,',
        '"hits_missing_any_close_scenario": [],',
        "TestCloseGateIsRecomputedNotHardcoded::test_every_hit_carries_the_full_close_family",
        "隐藏「命中 entry 缺 close 场景」—— close 族缺失无人管",
    ),
    Mutation(
        "M09",
        GATE_REL,
        "_close_predicate_arm",
        "capability is Capability.bidirectional and profile.room_model is RoomModel.shared",
        "capability is Capability.bidirectional or profile.room_model is RoomModel.shared",
        "TestCloseGateIsRecomputedNotHardcoded::test_and_instead_of_or_would_lose_the_close_family",
        "把反事实臂 A5 的变异体改回 `or` —— 臂不再翻转结论，反事实退化成重言式",
    ),
    # ── 结果声明禁令类 ────────────────────────────────────────────────────
    Mutation(
        "M10",
        GATE_REL,
        "assert_no_result_declarations",
        "if key_text.lower() in FORBIDDEN_RECORD_KEYS:",
        "if False:  # mutated: 禁令失效",
        "TestScenarioExecutionRows::test_forbidden_key_scanner_actually_catches_a_planted_key",
        "让结果声明扫描器恒不命中 —— 「文档式声明通过」有了落脚点",
    ),
    Mutation(
        "M11",
        GATE_REL,
        "FORBIDDEN_RECORD_KEYS",
        '        "passed",',
        '        "PASSED_MUTATED",',
        "TestScenarioExecutionRows::test_forbidden_keys_include_the_real_targets",
        "把 `passed` 从禁令名单里换掉 —— 名单类判据必须写死真实目标（教训 16）",
    ),
    # ── 判定顺序类（本门最贵的一组）────────────────────────────────────────
    Mutation(
        "M12",
        GATE_REL,
        "classify_scenario_execution",
        "if scenario_id in evidence.SCHEMA_UNREPRESENTABLE_SCENARIOS:",
        "if False:  # mutated: schema 欠账不再优先",
        "TestClassificationOrderIsNotCommutable::test_schema_gap_wins_over_black_box",
        "把 schema 欠账从第一位摘掉 —— 它会被别的码遮住并显示成「环境缺失」",
    ),
    Mutation(
        "M13",
        GATE_REL,
        "classify_scenario_execution",
        "if oracle.upstream_debt:",
        "if False:  # mutated: 上游缺口不再 fail closed",
        "TestClassificationOrderIsNotCommutable::test_upstream_gap_wins_over_black_box",
        "上游实现缺口降级成环境缺失 ⇒ **接上 OO 就会自动变绿**，而它永远不会通过",
    ),
    Mutation(
        "M14",
        GATE_REL,
        "classify_scenario_execution",
        'row["blocked_by"] = "application_chain_unavailable"',
        'row["blocked_by"] = "real_onlyoffice_not_executed"  # mutated: 两码合并',
        "TestClassificationOrderIsNotCommutable::test_application_chain_is_a_distinct_code",
        "把第三第四条拒绝合成一个码 —— 靠后的那条永久不可达（教训 1）",
    ),
    Mutation(
        "M15",
        GATE_REL,
        "classify_scenario_execution",
        'row["execution_tier"] = TIER_EXECUTED',
        'row["execution_tier"] = TIER_UNRUNNABLE  # mutated: 永不 executed',
        "TestClassificationOrderIsNotCommutable::test_all_premises_present_yields_executed",
        "让分类器恒返 UNVERIFIABLE —— 这是本门最危险的恒真式，对照组必须先过（教训 5/15）",
    ),
    # ── 真实 OO 探测类 ────────────────────────────────────────────────────
    Mutation(
        "M16",
        GATE_REL,
        "probe_real_onlyoffice",
        '"jwt_signed_by": "app.services.workpaper_sync.command_service:sign_command_token",',
        '"jwt_signed_by": "self-rolled-pyjwt",',
        "TestRealOnlyOfficeProbe::test_probe_used_the_production_token_signer",
        "谎报签名来源 —— 自己拼 JWT 会漏 iat/exp 并把「OO 不可用」这个错误结论坐实",
    ),
    Mutation(
        "M17",
        GATE_REL,
        "probe_real_onlyoffice",
        '"forcesave_requires_live_editing_session": forcesave_row.get("error_code") == 1,',
        '"forcesave_requires_live_editing_session": False,',
        "TestRealOnlyOfficeProbe::test_forcesave_without_session_is_error_1",
        "谎报 forcesave 不需要活动会话 —— 会让黑盒缺口凭空消失并把全部场景刷成可跑",
    ),
    Mutation(
        "M18",
        GATE_REL,
        "probe_real_onlyoffice",
        # 该 raise 已被抽成**单行**（gate 里把长 message 抽成 `_OO_TRANSPORT_ERROR` 常量），
        # 因此整行替换不会造成语法错 ⇒ 不会落进「ERROR 被误判成 GREEN」那一态（教训 7）。
        "                raise Task70GateError(_OO_TRANSPORT_ERROR.format(label=label, shape=shape, exc=exc)) from exc",
        "                pass  # mutated: fail-open，传输失败被吞",
        "TestRealOnlyOfficeProbe::test_gate_does_not_swallow_container_errors",
        "把 OO 传输失败降级成「无数据」—— AC 5.12 明令禁止的 fail-open",
    ),
    # ── 供给链类 ──────────────────────────────────────────────────────────
    Mutation(
        "M19",
        GATE_REL,
        "walk_supply_chain",
        'first_block = next((step for step in steps if step["blocked_by"]), None)',
        "first_block = None  # mutated: 不再报第一处硬阻塞",
        "TestSupplyChainWalk::test_first_hard_stop_is_the_capability_adjudication",
        "隐藏第一处硬阻塞 —— 「卡在第几步」这条交代没了",
    ),
    Mutation(
        "M20",
        GATE_REL,
        "walk_supply_chain",
        '"accounting_identity_holds": (',
        '"accounting_identity_holds": True,  # mutated: 恒真\n                "_unused": (',
        "TestSupplyChainWalk::test_register_from_manifest_accounting_identity_holds",
        "把 planned = registered + reasons 改成恒真 —— 静默跳过 entry 测不出来（Property 62）",
    ),
    Mutation(
        "M21",
        GATE_REL,
        "walk_supply_chain",
        # 单行锚点（多行锚点在 CRLF 上必 ANCHOR-MISS，本脚本首轮实测踩到）。
        '        "S8",',
        '        "S8_renamed",',
        "TestSupplyChainWalk::test_both_first_version_sources_are_blocked_and_no_third_path_is_built",
        "改掉 S8 步骤 id —— 「两条首版来源都被挡住」这条实证找不到了",
    ),
    # ── 反事实 / 正向重算类 ────────────────────────────────────────────────
    Mutation(
        "M22",
        GATE_REL,
        "build_forward_recompute",
        '            row["expected_tier"] == TIER_EXECUTED for row in rows',
        "            False for row in rows  # mutated: 不再要求有正例",
        "TestCounterfactualAndForwardRecompute::test_forward_recompute_has_a_positive_case",
        "去掉「至少一条正例」的判据 —— 正向重算失去抓「恒真」的能力（教训 15）",
    ),
    Mutation(
        "M23",
        GATE_REL,
        "build_counterfactual_arms",
        '"conclusion_changes": tier_counts(oo_ok=True, browser_ok=True, chain_ok=False) != today,',
        '"conclusion_changes": False,',
        "TestCounterfactualAndForwardRecompute::test_arm_a3_proves_the_classifier_is_sensitive_to_black_box",
        "把 A3 臂的敏感性判据写死成 False —— 臂不再证明任何东西",
    ),
    # ── Property 落点类 ───────────────────────────────────────────────────
    Mutation(
        "M24",
        GATE_REL,
        "build_property_landings",
        "missing = sorted(set(DECLARED_PROPERTIES) - set(_PROPERTY_LANDINGS))",
        "missing = []  # mutated: 不再报缺落点",
        "TestPropertyLandings::test_all_29_declared_properties_have_a_landing",
        "隐藏缺失的 Property 落点 —— 「29 条逐条」退化成「有几条算几条」",
    ),
    Mutation(
        "M25",
        GATE_REL,
        "build_property_landings",
        "if row[\"tier\"] != \"executed\" and not str(row[\"owner_if_unverified\"]).strip()",
        "if False",
        "TestPropertyLandings::test_every_unverified_property_names_an_owner",
        "允许未验证的 Property 不点名 owner —— 正文明令要求「owner 是谁」",
    ),
    # ── 数据库只读类 ──────────────────────────────────────────────────────
    Mutation(
        "M26",
        GATE_REL,
        "_gather_db_facts",
        "if before_counts.get(table) == after_counts.get(table)",
        "if True",
        "TestDatabaseIsReadOnlyThisRound::test_zero_write_tables_unchanged",
        "把「前后行数相等」改成恒真 —— 悄悄写了库也报 0 行新增",
    ),
    Mutation(
        "M27",
        GATE_REL,
        "ZERO_WRITE_TABLES",
        '    "working_paper_entry_evidence_scenario",',
        '    "working_paper_sync_operation",  # mutated: 换掉 evidence scenario 表',
        "TestDatabaseIsReadOnlyThisRound::test_zero_write_tables_cover_the_real_evidence_tables",
        "从零写名单里删掉 evidence scenario 表 —— 缩小分母（教训 16）",
    ),
    # ── verdict / BP 类 ───────────────────────────────────────────────────
    Mutation(
        "M28",
        GATE_REL,
        "build_verdict",
        "elif executed == 0:",
        "elif False:  # mutated: 零场景不再判 unverifiable",
        "TestBlockingPointsAndVerdict::test_verdict_is_unverifiable_with_zero_executed",
        "让「零场景」不再触发 unverifiable —— 「零场景全过算通过」的经典假绿（Property 71）",
    ),
    Mutation(
        "M29",
        GATE_REL,
        "VERDICT_VOCABULARY",
        'VERDICT_VOCABULARY: Final[tuple[str, ...]] = ("refreshed", "failed", "unverifiable")',
        'VERDICT_VOCABULARY: Final[tuple[str, ...]] = ("refreshed", "failed", "unverifiable", "passed")',
        "TestBlockingPointsAndVerdict::test_verdict_vocabulary_has_no_passed",
        "给 verdict 词表加 `passed` —— 本门只有三态，加第四态就为「宣称通过」开了门",
    ),
    Mutation(
        "M30",
        GATE_REL,
        "BP_ID_PATTERN",
        'BP_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"BP-70-\\d+")',
        'BP_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r".*")',
        "TestBlockingPointsAndVerdict::test_every_blocking_point_id_matches_bp_70_n",
        "把 BP 编号锁放宽成 `.*` —— 编号规范失守",
    ),
    Mutation(
        "M31",
        GATE_REL,
        "build_blocking_points",
        '"id": "BP-70-2",',
        '"id": "BP70-2",',
        "TestBlockingPointsAndVerdict::test_every_blocking_point_id_matches_bp_70_n",
        "写错一个 BP 编号 —— 锁必须逐条命中而不是抽查",
    ),
    # ── body digest 归一化类 ──────────────────────────────────────────────
    Mutation(
        "M32",
        GATE_REL,
        "task_body",
        'body[0] = _CHECKBOX_RE.sub(r"\\1?\\2", body[0])',
        "pass  # mutated: 不再归一化复选框",
        "TestTaskBodyDigestIgnoresCheckboxState::test_checkbox_flip_does_not_change_body_digest",
        "去掉复选框归一化 —— 编排器翻牌就让本门假红（BP-70-6 的形态）",
    ),
    Mutation(
        "M33",
        GATE_REL,
        "VOLATILE_KEYS",
        '    {"generated_at", "elapsed_seconds", "wallclock_seconds", "probe_elapsed_seconds"}',
        '    {"generated_at", "elapsed_seconds", "wallclock_seconds", "probe_elapsed_seconds", "source_commit"}',
        "TestReportIsFreshAndByteLocked::test_volatile_keys_are_exactly_the_two_kinds",
        "把 source_commit 排除出逐字节比对 —— 源码漂移后报告仍「一致」，stale 轴失守",
    ),
    # ── 守卫落位类 ────────────────────────────────────────────────────────
    Mutation(
        "M34",
        GATE_REL,
        "radiation_surface",
        '"own_guard_outside_census_dir": True,',
        '"own_guard_outside_census_dir": False,',
        "TestGuardPlacement::test_report_records_the_placement_rationale",
        "谎报守卫落位 —— BP-69-6 的规避法失去可核对性",
    ),
    Mutation(
        "M35",
        GATE_REL,
        "git_porcelain",
        'if not (REPO / path).exists():',
        "if False:  # mutated: 不再区分「不在磁盘上」",
        "TestGuardPlacement::test_artifact_git_status_is_reported_for_every_product",
        "把「产物不存在」报成 tracked-clean —— CI 在干净 checkout 下必挂而报告说一切正常",
    ),
    # ── 普查免疫类（BP-71-8 的修复：普查派生量不进冻结基线，但仍现算断言语义）──────
    Mutation(
        "M36",
        CENSUS_LOCK_REL,
        "strip_census",
        "            if child in keys:",
        "            if False:  # mutated: 不再剔除普查派生量",
        "TestCensusLock::test_census_derived_quantities_are_excluded_from_the_byte_lock",
        "让 `strip_census` 不再剔除任何东西 —— 普查量重新进锁，仓库长大即打红（BP-71-8 复发）",
    ),
    Mutation(
        "M37",
        GATE_REL,
        "CENSUS_KEYS",
        '        "radiation_surface.scanned_test_files",',
        '        "radiation_surface.scanned_test_files_MUTATED",',
        "TestCensusLock::test_census_derived_quantities_are_excluded_from_the_byte_lock",
        "把全树计数从 census 名单里改名剔走 —— 名单类判据必须写死真实目标（教训 16）；"
        "它正是 BP-71-8 的根因字段",
    ),
    Mutation(
        "M38",
        GATE_REL,
        "CENSUS_KEYS",
        '        "census_contract.measured",',
        '        "census_contract.measured",\n        "radiation_surface.subject_coverage",',
        "TestCensusLock::test_census_derived_quantities_are_excluded_from_the_byte_lock",
        "把**选取契约**字段也剔进 census —— 剔多了会让「辐射面选取逻辑被改坏」一起被放过，"
        "这正是「不许整块剔掉 radiation_surface」那条约束",
    ),
    Mutation(
        "M39",
        CENSUS_LOCK_REL,
        "finalize_checks",
        '        "all_hold": all(checks.values()),',
        '        "all_hold": True,  # mutated: 语义断言恒真',
        "TestCensusLock::test_census_semantics_are_asserted_not_merely_skipped",
        "把普查语义断言改成恒真 —— 「剔除 ≠ 不管」退化成「不看了」，第 1 条修法失去意义",
    ),
    Mutation(
        "M40",
        GATE_REL,
        "radiation_surface",
        '"subject_coverage": coverage,',
        '"subject_coverage": {},  # mutated: 逐单元覆盖布尔清空',
        "TestCensusLock::test_census_semantics_are_asserted_not_merely_skipped",
        "把逐被验单元覆盖布尔清空 —— 空集恒真（`not uncovered` 对空字典成立），"
        "只有独立的 `subject_coverage_is_complete` 能抓到",
    ),
    Mutation(
        "M41",
        GATE_REL,
        "build_report",
        '        "census_contract": build_census_contract(surface),',
        "        # mutated: 报告里不再登记普查契约",
        "TestCensusLock::test_census_contract_declares_what_is_still_locked",
        "把普查契约节点从报告里摘掉 —— 「剔了什么 / 为什么 / 什么仍然锁死」无从复核",
    ),
)


# ════════════════════════════════════════════════════════════════════════════
# 定位与执行
# ════════════════════════════════════════════════════════════════════════════


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _scope_span(source: str, scope: str) -> tuple[int, int]:
    """`scope` 的行区间。

    支持三种 scope：`def name` / `class name` / 模块级常量 `NAME`。
    区间到**下一个同缩进或更浅缩进**的定义/常量为止。
    """
    lines = source.split("\n")
    patterns = (
        rf"^(\s*)(?:async\s+)?def\s+{re.escape(scope)}\s*\(",
        rf"^(\s*)class\s+{re.escape(scope)}\b",
        rf"^(\s*){re.escape(scope)}\s*[:=]",
    )
    start = None
    indent = ""
    for index, line in enumerate(lines):
        for pattern in patterns:
            match = re.match(pattern, line)
            if match:
                start = index
                indent = match.group(1)
                break
        if start is not None:
            break
    if start is None:
        raise LookupError(f"scope {scope!r} 未找到")
    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if not line.strip():
            continue
        current = line[: len(line) - len(line.lstrip())]
        if len(current) <= len(indent) and re.match(
            r"^\s*(?:async\s+def|def|class|[A-Z_][A-Z0-9_]*\s*[:=]|@)", line
        ):
            end = index
            break
    return start, end


def read_source(path: Path) -> str:
    """读源码。**不走 `read_text`** —— 它做换行翻译，写回时 `\\n` 会变 `\\r\\n`，
    于是逐文件 md5 复原校验必定失败（本脚本首轮实测 RestoreFailed rc=5，而文件内容其实没坏）。
    """
    return path.read_bytes().decode("utf-8")


def write_source(path: Path, text: str) -> None:
    """写源码，字节级，不做换行翻译。"""
    path.write_bytes(text.encode("utf-8"))


def locate(mutation: Mutation) -> tuple[Path, str, str]:
    """定位并生成变异后的源码。命中数 != 1 一律 ANCHOR-MISS。"""
    path = REPO / mutation.file
    source = read_source(path)
    start, end = _scope_span(source, mutation.scope)
    lines = source.split("\n")
    region = "\n".join(lines[start:end])
    hits = region.count(mutation.anchor)
    if hits != 1:
        raise LookupError(
            f"锚点在 scope {mutation.scope!r} 内命中 {hits} 次（要求恰 1）: "
            f"{mutation.anchor[:70]!r}"
        )
    mutated_region = region.replace(mutation.anchor, mutation.replacement, 1)
    mutated = "\n".join(lines[:start] + mutated_region.split("\n") + lines[end:])
    return path, source, mutated


def check_anchors() -> int:
    """只读锚点体检 —— 「已归档的变异集是否还可复现」的最便宜判据。"""
    bad: list[str] = []
    for mutation in MUTATIONS:
        try:
            locate(mutation)
        except LookupError as exc:
            bad.append(f"  {mutation.mid}  {exc}")
    print(f"[任务70变异] 锚点体检 {len(MUTATIONS) - len(bad)}/{len(MUTATIONS)} 命中")
    for line in bad:
        print(line)
    return 1 if bad else 0


def run_pytest(want: str) -> tuple[int, str]:
    """跑守卫文件并只看 `want` 是否红。**不经 shell**（`-k "a or b"` 会被拆成位置参数）。"""
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            *TARGETS,
            "-q",
            "--no-header",
            "-p",
            "no:cacheprovider",
            "--tb=no",
            "-rfE",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=1800,
        check=False,
    )
    return int(proc.returncode), proc.stdout + proc.stderr


def classify(output: str, want: str) -> str:
    """四态判定。

    🔴 只看退出码会把 GREEN / ANCHOR-MISS / WRONG-TEST 全误判成 RED。这里逐行读 `-rfE` 的
    FAILED/ERROR 清单：**ERROR 也算命中**（多行 `raise` 被整行替换会造成语法错 ⇒ ERROR，
    而 `-rf` 只列 FAILED ⇒ 会被误判成 GREEN，教训 7）。
    """
    reds: set[str] = set()
    for line in output.split("\n"):
        match = re.match(r"^(?:FAILED|ERROR)\s+(\S+)", line.strip())
        if match:
            reds.add(match.group(1).replace("\\", "/"))
    want_norm = want.replace("\\", "/")
    hit = any(want_norm in nodeid for nodeid in reds)
    if hit:
        return "RED"
    if reds:
        return "WRONG-TEST"
    return "GREEN"


def run(selected: list[str]) -> int:
    chosen = [m for m in MUTATIONS if m.mid in selected] if selected != ["all"] else list(MUTATIONS)
    unknown = sorted(set(selected) - {m.mid for m in MUTATIONS} - {"all"})
    if unknown:
        print(f"[任务70变异] 未知变异号: {unknown}", file=sys.stderr)
        return 2

    baseline = {rel: md5(REPO / rel) for rel in {GATE_REL, GUARD_REL} | {m.file for m in chosen}}
    verdicts: dict[str, str] = {}
    for mutation in chosen:
        try:
            path, original, mutated = locate(mutation)
        except LookupError as exc:
            verdicts[mutation.mid] = f"ANCHOR-MISS  {exc}"
            print(f"  {mutation.mid}  ANCHOR-MISS  {exc}")
            continue
        try:
            write_source(path, mutated)
            _, output = run_pytest(mutation.want)
            state = classify(output, mutation.want)
        finally:
            write_source(path, original)
            restored = md5(path)
            if restored != baseline[mutation.file]:
                print(
                    f"[任务70变异] 🔴 {mutation.mid} 复原失败: {mutation.file} md5 "
                    f"{restored} != {baseline[mutation.file]}",
                    file=sys.stderr,
                )
                return 5
        verdicts[mutation.mid] = state
        print(f"  {mutation.mid}  {state:<12} want={mutation.want.split('::')[-1]}")

    for rel_path, expected in baseline.items():
        actual = md5(REPO / rel_path)
        if actual != expected:
            print(f"[任务70变异] 🔴 收尾 md5 不符: {rel_path}", file=sys.stderr)
            return 5

    non_red = {mid: state for mid, state in verdicts.items() if state != "RED"}
    print(
        f"\n[任务70变异] RED {sum(1 for s in verdicts.values() if s == 'RED')}/{len(verdicts)}"
        f"；逐文件 md5 复原已校验"
    )
    if non_red:
        print(f"[任务70变异] 非 RED: {non_red}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="任务 70 守卫变异检验")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--list", action="store_true")
    mode.add_argument("--run", type=str, help="逗号分隔的变异号，或 all")
    mode.add_argument("--check-anchors", action="store_true")
    args = parser.parse_args(argv)

    if args.list:
        print(f"[任务70变异] 共 {len(MUTATIONS)} 条")
        for mutation in MUTATIONS:
            print(f"  {mutation.mid}  {mutation.scope:<34} {mutation.why}")
        return 0
    if args.check_anchors:
        return check_anchors()
    return run([part.strip() for part in str(args.run).split(",") if part.strip()])


if __name__ == "__main__":
    raise SystemExit(main())
