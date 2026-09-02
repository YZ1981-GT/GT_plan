# -*- coding: utf-8 -*-
"""任务 72 Stage A 守卫的变异检验。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 7

═══ 为什么必须有这个脚本 ═══

「守卫写完就绿」不构成任何证据。本 spec 已多次实测两类缺陷：**grep 式守卫只查字符串存在**、
**把错值当基线锁死**。每写完一条守卫必须做变异检验 —— 改一字看它是否变红；**没打红 = 守卫有
缺陷，不是代码没问题**。

本门还有一类专属风险：**恒红门**。Stage A 今天为红，一个把结论写死成红的门也「看起来对」。
因此变异集里专门有几条把「门能变绿」这件事打掉（M11/M12/M13），它们必须打红。

═══ 四态判定（只看退出码会把后三态误判成 RED）═══

* **RED** —— 打红了，且**正是**预期那条测试（`want` 命中）；
* **GREEN** —— 守卫缺陷（改了行为却没有任何判据变红）⇒ 修守卫，**不删变异**；
* **ANCHOR-MISS** —— 脚本缺陷：锚点未命中或命中 >1 处。含 `\\n` 的跨行锚点在 CRLF 文件上
  必 MISS，所以本脚本的锚点全部是**单行**片段；
* **WRONG-TEST** —— 打红了但不是预期项（污染残留或锚点错行）。

**ERROR 也算命中**：多行 `raise` 被整行替换会造成语法错 ⇒ pytest 报 ERROR，而 `-rf` 只列
FAILED ⇒ 会被误判成 GREEN。本脚本用 `-rfE` 并同时读两类行。

═══ 三条硬约束 ═══

1. **`want` 用短 nodeid 且目标不参数化**（BP-29：`_locate_want` 对 parametrize nodeid 恒误报）。
2. **禁后台执行**：孤儿进程会让复原失败。全程前台。
3. **绝不 `--restore` 手工兜底**：复原由 `try/finally` 逐文件 md5 校验完成，收尾再全量校验。
   源码读写一律走 `read_bytes`/`write_bytes` —— `read_text` 的换行翻译会让 md5 复原校验必失败。

🔴 **本脚本变异的是门与守卫的源码，不碰报告 JSON**：报告是 `--write` 的产物，改它只会让
`--check` 打红一条（信息量 = 0），而我们要测的是**判据**是否有效。

用法::

    python backend/scripts/diagnose/mutate_task72_pre_delete_eligibility_guards.py --list
    python backend/scripts/diagnose/mutate_task72_pre_delete_eligibility_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_task72_pre_delete_eligibility_guards.py --run all
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

GATE_REL: Final[str] = "backend/scripts/check/check_task72_pre_delete_eligibility_gate.py"
GUARD_REL: Final[str] = (
    "backend/tests/workpaper_sync_predelete/test_task72_pre_delete_eligibility.py"
)
GUARD_TEST: Final[str] = GUARD_REL


@dataclass(frozen=True)
class Mutation:
    """一条变异。

    :param scope: 锚点搜索的**函数/类名**或模块级常量名。锚点用 `scope + 单行片段`定位，
        **禁绝对行号**（绝对行号在任何一次编辑后全部失效）。
    :param anchor: 单行片段，必须在 `scope` 内**恰好命中一次**。
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
    # ── ① vacuous zero 判据（本门最容易被做成假绿的一条）──────────────────
    Mutation(
        "M01",
        GATE_REL,
        "count_admissibility",
        '        "admissible": bool(zero and not denominator_empty),',
        '        "admissible": bool(zero),  # mutated: 空分母下的 0 也算达标',
        "TestVacuousZeroIsNotAdmissible::test_zero_with_empty_denominator_is_rejected",
        "空集恒真放行 —— `evidence stale=0` 会因为「没有 evidence 可以过期」被当成已刷新，"
        "Stage A 少一条红（假绿第⑥源的直接落脚点）",
    ),
    Mutation(
        "M02",
        GATE_REL,
        "count_admissibility",
        "    elif denominator_empty:",
        "    elif False:  # mutated: 不再区分 vacuous 与真清零",
        "TestVacuousZeroIsNotAdmissible::test_zero_with_empty_denominator_is_rejected",
        "reason 词表塌成两态 —— 报告读者无法区分「真清零」与「分母为空」。"
        "🔴 刻意打**分支本身**而不是那行 `admissible`：两条独立的失守路径都要有落点",
    ),
    Mutation(
        "M03",
        GATE_REL,
        "build_five_counts",
        "            value=recomputed_primary[\"evidence_stale\"], denominator=stale_measurable",
        "            value=recomputed_primary[\"evidence_stale\"], denominator=len(independent)",
        "TestVacuousZeroIsNotAdmissible::test_evidence_stale_today_is_the_vacuous_kind",
        "把 evidence stale 的分母偷换成 entry 总数 —— 分母立刻非空，vacuous zero 变成"
        "「可采纳的 0」，Stage A 凭空少一条红。这是本门最贵的一种偷渡",
    ),
    # ── ② Stage A 谓词词表封闭（AC 12.13 的两条禁令）─────────────────────
    Mutation(
        "M04",
        GATE_REL,
        "stage_a_state",
        "    if got != want:",
        "    if False:  # mutated: 谓词集合不再受词表约束",
        "TestStageAPredicateVocabulary::test_extra_predicate_raises_instead_of_silently_concluding",
        "词表校验失守 —— 偷偷加一条（unreachable=0）或摘掉一条（evidence stale）都能静静算出"
        "一个更好看的结论",
    ),
    Mutation(
        "M05",
        GATE_REL,
        "STAGE_A_PREDICATE_IDS",
        '    "deletion_plan_is_current_with_head",',
        '    "deletion_plan_is_current_with_head",\n    "pending_delete_unreachable_is_zero",',
        "TestStageAPredicateVocabulary::test_stage_a_never_requires_unreachable_to_be_zero",
        "往 Stage A 词表里加「待删 unreachable 已为 0」—— AC 12.13 逐字禁止，加上即让删除门"
        "永久不可达（要删的东西必须先不存在）",
    ),
    Mutation(
        "M06",
        GATE_REL,
        "stage_a_vocabulary_excludes_unreachable_zero",
        '        pid for pid in ids if "unreachable" in pid and ("zero" in pid or "cleared" in pid)',
        "        pid for pid in ids if False  # mutated: 不再检出 unreachable-zero 谓词",
        "TestStageAPredicateVocabulary::test_stage_a_never_requires_unreachable_to_be_zero",
        "检出器恒空 —— 词表里真加了 unreachable-zero 也报「合规」（判据退化成重言式）。"
        "🔴 首版函数零参、判据只查真词表，实测 **GREEN**：真词表本来就干净 ⇒ 检出器坏掉与合规"
        "长得一样。改成吃 `predicate_ids` + 守卫喂含违规 id 的合成词表后转 RED",
    ),
    # ── ③ required scenario 执行档（Stage A 最重的一条红）─────────────────
    Mutation(
        "M07",
        GATE_REL,
        "family_execution_state",
        '        "really_executed": bool(total > 0 and executed == total),',
        '        "really_executed": True,  # mutated: 一律算跑过',
        "TestStageAIsRedTodayWithAttribution::test_empty_scenario_family_is_not_a_pass",
        "「零场景全部通过」被当成通过 —— 3290 行一条没跑却报 Stage A 可放行",
    ),
    Mutation(
        "M08",
        GATE_REL,
        "EXECUTED_TIERS",
        'EXECUTED_TIERS: Final[frozenset[str]] = frozenset({"executed_end_to_end"})',
        'EXECUTED_TIERS: Final[frozenset[str]] = frozenset({"executed_end_to_end", "unrunnable_today"})',
        "TestStageAIsRedTodayWithAttribution::test_named_required_scenarios_are_recomputed_not_read_from_verdict",
        "把「今天跑不了」算进已执行档 —— 环境不具备被重命名成已验收，正是 Task 70 forbidden "
        "claim 里点名禁止的那种偷渡",
    ),
    Mutation(
        "M09",
        GATE_REL,
        "NAMED_REQUIRED_SCENARIOS",
        '    "quarantined_rejects_application_and_engine",',
        "    # mutated: 摘掉 quarantined 这条点名 scenario",
        "TestStageAIsRedTodayWithAttribution::test_named_required_scenarios_are_recomputed_not_read_from_verdict",
        "缩小分母 —— 正文逐字点名的五类少一类，「任一未执行即 UNVERIFIABLE」被架空",
    ),
    Mutation(
        "M10",
        GATE_REL,
        "scenario_counts_agree",
        "        recomputed_rows == self_reported_rows and recomputed_executed == self_reported_executed",
        "        True  # mutated: 两侧漂移不再报",
        "TestStageAIsRedTodayWithAttribution::test_scenario_agreement_really_reports_a_mismatch",
        "跨文件双向锁失效 —— 现算与 Task 70 自述漂移时不再报，「我复核过」变成一句话。"
        "🔴 首版把变异打在报告字段的构造上、判据只断言「今天一致」，实测 **GREEN**：今天两侧本来"
        "就一致 ⇒ 写死与真算等价。改成打**纯函数体** + 守卫喂不一致输入后转 RED",
    ),
    # ── ④ 门必须能变绿（恒红门与恒绿门一样没有信息量）────────────────────
    Mutation(
        "M11",
        GATE_REL,
        "stage_a_state",
        '    return "green" if all(bool(v) for v in predicates.values()) else "red"',
        '    return "red"  # mutated: 恒红',
        "TestStageAIsNotPermanentlyRed::test_all_green_input_returns_green",
        "把结论写死成红 —— 世界变好了门也不会变绿，等于放弃判据（假绿第③源的镜像）",
    ),
    Mutation(
        "M12",
        GATE_REL,
        "build_counterfactual_arms",
        "    green_state = state_fn(all_green)",
        '    green_state = "green"  # mutated: 不真跑全绿探针',
        "TestStageAIsNotPermanentlyRed::test_report_records_the_sensitivity",
        "全绿探针不再真跑 —— 「本门会变绿」从实测降级成声明。"
        "🔴 打**探针本身**而不是那行 `gate_can_go_green`：把字段写死成 True 是等价变异。"
        "首版实测 **GREEN**（判据只读报告字段，而今天探针本来就返回 green）；补 `state_fn` 注入口 + "
        "守卫喂恒红实现后转 RED",
    ),
    Mutation(
        "M13",
        GATE_REL,
        "stage_a_state",
        '    return "green" if all(bool(v) for v in predicates.values()) else "red"',
        '    return "green" if all(\n'
        '        bool(v)\n'
        '        for pid, v in predicates.items()\n'
        '        if pid != "evidence_stale_is_admissibly_zero"\n'
        '    ) else "red"  # mutated: 让一条谓词不参与结论',
        "TestStageAIsNotPermanentlyRed::test_every_predicate_alone_can_turn_it_red",
        "让 `evidence_stale` 那条谓词**不参与**结论 —— 词表校验仍通过、全绿仍返回 green，只有"
        "「每条谓词单独为假都要能翻红」这条测得出来。这就是 additive 死判据（假绿第①源）的形态。"
        "🔴 首版本条曾设计成「把守卫自己的断言改弱成重言式」，实测 **GREEN** —— 改弱断言**不可能**"
        "让通过的测试失败，那是等价变异、脚本缺陷，不是守卫缺陷。教训：反向变异要打**被判据的"
        "主体**（这里是 `stage_a_state` 的谓词参与面），不能打断言本身",
    ),
    # ── ⑤ 待删项唯一命中的四个维度 ────────────────────────────────────────
    Mutation(
        "M14",
        GATE_REL,
        "pending_delete_landing_verdict",
        "    if not rollback_recoverable:",
        "    if False:  # mutated: rollback 不可回滚也算唯一命中",
        "TestPendingDeleteLanding::test_all_four_dimensions_are_load_bearing",
        "rollback 维度失守 —— 22 个替代面未入库 + 2 个待删项不可回滚的今天，Stage A 会凭空变绿"
        "一条谓词，而删除一旦执行不可逆",
    ),
    Mutation(
        "M15",
        GATE_REL,
        "pending_delete_landing_verdict",
        "    if plan_item_count_for_subject != 1:",
        "    if plan_item_count_for_subject == 0:  # mutated: 只查计划外，不查重复命中",
        "TestPendingDeleteLanding::test_all_four_dimensions_are_load_bearing",
        "「唯一」退化成「存在」—— 一个 subject 被两条计划项认领时 Stage B 不知道删哪份",
    ),
    Mutation(
        "M16",
        GATE_REL,
        "pending_delete_landing_verdict",
        "    if not digest_matches_disk:",
        "    if False:  # mutated: digest 漂移不再报",
        "TestPendingDeleteLanding::test_all_four_dimensions_are_load_bearing",
        "计划 stale 不再被抓 —— 按过期计划删就是删了没审过的内容",
    ),
    Mutation(
        "M17",
        GATE_REL,
        "build_pending_delete_landing",
        "        if _git([\"ls-files\", \"--error-unmatch\", str(row.get(\"path\"))]).returncode != 0",
        "        if row.get(\"tracked_in_git\") is False  # mutated: 读登记值而不是现测",
        "TestPendingDeleteLanding::test_untracked_measurement_provenance_is_git_not_the_upstream_field",
        "把「现测 git」换成「读 Task 66 的登记自述」—— 上游登记一旦过期，本门跟着错，"
        "而且这正是「独立复核」两个字被架空的形态。"
        "🔴 今天两个来源给出同一个数（22 == 22）⇒ 数值判据测不出差别（首版实测 GREEN / 只打红逐"
        "字节锁）。判据改落在**取值出处**上，用 AST 判 `_git([\"ls-files\", ...])` 是否真被调用",
    ),
    # ── ⑥ Stage B 反证与 AST 边界 ─────────────────────────────────────────
    Mutation(
        "M18",
        GATE_REL,
        "scan_source_boundary",
        "        if attr in _DELETE_CALLS:",
        "        if False:  # mutated: 无歧义删除原语不再检出",
        "TestStageBWasNotExecuted::test_delete_primitive_detector_actually_fires",
        "删除原语检测器恒空 —— 「本门没删」这条反证退化成重言式（假绿第②源的 AST 版本）",
    ),
    Mutation(
        "M19",
        GATE_REL,
        "_DELETE_CALLS",
        '_DELETE_CALLS: Final[frozenset[str]] = frozenset({"unlink", "rmdir", "rmtree", "removedirs"})',
        '_DELETE_CALLS: Final[frozenset[str]] = frozenset({"unlink", "rmdir", "rmtree", "removedirs", "replace"})',
        "TestStageBWasNotExecuted::test_str_replace_is_not_mistaken_for_a_delete_primitive",
        "🔴 **回归变异**：把首版那条假红（`str.replace` 被当成删除原语）放回去。守卫必须记住"
        "这个坑，否则下一个人会再踩一次",
    ),
    Mutation(
        "M20",
        GATE_REL,
        "build_stage_b",
        "    disk_untouched = not unexplained_drift and not unexplained_missing",
        "    disk_untouched = True  # mutated: 磁盘反证写死成真",
        "TestStageBWasNotExecuted::test_disk_still_matches_the_plan_digests",
        "磁盘反证写死成真 —— 「没删」从实测降级成自述，而这是 Stage B 唯一的客观证据。"
        "🔴 2026-09-02 重锚：`disk_untouched` 的算式随 out-of-band 登记改写成单行"
        "（原锚点 `    disk_untouched = (` 在 scope 内命中 0 次 ⇒ ANCHOR-MISS）。变异语义不变："
        "仍然是把这一条结论写死",
    ),
    # ── ⑦ Stage D 的「未运行 ≠ 静默 skip」────────────────────────────────
    Mutation(
        "M21",
        GATE_REL,
        "stage_d_run_decision",
        "    return STAGE_D_NOT_RUN",
        '    return "skipped"  # mutated: 引入静默 skip 态',
        "TestStageDDistinguishesNotRunFromSkip::test_run_decision_has_no_skip_state",
        "引入 `skipped` 态 —— 正文逐字「禁止静默 skip」；有理由的未运行与没理由的缺席被合成一档",
    ),
    Mutation(
        "M22",
        GATE_REL,
        "build_stage_d",
        '            "run": False,',
        '            "run": True,  # mutated: 声称最终门已运行',
        "TestStageDDistinguishesNotRunFromSkip::test_all_six_final_gates_are_recorded_as_not_run_with_a_reason",
        "Stage A 红却声称六个最终门都跑过 —— 归档条件被伪造",
    ),
    # ── ⑧ multi_resolver 准则的两个条件 ──────────────────────────────────
    Mutation(
        "M23",
        GATE_REL,
        "multi_resolver_criterion_passes",
        "    return len(multi_resolver_rows) == 0 and not list(rows_still_deferred)",
        "    return len(multi_resolver_rows) == 0  # mutated: 不再要求行已不是 deferred",
        "TestStageAIsRedTodayWithAttribution::test_multi_resolver_criterion_needs_both_conditions",
        "只查计数不查登记状态 —— 正文逐字「任一行仍 deferred 或计数非零则本门不过」的后半条失守",
    ),
    Mutation(
        "M24",
        GATE_REL,
        "resolver_matrix_facts",
        '        and "onlyoffice_router" in str(row.get("module"))',
        "        # mutated: 不再按 module 收窄",
        "TestStageAIsRedTodayWithAttribution::test_matrix_reader_narrows_by_module_not_just_by_name",
        "同名函数跨 module 混入 —— 四行的身份不再唯一，`status` 读到别的模块那一行。"
        "🔴 今天没有别的 module 有这些同名函数 ⇒ 去掉收窄是等价变异（首版实测 GREEN）。判据改成"
        "喂**植入矩阵**，且植入行的顺序必须让「真身在前、冒充者在后」—— 反过来时 dict 推导保留"
        "最后一次赋值，去掉收窄也会碰巧取对（第二轮实测）",
    ),
    # ── ⑨ 上游产物零改动 + 声明落位 ──────────────────────────────────────
    Mutation(
        "M25",
        GATE_REL,
        "git_porcelain",
        "        if not (REPO / path).exists():",
        "        if False:  # mutated: 不再先判存在",
        "TestDeclarationsAndPlacement::test_artifact_git_status_distinguishes_missing_from_clean",
        "「产物还没写出来」被报成 `tracked-clean` —— 挂进 CI 的 job 在干净 checkout 下必挂而报告"
        "里看不出来",
    ),
    Mutation(
        "M26",
        GATE_REL,
        "assert_property_tier",
        "    if tier not in PROPERTY_TIERS:",
        "    if False:  # mutated: 档位不再受词表约束",
        "TestDeclarationsAndPlacement::test_property_tier_vocabulary_rejects_free_text",
        "档位词表失守 —— 自由文本档位（如「已覆盖」）可以充当验证结论。"
        "🔴 首版把校验内联在 `build_property_landings` 的循环里、判据只断言「今天全部合规」，"
        "实测 **GREEN**：全合规时校验有没有都一样。抽成吃一个字符串的函数 + 守卫喂违规值后转 RED",
    ),
    Mutation(
        "M27",
        GATE_REL,
        "build_verdict",
        "    if not arms[\"gate_can_go_green\"]:",
        "    if False:  # mutated: 恒红门不再算结构错误",
        "TestUpstreamArtifactsAreUntouched::test_verdict_really_catches_an_ever_red_gate",
        "恒红门不再被 verdict 抓 —— 结构错误清零，报告看起来一切正常。"
        "🔴 首版判据只断言「今天结构错误为 0」，实测 GREEN：今天门本来就能变绿 ⇒ 那条分支从不"
        "触发。改成喂一份 `gate_can_go_green=False` 的合成报告后转 RED",
    ),
    Mutation(
        "M28",
        GATE_REL,
        "task_body",
        "    body[0] = _CHECKBOX_RE.sub(r\"\\1?\\2\", body[0])",
        "    body[0] = body[0]  # mutated: 不再归一化复选框",
        "TestReportIsFreshAndByteLocked::test_checkbox_flip_does_not_change_body_digest",
        "复选框不归一化 —— 编排器把 `[-]` 勾成 `[x]` 就打红逐字节锁而正文零变化（BP-70-6 复现）",
    ),
    Mutation(
        "M29",
        GATE_REL,
        "VOLATILE_KEYS",
        'VOLATILE_KEYS: Final[frozenset[str]] = frozenset({"generated_at", "elapsed_seconds"})',
        'VOLATILE_KEYS: Final[frozenset[str]] = frozenset({"generated_at", "elapsed_seconds", "source_commit"})',
        "TestReportIsFreshAndByteLocked::test_source_commit_is_not_excluded_from_the_lock",
        "把 source_commit 排除出锁 —— 源码漂移后报告仍逐字节相等，stale 轴的唯一锁失守",
    ),
    Mutation(
        "M30",
        GATE_REL,
        "build_five_counts",
        "    independent = [row for row in entries if row.get(\"independent_entry\")]",
        "    independent = list(entries)  # mutated: 父入口重复计数",
        "TestStageAIsRedTodayWithAttribution::test_five_counts_recompute_agrees_with_task67",
        "父入口重复计数 —— 正文「父入口不重复计数」失守，主口径分母被放大 44",
    ),
    # ── ⑧ out-of-band 移除登记（2026-09-02 新增，Task 74 会话内的用户点名清理）────
    #
    # 登记的存在意义是「解释一条计划内路径为什么已经不在盘上」，绝不是「往列表里加一行就变绿」。
    # 这两条变异各打掉登记的一半校验：M31 打「盘上还在就不算移除」，M32 打「必须落在计划里」。
    # 任一条变成 GREEN，就说明 `OUT_OF_BAND_REMOVALS` 已经退化成豁免列 —— 与本 spec 反复拒绝的
    # 「加豁免列」逐字同型。
    Mutation(
        "M31",
        GATE_REL,
        "validate_out_of_band_removals",
        '        if (REPO / path).exists():',
        "        if False:  # mutated: 盘上还在的路径也算「已 out-of-band 移除」",
        "TestStageBWasNotExecuted::test_planting_an_unrelated_path_in_the_registry_still_turns_the_proof_red",
        "登记不再核验「这条路径真的已经不在盘上」⇒ 把任何一条还在盘上的待删路径塞进登记即可让"
        "它从「磁盘未动」的反证里消失。这就是给 Stage B 的唯一客观证据开后门",
    ),
    Mutation(
        "M32",
        GATE_REL,
        "validate_out_of_band_removals",
        "        if path not in pending:",
        "        if False:  # mutated: 计划外路径也可以登记",
        "TestStageBWasNotExecuted::test_planting_an_unrelated_path_in_the_registry_still_turns_the_proof_red",
        "登记不再要求落在 Task 66 计划的待删集合里 ⇒ 任意路径都能被「解释」，Stage B 的"
        "「删的每一条都唯一命中计划」这层约束在登记这一侧被绕开",
    ),
)


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _scope_span(source: str, scope: str) -> tuple[int, int]:
    """`scope` 的行区间。支持 `def name` / `class name` / 模块级常量 `NAME`。"""
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
    """读源码。**不走 `read_text`** —— 它做换行翻译，写回时 `\\n` 会变 `\\r\\n`，逐文件 md5
    复原校验必失败（表现为复原失败而文件其实没坏）。
    """
    return path.read_bytes().decode("utf-8")


def write_source(path: Path, text: str) -> None:
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
    """只读锚点体检 —— 「已归档的变异集是否还可复现」最便宜的判据（秒级、不写盘）。"""
    bad: list[str] = []
    for mutation in MUTATIONS:
        try:
            locate(mutation)
        except LookupError as exc:
            bad.append(f"  {mutation.mid}  {exc}")
    print(f"[任务72变异] 锚点体检 {len(MUTATIONS) - len(bad)}/{len(MUTATIONS)} 命中")
    for line in bad:
        print(line)
    return 1 if bad else 0


def run_pytest() -> tuple[int, str]:
    """跑守卫文件。**不经 shell**；`-rfE` 同时收 ERROR。"""
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            GUARD_TEST,
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
        # 🔴 显式 utf-8 + errors="replace"：Windows 默认按 GBK 解 pytest 输出，中文断言消息会抛
        #    UnicodeDecodeError 让 stdout 变 None ⇒ 拼接时 TypeError 打断整批变异。
        encoding="utf-8",
        errors="replace",
        timeout=3600,
        check=False,
    )
    return int(proc.returncode), (proc.stdout or "") + (proc.stderr or "")


def classify(output: str, want: str) -> str:
    """四态判定。只看退出码会把 GREEN / ANCHOR-MISS / WRONG-TEST 全误判成 RED。"""
    reds: set[str] = set()
    for line in output.split("\n"):
        match = re.match(r"^(?:FAILED|ERROR)\s+(\S+)", line.strip())
        if match:
            reds.add(match.group(1).replace("\\", "/"))
    want_norm = want.replace("\\", "/")
    if any(want_norm in nodeid for nodeid in reds):
        return "RED"
    if reds:
        return "WRONG-TEST"
    return "GREEN"


def run(selected: list[str]) -> int:
    chosen = [m for m in MUTATIONS if m.mid in selected] if selected != ["all"] else list(MUTATIONS)
    unknown = sorted(set(selected) - {m.mid for m in MUTATIONS} - {"all"})
    if unknown:
        print(f"[任务72变异] 未知变异号: {unknown}", file=sys.stderr)
        return 2
    baseline = {rel_path: md5(REPO / rel_path) for rel_path in {GATE_REL, GUARD_REL}}
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
            _, output = run_pytest()
            state = classify(output, mutation.want)
        finally:
            write_source(path, original)
            restored = md5(path)
            if restored != baseline[mutation.file]:
                print(
                    f"[任务72变异] 🔴 {mutation.mid} 复原失败: {mutation.file} md5 "
                    f"{restored} != {baseline[mutation.file]}",
                    file=sys.stderr,
                )
                return 5
        verdicts[mutation.mid] = state
        print(f"  {mutation.mid}  {state:<12} want={mutation.want.split('::')[-1]}")
    for rel_path, expected in baseline.items():
        actual = md5(REPO / rel_path)
        if actual != expected:
            print(f"[任务72变异] 🔴 收尾 md5 不符: {rel_path}", file=sys.stderr)
            return 5
    non_red = {mid: state for mid, state in verdicts.items() if state != "RED"}
    print(
        f"\n[任务72变异] RED {sum(1 for s in verdicts.values() if s == 'RED')}/{len(verdicts)}"
        f"；逐文件 md5 复原已校验"
    )
    if non_red:
        print(f"[任务72变异] 非 RED: {non_red}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="任务 72 Stage A 守卫变异检验")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--list", action="store_true")
    mode.add_argument("--run", type=str, help="逗号分隔的变异号，或 all")
    mode.add_argument("--check-anchors", action="store_true")
    args = parser.parse_args(argv)
    if args.list:
        print(f"[任务72变异] 共 {len(MUTATIONS)} 条")
        for mutation in MUTATIONS:
            print(f"  {mutation.mid}  {mutation.scope:<42} {mutation.why[:80]}")
        return 0
    if args.check_anchors:
        return check_anchors()
    return run([part.strip() for part in str(args.run).split(",") if part.strip()])


if __name__ == "__main__":
    raise SystemExit(main())
