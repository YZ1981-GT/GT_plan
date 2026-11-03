"""回滚取服务端快照测试（需求 13.1~13.3，ADR-FHIC-10，变异 #35）。

验证：
- change_entry 写入 old_definition / new_definition 完整字典
- rollback_from_log 从审计条目的 old_definition 恢复，不读请求体 target_formula
- expected_version 缺 428、不符 409
- cross_check 新条目有 old_definition 可回滚
- 历史 GET 带 rollbackable / rollback_blocked_reason
"""
from __future__ import annotations

import uuid

import pytest

from app.services.formula_settings.audit import change_entry
from app.services.formula_settings.definitions import normalize


# ── change_entry 完整定义 ────────────────────────────────────────

class TestChangeEntryFullDefinition:
    """需求 13.1：change_entry 记录完整旧/新定义。"""

    def test_report_domain_stores_full_definition(self):
        old = {"formula": "TB('1001','审定数')", "formula_description": "应收账款", "formula_category": "auto_calc"}
        new = {"formula": "TB('1002','审定数')", "formula_description": "应收票据", "formula_category": "custom"}
        entry = change_entry("report", "balance_sheet:BS-002", old, new)
        assert "old_definition" in entry
        assert "new_definition" in entry
        assert entry["old_definition"] == normalize("report", old)
        assert entry["new_definition"] == normalize("report", new)
        # 显示文本也在
        assert entry["old_formula"]
        assert entry["new_formula"]

    def test_cross_check_domain_stores_full_definition(self):
        old = {"left_ref": "TB('1001','审定数')", "operator": "=", "right_ref": "TB('1002','审定数')", "tolerance": "0.01"}
        new = {"left_ref": "TB('1001','期末余额')", "operator": "=", "right_ref": "TB('1002','期末余额')", "tolerance": "0.02"}
        entry = change_entry("cross_check", "XR-01", old, new)
        assert isinstance(entry["old_definition"], dict)
        assert entry["old_definition"]["left_ref"] == "TB('1001','审定数')"
        assert entry["old_definition"]["tolerance"] == "0.01"
        assert isinstance(entry["new_definition"], dict)

    def test_wp_domain_stores_full_definition(self):
        old = {"expression": "=TB('1001','审定数')", "formula_type": "auto_calc"}
        new = {"expression": "=TB('1002','审定数')", "formula_type": "auto_calc"}
        entry = change_entry("wp", "D1|审定表|B5", old, new)
        assert isinstance(entry["old_definition"], dict)
        assert isinstance(entry["new_definition"], dict)

    def test_none_old_no_old_definition(self):
        new = {"formula": "100"}
        entry = change_entry("report", "balance_sheet:BS-002", None, new)
        assert "old_definition" not in entry
        assert "new_definition" in entry

    def test_none_new_no_new_definition(self):
        old = {"formula": "100"}
        entry = change_entry("report", "balance_sheet:BS-002", old, None)
        assert "old_definition" in entry
        assert "new_definition" not in entry


# ── rollback：服务端快照、CAS、cross_check ──────────────────────

class TestRollbackFromLog:
    """需求 13.1~13.2：rollback_from_log 从 old_definition 恢复。"""

    @pytest.fixture()
    def _domain_fixtures(self):
        """返回各域的完整旧定义，供子测试使用。"""
        return {
            "report": {"formula": "TB('1001','审定数')", "formula_description": "测试", "formula_category": "auto_calc"},
            "cross_check": {"left_ref": "TB('1001','审定数')", "operator": "=", "right_ref": "TB('1002','审定数')",
                            "tolerance": "0.01", "label": "XR-07", "description": "测试规则"},
        }

    def test_extract_old_definition_with_full(self):
        """新条目有 old_definition 完整字典。"""
        from app.services.formula_settings.rollback import _extract_old_definition
        payload = {"old_definition": {"formula": "TB('1001','审定数')"}, "old_formula": "TB('1001','审定数')"}
        result = _extract_old_definition("report", payload)
        assert result == {"formula": "TB('1001','审定数')"}

    def test_extract_old_definition_legacy_report(self):
        """旧条目只有 old_formula，报表域可回滚。"""
        from app.services.formula_settings.rollback import _extract_old_definition
        payload = {"old_formula": "TB('1001','审定数')"}
        result = _extract_old_definition("report", payload)
        assert result == {"formula": "TB('1001','审定数')"}

    def test_extract_old_definition_legacy_cross_check_none(self):
        """旧条目只有 old_formula，cross_check 域不可回滚。"""
        from app.services.formula_settings.rollback import _extract_old_definition
        payload = {"old_formula": "TB('1001','审定数') = TB('1002','审定数')（容差 0.01）"}
        result = _extract_old_definition("cross_check", payload)
        assert result is None

    def test_can_rollback_new_entry(self):
        """新条目有 old_definition 可回滚。"""
        from app.services.formula_settings.rollback import can_rollback
        payload = {"action": "update", "old_definition": {"formula": "100"}, "old_formula": "100"}
        ok, reason = can_rollback("report", payload)
        assert ok is True
        assert reason == ""

    def test_can_rollback_cross_check_new(self):
        """cross_check 新条目有 old_definition 可回滚（需求 13.2）。"""
        from app.services.formula_settings.rollback import can_rollback
        payload = {"action": "update", "old_definition": {"left_ref": "A", "operator": "=", "right_ref": "B"}}
        ok, reason = can_rollback("cross_check", payload)
        assert ok is True

    def test_can_rollback_legacy_report(self):
        """旧报表条目有 old_formula 可回滚。"""
        from app.services.formula_settings.rollback import can_rollback
        payload = {"action": "update", "old_formula": "TB('1001','审定数')"}
        ok, reason = can_rollback("report", payload)
        assert ok is True

    def test_cannot_rollback_legacy_cross_check(self):
        """旧 cross_check 条目只有显示文本不可回滚。"""
        from app.services.formula_settings.rollback import can_rollback
        payload = {"action": "update", "old_formula": "A = B"}
        ok, reason = can_rollback("cross_check", payload)
        assert ok is False
        assert "旧格式" in reason

    def test_cannot_rollback_no_old(self):
        """没有旧定义不可回滚。"""
        from app.services.formula_settings.rollback import can_rollback
        payload = {"action": "update"}
        ok, reason = can_rollback("report", payload)
        assert ok is False
        assert "没有变更前定义" in reason

    def test_cannot_rollback_manual_note(self):
        """人工补记不可回滚。"""
        from app.services.formula_settings.rollback import can_rollback
        payload = {"action": "manual_note", "old_definition": {"formula": "100"}}
        ok, reason = can_rollback("report", payload)
        assert ok is False
        assert "人工补记" in reason


class TestRollbackVersionRequired:
    """需求 13.2：expected_version 缺 428、不符 409。"""

    @pytest.mark.asyncio
    async def test_missing_version_raises_428(self):
        from app.services.formula_settings.errors import VersionRequired
        from app.services.formula_settings.rollback import rollback_from_log
        with pytest.raises(VersionRequired):
            await rollback_from_log(
                None,  # type: ignore
                project_id=uuid.uuid4(),
                source_log_id=str(uuid.uuid4()),
                expected_version=None,
                user_id=uuid.uuid4(),
            )
