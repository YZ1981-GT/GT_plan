# -*- coding: utf-8 -*-
r"""Task 60 守卫变异检验 —— F2-22 / F2-23 统一 Word adapter 的契约与发布记录。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 5 Task 60
用平台共享件 `backend/scripts/_mutation_kit`（`test_mutation_kit_adoption.py` 对新脚本强制
采纳）。`guard_files` 是签名层面必填的覆盖面分母。

═══ 本脚本的八条硬约束（前几轮踩出来的） ═══

1. **每条变异都带 `scope_check`**。四态判定式「新增失败集合是否为空」识别不出「锚点落在被测
   判据的作用域之外」—— 改到了别处会被判 GREEN（守卫缺陷），而真相是脚本缺陷。
   🔴 数据侧的 `scope_check` **必须解析 JSON 定位目标节**（Decision 14），不能用「文本里不存在
   某字面量」—— 同一字面量常出现在散文里 ⇒ 判据恒假 ⇒ ANCHOR-MISS。
2. 🔴 **`scope_check` 与锚点都禁用含 `\n` 的字面量**（Decision 17）：工作树是 CRLF，多行字面量
   恒假 ⇒ RED 会被误报成 ANCHOR-MISS。源码侧一律**按整行集合**断言。
3. 🔴 **`delete` 不用在 JSON 数组末元素上**（Decision 12）：删掉末元素会给前一行留下尾逗号、
   JSON 失效，`scope_check` 的 `json.loads` 抛异常 ⇒ 判定 ERROR（脚本缺陷而非守卫缺陷）。
   一律用 `replace`。
4. **重复形态字段用 `scope` + `offset` 相对定位，绝不用绝对行号**。发布记录里 entry 级字段
   dup=2（两个 entry 同形），一律以该 entry 唯一的 `"lane_entry_key": "…"` 行作 `scope`，
   `offset` 由一次性诊断**实算**。
5. **必须含反向变异**（把缺陷"修好"也要打红）：M18 把 `oo_mount_site_count` 改成 0（首版记录
   的错值）· M19 给挂载点补 `:descriptor` prop（BP-12/15 可解除 ⇒ xfail(strict) 转 XPASS 必红）·
   M20 把 `_UNJUDGED_SLICES` 从 `{}` 改成非空。
6. **真源码变异**（M21~M28）—— 数据侧变异只能证明「守卫读了 JSON」；只有改真源码还打红，
   才能证明 impl 侧是**现读**。本轮必须有源码变异撑着的判据有九类：① 权威 docx 字节
   （M21）· ② 载体探针门（M22）· ③ 生产契约清册（M23）· ④ 两个 writer 的 authority model
   （M24）· ⑤ 第二流程路由（M25）· ⑥ 前端挂载点与自取 config（M19/M26）· ⑦ callback 的
   lane 分支（M27）· ⑧ Task 59 fixture 形态（M28）· ⑨ 生成器的字段声明表（M29/M30）。
7. 🔴 **CJK 算 `\w`** ⇒ 提取 sheet 码禁用 `\b`（Decision 19）；M26 专门变异生产代码里的
   `"监盘计划F2-22"` 别名，验证守卫的 lookaround 口径真的在起作用。
8. 🔴 **「改符号名对『路径解析口径』的边数判据无效」**（Decision 23）：本脚本不靠改函数名去打
   「staged 目录无生产消费方」那条判据，而是**改 import/路径字面量本身**（M23）。

用法（仓库根；本仓库 PATH 上的 `python` 可能指向坏掉的解释器，必须用显式解释器）::

    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task60_f2_word_adapter_guards.py --list
    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task60_f2_word_adapter_guards.py --check-anchors
    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task60_f2_word_adapter_guards.py --run M01,M02

🔴 **禁止后台执行**：外层 shell 被杀会让 python 变成孤儿进程，与前台运行同时变异同一文件 ⇒
`RestoreFailed` rc=5。分批跑用 `--run M01,M02,...`（子集运行不做覆盖面结论）。
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
REC = "backend/data/workpaper_sync_f2_word_lane_publication.json"
CT_PLAN = "backend/data/workpaper_sync_word_contracts/f2.stocktake.plan.json"
CT_SUM = "backend/data/workpaper_sync_word_contracts/f2.stocktake.summary.json"
GENERATOR = "backend/scripts/gen/generate_task60_f2_word_contracts.py"
GUARD = "backend/tests/workpaper_sync/test_task60_f2_word_adapter.py"
COVERAGE_GUARD = "backend/tests/workpaper_sync/test_slice_schema_validator_coverage.py"
CARRIER = "backend/data/onlyoffice_word_sdt_carrier_contract.json"
REGISTRY_PY = "backend/app/services/workpaper_sync/adapters/registry.py"
PLAN_WRITER = "backend/app/routers/wp_render_strategies/_f2_stocktake_plan_sync.py"
SUM_WRITER = "backend/app/routers/wp_render_strategies/_f2_stocktake_summary_sync.py"
OO_ROUTER = "backend/app/routers/wp_onlyoffice_router.py"
FE = "audit-platform/frontend/src/components/workpaper"
HOST_VUE = f"{FE}/GtF2StocktakeBundle.vue"
OO_SHEET_VUE = f"{FE}/GtOnlyOfficeSheet.vue"
T59_GUARD = "backend/tests/workpaper_sync/test_task59_word_sdt_engine.py"

# ── 期望打红的守卫（文件::类::方法，与 pytest 的 short nodeid 同形）─────────
T60 = "test_task60_f2_word_adapter.py"
_SELF = f"{T60}::TestGuardSelfChecks"
_PARA = f"{T60}::TestParadigmIsReadOnly"
_REF = f"{T60}::TestSourceRefThreeWayLock"
_CNT = f"{T60}::TestCountersRecomputeFromEntries"
_ZERO = f"{T60}::TestSixZeroFamiliesAreNonVacuous"
_P31 = f"{T60}::TestProperty31WordOnlyPreserved"
_P32 = f"{T60}::TestProperty32DuplicateWordInstances"
_P4769 = f"{T60}::TestProperty47AndProperty69AreNotClaimed"
_AC = f"{T60}::TestAcceptanceCriteria"
_RUNTIME = f"{T60}::TestNothingUnapprovedReachesTheRuntime"
_SLICE = f"{T60}::TestSliceInvariantsAreUntouched"
_ISO = f"{T60}::TestCrossEntryIsolation"
_T59C = f"{T60}::TestTask59Compatibility"
_BP10 = f"{T60}::test_bp10_the_lane_contracts_are_installed_into_the_production_inventory"
_BP11 = f"{T60}::test_bp11_the_planned_bundle_slots_pass_the_production_gate"
_BP12 = f"{T60}::test_bp12_the_lane_mount_consumes_a_descriptor"
_BP14 = f"{T60}::test_bp14_the_lane_extract_no_longer_depends_on_chinese_headings"
_CONTRACT_GUARD = "test_migration_paradigm_contract.py"
_COVERAGE = "test_slice_schema_validator_coverage.py"
_T59 = "test_task59_word_sdt_engine.py"

# ── entry 级重复形态字段的相对定位锚点（dup=2）───────────────────────────────
#: 每个 entry 唯一的 scope 行（发布记录用 indent=2 落盘 ⇒ entry 级字段 6 空格缩进）。
LANE_PLAN = '      "lane_entry_key": "word-lane/f2-22-stocktake-plan",'
LANE_SUM = '      "lane_entry_key": "word-lane/f2-23-stocktake-summary",'

#: 逐字段 offset —— 由一次性诊断**实算**（非估计值），见 `--check-anchors`。
OFF_TEMPLATE_SHA = 7
OFF_MANIFEST_STATE = 9


# ══════════════════════════════════════════════════════════════════════════
# scope_check 工具：数据侧一律解析 JSON 定位目标节（Decision 14）
# ══════════════════════════════════════════════════════════════════════════
def _doc(data: bytes) -> dict:
    return json.loads(data.decode("utf-8"))


def _entry(data: bytes, sheet_code: str) -> dict:
    for entry in _doc(data)["entries"]:
        if entry["sheet_code"] == sheet_code:
            return entry
    raise AssertionError(f"变异后的记录里找不到 entry {sheet_code}")


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


def entry_path_is(sheet_code: str, path: tuple[Any, ...], expected: Any):
    def check(data: bytes) -> bool:
        node: Any = _entry(data, sheet_code)
        for key in path:
            try:
                node = node[key]
            except (KeyError, IndexError, TypeError):
                return False
        return node == expected

    return check


def field_evidence_path_is(sheet_code: str, stable_key: str, path: tuple[Any, ...], expected: Any):
    def check(data: bytes) -> bool:
        rows = _entry(data, sheet_code)["field_evidence"]
        row = next((r for r in rows if r["stable_field_key"] == stable_key), None)
        if row is None:
            return False
        node: Any = row
        for key in path:
            try:
                node = node[key]
            except (KeyError, IndexError, TypeError):
                return False
        return node == expected

    return check


def contract_field_path_is(stable_key: str, path: tuple[Any, ...], expected: Any):
    def check(data: bytes) -> bool:
        fields = _doc(data)["fields"]
        row = next((f for f in fields if f["stable_field_key"] == stable_key), None)
        if row is None:
            return False
        node: Any = row
        for key in path:
            try:
                node = node[key]
            except (KeyError, IndexError, TypeError):
                return False
        return node == expected

    return check


def bp_field_is(bp_id: str, key: str, expected: Any):
    def check(data: bytes) -> bool:
        for bp in _doc(data)["blocking_preconditions"]:
            if bp["id"] == bp_id:
                return bp.get(key) == expected
        return False

    return check


def bp_absent(bp_id: str):
    def check(data: bytes) -> bool:
        return all(bp["id"] != bp_id for bp in _doc(data)["blocking_preconditions"])

    return check


# ── 源码侧：**按整行集合**断言（禁多行字面量；CRLF 下恒假）─────────────────
def _lines(data: bytes) -> list[str]:
    return [line.rstrip("\r").strip() for line in data.decode("utf-8", "replace").split("\n")]


def source_has_line(needle: str):
    def check(data: bytes) -> bool:
        return needle.strip() in _lines(data)

    return check


def source_lacks_line(needle: str):
    def check(data: bytes) -> bool:
        return needle.strip() not in _lines(data)

    return check


def source_matches(pattern: str, expected: int):
    """整文按行匹配计数（pattern 自身**不含** `\\n`）。"""
    rx = re.compile(pattern)

    def check(data: bytes) -> bool:
        return sum(1 for line in _lines(data) if rx.search(line)) == expected

    return check


def source_line_count_is(needle: str, expected: int):
    def check(data: bytes) -> bool:
        return _lines(data).count(needle.strip()) == expected

    return check


# ══════════════════════════════════════════════════════════════════════════
# 变异清单
# ══════════════════════════════════════════════════════════════════════════
_P47 = f"{_P4769}::test_property_47_premise_is_recomputed_from_the_frontend_source"
_COUNTERS = f"{_CNT}::test_every_counter_recomputes_from_the_entries"
_FIELD_TOTALS = f"{_CNT}::test_the_field_totals_are_non_vacuous_and_split_per_entry"
_SREF = f"{_REF}::test_every_source_ref_is_recomputable_from_the_docx"
_DIGEST = f"{_REF}::test_the_digest_chain_recomputes_from_the_authoritative_bytes"

MUTATIONS: list[Mutation] = [
    # ── A 组：descriptor 现算 / Property 47 不宣称（数据侧；含反向变异）────────
    Mutation(
        id="M01", side="be", path=REC, kind="replace",
        anchor='    "oo_mount_site_count": 1,',
        new='    "oo_mount_site_count": 0,',
        want=_P47,
        why="🔴 **反向变异**：0 正是首版发布记录的错值（「本 lane 没有 OO 挂载点」）。"
            "守卫必须从前端源码现算出 1 并打红 —— 否则那个假前提会被守卫当基线锁死。",
        scope_check=doc_path_is(("descriptor_consumption", "oo_mount_site_count"), 0),
    ),
    Mutation(
        id="M02", side="be", path=REC, kind="replace",
        anchor='    "descriptor_props_on_the_mount": [],',
        new='    "descriptor_props_on_the_mount": ["descriptor"],',
        want=_P47,
        wants=(_BP12,),
        why="声称挂载点已消费 descriptor（BP-12/BP-15 的解除态）。源码里现算仍是零 prop ⇒ "
            "必须打红；同时 xfail(strict) 的 BP-12 条不该因此转 XPASS。",
        scope_check=doc_path_is(
            ("descriptor_consumption", "descriptor_props_on_the_mount"), ["descriptor"]
        ),
    ),
    Mutation(
        id="M03", side="be", path=REC, kind="replace",
        anchor='    "oo_component_self_fetches_config": true,',
        new='    "oo_component_self_fetches_config": false,',
        want=_P47,
        why="「组件自行请求 config」是 Property 47 反例判据的核心事实；改成 false ⇒ "
            "与 GtOnlyOfficeSheet.vue 现读不符。",
        scope_check=doc_path_is(
            ("descriptor_consumption", "oo_component_self_fetches_config"), False
        ),
    ),
    Mutation(
        id="M04", side="be", path=REC, kind="replace",
        anchor='    "oo_component_self_fetch_line": 172,',
        new='    "oo_component_self_fetch_line": 171,',
        want=_P47,
        why="行号也要现算（差一行都不行）—— 否则「自取 config 在哪一行」退化成自由文本，"
            "将来那行被删掉也看不出来。",
        scope_check=doc_path_is(
            ("descriptor_consumption", "oo_component_self_fetch_line"), 171
        ),
    ),
    Mutation(
        id="M05", side="be", path=REC, kind="replace",
        anchor='    "router_callback_has_a_lane_specific_docx_branch": true,',
        new='    "router_callback_has_a_lane_specific_docx_branch": false,',
        want=_P47,
        why="BP-15 的第二条腿（callback 里的 F2-22/F2-23 docx 回写分支）必须现读 router 源码；"
            "改成 false ⇒ 与 `_save_wp_code in (\"F2-22\", \"F2-23\")` 的现读结果不符。",
        scope_check=doc_path_is(
            ("descriptor_consumption", "router_callback_has_a_lane_specific_docx_branch"),
            False,
        ),
    ),
    Mutation(
        id="M06", side="be", path=REC, kind="replace",
        anchor='      "claim": "NOT_CLAIMED_CARRIER_IS_A_COUNTEREXAMPLE",',
        new='      "claim": "PASS",',
        want=f"{_P4769}::test_not_claimed_is_registered_for_both",
        why="🔴 空分母/反例承载者的 Property 被改成宣称通过 —— 这正是「假绿第三源」的入口，"
            "守卫必须咬住「登记在 not_claimed 里的条目不得写 PASS」。",
        scope_check=doc_path_is(("properties_verified", "Property 47", "claim"), "PASS"),
    ),
    Mutation(
        id="M07", side="be", path=REC, kind="replace",
        anchor='      "denominator": 1,',
        new='      "denominator": 0,',
        want=_P47,
        why="🔴 **反向变异**：把 Property 47 的分母改回首版的 0（「无承载者」）。"
            "现算挂载点是 1 ⇒ 必须打红，否则「空分母」这个借口能一直用下去。",
        scope_check=doc_path_is(("properties_verified", "Property 47", "denominator"), 0),
    ),
    Mutation(
        id="M08", side="be", path=REC, kind="replace",
        anchor='      "Property 47",',
        new='      "Property 470",',
        want=f"{_P4769}::test_not_claimed_is_registered_for_both",
        why="把「不宣称」登记表里的条目改名 ⇒ 登记与 properties_verified 脱钩，"
            "Property 47 变成「没人登记它不宣称」。",
        scope_check=doc_path_is(("property_denominators", "not_claimed", 0), "Property 470"),
    ),
    # ── B 组：counters 全族现算等值（数据侧）──────────────────────────────
    Mutation(
        id="M09", side="be", path=REC, kind="replace",
        anchor='    "managed_fields_total": 33,',
        new='    "managed_fields_total": 32,',
        want=_COUNTERS, wants=(_FIELD_TOTALS,),
        why="受管字段总数手改 ⇒ 与 field_evidence 长度求和不符（counters 现算等值的主判据）。",
        scope_check=doc_path_is(("counters", "managed_fields_total"), 32),
    ),
    Mutation(
        id="M10", side="be", path=REC, kind="replace",
        anchor='    "multi_instance_fields_total": 2,',
        new='    "multi_instance_fields_total": 1,',
        want=_COUNTERS, wants=(_FIELD_TOTALS,),
        why="多实例字段数是 Property 32 的分母；改小它 ⇒ 与 occurrences>1 现算不符，"
            "且「异值冲突有两个对象」的分母被削弱。",
        scope_check=doc_path_is(("counters", "multi_instance_fields_total"), 1),
    ),
    Mutation(
        id="M11", side="be", path=REC, kind="replace",
        anchor='    "block_carrier_fields_total": 2,',
        new='    "block_carrier_fields_total": 1,',
        want=_COUNTERS, wants=(_FIELD_TOTALS,),
        why="block 载体字段数证明「两种载体都真用到」；改小它 ⇒ 与 carrier 现算不符。",
        scope_check=doc_path_is(("counters", "block_carrier_fields_total"), 1),
    ),
    Mutation(
        id="M12", side="be", path=REC, kind="replace",
        anchor='    "row_scoped_fields_total": 0,',
        new='    "row_scoped_fields_total": 1,',
        want=_COUNTERS,
        wants=(f"{_REF}::test_row_scoped_total_is_zero_because_the_documents_have_no_rows",),
        why="行域字段数必须由**现读文档**（0 w:tbl / 0 w:tr）与契约（0 repeaters）双向证明；"
            "手写 1 ⇒ 两侧都对不上。",
        scope_check=doc_path_is(("counters", "row_scoped_fields_total"), 1),
    ),
    Mutation(
        id="M13", side="be", path=REC, kind="replace",
        anchor='    "second_pipeline_endpoints_deleted": 0,',
        new='    "second_pipeline_endpoints_deleted": 2,',
        want=_COUNTERS,
        wants=(
            f"{_ZERO}::test_second_pipeline_endpoints_deleted_is_zero_and_the_routes_are_still_there",
        ),
        why="🔴 AC 12.7：本轮不删任何调用点。声称删了 2 条 ⇒ 与「四条路由仍在源码里现读得到」"
            "矛盾。这条守住「删除计数不是自述」。",
        scope_check=doc_path_is(("counters", "second_pipeline_endpoints_deleted"), 2),
    ),
    Mutation(
        id="M14", side="be", path=REC, kind="replace",
        anchor='    "contracts_installed_into_production_inventory": 0,',
        new='    "contracts_installed_into_production_inventory": 2,',
        want=_COUNTERS,
        wants=(
            f"{_ZERO}::test_contracts_installed_into_production_inventory_is_zero_but_the_scan_works",
        ),
        why="声称契约已装进生产清册 ⇒ 与 contracts.available_contract_ids() 现扫不符（BP-10 被绕过）。",
        scope_check=doc_path_is(
            ("counters", "contracts_installed_into_production_inventory"), 2
        ),
    ),
    Mutation(
        id="M15", side="be", path=REC, kind="replace",
        anchor='    "definition_bundles_published": 0,',
        new='    "definition_bundles_published": 2,',
        want=_COUNTERS,
        why="声称 bundle 已发布，而 entries 里 definition_bundle 仍是 null ⇒ 现算取补必红。"
            "这条是「四个 0 不得解读为已具备双向能力」的守门。",
        scope_check=doc_path_is(("counters", "definition_bundles_published"), 2),
    ),
    Mutation(
        id="M16", side="be", path=REC, kind="replace",
        anchor='    "adapters_registered": 0,',
        new='    "adapters_registered": 2,',
        want=_COUNTERS,
        wants=(f"{_ZERO}::test_adapters_registered_is_zero_and_the_registry_has_no_lane_row",),
        why="声称 adapter 已注册 ⇒ 与 registry 现算（registered_adapter_ids 里没有本 lane）不符。",
        scope_check=doc_path_is(("counters", "adapters_registered"), 2),
    ),
    Mutation(
        id="M17", side="be", path=REC, kind="replace",
        anchor='      "F2-22": 17,',
        new='      "F2-22": 18,',
        want=_COUNTERS, wants=(_FIELD_TOTALS,),
        why="逐 entry 字段数与 field_evidence 长度双向等值；改一个 ⇒ 分项与总和同时对不上。",
        scope_check=doc_path_is(("counters", "managed_fields_by_entry", "F2-22"), 18),
    ),
    Mutation(
        id="M18", side="be", path=REC, kind="replace",
        anchor='    "lane_entries": 2,',
        new='    "lane_entries_x": 2,',
        want=_COUNTERS,
        wants=(f"{_CNT}::test_counting_notes_covers_every_numeric_key",),
        why="🔴 计数**键名**改掉 ⇒ ① 键集合现算等值必红 ② counting_notes 的覆盖面元判据"
            "（它提到的键必须覆盖全部数值键）也必红。这条同时验两层。",
        scope_check=lambda data: "lane_entries_x" in _doc(data)["counters"]
        and "lane_entries" not in _doc(data)["counters"],
    ),
    # ── C 组：契约的 source_ref 三边锁（数据侧，两份契约都动到）─────────────
    Mutation(
        id="M19", side="be", path=CT_PLAN, kind="replace",
        anchor='      "source_ref": "F2-22!p01+04:${entityName}",',
        new='      "source_ref": "F2-22!p04:${entityName}",',
        want=_SREF, wants=(_DIGEST,),
        why="🔴 AC 7.4「列出全部 OO 位置」：两实例字段只写一个段落序号 ⇒ 与现读的 [1,4] 不等值。"
            "这条正是三边锁里「磁盘真读」那一边在起作用的证据。",
        scope_check=contract_field_path_is(
            "plan/entity_name", ("source_ref",), "F2-22!p04:${entityName}"
        ),
    ),
    Mutation(
        id="M20", side="be", path=CT_PLAN, kind="replace",
        anchor='      "instances": "many"',
        new='      "instances": "one"',
        want=_SREF, wants=(_DIGEST,),
        why="实例基数改成 one ⇒ 与现算出现 2 次不符。若守卫只比 source_ref 不比 instances，"
            "「多实例合并/冲突」的下游判据就会拿到错的基数。",
        scope_check=contract_field_path_is("plan/entity_name", ("instances",), "one"),
    ),
    Mutation(
        id="M21", side="be", path=CT_PLAN, kind="replace",
        anchor='      "sdt_tag": "gt:field:f2.stocktake.plan:plan/entity_name",',
        new='      "sdt_tag": "gt:field:f2.stocktake.summary:plan/entity_name",',
        want=f"{_REF}::test_no_paragraph_or_run_ordinal_is_used_as_a_runtime_anchor",
        wants=(_DIGEST, f"{_ISO}::test_tags_of_one_entry_cannot_be_resolved_by_the_other_contract"),
        why="🔴 把 tag 的 contract 段指向**另一个 entry** ⇒ 跨 entry 复用（Property 70 禁止），"
            "且 WordEngineBinding.resolve_tag 会 fail closed。这条守住「一份文档的 tag 不可能"
            "被另一份契约解析」。",
        scope_check=contract_field_path_is(
            "plan/entity_name",
            ("sdt_tag",),
            "gt:field:f2.stocktake.summary:plan/entity_name",
        ),
    ),
    Mutation(
        id="M22", side="be", path=CT_PLAN, kind="replace",
        anchor='    "field_sdt_block",',
        new='    "row_sdt",',
        want=f"{_REF}::test_carriers_and_anchors_come_only_from_the_task6_gate",
        wants=(
            _DIGEST,
            f"{_SELF}::test_contract_validator_is_the_production_one_and_rejects_a_bad_carrier",
            f"{_REF}::test_no_paragraph_or_run_ordinal_is_used_as_a_runtime_anchor",
        ),
        why="🔴 Task 6 把 row_sdt 裁为 carriers_blocked（OO 9.4 上行级 SDT 不保留）。"
            "契约里出现它 ⇒ 载体门、生产校验器、否定式扫描三处都必须打红。",
        scope_check=lambda data: "row_sdt" in _doc(data)["identity_carriers"],
    ),
    Mutation(
        id="M23", side="be", path=CT_PLAN, kind="replace",
        anchor='  "review_status": "reviewed",',
        new='  "review_status": "candidate",',
        want=_COUNTERS,
        wants=(_DIGEST,),
        why="🔴 candidate 契约不得被当成已发布：`contracts_published_reviewed` 现算按 "
            "review_status=='reviewed' 计数 ⇒ 必须从 2 掉到 1；contract canonical digest 亦变。",
        scope_check=doc_path_is(("review_status",), "candidate"),
    ),
    Mutation(
        id="M24", side="be", path=CT_SUM, kind="replace",
        anchor='      "source_ref": "F2-23!p01+04:${entityName}",',
        new='      "source_ref": "F2-23!p01+05:${entityName}",',
        want=_SREF, wants=(_DIGEST,),
        why="第二份契约也要走同一条判据（否则「逐字段 33 条」的分母只有一半在被守）。"
            "把第二个段落序号改成 05 ⇒ 与现读的 [1,4] 不等值。",
        scope_check=contract_field_path_is(
            "summary/entity_name", ("source_ref",), "F2-23!p01+05:${entityName}"
        ),
    ),
    Mutation(
        id="M25", side="be", path=CT_PLAN, kind="replace",
        anchor='      "source_ref": "F2-22!p10:${warehouses}",',
        new='      "source_ref": "F2-22!p10:${warehouse}",',
        want=_SREF, wants=(_DIGEST,),
        why="token 改成磁盘上**不存在**的形态（少个 s）⇒ 「source_ref 指向磁盘上不存在的 token」"
            "这条必须打红。这条守的是「自造字段」方向。",
        scope_check=contract_field_path_is(
            "plan/warehouses", ("source_ref",), "F2-22!p10:${warehouse}"
        ),
    ),
    # ── D 组：生成器（声明侧 + impl 现读）─────────────────────────────────
    Mutation(
        id="M26", side="be", path=GENERATOR, kind="replace",
        anchor='    FieldDecl("${purpose}", "plan/purpose", "purpose", "text", "监盘目的"),',
        new='    FieldDecl("${purposes}", "plan/purpose", "purpose", "text", "监盘目的"),',
        want=f"{_REF}::test_declared_tokens_equal_the_tokens_on_disk",
        wants=(f"{_SELF}::test_the_generator_is_idempotent_against_the_artifacts_on_disk",),
        why="🔴 三边锁第一边（生成器的声明表）**现读**证明：改一个 token ⇒ 声明集合与磁盘集合"
            "不再双向等值。若守卫抄了一份字段表而不 import 生成器，这条会 GREEN。",
        scope_check=source_has_line(
            'FieldDecl("${purposes}", "plan/purpose", "purpose", "text", "监盘目的"),'
        ),
    ),
    Mutation(
        id="M27", side="be", path=GENERATOR, kind="replace",
        anchor="                \"carrier=='field_sdt_block' 计数；row_scoped_fields_total 由 repeaters 长度求和\"",
        new="                \"carrier=='field_sdt_block' 计数\"",
        want=f"{_SELF}::test_the_generator_is_idempotent_against_the_artifacts_on_disk",
        why="`counting_notes` 的正文由生成器拥有 ⇒ 改它而不重跑 --write，产物与现算就不一致。"
            "（覆盖面元判据本身的活性由守卫内的反向自检 + 「四项」基数断言撑着 —— 那两条不需要"
            "落盘变异就能证伪。）",
        scope_check=source_lacks_line(
            "\"carrier=='field_sdt_block' 计数；row_scoped_fields_total 由 repeaters 长度求和\""
        ),
    ),
    # ── E 组：真源码（证明 impl 侧是现读，不是快照）───────────────────────
    Mutation(
        id="M28", side="be", path=HOST_VUE, kind="replace",
        anchor="      <GtOnlyOfficeSheet",
        new="      <GtOoSheetRenamed",
        want=_P47,
        why="🔴 把 lane 宿主的 OO 挂载点改名 ⇒ 现算挂载点数从 1 掉到 0，与记录声明不符。"
            "**不能**改成 `<GtOnlyOfficeSheetX`：那仍含原子串，计数不变 = 无效变异。",
        scope_check=source_lacks_line("<GtOnlyOfficeSheet"),
    ),
    Mutation(
        id="M29", side="be", path=HOST_VUE, kind="replace",
        anchor="        v-if=\"dualMode.currentMode.value === 'onlyoffice'\"",
        new='        v-if="true"',
        want=_P47,
        why="去掉 mode 门控 ⇒ OO 挂载点变成常挂。`oo_mount_is_mode_gated` 是**现算**的，"
            "所以必须打红（若写成 declared-only，改掉门控会悄悄通过）。",
        scope_check=source_lacks_line(
            "v-if=\"dualMode.currentMode.value === 'onlyoffice'\""
        ),
    ),
    Mutation(
        id="M30", side="be", path=HOST_VUE, kind="replace",
        anchor="  { id: 'F2-22', label: '监盘计划' },",
        new="  { id: 'F2-22X', label: '监盘计划' },",
        want=_P47,
        why="F2-22 不再是该宿主的 tab ⇒ 「这个挂载点服务的正是本 lane 的两个 sheet」这条归属"
            "判据必须打红（否则挂载点归属是自述）。",
        scope_check=source_lacks_line("{ id: 'F2-22', label: '监盘计划' },"),
    ),
    Mutation(
        id="M31", side="be", path=OO_SHEET_VUE, kind="replace",
        anchor="    const configUrl = `/api/workpapers/${props.wpId}/sheets/${encodeURIComponent(props.sheetName)}/onlyoffice-config`",
        new="    const configUrl = `/api/workpapers/${props.wpId}/sheets/${encodeURIComponent(props.sheetName)}/oo-cfg`",
        want=_P47,
        why="🔴 组件不再自取 `/onlyoffice-config` ⇒ Property 47 反例判据的核心事实变了，"
            "守卫必须打红并要求重判（而不是继续拿旧结论当真）。",
        scope_check=source_lacks_line(
            "const configUrl = `/api/workpapers/${props.wpId}/sheets/${encodeURIComponent(props.sheetName)}/onlyoffice-config`"
        ),
    ),
    Mutation(
        id="M32", side="be", path=OO_ROUTER, kind="replace",
        anchor='            _save_wp_code in ("F2-22", "F2-23")',
        new='            _save_wp_code in ("F2-22",)',
        want=_P47,
        why="callback 里的 lane 分支形态变了（少了 F2-23）⇒ BP-15 登记的第二条腿与源码不符。"
            "这条同时证明守卫是**剥注释后**在源码里查，不是在注释里查。",
        scope_check=source_lacks_line('_save_wp_code in ("F2-22", "F2-23")'),
    ),
    Mutation(
        id="M33", side="be", path=PLAN_WRITER, kind="replace",
        anchor='        lane_id="f2_stocktake_plan",',
        new='        lane_id="custom_cells",',
        want=f"{_RUNTIME}::test_the_lane_writers_still_declare_the_pre_task60_authority_model",
        why="🔴 writer 的 authority model 被切走 ⇒ 记录里的 `currently_used_by_writer` / "
            "`switch_condition` 立刻过期，守卫必须打红。"
            "🔴 锚点随生产载体迁移（Task 65）：改造前的落点是 "
            "`authority_model=AuthorityModel.opaque_single_onlyoffice,`，那个参数已被删除 ⇒ "
            "锚点 ANCHOR-MISS。新载体是 `lane_id=` + lane 登记表。这里换成 `custom_cells`"
            "（登记的 authority model 是 `custom_authoritative_ooxml`）而不是原来的 "
            "`projection_contract`：后者经新载体已**结构性不可达** —— lane 登记表拒绝把 "
            "`projection_contract` 登记成 opaque lane（`assert_lane_self_consistent` 抛 "
            "`OpaqueAuthorityModelNotOpaqueError`，该拒绝由 test_task65_opaque_authority_"
            "bundle.py::test_projection_contract_lane_is_rejected 单独把守）。变异要证的那件事"
            "（authority model 一旦被切走、记录的 switch_condition 就过期）一字未变。",
        scope_check=source_has_line('lane_id="custom_cells",'),
    ),
    Mutation(
        id="M34", side="be", path=PLAN_WRITER, kind="replace",
        anchor='_SHEET_CODES = {"F2-22", "监盘计划F2-22"}',
        new='_SHEET_CODES = {"F2-22"}',
        want=f"{_SELF}::test_source_ref_regex_survives_cjk_word_boundaries",
        why="🔴 CJK 别名（`监盘计划F2-22`）是「为什么禁用 `\\b` 提码」这条自检的**真实对象**。"
            "删掉它 ⇒ 自检失去对象，守卫必须打红要求重新论证，而不是让理由悄悄变成假设。",
        scope_check=source_lacks_line('_SHEET_CODES = {"F2-22", "监盘计划F2-22"}'),
    ),
    Mutation(
        id="M35", side="be", path=REGISTRY_PY, kind="replace",
        anchor='        "blocking_task": "59,60,61",',
        new='        "blocking_task": "59,61",',
        want=f"{_ZERO}::test_adapters_registered_is_zero_and_the_registry_has_no_lane_row",
        why="🔴 pending Word engine adapter 的 `blocking_task` 去掉 60 ⇒ 本任务与那道门脱钩"
            "（「登记的阻塞必须真的把守发布门」这条判据失效）。",
        scope_check=source_has_line('"blocking_task": "59,61",'),
    ),
    Mutation(
        id="M36", side="be", path=COVERAGE_GUARD, kind="replace",
        anchor="_UNJUDGED_SLICES: dict[str, str] = {}",
        new='_UNJUDGED_SLICES: dict[str, str] = {"backend/data/workpaper_sync_f_cycle_manifest_slice.json": "本轮临时豁免"}',
        want=f"{_SLICE}::test_the_slice_coverage_guard_still_reports_no_unjudged_slices",
        why="🔴 `_UNJUDGED_SLICES` 必须保持 `{}`（本轮不新建 slice、也不豁免任何 slice）。"
            "塞一条豁免 ⇒ 「slice 侧三条前提不受本轮影响」的反向锁必须打红。",
        scope_check=source_lacks_line("_UNJUDGED_SLICES: dict[str, str] = {}"),
    ),
    Mutation(
        id="M37", side="be", path=T59_GUARD, kind="insert",
        anchor='PLAN_ID = "f2.stocktake.plan"',
        new='_STAGED_DIR_PROBE = "workpaper_sync_word_contracts"',
        want=f"{_T59C}::test_task59_guard_file_still_exists_and_uses_its_own_fixture",
        why="Task 59 一旦开始读 staged 契约目录，「两份真源共存不冲突」的结论就要重判。"
            "用 insert 而不是改 fixture 名：后者会连带打红 Task 59 自己几十条测试（噪声）。",
        scope_check=source_has_line('_STAGED_DIR_PROBE = "workpaper_sync_word_contracts"'),
    ),
    # ── F 组：slice 侧三条前提 / 权威册 / BP 结构（数据侧）──────────────────
    Mutation(
        id="M38", side="be", path=REC, kind="replace",
        anchor='      "slice_count_before_and_after_task_60": 12,',
        new='      "slice_count_before_and_after_task_60": 13,',
        want=f"{_SLICE}::test_slice_count_and_pairwise_count_are_recomputed_not_hardcoded",
        why="🔴 本轮**未新建**第 13 份 slice。声称 13 ⇒ 与 scan_glob 现扫的 12 不符。"
            "这条守住「slice 数与 Property 70 配对分母未被本轮扰动」。",
        scope_check=doc_path_is(
            (
                "why_not_a_cycle_manifest_slice",
                "denominators",
                "slice_count_before_and_after_task_60",
            ),
            13,
        ),
    ),
    Mutation(
        id="M39", side="be", path=REC, kind="replace",
        anchor='      "property_70_pairwise_count": 66,',
        new='      "property_70_pairwise_count": 78,',
        want=f"{_SLICE}::test_slice_count_and_pairwise_count_are_recomputed_not_hardcoded",
        why="78 = 13 份 slice 的配对数（若真新建了一份就会是它）。配方是 `len*(len-1)//2` **现算**，"
            "写死 78 ⇒ 必红。",
        scope_check=doc_path_is(
            ("why_not_a_cycle_manifest_slice", "denominators", "property_70_pairwise_count"),
            78,
        ),
    ),
    Mutation(
        id="M40", side="be", path=REC, kind="replace",
        anchor='      "excluded_from_slice_index": 0,',
        new='      "excluded_from_slice_index": 1,',
        want=f"{_SLICE}::test_the_f_cycle_slice_is_consumed_not_overturned",
        why="F 循环 slice 里委派 Tasks 60/61 的那条排除项下标改错 ⇒ 「消费而非改写 F slice」"
            "这条判据必须打红（否则委派关系是自述）。",
        scope_check=doc_path_is(
            ("why_not_a_cycle_manifest_slice", "f_slice_delegation", "excluded_from_slice_index"),
            1,
        ),
    ),
    Mutation(
        id="M41", side="be", path=REC, kind="replace",
        anchor='    "runtime_locator": "w:tag（sdt_tag）—— 唯一正式协议锚点",',
        new='    "runtime_locator": "paragraph_index（段落序号）",',
        want=f"{_REF}::test_no_paragraph_or_run_ordinal_is_used_as_a_runtime_anchor",
        why="🔴 把运行态锚点改成 Task 6 裁为 failed 的段落序号 ⇒ 直接违反 downstream_gate 的"
            "anchors_blocked。这是 Requirement 7.1「禁段落索引/正则定位」的守门。",
        scope_check=doc_path_is(
            ("source_ref_semantics", "runtime_locator"), "paragraph_index（段落序号）"
        ),
    ),
    Mutation(
        id="M42", side="be", path=REC, kind="replace",
        anchor='      "row_sdt"',
        new='      "row_sdt_typo"',
        want=f"{_REF}::test_carriers_and_anchors_come_only_from_the_task6_gate",
        why="记录里抄的 `carriers_blocked` 与探针 JSON 现读不一致 ⇒ 「载体白/黑名单只有一个真源」"
            "这条必须打红。",
        scope_check=doc_path_is(("probe_gate", "carriers_blocked"), ["row_sdt_typo"]),
    ),
    Mutation(
        id="M43", side="be", path=REC, kind="replace",
        anchor='      "id": "BP-15",',
        new='      "id": "BP-16",',
        want=f"{_AC}::test_every_blocking_precondition_is_well_formed",
        why="BP 编号集合是有序等值判据（BP-10..BP-15）；跳号 ⇒ 打红。"
            "这条防「新查出的缺陷随手换个号、与守卫/报告脱钩」。",
        scope_check=bp_absent("BP-15"),
    ),
    Mutation(
        id="M44", side="be", path=REC, kind="replace",
        anchor='    "delete_files": [],',
        new='    "delete_files": ["backend/app/routers/wp_render_strategies/_f2_stocktake_plan_sync.py"],',
        want=f"{_AC}::test_ac_12_7_keeps_the_second_pipeline_but_registers_the_plan",
        why="🔴 AC 12.7：删除前必须有等价证据与 rollback 点，本轮只生成计划。"
            "`delete_files` 一旦非空就等于宣称本轮要删 ⇒ 打红。",
        scope_check=lambda data: _doc(data)["second_pipeline_deletion_plan"]["delete_files"]
        == ["backend/app/routers/wp_render_strategies/_f2_stocktake_plan_sync.py"],
    ),
    Mutation(
        id="M45", side="be", path=REC, kind="replace",
        anchor='    "production_contract_dir_untouched": true',
        new='    "production_contract_dir_untouched": false',
        want=f"{_ZERO}::test_contracts_installed_into_production_inventory_is_zero_but_the_scan_works",
        why="声称动过生产契约目录 ⇒ 与「目录里没有本 lane 的文件」现读不符。",
        scope_check=doc_path_is(("cross_entry_isolation", "production_contract_dir_untouched"), False),
    ),
    Mutation(
        id="M46", side="be", path=REC, kind="replace",
        anchor='      "template_sha256": "f19aa64a9daa01022231d91f43d342a4ae973088dbd42b58459ad65c206662ba",',
        scope=LANE_PLAN, offset=OFF_TEMPLATE_SHA,
        new='      "template_sha256": "f19aa64a9daa01022231d91f43d342a4ae973088dbd42b58459ad65c206662bb",',
        want=_DIGEST,
        why="entry 级模板 digest 改一位 ⇒ 与 hashlib 现算不符（Requirement 6.10 / 9.9 的漂移 "
            "fail closed）。用 scope+offset 定位：该行在记录里 dup=3（entry / template payload / "
            "instrumentation payload）。",
        scope_check=entry_path_is(
            "F2-22",
            ("template_sha256",),
            "f19aa64a9daa01022231d91f43d342a4ae973088dbd42b58459ad65c206662bb",
        ),
    ),
    Mutation(
        id="M47", side="be", path=REC, kind="replace",
        anchor='      "manifest_entry_state": "absent_from_source_manifest",',
        scope=LANE_SUM, offset=OFF_MANIFEST_STATE,
        new='      "manifest_entry_state": "present_in_source_manifest",',
        want=f"{_RUNTIME}::test_bp10_root_cause_is_recomputable_from_the_source_manifest",
        wants=(f"{_SELF}::test_the_generator_is_idempotent_against_the_artifacts_on_disk",),
        why="🔴 BP-10 的根因是「本 lane 在 source-backed manifest 里没有 entry」。声称已有 entry ⇒ "
            "与 manifest 现算（F 前缀 docx entry 0 条）不符。"
            "**不能**把 want 写成 xfail(strict) 的 BP-10 条：那条读的是 available_contract_ids()，"
            "改一句 manifest_entry_state 不会让它转 XPASS —— 本脚本实测过一次 WRONG-TEST。",
        scope_check=entry_path_is(
            "F2-23", ("manifest_entry_state",), "present_in_source_manifest"
        ),
    ),
    # ── G 组：守卫自身（证明反向自检真的有效）──────────────────────────────
    Mutation(
        id="M48", side="be", path=GUARD, kind="replace",
        anchor="        return left == right",
        new="        return left.strip() == right.strip()",
        want=f"{_SELF}::test_verbatim_comparator_is_strip_sensitive",
        why="🔴 把本文件全域的字面量比较口径改成 strip 版 ⇒ 「文本字面量不得 strip」这条的"
            "**合成反例自检**必须打红。没有这条，本 lane 现算 0 条脏字面量的事实会让该规则"
            "变成纯装饰。",
        scope_check=source_has_line("return left.strip() == right.strip()"),
    ),
    Mutation(
        id="M49", side="be", path=GUARD, kind="replace",
        anchor='        "248808df9cade7e5d41a6ab8309acce47b5d7f973e85063a760c42889c790258",',
        new='        "248808df9cade7e5d41a6ab8309acce47b5d7f973e85063a760c42889c790259",',
        want=f"{_PARA}::test_four_blocks_are_frozen_both_by_raw_bytes_and_canonical_structure",
        why="改掉 `slice_schema` 那块的 raw 冻结值 ⇒ 范式四块双向锁必须打红。"
            "这条证明「范式 JSON 只读」不是注释，而且四块**每块**都真的在被比。",
        scope_check=source_has_line(
            '"248808df9cade7e5d41a6ab8309acce47b5d7f973e85063a760c42889c790259",'
        ),
    ),
    Mutation(
        id="M50", side="be", path=GUARD, kind="replace",
        anchor="    return list(declared) == list(computed)",
        new="    return sorted(map(str, declared)) == sorted(map(str, computed))",
        want=f"{_SELF}::test_declared_vs_computed_helper_checks_both_order_and_duplicates",
        why="🔴 Decision 18：集合层判据必须「有序等值 + 无重复」。改成排序后比较 ⇒ 换序不再被"
            "发现，自检必须打红。",
        scope_check=source_has_line(
            "return sorted(map(str, declared)) == sorted(map(str, computed))"
        ),
    ),
]

#: 覆盖面分母 —— 只列**本脚本真的会打红**的守卫文件。
#: 🔴 `test_task59_word_sdt_engine.py` 与 `test_migration_paradigm_contract.py` 都在
#: `backend_args` 里（用于发现附带损伤），但本脚本对它们只做「不该红」的旁证，不进分母：
#: 把永远不会被命中的文件写进分母，只会让覆盖面报告永久 incomplete。
GUARD_FILES = {
    T60: "Task 60 新建",
    _COVERAGE: "Task 45/56 的覆盖面守卫（本轮反向锁住 `_UNJUDGED_SLICES == {}` 与 slice 数 12）",
}

if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            backend_args=[
                "backend/tests/workpaper_sync/test_task60_f2_word_adapter.py",
                "backend/tests/workpaper_sync/test_migration_paradigm_contract.py",
                "backend/tests/workpaper_sync/test_slice_schema_validator_coverage.py",
                "backend/tests/workpaper_sync/test_task59_word_sdt_engine.py",
                "-q",
                "--tb=no",
                "-rf",
                "-p",
                "no:randomly",
            ],
            baseline_backend_passed=None,
        )
    )
