# -*- coding: utf-8 -*-
r"""Task 56 守卫变异检验 —— N 循环（税项循环）Excel 独立 entry 迁移。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 5 Task 56

用平台共享件 `backend/scripts/_mutation_kit`（`test_mutation_kit_adoption.py` 对新脚本强制
采纳）。`guard_files` 是签名层面必填的覆盖面分母。

═══ 本脚本的六条硬约束 ═══

1. **每条变异都带 `scope_check`**。四态判定式「新增失败集合是否为空」识别不出「锚点落在被测
   判据的作用域之外」—— 改到了别处会被判 GREEN（守卫缺陷），而真相是脚本缺陷。
   🔴 Task 54 的 M10 教训：`scope_check` **必须解析 JSON 定位到目标节**，不能用「文本里不存在
   某字面量」当判据 —— 同一字面量常出现在散文里，那种判据恒假。本脚本的数据侧回调一律
   `json.loads` 后按路径取值断言。

2. 🔴 **`scope_check` 与锚点都禁用含 `\n` 的字面量**（Task 55 的 M38/M44 各踩一次）：
   工作树是 CRLF，多行字面量恒假 ⇒ RED 会被误报成 ANCHOR-MISS。源码侧的作用域自证一律
   改「按整行集合断言」（`[line.rstrip("\r").strip() for line in text.split("\n")]`）。

3. **重复形态字段用 `scope` + `offset` 相对定位，绝不用绝对行号**。本 slice 有 **5 条** entry，
   故 entry 级字段全是 dup=5，一律以该 entry 唯一的 `"entry_id": "…"` 行作 `scope`，
   `offset` 由一次性诊断**实算**（非估计值）。

4. **变异按「可区分的错法」枚举而不是逐条目复制**，并分布在不同 entry 上（N1/N2/N3/N4/N5），
   从而同时走通各 entry 的 offset。

5. **必须含反向变异**（把缺陷修好也要打红）。只验「新增缺陷」一个方向是半个判据：
   缺陷被修好而登记没删，报告会长期挂着一条已解决的债。本脚本的反向变异：
   * M23 把 N4 的 inert 空回调**改成真实现**（BP-5 可解除 ⇒ inert 数 2→1）；
   * M24 给 N2-8 的手工行**补上 `:key` 消费方**（latent 缺陷升级为 live ⇒ 判据必须变红）；
   * M25 把 N3 宿主的 legacy health 直调**删掉**（BP-4 可解除 ⇒ ND-4 的 1 变 0）；
   * M26 在 N1 宿主里**真挂上** AC 1.4 的 notice 组件（BP-7 可解除）；
   * M27 把 N1 审定表的位置化持久化键**改成 category**（BP-8 可解除 ⇒ 持久化键族 3→0）。

6. **真源码变异**（M18~M31）—— 数据侧变异只能证明「守卫读了 slice」；只有改真源码还打红，
   才能证明 impl 侧是**现读**而不是抄了一份快照。N 循环的判据里有十类必须有源码变异撑着：
   ① `ITEM_PREFIX` 三边锁（M18）· ② 多行 import 的边解析（M19）· ③ 权威册 sheet 名不 strip
   （M20，改 slice 侧的脏字面量登记）· ④ orphan 可达性（M21：给 orphan 加一条真 import）·
   ⑤ 三载体族划分（M22）· ⑥ inert 判据（M23 反向）· ⑦ render-key 消费方（M24 反向）·
   ⑧ 宿主直调 legacy 端点（M25 反向）· ⑨ AC 1.4 挂载（M26 反向）· ⑩ 位置化持久化键（M27 反向）·
   ⑪ 硬编码族非空跑（M28/M29）· ⑫ V1/V2 伪造键（M30）· ⑬ N5 跨命名空间只读（M31）。

用法（仓库根；本仓库 PATH 上的 `python` 可能指向坏掉的解释器，必须用显式解释器）::

    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task56_n_cycle_guards.py --list
    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task56_n_cycle_guards.py --check-anchors
    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task56_n_cycle_guards.py --run M01,M02

🔴 **禁止后台执行**：外层 shell 被杀会让 python 变成孤儿进程，与前台运行同时变异同一文件 ⇒
`RestoreFailed` rc=5。分批跑用 `--run M01,M02,...`（子集运行不做覆盖面结论）。

🔴 **`delete` 不要用在数组末元素上**：删掉末元素会给前一行留下尾逗号、JSON 失效，
`scope_check` 的 `json.loads` 抛异常 ⇒ 判定 ERROR（脚本缺陷，不是守卫缺陷）。一律用 `replace`。

🔴 **运行前把并发遗留的 `backend/scripts/**/*.mutbak` 移到仓库外**（`%TEMP%`），否则
`_mutation_kit` 的残留扫描会 `[ABORT]`。跑完原位放回并核验 sha256；**绝不 `--restore`**。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

# ── 被变异的对象 ───────────────────────────────────────────────────────────
SLICE = "backend/data/workpaper_sync_n_cycle_manifest_slice.json"
PLAN = "backend/data/workpaper_sync_n_cycle_deletion_plan.json"
FE = "audit-platform/frontend/src"
WP = f"{FE}/components/workpaper"
CO = f"{WP}/composables"
HOST_N1 = f"{WP}/GtN1DeferredTaxAssets.vue"
HOST_N2 = f"{WP}/GtN2TaxesPayable.vue"
HOST_N3 = f"{WP}/GtN3DeferredTaxLiabilities.vue"
HOST_N4 = f"{WP}/GtN4TaxesAndSurcharges.vue"
HOST_N5 = f"{WP}/GtN5IncomeTaxExpense.vue"
FORMDATA_N1 = f"{CO}/useN1FormData.ts"
ADJ_N1 = f"{CO}/useN1Adjudication.ts"
OTHERTAX_N2 = f"{CO}/useN2OtherTaxCalc.ts"
TAB_N2_OTHERTAX = f"{WP}/n2/calc/N2TabOtherTaxCalc.vue"
DETAIL_N3 = f"{CO}/useN3Detail.ts"
ADJV2_N4 = f"{CO}/useN4AdjudicationV2.ts"
CROSS_N5 = f"{CO}/useN5CrossSheet.ts"
ROUTING_N2 = f"{CO}/n2SheetRouting.ts"
SHARED_ROUTER = f"{CO}/shared/cycleSheetRouting.ts"

# ── 期望打红的守卫（文件::类::方法，与 pytest 的 short nodeid 同形）─────────
T56 = "test_task56_n_cycle_migration.py"
_SELF = f"{T56}::TestGuardSelfChecks"
_SCOPE = f"{T56}::TestSliceScopeIsRecomputable"
_ADJ = f"{T56}::TestAdjudicationLegality"
_HTML = f"{T56}::TestHtmlCounterpartIsSourceBacked"
_TK = f"{T56}::TestTransportKeyResolution"
_P23 = f"{T56}::TestProperty23DynamicRowIdentity"
_FORM = f"{T56}::TestNCycleFormDifferences"
_ORPHAN = f"{T56}::TestOrphanInventory"
_SHEET = f"{T56}::TestSheetGranularityAndRouter"
_SWITCH = f"{T56}::TestModeSwitchResolution"
_P69 = f"{T56}::TestProperty69EvidenceAndCounters"
_P70 = f"{T56}::TestProperty70CrossEntryIsolation"
_DEL = f"{T56}::TestDeletionPlanConsistency"
_PARA = f"{T56}::TestParadigmCompliance"
_CONTRACT = "test_migration_paradigm_contract.py"
_COVERAGE = "test_slice_schema_validator_coverage.py"


def EID(slug: str) -> str:
    """某 entry 在 `independent_entries` 里唯一的 scope 行（dup=1，3 空格缩进）。"""
    return '   "entry_id": "xlsx/%s",' % slug


N1 = EID("gt-n1-deferred-tax-assets")
N2 = EID("gt-n2-taxes-payable")
N3 = EID("gt-n3-deferred-tax-liabilities")
N4 = EID("gt-n4-taxes-and-surcharges")
N5 = EID("gt-n5-income-tax-expense")

#: 逐字段 offset（由一次性诊断**实算**，非估计值）。
#: 🔴 逐 entry 的 offset **不相等**（各 entry 的 source_refs / how_resolved 文本行数不同）
#: ⇒ 必须逐 entry 实算。slice 用 `indent=1` 落盘 ⇒ entry 级字段是 3 空格缩进、
#: entry 内嵌一层是 4 空格、per_sheet 行是 6 空格。
OFF_CAPABILITY = 6
OFF_VERDICT_STAGE = 7
OFF_CAPABILITY_TARGET = 8
OFF_HTML_VERDICT = {"N1": 20, "N2": 19, "N3": 20, "N4": 19, "N5": 21}
OFF_MIRROR_CAPABILITY = {"N1": 69, "N2": 68, "N3": 69, "N4": 68, "N5": 70}
#: `dual_mode_carrier.kind` 相对 entry_id 行的偏移（N4 / N5 各自实算）。
OFF_CARRIER_KIND = {"N4": 90, "N5": 93}


# ══════════════════════════════════════════════════════════════════════════
# scope_check 工具：数据侧一律解析 JSON 定位目标节（Task 54 的 M10 教训）
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
        for key in path:
            if not isinstance(node, dict) or key not in node:
                return False
            node = node[key]
        return node == expected
    return check


def doc_path_is(path: tuple[Any, ...], expected: Any):
    def check(data: bytes) -> bool:
        node: Any = _doc(data)
        for key in path:
            try:
                node = node[key]
            except (KeyError, IndexError, TypeError):
                return False
        return node == expected
    return check


def doc_path_absent(path: tuple[Any, ...]):
    def check(data: bytes) -> bool:
        node: Any = _doc(data)
        for key in path[:-1]:
            try:
                node = node[key]
            except (KeyError, IndexError, TypeError):
                return True
        if isinstance(node, dict):
            return path[-1] not in node
        if isinstance(node, list):
            return not isinstance(path[-1], int) or path[-1] >= len(node)
        return True
    return check


def _lines(data: bytes) -> list[str]:
    """按**整行集合**断言用（禁多行字面量：CRLF 下恒假）。"""
    return [line.rstrip("\r").strip() for line in data.decode("utf-8").split("\n")]


def source_has_line(needle: str):
    """源码侧作用域自证：变异后的文件里**存在**某条整行（strip 后逐字相等）。"""
    def check(data: bytes) -> bool:
        return needle.strip() in _lines(data)
    return check


def source_lacks_line(needle: str):
    def check(data: bytes) -> bool:
        return needle.strip() not in _lines(data)
    return check


def source_line_count_is(needle: str, expected: int):
    def check(data: bytes) -> bool:
        return _lines(data).count(needle.strip()) == expected
    return check


def source_matches(pattern: str, expected: int):
    """整文匹配计数（用于跨行结构；pattern 自身**不含** `\\n`）。"""
    rx = re.compile(pattern)
    def check(data: bytes) -> bool:
        return sum(1 for line in _lines(data) if rx.search(line)) == expected
    return check


# ══════════════════════════════════════════════════════════════════════════
# 变异清单
# ══════════════════════════════════════════════════════════════════════════
MUTATIONS: list[Mutation] = [
    # ── A 组：selection_rule / scope 可复算（数据侧）─────────────────────
    Mutation(
        id="M01", side="be", path=SLICE, kind="replace",
        anchor='   "entry_id": "xlsx/gt-n5-income-tax-expense",',
        new='   "entry_id": "xlsx/gt-n5-income-tax-expense-typo",',
        want=f"{_SCOPE}::test_selection_rule_recomputes_the_entry_set",
        why="改一条 entry_id ⇒ 按 selection_rule 现算的集合与声明不再等值。"
            "不能改 capability（那是别的判据）；改 id 才落在「集合等值」这条上。",
        scope_check=doc_path_is(("independent_entries", 4, "entry_id"),
                               "xlsx/gt-n5-income-tax-expense-typo"),
    ),
    Mutation(
        id="M02", side="be", path=SLICE, kind="replace",
        anchor='  "independent_entry_count": 5,',
        new='  "independent_entry_count": 4,',
        want=f"{_SCOPE}::test_scope_counters_match_the_manifest",
        why="scope 计数手改 ⇒ 与 manifest 现算不符。SR-1 同形。",
        scope_check=doc_path_is(("slice_scope", "independent_entry_count"), 4),
    ),
    Mutation(
        id="M03", side="be", path=SLICE, kind="replace",
        anchor='  "parent_duplicate_count": 4,',
        new='  "parent_duplicate_count": 0,',
        want=f"{_SCOPE}::test_parent_duplicate_children_recompute_and_the_section_is_present",
        why="🔴 ND-1：把子入口数改回 K/L/M 三轮的 0 ⇒ 现算 4 与声明 0 不符。"
            "这条同时证明「照抄 M 的 0」会被抓住。",
        scope_check=doc_path_is(("slice_scope", "parent_duplicate_count"), 0),
    ),
    Mutation(
        id="M04", side="be", path=SLICE, kind="replace",
        anchor='   "n1_subtree_components_without_oo_mount": 8',
        new='   "n1_subtree_components_without_oo_mount": 10',
        want=f"{_SCOPE}::test_children_have_no_write_channel_of_their_own_unlike_j",
        why="补集计数改错 ⇒ 现算 8 与声明 10 不符。补集是「只有 4 个子组件挂了 OO」这条结论的"
            "另一半，不验它就等于只验了正集。",
        scope_check=doc_path_is(
            ("parent_duplicate_summary", "counters", "n1_subtree_components_without_oo_mount"), 10),
    ),

    # ── B 组：待裁决态与 AC 12.8（数据侧，entry 级 offset）──────────────
    Mutation(
        id="M05", side="be", path=SLICE, kind="replace",
        anchor='   "capability": null,', scope=N1, offset=OFF_CAPABILITY,
        new='   "capability": "single_onlyoffice",',
        want=f"{_ADJ}::test_single_onlyoffice_requires_no_html_counterpart",
        why="🔴 AC 12.8 的核心：把有 HTML 对端的 entry 硬裁成 single_onlyoffice。"
            "这正是本轮 tasks.md 提醒「不要为了凑纯 OO entry 而硬裁」的那个错法。",
        scope_check=entry_field_is("xlsx/gt-n1-deferred-tax-assets", "capability",
                                  "single_onlyoffice"),
    ),
    Mutation(
        id="M06", side="be", path=SLICE, kind="replace",
        anchor='   "html_counterpart_verdict": "exists",', scope=N2,
        offset=OFF_HTML_VERDICT["N2"],
        new='   "html_counterpart_verdict": "none",',
        want=f"{_ADJ}::test_no_pure_oo_entry_exists_in_this_cycle",
        why="把一条 entry 的对端结论改成 none（伪造「纯 OO entry」）⇒ 与 summary 的"
            " html_counterpart_none==0 冲突。tasks.md 点名项的正面判据。",
        scope_check=entry_field_is("xlsx/gt-n2-taxes-payable", "html_counterpart_verdict", "none"),
    ),
    Mutation(
        id="M07", side="be", path=SLICE, kind="replace",
        anchor='   "html_counterpart_verdict": "exists",', scope=N3,
        offset=OFF_HTML_VERDICT["N3"],
        new='   "html_counterpart_verdict": "unresolved",',
        want=f"{_ADJ}::test_every_entry_has_a_binary_html_counterpart_verdict",
        why="AP-3：把「还没查」当结论。二值枚举必须拒收 unresolved。",
        scope_check=entry_field_is("xlsx/gt-n3-deferred-tax-liabilities",
                                  "html_counterpart_verdict", "unresolved"),
    ),
    Mutation(
        id="M08", side="be", path=SLICE, kind="delete",
        anchor='   "capability_target": "bidirectional",', scope=N4,
        offset=OFF_CAPABILITY_TARGET,
        want=f"{_ADJ}::test_capability_is_null_and_pending_fields_are_complete",
        why="SR-3 右支的三字段之一缺失 ⇒ 待裁决态不再合法（「留空而不解释」）。"
            "`capability_target` 不是数组末元素，删它不会留尾逗号。",
        scope_check=entry_field_absent("xlsx/gt-n4-taxes-and-surcharges", "capability_target"),
    ),
    Mutation(
        id="M09", side="be", path=SLICE, kind="replace",
        anchor='    "capability": "single_onlyoffice",', scope=N5,
        offset=OFF_MIRROR_CAPABILITY["N5"],
        new='    "capability": null,',
        want=f"{_ADJ}::test_manifest_mirror_divergence_is_registered_not_silently_equal",
        why="🔴 把 mirror 改成与 slice 裁决**相同** ⇒ 「必须不一致」这条判据打红。"
            "反过来写（断言相等）是本 spec 明确拒绝的形态。",
        scope_check=entry_path_is("xlsx/gt-n5-income-tax-expense",
                                  ("manifest_mirror", "capability"), None),
    ),
    Mutation(
        id="M10", side="be", path=SLICE, kind="replace",
        anchor='    "BP-12"',
        new='    "BP-99"',
        want=f"{_ADJ}::test_every_blocking_precondition_is_referenced_by_someone",
        why="entry 引用了不存在的 BP ⇒ 声明集合与引用集合不再相等（两个方向都咬）。",
        scope_check=lambda data: "BP-99" in [
            b for e in _doc(data)["independent_entries"]
            for b in e["capability_target_blocked_by"]],
    ),

    # ── C 组：Property 69 的计数与 evidence（数据侧）─────────────────────
    Mutation(
        id="M11", side="be", path=SLICE, kind="replace",
        anchor='  "capability_verdict_pending": 5,',
        new='  "capability_verdict_pending": 0,',
        line=2677,
        want=f"{_P69}::test_summary_counters_recompute_from_the_entries",
        why="summary 与明细脱节（SR-2 同形）。",
        scope_check=doc_path_is(("honest_adjudication_summary", "capability_verdict_pending"), 0),
    ),
    Mutation(
        id="M12", side="be", path=SLICE, kind="replace",
        anchor='  "authoritative_formula_cells_total": 2185,',
        new='  "authoritative_formula_cells_total": 2186,',
        line=2689,
        want=f"{_P69}::test_template_counters_recompute",
        why="公式格总数改 1 ⇒ openpyxl 现算不符。这条同时证明公式扫描是真跑而不是抄数。",
        scope_check=doc_path_is(
            ("honest_adjudication_summary", "authoritative_formula_cells_total"), 2186),
    ),
    Mutation(
        id="M13", side="be", path=SLICE, kind="replace",
        anchor='    "blocking_preconditions_total"',
        new='    "blocking_preconditions_total_TYPO"',
        want=f"{_P69}::test_counting_notes_cover_every_summary_counter",
        why="🔴 Task 54 的 M28/M29 教训：counting_notes 漏一族就等于那族可以随便填。"
            "把一族的键名改掉 ⇒ 覆盖面元判据（并集必须覆盖全部数值键）打红。",
        scope_check=lambda data: "blocking_preconditions_total_TYPO" in json.dumps(
            _doc(data)["honest_adjudication_summary"]["counting_notes"], ensure_ascii=False),
    ),
    Mutation(
        id="M14", side="be", path=SLICE, kind="replace",
        anchor='   "unadjudicated": 5,',
        new='   "unadjudicated": 0,',
        want=f"{_P69}::test_slice_counters_are_all_zero_except_unadjudicated",
        wants=(f"{_CONTRACT}::test_every_scanned_slice_passes_the_schema",),
        why="SR-9：把全部 entry 记成待裁决同时报 unadjudicated=0 —— SR-3 右支被当后门用的形态。",
        scope_check=doc_path_is(
            ("honest_adjudication_summary", "slice_counters", "unadjudicated"), 0),
    ),
    Mutation(
        id="M15", side="be", path=SLICE, kind="replace",
        anchor='     "BP-4：宿主直调 legacy `/api/workpapers/onlyoffice/health`，违反范式 step 6。",',
        new='     "BP-4 宿主直调 legacy 端点（已去掉编号冒号）",',
        want=f"{_P69}::test_entry_scoped_bp_appears_only_in_its_own_reasons",
        why="entry 级 BP 的 reasons 与 BP 自己的 entries 列表必须双向一致 —— "
            "去掉 `BP-4：` 前缀 ⇒ N3 的 reasons 不再提及 BP-4，双向判据打红。",
        scope_check=lambda data: not any(
            "BP-4：" in r
            for e in _doc(data)["independent_entries"]
            for r in e["evidence"]["unverifiable_reasons"]),
    ),

    # ── D 组：Property 70（跨 entry 隔离，数据侧）────────────────────────
    Mutation(
        id="M16", side="be", path=SLICE, kind="replace",
        anchor='  "backend/data/workpaper_sync_m_cycle_manifest_slice.json"',
        new='  "backend/data/workpaper_sync_z_cycle_manifest_slice.json"',
        want=f"{_P70}::test_sibling_slices_declared_match_the_disk",
        why="🔴 兄弟 slice 必须收全**十份**：把 M 那份改成不存在的 Z ⇒ 与磁盘现扫不等值。"
            "这条直接对应交付要求「sibling_slices 收全 D/E/F/G/H/I/J/K/L/M 十份」。",
        scope_check=lambda data: (
            "backend/data/workpaper_sync_z_cycle_manifest_slice.json"
            in _doc(data)["sibling_slices"]),
    ),
    Mutation(
        id="M17", side="be", path=SLICE, kind="replace",
        anchor='  "pairwise_recipe": "配对数 = C(len(slices), 2)。本轮 slice 数 11 ⇒ '
               '55 对。\U0001f534 守卫必须**现算** `len(slices) * (len(slices) - 1) // 2` '
               '并与实际比较的对数相等，不得写死 55 —— 下一轮（Task 57 的 A/B/C/S）会再变。",',
        new='  "pairwise_recipe": "配对数 = 45 对（写死）。",',
        want=f"{_P70}::test_all_slices_are_pairwise_disjoint",
        why="🔴 把对数写死成 M 那轮的 45 ⇒ 与现算 `C(11,2)=55` 不符。"
            "交付要求明确点名「必须现算不写死」。",
        scope_check=lambda data: (
            "45" in _doc(data)["cross_entry_isolation"]["pairwise_recipe"]
            and "55" not in _doc(data)["cross_entry_isolation"]["pairwise_recipe"]),
    ),

    # ── E 组：真源码变异（证明 impl 现读）───────────────────────────────
    Mutation(
        id="M18", side="be", path=FORMDATA_N1, kind="replace",
        anchor="const ITEM_PREFIX = 'N1-'",
        new="const ITEM_PREFIX = 'N1x-'",
        want=f"{_HTML}::test_item_prefix_is_read_from_the_owner_constant",
        why="🔴 三边锁的第三边：改 impl 的 owner 常量 ⇒ 与 slice 声明的 `N1-` 不再逐字相等。"
            "只验「声明里有个前缀」而不现读 impl，这条会 GREEN。",
        scope_check=source_has_line("const ITEM_PREFIX = 'N1x-'"),
    ),
    Mutation(
        id="M19", side="be", path=HOST_N2, kind="replace",
        anchor="} from './composables/n2SheetRouting'",
        new="} from './composables/n2SheetRoutingXX'",
        want=f"{_SELF}::test_import_scanner_accepts_a_multiline_import",
        wants=(f"{_SHEET}::test_router_kind_split_is_real",),
        why="🔴 本轮实测缺陷的锚：`from '…'` 独占一行（多行 import 的收尾行）。"
            "改掉它 ⇒ 该模块的生产边变 0，自检与 router 划分判据都该红。"
            "这条证明边扫描器真在按路径解析，而不是只看「同一行 import…from」。",
        scope_check=source_lacks_line("} from './composables/n2SheetRouting'"),
    ),
    Mutation(
        id="M20", side="be", path=SLICE, kind="replace",
        anchor='    "sheet": "税金及附加审计程序表N4A ",',
        new='    "sheet": "税金及附加审计程序表N4A",',
        want=f"{_FORM}::test_nd6_dirty_sheet_name_literals_recompute",
        wants=(f"{_SELF}::test_sheet_names_are_not_stripped",
               f"{_SHEET}::test_per_sheet_table_equals_the_workbook_sheet_list"),
        why="🔴 ND-6：把尾随空格 strip 掉 ⇒ 与 openpyxl 现读的真名不等值。"
            "这条证明 sheet 名判据不许 strip（strip 了 BP-11 会凭空消失）。",
        scope_check=lambda data: (
            "税金及附加审计程序表N4A" in json.dumps(
                _doc(data)["sheet_granularity_and_router_audit"]["dirty_sheet_name_literals"],
                ensure_ascii=False)
            and "税金及附加审计程序表N4A " not in json.dumps(
                _doc(data)["sheet_granularity_and_router_audit"]["dirty_sheet_name_literals"],
                ensure_ascii=False)),
    ),
    Mutation(
        id="M21", side="be", path=HOST_N5, kind="insert",
        anchor="import http from '@/utils/http'",
        new="import { useN5DualMode } from './composables/useN5DualMode'",
        want=f"{_ORPHAN}::test_declared_orphans_are_unreachable_and_the_set_matches",
        wants=(f"{_FORM}::test_nd2_three_carrier_kinds_partition_the_hosts",),
        why="🔴 给一个 orphan 加一条**真** import ⇒ 它不再是 orphan，"
            "现算集合与声明集合不再等值。可达性判据（不是入度、不是命名）由此证明为真跑。",
        scope_check=source_has_line(
            "import { useN5DualMode } from './composables/useN5DualMode'"),
    ),
    Mutation(
        id="M22", side="be", path=SLICE, kind="replace",
        anchor='    "kind": "host_inline_inert",', scope=N4,
        offset=OFF_CARRIER_KIND["N4"],
        new='    "kind": "per_entry_wrapper_over_shared_base",',
        want=f"{_FORM}::test_nd2_three_carrier_kinds_partition_the_hosts",
        why="把内联载体谎报成模块载体 ⇒ 「import 的宿主与内联的宿主互补划分」这条打红。"
            "只数「有几种 kind 字符串」不会红（数量不变），必须验形态。",
        scope_check=entry_path_is("xlsx/gt-n4-taxes-and-surcharges",
                                  ("dual_mode_carrier", "kind"),
                                  "per_entry_wrapper_over_shared_base"),
    ),

    # ── F 组：反向变异（缺陷修好也打红）─────────────────────────────────
    Mutation(
        id="M23", side="be", path=HOST_N4, kind="replace",
        anchor="  onModeChange: () => {},",
        new="  onModeChange: (v: any) => { dualMode.currentMode.value = v },",
        want=f"{_FORM}::test_nd3_inert_switches_are_noop_callbacks",
        wants=(f"{_SWITCH}::test_switch_counters_recompute",),
        why="🔴 **反向**：把 N4 的空回调改成真实现 ⇒ inert 现算 2→1，与声明不符。"
            "BP-5 若被真修好，本 slice 的登记必须同步删 —— 只验「新增缺陷」一个方向是半个判据。",
        scope_check=source_lacks_line("onModeChange: () => {},"),
    ),
    Mutation(
        id="M24", side="be", path=TAB_N2_OTHERTAX, kind="insert",
        anchor="<template>",
        new='  <!-- mutation --><span :key="1" />',
        want=f"{_P23}::test_the_unconsumed_render_key_really_has_no_consumer",
        why="🔴 **反向**：给 N2-8 的表加一个 `:key` 消费方 ⇒ 「位置化身份字段当前无消费方」"
            "这条前提不再成立，缺陷等级要从 latent 升级为 live。判据两面都咬。",
        scope_check=source_has_line('<!-- mutation --><span :key="1" />'),
    ),
    Mutation(
        id="M25", side="be", path=HOST_N3, kind="replace",
        anchor="    const res = await http.get('/api/workpapers/onlyoffice/health', "
               "{ _silent: true } as any)",
        new="    const res = { data: { healthy: true } } as any",
        want=f"{_FORM}::test_nd4_exactly_one_host_calls_the_legacy_health_endpoint",
        wants=(f"{_ORPHAN}::test_legacy_endpoint_call_counts_recompute",),
        why="🔴 **反向**：把 N3 宿主的 legacy 直调删掉 ⇒ ND-4 的 1 变 0，声明与现算不符。"
            "BP-4 修好即打红，逼作者回来删登记。",
        scope_check=source_lacks_line(
            "const res = await http.get('/api/workpapers/onlyoffice/health', "
            "{ _silent: true } as any)"),
    ),
    Mutation(
        id="M26", side="be", path=HOST_N1, kind="insert",
        anchor="const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))",
        new="import GtEntrySyncCapabilityNotice from './sync/GtEntrySyncCapabilityNotice.vue'",
        want=f"{_ADJ}::test_bp7_is_registered_because_no_n_host_mounts_the_notice",
        why="🔴 **反向**：在 N1 宿主里真挂上 AC 1.4 的提示组件 ⇒ BP-7 可解除，"
            "「0/5 挂载」的现算与声明不符。AP-4（只改 capability 不改界面）的对偶方向。",
        scope_check=source_has_line(
            "import GtEntrySyncCapabilityNotice from './sync/GtEntrySyncCapabilityNotice.vue'"),
    ),
    Mutation(
        id="M27", side="be", path=ADJ_N1, kind="replace",
        anchor="    formData.debouncedSave(`${ITEM_PREFIX}-${index}`, {",
        new="    formData.debouncedSave(`${ITEM_PREFIX}-${row.category}`, {",
        line=429,
        want=f"{_P23}::test_two_families_and_the_reverse_families_recompute",
        wants=(f"{_P23}::test_identity_counters_recompute",
               f"{_P23}::test_defect_tables_source_refs_carry_the_expected_tokens"),
        why="🔴 **反向**：把位置化持久化键改成稳定 category 键（BP-8 的正解）⇒ "
            "持久化键族现算 3→2，与声明不符。缺陷修好也必须打红。",
        scope_check=source_has_line(
            "formData.debouncedSave(`${ITEM_PREFIX}-${row.category}`, {"),
    ),

    # ── G 组：硬编码族非空跑 + 伪造键 + 跨命名空间（真源码）──────────────
    Mutation(
        id="M28", side="be", path=DETAIL_N3, kind="insert",
        anchor="function generateRowId(): string {",
        new="  const _mut = blankRows(page, 3)",
        want=f"{_P23}::test_hardcoded_scan_is_all_zero_and_non_vacuous",
        why="🔴 往真源码注入一处 `blankRows(p, 3)` ⇒ 该族从 0 变 1，证明「六族全 0」是非空跑"
            "而不是正则失效。",
        scope_check=source_has_line("const _mut = blankRows(page, 3)"),
    ),
    Mutation(
        id="M29", side="be", path=DETAIL_N3, kind="insert",
        anchor="function generateRowId(): string {",
        new="  const _mut2 = `row-${idx}`",
        want=f"{_P23}::test_hardcoded_scan_is_all_zero_and_non_vacuous",
        why="🔴 第二族：注入 `` `row-${idx}` `` ⇒ `positional_row_id_template` 从 0 变 1。"
            "两族各注一次，才能证明不是只有一条正则活着。",
        scope_check=source_has_line("const _mut2 = `row-${idx}`"),
    ),
    Mutation(
        id="M30", side="be", path=ADJV2_N4, kind="replace",
        anchor="const ROWS_KEY = 'N4-1-rows-v2'",
        new="const ROWS_KEY = 'N4-1-rows'",
        want=f"{_TK}::test_the_fabricated_v2_key_only_lives_in_the_orphan_module",
        why="🔴 把 orphan 的伪造键改成与生产同名 ⇒ 「该键只在 orphan 自己里命中」这条打红。"
            "这是 J 的 TK-6 同型陷阱在 N 上的判据：接错模块时契约会按从未存在的键形态生成。",
        scope_check=source_has_line("const ROWS_KEY = 'N4-1-rows'"),
    ),
    Mutation(
        id="M31", side="be", path=CROSS_N5, kind="replace",
        anchor="    _persistCrossData('N5-cross-n1-change', _n1Change.value)",
        new="    _persistCrossData('N1-cross-n1-change', _n1Change.value)",
        line=175,
        want=f"{_TK}::test_n5_foreign_namespace_reads_are_read_only",
        why="🔴 让 N5 **写**进 N1 的命名空间 ⇒ 「读是只读、写只写自己」这条打红。"
            "Property 70 在 N 上的新增判据（只验「读不算污染」是半个判据）。",
        scope_check=source_has_line("_persistCrossData('N1-cross-n1-change', _n1Change.value)"),
    ),

    # ── H 组：deletion plan 与范式（数据侧）─────────────────────────────
    Mutation(
        id="M32", side="be", path=PLAN, kind="replace",
        anchor='   "switch_verdict": "inert",',
        new='   "switch_verdict": "redeemable",',
        line=486,
        want=f"{_DEL}::test_plan_entries_mirror_the_slice_adjudication",
        why="plan 与 slice 的开关结论脱节 ⇒ 两份产物必须同口径。",
        scope_check=lambda data: [
            e["switch_verdict"] for e in _doc(data)["entries"]].count("inert") == 1,
    ),
    Mutation(
        id="M33", side="be", path=PLAN, kind="replace",
        anchor='   "modules_to_delete": 8,',
        new='   "modules_to_delete": 3,',
        want=f"{_DEL}::test_plan_counters_recompute",
        why="🔴 ND-5：把 orphan 数报成「只有 3 个 dual-mode 孪生」⇒ 与清单条数（8）不符。"
            "这条抓的正是「只扫 use N*DualMode.ts」那条捷径。",
        scope_check=doc_path_is(("orphan_to_delete", "counters", "modules_to_delete"), 3),
    ),
    Mutation(
        id="M34", side="be", path=PLAN, kind="replace",
        anchor='  "can_delete_before_step_9": false,',
        scope=' "live_dual_mode_to_rewire_then_delete": {', offset=3,
        new='  "can_delete_before_step_9": true,',
        want=f"{_DEL}::test_plan_orphans_can_be_deleted_before_step_9_but_live_cannot",
        why="把 live 载体标成可先删 ⇒ 删了宿主就引用未定义变量（运行期白屏）。"
            "删除时机是三类划分的实质，不能混。",
        scope_check=doc_path_is(
            ("live_dual_mode_to_rewire_then_delete", "can_delete_before_step_9"), True),
    ),
    Mutation(
        id="M35", side="be", path=SLICE, kind="replace",
        anchor='    "transport_key_resolution",',
        new='    "transport_key_resolution_TYPO",',
        want=f"{_PARA}::test_new_sections_are_declared_as_non_conflicting",
        why="追加节登记与实际顶层键不再精确等值（declared == extra）。"
            "只验「登记的都存在」不验「存在的都登记」是半个判据。",
        scope_check=lambda data: (
            "transport_key_resolution_TYPO"
            in _doc(data)["paradigm_schema_conflict"]["new_section_not_in_schema"]["sections"]),
    ),
    Mutation(
        id="M36", side="be", path=SLICE, kind="replace",
        anchor='     "kind": "generated_opaque_persisted",',
        new='     "kind": "array_index",',
        line=2173,
        want=f"{_P23}::test_every_table_verdict_follows_from_its_kind",
        wants=(f"{_CONTRACT}::test_every_scanned_slice_passes_the_schema",
               f"{_COVERAGE}::test_every_slice_passes_the_json_nominated_validator"),
        why="🔴 把干净表的 kind 改成禁用字面值 ⇒ 范式校验器拒收 + 本轮的蕴含判据打红。"
            "同时证明 CLEAN 的两张反向分母不是装饰。",
        scope_check=lambda data: any(
            t["row_identity"]["kind"] == "array_index"
            for t in _doc(data)["dynamic_row_identity"]["tables"]),
    ),
    Mutation(
        id="M37", side="be", path=SLICE, kind="replace",
        anchor='     "identity_field": "rowKey",',
        new='     "identity_field": "id",',
        want=f"{_P23}::test_clean_tables_really_address_rows_by_stable_id",
        why="🔴 N4-2 的身份字段实为 `rowKey`（N3-2 才是 `id`）。写死成 `id` ⇒ 现读那一行找不到"
            "`id:` ⇒ 打红。这条抓的是「字段名照抄另一张表」这类同源错。",
        scope_check=lambda data: any(
            t["row_identity"].get("identity_field") == "id"
            and t["table_key"] == "n4_detail_rows"
            for t in _doc(data)["dynamic_row_identity"]["tables"]),
    ),
    Mutation(
        id="M38", side="be", path=SLICE, kind="replace",
        anchor='      "normalized": "应交税费审计程序表O1A （原底稿）",',
        new='      "normalized": "O1A",',
        want=f"{_SHEET}::test_the_python_port_matches_the_declared_normalization",
        why="🔴 `O1A` **不在** N2 的 codeRe 里（N4 的 O2A 在）⇒ 归一键是 sheet 全名。"
            "按「原底稿都归一成码」照抄 N4 的写法必红。这条证明 Python 端口在真跑共享 router。",
        scope_check=lambda data: any(
            r["normalized"] == "O1A"
            for e in _doc(data)["independent_entries"]
            for r in e["sheet_granularity"]["per_sheet"]),
    ),
    Mutation(
        id="M39", side="be", path=SLICE, kind="replace",
        anchor='      "renderer": "n1/core/N1TabIndex.vue",',
        new='      "renderer": "N1TabIndex.vue",',
        want=f"{_SHEET}::test_classification_is_a_closed_enum_and_renderers_exist",
        why="渲染器路径写成裸文件名 ⇒ 该文件在 `components/workpaper/` 根下不存在。"
            "只验「声明了一个渲染器」不落到磁盘，这条会 GREEN。",
        scope_check=lambda data: any(
            r["renderer"] == "N1TabIndex.vue"
            for e in _doc(data)["independent_entries"]
            for r in e["sheet_granularity"]["per_sheet"]),
    ),
    Mutation(
        id="M40", side="be", path=SLICE, kind="replace",
        anchor='   "statement_production_consumers": 26,',
        new='   "statement_production_consumers": 29,',
        want=f"{_ORPHAN}::test_shared_base_edges_recompute_and_are_not_copied_from_m",
        why="🔴 抄 M 那轮的 29 ⇒ 与本轮现算 26 不符。交付要求点名「边数两侧都验」，"
            "且共享基类边集在两轮间已漂移。",
        scope_check=doc_path_is(
            ("orphan_dual_mode_inventory", "shared_base_preserved",
             "statement_production_consumers"), 29),
    ),
    Mutation(
        id="M41", side="be", path=SLICE, kind="replace",
        anchor='    "array_addressing_sites": 48,',
        new='    "array_addressing_sites": 47,',
        want=f"{_P23}::test_array_addressing_family_counts_recompute",
        why="N 的系统性形态（48 处按数组位置寻址）改 1 ⇒ 五条正则现算之和不符。",
        scope_check=doc_path_is(
            ("dynamic_row_identity", "positional_identity_inventory", "counters",
             "array_addressing_sites"), 47),
    ),
    Mutation(
        id="M42", side="be", path=SLICE, kind="replace",
        anchor='    "update_by_row_index": 9,',
        new='    "update_by_row_index": 10,',
        want=f"{_P23}::test_array_addressing_family_counts_recompute",
        why="逐族计数也要等值 —— 只验总和会让「一族多 1、另一族少 1」通过。",
        scope_check=doc_path_is(
            ("dynamic_row_identity", "positional_identity_inventory",
             "array_addressing_family_counts", "update_by_row_index"), 10),
    ),
    Mutation(
        id="M43", side="be", path=SLICE, kind="replace",
        anchor='     "N1-1-adj-0",',
        new='     "N1-1-adj-7",',
        want=f"{_TK}::test_runtime_derived_keys_expand_from_the_impl",
        why="🔴 展开值与 impl 的类别数组（现算 7 项、0..6）不再对齐。"
            "这条证明「模板形态键」的判据是从 impl 现算展开的，不是抄一串字面量。",
        scope_check=lambda data: any(
            "N1-1-adj-7" in (d.get("key_expansion") or [])
            for d in _doc(data)["transport_key_resolution"]["declarations"]),
    ),
    Mutation(
        id="M44", side="be", path=SLICE, kind="replace",
        anchor='   "N1-1-rows",',
        new='   "N1-1-total-audited",',
        want=f"{_TK}::test_declared_keys_all_exist_in_production_source",
        why="🔴 把一个**真实存在**的键放进「按规律猜、实际不存在」的反向清单 ⇒ 反向分母失效。"
            "这条守的是「0 命中」那一侧不许注水。",
        scope_check=lambda data: (
            "N1-1-total-audited"
            in _doc(data)["transport_key_resolution"]["nonexistent_guessed_keys"]),
    ),
]

GUARD_FILES = {
    T56: "Task 56 新建（N 循环 Property 3/23/69/70）",
    _CONTRACT: "范式校验器（本轮只读，被 M14/M36 顺带打红）",
    _COVERAGE: "slice_schema 覆盖面（_UNJUDGED_SLICES 必须保持为空）",
}

BACKEND_ARGS = [
    "backend/tests/workpaper_sync/test_task56_n_cycle_migration.py",
    "backend/tests/workpaper_sync/test_migration_paradigm_contract.py",
    "backend/tests/workpaper_sync/test_slice_schema_validator_coverage.py",
    "-q", "--tb=no", "-rf", "-p", "no:randomly",
]

if __name__ == "__main__":
    raise SystemExit(run_cli(
        mutations=MUTATIONS,
        guard_files=GUARD_FILES,
        repo=REPO,
        description="Task 56 守卫变异检验（N 循环）",
        backend_args=BACKEND_ARGS,
        baseline_backend_passed=346,
    ))
