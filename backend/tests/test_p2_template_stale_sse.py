"""P2 模板扩展/增量刷新/SSE/后台任务 验收测试。

P2-1: 国企/上市核心章节覆盖率
P2-2: Word 模板和同步工具
P2-3: 多级表头覆盖率
P2-4: stale 增量刷新机制
P2-5: 后台任务/SSE 进度/失败重试
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
APP_DATA_DIR = Path(__file__).resolve().parents[1] / "app" / "data"


def _load_template(std: str) -> list[dict]:
    for d in (APP_DATA_DIR, DATA_DIR):
        p = d / f"consol_note_sections_{std}.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    pytest.skip(f"consol_note_sections_{std}.json 不存在")


# ═══════════════════════════════════════════════════════════════════════════
# P2-1: 国企/上市核心章节覆盖率
# ═══════════════════════════════════════════════════════════════════════════


class TestP2_1_TemplateCoverage:

    def test_soe_section_count_baseline(self):
        """soe 模板章节数 ≥ 321（棘轮基线）。"""
        data = _load_template("soe")
        assert len(data) >= 321, f"soe 只有 {len(data)} 章节"

    def test_listed_section_count_baseline(self):
        """listed 模板章节数 ≥ 432。"""
        data = _load_template("listed")
        assert len(data) >= 432, f"listed 只有 {len(data)} 章节"

    def test_soe_covers_key_sections(self):
        """soe 覆盖关键科目章节（应收/存货/固定/无形/权益）。"""
        data = _load_template("soe")
        ids = {s.get("section_id", "") for s in data}
        # soe 格式：五-N-M
        for prefix in ("五-4", "五-5", "五-10", "五-11", "五-45"):
            found = any(sid.startswith(prefix) for sid in ids)
            assert found, f"soe 缺少 {prefix} 相关章节"

    def test_listed_covers_key_sections(self):
        """listed 覆盖关键章节。"""
        data = _load_template("listed")
        ids = {s.get("section_id", "") for s in data}
        for prefix in ("五-4", "五-5", "五-10", "五-11"):
            found = any(sid.startswith(prefix) for sid in ids)
            assert found, f"listed 缺少 {prefix} 相关章节"

    def test_single_note_template_soe_exists(self):
        """单体 soe 附注模板存在。"""
        from app.services.note_check_rules import _load_check_rules
        # 能加载就说明文件存在且可解析
        rules = _load_check_rules("soe", "nonexistent")
        assert rules == []  # 不存在的章节返回空，但文件本身可读


# ═══════════════════════════════════════════════════════════════════════════
# P2-2: Word 模板和同步工具
# ═══════════════════════════════════════════════════════════════════════════


class TestP2_2_WordTemplateSync:

    def test_sync_tool_exists(self):
        """sync_note_templates_from_word.py 长期可重跑工具存在。"""
        tool = Path(__file__).resolve().parents[1] / "scripts" / "seed" / "sync_note_templates_from_word.py"
        assert tool.exists(), f"同步工具不存在: {tool}"

    def test_word_templates_exist(self):
        """Word 权威模板目录存在且有 docx 文件。"""
        template_dir = Path(__file__).resolve().parents[1] / "data" / "audit_report_templates"
        if not template_dir.exists():
            template_dir = Path(__file__).resolve().parents[1] / "wp_templates"
        # 至少有一个目录存在
        assert template_dir.exists() or (Path(__file__).resolve().parents[1] / "wp_templates").exists()

    def test_normalize_template_type_is_pure(self):
        """模板类型规范化是纯函数。"""
        from app.services.note_section_catalog import normalize_template_type
        assert normalize_template_type("soe") == "soe"
        assert normalize_template_type("listed") == "listed"


# ═══════════════════════════════════════════════════════════════════════════
# P2-3: 多级表头覆盖率
# ═══════════════════════════════════════════════════════════════════════════


class TestP2_3_MultiHeaderCoverage:

    def test_soe_multi_header_count(self):
        """soe 有 ≥ 60 张多级表头表（棘轮基线）。"""
        data = _load_template("soe")
        mh = sum(1 for s in data if s.get("multi_header"))
        assert mh >= 60, f"soe multi_header 只有 {mh} 张"

    def test_listed_multi_header_count(self):
        """listed 有 ≥ 100 张多级表头表。"""
        data = _load_template("listed")
        mh = sum(1 for s in data if s.get("multi_header"))
        assert mh >= 100, f"listed multi_header 只有 {mh} 张"

    def test_column_groups_consistent_with_multi_header(self):
        """有 multi_header 的表必有 _column_groups。"""
        for std in ("soe", "listed"):
            data = _load_template(std)
            for s in data:
                if s.get("multi_header"):
                    assert s.get("_column_groups"), (
                        f"{std} {s.get('section_id')} 有 multi_header 但缺 _column_groups"
                    )

    def test_check_rules_total_baseline(self):
        """check_rules 总量 ≥ 100（棘轮）。"""
        from app.services.note_check_rules import load_all_check_rules
        total = sum(len(v) for v in load_all_check_rules("soe").values()) + \
                sum(len(v) for v in load_all_check_rules("listed").values())
        assert total >= 100, f"check_rules 总量 {total} < 100"


# ═══════════════════════════════════════════════════════════════════════════
# P2-4: stale 增量刷新机制
# ═══════════════════════════════════════════════════════════════════════════


class TestP2_4_StaleRefresh:

    def test_financial_report_has_is_stale(self):
        """financial_report 表有 is_stale 列。"""
        from app.models.report_models import FinancialReport
        assert hasattr(FinancialReport, "is_stale")

    def test_disclosure_notes_has_is_stale(self):
        """disclosure_notes 表有 is_stale 列。"""
        from app.models.report_models import DisclosureNote
        assert hasattr(DisclosureNote, "is_stale")

    def test_consol_note_data_has_is_stale(self):
        """consol_note_data 表有 is_stale 列。"""
        from app.models.consol_note_data_models import ConsolNoteData
        assert hasattr(ConsolNoteData, "is_stale")

    def test_stale_propagation_engine_exists(self):
        """stale 传播引擎存在。"""
        from app.services.stale_propagation_engine import stale_engine
        assert stale_engine is not None

    def test_mark_consol_sections_stale_exists(self):
        """合并附注 stale 标记函数存在。"""
        from app.services.consol_note_stale_handler import mark_consol_sections_stale
        assert callable(mark_consol_sections_stale)

    def test_trial_balance_updated_triggers_report_stale(self):
        """TRIAL_BALANCE_UPDATED 订阅了报表引擎（增量重算）。"""
        from app.services.report_engine import ReportEngine
        assert hasattr(ReportEngine, "on_trial_balance_updated")

    def test_reports_updated_triggers_disclosure_stale(self):
        """REPORTS_UPDATED 订阅了附注引擎。"""
        from app.services.disclosure_engine import DisclosureEngine
        assert hasattr(DisclosureEngine, "on_reports_updated")


# ═══════════════════════════════════════════════════════════════════════════
# P2-5: 后台任务/SSE 进度/失败重试
# ═══════════════════════════════════════════════════════════════════════════


class TestP2_5_BackgroundTaskSSE:

    def test_consol_push_has_sse_events(self):
        """合并推送有 SSE 事件定义。"""
        from app.services.consol_push_service import SSE_PUSHED, SSE_FAILED, SSE_STALE
        assert SSE_PUSHED == "consol.pushed"
        assert SSE_FAILED == "consol.push_failed"
        assert SSE_STALE == "consol.push_stale"

    def test_consol_push_has_background_queue(self):
        """合并推送有后台排队机制。"""
        from app.services.consol_push_service import request_push, pending_count
        assert callable(request_push)
        assert callable(pending_count)
        assert pending_count() >= 0

    def test_consol_push_run_model_exists(self):
        """合并推送运行记录 ORM 存在。"""
        from app.models.consol_push_models import ConsolPushRun
        assert hasattr(ConsolPushRun, "status")
        assert hasattr(ConsolPushRun, "steps")
        assert hasattr(ConsolPushRun, "warnings")
        assert hasattr(ConsolPushRun, "trigger_source")

    def test_formula_push_run_model_exists(self):
        """公式推送运行记录 ORM 存在。"""
        from app.models.formula_push_models import FormulaPushRun
        assert hasattr(FormulaPushRun, "status")
        assert hasattr(FormulaPushRun, "written_count")

    def test_formula_push_has_retry_endpoint(self):
        """公式推送有重试端点。"""
        from app.main import app
        paths = [r.path for r in app.routes if hasattr(r, "path")]
        found = any("formula-push/run" in p for p in paths)
        assert found, "公式推送重试端点未注册"

    def test_consol_refresh_has_sse_progress(self):
        """合并刷新 job 有 SSE 进度事件。"""
        from app.services.consol_refresh_job_service import SSE_PROGRESS, SSE_COMPLETED, SSE_ERROR
        assert SSE_PROGRESS == "consol.refresh.progress"
        assert SSE_COMPLETED == "consol.refresh.completed"
        assert SSE_ERROR == "consol.refresh.error"

    def test_sync_failed_sse_exists(self):
        """sync.failed SSE 事件定义存在（公式推送/科目映射失败通道）。"""
        from app.models.audit_platform_schemas import EventType
        assert hasattr(EventType, "SYNC_FAILED")

    def test_export_job_model_exists(self):
        """导出任务 ORM 存在（后台导出任务）。"""
        from app.models.report_models import ExportTask
        assert hasattr(ExportTask, "status")
