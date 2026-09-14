# -*- coding: utf-8 -*-
r"""Task 53 守卫变异检验 —— K 循环 Excel 独立 entry 迁移。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 5 Task 53

用平台共享件 `backend/scripts/_mutation_kit`（`test_mutation_kit_adoption.py` 对新脚本强制
采纳：共享件的 `run_cli` 把 `guard_files`（覆盖面分母）做成签名层面必填，把「锚点含换行」
「new == anchor」「id 重复」「want 定位不到」全部拦在声明期）。

═══ 本脚本的四条硬约束 ═══

1. **每条变异都带 `scope_check`**。四态判定式「新增失败集合是否为空」识别不出「锚点落在被测
   判据的作用域之外」—— 改到了别处会被判 GREEN（守卫缺陷），而真相是脚本缺陷。数据文件的
   回调解析 JSON 后断言目标字段真的变成了期望值；源码文件的回调断言改动确实落在那段文本上。

2. **重复形态字段用 `scope` + `offset` 相对定位，绝不用绝对行号**。本 slice 有 **13 条**
   entry，故 entry 级字段全是 dup=13（`"capability": null,` / `"html_counterpart_verdict"` /
   `"mounts_ac14_notice"` …）。这些一律以该 entry 唯一的 `"entry_id": "…"` 行作 `scope`，
   `offset` 由 `tmp_task53_anchors3.py` 一次性诊断实算（非估计值）：
   capability=+5 · verdict=+18 · blocked_by 首元素=+9 · manifest_mirror.capability=+52 ·
   segmented_sites_in_gate 首元素=+59 · mounts_ac14_notice=+68。

3. **变异按「可区分的错法」枚举而不是逐条目复制**。13 条 entry 形态同构，逐条各写一次是同
   信息量的重复。这里按错法分组，并**分布在不同 entry 上**（K1/K2/K5/K8/K9/K11/K13），
   从而同时把各 entry 的 offset 走通。

4. **必须含反向变异**。只验「新增缺陷」一个方向的穷举判据是半个判据：缺陷被修好而登记没删，
   报告会长期挂着一条已解决的债。本脚本的反向变异：
   * M28 把 BP-8 的一处 family_a 位置化身份**修好**（`row-${idx}` → 稳定 uuid），命中数 32 → 31；
   * M29 在 K2 宿主里**真挂上** AC 1.4 的 notice 组件（BP-7 可解除）；
   * M30 **删掉** `useK1DualMode` 的 legacy health 端点直调（端点计数 13 → 12）；
   * M31 在 K1 宿主里**真 import** 那个 orphan composable（orphan 变活桩，7 → 6）；
   * M35 把 `_reference` 说明里的目录名改掉（防误认那条判据的反向）。

═══ 为什么要对**真源码常量**做变异（M22~M35）═══

数据侧变异只能证明「守卫读了 slice」；只有改真源码还打红，才能证明 impl 侧是**现读**而不是
抄了一份快照。K 循环的判据里有六类必须有源码变异撑着：
① writeoff owner 常量现读（M22/M23）· ② Property 24 的「派生且只写不读」（M24/M25）·
③ K1/K2 scope 的真源派生（M26/M27）· ④ 位置化身份穷举（M28）· ⑤ 消费边可达性（M30/M31）·
⑥ 四表复用的分支判据（M32/M33）· ⑦ 宿主 toolbar 锚点与渲染器模块边（M34/M36）。

用法（仓库根；本仓库 PATH 上的 `python` 可能指向坏掉的解释器，必须用显式解释器）::

    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task53_k_cycle_migration_guards.py --list
    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task53_k_cycle_migration_guards.py --check-anchors
    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task53_k_cycle_migration_guards.py --run M01,M02,M03

🔴 **禁止后台执行**：外层 shell 被杀会让 python 变成孤儿进程，与前台运行同时变异同一文件 ⇒
`RestoreFailed` rc=5。分批跑用 `--run M01,M02,...`（子集运行不做覆盖面结论，见 kit 的
`CoverageTally.report`）。

🔴 **`delete` 不要用在数组末元素上**：删掉末元素会给前一行留下尾逗号、JSON 失效，
`scope_check` 的 `json.loads` 抛异常 ⇒ 判定 ERROR（脚本缺陷，不是守卫缺陷）。一律用 `replace`。

🔴 **运行前把并发遗留的 `backend/scripts/check/*.mutbak` 移到仓库外**（`%TEMP%`），否则
`_mutation_kit` 的残留扫描会 `[ABORT]`。跑完原位放回并核验 sha256；**绝不 `--restore`**。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

# ── 被变异的对象 ───────────────────────────────────────────────────────────
SLICE = "backend/data/workpaper_sync_k_cycle_manifest_slice.json"
PLAN = "backend/data/workpaper_sync_k_cycle_deletion_plan.json"
FE = "audit-platform/frontend/src"
WP = f"{FE}/components/workpaper"
COMP = f"{WP}/composables"
WRITEOFF_OWNER = f"{COMP}/useK1WriteoffCheck.ts"
K1_SCOPE = f"{COMP}/k1AccountScope.ts"
K2_SCOPE = f"{COMP}/k2AccountScope.ts"
K1_ORPHAN = f"{COMP}/useK1DualMode.ts"
HOST_K1 = f"{WP}/GtK1OtherReceivables.vue"
HOST_K2 = f"{WP}/GtK2OtherCurrentAssets.vue"
K9_SOE = f"{WP}/k9/core/K9TabDisclosureSoe.vue"
REGISTRY_TS = f"{WP}/htmlRendererRegistry.ts"
K8_STRATEGY = "backend/app/routers/wp_render_strategies/_k8_selling_expenses.py"
K_SPECS = "backend/app/services/four_table/k_cycle_specs.py"

# ── 期望打红的守卫（文件::类::方法，与 pytest 的 short nodeid 同形）─────────
T53 = "test_task53_k_cycle_migration.py"
_SELF = f"{T53}::TestGuardSelfChecks"
_SCOPE = f"{T53}::TestSliceScopeIsRecomputable"
_ADJ = f"{T53}::TestAdjudicationLegality"
_HTML = f"{T53}::TestHtmlCounterpartIsSourceBacked"
_ORPHAN = f"{T53}::TestOrphanDualModeInventory"
_FORM = f"{T53}::TestKCycleFormDifferences"
_WO = f"{T53}::TestWriteoffCapability"
_ACC = f"{T53}::TestAccountScopeAndFourTableReuse"
_P23 = f"{T53}::TestProperty23StaticStructure"
_P3 = f"{T53}::TestProperty3And20"
_P28 = f"{T53}::TestProperty28DefinitionDriftFailClosed"
_P69 = f"{T53}::TestProperty69EvidenceAndCounters"
_P70 = f"{T53}::TestProperty70CrossEntryIsolation"
_DEL = f"{T53}::TestDeletionPlanConsistency"
_PARA = f"{T53}::TestParadigmCompliance"
_CONTRACT = "test_migration_paradigm_contract.py"
_COVERAGE = "test_slice_schema_validator_coverage.py"


def EID(slug: str) -> str:
    """某 entry 唯一的 scope 行（dup=1）。"""
    return '      "entry_id": "xlsx/%s",' % slug


K1 = EID("gt-k1-other-receivables")
K2 = EID("gt-k2-other-current-assets")
K5 = EID("gt-k5-provisions")
K8 = EID("gt-k8-selling-expenses")
K9 = EID("gt-k9-admin-expenses")
K11 = EID("gt-k11-asset-impairment-loss")
K13 = EID("gt-k13-non-operating-expense")

#: 逐字段 offset（由 `tmp_task53_anchors3.py` 一次性诊断实算，非估计值）。
OFF_CAPABILITY = 5
OFF_VERDICT_STAGE = 6
OFF_CAPABILITY_TARGET = 7
OFF_BLOCKED_FIRST = 9
OFF_HTML_VERDICT = 18
#: 🔴 逐 entry 的 offset **不相等**（各 entry 的 reason/how_resolved 文本长度不同，
#: 且 K1 多一条 BP-4 使 blocked_by 数组长一行）⇒ 必须逐 entry 实算，不能共用一个常量。
#: 首轮把 K1 的 offset 套到 K9/K11/K13/K2 上，`--list` 当场报 4 条 ANCHOR-MISS。
OFF_HTML_VERDICT_K9 = 17
OFF_MIRROR_CAPABILITY_K11 = 51
OFF_MOUNTS_NOTICE_K13 = 66
OFF_SEGMENTED_FIRST_K2 = 57
OFF_MUST_NOT_WIRE_FIRST_K1 = 35


# ── scope_check 工具 ──────────────────────────────────────────────────────
def _doc(raw: bytes) -> dict:
    return json.loads(raw.decode("utf-8"))


def _entry(raw: bytes, entry_id: str) -> dict:
    for e in _doc(raw)["independent_entries"]:
        if e["entry_id"] == entry_id:
            return e
    raise AssertionError(f"scope_check: slice 里找不到 {entry_id}")


def entry_field_is(entry_id: str, path: tuple, expect):
    """断言某 entry 的某字段变成了期望值（作用域自证）。"""
    def check(raw: bytes) -> bool:
        node = _entry(raw, entry_id)
        for k in path:
            node = node[k] if not isinstance(k, int) else node[k]
        return node == expect
    return check


def top_field_is(path: tuple, expect):
    def check(raw: bytes) -> bool:
        node = _doc(raw)
        for k in path:
            node = node[k] if not isinstance(k, int) else node[k]
        return node == expect
    return check


def text_contains(needle: str, *, absent: bool = False):
    """源码侧作用域自证：变异后的字节里该文本必须（不）存在。"""
    def check(raw: bytes) -> bool:
        present = needle in raw.decode("utf-8", errors="replace")
        return (not present) if absent else present
    return check


def text_both(present: str, absent: str):
    def check(raw: bytes) -> bool:
        s = raw.decode("utf-8", errors="replace")
        return present in s and absent not in s
    return check


MUTATIONS: list[Mutation] = [
    # ══ A. 裁决合法性（SR-3 / SR-4 / SR-5 / AC 12.8 / AP-1 / overlay 陷阱）══
    Mutation(
        id="M01", side="be", path=SLICE, kind="replace",
        scope=K1, offset=OFF_CAPABILITY,
        anchor='      "capability": null,',
        new='      "capability": "single_onlyoffice",',
        want=f"{_ADJ}::test_capability_matches_honest_capability",
        wants=(
            f"{_ADJ}::test_single_onlyoffice_requires_no_html_counterpart",
            f"{_ADJ}::test_capability_is_null_and_pending_fields_are_complete",
            f"{_ADJ}::test_manifest_mirror_divergence_is_registered_not_silently_equal",
            f"{_ADJ}::test_ac15_is_declared_not_applicable_and_ac14_is_the_live_one",
            f"{_P69}::test_summary_counters_recompute_from_the_entries",
            f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",
            f"{_WO}::test_verdict_is_binary_and_not_a_single_adjudication",
            f"{_DEL}::test_plan_entries_mirror_the_slice_adjudication",
            _CONTRACT, _COVERAGE,
        ),
        why="把有 HTML 对端的 entry 硬裁 single_onlyoffice —— AC 12.8 的唯一判据被违反，"
            "SR-4 双口径、SR-2 计数、overlay 分歧判据应同时打红",
        scope_check=entry_field_is(
            "xlsx/gt-k1-other-receivables", ("capability",), "single_onlyoffice"),
    ),
    Mutation(
        id="M02", side="be", path=SLICE, kind="replace",
        scope=K2, offset=OFF_VERDICT_STAGE,
        anchor='      "capability_verdict_stage": "step_4_blocked_by_step_3_result_exists",',
        new='      "capability_verdict_stage": "",',
        want=f"{_ADJ}::test_capability_is_null_and_pending_fields_are_complete",
        wants=(f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",
               _CONTRACT, _COVERAGE),
        why="SR-3 右支：待裁决态的 stage 空串 = 「留空而不解释」，必须仍报违规",
        scope_check=entry_field_is(
            "xlsx/gt-k2-other-current-assets", ("capability_verdict_stage",), ""),
    ),
    Mutation(
        id="M03", side="be", path=SLICE, kind="replace",
        scope=K5, offset=OFF_CAPABILITY_TARGET,
        anchor='      "capability_target": "bidirectional",',
        new='      "capability_target": "dual",',
        want=f"{_ADJ}::test_capability_is_null_and_pending_fields_are_complete",
        wants=(f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",
               _CONTRACT, _COVERAGE),
        why="`dual` 是 AC 1.3 明文禁止的含糊布尔值；capability_target 必须落在四个终态内",
        scope_check=entry_field_is("xlsx/gt-k5-provisions", ("capability_target",), "dual"),
    ),
    Mutation(
        id="M04", side="be", path=SLICE, kind="replace",
        scope=K8, offset=OFF_BLOCKED_FIRST,
        anchor='        "BP-1",',
        new='        "BP-99",',
        want=f"{_ADJ}::test_capability_is_null_and_pending_fields_are_complete",
        wants=(f"{_ADJ}::test_every_blocking_precondition_is_referenced_by_someone",),
        why="capability_target_blocked_by 引用不存在的阻断项 —— 「被什么阻断」必须可核对，"
            "且 BP-1 从此没有引用方（死声明）",
        scope_check=entry_field_is(
            "xlsx/gt-k8-selling-expenses", ("capability_target_blocked_by", 0), "BP-99"),
    ),
    Mutation(
        id="M05", side="be", path=SLICE, kind="replace",
        scope=K9, offset=OFF_HTML_VERDICT_K9,
        anchor='      "html_counterpart_verdict": "exists",',
        new='      "html_counterpart_verdict": "unresolved",',
        want=f"{_ADJ}::test_every_entry_has_a_binary_html_counterpart_verdict",
        wants=(f"{_P69}::test_summary_counters_recompute_from_the_entries",
               f"{_DEL}::test_plan_entries_mirror_the_slice_adjudication"),
        why="AP-3：把「还没查」写成 unresolved 就据此推进 —— 二值结论口径必须拒绝",
        scope_check=entry_field_is(
            "xlsx/gt-k9-admin-expenses", ("html_counterpart_verdict",), "unresolved"),
    ),
    Mutation(
        id="M06", side="be", path=SLICE, kind="replace",
        scope=K11, offset=OFF_MIRROR_CAPABILITY_K11,
        anchor='        "capability": "single_onlyoffice",',
        new='        "capability": "bidirectional",',
        want=f"{_ADJ}::test_manifest_mirror_divergence_is_registered_not_silently_equal",
        why="🔴 overlay 陷阱的核心判据：镜像值必须逐字等于 manifest 现值**且**等于 overlay "
            "默认值。抄错镜像（写成 bidirectional）必须打红，否则「分歧已登记」是自说自话",
        scope_check=entry_field_is(
            "xlsx/gt-k11-asset-impairment-loss",
            ("manifest_mirror", "capability"), "bidirectional"),
    ),
    Mutation(
        id="M07", side="be", path=SLICE, kind="replace",
        scope=K13, offset=OFF_MOUNTS_NOTICE_K13,
        anchor='        "mounts_ac14_notice": false',
        new='        "mounts_ac14_notice": true',
        want=f"{_P3}::test_bp7_is_registered_because_no_host_mounts_the_notice",
        wants=(f"{_P69}::test_summary_counters_recompute_from_the_entries",),
        why="AC 1.4 的挂载事实必须现算：声称挂了而宿主里搜不到组件名 ⇒ 打红",
        scope_check=entry_field_is(
            "xlsx/gt-k13-non-operating-expense",
            ("ui_toolbar_gate", "mounts_ac14_notice"), True),
    ),
    Mutation(
        id="M08", side="be", path=SLICE, kind="replace",
        scope=K2, offset=OFF_SEGMENTED_FIRST_K2,
        anchor="          10",
        new="          375",
        want=f"{_P3}::test_toolbar_gate_anchor_is_unique_resolvable_and_contains_the_switcher",
        wants=(f"{_FORM}::test_kd7_commented_segmented_would_fool_a_raw_grep",),
        why="🔴 KD-7：375 行那处 el-segmented 落在**块注释里**，剥注释后不存在。"
            "把 gate 内分段器行号改成它 ⇒ 「登记 == 剥注释后现算」这条判据必须打红，"
            "否则裸 grep 口径会悄悄通过",
        scope_check=entry_field_is(
            "xlsx/gt-k2-other-current-assets",
            ("ui_toolbar_gate", "segmented_sites_in_gate", 0), 375),
    ),

    # ══ B. 计数现算（SR-1 / SR-2 / SR-9 / 各来源节等值）══
    Mutation(
        id="M09", side="be", path=SLICE, kind="replace",
        anchor='    "total_independent": 13,',
        new='    "total_independent": 12,',
        want=f"{_P69}::test_summary_counters_recompute_from_the_entries",
        wants=(f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",
               _CONTRACT, _COVERAGE),
        why="SR-1：总数手填改错必须打红（计数现算，不许抄）",
        scope_check=top_field_is(("honest_adjudication_summary", "total_independent"), 12),
    ),
    Mutation(
        id="M10", side="be", path=SLICE, kind="replace",
        anchor='      "unadjudicated": 13,',
        new='      "unadjudicated": 0,',
        want=f"{_PARA}::test_the_validator_really_catches_a_counter_mismatch",
        wants=(f"{_ADJ}::test_capability_is_null_and_pending_fields_are_complete",
               f"{_P69}::test_slice_counters_are_all_zero_except_unadjudicated",
               f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",
               _CONTRACT, _COVERAGE),
        why="SR-9：「全记待裁决同时报 0」就是把 SR-3 右支当后门用 —— 必须打红",
        scope_check=top_field_is(
            ("honest_adjudication_summary", "slice_counters", "unadjudicated"), 0),
    ),
    Mutation(
        id="M11", side="be", path=SLICE, kind="replace",
        anchor='      "total_hits": 48,',
        new='      "total_hits": 45,',
        want=f"{_P23}::test_positional_identity_inventory_is_exhaustive_and_partitioned",
        wants=(f"{_P69}::test_derived_counters_recompute_from_their_own_sections",),
        why="把 48 处命中改成 45（等于悄悄把 family_c 的 3 处从分母里拿掉）—— "
            "三族并集必须等于 total_hits",
        scope_check=top_field_is(
            ("dynamic_row_identity", "positional_identity_inventory", "total_hits"), 45),
    ),
    Mutation(
        id="M12", side="be", path=SLICE, kind="replace",
        scope='      "family_a_pure_ordinal": {', offset=3,
        anchor='        "count": 32,',
        new='        "count": 31,',
        want=f"{_P23}::test_positional_identity_inventory_is_exhaustive_and_partitioned",
        wants=(f"{_P69}::test_derived_counters_recompute_from_their_own_sections",),
        why="family_a 计数与 hits 数组长度必须等值（少报一处缺陷即红）",
        scope_check=top_field_is(
            ("dynamic_row_identity", "positional_identity_inventory",
             "family_a_pure_ordinal", "count"), 31),
    ),
    Mutation(
        id="M13", side="be", path=SLICE, kind="replace",
        anchor='      "defect_hits_total": 45,',
        new='      "defect_hits_total": 32,',
        want=f"{_P23}::test_defect_count_and_per_entry_distribution_recompute",
        wants=(f"{_P69}::test_derived_counters_recompute_from_their_own_sections",),
        why="把 family_b 的 13 处下标兜底从缺陷总数里抹掉 —— 「?? 退化也是缺陷」这条判定必须守住",
        scope_check=top_field_is(
            ("dynamic_row_identity", "positional_identity_inventory", "defect_hits_total"), 32),
    ),
    Mutation(
        id="M14", side="be", path=SLICE, kind="replace",
        scope='      "entries_with_zero_defect_hits": [', offset=1,
        anchor='        "K2",',
        new='        "K1",',
        want=f"{_P23}::test_entries_with_zero_defect_hits_are_really_zero",
        wants=(f"{_P69}::test_derived_counters_recompute_from_their_own_sections",),
        why="🔴「某族 0 命中」的反向判据：把 K1（实有 3 处缺陷）说成零命中必须打红，"
            "否则四条零命中 entry 的登记是空谈",
        scope_check=top_field_is(
            ("dynamic_row_identity", "positional_identity_inventory",
             "entries_with_zero_defect_hits", 0), "K1"),
    ),
    Mutation(
        id="M15", side="be", path=SLICE, kind="replace",
        anchor='        "positional_row_id_template": 13',
        new='        "positional_row_id_template": 0',
        want=f"{_P23}::test_hardcoded_scan_recomputes_including_the_non_zero_one",
        wants=(f"{_P23}::test_the_non_zero_pattern_is_a_subset_of_the_positional_hits",
               f"{_P69}::test_derived_counters_recompute_from_their_own_sections"),
        why="🔴 照抄 J 循环「六个模式全 0」的陷阱：K 的第六个是 13。"
            "改成 0 必须打红，否则「不得照抄」这条提醒没有判据撑着",
        scope_check=top_field_is(
            ("dynamic_row_identity", "hardcoded_scan_result", "patterns",
             "positional_row_id_template"), 0),
    ),
    Mutation(
        id="M16", side="be", path=SLICE, kind="replace",
        anchor='      "k_cycle_contribution": 0,',
        new='      "k_cycle_contribution": 3,',
        want=f"{_ORPHAN}::test_shared_base_counts_are_recomputed_both_ways",
        wants=(f"{_P69}::test_derived_counters_recompute_from_their_own_sections",
               f"{_DEL}::test_plan_shared_base_numbers_agree_with_the_slice"),
        why="🔴 KD-3：K 对共享基类贡献 0 条边。抄成 J 的 3 条必须打红",
        scope_check=top_field_is(
            ("orphan_dual_mode_inventory", "shared_base", "k_cycle_contribution"), 3),
    ),
    Mutation(
        id="M17", side="be", path=SLICE, kind="replace",
        anchor='      "statement_position_consumers": 29,',
        new='      "statement_position_consumers": 26,',
        want=f"{_ORPHAN}::test_shared_base_counts_are_recomputed_both_ways",
        wants=(f"{_P69}::test_derived_counters_recompute_from_their_own_sections",
               f"{_DEL}::test_plan_shared_base_numbers_agree_with_the_slice"),
        why="🔴 照抄 J 循环「删完还剩 26」的陷阱：K 循环前后都是 29",
        scope_check=top_field_is(
            ("orphan_dual_mode_inventory", "shared_base",
             "statement_position_consumers"), 26),
    ),
    Mutation(
        id="M18", side="be", path=SLICE, kind="replace",
        anchor='      "orphan_dual_mode_second_order": 0,',
        new='      "orphan_dual_mode_second_order": 2,',
        want=f"{_ORPHAN}::test_orphans_are_all_first_order_because_there_is_no_barrel",
        wants=(f"{_P69}::test_derived_counters_recompute_from_their_own_sections",),
        why="🔴 照抄 J 循环「2 个二阶 orphan + 2 个 barrel」的陷阱：K 的 composables 目录"
            "没有 index.ts barrel，二阶恒 0",
        scope_check=top_field_is(
            ("orphan_dual_mode_inventory", "summary",
             "orphan_dual_mode_second_order"), 2),
    ),
    Mutation(
        id="M19", side="be", path=SLICE, kind="replace",
        scope='        "id": "OD-1",', offset=3,
        anchor='        "lines": 115,',
        new='        "lines": 65,',
        want=f"{_ORPHAN}::test_declared_orphans_really_have_no_reachability",
        wants=(f"{_ORPHAN}::test_orphan_summary_counts_recompute",
               f"{_DEL}::test_plan_orphan_modules_mirror_the_slice_inventory",
               f"{_DEL}::test_plan_counters_recompute"),
        why="行数登记必须与磁盘现算相等（65 是共享基类的行数 —— 抄错对象的典型形态）",
        scope_check=top_field_is(
            ("orphan_dual_mode_inventory", "modules", 0, "lines"), 65),
    ),
    Mutation(
        id="M20", side="be", path=SLICE, kind="replace",
        anchor='      "duplicate_aggregation_found": 0,',
        new='      "duplicate_aggregation_found": 1,',
        want=f"{_ACC}::test_no_duplicated_account_location_or_aggregation_in_k_domain",
        wants=(f"{_P69}::test_derived_counters_recompute_from_their_own_sections",),
        why="「抄了第二份科目定位/聚合」的登记必须与现扫相等 —— 反向也要红（现扫 0 而登记 1）",
        scope_check=top_field_is(
            ("account_scope_and_four_table_audit", "backend_four_table_reuse",
             "duplicate_aggregation_found"), 1),
    ),
    Mutation(
        id="M21", side="be", path=SLICE, kind="replace",
        anchor='    "cross_workbook_fallback_hits": 0,',
        new='    "cross_workbook_fallback_hits": 2,',
        want=f"{_P28}::test_template_resolution_audit_recomputes",
        wants=(f"{_P69}::test_derived_counters_recompute_from_their_own_sections",),
        why="168 个 K 码的解析审计结论必须现跑复算（登记 2 而现算 0 ⇒ 红）",
        scope_check=top_field_is(
            ("template_resolution_audit", "cross_workbook_fallback_hits"), 2),
    ),

    # ══ C. writeoff 能力（tasks.md 正文第二条）══
    Mutation(
        id="M22", side="be", path=SLICE, kind="replace",
        anchor='    "is_client_only": false,',
        new='    "is_client_only": true,',
        want=f"{_WO}::test_verdict_is_binary_and_not_a_single_adjudication",
        wants=(f"{_P69}::test_derived_counters_recompute_from_their_own_sections",),
        why="🔴 把「不是纯客户端」翻成「是」—— 那正是通往「据此裁 single」的错路，必须打红",
        scope_check=top_field_is(
            ("writeoff_capability_resolution", "is_client_only"), True),
    ),
    Mutation(
        id="M23", side="be", path=SLICE, kind="replace",
        anchor='      "K1-9-writeoff": 9,',
        new='      "K1-9-writeoff": 12,',
        want=f"{_WO}::test_declared_transport_keys_hit_counts_recompute",
        why="🔴 12 是**子串口径**的错值（`'K1-9-writeoff-total'` 被算进去）。"
            "精确字面量口径必须拒绝它，否则「现读了 owner 常量」只是自述",
        scope_check=top_field_is(
            ("writeoff_capability_resolution", "declared_key_hit_counts",
             "K1-9-writeoff"), 12),
    ),
    Mutation(
        id="M24", side="be", path=SLICE, kind="replace",
        scope='    "guessed_keys_with_zero_hits": [', offset=1,
        anchor='      "K1-9-rows",',
        new='      "K1-9",',
        want=f"{_WO}::test_guessed_keys_have_zero_hits",
        why="🔴 `K1-9` 是 sheet 码、有 11 处真实命中。把它列进「0 命中」清单必须打红 —— "
            "反向分母不能被稀释成恒真",
        scope_check=top_field_is(
            ("writeoff_capability_resolution", "guessed_keys_with_zero_hits", 0), "K1-9"),
    ),
    Mutation(
        id="M25", side="be", path=WRITEOFF_OWNER, kind="replace",
        anchor="const ITEM_ID = 'K1-9-writeoff'",
        new="const ITEM_ID = 'K1-9-writeoff-v2'",
        want=f"{_WO}::test_owner_constants_are_read_from_source_not_copied",
        wants=(f"{_WO}::test_declared_transport_keys_hit_counts_recompute",
               f"{_SELF}::test_const_literal_reads_from_source_not_from_comment"),
        why="🔴 对**真源码常量**变异：改了 owner 常量而 slice 登记没跟 ⇒ 必须打红。"
            "这是第③边（impl 现读）的唯一证明",
        scope_check=text_both("const ITEM_ID = 'K1-9-writeoff-v2'",
                              "const ITEM_ID = 'K1-9-writeoff'\n"),
    ),
    Mutation(
        id="M26", side="be", path=WRITEOFF_OWNER, kind="replace",
        anchor="  const reversalTotal: ComputedRef<number> = computed(() =>",
        new="  const reversalTotal = { value: 0 } as unknown as ComputedRef<number>; ((() =>",
        want=f"{_WO}::test_property_24_derived_totals_are_computed_and_write_only",
        why="🔴 Property 24 的**真分母**：合计键必须是派生态（computed）。"
            "改成常量后「它是派生值、adapter 不得当录入」这条前提性质失守 ⇒ 打红",
        scope_check=text_both(
            "const reversalTotal = { value: 0 }",
            "const reversalTotal: ComputedRef<number> = computed"),
    ),
    Mutation(
        id="M27", side="be", path=WRITEOFF_OWNER, kind="replace",
        anchor="      conclusionOption.value = data.conclusionOption ?? ''",
        new="      conclusionOption.value = data.conclusionOption ?? ''\n"
            "      if (data[REVERSAL_TOTAL_KEY]) reversalRows.value = []",
        want=f"{_WO}::test_property_24_derived_totals_are_computed_and_write_only",
        why="🔴 **反向式**源码变异：让 `load()` 开始回读派生合计键 ⇒ summary 从「只写不读」"
            "变成可被回灌覆盖，Property 24 的受保护性质失守，必须打红",
        scope_check=text_contains("if (data[REVERSAL_TOTAL_KEY]) reversalRows.value = []"),
    ),

    # ══ D. K1/K2 scope 与四表真源（tasks.md 正文第一条）══
    Mutation(
        id="M28", side="be", path=K1_SCOPE, kind="replace",
        anchor="export const K1_BAD_DEBT_FALLBACK_STANDARD = '1231-03'",
        new="export const K1_BAD_DEBT_FALLBACK_STANDARD = '1231'",
        want=f"{_ACC}::test_k1_and_k2_scope_derive_from_render_issued_tb_source_codes",
        why="🔴 宽口径 `1231` 会把 D1/D2 的坏账一起吃进来（K2 文件头注释记录的历史缺陷）。"
            "回归到宽口径必须打红",
        scope_check=text_both("K1_BAD_DEBT_FALLBACK_STANDARD = '1231'",
                              "K1_BAD_DEBT_FALLBACK_STANDARD = '1231-03'"),
    ),
    Mutation(
        id="M29", side="be", path=K2_SCOPE, kind="replace",
        anchor="import { tbQueryCodes, type TbSourceCodes } from './shared/tbSourceCodes'",
        new="type TbSourceCodes = Record<string, string[]>; "
            "const tbQueryCodes = (a: unknown, b: string) => [b]",
        want=f"{_ACC}::test_k1_and_k2_scope_derive_from_render_issued_tb_source_codes",
        why="🔴 抄第二份而不复用共享真源：本地重定义 tbQueryCodes ⇒ 运行态不再取 render "
            "下发的 tb_source_codes，「真从真源派生」这条判据必须打红",
        scope_check=text_both("const tbQueryCodes = (a: unknown, b: string) => [b]",
                             "from './shared/tbSourceCodes'"),
    ),
    Mutation(
        id="M30", side="be", path=K8_STRATEGY, kind="replace",
        anchor="from app.services.four_table.pl_render import render_pl_cycle",
        new="from app.services.four_table.leaf_aggregation import select_leaves",
        want=f"{_ACC}::test_balance_side_uses_leaf_aggregation_and_pl_side_uses_pl_render",
        why="🔴 分支判据的**损益侧**：K8 是损益类，必须走共享 render_pl_cycle。"
            "换成 select_leaves ⇒ 分支判据打红（同时验证它不是统一口径的空跑）",
        scope_check=text_both(
            "from app.services.four_table.leaf_aggregation import select_leaves",
            "from app.services.four_table.pl_render import render_pl_cycle"),
    ),
    Mutation(
        id="M31", side="be", path=K_SPECS, kind="replace",
        anchor="from .report_line_accounts import ReportLineAccountSpec",
        new="ReportLineAccountSpec = dict  # type: ignore[assignment,misc]",
        want=f"{_ACC}::test_backend_k_cycle_specs_uses_the_shared_report_line_spec",
        wants=(f"{_ACC}::test_all_thirteen_render_strategies_import_k_cycle_specs",),
        why="🔴 抄第二份科目定位逻辑的最短路径：不再 import 共享的 ReportLineAccountSpec。"
            "「四表真源复用」这条判据必须打红",
        scope_check=text_both("ReportLineAccountSpec = dict",
                             "from .report_line_accounts import ReportLineAccountSpec"),
    ),

    # ══ E. 消费边可达性与宿主形态（源码侧，含反向变异）══
    Mutation(
        id="M32", side="be", path=HOST_K1, kind="replace",
        anchor='      <div v-if="isHtmlSheet && currentSheet !== \'K1\'" class="k1-header-toolbar">',
        new='      <div v-if="isHtmlSheet && currentSheet !== \'K1\'" class="k1-toolbar-renamed">',
        want=f"{_P3}::test_toolbar_gate_anchor_is_unique_resolvable_and_contains_the_switcher",
        why="🔴 AC 1.4 的挂载点必须落在该 entry 自己声明的 ui_toolbar_gate 区块内。"
            "toolbar 容器改名 ⇒ 锚点失效，判据必须打红（而不是退化成全文件 grep）",
        scope_check=text_both('class="k1-toolbar-renamed"', 'class="k1-header-toolbar"'),
    ),
    Mutation(
        id="M33", side="be", path=REGISTRY_TS, kind="replace",
        anchor="    component: defineAsyncComponent(() => import('./GtK5Provisions.vue')),",
        new="    component: defineAsyncComponent(() => import('./GtKamWorkpaper.vue')),",
        want=f"{_SCOPE}::test_host_module_edges_in_the_renderer_registry_are_real",
        why="🔴「入口可达」用 htmlRendererRegistry 的**模块边**判、不按符号名 grep。"
            "把 K5 的模块边换成别的文件 ⇒ 可达性判据打红",
        scope_check=text_both("import('./GtKamWorkpaper.vue')",
                             "import('./GtK5Provisions.vue')"),
    ),
    Mutation(
        id="M34", side="be", path=K1_ORPHAN, kind="replace",
        anchor="const STORAGE_PREFIX = 'k1-dual-mode:'",
        new="const STORAGE_PREFIX = 'workpaper-sync-mode:'",
        want=f"{_ORPHAN}::test_orphan_and_host_twin_prefix_relationship_recomputes",
        why="orphan 的持久化前缀必须现读（不是抄登记）。改前缀 ⇒ 登记与现读不等 ⇒ 打红",
        scope_check=text_both("const STORAGE_PREFIX = 'workpaper-sync-mode:'",
                             "const STORAGE_PREFIX = 'k1-dual-mode:'"),
    ),
    Mutation(
        id="M35", side="be", path=K1_ORPHAN, kind="replace",
        anchor="      const response = await fetch('/api/workpapers/onlyoffice/health')",
        new="      const response = { ok: true, json: async () => ({ healthy: false }) } as any",
        want=f"{_ORPHAN}::test_legacy_endpoint_direct_calls_are_registered_per_class",
        wants=(f"{_ORPHAN}::test_orphan_summary_counts_recompute",
               f"{_DEL}::test_plan_counters_recompute"),
        why="🔴 **反向变异**：删掉 legacy health 端点直调（缺陷被修好）⇒ 端点计数 13 → 12，"
            "登记没跟就必须打红。只验「新增缺陷」一个方向是半个判据",
        scope_check=text_both("const response = { ok: true, json: async () => "
                              "({ healthy: false }) } as any",
                              "fetch('/api/workpapers/onlyoffice/health')"),
    ),
    Mutation(
        id="M36", side="be", path=HOST_K1, kind="insert",
        anchor="import http from '@/utils/http'",
        new="import { useK1DualMode } from './composables/useK1DualMode'",
        want=f"{_ORPHAN}::test_declared_orphans_really_have_no_reachability",
        wants=(f"{_ORPHAN}::test_live_modules_have_exactly_one_edge_to_the_declared_host",
               f"{_FORM}::test_kd2_carrier_split_is_real_and_exclusive"),
        why="🔴 **反向变异**：让 orphan 变成活桩（宿主真 import 它）⇒ "
            "「7 个一阶 orphan、生产边各 0」必须打红。这条同时证明消费边是 statement-position "
            "路径口径而不是「文件里出现过这个名字」",
        scope_check=text_contains(
            "import { useK1DualMode } from './composables/useK1DualMode'"),
    ),
    Mutation(
        id="M37", side="be", path=HOST_K2, kind="insert",
        anchor='      <div v-if="isHtmlSheet && currentSheet !== \'K2\'" class="k2-header-toolbar">',
        new="        <GtEntrySyncCapabilityNotice :entry-id=\"'xlsx/gt-k2-other-current-assets'\" />",
        want=f"{_P3}::test_bp7_is_registered_because_no_host_mounts_the_notice",
        wants=(f"{_P69}::test_summary_counters_recompute_from_the_entries",),
        why="🔴 **反向变异**：在 K2 宿主的 toolbar 区块里真挂上 AC 1.4 的提示组件 ⇒ "
            "BP-7 可解除、`entries_mounting_the_ac14_notice` 从 0 变 1，登记没跟必须打红",
        scope_check=text_contains("<GtEntrySyncCapabilityNotice"),
    ),
    Mutation(
        id="M38", side="be", path=K9_SOE, kind="replace",
        anchor="    id: `row-${idx}`,",
        new="    id: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,",
        want=f"{_P23}::test_positional_identity_inventory_is_exhaustive_and_partitioned",
        wants=(f"{_P23}::test_defect_count_and_per_entry_distribution_recompute",
               f"{_P23}::test_hardcoded_scan_recomputes_including_the_non_zero_one"),
        why="🔴 **反向变异**：把 BP-8 的一处 family_a 位置化身份**修好**（改成带熵的稳定 id）"
            "⇒ family_a 32 → 31、K9 的逐 entry 分布 7 → 6、模板模式 13 → 12。"
            "缺陷修好而登记没删也必须打红，否则报告会长期挂着一条已解决的债",
        scope_check=text_both(
            "id: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,",
            "    id: `row-${idx}`,\n"),
    ),

    # ══ F. 模板层与跨 entry 隔离 ══
    Mutation(
        id="M39", side="be", path=SLICE, kind="replace",
        scope='        "name": "K11 资产减值损失.xlsx",', offset=2,
        anchor='        "sha256": "dc0e5434b7c8e345913864ce524ad30a0a3729b5655627f3c30bce52294a9190",',
        new='        "sha256": "0000000000000000000000000000000000000000000000000000000000000000",',
        want=f"{_P28}::test_authoritative_template_digests_recompute",
        why="Property 28：模板 digest 现算比对，任一漂移 fail closed（全零 hash 是典型占位）",
        # 🔴 files[] 按**文件名字符串**排序 ⇒ K11 在 index **3**（K0 / K1 / K10 / K11 …），
        # 不是「K11 是第 11 本」直觉上的 4。首轮按直觉写 4 ⇒ ANCHOR-MISS（脚本缺陷，
        # 不是守卫缺陷）。这正是「只看退出码会把 ANCHOR-MISS 误判成 RED」要防的那一态。
        scope_check=top_field_is(
            ("authoritative_templates", "files", 3, "sha256"), "0" * 64),
    ),
    Mutation(
        id="M40", side="be", path=SLICE, kind="replace",
        scope='        "name": "K0 管理循环函证.xlsx",', offset=17,
        anchor='        "belongs_to_entry": null,',
        new='        "belongs_to_entry": "xlsx/gt-k1-other-receivables",',
        want=f"{_P28}::test_template_owner_mapping_is_injective_with_reasoned_nulls",
        wants=(f"{_SCOPE}::test_k0_confirmation_workbook_exists_but_has_no_entry",
               f"{_FORM}::test_kd4_template_count_exceeds_entry_count_by_the_k0_book",
               f"{_P69}::test_derived_counters_recompute_from_their_own_sections"),
        why="🔴 把 K0 函证册硬挂到 K1 上 ⇒ 模板→entry 不再是单射（K1 有两本册），"
            "且 K0 的排除结论被抹掉。SR-8 与 KD-4 必须同时打红",
        scope_check=top_field_is(
            ("authoritative_templates", "files", 0, "belongs_to_entry"),
            "xlsx/gt-k1-other-receivables"),
    ),
    Mutation(
        id="M41", side="be", path=SLICE, kind="replace",
        scope='    "production_contract_files": [', offset=1,
        anchor='      "b60.hour_budget.json",',
        new='      "_example.candidate.json",',
        want=f"{_SCOPE}::test_no_pilot_contract_belongs_to_the_k_cycle",
        why="🔴 把 candidate 样例登记成生产契约 ⇒ step 6「candidate 不得注册生产 adapter」"
            "的反例分母被污染，判据必须打红",
        scope_check=top_field_is(
            ("cross_entry_isolation", "production_contract_files", 0),
            "_example.candidate.json"),
    ),
    Mutation(
        id="M42", side="be", path=SLICE, kind="replace",
        scope='  "sibling_slices": [', offset=1,
        anchor='    "backend/data/workpaper_sync_d_cycle_manifest_slice.json",',
        new='    "backend/data/workpaper_sync_z_cycle_manifest_slice.json",',
        want=f"{_P70}::test_sibling_slices_declared_match_the_disk",
        why="Property 70：兄弟 slice 清单必须与磁盘等值（写一个不存在的循环即红）",
        scope_check=top_field_is(
            ("sibling_slices", 0),
            "backend/data/workpaper_sync_z_cycle_manifest_slice.json"),
    ),

    # ══ G. deletion plan 与范式合规 ══
    Mutation(
        id="M43", side="be", path=PLAN, kind="replace",
        anchor='    "shared_base_consumers_after": 29,',
        new='    "shared_base_consumers_after": 26,',
        want=f"{_DEL}::test_plan_shared_base_numbers_agree_with_the_slice",
        wants=(f"{_DEL}::test_plan_counters_recompute",),
        why="🔴 照抄 J 的「29 → 26」：K 循环执行前后都是 29",
        scope_check=lambda raw: _doc(raw)["counters"]["shared_base_consumers_after"] == 26,
    ),
    Mutation(
        id="M44", side="be", path=PLAN, kind="replace",
        anchor='    "host_inlined_blocks_to_remove": 7,',
        new='    "host_inlined_blocks_to_remove": 0,',
        want=f"{_DEL}::test_plan_host_inlined_blocks_are_real",
        wants=(f"{_DEL}::test_plan_counters_recompute",),
        why="🔴 照抄 J 的「hosts_with_inlined_second_implementation = 0」：K 有 7 处内联 IIFE。"
            "报 0 等于把这 7 段代码从删除清单里漏掉",
        scope_check=lambda raw: _doc(raw)["counters"]["host_inlined_blocks_to_remove"] == 0,
    ),
    Mutation(
        id="M45", side="be", path=PLAN, kind="replace",
        scope='      "entry_id": "xlsx/gt-k1-other-receivables",',
        offset=OFF_MUST_NOT_WIRE_FIRST_K1,
        anchor='        "audit-platform/frontend/src/components/workpaper/composables/useK1DualMode.ts"',
        new='        "audit-platform/frontend/src/components/workpaper/composables/useK9DualMode.ts"',
        want=f"{_DEL}::test_plan_must_not_wire_to_targets_are_the_orphan_twins",
        why="🔴 must_not_wire_to 必须逐条覆盖 orphan 孪生集合（指错对象 ⇒ 改线时仍会误接 "
            "useK1DualMode）",
        scope_check=lambda raw: any(
            "useK9DualMode.ts" in t
            for e in _doc(raw)["entries"] for t in e["must_not_wire_to"]),
    ),
]

GUARD_FILES = {
    T53: "Task 53 新建 —— K 循环迁移守卫",
    _CONTRACT: "范式校验器（本 slice 必须过它，且反例两侧都验）",
    _COVERAGE: "校验器覆盖面（scan_glob 自动收本 slice，_UNJUDGED_SLICES 必须为空）",
}

if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="Task 53 · K 循环 Excel 独立 entry 迁移守卫变异检验",
            backend_args=[
                "backend/tests/workpaper_sync/test_task53_k_cycle_migration.py",
                "backend/tests/workpaper_sync/test_migration_paradigm_contract.py",
                "backend/tests/workpaper_sync/test_slice_schema_validator_coverage.py",
                "-p", "no:randomly", "-q",
            ],
        )
    )
