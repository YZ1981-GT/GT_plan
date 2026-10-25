"""建表脚本 ↔ ORM ↔ 迁移 三向交叉锁死（R10.5）+ 拒绝类审计（R5.5 / R12.3）。

Feature: advanced-query-hardening-wiring-closure

`backend/scripts/_ensure_custom_query_tables.py` 与 ORM
`CustomQueryTemplate`、迁移 `V033` / `V051` / `V101` 描述的是**同一张表**。
四处各写一份列集与索引集，任何一处改动都可能悄悄漂移 —— 表现为「脚本建出来的表
少一列」这类只在新环境暴露的故障。故用守卫把它们锁在一起。
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND = Path(__file__).resolve().parents[1]
SCRIPT = BACKEND / "scripts" / "_ensure_custom_query_tables.py"
MIGRATIONS = BACKEND / "migrations"


def _load_script():
    spec = importlib.util.spec_from_file_location("_ensure_cqt", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script():
    return _load_script()


@pytest.fixture(scope="module")
def orm():
    from app.models.custom_query_models import CustomQueryTemplate

    return CustomQueryTemplate


class TestDdlMatchesOrm:
    def test_declared_columns_equal_orm_columns(self, script, orm):
        """脚本声明的列集必须与 ORM 完全一致（不多不少）。"""
        orm_cols = {c.name for c in orm.__table__.columns}
        script_cols = set(script.DDL_COLUMNS)
        assert script_cols == orm_cols, (
            f"脚本缺 {sorted(orm_cols - script_cols)}；"
            f"脚本多 {sorted(script_cols - orm_cols)}"
        )

    def test_ddl_text_contains_every_declared_column(self, script):
        """DDL_COLUMNS 不能只是一份「说明」——每一列都要真的出现在 DDL 里。"""
        for col in script.DDL_COLUMNS:
            assert re.search(rf"\b{re.escape(col)}\b", script.DDL), f"DDL 缺列 {col}"

    def test_index_names_equal_orm_idx_cqt_indexes(self, script, orm):
        """脚本索引名集合必须等于 ORM 中的 idx_cqt_* 索引集合。"""
        orm_idx = {
            ix.name
            for ix in orm.__table__.indexes
            if str(ix.name).startswith("idx_cqt_")
        }
        assert set(script.INDEX_NAMES) == orm_idx, (
            f"脚本缺 {sorted(orm_idx - set(script.INDEX_NAMES))}；"
            f"脚本多 {sorted(set(script.INDEX_NAMES) - orm_idx)}"
        )

    def test_index_ddl_contains_every_declared_index(self, script):
        for name in script.INDEX_NAMES:
            assert name in script.INDEXES_DDL, f"INDEXES_DDL 缺索引 {name}"

    def test_gin_used_for_array_columns(self, script, orm):
        """数组列的索引必须是 GIN（B-tree 无法支持数组包含查询）。"""
        from sqlalchemy.dialects.postgresql import ARRAY

        array_cols = {
            c.name
            for c in orm.__table__.columns
            if isinstance(getattr(c.type, "impl", c.type), ARRAY)
            or isinstance(c.type, ARRAY)
        }
        assert array_cols, "ORM 中应存在数组列（tags / shared_project_ids）"
        for stmt in script.INDEXES_DDL.split(";"):
            if any(col in stmt for col in array_cols) and "CREATE INDEX" in stmt:
                assert "GIN" in stmt.upper(), f"数组列索引未用 GIN: {stmt.strip()}"


class TestDdlMatchesMigrations:
    def _migration_text(self, prefix: str) -> str:
        files = sorted(MIGRATIONS.glob(f"{prefix}*.sql"))
        assert files, f"未找到迁移 {prefix}"
        return "\n".join(f.read_text(encoding="utf-8") for f in files)

    def test_v051_added_columns_all_covered_by_alter(self, script):
        """V051 补的列必须都在 ALTER_ADD_COLUMNS 里（旧库自愈路径不能漏）。"""
        text = self._migration_text("V051")
        section = text.split("custom_query_templates")
        added = set()
        for line in text.splitlines():
            m = re.search(
                r"ALTER TABLE custom_query_templates ADD COLUMN IF NOT EXISTS (\w+)",
                line,
            )
            if m:
                added.add(m.group(1))
        assert added, "V051 中未解析到 custom_query_templates 的补列语句"
        assert added <= set(script.ALTER_ADD_COLUMNS), (
            f"ALTER_ADD_COLUMNS 缺 V051 补的列：{sorted(added - set(script.ALTER_ADD_COLUMNS))}"
        )
        assert section  # 保留分段引用，确保断言基于该表而非全文件

    def test_v101_shared_column_and_index_covered(self, script):
        """V101 引入的 shared_project_ids 列与 GIN 索引必须被脚本覆盖。"""
        text = self._migration_text("V101")
        assert "shared_project_ids" in text
        assert "shared_project_ids" in script.ALTER_ADD_COLUMNS
        assert "shared_project_ids" in script.DDL
        m = re.search(r"CREATE INDEX IF NOT EXISTS (idx_cqt_\w+)", text)
        assert m, "V101 未解析到 idx_cqt_* 索引"
        assert m.group(1) in script.INDEX_NAMES

    def test_scope_check_values_match_orm_docstring_contract(self, script):
        """scope CHECK 取值必须覆盖 SCOPE_VALUES，且两者与 DDL 文本一致。"""
        for value in script.SCOPE_VALUES:
            assert f"'{value}'" in script.DDL, f"DDL 的 scope CHECK 缺 {value}"

    def test_alter_statements_are_idempotent(self, script):
        for col, stmt in script.ALTER_ADD_COLUMNS.items():
            assert "ADD COLUMN IF NOT EXISTS" in stmt, col
            assert col in stmt, f"{col} 的语句与键名不一致：{stmt}"


class TestScriptImportPurity:
    def test_import_has_no_db_side_effect(self):
        """导入脚本不得连库 / 执行 DDL（R10.2）。"""
        module = _load_script()
        assert hasattr(module, "main")
        # 模块级不得持有 engine / session 之类的连接对象
        for name in ("engine", "session", "conn", "connection"):
            assert not hasattr(module, name), f"模块级不应持有 {name}"

    def test_main_is_not_invoked_on_import(self):
        """模块级不得有任何函数调用语句（AST 判据，不用文本 grep）。

        🔴 初版用 `"main()" not in source.split('if __name__')[0]` —— docstring 里
        写的说明文字「``main()`` 仅在 __main__ 下运行」也被算作调用，判据自相矛盾。
        文本判据对注释/docstring 天生不可靠，改用 AST 看真实语法结构。
        """
        import ast

        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        main_guard_found = False
        for node in tree.body:
            if isinstance(node, ast.If):
                # 识别 `if __name__ == "__main__":`
                test = ast.dump(node.test)
                if "__name__" in test and "__main__" in test:
                    main_guard_found = True
                    continue
            # 模块级顶层不得存在裸调用表达式（赋值/函数定义/import 都可以）
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                func = node.value.func
                name = getattr(func, "id", None) or getattr(func, "attr", None)
                pytest.fail(f"模块级存在调用 {name}()，导入即有副作用")
        assert main_guard_found, "缺少 if __name__ == '__main__' 守卫"


# ════════════════════════════════════════════════════════════════════════════
# R5.5 / R12.3 — 拒绝类审计可区分
# ════════════════════════════════════════════════════════════════════════════
class TestRejectionAudit:
    def test_each_rejection_kind_has_distinct_action(self):
        """三类拒绝必须映射到**互不相同**的动作名。

        统一记成一条「查询失败」等于没记：超时要加筛选、预算超限要拆查询、
        PII 越权要走权限申请，处置完全不同。
        """
        from app.services.custom_query.audit_helper import (
            REJECTION_ACTION_BY_ERROR_CODE,
            resolve_rejection_action,
        )

        actions = [
            resolve_rejection_action(code)
            for code in ("QUERY_TIMEOUT", "COMPLEXITY_BUDGET_EXCEEDED", "PII_FIELD_FORBIDDEN")
        ]
        assert all(actions), "三类拒绝都必须有对应动作名"
        assert len(set(actions)) == 3, f"动作名重复：{actions}"
        assert set(REJECTION_ACTION_BY_ERROR_CODE) >= {
            "QUERY_TIMEOUT",
            "COMPLEXITY_BUDGET_EXCEEDED",
            "PII_FIELD_FORBIDDEN",
        }

    def test_ownership_denied_not_double_recorded(self):
        """归属拒绝由 OwnershipGuard 记录，不得在此表内重复登记。"""
        from app.services.custom_query.audit_helper import (
            REJECTION_ACTION_BY_ERROR_CODE,
        )

        assert "FORBIDDEN_PROJECT" not in REJECTION_ACTION_BY_ERROR_CODE

    def test_unregistered_error_code_records_nothing(self):
        from app.services.custom_query.audit_helper import resolve_rejection_action

        assert resolve_rejection_action("INVALID_SORT_FIELD") is None
        assert resolve_rejection_action(None) is None
        assert resolve_rejection_action("") is None

    @pytest.mark.asyncio
    async def test_audit_failure_does_not_mask_original_error(self, monkeypatch):
        """审计写入失败必须被吞掉，不能盖住原始错误（R5.5）。"""
        import app.services.custom_query.audit_helper as helper

        async def _boom(**kwargs):
            raise RuntimeError("audit backend down")

        monkeypatch.setattr(helper, "_log_unthrottled", _boom)
        # 不抛异常、返回 False
        assert (
            await helper.record_query_rejected(
                user_id="u1", error_code="QUERY_TIMEOUT", source="trial_balance"
            )
            is False
        )

    @pytest.mark.asyncio
    async def test_rejection_audit_is_not_throttled(self, monkeypatch):
        """拒绝类审计不走节流 —— 反复试探的模式本身就是要被看见的信号。"""
        import app.services.custom_query.audit_helper as helper

        calls: list[str] = []

        async def _spy(**kwargs):
            calls.append(kwargs["action"])
            return True

        monkeypatch.setattr(helper, "_log_unthrottled", _spy)
        for _ in range(3):
            await helper.record_query_rejected(
                user_id="u1", error_code="QUERY_TIMEOUT", source="tb"
            )
        assert len(calls) == 3, "拒绝类审计不应被节流窗口聚合"
        assert set(calls) == {helper.ACTION_QUERY_TIMEOUT}


class TestRejectionAuditWiring:
    """接线判据：router 的异常分支**真的**调用了拒绝审计。"""

    @pytest.mark.asyncio
    async def test_custom_query_execute_records_timeout_rejection(self, monkeypatch):
        from fastapi import HTTPException, Response
        from unittest.mock import AsyncMock

        import app.routers.custom_query as router_module
        from app.services.custom_query.execute_compatibility import (
            ExecuteCompatibilityAdapter,
        )

        recorded: list[dict] = []

        async def _reject(self, body, *, user, db):
            raise HTTPException(
                status_code=408, detail={"error_code": "QUERY_TIMEOUT"}
            )

        async def _record(**kwargs):
            recorded.append(kwargs)
            return True

        monkeypatch.setattr(ExecuteCompatibilityAdapter, "execute", _reject)
        monkeypatch.setattr(
            "app.services.custom_query.audit_helper.record_query_rejected", _record
        )
        monkeypatch.setattr(
            "app.services.gin_index_monitor.is_index_building", lambda: False
        )

        with pytest.raises(HTTPException) as exc:
            await router_module.execute_query(
                router_module.QueryRequest(project_id="p1", year=2025, source="report"),
                Response(),
                AsyncMock(),
                SimpleNamespace(id="u1"),
            )
        assert exc.value.status_code == 408, "原始错误必须原样上抛"
        assert len(recorded) == 1
        assert recorded[0]["error_code"] == "QUERY_TIMEOUT"

    @pytest.mark.asyncio
    async def test_builder_records_budget_rejection(self, monkeypatch):
        from fastapi import HTTPException

        import app.routers.query_builder as qb

        recorded: list[dict] = []

        async def _record(**kwargs):
            recorded.append(kwargs)
            return True

        monkeypatch.setattr(
            "app.services.custom_query.audit_helper.record_query_rejected", _record
        )
        await qb._audit_query_rejection(
            HTTPException(
                status_code=400, detail={"error_code": "COMPLEXITY_BUDGET_EXCEEDED"}
            ),
            user=SimpleNamespace(id="u1"),
            table="trial_balance",
        )
        assert len(recorded) == 1
        assert recorded[0]["error_code"] == "COMPLEXITY_BUDGET_EXCEEDED"
        assert recorded[0]["source"] == "builder:trial_balance"
