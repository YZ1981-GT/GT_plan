# -*- coding: utf-8 -*-
r"""Task 55 守卫变异检验 —— M 循环（权益循环）Excel 独立 entry 迁移。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 5 Task 55

用平台共享件 `backend/scripts/_mutation_kit`（`test_mutation_kit_adoption.py` 对新脚本强制
采纳：共享件的 `run_cli` 把 `guard_files`（覆盖面分母）做成签名层面必填，把「锚点含换行」
「new == anchor」「id 重复」「want 定位不到」全部拦在声明期）。

═══ 本脚本的五条硬约束 ═══

1. **每条变异都带 `scope_check`**。四态判定式「新增失败集合是否为空」识别不出「锚点落在被测
   判据的作用域之外」—— 改到了别处会被判 GREEN（守卫缺陷），而真相是脚本缺陷。
   🔴 Task 54 的 M10 教训：`scope_check` **必须解析 JSON 定位到目标节**，
   不能用「文本里不存在某字面量」当判据 —— 同一字面量常出现在散文里，那种判据恒假。
   本脚本的数据侧回调一律 `json.loads` 后按路径取值断言。

2. **重复形态字段用 `scope` + `offset` 相对定位，绝不用绝对行号**。本 slice 有 **10 条** entry，
   故 entry 级字段全是 dup=10。这些一律以该 entry 唯一的 `"entry_id": "…"` 行作 `scope`，
   `offset` 由 `tmp_task55_off.py` 一次性诊断**实算**（非估计值）：
   capability=+5 · verdict_stage=+6 · capability_target=+7 ·
   html_counterpart_verdict=+19(M1) / +21(M2) / +18(M9) / +21(M10) ·
   manifest_mirror.capability=+58(M1) / +60(M2) / +57(M9) / +60(M10)。
   🔴 **逐 entry 的 offset 不相等**（各 entry 的 reason/source_refs 文本行数不同）⇒ 必须逐 entry 实算。

3. **变异按「可区分的错法」枚举而不是逐条目复制**。10 条 entry 形态同构，逐条各写一次是同
   信息量的重复。这里按错法分组，并分布在不同 entry 上（M1/M2/M9/M10），从而同时走通各 entry 的 offset。

4. **必须含反向变异**（把缺陷修好也要打红）。只验「新增缺陷」一个方向是半个判据：
   缺陷被修好而登记没删，报告会长期挂着一条已解决的债。本脚本的反向变异：
   * M31 把 M2 的一处 SHEET_MAP 错映射**修好**（缺陷数 11 → 10）；
   * M34 把 M10 的 `国有企业` 改成 `国企`（BP-12 可解除，国企披露 sheet 变可达）；
   * M35 把 M1 审定表的位置化持久化键换成稳定行身份（BP-10 可解除，命中数 44 → 41）；
   * M43 在 M1 宿主里**真挂上** AC 1.4 的 notice 组件（BP-7 可解除）。

═══ 为什么要对**真源码**做变异（M31~M44）═══

数据侧变异只能证明「守卫读了 slice」；只有改真源码还打红，才能证明 impl 侧是**现读**而不是
抄了一份快照。M 循环的判据里有九类必须有源码变异撑着：
① SHEET_MAP × 权威册的三边（M31 / M32）· ② 开关三要素与 no_switch 对照组（M33 / M44）·
③ Q 表三待遇与 dispatch 顺序（M36）· ④ BP-12 的可达性（M34）·
⑤ 持久化键位置化身份（M35）· ⑥ 共享基类无 localStorage（M37）·
⑦ 受保护字段三类只读来源与包装关系（M39 / M40）· ⑧ 硬编码族的非空跑（M41）·
⑨ 渲染器模块边与 item_id 命名空间（M42 / M38）。

用法（仓库根；本仓库 PATH 上的 `python` 可能指向坏掉的解释器，必须用显式解释器）::

    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task55_m_cycle_guards.py --list
    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task55_m_cycle_guards.py --check-anchors
    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task55_m_cycle_guards.py --run M01,M02,M03

🔴 **禁止后台执行**：外层 shell 被杀会让 python 变成孤儿进程，与前台运行同时变异同一文件 ⇒
`RestoreFailed` rc=5。分批跑用 `--run M01,M02,...`（子集运行不做覆盖面结论）。

🔴 **`delete` 不要用在数组末元素上**：删掉末元素会给前一行留下尾逗号、JSON 失效，
`scope_check` 的 `json.loads` 抛异常 ⇒ 判定 ERROR（脚本缺陷，不是守卫缺陷）。一律用 `replace`。

🔴 **运行前把并发遗留的 `backend/scripts/**/*.mutbak` 移到仓库外**（`%TEMP%`），否则
`_mutation_kit` 的残留扫描会 `[ABORT]`。跑完原位放回并核验 sha256；**绝不 `--restore`**。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

# ── 被变异的对象 ───────────────────────────────────────────────────────────
SLICE = "backend/data/workpaper_sync_m_cycle_manifest_slice.json"
PLAN = "backend/data/workpaper_sync_m_cycle_deletion_plan.json"
FE = "audit-platform/frontend/src"
WP = f"{FE}/components/workpaper"
COMP = f"{WP}/composables"
HOST_M1 = f"{WP}/GtM1DividendsPayable.vue"
HOST_M6 = f"{WP}/GtM6RetainedEarnings.vue"
HOST_M9 = f"{WP}/GtM9OtherComprehensiveIncome.vue"
HOST_M10 = f"{WP}/GtM10OtherEquityInstruments.vue"
MAP_M2 = f"{COMP}/useM2EntryDualMode.ts"
MAP_M9 = f"{COMP}/useM9EntryDualMode.ts"
ADJ_M1 = f"{COMP}/useM1Adjudication.ts"
DETAIL_M1 = f"{COMP}/useM1Detail.ts"
FORMDATA_M1 = f"{COMP}/useM1FormData.ts"
CLASSIFY_M10 = f"{COMP}/useM10ClassificationCheck.ts"
SHARED_BASE = f"{COMP}/useWorkpaperEntryDualMode.ts"
REGISTRY_TS = f"{WP}/htmlRendererRegistry.ts"
CONFLICTS_PY = "backend/app/services/workpaper_sync/conflicts.py"
REMATERIALIZE_PY = "backend/app/services/workpaper_sync/excel_rematerialize.py"

# ── 期望打红的守卫（文件::类::方法，与 pytest 的 short nodeid 同形）─────────
T55 = "test_task55_m_cycle_migration.py"
_SELF = f"{T55}::TestGuardSelfChecks"
_SCOPE = f"{T55}::TestSliceScopeIsRecomputable"
_ADJ = f"{T55}::TestAdjudicationLegality"
_HTML = f"{T55}::TestHtmlCounterpartIsSourceBacked"
_FORM = f"{T55}::TestMCycleFormDifferences"
_ORPHAN = f"{T55}::TestOrphanDualModeInventory"
_SWITCH = f"{T55}::TestModeSwitchResolution"
_SHEET = f"{T55}::TestSheetGranularityAndRouter"
_P24 = f"{T55}::TestProperty24ProtectedFormulaAndSummary"
_P28 = f"{T55}::TestProperty28DefinitionDriftFailClosed"
_P69 = f"{T55}::TestProperty69EvidenceAndCounters"
_P70 = f"{T55}::TestProperty70CrossEntryIsolation"
_DEL = f"{T55}::TestDeletionPlanConsistency"
_PARA = f"{T55}::TestParadigmCompliance"
_CONTRACT = "test_migration_paradigm_contract.py"
_COVERAGE = "test_slice_schema_validator_coverage.py"


def EID(slug: str) -> str:
    """某 entry 在 `independent_entries` 里唯一的 scope 行（dup=1，3 空格缩进）。"""
    return '   "entry_id": "xlsx/%s",' % slug


M1 = EID("gt-m1-dividends-payable")
M2 = EID("gt-m2-paid-in-capital")
M9 = EID("gt-m9-other-comprehensive-income")
M10 = EID("gt-m10-other-equity-instruments")

#: 逐字段 offset（由 `tmp_task55_off.py` 实算，非估计值）。
OFF_CAPABILITY = 5
OFF_VERDICT_STAGE = 6
OFF_CAPABILITY_TARGET = 7
OFF_HTML_VERDICT = {"M1": 19, "M2": 21, "M9": 18, "M10": 21}
OFF_MIRROR_CAPABILITY = {"M1": 58, "M2": 60, "M9": 57, "M10": 60}
#: orphan 模块块：`"file"` 行 → `"production_consumers"` 行。
OFF_ORPHAN_PROD = 3

ORPHAN_M1_FILE = f'    "file": "{COMP}/useM1DualMode.ts",'


# ══════════════════════════════════════════════════════════════════════════
# scope_check 工具：一律解析 JSON 定位到目标节（Task 54 的 M10 教训）
# ══════════════════════════════════════════════════════════════════════════
def _doc(data: bytes) -> dict:
    return json.loads(data.decode("utf-8"))


def _entry(data: bytes, entry_id: str) -> dict:
    for e in _doc(data)["independent_entries"]:
        if e["entry_id"] == entry_id:
            return e
    raise AssertionError(f"变异后的 slice 里找不到 entry {entry_id}")


def entry_field_is(entry_id: str, key: str, expected: Any):
    def check(data: bytes) -> bool:
        return _entry(data, entry_id).get(key, "<missing>") == expected
    return check


def entry_field_absent(entry_id: str, key: str):
    def check(data: bytes) -> bool:
        return key not in _entry(data, entry_id)
    return check


def entry_path_is(entry_id: str, path: tuple[str, ...], expected: Any):
    def check(data: bytes) -> bool:
        node: Any = _entry(data, entry_id)
        for step in path:
            node = node[step]
        return node == expected
    return check


def doc_path_is(path: tuple[str, ...], expected: Any):
    def check(data: bytes) -> bool:
        node: Any = _doc(data)
        for step in path:
            node = node[step] if not isinstance(step, int) else node[step]
        return node == expected
    return check


def doc_path_pred(path: tuple[Any, ...], pred):
    def check(data: bytes) -> bool:
        node: Any = _doc(data)
        for step in path:
            node = node[step]
        return bool(pred(node))
    return check


def text_has(needle: str, *, present: bool = True):
    """源码侧回调：断言改动确实落在那段文本上。"""
    def check(data: bytes) -> bool:
        return (needle in data.decode("utf-8")) is present
    return check


def text_counts(needle: str, expected: int):
    def check(data: bytes) -> bool:
        return data.decode("utf-8").count(needle) == expected
    return check


BE_ARGS = [
    "backend/tests/workpaper_sync/test_task55_m_cycle_migration.py",
    "backend/tests/workpaper_sync/test_migration_paradigm_contract.py",
    "backend/tests/workpaper_sync/test_slice_schema_validator_coverage.py",
    "-q", "--tb=no", "-rf", "-p", "no:randomly",
]

GUARD_FILES = {
    "test_task55_m_cycle_migration.py": "Task 55 新建：M 循环逐 entry 迁移守卫",
    "test_migration_paradigm_contract.py": "范式校验器（本轮 slice 进它的 scan_glob 分母）",
    "test_slice_schema_validator_coverage.py": "校验器覆盖面（_UNJUDGED_SLICES 必须保持空）",
}


# ══════════════════════════════════════════════════════════════════════════
# 变异清单
# ══════════════════════════════════════════════════════════════════════════
MUTATIONS: list[Mutation] = [
    # ── A. slice 范围与裁决合法性（数据侧）──────────────────────────────
    Mutation(
        id="M01", side="be", path=SLICE, kind="replace",
        anchor='  "independent_entry_count": 10,',
        new='  "independent_entry_count": 9,',
        want=f"{_SCOPE}::test_scope_counters_match_the_manifest",
        wants=(f"{_CONTRACT}::",),
        why="SR-1 要求 scope 计数 == len(independent_entries) == manifest 现算集合大小。"
            "改 9 后既该打红本轮守卫，也该被范式校验器的 SR-1 拦住（两个判官同向）。",
        scope_check=doc_path_is(("slice_scope", "independent_entry_count"), 9),
    ),
    Mutation(
        id="M02", side="be", path=SLICE, kind="replace",
        anchor='  "m_prefixed_entry_total": 10,',
        new='  "m_prefixed_entry_total": 11,',
        want=f"{_SCOPE}::test_scope_counters_match_the_manifest",
        why="M 前缀 entry 总数从 manifest 现算；写 11 = 凭空多一条。"
            "这条与 M01 不同：它验的是「与 manifest 的 M 前缀集合」而非「与 slice 自身条数」。",
        scope_check=doc_path_is(("slice_scope", "m_prefixed_entry_total"), 11),
    ),
    Mutation(
        id="M03", side="be", path=SLICE, kind="replace",
        scope=M1, offset=OFF_CAPABILITY,
        anchor='   "capability": null,',
        new='   "capability": "single_onlyoffice",',
        want=f"{_ADJ}::test_single_onlyoffice_requires_no_html_counterpart",
        wants=(f"{_ADJ}::test_capability_matches_honest_capability",
               f"{_ADJ}::test_capability_is_null_and_pending_fields_are_complete",
               f"{_CONTRACT}::"),
        why="AC 12.8 的唯一合法判据是「无 HTML 对端」。M1 的 html_counterpart_verdict 是 exists ⇒ "
            "硬填 single_onlyoffice 是伪造裁决（AP-1 的镜像形态），三条判据 + 范式校验器都该红。",
        scope_check=entry_field_is("xlsx/gt-m1-dividends-payable", "capability", "single_onlyoffice"),
    ),
    Mutation(
        id="M04", side="be", path=SLICE, kind="replace",
        scope=M2, offset=OFF_VERDICT_STAGE,
        anchor='   "capability_verdict_stage": "step_4_blocked_by_step_3_result_exists",',
        new='   "capability_verdict_stage": "",',
        want=f"{_ADJ}::test_capability_is_null_and_pending_fields_are_complete",
        wants=(f"{_CONTRACT}::",),
        why="SR-3 右支的 `pending_verdict_field_semantics` 规定该字段是 non_empty_string；"
            "空串 = 「留空而不解释」，必须被拦。",
        scope_check=entry_field_is("xlsx/gt-m2-paid-in-capital", "capability_verdict_stage", ""),
    ),
    Mutation(
        id="M05", side="be", path=SLICE, kind="replace",
        scope=M9, offset=OFF_CAPABILITY_TARGET,
        anchor='   "capability_target": "bidirectional",',
        new='   "capability_target": "dual",',
        want=f"{_ADJ}::test_capability_is_null_and_pending_fields_are_complete",
        wants=(f"{_CONTRACT}::",),
        why="AC 1.3 逐字禁止含糊的 `dual`；`capability_target` 必须落在四值枚举内。"
            "扩枚举等于改 AC，故这条必须红。",
        scope_check=entry_field_is("xlsx/gt-m9-other-comprehensive-income", "capability_target", "dual"),
    ),
    Mutation(
        id="M06", side="be", path=SLICE, kind="replace",
        scope=M10, offset=OFF_HTML_VERDICT["M10"],
        anchor='   "html_counterpart_verdict": "exists",',
        new='   "html_counterpart_verdict": "unresolved",',
        want=f"{_ADJ}::test_every_entry_has_a_binary_html_counterpart_verdict",
        wants=(f"{_P69}::test_summary_counters_recompute_from_the_entries", f"{_CONTRACT}::"),
        why="AP-3：`unresolved` 不是结论。step 3 必须产出二值之一，"
            "把「还没查」写成 unresolved 再据此裁 single 是本 spec 明禁的路。",
        scope_check=entry_field_is("xlsx/gt-m10-other-equity-instruments",
                                   "html_counterpart_verdict", "unresolved"),
    ),
    Mutation(
        id="M07", side="be", path=SLICE, kind="replace",
        scope=M1, offset=OFF_MIRROR_CAPABILITY["M1"],
        anchor='    "capability": "single_onlyoffice",',
        new='    "capability": null,',
        want=f"{_ADJ}::test_manifest_mirror_divergence_is_registered_not_silently_equal",
        why="🔴 manifest_mirror 的判据是「必须**不**一致且已登记 BP-9」，不是断言相等。"
            "把 mirror 改成与裁决一致 = 让 overlay 默认值冒充逐 entry 裁决（AP-3）⇒ 必须红。"
            "若守卫写成「断言相等」，这条变异会变绿 —— 那正是要防的方向。",
        scope_check=entry_path_is("xlsx/gt-m1-dividends-payable", ("manifest_mirror", "capability"), None),
    ),
    Mutation(
        id="M08", side="be", path=SLICE, kind="replace",
        anchor='   "unadjudicated": 10,',
        new='   "unadjudicated": 0,',
        want=f"{_P69}::test_slice_counters_are_all_zero_except_unadjudicated",
        wants=(f"{_CONTRACT}::",),
        why="SR-9：待裁决条数必须等于 slice_counters.unadjudicated。报 0 = 「把全部 entry 记成"
            "待裁决同时报 0」这个后门，范式 owner 专门为它加了 SR-9。",
        scope_check=doc_path_is(("honest_adjudication_summary", "slice_counters", "unadjudicated"), 0),
    ),
    Mutation(
        id="M09", side="be", path=SLICE, kind="replace",
        scope=M9, offset=OFF_CAPABILITY,
        anchor='   "capability": null,',
        new='   "capability": "unreachable",',
        want=f"{_ADJ}::test_capability_matches_honest_capability",
        wants=(f"{_P69}::test_summary_counters_recompute_from_the_entries", f"{_CONTRACT}::"),
        why="M9 的宿主经 htmlRendererRegistry 的模块边可达（现算命中 1 条）⇒ 裁 unreachable 是"
            "伪造裁决。同时 SR-2 的 `adjudicated_as_unreachable` 计数会不匹配。",
        scope_check=entry_field_is("xlsx/gt-m9-other-comprehensive-income", "capability", "unreachable"),
    ),

    # ── B. BP 与 evidence 归属（数据侧）────────────────────────────────
    Mutation(
        id="M10", side="be", path=SLICE, kind="replace",
        anchor='  "capability_verdict_pending": 10,',
        new='  "capability_verdict_pending": 9,',
        want=f"{_P69}::test_summary_counters_recompute_from_the_entries",
        why="summary 的每一族计数都必须从来源节现算。这一条验「entries 族」。",
        scope_check=doc_path_is(("honest_adjudication_summary", "capability_verdict_pending"), 9),
    ),
    Mutation(
        id="M11", side="be", path=SLICE, kind="replace",
        anchor='    "hardcoded_patterns_at_zero": 6,',
        new='    "hardcoded_patterns_at_zero": 0,',
        want=f"{_P69}::test_hardcoded_scan_is_all_zero_and_non_vacuous",
        wants=(f"{_P69}::test_derived_counters_recompute_from_their_own_sections",),
        why="🔴 Task 54 的 M28/M29 教训：`hardcoded_pattern_*` 与位置化族两组摘要计数曾被漏掉。"
            "这条与 M12 一起证明本轮的 `test_derived_counters_…` 真覆盖了这两族。",
        scope_check=doc_path_is(
            ("dynamic_row_identity", "hardcoded_pattern_scan", "counters", "hardcoded_patterns_at_zero"), 0),
    ),
    Mutation(
        id="M12", side="be", path=SLICE, kind="replace",
        anchor='  "positional_identity_persistence_key_hits": 44,',
        new='  "positional_identity_persistence_key_hits": 1,',
        want=f"{_P69}::test_derived_counters_recompute_from_their_own_sections",
        why="🔴 把 M 的主形态计数改成 L 那套扫描器的命中数（1）—— 正是「照抄前轮扫描器」的具体错法。"
            "若守卫沿用旧口径，这条会变绿。",
        scope_check=doc_path_is(
            ("honest_adjudication_summary", "positional_identity_persistence_key_hits"), 1),
    ),
    Mutation(
        id="M13", side="be", path=SLICE, kind="replace",
        anchor='  "shared_base_consumers_after_rewiring": 19,',
        new='  "shared_base_consumers_after_rewiring": 29,',
        want=f"{_P69}::test_derived_counters_recompute_from_their_own_sections",
        why="🔴 照抄 L 循环「改线前后不变」（29 → 29）的具体错法。M 贡献 10 条边 ⇒ 必须收缩到 19。",
        scope_check=doc_path_is(
            ("honest_adjudication_summary", "shared_base_consumers_after_rewiring"), 29),
    ),
    Mutation(
        id="M14", side="be", path=SLICE, kind="replace",
        anchor='  "entries_with_inert_switch": 0,',
        new='  "entries_with_inert_switch": 4,',
        want=f"{_P69}::test_derived_counters_recompute_from_their_own_sections",
        wants=(f"{_SWITCH}::test_switch_counters_recompute",),
        why="🔴 照抄 L 循环 4 条 inert 的具体错法。M 现算 inert 为 0（三要素齐验）。",
        scope_check=doc_path_is(("honest_adjudication_summary", "entries_with_inert_switch"), 4),
    ),
    Mutation(
        id="M15", side="be", path=SLICE, kind="replace",
        anchor='  "oo_sheet_map_pairs_missing_from_workbook": 11,',
        new='  "oo_sheet_map_pairs_missing_from_workbook": 0,',
        want=f"{_P69}::test_derived_counters_recompute_from_their_own_sections",
        why="把 BP-4 的缺陷数报成 0 = 「缺陷不存在」。本轮最贵的一条形态差异必须有计数守着。",
        scope_check=doc_path_is(
            ("honest_adjudication_summary", "oo_sheet_map_pairs_missing_from_workbook"), 0),
    ),
    Mutation(
        id="M16", side="be", path=SLICE, kind="replace",
        anchor='    "pairs_missing_from_authoritative_workbook": 11,',
        new='    "pairs_missing_from_authoritative_workbook": 10,',
        want=f"{_SHEET}::test_sheet_map_counters_recompute",
        wants=(f"{_FORM}::test_md3_sheet_map_defects_recompute_both_ways",),
        why="节内计数与 summary 是两个独立来源（summary 现算它、它现算源码）。"
            "这条验节内那一层，M15 验 summary 那一层 —— 两层都得有人管。",
        scope_check=doc_path_pred(
            ("sheet_granularity_and_router_audit", "oo_sheet_map_audit", "counters",
             "pairs_missing_from_authoritative_workbook"),
            lambda v: v == 10),
    ),
    Mutation(
        id="M17", side="be", path=SLICE, kind="replace",
        anchor='  "classification_summary_persist_sites": 3,',
        new='  "classification_summary_persist_sites": 0,',
        want=f"{_P24}::test_classification_summary_highlight_is_real",
        wants=(f"{_P69}::test_derived_counters_recompute_from_their_own_sections",),
        why="tasks.md 点名的「分类 summary」计数报 0 = 该欠账消失。必须有判据守着。",
        scope_check=doc_path_is(
            ("honest_adjudication_summary", "classification_summary_persist_sites"), 0),
    ),
    Mutation(
        id="M18", side="be", path=SLICE, kind="replace",
        anchor='  "authoritative_formula_cells_total": 2937,',
        new='  "authoritative_formula_cells_total": 0,',
        want=f"{_P69}::test_derived_counters_recompute_from_their_own_sections",
        why="🔴 公式格数报 0 正是「用 data_only=True 扫描」的结果。若守卫也用 True，两边一起错、"
            "这条会变绿 —— 故 `test_formula_scan_needs_data_only_false` 是它的必要搭档。",
        scope_check=doc_path_is(("honest_adjudication_summary", "authoritative_formula_cells_total"), 0),
    ),
    Mutation(
        id="M19", side="be", path=SLICE, kind="replace",
        anchor='  "derived_column_persist_sites": 18,',
        new='  "derived_column_persist_sites": 0,',
        want=f"{_P69}::test_derived_counters_recompute_from_their_own_sections",
        why="AC 6.6 的消费侧欠账计数报 0 = BP-11 消失。",
        scope_check=doc_path_is(("honest_adjudication_summary", "derived_column_persist_sites"), 0),
    ),
    Mutation(
        id="M20", side="be", path=SLICE, kind="replace",
        scope=ORPHAN_M1_FILE, offset=OFF_ORPHAN_PROD,
        anchor='    "production_consumers": 0,',
        new='    "production_consumers": 1,',
        want=f"{_ORPHAN}::test_declared_orphans_are_unreachable_and_declared_value_matches",
        why="🔴 Task 54 的 M20 教训直译：只断言「现算为 0」时，声明写 1、实际 0 这种谎话能通过。"
            "本轮守卫两侧都验 ⇒ 这条必须红。",
        scope_check=doc_path_pred(
            ("orphan_dual_mode_inventory", "modules"),
            lambda mods: any(
                m["file"].endswith("useM1DualMode.ts") and m["production_consumers"] == 1
                for m in mods)),
    ),
    Mutation(
        id="M21", side="be", path=SLICE, kind="replace",
        anchor='   "orphan_dual_mode_modules": 11,',
        new='   "orphan_dual_mode_modules": 9,',
        want=f"{_ORPHAN}::test_twenty_files_partition_into_eleven_orphans_and_nine_live",
        wants=(f"{_ORPHAN}::test_orphan_summary_counts_recompute",
               f"{_FORM}::test_md1_twin_pairing_is_exclusive_and_exhaustive"),
        why="🔴 把 orphan 数改成「与 live 数相等」（K 循环那种 13 == 13 的形态）。"
            "M 的 11 ≠ 9 是因为 M9 的两个孪生都是死桩 —— 抄 K 的对称假设会漏掉这条。",
        scope_check=doc_path_is(
            ("orphan_dual_mode_inventory", "counters", "orphan_dual_mode_modules"), 9),
    ),
    Mutation(
        id="M22", side="be", path=SLICE, kind="replace",
        anchor='   "positional_persistence_key"',
        new='   "label_text"',
        want=f"{_PARA}::test_forbidden_identity_kinds_include_the_m_specific_one",
        why="M 的主缺陷形态若不进 `forbidden_identity_kinds`，下一轮抄这份 slice 时会漏检。"
            "这条把它替换成一个已有值（保持 JSON 合法且不改数组长度）。",
        scope_check=doc_path_pred(
            ("dynamic_row_identity", "forbidden_identity_kinds"),
            lambda kinds: "positional_persistence_key" not in kinds),
    ),
    Mutation(
        id="M23", side="be", path=SLICE, kind="replace",
        anchor='     "read_only_masked_cell"',
        new='     "read_only_formula"',
        want=f"{_P24}::test_platform_protection_policy_enum_behaves",
        why="三类只读来源里第三类（受保护单元格）是**独立判据**：契约允许 editable 字段的列落在 "
            "formula_mask 里，Task 13 只校验反向。把它从 protected_members 里抹掉 ⇒ "
            "「受保护单元格」永不被测到。守卫按枚举成员集合等值比对 ⇒ 必须红。",
        scope_check=doc_path_pred(
            ("protected_formula_and_classification_summary", "platform_carrier",
             "protection_policy_enum", "protected_members"),
            lambda ms: ms.count("read_only_formula") == 2),
    ),
    Mutation(
        id="M24", side="be", path=SLICE, kind="replace",
        anchor='    "wraps": "excel_extract.protected_conflicts_for_findings",',
        new='    "wraps": "excel_extract.protected_conflicts_never_existed",',
        want=f"{_P24}::test_conflict_emitter_really_wraps_the_task37_function",
        why="包装关系是结构判据：守卫截出 `protected_conflicts_from_incoming` 的函数体，"
            "断言体内真的调用了声明的被包装者。指向一个不存在的函数名 ⇒ 必须红。",
        scope_check=doc_path_pred(
            ("protected_formula_and_classification_summary", "platform_carrier",
             "conflict_emitter", "wraps"),
            lambda s: s.endswith("protected_conflicts_never_existed")),
    ),
    Mutation(
        id="M25", side="be", path=SLICE, kind="replace",
        anchor='  "backend/data/workpaper_sync_l_cycle_manifest_slice.json"',
        new='  "backend/data/workpaper_sync_x_cycle_manifest_slice.json"',
        want=f"{_P70}::test_sibling_slices_declared_match_the_disk",
        why="`sibling_slices` 必须收全 D/E/F/G/H/I/J/K/L 九份且逐个在磁盘上存在。"
            "指向一个不存在的循环 ⇒ Property 70 的分母被偷偷改小。",
        scope_check=doc_path_pred(
            ("sibling_slices",),
            lambda xs: any("x_cycle" in x for x in xs)),
    ),
    Mutation(
        id="M26", side="be", path=SLICE, kind="replace",
        anchor='    "orphan_dual_mode_modules",',
        new='    "orphan_dual_mode_second_order",',
        want=f"{_P69}::test_counting_notes_cover_every_summary_counter",
        why="🔴 Task 54 的 M28/M29 教训的制度化：counting_notes 必须**穷举** summary 的每一族计数。"
            "把一个键换成重复项 ⇒ `orphan_dual_mode_modules` 变成「无来源登记」⇒ 必须红。",
        scope_check=doc_path_pred(
            ("honest_adjudication_summary", "counting_notes", "from_orphan_dual_mode_inventory"),
            lambda xs: "orphan_dual_mode_modules" not in xs),
    ),
    Mutation(
        id="M27", side="be", path=SLICE, kind="replace",
        # 🔴 该 sha256 在文件里出现两次（`authoritative_templates.files[]` 与 entry 的
        #    `template_ref`）⇒ 必须相对定位。scope 取 `authoritative_templates` 块里唯一的
        #    册名行（entry 的 template_ref 用的键是 `workbook` 而不是 `name`），offset 实算 +2。
        scope='    "name": "M1 应付股利（利润）.xlsx",',
        offset=2,
        anchor='    "sha256": "fe19e06e954699db4c0d710a12ec9af02ea4ba462d13fb7cd9fc2ed4d5fa6bf2",',
        new='    "sha256": "0000000000000000000000000000000000000000000000000000000000000000",',
        want=f"{_P28}::test_authoritative_template_digests_recompute",
        why="Property 28 的模板层：digest 用 hashlib 现算比对，任一漂移 fail closed（AC 6.10）。"
            "全零 hash 是 Requirement 2.3 明禁的形态之一，这里正好用它做变异值。",
        scope_check=doc_path_pred(
            ("authoritative_templates", "files"),
            lambda fs: any(f["sha256"] == "0" * 64 for f in fs)),
    ),

    # ── C. 删除清册（数据侧）───────────────────────────────────────────
    Mutation(
        id="M28", side="be", path=PLAN, kind="replace",
        anchor='  "legacy_health_endpoint_call_sites_after": 1,',
        new='  "legacy_health_endpoint_call_sites_after": 0,',
        want=f"{_DEL}::test_plan_health_endpoint_after_is_one_not_zero",
        why="🔴 「删完剩 0」是照抄 orphan-only 循环的错法：共享基类那一处不删 ⇒ 恒剩 1。",
        scope_check=doc_path_is(("counters", "legacy_health_endpoint_call_sites_after"), 0),
    ),
    Mutation(
        id="M29", side="be", path=PLAN, kind="replace",
        anchor='  "can_delete_before_step_9": false,',
        new='  "can_delete_before_step_9": true,',
        want=f"{_DEL}::test_plan_lives_cannot_be_deleted_before_step_9_unlike_l",
        why="🔴 照抄 L 循环「inert 开关可先删」的错法。M 的活封装承载真开关且是 "
            "`resolveOoSheetName` 唯一实现方 ⇒ 必须先改线。",
        scope_check=doc_path_is(
            ("live_dual_mode_to_rewire_then_delete", "can_delete_before_step_9"), True),
    ),
    Mutation(
        id="M30", side="be", path=PLAN, kind="replace",
        anchor='   "defect_pairs_total": 11,',
        new='   "defect_pairs_total": 0,',
        want=f"{_DEL}::test_plan_sheet_map_fix_class_is_real",
        why="第三类动作（修，不是删/改线）的计数报 0 = 该类动作消失。前九轮清册只有两类动作，"
            "抄过去会把这一类整体丢掉。",
        scope_check=doc_path_is(
            ("oo_sheet_map_defects_to_fix_not_delete", "counters", "defect_pairs_total"), 0),
    ),
]


# ══════════════════════════════════════════════════════════════════════════
# D. 真源码变异（证明 impl 侧是**现读**而不是抄了一份快照）
# ══════════════════════════════════════════════════════════════════════════
MUTATIONS += [
    Mutation(
        id="M31", side="be", path=MAP_M2, kind="replace",
        anchor="  'M2-5': '检查表M2-5',",
        new="  'M2-5': '实收资本（股本）检查表M2-5',",
        want=f"{_FORM}::test_md3_sheet_map_defects_recompute_both_ways",
        wants=(f"{_SHEET}::test_sheet_map_counters_recompute",
               f"{_P69}::test_derived_counters_recompute_from_their_own_sections"),
        why="🔴 **反向变异**：把 M2 的一处错映射**修好**（改成权威册里的真名）⇒ 缺陷数 11 → 10。"
            "只验「新增缺陷」一个方向是半个判据 —— 缺陷被修好而 BP-4 的登记没删，"
            "报告会长期挂一条已解决的债。这条同时证明守卫是从**源码 + openpyxl** 现算的，"
            "不是读 slice 里的快照。",
        scope_check=text_has("'实收资本（股本）检查表M2-5'"),
    ),
    Mutation(
        id="M32", side="be", path=MAP_M2, kind="replace",
        anchor="  procedure: '实收资本实质性程序表M2A',",
        new="  procedure: '另一个不存在的名字M2A',",
        want=f"{_FORM}::test_md3_sheet_map_defects_recompute_both_ways",
        why="换成另一个同样不存在的名字：缺陷**数**不变（仍是 11），但缺陷**内容**变了。"
            "守卫除了比对计数，还逐条比对 `declared` 值集合 ⇒ 必须红。"
            "若守卫只数个数，这条会变绿 —— 那正是要防的粗判据。",
        scope_check=text_has("'另一个不存在的名字M2A'"),
    ),
    Mutation(
        id="M33", side="be", path=HOST_M9, kind="insert",
        anchor='  <div class="m9-other-comprehensive-income">',
        new='    <div class="mode-toggle-bar">\n'
            '      <el-segmented :model-value="\'html\'" :options="[]" size="small" />\n'
            '    </div>',
        want=f"{_SWITCH}::test_no_switch_entry_really_has_none_of_the_three",
        wants=(f"{_FORM}::test_md2_inert_is_zero_and_the_scanner_is_not_stuck",
               f"{_SWITCH}::test_per_entry_verdicts_are_from_a_closed_enum",
               f"{_ADJ}::test_ui_toolbar_gate_anchors_are_resolvable_or_explicitly_absent"),
        why="🔴 给 M9 塞一个 `el-segmented` 但不给 mode 门控 ⇒ 三要素扫描器应把它判成 "
            "`switch_present_but_inert`，inert 计数从 0 变 1。这条同时证明"
            "「M 循环 inert == 0」是**判据**而不是扫描器恒 0（Task 54 的对照组要求）。",
        scope_check=text_counts("el-segmented", 1),
    ),
    Mutation(
        id="M34", side="be", path=HOST_M10, kind="replace",
        anchor="  if (name.includes('国有企业')) return 'disclosure-soe'",
        new="  if (name.includes('国企')) return 'disclosure-soe'",
        want=f"{_SHEET}::test_m10_soe_disclosure_child_exists_but_is_unreachable",
        wants=(f"{_SHEET}::test_oo_fallthrough_classification_recomputes",
               f"{_SHEET}::test_sheet_coverage_recomputes_three_ways",
               f"{_ADJ}::test_bp12_is_the_unreachable_child_blocker"),
        why="🔴 **反向变异**：把 BP-12 的缺陷修好（`国有企业` → `国企`，与真 sheet 名对齐）⇒ "
            "M10 的国企披露 sheet 从 OO 兜底变成 HTML 覆盖，覆盖面 89 → 90、"
            "`unmatched_by_dispatch` 1 → 0。BP-12 应随之解除。"
            "这条证明覆盖面判据是**复刻 dispatch 现算**的，不是读 slice 里的清单。",
        scope_check=text_has("name.includes('国企')") ,
    ),
    Mutation(
        id="M35", side="be", path=ADJ_M1, kind="replace",
        anchor="        { itemId: `M1-M1-1-row-${n}-name`, data: { remark: row.shareholderName } },",
        new="        { itemId: `M1-M1-1-row-${row.key}-name`, data: { remark: row.shareholderName } },",
        want=f"{_FORM}::test_md8_positional_main_form_is_the_persistence_key",
        wants=(f"{_P69}::test_derived_counters_recompute_from_their_own_sections",),
        why="🔴 **反向变异**：把一处位置化持久化键换成稳定行身份（内存里已有熵键 `row.key`）⇒ "
            "命中数 44 → 43。BP-10 的一部分被兑现。这条证明持久化键族是从源码现扫的。",
        scope_check=text_has("`M1-M1-1-row-${row.key}-name`"),
    ),
    Mutation(
        id="M36", side="be", path=HOST_M6, kind="replace",
        anchor="  if (name.includes('Q6A') && name.includes('修订前')) return 'skip-q6a'",
        new="  // if (name.includes('Q6A') && name.includes('修订前')) return 'skip-q6a'",
        want=f"{_FORM}::test_md4_three_q_sheets_have_three_different_treatments",
        wants=(f"{_SHEET}::test_collapse_recomputes_and_is_exactly_three_entries",
               f"{_SHEET}::test_sheet_coverage_recomputes_three_ways",
               f"{_P69}::test_derived_counters_recompute_from_their_own_sections"),
        why="🔴 把 M6 那条**排在 `实质性程序表` 之前**的专用判断注释掉 ⇒ Q6A 会跟着折叠到 "
            "`procedure`，「三张 Q 表三种待遇」变成「两种」、折叠 entry 从 3 变 4。"
            "这条同时验剥注释保留行号（注释掉的行仍在，行号不动）与 dispatch 顺序复刻。",
        scope_check=text_has("  // if (name.includes('Q6A')"),
    ),
    Mutation(
        id="M37", side="be", path=SHARED_BASE, kind="replace",
        anchor="  const mode = ref<WorkpaperRenderMode>('html')",
        new="  const mode = ref<WorkpaperRenderMode>("
            "(localStorage.getItem('workpaper-sync-mode:') as WorkpaperRenderMode) || 'html')",
        want=f"{_FORM}::test_md6_live_path_has_no_localstorage_key",
        why="🔴 MD-6 的结论是「活路径**无** localStorage 键」。给共享基类加上键 ⇒ 结论翻转。"
            "这条证明该结论是现读源码得出的，不是抄 L 的形态。",
        scope_check=text_has("localStorage.getItem('workpaper-sync-mode:')"),
    ),
    Mutation(
        id="M38", side="be", path=FORMDATA_M1, kind="replace",
        anchor="const ITEM_PREFIX = 'M1-'",
        new="const ITEM_PREFIX = 'M1'",
        want=f"{_HTML}::test_item_id_prefixes_are_pairwise_non_prefixing",
        wants=(f"{_HTML}::test_formdata_refs_really_hit_the_prefix_filter_and_the_calls",),
        why="🔴 去掉前缀末尾的 `-` ⇒ `'M10-1-x'.startsWith('M1')` 为真 ⇒ M1 会把 M10 的数据"
            "读进自己的命名空间（Property 70 的真实风险点）。守卫两两验「不互为前缀」⇒ 必须红。",
        # 🔴 不得写 `"…'M1'\n"`：工作树是 CRLF，行尾是 `\r\n` ⇒ 那种 scope_check 恒假、
        #    判定会误报 ANCHOR-MISS（首轮实测踩过）。改成按**整行集合**判。
        scope_check=lambda data: "const ITEM_PREFIX = 'M1'" in [
            line.rstrip("\r") for line in data.decode("utf-8").split("\n")
        ],
    ),
    Mutation(
        id="M39", side="be", path=CONFLICTS_PY, kind="replace",
        anchor='    read_only_masked_cell = "read_only_masked_cell"',
        new='    read_only_masked_cell = "read_only_masked"',
        want=f"{_P24}::test_platform_protection_policy_enum_behaves",
        why="🔴 改真枚举值。守卫用 importlib 真加载 `conflicts.py` 取成员集合并跑 `is_protected` "
            "谓词（行为判据）⇒ 值一变集合就不等。若守卫只 grep 类名，这条会变绿。",
        scope_check=text_has('read_only_masked_cell = "read_only_masked"'),
    ),
    Mutation(
        id="M40", side="be", path=REMATERIALIZE_PY, kind="replace",
        anchor="    return protected_conflicts_for_findings(",
        new="    return list(",
        want=f"{_P24}::test_conflict_emitter_really_wraps_the_task37_function",
        why="🔴 把包装体内对 Task 37 函数的调用抽掉 ⇒ 它变成第二份实现，merge 侧与 rematerialize "
            "侧口径会漂移而两边都不红。守卫截**函数体**（括号配对 + 跳参数列表）后断言体内有该调用。",
        scope_check=text_has("    return list("),
    ),
    Mutation(
        id="M41", side="be", path=DETAIL_M1, kind="insert",
        anchor="      const key = `m1-detail-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`",
        new="      const _injected = blankRows(rows, 3)",
        want=f"{_P69}::test_hardcoded_scan_is_all_zero_and_non_vacuous",
        wants=(f"{_P69}::test_derived_counters_recompute_from_their_own_sections",),
        why="🔴 「某族 0 命中」也要落成判据 + 用变异证明它是**非空跑**。注入一处 "
            "`blankRows(rows, 3)` ⇒ `blankRows_literal_count` 族从 0 变 1。"
            "若守卫的扫描分母是空的（口径写坏），这条会变绿。",
        scope_check=text_has("blankRows(rows, 3)"),
    ),
    Mutation(
        id="M42", side="be", path=REGISTRY_TS, kind="replace",
        anchor="    component: defineAsyncComponent(() => import('./GtM9OtherComprehensiveIncome.vue')),",
        new="    component: defineAsyncComponent(() => import('./GtM9OtherComprehensiveIncomeX.vue')),",
        want=f"{_SCOPE}::test_host_module_edges_in_the_renderer_registry_are_real",
        why="🔴 可达性判据 = htmlRendererRegistry 的**模块边**（路径解析口径，不是符号名 grep）。"
            "把 import 路径改掉 ⇒ M9 宿主失去模块边、可达性结论翻转。"
            "若守卫按符号名 grep，改路径后名字仍在 ⇒ 会变绿。",
        scope_check=text_has("GtM9OtherComprehensiveIncomeX.vue"),
    ),
    Mutation(
        id="M43", side="be", path=HOST_M1, kind="insert",
        anchor='          <el-segmented',
        new='          <GtEntrySyncCapabilityNotice />',
        want=f"{_ADJ}::test_bp7_is_registered_because_no_m_host_mounts_the_notice",
        wants=(f"{_SWITCH}::test_switch_counters_recompute",
               f"{_ADJ}::test_ui_toolbar_gate_anchors_are_resolvable_or_explicitly_absent",
               f"{_P69}::test_derived_counters_recompute_from_their_own_sections"),
        why="🔴 **反向变异**：在 M1 宿主里真挂上 AC 1.4 的 notice 组件 ⇒ BP-7 可解除、"
            "`entries_mounting_the_ac14_notice` 从 0 变 1。"
            "只验「没挂」一个方向的话，挂上之后登记不删也没人提醒。",
        scope_check=text_has("<GtEntrySyncCapabilityNotice />"),
    ),
    Mutation(
        id="M44", side="be", path=HOST_M1, kind="replace",
        anchor='          :sheet-name="dualMode.resolveOoSheetName()"',
        new='          :sheet-name="props.sheetName"',
        want=f"{_SWITCH}::test_redeemable_switch_has_all_three_elements",
        why="🔴 开关「可兑现」的结构判据要求 OO 挂载真在 mode 的 `v-else` 分支下且用 "
            "`dualMode.resolveOoSheetName()` 定位。换成 `props.sheetName` ⇒ 切到 OO 不再按 mode "
            "解析 tab，`switch_redeemable` 的形态判据不成立。"
            "若守卫只数 `el-segmented` 与 `GtOnlyOfficeSheet` 的个数，这条会变绿。",
        # 🔴 同 M38：禁用含 `\n` 的字面量做 scope_check（CRLF 工作树恒假 ⇒ 误报 ANCHOR-MISS）。
        #    这里按整行集合断言「已无 resolveOoSheetName 绑定、且新绑定出现两次」——
        #    两次 = HTML 分支内的 OO 兜底原本就用 props.sheetName，加上被改的这一处。
        scope_check=lambda data: (
            lambda lines: (
                ':sheet-name="dualMode.resolveOoSheetName()"' not in lines
                and lines.count(':sheet-name="props.sheetName"') == 2
            )
        )([line.rstrip("\r").strip() for line in data.decode("utf-8").split("\n")]),
    ),
    Mutation(
        id="M45", side="be", path=CLASSIFY_M10, kind="replace",
        anchor="  const summary: ComputedRef<M10ClassificationSummary> = computed(() => {",
        new="  const summary: any = ((): any => {",
        want=f"{_P24}::test_classification_summary_highlight_is_real",
        why="🔴 tasks.md 点名项：分类 summary 必须是**派生量**（computed）才谈得上「保持受保护」。"
            "把它改成普通 IIFE ⇒ 「派生值」的前提不成立，守卫按正则核 `computed(` 形态 ⇒ 必须红。",
        scope_check=text_has("const summary: any = ((): any => {"),
    ),
]

if __name__ == "__main__":
    raise SystemExit(run_cli(
        mutations=MUTATIONS,
        guard_files=GUARD_FILES,
        repo=REPO,
        description="Task 55 M 循环守卫变异检验",
        backend_args=BE_ARGS,
        baseline_backend_passed=None,
        allow_dirty_baseline=True,
    ))
