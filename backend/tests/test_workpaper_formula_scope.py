"""Task 17b: 公式管理覆盖底稿数据源（§九 P1-7 补全）

验证:
1. FormulaManagerScope 含 'workpaper' scope + SCOPE_LABEL_MAP 含中文 label '底稿'
2. cell_formula_evaluator 处理 Excel Cell 语法（=A1+B2），非报表 DSL
3. 底稿公式变更走哈希链 formula.changed 留痕（module='workpaper'）
4. formula_audit_log GET 端点支持 module='workpaper' 过滤

需求: 8.1, 8.2, 8.3, 8.4
属性: Q5
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base

# SQLite 兼容 JSONB + ARRAY
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

import app.models.core  # noqa: F401
import app.models.audit_log_models  # noqa: F401

from app.models.audit_log_models import AuditLogEntry

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """每个测试独立的内存数据库会话。"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        tables_to_create = [
            Base.metadata.tables["users"],
            Base.metadata.tables["audit_log_entries"],
        ]
        await conn.run_sync(Base.metadata.create_all, tables=tables_to_create)
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


# --------------------------------------------------------------------------
# 1. FormulaManagerScope 含 'workpaper' + SCOPE_LABEL_MAP 含 '底稿'
# --------------------------------------------------------------------------


class TestWorkpaperScopeDefinition:
    """验证前端 FormulaManagerScope 类型定义包含 workpaper scope。"""

    def test_scope_type_includes_workpaper(self):
        """FormulaManagerScope 类型联合体含 'workpaper'。

        由于 TypeScript 类型在运行时不可直接验证，
        我们通过读取源文件确认类型定义包含 'workpaper'。
        """
        from pathlib import Path

        vue_file = (
            Path(__file__).resolve().parents[2]
            / "audit-platform"
            / "frontend"
            / "src"
            / "components"
            / "formula"
            / "FormulaManagerDialog.vue"
        )
        assert vue_file.exists(), f"FormulaManagerDialog.vue 不存在: {vue_file}"
        content = vue_file.read_text(encoding="utf-8")

        # 验证 FormulaManagerScope 类型定义包含 'workpaper'
        assert "type FormulaManagerScope" in content
        assert "'workpaper'" in content

    def test_scope_label_map_has_workpaper_chinese_label(self):
        """SCOPE_LABEL_MAP 含 workpaper: '底稿' 中文标签。"""
        from pathlib import Path

        vue_file = (
            Path(__file__).resolve().parents[2]
            / "audit-platform"
            / "frontend"
            / "src"
            / "components"
            / "formula"
            / "FormulaManagerDialog.vue"
        )
        content = vue_file.read_text(encoding="utf-8")

        # 验证 SCOPE_LABEL_MAP 包含 workpaper 的中文标签
        assert "SCOPE_LABEL_MAP" in content
        assert "workpaper: '底稿'" in content


# --------------------------------------------------------------------------
# 2. cell_formula_evaluator 处理 Excel Cell 语法
# --------------------------------------------------------------------------


class TestCellFormulaEvaluatorDomain:
    """验证 cell_formula_evaluator 是 Excel Cell 语法域（非报表 DSL）。"""

    def test_module_docstring_declares_excel_syntax(self):
        """cell_formula_evaluator 文件头声明处理 Excel 公式。"""
        import app.services.cell_formula_evaluator as cfe

        doc = cfe.__doc__ or ""
        assert "Excel" in doc
        assert "底稿" in doc or "workpaper" in doc.lower()
        assert "非报表 DSL" in doc

    def test_parse_formula_handles_cell_references(self):
        """parse_formula 能解析 Excel 单元格引用（=A1+B2 风格）。"""
        from app.services.cell_formula_evaluator import parse_formula

        result = parse_formula("=B3+C3")
        assert result is not None
        # 解析结果应包含 cell 引用信息
        assert "type" in result or "tokens" in result or "refs" in result or "formula_type" in result

    def test_validate_formula_checks_cell_bounds(self):
        """validate_formula 校验行列边界（Excel 语法域特征）。"""
        from app.services.cell_formula_evaluator import validate_formula

        # 合法公式
        valid = validate_formula("=B3+C3", max_row=10, max_col=10)
        assert valid.get("valid") is True or valid.get("errors") == [] or not valid.get("errors")

        # 超出边界
        invalid = validate_formula("=ZZ999", max_row=5, max_col=5)
        # 应有错误或标记无效
        assert invalid.get("valid") is False or invalid.get("errors")


# --------------------------------------------------------------------------
# 3. 底稿公式变更走哈希链 formula.changed 留痕
# --------------------------------------------------------------------------


class TestWorkpaperAuditTrail:
    """验证底稿公式变更通过 append_audit_log 写入哈希链。"""

    def test_event_type_schema_includes_formula_changed(self):
        """EVENT_TYPE_SCHEMAS 含 formula_changed schema。"""
        from app.services.audit_log_helper import EVENT_TYPE_SCHEMAS

        assert "formula_changed" in EVENT_TYPE_SCHEMAS
        schema = EVENT_TYPE_SCHEMAS["formula_changed"]
        # 必需字段
        assert "module" in schema
        assert "row_code" in schema
        assert "action" in schema
        assert "old_formula" in schema
        assert "new_formula" in schema
        assert "result_value" in schema

    def test_wp_user_formulas_has_audit_trail_code(self):
        """wp_user_formulas 路由包含 formula.changed 审计留痕代码。"""
        from pathlib import Path

        router_file = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "routers"
            / "wp_user_formulas.py"
        )
        content = router_file.read_text(encoding="utf-8")

        # 验证审计留痕关键代码存在
        assert "formula.changed" in content
        assert "module" in content and "workpaper" in content
        assert "append_audit_log" in content

    @pytest.mark.asyncio
    async def test_workpaper_audit_entry_queryable(self, db_session: AsyncSession):
        """module='workpaper' 的 formula.changed 条目可通过 GET 端点查询。"""
        pid = str(uuid.uuid4())

        # 插入一条 workpaper 模块的 formula.changed 条目
        entry = AuditLogEntry(
            id=uuid.uuid4(),
            ts=datetime.now(timezone.utc),
            user_id=uuid.uuid4(),
            session_id=None,
            action_type="formula.changed",
            object_type="workpaper",
            object_id=None,
            payload={
                "project_id": pid,
                "event_type": "formula_changed",
                "module": "workpaper",
                "row_code": "现金明细表E1-2!B15",
                "action": "update",
                "old_formula": "=TB('1001','期末余额')",
                "new_formula": "=TB('1001','审定数')",
                "result_value": "50000.00",
            },
            ip=None,
            ua=None,
            trace_id=None,
            prev_hash="0" * 64,
            entry_hash=uuid.uuid4().hex + uuid.uuid4().hex[:32],
        )
        db_session.add(entry)
        await db_session.commit()

        # 通过 GET 端点查询
        from app.routers.formula_audit_log import get_audit_log

        result = await get_audit_log(pid, 2025, module="workpaper", db=db_session)
        assert len(result) == 1
        assert result[0]["module"] == "workpaper"
        assert result[0]["row_code"] == "现金明细表E1-2!B15"
        assert result[0]["action"] == "update"
        assert result[0]["old_formula"] == "=TB('1001','期末余额')"
        assert result[0]["new_formula"] == "=TB('1001','审定数')"

    @pytest.mark.asyncio
    async def test_workpaper_entries_excluded_when_filtering_other_module(
        self, db_session: AsyncSession
    ):
        """module='report' 过滤时不返回 workpaper 条目。"""
        pid = str(uuid.uuid4())

        # 插入 workpaper 条目
        entry_wp = AuditLogEntry(
            id=uuid.uuid4(),
            ts=datetime.now(timezone.utc),
            user_id=uuid.uuid4(),
            session_id=None,
            action_type="formula.changed",
            object_type="workpaper",
            object_id=None,
            payload={
                "project_id": pid,
                "event_type": "formula_changed",
                "module": "workpaper",
                "row_code": "Sheet1!A1",
                "action": "update",
                "old_formula": "",
                "new_formula": "=TB('1001','期末余额')",
                "result_value": "",
            },
            ip=None,
            ua=None,
            trace_id=None,
            prev_hash="0" * 64,
            entry_hash=uuid.uuid4().hex + uuid.uuid4().hex[:32],
        )
        # 插入 report 条目
        entry_rpt = AuditLogEntry(
            id=uuid.uuid4(),
            ts=datetime.now(timezone.utc),
            user_id=uuid.uuid4(),
            session_id=None,
            action_type="formula.changed",
            object_type="report_config",
            object_id=None,
            payload={
                "project_id": pid,
                "event_type": "formula_changed",
                "module": "report",
                "row_code": "BS-001",
                "action": "execute",
                "old_formula": "TB('1002','期末余额')",
                "new_formula": "TB('1002','期末余额')+TB('1003','期末余额')",
                "result_value": "1500.00",
            },
            ip=None,
            ua=None,
            trace_id=None,
            prev_hash="0" * 64,
            entry_hash=uuid.uuid4().hex + uuid.uuid4().hex[:32],
        )
        db_session.add(entry_wp)
        db_session.add(entry_rpt)
        await db_session.commit()

        from app.routers.formula_audit_log import get_audit_log

        # 过滤 report 模块
        result = await get_audit_log(pid, 2025, module="report", db=db_session)
        assert len(result) == 1
        assert result[0]["module"] == "report"

        # 过滤 workpaper 模块
        result = await get_audit_log(pid, 2025, module="workpaper", db=db_session)
        assert len(result) == 1
        assert result[0]["module"] == "workpaper"
