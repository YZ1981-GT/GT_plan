"""Sprint 6.14 / F32: 错误码 ↔ hint 一致性检查。

CI 必跑：ErrorCode 中每个枚举值必须在 ERROR_HINTS 中有条目；
反之亦然（ERROR_HINTS 不应含游离码）。
"""

from __future__ import annotations

import pytest

from app.services.ledger_import.error_hints import (
    ERROR_HINTS,
    ErrorHint,
    all_error_code_values,
    all_registered_codes,
    enrich_finding_with_hint,
    get_error_hint,
)
from app.services.ledger_import.errors import ErrorCode


class TestHintCoverage:
    def test_every_error_code_has_hint(self):
        """每个 ErrorCode 都应在 ERROR_HINTS 中有条目。"""
        enum_codes = all_error_code_values()
        hint_codes = all_registered_codes()
        missing = enum_codes - hint_codes
        assert not missing, (
            f"以下 ErrorCode 缺 hint 定义：{sorted(missing)}\n"
            "请在 error_hints.py 中补充对应条目。"
        )

    def test_no_stray_hint_entries(self):
        """ERROR_HINTS 中不应有游离码（未在 ErrorCode 枚举中）。"""
        enum_codes = all_error_code_values()
        hint_codes = all_registered_codes()
        extra = hint_codes - enum_codes
        assert not extra, (
            f"以下 hint 条目找不到对应 ErrorCode：{sorted(extra)}\n"
            "请清理 error_hints.py 中的游离条目或在 errors.py 补充 ErrorCode。"
        )

    def test_hint_shape(self):
        """每条 hint 的 title/description/suggestions 都非空。"""
        for code, hint in ERROR_HINTS.items():
            assert isinstance(hint, ErrorHint), f"{code}: not ErrorHint instance"
            assert hint.title.strip(), f"{code}: title 不应为空"
            assert hint.description.strip(), f"{code}: description 不应为空"
            assert hint.suggestions, f"{code}: suggestions 不应为空列表"
            assert all(s.strip() for s in hint.suggestions), (
                f"{code}: suggestions 含空字符串"
            )
            assert hint.severity in ("fatal", "blocking", "warning", "info")


class TestEnrichFinding:
    def test_enrich_adds_hint_field(self):
        finding = {
            "code": "L2_LEDGER_YEAR_OUT_OF_RANGE",
            "severity": "blocking",
            "message": "跨年度凭证",
        }
        out = enrich_finding_with_hint(finding)
        assert out["code"] == "L2_LEDGER_YEAR_OUT_OF_RANGE"
        assert "hint" in out
        assert out["hint"]["title"] == "序时账年度超出范围"
        assert isinstance(out["hint"]["suggestions"], list)
        # 原字段保留
        assert out["severity"] == "blocking"
        assert out["message"] == "跨年度凭证"

    def test_enrich_passthrough_unknown_code(self):
        finding = {"code": "TOTALLY_UNKNOWN_CODE", "message": "foo"}
        out = enrich_finding_with_hint(finding)
        assert "hint" not in out  # 不影响原结构
        assert out == finding

    def test_enrich_passthrough_no_code(self):
        finding = {"message": "no code field"}
        out = enrich_finding_with_hint(finding)
        assert out == finding

    def test_get_error_hint_returns_none_for_unknown(self):
        assert get_error_hint("NOT_A_REAL_CODE") is None

    def test_get_error_hint_returns_hint_for_known(self):
        h = get_error_hint("FILE_TOO_LARGE")
        assert h is not None
        assert h.severity == "fatal"
