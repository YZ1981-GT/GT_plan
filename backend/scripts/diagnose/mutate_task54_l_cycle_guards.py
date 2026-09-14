# -*- coding: utf-8 -*-
r"""Task 54 守卫变异检验 —— L 循环 Excel 独立 entry 迁移。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 5 Task 54

用平台共享件 `backend/scripts/_mutation_kit`（`test_mutation_kit_adoption.py` 对新脚本强制
采纳：共享件的 `run_cli` 把 `guard_files`（覆盖面分母）做成签名层面必填，把「锚点含换行」
「new == anchor」「id 重复」「want 定位不到」全部拦在声明期）。

═══ 本脚本的四条硬约束 ═══

1. **每条变异都带 `scope_check`**。四态判定式「新增失败集合是否为空」识别不出「锚点落在被测
   判据的作用域之外」—— 改到了别处会被判 GREEN（守卫缺陷），而真相是脚本缺陷。数据文件的
   回调解析 JSON 后断言目标字段真的变成了期望值；源码文件的回调断言改动确实落在那段文本上。

2. **重复形态字段用 `scope` + `offset` 相对定位，绝不用绝对行号**。本 slice 有 **8 条** entry，
   故 entry 级字段全是 dup=8（`"capability": null,` / `"html_counterpart_verdict"` /
   `"mounts_ac14_notice"` …）。这些一律以该 entry 唯一的 `"entry_id": "…"` 行作 `scope`，
   `offset` 由 `tmp_task54_anchors2/4.py` 一次性诊断**实算**（非估计值）：
   capability=+5 · verdict_stage=+6 · capability_target=+7 · blocked_by 首元素=+9 ·
   html_counterpart_verdict=+17（L1/L4~L8）或 +16（L2/L3）· manifest_mirror.capability=+51 ·
   mounts_ac14_notice=+66（L1，逐 entry 不同）。
   🔴 **逐 entry 的 offset 不相等**（各 entry 的 reason/sheets 文本行数不同）⇒ 必须逐 entry 实算。

3. **变异按「可区分的错法」枚举而不是逐条目复制**。8 条 entry 形态同构，逐条各写一次是同
   信息量的重复。这里按错法分组，并分布在不同 entry 上（L1/L4/L5），从而同时走通各 entry 的 offset。

4. **必须含反向变异**。只验「新增缺陷」一个方向的穷举判据是半个判据：缺陷被修好而登记没删，
   报告会长期挂着一条已解决的债。本脚本的反向变异：
   * M39 把 BP-10 的那处 family_a 位置化身份**修好**（`String(idx)` → `c.name`），命中数 1 → 0；
   * M44 在 L1 宿主里**真挂上** AC 1.4 的 notice 组件（BP-7 可解除）；
   * M37 把 `useL3DualMode` 的 localStorage 键**改成按 wpId 分区**（LD-6 可解除）。

═══ 为什么要对**真源码**做变异（M35~M44）═══

数据侧变异只能证明「守卫读了 slice」；只有改真源码还打红，才能证明 impl 侧是**现读**而不是
抄了一份快照。L 循环的判据里有七类必须有源码变异撑着：
① inert 开关的模板形态判据（M35）· ② 对照组的 mode 门控（M36）· ③ LD-6 的 wpId 分区（M37）·
④ family_b 的「兜底真调生成器」（M38）· ⑤ 位置化身份穷举（M39）·
⑥ sheet 粒度折叠与裸码兜底（M40 / M41）· ⑦ router 匹配规则复刻与渲染器模块边（M42 / M43）。

用法（仓库根；本仓库 PATH 上的 `python` 可能指向坏掉的解释器，必须用显式解释器）::

    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task54_l_cycle_guards.py --list
    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task54_l_cycle_guards.py --check-anchors
    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task54_l_cycle_guards.py --run M01,M02,M03

🔴 **禁止后台执行**：外层 shell 被杀会让 python 变成孤儿进程，与前台运行同时变异同一文件 ⇒
`RestoreFailed` rc=5。分批跑用 `--run M01,M02,...`（子集运行不做覆盖面结论）。

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
SLICE = "backend/data/workpaper_sync_l_cycle_manifest_slice.json"
PLAN = "backend/data/workpaper_sync_l_cycle_deletion_plan.json"
FE = "audit-platform/frontend/src"
WP = f"{FE}/components/workpaper"
COMP = f"{WP}/composables"
HOST_L1 = f"{WP}/GtL1ShortTermLoans.vue"
HOST_L4 = f"{WP}/GtL4BondsPayable.vue"
TAB_L1_ADJ = f"{WP}/l1/core/L1TabAdjudication.vue"
TAB_L5_ADJ = f"{WP}/l5/core/L5TabAdjudication.vue"
L3_ORPHAN = f"{COMP}/useL3DualMode.ts"
L2_DETAIL = f"{COMP}/useL2Detail.ts"
REGISTRY_TS = f"{WP}/htmlRendererRegistry.ts"
OO_ROUTER = "backend/app/routers/wp_onlyoffice_router.py"

# ── 期望打红的守卫（文件::类::方法，与 pytest 的 short nodeid 同形）─────────
T54 = "test_task54_l_cycle_migration.py"
_SELF = f"{T54}::TestGuardSelfChecks"
_SCOPE = f"{T54}::TestSliceScopeIsRecomputable"
_ADJ = f"{T54}::TestAdjudicationLegality"
_HTML = f"{T54}::TestHtmlCounterpartIsSourceBacked"
_FORM = f"{T54}::TestLCycleFormDifferences"
_ORPHAN = f"{T54}::TestOrphanDualModeInventory"
_INERT = f"{T54}::TestInertModeSwitch"
_SHEET = f"{T54}::TestSheetGranularityAndRouter"
_P20 = f"{T54}::TestProperty20AndProperty3"
_P28 = f"{T54}::TestProperty28DefinitionDriftFailClosed"
_P23 = f"{T54}::TestProperty23StaticStructure"
_P69 = f"{T54}::TestProperty69EvidenceAndCounters"
_P70 = f"{T54}::TestProperty70CrossEntryIsolation"
_DEL = f"{T54}::TestDeletionPlanConsistency"
_PARA = f"{T54}::TestParadigmCompliance"
_CONTRACT = "test_migration_paradigm_contract.py"
_COVERAGE = "test_slice_schema_validator_coverage.py"


def EID(slug: str) -> str:
    """某 entry 在 `independent_entries` 里唯一的 scope 行（dup=1，3 空格缩进）。"""
    return '   "entry_id": "xlsx/%s",' % slug


L1 = EID("gt-l1-short-term-loans")
L4 = EID("gt-l4-bonds-payable")
L5 = EID("gt-l5-long-term-payables")

#: 逐字段 offset（由锚点诊断实算，非估计值）。
OFF_CAPABILITY = 5
OFF_VERDICT_STAGE = 6
OFF_BLOCKED_FIRST = 9
OFF_HTML_VERDICT_L1 = 17
OFF_MIRROR_CAPABILITY_L1 = 51
OFF_MOUNTS_NOTICE_L1 = 66
#: 模板节：`"name"` 行 → `"sha256"` 行。
OFF_SHA256 = 2
#: 模板节：`"name"` 行 → `"sheets"` 数组里带前导空格的那一项（第 2 个元素，第 1 个是「底稿目录」）。
OFF_L1A_SHEET = 6
#: inert site：`"segmented_site"` 行 → 两个计数。
OFF_V_IF_COUNT = 8
OFF_OO_COUNT = 9
#: orphan/live 模块：`"file"` 行 → 目标字段。
OFF_PROD_CONSUMERS = 3
OFF_CONSUMER_IS_CHILD = 13
#: dynamic table：`"table_key"` 行 → `"kind"` 行。
OFF_ROW_KIND = 3

L1_TEMPLATE_NAME = '    "name": "L1 短期借款.xlsx",'
L5_SEGMENTED_SITE = (
    '    "segmented_site": "audit-platform/frontend/src/components/workpaper/'
    'l5/core/L5TabAdjudication.vue#L16",'
)
L1_ORPHAN_FILE = '    "file": "audit-platform/frontend/src/composables/useL1DualMode.ts",'
L5_LIVE_FILE = (
    '    "file": "audit-platform/frontend/src/components/workpaper/composables/useL5DualMode.ts",'
)
L2_TABLE_KEY = '    "table_key": "L2-2 应付利息明细表（可增删行）",'
L5_CARRIER_IN_PLAN = (
    '    "carrier_module_to_delete_with_it": "audit-platform/frontend/src/components/'
    'workpaper/composables/useL5DualMode.ts",'
)


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
        node: object = _entry(raw, entry_id)
        for k in path:
            node = node[k]  # type: ignore[index]
        return node == expect
    return check


def top_field_is(path: tuple, expect):
    def check(raw: bytes) -> bool:
        node: object = _doc(raw)
        for k in path:
            node = node[k]  # type: ignore[index]
        return node == expect
    return check


def _sheets_of(raw: bytes, name: str) -> list[str]:
    for f in _doc(raw)["authoritative_templates"]["files"]:
        if f["name"] == name:
            return list(f["sheets"])
    raise AssertionError(f"scope_check: 找不到模板 {name}")


def template_field_is(name: str, key: str, expect):
    def check(raw: bytes) -> bool:
        for f in _doc(raw)["authoritative_templates"]["files"]:
            if f["name"] == name:
                return f[key] == expect
        raise AssertionError(f"scope_check: 找不到模板 {name}")
    return check


def inert_site_field_is(wp_code: str, key: str, expect):
    def check(raw: bytes) -> bool:
        for s in _doc(raw)["inert_mode_switch_resolution"]["sites"]:
            if s["wp_code"] == wp_code:
                return s[key] == expect
        raise AssertionError(f"scope_check: 找不到 inert site {wp_code}")
    return check


def module_field_is(container: str, file_suffix: str, key: str, expect):
    def check(raw: bytes) -> bool:
        node = _doc(raw)["orphan_dual_mode_inventory"][container]
        for m in node:
            if str(m["file"]).endswith(file_suffix):
                return m[key] == expect
        raise AssertionError(f"scope_check: {container} 里找不到 {file_suffix}")
    return check


def dynamic_table_kind_is(table_key_prefix: str, expect: str):
    def check(raw: bytes) -> bool:
        for t in _doc(raw)["dynamic_row_identity"]["tables"]:
            if str(t["table_key"]).startswith(table_key_prefix):
                return t["row_identity"]["kind"] == expect
        raise AssertionError(f"scope_check: 找不到动态表 {table_key_prefix}")
    return check


def plan_field_is(path: tuple, expect):
    return top_field_is(path, expect)


def plan_inert_block_carrier_is(wp_code: str, expect: str):
    def check(raw: bytes) -> bool:
        for b in _doc(raw)["inert_switch_blocks_to_remove"]["blocks"]:
            if b["wp_code"] == wp_code:
                return b["carrier_module_to_delete_with_it"] == expect
        raise AssertionError(f"scope_check: plan 里找不到 inert block {wp_code}")
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
    # ══ A. 裁决合法性（SR-1/3/4/5/9 · AC 12.8 · AP-3 · overlay 镜像陷阱）══
    Mutation(
        id="M01", side="be", path=SLICE, kind="replace",
        scope=L1, offset=OFF_CAPABILITY,
        anchor='   "capability": null,',
        new='   "capability": "single_onlyoffice",',
        want=f"{_ADJ}::test_capability_matches_honest_capability",
        wants=(
            f"{_ADJ}::test_single_onlyoffice_requires_no_html_counterpart",
            f"{_ADJ}::test_capability_is_null_and_pending_fields_are_complete",
            f"{_ADJ}::test_manifest_mirror_divergence_is_registered_not_silently_equal",
            f"{_ADJ}::test_ac15_is_declared_not_applicable_and_ac14_is_the_live_one",
            f"{_INERT}::test_inert_is_not_read_as_a_single_html_reason",
            f"{_P69}::test_summary_counters_recompute_from_the_entries",
            f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",
            f"{_DEL}::test_plan_entries_mirror_the_slice_adjudication",
            f"{_CONTRACT}::TestSliceSchemaPositiveExample::test_every_scanned_slice_passes_the_schema",
            f"{_COVERAGE}::test_every_slice_passes_the_json_nominated_validator",
        ),
        why="把待裁决态硬填成 single_onlyoffice —— AP-1 镜像形态；SR-4/SR-5/AC 12.8 与镜像分歧判据都必须打红",
        scope_check=entry_field_is("xlsx/gt-l1-short-term-loans", ("capability",),
                                  "single_onlyoffice"),
        tags=("adjudication",),
    ),
    Mutation(
        id="M02", side="be", path=SLICE, kind="replace",
        scope=L1, offset=OFF_HTML_VERDICT_L1,
        anchor='   "html_counterpart_verdict": "exists",',
        new='   "html_counterpart_verdict": "none",',
        want=f"{_P69}::test_summary_counters_recompute_from_the_entries",
        why="把 step 3 的二值结论翻面 —— summary 的 exists/none 计数必须现算打红",
        scope_check=entry_field_is("xlsx/gt-l1-short-term-loans",
                                  ("html_counterpart_verdict",), "none"),
        tags=("adjudication",),
    ),
    Mutation(
        id="M03", side="be", path=SLICE, kind="replace",
        scope=L1, offset=OFF_VERDICT_STAGE,
        anchor='   "capability_verdict_stage": "step_4_blocked_by_step_3_result_exists",',
        new='   "capability_verdict_stage": "",',
        want=f"{_ADJ}::test_capability_is_null_and_pending_fields_are_complete",
        wants=(
            f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",
            f"{_DEL}::test_plan_entries_mirror_the_slice_adjudication",
            f"{_CONTRACT}::TestSliceSchemaPositiveExample::test_every_scanned_slice_passes_the_schema",
            f"{_COVERAGE}::test_every_slice_passes_the_json_nominated_validator",
        ),
        why="SR-3 右支：待裁决态的 stage 写成空串 = 「留空而不解释」，校验器与本守卫都必须拦",
        scope_check=entry_field_is("xlsx/gt-l1-short-term-loans",
                                  ("capability_verdict_stage",), ""),
        tags=("adjudication",),
    ),
    Mutation(
        id="M04", side="be", path=SLICE, kind="replace",
        scope=L1, offset=OFF_BLOCKED_FIRST,
        anchor='    "BP-1",',
        new='    "BP-99",',
        want=f"{_ADJ}::test_every_blocking_precondition_is_referenced_by_someone",
        wants=(f"{_DEL}::test_plan_entries_mirror_the_slice_adjudication",),
        why="引用一个不存在的 BP —— 声明集合与引用集合的等值判据必须打红",
        scope_check=entry_field_is("xlsx/gt-l1-short-term-loans",
                                  ("capability_target_blocked_by", 0), "BP-99"),
        tags=("adjudication",),
    ),
    Mutation(
        id="M05", side="be", path=SLICE, kind="replace",
        anchor='   "unadjudicated": 8,',
        new='   "unadjudicated": 0,',
        want=f"{_P69}::test_slice_counters_are_all_zero_except_unadjudicated",
        wants=(
            f"{_ADJ}::test_capability_is_null_and_pending_fields_are_complete",
            f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",
            f"{_CONTRACT}::TestSliceSchemaPositiveExample::test_every_scanned_slice_passes_the_schema",
            f"{_COVERAGE}::test_every_slice_passes_the_json_nominated_validator",
        ),
        why="SR-9：把 8 条待裁决报成 0（右支被当后门用）—— 计数现算判据必须打红",
        scope_check=top_field_is(
            ("honest_adjudication_summary", "slice_counters", "unadjudicated"), 0),
        tags=("counters",),
    ),
    Mutation(
        id="M06", side="be", path=SLICE, kind="replace",
        anchor='  "total_independent": 8,',
        new='  "total_independent": 7,',
        want=f"{_P69}::test_summary_counters_recompute_from_the_entries",
        wants=(
            f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",
            f"{_CONTRACT}::TestSliceSchemaPositiveExample::test_every_scanned_slice_passes_the_schema",
            f"{_COVERAGE}::test_every_slice_passes_the_json_nominated_validator",
        ),
        why="SR-1：摘要与明细脱节",
        scope_check=top_field_is(("honest_adjudication_summary", "total_independent"), 7),
        tags=("counters",),
    ),
    Mutation(
        id="M07", side="be", path=SLICE, kind="replace",
        scope=L1, offset=OFF_MIRROR_CAPABILITY_L1,
        anchor='    "capability": "single_onlyoffice",',
        new='    "capability": null,',
        want=f"{_ADJ}::test_manifest_mirror_divergence_is_registered_not_silently_equal",
        why="把 manifest 镜像值抄成 null —— 「镜像必须等于 manifest 现值且与 slice 不等」两侧判据必须打红",
        scope_check=entry_field_is("xlsx/gt-l1-short-term-loans",
                                  ("manifest_mirror", "capability"), None),
        tags=("adjudication",),
    ),
    Mutation(
        id="M08", side="be", path=SLICE, kind="replace",
        scope=L1, offset=OFF_MOUNTS_NOTICE_L1,
        anchor='    "mounts_ac14_notice": false',
        new='    "mounts_ac14_notice": true',
        want=f"{_ADJ}::test_ac15_is_declared_not_applicable_and_ac14_is_the_live_one",
        why="声称已挂 AC 1.4 提示组件而磁盘上没有 —— BP-7 的两侧判据必须打红",
        scope_check=entry_field_is("xlsx/gt-l1-short-term-loans",
                                  ("ui_toolbar_gate", "mounts_ac14_notice"), True),
        tags=("ui",),
    ),

    # ══ B. Property 28：模板层 fail closed ═════════════════════════════════
    Mutation(
        id="M09", side="be", path=SLICE, kind="replace",
        scope=L1_TEMPLATE_NAME, offset=OFF_SHA256,
        anchor='    "sha256": "78033d804a379d42e7e0bc500aefb617fe6175537373126f88827d70b728ceeb",',
        new='    "sha256": "0000000000000000000000000000000000000000000000000000000000000000",',
        want=f"{_P28}::test_authoritative_template_digests_recompute",
        wants=(f"{_HTML}::test_template_ref_resolves_through_the_runtime_index",),
        why="模板 digest 漂移必须 fail closed（Requirement 6.10）；entry 级 template_ref 也共用同一 digest",
        scope_check=template_field_is(
            "L1 短期借款.xlsx", "sha256",
            "0000000000000000000000000000000000000000000000000000000000000000"),
        tags=("property28",),
    ),
    Mutation(
        id="M10", side="be", path=SLICE, kind="replace",
        scope=L1_TEMPLATE_NAME, offset=OFF_L1A_SHEET,
        anchor='     " 短期借款实质性程序表L1A",',
        new='     "短期借款实质性程序表L1A",',
        want=f"{_P28}::test_sheet_inventory_recomputes_and_names_are_not_stripped",
        why="把 sheet 名的前导空格 strip 掉 —— openpyxl 现读比对必须打红（L4 的同码 sheet 判据依赖它）",
        # 🔴 作用域自证必须解析 JSON 定位到 authoritative_templates 的那一项：
        # 同一字面量还出现在 `not_single_html_because` 与 `property_denominators.how_handled`
        # 的散文里，用「文本里不存在带空格的版本」当判据会恒假 ⇒ ANCHOR-MISS（实测踩过）。
        scope_check=lambda raw: "短期借款实质性程序表L1A" in _sheets_of(raw, "L1 短期借款.xlsx")
        and " 短期借款实质性程序表L1A" not in _sheets_of(raw, "L1 短期借款.xlsx"),
        tags=("property28",),
    ),
    Mutation(
        id="M11", side="be", path=SLICE, kind="replace",
        anchor='  "authoritative_template_sheets_total": 100,',
        new='  "authoritative_template_sheets_total": 99,',
        want=f"{_P28}::test_sheet_inventory_recomputes_and_names_are_not_stripped",
        wants=(f"{_P69}::test_derived_counters_recompute_from_their_own_sections",),
        why="sheet 合计抄错 —— 逐册现读求和的等值判据必须打红",
        scope_check=top_field_is(
            ("honest_adjudication_summary", "authoritative_template_sheets_total"), 99),
        tags=("counters", "property28"),
    ),

    # ══ C. sheet 粒度与 router 参数 ════════════════════════════════════════
    Mutation(
        id="M12", side="be", path=SLICE, kind="replace",
        anchor='   "sheets_covered_by_html_children": 86,',
        new='   "sheets_covered_by_html_children": 85,',
        want=f"{_SHEET}::test_sheet_coverage_recomputes_three_ways",
        wants=(f"{_P69}::test_derived_counters_recompute_from_their_own_sections",),
        why="覆盖数抄错 —— 86 + 4 == 90 的三方等值必须打红",
        scope_check=top_field_is(
            ("sheet_granularity_and_router_audit", "counters",
             "sheets_covered_by_html_children"), 85),
        tags=("sheet",),
    ),
    Mutation(
        id="M13", side="be", path=SLICE, kind="replace",
        anchor='   "router_ambiguous_codes_total": 10,',
        new='   "router_ambiguous_codes_total": 2,',
        want=f"{_SHEET}::test_router_ambiguity_recomputes_and_splits_reachable_from_not",
        wants=(f"{_P69}::test_derived_counters_recompute_from_their_own_sections",),
        why="把总歧义数改成等于真可达数 —— 「两个数必须分开」的判据必须打红",
        scope_check=top_field_is(
            ("sheet_granularity_and_router_audit", "counters",
             "router_ambiguous_codes_total"), 2),
        tags=("sheet",),
    ),
    Mutation(
        id="M14", side="be", path=SLICE, kind="replace",
        anchor='    "L4:L4-8"',
        new='    "L4:L4-9"',
        want=f"{_SHEET}::test_router_ambiguity_recomputes_and_splits_reachable_from_not",
        why="真可达歧义清单改错一项 —— 现算集合等值必须打红（末元素用 replace 不用 delete，见 docstring）",
        scope_check=top_field_is(
            ("sheet_granularity_and_router_audit", "counters",
             "router_ambiguous_and_reachable"), ["L4:L4-7", "L4:L4-9"]),
        tags=("sheet",),
    ),
    Mutation(
        id="M15", side="be", path=SLICE, kind="replace",
        anchor='  "router_ambiguous_and_reachable_total": 2,',
        new='  "router_ambiguous_and_reachable_total": 10,',
        want=f"{_P69}::test_derived_counters_recompute_from_their_own_sections",
        why="把真可达数抬成总数 —— 稀释判据必须打红",
        scope_check=top_field_is(
            ("honest_adjudication_summary", "router_ambiguous_and_reachable_total"), 10),
        tags=("sheet", "counters"),
    ),

    # ══ D. inert 开关（L 循环特有）════════════════════════════════════════
    Mutation(
        id="M16", side="be", path=SLICE, kind="replace",
        anchor='   "L5": "switch_present_but_inert",',
        new='   "L5": "switch_redeemable",',
        want=f"{_INERT}::test_verdict_is_from_a_closed_enum",
        wants=(
            f"{_INERT}::test_summary_switch_counters_recompute",
            f"{_INERT}::test_inert_switch_has_no_mode_gated_branch_and_no_oo_component",
        ),
        why="把一个 inert 开关谎报成可兑现 —— 三类互斥划分与模板形态判据都必须打红",
        scope_check=top_field_is(
            ("inert_mode_switch_resolution", "per_entry_verdict", "L5"), "switch_redeemable"),
        tags=("inert",),
    ),
    Mutation(
        id="M17", side="be", path=SLICE, kind="replace",
        scope=L5_SEGMENTED_SITE, offset=OFF_V_IF_COUNT,
        anchor='    "mode_gated_v_if_count": 0,',
        new='    "mode_gated_v_if_count": 1,',
        want=f"{_INERT}::test_inert_switch_has_no_mode_gated_branch_and_no_oo_component",
        why="声称有一处 mode 门控而模板里没有 —— DOM/模板形态判据必须现算打红",
        scope_check=inert_site_field_is("L5", "mode_gated_v_if_count", 1),
        tags=("inert",),
    ),
    Mutation(
        id="M18", side="be", path=SLICE, kind="replace",
        scope=L5_SEGMENTED_SITE, offset=OFF_OO_COUNT,
        anchor='    "onlyoffice_component_count_in_file": 0,',
        new='    "onlyoffice_component_count_in_file": 2,',
        want=f"{_INERT}::test_inert_switch_has_no_mode_gated_branch_and_no_oo_component",
        why="声称文件里有 2 个 OO 组件而实际 0 个 —— 现算判据必须打红",
        scope_check=inert_site_field_is("L5", "onlyoffice_component_count_in_file", 2),
        tags=("inert",),
    ),
    Mutation(
        id="M19", side="be", path=SLICE, kind="replace",
        anchor='  "entries_with_inert_switch": 4,',
        new='  "entries_with_inert_switch": 3,',
        want=f"{_INERT}::test_summary_switch_counters_recompute",
        why="inert 条数抄错 —— 2 + 4 + 2 == 8 的划分等值必须打红",
        scope_check=top_field_is(
            ("honest_adjudication_summary", "entries_with_inert_switch"), 3),
        tags=("inert", "counters"),
    ),

    # ══ E. orphan / live / 共享件三形态 ═══════════════════════════════════
    Mutation(
        id="M20", side="be", path=SLICE, kind="replace",
        scope=L1_ORPHAN_FILE, offset=OFF_PROD_CONSUMERS,
        anchor='    "production_consumers": 0,',
        new='    "production_consumers": 1,',
        want=f"{_ORPHAN}::test_declared_orphans_really_have_no_reachability",
        why="声称 orphan 有 1 条生产边而现算 0 —— 可达性判据必须打红",
        scope_check=module_field_is("modules", "composables/useL1DualMode.ts",
                                   "production_consumers", 1),
        tags=("orphan",),
    ),
    Mutation(
        id="M21", side="be", path=SLICE, kind="replace",
        scope=L5_LIVE_FILE, offset=OFF_CONSUMER_IS_CHILD,
        anchor='    "consumer_is_child_tab": true,',
        new='    "consumer_is_child_tab": false,',
        want=f"{_ORPHAN}::test_live_modules_have_exactly_one_edge_to_the_declared_child_tab",
        why="把「边在子 Tab」谎报成不在 —— LD-1 三分声明的支撑判据必须打红",
        scope_check=module_field_is("live_modules", "composables/useL5DualMode.ts",
                                   "consumer_is_child_tab", False),
        tags=("orphan",),
    ),
    Mutation(
        id="M22", side="be", path=SLICE, kind="replace",
        anchor='   "l_cycle_consumers": 0,',
        new='   "l_cycle_consumers": 1,',
        want=f"{_ORPHAN}::test_shared_base_counts_are_recomputed_both_ways",
        why="声称 L 域对共享基类贡献了 1 条边（实际 0）—— 「删前后不变」的论证必须打红",
        scope_check=top_field_is(
            ("orphan_dual_mode_inventory", "shared_base_preserved", "l_cycle_consumers"), 1),
        tags=("orphan",),
    ),
    Mutation(
        id="M23", side="be", path=SLICE, kind="replace",
        anchor='   "statement_position_consumers": 29,',
        new='   "statement_position_consumers": 28,',
        want=f"{_ORPHAN}::test_shared_base_counts_are_recomputed_both_ways",
        wants=(f"{_DEL}::test_plan_shared_numbers_agree_with_the_slice",),
        why="共享基类边数抄错 —— 窄口径现算与 plan 侧一致性都必须打红",
        scope_check=top_field_is(
            ("orphan_dual_mode_inventory", "shared_base_preserved",
             "statement_position_consumers"), 28),
        tags=("orphan", "counters"),
    ),
    Mutation(
        id="M24", side="be", path=SLICE, kind="replace",
        anchor='   "remaining_after_this_plan": 1,',
        new='   "remaining_after_this_plan": 0,',
        want=f"{_ORPHAN}::test_shared_cycle_carrier_partially_shrinks",
        wants=(f"{_DEL}::test_plan_shared_numbers_agree_with_the_slice",),
        why="把「部分收缩 3→1」写成「删到 0」（照抄 orphan 形态）—— 第三形态判据必须打红",
        scope_check=top_field_is(
            ("orphan_dual_mode_inventory", "shared_cycle_carrier",
             "remaining_after_this_plan"), 0),
        tags=("orphan",),
    ),
    Mutation(
        id="M25", side="be", path=SLICE, kind="replace",
        anchor='   "modules_not_scoped_to_wp_id": 1,',
        new='   "modules_not_scoped_to_wp_id": 0,',
        want=f"{_FORM}::test_ld6_only_one_module_is_not_scoped_to_wp_id",
        wants=(f"{_P69}::test_derived_counters_recompute_from_their_own_sections",),
        why="LD-6 的「恰 1 个未按 wpId 分区」抹成 0 —— 现算判据必须打红",
        scope_check=top_field_is(
            ("orphan_dual_mode_inventory", "counters", "modules_not_scoped_to_wp_id"), 0),
        tags=("form",),
    ),
    Mutation(
        id="M26", side="be", path=SLICE, kind="replace",
        anchor='   "modules_with_matrix_mode": 2,',
        new='   "modules_with_matrix_mode": 1,',
        want=f"{_ORPHAN}::test_orphan_summary_counts_recompute",
        why="含 matrix 模式的模块数抄错 —— 逐文件读枚举字面量的现算必须打红",
        scope_check=top_field_is(
            ("orphan_dual_mode_inventory", "counters", "modules_with_matrix_mode"), 1),
        tags=("form",),
    ),

    # ══ F. Property 23 / BP-10 ════════════════════════════════════════════
    Mutation(
        id="M27", side="be", path=SLICE, kind="replace",
        anchor='   "total_hits": 1,',
        new='   "total_hits": 0,',
        want=f"{_P23}::test_positional_identity_inventory_is_exhaustive_and_partitioned",
        why="把唯一的位置化命中抹成 0 —— 穷举判据必须打红（照抄 J 的「六个 0」就是这个错法）",
        scope_check=top_field_is(
            ("dynamic_row_identity", "positional_identity_inventory", "total_hits"), 0),
        tags=("property23",),
    ),
    Mutation(
        id="M28", side="be", path=SLICE, kind="replace",
        anchor='  "positional_identity_family_d": 9,',
        new='  "positional_identity_family_d": 8,',
        want=f"{_P69}::test_derived_counters_recompute_from_their_own_sections",
        why="展示序号站点数抄错 —— family_d 的反向判据必须打红",
        scope_check=top_field_is(
            ("honest_adjudication_summary", "positional_identity_family_d"), 8),
        tags=("property23", "counters"),
    ),
    Mutation(
        id="M29", side="be", path=SLICE, kind="replace",
        anchor='  "hardcoded_pattern_hits_total": 0,',
        new='  "hardcoded_pattern_hits_total": 1,',
        want=f"{_P69}::test_derived_counters_recompute_from_their_own_sections",
        why="六个硬编码模式的 0 改成 1 —— 「0 也要落成判据」必须打红",
        scope_check=top_field_is(
            ("honest_adjudication_summary", "hardcoded_pattern_hits_total"), 1),
        tags=("property23", "counters"),
    ),
    Mutation(
        id="M30", side="be", path=SLICE, kind="replace",
        scope=L2_TABLE_KEY, offset=OFF_ROW_KIND,
        anchor='     "kind": "generated_opaque_string",',
        new='     "kind": "array_index",',
        want=f"{_P23}::test_declared_dynamic_tables_avoid_forbidden_identity_kinds",
        wants=(
            f"{_P23}::test_family_b_zero_is_a_judgement_not_an_absence",
            f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",
            f"{_CONTRACT}::TestSliceSchemaPositiveExample::test_every_scanned_slice_passes_the_schema",
            f"{_COVERAGE}::test_every_slice_passes_the_json_nominated_validator",
        ),
        why="把动态行身份写成禁止值 —— 范式条件节的 forbidden_identity_kinds 与本守卫都必须打红",
        scope_check=dynamic_table_kind_is("L2-2", "array_index"),
        tags=("property23",),
    ),
    Mutation(
        id="M31", side="be", path=SLICE, kind="replace",
        anchor='  "blocking_preconditions_total": 10,',
        new='  "blocking_preconditions_total": 9,',
        want=f"{_ADJ}::test_every_blocking_precondition_is_referenced_by_someone",
        wants=(f"{_P69}::test_derived_counters_recompute_from_their_own_sections",),
        why="BP 总数抄错 —— 声明/引用/计数三方等值必须打红",
        scope_check=top_field_is(
            ("honest_adjudication_summary", "blocking_preconditions_total"), 9),
        tags=("counters",),
    ),

    # ══ G. 删除清册 ═══════════════════════════════════════════════════════
    Mutation(
        id="M32", side="be", path=PLAN, kind="replace",
        anchor='  "dual_mode_module_files_total": 9,',
        new='  "dual_mode_module_files_total": 8,',
        want=f"{_DEL}::test_plan_counters_recompute",
        why="把「9 个文件」抄成 8（== entry 数）—— 「9 ≠ 8」这条 L 循环形态特征必须打红",
        scope_check=plan_field_is(("counters", "dual_mode_module_files_total"), 8),
        tags=("plan",),
    ),
    Mutation(
        id="M33", side="be", path=PLAN, kind="replace",
        anchor='  "host_inlined_blocks_to_remove": 0,',
        new='  "host_inlined_blocks_to_remove": 1,',
        want=f"{_DEL}::test_plan_has_no_host_inlined_class",
        why="声称有宿主内联块（照抄 H/K）—— L 域现算 0 处必须打红",
        scope_check=plan_field_is(("counters", "host_inlined_blocks_to_remove"), 1),
        tags=("plan",),
    ),
    Mutation(
        id="M34", side="be", path=PLAN, kind="replace",
        anchor='  "localStorage_prefix_declaration_sites": 11,',
        new='  "localStorage_prefix_declaration_sites": 9,',
        want=f"{_DEL}::test_plan_localstorage_prefix_sites_recompute",
        wants=(f"{_DEL}::test_plan_counters_recompute",),
        why="漏掉共享载体的两处前缀（step 5 的收敛面积算小了）—— 现算必须打红",
        scope_check=plan_field_is(("counters", "localStorage_prefix_declaration_sites"), 9),
        tags=("plan",),
    ),
    Mutation(
        id="M35", side="be", path=PLAN, kind="replace",
        anchor=(
            '    "template_block": "audit-platform/frontend/src/components/workpaper/'
            'l5/core/L5TabAdjudication.vue#L16",'
        ),
        new=(
            '    "template_block": "audit-platform/frontend/src/components/workpaper/'
            'l5/core/L5TabAdjudication.vue#L17",'
        ),
        want=f"{_DEL}::test_plan_inert_blocks_are_real",
        why="把 inert 块的模板行号指偏一行（L17 不是 el-segmented 那行）—— 「块是真的」必须现读打红",
        scope_check=lambda raw: any(
            str(b["template_block"]).endswith("L5TabAdjudication.vue#L17")
            for b in _doc(raw)["inert_switch_blocks_to_remove"]["blocks"]),
        tags=("plan", "inert"),
    ),
    Mutation(
        id="M36", side="be", path=PLAN, kind="replace",
        anchor=L5_CARRIER_IN_PLAN,
        new=(
            '    "carrier_module_to_delete_with_it": "audit-platform/frontend/src/components/'
            'workpaper/composables/useL6DualMode.ts",'
        ),
        want=f"{_DEL}::test_plan_four_deletion_classes_partition_the_nine_files",
        why="把 L5 的 carrier 指到 L6 的模块 —— 集合等值判据必须打红",
        scope_check=plan_inert_block_carrier_is(
            "L5",
            "audit-platform/frontend/src/components/workpaper/composables/useL6DualMode.ts"),
        tags=("plan",),
    ),
    Mutation(
        id="M37", side="be", path=PLAN, kind="replace",
        anchor='  "shared_cycle_carrier_consumers_after": 1,',
        new='  "shared_cycle_carrier_consumers_after": 0,',
        want=f"{_DEL}::test_plan_counters_recompute",
        wants=(f"{_DEL}::test_plan_shared_numbers_agree_with_the_slice",),
        why="把部分收缩写成删到 0 —— plan 与 slice 的一致性判据必须打红",
        scope_check=plan_field_is(("counters", "shared_cycle_carrier_consumers_after"), 0),
        tags=("plan",),
    ),
    Mutation(
        id="M38", side="be", path=PLAN, kind="replace",
        anchor='  "entries_with_must_not_wire_to": 4,',
        new='  "entries_with_must_not_wire_to": 3,',
        want=f"{_DEL}::test_plan_must_not_wire_to_targets_are_the_orphan_twins",
        wants=(f"{_DEL}::test_plan_counters_recompute",),
        why="must_not_wire_to 的 entry 数抄错 —— orphan 全覆盖判据必须打红",
        scope_check=plan_field_is(("counters", "entries_with_must_not_wire_to"), 3),
        tags=("plan",),
    ),

    # ══ H. 真源码变异（证明 impl 侧是现读而不是快照）════════════════════════
    Mutation(
        id="M39", side="be", path=TAB_L5_ADJ, kind="replace",
        anchor=(
            '        <el-segmented v-model="dualMode.mode.value" '
            ':options="dualMode.modeOptions.value" size="small" '
            '@change="(val: any) => dualMode.switchMode(val)" />'
        ),
        new=(
            '        <el-segmented v-if="dualMode.mode.value === \'structured\'" '
            'v-model="dualMode.mode.value" '
            ':options="dualMode.modeOptions.value" size="small" '
            '@change="(val: any) => dualMode.switchMode(val)" />'
        ),
        want=f"{_INERT}::test_inert_switch_has_no_mode_gated_branch_and_no_oo_component",
        why="在真源码里加一处以 mode 为条件的分支 —— inert 结论必须由现读模板推出而不是抄 slice",
        scope_check=text_contains("v-if=\"dualMode.mode.value === 'structured'\""),
        tags=("source", "inert"),
    ),
    Mutation(
        id="M40", side="be", path=HOST_L1, kind="replace",
        anchor=(
            '        v-if="isProcedureSheet && '
            'procedureDualMode.currentMode.value === \'onlyoffice\'"'
        ),
        new='        v-if="isProcedureSheet"',
        want=f"{_INERT}::test_the_control_group_really_has_a_mode_gated_oo_mount",
        wants=(
            f"{_P20}::test_ui_toolbar_gate_anchors_are_resolvable_or_explicitly_absent",
        ),
        why="拆掉对照组的 mode 门控 —— 「扫描器不是恒 0」这条非空跑证明必须打红",
        scope_check=text_both('v-if="isProcedureSheet"',
                              "procedureDualMode.currentMode.value === 'onlyoffice'\""),
        tags=("source", "inert"),
    ),
    Mutation(
        id="M41", side="be", path=L3_ORPHAN, kind="replace",
        anchor="const STORAGE_KEY = 'l3-dual-mode'",
        new="const STORAGE_KEY = `l3-dual-mode-${wpId.value}`",
        want=f"{_FORM}::test_ld6_only_one_module_is_not_scoped_to_wp_id",
        why="反向变异：把唯一未按 wpId 分区的模块**修好** ⇒ LD-6 的登记必须因 XPASS 式落空而打红",
        scope_check=text_contains("l3-dual-mode-${wpId.value}"),
        tags=("source", "reverse"),
    ),
    Mutation(
        id="M42", side="be", path=L2_DETAIL, kind="replace",
        anchor="    rowId: raw.rowId || generateRowId(),",
        new="    rowId: raw.rowId || `row-${idx}`,",
        want=f"{_P23}::test_family_b_zero_is_a_judgement_not_an_absence",
        wants=(
            f"{_P23}::test_positional_identity_inventory_is_exhaustive_and_partitioned",
            f"{_P23}::test_the_two_containers_partition_all_hits",
        ),
        why="把反序列化兜底退化成位置化身份 —— family_b 的「0 是判断不是缺席」必须打红",
        scope_check=text_both("rowId: raw.rowId || `row-${idx}`", "|| generateRowId(),"),
        tags=("source", "property23"),
    ),
    Mutation(
        id="M43", side="be", path=TAB_L1_ADJ, kind="replace",
        anchor="    rowKey: String(idx),",
        new="    rowKey: c.name,",
        want=f"{_P23}::test_positional_identity_inventory_is_exhaustive_and_partitioned",
        wants=(
            f"{_P23}::test_family_a_hit_is_a_real_line_of_source",
            f"{_P23}::test_hardcoded_scan_is_all_zero_and_non_vacuous",
            f"{_P23}::test_the_two_containers_partition_all_hits",
        ),
        why="反向变异：把 BP-10 的位置化身份**修好** ⇒ 登记与非空跑证明双向锁死，必须打红提醒摘掉登记",
        scope_check=text_both("rowKey: c.name,", "rowKey: String(idx),"),
        tags=("source", "reverse"),
    ),
    Mutation(
        id="M44", side="be", path=HOST_L4, kind="replace",
        anchor=(
            '        v-else-if="currentSheet === \'L4-7\' && '
            'bondBranch === \'到期一次还本付息\'"'
        ),
        new=(
            '        v-else-if="currentSheet === \'L4-7A\' && '
            'bondBranch === \'到期一次还本付息\'"'
        ),
        want=f"{_FORM}::test_ld8_only_l4_collapses_sheet_codes",
        wants=(
            f"{_SHEET}::test_sheet_coverage_recomputes_three_ways",
            f"{_SHEET}::test_router_ambiguity_recomputes_and_splits_reachable_from_not",
            f"{_SHEET}::test_entry_level_sheet_granularity_mirrors_the_audit",
        ),
        why="把 L4 的一个同码 dispatch 改成唯一码 —— 折叠事实与 router 歧义都由现读推出，必须打红",
        scope_check=text_contains("currentSheet === 'L4-7A'"),
        tags=("source", "sheet"),
    ),
    Mutation(
        id="M45", side="be", path=HOST_L1, kind="replace",
        anchor="        :sheet-name=\"props.sheetName || 'L1A'\"",
        new='        :sheet-name="props.sheetName"',
        want=f"{_SHEET}::test_bare_code_fallback_bindings_are_exactly_the_two_declared",
        why="拆掉裸码兜底绑定 —— 「恰两处」的现算判据必须打红",
        scope_check=text_both(':sheet-name="props.sheetName"', "props.sheetName || 'L1A'"),
        tags=("source", "sheet"),
    ),
    Mutation(
        id="M46", side="be", path=OO_ROUTER, kind="replace",
        anchor="            if ws.title == target_sheet:",
        new="            if ws.title.strip() == target_sheet.strip():",
        want=f"{_SELF}::test_router_matcher_replicates_the_real_source_rule",
        why="改掉 router 的精确匹配分支 —— 复刻规则的自检必须打红（否则 _router_matches 会静默过期）",
        scope_check=text_both("ws.title.strip() == target_sheet.strip():",
                              "            if ws.title == target_sheet:"),
        tags=("source", "sheet"),
    ),
    Mutation(
        id="M47", side="be", path=REGISTRY_TS, kind="replace",
        anchor="    component: defineAsyncComponent(() => import('./GtL8FinancialExpenses.vue')),",
        new="    component: defineAsyncComponent(() => import('./GtL8FinancialExpensesX.vue')),",
        want=f"{_SCOPE}::test_host_module_edges_in_the_renderer_registry_are_real",
        why="把 L8 宿主的 registry 模块边指到不存在的文件 —— 可达性判据必须由模块边现算打红",
        scope_check=text_contains("GtL8FinancialExpensesX.vue"),
        tags=("source", "reachability"),
    ),
    Mutation(
        id="M48", side="be", path=HOST_L1, kind="insert",
        anchor='      <div v-if="isProcedureSheet" class="l1-procedure-toolbar">',
        new='        <GtEntrySyncCapabilityNotice :entry-id="\'xlsx/gt-l1-short-term-loans\'" />',
        want=f"{_P20}::test_bp7_is_registered_because_no_host_mounts_the_notice",
        wants=(f"{_ADJ}::test_ac15_is_declared_not_applicable_and_ac14_is_the_live_one",),
        why="反向变异：在宿主里**真挂上** AC 1.4 提示组件 ⇒ BP-7 可解除，登记必须因此打红",
        scope_check=text_contains("GtEntrySyncCapabilityNotice"),
        tags=("source", "reverse", "ui"),
    ),
    Mutation(
        id="M49", side="be", path=HOST_L1, kind="insert",
        anchor="import http from '@/utils/http'",
        new="import { useChecklistPersistence } from '@/composables/workpaper/useChecklistPersistence'",
        want=f"{_HTML}::test_no_l_host_imports_the_shared_checklist_persistence",
        why="在 L 宿主里引入共享持久化适配器 —— LD-3 的否定式判据（L 域恒 0）必须打红",
        scope_check=text_contains("useChecklistPersistence"),
        tags=("source", "form"),
    ),
    Mutation(
        id="M50", side="be", path=HOST_L1, kind="insert",
        anchor='      <div v-if="isProcedureSheet" class="l1-procedure-toolbar">',
        new='        <el-tag type="success">可双向回写</el-tag>',
        want=f"{_ADJ}::test_no_host_template_claims_bidirectional",
        why="在宿主模板里宣称「可双向回写」—— AC 1.4 / Property 3 的否定方向必须打红",
        scope_check=text_contains("可双向回写"),
        tags=("source", "ui"),
    ),
]

GUARD_FILES = {
    T54: "Task 54 新建 —— L 循环迁移守卫",
    _CONTRACT: "范式校验器（本 slice 必须过它，且反例两侧都验）",
    _COVERAGE: "校验器覆盖面（scan_glob 自动收本 slice，_UNJUDGED_SLICES 必须为空）",
}

if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="Task 54 · L 循环 Excel 独立 entry 迁移守卫变异检验",
            backend_args=[
                "backend/tests/workpaper_sync/test_task54_l_cycle_migration.py",
                "backend/tests/workpaper_sync/test_migration_paradigm_contract.py",
                "backend/tests/workpaper_sync/test_slice_schema_validator_coverage.py",
                "-p", "no:randomly", "-q",
            ],
        )
    )
