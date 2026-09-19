"""D4-9 同 sheet 双区 instrumentation —— 行为级验证（judge-first）。

spec: d4-9-customer-structure-bidirectional-writeback · Task 1
Requirements 2.1 / 2.2 / 1.4 / 8.1 / 8.3

背景（design §2.1.1，实测裁决）：
D4-9「重要客户结构分析D4-9」的本期(R13-22)与上期(R27-36)是**同一张 sheet** 内的
两个受管区。`_attach_table_part` 原实现对同一 sheet 二次注入无条件新建一个独立
``<tableParts>`` 块 ⇒ 产出两个 ``<tableParts>`` 块（非法 OOXML，只允许一个）；
openpyxl 只认出最后一张 Table，第一区 identity 被丢弃 = 假双向。

修复（路径 A）：``_attach_table_part`` 在 sheet 已有 ``<tableParts>`` 块时**往块内
追加** ``<tablePart>`` 并把 ``count`` +1，而不是新建块。单区 sheet（现有全部工作簿）
无既有块 ⇒ 走原路径，注入字节不变（Task 40/41 冻结的 structure hash 守卫）。

本文件锁死三条判据：
1. 真实注入回归：D4-9 同 sheet 两 spec（UUID 列 W/X）→ openpyxl 同时认出两张 Table；
2. 单区字节稳定：单 spec 注入只产出**一个** ``<tableParts count="1">``，合并分支未触发；
3. 变异守卫：把 ``_attach_table_part`` 改回「无条件新建独立块」→ 同 sheet 双区
   openpyxl 只认 1 张 table（RED），证明判据 1 真的在盯这个缺陷。
"""
from __future__ import annotations

import io
import os
import re
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import excel_instrumentation as EI  # noqa: E402
from app.services.workpaper_sync.phase5_d4_revenue_detail import (  # noqa: E402
    excel_carrier_gate,
)

_TEMPLATE_REL = "D/D4 收入底稿.xlsx"
_D49_SHEET = "重要客户结构分析D4-9"

# design §2.1.1：本期 R13-22（合计 R23）/ 上期 R27-36（合计 R37）；UUID 列 W/X（互不相同）。
_SPEC_CURRENT = dict(
    template_id="D49C",
    managed_sheet=_D49_SHEET,
    first_data_row=13,
    last_data_row=22,
    footer_row=23,
    managed_last_col="S",
    uuid_col="W",
    table_name="GT_D49C_ROWS",
    sheet_key="d49c-managed",
)
_SPEC_PRIOR = dict(
    template_id="D49P",
    managed_sheet=_D49_SHEET,
    first_data_row=27,
    last_data_row=36,
    footer_row=37,
    managed_last_col="S",
    uuid_col="X",
    table_name="GT_D49P_ROWS",
    sheet_key="d49p-managed",
)


def _spec(entry_id: str, **kw) -> EI.ExcelInstrumentationSpec:
    return EI.ExcelInstrumentationSpec(
        entry_id=entry_id,
        template_relative_path=_TEMPLATE_REL,
        **kw,
    )


def _read_template() -> bytes:
    path = _REPO / "backend" / "wp_templates" / _TEMPLATE_REL
    assert path.is_file(), f"权威模板缺失: {path}"
    return path.read_bytes()


def _tables_on_d49(instrumented_bytes: bytes) -> list[str]:
    """用 openpyxl（独立第三方 OOXML 实现）加载后 D4-9 sheet 上的 Table displayName。"""
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(instrumented_bytes))
    try:
        ws = wb[_D49_SHEET]
        return sorted(ws.tables.keys())
    finally:
        wb.close()


@pytest.fixture(scope="module")
def dual_region_bytes() -> bytes:
    specs = [
        _spec("gt-d4-customer-structure", **_SPEC_CURRENT),
        _spec("gt-d4-customer-structure", **_SPEC_PRIOR),
    ]
    inst = EI.instrument_workbook_bytes_multi(
        _read_template(), specs, gate=excel_carrier_gate()
    )
    return inst.instrumented_bytes


# ═══════════════════════════════════════════════════════════════════════════
# 判据 1：真实注入回归 —— 同 sheet 双区，openpyxl 同时认出两张 Table
# ═══════════════════════════════════════════════════════════════════════════
class TestDualRegionRecognized:
    """**Validates: Requirements 2.1, 2.2, 1.4**"""

    def test_openpyxl_sees_both_tables_on_the_same_sheet(
        self, dual_region_bytes: bytes
    ) -> None:
        tables = _tables_on_d49(dual_region_bytes)
        assert tables == ["GT_D49C_ROWS", "GT_D49P_ROWS"], (
            "同 sheet 双区注入后 openpyxl 未同时认出两张 Table —— "
            f"实得 {tables}（缺失即第一区 identity 被丢弃 = 假双向）"
        )

    def test_exactly_one_tableparts_block_with_count_two(
        self, dual_region_bytes: bytes
    ) -> None:
        """OOXML 合法性：整张 worksheet 只允许一个 ``<tableParts>``，且 count==2。"""
        import zipfile

        with zipfile.ZipFile(io.BytesIO(dual_region_bytes)) as zf:
            # 找到 D4-9 sheet 部件（含两个 tablePart 引用的那张）
            target = None
            for name in zf.namelist():
                if not name.startswith("xl/worksheets/sheet"):
                    continue
                xml = zf.read(name).decode("utf-8")
                if xml.count("<tablePart ") == 2:
                    target = xml
                    break
            assert target is not None, "找不到含两个 <tablePart> 的受管 sheet 部件"

        blocks = re.findall(r"<tableParts\b[^>]*>", target)
        assert len(blocks) == 1, (
            f"同一 worksheet 出现 {len(blocks)} 个 <tableParts> 块 —— OOXML 只允许一个"
        )
        count_m = re.search(r'<tableParts\b[^>]*\bcount="(\d+)"', target)
        assert count_m and count_m.group(1) == "2", (
            f"<tableParts count> 未随第二区 +1，实得 {count_m and count_m.group(1)}"
        )

    def test_result_is_a_valid_ooxml_parseable_by_elementtree(
        self, dual_region_bytes: bytes
    ) -> None:
        """独立 XML 解析器也能解析受管 sheet（非法双块会让解析器不认）。"""
        import xml.etree.ElementTree as ET
        import zipfile

        with zipfile.ZipFile(io.BytesIO(dual_region_bytes)) as zf:
            for name in zf.namelist():
                if name.startswith("xl/worksheets/sheet"):
                    ET.fromstring(zf.read(name))  # 抛异常即 FAIL


# ═══════════════════════════════════════════════════════════════════════════
# 判据 2：单区路径字节稳定 —— 合并分支对单区 sheet 不触发（358 工作簿回归守卫）
# ═══════════════════════════════════════════════════════════════════════════
class TestSingleRegionPathUnchanged:
    """**Validates: Requirements 8.1, 8.3**

    单区（无既有 ``<tableParts>``）必须走 else 分支新建 ``count="1"`` 块。这是那 358 个
    单 sheet 工作簿注入字节不变的直接证据 —— 合并分支只在**已有块**时才动手。
    """

    def test_single_injection_yields_one_block_count_one(self) -> None:
        specs = [_spec("gt-d4-customer-structure", **_SPEC_CURRENT)]
        inst = EI.instrument_workbook_bytes_multi(
            _read_template(), specs, gate=excel_carrier_gate()
        )
        tables = _tables_on_d49(inst.instrumented_bytes)
        assert tables == ["GT_D49C_ROWS"], f"单区注入实得 {tables}"

        import zipfile

        with zipfile.ZipFile(io.BytesIO(inst.instrumented_bytes)) as zf:
            hit = None
            for name in zf.namelist():
                if not name.startswith("xl/worksheets/sheet"):
                    continue
                xml = zf.read(name).decode("utf-8")
                if "<tablePart " in xml:
                    hit = xml
                    break
        assert hit is not None
        assert hit.count("<tableParts") == 1
        assert re.search(r'<tableParts\b[^>]*\bcount="1"', hit), (
            "单区注入未产出 count=\"1\" 块 —— 合并分支不应对单区 sheet 触发"
        )

    def test_attach_on_fresh_sheet_is_byte_identical_to_legacy_new_block(self) -> None:
        """``_attach_table_part`` 对无既有块的 sheet 产物 = 历史「新建独立块」形态，逐字节相同。

        这把「单区路径未被改动」钉在函数级：合并分支的 ``if existing`` 对无块 sheet 为假，
        返回值必须与只跑 else 分支的旧实现一字不差。
        """
        fresh = '<worksheet xmlns:r="http://x"><sheetData/></worksheet>'
        attached = EI._attach_table_part(fresh, rel_id="rIdX")
        legacy = fresh.replace(
            "</worksheet>",
            '<tableParts count="1"><tablePart r:id="rIdX"/></tableParts></worksheet>',
        )
        assert attached == legacy, (
            "无既有块时 _attach_table_part 产物偏离历史「新建独立块」形态 —— "
            "会改掉 358 个单 sheet 工作簿的注入字节"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 判据 3：变异守卫 —— 改回「无条件新建独立块」必红（同 sheet 双区只认 1 张 table）
# ═══════════════════════════════════════════════════════════════════════════
class TestMutationGuard:
    """**Validates: Requirements 8.1, 8.3**

    把 ``_attach_table_part`` 换成缺陷版（无条件新建独立块，即修复前的行为），同 sheet
    双区注入后 openpyxl 只认出 1 张 table。这条证明判据 1 不是空转：拿掉修复它立刻红。
    """

    def test_reverting_to_unconditional_new_block_drops_first_region(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _broken(sheet_xml: str, *, rel_id: str = EI._GT_TABLE_REL_ID) -> str:
            # 修复前的行为：无条件新建独立 <tableParts> 块（不合并）。
            root_end = sheet_xml.find(">", sheet_xml.find("<worksheet"))
            root_tag = sheet_xml[: root_end + 1] if root_end > 0 else sheet_xml
            ns = "" if 'xmlns:r="' in root_tag else f' xmlns:r="{EI._REL_NS}"'
            block = (
                f'<tableParts{ns} count="1">'
                f'<tablePart r:id="{rel_id}"/></tableParts>'
            )
            for tail in EI._SHEET_TAIL_ORDER:
                idx = sheet_xml.find(f"<{tail}")
                if idx >= 0:
                    return sheet_xml[:idx] + block + sheet_xml[idx:]
            return EI._insert_before(
                sheet_xml, "</worksheet>", block, what="tableParts"
            )

        monkeypatch.setattr(EI, "_attach_table_part", _broken)

        specs = [
            _spec("gt-d4-customer-structure", **_SPEC_CURRENT),
            _spec("gt-d4-customer-structure", **_SPEC_PRIOR),
        ]
        inst = EI.instrument_workbook_bytes_multi(
            _read_template(), specs, gate=excel_carrier_gate()
        )
        tables = _tables_on_d49(inst.instrumented_bytes)
        assert tables != ["GT_D49C_ROWS", "GT_D49P_ROWS"], (
            "缺陷版仍被 openpyxl 认出两张 table —— 变异守卫空转，判据 1 不可信"
        )
        assert len(tables) <= 1, (
            f"缺陷版应让 openpyxl 只认出 ≤1 张 table，实得 {tables}"
        )
