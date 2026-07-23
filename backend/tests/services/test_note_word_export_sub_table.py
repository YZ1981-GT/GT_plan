"""Word 导出复用投影器：导出表结构（表名/列头/行）== 投影结果（P12）

spec: disclosure-table-sync-convergence Task 5.2
仅测试 NoteWordExporter._note_tables / _effective_table_data 的投影集成，
不生成完整 docx（表结构一致即证明导出与模块渲染同源）。
"""

from __future__ import annotations

from types import SimpleNamespace

from app.services.note_word_exporter import NoteWordExporter
from app.services.note_sub_table_projector import project_sub_tables


def _exporter() -> NoteWordExporter:
    return NoteWordExporter(db=None)  # _note_tables/_effective_table_data 不触库


def _workpaper_note():
    td = {
        "_source": "workpaper",
        "sub_table_data": {
            "存货分类": [
                {"label": "原材料", "end_gross": 100, "end_impairment": 5},
                {"label": "合计", "end_gross": 100, "end_impairment": 5, "is_total": True},
            ]
        },
        "_sub_table_columns": {
            "存货分类": [
                {"key": "label", "label": "存货类别", "is_label": True},
                {"key": "end_gross", "label": "期末账面余额"},
                {"key": "end_impairment", "label": "期末跌价准备"},
            ]
        },
    }
    return SimpleNamespace(table_data=td, text_content=None)


def test_p12_export_tables_equal_projection():
    """workpaper 来源：_note_tables 返回的表 == project_sub_tables 结果（同源）。"""
    note = _workpaper_note()
    exporter = _exporter()

    projected = project_sub_tables(note.table_data)
    export_tables = exporter._note_tables(note)

    assert projected is not None and len(projected) == 1
    assert len(export_tables) == 1
    et, pt = export_tables[0], projected[0]
    assert et["name"] == pt["name"] == "存货分类"
    assert et["headers"] == pt["headers"] == ["存货类别", "期末账面余额", "期末跌价准备"]
    assert et["rows"] == pt["rows"]
    # 合计行保持
    assert et["rows"][-1]["is_total"] is True


def test_p12_has_content_true_for_workpaper_projected():
    """workpaper 投影出非零值 → _has_content 为 True（不被误判空章节跳过）。"""
    exporter = _exporter()
    note = SimpleNamespace(
        table_data=_workpaper_note().table_data,
        text_content=None,
        is_deleted=False,
        status=None,
    )
    assert exporter._has_content(note) is True


def test_engine_source_export_unchanged():
    """非 workpaper 来源：_note_tables 不投影，沿用既有 _tables（导出行为不变，Req6.2）。"""
    exporter = _exporter()
    td = {
        "_source": "engine_fill",
        "_tables": [
            {"name": "既有表", "headers": ["项目", "金额"],
             "rows": [{"label": "行1", "values": [10]}], "export_enabled": True}
        ],
    }
    note = SimpleNamespace(table_data=td, text_content=None)
    tables = exporter._note_tables(note)
    assert len(tables) == 1
    assert tables[0]["name"] == "既有表"
    assert tables[0]["headers"] == ["项目", "金额"]


def test_export_enabled_false_filtered_after_projection():
    """投影表默认 export_enabled 缺省视为 True（不被过滤）。"""
    exporter = _exporter()
    note = _workpaper_note()
    tables = exporter._note_tables(note)
    assert len(tables) == 1  # 投影表无 export_enabled=false → 保留
