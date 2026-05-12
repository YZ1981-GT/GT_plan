"""Unit tests for _humanize_import_error function (P1-5.1 failure readability)."""
import pytest

from app.services.import_job_runner import _humanize_import_error
from app.services.smart_import_engine import SmartImportError


class TestHumanizeImportError:
    """确保异常 → 用户友好提示的映射覆盖常见 PG/文件/IO 异常。"""

    def test_asyncpg_foreign_key_violation_by_class_name(self):
        import asyncpg.exceptions as e
        result = _humanize_import_error(e.ForeignKeyViolationError("parent row not found"))
        assert "数据关联错误" in result

    def test_asyncpg_unique_violation_by_class_name(self):
        import asyncpg.exceptions as e
        result = _humanize_import_error(e.UniqueViolationError("dup"))
        assert "数据重复" in result

    def test_asyncpg_not_null_violation_by_class_name(self):
        import asyncpg.exceptions as e
        result = _humanize_import_error(e.NotNullViolationError("null"))
        assert "必填字段为空" in result

    def test_asyncpg_invalid_text_representation_by_class_name(self):
        import asyncpg.exceptions as e
        result = _humanize_import_error(e.InvalidTextRepresentationError("not int"))
        assert "字段格式错误" in result

    def test_memory_error_recognized(self):
        result = _humanize_import_error(MemoryError("out of memory"))
        assert "内存不足" in result

    def test_timeout_error_recognized(self):
        result = _humanize_import_error(TimeoutError("slow"))
        assert "操作超时" in result

    def test_unicode_decode_error_recognized(self):
        result = _humanize_import_error(
            UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad")
        )
        assert "文件编码错误" in result

    def test_smart_import_error_direct_passthrough(self):
        exc = SmartImportError("账套文件格式不支持", errors=[], diagnostics={}, year=None)
        result = _humanize_import_error(exc)
        assert result.startswith("账套文件格式不支持")

    def test_unknown_exception_fallback(self):
        result = _humanize_import_error(ValueError("arbitrary"))
        assert "[ValueError]" in result
        assert "arbitrary" in result

    def test_truncation_500_chars(self):
        long_msg = "x" * 1000
        result = _humanize_import_error(ValueError(long_msg))
        # "[ValueError] " + 500 char
        assert len(result) <= 600

    def test_message_substring_fallback(self):
        """类名不匹配但 message 含关键词时也能识别（如被 wrap 的场景）。"""
        result = _humanize_import_error(
            Exception("SQLAlchemy raised foreign key violation")
        )
        assert "数据关联错误" in result



class TestErrorRuleRegistration:
    """E1 规则注册表扩展点测试（开闭原则）。"""

    def test_register_rule_at_end(self):
        """register_error_rule 追加到末尾，原规则优先级不变。"""
        from app.services.import_job_runner import (
            _ErrorRule, register_error_rule, _ERROR_RULES, _humanize_import_error,
        )
        original_len = len(_ERROR_RULES)

        class _CustomExc(Exception):
            pass

        rule = _ErrorRule(
            name="test_custom_v1",
            matcher=lambda exc, _n, _m: isinstance(exc, _CustomExc),
            formatter=lambda _e, _m: "自定义规则命中",
        )
        register_error_rule(rule)
        try:
            assert len(_ERROR_RULES) == original_len + 1
            assert _humanize_import_error(_CustomExc("x")) == "自定义规则命中"
        finally:
            _ERROR_RULES.pop()  # 清理

    def test_register_rule_at_priority_0(self):
        """priority=0 插入到最前，优先级最高。"""
        from app.services.import_job_runner import (
            _ErrorRule, register_error_rule, _ERROR_RULES, _humanize_import_error,
        )
        rule = _ErrorRule(
            name="override_smart_error",
            matcher=lambda _e, _n, _m: True,  # 匹配所有
            formatter=lambda _e, _m: "高优先级规则",
        )
        register_error_rule(rule, priority=0)
        try:
            # 即使是 SmartImportError 也应命中此规则
            from app.services.smart_import_engine import SmartImportError
            exc = SmartImportError("业务异常", errors=[], diagnostics={}, year=None)
            assert _humanize_import_error(exc) == "高优先级规则"
        finally:
            _ERROR_RULES.pop(0)

    def test_rule_matcher_exception_doesnt_break_others(self):
        """某条规则 matcher 抛错不影响后续规则。"""
        from app.services.import_job_runner import (
            _ErrorRule, register_error_rule, _ERROR_RULES, _humanize_import_error,
        )

        def _broken_matcher(_e, _n, _m):
            raise RuntimeError("buggy matcher")

        rule = _ErrorRule(
            name="broken_matcher",
            matcher=_broken_matcher,
            formatter=lambda _e, _m: "unreachable",
        )
        register_error_rule(rule, priority=0)
        try:
            # MemoryError 应仍被正确识别
            result = _humanize_import_error(MemoryError("oom"))
            assert "内存不足" in result
        finally:
            _ERROR_RULES.pop(0)
