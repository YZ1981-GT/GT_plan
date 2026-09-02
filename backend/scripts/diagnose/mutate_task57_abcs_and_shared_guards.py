# -*- coding: utf-8 -*-
r"""Task 57 守卫变异检验 —— A/B/C/S 与跨循环共享 Excel 独立 entry 迁移。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 5 Task 57

用平台共享件 `backend/scripts/_mutation_kit`（`test_mutation_kit_adoption.py` 对新脚本强制
采纳）。`guard_files` 是签名层面必填的覆盖面分母。

═══ 本脚本的七条硬约束 ═══

1. **每条变异都带 `scope_check`**。四态判定式「新增失败集合是否为空」识别不出「锚点落在被测
   判据的作用域之外」—— 改到了别处会被判 GREEN（守卫缺陷），而真相是脚本缺陷。
   🔴 Task 54 的 M10 教训：`scope_check` **必须解析 JSON 定位到目标节**，不能用「文本里不存在
   某字面量」当判据。本脚本的数据侧回调一律 `json.loads` 后按路径取值断言。

2. 🔴 **`scope_check` 与锚点都禁用含 `\n` 的字面量**（Task 55 的 M38/M44 各踩一次）：
   工作树是 CRLF，多行字面量恒假 ⇒ RED 会被误报成 ANCHOR-MISS。源码侧的作用域自证一律
   改「按整行集合断言」。

3. **重复形态字段用 `scope` + `offset` 相对定位，绝不用绝对行号**。本 slice 有 **46 条** entry，
   故 entry 级字段全是 dup=46，一律以该 entry 唯一的 `"entry_id": "…"` 行作 `scope`，
   `offset` 由一次性诊断**实算**（非估计值）。

4. **变异按「可区分的错法」枚举而不是逐条目复制**，并分布在不同分组上（A 类 / B 类 / C 类 /
   S 类 / 跨循环共享），从而同时走通各组的 offset。

5. **必须含反向变异**（把缺陷修好也要打红）。只验「新增缺陷」一个方向是半个判据。本脚本的
   反向变异：M20 把 A38 的写死 5 列改成动态（BP-14 的 P22-D1 可解除）· M21 给 B14 补 `peer3`
   列（P22-D2 可解除）· M22 把 B50 的 `:key="row.name"` 改成 `row.code`（P22-D3 可解除）·
   M23 在 A101 宿主里**真挂上** AC 1.4 的 notice 组件（BP-7 可解除）· M24 给 `useWpDualMode.ts`
   加一条**非本 slice**生产边（`delete_after_rewire` 必须从 1 变 0）。

6. **真源码变异**（M14~M27）—— 数据侧变异只能证明「守卫读了 slice」；只有改真源码还打红，
   才能证明 impl 侧是**现读**而不是抄了一份快照。本轮的判据里有十一类必须有源码变异撑着：
   ① registry 模块边（M14）· ② 两种 `component:` 写法都要认（M15）· ③ 持久化通道现读（M16）·
   ④ mode 门控的**祖先链**解析（M17）· ⑤ mode token 覆盖面（M18）· ⑥ 动态列 key/label 解耦
   （M19）· ⑦ 三处 Property 22 缺陷的反向变异（M20/M21/M22）· ⑧ AC 1.4 挂载（M23 反向）·
   ⑨ 共享载体边数与 orphan 判定（M24 反向 / M25）· ⑩ 函证族 componentType 与 wp_code 现读
   （M26/M27）· ⑪ 权威模板 digest 现算（M13）。

7. 🔴 **CJK 在 Python 里算 `\w`** ⇒ 函证族提取码不能用 `\b`；本脚本的 M27 专门变异那条
   ASCII 码，验证提取器真的在按 `^[A-Z]0` 分循环。

用法（仓库根；本仓库 PATH 上的 `python` 可能指向坏掉的解释器，必须用显式解释器）::

    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task57_abcs_and_shared_guards.py --list
    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task57_abcs_and_shared_guards.py --check-anchors
    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task57_abcs_and_shared_guards.py --run M01,M02

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
SLICE = "backend/data/workpaper_sync_abcs_cycle_manifest_slice.json"
PLAN = "backend/data/workpaper_sync_abcs_cycle_deletion_plan.json"
FE = "audit-platform/frontend/src"
WP = f"{FE}/components/workpaper"
CO = f"{WP}/composables"
REGISTRY_TS = f"{WP}/htmlRendererRegistry.ts"
OVERRIDES = "backend/app/data/wp_code_overrides.json"
HOST_A101 = f"{WP}/GtA101GovernanceCommunication.vue"
A101_PERSIST = f"{CO}/useA101GovernanceCommunication.ts"
HOST_A38 = f"{WP}/GtA38GoodwillImpairment.vue"
HOST_B14 = f"{WP}/GtB14DueDiligenceReport.vue"
HOST_B23 = f"{WP}/GtB23ProcessControl.vue"
HOST_B50 = f"{WP}/GtB50RiskAssessment.vue"
HOST_B1EVAL = f"{WP}/GtB1Evaluation.vue"
HOST_CCTL = f"{WP}/GtCControlTest.vue"
HOST_S3 = f"{WP}/s3-policy-change/GtS3PolicyChange.vue"
WPDUAL = f"{CO}/useWpDualMode.ts"
HOST_B1KAA = f"{WP}/GtB1KaaCheck.vue"

# ── 期望打红的守卫（文件::类::方法，与 pytest 的 short nodeid 同形）─────────
T57 = "test_task57_abcs_and_shared_migration.py"
_SELF = f"{T57}::TestGuardSelfChecks"
_SCOPE = f"{T57}::TestSliceScopeIsRecomputable"
_GRP = f"{T57}::TestEntryGroupsAreRecomputable"
_ADJ = f"{T57}::TestAdjudicationLegality"
_HTML = f"{T57}::TestHtmlCounterpartIsSourceBacked"
_AC16 = f"{T57}::TestAc16ConfirmationAdapterReuse"
_P22 = f"{T57}::TestProperty22DynamicColumnIdentity"
_ROWS = f"{T57}::TestDynamicRowIdentity"
_SWITCH = f"{T57}::TestModeSwitchResolution"
_CARRIER = f"{T57}::TestDualModeCarrierInventory"
_BIZ = f"{T57}::TestBusinessModelProjection"
_P69 = f"{T57}::TestProperty69EvidenceAndCounters"
_P70 = f"{T57}::TestProperty70CrossEntryIsolation"
_DEL = f"{T57}::TestDeletionPlanConsistency"
_FORM = f"{T57}::TestFormDifferences"
_PARA = f"{T57}::TestParadigmCompliance"
_CONTRACT = "test_migration_paradigm_contract.py"
_COVERAGE = "test_slice_schema_validator_coverage.py"


def EID(slug: str) -> str:
    """某 entry 在 `independent_entries` 里唯一的 scope 行（dup=1，3 空格缩进）。"""
    return '   "entry_id": "%s",' % slug


A101 = EID("xlsx/gt-a101-governance-communication")
A38 = EID("xlsx/gt-a38-goodwill-impairment")
B14 = EID("xlsx/gt-b14-due-diligence-report")
B50 = EID("xlsx/gt-b50-risk-assessment")
CCTL = EID("xlsx/gt-c-control-test")
S3 = EID("xlsx/s3-policy-change/gt-s3-policy-change")
SHELL = EID("xlsx/shared/cycle-standalone-procedure-shell")
WPREND = EID("xlsx/gt-wp-renderer")

#: 逐字段 offset（由一次性诊断**实算**，非估计值）。slice 用 `indent=1` 落盘 ⇒
#: entry 级字段是 3 空格缩进、entry 内嵌一层是 4 空格。
#: 🔴 逐 entry 的 offset **不相等**（`wp_code_patterns` / `component_types` /
#: `wp_codes_via_component_type` 三个数组长度各不同）⇒ 必须逐 entry 实算。
OFF_CAPABILITY = {"A101": 22, "S3": 21, "CCTL": 46, "B50": 21}
OFF_CAPABILITY_TARGET = {"A101": 24, "S3": 23, "CCTL": 48, "B50": 23}
OFF_HTML_VERDICT = {"A101": 34, "S3": 33, "CCTL": 58, "B50": 33}
OFF_MIRROR_CAPABILITY = {"A101": 77, "S3": 87, "CCTL": 116, "B50": 116}
SCOPE_SLICE_CYCLE = '  "cycle": "A/B/C/S + cross_cycle_shared",'


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


def entry_path_is(entry_id: str, path: tuple[Any, ...], expected: Any):
    def check(data: bytes) -> bool:
        node: Any = _entry(data, entry_id)
        for key in path:
            try:
                node = node[key]
            except (KeyError, IndexError, TypeError):
                return False
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


def group_entry_count_is(group_id: str, expected: int):
    def check(data: bytes) -> bool:
        for g in _doc(data)["entry_groups"]["groups"]:
            if g["group_id"] == group_id:
                return g["entry_count"] == expected
        return False
    return check


def family_field_is(component_type: str, key: str, expected: Any):
    def check(data: bytes) -> bool:
        for f in _doc(data)["confirmation_adapter_reuse"]["families"]:
            if f["component_type"] == component_type:
                return f.get(key) == expected
        return False
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
    """整文按行匹配计数（pattern 自身**不含** `\\n`）。"""
    rx = re.compile(pattern)

    def check(data: bytes) -> bool:
        return sum(1 for line in _lines(data) if rx.search(line)) == expected
    return check


def source_matches_at_least(pattern: str, minimum: int):
    rx = re.compile(pattern)

    def check(data: bytes) -> bool:
        return sum(1 for line in _lines(data) if rx.search(line)) >= minimum
    return check


# ══════════════════════════════════════════════════════════════════════════
# 变异清单
# ══════════════════════════════════════════════════════════════════════════
MUTATIONS: list[Mutation] = [
    # ── A 组：selection_rule / scope 可复算（数据侧）─────────────────────
    Mutation(
        id="M01", side="be", path=SLICE, kind="replace",
        anchor=A101,
        new='   "entry_id": "xlsx/gt-a101-governance-communication-typo",',
        want=f"{_SCOPE}::test_selection_rule_recomputes_the_entry_set",
        why="改一条 entry_id ⇒ 按 selection_rule 现算的集合与声明不再等值。"
            "不能改 capability（那是别的判据）；改 id 才落在「集合等值」这条上。",
        scope_check=entry_field_is("xlsx/gt-a101-governance-communication-typo",
                                   "host", "GtA101GovernanceCommunication.vue"),
    ),
    Mutation(
        id="M02", side="be", path=SLICE, kind="replace",
        anchor='  "independent_entry_count": 46,',
        new='  "independent_entry_count": 45,',
        want=f"{_SCOPE}::test_selection_rule_recomputes_the_entry_set",
        wants=(f"{_P69}::test_summary_counters_recompute_from_the_entries", _CONTRACT, _COVERAGE),
        why="scope 计数手改 ⇒ 与 manifest 现算不符（SR-1 同形）；范式校验器也必须咬住。",
        scope_check=doc_path_is(("slice_scope", "independent_entry_count"), 45),
    ),
    Mutation(
        id="M03", side="be", path=SLICE, kind="replace",
        anchor='   "pattern_less_shared": 5',
        new='   "pattern_less_shared": 4',
        want=f"{_SCOPE}::test_letter_bucket_counts_recompute",
        why="🔴 AD-1：跨循环共享（wp_code_patterns 为空）那 5 条是本轮独有的分母，"
            "改小它 ⇒ 与 manifest 现算不符。照抄单字母规则的人正是漏掉这 5 条。",
        scope_check=doc_path_is(("slice_scope", "letter_bucket_counts", "pattern_less_shared"), 4),
    ),
    Mutation(
        id="M04", side="be", path=SLICE, kind="replace",
        anchor='  "global_parent_duplicate_count": 43,',
        new='  "global_parent_duplicate_count": 42,',
        want=f"{_SCOPE}::test_parent_duplicate_section_is_absent_because_in_scope_count_is_zero",
        why="AC 1.6 原文写「43 个父组件重复入口」；改成 42 ⇒ 与 manifest 现算不符。"
            "这条同时守住「in-scope 为 0 不等于全局为 0」这个区分。",
        scope_check=doc_path_is(("slice_scope", "global_parent_duplicate_count"), 42),
    ),
    Mutation(
        id="M05", side="be", path=SLICE, kind="insert",
        anchor=' "independent_entries": [',
        new='  {\n   "entry_id": "xlsx/gt-fabricated-entry",\n   "capability": null\n  },',
        want=f"{_SCOPE}::test_selection_rule_recomputes_the_entry_set",
        wants=(_CONTRACT, _COVERAGE),
        why="凭空插一条 entry（凑数）⇒ 集合等值必红，且范式校验器因缺必填字段也必红。"
            "这条守的是「多写一条」方向（M01 守的是「改写一条」）。",
        scope_check=lambda data: any(
            e.get("entry_id") == "xlsx/gt-fabricated-entry"
            for e in _doc(data)["independent_entries"]),
    ),
    Mutation(
        id="M06", side="be", path=SLICE, kind="replace",
        anchor='  "excluded_pilot_entry_count": 1,',
        scope=SCOPE_SLICE_CYCLE, offset=16,
        new='  "excluded_pilot_entry_count": 0,',
        want=f"{_SCOPE}::test_b60_is_the_excluded_pilot_and_the_contract_denominator_is_non_vacuous",
        why="🔴 AD-2：B60 是本轮字母范围内的 pilot，`excluded_pilot_entry_count` 首次非 0。"
            "改回 0 ⇒ 与「契约归属按 review.entry_id 现算」不符。",
        scope_check=doc_path_is(("slice_scope", "excluded_pilot_entry_count"), 0),
    ),

    # ── B 组：待裁决态与裁决合法性（数据侧）──────────────────────────────
    Mutation(
        id="M07", side="be", path=SLICE, kind="replace",
        anchor='   "capability": null,', scope=A101, offset=OFF_CAPABILITY["A101"],
        new='   "capability": "single_onlyoffice",',
        want=f"{_ADJ}::test_no_pure_oo_entry_exists_in_this_slice",
        wants=(f"{_ADJ}::test_capability_matches_honest_capability",
               f"{_P69}::test_summary_counters_recompute_from_the_entries", _CONTRACT, _COVERAGE),
        why="🔴 AP-1 的正面拦截：该 entry 现算有 HTML 对端（checklist_responses），"
            "AC 12.8 禁止裁 single_onlyoffice。同时触发 SR-2/SR-4/SR-9 三条计数与一致性判据。",
        scope_check=entry_field_is("xlsx/gt-a101-governance-communication",
                                   "capability", "single_onlyoffice"),
    ),
    Mutation(
        id="M08", side="be", path=SLICE, kind="replace",
        anchor='   "capability_target": "bidirectional",', scope=S3,
        offset=OFF_CAPABILITY_TARGET["S3"],
        new='   "capability_target": "dual",',
        want=f"{_ADJ}::test_capability_is_null_and_pending_fields_are_complete",
        wants=(_CONTRACT, _COVERAGE),
        why="🔴 禁扩枚举：`dual` 不在 capability_enum 里（AC 1.3 逐字派生）。"
            "SR-3 右支的 `member_of_capability_enum` 必须咬住。",
        scope_check=entry_field_is("xlsx/s3-policy-change/gt-s3-policy-change",
                                   "capability_target", "dual"),
    ),
    Mutation(
        id="M09", side="be", path=SLICE, kind="replace",
        anchor='   "html_counterpart_verdict": "exists",', scope=CCTL,
        offset=OFF_HTML_VERDICT["CCTL"],
        new='   "html_counterpart_verdict": "unresolved",',
        want=f"{_ADJ}::test_every_entry_has_a_binary_html_counterpart_verdict",
        wants=(f"{_ADJ}::test_no_pure_oo_entry_exists_in_this_slice",),
        why="🔴 AP-3：`unresolved` 不是结论。step 3 只认二值 none / exists。",
        scope_check=entry_field_is("xlsx/gt-c-control-test",
                                   "html_counterpart_verdict", "unresolved"),
    ),
    Mutation(
        id="M10", side="be", path=SLICE, kind="replace",
        anchor='    "capability": "single_onlyoffice",', scope=B50,
        offset=OFF_MIRROR_CAPABILITY["B50"],
        new='    "capability": null,',
        want=f"{_ADJ}::test_manifest_mirror_divergence_is_registered_not_silently_equal",
        why="🔴 `manifest_mirror` 的判据是「必须**不一致**且已登记 BP-3」。把 mirror 改成 null "
            "⇒ 与本 slice 的 capability 一致了 ⇒ 守卫必须打红（提示 BP-3 该解除）。"
            "这条同时反证「守卫没有偷偷改成断言相等」。",
        scope_check=lambda data: any(
            e["manifest_mirror"]["capability"] is None
            for e in _doc(data)["independent_entries"]),
    ),
    Mutation(
        id="M11", side="be", path=SLICE, kind="replace",
        anchor='   "unadjudicated": 46,',
        new='   "unadjudicated": 0,',
        want=f"{_P69}::test_slice_counters_are_all_zero_except_unadjudicated",
        wants=(_CONTRACT, _COVERAGE),
        why="🔴 SR-9：SR-3 右支放行 null 之后必须有人管住计数；「全记待裁决同时报 0」"
            "是右支被当后门用的形态。",
        scope_check=doc_path_is(
            ("honest_adjudication_summary", "slice_counters", "unadjudicated"), 0),
    ),
    Mutation(
        id="M12", side="be", path=SLICE, kind="replace",
        anchor='   "confirmation": "confirmation_component_types / confirmation_shared_component_types / confirmation_wp_codes / confirmation_cjk_alias_keys / confirmation_cycles / confirmation_entries_in_source_manifest / confirmation_contracts_attributed 由 confirmation_adapter_reuse 现算",',
        new='   "confirmation": "（略）",',
        want=f"{_P69}::test_counting_notes_cover_every_summary_counter",
        why="🔴 Task 54 的 M28/M29 教训：`counting_notes` 的并集必须覆盖 summary 全部数值键。"
            "抽掉一族说明 ⇒ 覆盖面元判据必红（否则「加计数不加来源」就能悄悄放宽）。",
        scope_check=doc_path_is(
            ("honest_adjudication_summary", "counting_notes", "confirmation"), "（略）"),
    ),
    Mutation(
        id="M13", side="be", path=SLICE, kind="replace",
        anchor='    "sha256": "b859bcc138165ba8d765f4e74f504ca91c08bae337fd52f52bc1d01a27c34fa0",',
        new='    "sha256": "0000000000000000000000000000000000000000000000000000000000000000",',
        want=f"{_HTML}::test_template_digests_and_formats_recompute",
        why="权威模板 digest 必须现算比对（Requirement 6.10 fail closed）。"
            "🔴 本条的 anchor 由 --check-anchors 校准：若命中 0 处说明第一本册的 sha256 变了，"
            "换成 `--list` 打印出的实际值。",
        scope_check=source_matches(
            r'"sha256": "0{64}"', 1),
    ),

    # ── C 组：真源码变异 —— 分组键第一维（registry 模块边）───────────────
    Mutation(
        id="M14", side="be", path=REGISTRY_TS, kind="replace",
        anchor="    componentType: 'a10-1-governance-communication',",
        new="    componentType: 'a10-1-governance-communication-renamed',",
        want=f"{_GRP}::test_component_type_is_read_from_the_registry_module_edge",
        wants=(f"{_P69}::test_summary_counters_recompute_from_the_entries",),
        why="🔴 真源码变异：改 registry 里的 componentType 字面量 ⇒ 按**模块边**现算的结果与 "
            "slice 声明不符。若守卫抄了一份 componentType 快照，这条会 GREEN。",
        scope_check=source_has_line("componentType: 'a10-1-governance-communication-renamed',"),
    ),
    Mutation(
        id="M15", side="be", path=REGISTRY_TS, kind="replace",
        anchor="const GtB50RiskAssessment = defineAsyncComponent(() => import('./GtB50RiskAssessment.vue'))",
        new="const GtB50RiskAssessment = defineAsyncComponent(() => import('./GtB22AControlMatrix.vue'))",
        want=f"{_GRP}::test_component_type_is_read_from_the_registry_module_edge",
        why="🔴 把提升式 `const` 的 import 指到另一个组件 ⇒ 模块边改变。"
            "这条专门证明「两种 `component:` 写法都要认」不是空话：只认内联写法的解析器"
            "在这条上会 GREEN。",
        scope_check=source_has_line(
            "const GtB50RiskAssessment = defineAsyncComponent(() => import('./GtB22AControlMatrix.vue'))"),
    ),

    # ── D 组：真源码变异 —— 分组键第二维（持久化通道）────────────────────
    Mutation(
        id="M16", side="be", path=A101_PERSIST, kind="replace",
        anchor="      await api.put(`/api/workpapers/${wpId.value}/checklist-responses`, { items })",
        new="      await api.put(`/api/workpapers/${wpId.value}/nonexistent-store`, { items })",
        want=f"{_GRP}::test_persistence_channel_is_read_from_real_http_sites",
        wants=(f"{_ADJ}::test_no_pure_oo_entry_exists_in_this_slice",
               f"{_HTML}::test_read_and_write_sites_are_the_real_calls"),
        why="🔴 真源码变异：把读站点的端点改掉 ⇒ 现算通道变化（checklist_responses 消失）。"
            "同时守住「read_source_ref 那行必须是真读调用」这条三边锁。",
        scope_check=source_matches(r"/nonexistent-store", 1),
    ),

    # ── E 组：真源码变异 —— mode 门控祖先链 ─────────────────────────────
    Mutation(
        id="M17", side="be", path=HOST_B1EVAL, kind="replace",
        anchor="    <template v-if=\"mode === '结构化视图'\">",
        new="    <template v-if=\"section === 'structured'\">",
        want=f"{_SELF}::test_ancestor_chain_parser_beats_indentation_heuristics",
        wants=(f"{_SWITCH}::test_per_entry_verdicts_are_from_a_closed_enum_and_recompute",
               f"{_SWITCH}::test_switch_counters_recompute"),
        why="🔴 真源码变异 + 祖先链判据：把祖先门控表达式里的 mode token 去掉 ⇒ 该 entry 的 "
            "OO 挂载点不再落在 mode 门控区域内，switch_verdict 从 redeemable 变 inert。"
            "只看挂载点自身标签块的实现在这条上会 GREEN。",
        scope_check=source_has_line("<template v-if=\"section === 'structured'\">"),
    ),
    Mutation(
        id="M18", side="be", path=HOST_B23, kind="replace",
        anchor='              <el-segmented v-model="editorMode" :options="modeOptions" size="small" />',
        new='              <el-segmented v-model="viewToggle" :options="modeOptions" size="small" />',
        want=f"{_SWITCH}::test_redeemable_switch_has_all_three_elements",
        wants=(f"{_SWITCH}::test_per_entry_verdicts_are_from_a_closed_enum_and_recompute",),
        why="🔴 mode token 覆盖面：`editorMode` 是真实变量名之一。把 v-model 换成不含 mode 的名字 "
            "⇒ 第三要素（mode 由开关写入）不成立。只认字面 `mode` 的实现在这条上会 GREEN。",
        scope_check=source_has_line(
            '<el-segmented v-model="viewToggle" :options="modeOptions" size="small" />'),
    ),

    # ── F 组：Property 22（本轮点名项 3）─────────────────────────────────
    Mutation(
        id="M19", side="be", path=HOST_B14, kind="replace",
        anchor='                    :key="col.key"',
        scope='                    v-for="col in getTableColumns(ch.id)"', offset=1,
        new='                    :key="col.label"',
        want=f"{_P22}::test_every_dynamic_column_keeps_key_and_label_separate",
        wants=(f"{_P22}::test_the_denominator_is_non_empty_and_recomputes",),
        why="🔴 AC 6.4 前半句：把列 key 换成可改 label ⇒ 重复 label 即键冲突。"
            "这条是 Property 22 的**正向**判据（key/label 必须解耦）。",
        scope_check=source_matches(r':key="col\.label"', 1),
    ),
    Mutation(
        id="M20", side="be", path=HOST_A38, kind="replace",
        anchor="            <el-table-column v-for=\"(_, i) in 5\" :key=\"i\" :label=\"`第${i + 1}年`\" align=\"right\">",
        new="            <el-table-column v-for=\"(_, i) in dcfYears\" :key=\"`year_${i}`\" :label=\"`第${i + 1}年`\" align=\"right\">",
        want=f"{_P22}::test_the_three_defects_are_real_and_registered",
        why="🔴 **反向变异**：把写死 5 列 + 下标作 key 改成动态列 + `{slot}_{seq}` 稳定键 ⇒ "
            "P22-D1 可解除，登记必须跟着删。只验「新增缺陷」一个方向是半个判据。",
        scope_check=source_matches(r'v-for="\(_, i\) in dcfYears"', 1),
    ),
    Mutation(
        id="M21", side="be", path=HOST_B14, kind="replace",
        anchor="    { key: 'peer2', label: '对标公司2', width: 120 },",
        new="    { key: 'peer2', label: '对标公司2', width: 120 },\n    { key: 'peer3', label: '对标公司3', width: 120 },",
        want=f"{_P22}::test_the_three_defects_are_real_and_registered",
        why="🔴 **反向变异**：给行业对标表补第 3 家对标公司 ⇒ P22-D2 的「写死 2 家」不再成立。"
            "🔴 用 `replace` 而不是在数组末插入（避免尾逗号把 JSON/TS 弄坏的同型问题）。",
        scope_check=source_matches(r"key: 'peer3'", 1),
    ),
    Mutation(
        id="M22", side="be", path=HOST_B50, kind="replace",
        anchor='              <template v-for="(row, rowIdx) in accounts" :key="row.name">',
        new='              <template v-for="(row, rowIdx) in accounts" :key="row.code">',
        want=f"{_P22}::test_the_three_defects_are_real_and_registered",
        wants=(f"{_P22}::test_the_denominator_is_non_empty_and_recomputes",
               f"{_ROWS}::test_defect_tables_source_refs_carry_the_expected_tokens"),
        why="🔴 **反向变异**：把可改科目名换成稳定 code 作 key ⇒ P22-D3 与 "
            "`b50_account_assertion_matrix_rows` 的 DEFECT 都可解除。",
        scope_check=source_matches(r':key="row\.code"', 1),
    ),

    # ── G 组：AC 1.4 挂载与共享载体（反向变异）───────────────────────────
    Mutation(
        id="M23", side="be", path=HOST_A101, kind="insert",
        anchor='    <GtOnlyOfficeSheet v-else :wp-id="props.wpId" sheet-name="A10-1" class="gt-a101__oo" />',
        new='    <GtEntrySyncCapabilityNotice :entry-id="\'xlsx/gt-a101-governance-communication\'" />',
        want=f"{_ADJ}::test_ac14_notice_single_source_exists_and_is_consumed_out_of_scope",
        wants=(f"{_SWITCH}::test_switch_counters_recompute",),
        why="🔴 **反向变异**：在宿主里真挂上 AC 1.4 的 notice 组件 ⇒ BP-7 对该 entry 可解除，"
            "`entries_mounting_the_ac14_notice` 从 0 变 1。登记不跟着改就必须打红。",
        scope_check=source_matches(r"<GtEntrySyncCapabilityNotice", 1),
    ),
    Mutation(
        id="M24", side="be", path=HOST_CCTL, kind="insert",
        anchor="<script setup lang=\"ts\">",
        new="import { useWpDualMode } from './composables/useWpDualMode'",
        want=f"{_DEL}::test_delete_after_rewire_is_non_empty_and_justified",
        wants=(f"{_CARRIER}::test_shared_carrier_edges_recompute_both_ways",
               f"{_CARRIER}::test_orphan_after_rewire_is_exactly_one",
               f"{_DEL}::test_plan_counters_recompute"),
        why="🔴 **反向变异**（另一形态）：给 `useWpDualMode.ts` 加一条**本 slice 内**的新生产边 "
            "⇒ 它的 in_scope/production 边数都 +1，`delete_after_rewire` 的边数声明立刻过时。"
            "这条同时证明共享载体的边数是**现算**而非快照。",
        scope_check=source_matches(r"from './composables/useWpDualMode'", 1),
    ),
    Mutation(
        id="M25", side="be", path=HOST_B1KAA, kind="replace",
        anchor="import { useWpDualMode } from './composables/useWpDualMode'",
        new="import { useWorkpaperEntryDualMode } from './composables/useWorkpaperEntryDualMode'",
        want=f"{_CARRIER}::test_shared_carrier_edges_recompute_both_ways",
        wants=(f"{_DEL}::test_delete_after_rewire_is_non_empty_and_justified",
               f"{_DEL}::test_plan_counters_recompute",
               f"{_FORM}::test_ad10_shared_base_edges_are_recomputed_not_copied"),
        why="把三个 B1 宿主里的一条 import 改指到共享基类 ⇒ `useWpDualMode.ts` 的生产边 3→2、"
            "共享基类 26→27。🔴 判据是**路径解析**口径（禁 stem 相等），故必须改 import 路径"
            "而不是改导出符号名 —— 首版写成「改 `export function` 名」实测判 GREEN：路径没变、"
            "边数没变，那是**无效变异**而不是守卫缺陷。",
        scope_check=source_has_line(
            "import { useWorkpaperEntryDualMode } from './composables/useWorkpaperEntryDualMode'"),
    ),
    Mutation(
        id="M26", side="be", path=REGISTRY_TS, kind="replace",
        anchor="    componentType: 'confirmation-summary',",
        new="    componentType: 'confirmation-summary-x',",
        want=f"{_AC16}::test_component_types_and_workbooks_recompute",
        wants=(f"{_AC16}::test_wp_codes_per_component_type_recompute",
               f"{_AC16}::test_reuse_arithmetic_recomputes_and_is_not_a_vacuous_denominator"),
        why="🔴 真源码变异：函证族的 componentType 集合必须从 registry **现读**。"
            "改一个名字 ⇒ 22 个的集合等值不成立，且 `confirmation-summary` 那 7 个循环的"
            "复用算术随之变化。",
        scope_check=source_has_line("componentType: 'confirmation-summary-x',"),
    ),
    Mutation(
        id="M27", side="be", path=OVERRIDES, kind="replace",
        anchor='  "L0-1": "confirmation-summary",',
        new='  "L0-1": "confirmation-followup",',
        want=f"{_AC16}::test_wp_codes_per_component_type_recompute",
        wants=(f"{_AC16}::test_reuse_arithmetic_recomputes_and_is_not_a_vacuous_denominator",),
        why="🔴 真源码变异 + CJK 陷阱：把 L0-1 换挂到另一个 componentType ⇒ "
            "`confirmation-summary` 的循环数 7→6、`confirmation-followup` 6→7，复用算术两侧都动。"
            "提取器若用 `\\b` 分词（CJK 算 `\\w`）会 0 命中而 GREEN。",
        scope_check=lambda data: json.loads(data.decode("utf-8"))["L0-1"] == "confirmation-followup",
    ),

    # ── I 组：Property 70 / 兄弟 slice / plan ────────────────────────────
    Mutation(
        id="M28", side="be", path=SLICE, kind="replace",
        anchor='  "backend/data/workpaper_sync_m_cycle_manifest_slice.json",',
        new='  "backend/data/workpaper_sync_zz_cycle_manifest_slice.json",',
        want=f"{_P70}::test_sibling_slices_declared_match_the_disk",
        why="🔴 有序等值 + 无重复双断言（Task 55 的 M23 教训）：把一份兄弟 slice 换成不存在的"
            "路径 ⇒ 与磁盘现算不符。只逐元素比或只比长度的实现在这条上会 GREEN。",
        scope_check=lambda data: (
            "backend/data/workpaper_sync_zz_cycle_manifest_slice.json"
            in _doc(data)["sibling_slices"]),
    ),
    Mutation(
        id="M29", side="be", path=SLICE, kind="replace",
        anchor='  "slice_count_including_self": 12',
        new='  "slice_count_including_self": 11',
        want=f"{_P70}::test_all_slices_are_pairwise_disjoint",
        why="🔴 配对数必须**现算** `C(n,2)`；把 slice 数改小 ⇒ 与磁盘现扫的份数不符。"
            "写死 66 的实现在这条上会 GREEN（因为 66 仍在 recipe 文本里）。",
        scope_check=doc_path_is(("cross_entry_isolation", "slice_count_including_self"), 11),
    ),
    Mutation(
        id="M30", side="be", path=PLAN, kind="replace",
        anchor='  "delete_after_rewire": 1,',
        new='  "delete_after_rewire": 2,',
        want=f"{_DEL}::test_plan_counters_recompute",
        why="plan 计数手改 ⇒ 与清单长度不符。这条守住「空/非空都要现算」而不是「非空即通过」。",
        scope_check=doc_path_is(("counters", "delete_after_rewire"), 2),
    ),
    Mutation(
        id="M31", side="be", path=PLAN, kind="replace",
        anchor='   "path": "audit-platform/frontend/src/components/workpaper/composables/useWorkpaperEntryDualMode.ts",',
        new='   "path": "audit-platform/frontend/src/components/workpaper/composables/useNonexistentDualMode.ts",',
        want=f"{_DEL}::test_must_not_delete_files_all_exist",
        why="`must_not_delete` 的路径必须真存在（否则「保护清单」保护的是不存在的文件）。",
        scope_check=source_matches(r"useNonexistentDualMode\.ts", 1),
    ),

    # ── J 组：业务模型投影（本轮点名项 4）与形态差异 ─────────────────────
    Mutation(
        id="M32", side="be", path=SLICE, kind="replace",
        anchor='    "wp_code_count": 32,',
        new='    "wp_code_count": 31,',
        want=f"{_BIZ}::test_program_and_control_wp_code_counts_recompute",
        why="程序表族的 wp_code 数必须从 override 表现算（32 个，含 F0A/G0A/H0A/K0A/L0A）。"
            "改一个数就必须打红，否则「只投影既有业务模型」这条没有可核对的分母。",
        scope_check=source_matches(r'"wp_code_count": 31,', 1),
    ),
    Mutation(
        id="M33", side="be", path=SLICE, kind="replace",
        anchor='   "new_business_fields_invented": 0',
        new='   "new_business_fields_invented": 1',
        want=f"{_BIZ}::test_every_family_is_project_only_and_invents_no_field",
        why="🔴 「不得新造业务字段」必须是硬判据：改成 1 ⇒ 守卫立刻打红。"
            "若守卫只读文字说明而不断言这个数，这条会 GREEN。",
        scope_check=doc_path_is(
            ("business_model_projection", "counters", "new_business_fields_invented"), 1),
    ),
    Mutation(
        id="M34", side="be", path=SLICE, kind="replace",
        anchor='    "production": 26,',
        new='    "production": 29,',
        want=f"{_FORM}::test_ad10_shared_base_edges_are_recomputed_not_copied",
        wants=(f"{_CARRIER}::test_shared_carrier_edges_recompute_both_ways",),
        why="🔴 AD-10：共享基类边数**每轮现算**（M 那轮冻结 29）。把它改回 29 = 「照抄上一轮」"
            "的确切形态 ⇒ 守卫必须打红。这条正是 Task 56 复盘里点名的漂移。",
        scope_check=lambda data: any(
            d["value"].get("production") == 29
            for d in _doc(data)["abcs_form_differences"] if d["id"] == "AD-10"),
    ),
    Mutation(
        id="M35", side="be", path=SLICE, kind="replace",
        anchor='   "denominator_is_empty": true,',
        scope='  "property_3": {', offset=5,
        new='   "denominator_is_empty": false,',
        want=f"{_P69}::test_property_denominators_declare_what_is_not_claimed",
        why="🔴 空分母不得宣称通过：把 Property 3 的空分母标成非空 ⇒ 与 `denominator_value == 0` "
            "矛盾，守卫必须打红。这条守的是「空分母重言式」这个本 spec 明确拒绝的论证。",
        scope_check=lambda data: (
            _doc(data)["property_denominators"]["property_3"]["denominator_is_empty"] is False),
    ),
    Mutation(
        id="M36", side="be", path=SLICE, kind="replace",
        anchor='   "denominator_is_empty": false,',
        scope='  "property_22": {', offset=5,
        new='   "denominator_is_empty": true,',
        want=f"{_P22}::test_the_verdict_does_not_overclaim",
        wants=(f"{_P69}::test_property_denominators_declare_what_is_not_claimed",),
        why="🔴 分母非空但有缺陷 ⇒ 结论必须是 PARTIAL。把 Property 22 的分母标成「空」"
            "⇒ 与 `denominator_value > 0` 矛盾，且过度宣称的门就此打开，守卫必须打红。",
        scope_check=lambda data: (
            _doc(data)["property_denominators"]["property_22"]["denominator_is_empty"] is True),
    ),
    Mutation(
        id="M37", side="be", path=SLICE, kind="replace",
        anchor='     "kind": "mutable_account_name_as_render_key_and_dom_selector",',
        new='     "kind": "label_text",',
        want=_CONTRACT,
        wants=(f"{_ROWS}::test_section_declares_forbidden_kinds_and_no_table_uses_them",
               f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator"),
        why="把 `row_identity.kind` 直接写成 `forbidden_identity_kinds` 里的值 ⇒ 范式校验器的"
            "条件节判据必须咬住（禁行身份用下标/序号/label）。",
        scope_check=lambda data: any(
            t["row_identity"]["kind"] == "label_text"
            for t in _doc(data)["dynamic_row_identity"]["tables"]),
    ),
    Mutation(
        id="M38", side="be", path=SLICE, kind="replace",
        anchor='    "excluded_reason_class": "confirmation_family_shared_across_cycles_no_entry",',
        scope='    "name": "D/D0 收入循环函证.xlsx",', offset=7,
        new='    "excluded_reason_class": "not_statically_resolved_by_any_in_scope_entry",',
        want=f"{_AC16}::test_confirmation_workbooks_are_registered_but_unowned",
        why="🔴 七本函证册的排除理由类别必须是专门的一类（它们是「跨循环共享无 entry」而不是"
            "「静态解析不到」）。混成同一类 ⇒ AC 1.6 的处置在数据上不可区分。",
        scope_check=lambda data: not any(
            f.get("excluded_reason_class") == "confirmation_family_shared_across_cycles_no_entry"
            for f in _doc(data)["authoritative_templates"]["files"]
            if f["name"].startswith("D/D0")),
    ),
    Mutation(
        id="M39", side="be", path=SLICE, kind="replace",
        anchor=' "task": "Task 57",',
        new=' "task": "Task 47",',
        want=f"{_PARA}::test_paradigm_refs_and_task_number_are_right",
        wants=(_CONTRACT, _COVERAGE),
        why="🔴 任务号驱动 `effective_from_task_48` 的追加必填推导：改成 47 ⇒ 追加项不再施加，"
            "等于**悄悄放宽**。守卫必须咬住任务号本身。",
        scope_check=doc_path_is(("task",), "Task 47"),
    ),
    Mutation(
        id="M40", side="be", path=SLICE, kind="replace",
        anchor='   "group_id": "GRP-13",', scope=S3, offset=1,
        new='   "group_id": "GRP-01",',
        want=f"{_GRP}::test_group_membership_recomputes_from_both_dimensions",
        why="把一条 S 类 entry 的 group_id 改到 A 类分组 ⇒ 分组归属与两维现算不符。"
            "这条守住「分组不是自由文本」。",
        scope_check=entry_field_is("xlsx/s3-policy-change/gt-s3-policy-change",
                                   "group_id", "GRP-01"),
    ),
]

GUARD_FILES = {
    T57: "Task 57 新建",
    _CONTRACT: "Task 45 冻结的范式校验器（本轮新 slice 进入其 scan_glob）",
    _COVERAGE: "Task 45/56 的覆盖面守卫（本轮分母 11 → 12）",
    "test_task56_n_cycle_migration.py": "Task 56（兄弟 slice 数与配对数随本轮变化）",
}

if __name__ == "__main__":
    raise SystemExit(run_cli(
        mutations=MUTATIONS,
        guard_files=GUARD_FILES,
        repo=REPO,
        backend_args=[
            "backend/tests/workpaper_sync/test_task57_abcs_and_shared_migration.py",
            "backend/tests/workpaper_sync/test_migration_paradigm_contract.py",
            "backend/tests/workpaper_sync/test_slice_schema_validator_coverage.py",
            "backend/tests/workpaper_sync/test_task56_n_cycle_migration.py",
            "-q", "--tb=no", "-rf", "-p", "no:randomly",
        ],
        baseline_backend_passed=None,
    ))
