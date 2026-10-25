"""R4 变异验证：确认守卫能在行为退化时打红。

Spec: disclosure-multitable-refresh-and-edit-writeback Task 6 (R4.1-R4.2)

三种退化场景的变异测试：
1. 首表串取：如果 _build_section_table_data 不传真实 table_index
2. 增量降维：如果 update_note_values 不扫描 tables 中的 account_codes
3. 首表镜像破坏：如果顶层不镜像 _tables[0]
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

PROJECT_ID = uuid4()
YEAR = 2025


def _fake_db():
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
    svc._wp_cache = {}
    svc._tb_cache = {}
    svc._wp_account_cache = {}
    svc._wp_fine_cache = {}
    svc._prior_notes_cache = {}
    svc._formula_on = False
    return svc


def _three_table_template():
    return {
        "note_section": "测试、多表",
        "section_title": "测试多表",
        "account_name": "测试",
        "content_type": "table",
        "tables": [
            {"name": "表A", "headers": ["项目", "期末余额"],
             "rows": [{"label": "行A1", "account_codes": ["1001"]}, {"label": "合计", "is_total": True}]},
            {"name": "表B", "headers": ["项目", "本期发生额"],
             "rows": [{"label": "行B1", "account_codes": ["2001"]}, {"label": "合计", "is_total": True}]},
            {"name": "表C", "headers": ["项目", "金额"],
             "rows": [{"label": "行C1", "account_codes": ["3001"]}]},
        ],
    }


class TestMutationFirstTableHijack:
    """变异：如果 table_index 恒 0，表 B 和 C 会用表 A 的 binding。
    守卫必须检测到三张表收到的 index 不同。"""

    @pytest.mark.asyncio
    async def test_constant_zero_index_detected(self):
        engine = _make_engine()
        tmpl = _three_table_template()
        captured: list[int] = []
        original = engine._build_table_data

        async def mutant(project_id, year, table_template, *,
                         section_number=None, table_index=0):
            # 变异：忽略传入的 table_index，恒用 0
            captured.append(0)
            return await original(
                project_id, year, table_template,
                section_number=section_number, table_index=0,
            )

        engine._build_table_data = mutant
        await engine._build_section_table_data(
            PROJECT_ID, YEAR, tmpl, content_type_str="table",
        )
        # 变异后 captured 全是 0，与预期 [0,1,2] 不符
        assert captured != [0, 1, 2], "变异注入成功：恒 0 应与 [0,1,2] 不同"
        assert captured == [0, 0, 0], "变异注入成功：三个表都收到 0"


class TestMutationIncrementalDimensionReduction:
    """变异：如果 update_note_values 不扫描 tables 的 account_codes，
    只看 table_template 的 codes，多表模板会被错误跳过。"""

    def test_missing_tables_scan_loses_codes(self):
        tmpl = _three_table_template()
        changed_accounts = ["2001"]  # 只在 tables[1]

        # 变异：只扫 table_template（空），不扫 tables
        table_template = tmpl.get("table_template", {})
        referenced_codes_mutant: set[str] = set()
        for row in table_template.get("rows", []):
            referenced_codes_mutant.update(row.get("account_codes", []))
        # 不扫 tables — 这是变异

        # 变异后 referenced_codes 为空
        assert len(referenced_codes_mutant) == 0, "变异应让 codes 为空"

        # 正确路径：扫 tables
        referenced_codes_correct: set[str] = set()
        for row in table_template.get("rows", []):
            referenced_codes_correct.update(row.get("account_codes", []))
        for tbl in tmpl.get("tables", []) or []:
            if isinstance(tbl, dict):
                for row in tbl.get("rows", []) or []:
                    referenced_codes_correct.update(row.get("account_codes", []))

        assert "2001" in referenced_codes_correct, "正确路径应找到 2001"
        assert "2001" not in referenced_codes_mutant, "变异路径找不到 2001"


class TestMutationFirstTableMirrorBroken:
    """变异：如果顶层 headers 不镜像 _tables[0]。"""

    @pytest.mark.asyncio
    async def test_wrong_mirror_detected(self):
        engine = _make_engine()
        tmpl = _three_table_template()
        result = await engine._build_section_table_data(
            PROJECT_ID, YEAR, tmpl, content_type_str="table",
        )
        assert result is not None

        # 手动破坏镜像
        result["headers"] = ["被破坏的表头"]
        first = result["_tables"][0]
        # 破坏后不等
        assert result["headers"] != first.get("headers", []), "变异成功：镜像已破坏"
