# -*- coding: utf-8 -*-
"""任务 71 守卫的变异检验。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 7

═══ 为什么必须有这个脚本 ═══

「守卫写完就绿」不构成任何证据：本 spec 已多次实测「grep 式守卫」与「把错值当基线锁死」
两类缺陷。每写完一条守卫必须做变异检验 —— 改一字看它是否变红；**没打红 = 守卫有缺陷，
不是代码没问题**。

═══ 四态判定（只看退出码会把后三态误判成 RED）═══

* **RED** —— 打红了，且**正是**预期那条测试（`want` 命中）；
* **GREEN** —— 守卫缺陷（改了行为却没有任何判据变红）⇒ 修守卫，**不删变异**；
* **ANCHOR-MISS** —— 脚本缺陷：锚点未命中或命中 >1 处。含 `\\n` 的跨行锚点在 CRLF 文件上
  必 MISS，所以本脚本的锚点全部是**单行**片段；
* **WRONG-TEST** —— 打红了但不是预期项（污染残留或锚点错行）。

**ERROR 也算命中**：多行 `raise` 被整行替换会造成语法错 ⇒ pytest 报 ERROR，而 `-rf` 只列
FAILED ⇒ 会被误判成 GREEN。本脚本用 `-rfE` 并同时读两类行。

═══ 三条硬约束（各自都有实测代价）═══

1. **`want` 用短 nodeid 且目标不参数化**。BP-29：`_locate_want` 对 parametrize nodeid 恒误报。
2. **禁后台执行**。孤儿 python 进程会让复原失败（RestoreFailed rc=5）。本脚本全程前台。
3. **绝不 `--restore` 手工兜底**。复原由 `try/finally` 逐文件 md5 校验完成；收尾再全量校验。
   源码读写一律走 `read_bytes`/`write_bytes` —— `read_text` 的换行翻译会让 md5 复原校验必失败。

用法::

    python backend/scripts/diagnose/mutate_task71_chaos_guards.py --list
    python backend/scripts/diagnose/mutate_task71_chaos_guards.py --run M01,M02
    python backend/scripts/diagnose/mutate_task71_chaos_guards.py --check-anchors
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

GATE_REL: Final[str] = "backend/scripts/check/check_task71_mutation_capacity_recovery_gate.py"
GUARD_REL: Final[str] = "backend/tests/workpaper_sync_chaos/test_task71_chaos_gate.py"

GUARD_TEST: Final[str] = GUARD_REL


@dataclass(frozen=True)
class Mutation:
    """一条变异。

    :param scope: 锚点搜索的**函数/类名**或模块级常量名。锚点用 `scope + offset` 定位，
        **禁绝对行号**（教训 8：绝对行号在任何一次编辑后全部失效）。
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
    # ── 变异分母 / 证据解析类 ──────────────────────────────────────────────
    Mutation(
        "M01",
        GATE_REL,
        "resolve_mutation_coverage",
        "                if found is None:",
        "                if False:  # mutated: 上游 arm 缺失不再报",
        "TestMutationCoverageDenominator::test_resolver_really_reports_a_missing_or_disagreeing_upstream_arm",
        "上游 arm 消失时不再报 unresolved —— 跨文件双向锁失效，「已覆盖」变成一句话",
    ),
    Mutation(
        "M02",
        GATE_REL,
        "resolve_mutation_coverage",
        "                elif not found[\"agrees\"]:",
        "                elif False:  # mutated: 上游 arm 不成立不再报",
        "TestMutationCoverageDenominator::test_resolver_really_reports_a_missing_or_disagreeing_upstream_arm",
        "上游 arm 变 disagrees 时静静通过 —— 「引用的证据不成立」这条永久测不出来",
    ),
    Mutation(
        "M03",
        GATE_REL,
        "MutationTarget",
        "        if not self.evidence:",
        "        if False:  # mutated: 允许空 evidence",
        "TestMutationCoverageDenominator::test_every_target_has_at_least_one_evidence_ref",
        "允许空 evidence —— 空集恒真（假绿第⑥源）",
    ),
    Mutation(
        "M04",
        GATE_REL,
        "MutationTarget",
        "            if kind not in EVIDENCE_KINDS:",
        "            if False:  # mutated: 证据源前缀不再受词表约束",
        "TestMutationCoverageDenominator::test_evidence_kind_vocabulary_is_closed",
        "证据源前缀词表失守 —— 「documented:yes」这类自述可以充当证据",
    ),
    Mutation(
        "M05",
        GATE_REL,
        "_dig",
        "        if isinstance(current, Mapping) and part in current:",
        "        if True:  # mutated: 点号路径恒命中",
        "TestMutationCoverageDenominator::test_facet_refs_resolve_against_the_live_facet_pool",
        "facet 引用恒解析成功 —— 写错路径不再被抓（判据退化成重言式）",
    ),
    # ── 覆盖档位分类器类 ──────────────────────────────────────────────────
    Mutation(
        "M06",
        GATE_REL,
        "classify_coverage",
        "    if any_unresolved or any_disagreeing:",
        "    if False:  # mutated: 证据不成立不再优先",
        "TestCoverageClassifier::test_broken_beats_row_evidence",
        "把 `evidence_broken` 从第一位摘掉 —— 它会被真行证据遮住并显示成「已覆盖」",
    ),
    Mutation(
        "M07",
        GATE_REL,
        "classify_coverage",
        "    return TIER_BROKEN  # no-evidence fallback",
        "    return TIER_ROWS  # mutated: 无证据也算真行验过",
        "TestCoverageClassifier::test_nothing_at_all_is_broken_not_verified",
        "一条证据都没有时判成 `verified_on_rows` —— 「零证据全过」的直接落脚点",
    ),
    Mutation(
        "M08",
        GATE_REL,
        "classify_coverage",
        "    if has_row_evidence:",
        "    if False:  # mutated: 真行证据不再优先",
        "TestCoverageClassifier::test_row_beats_structural_beats_unverifiable",
        "真行档位不可达 —— 「真造过行」与「只有 schema 侧」被合成一档（教训 1/4）",
    ),
    Mutation(
        "M09",
        GATE_REL,
        "build_counterfactual_arms",
        '            "conclusion_changes": _shifted(any_unresolved=True) != today,',
        '            "conclusion_changes": _shifted() != today,',
        "TestCoverageClassifier::test_counterfactual_arms_are_all_sensitive",
        "把 A1 臂的 override 改成空操作 —— 臂不再翻转结论，反事实退化成重言式。"
        "🔴 刻意打**被判据的主体**（override 本身）而不是那行 `!=`：把该字段写死成 True 是"
        "等价变异（今天 A1 本来就翻转），改弱断言永远不会让通过的测试失败（教训 18）",
    ),
    Mutation(
        "M10",
        GATE_REL,
        "build_forward_recompute",
        '            "expected_tier": TIER_ROWS,',
        '            "expected_tier": TIER_STRUCTURAL,',
        "TestCoverageClassifier::test_forward_recompute_agrees_and_has_a_positive_case",
        "把唯一那条正例的期望档位改掉 —— 正向重算失去抓「分类器恒真」的能力（教训 15）。"
        "同样打主体：把 `has_positive_case` 写死成 True 是等价变异",
    ),
    # ── 行为臂类 ──────────────────────────────────────────────────────────
    Mutation(
        "M11",
        GATE_REL,
        "OwnArm",
        '        if self.expectation == "rejected" and not self.signature:',
        '        if False:  # mutated: rejected 臂不再要求 signature',
        "TestBehaviourArms::test_rejected_arms_must_declare_a_signature",
        "只比「抛了异常」—— NOT NULL / FK / 别的 CHECK 全算成通过（教训 1）",
    ),
    Mutation(
        "M12",
        GATE_REL,
        "evaluate_own_arm",
        "    if observation is None:",
        "    if False:  # mutated: 观测缺失视为通过",
        "TestBehaviourArms::test_missing_observation_is_not_a_pass",
        "观测缺失当成通过 —— additive 注入即死代码，声明与探针脱钩测不出来",
    ),
    Mutation(
        "M13",
        GATE_REL,
        "evaluate_own_arm",
        "        agrees = (not accepted) and len(hits) == len(arm.signature)",
        "        agrees = not accepted  # mutated: 不再比 signature",
        "TestBehaviourArms::test_rejected_arm_with_the_wrong_reason_disagrees",
        "拒绝理由不再逐片段比对 —— 拒错了原因也算通过",
    ),
    Mutation(
        "M14",
        GATE_REL,
        "build_behaviour_report",
        "            if len(hits) == len(left.get(\"signature\") or []) and hits:",
        "            if False:  # mutated: 交叉签名检测短路",
        "TestBehaviourArms::test_cross_signature_detector_catches_a_planted_collision",
        "拒绝理由互不命中的检测短路 —— 两条臂度量同一约束时其中一条成死判据",
    ),
    Mutation(
        "M15",
        GATE_REL,
        "_Obs",
        "        if arm_id in self.data:",
        "        if False:  # mutated: 重复写观测不再记录",
        "TestBehaviourArms::test_obs_records_a_duplicate_write",
        "同一臂被写两次时后写的静静覆盖前一条 —— 观测丢失无人管",
    ),
    Mutation(
        "M16",
        GATE_REL,
        "build_behaviour_report",
        '                if not any(a.facet == arm.facet and a.expectation == "accepted" for a in OWN_ARMS)',
        "                if False  # mutated: 不再报缺对照组",
        "TestBehaviourArms::test_missing_control_detector_catches_a_planted_facet",
        "隐藏「缺对照组的 facet」—— 对照组不过时「非法被拒」毫无信息量（教训 5）",
    ),
    # ── 容量面类 ──────────────────────────────────────────────────────────
    Mutation(
        "M17",
        GATE_REL,
        "build_capacity",
        '            "tier": "UNVERIFIABLE",',
        '            "tier": "EXECUTED",  # mutated: 谎报真实负载已跑',
        "TestCapacityFacet::test_real_load_is_unverifiable_with_an_owner_and_premises",
        "谎报真实负载已执行 —— 正是生产 `capacity_profile` 设计来防的那件事",
    ),
    Mutation(
        "M18",
        GATE_REL,
        "build_capacity",
        "        capacity.assert_capacity_verified(None)",
        "        pass  # mutated: 不再真调 fail-closed",
        "TestCapacityFacet::test_fail_closed_without_execution_record",
        "不再真调 fail-closed —— 「没有执行记录时会抛」这条实证消失",
    ),
    Mutation(
        "M19",
        GATE_REL,
        "build_capacity",
        "        capacity.assert_profile_matches_requirements()",
        "        pass  # mutated: 不再交叉锁需求原文",
        "TestCapacityFacet::test_gate_really_calls_the_production_requirement_lock",
        "登记值与 AC 原文脱钩 —— 「把目标改小」不再打红",
    ),
    # ── 删除门 / DAG 类 ───────────────────────────────────────────────────
    Mutation(
        "M20",
        GATE_REL,
        "build_dag_dependency",
        '        "task24_depends_on_task23": "23" in deps.get("24", []),',
        '        "task24_depends_on_task23": True,  # mutated: 写死成成立',
        "TestDagDependency::test_the_field_is_computed_not_hardcoded",
        "把任务 24 对任务 23 的依赖判据写死 —— 删掉依赖不再打红（正文点名的变异）",
    ),
    Mutation(
        "M21",
        GATE_REL,
        "build_deletion_gate",
        '            "stale_is_nonzero": sum(axes.values()) > 0,',
        '            "stale_is_nonzero": True,  # mutated: 写死成非零',
        "TestDeletionGateMutations::test_stale_and_eligibility_fields_are_computed_not_hardcoded",
        "任务 67 的 stale 计数写死成非零 —— 「错误要求 fresh/stale=0」的落点消失",
    ),
    Mutation(
        "M22",
        GATE_REL,
        "build_deletion_gate",
        '        "不得要求待删 unreachable在删除前已为0" in body72',
        "        True  # mutated: clause 现算写死成成立",
        "TestDeletionGateMutations::test_stage_a_clause_is_read_from_the_task_text",
        "Stage A「不得要求待删 unreachable 预先为 0」这条现算写死 —— 正文改了也不红",
    ),
    Mutation(
        "M23",
        GATE_REL,
        "build_deletion_gate",
        '            "task70_vocabulary_has_no_passed": "passed" not in t70_vocab,',
        '            "task70_vocabulary_has_no_passed": True,  # mutated: 写死',
        "TestDeletionGateMutations::test_smoke_field_is_read_from_task70_vocabulary",
        "「smoke 不能把 evidence 顶回 verified」的现算写死 —— 词表加第四态也不红",
    ),
    # ── 协议源码现算类 ────────────────────────────────────────────────────
    Mutation(
        "M24",
        GATE_REL,
        "build_protocol_source_scan",
        '            "doc_key_includes_mtime": bool(probe.doc_key_includes_mtime),',
        '            "doc_key_includes_mtime": False,  # mutated: 写死成不含 mtime',
        "TestProtocolSourceScan::test_doc_key_field_is_computed_not_hardcoded",
        "doc_key 是否含 mtime 写死成 False —— 「mtime 入 doc key」这条变异无处落脚",
    ),
    Mutation(
        "M57",
        GATE_REL,
        "build_protocol_source_scan",
        "        shutil.rmtree(probe_dir, ignore_errors=True)",
        "        pass  # mutated: 探针临时目录不再清理",
        "TestProtocolSourceScan::test_doc_key_is_mtime_free_measured_by_the_production_probe",
        "doc_key 探针的临时目录不再清理 —— 正文要求「测试数据/trace artifact 完整复原/清理」",
    ),
    Mutation(
        "M25",
        GATE_REL,
        "forbidden_key_inputs",
        "        if any(token in name for token in FORBIDDEN_KEY_INPUT_TOKENS)",
        "        if False  # mutated: 不再检查禁用入参",
        "TestProtocolSourceScan::test_forbidden_input_detector_catches_planted_names",
        "application key 的禁用入参检查失效 —— 「status 入 key」不再打红（Property 64）",
    ),
    Mutation(
        "M59",
        GATE_REL,
        "FORBIDDEN_KEY_INPUT_TOKENS",
        '    "status",',
        '    "status_renamed",',
        "TestProtocolSourceScan::test_forbidden_input_detector_catches_planted_names",
        "把 `status` 从禁用 token 名单里换掉 —— 名单类判据必须写死真实目标（教训 16）",
    ),
    # ── multi_resolver 类 ─────────────────────────────────────────────────
    Mutation(
        "M26",
        GATE_REL,
        "MULTI_RESOLVER_ROWS",
        '    "post_sheet_onlyoffice_callback",',
        '    "post_sheet_onlyoffice_callback_renamed",',
        "TestMultiResolverAdjudication::test_four_named_rows_are_written_down",
        "把一条 resolver 行名换掉 —— 名单类判据必须写死真实目标（教训 16）",
    ),
    Mutation(
        "M27",
        GATE_REL,
        "multi_resolver_criterion_passes",
        "    return len(multi_resolver_rows) == 0 and not list(rows_still_deferred)",
        "    return True  # mutated: 无条件放行",
        "TestMultiResolverAdjudication::test_criterion_helper_requires_both_conditions",
        "无条件放行 `multi_resolver` 准则 —— `legacy_delete` 会放行任务 72 的全局删除",
    ),
    Mutation(
        "M28",
        GATE_REL,
        "inventory_staleness",
        "    return live_digest != on_disk_digest",
        "    return False  # mutated: 谎报不 stale",
        "TestMultiResolverAdjudication::test_inventory_staleness_helper_compares_digests",
        "谎报 inventory 不 stale —— 「writer 门默认命令 exit 2」这件事被藏起来",
    ),
    Mutation(
        "M29",
        GATE_REL,
        "resolver_matrix_facts",
        '        "fields_are_not_merged": all(',
        '        "fields_are_not_merged": True,  # mutated: 写死\n        "_unused_merged": all(',
        "TestMultiResolverAdjudication::test_matrix_facts_catch_merged_fields",
        "两个独立字段是否被合并的判据写死 —— 合并后「登记的阻塞把守发布门」失去意义",
    ),
    Mutation(
        "M60",
        GATE_REL,
        "resolver_matrix_facts",
        '            qualname for qualname, row in per_row.items() if row["status"] == "deferred"',
        "            qualname for qualname, row in per_row.items() if False  # mutated",
        "TestMultiResolverAdjudication::test_matrix_facts_catch_merged_fields",
        "「仍 deferred」的行不再被报出来 —— 正文逐字要求的「任一行仍 deferred 即不过」失守",
    ),
    # ── Property 落点类 ───────────────────────────────────────────────────
    Mutation(
        "M30",
        GATE_REL,
        "build_property_landings",
        "    missing = sorted(set(DECLARED_PROPERTIES) - set(_PROPERTY_LANDINGS))",
        "    missing = []  # mutated: 不再报缺落点",
        "TestPropertyLandings::test_all_24_declared_properties_have_a_landing",
        "隐藏缺失的 Property 落点 —— 「24 条逐条」退化成「有几条算几条」",
    ),
    Mutation(
        "M31",
        GATE_REL,
        "build_property_landings",
        '        if tier != "verified_here" and not owner:',
        "        if False:  # mutated: 未验证不再要求 owner",
        "TestPropertyLandings::test_every_unverified_property_names_an_owner",
        "允许未验证的 Property 不点名 owner —— 正文明令要求「owner 是谁」",
    ),
    # ── verdict 类 ────────────────────────────────────────────────────────
    Mutation(
        "M32",
        GATE_REL,
        "build_verdict",
        "    elif row_arms == 0:",
        "    elif False:  # mutated: 零臂不再判 unverifiable",
        "TestVerdict::test_zero_behaviour_arms_would_be_unverifiable_not_passed",
        "「零证据全过」不再触发 unverifiable —— 本 spec 反复点名的假绿（Property 71）",
    ),
    Mutation(
        "M33",
        GATE_REL,
        "VERDICT_VOCABULARY",
        'VERDICT_VOCABULARY: Final[tuple[str, ...]] = ("passed", "failed", "unverifiable")',
        'VERDICT_VOCABULARY: Final[tuple[str, ...]] = ("passed", "failed", "unverifiable", "refreshed")',
        "TestVerdict::test_vocabulary_is_exactly_three",
        "给 verdict 词表加第四态 —— 「宣称通过」的旁门",
    ),
    Mutation(
        "M34",
        GATE_REL,
        "build_verdict",
        "    if not redaction[\"no_planted_secret_survives\"]:",
        "    if False:  # mutated: 密钥泄露不再判失败",
        "TestVerdict::test_a_leaked_secret_flips_to_failed",
        "植入的密钥存活时 verdict 不变 failed —— 脱敏面成装饰",
    ),
    Mutation(
        "M35",
        GATE_REL,
        "build_verdict",
        "    if not restoration[\"restored\"]:",
        "    if False:  # mutated: 复原不成立不再判失败",
        "TestVerdict::test_unrestored_data_flips_to_failed",
        "数据复原不成立时 verdict 不变 failed —— 写库红线失守",
    ),
    Mutation(
        "M36",
        GATE_REL,
        "build_verdict",
        "    if behaviour[\"cross_signature_hits\"]:",
        "    if False:  # mutated: 交叉命中不再判失败",
        "TestVerdict::test_cross_signature_hit_flips_to_failed",
        "拒绝理由互相命中时不再判失败 —— 死判据可以长期存在",
    ),
    # ── 复原实证类 ────────────────────────────────────────────────────────
    Mutation(
        "M37",
        GATE_REL,
        "restoration_record",
        "        if before.get(table) != after.get(table)",
        "        if False",
        "TestDataRestoration::test_restoration_record_catches_drift_leftovers_and_temp_dir",
        "把「前后行数相等」改成恒真 —— 悄悄写了生产库也报 0 行新增",
    ),
    Mutation(
        "M38",
        GATE_REL,
        "restoration_record",
        '        "restored": bool(measured and not drifted and own_left == 0 and temp_removed),',
        '        "restored": True,  # mutated: 恒真',
        "TestDataRestoration::test_restoration_record_catches_drift_leftovers_and_temp_dir",
        "复原结论恒真 —— scratch 残留与临时目录残留都被静默容忍",
    ),
    Mutation(
        "M39",
        GATE_REL,
        "restoration_record",
        '        "own_schema_left": own_left,',
        '        "own_schema_left": 0,  # mutated: 写死成 0',
        "TestDataRestoration::test_restoration_record_catches_drift_leftovers_and_temp_dir",
        "本轮残留写死成 0 —— 「区分本轮与外来」失去意义",
    ),
    # ── 故障注入类 ────────────────────────────────────────────────────────
    Mutation(
        "M40",
        GATE_REL,
        "_inject_windows_file_lock",
        '        handle = target.open("rb")',
        '        handle = open(__file__, "rb")  # mutated: 不再真占用目标文件',
        "TestFaultInjectionFacet::test_windows_lock_keeps_the_file_and_classifies_the_error",
        "Windows lock 注入不再真占用目标文件 —— 「删不掉时分类成 FILE_IN_USE」这条实证消失。"
        "🔴 打**被判据的主体**（有没有真的持有句柄）而不是那行分类表达式：把它写死成 True 在"
        "今天是等价变异（教训 18）",
    ),
    Mutation(
        "M41",
        GATE_REL,
        "build_fault_injection",
        '        if name == "onlyoffice":',
        "        if False:  # mutated: OO 注入不再判定",
        "TestFaultInjectionFacet::test_all_six_injections_are_present_and_agree",
        "OO 注入的判定落到兜底分支 —— 六条注入被合成一条（教训 1/4）",
    ),
    Mutation(
        "M42",
        GATE_REL,
        "_inject_disk_path_escape",
        '            repo.delete_artifact_file("../../etc/passwd", project_id=project)',
        '            repo.delete_artifact_file(f"storage/{project}/workpapers/x.xlsx", project_id=project)',
        "TestFaultInjectionFacet::test_disk_injection_distinguishes_escape_from_absent",
        "把越界路径换成合法路径 —— Property 42 的实证退化成「删一个不存在的文件」。"
        "🔴 打主体（越界的那个路径）而不是那行 `raised: False`：后者落在今天永不执行的 else "
        "分支上，是不可达分支上的等价变异（教训 4/18）",
    ),
    # ── 复选框 / 逐字节锁类 ───────────────────────────────────────────────
    Mutation(
        "M43",
        GATE_REL,
        "task_body",
        '    body[0] = _CHECKBOX_RE.sub(r"\\1?\\2", body[0])',
        "    pass  # mutated: 不再归一化复选框",
        "TestTaskBodyDigestIgnoresCheckboxState::test_checkbox_flip_does_not_change_body_digest",
        "去掉复选框归一化 —— 编排器翻牌就让本门假红（BP-70-6 的形态）",
    ),
    Mutation(
        "M44",
        GATE_REL,
        "VOLATILE_KEYS",
        '        "probe_elapsed_seconds",',
        '        "source_commit",',
        "TestReportIsFreshAndByteLocked::test_volatile_keys_are_only_random_and_wallclock",
        "把 source_commit 排除出逐字节比对 —— 源码漂移后报告仍「一致」，stale 轴失守",
    ),
    Mutation(
        "M45",
        GATE_REL,
        "BP_ID_PATTERN",
        'BP_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"BP-71-\\d+")',
        'BP_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r".*")',
        "TestBlockingPoints::test_every_id_matches_bp_71_n",
        "把 BP 编号锁放宽成 `.*` —— 编号规范失守",
    ),
    Mutation(
        "M46",
        GATE_REL,
        "build_blocking_points",
        '            "id": "BP-71-3",',
        '            "id": "BP71-3",',
        "TestBlockingPoints::test_every_id_matches_bp_71_n",
        "写错一个 BP 编号 —— 锁必须逐条命中而不是抽查",
    ),
    # ── 守卫落位 / 产物跟踪类 ─────────────────────────────────────────────
    Mutation(
        "M47",
        GATE_REL,
        "GUARD_TEST_REL",
        'GUARD_TEST_REL: Final[str] = "backend/tests/workpaper_sync_chaos/test_task71_chaos_gate.py"',
        'GUARD_TEST_REL: Final[str] = "backend/tests/workpaper_sync/test_task71_chaos_gate.py"',
        "TestGuardPlacement::test_report_records_the_placement_rationale",
        "把守卫落位改回上游的目录普查范围 —— BP-69-6 的形态（会打红它 1~3 条守卫）。"
        "🔴 打主体（落位本身）而不是那行 `not startswith`：后者今天恒真，写死是等价变异",
    ),
    Mutation(
        "M61",
        GATE_REL,
        "upstream_lock_impact",
        '        "task70_lock_goes_stale_because_of_this_gate": not projection_agrees,',
        '        "task70_lock_goes_stale_because_of_this_gate": False,  # mutated: 与现算脱钩',
        "TestGuardPlacement::test_upstream_lock_impact_is_measured_and_owned",
        "把「上游锁是否被本门顶红」写死成 False 而不是由现算投影派生 —— 上游普查免疫被回退时"
        "本门会谎报「无影响」，收尾必须交代是否新增红，藏起来等于隐瞒",
    ),
    Mutation(
        "M62",
        GATE_REL,
        "UPSTREAM_LOCKS",
        '    ("backend/tests/workpaper_sync/test_task67_structural_pre_reconcile.py", "67", 66, 0),',
        '    ("backend/tests/workpaper_sync/test_task67_structural_pre_reconcile.py", "67", 0, 0),',
        "TestGuardPlacement::test_all_four_upstream_locks_are_declared_with_baselines",
        "把一把上游锁的基线通过数改成 0 —— 基线归零后「是否新增红」无从判断",
    ),
    Mutation(
        "M48",
        GATE_REL,
        "git_porcelain",
        "        if not (REPO / path).exists():",
        "        if False:  # mutated: 不再区分「不在磁盘上」",
        "TestGuardPlacement::test_artifact_git_status_is_reported_for_every_product",
        "把「产物不存在」报成 tracked-clean —— CI 在干净 checkout 下必挂而报告说一切正常",
    ),
    # ── BP-68-1 复核类 ────────────────────────────────────────────────────
    Mutation(
        "M49",
        GATE_REL,
        "build_bp_68_1_recheck",
        '        "agrees_with_task68": mine == upstream_claim,',
        '        "agrees_with_task68": True,  # mutated: 写死成一致',
        "TestBp681Recheck::test_recheck_flips_when_the_two_sides_disagree",
        "「与上游一致」写死 —— 独立复核退化成复述上游结论",
    ),
    Mutation(
        "M50",
        GATE_REL,
        "probe_delivery_ownership_invariant",
        "            invariant_accepts[label] = False",
        "            invariant_accepts[label] = True  # mutated: 抛了也算接受",
        "TestBp681Recheck::test_service_layer_pure_invariant_half_is_measured",
        "服务层不变量抛异常时也记成「接受」—— BP-68-1 的另一半结论被伪造。"
        "该 except 分支由负对照 `double_owner_negative_control` 保持可达（教训 4）",
    ),
    # ── 告警面类 ──────────────────────────────────────────────────────────
    Mutation(
        "M51",
        GATE_REL,
        "build_alerting",
        '        at = registry.evaluate(_samples(rule, value=rule.threshold, key="at"))',
        '        at = registry.evaluate(_samples(rule, value=0.0, key="at"))',
        "TestAlertingFacet::test_every_rule_fires_at_threshold_and_is_silent_below",
        "「恰在阈值」那一组样本的值改成 0 —— 阈值上那一半不再被验证。"
        "🔴 打主体（样本值）而不是那行 `agrees`：今天所有规则都 agrees，写死是等价变异",
    ),
    Mutation(
        "M52",
        GATE_REL,
        "build_alerting",
        '        below = registry.evaluate(_samples(rule, value=max(rule.threshold - 1.0, 0.0), key="lo"))',
        '        below = registry.evaluate(_samples(rule, value=rule.threshold, key="lo"))',
        "TestAlertingFacet::test_every_rule_fires_at_threshold_and_is_silent_below",
        "「阈值以下」那一组样本的值抬到阈值 —— 「恒触发」的规则会被判成正确",
    ),
    # ── 脱敏面类 ──────────────────────────────────────────────────────────
    Mutation(
        "M53",
        GATE_REL,
        "build_redaction",
        "    projected, report = policy.redact(payload)",
        "    projected, report = dict(payload), policy.redact(payload)[1]  # mutated: 不脱敏",
        "TestRedactionFacet::test_no_planted_secret_survives",
        "把「脱敏后的载荷」换成原始载荷 —— 植入的密钥会全部存活。"
        "🔴 打主体（被检查的那个对象）而不是那行 `leaked = sorted(...)`：今天没有泄露，"
        "把它写死成 `[]` 是等价变异（教训 18）",
    ),
    Mutation(
        "M58",
        GATE_REL,
        "build_redaction",
        "    bare_token_text = policy.redact_exception(",
        "    bare_token_text = '[redacted-secret]'  # mutated: 谎报已抹\n    _unused_bare = policy.redact_exception(",
        "TestRedactionFacet::test_bare_token_in_free_text_gap_is_registered_not_hidden",
        "谎报「自由文本裸 token 已被抹」—— 既有设计边界被藏起来，owner 无从接手",
    ),
    Mutation(
        "M54",
        GATE_REL,
        "build_redaction",
        '    _arm("red_control_projected_passes", "accepted", lambda: policy.assert_no_leak(projected))',
        '    _arm("red_control_projected_passes", "accepted", lambda: policy.assert_no_leak(payload))',
        "TestRedactionFacet::test_control_passes_and_four_experiments_raise",
        "把对照组喂原始（未脱敏）载荷 —— 对照组必须先过，它一旦不过，四条实验组的「被拒」"
        "就毫无信息量（教训 5）",
    ),
    # ── retention 面类 ────────────────────────────────────────────────────
    Mutation(
        "M55",
        GATE_REL,
        "_probe_retention",
        "            if row.decision == \"delete\":",
        "            if True:  # mutated: 所有判定都记成 delete",
        "TestRetentionFacet::test_plan_covers_seven_decision_branches_live",
        "七条 retain 分支全被记成 delete —— 判定分支合成一条（教训 1）",
    ),
    Mutation(
        "M56",
        GATE_REL,
        "_probe_retention",
        "        handle = locked_file.open(\"rb\")",
        "        handle = open(__file__, \"rb\")  # mutated: 不再真占用目标文件",
        "TestRetentionFacet::test_apply_protocol_and_recheck_branches_live",
        "Windows lock 注入不再真占用目标文件 —— 「删不掉时改判 retain」这条实证消失",
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
    于是逐文件 md5 复原校验必定失败（表现为 RestoreFailed rc=5 而文件内容其实没坏）。
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


def check_anchors(mutations: tuple[Mutation, ...] | None = None) -> int:
    """只读锚点体检 —— 「已归档的变异集是否还可复现」的最便宜判据。"""
    chosen = MUTATIONS if mutations is None else mutations
    bad: list[str] = []
    for mutation in chosen:
        try:
            locate(mutation)
        except LookupError as exc:
            bad.append(f"  {mutation.mid}  {exc}")
    print(f"[任务71变异] 锚点体检 {len(chosen) - len(bad)}/{len(chosen)} 命中")
    for line in bad:
        print(line)
    return 1 if bad else 0


def run_pytest(targets: tuple[str, ...] = (GUARD_TEST,)) -> tuple[int, str]:
    """跑守卫文件。**不经 shell**（`-k "a or b"` 会被拆成位置参数）。`-rfE` 同时收 ERROR。"""
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            *targets,
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
        # 🔴 必须显式指定 utf-8 + errors="replace"：Windows 默认按 GBK 解 pytest 输出，
        #    中文断言消息会抛 UnicodeDecodeError 让 `proc.stdout` 变 None ⇒
        #    `stdout + stderr` TypeError（首轮实测直接打断整批变异）。
        encoding="utf-8",
        errors="replace",
        timeout=3600,
        check=False,
    )
    return int(proc.returncode), (proc.stdout or "") + (proc.stderr or "")


def classify(output: str, want: str) -> str:
    """四态判定。

    🔴 只看退出码会把 GREEN / ANCHOR-MISS / WRONG-TEST 全误判成 RED。这里逐行读 `-rfE` 的
    FAILED/ERROR 清单：**ERROR 也算命中**（多行 `raise` 被整行替换会造成语法错 ⇒ ERROR，
    而 `-rf` 只列 FAILED ⇒ 会被误判成 GREEN）。
    """
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


def run(
    selected: list[str],
    mutations: tuple[Mutation, ...] | None = None,
    targets: tuple[str, ...] = (GUARD_TEST,),
) -> int:
    pool = MUTATIONS if mutations is None else mutations
    chosen = [m for m in pool if m.mid in selected] if selected != ["all"] else list(pool)
    unknown = sorted(set(selected) - {m.mid for m in pool} - {"all"})
    if unknown:
        print(f"[任务71变异] 未知变异号: {unknown}", file=sys.stderr)
        return 2

    baseline = {rel: md5(REPO / rel) for rel in {m.file for m in chosen}}
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
            _, output = run_pytest(targets)
            state = classify(output, mutation.want)
        finally:
            write_source(path, original)
            restored = md5(path)
            if restored != baseline[mutation.file]:
                print(
                    f"[任务71变异] 🔴 {mutation.mid} 复原失败: {mutation.file} md5 "
                    f"{restored} != {baseline[mutation.file]}",
                    file=sys.stderr,
                )
                return 5
        verdicts[mutation.mid] = state
        print(f"  {mutation.mid}  {state:<12} want={mutation.want.split('::')[-1]}")

    for rel_path, expected in baseline.items():
        actual = md5(REPO / rel_path)
        if actual != expected:
            print(f"[任务71变异] 🔴 收尾 md5 不符: {rel_path}", file=sys.stderr)
            return 5

    non_red = {mid: state for mid, state in verdicts.items() if state != "RED"}
    print(
        f"\n[任务71变异] RED {sum(1 for s in verdicts.values() if s == 'RED')}/{len(verdicts)}"
        f"；逐文件 md5 复原已校验"
    )
    if non_red:
        print(f"[任务71变异] 非 RED: {non_red}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="任务 71 守卫变异检验")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--list", action="store_true")
    mode.add_argument("--run", type=str, help="逗号分隔的变异号，或 all")
    mode.add_argument("--check-anchors", action="store_true")
    args = parser.parse_args(argv)

    if args.list:
        print(f"[任务71变异] 共 {len(MUTATIONS)} 条")
        for mutation in MUTATIONS:
            print(f"  {mutation.mid}  {mutation.scope:<38} {mutation.why}")
        return 0
    if args.check_anchors:
        return check_anchors()
    return run([part.strip() for part in str(args.run).split(",") if part.strip()])


if __name__ == "__main__":
    raise SystemExit(main())
