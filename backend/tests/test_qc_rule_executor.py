"""Tests for qc_rule_executor — Python + JSONPath + audit_log 执行器

Validates: Requirements 1, 12 (R3)
- Python 类型：加载 dotted path 类，沙箱 timeout=10s
- JSONPath 类型：只读 parsed_data，用 jsonpath-ng 库
- audit_log 类型：查询 audit_log_entries 表，JSONPath 过滤 payload
- SQL/Regex 类型：抛 NotImplementedError
"""

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.qc_rule_executor import (
    AuditLogContext,
    RuleExecutionResult,
    _load_class_from_dotted_path,
    execute_audit_log_rule,
    execute_jsonpath_rule,
    execute_python_rule,
    execute_rule,
)


# ---------------------------------------------------------------------------
# Helpers: 模拟 QcRuleDefinition
# ---------------------------------------------------------------------------


def _make_rule_def(
    rule_code: str = "QC-TEST-01",
    expression_type: str = "python",
    expression: str = "app.services.qc_engine.ConclusionNotEmptyRule",
    severity: str = "blocking",
    parameters_schema: dict | None = None,
) -> MagicMock:
    """创建模拟的 QcRuleDefinition 对象。"""
    rule = MagicMock()
    rule.rule_code = rule_code
    rule.expression_type = expression_type
    rule.expression = expression
    rule.severity = severity
    rule.parameters_schema = parameters_schema
    return rule


# ---------------------------------------------------------------------------
# Tests: _load_class_from_dotted_path
# ---------------------------------------------------------------------------


class TestLoadClassFromDottedPath:
    def test_load_existing_class(self):
        cls = _load_class_from_dotted_path(
            "app.services.qc_engine.ConclusionNotEmptyRule"
        )
        assert cls.__name__ == "ConclusionNotEmptyRule"

    def test_load_nonexistent_module(self):
        with pytest.raises(ImportError, match="not found"):
            _load_class_from_dotted_path("nonexistent.module.SomeClass")

    def test_load_nonexistent_class(self):
        with pytest.raises(ImportError, match="not found"):
            _load_class_from_dotted_path(
                "app.services.qc_engine.NonExistentClass"
            )

    def test_invalid_dotted_path(self):
        with pytest.raises(ImportError, match="Invalid dotted path"):
            _load_class_from_dotted_path("NoDotsHere")


# ---------------------------------------------------------------------------
# Tests: execute_python_rule
# ---------------------------------------------------------------------------


class TestExecutePythonRule:
    @pytest.mark.asyncio
    async def test_successful_execution_no_findings(self):
        """Python 规则执行成功，无 findings → passed=True"""
        rule_def = _make_rule_def(
            expression="app.services.qc_engine.ConclusionNotEmptyRule"
        )

        # 创建一个有结论的 mock context
        wp = MagicMock()
        wp.parsed_data = {"conclusion": "审计结论已填写"}
        context = MagicMock()
        context.working_paper = wp

        result = await execute_python_rule(rule_def, context)
        assert result.passed is True
        assert result.findings == []
        assert result.error is None

    @pytest.mark.asyncio
    async def test_successful_execution_with_findings(self):
        """Python 规则执行成功，有 findings → passed=False"""
        rule_def = _make_rule_def(
            expression="app.services.qc_engine.ConclusionNotEmptyRule"
        )

        # 创建一个无结论的 mock context
        wp = MagicMock()
        wp.parsed_data = {}
        context = MagicMock()
        context.working_paper = wp

        result = await execute_python_rule(rule_def, context)
        assert result.passed is False
        assert len(result.findings) > 0
        assert result.findings[0]["rule_id"] == "QC-01"

    @pytest.mark.asyncio
    async def test_timeout_enforcement(self):
        """Python 规则超时 → 返回 error"""
        rule_def = _make_rule_def(expression="app.services.qc_engine.ConclusionNotEmptyRule")

        # 创建一个会超时的 mock
        async def slow_check(ctx):
            await asyncio.sleep(5)
            return []

        with patch(
            "app.services.qc_rule_executor._load_class_from_dotted_path"
        ) as mock_load:
            mock_cls = MagicMock()
            mock_instance = MagicMock()
            mock_instance.check = slow_check
            mock_cls.return_value = mock_instance
            mock_load.return_value = mock_cls

            result = await execute_python_rule(rule_def, MagicMock(), timeout=0.1)
            assert result.passed is False
            assert "timed out" in result.error

    @pytest.mark.asyncio
    async def test_invalid_dotted_path(self):
        """无效的 dotted path → 返回 error"""
        rule_def = _make_rule_def(expression="nonexistent.module.FakeRule")

        result = await execute_python_rule(rule_def, MagicMock())
        assert result.passed is False
        assert "Failed to load rule class" in result.error

    @pytest.mark.asyncio
    async def test_rule_raises_exception(self):
        """规则 check() 抛异常 → 返回 error"""
        rule_def = _make_rule_def(expression="app.services.qc_engine.ConclusionNotEmptyRule")

        async def broken_check(ctx):
            raise RuntimeError("Something went wrong")

        with patch(
            "app.services.qc_rule_executor._load_class_from_dotted_path"
        ) as mock_load:
            mock_cls = MagicMock()
            mock_instance = MagicMock()
            mock_instance.check = broken_check
            mock_cls.return_value = mock_instance
            mock_load.return_value = mock_cls

            result = await execute_python_rule(rule_def, MagicMock())
            assert result.passed is False
            assert "Rule execution error" in result.error


# ---------------------------------------------------------------------------
# Tests: execute_jsonpath_rule
# ---------------------------------------------------------------------------


class TestExecuteJsonpathRule:
    @pytest.mark.asyncio
    async def test_match_found_expect_match_true(self):
        """JSONPath 匹配到数据 + expect_match=True → passed"""
        rule_def = _make_rule_def(
            expression_type="jsonpath",
            expression="$.conclusion",
            parameters_schema={"expect_match": True},
        )
        parsed_data = {"conclusion": "审计结论"}

        result = await execute_jsonpath_rule(rule_def, parsed_data)
        assert result.passed is True
        assert result.findings == []

    @pytest.mark.asyncio
    async def test_no_match_expect_match_true(self):
        """JSONPath 未匹配 + expect_match=True → finding"""
        rule_def = _make_rule_def(
            expression_type="jsonpath",
            expression="$.conclusion",
            parameters_schema={"expect_match": True},
        )
        parsed_data = {"other_field": "value"}

        result = await execute_jsonpath_rule(rule_def, parsed_data)
        assert result.passed is False
        assert len(result.findings) == 1
        assert "未匹配到数据" in result.findings[0]["message"]

    @pytest.mark.asyncio
    async def test_match_found_expect_match_false(self):
        """JSONPath 匹配到数据 + expect_match=False → finding"""
        rule_def = _make_rule_def(
            expression_type="jsonpath",
            expression="$.bad_field",
            severity="warning",
            parameters_schema={"expect_match": False},
        )
        parsed_data = {"bad_field": "should not exist"}

        result = await execute_jsonpath_rule(rule_def, parsed_data)
        assert result.passed is False
        assert len(result.findings) == 1
        assert "不应匹配到数据" in result.findings[0]["message"]

    @pytest.mark.asyncio
    async def test_no_match_expect_match_false(self):
        """JSONPath 未匹配 + expect_match=False → passed"""
        rule_def = _make_rule_def(
            expression_type="jsonpath",
            expression="$.bad_field",
            parameters_schema={"expect_match": False},
        )
        parsed_data = {"good_field": "value"}

        result = await execute_jsonpath_rule(rule_def, parsed_data)
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_default_expect_match_is_true(self):
        """默认 expect_match=True"""
        rule_def = _make_rule_def(
            expression_type="jsonpath",
            expression="$.conclusion",
            parameters_schema=None,
        )
        parsed_data = {"conclusion": "有结论"}

        result = await execute_jsonpath_rule(rule_def, parsed_data)
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_invalid_jsonpath_expression(self):
        """无效 JSONPath 表达式 → error"""
        rule_def = _make_rule_def(
            expression_type="jsonpath",
            expression="$[invalid[[",
        )

        result = await execute_jsonpath_rule(rule_def, {"a": 1})
        assert result.passed is False
        assert "Invalid JSONPath expression" in result.error

    @pytest.mark.asyncio
    async def test_none_parsed_data(self):
        """parsed_data 为 None → 视为空 dict"""
        rule_def = _make_rule_def(
            expression_type="jsonpath",
            expression="$.conclusion",
            parameters_schema={"expect_match": True},
        )

        result = await execute_jsonpath_rule(rule_def, None)
        assert result.passed is False
        assert "未匹配到数据" in result.findings[0]["message"]

    @pytest.mark.asyncio
    async def test_nested_jsonpath(self):
        """嵌套 JSONPath 表达式"""
        rule_def = _make_rule_def(
            expression_type="jsonpath",
            expression="$.ai_content[*].status",
            parameters_schema={"expect_match": True},
        )
        parsed_data = {
            "ai_content": [
                {"status": "confirmed", "content": "test"},
            ]
        }

        result = await execute_jsonpath_rule(rule_def, parsed_data)
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_custom_message(self):
        """自定义 finding 消息"""
        rule_def = _make_rule_def(
            expression_type="jsonpath",
            expression="$.conclusion",
            parameters_schema={
                "expect_match": True,
                "message": "结论区必须填写",
            },
        )
        parsed_data = {}

        result = await execute_jsonpath_rule(rule_def, parsed_data)
        assert result.passed is False
        assert result.findings[0]["message"] == "结论区必须填写"


# ---------------------------------------------------------------------------
# Tests: execute_rule (统一分派)
# ---------------------------------------------------------------------------


class TestExecuteRule:
    @pytest.mark.asyncio
    async def test_dispatch_python(self):
        """分派到 Python 执行器"""
        rule_def = _make_rule_def(
            expression_type="python",
            expression="app.services.qc_engine.ConclusionNotEmptyRule",
        )
        wp = MagicMock()
        wp.parsed_data = {"conclusion": "OK"}
        context = MagicMock()
        context.working_paper = wp

        result = await execute_rule(rule_def, context=context)
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_dispatch_jsonpath(self):
        """分派到 JSONPath 执行器"""
        rule_def = _make_rule_def(
            expression_type="jsonpath",
            expression="$.conclusion",
        )

        result = await execute_rule(
            rule_def, parsed_data={"conclusion": "审计结论"}
        )
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_dispatch_sql_raises(self):
        """SQL 类型 → NotImplementedError"""
        rule_def = _make_rule_def(expression_type="sql", expression="SELECT 1")

        with pytest.raises(NotImplementedError, match="sql"):
            await execute_rule(rule_def)

    @pytest.mark.asyncio
    async def test_dispatch_regex_raises(self):
        """Regex 类型 → NotImplementedError"""
        rule_def = _make_rule_def(
            expression_type="regex", expression=".*pattern.*"
        )

        with pytest.raises(NotImplementedError, match="regex"):
            await execute_rule(rule_def)

    @pytest.mark.asyncio
    async def test_dispatch_unknown_type(self):
        """未知类型 → error"""
        rule_def = _make_rule_def(expression_type="unknown", expression="???")

        result = await execute_rule(rule_def)
        assert result.passed is False
        assert "Unknown expression_type" in result.error

    @pytest.mark.asyncio
    async def test_python_without_context(self):
        """Python 类型无 context → error"""
        rule_def = _make_rule_def(expression_type="python")

        result = await execute_rule(rule_def, context=None)
        assert result.passed is False
        assert "requires a QCContext" in result.error


# ---------------------------------------------------------------------------
# Tests: execute_audit_log_rule
# ---------------------------------------------------------------------------


class TestExecuteAuditLogRule:
    """Tests for audit_log scope executor (需求 12)."""

    def _make_audit_log_entry(
        self,
        action_type: str = "workpaper_modified",
        payload: dict | None = None,
        ts: datetime | None = None,
        user_id: uuid.UUID | None = None,
        ip: str | None = None,
    ) -> MagicMock:
        """Create a mock AuditLogEntry."""
        entry = MagicMock()
        entry.id = uuid.uuid4()
        entry.ts = ts or datetime(2026, 1, 15, 3, 0, 0)
        entry.action_type = action_type
        entry.user_id = user_id or uuid.uuid4()
        entry.ip = ip or "192.168.1.100"
        entry.payload = payload or {"action_type": action_type}
        entry.object_id = uuid.uuid4()
        return entry

    def _make_mock_db(self, entries: list) -> AsyncMock:
        """Create a mock AsyncSession that returns given entries."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = entries
        mock_result.scalars.return_value = mock_scalars
        db.execute = AsyncMock(return_value=mock_result)
        return db

    @pytest.mark.asyncio
    async def test_jsonpath_matches_payload(self):
        """audit_log 规则 JSONPath 匹配 payload → 产生 findings"""
        rule_def = _make_rule_def(
            rule_code="AL-01",
            expression_type="jsonpath",
            expression="$.action_type",
            severity="warning",
            parameters_schema={"expect_match": False},
        )
        rule_def.scope = "audit_log"

        entries = [
            self._make_audit_log_entry(
                action_type="workpaper_modified",
                payload={"action_type": "workpaper_modified"},
            ),
        ]
        db = self._make_mock_db(entries)

        result = await execute_audit_log_rule(rule_def, db)
        assert result.passed is False
        assert len(result.findings) == 1
        assert result.findings[0]["action_type"] == "workpaper_modified"
        assert result.findings[0]["rule_id"] == "AL-01"

    @pytest.mark.asyncio
    async def test_jsonpath_no_match(self):
        """audit_log 规则 JSONPath 不匹配 → passed"""
        rule_def = _make_rule_def(
            rule_code="AL-03",
            expression_type="jsonpath",
            expression="$.retention_override_flag",
            severity="info",
        )
        rule_def.scope = "audit_log"

        entries = [
            self._make_audit_log_entry(
                action_type="login",
                payload={"action_type": "login", "role": "auditor"},
            ),
        ]
        db = self._make_mock_db(entries)

        result = await execute_audit_log_rule(rule_def, db)
        assert result.passed is True
        assert result.findings == []

    @pytest.mark.asyncio
    async def test_empty_entries(self):
        """无日志条目 → passed"""
        rule_def = _make_rule_def(
            rule_code="AL-01",
            expression_type="jsonpath",
            expression="$.action_type",
            severity="warning",
        )
        rule_def.scope = "audit_log"

        db = self._make_mock_db([])

        result = await execute_audit_log_rule(db=db, rule=rule_def)
        assert result.passed is True
        assert result.findings == []

    @pytest.mark.asyncio
    async def test_python_type_deferred(self):
        """Python 类型 audit_log 规则 → deferred 消息"""
        rule_def = _make_rule_def(
            rule_code="AL-02",
            expression_type="python",
            expression="app.services.audit_log_rules.MultiAccountSameIPRule",
            severity="blocking",
        )
        rule_def.scope = "audit_log"

        db = self._make_mock_db([])

        result = await execute_audit_log_rule(rule_def, db)
        assert result.passed is True
        assert "deferred" in result.error.lower()

    @pytest.mark.asyncio
    async def test_invalid_jsonpath_expression(self):
        """无效 JSONPath → error"""
        rule_def = _make_rule_def(
            rule_code="AL-TEST",
            expression_type="jsonpath",
            expression="$[invalid[[",
            severity="warning",
        )
        rule_def.scope = "audit_log"

        db = self._make_mock_db([])

        result = await execute_audit_log_rule(rule_def, db)
        assert result.passed is False
        assert "Invalid JSONPath expression" in result.error

    @pytest.mark.asyncio
    async def test_with_project_id_filter(self):
        """传入 project_id 过滤"""
        rule_def = _make_rule_def(
            rule_code="AL-01",
            expression_type="jsonpath",
            expression="$.action_type",
            severity="warning",
        )
        rule_def.scope = "audit_log"

        entries = [
            self._make_audit_log_entry(
                action_type="workpaper_modified",
                payload={"action_type": "workpaper_modified"},
            ),
        ]
        db = self._make_mock_db(entries)
        project_id = uuid.uuid4()

        result = await execute_audit_log_rule(
            rule_def, db, project_id=project_id
        )
        # 验证 db.execute 被调用（查询构建正确）
        assert db.execute.called
        assert result.findings[0]["action_type"] == "workpaper_modified"

    @pytest.mark.asyncio
    async def test_with_time_window(self):
        """传入时间窗口过滤"""
        rule_def = _make_rule_def(
            rule_code="AL-01",
            expression_type="jsonpath",
            expression="$.action_type",
            severity="warning",
        )
        rule_def.scope = "audit_log"

        entries = [
            self._make_audit_log_entry(
                action_type="workpaper_modified",
                payload={"action_type": "workpaper_modified"},
                ts=datetime(2026, 1, 15, 3, 0, 0),
            ),
        ]
        db = self._make_mock_db(entries)

        result = await execute_audit_log_rule(
            rule_def,
            db,
            time_window_start=datetime(2026, 1, 15, 0, 0, 0),
            time_window_end=datetime(2026, 1, 15, 6, 0, 0),
        )
        assert db.execute.called
        assert len(result.findings) == 1

    @pytest.mark.asyncio
    async def test_null_payload_skipped(self):
        """payload 为 None 的条目不崩溃"""
        rule_def = _make_rule_def(
            rule_code="AL-01",
            expression_type="jsonpath",
            expression="$.action_type",
            severity="warning",
        )
        rule_def.scope = "audit_log"

        entry_with_null = self._make_audit_log_entry(payload=None)
        entry_with_null.payload = None
        db = self._make_mock_db([entry_with_null])

        result = await execute_audit_log_rule(rule_def, db)
        # null payload → jsonpath 对 {} 查询，$.action_type 不匹配
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_multiple_entries_partial_match(self):
        """多条日志部分匹配"""
        rule_def = _make_rule_def(
            rule_code="AL-03",
            expression_type="jsonpath",
            expression="$.override_type",
            severity="info",
        )
        rule_def.scope = "audit_log"

        entries = [
            self._make_audit_log_entry(
                action_type="retention_override",
                payload={"override_type": "retention_override"},
            ),
            self._make_audit_log_entry(
                action_type="login",
                payload={"role": "auditor"},
            ),
            self._make_audit_log_entry(
                action_type="rotation_override",
                payload={"override_type": "rotation_override"},
            ),
        ]
        db = self._make_mock_db(entries)

        result = await execute_audit_log_rule(rule_def, db)
        assert result.passed is False
        assert len(result.findings) == 2


# ---------------------------------------------------------------------------
# Tests: execute_rule dispatch for audit_log scope
# ---------------------------------------------------------------------------


class TestExecuteRuleAuditLogDispatch:
    """Tests for execute_rule dispatching to audit_log executor."""

    @pytest.mark.asyncio
    async def test_dispatch_audit_log_scope(self):
        """scope='audit_log' → 分派到 audit_log 执行器"""
        rule_def = _make_rule_def(
            rule_code="AL-01",
            expression_type="jsonpath",
            expression="$.action_type",
            severity="warning",
        )
        rule_def.scope = "audit_log"

        db = AsyncMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        db.execute = AsyncMock(return_value=mock_result)

        result = await execute_rule(rule_def, db=db)
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_dispatch_audit_log_no_db(self):
        """scope='audit_log' 无 db → error"""
        rule_def = _make_rule_def(
            rule_code="AL-01",
            expression_type="jsonpath",
            expression="$.action_type",
        )
        rule_def.scope = "audit_log"

        result = await execute_rule(rule_def, db=None)
        assert result.passed is False
        assert "requires a database session" in result.error

    @pytest.mark.asyncio
    async def test_dispatch_audit_log_with_time_window(self):
        """scope='audit_log' 带时间窗口参数"""
        rule_def = _make_rule_def(
            rule_code="AL-01",
            expression_type="jsonpath",
            expression="$.action_type",
            severity="warning",
        )
        rule_def.scope = "audit_log"

        db = AsyncMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        db.execute = AsyncMock(return_value=mock_result)

        result = await execute_rule(
            rule_def,
            db=db,
            project_id=uuid.uuid4(),
            time_window_start=datetime(2026, 1, 1),
            time_window_end=datetime(2026, 1, 31),
        )
        assert result.passed is True
        assert db.execute.called
