# -*- coding: utf-8 -*-
"""A 域 19 条未接通 entry 的阻塞登记守卫。

spec: a-cycle-sync-foundation-and-first-canary（接通阶段复盘）

═══ 为什么需要这份守卫 ═══

A 域 20 条 entry 里只有 canary `xlsx/gt-a51-cashflow-audit` 走完了 definition 发布链
（capability=bidirectional + 契约落盘 + 四条 definition 真落库 `approved`）。但它**仍未
接通**：交付台账里它的 `adapter_registered` 是 **False**，且它自己卡在第 4 类阻塞（纯静态
entry 的 instrumentation 注入缺口，见 §6）。其余 **19 条另有硬阻塞**，四类阻塞的性质
完全不同。若不把阻塞原因写成可执行判据，未来会出现两种事故：

* 有人以为「只是还没做」而去硬造 provider —— 那会产出**假双向**（投影恒空或写错位置）；
* 阻塞解除了（平台交付 word adapter / 业务补册 / 前端补结构化对端）却没人知道可以接了。

⇒ 每条阻塞都写成**成对断言**：「阻塞当前成立」+「解除信号」。解除信号命中即打红，
提醒同步更新本文件与对应 entry 的 capability。

═══ 四类阻塞（现算实证）═══

| 类别 | 条数 | 阻塞根因 | 解除信号 |
|---|---|---|---|
| docx 权威册 | **16** | 平台明禁 `adapters/word.py`（`PENDING_ENGINE_ADAPTERS.forbidden_paths`，门 = Task 59/60/61 的真实 OO 9.4 pilot） | 该路径出现 |
| 册未钉住 | **2** | a177 是 `runtime_sheet_name_expression`（slice `why_null` 明禁硬指册，`workbook` 仍 `null`）· a38 🔴 **归因已更正**：册**一直在磁盘上**（`A/A3-7内部往来核对表、A3-8商誉减值测试.xlsx`），原 slice 写 `workbook: null` 是假事实；解析层缺陷已由 spec `workpaper-sync-pure-static-lane-and-combined-workbook-resolution` 修复（两路入口都解析到合册），剩余阻塞是**宿主层第二步**（宿主传中文字面 sheet 名而非 wp_code），登记为后继 | a177：resolution_kind 变 · a38：宿主改传 wp_code |
| 投影对端缺失 | **1** | a3-console 的 HTML 侧是程序表（`field_overrides`/`procedure_table:A3`），Excel 侧是 A3-3 册 33 列判断表，**两侧字段零交集** | Excel 列名在前端命中 |
| 纯静态注入缺口 | **1**（canary 自己）| **已解除**（spec workpaper-sync-pure-static-lane-and-combined-workbook-resolution）。原阻塞是平台instrumentation 管线整条预设「每个 entry 至少有一张动态行表」—— 平台代码站点**现算 6 处**（注入器拒空 specs · spec 强校验行表几何 · payload 构建器拒空 specs · substrate 只认两个行 spec 入口 · 身份 binding 只有 row_identity 路径 · 观测清册在全静态锚点下恒 `None`）。处置恰为「3 处旁路 + 3 处加分派臂」，**放宽既有校验 0 处** | 本段现改为**正向**判据：静态通道缺任一段即打红 |

🔴 前三类的分母是**那 19 条未接通 entry**（16+2+1 互斥穷尽，见 §1）；第 4 类与它们**正交**
—— 它的成员是 **canary 自己**，不进那 19 条的分类，不要把两个分母相加。

🔴 **a3-console 的 `single_onlyoffice` 是正确 capability，不是欠账** —— 它的两个模式
编辑的是**两份不同数据**（程序表执行状态 vs 结构化主体判断表），没有可投影的公共数据集。
把它升成 bidirectional 会要求一个不存在的投影。
"""
from __future__ import annotations

import dataclasses
import inspect
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterable

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
_ROOT = _BACKEND.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_TEMPLATE_DIR = _BACKEND / "wp_templates" / "A"
_SLICE_PATH = _BACKEND / "data" / "workpaper_sync_abcs_cycle_manifest_slice.json"
_FRONTEND = _ROOT / "audit-platform" / "frontend" / "src"

sys.path.insert(0, str(_BACKEND / "scripts" / "analyze"))
from a_cycle_scanner import a_domain_entries  # noqa: E402

CANARY_ENTRY_ID = "xlsx/gt-a51-cashflow-audit"


@pytest.fixture(scope="module")
def manifest_slice() -> dict:
    return json.loads(_SLICE_PATH.read_bytes())


@pytest.fixture(scope="module")
def a_entries(manifest_slice: dict) -> list[dict]:
    return a_domain_entries(manifest_slice["independent_entries"])


@pytest.fixture(scope="module")
def unconnected(a_entries: list[dict]) -> list[dict]:
    """19 条未接通 entry（A 域 20 条减 canary）。"""
    return [e for e in a_entries if e["entry_id"] != CANARY_ENTRY_ID]


def _short(entry_id: str) -> str:
    return entry_id.split("/")[-1].replace("gt-", "")


# ═══════════════════════════════════════════════════════════════════════════
# §1 分类总账
# ═══════════════════════════════════════════════════════════════════════════


class TestBlockerLedger:
    """19 条 = docx 16 + 无册 2 + 投影缺失 1，三类互斥且穷尽。"""

    def test_unconnected_count_is_19(self, unconnected: list[dict]) -> None:
        assert len(unconnected) == 19, \
            f"A 域应有 19 条未接通（20 减 canary），实际 {len(unconnected)}"

    def test_three_categories_are_exhaustive(self, unconnected: list[dict]) -> None:
        """三类阻塞互斥且穷尽覆盖 19 条。

        🔴 **判别器已换**：原先第二类用 `workbook is None` 判定，而 a38 的
        `template_ref.workbook` 原值 `null` 是**假事实**（册一直在磁盘上）。spec
        `workpaper-sync-pure-static-lane-and-combined-workbook-resolution` 把它改成真实
        路径后，形状判别会把 a38 错分到「投影缺失」那一类 —— 而 a38 的阻塞与「投影对端
        缺失」毫无关系。

        改用**权威阻塞清单** `capability_target_blocked_by` 判别（现算：
        a177 带 BP-8 / a38 带 BP-6 / a3-console 带 BP-10）—— 这是语义判别，
        不会随 `template_ref` 的形状修正而漂。三类的**分母仍是 16 + 2 + 1 = 19**。
        """
        docx, book_not_pinned, projection_gap = [], [], []
        for e in unconnected:
            tref = e.get("template_ref", {})
            blocked = set(e.get("capability_target_blocked_by") or ())
            if tref.get("workbook_format") == "docx":
                docx.append(e["entry_id"])
            elif {"BP-6", "BP-8"} & blocked:
                book_not_pinned.append(e["entry_id"])
            else:
                projection_gap.append(e["entry_id"])

        assert len(docx) == 16, f"docx 应 16 条，实际 {len(docx)}"
        assert len(book_not_pinned) == 2, (
            f"册未钉住应 2 条（a177 BP-8 + a38 BP-6），实际 {len(book_not_pinned)}: "
            f"{book_not_pinned}"
        )
        assert len(projection_gap) == 1, f"投影缺失应 1 条，实际 {len(projection_gap)}"
        assert len(docx) + len(book_not_pinned) + len(projection_gap) == 19
        # 互斥性：三类两两无交集
        assert len(set(docx) | set(book_not_pinned) | set(projection_gap)) == 19

    def test_only_canary_is_bidirectional(self, a_entries: list[dict]) -> None:
        """A 域仅 canary 一条 capability=bidirectional（读真实 manifest）。"""
        from app.services.workpaper_sync.entry_profile import (
            load_entry_manifest,
            manifest_entries_by_id,
        )
        load_entry_manifest.cache_clear()
        by_id = manifest_entries_by_id(load_entry_manifest())
        bidi = [
            e["entry_id"] for e in a_entries
            if by_id.get(e["entry_id"], {}).get("capability") == "bidirectional"
        ]
        assert bidi == [CANARY_ENTRY_ID], \
            f"A 域应仅 canary 为 bidirectional，实际 {bidi}"


# ═══════════════════════════════════════════════════════════════════════════
# §2 docx 16 条：平台禁 word adapter
# ═══════════════════════════════════════════════════════════════════════════


class TestDocxBlockedByPlatformGate:
    """16 条 docx entry 被平台 `PENDING_ENGINE_ADAPTERS` 门阻塞。"""

    _EXPECTED_DOCX = {
        "a101-governance-communication",
        "a111-subsequent-events-inquiry",
        "a112-dual-checklist",
        "a115-disclosure-checklist",
        "a121-legal-confirmation",
        "a171-audit-summary",
        "a1721-kam",
        "a173-consultation-record",
        "a1731-consultation-execution",
        "a174-disagreement-record",
        "a176-closing-meeting",
        "a181-regulatory-submission",
        "a182-regulatory-communication",
        "a271-it-audit-memo",
        "a81-other-info-representation",
        "a91-deficiency-letter",
    }

    def test_docx_member_set_is_frozen(self, unconnected: list[dict]) -> None:
        """16 条 docx 成员集逐条吻合。"""
        actual = {
            _short(e["entry_id"]) for e in unconnected
            if e.get("template_ref", {}).get("workbook_format") == "docx"
        }
        assert actual == self._EXPECTED_DOCX, (
            f"docx 成员集漂移\n  多出: {actual - self._EXPECTED_DOCX}"
            f"\n  缺少: {self._EXPECTED_DOCX - actual}"
        )

    def test_platform_declares_docx_adapter_pending(self) -> None:
        """平台 `PENDING_ENGINE_ADAPTERS` 里 docx 仍是未交付状态。"""
        from app.services.workpaper_sync.adapters.registry import (
            PENDING_ENGINE_ADAPTERS,
        )
        docx_rows = [
            r for r in PENDING_ENGINE_ADAPTERS
            if str(r.get("document_type")) == "docx"
        ]
        assert len(docx_rows) == 1, \
            f"PENDING_ENGINE_ADAPTERS 应恰有 1 条 docx，实际 {len(docx_rows)}"
        row = docx_rows[0]
        assert row.get("blocking_task"), "docx 行应声明 blocking_task"
        assert row.get("forbidden_paths"), "docx 行应声明 forbidden_paths"

    def test_forbidden_word_adapter_paths_absent(self) -> None:
        """🔴 解除信号：`adapters/word.py` 一旦出现即打红。

        该路径出现意味着平台交付了 Word engine adapter ⇒ 16 条 docx 可以开始接通，
        本文件的 docx 段与那 16 条的 capability 须同步更新。
        """
        from app.services.workpaper_sync.adapters.registry import (
            PENDING_ENGINE_ADAPTERS,
        )
        docx_row = next(
            r for r in PENDING_ENGINE_ADAPTERS
            if str(r.get("document_type")) == "docx"
        )
        for rel in docx_row["forbidden_paths"]:
            path = _BACKEND / rel
            assert not path.exists(), (
                f"🔴 阻塞已解除：{rel} 已落地 ⇒ 16 条 docx entry 可接通，"
                f"请同步更新本守卫与那 16 条的 capability"
            )

    def test_docx_entries_have_no_contract(self, unconnected: list[dict]) -> None:
        """16 条 docx 均无 per-entry 契约（未接通的直接证据）。"""
        from app.services.workpaper_sync.adapters.registry import (
            DELIVERED_PER_ENTRY_CONTRACTS,
        )
        delivered = {str(r.get("entry_id")) for r in DELIVERED_PER_ENTRY_CONTRACTS}
        for e in unconnected:
            if e.get("template_ref", {}).get("workbook_format") != "docx":
                continue
            assert e["entry_id"] not in delivered, (
                f"{_short(e['entry_id'])}: docx entry 竟有契约 —— "
                f"平台 word adapter 未交付，契约无处消费"
            )


# ═══════════════════════════════════════════════════════════════════════════
# §3 无权威册 2 条
# ═══════════════════════════════════════════════════════════════════════════


class TestNoAuthoritativeWorkbook:
    """a177 / a38 无权威册，两者根因不同。"""

    def test_exactly_two_without_a_pinned_workbook(self, unconnected: list[dict]) -> None:
        """本类分母仍是 **2** 条，但两者的根因**已不同源**。

        🔴 **a38 已从「无权威册」移出**：slice 的 `template_ref.workbook` 原值 `null` 是
        假事实（册一直在磁盘上），本 spec 已改为真实相对路径 ⇒ `workbook is None` 的集合
        现在只剩 a177。a38 仍未接通，但剩余阻塞是**宿主层第二步**（宿主传中文字面 sheet 名
        而非 wp_code），不是「没有册」。19 条未接通 entry 的总数不变。

        🔴 这条方法名与断言的改动**超出** R14.10 给 Lane B 划的编辑范围
        （原文只列 `test_a38_workbook_absent_on_disk` 与顶部阻塞表那一行）。
        但它是 R14.5「把 `workbook` 由 null 改为真实路径」的**必然连带** —— 不改这里，
        本方法会因假事实被纠正而变红。该边界外扩已登记在
        `.kiro/specs/workpaper-sync-pure-static-lane-and-combined-workbook-resolution/errata.md`。
        """
        no_wb = {
            _short(e["entry_id"]) for e in unconnected
            if e.get("template_ref", {}).get("workbook") is None
        }
        assert no_wb == {"a177-independence-declaration"}, (
            f"「未钉住权威册」成员集漂移: {no_wb}"
        )
        a38 = next(e for e in unconnected if "a38" in e["entry_id"])
        tref = a38["template_ref"]
        assert tref.get("workbook"), "a38 的 workbook 应已是真实相对路径"
        # slice 惯例：`workbook` 相对 `backend/wp_templates/`（同 a3-console 那条）
        assert (_BACKEND / "wp_templates" / tref["workbook"]).is_file(), tref["workbook"]
        assert tref.get("workbook_format") == "xlsx", tref.get("workbook_format")
        assert "已更正" in (tref.get("why_null") or ""), (
            "a38 的 why_null 应记录归因第一层与「解析层缺陷已解除」"
        )
        assert len(unconnected) == 19, (
            f"未接通 entry 总数应不变（19），实得 {len(unconnected)}"
        )

    def test_a177_is_runtime_sheet_name_expression(
        self, unconnected: list[dict]
    ) -> None:
        """a177 的册在运行时才定（BP-8），slice 明禁硬指。"""
        a177 = next(e for e in unconnected if "a177" in e["entry_id"])
        tref = a177["template_ref"]
        assert tref.get("resolution_kind") == "runtime_sheet_name_expression"
        assert tref.get("workbook") is None
        assert tref.get("workbook_format") is None
        exprs = tref.get("sheet_name_exprs", [])
        assert exprs, "a177 应有 sheet_name_exprs"
        # 双变体：A17-7（team）/ A17-7A（非 team）
        assert "A17-7" in exprs[0] and "A17-7A" in exprs[0]

    def test_a38_workbook_absent_on_disk(self) -> None:
        """🔴 **方向已反转**：a38 的合册在磁盘上**且**能被解析到 —— 解析不到即打红。

        原断言是 `rglob("A3-8*")` 后 `assert not found`，那是**假事实**：glob 锚定文件名
        开头，而该合册真名以 `A3-7` 起头 ⇒ 该 pattern 恒 0 命中，断言恒绿。
        现算对照：`rglob("A3-8*")` = 0 命中，`rglob("*A3-8*")` = 1 命中（就是那本合册）。
        0 与 1 的差就是这条（以及 lane3 那三条）断言的全部成因。

        🔴 **禁**把 pattern 换成 `*A3-8*` 后仍断言 `not found` —— 那会立刻红，但红的原因
        是假事实被纠正，不是阻塞解除。
        """
        from app.services import wp_template_finder as FINDER

        anchored = sorted(
            f.name for f in _TEMPLATE_DIR.rglob("A3-8*")
            if f.suffix.lower() in (".xlsx", ".docx", ".xlsm") and "~$" not in f.name
        )
        contained = sorted(
            f.name for f in _TEMPLATE_DIR.rglob("*A3-8*")
            if f.suffix.lower() in (".xlsx", ".docx", ".xlsm") and "~$" not in f.name
        )
        assert anchored == [], f"口径说明失效：`A3-8*` 竟有命中 {anchored}"
        assert len(contained) == 1, (
            f"承载 A3-8 的册应恰 1 本，实得 {contained}（两数现算，禁写死）"
        )
        # 正向：两路入口都要解析到它
        one = FINDER.find_template_file_unresolved("A3-8")
        anyf = FINDER.find_template_file_any_unresolved("A3-8")
        assert one is not None and anyf is not None, (
            f"🔴 A3-8 解析不到合册（one={one} any={anyf}）⇒ 合册声明码索引可能被回退"
        )
        assert Path(one).name == contained[0], (Path(one).name, contained[0])
        assert Path(anyf).name == contained[0], (Path(anyf).name, contained[0])

    def test_other_a_codes_do_resolve_mutation_proof(self) -> None:
        """变异证明：同目录下 A3-3 / A5-1 / A10-1 都能解析到真实册。

        证明「a38 找不到册」不是扫描器写错，而是事实。
        """
        for code in ("A3-3", "A5-1", "A10-1"):
            found = [
                f for f in _TEMPLATE_DIR.rglob(f"{code}*")
                if f.suffix.lower() in (".xlsx", ".docx")
                and "~$" not in f.name
            ]
            assert found, f"{code} 应能解析到真实册（变异证明失效）"


# ═══════════════════════════════════════════════════════════════════════════
# §4 a3-console：投影对端缺失
# ═══════════════════════════════════════════════════════════════════════════


class TestA3ConsoleProjectionCounterpartAbsent:
    """a3-console 有 xlsx 册但 HTML 侧无对应数据集。

    🔴 `single_onlyoffice` 是**正确** capability，不是欠账。
    """

    _HOST = (
        _ROOT / "audit-platform/frontend/src/components/workpaper"
        / "GtA3ConsolidationConsole.vue"
    )

    #: A3-3 册 sheet1 的关键业务列（R5 表头实测）
    _EXCEL_KEY_COLUMNS = (
        "期末总份额",
        "期末A级份额",
        "期末B级份额",
        "管理费率",
        "业绩报酬收取方式",
        "可变动性",
    )

    def test_a3_console_is_the_only_projection_gap(
        self, unconnected: list[dict]
    ) -> None:
        # 🔴 判别器已换：`workbook_format == "xlsx"` 不再唯一 —— a38 的
        #    `workbook_format` 原值 `null` 是假事实（册在磁盘上且是 xlsx），已更正为
        #    `"xlsx"`。投影缺失这一类的权威判别是 **BP-10**（a3-console 独有）。
        xlsx_books = sorted(
            _short(e["entry_id"]) for e in unconnected
            if e.get("template_ref", {}).get("workbook_format") == "xlsx"
        )
        assert xlsx_books == ["a3-consolidation-console", "a38-goodwill-impairment"], (
            f"xlsx 册成员漂移: {xlsx_books}"
        )
        gap = [
            _short(e["entry_id"]) for e in unconnected
            if "BP-10" in set(e.get("capability_target_blocked_by") or ())
        ]
        assert gap == ["a3-consolidation-console"], f"投影缺失成员漂移: {gap}"

    def test_a3_console_workbook_exists(self, unconnected: list[dict]) -> None:
        """前提：a3-console 确实有 xlsx 册（阻塞不是缺册）。"""
        a3 = next(e for e in unconnected if "a3-consolidation" in e["entry_id"])
        wb = a3["template_ref"]["workbook"]
        assert wb, "a3-console 应声明权威册"
        found = [
            f for f in _TEMPLATE_DIR.rglob("A3-3*")
            if f.suffix.lower() == ".xlsx" and "~$" not in f.name
        ]
        assert found, "A3-3 册应在磁盘上"

    def test_html_side_persists_procedure_table_not_workbook_rows(self) -> None:
        """HTML 侧持久化的是程序表状态，不是册里的表格行。"""
        src = self._HOST.read_text(encoding="utf-8", errors="replace")
        # 通道是 field-overrides
        assert "field-overrides" in src, "a3-console 应走 field_overrides 通道"
        # scope 是 procedure_table
        assert "procedure_table" in src, \
            "a3-console 的 scope 应是 procedure_table（程序表，非册表格）"
        # 持久化字段只有 status / execution_summary
        persisted = set(re.findall(r"persistField\([^,]+,\s*'(\w+)'", src))
        assert persisted == {"status", "execution_summary"}, \
            f"a3-console 持久化字段应为 status/execution_summary，实际 {persisted}"

    def test_excel_columns_have_zero_frontend_counterpart(self) -> None:
        """🔴 解除信号：A3-3 册的业务列名在前端出现即打红。

        命中意味着有人建了结构化对端 ⇒ a3-console 可以接双向回写，
        本守卫与其 capability 须同步更新。
        """
        hits: dict[str, list[str]] = {}
        for col in self._EXCEL_KEY_COLUMNS:
            for pattern in ("*.vue", "*.ts"):
                for f in _FRONTEND.rglob(pattern):
                    try:
                        if col in f.read_text(encoding="utf-8", errors="replace"):
                            hits.setdefault(col, []).append(f.name)
                    except OSError:
                        continue
        assert not hits, (
            f"🔴 阻塞已解除：A3-3 册业务列已有前端对端 {hits} ⇒ "
            f"a3-console 可接双向回写，请同步更新本守卫与其 capability"
        )

    def test_program_row_fields_disjoint_from_excel_headers(self) -> None:
        """HTML 侧 ProgramRow 字段与 Excel 表头零交集（投影不可建的直接证据）。"""
        import openpyxl

        src = self._HOST.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"interface ProgramRow \{(.*?)\n\}", src, re.S)
        assert m, "宿主应有 ProgramRow 接口"
        html_fields = set(re.findall(r"(\w+)\??\s*:", m.group(1)))
        assert html_fields, "ProgramRow 应有字段"

        found = [
            f for f in _TEMPLATE_DIR.rglob("A3-3*")
            if f.suffix.lower() == ".xlsx" and "~$" not in f.name
        ]
        wb = openpyxl.load_workbook(str(found[0]), data_only=False)
        ws = wb.worksheets[0]
        headers = " ".join(
            str(ws.cell(row=5, column=c).value or "")
            for c in range(1, ws.max_column + 1)
        )
        wb.close()

        overlap = {f for f in html_fields if f in headers}
        assert not overlap, (
            f"ProgramRow 字段与 Excel 表头出现交集 {overlap} ⇒ "
            f"投影对端可能已建立，请复核 capability"
        )

    def test_a3_console_capability_stays_single_onlyoffice(self) -> None:
        """a3-console 的 capability 应保持 single_onlyoffice（正确态非欠账）。"""
        from app.services.workpaper_sync.entry_profile import (
            load_entry_manifest,
            manifest_entries_by_id,
        )
        load_entry_manifest.cache_clear()
        by_id = manifest_entries_by_id(load_entry_manifest())
        entry = by_id.get("xlsx/gt-a3-consolidation-console")
        assert entry is not None, "manifest 应含 a3-console"
        assert entry.get("capability") == "single_onlyoffice", (
            f"a3-console capability 应为 single_onlyoffice（两侧零交集，"
            f"无可投影数据集），实际 {entry.get('capability')}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# §5 canary 对照：接通的那条什么样
# ═══════════════════════════════════════════════════════════════════════════


class TestCanaryIsFullyConnected:
    """canary 四件套齐备——作为「接通」的定义性样板。"""

    def test_canary_has_contract_on_disk(self) -> None:
        path = (
            _BACKEND / "data" / "workpaper_sync_contracts"
            / "a51.cashflow_audit.json"
        )
        assert path.is_file(), "canary 契约应已落盘"
        raw = path.read_bytes()
        assert b"\r\n" not in raw, "契约须 LF 换行"
        assert raw.endswith(b"\n"), "契约须以换行结尾"

    def test_canary_provider_in_whitelist_and_ledger(self) -> None:
        from app.services.workpaper_sync.adapters.registry import (
            DELIVERED_PER_ENTRY_CONTRACTS,
            _ALLOWED_PROVIDER_MODULES,
        )
        module = "app.services.workpaper_sync.phase5_a51_cashflow_audit"
        assert module in _ALLOWED_PROVIDER_MODULES, "provider 应在白名单"
        rows = [
            r for r in DELIVERED_PER_ENTRY_CONTRACTS
            if str(r.get("entry_id")) == CANARY_ENTRY_ID
        ]
        assert len(rows) == 1, "台账应恰有 1 条 canary 记录"
        assert rows[0]["provider_module"] == module

    def test_canary_registration_plan_is_unblocked(self) -> None:
        from app.services.workpaper_sync.adapters import registry as REG
        from app.services.workpaper_sync.entry_profile import (
            load_entry_manifest,
            manifest_entries_by_id,
        )
        load_entry_manifest.cache_clear()
        entries = manifest_entries_by_id(load_entry_manifest())
        plan = REG.build_manifest_registration_plan(entries)
        item = next(p for p in plan if p.entry_id == CANARY_ENTRY_ID)
        assert item.provider_module == (
            "app.services.workpaper_sync.phase5_a51_cashflow_audit"
        )
        assert getattr(item, "blocked_reason", None) is None, (
            f"canary 注册计划不应被阻塞，实际 {item.blocked_reason}"
        )

    def test_canary_contract_loads_with_expected_shape(self) -> None:
        from app.services.workpaper_sync.phase5_a51_cashflow_audit import (
            load_contract_from_disk,
        )
        c = load_contract_from_disk()
        assert c.contract_id == "a51.cashflow_audit"
        assert len(c.sheets) == 2, "canary 契约应有 2 张受管 sheet"
        assert len(c.editable_field_keys()) == 24, "应有 24 个 editable 字段"
        assert len(c.protected_field_keys()) == 15, "应有 15 个 protected 字段"


# ═══════════════════════════════════════════════════════════════════════════
# §6 第 4 类阻塞：纯静态 entry 的 instrumentation 注入缺口（canary 自己）
# ═══════════════════════════════════════════════════════════════════════════

#: canary 的两条 definition digest（本轮真库实测 4 条 artifact 全 `state='approved'`）。
#: 🔴 这里**不**连 DB：本守卫是纯离线（文件 + 反射）判据，引 DB fixture 会让它在无库环境
#: 整体 error。等价固化方式 = 磁盘契约里的两个 digest + provider 现算 digest 三方相等 ——
#: 真库那 4 条 artifact 的 payload 正是由同一个 provider 现算出来的，digest 相等即等价。
CANARY_TEMPLATE_DEFINITION_SHA256 = (
    "d1edfca4e7ed07f6c5dc010ee9cbd244c36b39b2517ce865990e98b8cce21d7e"
)
CANARY_INSTRUMENTATION_DEFINITION_SHA256 = (
    "223b5a69bf79edbd0119a3b5e68c106b7a0e85de0f94f9b6ae0a6e8f143c53ab"
)

#: `instrument_workbook_bytes_multi` 的 `_GT_SYNC` 段硬取的 primary 行表几何属性。
#: 🔴 语义已变：原先它是「阻塞的机理」，现在它是**对照组** —— 静态通道上提后，
#: 这六项必须**仍然**逐条硬取，否则说明有人把行表几何放宽了（那是全域失去保护）。
_ROW_GEOMETRY_ATTRS = (
    "footer_row",
    "uuid_col",
    "table_name",
    "table_ref",
    "first_data_row",
    "last_data_row",
)

#: `stage_instrumented_substrate` **既有**的两个 provider 入口名（都要行表几何）。
#: 第三臂的入口名见 :data:`_STATIC_PROVIDER_ENTRY_NAME`。
_SUBSTRATE_PROVIDER_ENTRY_NAMES = ("instrumentation_spec", "instrumentation_specs")

#: 第三条分派臂读的 provider 入口名（纯静态，零行表几何）。
_STATIC_PROVIDER_ENTRY_NAME = "static_only_instrumentation_spec"


def top_level_function_names(module: Any) -> tuple[str, ...]:
    """模块自己定义的顶层函数名（剔除 import 进来的，否则会数到别人家的函数）。"""
    return tuple(
        sorted(
            name
            for name, value in vars(module).items()
            if inspect.isfunction(value)
            and getattr(value, "__module__", "") == module.__name__
        )
    )


def static_injection_entry_points(func_names: Iterable[str]) -> tuple[str, ...]:
    """从函数名集合里挑出「纯静态注入入口」—— 抽成纯函数以便**双向**变异。

    判据是**合取**：名字里同时含 `instrument` 与 `static` 两个语义词（大小写不敏感）。
    单含其一不算 —— `instrument_workbook_bytes_multi`（只有 instrument）与
    `_resolve_static_region`（只有 static，且在 excel_extract 而非本模块）都不得命中。

    🔴 方向已**反转**：改造前它的期望是空集（「还没有静态入口」），改造后它的期望是
    恰含平台那个静态注入器。判定函数本身一字未改 —— 反转的是期望值，这正是「同一判据
    可双向使用」的价值所在。
    """
    hits = []
    for name in func_names:
        low = name.lower()
        if "instrument" in low and "static" in low:
            hits.append(name)
    return tuple(sorted(hits))


class TestStaticOnlyInstrumentationGap:
    """canary 是平台**首个纯静态 entry**（0 个动态行表）。

    ═══ 本段的方向已经反转 ═══

    改造前：substrate 注入这一段整条走不通，本段是**阻塞登记**（「阻塞成立」+「解除信号」
    成对断言，解除信号命中即打红）。

    改造后（spec `workpaper-sync-pure-static-lane-and-combined-workbook-resolution`）：
    静态支已从「寄生在动态 primary 上」上提为平台**一等通道**，本段改为**正向判据** ——
    静态通道缺任一段即打红，同时既有动态通道的每一条校验必须**仍然**成立。

    ═══ 平台代码站点是 6 处，不是 5 处 ═══

    文件顶部阻塞表原写「五处」，现算是 **6** 处（第 6 处是观测清册，原表未列）：

    | # | 站点 | 处置 |
    |---|---|---|
    | 1 | `instrument_workbook_bytes_multi` | 旁路（新增 `instrument_workbook_bytes_static_only`） |
    | 2 | `ExcelInstrumentationSpec.__post_init__` | 旁路（新增 `ExcelStaticOnlyInstrumentationSpec`） |
    | 3 | `build_instrumentation_payload_for_sheets` | 旁路（新增 `build_static_only_instrumentation_payload`） |
    | 4 | `stage_instrumented_substrate` | 加第三条分派臂 |
    | 5 | `_build_identity_binding` | 加静态臂 |
    | 6 | `_observe_workbook` / `collect_workbook_structure` | 加静态清册（消除 `None`） |

    合计「**3 处旁路 + 3 处加分派臂**」，**放宽既有校验 0 处**。

    🔴 原 §6 有 **6** 个断言方法而顶部表写「五处」，差异有实义：
    `test_a51_provider_has_no_row_spec_by_design` 断言的是纯静态的**正确状态**
    （provider 就**不该**有行表 spec），**不是**平台阻塞 —— 把它算进阻塞数会让
    「阻塞已解除」的判据永远差一条。

    🔴 **DEC-3 仍然不可绕**：禁给纯静态 sheet 注一张退化动态表（1 行 Table + UUID 列）
    当载体（归档 spec `.kiro/specs/_archive/15-workpaper-sync-engine-hardening/
    workpaper-sync-static-cell-sheet-writeback/requirements.md`）。现在它由**类型边界**
    保证：`instrument_workbook_bytes_static_only` 的签名只接受
    `(source, spec, *, gate, identity_carriers)`，写不出 Table 也写不出隐藏列。

    🔴 **平台早就支持的部分不要写成阻塞**（会误报）：
    `validate_instrumentation_payload()` 不要求 `managed_sheets` 非空 ·
    `_frozen_sheet_anchors()` 迭代 `(managed_sheets, transposed_sheets, static_sheets)`
    并按 `region_kind=="static"` 分派 · `excel_extract` 有 `static_region` binding ·
    `excel_materialize` 有 `_plan_static_writes`。既有静态区**全部寄生在同 entry 的动态
    primary spec 上**（`static_sheets=(...)`），故缺口**只**影响「整个 entry 无动态表」
    这一形态 —— 这也是本 lane 零回归的结构性理由。
    """

    # ── 对照组：既有动态通道的校验一条都没被放宽（原阻塞①②③④⑥ 原样保留）──

    def test_multi_injector_rejects_empty_specs_and_hardcodes_row_geometry(self) -> None:
        """对照组①（原阻塞①）：注入器**仍**拒空 specs，`_GT_SYNC` 段**仍**硬取 6 项行表几何。

        静态通道是**旁路**而不是放宽 ⇒ 这些判据一条都不该变。任一条变红即
        「放宽了既有校验」，须回退那处改动。
        """
        from app.services.workpaper_sync import excel_instrumentation as XI

        src = inspect.getsource(XI.instrument_workbook_bytes_multi)
        assert "instrument_workbook_bytes_multi: specs 不得为空" in src, (
            "注入器的拒空 specs 判据不见了 ⇒ 有人放宽了既有校验（本 lane 明令旁路），"
            "须回退该处改动"
        )
        missing = [a for a in _ROW_GEOMETRY_ATTRS if f"primary.{a}" not in src]
        assert not missing, (
            f"`_GT_SYNC` 段不再引用行表几何 {missing} ⇒ 既有注入器被放宽，须回退"
        )
        assert "gate.assert_carrier_allowed" in src, "注入器应逐载体过 gate"
        for carrier in ("excel_table", "hidden_uuid_column"):
            assert f'"{carrier}"' in src, (
                f"既有注入器不再无条件要求载体 {carrier!r} ⇒ 它被放宽了；"
                f"纯静态应走 `instrument_workbook_bytes_static_only`（只声明 "
                f"defined_name + hidden_sheet），不是放宽这一个"
            )

    def test_instrumentation_spec_requires_row_table_geometry(self) -> None:
        """对照组②（原阻塞②）：`ExcelInstrumentationSpec` 的 5 个必填字段**仍**全是行表几何。"""
        from app.services.workpaper_sync.excel_instrumentation import (
            ExcelInstrumentationSpec,
        )

        fields = {f.name for f in dataclasses.fields(ExcelInstrumentationSpec)}
        required = {
            f.name
            for f in dataclasses.fields(ExcelInstrumentationSpec)
            if f.default is dataclasses.MISSING
        }
        geometry = {
            "first_data_row",
            "last_data_row",
            "footer_row",
            "uuid_col",
            "table_name",
        }
        assert geometry <= fields, f"spec 字段集缺 {geometry - fields}"
        assert geometry <= required, (
            f"行表几何 {geometry - required} 变成可选 ⇒ 既有类被放宽（本 lane 明令"
            f"新增兄弟类而不是放宽它），须回退"
        )
        # 静态支寄生字段在（既有静态区靠它，不得顺手删）
        assert "static_sheets" in fields, (
            "spec 应保留 static_sheets 寄生支（既有静态区全部挂在它上面）"
        )

    def test_static_only_spec_construction_is_really_rejected(self) -> None:
        """对照组③（原阻塞③）：纯静态参数**仍**被既有类的 `__post_init__` 打掉。

        不是读源码猜，是真 `ExcelInstrumentationSpec(...)` 抛 `InstrumentationError`。
        纯静态 entry 应该用**兄弟类** `ExcelStaticOnlyInstrumentationSpec`，
        而不是让既有类接纳零几何 —— 后者会让 19 本寄生静态区一起失去保护。
        """
        from app.services.workpaper_sync.excel_instrumentation import (
            ExcelInstrumentationSpec,
            InstrumentationError,
        )

        base = dict(
            entry_id=CANARY_ENTRY_ID,
            template_id="A51",
            template_relative_path="A/A5-1 现金流量表审计.xlsx",
            managed_sheet="A5-1-1列示于现金流量表的现金及现金等价物",
            managed_last_col="G",
            table_name="a51_static_region",
        )
        # ① 不给行区间（纯静态没有「首末数据行」概念）
        with pytest.raises(InstrumentationError) as ei:
            ExcelInstrumentationSpec(
                **base, first_data_row=0, last_data_row=0, footer_row=0, uuid_col="H"
            )
        assert "受管行区间非法" in str(ei.value)
        # ② 不给 footer（纯静态没有会被插删行推走的 footer）
        with pytest.raises(InstrumentationError) as ef:
            ExcelInstrumentationSpec(
                **base, first_data_row=1, last_data_row=1, footer_row=1, uuid_col="H"
            )
        assert "footer_row" in str(ef.value)

    def test_a51_provider_has_no_row_spec_by_design(self) -> None:
        """对照组④（原阻塞④，**从来不是平台阻塞**）：A5-1 provider 没有
        `instrumentation_spec(s)` —— 那是纯静态的**正确状态**。

        证明「不是漏写」：provider 同时**有** static-only 三件套
        （`static_only_instrumentation_spec` / `static_sheet_payloads` /
        `static_identity_bindings`）与委派门面 `build_instrumentation_payload`
        （`managed_sheets: []` + 非空 `static_sheets`）⇒ 它是有意选了静态形态。
        """
        from app.services.workpaper_sync import phase5_a51_cashflow_audit as A51

        for name in _SUBSTRATE_PROVIDER_ENTRY_NAMES:
            assert getattr(A51, name, None) is None, (
                f"provider 出现 {name} ⇒ 有人给纯静态 entry 造了行表 spec，"
                f"须人工复核是否违反 DEC-3（禁给纯静态注退化动态表当载体）；"
                f"另：`stage_instrumented_substrate` 的 fail-closed 守卫也会挡住它"
            )
        for name in (_STATIC_PROVIDER_ENTRY_NAME, "static_sheet_payloads",
                     "static_identity_bindings", "build_instrumentation_payload"):
            assert callable(getattr(A51, name, None)), (
                f"provider 应有 {name} —— 缺它说明纯静态形态本身退化了"
            )
        payload = A51.build_instrumentation_payload()
        assert payload["managed_sheets"] == [], (
            f"canary 应 0 个动态受管 sheet，实际 {payload['managed_sheets']}"
        )
        spec = A51.static_only_instrumentation_spec()
        assert len(payload["static_sheets"]) == len(spec.static_regions), (
            "payload 的 static_sheets 数应与 spec 的 static_regions 数相等（现算，禁写死）"
        )
        assert len(spec.static_regions) >= 1

    def test_identity_observer_main_binding_keeps_the_dynamic_path(self) -> None:
        """对照组⑤（原阻塞⑥）：身份观测器的**动态**路径逐条原样保留。

        静态臂是**加**的，不是替换的 ⇒ 动态路径的三项判据一条都不该少。
        """
        from app.services.workpaper_sync.published_identity_observer import (
            FrozenChildUnusableError,
            PublishedIdentityObserver,
            _frozen_sheet_anchors,
        )

        assert FrozenChildUnusableError is not None
        src = inspect.getsource(PublishedIdentityObserver._build_identity_binding)
        assert "契约未声明任何带 row_identity 的表" in src, (
            "动态主 binding 的 row_identity 硬要求不见了 ⇒ 动态路径被改动，须回退"
        )
        for token in ('anchors["table_name"]', "uuid_column_letter"):
            assert token in src, (
                f"动态主 binding 不再取 {token} ⇒ 动态路径被改动，须回退"
            )
        assert "elif len(row_tables) == 1:" in src, (
            "动态臂的单表兜底不见了 ⇒ 动态路径被改动"
        )
        # 对照：静态锚点**一直**能被读出（`_frozen_sheet_anchors` 零改动）
        fsa = inspect.getsource(_frozen_sheet_anchors)
        for collection in ("managed_sheets", "transposed_sheets", "static_sheets"):
            assert collection in fsa, (
                f"`_frozen_sheet_anchors` 应迭代 {collection} —— 它是平台**早就支持**"
                f"纯静态的部分，写成阻塞会误报"
            )

    # ── 正向判据：静态通道三段已接通（原「解除信号①②」与「阻塞⑤」在此反转）──

    def test_static_injection_entry_point_exists_in_excel_instrumentation(self) -> None:
        """正向①（原解除信号①，**方向已反转**）：`excel_instrumentation` 必须有静态注入入口。

        原判据是 `static_injection_entry_points(...) == ()`（「还没有」）。静态通道上提后
        它必然非空 —— 那条红是**设计意图**，本方法即它的绿态承接：入口不在即打红。
        """
        from app.services.workpaper_sync import excel_instrumentation as XI

        names = top_level_function_names(XI)
        # 正面控制：收集器确实抓到了真实注入器（不是空集合恒绿）
        assert "instrument_workbook_bytes_multi" in names, \
            "顶层函数收集器失效（连真实注入器都没抓到）—— 判据不可信"
        hits = static_injection_entry_points(names)
        # 🔴 判据按**语义类别**而不是写死集合：合取判据（instrument ∧ static）会同时命中
        #    注入器与 payload 构建器 —— 后者名里的 `instrumentation` 含 `instrument`。
        #    这不是误报，两者都是静态通道的平台入口；但「注入器必须恰 1 个」才是要守的。
        injectors = tuple(n for n in hits if n.startswith("instrument"))
        builders = tuple(n for n in hits if n.startswith("build"))
        assert injectors == ("instrument_workbook_bytes_static_only",), (
            f"纯静态**注入器**应恰 1 个，实际 {injectors} ⇒ 要么静态通道被删（回退），"
            f"要么有人加了第二个静态注入器（两个入口会各自漂，须收敛到一个）"
        )
        assert builders == ("build_static_only_instrumentation_payload",), (
            f"纯静态 payload **构建器**应恰 1 个，实际 {builders}"
        )
        assert set(hits) == set(injectors) | set(builders), (
            f"出现第三类静态入口 {sorted(set(hits) - set(injectors) - set(builders))} ⇒ "
            f"静态通道的入口面扩大了，须人工复核"
        )
        # 结构上写不出动态载体：签名只接受四项入参（DEC-3 由类型边界保证）
        params = list(
            inspect.signature(XI.instrument_workbook_bytes_static_only).parameters
        )
        assert params == ["source", "spec", "gate", "identity_carriers"], (
            f"静态注入器签名变了：{params} ⇒ 多一个入参就可能把 Table / 隐藏 UUID 列"
            f"写回来，DEC-3 的类型边界失效"
        )

    def test_static_injection_criterion_is_bidirectionally_mutated(self) -> None:
        """变异证明①（判据本体，双向）：同一判定函数必须两侧都可用。

        方向①（假阴防御）：含静态注入入口的名字集合 ⇒ 判据命中。
        方向②（假阳防御）：只含 instrument 或只含 static ⇒ 判据不命中。
        少了方向①判据可能恒空；少了方向②会把「只是有个静态辅助函数」误判成通道已建。
        """
        # 方向①：两种现实可能的命名都要抓到
        for fake in ("instrument_workbook_bytes_static", "instrument_static_only_workbook"):
            assert static_injection_entry_points(
                ("instrument_workbook_bytes", "instrument_workbook_bytes_multi", fake)
            ) == (fake,), f"判据漏抓静态注入入口 {fake}"
        # 大小写不敏感
        assert static_injection_entry_points(("InstrumentStaticRegion",)) == (
            "InstrumentStaticRegion",
        )
        # 方向②：单含其一不得命中
        assert static_injection_entry_points(
            ("instrument_workbook_bytes", "build_instrumentation_payload_for_sheets")
        ) == ()
        assert static_injection_entry_points(
            ("_resolve_static_region", "_extract_static_projection", "_plan_static_writes")
        ) == ()
        assert static_injection_entry_points(()) == ()

    def test_real_module_goes_red_when_the_static_injector_disappears(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """变异证明②（接真模块，方向已反转）：把静态注入入口从模块上摘掉后，
        走**同一条**真实链路（`top_level_function_names` + 判定函数）必须变空。

        这一条证的是「收集器 + 判据」整条接线，不只是判据的纯逻辑 ——
        只跑伪造名字集合的话，收集器写错（例如漏了 `__module__` 过滤）仍会恒绿。
        """
        from app.services.workpaper_sync import excel_instrumentation as XI

        def injectors_now() -> tuple[str, ...]:
            return tuple(
                n for n in static_injection_entry_points(top_level_function_names(XI))
                if n.startswith("instrument")
            )

        assert injectors_now() == ("instrument_workbook_bytes_static_only",), \
            "变异前真实模块应恰含那一个静态注入器"

        monkeypatch.delattr(XI, "instrument_workbook_bytes_static_only")
        assert injectors_now() == (), (
            "摘掉静态注入器后判据仍非空 ⇒ 本正向判据是死判据"
        )

        # 反向：`__module__` 不伪装时收集器应忽略（证明过滤在起作用，不是碰巧）
        def instrument_static_foreign(source: bytes) -> bytes:  # pragma: no cover
            return source

        monkeypatch.setattr(
            XI, "instrument_static_foreign", instrument_static_foreign, raising=False
        )
        assert "instrument_static_foreign" not in top_level_function_names(XI), \
            "收集器应剔除非本模块定义的函数（否则会数到 import 进来的别家函数）"

    def test_observer_main_binding_has_the_static_region_arm(self) -> None:
        """正向②（原解除信号②，**方向已反转**）：主 binding 必须有 `region_kind` 静态臂。

        原判据是 `"region_kind" not in src`。静态臂落地后它必然为红 —— 本方法承接其绿态。
        """
        from app.services.workpaper_sync.published_identity_observer import (
            PublishedIdentityObserver,
            _frozen_sheet_anchors,
        )

        src = inspect.getsource(PublishedIdentityObserver._build_identity_binding)
        assert "region_kind" in src, (
            "`_build_identity_binding` 没有 region_kind 静态臂 ⇒ 纯静态 entry 会被判"
            "`FrozenChildUnusableError`（契约里一张带 row_identity 的表都没有）"
        )
        static_seg = src[src.index("region_kind"):src.index("row_tables = [")]
        assert "不得随手挑第一张" in static_seg, (
            "静态臂缺「唯一对齐」判据 ⇒ 它与动态臂在这条上必须对称"
        )
        assert "static_tables[0]" not in static_seg, (
            "静态臂出现「取首元素」兜底 ⇒ 违反「禁随手挑第一张」"
        )
        assert src.index("region_kind") < src.index("row_tables = ["), (
            "静态臂应排在动态路径**之前**（静态锚点不带 table_name / uuid_column_letter，"
            "落到动态路径会拿裸 KeyError）"
        )
        # 正面控制：`_frozen_sheet_anchors` 仍含 region_kind（它一直是静态锚点的产出者）
        assert "region_kind" in inspect.getsource(_frozen_sheet_anchors)

    def test_stage_substrate_has_a_third_static_arm_after_the_two_row_arms(self) -> None:
        """正向③（原阻塞⑤，**方向已反转**）：substrate 组装必须有第三条静态分派臂，
        且它排在既有两臂**之后**。

        原判据是「源码不含 `static` 与 `region_kind`」。第三臂落地后它必然为红 ——
        本方法承接其绿态，并把「既有两臂零走向变更」一并钉死。
        """
        from app.services.workpaper_sync import projection_first_publication as PFP

        src = inspect.getsource(PFP.stage_instrumented_substrate)
        # 三个入口名都在，且第三臂的判据排在既有两臂之后
        for name in (*_SUBSTRATE_PROVIDER_ENTRY_NAMES, _STATIC_PROVIDER_ENTRY_NAME):
            assert f'"{name}"' in src, f"substrate 不认 provider 入口 {name}"
        i_specs = src.index("if callable(specs_fn):")
        i_spec = src.index("elif callable(spec_fn):")
        i_static = src.index("instrument_workbook_bytes_static_only(")
        assert i_specs < i_spec < i_static, (
            f"分派臂顺序应为 specs → spec → static_only，实际偏移 "
            f"{(i_specs, i_spec, i_static)} ⇒ 既有 provider 可能不再先命中原臂"
        )
        # DEC-3 结构化守卫：判据是**单向蕴含**，且排在分派之前
        assert "DEC-3" in src, "第三臂缺 DEC-3 fail-closed 守卫"
        i_guard = src.index("DEC-3")
        assert i_guard < i_specs, (
            "DEC-3 守卫必须排在分派**之前** —— 否则同时暴露 static_only 与 "
            "instrumentation_specs 的 provider 会先命中第一臂，永远查不到它"
        )
        # 安全门位置不变
        assert src.index("validate_ooxml_artifact(") < src.index("probe_path.replace(")

    # ── 覆盖面缺口补齐（原 §6 对这两个站点零断言）───────────────────────────

    def test_payload_builder_has_a_static_only_sibling(self) -> None:
        """覆盖面缺口①：`build_instrumentation_payload_for_sheets` 原先在 §6 里**无断言**。

        它是任务书列的第 3 处阻塞（`if not specs: raise` + `identity_carriers` 取
        `sorted(gate.allowed_carriers)`），改造后它是「已支持静态」的正面判据：
        通用构建器保持原样 + 兄弟构建器从**入参**取载体清单。
        """
        from app.services.workpaper_sync import excel_instrumentation as XI
        from app.services.workpaper_sync import phase5_a51_cashflow_audit as A51

        generic = inspect.getsource(XI.build_instrumentation_payload_for_sheets)
        assert "build_instrumentation_payload_for_sheets: specs 不得为空" in generic, (
            "通用 payload 构建器的拒空 specs 判据不见了 ⇒ 既有校验被放宽，须回退"
        )
        assert "list(sorted(gate.allowed_carriers))" in generic, (
            "通用构建器的 identity_carriers 取值逻辑被改动 ⇒ 它必须逐条保留"
        )
        assert callable(getattr(XI, "build_static_only_instrumentation_payload", None)), (
            "缺纯静态 payload 构建器 ⇒ provider 会被迫自组装（两份必漂）"
        )
        params = list(
            inspect.signature(XI.build_static_only_instrumentation_payload).parameters
        )
        assert params == [
            "spec", "template_definition_sha256", "template_sha256",
            "gate", "identity_carriers", "identity_anchors",
        ], f"静态 payload 构建器签名变了：{params}"
        # 载体清单从入参取，不从 gate 推导（否则语义过度声明）
        payload = A51.build_instrumentation_payload()
        gate = A51.excel_carrier_gate()
        assert payload["identity_carriers"] == list(A51.IDENTITY_CARRIERS)
        assert payload["identity_carriers"] != sorted(gate.allowed_carriers), (
            "静态 payload 的载体清单等于 gate 放行集 ⇒ 语义过度声明"
            "（宣称了本 entry 根本不写的载体）"
        )

    def test_observe_workbook_no_longer_hits_a_bare_attribute_error(self) -> None:
        """覆盖面缺口②：`_observe_workbook` 原先在 §6 里**无断言**（第 6 处阻塞未被覆盖）。

        机理：`canonical_digest(inventory.inventory_digest_input)` 无 `None` 守卫，而
        `collect_workbook_structure` 的第 3 返回值在全静态锚点下恒 `None` ⇒ 纯静态 entry
        在请求期观测抛的是裸 `AttributeError`，**不是**设计好的 `FrozenChildUnusableError`。

        处置方式是**消除 `None`**（返回真实的静态清册），不是给那行加 `None` 特判、
        也不是把字段改成 `Optional` —— 后两者会让 `identity_inventory_sha256` 对纯静态
        entry 变成假值，从此零反漂移能力。
        """
        from app.services.workpaper_sync.published_identity_observer import (
            PublishedIdentityObserver,
            StaticIdentityInventory,
            collect_workbook_structure,
        )

        observe_src = inspect.getsource(PublishedIdentityObserver._observe_workbook)
        assert "canonical_digest(inventory.inventory_digest_input)" in observe_src, (
            "digest 行变了 ⇒ 请复核第 6 处的处置是否退化成「特判 None」"
        )
        assert "inventory is None" not in observe_src, (
            "`_observe_workbook` 出现 None 特判 ⇒ 处置方式错了（应为消除 None）"
        )
        assert "Optional" not in observe_src, (
            "identity_inventory 被改成 Optional ⇒ 同上"
        )

        collect_src = inspect.getsource(collect_workbook_structure)
        assert "StaticIdentityInventory" in collect_src, (
            "`collect_workbook_structure` 不构造静态清册 ⇒ 第 3 返回值在全静态锚点下"
            "仍为 None，纯静态 entry 会撞裸 AttributeError"
        )
        i_dyn = collect_src.index("if primary_inventory is None:")
        i_static = collect_src.index("if primary_inventory is None and static_observed:")
        assert i_dyn < i_static, (
            "静态兜底必须排在动态赋值**之后** —— 否则会抢掉动态清册（Requirement 6.7）"
        )

        # 清册的两个受命成员 + 消费方审计要求的真实观测成员
        inv = StaticIdentityInventory(
            regions=(("k", "GT_A", "Sheet1"),), hidden_sheet_present=True,
            hidden_sheet_is_hidden=True, excluded_from_business_enumeration=True,
        )
        assert inv.row_uuids == ()
        assert inv.inventory_digest_input["kind"] == "static_region"
        assert inv.defined_names == ("GT_A",)
        # 🔴 行表事实**刻意不提供**：伪造它们就是 DEC-3 明禁的「注退化动态表当载体」
        for member in ("table_present", "table_ref", "resolved_sheet_by",
                       "uuid_column_hidden"):
            assert not hasattr(inv, member), f"静态清册伪造了行表事实 {member!r}"

    # ── 已达成状态（4 处，防回退）─────────────────────────────────────────

    def test_canary_definition_digests_are_frozen(self) -> None:
        """已达成①：definition 发布链真落库那两条 digest 三方相等（离线等价固化）。

        真库 `working_paper_sync_definition_artifact` 现查 `a51.cashflow_audit%` 4 条全
        `state='approved'`；那些 payload 由本 provider 现算，故「磁盘契约 digest ==
        provider 现算 digest == 本文件常量」三方相等即等价固化，且守住离线。
        """
        from app.services.workpaper_sync.definitions import canonical_digest
        from app.services.workpaper_sync import phase5_a51_cashflow_audit as A51

        path = (
            _BACKEND / "data" / "workpaper_sync_contracts"
            / "a51.cashflow_audit.json"
        )
        doc = json.loads(path.read_text(encoding="utf-8"))
        assert doc["template_definition_sha256"] == CANARY_TEMPLATE_DEFINITION_SHA256
        assert (
            doc["instrumentation_definition_sha256"]
            == CANARY_INSTRUMENTATION_DEFINITION_SHA256
        )
        assert canonical_digest(A51.template_definition_payload()) == \
            CANARY_TEMPLATE_DEFINITION_SHA256, (
                "provider 现算 template digest 与已发布 definition 不等 ⇒ 真库那 4 条 "
                "approved artifact 已与代码漂开，须重发布（不要改常量了事）"
            )
        assert canonical_digest(A51.instrumentation_definition_payload()) == \
            CANARY_INSTRUMENTATION_DEFINITION_SHA256, (
                "provider 现算 instrumentation digest 与已发布 definition 不等 ⇒ 同上"
            )

    def test_provider_satisfies_projection_supply_hard_requirements(self) -> None:
        """已达成②：provider 有 `load_projection_supply` 硬要求的那两个可调用名。

        缺任一即 `ProviderModuleNotAllowedError: provider 是空壳`，发布链在 plan 阶段
        就断 —— 本轮 `fix_task76_provision_projection_definitions.py --apply` 能跑到
        `status=ok / created_total=5` 正是靠这两个名字到位。
        """
        from app.services.workpaper_sync import phase5_a51_cashflow_audit as A51
        from app.services.workpaper_sync import projection_provisioning as PP

        required = ("publish_pilot_definitions", "assert_contract_file_matches_source")
        supply_src = inspect.getsource(PP.load_projection_supply)
        for name in required:
            assert name in supply_src, (
                f"`load_projection_supply` 不再要求 {name} ⇒ 硬要求清单变了，"
                f"请照现状更新本判据（不要照抄旧名字）"
            )
            assert callable(getattr(A51, name, None)), (
                f"provider 缺可调用的 {name} ⇒ load_projection_supply 会判它是空壳，"
                f"发布链在 plan 阶段整体断"
            )

    def test_contract_declares_pure_static_sheets(self) -> None:
        """已达成③：契约两张 sheet 都是 `region_kind=static` 且 0 动态行。"""
        from app.services.workpaper_sync.phase5_a51_cashflow_audit import (
            load_contract_from_disk,
        )

        path = (
            _BACKEND / "data" / "workpaper_sync_contracts"
            / "a51.cashflow_audit.json"
        )
        doc = json.loads(path.read_text(encoding="utf-8"))
        sheets = doc["sheets"]
        assert len(sheets) == 2, f"canary 契约应 2 张 sheet，实际 {len(sheets)}"
        for sheet in sheets:
            boundary = sheet.get("region_boundary_locator") or {}
            assert boundary.get("region_kind") == "static", (
                f"{sheet.get('sheet_key')} 的 region_kind 应为 static，"
                f"实际 {boundary.get('region_kind')!r} ⇒ 纯静态形态被改动，"
                f"请复核是否有人按 DEC-3 禁止的方式造了动态载体"
            )
        # 解析后的 table 侧同样零动态行（两个口径都查，防单侧漂）
        contract = load_contract_from_disk()
        for sheet in contract.sheets:
            for table in sheet.tables:
                assert table.has_dynamic_rows is False, (
                    f"{sheet.sheet_key}/{table.table_key} 出现动态行 ⇒ 违反 DEC-3"
                    f"（禁给纯静态 sheet 注退化动态表当载体），须人工复核"
                )
                assert table.row_identity is None, (
                    f"{sheet.sheet_key}/{table.table_key} 出现 row_identity ⇒ 同上"
                )

    def test_adjudication_covers_canary_and_e1_plan_unblocker(self) -> None:
        """已达成④：裁决台账含 canary 与 E1 两条。

        E1 那条是**解除「plan 阶段整体抛错连带阻塞全部 entry」的关键** ——
        `_build_plan_rows()` 要求台账内每条 entry 都有显式裁决，而 `--entry` 过滤发生在
        plan 之后，缺一条就把全部 entry 一起挡住。
        """
        path = _BACKEND / "data" / "workpaper_sync_entry_wp_code_adjudication.json"
        raw = path.read_bytes()
        assert b"\r\n" not in raw, "裁决台账须 LF 换行（CRLF 会让 digest 与 CI 对不上）"
        assert raw.endswith(b"\n"), "裁决台账须以换行结尾"
        doc = json.loads(raw.decode("utf-8"))
        by_id = {
            str(r.get("entry_id")): r for r in doc["adjudications"]
        }
        expected = {
            CANARY_ENTRY_ID: "a51.cashflow_audit",
            "xlsx/gt-e1-monetary-fund": "e1.monetary_fund_detail",
        }
        for entry_id, contract_id in expected.items():
            row = by_id.get(entry_id)
            assert row is not None, (
                f"裁决台账缺 {entry_id} ⇒ `_build_plan_rows()` 会在 plan 阶段整体抛错，"
                f"连带阻塞其余全部 entry（--entry 过滤在 plan 之后）"
            )
            assert row.get("contract_id") == contract_id, (
                f"{entry_id} 的 contract_id 应为 {contract_id}，实际 {row.get('contract_id')}"
            )
            assert row.get("resolvable_for_provisioning") is True, (
                f"{entry_id} 应可供发布链解析，实际 "
                f"{row.get('resolvable_for_provisioning')!r}"
            )
            assert (row.get("basis") or {}).get("wp_index_evidence"), (
                f"{entry_id} 的裁决应有 wp_index 实证（裁决不能只写结论）"
            )
