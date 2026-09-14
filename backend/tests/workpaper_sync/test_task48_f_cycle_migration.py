# -*- coding: utf-8 -*-
"""
test_task48_f_cycle_migration — F 循环 Excel 独立 entry 迁移验证

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 5 Task 48
Requirements: 6.2, 6.10, 12.1, 12.4, 12.10, 12.11, 12.12, 14.1（另覆盖 1.4 / 12.8 / 12.9）

验证 Properties:
  - Property 21: contract 字段完整（F 循环分母为 0，**不宣称通过**，见 TestProperty21）
  - Property 28: immutable definition 漂移 fail closed（真分母：18 个模板 digest +
    8 个 normalized_structure_hash + 8 组 sheet!cell 真读）
  - Property 69: evidence 由逐 scenario 实体与服务端重算闭合（负向分母真验，
    正向逐 scenario 闭合不宣称通过，已登记 BP-4）
  - Property 70: scenario/evidence/contract/bundle 不得跨 entry 复用

═══ 判据设计（避开 Task 46 首轮踩过的四类坑）═══

1. **不用空分母重言式**。「F 循环没有 contract 所以 Property 21 通过」是重言式 ——
   同 spec 的 Task 20 专门写代码拒绝这种论证（`WriterGateError("...would be evaluated
   over an empty denominator (a tautology)")`）。本文件对每条 Property 显式区分
   「有真分母的部分（真验）」与「无适用分母的部分（只断言前提成立 + 承载者存在，
   **不宣称通过**）」，划分与 slice 的 `property_denominators` 逐项对齐。

2. **不用 fail-open**。没有 `pytest.skip`、没有 `if x: assert ...`（缺值即跳过）、
   没有 `except Exception` 吞异常。缺文件/缺字段一律打红。

3. **不用硬编码豁免**。F 循环没有 pilot，本文件也不给任何 entry 开例外列。

4. **不假设全 slice 同形**。F 循环实测出三处与 D 循环不同的形态，判据逐 entry 从
   slice 读声明再回源码核对，而不是写死一个值：
   * 行身份键有 `rowId`（F1/F3/F4）与 `id`（F2 四条 + F5）两族，生成器五种；
   * 传输键有字面量、`{sheet_code}-rows` 复合、新旧双键三种形态；
   * 模式工具栏门控有 `v-if="showHtmlToolbar"`（6 条）、`class="toolbar"`（F2 监盘）、
     `class="f5-cost-of-sales-toolbar"`（F5）三种。写死任一种都会让另两种静默失效。

依赖（缺任一即 fail closed）：
  - backend/data/workpaper_sync_f_cycle_manifest_slice.json（frozen slice）
  - backend/data/workpaper_sync_f_cycle_deletion_plan.json（deletion plan）
  - backend/data/workpaper_sync_migration_paradigm.json（Task 45 范式，只读）
  - backend/data/workpaper_sync_entry_manifest.json（source-backed manifest，只读）
  - backend/wp_templates/F/ 与 backend/wp_templates/_index.json（运行时权威，唯一真源）
"""
from __future__ import annotations

import ast
import copy
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

MANIFEST_SLICE_PATH = DATA / "workpaper_sync_f_cycle_manifest_slice.json"
DELETION_PLAN_PATH = DATA / "workpaper_sync_f_cycle_deletion_plan.json"
PARADIGM_PATH = DATA / "workpaper_sync_migration_paradigm.json"
FULL_MANIFEST_PATH = DATA / "workpaper_sync_entry_manifest.json"
D_SLICE_PATH = DATA / "workpaper_sync_d_cycle_manifest_slice.json"
E_SLICE_PATH = DATA / "workpaper_sync_e_cycle_manifest_slice.json"
CONTRACT_DIR = DATA / "workpaper_sync_contracts"
TEMPLATE_DIR = BACKEND / "wp_templates"
TEMPLATE_INDEX = TEMPLATE_DIR / "_index.json"
CHECKLIST_ROUTER = BACKEND / "app" / "routers" / "checklist_responses.py"
TEMPLATE_FINDER = BACKEND / "app" / "services" / "wp_template_finder.py"
PLAN_SYNC = BACKEND / "app" / "routers" / "wp_render_strategies" / "_f2_stocktake_plan_sync.py"
SUMMARY_SYNC = BACKEND / "app" / "routers" / "wp_render_strategies" / "_f2_stocktake_summary_sync.py"
REGISTRY = BACKEND / "app" / "services" / "workpaper_sync" / "adapters" / "registry.py"

#: AC 1.3 的能力态枚举（真源在范式 JSON 的 adjudication_criteria.capability_enum）。
CAPABILITY_ENUM = ("bidirectional", "single_html", "single_onlyoffice", "unreachable")
#: step 3 的二值结论（真源在范式 JSON 的 anti_patterns[AP-1].allowed_verdict_values）。
HTML_COUNTERPART_VERDICTS = ("none", "exists")

#: AC 1.4 的 UI 义务落点（Task 46 收口新建的单一真源，本任务复用不新建第二份）。
NOTICE_MODULE = SYNC_DIR / "workpaperEntrySyncNotice.ts"
NOTICE_COMPONENT = SYNC_DIR / "GtEntrySyncCapabilityNotice.vue"
NOTICE_COMPONENT_NAME = "GtEntrySyncCapabilityNotice"

#: F 循环 8 个宿主实际 import 的 entry 级 dual-mode composable（删除归 Task 66/72，
#: 本任务只锁现状；名字与 deletion plan 双向印证）。
F_CYCLE_HOST_DUAL_MODE = {
    "GtF1Prepayment.vue": "useF1DualMode",
    "GtF2InventoryMain.vue": "useF2DualMode",
    "GtF2InventorySpecial.vue": "useF2SpecialDualMode",
    "GtF2InventoryValuation.vue": "useF2ValuationDualMode",
    "GtF2StocktakeBundle.vue": "useF2StocktakeDualMode",
    "GtF3NotesPayable.vue": "useF3DualMode",
    "GtF4AccountsPayable.vue": "useF4DualMode",
    "GtF5CostOfSales.vue": "useF5CosOfDualMode",
}
SHARED_BASE = COMPOSABLES / "useWorkpaperEntryDualMode.ts"


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────
def _load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_of(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _strip_ts_comments(source: str) -> str:
    """剥掉 TS/Vue 注释 —— 说明文字不得充当判据证据。

    🔴 剥完必须反向自检（见 TestGuardSelfChecks），剥过头会让判据恒真。
    """
    source = re.sub(r"/\*[\s\S]*?\*/", "", source)
    source = re.sub(r"(?m)^\s*//.*$", "", source)
    source = re.sub(r"(?m)//[^\n\"'`]*$", "", source)
    source = re.sub(r"<!--[\s\S]*?-->", "", source)
    return source


def _vue_template(source: str) -> str:
    """取 SFC 的**外层** template 区块。

    🔴 不能用 `source.split("</template>")[0]`：SFC 里嵌套的具名插槽/`<template v-else>`
    会先闭合，第一处 `</template>` 落在内层 ⇒ 截出来的片段比真实模板短，判据会把
    「已在模板里」误判成「不在模板里」。这里改用 `<script` 边界。
    """
    marker = source.find("<script")
    assert marker > 0, "找不到 <script 边界 —— 该文件不是常规 SFC（template 在 script 之前）"
    head = source[:marker]
    assert "<template>" in head, "SFC 头部没有 <template>"
    return head


def _toolbar_block(template: str, gate_anchor: str) -> str:
    """按 slice 声明的工具栏门控锚点截出该区块（开标签行 → 同缩进的 `</div>`）。

    🔴 为什么按 slice 声明取锚点而不是写死正则：F 循环三种门控形态并存
    （`v-if="showHtmlToolbar"` / `class="toolbar"` / `class="f5-cost-of-sales-toolbar"`），
    写死任一种都会让另两种的判据静默恒真（挂载点根本不在被搜的区块里也不报错）。
    """
    lines = template.splitlines()
    opens = [i for i, ln in enumerate(lines) if gate_anchor in ln]
    assert len(opens) == 1, (
        f"工具栏门控锚点 {gate_anchor!r} 在模板里命中 {len(opens)} 次（应为 1）"
    )
    start = opens[0]
    indent = len(lines[start]) - len(lines[start].lstrip())
    for i in range(start + 1, len(lines)):
        if lines[i].strip() == "</div>" and (len(lines[i]) - len(lines[i].lstrip())) == indent:
            return "\n".join(lines[start : i + 1])
    pytest.fail(f"锚点 {gate_anchor!r} 之后找不到同缩进的 </div> —— 工具栏区块无法界定")


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


def _py_code_only(source: str) -> str:
    """剥掉 Python 的 docstring 与 `#` 注释，只留可执行代码。

    🔴 为什么必须有：`_f2_stocktake_plan_sync.py` 的 docstring 里**逐字引用**了它改造前
    的旧写法 `await db.commit()`，用来解释「以前是这样，现在不是了」。裸字符串匹配会把
    这段说明当成代码证据 ⇒ 「有没有绕出版本域」这条判据必然误报。用 AST 剥比正则稳：
    docstring 是表达式语句里的字符串常量，正则分不清它与普通赋值里的字符串。
    """
    import ast

    tree = ast.parse(source)
    doc_spans: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        body = getattr(node, "body", [])
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            doc_spans.append((first.lineno, first.end_lineno or first.lineno))
    drop: set[int] = set()
    for start, end in doc_spans:
        drop.update(range(start, end + 1))
    kept = [
        line
        for i, line in enumerate(source.splitlines(), 1)
        if i not in drop and not line.lstrip().startswith("#")
    ]
    return "\n".join(kept)


def _collapse_ws(text: str) -> str:
    """把连续空白（含换行）折成单空格 —— 供跨行折行的 docstring 片段做子串匹配。"""
    return re.sub(r"\s+", " ", text)


def _commit_bytes_lane_id(path: pathlib.Path) -> str:
    """取 `_save_fields` 里 `commit_bytes(lane_id=...)` 的**字面量**实参（AST，不 grep）。

    🔴 Task 65 之后 authority model 不再是 `commit_bytes` 的实参，改由 `lane_id` 经
    `opaque_entry_gate` 的 lane 登记表**单向**决定。所以「这个 writer 用的是哪个
    authority model」的判据落点变成了这个字面量 + 那张登记表；子串匹配
    `AuthorityModel.opaque_single_onlyoffice` 从此只能证明「注释里提过它」。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "commit_bytes"
    ]
    assert len(calls) == 1, (
        f"{path.name} 里 `commit_bytes` 调用点有 {len(calls)} 处（应恰 1 处）"
    )
    lane_kw = [kw for kw in calls[0].keywords if kw.arg == "lane_id"]
    assert len(lane_kw) == 1, f"{path.name}: `commit_bytes` 缺 `lane_id=` 实参"
    value = lane_kw[0].value
    assert isinstance(value, ast.Constant) and isinstance(value.value, str), (
        f"{path.name}: `lane_id=` 实参是 {ast.unparse(value)!r} 而不是字符串字面量 —— "
        "运行期变量会让 authority model 的静态判据退化成猜测"
    )
    return value.value


def _lane_registry() -> Any:
    """生产那份 opaque lane 登记表（authority model 的唯一真源）。"""
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    from app.services.workpaper_sync import opaque_entry_gate as OG  # noqa: PLC0415

    return OG


def _indexed_relpaths() -> set[str]:
    """`_index.json` 登记的相对路径集合（分隔符归一为 /）。"""
    index = _load(TEMPLATE_INDEX)
    return {str(f["relative_path"]).replace("\\", "/") for f in index["files"]}


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


# ════════════════════════════════════════════════════════════════════════════
# 判据自检 —— 判据本身不能恒真
# ════════════════════════════════════════════════════════════════════════════
class TestGuardSelfChecks:
    """反向自检：辅助函数既不能什么都不做，也不能把代码一起剥掉/截掉。"""

    def test_strip_comments_self_check(self) -> None:
        sample = (
            "// leading line comment\n"
            "/* block */\n"
            "const KEEP = 'value' // trailing\n"
            "<!-- html comment -->\n"
            "const ALSO = 'x'\n"
        )
        stripped = _strip_ts_comments(sample)
        for gone in ("leading line comment", "block", "trailing", "html comment"):
            assert gone not in stripped, f"{gone!r} 应被剥掉"
        assert "const KEEP = 'value'" in stripped
        assert "const ALSO = 'x'" in stripped

    def test_vue_template_extraction_does_not_stop_at_inner_template(self) -> None:
        """`</template>` 提前闭合的坑：截取必须以 `<script` 为界。"""
        sfc = (
            "<template>\n"
            "  <div>\n"
            "    <el-tooltip>\n"
            "      <template #content>inner</template>\n"
            "    </el-tooltip>\n"
            "    <MarkerTag />\n"
            "  </div>\n"
            "</template>\n"
            "<script setup lang=\"ts\">\nconst x = 1\n</script>\n"
        )
        head = _vue_template(sfc)
        assert "<MarkerTag />" in head, (
            "外层模板尾部的标签被截掉了 —— 用 `</template>` 切会停在内层具名插槽处"
        )
        assert "const x = 1" not in head, "script 内容不该被当成模板"

    def test_toolbar_block_extraction_is_bounded(self) -> None:
        """区块截取必须按同缩进闭合，不能吞掉后面的兄弟节点。"""
        template = (
            "<template>\n"
            "  <div class=\"host\">\n"
            "    <div class=\"toolbar\">\n"
            "      <A />\n"
            "      <div class=\"nested\">\n"
            "        <B />\n"
            "      </div>\n"
            "    </div>\n"
            "    <OutsideTag />\n"
            "  </div>\n"
            "</template>\n"
        )
        block = _toolbar_block(template, 'class="toolbar"')
        assert "<A />" in block and "<B />" in block, "区块内的节点被漏掉"
        assert "<OutsideTag />" not in block, "区块把兄弟节点吞进来了 ⇒ 判据范围失控"

    def test_toolbar_block_rejects_ambiguous_anchor(self) -> None:
        """锚点命中多处必须报错，而不是取第一处（取第一处会让判据锁错区块）。"""
        template = (
            "<template>\n"
            "  <div class=\"toolbar\">\n"
            "  </div>\n"
            "  <div class=\"toolbar\">\n"
            "  </div>\n"
            "</template>\n"
        )
        with pytest.raises(AssertionError, match="命中 2 次"):
            _toolbar_block(template, 'class="toolbar"')

    def test_all_required_artifacts_exist(self) -> None:
        """本文件依赖的每个真源都必须真存在 —— 缺文件一律 fail closed，不 skip。"""
        for path in (
            MANIFEST_SLICE_PATH,
            DELETION_PLAN_PATH,
            PARADIGM_PATH,
            FULL_MANIFEST_PATH,
            D_SLICE_PATH,
            E_SLICE_PATH,
            CONTRACT_DIR,
            TEMPLATE_DIR / "F",
            TEMPLATE_INDEX,
            CHECKLIST_ROUTER,
            TEMPLATE_FINDER,
            PLAN_SYNC,
            SUMMARY_SYNC,
            REGISTRY,
            NOTICE_MODULE,
            NOTICE_COMPONENT,
        ):
            assert path.exists(), (
                f"{path} 不存在。缺真源必须打红：`if not x.exists(): return` / "
                "`pytest.skip(...)` 都是 fail-open —— 文件一消失判据就自动通过"
            )


# ════════════════════════════════════════════════════════════════════════════
# AC 12.8 / 12.9 / 12.1 / 1.3：裁决合法性
# ════════════════════════════════════════════════════════════════════════════
class TestAdjudicationLegality:
    """
    **Validates: Requirements 12.1**

    AC 12.8 原文：「无 HTML 对端的纯 OO entry SHALL 标为 `single_onlyoffice`；
    不得为满足数字伪造字段映射或修改模板制造对端。」判据是**有没有 HTML 对端**，
    不是「adapter / contract / bundle 还不存在」。
    """

    def test_every_entry_has_a_binary_html_counterpart_verdict(
        self, manifest_slice: dict
    ) -> None:
        """step 3 必须产出二值结论；unresolved / unknown / 空值都不是结论（AP-3）。"""
        assert manifest_slice["independent_entries"], "entry 列表为空 ⇒ 后续判据全无分母"
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

    def test_adjudication_reason_is_not_circular(
        self, manifest_slice: dict, paradigm: dict
    ) -> None:
        """AP-1：不得用「本任务应交付的产物尚不存在」当裁决理由。

        判据取范式 JSON 登记的 `circular_reason_markers`（真源在范式，不在这里另写一份）。
        三个理由字段都扫 —— 只扫 `reason` 会让循环论证换到
        `not_bidirectional_because` 里照样通过。
        """
        markers = paradigm["adjudication_criteria"]["anti_patterns"][0][
            "circular_reason_markers"
        ]
        assert markers, "circular_reason_markers 为空 ⇒ 判据恒真"
        for entry in manifest_slice["independent_entries"]:
            adjudication = entry["adjudication"]
            for field in ("reason", "not_single_html_because", "not_bidirectional_because"):
                text = adjudication.get(field, "")
                hits = [m for m in markers if m in text]
                assert not hits, (
                    f"{entry['entry_id']} 的 adjudication.{field} 命中循环论证标记 {hits}。"
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

    def test_every_blocking_precondition_has_a_carrier(self, manifest_slice: dict) -> None:
        """反向：登记的阻断项必须有承载者（被某 entry 引用，或明确是 slice 级）。

        没有承载者的阻断项 = 死条目：它可以被修好而无人回来删，也可以永远挂着而不阻断
        任何东西。slice 级的（BP-6/BP-8/BP-10）在 `blocks` 里明写不是 bidirectional。
        """
        referenced: set[str] = set()
        for entry in manifest_slice["independent_entries"]:
            referenced.update(entry.get("capability_target_blocked_by", []))
        for bp in manifest_slice["blocking_preconditions"]:
            if bp["id"] in referenced:
                continue
            assert bp["blocks"] != "bidirectional", (
                f"{bp['id']} 声称阻断 bidirectional 却没有任何 entry 引用它 ⇒ 死条目"
            )


# ════════════════════════════════════════════════════════════════════════════
# HTML 对端事实的三边锁：slice ↔ 前端源码 ↔ 权威 xlsx
# ════════════════════════════════════════════════════════════════════════════
class TestHtmlCounterpartIsSourceBacked:
    """
    **Validates: Requirements 12.4**

    「有 HTML 对端」这个结论不能是自由文本 —— 每条都要能在磁盘上复核。
    F 循环的三处形态差异（复合传输键 / 两族行身份键 / 位置化缺陷）逐 entry 从 slice
    读声明再回源码核对，不写死单一形态。
    """

    def test_source_refs_point_at_real_paths(self, manifest_slice: dict) -> None:
        """每条 source_ref 的路径部分必须真存在（含 sheet!cell 形态的模板引用）。"""
        checked = 0
        for entry in manifest_slice["independent_entries"]:
            refs = entry.get("html_counterpart_source_refs")
            assert isinstance(refs, list) and len(refs) >= 6, (
                f"{entry['entry_id']} 的 html_counterpart_source_refs 太少（至少要有"
                "宿主 / 持久化 composable / 主表 owner / 两个后端端点 / render 策略 / "
                "模板单元格）"
            )
            for ref in refs:
                # 形如 path#L12 / path!sheet!cell = 'text' / 裸 path
                raw = ref.split("#")[0].split("!")[0].strip()
                candidate = ROOT / raw
                assert candidate.exists(), (
                    f"{entry['entry_id']} 的 source_ref {ref!r} 指向不存在的路径 {raw!r}"
                )
                checked += 1
        assert checked >= 48, f"source_ref 校验数 {checked} 太少 —— 分母可疑"

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

    def test_persistence_composable_really_calls_both_endpoints(
        self, manifest_slice: dict
    ) -> None:
        """第二边（持久化侧）：声称的 composable 必须真的 GET 且 PUT checklist-responses。

        🔴 只断言文件存在不够 —— 那退化成路径存在性判据。这里要求同一个模块里同时出现
        读与写两个调用，否则「业务内容落在 HTML 侧」这个结论没有写入路径支撑。
        """
        for entry in manifest_slice["independent_entries"]:
            declared = entry["html_counterpart"]["html_persistence_composable"]
            module = ROOT / declared.split("#")[0]
            assert module.is_file(), (
                f"{entry['entry_id']} 的 html_persistence_composable 不存在: {module}"
            )
            source = _strip_ts_comments(module.read_text(encoding="utf-8"))
            assert re.search(r"api\.get\(\s*`[^`]*checklist-responses`", source), (
                f"{entry['entry_id']}: {module.name} 里找不到 GET checklist-responses 的调用"
            )
            assert re.search(r"api\.put\(\s*`[^`]*checklist-responses`", source), (
                f"{entry['entry_id']}: {module.name} 里找不到 PUT checklist-responses 的调用 "
                "⇒ 只读不写的话业务内容并不落在 HTML 侧"
            )

    def test_transport_key_kind_is_declared_and_matches_the_source(
        self, manifest_slice: dict
    ) -> None:
        """复合传输键必须逐 entry 实测登记，且形态声明要与源码一致。

        三种合法形态各有各的源码判据：
        * `literal_item_id` —— owner 模块里必须有 `const X = '<item_id>'`；
        * `composite_sheet_code_plus_table_role` —— owner 模块里必须有拼接表达式
          （模板串含 `${sheetCode}` 或后端 sheet code 常量），且**不得**只有字面量；
        * `literal_item_id_with_legacy_alias` —— 必须同时能找到现行键与 legacy 键。
        """
        allowed = {
            "literal_item_id",
            "composite_sheet_code_plus_table_role",
            "per_sheet_literal_injected_into_generic_composable",
            "literal_item_id_with_legacy_alias",
        }
        kinds: dict[str, int] = {}
        for entry in manifest_slice["independent_entries"]:
            store = entry["html_counterpart"]
            kind = store.get("transport_key_kind")
            assert kind in allowed, (
                f"{entry['entry_id']} 的 transport_key_kind={kind!r} 不在 {sorted(allowed)}"
            )
            kinds[kind] = kinds.get(kind, 0) + 1
            shape = store.get("transport_key_shape")
            assert isinstance(shape, str) and shape.strip(), (
                f"{entry['entry_id']} 缺 transport_key_shape"
            )
            if kind == "composite_sheet_code_plus_table_role":
                assert store.get("transport_key_composition_source"), (
                    f"{entry['entry_id']} 声称拼接式复合键却没给 transport_key_composition_source"
                )
                family = store.get("sheet_codes_in_family")
                assert isinstance(family, list) and len(family) >= 2, (
                    f"{entry['entry_id']} 声称复合键却没列出 sheet_codes_in_family（≥2）"
                )
                assert "${" in shape or "{sheet" in shape, (
                    f"{entry['entry_id']} 的 transport_key_shape={shape!r} 看不出拼接结构"
                )
            if kind == "per_sheet_literal_injected_into_generic_composable":
                assert store.get("transport_key_injection_source"), (
                    f"{entry['entry_id']} 声称注入式键却没给 transport_key_injection_source"
                )
                assert store.get("composite_commit_entry_id"), (
                    f"{entry['entry_id']} 声称注入式键却没登记 composite_commit_entry_id —— "
                    "注入式本身不是复合键，本 entry 的复合性在 commit 侧"
                )
            if kind == "literal_item_id_with_legacy_alias":
                assert "LEGACY" in shape.upper() or "回退" in shape, (
                    f"{entry['entry_id']} 声称新旧双键却没在 shape 里写出旧键"
                )
        assert kinds.get("composite_sheet_code_plus_table_role", 0) >= 1, (
            "F2 核心组的 primary managed table 实测用 dataKey(sheetCode) 拼键，"
            f"slice 却登记了 {kinds.get('composite_sheet_code_plus_table_role', 0)} 条 ⇒ 形态漂移"
        )
        assert len(kinds) >= 3, (
            f"F 循环实测至少三种传输键形态并存，slice 只出现 {sorted(kinds)} ⇒ 调查缩水"
        )

    def test_composite_transport_key_mechanisms_are_source_backed(
        self, manifest_slice: dict
    ) -> None:
        """四种传输键机制逐条回源码核验 —— 每种有自己的判据，不通用。

        🔴 首轮把监盘的「注入式」误当成「拼接式」，去 useF2StocktakeQuestionnaire.ts 里找
        `${sheetCode}-` 表达式（那里没有），被本判据的前身当场打红。所以每种机制的
        `how_to_verify` 都要落成独立的源码探针。
        """
        block = manifest_slice["composite_transport_keys"]
        mechanisms = block["mechanisms"]
        assert len(mechanisms) >= 4, (
            f"只登记了 {len(mechanisms)} 种机制 —— 实测 F 循环有 4 种（拼接 / 注入 / "
            "复合 commit entry_id / 新旧双键）"
        )
        entry_ids = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        probes = {
            "template_literal_composed_from_sheet_code": (
                lambda src: bool(re.search(r"\$\{\s*(?:def\.)?sheetCode\s*\}-", src))
            ),
            "per_sheet_literal_injected_into_generic_composable": (
                lambda src: bool(re.search(r"opts\.(?:fieldsKey|rowsKey|noteKey)", src))
                or bool(re.search(r"(?:fieldsKey|rowsKey):\s*'F2-\d+", src))
            ),
            "composite_commit_entry_id_wp_code_hash_sheet_code": (
                lambda src: "opaque_entry_id(" in src
            ),
            "literal_item_id_with_legacy_alias": (
                lambda src: bool(re.search(r"LEGACY[A-Z_]*KEY\s*=|_LEGACY_KEY\s*=", src))
            ),
        }
        checked = 0
        seen_ids: set[str] = set()
        for mech in mechanisms:
            name = mech["name"]
            assert name in probes, f"机制 {name!r} 没有对应的源码探针 ⇒ 登记了但没人验"
            assert mech["id"] not in seen_ids, f"机制 id 重复: {mech['id']}"
            seen_ids.add(mech["id"])
            assert mech["how_to_verify"], f"{mech['id']} 缺 how_to_verify"
            sources = mech["sources"]
            assert isinstance(sources, list) and sources, f"{mech['id']} 没有 sources"
            probe = probes[name]
            # 🔴 **每个** source 都必须通过探针，不是「至少一个」。
            #    「至少一个」实测被绕过：CK-1 有 5 个 source，把其中一个换成不含
            #    `${sheetCode}-` 的模块后仍绿（其余 4 个还命中）⇒ 登记表可以混进
            #    不体现该机制的模块，而那正是「登记了但不成立」的假绿形态。
            bad: list[str] = []
            for rel in sources:
                path = ROOT / rel
                assert path.is_file(), f"{mech['id']} 的 source 不存在: {rel}"
                text = path.read_text(encoding="utf-8")
                stripped = _strip_ts_comments(text) if path.suffix in (".ts", ".vue") else text
                if not probe(stripped):
                    bad.append(rel)
                checked += 1
            assert not bad, (
                f"{mech['id']}（{name}）登记的 source 里有 {len(bad)} 个不体现该机制: {bad} "
                f"⇒ 判据是「{mech['how_to_verify']}」，这些模块过不了"
            )
            for eid in mech["entries_affected"]:
                assert eid in entry_ids, f"{mech['id']} 指向不存在的 entry {eid!r}"
            for eid in mech["primary_table_uses_it"]:
                assert eid in mech["entries_affected"], (
                    f"{mech['id']} 的 primary_table_uses_it 不是 entries_affected 的子集"
                )
        assert checked >= 15, f"机制源码核验数 {checked} 太少 —— 分母可疑"

        # 纯字面量 primary key 的 entry 集合必须与逐 entry 声明一致（两侧互锁）
        declared_plain = set(block["entries_with_plain_literal_primary_key"])
        actual_plain = {
            e["entry_id"]
            for e in manifest_slice["independent_entries"]
            if e["html_counterpart"]["transport_key_kind"] == "literal_item_id"
        }
        assert declared_plain == actual_plain, (
            f"composite_transport_keys 声称纯字面量 primary key 的是 {sorted(declared_plain)}，"
            f"逐 entry 现算是 {sorted(actual_plain)}"
        )

    def test_row_identity_key_and_generator_are_source_backed(
        self, manifest_slice: dict
    ) -> None:
        """行身份键与生成器逐 entry 回源码核对。

        🔴 不能像 D 循环那样写死 `row_identity_key == "rowId"`：F 循环实测 3 条是
        `rowId`、5 条是 `id`，生成器有 generateRowId / newContractCostId /
        newImpairmentProductId / genId(prefix) / 内联模板串五种。写死一种会让另一族的
        判据恒真。
        """
        seen_keys: set[str] = set()
        for entry in manifest_slice["independent_entries"]:
            store = entry["html_counterpart"]
            key = store["row_identity_key"]
            assert key in ("rowId", "id"), (
                f"{entry['entry_id']} 的 row_identity_key={key!r} 不是实测到的两族之一"
            )
            seen_keys.add(key)
            # 🔴 声明的键必须真是 owner 模块用来定位行的字段：`r.<key> === <key>`。
            #    只校验「键名在两族之内」是不够的（实测过：把 F2 核心组的 id 改成 rowId
            #    仍全绿，因为其余 4 条 entry 还有 id、两族都在，集合判据不动）。
            owner = ROOT / store["primary_table"]["owner_module"]
            owner_src = _strip_ts_comments(owner.read_text(encoding="utf-8"))
            other = "id" if key == "rowId" else "rowId"
            assert re.search(rf"\.{key}\s*===", owner_src), (
                f"{entry['entry_id']}: {owner.name} 里没有 `.{key} ===` 形态的行定位 ⇒ "
                f"slice 声称行身份键是 {key!r}，但源码不按它定位行"
            )
            assert not re.search(rf"\.{other}\s*===", owner_src), (
                f"{entry['entry_id']}: {owner.name} 里按 `.{other} ===` 定位行，"
                f"而 slice 声称的键是 {key!r} ⇒ 两者不一致"
            )
            forbidden = store["forbidden_row_identity_kinds"]
            assert {"array_index", "ordinal", "position"} <= set(forbidden), (
                f"{entry['entry_id']} 的 forbidden_row_identity_kinds 缺位置化种类"
            )
            ref = store["row_identity_generator_source"]
            path = ROOT / ref.split("#")[0]
            assert path.is_file(), (
                f"{entry['entry_id']} 的 row_identity_generator_source 不存在: {path}"
            )
            source = _strip_ts_comments(path.read_text(encoding="utf-8"))
            form = store["row_identity_generator_form"]
            # 生成器形态里的核心片段必须在源码里（取 `-${Date.now` 之前的稳定前缀）
            probe = re.search(r"`([a-z0-9]*)-\$\{", form) or re.search(r"`(row)-\$\{", form)
            if probe:
                marker = f"`{probe.group(1)}-${{"
                assert marker in source, (
                    f"{entry['entry_id']}: {path.name} 里找不到生成器前缀 {marker!r}"
                )
            else:
                assert "Date.now()" in source, (
                    f"{entry['entry_id']}: {path.name} 里找不到 Date.now() 形态的行 id 生成"
                )
        assert seen_keys == {"rowId", "id"}, (
            f"F 循环实测两族行身份键并存，slice 只出现 {sorted(seen_keys)} ⇒ 调查缩水或形态漂移"
        )

    def test_positional_row_identity_defects_are_real_and_exhaustive(
        self, manifest_slice: dict
    ) -> None:
        """位置化行身份缺陷必须双向锁死：声称有的源码里真有，声称没有的真没有。

        🔴 只查「声称有的真有」会让漏报（某 entry 也有下标派生但 slice 写 false）通过；
        只查「声称没有的真没有」会让虚报（拿一个不存在的缺陷凑 BP）通过。两侧都要。
        """
        index_pattern = re.compile(r"\?\?\s*`[^`]*\$\{\s*i\s*\}`|\|\|\s*i\s*\+\s*1|\$\{\s*i\s*\}")
        flagged: list[str] = []
        for entry in manifest_slice["independent_entries"]:
            store = entry["html_counterpart"]
            owner = ROOT / store["primary_table"]["owner_module"]
            source = _strip_ts_comments(owner.read_text(encoding="utf-8"))
            # 只在「构造行 id」的语句上找位置化派生，避免把普通循环下标当缺陷
            id_lines = [
                ln
                for ln in source.splitlines()
                if re.search(r"\bid\s*:", ln) or re.search(r"emptyRow\(", ln)
            ]
            actual = any(index_pattern.search(ln) for ln in id_lines)
            declared = bool(store.get("row_identity_is_positional"))
            assert declared == actual, (
                f"{entry['entry_id']}: row_identity_is_positional 声称 {declared}，"
                f"但 {owner.name} 的行 id 构造语句实测 {actual}"
                f"（命中行：{[ln.strip()[:110] for ln in id_lines if index_pattern.search(ln)]}）"
            )
            if declared:
                assert store.get("row_identity_positional_defect"), (
                    f"{entry['entry_id']} 声称位置化却没写 row_identity_positional_defect"
                )
                flagged.append(entry["entry_id"])
        assert set(flagged) == {
            "xlsx/gt-f2-inventory-main",
            "xlsx/gt-f5-cost-of-sales",
        }, f"位置化缺陷 entry 集合实测为 {sorted(flagged)}，与冻结结论不符"

    def test_primary_table_is_declared_by_its_owner_module(self, manifest_slice: dict) -> None:
        """第二边：primary table 的 item_id 必须真由 owner 模块声明或拼出。

        `owner_declaration_kind` 三态各有各的判据，不许互相顶替：
        * `module_constant` ⇒ 必须有 `const <NAME> = '<item_id>'` 且常量名一致；
        * `inline_literal` ⇒ 字面量出现且**不得**已提成模块常量；
        * `composed_from_sheet_code` ⇒ 拼接表达式出现，且字面量**不该**出现
          （出现就说明它其实是字面量键，slice 的形态声明错了）。
        """
        kinds: dict[str, int] = {}
        for entry in manifest_slice["independent_entries"]:
            primary = entry["html_counterpart"]["primary_table"]
            module = ROOT / primary["owner_module"]
            assert module.is_file(), f"{entry['entry_id']} 的 owner_module 不存在: {module}"
            source = _strip_ts_comments(module.read_text(encoding="utf-8"))
            item_id = primary["item_id"]
            constant = primary["owner_constant"]
            kind = primary["owner_declaration_kind"]
            kinds[kind] = kinds.get(kind, 0) + 1
            const_pattern = re.compile(
                r"const\s+([A-Z0-9_]+)\s*=\s*['\"]" + re.escape(item_id) + r"['\"]"
            )
            found = const_pattern.search(source)
            if kind == "module_constant":
                assert constant, f"{entry['entry_id']}: module_constant 必须给 owner_constant"
                assert found, (
                    f"{entry['entry_id']}: {module.name} 里找不到 "
                    f"const {constant} = '{item_id}'"
                )
                assert found.group(1) == constant, (
                    f"{entry['entry_id']}: 常量名应为 {constant}，实为 {found.group(1)}"
                )
            elif kind == "inline_literal":
                assert constant is None
                assert f"'{item_id}'" in source, (
                    f"{entry['entry_id']}: {module.name} 里找不到字面量 '{item_id}'"
                )
                assert not found, (
                    f"{entry['entry_id']}: {module.name} 已把 '{item_id}' 提成模块常量 "
                    f"{found.group(1) if found else '?'}，slice 需同步更新"
                )
            elif kind == "composed_from_sheet_code":
                assert constant is None
                expr = primary.get("owner_composition_expression")
                assert expr, f"{entry['entry_id']}: 缺 owner_composition_expression"
                assert expr.strip("`") in source or expr in source, (
                    f"{entry['entry_id']}: {module.name} 里找不到拼接表达式 {expr!r}"
                )
                assert not found, (
                    f"{entry['entry_id']}: {module.name} 里 '{item_id}' 其实是模块常量 ⇒ "
                    "owner_declaration_kind 声明成 composed_from_sheet_code 是错的"
                )
            else:
                pytest.fail(f"{entry['entry_id']}: 未知 owner_declaration_kind={kind!r}")
        assert kinds.get("composed_from_sheet_code", 0) >= 1, (
            "F2 核心组的主表键实测是从 sheetCode 拼出的，slice 却没有任何 "
            "composed_from_sheet_code ⇒ 形态调查缩水"
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

        🔴 Task 46 实测的 D4 同型缺陷：`D/D4收入底稿.xlsx` 磁盘上有，但不在
        `_index.json` 里，`find_template_file_any()` 对任何 D4 码都永不返回它。
        F 循环有同型对象 `F/F2存货.xlsx`（见 BP-8），它**不得**出现在任何 template_ref 里。
        """
        indexed = _indexed_relpaths()
        assert len(indexed) > 400, f"_index.json 只索引到 {len(indexed)} 个文件，可疑"
        for entry in manifest_slice["independent_entries"]:
            ref = entry.get("template_ref")
            assert isinstance(ref, str) and ref.strip(), (
                f"{entry['entry_id']} 的 template_ref 为空 —— 不允许缺省跳过"
            )
            assert ref in indexed, (
                f"{entry['entry_id']} 的 template_ref {ref!r} 不在 "
                "backend/wp_templates/_index.json 里 ⇒ 运行时 finder 永不返回它，"
                "不能当权威模板"
            )
            assert (TEMPLATE_DIR / ref).is_file(), (
                f"{entry['entry_id']} 的 template_ref {ref!r} 在索引里但磁盘上不存在"
            )


# ════════════════════════════════════════════════════════════════════════════
# Property 21：contract 与 adapter —— 本文件**不宣称通过**的部分写在类名与 docstring 里
# ════════════════════════════════════════════════════════════════════════════
class TestProperty21ContractFieldsNotClaimedPassingForFCycle:
    """
    **Validates: Requirements 6.2**

    ═══ 空分母怎么处理 ═══

    「本 slice 里没有 contract，所以 Property 21 通过」是重言式（同 spec 的 Task 20
    专门写代码拒绝这种论证）。诚实的写法是区分两件事：

    * **本 slice 无适用分母的部分** —— F 循环已发布的 per-entry contract 数 = 0
      （这是可复核事实：逐文件读 `review.entry_id`，四条生产契约分别属 b60/D2/G7/H1），
      字段级 col 占位与 contract 完整性判据由 **pilot** 承载
      （`test_task13_contract_registry.py` + `test_task41_d2_large_json_pilot.py`）。
      **本类不宣称 Property 21 在 F 循环上通过**，只断言这个前提成立且承载者真存在。
    * **有真分母的部分** —— F 循环的真分母在 Property 28（模板 digest / structure hash /
      sheet!cell）与 F2 Word lane 的复合 entry_id 上，见后面两个类。
    """

    def test_no_f_entry_has_a_contract_and_the_pilot_carriers_exist(
        self, manifest_slice: dict
    ) -> None:
        """分母为 0 这件事本身要被证实，并指向承载判据的 pilot（不是「所以通过」）。"""
        f_ids = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        assert f_ids, "F entry 集合为空 ⇒ 本判据无分母"

        contract_files = sorted(CONTRACT_DIR.glob("*.json"))
        assert len(contract_files) >= 4, (
            f"契约目录只有 {len(contract_files)} 个文件 —— 分母可疑，"
            "「F 循环没有契约」这个结论必须建立在真的读过全部契约之上"
        )
        owners: dict[str, str] = {}
        for path in contract_files:
            if path.name.startswith("_"):
                continue  # _example.candidate.json 是模板样例，不是生产契约
            entry_id = (_load(path).get("review") or {}).get("entry_id")
            if entry_id:
                owners[path.name] = entry_id
        assert owners, "读不出任何契约的 review.entry_id ⇒ 判据失去分母"
        leaked = {name: eid for name, eid in owners.items() if eid in f_ids}
        assert not leaked, (
            f"契约 {leaked} 归属 F 循环 entry，「F 循环 contract 数 = 0」这个前提不再成立 "
            "⇒ 必须在此补齐字段级判据（stable_field_key / json_pointer / mode / "
            "value_type / source_ref 与 col_ 占位拒绝）"
        )

        pilot_guard = BACKEND / "tests" / "workpaper_sync" / "test_task41_d2_large_json_pilot.py"
        registry_guard = BACKEND / "tests" / "workpaper_sync" / "test_task13_contract_registry.py"
        assert pilot_guard.is_file(), (
            f"{pilot_guard} 不存在 —— 承载 Property 21 的 pilot 判据缺失，"
            "「由 pilot 承载」就成了空头承诺"
        )
        assert registry_guard.is_file(), f"{registry_guard} 不存在"

    def test_no_f_entry_has_a_registered_adapter(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        """F 循环 adapter 数 = 0 —— slice 与 source manifest 两侧都验。"""
        f_ids = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        for entry in manifest_slice["independent_entries"]:
            assert entry["adapter_id"] is None, (
                f"{entry['entry_id']} 出现了 adapter_id={entry['adapter_id']!r}，"
                "本 slice 的「无已注册 adapter」前提不再成立"
            )
        seen = 0
        for entry in full_manifest["entries"]:
            if entry["entry_id"] in f_ids:
                assert entry.get("adapter_id") is None, (
                    f"source manifest 里 {entry['entry_id']} 已有 adapter_id"
                )
                seen += 1
        assert seen == len(f_ids), (
            f"source manifest 里只找到 {seen}/{len(f_ids)} 条 F entry ⇒ slice 与 manifest 脱钩"
        )

    def test_registry_delivered_contracts_contain_no_f_entry(self) -> None:
        """registry 的 DELIVERED_PER_ENTRY_CONTRACTS 登记表里不得出现 F 循环 entry。"""
        source = REGISTRY.read_text(encoding="utf-8")
        block = re.search(
            r"DELIVERED_PER_ENTRY_CONTRACTS[^=]*=\s*\(([\s\S]*?)\n\)\n", source
        )
        assert block, "找不到 DELIVERED_PER_ENTRY_CONTRACTS 的声明 ⇒ 判据无分母"
        declared = re.findall(r"\"entry_id\":\s*\"([^\"]+)\"", block.group(1))
        assert len(declared) >= 4, (
            f"登记表只解析出 {len(declared)} 条 entry_id ⇒ 正则失配，判据会恒真"
        )
        f_like = [e for e in declared if re.match(r"^xlsx/(gt-)?f\d", e)]
        assert not f_like, f"DELIVERED_PER_ENTRY_CONTRACTS 里出现 F 循环 entry: {f_like}"

    def test_property_denominator_block_declares_what_is_not_claimed(
        self, manifest_slice: dict
    ) -> None:
        """slice 必须显式写明「Property 21 在 F 循环上不宣称通过」。

        🔴 这条不是形式主义：Task 46 首轮之所以能把空分母写成通过，正是因为没有任何
        字段迫使作者把「宣称 / 不宣称」写下来。
        """
        block = manifest_slice["property_denominators"]
        assert block["property_21"]["not_claimed_passing"] is True, (
            "slice 的 property_21.not_claimed_passing 必须为 true —— F 循环 contract 数为 0，"
            "不得宣称该 Property 通过"
        )
        assert block["property_28"]["not_claimed_passing"] is False, (
            "Property 28 在 F 循环有真分母（模板 digest），必须宣称通过而不是回避"
        )
        assert block["property_69"].get("not_claimed_passing_part"), (
            "Property 69 的正向逐 scenario 闭合缺分母，必须写明哪部分不宣称通过"
        )
        assert block["property_70"]["not_claimed_passing"] is False


# ════════════════════════════════════════════════════════════════════════════
# Property 28：immutable definition 漂移 fail closed（真分母，现算）
# ════════════════════════════════════════════════════════════════════════════
class TestProperty28DefinitionDriftFailClosed:
    """
    **Validates: Requirements 6.10**

    F 循环的真分母：18 个权威模板的 size + sha256、8 张主模板的
    `normalized_structure_hash`（由 excel_instrumentation 现算）、8 组 sheet!cell 真读。
    任一字节漂移即红 —— 不是「无可漂移 identity 所以通过」。
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
        assert len(files) >= 8, f"只登记了 {len(files)} 个模板，少于独立 entry 数"
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

    def test_normalized_structure_hash_recomputes(self, manifest_slice: dict) -> None:
        """8 张主模板的 normalized_structure_hash 由生产实现现算复核。

        用的是生产代码里的同一个函数（`excel_instrumentation.normalized_structure_hash`），
        不在这里另写一份 —— 另写一份就是第二个真源，两侧漂移时谁都不红。
        """
        sys.path.insert(0, str(BACKEND))
        from app.services.workpaper_sync.excel_instrumentation import (  # noqa: PLC0415
            normalized_structure_hash,
        )

        block = manifest_slice["authoritative_templates"]
        root = ROOT / block["root"]
        checked = 0
        for record in block["files"]:
            expected = record.get("normalized_structure_hash")
            if expected is None:
                continue
            path = root / record["name"]
            actual = normalized_structure_hash(path.read_bytes())
            assert actual == expected, (
                f"{record['name']} 的 normalized_structure_hash 漂移: "
                f"实测 {actual}，登记 {expected}"
            )
            checked += 1
        assert checked == 8, (
            f"只有 {checked} 张模板登记了 normalized_structure_hash，应为 8（每个 entry 一张）"
            " ⇒ Property 28 的结构分母缩水"
        )

    def test_digests_are_real_digests(self, manifest_slice: dict) -> None:
        """登记的 digest 必须是真 64 位十六进制且非全零（Requirement 2.3 同族）。"""
        digest_re = re.compile(r"^[0-9a-f]{64}$")
        for record in manifest_slice["authoritative_templates"]["files"]:
            for key in ("sha256", "normalized_structure_hash"):
                value = record.get(key)
                if value is None:
                    continue
                assert digest_re.match(value), f"{record['name']}.{key} 非法: {value!r}"
                assert set(value) != {"0"}, f"{record['name']}.{key} 是全零 hash"

    def test_template_owner_mapping_is_consistent(self, manifest_slice: dict) -> None:
        """SR-8：belongs_to_entry 非 null 必须命中本 slice 的 entry；为 null 必须给 excluded_reason。"""
        entry_ids = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        owners: list[str] = []
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
                owners.append(owner)
        assert len(owners) == len(set(owners)), (
            f"belongs_to_entry 不是单射（同一 entry 被多张模板认领）: {owners}"
        )
        assert set(owners) == entry_ids, (
            f"每个 entry 必须恰有一张归属模板，缺 {sorted(entry_ids - set(owners))}"
        )

    def test_in_runtime_index_flag_recomputes(self, manifest_slice: dict) -> None:
        """登记的 in_runtime_index 必须与 _index.json 现算一致（防手填）。"""
        indexed = _indexed_relpaths()
        root_rel = manifest_slice["authoritative_templates"]["root"].split("/")[-1]
        unreachable: list[str] = []
        for record in manifest_slice["authoritative_templates"]["files"]:
            actual = f"{root_rel}/{record['name']}" in indexed
            assert record.get("in_runtime_index") == actual, (
                f"{record['name']} 的 in_runtime_index 登记为 "
                f"{record.get('in_runtime_index')}，现算为 {actual}"
            )
            if not actual:
                unreachable.append(record["name"])
        assert set(unreachable) == {
            "F2-22 存货监盘计划.docx",
            "F2-23 存货监盘小结.docx",
            "F2存货.xlsx",
        }, f"未索引文件集合实测为 {sorted(unreachable)}，与冻结结论不符"

    def test_every_entry_template_ref_is_registered_with_digest(
        self, manifest_slice: dict
    ) -> None:
        """template_ref **必须非空**，且它指向的文件在 authoritative_templates 里带 digest。

        🔴 不许写成 `if ref:` —— template_ref 为 null 时整条跳过是 Task 46 首轮实测过的
        fail-open（置 null 后 36 例全绿）。
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
            assert record.get("normalized_structure_hash"), (
                f"{entry['entry_id']} 的 template_ref 没有 normalized_structure_hash ⇒ "
                "结构漂移无从检出"
            )
            path = root / name
            assert path.is_file()
            assert _sha256_of(path) == record["sha256"]
            assert path.stat().st_size == record["size"]

    def test_bp5_wrong_workbook_fallback_is_reproducible(self, manifest_slice: dict) -> None:
        """BP-5 双向锁：F2 整册码回落**真的**返回会计政策册（不是审定明细表）。

        🔴 这条既锁缺陷存在（描述不是猜的），也锁修复后必须回来改 slice：解析器修好后
        它会打红，逼作者把 BP-5 的 status 从 REGISTERED_NOT_FIXED 改掉。
        """
        sys.path.insert(0, str(BACKEND))
        from app.services.wp_template_finder import (  # noqa: PLC0415
            find_template_file,
            find_template_file_any,
        )

        bp5 = next(
            bp for bp in manifest_slice["blocking_preconditions"] if bp["id"] == "BP-5"
        )
        assert bp5["status"] == "REGISTERED_NOT_FIXED"

        fallback = find_template_file("F2")
        assert fallback is not None, "find_template_file('F2') 返回 None —— 形态已变"
        assert fallback.name == "F2-16 存货及跌价准备-会计政策（Leap-常规程序）.xlsx", (
            f"F2 整册码回落实测返回 {fallback.name!r} —— 与 BP-5 描述不符。"
            "若解析器已修好，请更新 BP-5 的 status 与本判据"
        )
        assert find_template_file_any("F2") == fallback, (
            "find_template_file_any('F2') 与 find_template_file('F2') 结果不一致 —— "
            "BP-5 的复现路径已变"
        )
        # 反向：审定明细表册确实是 F2 核心组的 template_ref，且能被子码正确解析
        main = next(
            e
            for e in manifest_slice["independent_entries"]
            if e["entry_id"] == "xlsx/gt-f2-inventory-main"
        )
        expected = main["template_ref"].split("/")[-1]
        assert fallback.name != expected, (
            "回落结果与 F2 核心组的 template_ref 相同 ⇒ BP-5 描述的缺陷不存在，不得虚报"
        )
        by_sub = find_template_file_any("F2-1")
        assert by_sub is not None and by_sub.name == expected, (
            f"子码 F2-1 应解析到 {expected!r}，实测 {by_sub.name if by_sub else None!r} ⇒ "
            "BP-5「只在回落路径暴露」这个限定不成立"
        )

    def test_bp8_unreachable_workbook_is_really_unreachable(
        self, manifest_slice: dict
    ) -> None:
        """BP-8 双向锁：`F2存货.xlsx` 真的不可达（任何 F2* 码都不返回它）。"""
        sys.path.insert(0, str(BACKEND))
        from app.services.wp_template_finder import (  # noqa: PLC0415
            find_all_template_files,
            find_template_file_any,
        )

        bp8 = next(
            bp for bp in manifest_slice["blocking_preconditions"] if bp["id"] == "BP-8"
        )
        assert bp8["status"] == "REGISTERED_NOT_FIXED"
        target = TEMPLATE_DIR / "F" / "F2存货.xlsx"
        assert target.is_file(), (
            "F2存货.xlsx 已不在磁盘上 ⇒ BP-8 已被处理，请更新 slice 与本判据"
        )
        probes = ("F2", "F2-1", "F2-2", "F2-16", "F2-21", "F2-38", "F2-47", "F2-55", "F2-61")
        for code in probes:
            got = find_template_file_any(code)
            assert got is None or got.name != target.name, (
                f"find_template_file_any({code!r}) 返回了 {target.name} —— "
                "BP-8「运行时不可达」的结论不成立"
            )
        all_f2 = {p.name for p in find_all_template_files("F2")}
        assert target.name not in all_f2, (
            f"find_all_template_files('F2') 里出现 {target.name} ⇒ 它其实可达"
        )
        assert len(all_f2) >= 9, (
            f"find_all_template_files('F2') 只返回 {len(all_f2)} 本 ⇒ 分母可疑，"
            "「不含合册」这个结论可能只是因为整体返回为空"
        )


# ════════════════════════════════════════════════════════════════════════════
# Property 69：evidence 与计数 —— 负向分母真验，正向逐 scenario 闭合不宣称通过
# ════════════════════════════════════════════════════════════════════════════
class TestProperty69EvidenceAndCounters:
    """
    **Validates: Requirements 12.10, 12.11**

    F 循环没有任何 sync_test_run，故 evidence 的**正向**闭合（逐 scenario 实体 +
    服务端重算 summary）在这里没有分母 —— 那部分由 Task 44 同型的 OO 9.4 gate 承载，
    已登记 BP-4，**本类不宣称它通过**。本类真验的是负向分母与计数的可复算性。
    """

    def test_slice_scope_is_recomputable_from_the_manifest(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        """slice_scope.selection_rule 必须能现算出同一个 entry 集合（不是手抄清单）。"""
        scope = manifest_slice["slice_scope"]
        assert scope["cycle"] == "F"
        assert scope["document_type"] == "xlsx"
        assert scope["selection_rule"], "selection_rule 为空 ⇒ 「8」在文档里无推导"

        independent: set[str] = set()
        duplicates: set[str] = set()
        for entry in full_manifest["entries"]:
            if entry.get("document_type") != "xlsx":
                continue
            patterns = entry.get("wp_match", {}).get("wp_code_patterns", [])
            if not any(str(p).startswith("F") for p in patterns):
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

    def test_no_f_docx_entry_exists_in_the_source_manifest(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        """F2 Word lane 的排除边界：source manifest 里没有 F 码 docx entry。

        这是 `slice_scope.excluded_from_slice` 第 1 条的可复核依据 —— 若哪天 Word 宿主
        真的产生了 F 码 docx entry，本条打红，提醒重算「与 F2 Word lane 分开计数」。
        """
        docx_entries = [e for e in full_manifest["entries"] if e.get("document_type") == "docx"]
        assert docx_entries, "全量 manifest 里一条 docx entry 都没有 ⇒ 判据无分母"
        f_docx = [
            e["entry_id"]
            for e in docx_entries
            if any(str(p).startswith("F") for p in e.get("wp_match", {}).get("wp_code_patterns", []))
        ]
        assert not f_docx, (
            f"source manifest 里出现 F 码 docx entry {f_docx} ⇒ Word lane 的排除边界要重算"
        )
        excluded = manifest_slice["slice_scope"]["excluded_from_slice"]
        assert any("F2-22" in item["what"] and "F2-23" in item["what"] for item in excluded), (
            "excluded_from_slice 必须显式排除 F2-22 / F2-23 的 Word 通道并写明理由"
        )

    def test_excluded_items_have_reasons(self, manifest_slice: dict) -> None:
        excluded = manifest_slice["slice_scope"]["excluded_from_slice"]
        assert len(excluded) >= 4, (
            f"excluded_from_slice 只有 {len(excluded)} 条 —— Word 通道 / F0 函证 / "
            "不可达合册 / sub-tab 桩四类都要显式排除"
        )
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

    def test_contract_test_points_at_this_file(self, manifest_slice: dict) -> None:
        """evidence.contract_test 必须指向真存在的守卫文件（且就是本文件）。"""
        expected = "backend/tests/workpaper_sync/test_task48_f_cycle_migration.py"
        for entry in manifest_slice["independent_entries"]:
            declared = entry["evidence"]["contract_test"]
            assert declared == expected, (
                f"{entry['entry_id']} 的 contract_test={declared!r}，应为 {expected!r}"
            )
            assert (ROOT / declared).is_file()

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
        for counter_key, kind in (
            ("entries_with_composite_transport_key", "composite_sheet_code_plus_table_role"),
            (
                "entries_with_per_sheet_injected_transport_key",
                "per_sheet_literal_injected_into_generic_composable",
            ),
            ("entries_with_legacy_alias_transport_key", "literal_item_id_with_legacy_alias"),
            ("entries_with_plain_literal_transport_key", "literal_item_id"),
        ):
            expected = sum(
                1 for e in entries if e["html_counterpart"]["transport_key_kind"] == kind
            )
            assert summary[counter_key] == expected, (
                f"{counter_key} 应为 {expected}，slice 写 {summary[counter_key]}"
            )
        assert summary["composite_transport_key_mechanisms"] == len(
            manifest_slice["composite_transport_keys"]["mechanisms"]
        ), "机制计数与 composite_transport_keys.mechanisms 实际条数不符"
        assert summary["entries_with_positional_row_identity_defect"] == sum(
            1 for e in entries if e["html_counterpart"].get("row_identity_is_positional")
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
        assert summary["pilot_contract_published"] == 0, (
            "F 循环没有 pilot（registry 四条 pilot 无 F 条目）⇒ 该计数必须是 0"
        )

    def test_blocking_preconditions_are_complete(self, manifest_slice: dict) -> None:
        """每条阻断项必须有 id/blocks/what/后果/status/must_fix_before/source_refs。

        「后果」在事实范式里有两种形态（单串 `consequence` / 数组 `observable_consequences`），
        按 one-of 校验：至少一个非空。
        """
        blocking = manifest_slice["blocking_preconditions"]
        assert len(blocking) >= 8, f"只登记了 {len(blocking)} 条阻断项，可疑"
        ids = [bp["id"] for bp in blocking]
        assert len(ids) == len(set(ids)), f"阻断项 id 重复: {ids}"
        for bp in blocking:
            for key in ("id", "blocks", "what", "status", "must_fix_before", "owner_task"):
                assert bp.get(key), f"阻断项 {bp.get('id')} 缺 {key}"
            assert bp.get("consequence") or bp.get("observable_consequences"), (
                f"阻断项 {bp['id']} 既没有 consequence 也没有 observable_consequences —— "
                "后果必须写明，否则它只是一句「有问题」"
            )
            assert bp.get("why_not_fixed_here"), (
                f"阻断项 {bp['id']} 没写 why_not_fixed_here ⇒ 「只登记不修」缺理由"
            )
            refs = bp.get("source_refs")
            assert isinstance(refs, list) and refs, (
                f"阻断项 {bp['id']} 没有 source_refs —— 无据可查的阻断项等于自由文本"
            )
            for ref in refs:
                raw = ref.split("#")[0].strip()
                assert (ROOT / raw).exists(), (
                    f"阻断项 {bp['id']} 的 source_ref {ref!r} 指向不存在的路径"
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
        assert len(isolation["assertions"]) >= 5

    def test_f_entries_disjoint_from_d_and_e_slices(self, manifest_slice: dict) -> None:
        """D / E / F 三个 slice 的 entry 集合两两不相交（重复计数 = 假迁移进度）。"""
        f_ids = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        for label, path in (("D", D_SLICE_PATH), ("E", E_SLICE_PATH)):
            assert path.is_file(), f"{path} 不存在（{label} 循环交付物）"
            other = {e["entry_id"] for e in _load(path)["independent_entries"]}
            assert other, f"{label} slice 的 entry 集合为空 ⇒ 不相交判据恒真"
            assert not (f_ids & other), f"F/{label} slice entry 相交: {sorted(f_ids & other)}"

    def test_no_entry_carries_a_per_entry_contract_field(self, manifest_slice: dict) -> None:
        """F 循环一条 contract 都没有 ⇒ 任何 entry 都不得挂 per_entry_contract。"""
        for entry in manifest_slice["independent_entries"]:
            assert "per_entry_contract" not in entry, (
                f"{entry['entry_id']} 挂了 per_entry_contract —— F 循环无契约，"
                "不得借用其他循环的 contract_id"
            )

    def test_word_lane_block_only_on_the_stocktake_entry(self, manifest_slice: dict) -> None:
        """F2 Word lane 的登记只能出现在监盘 entry 上（不得跨 entry 复用其 authority model）。"""
        carriers = [
            e["entry_id"]
            for e in manifest_slice["independent_entries"]
            if "partially_wired_word_lane" in e
        ]
        assert carriers == ["xlsx/gt-f2-stocktake-bundle"], (
            f"partially_wired_word_lane 出现在 {carriers} —— 只允许监盘 entry 有"
        )

    def test_deletion_plan_entries_are_distinct(self, deletion_plan: dict) -> None:
        ids = [e["entry_id"] for e in deletion_plan["entries"]]
        assert len(ids) == len(set(ids))

    def test_deletion_plan_composables_are_distinct_and_real(self, deletion_plan: dict) -> None:
        """legacy composable 不得跨 entry 复用，且每条必须真在磁盘上。"""
        all_composables: list[str] = []
        for entry in deletion_plan["entries"]:
            for comp in entry.get("legacy_composables_to_delete", []):
                all_composables.append(comp["file"])
                assert (ROOT / comp["file"]).is_file(), (
                    f"deletion plan 里的 {comp['file']} 不存在 ⇒ 清册与磁盘脱钩"
                )
        assert len(all_composables) == len(set(all_composables)), (
            f"legacy composable 跨 entry 重复: {all_composables}"
        )
        assert len(all_composables) >= 8, (
            f"清册只列了 {len(all_composables)} 个 composable，少于 entry 数 ⇒ 漏登"
        )

    def test_deletion_plan_matches_slice(
        self, deletion_plan: dict, manifest_slice: dict
    ) -> None:
        """deletion plan 的裁决字段必须与 slice 一致，且理由不循环论证。"""
        by_id = {e["entry_id"]: e for e in manifest_slice["independent_entries"]}
        assert set(e["entry_id"] for e in deletion_plan["entries"]) == set(by_id), (
            "deletion plan 与 slice 的 entry 集合不等 ⇒ 有 entry 漏登或多登"
        )
        for entry in deletion_plan["entries"]:
            sliced = by_id[entry["entry_id"]]
            assert entry.get("capability_adjudication") == sliced.get("capability"), (
                f"{entry['entry_id']} 的 deletion plan 裁决与 slice 不一致"
            )
            assert entry.get("html_counterpart_verdict") == sliced.get(
                "html_counterpart_verdict"
            )
            assert entry.get("capability_target") == sliced.get("capability_target")
            assert entry.get("capability_verdict_stage") == sliced.get(
                "capability_verdict_stage"
            )
            assert len(entry.get("adjudication_reason", "")) > 40
            assert entry.get("host_component") == sliced["host_path"]

    def test_deletion_plan_reasons_are_not_circular(
        self, deletion_plan: dict, paradigm: dict
    ) -> None:
        """deletion plan 的裁决理由同样不得循环论证（两份产物同一把尺）。"""
        markers = paradigm["adjudication_criteria"]["anti_patterns"][0][
            "circular_reason_markers"
        ]
        for entry in deletion_plan["entries"]:
            text = entry.get("adjudication_reason", "")
            hits = [m for m in markers if m in text]
            assert not hits, (
                f"deletion plan 里 {entry['entry_id']} 的理由命中循环论证标记 {hits}"
            )

    def test_deletion_plan_declares_no_pilot_and_preserves_shared_base(
        self, deletion_plan: dict
    ) -> None:
        """F 循环没有 pilot；共享基座不得进删除清册，且 F 循环确实不消费它。"""
        pilot = deletion_plan["pilot_already_migrated"]
        assert pilot["entry_id"] is None and pilot["note"], (
            "F 循环无 pilot 必须显式写 null + 说明，不能省略字段"
        )
        preserved = deletion_plan["shared_base_preserved"]
        assert "useWorkpaperEntryDualMode.ts" in preserved["file"]
        assert preserved["f_cycle_does_not_consume_it"] is True
        assert SHARED_BASE.is_file(), "共享基座必须存在"
        to_delete = {
            comp["file"]
            for entry in deletion_plan["entries"]
            for comp in entry["legacy_composables_to_delete"]
        }
        assert preserved["file"] not in to_delete, "共享基座被列入删除清册"

    def test_f_cycle_composables_really_do_not_wrap_the_shared_base(
        self, deletion_plan: dict
    ) -> None:
        """`f_cycle_does_not_consume_it` 必须能在源码上复核（不是自述）。"""
        checked = 0
        for entry in deletion_plan["entries"]:
            for comp in entry["legacy_composables_to_delete"]:
                source = _strip_ts_comments((ROOT / comp["file"]).read_text(encoding="utf-8"))
                wraps = "useWorkpaperEntryDualMode" in source
                assert wraps == bool(comp.get("wraps_shared_base")), (
                    f"{comp['file']}: wraps_shared_base 声称 "
                    f"{comp.get('wraps_shared_base')}，实测 {wraps}"
                )
                assert not wraps, (
                    f"{comp['file']} 实际包了共享基座 ⇒ deletion plan 的 "
                    "`f_cycle_does_not_consume_it` 与 shared_base_preserved 结论要重写"
                )
                checked += 1
        assert checked >= 8, f"只核验了 {checked} 个 composable ⇒ 分母可疑"


# ════════════════════════════════════════════════════════════════════════════
# AC 1.4：裁决自带的 UI 义务（范式 step 11）
# ════════════════════════════════════════════════════════════════════════════
class TestAc14HonestModeVisibility:
    """
    **Validates: Requirements 14.1**

    AC 1.4：未注册 adapter 的入口**禁止**显示「可双向回写」，并**必须**显示可操作原因。

    🔴 只改 slice 的 capability 而界面照旧 = AP-4 capability_without_ui_change。
    判据必须落到**模板形态**（宿主真挂了组件 + 传了自己的 entry id + 落在模式工具栏区块内），
    不能只 grep 符号名 —— 「模型声明了而模板零引用」是 G7 两级表头 0/38 的同型结构性死代码。

    AC 1.5 为什么不在这里：它的触发条件是「入口被裁决为纯 OO 或纯 HTML」。8 条 entry 都不是
    single_*，AC 1.5 的 WHEN 不成立；收掉切换按钮反而会砍掉真实可用的 OO 独立编辑通道。
    见 slice 的 BP-10。
    """

    def test_notice_module_is_the_single_source(self) -> None:
        """复用 Task 46 收口新建的单一真源，不新建第二份文案模块。"""
        source = _strip_ts_comments(NOTICE_MODULE.read_text(encoding="utf-8"))
        assert "export function entrySyncNotice" in source
        assert "SYNC_ADAPTER_REGISTERED_ENTRY_IDS" in source
        assert "ENTRY_SYNC_NOTICE_SUMMARY" in source
        assert "ENTRY_SYNC_NOTICE_REASON" in source
        # 反向：不得出现第二份 F 循环专用文案模块
        siblings = sorted(p.name for p in SYNC_DIR.glob("*EntrySyncNotice*.ts"))
        assert siblings == ["workpaperEntrySyncNotice.ts"], (
            f"sync/ 下出现了多份通知文案模块 {siblings} ⇒ 单一真源被破坏"
        )

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
            found = mount_pattern.findall(template)
            assert len(found) == 1, (
                f"{host.name} 的 {NOTICE_COMPONENT_NAME} 挂载点命中 {len(found)} 次（应为 1）"
            )
            assert found[0] == entry["entry_id"], (
                f"{host.name} 传的 entry-id={found[0]!r}，应为 {entry['entry_id']!r}"
            )
            checked += 1
        assert checked == 8, f"只校验到 {checked} 个宿主，应为 8 —— 分母缩水"

    def test_notice_mount_sits_inside_the_declared_mode_toolbar(
        self, manifest_slice: dict
    ) -> None:
        """通知必须挂在**该宿主自己声明的**模式工具栏区块内。

        🔴 工具栏门控锚点逐 entry 从 slice 的 `ui_toolbar_gate` 读：F 循环有三种形态并存
        （`v-if="showHtmlToolbar"` 6 条 / `class="toolbar"` 监盘 / `class="f5-cost-of-sales-toolbar"`
        F5）。写死单一正则会让另两种的区块判据恒真（挂载点不在被搜区块里也不报错）。
        """
        gates: set[str] = set()
        for entry in manifest_slice["independent_entries"]:
            gate = entry.get("ui_toolbar_gate")
            assert isinstance(gate, str) and gate.strip(), (
                f"{entry['entry_id']} 缺 ui_toolbar_gate ⇒ 区块判据无锚点"
            )
            gates.add(gate)
            host = ROOT / entry["host_path"]
            source = _strip_ts_comments(host.read_text(encoding="utf-8"))
            template = _vue_template(source)
            block = _toolbar_block(template, gate)
            assert f"<{NOTICE_COMPONENT_NAME}" in block, (
                f"{host.name} 的通知没挂在 {gate!r} 界定的模式工具栏区块内"
            )
            assert "el-segmented" in block, (
                f"{host.name} 的 {gate!r} 区块里没有模式切换器 ⇒ 它不是模式工具栏，锚点选错了"
            )
        assert len(gates) >= 3, (
            f"F 循环实测三种工具栏门控形态并存，slice 只出现 {len(gates)} 种 ⇒ "
            "有宿主的门控被误抄成别人的"
        )

    def test_ui_gate_source_refs_and_dom_guard_ref_are_real(
        self, manifest_slice: dict
    ) -> None:
        """范式 step 11 要求的 ui_gate_source_refs / dom_guard_ref 必须真存在。"""
        for entry in manifest_slice["independent_entries"]:
            refs = entry.get("ui_gate_source_refs")
            assert isinstance(refs, list) and len(refs) >= 3, (
                f"{entry['entry_id']} 的 ui_gate_source_refs 太少（宿主 + 组件 + 文案模块）"
            )
            for ref in refs:
                assert (ROOT / ref.split("#")[0]).exists(), (
                    f"{entry['entry_id']} 的 ui_gate_source_refs 指向不存在的路径 {ref!r}"
                )
            guard = entry.get("dom_guard_ref")
            assert isinstance(guard, str) and guard, f"{entry['entry_id']} 缺 dom_guard_ref"
            path, _, node = guard.partition("::")
            assert (ROOT / path).is_file(), f"dom_guard_ref 指向不存在的文件: {path}"
            body = (ROOT / path).read_text(encoding="utf-8")
            cls = node.split("::")[0]
            assert f"class {cls}" in body, (
                f"dom_guard_ref 指向的类 {cls} 不在 {path} 里 ⇒ 声明了但没人实现"
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
        """AC 1.4 前半句：宿主不得出现「可双向回写」「同步成功」之类的成功态宣称。

        注：F2 监盘宿主有「仅预览·无回写」与「同步中…」两个标签 —— 前者是诚实的能力否认、
        后者是进行态，都不在禁列里。禁的是**成功态宣称**。
        """
        forbidden = ("可双向回写", "双向同步", "同步成功", "已同步")
        for entry in manifest_slice["independent_entries"]:
            host = ROOT / entry["host_path"]
            source = _strip_ts_comments(host.read_text(encoding="utf-8"))
            for word in forbidden:
                assert word not in source, (
                    f"{host.name} 出现 {word!r} —— 未注册 adapter 的入口不得宣称双向/同步成功"
                )


# ════════════════════════════════════════════════════════════════════════════
# F2 Word lane 的边界与「已接统一 commit」对裁决的实际影响
# ════════════════════════════════════════════════════════════════════════════
class TestWordLaneBoundaryAndUnifiedCommit:
    """
    **Validates: Requirements 12.1**

    任务正文要求核实 `f2_stocktake_plan_sync` / `f2_stocktake_summary_sync` 已接统一 commit
    这件事对裁决的实际影响。这里把「实际影响」落成可复核判据，而不是一句备注。
    """

    def test_both_writers_go_through_the_unified_commit(
        self, manifest_slice: dict
    ) -> None:
        """两个 writer 必须真的走 build_content_mutation_service_writer + commit_bytes。

        🔴 authority model 这一条的**载体**变了（Task 65），语义没变。原判据是
        `"AuthorityModel.opaque_single_onlyoffice" in code` —— 锁的是「本 writer 用的
        authority model 是 opaque_single_onlyoffice，不得靠默认值漂移」。现在
        `commit_bytes` 已无 `authority_model` 参数，那句子串只会在注释里命中，所以判据
        迁到新载体上并**同时加强**为四向锁死：

          调用点 `lane_id=` 字面量 → lane 登记表（该 lane 的 writer 必须正是本模块）
          → `authority_model_for_lane()` 仍是 `opaque_single_onlyoffice`
          → slice 声明的 `authority_model_used` 与它等值

        最后一环是新增的：`authority_model_used` 从前只被「等于这个常量」自证一次
        （`test_word_lane_block_records_the_authority_model_premise_defect`），与生产
        毫无联系；接上登记表之后，生产改了而 slice 没跟就会打红。
        """
        OG = _lane_registry()
        from app.services.workpaper_sync.models import AuthorityModel  # noqa: PLC0415

        declared = {
            str(writer["module"]): str(writer["authority_model_used"])
            for entry in manifest_slice["independent_entries"]
            for writer in (entry.get("partially_wired_word_lane") or {}).get(
                "wired_writers", []
            )
        }
        assert len(declared) == 2, f"slice 的 wired_writers 声明实得 {sorted(declared)}"

        for path in (PLAN_SYNC, SUMMARY_SYNC):
            code = _py_code_only(path.read_text(encoding="utf-8"))
            assert "build_content_mutation_service_writer(db)" in code, (
                f"{path.name} 没走统一 commit ⇒ slice 的 partially_wired_word_lane 结论失效"
            )
            assert "writer.commit_bytes(" in code, f"{path.name} 没调用 commit_bytes"
            assert "authority_model=" not in code, (
                f"{path.name} 的调用点又出现 `authority_model=` —— 那个可漏可错的身份参数"
                "已被删除，重新长出来就意味着同一个 entry 有两个 authority model 来源"
            )
            lane_id = _commit_bytes_lane_id(path)
            lane = OG.lane_for(lane_id)  # 未登记的 lane_id 直接抛
            module = "app." + (
                path.relative_to(BACKEND / "app").with_suffix("").as_posix().replace("/", ".")
            )
            assert (lane.writer_module, lane.writer_qualname) == (module, "_save_fields"), (
                f"{path.name} 传的 lane_id={lane_id!r} 登记在 {lane.writer_ref} 名下 —— "
                "两个 F2 writer 借用彼此的 lane 会让 authority model、entry_id 口径与"
                "evidence 分桶一起失真"
            )
            assert (
                OG.authority_model_for_lane(lane_id)
                is AuthorityModel.opaque_single_onlyoffice
            ), (
                f"{path.name} 的 authority_model 实为 "
                f"{OG.authority_model_for_lane(lane_id).value}，不是 opaque_single_onlyoffice"
            )
            slice_key = path.relative_to(ROOT).as_posix()
            assert declared.get(slice_key) == (
                f"AuthorityModel.{OG.authority_model_for_lane(lane_id).value}"
            ), (
                f"slice 声明 {slice_key} 的 authority_model_used="
                f"{declared.get(slice_key)!r}，与登记表现算的 "
                f"AuthorityModel.{OG.authority_model_for_lane(lane_id).value} 不等值"
            )
            # 🔴 必须在剥掉 docstring 之后查：两个 writer 的 docstring 逐字引用了改造前的
            #    `await db.commit()` 来解释「以前是这样」。裸匹配会把说明当代码。
            assert "db.commit()" not in code, (
                f"{path.name} 的可执行代码里出现裸 db.commit() ⇒ 又绕出了版本域"
            )
            # 反向自检：docstring 里那段引用确实存在，证明上面这条剥对了而不是剥过头
            assert "db.commit()" in path.read_text(encoding="utf-8"), (
                f"{path.name} 的 docstring 已不再引用旧写法 ⇒ _py_code_only 的反向自检失去分母，"
                "上面那条判据可能只是因为整份源码都被剥空了才通过"
            )

    def test_commit_entry_id_is_composite_with_the_sheet_code(self) -> None:
        """复合传输键实证：commit 的 entry_id 必须带 sheet code，两个 writer 的 sheet code 不同。

        🔴 这是本任务「核验复合传输键」的核心判据之一：F2-22 与 F2-23 是同一底稿的两份
        不同文档，共用一个 entry_id 会互相顶掉 representation generation。
        """
        codes: set[str] = set()
        for path in (PLAN_SYNC, SUMMARY_SYNC):
            source = path.read_text(encoding="utf-8")
            assert 'opaque_entry_id(wp_code=f"{wp_code or wp_id}#{_SHEET_CODE}", wp_id=wp_id)' in source, (
                f"{path.name} 的 commit entry_id 不是 `{{wp_code}}#{{sheet_code}}` 复合形态 ⇒ "
                "两张表会共用一个 representation entry"
            )
            found = re.search(r'_SHEET_CODE\s*=\s*"([^"]+)"', source)
            assert found, f"{path.name} 里找不到 _SHEET_CODE 常量"
            codes.add(found.group(1))
        assert codes == {"F2-22", "F2-23"}, (
            f"两个 writer 的 sheet code 实测为 {sorted(codes)}，应为 F2-22 / F2-23"
        )

    def test_fields_item_ids_are_distinct_backend_constants(self) -> None:
        """F2-22 / F2-23 的 -fields 键是后端常量且互不相同。"""
        item_ids: set[str] = set()
        for svc in ("f2_stocktake_plan_sync.py", "f2_stocktake_summary_sync.py"):
            path = BACKEND / "app" / "services" / svc
            assert path.is_file(), f"{path} 不存在"
            source = path.read_text(encoding="utf-8")
            found = re.search(r'FIELDS_ITEM_ID\s*=\s*"([^"]+)"', source)
            assert found, f"{svc} 里找不到 FIELDS_ITEM_ID"
            item_ids.add(found.group(1))
        assert item_ids == {"F2-22-fields", "F2-23-fields"}, (
            f"实测 {sorted(item_ids)}，与 slice 登记的复合键形态不符"
        )

    def test_word_lane_block_records_the_authority_model_premise_defect(
        self, manifest_slice: dict
    ) -> None:
        """BP-9：两个 writer 的 lane 选择理由建立在 overlay 默认值上，必须已登记。"""
        stocktake = next(
            e
            for e in manifest_slice["independent_entries"]
            if e["entry_id"] == "xlsx/gt-f2-stocktake-bundle"
        )
        lane = stocktake["partially_wired_word_lane"]
        assert len(lane["wired_writers"]) == 2
        for writer in lane["wired_writers"]:
            assert (ROOT / writer["module"]).is_file()
            assert writer["document_type"] == "docx", (
                "Word lane 的 document_type 必须是 docx —— 若变成 xlsx，它就不再是"
                "「与本 entry 的 xlsx 通道无共用」了，裁决影响要重算"
            )
            assert writer["authority_model_used"] == "AuthorityModel.opaque_single_onlyoffice"
        for key in (
            "impact_on_adjudication_1_does_not_make_it_bidirectional",
            "impact_on_adjudication_2_does_not_make_it_single_onlyoffice",
            "impact_on_adjudication_3_authority_model_is_not_free_to_copy",
            "impact_on_adjudication_4_composite_key_is_a_precedent",
        ):
            assert len(lane.get(key, "")) > 60, f"partially_wired_word_lane 缺 {key}"
        assert "BP-9" in stocktake["capability_target_blocked_by"]
        bp9 = next(
            bp for bp in manifest_slice["blocking_preconditions"] if bp["id"] == "BP-9"
        )
        assert bp9["owner_task"].startswith("Task 60")

        # 前提缺陷本体必须在源码里可复核：docstring 真的把 lane 选择理由挂在
        # `capability=single_onlyoffice` 上。
        # 🔴 必须先折行再匹配：summary_sync 的 docstring 把这个片段折成两行
        #    （`capability=` 在行尾、`single_onlyoffice` 在下一行行首），裸子串匹配必假红。
        for writer in lane["wired_writers"]:
            flat = _collapse_ws((ROOT / writer["module"]).read_text(encoding="utf-8"))
            assert "capability= single_onlyoffice" in flat or "capability=single_onlyoffice" in flat, (
                f"{writer['module']} 的 docstring 已不再引用 capability=single_onlyoffice ⇒ "
                "BP-9 描述的前提缺陷可能已被修好，请更新 slice"
            )

    def test_docx_templates_are_reachable_only_via_the_explicit_map(self) -> None:
        """两个 docx 不在 _index.json 里，但经 _EXPLICIT_TEMPLATE_RELPATHS 可达。

        这条锁的是 slice 里「与 F2存货.xlsx 的不可达形态不同」这句话 —— 不验它就只是散文。
        """
        sys.path.insert(0, str(BACKEND))
        from app.services.wp_template_finder import (  # noqa: PLC0415
            _EXPLICIT_TEMPLATE_RELPATHS,
            find_template_file_any,
        )

        indexed = _indexed_relpaths()
        for code, rel in (("F2-22", "F/F2-22 存货监盘计划.docx"), ("F2-23", "F/F2-23 存货监盘小结.docx")):
            assert _EXPLICIT_TEMPLATE_RELPATHS.get(code) == rel, (
                f"_EXPLICIT_TEMPLATE_RELPATHS[{code!r}] 实为 "
                f"{_EXPLICIT_TEMPLATE_RELPATHS.get(code)!r}"
            )
            assert rel not in indexed, f"{rel} 已进 _index.json ⇒ slice 的说明要更新"
            got = find_template_file_any(code)
            assert got is not None and got.name == rel.split("/")[-1], (
                f"find_template_file_any({code!r}) 返回 {got.name if got else None!r}，"
                f"应为 {rel.split('/')[-1]!r}"
            )


# ════════════════════════════════════════════════════════════════════════════
# 范式一致性与源码结构
# ════════════════════════════════════════════════════════════════════════════
class TestParadigmCompliance:
    """验证 slice / deletion plan 与 Task 45 冻结的范式一致（范式 JSON 只读）。"""

    def test_paradigm_exists(self, paradigm: dict) -> None:
        assert paradigm["schema_version"] == "migration-paradigm:v1"
        assert paradigm["frozen_by"] == "Task 45"

    def test_task48_is_in_both_paradigm_scopes(self, paradigm: dict) -> None:
        """Task 48 同时受 definition_producer_paradigm 与 slice_schema 约束。"""
        producer = paradigm["definition_producer_paradigm"]
        assert 48 in producer["applies_to_tasks"]
        assert 48 in paradigm["slice_schema"]["applies_to_tasks"]
        step3 = next(s for s in producer["steps"] if s["step"] == 3)
        assert step3["name"] == "resolve_html_counterpart"
        assert set(step3["output"]["allowed_values"]) == set(HTML_COUNTERPART_VERDICTS)
        step11 = next(s for s in producer["steps"] if s["step"] == 11)
        assert step11["name"] == "enforce_honest_mode_visibility"
        assert set(step11["output"]["must_contain"]) == {"ui_gate_source_refs", "dom_guard_ref"}

    def test_capability_enum_comes_from_the_paradigm(self, paradigm: dict) -> None:
        """本文件的 CAPABILITY_ENUM 必须与范式登记的枚举一致（不另立一份真源）。"""
        assert set(paradigm["adjudication_criteria"]["capability_enum"]) == set(CAPABILITY_ENUM)

    def test_single_onlyoffice_illegal_criteria_are_registered(self, paradigm: dict) -> None:
        """范式明文把「无 adapter / 无 contract / 无 bundle」列为非法判据。"""
        verdict = paradigm["adjudication_criteria"]["verdicts"]["single_onlyoffice"]
        assert verdict["forbidden_verdict_value"] == "exists"
        assert verdict["illegal_criteria"], "illegal_criteria 为空 ⇒ AP-1 判据无分母"

    def test_slice_satisfies_the_schema_required_fields(
        self, manifest_slice: dict, paradigm: dict
    ) -> None:
        """逐项校验 slice_schema.required_* **加** effective_from_task_48 的追加必填。"""
        schema = paradigm["slice_schema"]
        assert schema["target_schema_version"] == manifest_slice["schema_version"]
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
        assert set(effective["required_entry"]) == {
            "html_counterpart_verdict",
            "html_counterpart_source_refs",
        }
        required_entry = list(schema["required_entry"]) + list(effective["required_entry"])
        for entry in manifest_slice["independent_entries"]:
            for key in required_entry:
                assert key in entry, f"{entry['entry_id']} 缺 entry 字段 {key}"
            for key in schema["presence_required_value_may_be_null"]:
                assert key in entry, f"{entry['entry_id']} 缺（值可为 null 的）字段 {key}"
            for key in schema["required_entry_adjudication"]:
                assert key in entry["adjudication"], (
                    f"{entry['entry_id']} 的 adjudication 缺 {key}"
                )
            for key in schema["required_entry_evidence"]:
                assert key in entry["evidence"], f"{entry['entry_id']} 的 evidence 缺 {key}"

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

    def test_dynamic_row_identity_section_satisfies_the_conditional_schema(
        self, manifest_slice: dict, paradigm: dict
    ) -> None:
        """conditional_sections 的 dynamic_row_identity 一旦出现就必须字段齐备。"""
        spec = next(
            cs
            for cs in paradigm["slice_schema"]["conditional_sections"]
            if cs["section"] == "dynamic_row_identity"
        )
        body = manifest_slice["dynamic_row_identity"]
        for key in spec["required_fields"]:
            assert key in body, f"dynamic_row_identity 缺 {key}"
        entry_ids = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        assert len(body["tables"]) == len(entry_ids), (
            f"dynamic_row_identity 登记 {len(body['tables'])} 张表，entry 有 {len(entry_ids)} 条 "
            "⇒ 有 entry 的动态行表没登记"
        )
        for table in body["tables"]:
            for key in spec["required_table_fields"]:
                assert key in table, f"{table.get('table_key')} 缺 {key}"
            assert table["entry_id"] in entry_ids
            for key in spec["required_row_identity_fields"]:
                assert key in table["row_identity"], (
                    f"{table['table_key']}.row_identity 缺 {key}"
                )
            ref = table["row_identity"]["source_ref"]
            assert (ROOT / ref.split("#")[0]).is_file(), (
                f"{table['table_key']} 的 source_ref 指向不存在的文件 {ref!r}"
            )
            assert table["row_identity"]["kind"] not in body["forbidden_identity_kinds"], (
                f"{table['table_key']} 的 row_identity.kind 落在 forbidden_identity_kinds 里"
            )

    def test_the_slice_passes_the_paradigm_nominated_validator(
        self, manifest_slice: dict
    ) -> None:
        """被范式点名的校验器对本 slice **一条违规都不许报**。

        🔴 判据换过一次，换的理由要留痕：本条原名
        `test_the_only_schema_violations_are_the_registered_sr3_gap`，断言「违规存在且**全部**
        是 SR-3」—— 那是 G1（同一条 SR-3 有两个互相矛盾的判官）还没收口时的诚实形态，它自己的
        docstring 写明「若范式 owner 收口了 SR-3 ⇒ 违规变空 ⇒ 打红，提醒回来删登记」。范式
        owner 已把 SR-3 改成蕴含式（`capability` 在 `capability_enum` 内 **或** 为 null 且
        `required_pending_verdict_fields` 三字段齐备），待裁决态成为合法一等公民 ⇒ 本 slice 的
        8 条 `capability: null` 不再是违规，旧判据按其设计当场打红。按新事实重写为「通过」。

        两个方向仍然都咬：
        * 本 slice 破了任何 schema 规则（含把待裁决态写得不齐备：缺 `capability_verdict_stage`
          / `capability_target` 不在枚举内 / `capability_target_blocked_by` 空数组）⇒ 打红；
        * 校验器被短路成恒返回空列表 ⇒ 由下面对合成残缺 slice 的反向自检打红。

        为什么当初不能靠「给 capability 填一个枚举值」消掉那条红：违反 AC 12.8（有 HTML 对端
        不得 `single_onlyoffice`）或 AC 12.1 + SR-6（五个身份字段全 null 不得 `bidirectional`）。
        收口走的是范式侧，不是往 slice 里填假裁决。
        """
        contract = pathlib.Path(__file__).with_name("test_migration_paradigm_contract.py")
        assert contract.is_file(), f"{contract} 不存在 —— 被点名的校验器缺失"
        import importlib.util  # noqa: PLC0415

        spec = importlib.util.spec_from_file_location("_t48_paradigm_contract_host", contract)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        problems = module.validate_slice_against_schema(manifest_slice)
        assert problems == [], (
            f"本 slice 通不过范式自己的 slice_schema（{len(problems)} 条）：\n"
            + "\n".join(f"  !! {p}" for p in problems)
        )
        # 反向自检：校验器不是恒返回空列表。把第一条 entry 的待裁决声明抽掉一项 ——
        # SR-3 右支必须当场报违规并点名该字段，否则「通过」这个结论毫无信息量。
        crippled = copy.deepcopy(manifest_slice)
        crippled["independent_entries"][0].pop("capability_verdict_stage")
        crippled_problems = module.validate_slice_against_schema(crippled)
        assert any("capability_verdict_stage" in p for p in crippled_problems), (
            "抽掉 capability_verdict_stage 后校验器不点名它 ⇒ 待裁决态被放宽成「null 一律通过」，"
            f"本条的「通过」是假绿。实际违规：{crippled_problems}"
        )
        # 收口留痕：slice 自述里的 G1 登记必须已改写成「已解除」，不许留着过期的「已知红」。
        registered = manifest_slice["paradigm_schema_conflict"]["known_red_it_causes"]
        assert registered["status"] == "resolved", (
            "G1 已收口但 slice 的 known_red_it_causes.status 不是 resolved ⇒ 自述过期"
        )
        assert "SR-3" in registered["resolved_by"], (
            "known_red_it_causes.resolved_by 必须写明是哪条规则接纳了待裁决态"
        )
        assert not registered["failing_test"], (
            "G1 已解除，known_red_it_causes.failing_test 必须清空 —— 留着旧 nodeid 会让下一个人"
            "以为那条测试还在红"
        )

    def test_paradigm_conflict_is_registered(self, manifest_slice: dict) -> None:
        """范式内部冲突必须登记，不许悄悄绕过。"""
        conflict = manifest_slice["paradigm_schema_conflict"]
        for key in (
            "what",
            "how_resolved_here",
            "residual_inconsistency",
            "sibling_slice_conflicts",
        ):
            assert len(conflict.get(key, "")) > 40, f"paradigm_schema_conflict 缺 {key}"

    def test_deletion_plan_has_paradigm_ref(self, deletion_plan: dict) -> None:
        assert deletion_plan["paradigm_ref"] == (
            "backend/data/workpaper_sync_migration_paradigm.json"
        )
        assert deletion_plan["adjudication_source_of_truth"].startswith(
            "backend/data/workpaper_sync_f_cycle_manifest_slice.json"
        )
        assert deletion_plan["deletion_execution_owner"]

    def test_properties_and_requirements_are_declared(
        self, manifest_slice: dict, deletion_plan: dict
    ) -> None:
        """slice 与 deletion plan 声明的 Property / Requirement 必须与任务正文一致。"""
        expected_props = {21, 28, 69, 70}
        assert set(manifest_slice["properties_verified"]) == expected_props
        assert set(deletion_plan["properties_verified"]) == expected_props
        expected_reqs = {"6.2", "6.10", "12.1", "12.4", "12.10", "12.11", "12.12", "14.1"}
        assert expected_reqs <= set(manifest_slice["requirements_covered"]), (
            f"slice 的 requirements_covered 缺 "
            f"{sorted(expected_reqs - set(manifest_slice['requirements_covered']))}"
        )


class TestSourceCodeStructure:
    """验证源码结构与 slice/deletion plan 一致（现状锁，删除归 Task 66/72）。"""

    def test_hosts_exist_and_still_import_their_legacy_composable(
        self, manifest_slice: dict
    ) -> None:
        """宿主存在且仍引用各自的 legacy dual-mode composable（BP-10 登记的未删状态）。"""
        hosts = {
            (ROOT / e["host_path"]).name for e in manifest_slice["independent_entries"]
        }
        assert hosts == set(F_CYCLE_HOST_DUAL_MODE), (
            f"slice 的宿主集合与预期不符: {sorted(hosts)}"
        )
        for entry in manifest_slice["independent_entries"]:
            host = ROOT / entry["host_path"]
            assert host.is_file()
            source = _strip_ts_comments(host.read_text(encoding="utf-8"))
            expected = F_CYCLE_HOST_DUAL_MODE[host.name]
            assert re.search(
                r"import\s*\{?\s*" + expected + r"\s*\}?\s*from", source
            ), f"{host.name} 应仍 import {expected}"

    def test_deletion_plan_covers_every_host_composable(self, deletion_plan: dict) -> None:
        """每个宿主实际 import 的 composable 都必须在删除清册里（漏一个就删不干净）。"""
        listed = {
            pathlib.Path(comp["file"]).stem
            for entry in deletion_plan["entries"]
            for comp in entry["legacy_composables_to_delete"]
        }
        missing = set(F_CYCLE_HOST_DUAL_MODE.values()) - listed
        assert not missing, f"deletion plan 漏了宿主在用的 composable: {sorted(missing)}"

    def test_f_cycle_templates_exist(self) -> None:
        f_dir = TEMPLATE_DIR / "F"
        assert f_dir.is_dir()
        xlsx_files = [p for p in f_dir.glob("F*.xlsx") if not p.name.startswith("~$")]
        assert len(xlsx_files) >= 8, f"至少 8 个 F 循环 xlsx 模板，实际 {len(xlsx_files)}"

    def test_bridge_adapter_supports_entry_id(self) -> None:
        adapter = SYNC_DIR / "usePilotBridgeAdapter.ts"
        assert adapter.is_file(), "usePilotBridgeAdapter.ts 必须存在（Task 45 产物）"
        assert "entryId" in adapter.read_text(encoding="utf-8")
