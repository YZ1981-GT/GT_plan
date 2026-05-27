"""集成测试 — 多表 + 多层表头 Word 导出（Sprint 2 Task 2.7）.

Spec:   .kiro/specs/disclosure-note-full-revamp/ Sprint 2 Task 2.7
Design: D7 致同 Word 排版规范
Reqs:   R5.2 多表渲染 + 多层表头合并

测试目标：
  1. 应收票据 12 张表全部出现（伪造 _tables 数组 12 个）— 单元格采样断言
  2. 固定资产变动表二级表头合并正确（用 fill_multi_header 构造 + 验证 OOXML）
  3. 单表降级（无 _tables 字段）正常工作 — 老结构兼容
  4. 表名 H4 标题渲染（多表时加表名标题，单表时不加）

策略：
- 沿用 test_note_export_visual.py 的 SimpleNamespace + Mock db 模式
- 解 docx zip 取 word/document.xml 做字符串断言
"""

from __future__ import annotations

import zipfile
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.note_word_exporter import (
    NoteWordExporter,
    fill_multi_header,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_note(
    section: str,
    title: str,
    *,
    table_data: dict | None = None,
):
    return SimpleNamespace(
        id=uuid4(),
        project_id=uuid4(),
        year=2025,
        note_section=section,
        section_title=title,
        account_name=None,
        content_type=None,
        table_data=table_data,
        text_content=None,
        source_template=None,
        status=None,
        sort_order=None,
        is_deleted=False,
        is_stale=False,
    )


def _make_db(notes: list) -> MagicMock:
    db = MagicMock()
    scalars = MagicMock()
    scalars.all = MagicMock(return_value=notes)
    result = MagicMock()
    result.scalars = MagicMock(return_value=scalars)
    db.execute = AsyncMock(return_value=result)
    return db


def _extract(docx_bytes: bytes, member: str) -> str:
    with zipfile.ZipFile(BytesIO(docx_bytes)) as z:
        return z.read(member).decode("utf-8")


# ===========================================================================
# 1. 应收票据 12 张表全部出现
# ===========================================================================


@pytest.mark.asyncio
async def test_multi_table_12_subtables_all_rendered():
    """应收票据 12 张表全部出现 — 每张表都有自己的表名 + 至少一行数据."""
    sub_tables = []
    for i in range(12):
        sub_tables.append({
            "name": f"应收票据子表-{i + 1}",
            "headers": ["项目", "金额"],
            "rows": [
                {"label": f"票据{i + 1}", "values": [1000.0 + i * 100]},
            ],
        })
    note = _make_note(
        "1",
        "应收票据",
        table_data={
            "headers": sub_tables[0]["headers"],
            "rows": sub_tables[0]["rows"],
            "name": sub_tables[0]["name"],
            "_tables": sub_tables,
        },
    )
    db = _make_db([note])
    exporter = NoteWordExporter(db)
    bio = await exporter.export(project_id=uuid4(), year=2025)
    doc_xml = _extract(bio.getvalue(), "word/document.xml")

    # 12 张表名都必须出现在 document.xml 文本节点中
    for i in range(12):
        name = f"应收票据子表-{i + 1}"
        assert name in doc_xml, f"子表 {name} 未在 document.xml 中渲染"

    # 12 行数据 label 也必须出现
    for i in range(12):
        label = f"票据{i + 1}"
        assert label in doc_xml, f"row label {label} 未渲染"


# ===========================================================================
# 2. 固定资产变动表二级表头合并正确（fill_multi_header 单元 + OOXML）
# ===========================================================================


def test_fill_multi_header_two_level_merge_correctness():
    """固定资产变动表"本期增加→购置/在建转入"二级表头 — 合并 colspan/rowspan 正确."""
    from docx import Document as _Doc

    # 模板：
    #   行1: [项目(rs=2), 期初余额(rs=2), 本期增加(cs=2), 期末余额(rs=2)]
    #   行2: [—,         —,           购置, 在建转入,    —]
    # 总列数 = 5（项目 + 期初 + 购置 + 在建转入 + 期末）
    header_rows = [
        [
            {"text": "项目",     "rowspan": 2, "colspan": 1},
            {"text": "期初余额", "rowspan": 2, "colspan": 1},
            {"text": "本期增加", "rowspan": 1, "colspan": 2},
            {"text": "期末余额", "rowspan": 2, "colspan": 1},
        ],
        [
            # 注意：跳过 col0/col1/col4（被上方 rowspan 占用），只填 col2/col3
            {"text": "购置",        "rowspan": 1, "colspan": 1},
            {"text": "在建转入",    "rowspan": 1, "colspan": 1},
        ],
    ]

    doc = _Doc()
    table = doc.add_table(rows=2, cols=5)
    fill_multi_header(table, header_rows, total_cols=5)

    # 序列化检测合并：master cell.text 必须正确写入；占位 cell 则不重复出现
    # 行 0：master cell 0/1/2/4 含文字；col3 是 col2 colspan 占位
    assert table.rows[0].cells[0].text.strip() == "项目"
    assert table.rows[0].cells[1].text.strip() == "期初余额"
    assert table.rows[0].cells[2].text.strip() == "本期增加"
    assert table.rows[0].cells[4].text.strip() == "期末余额"

    # 行 1：col2/col3 含 购置/在建转入；col0/1/4 是上方 rowspan 占位（不应有新文字）
    assert table.rows[1].cells[2].text.strip() == "购置"
    assert table.rows[1].cells[3].text.strip() == "在建转入"

    # 序列化为 docx → 解 OOXML 验 gridSpan / vMerge
    bio = BytesIO()
    doc.save(bio)
    bio.seek(0)
    doc_xml = _extract(bio.getvalue(), "word/document.xml")

    # colspan=2 → gridSpan val="2"
    assert 'w:gridSpan' in doc_xml, "未发现 gridSpan 元素（colspan 合并失败）"
    assert 'w:val="2"' in doc_xml, "gridSpan val=2 缺失"
    # rowspan>1 → vMerge restart + continue
    assert 'w:vMerge' in doc_xml, "未发现 vMerge 元素（rowspan 合并失败）"


# ===========================================================================
# 3. 单表降级（无 _tables 字段）正常工作
# ===========================================================================


@pytest.mark.asyncio
async def test_single_table_no_underscore_tables_field():
    """老结构兼容：table_data 无 _tables 字段时按单表渲染."""
    note = _make_note(
        "1",
        "货币资金",
        table_data={
            "headers": ["项目", "期末数", "期初数"],
            "rows": [
                {"label": "库存现金", "values": [100.0, 80.0]},
                {"label": "银行存款", "values": [9000.0, 8500.0]},
            ],
            # 无 _tables 字段
        },
    )
    db = _make_db([note])
    exporter = NoteWordExporter(db)
    bio = await exporter.export(project_id=uuid4(), year=2025)
    doc_xml = _extract(bio.getvalue(), "word/document.xml")

    assert "库存现金" in doc_xml
    assert "银行存款" in doc_xml
    # 单表降级时不应出现 H4 表名标题（因为只有一张表）— 用 name 字段也不渲染
    # （headers / rows 直接挂顶层）— 没什么独立 name 文本节点要求


# ===========================================================================
# 4. 表名 H4 标题渲染（多表时加，单表时不加）
# ===========================================================================


@pytest.mark.asyncio
async def test_multi_table_renders_h4_table_name_titles():
    """多表时每张表加表名 H4 标题；单表时不加."""
    multi_note = _make_note(
        "1",
        "固定资产",
        table_data={
            "headers": ["项目", "余额"],
            "rows": [],
            "_tables": [
                {"name": "原值变动表", "headers": ["项目", "余额"],
                 "rows": [{"label": "房屋建筑物", "values": [1000.0]}]},
                {"name": "累计折旧变动表", "headers": ["项目", "余额"],
                 "rows": [{"label": "房屋建筑物", "values": [200.0]}]},
                {"name": "减值准备变动表", "headers": ["项目", "余额"],
                 "rows": [{"label": "房屋建筑物", "values": [50.0]}]},
            ],
        },
    )
    db = _make_db([multi_note])
    exporter = NoteWordExporter(db)
    bio = await exporter.export(project_id=uuid4(), year=2025)
    doc_xml = _extract(bio.getvalue(), "word/document.xml")

    # 3 个表名 H4 都必须出现
    assert "原值变动表" in doc_xml
    assert "累计折旧变动表" in doc_xml
    assert "减值准备变动表" in doc_xml


@pytest.mark.asyncio
async def test_single_table_does_not_render_redundant_name():
    """单表（_tables 仅 1 条 / 或老结构）不渲染重复 H4 表名（避免冗余）."""
    note = _make_note(
        "1",
        "货币资金",
        table_data={
            "headers": ["项目", "余额"],
            "rows": [{"label": "库存现金", "values": [100.0]}],
            "name": "货币资金明细",
            # 不放 _tables — 老结构降级为 [table_data]
        },
    )
    db = _make_db([note])
    exporter = NoteWordExporter(db)
    bio = await exporter.export(project_id=uuid4(), year=2025)
    doc_xml = _extract(bio.getvalue(), "word/document.xml")

    # 当只有一张表（tables_to_render == 1）时，note_word_exporter 不会渲染 H4 表名
    # （len(tables_to_render) > 1 才加）
    # 注意：这里的"货币资金明细"作为 name 字段不应作为独立 H4 标题出现
    # （但章节标题 "货币资金" 仍可能在文档其他地方出现 — 那是 note.section_title 渲染逻辑）

    # 章节标题（"货币资金"）应该出现
    assert "货币资金" in doc_xml
    # 但作为 H4 表名的"货币资金明细"在单表场景不应被加
    # 由于我们设的 name 是"货币资金明细"，单表时不加 H4，故"货币资金明细"
    # 应该不在文档中（除非 _render_table 内部渲染 — 实测它不渲染 name）
    assert "货币资金明细" not in doc_xml, (
        "单表场景不应渲染表名 H4 标题"
    )
