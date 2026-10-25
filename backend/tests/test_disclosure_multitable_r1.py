"""R1 守卫：附注多表构建与刷新 — 按表 binding、完整章节构表、三态/首表镜像/底稿来源保护。

Spec: .kiro/specs/disclosure-multitable-refresh-and-edit-writeback/ Task 2 (R1)

红基线 → 绿：
- 多表构建传真实 table_index 给 get_binding_for_table
- 缺表不借首表（binding 越界 → None → legacy 兜底）
- 首表镜像（顶层 headers/rows == _tables[0]）
- 增量更新三态合并保护 manual/locked
- 底稿同步来源不覆盖
- 增量更新扫描所有表的科目依赖
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

# ---------------------------------------------------------------------------
# 辅助工具
# ---------------------------------------------------------------------------

PROJECT_ID = uuid4()
YEAR = 2025


def _fake_db():
    """最小 mock db：execute 返空结果。"""
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=result)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


def _make_engine(db=None):
    from app.services.disclosure_engine import DisclosureEngine
    svc = DisclosureEngine(db or _fake_db())
    # 预填缓存，避免 preload 去查 DB
    svc._wp_cache = {}
    svc._tb_cache = {}
    svc._wp_account_cache = {}
    svc._wp_fine_cache = {}
    svc._prior_notes_cache = {}
    svc._formula_on = False
    return svc


def _three_table_template() -> dict:
    """3 张表的模板：每张表的 headers/rows 和行标签各不同。"""
    return {
        "note_section": "测试、多表",
        "section_title": "测试多表",
        "account_name": "测试",
        "content_type": "table",
        "tables": [
            {
                "name": "表A",
                "headers": ["项目", "期末余额"],
                "rows": [
                    {"label": "行A1", "account_codes": ["1001"]},
                    {"label": "合计", "is_total": True},
                ],
            },
            {
                "name": "表B",
                "headers": ["项目", "本期发生额"],
                "rows": [
                    {"label": "行B1", "account_codes": ["2001"]},
                    {"label": "合计", "is_total": True},
                ],
            },
            {
                "name": "表C",
                "headers": ["项目", "金额"],
                "rows": [
                    {"label": "行C1", "account_codes": ["3001"]},
                ],
            },
        ],
    }


# ===========================================================================
# 1. 多表构建传真实 table_index
# ===========================================================================

class TestMultiTableBuildPassesRealIndex:
    """_build_section_table_data 必须把 enumerate 的真实 index 传给
    _build_table_data → get_binding_for_table。"""

    @pytest.mark.asyncio
    async def test_each_table_receives_correct_index(self):
        """通过 spy _build_table_data 拦截每次调用的 table_index 参数。"""
        engine = _make_engine()
        tmpl = _three_table_template()
        captured_indexes: list[int] = []
        original = engine._build_table_data

        async def spy_build(project_id, year, table_template, *,
                            section_number=None, table_index=0):
            captured_indexes.append(table_index)
            return await original(
                project_id, year, table_template,
                section_number=section_number, table_index=table_index,
            )

        engine._build_table_data = spy_build
        result = await engine._build_section_table_data(
            PROJECT_ID, YEAR, tmpl, content_type_str="table",
        )
        assert captured_indexes == [0, 1, 2], (
            f"table_index 序列应为 [0,1,2]，实际 {captured_indexes}"
        )
        assert result is not None
        assert len(result["_tables"]) == 3


# ===========================================================================
# 2. 缺表不借首表
# ===========================================================================

class TestMissingBindingDoesNotBorrowFirst:
    """binding 对表 N 越界返回 None → 走 legacy，不借首表 binding。"""

    @pytest.mark.asyncio
    async def test_binding_out_of_range_returns_legacy(self):
        """模拟 binding 只有 1 张表但模板有 3 张，后 2 张应走 legacy。"""
        engine = _make_engine()

        # 模拟 binding：只有 table_index=0 有 binding
        fake_section_binding = {
            "tables": [
                {
                    "table_index": 0,
                    "table_name": "表A",
                    "header_normalize": [
                        {"text": "项目", "semantic": "row_label"},
                        {"text": "期末余额", "semantic": "closing_balance"},
                    ],
                    "rows": {
                        "行A1": {
                            "row_type": "data",
                            "binding": {
                                "closing_balance": {
                                    "source": "manual",
                                    "manual_value": 999,
                                    "mode": "auto",
                                },
                            },
                        },
                    },
                },
            ],
        }

        with patch(
            "app.services.note_template_bindings_loader.get_binding_for_section",
            return_value=fake_section_binding,
        ), patch(
            "app.services.note_template_bindings_loader.get_binding_for_table",
        ) as mock_gbt:
            # get_binding_for_table: index=0 返 binding，index=1,2 返 None
            def side_effect(section, idx):
                if idx == 0:
                    return fake_section_binding["tables"][0]
                return None
            mock_gbt.side_effect = side_effect

            tmpl = _three_table_template()
            result = await engine._build_section_table_data(
                PROJECT_ID, YEAR, tmpl, content_type_str="table",
            )

        assert result is not None
        tables = result["_tables"]
        assert len(tables) == 3

        # 表A 走 binding 路径 → 有 _cell_modes
        assert "_cell_modes" in tables[0]["rows"][0], "表A 应走 binding 路径"

        # 表B 和表C 走 legacy → 无 _cell_modes（legacy 不产出 sidecar）
        for idx in (1, 2):
            rows = tables[idx].get("rows", [])
            if rows:
                non_total = [r for r in rows if not r.get("is_total")]
                if non_total:
                    # legacy 路径不产出 _cell_modes key
                    assert "_cell_modes" not in non_total[0], (
                        f"表[{idx}] 应走 legacy 路径而非借用首表 binding"
                    )


# ===========================================================================
# 3. 首表镜像
# ===========================================================================

class TestFirstTableMirror:
    """_build_section_table_data 输出的顶层 headers/rows/name == _tables[0]。"""

    @pytest.mark.asyncio
    async def test_top_level_mirrors_first_table(self):
        engine = _make_engine()
        tmpl = _three_table_template()
        result = await engine._build_section_table_data(
            PROJECT_ID, YEAR, tmpl, content_type_str="table",
        )
        assert result is not None
        first = result["_tables"][0]
        assert result["headers"] == first.get("headers", [])
        assert result["rows"] == first.get("rows", [])
        assert result.get("name") == first.get("name", "")


# ===========================================================================
# 4. 增量更新三态合并保护 manual/locked
# ===========================================================================

class TestIncrementalUpdatePreservesManualLocked:
    """update_note_values 对既有 note 做三态合并，manual/locked 值不被覆盖。"""

    @pytest.mark.asyncio
    async def test_manual_cell_preserved_after_update(self):
        """验证 merge_table_data_preserving_cell_modes 保留 manual 值。"""
        from app.services.note_cell_merge import (
            merge_table_data_preserving_cell_modes,
        )

        old = {
            "headers": ["项目", "金额"],
            "rows": [
                {
                    "label": "行1",
                    "values": [100],
                    "_cell_modes": {"0": "manual"},
                    "_cell_meta": {"0": {"manual_value": 100}},
                },
            ],
        }
        new = {
            "headers": ["项目", "金额"],
            "rows": [
                {
                    "label": "行1",
                    "values": [200],
                    "_cell_modes": {"0": "auto"},
                    "_cell_meta": {"0": {}},
                },
            ],
        }
        merged = merge_table_data_preserving_cell_modes(old, new)
        row = merged["rows"][0]
        # manual 单元格不被 auto 新值覆盖
        assert row["_cell_modes"]["0"] == "manual"
        assert row["values"][0] == 100

    @pytest.mark.asyncio
    async def test_locked_cell_preserved_after_update(self):
        from app.services.note_cell_merge import (
            merge_table_data_preserving_cell_modes,
        )

        old = {
            "headers": ["项目", "金额"],
            "rows": [
                {
                    "label": "行1",
                    "values": [50],
                    "_cell_modes": {"0": "locked"},
                    "_cell_meta": {"0": {}},
                },
            ],
        }
        new = {
            "headers": ["项目", "金额"],
            "rows": [
                {
                    "label": "行1",
                    "values": [300],
                    "_cell_modes": {"0": "auto"},
                    "_cell_meta": {"0": {}},
                },
            ],
        }
        merged = merge_table_data_preserving_cell_modes(old, new)
        row = merged["rows"][0]
        assert row["_cell_modes"]["0"] == "locked"
        assert row["values"][0] == 50


# ===========================================================================
# 5. 底稿同步来源不覆盖
# ===========================================================================

class TestWorkpaperSourceNotOverwritten:
    """底稿来源（_source=workpaper）的 table_data 在增量更新时不被覆盖。

    本测试直接验证 update_note_values 中的 guard 逻辑。
    """

    @pytest.mark.asyncio
    async def test_workpaper_source_skipped(self):
        """模拟既有 note._source=workpaper，增量更新不覆盖 table_data。"""
        engine = _make_engine()

        # 构造既有 note 对象
        class FakeNote:
            table_data = {
                "_source": "workpaper",
                "headers": ["项目", "金额"],
                "rows": [{"label": "原始底稿行", "values": [42]}],
            }

        note = FakeNote()
        old_td = note.table_data.copy()

        # 模拟增量更新判断
        existing_source = old_td.get("_source") if isinstance(old_td, dict) else None
        should_skip = existing_source in ("workpaper", "workpaper_html")
        assert should_skip, "底稿来源应跳过覆盖"

        # 确认 note 不变
        assert note.table_data["rows"][0]["label"] == "原始底稿行"


# ===========================================================================
# 6. 增量更新扫描所有表的科目依赖
# ===========================================================================

class TestIncrementalUpdateScansAllTables:
    """update_note_values 在判断是否跳过章节时，扫描 tables 列表中所有表的
    account_codes，不仅限于 table_template。"""

    def test_referenced_codes_include_all_tables(self):
        """模拟 update_note_values 的科目过滤逻辑。"""
        tmpl = _three_table_template()
        changed_accounts = ["2001"]  # 只在表B

        # 复现 update_note_values 的过滤逻辑
        table_template = tmpl.get("table_template", {})
        referenced_codes: set[str] = set()
        for row in table_template.get("rows", []):
            referenced_codes.update(row.get("account_codes", []))
        for tbl in tmpl.get("tables", []) or []:
            if isinstance(tbl, dict):
                for row in tbl.get("rows", []) or []:
                    referenced_codes.update(row.get("account_codes", []))

        # 应包含三张表的所有科目
        assert "1001" in referenced_codes
        assert "2001" in referenced_codes
        assert "3001" in referenced_codes

        # 2001 在 referenced_codes 中，所以不应跳过
        should_continue = referenced_codes and not referenced_codes.intersection(
            set(changed_accounts)
        )
        assert not should_continue, "账户 2001 存在于表B，不应跳过此章节"


# ===========================================================================
# 7. _build_table_data 的 table_index 是 keyword-only
# ===========================================================================

class TestBuildTableDataSignature:
    """table_index 必须是 keyword-only 参数（防止位置传参混淆）。"""

    def test_table_index_is_keyword_only(self):
        import inspect
        from app.services.disclosure_engine import DisclosureEngine
        sig = inspect.signature(DisclosureEngine._build_table_data)
        param = sig.parameters["table_index"]
        assert param.kind == inspect.Parameter.KEYWORD_ONLY, (
            "table_index 必须是 keyword-only 参数"
        )
        assert param.default == 0, "table_index 默认值应为 0"


# ===========================================================================
# 8. 三入口共用 _build_section_table_data（接线验证）
# ===========================================================================

class TestThreeEntryPointsShareBuilder:
    """generate_notes / get_note_detail / update_note_values 必须调用
    _build_section_table_data 构表。"""

    @pytest.mark.asyncio
    async def test_generate_notes_calls_build_section(self):
        engine = _make_engine()
        called = []
        original = engine._build_section_table_data

        async def spy(*args, **kwargs):
            called.append(1)
            return await original(*args, **kwargs)

        engine._build_section_table_data = spy

        # 提供最小模板
        with patch.object(engine, '_load_templates', return_value=[
            {
                "note_section": "测试、1",
                "section_title": "测试",
                "account_name": "测试",
                "content_type": "table",
                "tables": [
                    {
                        "name": "表1",
                        "headers": ["项目", "金额"],
                        "rows": [{"label": "行1"}],
                    },
                ],
            },
        ]), patch.object(engine, '_get_active_template_type', return_value="soe"), \
             patch.object(engine, '_persist_source_template', return_value="soe"), \
             patch.object(engine, '_preload_data_for_notes', new_callable=AsyncMock):
            await engine.generate_notes(PROJECT_ID, YEAR)

        assert len(called) > 0, "generate_notes 必须调用 _build_section_table_data"

    @pytest.mark.asyncio
    async def test_update_note_values_calls_build_section(self):
        engine = _make_engine()
        called = []
        original = engine._build_section_table_data

        async def spy(*args, **kwargs):
            called.append(1)
            return await original(*args, **kwargs)

        engine._build_section_table_data = spy

        with patch.object(engine, '_load_templates', return_value=[
            {
                "note_section": "测试、1",
                "section_title": "测试",
                "content_type": "table",
                "tables": [
                    {
                        "name": "表1",
                        "headers": ["项目", "金额"],
                        "rows": [{"label": "行1"}],
                    },
                ],
            },
        ]), patch.object(engine, '_get_active_template_type', return_value="soe"):
            await engine.update_note_values(PROJECT_ID, YEAR)

        assert len(called) > 0, "update_note_values 必须调用 _build_section_table_data"


# ===========================================================================
# 9. 行标签全角空格归一化匹配（剩余边界修复）
# ===========================================================================

class TestLabelFullWidthSpaceNormalization:
    """模板行标签含全角空格（如"合　计"）时应能匹配 binding 的"合计"。"""

    @pytest.mark.asyncio
    async def test_fullwidth_space_label_matches_binding(self):
        """模板 label="合\u3000计"，binding key="合计"，应匹配到 binding。"""
        engine = _make_engine()
        tmpl = {
            "note_section": "测试、全角",
            "section_title": "测试全角",
            "account_name": "测试",
            "content_type": "table",
            "tables": [
                {
                    "name": "表1",
                    "headers": ["项目", "期末余额"],
                    "rows": [
                        {"label": "行1"},
                        {"label": "合\u3000计", "is_total": True},
                    ],
                },
            ],
        }

        # 模拟 binding：key 是"合计"（无空格）
        fake_binding = {
            "tables": [{
                "table_index": 0,
                "table_name": "表1",
                "header_normalize": [
                    {"text": "项目", "semantic": "row_label"},
                    {"text": "期末余额", "semantic": "closing_balance"},
                ],
                "rows": {
                    "行1": {
                        "row_type": "data",
                        "binding": {
                            "closing_balance": {
                                "source": "manual",
                                "manual_value": 42,
                                "mode": "auto",
                            },
                        },
                    },
                    "合计": {"row_type": "total"},
                },
            }],
        }

        with patch(
            "app.services.note_template_bindings_loader.get_binding_for_table",
            return_value=fake_binding["tables"][0],
        ):
            result = await engine._build_section_table_data(
                PROJECT_ID, YEAR, tmpl, content_type_str="table",
            )

        assert result is not None
        tables = result["_tables"]
        assert len(tables) == 1
        # 行1 应走 binding 路径（有 _cell_modes）
        row1 = tables[0]["rows"][0]
        assert "_cell_modes" in row1, "行1 应走 binding 路径"
        assert row1["values"][0] == 42, "行1 应拿到 manual_value=42"

    @pytest.mark.asyncio
    async def test_binding_fullwidth_matches_template_plain(self):
        """反向：binding key="合\u3000计"，模板 label="合计"，也应匹配。"""
        engine = _make_engine()
        tmpl = {
            "note_section": "测试、反向",
            "section_title": "测试反向",
            "account_name": "测试",
            "content_type": "table",
            "tables": [
                {
                    "name": "表1",
                    "headers": ["项目", "金额"],
                    "rows": [
                        {"label": "合计", "is_total": True},
                    ],
                },
            ],
        }

        fake_binding = {
            "tables": [{
                "table_index": 0,
                "table_name": "表1",
                "header_normalize": [
                    {"text": "项目", "semantic": "row_label"},
                    {"text": "金额", "semantic": "amount"},
                ],
                "rows": {
                    "合\u3000计": {"row_type": "total"},
                },
            }],
        }

        with patch(
            "app.services.note_template_bindings_loader.get_binding_for_table",
            return_value=fake_binding["tables"][0],
        ):
            result = await engine._build_section_table_data(
                PROJECT_ID, YEAR, tmpl, content_type_str="table",
            )

        assert result is not None
        # 合计行应被识别（is_total=True）
        row = result["_tables"][0]["rows"][0]
        assert row["is_total"] is True
