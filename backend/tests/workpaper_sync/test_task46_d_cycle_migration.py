"""
test_task46_d_cycle_migration — D 循环 Excel 独立 entry 迁移验证（2026-08-30 收口重写）

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 5 Task 46
Requirements: 1.4, 6.1, 6.2, 6.10, 9.1, 12.1, 12.4, 12.8, 12.9, 12.10, 12.11, 12.12, 14.1

验证 Properties:
  - Property 20: generated col 占位不可注册生产 adapter
  - Property 21: contract 字段完整
  - Property 28: immutable definition 漂移 fail closed
  - Property 69: evidence 由逐 scenario 实体与服务端重算闭合
  - Property 70: scenario/evidence 不得跨 entry 或跨场景复用

═══ 为什么整份重写 ═══

首轮这份守卫的核心逻辑写在 docstring 里，原文是：

    - 没有 bidirectional adapter → 没有 contract → Property 20/21 通过（无假 contract）
    - 没有 definition bundle → Property 28 通过（无可漂移 identity）

那是**空分母重言式**：同一个 spec 的 Task 20 专门写代码拒绝这种论证
（`WriterGateError("...would be evaluated over an empty denominator (a tautology)")`）。
而且 Property 28 对 D2 **有真分母** —— `workpaper_sync_contracts/d2.receivable_detail.json`
里的 `template_sha256` / `normalized_structure_hash` / `instrumentation_definition_sha256`
都能从权威模板字节现算复核，首轮一条都没验。

首轮还有四处 fail-open / 一处硬编码豁免：

1. `if tref: assert tpath.exists()` —— `template_ref` 为 null 时整条跳过；只查存在不查内容
   （实测：把某 entry 的 template_ref 置 null，36 例全绿）。
2. `if not contract_dir.exists(): return` —— 契约目录消失即通过。
3. `if not pilot_plan_path.exists(): pytest.skip(...)` —— skip 记为通过。
4. `if name.startswith("d2"): continue` —— 硬编码豁免，且它掩盖的恰是本次重裁的决定性反例
   （Task 20 的门明文禁止 "No exemption column."）。

收口后的判据一律落在**可复算的事实**上：AC 12.8 的裁决判据（有无 HTML 对端）、
模板 size+sha256 现算、契约 digest 现算、模板 sheet!cell 真读、宿主模板形态。

依赖：
  - backend/data/workpaper_sync_d_cycle_manifest_slice.json（frozen slice）
  - backend/data/workpaper_sync_d_cycle_deletion_plan.json（deletion plan）
  - backend/data/workpaper_sync_migration_paradigm.json（Task 45 范式，只读）
  - backend/data/workpaper_sync_entry_manifest.json（source-backed manifest）
  - backend/wp_templates/D/（运行时权威模板，唯一真源）
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys
from typing import Any

import pytest

# ────────────────────────────────────────────────────────────────────────────
# Paths
# ────────────────────────────────────────────────────────────────────────────
# __file__ = backend/tests/workpaper_sync/test_...py
# parents[0] = workpaper_sync/, [1] = tests/, [2] = backend/, [3] = repo root
_THIS = pathlib.Path(__file__).resolve()
ROOT = _THIS.parents[3]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "audit-platform" / "frontend" / "src"
WP_COMPONENTS = FRONTEND / "components" / "workpaper"
COMPOSABLES = WP_COMPONENTS / "composables"
SYNC_DIR = WP_COMPONENTS / "sync"
DATA = BACKEND / "data"

MANIFEST_SLICE_PATH = DATA / "workpaper_sync_d_cycle_manifest_slice.json"
DELETION_PLAN_PATH = DATA / "workpaper_sync_d_cycle_deletion_plan.json"
PARADIGM_PATH = DATA / "workpaper_sync_migration_paradigm.json"
FULL_MANIFEST_PATH = DATA / "workpaper_sync_entry_manifest.json"
E_SLICE_PATH = DATA / "workpaper_sync_e_cycle_manifest_slice.json"
CONTRACT_DIR = DATA / "workpaper_sync_contracts"
TEMPLATE_DIR = BACKEND / "wp_templates"
CHECKLIST_ROUTER = BACKEND / "app" / "routers" / "checklist_responses.py"

#: D2 是 D 循环唯一有 per-entry contract 的 entry（Task 41 pilot 交付）。
D2_ENTRY_ID = "xlsx/gt-d2-accounts-receivable"
D2_CONTRACT_PATH = CONTRACT_DIR / "d2.receivable_detail.json"

#: AC 1.3 的能力态枚举（真源在范式 JSON 的 adjudication_criteria.capability_enum）。
CAPABILITY_ENUM = ("bidirectional", "single_html", "single_onlyoffice", "unreachable")

#: step 3 的二值结论（真源在范式 JSON 的 anti_patterns[AP-1].allowed_verdict_values）。
HTML_COUNTERPART_VERDICTS = ("none", "exists")

#: AC 1.4 的 UI 义务落点。
NOTICE_MODULE = SYNC_DIR / "workpaperEntrySyncNotice.ts"
NOTICE_COMPONENT = SYNC_DIR / "GtEntrySyncCapabilityNotice.vue"
NOTICE_COMPONENT_NAME = "GtEntrySyncCapabilityNotice"

# Legacy composable paths（待 Task 66/72 删除；本任务只断言现状一致）
D_CYCLE_ENTRY_COMPOSABLES = {
    "D1": COMPOSABLES / "useD1EntryDualMode.ts",
    "D3": COMPOSABLES / "useD3EntryDualMode.ts",
    "D4": COMPOSABLES / "useD4EntryDualMode.ts",
    "D5": COMPOSABLES / "useD5EntryDualMode.ts",
    "D6": COMPOSABLES / "useD6EntryDualMode.ts",
    "D7": COMPOSABLES / "useD7EntryDualMode.ts",
}

SHARED_BASE = COMPOSABLES / "useWorkpaperEntryDualMode.ts"

PRESERVED_COMPOSABLES = [
    COMPOSABLES / "useD1DualMode.ts",
    COMPOSABLES / "useD3DualMode.ts",
    COMPOSABLES / "useD4DualMode.ts",
]


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────
def _load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_of(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _strip_ts_comments(source: str) -> str:
    """剥掉 TS/Vue 注释 —— 说明文字不得充当判据证据。

    🔴 剥完必须反向自检（见 test_strip_comments_self_check），剥过头会让判据恒真。
    """
    source = re.sub(r"/\*[\s\S]*?\*/", "", source)
    source = re.sub(r"(?m)^\s*//.*$", "", source)
    source = re.sub(r"(?m)//[^\n\"'`]*$", "", source)
    source = re.sub(r"<!--[\s\S]*?-->", "", source)
    return source


def _vue_template(source: str) -> str:
    """取 SFC 的**外层** template 区块。

    🔴 不能用 `source.split("</template>")[0]`：SFC 里嵌套的具名插槽
    （`<template #content>`）会先闭合，第一处 `</template>` 落在内层 ⇒ 截出来的片段
    比真实模板短，判据会把「已在模板里」误判成「不在模板里」。这里改用 `<script` 边界。
    """
    marker = source.find("<script")
    assert marker > 0, "找不到 <script 边界 —— 该文件不是常规 SFC（template 在 script 之前）"
    head = source[:marker]
    assert "<template>" in head, "SFC 头部没有 <template>"
    return head


def _cell_value(path: pathlib.Path, sheet: str, cell: str) -> Any:
    """openpyxl 真读权威模板的一个单元格（data_only）。"""
    import openpyxl
    from openpyxl.utils import column_index_from_string

    workbook = openpyxl.load_workbook(path, data_only=True)
    try:
        assert sheet in workbook.sheetnames, (
            f"{path.name} 里没有 sheet {sheet!r}；实有 {workbook.sheetnames}"
        )
        match = re.fullmatch(r"([A-Z]+)(\d+)", cell)
        assert match, f"非法单元格坐标 {cell!r}"
        return workbook[sheet].cell(
            row=int(match.group(2)),
            column=column_index_from_string(match.group(1)),
        ).value
    finally:
        workbook.close()


# ────────────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def manifest_slice() -> dict:
    return _load(MANIFEST_SLICE_PATH)


@pytest.fixture(scope="module")
def deletion_plan() -> dict:
    return _load(DELETION_PLAN_PATH)


@pytest.fixture(scope="module")
def paradigm() -> dict:
    return _load(PARADIGM_PATH)


@pytest.fixture(scope="module")
def full_manifest() -> dict:
    return _load(FULL_MANIFEST_PATH)


@pytest.fixture(scope="module")
def d2_contract() -> dict:
    assert D2_CONTRACT_PATH.is_file(), (
        f"{D2_CONTRACT_PATH} 必须存在 —— 它是 Task 41 的交付物，"
        "也是本次重裁的决定性反例（D2 有 HTML 对端）。缺文件不得当成「没有可验的东西」"
    )
    return _load(D2_CONTRACT_PATH)


# ════════════════════════════════════════════════════════════════════════════
# 判据自检 —— 判据本身不能恒真
# ════════════════════════════════════════════════════════════════════════════
class TestGuardSelfChecks:
    """反向自检：剥注释函数不能把代码一起剥掉，也不能什么都不剥。"""

    def test_strip_comments_self_check(self) -> None:
        sample = (
            "// leading line comment\n"
            "/* block */\n"
            "const KEEP = 'value' // trailing\n"
            "<!-- html comment -->\n"
            "const ALSO = 'x'\n"
        )
        stripped = _strip_ts_comments(sample)
        # 正向：注释真被剥掉
        for gone in ("leading line comment", "block", "trailing", "html comment"):
            assert gone not in stripped, f"{gone!r} 应被剥掉"
        # 反向：代码没被剥过头
        assert "const KEEP = 'value'" in stripped
        assert "const ALSO = 'x'" in stripped

    def test_all_required_artifacts_exist(self) -> None:
        """本文件依赖的每个真源都必须真存在 —— 缺文件一律 fail closed，不 skip。"""
        for path in (
            MANIFEST_SLICE_PATH,
            DELETION_PLAN_PATH,
            PARADIGM_PATH,
            FULL_MANIFEST_PATH,
            CONTRACT_DIR,
            TEMPLATE_DIR / "D",
            CHECKLIST_ROUTER,
            NOTICE_MODULE,
            NOTICE_COMPONENT,
        ):
            assert path.exists(), (
                f"{path} 不存在。缺真源必须打红：first-round 的 "
                "`if not contract_dir.exists(): return` / `pytest.skip(...)` 是 fail-open —— "
                "目录一消失判据就自动通过"
            )


# ════════════════════════════════════════════════════════════════════════════
# AC 12.8 / 12.9 / 12.1：裁决合法性（本次收口的核心）
# ════════════════════════════════════════════════════════════════════════════
class TestAdjudicationLegality:
    """
    **Validates: Requirements 12.8**

    AC 12.8 原文：「无 HTML 对端的纯 OO entry SHALL 标为 `single_onlyoffice`；
    不得为满足数字伪造字段映射或修改模板制造对端。」判据是**有没有 HTML 对端**，
    不是「adapter / contract / bundle 还不存在」。
    """

    def test_every_entry_has_a_binary_html_counterpart_verdict(
        self, manifest_slice: dict
    ) -> None:
        """step 3 必须产出二值结论；unresolved / unknown / 空值都不是结论（AP-3）。"""
        for entry in manifest_slice["independent_entries"]:
            verdict = entry.get("html_counterpart_verdict")
            assert verdict in HTML_COUNTERPART_VERDICTS, (
                f"{entry['entry_id']} 的 html_counterpart_verdict={verdict!r} 不是二值结论。"
                f"合法值只有 {HTML_COUNTERPART_VERDICTS}"
            )

    def test_single_onlyoffice_requires_no_html_counterpart(
        self, manifest_slice: dict
    ) -> None:
        """AC 12.8 的蕴含关系：single_onlyoffice ⇒ verdict == 'none'。"""
        for entry in manifest_slice["independent_entries"]:
            if entry.get("capability") == "single_onlyoffice":
                assert entry.get("html_counterpart_verdict") == "none", (
                    f"{entry['entry_id']} 裁为 single_onlyoffice 但 html_counterpart_verdict="
                    f"{entry.get('html_counterpart_verdict')!r}。AC 12.8 只允许「无 HTML 对端」"
                    "的 entry 标 single_onlyoffice"
                )

    def test_adjudication_reason_is_not_circular(self, manifest_slice: dict, paradigm: dict) -> None:
        """AP-1：不得用「本任务应交付的产物尚不存在」当裁决理由。

        判据取范式 JSON 登记的 `circular_reason_markers`（真源在范式，不在这里另写一份）。
        """
        markers = paradigm["adjudication_criteria"]["anti_patterns"][0]["circular_reason_markers"]
        assert markers, "circular_reason_markers 为空 ⇒ 判据恒真"
        for entry in manifest_slice["independent_entries"]:
            reason = entry["adjudication"]["reason"]
            hits = [m for m in markers if m in reason]
            assert not hits, (
                f"{entry['entry_id']} 的裁决理由命中循环论证标记 {hits}。"
                "缺什么写进 blocking_preconditions，不要当裁决依据"
            )

    def test_capability_is_enum_or_explicitly_pending(self, manifest_slice: dict) -> None:
        """AC 1.3：capability 只能是四个枚举值；当下没有一个成立时必须显式记 pending。

        🔴 这不是「允许留空」：capability 为 null 时必须同时给 `capability_verdict_stage`、
        `capability_target` 与非空 `capability_target_blocked_by`，并计入 unadjudicated。
        留空而不解释就是「未裁决伪装成已裁决」。
        """
        for entry in manifest_slice["independent_entries"]:
            capability = entry.get("capability")
            if capability is None:
                assert entry.get("capability_verdict_stage"), (
                    f"{entry['entry_id']} capability 为 null 却没有 capability_verdict_stage"
                )
                assert entry.get("capability_target") in CAPABILITY_ENUM, (
                    f"{entry['entry_id']} 的 capability_target 必须落在能力态枚举内"
                )
                blocked_by = entry.get("capability_target_blocked_by")
                assert isinstance(blocked_by, list) and blocked_by, (
                    f"{entry['entry_id']} capability 未定却没登记阻断项"
                )
            else:
                assert capability in CAPABILITY_ENUM, (
                    f"{entry['entry_id']} capability={capability!r} 不在 {CAPABILITY_ENUM}"
                )

    def test_capability_matches_honest_capability(self, manifest_slice: dict) -> None:
        """SR-4：对外 capability 与 adjudication.honest_capability 不得双口径。"""
        for entry in manifest_slice["independent_entries"]:
            assert entry.get("capability") == entry["adjudication"].get("honest_capability"), (
                f"{entry['entry_id']} capability 与 honest_capability 不一致"
            )

    def test_bidirectional_requires_all_five_identity_fields(
        self, manifest_slice: dict
    ) -> None:
        """SR-6 / AC 12.1：标 bidirectional 必须五个身份字段全非空。"""
        keys = (
            "adapter_id",
            "authority_model",
            "definition_bundle",
            "instrumentation_candidate",
            "published_representation",
        )
        for entry in manifest_slice["independent_entries"]:
            if entry.get("capability") == "bidirectional":
                for key in keys:
                    assert entry.get(key) is not None, (
                        f"{entry['entry_id']} 标 bidirectional 但 {key} 为空"
                    )

    def test_single_or_pending_entries_carry_no_identity(self, manifest_slice: dict) -> None:
        """SR-5 / AP-5：裁 single 或终态未定的 entry 不得挂身份字段（不伪造凑数）。"""
        keys = (
            "adapter_id",
            "authority_model",
            "definition_bundle",
            "instrumentation_candidate",
            "published_representation",
        )
        for entry in manifest_slice["independent_entries"]:
            capability = entry.get("capability")
            if capability == "bidirectional":
                continue
            for key in keys:
                assert entry.get(key) is None, (
                    f"{entry['entry_id']} capability={capability!r} 却挂了 {key}={entry[key]!r}"
                )

    def test_adjudication_carries_both_negative_reasons(self, manifest_slice: dict) -> None:
        """step 4 要求：not_single_html_because 与 not_bidirectional_because 都要写。"""
        for entry in manifest_slice["independent_entries"]:
            adjudication = entry["adjudication"]
            for key in ("not_single_html_because", "not_bidirectional_because"):
                assert len(adjudication.get(key, "")) > 40, (
                    f"{entry['entry_id']} 的 {key} 缺失或过短 —— 排除另外两个枚举值也要给理由"
                )


# ════════════════════════════════════════════════════════════════════════════
# HTML 对端事实的三边锁：slice ↔ 前端源码 ↔ 权威 xlsx
# ════════════════════════════════════════════════════════════════════════════
class TestHtmlCounterpartIsSourceBacked:
    """
    **Validates: Requirements 6.1, 12.8**

    「有 HTML 对端」这个结论不能是自由文本 —— 每条都要能在磁盘上复核。
    """

    def test_source_refs_point_at_real_paths(self, manifest_slice: dict) -> None:
        """每条 source_ref 的路径部分必须真存在（含 sheet!cell 形态的模板引用）。"""
        checked = 0
        for entry in manifest_slice["independent_entries"]:
            refs = entry.get("html_counterpart_source_refs")
            assert isinstance(refs, list) and len(refs) >= 4, (
                f"{entry['entry_id']} 的 html_counterpart_source_refs 太少（至少要有"
                "宿主 / 持久化 composable / 后端端点 / 模板单元格四类）"
            )
            for ref in refs:
                # 形如 path#L12 / path!sheet!cell = 'text' / 裸 path
                raw = ref.split("#")[0].split("!")[0].strip()
                candidate = ROOT / raw
                assert candidate.exists(), (
                    f"{entry['entry_id']} 的 source_ref {ref!r} 指向不存在的路径 {raw!r}"
                )
                checked += 1
        assert checked >= 28, f"source_ref 校验数 {checked} 太少 —— 分母可疑"

    def test_html_store_endpoints_exist_in_the_router(self, manifest_slice: dict) -> None:
        """slice 声称的读写端点必须真在 checklist_responses 路由里。"""
        router = CHECKLIST_ROUTER.read_text(encoding="utf-8")
        assert 'prefix="/api/workpapers/{wp_id}/checklist-responses"' in router
        assert '@router.get("", response_model=list[ChecklistResponseOut])' in router
        assert '@router.put("", response_model=list[ChecklistResponseOut])' in router
        assert "FROM checklist_responses" in router
        for entry in manifest_slice["independent_entries"]:
            store = entry["html_counterpart"]
            assert store["store"] == "checklist_responses"
            assert store["endpoint_read"].endswith("/checklist-responses")
            assert store["endpoint_write"].endswith("/checklist-responses")
            assert store["payload_column"] == "remark"

    def test_row_identity_key_is_not_positional(self, manifest_slice: dict) -> None:
        """行身份不得是数组下标/序号（AC 6.9 同族；stable row key 定义）。"""
        for entry in manifest_slice["independent_entries"]:
            store = entry["html_counterpart"]
            key = store["row_identity_key"]
            assert key == "rowId", f"{entry['entry_id']} 行身份键应为 rowId，实为 {key!r}"
            forbidden = store["forbidden_row_identity_kinds"]
            assert {"array_index", "ordinal", "position"} <= set(forbidden)

    def test_primary_table_is_declared_by_its_owner_module(self, manifest_slice: dict) -> None:
        """第二边：primary table 的 item_id 必须真由 owner 模块声明。

        `owner_constant` 非空 ⇒ 该模块必须有 `const <NAME> = '<item_id>'`；
        `owner_constant` 为 null（inline literal 形态）⇒ 字面量必须出现，且**不得**存在
        模块级常量声明（否则 slice 与源码脱钩，要更新 slice）。
        """
        for entry in manifest_slice["independent_entries"]:
            primary = entry["html_counterpart"]["primary_table"]
            module = ROOT / primary["owner_module"]
            assert module.is_file(), f"{entry['entry_id']} 的 owner_module 不存在: {module}"
            source = _strip_ts_comments(module.read_text(encoding="utf-8"))
            item_id = primary["item_id"]
            constant = primary["owner_constant"]
            const_pattern = re.compile(
                r"const\s+([A-Z0-9_]+)\s*=\s*['\"]" + re.escape(item_id) + r"['\"]"
            )
            found = const_pattern.search(source)
            if constant:
                assert primary["owner_declaration_kind"] == "module_constant"
                assert found, (
                    f"{entry['entry_id']}: {module.name} 里找不到 "
                    f"const {constant} = '{item_id}'"
                )
                assert found.group(1) == constant, (
                    f"{entry['entry_id']}: 常量名应为 {constant}，实为 {found.group(1)}"
                )
            else:
                assert primary["owner_declaration_kind"] == "inline_literal"
                assert f"'{item_id}'" in source, (
                    f"{entry['entry_id']}: {module.name} 里找不到字面量 '{item_id}'"
                )
                assert not found, (
                    f"{entry['entry_id']}: {module.name} 已把 '{item_id}' 提成模块常量 "
                    f"{found.group(1)}，slice 的 owner_declaration_kind 需同步更新"
                )

    def test_primary_table_identity_cell_matches_the_authoritative_template(
        self, manifest_slice: dict
    ) -> None:
        """第三边：primary table 的身份列表头必须与权威模板单元格逐字相等。"""
        for entry in manifest_slice["independent_entries"]:
            primary = entry["html_counterpart"]["primary_table"]
            template = TEMPLATE_DIR / primary["template_relative_path"]
            assert template.is_file(), (
                f"{entry['entry_id']} 的权威模板不存在: {template}"
            )
            actual = _cell_value(
                template, primary["template_sheet"], primary["identity_cell"]
            )
            expected = primary["identity_text"]
            assert actual is not None and str(actual).strip() == expected, (
                f"{entry['entry_id']}: {primary['template_sheet']}!"
                f"{primary['identity_cell']} 实测 {actual!r}，slice 记的是 {expected!r}"
            )

    def test_template_ref_resolves_through_the_runtime_index(
        self, manifest_slice: dict
    ) -> None:
        """template_ref 必须是运行时 finder 能拿到的文件（不在 _index.json 里的不算权威）。

        🔴 首轮 D4 的 template_ref 写的是 `D/D4收入底稿.xlsx` —— 磁盘上有，但不在
        `_index.json` 里，`find_template_file_any()` 对任何 D4 码都永不返回它。
        """
        index = _load(TEMPLATE_DIR / "_index.json")
        indexed = {
            str(f["relative_path"]).replace("\\", "/")
            for f in index["files"]
        }
        assert len(indexed) > 400, f"_index.json 只索引到 {len(indexed)} 个文件，可疑"
        for entry in manifest_slice["independent_entries"]:
            ref = entry.get("template_ref")
            assert ref, f"{entry['entry_id']} 的 template_ref 为空"
            assert ref in indexed, (
                f"{entry['entry_id']} 的 template_ref {ref!r} 不在 backend/wp_templates/_index.json 里 "
                "⇒ 运行时 finder 永不返回它，不能当权威模板"
            )


# ════════════════════════════════════════════════════════════════════════════
# Property 20 / 21：contract 与 adapter 的真判据（不用空分母）
# ════════════════════════════════════════════════════════════════════════════
class TestProperty20And21ContractAndAdapter:
    """
    **Validates: Requirements 6.1, 6.2**

    ═══ 空分母怎么处理 ═══

    「本 slice 里没有已注册 adapter，所以 Property 20/21 通过」是重言式。诚实的写法是
    区分两件事：

    * **本 slice 无适用分母的部分** —— 已注册 adapter 的 D entry 数为 0（这是事实，
      registry 里 `adapter_registered: False`），字段级 col 占位与 contract 完整性判据
      由 **Task 41 pilot** 承载（`test_task41_d2_large_json_pilot.py` +
      `test_task13_contract_registry.py`）。本文件**不宣称通过**，只断言这个事实成立
      且 pilot evidence 真存在。
    * **本 slice 有真分母的部分** —— D2 的 per-entry contract 是真文件，它的字段完整性、
      col 占位、review_status、contract↔entry 绑定都在这里真验。
    """

    def test_no_d_entry_has_a_registered_adapter_and_pilot_evidence_exists(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        """分母为 0 这件事本身要被证实，并指向承载判据的 pilot（不是「所以通过」）。"""
        for entry in manifest_slice["independent_entries"]:
            assert entry["adapter_id"] is None, (
                f"{entry['entry_id']} 出现了 adapter_id={entry['adapter_id']!r}，"
                "本 slice 的「无已注册 adapter」前提不再成立 ⇒ 必须在此补齐字段级判据"
            )
        d_ids = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        for entry in full_manifest["entries"]:
            if entry["entry_id"] in d_ids:
                assert entry.get("adapter_id") is None

        # pilot 承载物必须真存在 —— 否则「判据由 pilot 承载」是空头承诺
        pilot_guard = BACKEND / "tests" / "workpaper_sync" / "test_task41_d2_large_json_pilot.py"
        registry_guard = BACKEND / "tests" / "workpaper_sync" / "test_task13_contract_registry.py"
        assert pilot_guard.is_file(), f"{pilot_guard} 不存在 —— 承载 Property 20/21 的 pilot 判据缺失"
        assert registry_guard.is_file(), f"{registry_guard} 不存在"

    def test_d2_contract_fields_are_complete_and_source_backed(
        self, d2_contract: dict
    ) -> None:
        """真分母：D2 契约逐字段必须有 stable_field_key / json_pointer / mode / source_ref。"""
        assert d2_contract["review_status"] == "reviewed"
        assert d2_contract["contract_id"] == "d2.receivable_detail"
        fields = [
            field
            for sheet in d2_contract["sheets"]
            for table in sheet["tables"]
            for field in table["fields"]
        ]
        assert len(fields) >= 30, f"D2 契约只有 {len(fields)} 个字段，可疑"
        for field in fields:
            for key in ("stable_field_key", "json_pointer", "mode", "value_type", "source_ref"):
                assert field.get(key), f"D2 契约字段 {field.get('column_key')!r} 缺 {key}"
            assert field["mode"] in ("editable", "formula", "readonly")

    def test_d2_contract_has_no_generated_column_placeholder(self, d2_contract: dict) -> None:
        """Property 20：`col_[a-z]+` 形态的无语义列占位一律拒绝，即使填了 source_ref。"""
        placeholder = re.compile(r"^col_[a-z]+$")
        for sheet in d2_contract["sheets"]:
            for table in sheet["tables"]:
                for field in table["fields"]:
                    column_key = str(field.get("column_key", ""))
                    assert not placeholder.match(column_key), (
                        f"D2 契约出现 generated col 占位: {column_key}"
                    )
                    assert "col_" not in str(field.get("stable_field_key", "")), (
                        f"D2 契约的 stable_field_key 含 col_ 占位: {field['stable_field_key']}"
                    )

    def test_contract_presence_forbids_single_onlyoffice(self, manifest_slice: dict) -> None:
        """替代硬编码豁免的真判据：contract 存在 ⇒ 该 entry 不得裁 single_onlyoffice。

        首轮这里写的是 `if name.startswith("d2"): continue` —— 硬编码豁免，且它掩盖的恰是
        「D2 有 HTML 对端」这个反例。真判据不需要豁免列。
        """
        contract_owner_by_entry: dict[str, list[str]] = {}
        for path in sorted(CONTRACT_DIR.glob("*.json")):
            if path.name.startswith("_"):
                continue  # _example.candidate.json 是模板样例，不是生产契约
            payload = _load(path)
            entry_id = payload.get("review", {}).get("entry_id")
            if entry_id:
                contract_owner_by_entry.setdefault(entry_id, []).append(path.name)

        assert D2_ENTRY_ID in contract_owner_by_entry, (
            "D2 的 per-entry contract 必须被识别为归属 D2 —— 它是本次重裁的反例来源"
        )

        for entry in manifest_slice["independent_entries"]:
            owned = contract_owner_by_entry.get(entry["entry_id"], [])
            if owned:
                assert entry.get("capability") != "single_onlyoffice", (
                    f"{entry['entry_id']} 有 per-entry contract {owned} 却裁 single_onlyoffice。"
                    "contract 的 review.html_store 已记明 HTML 对端 ⇒ 违反 AC 12.8"
                )
                assert entry.get("html_counterpart_verdict") == "exists", (
                    f"{entry['entry_id']} 有 contract 却把 html_counterpart_verdict 记成 "
                    f"{entry.get('html_counterpart_verdict')!r}"
                )

    def test_entries_without_contract_have_no_contract_file(self, manifest_slice: dict) -> None:
        """反向：slice 里没登记 per_entry_contract 的 entry，契约目录里也不许有它的文件。"""
        declared = {
            entry["entry_id"]
            for entry in manifest_slice["independent_entries"]
            if entry.get("per_entry_contract")
        }
        assert declared == {D2_ENTRY_ID}, f"slice 登记的 D 契约集合异常: {declared}"
        for path in sorted(CONTRACT_DIR.glob("*.json")):
            if path.name.startswith("_"):
                continue
            entry_id = _load(path).get("review", {}).get("entry_id")
            if entry_id and entry_id.startswith("xlsx/gt-d") and entry_id not in declared:
                pytest.fail(
                    f"契约文件 {path.name} 归属 {entry_id}，但 slice 未登记它的 per_entry_contract"
                )

    def test_d2_contract_records_the_html_counterpart(
        self, d2_contract: dict, manifest_slice: dict
    ) -> None:
        """D2 契约里的 html_store 必须与 slice 的 html_counterpart 逐项一致（双向锁）。"""
        html_store = d2_contract["review"]["html_store"]
        d2 = next(
            e for e in manifest_slice["independent_entries"] if e["entry_id"] == D2_ENTRY_ID
        )
        counterpart = d2["html_counterpart"]
        assert html_store["table"] == counterpart["store"]
        assert html_store["shape"] == counterpart["shape"]
        assert html_store["row_identity_key"] == counterpart["row_identity_key"]
        assert html_store["item_id"] == counterpart["primary_table"]["item_id"]
        assert d2_contract["review"]["entry_id"] == D2_ENTRY_ID


# ════════════════════════════════════════════════════════════════════════════
# Property 28：immutable definition 漂移 fail closed（真 digest，不是空分母）
# ════════════════════════════════════════════════════════════════════════════
class TestProperty28DefinitionDriftFailClosed:
    """
    **Validates: Requirements 6.10, 9.1**

    首轮这里只断言 `authority_model is None` + `template_ref` 存在。收口后：
    D2 契约的三个 digest 全部**现算复核**，模板字节漂移一位即红。
    """

    def test_authoritative_templates_digests_recompute(self, manifest_slice: dict) -> None:
        """每个登记模板的 size + sha256 都现算比对（Requirement 6.10 fail closed）。"""
        block = manifest_slice["authoritative_templates"]
        root = ROOT / block["root"]
        assert root.is_dir(), f"{root} 不存在"
        assert block["lock_file_policy"], "必须登记 `~$` 锁文件策略"
        assert block["reference_copy_status"] in (
            "absent_from_working_tree",
            "present_and_compared",
        )

        files = block["files"]
        assert len(files) >= 7, f"只登记了 {len(files)} 个模板，少于独立 entry 数"

        on_disk = {
            p.name for p in root.iterdir() if p.is_file() and not p.name.startswith("~$")
        }
        registered = {f["name"] for f in files}
        assert registered == on_disk, (
            "登记模板集合与权威目录实况不符\n"
            f"  只在登记里: {sorted(registered - on_disk)}\n"
            f"  只在磁盘上: {sorted(on_disk - registered)}"
        )

        for record in files:
            path = root / record["name"]
            assert path.is_file(), f"{path} 不存在"
            assert path.stat().st_size == record["size"], (
                f"{record['name']} size 漂移: 实测 {path.stat().st_size}，登记 {record['size']}"
            )
            actual = _sha256_of(path)
            assert actual == record["sha256"], (
                f"{record['name']} sha256 漂移: 实测 {actual}，登记 {record['sha256']}"
            )

    def test_template_owner_mapping_is_consistent(self, manifest_slice: dict) -> None:
        """SR-8：belongs_to_entry 非 null 必须命中本 slice 的 entry；为 null 必须给 excluded_reason。"""
        entry_ids = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        for record in manifest_slice["authoritative_templates"]["files"]:
            owner = record.get("belongs_to_entry")
            if owner is None:
                assert record.get("excluded_reason"), (
                    f"{record['name']} 没有归属 entry 却也没写 excluded_reason"
                )
            else:
                assert owner in entry_ids, (
                    f"{record['name']} 归属到不存在的 entry {owner!r}"
                )

    def test_every_entry_template_ref_is_registered_with_digest(
        self, manifest_slice: dict
    ) -> None:
        """template_ref **必须非空**，且它指向的文件在 authoritative_templates 里带 digest。

        首轮是 `if tref:` —— template_ref 为 null 时整条跳过（实测置 null 后 36 例全绿）。
        """
        by_name = {
            f["name"]: f for f in manifest_slice["authoritative_templates"]["files"]
        }
        root = ROOT / manifest_slice["authoritative_templates"]["root"]
        for entry in manifest_slice["independent_entries"]:
            ref = entry.get("template_ref")
            assert isinstance(ref, str) and ref.strip(), (
                f"{entry['entry_id']} 的 template_ref 为空 —— 不允许缺省跳过"
            )
            name = ref.split("/")[-1]
            assert name in by_name, (
                f"{entry['entry_id']} 的 template_ref {ref!r} 未登记进 authoritative_templates"
            )
            record = by_name[name]
            assert record["belongs_to_entry"] == entry["entry_id"], (
                f"{entry['entry_id']} 的 template_ref 归属登记为 "
                f"{record['belongs_to_entry']!r}"
            )
            path = root / name
            assert path.is_file()
            assert _sha256_of(path) == record["sha256"]
            assert path.stat().st_size == record["size"]

    def test_d2_contract_template_digests_recompute_from_the_template_bytes(
        self, d2_contract: dict
    ) -> None:
        """真分母：D2 契约的 template_sha256 + normalized_structure_hash 现算复核。"""
        sys.path.insert(0, str(BACKEND))
        from app.services.workpaper_sync.excel_instrumentation import (  # noqa: PLC0415
            normalized_structure_hash,
        )

        template = d2_contract["template"]
        path = TEMPLATE_DIR / template["relative_path"]
        assert path.is_file(), f"D2 权威模板不存在: {path}"
        data = path.read_bytes()

        assert hashlib.sha256(data).hexdigest() == template["template_sha256"], (
            "D2 契约的 template_sha256 与权威模板字节不符 ⇒ definition 已漂移"
        )
        assert normalized_structure_hash(data) == template["normalized_structure_hash"], (
            "D2 契约的 normalized_structure_hash 与权威模板结构不符 ⇒ 结构已漂移"
        )

    def test_d2_contract_identity_digests_are_real_digests(self, d2_contract: dict) -> None:
        """三个 definition digest 必须是真 64 位十六进制且非全零（Requirement 2.3）。"""
        digest_re = re.compile(r"^[0-9a-f]{64}$")
        for key in (
            "instrumentation_definition_sha256",
            "template_definition_sha256",
        ):
            value = d2_contract.get(key, "")
            assert digest_re.match(value), f"{key} 不是合法 digest: {value!r}"
            assert set(value) != {"0"}, f"{key} 是全零 hash —— 不得代替真 digest"
        for key in ("template_sha256", "normalized_structure_hash"):
            value = d2_contract["template"].get(key, "")
            assert digest_re.match(value), f"template.{key} 不是合法 digest: {value!r}"
            assert set(value) != {"0"}, f"template.{key} 是全零 hash"

    def test_d2_formula_mask_columns_are_really_formulas(self, d2_contract: dict) -> None:
        """契约声明的 formula 列必须在权威模板里真是公式（Property 28 的另一侧）。"""
        import openpyxl

        template = TEMPLATE_DIR / d2_contract["template"]["relative_path"]
        workbook = openpyxl.load_workbook(template, data_only=False)
        try:
            for sheet in d2_contract["sheets"]:
                worksheet = workbook[sheet["excel_name"]]
                for table in sheet["tables"]:
                    masks = table.get("formula_mask", [])
                    assert masks, f"{sheet['excel_name']} 的 formula_mask 为空 ⇒ 判据无分母"
                    for mask in masks:
                        first = mask.split(":")[0]
                        value = worksheet[first].value
                        assert isinstance(value, str) and value.startswith("="), (
                            f"formula_mask {mask} 的首格 {first} 在权威模板里不是公式: {value!r}"
                        )
        finally:
            workbook.close()


# ════════════════════════════════════════════════════════════════════════════
# Property 69：evidence 逐 entry 闭合，UNVERIFIABLE 必须带原因
# ════════════════════════════════════════════════════════════════════════════
class TestProperty69EvidencePerEntry:
    """
    **Validates: Requirements 12.10, 12.11**
    """

    def test_slice_scope_is_recomputable_from_the_manifest(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        """slice_scope.selection_rule 必须能现算出同一个 entry 集合（不是手抄清单）。"""
        scope = manifest_slice["slice_scope"]
        assert scope["cycle"] == "D"
        assert scope["document_type"] == "xlsx"
        assert scope["selection_rule"], "selection_rule 为空 ⇒ 「7」在文档里无推导"

        independent: set[str] = set()
        duplicates: set[str] = set()
        for entry in full_manifest["entries"]:
            if entry.get("document_type") != "xlsx":
                continue
            patterns = entry.get("wp_match", {}).get("wp_code_patterns", [])
            if not any(str(p).startswith("D") for p in patterns):
                continue
            if entry.get("independent_entry"):
                independent.add(entry["entry_id"])
            else:
                duplicates.add(entry["entry_id"])

        assert len(independent) == scope["independent_entry_count"], (
            f"现算 independent={len(independent)}，slice 写 {scope['independent_entry_count']}"
        )
        assert len(duplicates) == scope["parent_duplicate_count"], (
            f"现算 parent_duplicate={len(duplicates)}，slice 写 {scope['parent_duplicate_count']}"
        )
        assert independent == {
            e["entry_id"] for e in manifest_slice["independent_entries"]
        }, "slice 的 entry 集合与按 selection_rule 现算的集合不等"

    def test_excluded_items_have_reasons(self, manifest_slice: dict) -> None:
        excluded = manifest_slice["slice_scope"]["excluded_from_slice"]
        assert excluded, "excluded_from_slice 为空 —— D0 函证等跨循环共享物必须显式排除"
        for item in excluded:
            assert item.get("what")
            assert len(item.get("reason", "")) > 20

    def test_each_entry_has_unique_id(self, manifest_slice: dict) -> None:
        ids = [e["entry_id"] for e in manifest_slice["independent_entries"]]
        assert len(ids) == len(set(ids))

    def test_evidence_state_and_reasons(self, manifest_slice: dict) -> None:
        """SR-7：UNVERIFIABLE 必须带非空 unverifiable_reasons；字段不得缺失。"""
        for entry in manifest_slice["independent_entries"]:
            evidence = entry.get("evidence")
            assert isinstance(evidence, dict), (
                f"{entry['entry_id']} 的 evidence 缺失 —— 连 UNVERIFIABLE 都没标的条目"
                "在 stale 统计里无法归类（AC 12.13）"
            )
            for key in (
                "browser_case",
                "contract_test",
                "sync_test_run_id",
                "required_scenario_set_digest",
                "verification_state",
            ):
                assert key in evidence, f"{entry['entry_id']} 的 evidence 缺 {key}"
            state = evidence["verification_state"]
            assert state in ("UNVERIFIABLE", "VERIFIED", "FAILED"), (
                f"{entry['entry_id']} 的 verification_state={state!r} 非法"
            )
            if state == "UNVERIFIABLE":
                reasons = evidence.get("unverifiable_reasons")
                assert isinstance(reasons, list) and reasons, (
                    f"{entry['entry_id']} 标 UNVERIFIABLE 却没说明原因 = 自由文本豁免"
                )

    def test_no_entry_claims_verified_without_a_test_run(self, manifest_slice: dict) -> None:
        """假双向已验收计数的真分母：VERIFIED 必须有 test run + scenario digest。"""
        for entry in manifest_slice["independent_entries"]:
            evidence = entry["evidence"]
            if evidence["verification_state"] == "VERIFIED":
                assert evidence["sync_test_run_id"], (
                    f"{entry['entry_id']} 声称 VERIFIED 但没有 sync_test_run_id"
                )
                assert evidence["required_scenario_set_digest"], (
                    f"{entry['entry_id']} 声称 VERIFIED 但没有 required_scenario_set_digest"
                )

    def test_summary_counters_are_recomputed_from_entries(self, manifest_slice: dict) -> None:
        """SR-1 / SR-2：摘要计数逐项由 entries 现算，抄错或凑数即红。"""
        entries = manifest_slice["independent_entries"]
        summary = manifest_slice["honest_adjudication_summary"]
        assert summary["total_independent"] == len(entries)
        assert summary["total_independent"] == manifest_slice["slice_scope"][
            "independent_entry_count"
        ]

        for capability, key in (
            ("bidirectional", "adjudicated_as_bidirectional"),
            ("single_onlyoffice", "adjudicated_as_single_onlyoffice"),
            ("single_html", "adjudicated_as_single_html"),
            ("unreachable", "adjudicated_as_unreachable"),
        ):
            expected = sum(1 for e in entries if e.get("capability") == capability)
            assert summary[key] == expected, (
                f"{key} 应为 {expected}，slice 写 {summary[key]}"
            )

        pending = sum(1 for e in entries if e.get("capability") is None)
        assert summary["capability_verdict_pending"] == pending
        assert summary["slice_counters"]["unadjudicated"] == pending, (
            "capability 终态未定的条目必须计入 unadjudicated —— 归零不是进度"
        )

        assert summary["html_counterpart_exists"] == sum(
            1 for e in entries if e.get("html_counterpart_verdict") == "exists"
        )
        assert summary["html_counterpart_none"] == sum(
            1 for e in entries if e.get("html_counterpart_verdict") == "none"
        )
        assert summary["entries_left_unverifiable"] == sum(
            1 for e in entries if e["evidence"]["verification_state"] == "UNVERIFIABLE"
        )
        assert summary["slice_counters"]["fake_bidirectional_claimed_verified"] == sum(
            1
            for e in entries
            if e.get("capability") == "bidirectional"
            and e["evidence"]["verification_state"] == "VERIFIED"
            and e.get("adapter_id") is None
        )
        assert summary["slice_counters"]["bidirectional_unverified"] == sum(
            1
            for e in entries
            if e.get("capability") == "bidirectional"
            and e["evidence"]["verification_state"] != "VERIFIED"
        )

    def test_blocking_preconditions_are_complete(self, manifest_slice: dict) -> None:
        """每条阻断项必须有 id/blocks/what/consequence/status/must_fix_before/source_refs。"""
        blocking = manifest_slice["blocking_preconditions"]
        assert len(blocking) >= 5, f"只登记了 {len(blocking)} 条阻断项，可疑"
        ids = [bp["id"] for bp in blocking]
        assert len(ids) == len(set(ids)), f"阻断项 id 重复: {ids}"
        for bp in blocking:
            for key in ("id", "blocks", "what", "consequence", "status", "must_fix_before"):
                assert bp.get(key), f"阻断项 {bp.get('id')} 缺 {key}"
            refs = bp.get("source_refs")
            assert isinstance(refs, list) and refs, (
                f"阻断项 {bp['id']} 没有 source_refs —— 无据可查的阻断项等于自由文本"
            )
            for ref in refs:
                raw = ref.split("#")[0].strip()
                assert (ROOT / raw).exists(), (
                    f"阻断项 {bp['id']} 的 source_ref {ref!r} 指向不存在的路径"
                )

    def test_capability_blockers_reference_real_preconditions(
        self, manifest_slice: dict
    ) -> None:
        """entry 上登记的阻断项 id 必须真在 blocking_preconditions 里。"""
        known = {bp["id"] for bp in manifest_slice["blocking_preconditions"]}
        for entry in manifest_slice["independent_entries"]:
            for bp_id in entry.get("capability_target_blocked_by", []):
                assert bp_id in known, (
                    f"{entry['entry_id']} 引用了不存在的阻断项 {bp_id}"
                )


# ════════════════════════════════════════════════════════════════════════════
# Property 70：不得跨 entry 复用
# ════════════════════════════════════════════════════════════════════════════
class TestProperty70NoCrossEntryReuse:
    """
    **Validates: Requirements 12.12**
    """

    def test_cross_entry_isolation_block_present(self, manifest_slice: dict) -> None:
        isolation = manifest_slice["cross_entry_isolation"]
        assert isolation["rule"]
        assert len(isolation["assertions"]) >= 4

    def test_d_entries_absent_from_e_slice(self, manifest_slice: dict) -> None:
        """D / E 两个 slice 的 entry 集合不得相交（重复计数 = 假迁移进度）。"""
        assert E_SLICE_PATH.is_file(), f"{E_SLICE_PATH} 不存在（Task 47 交付物）"
        e_ids = {e["entry_id"] for e in _load(E_SLICE_PATH)["independent_entries"]}
        d_ids = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        assert not (d_ids & e_ids), f"D/E slice entry 相交: {sorted(d_ids & e_ids)}"

    def test_only_d2_carries_a_contract(self, manifest_slice: dict) -> None:
        """D2 的契约不得被其余 6 条借用（cross_entry_rule）。"""
        for entry in manifest_slice["independent_entries"]:
            if entry["entry_id"] == D2_ENTRY_ID:
                assert entry["per_entry_contract"]["contract_id"] == "d2.receivable_detail"
            else:
                assert "per_entry_contract" not in entry, (
                    f"{entry['entry_id']} 挂了 per_entry_contract —— 不得跨 entry 复用 D2 契约"
                )

    def test_deletion_plan_entries_are_distinct(self, deletion_plan: dict) -> None:
        ids = [e["entry_id"] for e in deletion_plan["entries"]]
        assert len(ids) == len(set(ids))

    def test_deletion_plan_composables_are_distinct(self, deletion_plan: dict) -> None:
        all_composables: list[str] = []
        for entry in deletion_plan["entries"]:
            for comp in entry.get("legacy_composables_to_delete", []):
                all_composables.append(comp["file"])
        assert len(all_composables) == len(set(all_composables)), (
            "legacy composable 不应跨 entry 复用"
        )

    def test_deletion_plan_adjudication_matches_slice(
        self, deletion_plan: dict, manifest_slice: dict
    ) -> None:
        """deletion plan 的裁决字段必须与 slice 一致，且理由不循环论证。"""
        by_id = {e["entry_id"]: e for e in manifest_slice["independent_entries"]}
        for entry in deletion_plan["entries"]:
            sliced = by_id.get(entry["entry_id"])
            assert sliced is not None, (
                f"deletion plan 里的 {entry['entry_id']} 不在 slice 中"
            )
            assert entry.get("capability_adjudication") == sliced.get("capability"), (
                f"{entry['entry_id']} 的 deletion plan 裁决与 slice 不一致"
            )
            assert entry.get("html_counterpart_verdict") == sliced.get(
                "html_counterpart_verdict"
            )
            assert len(entry.get("adjudication_reason", "")) > 40

    def test_parent_duplicates_not_counted_as_independent(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        """AC 1.6：31 条 D4 sub-tab 不得进 independent_entries。"""
        d4_subs = {
            e["entry_id"]
            for e in full_manifest["entries"]
            if e["entry_id"].startswith("xlsx/d4/")
        }
        assert len(d4_subs) == 31, f"全量 manifest 里 D4 sub-tab 实为 {len(d4_subs)} 条"
        slice_ids = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        assert not (d4_subs & slice_ids)
        d4 = next(
            e
            for e in manifest_slice["independent_entries"]
            if e["entry_id"] == "xlsx/gt-d4-operating-revenue"
        )
        assert d4["parent_duplicate_count"] == len(d4_subs)

    def test_d4_sub_tabs_not_in_deletion_plan(self, deletion_plan: dict) -> None:
        for entry in deletion_plan["entries"]:
            assert not entry["entry_id"].startswith("xlsx/d4/")

    def test_d4_parent_duplicates_marked_in_full_manifest(self, full_manifest: dict) -> None:
        for entry in full_manifest["entries"]:
            if not entry["entry_id"].startswith("xlsx/d4/"):
                continue
            assert entry.get("independent_entry") is False
            assert entry.get("migration_state") == "parent_duplicate"


# ════════════════════════════════════════════════════════════════════════════
# AC 1.4：裁决自带的 UI 义务（step 11）
# ════════════════════════════════════════════════════════════════════════════
class TestAc14HonestModeVisibility:
    """
    **Validates: Requirements 1.4**

    AC 1.4：未注册 adapter 的入口**禁止**显示「可双向回写」，并**必须**显示可操作原因。

    🔴 只改 slice 的 capability 而界面照旧 = AP-4 capability_without_ui_change。
    判据必须落到**模板形态**（宿主真挂了组件 + 传了自己的 entry id），不能只 grep 符号名 ——
    「模型声明了而模板零引用」是 G7 两级表头 0/38 的同型结构性死代码。

    AC 1.5 为什么不在这里：它的触发条件是「入口被裁决为纯 OO 或纯 HTML」。重裁后 7 条
    entry 都不是 single_*，AC 1.5 的 WHEN 不成立；收掉切换按钮反而会砍掉真实可用的 OO
    独立编辑通道。见 slice 的 BP-7。
    """

    def test_notice_module_is_the_single_source(self) -> None:
        source = _strip_ts_comments(NOTICE_MODULE.read_text(encoding="utf-8"))
        assert "export function entrySyncNotice" in source
        assert "SYNC_ADAPTER_REGISTERED_ENTRY_IDS" in source
        assert "ENTRY_SYNC_NOTICE_SUMMARY" in source
        assert "ENTRY_SYNC_NOTICE_REASON" in source

    def test_notice_component_renders_summary_and_binds_entry_id(self) -> None:
        """常显摘要 + entry 绑定必须在模板里（不是只在 script 里算）。"""
        source = _strip_ts_comments(NOTICE_COMPONENT.read_text(encoding="utf-8"))
        template = _vue_template(source)
        assert "notice.summary" in template, (
            "摘要没进模板 ⇒ 可操作原因默认不可见（EP tooltip 内容是 teleport 且 hover 才挂载）"
        )
        assert 'v-if="notice"' in template, "缺 v-if ⇒ 组件恒显，已接双向的 entry 也会挂警告"
        assert ":data-entry-sync-notice=" in template, "entry 绑定没进模板 ⇒ DOM 判据无从落地"

    def test_every_pending_entry_host_mounts_the_notice(self, manifest_slice: dict) -> None:
        """三要素：宿主 import + 模板挂载 + 传自己的 entry id，缺一即红。"""
        checked = 0
        for entry in manifest_slice["independent_entries"]:
            if entry.get("adapter_id") is not None:
                continue  # 已注册 adapter 的 entry 由真实 bridge 状态表达
            host = ROOT / entry["host_path"]
            assert host.is_file(), f"{entry['entry_id']} 的宿主不存在: {host}"
            source = _strip_ts_comments(host.read_text(encoding="utf-8"))

            assert f"import {NOTICE_COMPONENT_NAME} from" in source, (
                f"{host.name} 没有 import {NOTICE_COMPONENT_NAME}"
            )
            template = _vue_template(source)
            assert f"<{NOTICE_COMPONENT_NAME}" in template, (
                f"{host.name} 的模板里没有挂 <{NOTICE_COMPONENT_NAME}> ⇒ 结构性死代码"
            )
            mount_pattern = re.compile(
                r"<" + NOTICE_COMPONENT_NAME + r"\s+entry-id=\"([^\"]+)\"\s*/?>"
            )
            found = mount_pattern.search(template)
            assert found, f"{host.name} 挂了组件但没传 entry-id"
            assert found.group(1) == entry["entry_id"], (
                f"{host.name} 传的 entry-id={found.group(1)!r}，应为 {entry['entry_id']!r}"
            )
            checked += 1
        assert checked == 7, f"只校验到 {checked} 个宿主，应为 7 —— 分母缩水"

    def test_notice_mount_sits_inside_the_mode_toolbar(self, manifest_slice: dict) -> None:
        """通知必须挂在模式切换工具栏内 —— 挂在别处等于用户看不见它跟切换有关。"""
        for entry in manifest_slice["independent_entries"]:
            host = ROOT / entry["host_path"]
            source = _strip_ts_comments(host.read_text(encoding="utf-8"))
            template = _vue_template(source)
            toolbar = re.search(
                r'<div v-if="showModeToolbar"[\s\S]*?</div>', template
            )
            assert toolbar, f"{host.name} 找不到 showModeToolbar 工具栏区块"
            assert f"<{NOTICE_COMPONENT_NAME}" in toolbar.group(0), (
                f"{host.name} 的通知没挂在模式工具栏里"
            )

    def test_registered_entry_ids_agree_with_the_slice(self, manifest_slice: dict) -> None:
        """双向锁：slice 的 adapter_id 与前端登记表必须互相印证。"""
        source = _strip_ts_comments(NOTICE_MODULE.read_text(encoding="utf-8"))
        block = re.search(
            r"SYNC_ADAPTER_REGISTERED_ENTRY_IDS:\s*readonly\s+string\[\]\s*=\s*\[([\s\S]*?)\]",
            source,
        )
        assert block, "找不到 SYNC_ADAPTER_REGISTERED_ENTRY_IDS 的声明"
        registered = set(re.findall(r"['\"]([^'\"]+)['\"]", block.group(1)))
        for entry in manifest_slice["independent_entries"]:
            if entry.get("adapter_id") is None:
                assert entry["entry_id"] not in registered, (
                    f"{entry['entry_id']} 在 slice 里没有 adapter，却被前端登记为已注册 ⇒ "
                    "界面会以「已双向」呈现"
                )
            else:
                assert entry["entry_id"] in registered, (
                    f"{entry['entry_id']} 在 slice 里已有 adapter，前端登记表却没跟上 ⇒ "
                    "界面会继续挂假警告"
                )

    def test_hosts_do_not_claim_bidirectional_writeback(self, manifest_slice: dict) -> None:
        """AC 1.4 前半句：宿主不得出现「可双向回写」「同步成功」之类的成功态宣称。"""
        forbidden = ("可双向回写", "双向同步", "同步成功", "已同步")
        for entry in manifest_slice["independent_entries"]:
            host = ROOT / entry["host_path"]
            source = _strip_ts_comments(host.read_text(encoding="utf-8"))
            for word in forbidden:
                assert word not in source, (
                    f"{host.name} 出现 {word!r} —— 未注册 adapter 的入口不得宣称双向/同步成功"
                )


# ════════════════════════════════════════════════════════════════════════════
# 范式一致性与源码结构
# ════════════════════════════════════════════════════════════════════════════
class TestParadigmCompliance:
    """验证 slice / deletion plan 与 Task 45 冻结的范式一致（范式 JSON 只读）。"""

    def test_paradigm_exists(self, paradigm: dict) -> None:
        assert paradigm["schema_version"] == "migration-paradigm:v1"
        assert paradigm["frozen_by"] == "Task 45"

    def test_task46_is_in_the_definition_producer_paradigm(self, paradigm: dict) -> None:
        """本任务确实受 definition_producer_paradigm 约束（含 step 3 的二值结论要求）。"""
        producer = paradigm["definition_producer_paradigm"]
        assert 46 in producer["applies_to_tasks"]
        step3 = next(s for s in producer["steps"] if s["step"] == 3)
        assert step3["name"] == "resolve_html_counterpart"
        assert set(step3["output"]["allowed_values"]) == set(HTML_COUNTERPART_VERDICTS)

    def test_capability_enum_comes_from_the_paradigm(self, paradigm: dict) -> None:
        """本文件的 CAPABILITY_ENUM 必须与范式登记的枚举一致（不另立一份真源）。"""
        assert set(paradigm["adjudication_criteria"]["capability_enum"]) == set(
            CAPABILITY_ENUM
        )

    def test_single_onlyoffice_illegal_criteria_are_registered(self, paradigm: dict) -> None:
        """范式明文把「无 adapter / 无 contract / 无 bundle」列为非法判据。"""
        verdict = paradigm["adjudication_criteria"]["verdicts"]["single_onlyoffice"]
        assert verdict["forbidden_verdict_value"] == "exists"
        assert verdict["illegal_criteria"], "illegal_criteria 为空 ⇒ AP-1 判据无分母"

    def test_paradigm_has_seven_legacy_deletion_steps(self, paradigm: dict) -> None:
        steps = paradigm["paradigm"]["steps"]
        assert len(steps) == 7
        assert [s["name"] for s in steps] == [
            "identify_legacy",
            "create_deletion_plan",
            "delete_legacy_composable",
            "update_host_imports",
            "unify_mode_values",
            "verify_no_legacy_endpoints",
            "run_post_delete_tests",
        ]

    def test_slice_references_the_paradigm_and_sibling(self, manifest_slice: dict) -> None:
        assert manifest_slice["paradigm_ref"] == (
            "backend/data/workpaper_sync_migration_paradigm.json"
        )
        assert "backend/data/workpaper_sync_e_cycle_manifest_slice.json" in manifest_slice[
            "sibling_slices"
        ]

    def test_slice_satisfies_the_paradigm_slice_schema(
        self, manifest_slice: dict, paradigm: dict
    ) -> None:
        """把 slice_schema 的 required_* 当必填字段真源逐项校验。

        🔴 `slice_schema.applies_to_tasks` 写的是 [48..57]、`effective_from_task_48`
        还写着「D / E 两个 slice … 本次不追溯改写它们的字节」。但同一份范式的
        `definition_producer_paradigm.applies_to_tasks` **包含 46**，且 AP-1 的
        `known_debt_inventory` 把这 7 条 D 债务的 owner 明确写成「Task 46 D 循环回填」。
        本 slice 按前者执行并满足 schema，冲突登记在 slice 的 paradigm_schema_conflict。
        """
        schema = paradigm["slice_schema"]
        for key in schema["required_top_level"]:
            assert key in manifest_slice, f"slice 缺顶层字段 {key}"
        for key in schema["required_slice_scope"]:
            assert key in manifest_slice["slice_scope"], f"slice_scope 缺 {key}"
        for item in manifest_slice["slice_scope"]["excluded_from_slice"]:
            for key in schema["required_excluded_item"]:
                assert key in item
        for key in schema["required_authoritative_templates"]:
            assert key in manifest_slice["authoritative_templates"]
        for record in manifest_slice["authoritative_templates"]["files"]:
            for key in schema["required_template_file"]:
                assert key in record, f"模板 {record.get('name')} 缺 {key}"

        effective = schema["effective_from_task_48"]
        required_entry = list(schema["required_entry"]) + list(effective["required_entry"])
        for entry in manifest_slice["independent_entries"]:
            for key in required_entry:
                assert key in entry, f"{entry['entry_id']} 缺 entry 字段 {key}"
            for key in schema["required_entry_adjudication"]:
                assert key in entry["adjudication"], (
                    f"{entry['entry_id']} 的 adjudication 缺 {key}"
                )
            for key in schema["required_entry_evidence"]:
                assert key in entry["evidence"], (
                    f"{entry['entry_id']} 的 evidence 缺 {key}"
                )

        required_bp = list(schema["required_blocking_precondition"]) + list(
            effective["required_blocking_precondition"]
        )
        for bp in manifest_slice["blocking_preconditions"]:
            for key in required_bp:
                assert key in bp, f"阻断项 {bp.get('id')} 缺 {key}"
        for key in schema["required_cross_entry_isolation"]:
            assert key in manifest_slice["cross_entry_isolation"]
        for key in schema["required_honest_adjudication_summary"]:
            assert key in manifest_slice["honest_adjudication_summary"], (
                f"honest_adjudication_summary 缺 {key}"
            )
        for key in schema["required_slice_counters"]:
            assert key in manifest_slice["honest_adjudication_summary"]["slice_counters"]

    def test_paradigm_conflict_is_registered(self, manifest_slice: dict) -> None:
        """范式内部冲突必须登记，不许悄悄绕过。"""
        conflict = manifest_slice["paradigm_schema_conflict"]
        for key in ("what", "how_resolved_here", "residual_inconsistency", "e_slice_conflicts"):
            assert len(conflict.get(key, "")) > 40, f"paradigm_schema_conflict 缺 {key}"

    def test_deletion_plan_has_paradigm_ref(self, deletion_plan: dict) -> None:
        assert deletion_plan["paradigm_ref"] == (
            "backend/data/workpaper_sync_migration_paradigm.json"
        )

    def test_shared_base_preserved(self, deletion_plan: dict) -> None:
        preserved = deletion_plan["shared_base_preserved"]
        assert "useWorkpaperEntryDualMode.ts" in preserved["file"]
        assert len(preserved["remaining_consumers_after_d_cycle"]) >= 4


class TestSourceCodeStructure:
    """验证源码结构与 manifest/deletion plan 一致（现状锁，删除归 Task 66/72）。"""

    def test_shared_base_composable_exists(self) -> None:
        assert SHARED_BASE.is_file(), "useWorkpaperEntryDualMode.ts 必须存在"

    def test_entry_composables_exist(self) -> None:
        for cycle, path in D_CYCLE_ENTRY_COMPOSABLES.items():
            assert path.is_file(), (
                f"{cycle} 的 entry composable {path.name} 必须存在（删除归 Task 66/72）"
            )

    def test_hosts_exist_and_import_legacy_composable(self, manifest_slice: dict) -> None:
        """宿主存在且仍引用 legacy composable（BP-7 登记的未删状态）。"""
        pattern_by_host = {
            "GtD1NotesReceivable.vue": "useD1EntryDualMode",
            "GtD2AccountsReceivable.vue": "useD2EntryDualMode",
            "GtD3PrepaidAccounts.vue": "useD3EntryDualMode",
            "GtD4OperatingRevenue.vue": "useD4EntryDualMode",
            "GtD5ReceivablesFinancing.vue": "useD5EntryDualMode",
            "GtD6ContractAssets.vue": "useD6EntryDualMode",
            "GtD7ContractLiabilities.vue": "useD7EntryDualMode",
        }
        hosts = {
            (ROOT / e["host_path"]).name for e in manifest_slice["independent_entries"]
        }
        assert hosts == set(pattern_by_host), (
            f"slice 的宿主集合与预期不符: {sorted(hosts)}"
        )
        for entry in manifest_slice["independent_entries"]:
            host = ROOT / entry["host_path"]
            assert host.is_file()
            content = host.read_text(encoding="utf-8")
            assert pattern_by_host[host.name] in content, (
                f"{host.name} 应仍引用 {pattern_by_host[host.name]}"
            )

    def test_preserved_composables_exist(self) -> None:
        for path in PRESERVED_COMPOSABLES:
            assert path.is_file(), f"保留的 composable {path.name} 必须存在"

    def test_d_cycle_templates_exist(self) -> None:
        d_dir = TEMPLATE_DIR / "D"
        assert d_dir.is_dir()
        xlsx_files = [
            p for p in d_dir.glob("D*.xlsx") if not p.name.startswith("~$")
        ]
        assert len(xlsx_files) >= 7, f"至少 7 个 D 循环模板，实际 {len(xlsx_files)}"

    def test_bridge_adapter_supports_entry_id(self) -> None:
        adapter = SYNC_DIR / "usePilotBridgeAdapter.ts"
        assert adapter.is_file(), "usePilotBridgeAdapter.ts 必须存在（Task 45 产物）"
        assert "entryId" in adapter.read_text(encoding="utf-8")

    def test_pilot_deletion_plan_marks_d2(self) -> None:
        """Task 45 的 pilot deletion plan 必须存在且含 D2 —— 缺文件打红，不 skip。"""
        pilot_plan_path = DATA / "workpaper_sync_pilot_deletion_plan.json"
        assert pilot_plan_path.is_file(), (
            f"{pilot_plan_path} 不存在。首轮这里是 `pytest.skip(...)` —— skip 记为通过 = fail-open"
        )
        pilot_plan = _load(pilot_plan_path)
        d2_entries = [
            p for p in pilot_plan["pilots"] if p["entry_id"] == D2_ENTRY_ID
        ]
        assert len(d2_entries) == 1, "D2 应在 pilot deletion plan 中恰好出现一次"


class TestManifestAlignment:
    """slice ↔ 全量 manifest 的对齐（分歧必须登记，不许当成相等）。"""

    def test_slice_entry_ids_in_full_manifest(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        full_ids = {e["entry_id"] for e in full_manifest["entries"]}
        for entry in manifest_slice["independent_entries"]:
            assert entry["entry_id"] in full_ids

    def test_source_backed_profile_fields_match_the_manifest(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        """source-backed 的字段（profile / room / mount / resolver）必须与 manifest 严格相等。

        这些是生成器从源码推导的事实，不是裁决 —— 不一致说明 slice 手抄错了。
        """
        by_id = {e["entry_id"]: e for e in full_manifest["entries"]}
        for entry in manifest_slice["independent_entries"]:
            src = by_id[entry["entry_id"]]
            assert entry["host_path"] == src["host_path"]
            assert entry["document_type"] == src["document_type"]
            assert entry["editability"] == src["editability"]
            assert entry["room_model"] == src["room_model"]
            assert entry["canonical_resolver"] == src["canonical_resolver"]
            assert entry["scenario_profile_id"] == src["scenario_profile"]["profile_id"]
            assert entry["mount_count"] == src["scenario_profile"]["mount_count"]
            assert entry["migration_state"] == src["migration_state"]
            assert entry["wp_code_pattern"] in src["wp_match"]["wp_code_patterns"]

    def test_manifest_capability_divergence_is_registered(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        """capability / html_store 的分歧必须逐 entry 镜像登记，并有对应阻断项。

        🔴 首轮这里断言 slice.capability == manifest.capability。那个「相等」把
        overlay 的**组件级默认值**当成裁决真源：manifest 里 186 条 entry 有 180 条
        `html_store == "unresolved"`、全部 GtOnlyOfficeSheet entry 的 capability 都来自
        `workpaper_sync_entry_overlay.json#defaults_by_component`。所以正确判据是
        「分歧存在且已登记」，而不是「相等」。
        """
        by_id = {e["entry_id"]: e for e in full_manifest["entries"]}
        bp_ids = {bp["id"] for bp in manifest_slice["blocking_preconditions"]}
        divergent = 0
        for entry in manifest_slice["independent_entries"]:
            src = by_id[entry["entry_id"]]
            mirror = entry.get("manifest_mirror")
            assert isinstance(mirror, dict), (
                f"{entry['entry_id']} 缺 manifest_mirror ⇒ 分歧无处登记"
            )
            assert mirror["capability"] == src["capability"], (
                f"{entry['entry_id']} 的 manifest_mirror.capability 与 manifest 实况不符"
            )
            assert mirror["html_store"] == src["html_store"]
            assert mirror["legacy_reasons"] == list(src["evidence"]["legacy_reasons"])
            if mirror["capability"] != entry.get("capability"):
                divergent += 1
                assert mirror.get("divergence_from_slice"), (
                    f"{entry['entry_id']} capability 与 manifest 不一致却没写 divergence_from_slice"
                )
                assert any(
                    bp_id in mirror["divergence_from_slice"] for bp_id in bp_ids
                ), (
                    f"{entry['entry_id']} 的分歧说明里没有引用任何 blocking_precondition id"
                )
        assert divergent == 7, (
            f"预期 7 条 entry 与 manifest 分歧（overlay 默认值仍是 single_onlyoffice），实测 {divergent}。"
            "若 manifest 已重生成，请同步更新 BP-6 与本判据"
        )

    def test_overlay_default_is_the_real_source_of_the_manifest_capability(self) -> None:
        """证实 BP-6 的根因：manifest 的 capability/html_store 来自 overlay 组件级默认值。"""
        overlay = _load(DATA / "workpaper_sync_entry_overlay.json")
        default = overlay["defaults_by_component"]["GtOnlyOfficeSheet"]
        assert default["capability"] == "single_onlyoffice"
        assert default["html_store"] == "unresolved"
