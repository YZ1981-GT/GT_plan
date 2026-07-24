"""附注模块硬化（P0-A findings 冲击缓冲 + P0-B 健康度诊断）测试.

复盘补强（非 disclosure-note-formula-and-report-sync 原 spec 任务）：
- P0-A：DISCLOSURE_NOTE_VALIDATION_STRICT 开关。默认宽松 → validate_all 只逐条列
  error 级 findings、warning 折叠进 warning_summary；严格 → 全部逐条。
- P0-B：diagnose_formula_health 只读诊断（metadata 扫描 + preset/linkage 计数 +
  三条管线激活标志），不跑规则、不 persist。

用 db=None 构造 engine + monkeypatch execute_all 注入合成 ValidationResult，
避免真实 DB（与既有 wave 测试同款隔离）。
"""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.config import settings
from app.services.note_validation_engine import (
    NoteValidationEngine,
    ValidationResult,
)


def _mk(passed: bool, section: str, rtype: str, diff) -> ValidationResult:
    return ValidationResult(
        section_code=section,
        rule_type=rtype,
        rule_expression=f"{section}-{rtype}",
        passed=passed,
        diff_amount=diff,
    )


# ---------------------------------------------------------------------------
# P0-A：strict / lenient findings 呈现
# ---------------------------------------------------------------------------

class TestValidationStrictFlag:
    @pytest.mark.asyncio
    async def test_lenient_folds_warnings(self, monkeypatch):
        """默认宽松：error 逐条进 findings；warning 折叠进 warning_summary（聚合计数）。"""
        eng = NoteValidationEngine(db=None)
        results = [
            _mk(False, "五、1", "balance", Decimal("100")),  # error（diff>0.01）
            _mk(False, "五、2", "sub_item", None),            # warning（无 diff）
            _mk(False, "五、2", "sub_item", Decimal("0")),    # warning（diff=0）同 section×type
            _mk(True, "五、3", "cross", None),                # 通过，不计
        ]

        async def fake_execute_all(*a, **k):
            return results

        monkeypatch.setattr(eng, "execute_all", fake_execute_all)
        monkeypatch.setattr(settings, "DISCLOSURE_NOTE_VALIDATION_STRICT", False)

        res = await eng.validate_all(uuid4(), 2025)

        assert res["strict"] is False
        assert res["error_count"] == 1
        assert res["warning_count"] == 2
        assert res["failed"] == 3  # 计数不受呈现粒度影响
        # findings 只含 error
        assert len(res["findings"]) == 1
        assert res["findings"][0]["severity"] == "error"
        # 两条同 section×type 的 warning 折叠为 1 桶 count=2
        assert len(res["warning_summary"]) == 1
        assert res["warning_summary"][0]["count"] == 2
        assert res["warning_summary"][0]["note_section"] == "五、2"

    @pytest.mark.asyncio
    async def test_strict_lists_all_findings(self, monkeypatch):
        """严格：error + warning 全部逐条进 findings；warning_summary 空。"""
        eng = NoteValidationEngine(db=None)
        results = [
            _mk(False, "五、1", "balance", Decimal("100")),  # error
            _mk(False, "五、2", "sub_item", None),            # warning
        ]

        async def fake_execute_all(*a, **k):
            return results

        monkeypatch.setattr(eng, "execute_all", fake_execute_all)
        monkeypatch.setattr(settings, "DISCLOSURE_NOTE_VALIDATION_STRICT", True)

        res = await eng.validate_all(uuid4(), 2025)

        assert res["strict"] is True
        assert len(res["findings"]) == 2
        severities = {f["severity"] for f in res["findings"]}
        assert severities == {"error", "warning"}
        assert res["warning_summary"] == []

    @pytest.mark.asyncio
    async def test_failed_count_flag_invariant(self, monkeypatch):
        """failed/error_count/warning_count 不随 strict 开关变化（仅呈现粒度变）。"""
        eng = NoteValidationEngine(db=None)
        results = [
            _mk(False, "五、1", "balance", Decimal("50")),
            _mk(False, "五、2", "sub_item", None),
            _mk(False, "五、5", "cross", None),
        ]

        async def fake_execute_all(*a, **k):
            return results

        monkeypatch.setattr(eng, "execute_all", fake_execute_all)

        monkeypatch.setattr(settings, "DISCLOSURE_NOTE_VALIDATION_STRICT", False)
        lenient = await eng.validate_all(uuid4(), 2025)
        monkeypatch.setattr(settings, "DISCLOSURE_NOTE_VALIDATION_STRICT", True)
        strict = await eng.validate_all(uuid4(), 2025)

        assert lenient["failed"] == strict["failed"] == 3
        assert lenient["error_count"] == strict["error_count"] == 1
        assert lenient["warning_count"] == strict["warning_count"] == 2


# ---------------------------------------------------------------------------
# P0-B：健康度诊断（只读）
# ---------------------------------------------------------------------------

class TestFormulaHealthDiagnostic:
    @pytest.mark.asyncio
    async def test_diagnose_no_db_reports_preset_active(self):
        """db=None：附注计数全 0，但 preset 规则可加载（Wave4 修后）→ 校验管线判活。"""
        eng = NoteValidationEngine(db=None)
        res = await eng.diagnose_formula_health(uuid4(), 2025)

        assert res["notes_total"] == 0
        assert res["notes_with_binding"] == 0
        assert res["notes_with_report_binding"] == 0
        # Wave4 路径修复后 preset 非空
        assert res["preset_rule_count"]["soe"] > 0
        assert res["preset_rule_count"]["listed"] > 0
        # linkage 骨架 → 0 业务条目
        assert res["linkage_config_entries"] == 0
        # 管线激活判定
        p = res["pipelines"]
        assert p["validation_findings_active"] is True  # preset 可加载
        assert p["in_cell_formula_active"] is False       # 无 binding
        assert p["report_sync_active"] is False           # 无 report binding + linkage 空

    @pytest.mark.asyncio
    async def test_diagnose_structure_keys(self):
        """诊断返回结构键齐全（供前端/运维消费）。"""
        eng = NoteValidationEngine(db=None)
        res = await eng.diagnose_formula_health(uuid4(), 2025, template_type="listed")
        for k in (
            "project_id", "year", "notes_total", "notes_with_cell_meta",
            "notes_with_binding", "notes_with_report_binding",
            "notes_with_inline_rules", "notes_with_text",
            "preset_rule_count", "linkage_config_entries", "pipelines",
        ):
            assert k in res, f"missing key {k}"
        assert set(res["pipelines"].keys()) == {
            "validation_findings_active",
            "in_cell_formula_active",
            "report_sync_active",
        }
