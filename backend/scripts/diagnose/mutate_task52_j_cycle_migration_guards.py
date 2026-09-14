# -*- coding: utf-8 -*-
r"""Task 52 守卫变异检验 —— J 循环 Excel 独立 entry 迁移。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 5 Task 52

用平台共享件 `backend/scripts/_mutation_kit`（`test_mutation_kit_adoption.py` 对新脚本强制
采纳：共享件的 `run_cli` 把 `guard_files`（覆盖面分母）做成签名层面必填，把「锚点含换行」
「new == anchor」「id 重复」「want 定位不到」全部拦在声明期）。

═══ 本脚本的四条硬约束 ═══

1. **每条变异都带 `scope_check`**。四态判定式「新增失败集合是否为空」识别不出「锚点落在被测
   判据的作用域之外」—— 改到了别处会被判 GREEN（守卫缺陷），而真相是脚本缺陷。数据文件的
   回调解析 JSON 后断言目标字段真的变成了期望值；源码文件的回调断言改动确实落在那段文本上。

2. **重复形态字段用 `scope` + `offset` 相对定位，绝不用绝对行号**。本 slice 只有 1 条 entry，
   所以 entry 级字段（`"capability": null,` / `"adapter_id": null,` / `"html_counterpart_verdict"`）
   在文件里 dup=1、可直接整行锚定；真正重复的是**逐条 declaration 的同名字段**：
   `"verdict":` 4 次、`"belongs_to_entry": null,` 2 次、`"count": 3,` 2 次、
   `"orphan_order":` 各 2 次、`"orphan_carrier_verdict":` 2 次、`"inbound_edges": 0,` 2 次。
   这些一律 `scope`（该块唯一的 `"id"` / `"name"` / `"file"` 行）+ `offset`（由
   `tmp_task52_offsets.py` 一次性诊断实算，非估计值）。

3. **变异按「可区分的错法」枚举而不是逐条目复制**。J slice 只有 1 条 entry，但有 4 条
   row-model declaration、7 条 transport-key declaration、4 个 orphan module —— 逐条各写一次
   是同信息量的重复。这里按错法分组，并**分布在不同条目上**，从而同时把各组 offset 走通。

4. **必须含反向变异**。只验「新增缺陷」一个方向的穷举判据是半个判据：缺陷被修好而登记没删，
   报告会长期挂着一条已解决的债。本脚本的反向变异：
   * M31 把 BP-8 的行标签缺陷**修一半**（给 `其中：1.基本养老保险` 补上「费」）；
   * M32 把 RD-4 的**正例**改坏（把 J1-6 那份带「费」的标签去掉「费」）——
     两个方向都必须打红，否则「缺陷定位在哪一侧」这条结论是空的；
   * M33 把 family_a 的纯序号身份改成稳定身份（命中数 1 → 0）；
   * M40 在宿主里真挂上 AC 1.4 的 notice 组件（BP-10 可解除）；
   * M41 给 el-segmented 真加上二级门控（BP-10 一半兑现）；
   * M43 删掉 `useJ3DualMode` 的 legacy 端点直调（BP-6 的一条依据消失）。

═══ 为什么要对**真源码常量**做变异（M28~M35 / M40~M45）═══

数据侧变异只能证明「守卫读了 slice」；只有改真源码还打红，才能证明 impl 侧是**现读**而不是
抄了一份快照。J 循环的三边锁里第③边（impl 现读）与「消费边可达性」「client 取得形态」
「位置化身份穷举」四类判据都必须有源码变异撑着。

用法（仓库根；本仓库 PATH 上的 `python` 指向坏掉的 `.venv_depprobe`，必须用显式解释器）::

    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task52_j_cycle_migration_guards.py --list
    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task52_j_cycle_migration_guards.py --check-anchors
    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task52_j_cycle_migration_guards.py --run M01,M02,M03

🔴 **禁止后台执行**：外层 shell 被杀会让 python 变成孤儿进程，与前台运行同时变异同一文件 ⇒
`RestoreFailed` rc=5。分批跑用 `--run M01,M02,...`（子集运行不做覆盖面结论，见 kit 的
`CoverageTally.report`）。

🔴 **`delete` 不要用在数组末元素上**：删掉末元素会给前一行留下尾逗号、JSON 失效，
`scope_check` 的 `json.loads` 抛异常 ⇒ 判定 ERROR（脚本缺陷，不是守卫缺陷）。一律用 `replace`。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

# ── 被变异的对象 ───────────────────────────────────────────────────────────
SLICE = "backend/data/workpaper_sync_j_cycle_manifest_slice.json"
PLAN = "backend/data/workpaper_sync_j_cycle_deletion_plan.json"
FE = "audit-platform/frontend/src"
WP = f"{FE}/components/workpaper"
COMP = f"{WP}/composables"
CB = f"{FE}/composables/workpaper"
HOST_J1 = f"{WP}/j1/GtJ1EmployeeCompensation.vue"
J1_DETAIL_TS = f"{CB}/j1/useJ1Detail.ts"
J1_ADJ_TS = f"{CB}/j1/useJ1Adjudication.ts"
J1_ACCRUAL_VUE = f"{WP}/j1/inspection/J1TabAccrualCheck.vue"
J1_ADJUSTMENT_VUE = f"{WP}/j1/core/J1TabAdjustment.vue"
J1_INDEX_VUE = f"{WP}/j1/core/J1TabIndex.vue"
J2_ADJUSTMENT_VUE = f"{WP}/j2/J2TabAdjustment.vue"
J2_ENTRY_DUAL_TS = f"{COMP}/useJ2EntryDualMode.ts"
J3_DUAL_TS = f"{CB}/j3/useJ3DualMode.ts"

# ── 期望打红的守卫（文件::类::方法，与 pytest 的 short nodeid 同形）─────────
T52 = "test_task52_j_cycle_migration.py"
_SELF = f"{T52}::TestGuardSelfChecks"
_SCOPE = f"{T52}::TestSliceScopeIsRecomputable"
_ADJ = f"{T52}::TestAdjudicationLegality"
_HTML = f"{T52}::TestHtmlCounterpartIsSourceBacked"
_ORPHAN = f"{T52}::TestOrphanDualModeInventory"
_TK = f"{T52}::TestTransportKeyResolution"
_RD = f"{T52}::TestRowModelDerivation"
_P22 = f"{T52}::TestProperty22And23StaticStructure"
_P3 = f"{T52}::TestProperty3And20"
_P28 = f"{T52}::TestProperty28DefinitionDriftFailClosed"
_P69 = f"{T52}::TestProperty69EvidenceAndCounters"
_P70 = f"{T52}::TestProperty70CrossEntryIsolation"
_AC14 = f"{T52}::TestAc14HonestModeVisibility"
_DEL = f"{T52}::TestDeletionPlanConsistency"
_PARA = f"{T52}::TestParadigmCompliance"


def RD(n: int) -> str:
    return '        "id": "RD-%d",' % n


def TK(n: int) -> str:
    return '        "id": "TK-%d",' % n


def OD(n: int) -> str:
    return '        "id": "OD-%d",' % n


def TPL(name: str) -> str:
    return '        "name": "%s",' % name


def BARREL(cycle: str) -> str:
    return '        "file": "%s/%s/index.ts",' % (CB, cycle)


#: 逐块字段 offset（由 `tmp_task52_offsets.py` 一次性诊断实算，非估计值）。
OFF_RD_VERDICT = {1: 67, 2: 43, 3: 25, 4: 41}
OFF_RD_CELLS = {1: 14, 2: 14, 3: 14}
OFF_RD_EXPECTED_FIRST = {1: 24, 2: 24}
OFF_RD_IMPL_FIRST = {1: 45 + 1, 2: 33 + 1}   # `"impl_labels": [` 行 + 1 = 首个标签
OFF_TK_STATUS = {1: 39, 3: 31, 6: 54, 7: 38}
OFF_TK_ORPHAN_VERDICT = {6: 51, 7: 35}
OFF_OD_LINES = 2
OFF_OD_ORDER = 3
OFF_OD_PRODUCTION = 6
OFF_OD_BARREL_EDGES = {2: 37, 3: 13, 4: 11}
OFF_OD_SHEET_MAP_COUNT = 13
OFF_TPL_SHA = 2
OFF_TPL_OWNER = 3
OFF_TPL_SHEETS = {"J1": 4, "J2": 5, "J3": 5}
OFF_TPL_RETIRED = {"J1": 10, "J2": 10, "J3": 11}
OFF_PLAN_OD_LINES = 3
OFF_PLAN_BARREL_EDGES = 2

TPL_J1 = "J1 应付职工薪酬.xlsx"
TPL_J2 = "J2 长期应付职工薪酬-设定受益计划净资产.xlsx"
TPL_J3 = "J3 股份支付.xlsx"


# ═══════════════════════════════════════════════════════════════════════════
# 作用域自证回调（每条变异必带）
#
# 🔴 为什么每条都要带：共享件的四态判定只看「新增失败集合」，锚点若命中了同名的文档说明 /
# 注释 / 另一个结构，判定会报 GREEN（守卫缺陷），而真相是脚本缺陷。回调在变异写盘后立刻
# 解析 JSON（或读文本）并断言目标**真的**变成了期望值 —— 不成立即判 ANCHOR-MISS。
# ═══════════════════════════════════════════════════════════════════════════
def _json_at(expected, *path):
    """JSON 里 `path`（dict 键 / list 下标混用）指向的节点必须**恰好**等于期望值。"""

    def check(data: bytes) -> bool:
        node = json.loads(data.decode("utf-8"))
        for key in path:
            try:
                node = node[key]
            except (KeyError, IndexError, TypeError):
                return False
        return node == expected

    return check


def _entry_field(*path):
    """slice / plan 里唯一那条 entry 的嵌套字段必须恰好等于期望值（`path` 末位是期望值）。"""
    expected = path[-1]
    keys = path[:-1]
    entry_id = "xlsx/j1/gt-j1-employee-compensation"

    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        rows = payload.get("independent_entries") or payload.get("entries") or []
        for entry in rows:
            if entry.get("entry_id") != entry_id:
                continue
            node = entry
            for key in keys:
                try:
                    node = node[key]
                except (KeyError, IndexError, TypeError):
                    return False
            return node == expected
        return False

    return check


def _by_id(section: str, item_id: str, *path):
    """slice 里某个带 `id` 的条目（RD-N / TK-N / OD-N / BP-N）的字段必须等于期望值。

    按 `id` 找而不是按下标 —— 增删条目时下标会静默指向别人。
    """
    expected = path[-1]
    keys = path[:-1]

    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        node_list = payload
        for part in section.split("."):
            node_list = node_list[part]
        for item in node_list:
            if item.get("id") != item_id:
                continue
            node = item
            for key in keys:
                try:
                    node = node[key]
                except (KeyError, IndexError, TypeError):
                    return False
            return node == expected
        return False

    return check


def _template_field(name: str, key: str, expected):
    """authoritative_templates.files 里某本工作簿的某个字段必须等于期望值。"""

    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        for record in payload["authoritative_templates"]["files"]:
            if record["name"] == name:
                return record.get(key) == expected
        return False

    return check


def _plan_module_field(module_id: str, key: str, expected):
    """deletion plan 的 orphan_dual_mode_to_delete.modules 里某条的字段。"""

    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        for module in payload["orphan_dual_mode_to_delete"]["modules"]:
            if module.get("id") == module_id:
                return module.get(key) == expected
        return False

    return check


def _plan_barrel_field(file_rel: str, key: str, expected):
    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        for barrel in payload["orphan_dual_mode_to_delete"]["orphan_barrels"]:
            if barrel.get("file") == file_rel:
                return barrel.get(key) == expected
        return False

    return check


def _text_contains(needle: str, *, absent: bool = False):
    """源码类（.ts/.vue）变异的作用域自证：变异后必须（或必须不）含该串。

    🔴 源码侧没有 JSON 结构可解析，但仍然需要自证 —— 否则「锚点命中了注释里的同名行」
    这类脚本缺陷会被判成 GREEN。
    """

    def check(data: bytes) -> bool:
        text = data.decode("utf-8", errors="replace")
        return (needle not in text) if absent else (needle in text)

    return check


def _text_gone_and_new(gone: str, new: str):
    """旧串必须消失且新串必须出现（反向变异「把缺陷修一半」的自证）。"""

    def check(data: bytes) -> bool:
        text = data.decode("utf-8", errors="replace")
        return gone not in text and new in text

    return check


MUTATIONS: list[Mutation] = [
    # ═══════════════════════════════════════════════════════════════════════
    # ① AC 1.3 / 12.1 / 12.8 / 12.9：capability 裁决（按错法枚举）
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M01", side="be", path=SLICE, kind="replace",
        anchor='      "capability": null,',
        new='      "capability": "bidirectional",',
        want=f"{_ADJ}::test_capability_matches_honest_capability",
        wants=(
            f"{_P69}::test_summary_counters_recompute_from_the_entries",
            f"{_DEL}::test_plan_entries_mirror_the_slice_adjudication",
            f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",
            f"{_P3}::test_no_entry_claims_bidirectional",
        ),
        why="把终态未定改成 bidirectional 而五个身份字段仍为 null 仍绿 ⇒ AC 12.1 的 SR-6 与 "
            "SR-4 双口径判据都是死的，而这正是「假双向」最直接的入口（Property 3 的正向门）",
        scope_check=_entry_field("capability", "bidirectional"),
        tags=("adjudication", "property-3", "data"),
    ),
    Mutation(
        id="M02", side="be", path=SLICE, kind="replace",
        anchor='      "capability": null,',
        new='      "capability": "single_onlyoffice",',
        want=f"{_ADJ}::test_single_onlyoffice_requires_no_html_counterpart",
        wants=(
            f"{_ADJ}::test_capability_matches_honest_capability",
            f"{_ADJ}::test_ac15_is_declared_not_applicable_with_a_reason",
            f"{_P69}::test_summary_counters_recompute_from_the_entries",
        ),
        why="html_counterpart_verdict == exists 却裁 single_onlyoffice 仍绿 ⇒ AC 12.8 的唯一"
            "合法判据（无 HTML 对端）没被执行；同时它必须触发 AC 1.5 适用性重判"
            "（本 slice 声明 AC 1.5 不适用的前提正是「无 single_* 裁决」）",
        scope_check=_entry_field("capability", "single_onlyoffice"),
        tags=("adjudication", "ac-1.5", "data"),
    ),
    Mutation(
        id="M03", side="be", path=SLICE, kind="replace",
        anchor='      "capability": null,',
        new='      "capability": "dual",',
        want=f"{_ADJ}::test_capability_is_enum_or_explicitly_pending",
        wants=(f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",),
        why="自造能力态 `dual` 仍绿 ⇒ AC 1.3 明禁的「含糊 dual 布尔」判据是死的",
        scope_check=_entry_field("capability", "dual"),
        tags=("adjudication", "data"),
    ),
    Mutation(
        id="M04", side="be", path=SLICE, kind="replace",
        anchor='      "capability_verdict_stage": "pipeline_entry_pending_definition_delivery",',
        new='      "capability_verdict_stage": "",',
        want=f"{_ADJ}::test_capability_is_enum_or_explicitly_pending",
        wants=(
            f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",
            f"{_DEL}::test_plan_entries_mirror_the_slice_adjudication",
        ),
        why="待裁决三字段之一变空串仍绿 ⇒ SR-3 右支退化成「留空即可」，未裁决就能伪装成已裁决",
        scope_check=_entry_field("capability_verdict_stage", ""),
        tags=("adjudication", "data"),
    ),
    Mutation(
        id="M05", side="be", path=SLICE, kind="replace",
        anchor='      "capability_target": "bidirectional",',
        new='      "capability_target": "maybe_someday",',
        want=f"{_ADJ}::test_capability_is_enum_or_explicitly_pending",
        wants=(
            f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",
            f"{_DEL}::test_plan_entries_mirror_the_slice_adjudication",
        ),
        why="capability_target 落在枚举外仍绿 ⇒「不知道往哪走」被当成待裁决，"
            "而范式明写那不是待裁决、是没调查",
        scope_check=_entry_field("capability_target", "maybe_someday"),
        tags=("adjudication", "data"),
    ),
    Mutation(
        id="M06", side="be", path=SLICE, kind="replace",
        anchor='      "adapter_id": null,',
        new='      "adapter_id": "j1.employee_compensation",',
        want=f"{_ADJ}::test_pending_entries_carry_no_identity",
        wants=(
            f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",
            f"{_P3}::test_no_slice_entry_has_a_registered_adapter",
        ),
        why="未裁决 entry 挂上 adapter_id 仍绿 ⇒ AP-5（裁 single/未裁决不得挂身份）与"
            "Property 3 的「未注册 adapter」前提判据都是死的",
        scope_check=_entry_field("adapter_id", "j1.employee_compensation"),
        tags=("adjudication", "property-3", "data"),
    ),
    Mutation(
        id="M07", side="be", path=SLICE, kind="replace",
        anchor='      "html_counterpart_verdict": "exists",',
        new='      "html_counterpart_verdict": "unresolved",',
        want=f"{_ADJ}::test_every_entry_has_a_binary_html_counterpart_verdict",
        wants=(
            f"{_P69}::test_summary_counters_recompute_from_the_entries",
            f"{_DEL}::test_plan_entries_mirror_the_slice_adjudication",
        ),
        why="verdict 写成 unresolved 仍绿 ⇒ AP-3（「还没查」不是结论）判据是死的",
        scope_check=_entry_field("html_counterpart_verdict", "unresolved"),
        tags=("adjudication", "data"),
    ),
    Mutation(
        id="M08", side="be", path=SLICE, kind="replace",
        anchor='        "BP-11"',
        new='        "BP-99"',
        want=f"{_ADJ}::test_capability_blockers_reference_real_preconditions",
        wants=(f"{_ADJ}::test_every_blocking_precondition_is_referenced_by_someone",),
        why="blockers 指向不存在的 BP-99 仍绿 ⇒「阻断项必须真存在」判据是死的，于是可以用任意"
            "编号冒充「已登记」；同时 BP-11 变成悬挂声明，反向那条也必须红",
        scope_check=_entry_field(
            "capability_target_blocked_by",
            ["BP-1", "BP-2", "BP-3", "BP-4", "BP-5", "BP-8", "BP-9", "BP-10", "BP-99"],
        ),
        tags=("adjudication", "data"),
    ),
    Mutation(
        id="M09", side="be", path=SLICE, kind="replace",
        anchor='        "capability": "single_onlyoffice",',
        new='        "capability": null,',
        want=f"{_ADJ}::test_manifest_mirror_divergence_is_registered_not_silently_equal",
        why="🔴 manifest overlay 陷阱：把 manifest_mirror 改成与 slice 相等（都是 null）仍绿 ⇒ "
            "判据写成了「断言相等」而不是「断言必须不相等且已登记为 BP-9」，"
            "于是「slice 抄了 manifest 的错值」这条最容易犯的错查不出来",
        scope_check=_entry_field("manifest_mirror", "capability", None),
        tags=("adjudication", "manifest-overlay", "data"),
    ),
    Mutation(
        id="M10", side="be", path=SLICE, kind="replace",
        anchor='        "verification_state": "UNVERIFIABLE",',
        new='        "verification_state": "VERIFIED",',
        want=f"{_P69}::test_unverifiable_entries_carry_non_empty_reasons",
        wants=(f"{_P69}::test_summary_counters_recompute_from_the_entries",),
        why="声称 VERIFIED 而 sync_test_run_id / required_scenario_set_digest 仍为 null 仍绿 ⇒ "
            "「声称已验收必须有 run id + digest」这条蕴含关系是死的 ⇒ 可以空口宣称验收",
        scope_check=_entry_field("evidence", "verification_state", "VERIFIED"),
        tags=("property-69", "data"),
    ),
    Mutation(
        id="M11", side="be", path=SLICE, kind="replace",
        anchor='    "total_independent": 1,',
        new='    "total_independent": 2,',
        want=f"{_P69}::test_summary_counters_recompute_from_the_entries",
        wants=(f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",),
        why="SR-1 的核心计数被篡改仍绿 ⇒ 摘要与明细脱节，「已迁移 N 条」可以凭空写大",
        scope_check=_json_at(2, "honest_adjudication_summary", "total_independent"),
        tags=("property-69", "counters", "data"),
    ),
    Mutation(
        id="M12", side="be", path=SLICE, kind="replace",
        anchor='      "unadjudicated": 1,',
        new='      "unadjudicated": 0,',
        want=f"{_P69}::test_slice_counters_are_all_zero_except_unadjudicated",
        wants=(
            f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",
            f"{_PARA}::test_the_validator_really_catches_a_counter_mismatch",
        ),
        why="把待裁决计数归零（=「全绿冒充进度」的经典形态）仍绿 ⇒ SR-9 是死的，"
            "SR-3 右支就成了后门：全记待裁决同时报 0",
        scope_check=_json_at(0, "honest_adjudication_summary", "slice_counters", "unadjudicated"),
        tags=("property-69", "counters", "data"),
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # ② JD-1..JD-6：J 循环的六处形态差异（照抄前六轮就会假红/假绿的地方）
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M13", side="be", path=SLICE, kind="replace",
        scope='          "%s/j2/GtJ2DefinedBenefitPlan.vue": {' % WP, offset=3,
        anchor='            "has_oo_mount": false,',
        new='            "has_oo_mount": true,',
        want=f"{_SCOPE}::test_j2_and_j3_hosts_are_really_absent_from_the_manifest",
        wants=(f"{_P69}::test_derived_counters_recompute_from_their_own_sections",),
        why="🔴 JD-1：把 J2 宿主声明成「有 OO 挂载点」仍绿 ⇒「3 个宿主只有 1 个有挂载点」这条"
            "决定 entry 数的实况没有回源核对，于是「补两条手写 entry」的错误修法查不出来。"
            "锚点取两处 false 的第一处（J2），第二处（J3）由同一判据覆盖",
        scope_check=lambda data: json.loads(data.decode("utf-8"))["j_cycle_form_differences"][
            "differences"
        ][0]["hosts"][f"{WP}/j2/GtJ2DefinedBenefitPlan.vue"]["has_oo_mount"] is True,
        tags=("form-difference", "data"),
    ),
    Mutation(
        id="M14", side="be", path=SLICE, kind="replace",
        anchor='        "write_carrier": "shared_platform_persistence_adapter",',
        new='        "write_carrier": "host_inline",',
        want=f"{_HTML}::test_host_really_has_no_direct_http_client_import",
        why="🔴 JD-3：把写载体族改标成 H/I 循环的 host_inline 仍绿 ⇒ 载体族判据没有回源核对，"
            "而 J1 宿主的 script 里根本没有 `@/utils/http`（照 I 的口径去核会假红，"
            "照本 slice 的声明去核才对）",
        scope_check=_entry_field("html_counterpart", "write_carrier", "host_inline"),
        tags=("form-difference", "html-counterpart", "data"),
    ),
    Mutation(
        id="M15", side="be", path=SLICE, kind="replace",
        anchor='        "write_client": "api",',
        new='        "write_client": "http",',
        want=f"{_HTML}::test_write_carrier_client_and_put_site_agree_with_the_source",
        why="🔴 把 client 名从 `api` 改成 `http` 仍绿 ⇒ 判据写死了 `http.put` 而不是按声明的"
            "client 名去找（`useChecklistPersistence` 用的是 `api.put`，H 的口径在此假红）",
        scope_check=_entry_field("html_counterpart", "write_client", "http"),
        tags=("form-difference", "html-counterpart", "data"),
    ),
    Mutation(
        id="M16", side="be", path=SLICE, kind="replace",
        anchor='          "static_import_file_count": 4,',
        new='          "static_import_file_count": 5,',
        want=f"{_HTML}::test_second_write_path_sites_are_all_real",
        why="🔴 client 取得形态的两族计数被篡改仍绿 ⇒「4 静态 / 3 动态」是抄的而不是现扫的，"
            "而首轮正是因为把「文件里必须有 `from '@/utils/http'`」写死，对 3 个用动态 "
            "`(await import('@/utils/http')).default` 的 Tab 假红",
        scope_check=lambda data: json.loads(data.decode("utf-8"))["independent_entries"][0][
            "html_counterpart"
        ]  # noqa: E501 —— 该字段在 JD-3 里，下面用 differences 现取
        is not None
        and json.loads(data.decode("utf-8"))["j_cycle_form_differences"]["differences"][2][
            "second_write_path_client_forms"
        ]["static_import_file_count"] == 5,
        tags=("form-difference", "counters", "data"),
    ),
    Mutation(
        id="M17", side="be", path=SLICE, kind="replace",
        anchor='        "second_write_path_file_count": 7,',
        new='        "second_write_path_file_count": 8,',
        want=f"{_HTML}::test_second_write_path_sites_are_all_real",
        wants=(f"{_P69}::test_derived_counters_recompute_from_their_own_sections",),
        why="把文件数改成站点数（7 → 8）仍绿 ⇒ 两个数没有分别现算，「7 还是 8」说不清，"
            "而 J1TabAdjustment.vue 有两处站点正是这个区别的来源",
        scope_check=lambda data: json.loads(data.decode("utf-8"))["j_cycle_form_differences"][
            "differences"
        ][2]["second_write_path_file_count"] == 8,
        tags=("form-difference", "counters", "data"),
    ),
    Mutation(
        id="M18", side="be", path=SLICE, kind="replace",
        anchor='            "J1-2-detail-shortTerm",',
        new='            "J1-2-rows",',
        want=f"{_HTML}::test_primary_table_owner_constant_is_real",
        wants=(
            f"{_TK}::test_every_declared_key_appears_at_least_once_in_production_source",
            f"{_TK}::test_guessed_keys_have_zero_hits",
            f"{_HTML}::test_second_declaration_of_the_transport_keys_is_consistent",
        ),
        why="🔴 JD-4：把主表键之一改成「按命名规律该有」的 `J1-2-rows` 仍绿 ⇒ 键不是从 owner "
            "常量 + section 派生现算出来的；同时它必须让 nonexistent_guessed_keys 的反向分母"
            "自相矛盾（那 8 个串要求 0 命中，而现在 slice 自己写了一个）",
        scope_check=lambda data: "J1-2-rows"
        in json.loads(data.decode("utf-8"))["independent_entries"][0]["html_counterpart"][
            "primary_table"
        ]["item_id_set"],
        tags=("form-difference", "transport-key", "data"),
    ),
    Mutation(
        id="M19", side="be", path=SLICE, kind="replace",
        anchor='        "row_identity_key": "id",',
        new='        "row_identity_key": "rowId",',
        want=f"{_HTML}::test_row_identity_field_and_generator_are_real",
        why="🔴 JD-4 的另一半：把身份字段改成前六轮通行的 `rowId` 仍绿 ⇒ 判据写死了 rowId，"
            "而 J1-2 的行对象根本没有 rowId 这个键 ⇒ 任何按 rowId 的断言在该表上恒真",
        scope_check=_entry_field("html_counterpart", "row_identity_key", "rowId"),
        tags=("form-difference", "data"),
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # ③ 🔴 orphan 可达性（Task 52 正文第一条前半句）
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M20", side="be", path=SLICE, kind="replace",
        scope=OD(1), offset=OFF_OD_PRODUCTION,
        anchor='        "production_consumers": [],',
        new='        "production_consumers": ["%s/j2/GtJ2DefinedBenefitPlan.vue#L1"],' % WP,
        want=f"{_ORPHAN}::test_declared_orphans_really_have_no_production_reachability",
        wants=(f"{_ORPHAN}::test_first_order_orphans_are_not_reachable_through_any_barrel_either",),
        why="把一阶 orphan 的消费方列表从空改成「宿主」仍绿 ⇒ 孤儿判据只验了一侧"
            "（声称零消费的真零），没验另一侧（声明有消费方就必须真有）",
        scope_check=_by_id(
            "orphan_dual_mode_inventory.modules", "OD-1",
            "production_consumers", [f"{WP}/j2/GtJ2DefinedBenefitPlan.vue#L1"],
        ),
        tags=("orphan", "data"),
    ),
    Mutation(
        id="M21", side="be", path=SLICE, kind="replace",
        scope=OD(1), offset=OFF_OD_ORDER,
        anchor='        "orphan_order": "first_order",',
        new='        "orphan_order": "second_order",',
        want=f"{_ORPHAN}::test_declared_orphans_really_have_no_production_reachability",
        wants=(
            f"{_ORPHAN}::test_orphan_summary_counts_recompute",
            f"{_DEL}::test_plan_orphan_modules_mirror_the_slice_inventory",
        ),
        why="🔴 把一阶 orphan 改标成二阶仍绿 ⇒ 两阶的判据是同一条（都只看「有没有边」），"
            "而二阶 orphan 的整个价值就在于它**有边**（1 条指向孤立 barrel）",
        scope_check=_by_id(
            "orphan_dual_mode_inventory.modules", "OD-1", "orphan_order", "second_order"
        ),
        tags=("orphan", "data"),
    ),
    Mutation(
        id="M22", side="be", path=SLICE, kind="replace",
        scope=OD(3), offset=OFF_OD_BARREL_EDGES[3],
        anchor='        "barrel_inbound_edges": 0,',
        new='        "barrel_inbound_edges": 1,',
        want=f"{_ORPHAN}::test_declared_orphans_really_have_no_production_reachability",
        why="🔴 把 barrel 入边改成 1 仍绿 ⇒ 可达性判定没有顺着 barrel 再问一层，"
            "「入度 > 0 ⇒ 不是孤儿」的朴素判据原地复活（OD-3 的边数本就是 2）",
        scope_check=_by_id(
            "orphan_dual_mode_inventory.modules", "OD-3", "barrel_inbound_edges", 1
        ),
        tags=("orphan", "data"),
    ),
    Mutation(
        id="M23", side="be", path=SLICE, kind="replace",
        anchor='      "statement_position_consumers": 29,',
        new='      "statement_position_consumers": 30,',
        want=f"{_ORPHAN}::test_shared_base_consumer_counts_are_recomputed_both_ways",
        wants=(
            f"{_P69}::test_derived_counters_recompute_from_their_own_sections",
            f"{_DEL}::test_plan_shared_base_numbers_agree_with_the_slice",
        ),
        why="🔴 JD-6：把窄口径消费方数改成宽口径的 30 仍绿 ⇒ 「双引号字符串内的匹配不是 import "
            "边」这条排除条没有生效，共享基类「删完还剩几个」的数就错 1",
        scope_check=_json_at(
            30, "orphan_dual_mode_inventory", "shared_base", "statement_position_consumers"
        ),
        tags=("orphan", "counters", "data"),
    ),
    Mutation(
        id="M24", side="be", path=SLICE, kind="replace",
        anchor='        "wide_scope_consumer_count": 30,',
        new='        "wide_scope_consumer_count": 29,',
        want=f"{_ORPHAN}::test_shared_base_consumer_counts_are_recomputed_both_ways",
        why="把宽口径也改成 29（=两口径相等）仍绿 ⇒ 差集判据的分母消失，"
            "「JD-6 的伪边确实存在」这条反向自检变成重言式",
        scope_check=lambda data: json.loads(data.decode("utf-8"))["j_cycle_form_differences"][
            "differences"
        ][5]["wide_scope_consumer_count"] == 29,
        tags=("orphan", "counters", "data"),
    ),
    Mutation(
        id="M25", side="be", path=SLICE, kind="replace",
        scope=OD(1), offset=OFF_OD_LINES,
        anchor='        "lines": 41,',
        new='        "lines": 42,',
        want=f"{_ORPHAN}::test_declared_orphans_really_have_no_production_reachability",
        wants=(f"{_DEL}::test_plan_orphan_modules_mirror_the_slice_inventory",),
        why="待删对象的行数登记改错仍绿 ⇒ 规模是抄的而不是现算的（I 循环首轮就是把 splitlines "
            "与 split('\\n') 口径搞混，6 条各多算 1 行）",
        scope_check=_by_id("orphan_dual_mode_inventory.modules", "OD-1", "lines", 42),
        tags=("orphan", "data"),
    ),
    Mutation(
        id="M26", side="be", path=SLICE, kind="replace",
        scope=OD(1), offset=OFF_OD_SHEET_MAP_COUNT,
        anchor='        "sheet_map_entry_count": 8,',
        new='        "sheet_map_entry_count": 7,',
        want=f"{_ORPHAN}::test_orphan_sheet_maps_target_sheets_that_do_not_exist",
        why="🔴 sheet 映射表条数改错仍绿 ⇒ 映射表没有被现读（首轮的 `_object_literal_values` "
            "只认标识符键，对 `'底稿目录': 'J2-目录'` 这种带引号键得 0 条，"
            "而「0 条」会被误读成「映射表是空的」）",
        scope_check=_by_id(
            "orphan_dual_mode_inventory.modules", "OD-1", "sheet_map_entry_count", 7
        ),
        tags=("orphan", "data"),
    ),
    Mutation(
        id="M27", side="be", path=SLICE, kind="replace",
        anchor='      "orphan_dual_mode_first_order": 2,',
        new='      "orphan_dual_mode_first_order": 3,',
        want=f"{_ORPHAN}::test_orphan_summary_counts_recompute",
        wants=(f"{_P69}::test_derived_counters_recompute_from_their_own_sections",),
        why="orphan 分阶计数被篡改仍绿 ⇒ 摘要与明细脱节，「4 个孤儿其中 2 个二阶」这条结论"
            "可以凭空写",
        scope_check=_json_at(
            3, "orphan_dual_mode_inventory", "summary", "orphan_dual_mode_first_order"
        ),
        tags=("orphan", "counters", "data"),
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # ④ 🔴 行模型三边锁 —— 三条边 + 合成边各自变异
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M28", side="be", path=SLICE, kind="replace",
        scope=RD(1), offset=OFF_RD_EXPECTED_FIRST[1],
        anchor='          "工资、奖金、津贴和补贴",',
        new='          "工资、奖金、津贴和补贴X",',
        want=f"{_RD}::test_declared_source_cells_read_back_exactly_the_frozen_labels",
        wants=(f"{_RD}::test_verdicts_equal_the_actual_comparison",),
        why="**第②边（源侧基线）**：改 slice 冻结的 expected_source_labels 仍绿 ⇒ 源侧从未被 "
            "openpyxl 现读，「声明」变成了自说自话",
        scope_check=_by_id(
            "row_model_derivation.declarations", "RD-1",
            "expected_source_labels", 0, "工资、奖金、津贴和补贴X",
        ),
        tags=("row-model", "source-ref-lock", "data"),
    ),
    Mutation(
        id="M29", side="be", path=SLICE, kind="replace",
        scope=RD(1), offset=OFF_RD_IMPL_FIRST[1],
        anchor='          "工资、奖金、津贴和补贴",',
        new='          "工资、奖金、津贴和补贴Y",',
        want=f"{_RD}::test_impl_constants_read_back_exactly_the_frozen_labels",
        wants=(f"{_RD}::test_verdicts_equal_the_actual_comparison",),
        why="**第③边（impl 侧现读）**：改 slice 冻结的 impl_labels 仍绿 ⇒ impl 常量从未被现读，"
            "「实现」也变成了自说自话",
        scope_check=_by_id(
            "row_model_derivation.declarations", "RD-1",
            "impl_labels", 0, "工资、奖金、津贴和补贴Y",
        ),
        tags=("row-model", "source-ref-lock", "data"),
    ),
    Mutation(
        id="M30", side="be", path=SLICE, kind="replace",
        scope=RD(2), offset=OFF_RD_CELLS[2],
        anchor='        "cells": "B37:B44",',
        new='        "cells": "B38:B45",',
        want=f"{_RD}::test_declared_source_cells_read_back_exactly_the_frozen_labels",
        wants=(f"{_RD}::test_declared_boundary_cells_read_back_exactly",),
        why="**第①边（声明）**：把区间整体下移一行（仍是 8 格）仍绿 ⇒ 源真读要么没做、要么做成了"
            "「数量对得上就算过」。B45 真读为 None（源模板的预留空行），下移后基线必不等",
        scope_check=_by_id("row_model_derivation.declarations", "RD-2", "cells", "B38:B45"),
        tags=("row-model", "source-ref-lock", "data"),
    ),
    Mutation(
        id="M31", side="be", path=SLICE, kind="replace",
        scope=RD(2), offset=OFF_RD_VERDICT[2],
        anchor='        "verdict": "MISMATCH",',
        new='        "verdict": "MATCH",',
        want=f"{_RD}::test_verdicts_equal_the_actual_comparison",
        wants=(
            f"{_RD}::test_row_model_summary_counts_recompute",
            f"{_RD}::test_defect_declarations_are_registered_as_blocking_preconditions",
        ),
        why="**合成边**：把 BP-8 的 MISMATCH 篡改成 MATCH 仍绿 ⇒ verdict 是自述而不是可复算的，"
            "「声明与实现同错仍自洽」的洞根本没堵上",
        scope_check=_by_id("row_model_derivation.declarations", "RD-2", "verdict", "MATCH"),
        tags=("row-model", "source-ref-lock", "data"),
    ),
    Mutation(
        id="M32", side="be", path=SLICE, kind="replace",
        anchor='          "real_label_difference": 1,',
        new='          "real_label_difference": 0,',
        want=f"{_RD}::test_rd2_diff_kinds_are_split_and_recomputed",
        why="🔴 把「真标签差异 1 处」抹成 0（即把 RD-2 说成纯标点问题）仍绿 ⇒ 两类差异没有分别"
            "现算，于是「改 impl 还是改源模板」这个决定会被误导成「统一标点即可」",
        scope_check=lambda data: json.loads(data.decode("utf-8"))["row_model_derivation"][
            "declarations"
        ][1]["diff_kinds"]["real_label_difference"] == 0,
        tags=("row-model", "source-ref-lock", "data"),
    ),
    Mutation(
        id="M33", side="be", path=SLICE, kind="replace",
        scope=RD(3), offset=24,
        anchor='        "impl_labels": [""],',
        new='        "impl_labels": ["", ""],',
        want=f"{_RD}::test_verdicts_equal_the_actual_comparison",
        wants=(f"{_RD}::test_row_model_summary_counts_recompute",),
        why="否定式声明（RD-3：源模板空白动态区不得被抄成多行占位）被改成 2 行仍绿 ⇒ "
            "「源必须真为空 **且** impl 必须恰 1 行空 label」这条双向断言只剩一半，"
            "而「照源模板补 3 行占位」这个危险动作只有它能拦",
        scope_check=_by_id("row_model_derivation.declarations", "RD-3", "impl_labels", ["", ""]),
        tags=("row-model", "source-ref-lock", "data"),
    ),
    Mutation(
        id="M34", side="be", path=SLICE, kind="replace",
        anchor='            "has_fee_char": false',
        new='            "has_fee_char": true',
        want=f"{_RD}::test_rd4_cross_impl_divergence_locates_the_defect",
        why="🔴 RD-4：把「第一份 impl 不带费」翻成 true 仍绿 ⇒ 跨 impl 比对是自述，"
            "「缺陷精确定位在 useJ1Detail.ts#L87 单一处」这条结论失去依据",
        scope_check=lambda data: json.loads(data.decode("utf-8"))["row_model_derivation"][
            "declarations"
        ][3]["cross_impl_divergence"]["site_a"]["has_fee_char"] is True,
        tags=("row-model", "source-ref-lock", "data"),
    ),
    Mutation(
        id="M35", side="be", path=SLICE, kind="replace",
        anchor='      "clean": 1,',
        new='      "clean": 2,',
        want=f"{_RD}::test_row_model_summary_counts_recompute",
        wants=(f"{_P69}::test_derived_counters_recompute_from_their_own_sections",),
        why="行模型核对的 status 计数被篡改（把一条缺陷记成 clean）仍绿 ⇒ 摘要与明细脱节，"
            "「本 slice 行模型全对」这种结论可以凭空写出来",
        scope_check=_json_at(2, "row_model_derivation", "summary", "clean"),
        tags=("row-model", "counters", "data"),
    ),

    # ── 第③边的**真源码**变异（证明 impl 侧是现读的，不是抄 slice）──────────
    Mutation(
        id="M36", side="be", path=J1_DETAIL_TS, kind="replace",
        anchor="      { seq: '一', label: '工资、奖金、津贴和补贴', indent: 0, isSubItem: false },",
        new="      { seq: '一', label: '工资奖金津贴和补贴', indent: 0, isSubItem: false },",
        want=f"{_RD}::test_impl_constants_read_back_exactly_the_frozen_labels",
        wants=(f"{_RD}::test_verdicts_equal_the_actual_comparison",),
        why="🔴 **真改前端行模型常量**（去掉 RD-1 正例首行标签里的顿号）仍绿 ⇒ impl 侧是抄 slice "
            "而不是现读源码，三边锁只有两边。RD-1 是全 slice 唯一的三向一致正例，"
            "没有正例锚点的穷举判据无法区分「守卫在跑」与「守卫恒返回空」",
        scope_check=_text_gone_and_new(
            "label: '工资、奖金、津贴和补贴'", "label: '工资奖金津贴和补贴'"
        ),
        tags=("row-model", "source-ref-lock", "source"),
    ),
    Mutation(
        id="M37", side="be", path=J1_DETAIL_TS, kind="replace",
        anchor="      { seq: '', label: '其中：1.基本养老保险', indent: 1, isSubItem: true },",
        new="      { seq: '', label: '其中：1.基本养老保险费', indent: 1, isSubItem: true },",
        want=f"{_RD}::test_rd2_diff_kinds_are_split_and_recomputed",
        wants=(
            f"{_RD}::test_impl_constants_read_back_exactly_the_frozen_labels",
            f"{_RD}::test_rd4_cross_impl_divergence_locates_the_defect",
        ),
        why="🔴 **反向变异**：把 BP-8 的行标签缺陷**修一半**（给 `其中：1.基本养老保险` 补上"
            "「费」）而不改登记 ⇒ 真标签差异从 1 降到 0、RD-4 的 site_a 变成带费 ⇒ 判据必须"
            "同样打红。只验「新增缺陷」一个方向的穷举判据是半个判据：缺陷被修好而登记没删，"
            "报告会长期挂着一条已解决的债",
        scope_check=_text_gone_and_new(
            "label: '其中：1.基本养老保险', indent: 1",
            "label: '其中：1.基本养老保险费', indent: 1",
        ),
        tags=("row-model", "source-ref-lock", "reverse", "source"),
    ),
    Mutation(
        id="M38", side="be", path=J1_ACCRUAL_VUE, kind="replace",
        anchor="  { label: '其中：1.基本养老保险费', indent: 1 }, { label: '2.失业保险费', indent: 1 },",
        new="  { label: '其中：1.基本养老保险', indent: 1 }, { label: '2.失业保险费', indent: 1 },",
        want=f"{_RD}::test_rd4_cross_impl_divergence_locates_the_defect",
        why="🔴 **反向变异（另一侧）**：把 RD-4 的**正例**改坏（去掉第二份 impl 那个「费」，"
            "即往错的方向对齐）仍绿 ⇒ 「两份 impl 互不一致、第二份站在源那一侧」这条把"
            "「改哪一边」从判断变成事实的结论是空的",
        scope_check=_text_gone_and_new(
            "{ label: '其中：1.基本养老保险费', indent: 1 }",
            "{ label: '其中：1.基本养老保险', indent: 1 }",
        ),
        tags=("row-model", "source-ref-lock", "reverse", "source"),
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # ⑤ 🔴 真实传输键（Task 52 正文第一条后半句）
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M39", side="be", path=J1_DETAIL_TS, kind="replace",
        anchor="const STORAGE_KEY_PREFIX = 'J1-2-detail-'",
        new="const STORAGE_KEY_PREFIX = 'J1-2-rows-'",
        want=f"{_TK}::test_tk1_prefix_derivation_matches_the_second_literal_declaration",
        wants=(
            f"{_HTML}::test_primary_table_owner_constant_is_real",
            f"{_HTML}::test_second_declaration_of_the_transport_keys_is_consistent",
        ),
        why="🔴 **真改 owner 常量**（写方前缀）仍绿 ⇒ 三个键是抄的而不是现算的；同时这正是 "
            "BP-11 描述的事故：前缀一改而读方 useJ1Adjudication 的三个全字面量不改，"
            "附注侧会静默读空而两侧各自的单测都不会红",
        scope_check=_text_gone_and_new(
            "const STORAGE_KEY_PREFIX = 'J1-2-detail-'", "const STORAGE_KEY_PREFIX = 'J1-2-rows-'"
        ),
        tags=("transport-key", "bp-11", "source"),
    ),
    Mutation(
        id="M40", side="be", path=J1_ADJ_TS, kind="replace",
        anchor="  postEmployment: 'J1-2-detail-postEmployment',",
        new="  postEmployment: 'J1-2-detail-post-employment',",
        want=f"{_TK}::test_tk1_prefix_derivation_matches_the_second_literal_declaration",
        wants=(f"{_HTML}::test_second_declaration_of_the_transport_keys_is_consistent",),
        why="🔴 BP-11 的**另一个方向**：改读方的字面量而不改写方前缀仍绿 ⇒ 两份真源的一致性"
            "判据只验了一侧。注释自称「与 STORAGE_KEY_PREFIX 一致」，本条就是去核那句话",
        scope_check=_text_gone_and_new(
            "postEmployment: 'J1-2-detail-postEmployment'",
            "postEmployment: 'J1-2-detail-post-employment'",
        ),
        tags=("transport-key", "bp-11", "source"),
    ),
    Mutation(
        id="M41", side="be", path=SLICE, kind="replace",
        scope=TK(6), offset=OFF_TK_ORPHAN_VERDICT[6],
        anchor='        "orphan_carrier_verdict": "FABRICATED_KEY_SHAPE_NEVER_WRITTEN_IN_PRODUCTION",',
        new='        "orphan_carrier_verdict": "REAL_KEY_SHAPE",',
        want=f"{_TK}::test_tk6_orphan_carrier_key_shape_never_appears_in_production",
        why="🔴 把 orphan 载体的伪造键形态裁决改掉仍绿 ⇒ 「`J2-${key}` 从未在生产写过」这条"
            "（Task 52 正文要「解清」的核心结论）是自述而非实证",
        scope_check=_by_id(
            "transport_key_resolution.declarations", "TK-6",
            "orphan_carrier_verdict", "REAL_KEY_SHAPE",
        ),
        tags=("transport-key", "orphan", "data"),
    ),
    Mutation(
        id="M42", side="be", path=SLICE, kind="replace",
        anchor='      "J1-2-rows",',
        new='      "J1-2-detail-shortTerm",',
        want=f"{_TK}::test_guessed_keys_have_zero_hits",
        why="🔴 把反向分母里的「猜的键」换成一个**真存在**的键仍绿 ⇒ "
            "「禁按命名规律推断」那条要求的反例分母是假的（8 个串必须各 0 命中）",
        scope_check=lambda data: "J1-2-detail-shortTerm"
        in json.loads(data.decode("utf-8"))["transport_key_resolution"][
            "nonexistent_guessed_keys"
        ],
        tags=("transport-key", "data"),
    ),
    Mutation(
        id="M43", side="be", path=SLICE, kind="replace",
        scope=TK(1), offset=OFF_TK_STATUS[1],
        anchor='        "status": "resolved_two_declarations_currently_consistent"',
        new='        "status": "resolved_with_defect"',
        want=f"{_TK}::test_transport_key_summary_counts_recompute",
        why="TK-1 的 status 被改成缺陷态仍绿 ⇒ 7 条 declaration 的 status 分类计数没有现算，"
            "「4 条干净 / 3 条带缺陷」这个分布可以手填",
        scope_check=_by_id(
            "transport_key_resolution.declarations", "TK-1", "status", "resolved_with_defect"
        ),
        tags=("transport-key", "counters", "data"),
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # ⑥ Property 22 / 23 的穷举等值（双向）
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M44", side="be", path=SLICE, kind="replace",
        anchor='      "total_hits": 10,',
        new='      "total_hits": 9,',
        want=f"{_P22}::test_positional_identity_inventory_is_exhaustive_and_partitioned",
        wants=(f"{_P69}::test_derived_counters_recompute_from_their_own_sections",),
        why="位置化命中总数被改仍绿 ⇒ 穷举清单不是现扫出来的，新出现的下一条不会被发现",
        scope_check=_json_at(
            9, "dynamic_row_identity", "positional_identity_inventory", "total_hits"
        ),
        tags=("property-23", "counters", "data"),
    ),
    Mutation(
        id="M45", side="be", path=SLICE, kind="replace",
        scope='      "family_c_generated_opaque_with_random_must_not_be_flagged": {',
        offset=1,
        anchor='        "count": 3,',
        new='        "count": 2,',
        want=f"{_P22}::test_positional_identity_inventory_is_exhaustive_and_partitioned",
        wants=(f"{_P22}::test_family_discriminator_really_separates_b_from_c",),
        why="🔴 family_c（3 处含 Date.now()+random 的生成式）计数被改仍绿 ⇒ 五族划分不是分割，"
            "而 family_c 正是「判别式必须是『同时含两者』而不是『含 random』」的唯一探针 ——"
            "只看含 random 会把最严重的 family_b 第 1 条洗成 family_c",
        scope_check=_json_at(
            2, "dynamic_row_identity", "positional_identity_inventory",
            "family_c_generated_opaque_with_random_must_not_be_flagged", "count",
        ),
        tags=("property-23", "counters", "data"),
    ),
    Mutation(
        id="M46", side="be", path=SLICE, kind="replace",
        scope='      "family_e_four_table_seed_absent": {',
        offset=1,
        anchor='        "count": 0,',
        new='        "count": 1,',
        want=f"{_P22}::test_four_table_seed_family_is_really_absent",
        why="family_e 的 0 命中被改成 1 仍绿 ⇒ 那个 0 是分母为空的重言式，"
            "而「J 循环没有四表种子位置化」这条结论正是靠它成立",
        scope_check=_json_at(
            1, "dynamic_row_identity", "positional_identity_inventory",
            "family_e_four_table_seed_absent", "count",
        ),
        tags=("property-23", "counters", "data"),
    ),
    Mutation(
        id="M47", side="be", path=SLICE, kind="replace",
        anchor='        "blankRows_with_integer_literal": 0,',
        new='        "blankRows_with_integer_literal": 1,',
        want=f"{_P22}::test_hardcoded_patterns_are_all_zero_and_the_denominator_is_real",
        wants=(f"{_P69}::test_derived_counters_recompute_from_their_own_sections",),
        why="硬编码模式的 0 命中被改成 1 仍绿 ⇒ 六个 0 是空跑出来的（memory 铁律 ⑥ 点名的"
            "「动态区骨架行数写死」形态在 J 域确实 0 命中，但那必须是现扫的结论）",
        scope_check=_json_at(
            1, "dynamic_row_identity", "hardcoded_scan_result", "patterns",
            "blankRows_with_integer_literal",
        ),
        tags=("property-22", "counters", "data"),
    ),
    Mutation(
        id="M48", side="be", path=J2_ADJUSTMENT_VUE, kind="replace",
        anchor="      id: i + 1, description: String(e.description ?? ''), category: String(e.category ?? '账项调整'),",
        new="      id: `adj-${String(e.description ?? '')}`, description: String(e.description ?? ''), category: String(e.category ?? '账项调整'),",
        want=f"{_P22}::test_positional_identity_inventory_is_exhaustive_and_partitioned",
        wants=(f"{_P22}::test_family_a_hit_writes_to_the_declared_persisted_key",),
        why="🔴 **反向变异**：把 family_a 那条（全 J 域唯一的纯序号身份、且真落库到 "
            "`J2-3-entries`）改成稳定身份 ⇒ 命中数从 10 降到 9、family_a 从 1 降到 0 ⇒ "
            "判据必须同样打红。修好而不删登记会让 BP-8 永久挂着一条已解决的债",
        scope_check=_text_gone_and_new(
            "      id: i + 1, description:", "      id: `adj-${String(e.description ?? '')}`,"
        ),
        tags=("property-23", "reverse", "source"),
    ),
    Mutation(
        id="M49", side="be", path=J1_INDEX_VUE, kind="replace",
        anchor="    seq: i + 1,",
        new="    id: i + 1,",
        want=f"{_P22}::test_display_sequence_sites_are_not_flagged",
        wants=(f"{_P22}::test_positional_identity_inventory_is_exhaustive_and_partitioned",),
        why="🔴 把一处**展示序号**改成身份键（`seq:` → `id:`）仍绿 ⇒ family_d 的反向自检没有"
            "现扫：判据要么误报（把 3 处展示序号当身份）、要么漏报（真出现第 11 处身份不发现），"
            "两个方向都靠这条探针",
        scope_check=_text_gone_and_new("    seq: i + 1,", "    id: i + 1,"),
        tags=("property-23", "source"),
    ),
    Mutation(
        id="M50", side="be", path=J1_ADJUSTMENT_VUE, kind="insert",
        anchor="        rowId: r.rowId || genId(i),",
        new="        padding: blankRows(rows, 3),",
        want=f"{_P22}::test_hardcoded_patterns_are_all_zero_and_the_denominator_is_real",
        why="注入一处 `blankRows(expr, 3)` 仍绿 ⇒ 硬编码扫描的 0 命中是空跑出来的",
        scope_check=_text_contains("blankRows(rows, 3)"),
        tags=("property-22", "source"),
    ),
    Mutation(
        id="M51", side="be", path=J1_ADJUSTMENT_VUE, kind="insert",
        anchor="        rowId: r.rowId || genId(i),",
        new="        col: { key: c.label, label: c.label },",
        want=f"{_P22}::test_hardcoded_patterns_are_all_zero_and_the_denominator_is_real",
        why="注入一处 `key: c.label`（H8 的 DV-1 形态）仍绿 ⇒「J 循环 label-as-key 0 命中」"
            "这条结论是空跑出来的，而它是 Property 22 的反例分母",
        scope_check=_text_contains("key: c.label"),
        tags=("property-22", "source"),
    ),
    Mutation(
        id="M52", side="be", path=J1_ADJUSTMENT_VUE, kind="insert",
        anchor="        rowId: r.rowId || genId(i),",
        new="        seedId: `seed-${i}`,",
        want=f"{_P22}::test_four_table_seed_family_is_really_absent",
        wants=(f"{_P22}::test_positional_identity_inventory_is_exhaustive_and_partitioned",),
        why="注入 H 循环 BP-6 那种四表种子位置化形态（`seed-${i}`）仍绿 ⇒ family_e 的 0 命中"
            "是分母为空的重言式",
        scope_check=_text_contains("seedId: `seed-${i}`"),
        tags=("property-23", "source"),
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # ⑦ Property 28：template identity 漂移 fail closed
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M53", side="be", path=SLICE, kind="replace",
        scope=TPL(TPL_J1), offset=OFF_TPL_SHA,
        anchor='        "sha256": "a6100d91202f4d066dc39fb00e3016ea87794489bb75d308fec2733e92ca6061",',
        new='        "sha256": "a6100d91202f4d066dc39fb00e3016ea87794489bb75d308fec2733e92ca6062",',
        want=f"{_P28}::test_authoritative_template_digests_recompute",
        why="权威模板 digest 改一字仍绿 ⇒ Property 28 的 template identity 层判据没有 hashlib 现算",
        scope_check=_template_field(
            TPL_J1, "sha256",
            "a6100d91202f4d066dc39fb00e3016ea87794489bb75d308fec2733e92ca6062",
        ),
        tags=("property-28", "data"),
    ),
    Mutation(
        id="M54", side="be", path=SLICE, kind="replace",
        scope=TPL(TPL_J1), offset=OFF_TPL_RETIRED["J1"],
        anchor='        "retired_sheet_count": 7,',
        new='        "retired_sheet_count": 6,',
        want=f"{_P28}::test_sheet_inventory_recomputes_four_ways",
        why="🔴 历史 sheet 计数改错仍绿 ⇒ 「23 = 7 历史 + 1 机制 + 15 业务」这条四向自洽没有"
            "现读 sheetnames；而「OO 侧有 15 张活业务表」正是 not_single_html_because 的证据",
        scope_check=_template_field(TPL_J1, "retired_sheet_count", 6),
        tags=("property-28", "data"),
    ),
    Mutation(
        id="M55", side="be", path=SLICE, kind="replace",
        scope=TPL(TPL_J2), offset=OFF_TPL_OWNER,
        anchor='        "belongs_to_entry": null,',
        new='        "belongs_to_entry": "xlsx/j1/gt-j1-employee-compensation",',
        want=f"{_P28}::test_template_owner_mapping_is_injective_with_reasoned_nulls",
        wants=(
            f"{_P69}::test_derived_counters_recompute_from_their_own_sections",
            f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",
        ),
        why="🔴 把 J2 册也挂到 J1 entry 上（J1 于是有两本册）仍绿 ⇒ SR-8 的**单射**判据只验了"
            "「归属命中某个 entry」而没验唯一性。本 slice 是 D~I 六轮里第一份真正走到 SR-8 "
            "null 分支的，两侧都必须验",
        scope_check=_template_field(
            TPL_J2, "belongs_to_entry", "xlsx/j1/gt-j1-employee-compensation"
        ),
        tags=("property-28", "property-70", "data"),
    ),
    Mutation(
        id="M56", side="be", path=SLICE, kind="replace",
        anchor='    "reference_copy_status": "absent_in_worktree",',
        new='    "reference_copy_status": "verified_against_reference_copy",',
        want=f"{_P28}::test_reference_copy_status_is_honest",
        why="把「参考副本不在工作树」改成「已与参考副本比对」仍绿 ⇒ 能力缺口可以被写成豁免，"
            "而 G4/G5/G6 正是因为据落后的参考副本重建而返工过",
        scope_check=_json_at(
            "verified_against_reference_copy", "authoritative_templates", "reference_copy_status"
        ),
        tags=("property-28", "data"),
    ),
    Mutation(
        id="M57", side="be", path=SLICE, kind="replace",
        anchor='      { "wp_code": "J2-5", "resolved": "J2 长期应付职工薪酬-设定受益计划净资产.xlsx", "resolved_any": "J2 长期应付职工薪酬-设定受益计划净资产.xlsx" },',
        new='      { "wp_code": "J2-5", "resolved": "J1 应付职工薪酬.xlsx", "resolved_any": "J1 应付职工薪酬.xlsx" },',
        want=f"{_P28}::test_template_resolution_audit_recomputes",
        why="模板解析审计的冻结结果改成另一本册仍绿 ⇒ 37 条 wp_code 没有真跑 wp_template_finder，"
            "「J 循环没有 F2 那种整册码回落」这条结论就只是文档声明",
        scope_check=lambda data: any(
            row["wp_code"] == "J2-5" and row["resolved"] == "J1 应付职工薪酬.xlsx"
            for row in json.loads(data.decode("utf-8"))["template_resolution_audit"]["measured"]
        ),
        tags=("property-28", "data"),
    ),
    Mutation(
        id="M58", side="be", path=SLICE, kind="replace",
        anchor='      { "wp_code": "J2A", "resolved": null, "resolved_any": null },',
        new='      { "wp_code": "J2A", "resolved": "J2 长期应付职工薪酬-设定受益计划净资产.xlsx", "resolved_any": null },',
        want=f"{_P28}::test_program_table_and_j0_codes_resolve_to_none",
        wants=(f"{_P28}::test_template_resolution_audit_recomputes",),
        why="把程序表码 J2A 的「两个函数都返回 None」改成有解仍绿 ⇒ 那组否定式判据没跑，"
            "而它与 J0（册不存在）是两种不同理由的 None，必须都真跑",
        scope_check=lambda data: any(
            row["wp_code"] == "J2A" and row["resolved"] is not None
            for row in json.loads(data.decode("utf-8"))["template_resolution_audit"]["measured"]
        ),
        tags=("property-28", "data"),
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # ⑧ Property 70 / property_denominators
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M59", side="be", path=SLICE, kind="replace",
        anchor='    "backend/data/workpaper_sync_i_cycle_manifest_slice.json"',
        new='    "backend/data/workpaper_sync_zz_cycle_manifest_slice.json"',
        want=f"{_P70}::test_sibling_slices_declared_match_the_disk",
        why="兄弟 slice 清单把 I 换成一份不存在的 slice 仍绿 ⇒ 跨 slice 互斥判据的分母可以被"
            "悄悄改掉，「与 I 循环无交集」这条最容易撞车的判据就不跑了。"
            "🔴 用 replace 而非 delete：它是数组末元素，删掉会留尾逗号使 JSON 失效 ⇒ "
            "scope_check 的 json.loads 抛异常 ⇒ 判定 ERROR（脚本缺陷而非守卫缺陷）",
        scope_check=lambda data: json.loads(data.decode("utf-8"))["sibling_slices"][-1]
        == "backend/data/workpaper_sync_zz_cycle_manifest_slice.json",
        tags=("property-70", "data"),
    ),
    Mutation(
        id="M60", side="be", path=SLICE, kind="replace",
        anchor='  "properties_verified": [3, 20, 69, 70],',
        new='  "properties_verified": [3, 20, 21, 69, 70],',
        want=f"{_P3}::test_property_denominator_block_declares_what_is_not_claimed",
        wants=(f"{_DEL}::test_plan_orphan_modules_mirror_the_slice_inventory",),
        why="properties_verified 里塞进一条分母为空的 Property（21）仍绿 ⇒「不宣称通过」的边界"
            "是散文，空分母重言式可以重新长回来",
        scope_check=_json_at([3, 20, 21, 69, 70], "properties_verified"),
        tags=("property-20", "data"),
    ),
    Mutation(
        id="M61", side="be", path=SLICE, kind="replace",
        scope='    "property_3": {', offset=4,
        anchor='      "not_claimed_passing": true,',
        new='      "not_claimed_passing": false,',
        want=f"{_P3}::test_property_denominator_block_declares_what_is_not_claimed",
        why="🔴 把 Property 3 的「不宣称通过」翻成 false（=宣称通过）仍绿 ⇒ 空分母与真分母的"
            "边界判据是死的。Property 3 的空分母部分（bidirectional entry 数 = 0）永远不能"
            "被宣称通过，否则「未注册 adapter 不得宣称双向」在本 slice 就是重言式",
        scope_check=_json_at(False, "property_denominators", "property_3", "not_claimed_passing"),
        tags=("property-3", "data"),
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # ⑨ AC 1.4 的 UI 义务（step 11 / BP-10）
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M62", side="be", path=SLICE, kind="replace",
        anchor='      "ui_toolbar_gate_second_level": null,',
        new='      "ui_toolbar_gate_second_level": "dualMode.ooAvailable.value",',
        want=f"{_AC14}::test_second_level_gate_absence_matches_the_declaration",
        wants=(f"{_P69}::test_summary_counters_recompute_from_the_entries",),
        why="🔴 把 J1 的「无二级门控」这一实况改成「有」仍绿 ⇒ 判据写死了「全 slice 都有二级"
            "门控」（照 I 循环 5/6 条的多数形态），于是在 J1 上静默恒真 —— 而 J1 恰恰是 "
            "BP-10 最严重的那条（OO 不可用也显示切换按钮、点了无声失败）",
        scope_check=_entry_field("ui_toolbar_gate_second_level", "dualMode.ooAvailable.value"),
        tags=("ac-1.4", "data"),
    ),
    Mutation(
        id="M63", side="be", path=SLICE, kind="replace",
        anchor='      "notice_mounted": false,',
        new='      "notice_mounted": true,',
        want=f"{_AC14}::test_bp10_is_registered_because_no_host_mounts_the_notice",
        wants=(f"{_P69}::test_summary_counters_recompute_from_the_entries",),
        why="把「宿主未挂 AC 1.4 notice」改成已挂仍绿 ⇒ 声明与 DOM/模板实测没有两侧比对",
        scope_check=_entry_field("notice_mounted", True),
        tags=("ac-1.4", "data"),
    ),
    Mutation(
        id="M64", side="be", path=HOST_J1, kind="insert",
        anchor='    <div v-if="!isLoading && isHtmlSheet" class="j1-dual-mode-bar">',
        new="      <GtEntrySyncCapabilityNotice :entry-id=\"'xlsx/j1/gt-j1-employee-compensation'\" />",
        want=f"{_AC14}::test_bp10_is_registered_because_no_host_mounts_the_notice",
        why="🔴 **反向变异**：在宿主里真挂上 AC 1.4 的 notice 组件而 BP-10 仍登记为未修 ⇒ "
            "判据必须打红提示「可以解除 BP-10 了」。只拦「没挂」不拦「挂了但登记未更新」"
            "会让阻断项永久挂着",
        scope_check=_text_contains("<GtEntrySyncCapabilityNotice"),
        tags=("ac-1.4", "reverse", "source"),
    ),
    Mutation(
        id="M65", side="be", path=HOST_J1, kind="replace",
        anchor='      <el-segmented :model-value="dualMode.mode.value === \'html\' ? \'HTML\' : \'OnlyOffice\'" @change="(v: any) => dualMode.switchMode(v === \'HTML\' ? \'html\' : \'onlyoffice\')" :options="[\'HTML\', \'OnlyOffice\']" size="small" />',
        new='      <el-segmented v-if="dualMode.ooAvailable.value" :model-value="dualMode.mode.value === \'html\' ? \'HTML\' : \'OnlyOffice\'" @change="(v: any) => dualMode.switchMode(v === \'HTML\' ? \'html\' : \'onlyoffice\')" :options="[\'HTML\', \'OnlyOffice\']" size="small" />',
        want=f"{_AC14}::test_second_level_gate_absence_matches_the_declaration",
        why="🔴 **反向变异**：给 el-segmented 真加上二级门控（BP-10 的一半兑现）而登记仍是 null "
            "⇒ 判据必须打红。这条同时证明模板形态判据是现读的：它要看的是切换器那一行有没有 "
            "`v-if`，不是「文件里有没有 v-if」",
        scope_check=_text_contains('<el-segmented v-if="dualMode.ooAvailable.value"'),
        tags=("ac-1.4", "reverse", "source"),
    ),
    Mutation(
        id="M66", side="be", path=SLICE, kind="replace",
        anchor='        "audit-platform/frontend/src/components/workpaper/j1/inspection/J1TabGeneralCheck.vue#L27",',
        new='        "audit-platform/frontend/src/components/workpaper/j1/inspection/J1TabGeneralCheck.vue#L28",',
        want=f"{_AC14}::test_extra_unrelated_segmented_sites_are_declared_and_outside_the_toolbar",
        why="Tab 内部分段用的 el-segmented 站点行号改错仍绿 ⇒「不能全文件 grep el-segmented」"
            "这条口径判据没有落到真实行号上（全 J 域 3 处，只有 1 处是模式切换器）",
        scope_check=lambda data: (
            f"{WP}/j1/inspection/J1TabGeneralCheck.vue#L28"
            in json.loads(data.decode("utf-8"))["independent_entries"][0][
                "extra_unrelated_segmented_sites"
            ]
        ),
        tags=("ac-1.4", "data"),
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # ⑩ orphan 源码侧 + deletion plan
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M67", side="be", path=J2_ENTRY_DUAL_TS, kind="replace",
        anchor="  '底稿目录': 'J2-目录',",
        new="  '底稿目录': '底稿目录',",
        want=f"{_ORPHAN}::test_orphan_sheet_maps_target_sheets_that_do_not_exist",
        why="🔴 **真改 orphan 的 sheet 映射表**（把一个目标改成真实存在的 sheet 名）仍绿 ⇒ "
            "「映射目标与权威模板交集为空」这条是抄的而不是 openpyxl 现读 sheetnames 比对的",
        scope_check=_text_gone_and_new("'底稿目录': 'J2-目录'", "'底稿目录': '底稿目录'"),
        tags=("orphan", "source"),
    ),
    Mutation(
        id="M68", side="be", path=J3_DUAL_TS, kind="replace",
        anchor="      const res = await http.get('/api/workpapers/onlyoffice/health')",
        new="      const res = { data: { healthy: false } }",
        want=f"{_ORPHAN}::test_orphan_with_legacy_endpoint_direct_call_is_registered",
        why="🔴 **反向变异**：删掉 `useJ3DualMode` 的 legacy 端点直调（step 6 明禁项）而登记"
            "仍在 ⇒ 判据必须打红。这条把「BP-6 的一条依据已消失」变成可见的红，"
            "否则登记会一直挂着一条已解决的债",
        scope_check=_text_gone_and_new(
            "http.get('/api/workpapers/onlyoffice/health')", "const res = { data: { healthy: false } }"
        ),
        tags=("orphan", "reverse", "source"),
    ),
    Mutation(
        id="M69", side="be", path=PLAN, kind="replace",
        anchor='      "modules_to_delete": 4,',
        new='      "modules_to_delete": 3,',
        want=f"{_DEL}::test_plan_counters_recompute",
        why="清册计数被篡改仍绿 ⇒ 待删对象数量是手填的，删除执行方（Task 72）无从核对",
        scope_check=_json_at(3, "orphan_dual_mode_to_delete", "counters", "modules_to_delete"),
        tags=("deletion-plan", "counters", "data"),
    ),
    Mutation(
        id="M70", side="be", path=PLAN, kind="replace",
        anchor='      "total_lines_to_delete": 152,',
        new='      "total_lines_to_delete": 151,',
        want=f"{_DEL}::test_plan_counters_recompute",
        why="待删总行数被篡改仍绿 ⇒ 每条 lines 没有与文件 splitlines() 现算比对",
        scope_check=_json_at(151, "orphan_dual_mode_to_delete", "counters", "total_lines_to_delete"),
        tags=("deletion-plan", "counters", "data"),
    ),
    Mutation(
        id="M71", side="be", path=PLAN, kind="replace",
        anchor='    "composables_to_delete_entry_scoped": 0,',
        new='    "composables_to_delete_entry_scoped": 1,',
        want=f"{_DEL}::test_plan_counters_recompute",
        why="🔴 把「entry 级零删除」改成 1 仍绿 ⇒ 「空数组是实测结论而非漏填」这条（J 循环最"
            "特殊的一点：J1 没有 per-entry dual-mode composable）没有与四条磁盘判据联动",
        scope_check=_json_at(1, "counters", "composables_to_delete_entry_scoped"),
        tags=("deletion-plan", "counters", "data"),
    ),
    Mutation(
        id="M72", side="be", path=PLAN, kind="replace",
        anchor='    "result": "not_applicable_but_worse",',
        new='    "result": "found",',
        want=f"{_DEL}::test_plan_counters_recompute",
        why="把「J 循环没有宿主内联第二份实现」改成「有」仍绿 ⇒ 那个结论是文档声明而非实测，"
            "而它直接决定「删完行为不变」在 J2/J3 上是正确期望还是可疑信号",
        scope_check=_json_at("found", "host_inlined_second_implementation", "result"),
        tags=("deletion-plan", "data"),
    ),
    Mutation(
        id="M73", side="be", path=PLAN, kind="replace",
        anchor='        "OnlyOffice": 2',
        new='        "OnlyOffice": 0',
        want=f"{_AC14}::test_j2_and_j3_hosts_have_no_mode_switcher_at_all",
        why="🔴 把 J3 宿主的 2 处大写 `OnlyOffice` 文案命中改成 0 仍绿 ⇒ token 命中表是「都为 0」"
            "的想当然而不是逐 token 现算。首轮就把它写成六个 token 全 0，实际 J3 有 2 处"
            "（#L65 注释 + #L67 el-empty 文案）—— 错一个数会让整条判据失去可信度",
        scope_check=lambda data: json.loads(data.decode("utf-8"))[
            "host_inlined_second_implementation"
        ]["measured_token_hits"][f"{WP}/j3/GtJ3ShareBasedPayment.vue"]["OnlyOffice"] == 0,
        tags=("deletion-plan", "ac-1.4", "data"),
    ),
    Mutation(
        id="M74", side="be", path=PLAN, kind="replace",
        anchor='  "pilot_already_migrated": null,',
        new='  "pilot_already_migrated": {"entry_id": "xlsx/j1/gt-j1-employee-compensation"},',
        want=f"{_DEL}::test_plan_has_no_pilot_branch",
        why="给 J 循环编一个 pilot 仍绿 ⇒「J 循环没有 pilot」这条排除项是自述而非实证"
            "（逐文件读四份契约的 review.entry_id），而它直接决定 selection_rule 里"
            "有没有第四条排除条件",
        scope_check=_json_at(
            {"entry_id": "xlsx/j1/gt-j1-employee-compensation"}, "pilot_already_migrated"
        ),
        tags=("deletion-plan", "data"),
    ),
    Mutation(
        id="M75", side="be", path=PLAN, kind="replace",
        scope=BARREL("j3"), offset=OFF_PLAN_BARREL_EDGES,
        anchor='        "inbound_edges": 0,',
        new='        "inbound_edges": 2,',
        want=f"{_DEL}::test_plan_barrel_reexport_lines_are_real",
        why="🔴 把 j3 barrel 的入边改成 2（正是 stem 口径给出的假数）仍绿 ⇒ 入边判据用的是"
            "模块 stem 相等而不是路径解析 —— `services/apiPaths.ts` 的 "
            "`export * from './apiPaths/index'` 会被误命中成 j2/j3 barrel 的入边",
        scope_check=_plan_barrel_field(f"{CB}/j3/index.ts", "inbound_edges", 2),
        tags=("deletion-plan", "orphan", "data"),
    ),
    Mutation(
        id="M76", side="be", path=PLAN, kind="replace",
        anchor='        "action": "delete_file_and_drop_barrel_reexport",',
        new='        "action": "delete_file",',
        want=f"{_DEL}::test_plan_orphan_modules_mirror_the_slice_inventory",
        wants=(f"{_DEL}::test_plan_counters_recompute",),
        why="把二阶 orphan 的动作降级成「只删文件」仍绿 ⇒ 「删了它必须同步删 barrel 的 "
            "re-export（否则构建失败）」这条连带改动判据是死的，删除动作本身会把构建打红",
        scope_check=_plan_module_field("OD-4", "action", "delete_file"),
        tags=("deletion-plan", "data"),
    ),
    Mutation(
        id="M77", side="be", path=PLAN, kind="replace",
        scope=OD(3), offset=OFF_PLAN_OD_LINES,
        anchor='        "lines": 35,',
        new='        "lines": 36,',
        want=f"{_DEL}::test_plan_counters_recompute",
        wants=(f"{_DEL}::test_plan_orphan_modules_mirror_the_slice_inventory",),
        why="清册里某条待删对象的行数与 slice 脱节仍绿 ⇒ 两份产物没有同源比对，"
            "「清册裁决字段逐条与 slice 同源」这句话就是散文",
        scope_check=_plan_module_field("OD-3", "lines", 36),
        tags=("deletion-plan", "data"),
    ),
    Mutation(
        id="M78", side="be", path=SLICE, kind="replace",
        anchor='    "residual_inconsistency": null,',
        new='    "residual_inconsistency": "范式与 slice 仍有未收口的字段级冲突",',
        want=f"{_PARA}::test_new_sections_are_declared_as_non_conflicting",
        why="范式冲突登记从「已收口」改成「仍有残留」而判据仍绿 ⇒ paradigm_schema_conflict "
            "整块变成自述散文，「本 slice 未改范式 JSON / 未扩充 capability_enum」也就无从核对",
        scope_check=_json_at(
            "范式与 slice 仍有未收口的字段级冲突", "paradigm_schema_conflict",
            "residual_inconsistency",
        ),
        tags=("paradigm", "data"),
    ),
]

GUARD_FILES = {
    T52: "Task 52 新建（AC 1.3/1.4/1.7/12.1/12.8/12.9 裁决合法性；**orphan 可达性判定**"
         "（4 个 orphan dual-mode，2 个二阶 —— barrel 入边用路径解析口径而非 stem，两侧断言）；"
         "**真实传输键从 owner 常量现读**（J1-2 一表三键的前缀派生 + 读方三个全字面量的双侧锁 + "
         "8 个「按规律该有」的键 0 命中反向分母）；**行模型三边锁**（声明 → openpyxl 真读源 xlsx → "
         "impl 常量现读，4 条 declaration + 15 个边界格 + verdict 可复算 + 否定式声明 + "
         "跨 impl 分歧定位 + 两份 note_template 否证）；JD-1..JD-6 六处形态差异逐条回源"
         "（3 宿主 1 挂载点 / 无 per-entry composable / 共享适配器 + 7 Tab 双写路径且 client "
         "取得形态分静态动态两族 / 一表三键身份字段 id / 4 orphan / JSON snippet 伪消费边）；"
         "Property 22 的六个硬编码模式穷举 0 命中；Property 23 的 9 张动态行表 + 10 处位置化命中"
         "五族划分（含 family_d 的 3 与 family_e 的 0 反向自检）；Property 28 的 3 个模板 "
         "digest/sheet 四向计数 + 37 条模板解析实跑（含 J{n}A / J0 断言 None）；selection_rule 与 "
         "43 项计数现算；七 slice 不相交 + 模板归属单射且 null 必带 excluded_reason；"
         "AC 1.4 的工具栏区块形态判据（含 J1 无二级门控这一实况与 notice 未挂载的两侧断言）；"
         "deletion plan 同源与计数；范式 slice_schema 校验器与四条反向自检）",
}

if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="Task 52 J 循环 Excel 独立 entry 迁移守卫变异检验",
            backend_args=[
                "backend/tests/workpaper_sync/test_task52_j_cycle_migration.py",
                "-q",
                "--tb=no",
                "-rfE",
                "-p",
                "no:randomly",
            ],
            baseline_backend_passed=132,
        )
    )
