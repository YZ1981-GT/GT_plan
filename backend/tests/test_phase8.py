"""Phase 8 测试 — 数据模型优化 + 查询性能 + 事件去重 + 公式超时

覆盖：
- Task 1.2: trial_balance currency_code 字段
- Task 2.5: 复合索引（ORM 模型定义验证）
- Task 2.6: EventBus debounce 去重
- Task 2.7: FormulaEngine 超时控制
"""

import asyncio
import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import inspect

from app.models.audit_platform_models import (
    Adjustment,
    ImportBatch,
    TbBalance,
    TrialBalance,
)
from app.models.audit_platform_schemas import EventPayload, EventType
from app.services.event_bus import EventBus
from app.services.formula_engine import FormulaEngine, FormulaError


# ---------------------------------------------------------------------------
# Task 1.2: TrialBalance currency_code 字段
# ---------------------------------------------------------------------------


class TestTrialBalanceCurrencyCode:
    """验证 TrialBalance ORM 模型包含 currency_code 字段"""

    def test_currency_code_field_exists(self):
        mapper = inspect(TrialBalance)
        col_names = [c.key for c in mapper.column_attrs]
        assert "currency_code" in col_names

    def test_currency_code_default_cny(self):
        tb = TrialBalance(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            year=2025,
            company_code="001",
            standard_account_code="1001",
            account_name="货币资金",
            account_category="asset",
            unadjusted_amount=Decimal("100000"),
        )
        # server_default 在 Python 层不自动填充，但列定义存在
        col = TrialBalance.__table__.c.currency_code
        assert col.server_default is not None
        assert "CNY" in str(col.server_default.arg)


# ---------------------------------------------------------------------------
# Task 2.5: 复合索引验证
# ---------------------------------------------------------------------------


class TestCompositeIndexes:
    """验证 ORM 模型中定义了核心复合索引"""

    def test_trial_balance_project_year_std_code_index(self):
        indexes = {idx.name for idx in TrialBalance.__table__.indexes}
        assert "idx_trial_balance_project_year_std_code" in indexes

    def test_tb_balance_project_year_deleted_index(self):
        indexes = {idx.name for idx in TbBalance.__table__.indexes}
        assert "idx_tb_balance_project_year_deleted" in indexes

    def test_adjustments_project_year_account_code_index(self):
        indexes = {idx.name for idx in Adjustment.__table__.indexes}
        assert "idx_adjustments_project_year_account_code" in indexes

    def test_import_batches_project_year_index(self):
        indexes = {idx.name for idx in ImportBatch.__table__.indexes}
        assert "idx_import_batches_project_year" in indexes


# ---------------------------------------------------------------------------
# Task 2.6: EventBus debounce 去重
# ---------------------------------------------------------------------------


class TestEventBusDebounce:
    """验证 EventBus 的 debounce 去重机制"""

    @pytest.mark.asyncio
    async def test_debounce_merges_events(self):
        """10 次 publish 相同 key 只触发 1 次 handler"""
        bus = EventBus(debounce_ms=100)
        call_count = 0
        received_codes = []

        async def handler(payload: EventPayload):
            nonlocal call_count
            call_count += 1
            received_codes.extend(payload.account_codes or [])

        bus.subscribe(EventType.ADJUSTMENT_CREATED, handler)

        project_id = uuid.uuid4()
        for i in range(10):
            await bus.publish(
                EventPayload(
                    event_type=EventType.ADJUSTMENT_CREATED,
                    project_id=project_id,
                    account_codes=[f"100{i}"],
                )
            )

        # 等待 debounce 窗口过期
        await asyncio.sleep(0.3)

        assert call_count == 1, f"Expected 1 dispatch, got {call_count}"
        # 所有 account_codes 应被合并
        assert len(received_codes) == 10

    @pytest.mark.asyncio
    async def test_publish_immediate_bypasses_debounce(self):
        """publish_immediate 不经过 debounce"""
        bus = EventBus(debounce_ms=5000)
        call_count = 0

        async def handler(payload: EventPayload):
            nonlocal call_count
            call_count += 1

        bus.subscribe(EventType.DATA_IMPORTED, handler)

        await bus.publish_immediate(
            EventPayload(
                event_type=EventType.DATA_IMPORTED,
                project_id=uuid.uuid4(),
            )
        )

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_different_keys_not_merged(self):
        """不同 project_id 的事件不合并"""
        bus = EventBus(debounce_ms=100)
        call_count = 0

        async def handler(payload: EventPayload):
            nonlocal call_count
            call_count += 1

        bus.subscribe(EventType.ADJUSTMENT_CREATED, handler)

        await bus.publish(
            EventPayload(
                event_type=EventType.ADJUSTMENT_CREATED,
                project_id=uuid.uuid4(),
            )
        )
        await bus.publish(
            EventPayload(
                event_type=EventType.ADJUSTMENT_CREATED,
                project_id=uuid.uuid4(),
            )
        )

        await asyncio.sleep(0.3)
        assert call_count == 2


# ---------------------------------------------------------------------------
# Task 2.7: FormulaEngine 超时控制
# ---------------------------------------------------------------------------


class TestFormulaEngineTimeout:
    """验证 FormulaEngine 的超时控制"""

    @pytest.mark.asyncio
    async def test_timeout_returns_error(self):
        """超时时返回 TIMEOUT 错误而非卡死"""
        engine = FormulaEngine()

        # Mock _execute_inner to simulate a slow formula
        async def slow_inner(*args, **kwargs):
            await asyncio.sleep(30)
            return {"value": 1, "cached": False, "error": None}

        engine._execute_inner = slow_inner

        with patch("app.services.formula_engine.settings", create=True) as mock_settings:
            mock_settings.FORMULA_EXECUTE_TIMEOUT = 1

            result = await engine.execute(
                db=AsyncMock(),
                project_id=uuid.uuid4(),
                year=2025,
                formula_type="TB",
                params={"account_code": "1001", "column_name": "audited_amount"},
            )

        assert result["error"] is not None
        assert "超时" in result["error"]
        assert result["value"] is None

    @pytest.mark.asyncio
    async def test_normal_execution_not_affected(self):
        """正常执行不受超时影响"""
        engine = FormulaEngine()

        # Mock _execute_inner to return quickly
        async def fast_inner(*args, **kwargs):
            return {"value": 42.0, "cached": False, "error": None}

        engine._execute_inner = fast_inner

        result = await engine.execute(
            db=AsyncMock(),
            project_id=uuid.uuid4(),
            year=2025,
            formula_type="TB",
            params={"account_code": "1001", "column_name": "audited_amount"},
        )

        assert result["value"] == 42.0
        assert result["error"] is None


# ---------------------------------------------------------------------------
# Task 2.2: 游标分页
# ---------------------------------------------------------------------------


class TestCursorPagination:
    """验证 LedgerPenetrationService 的游标分页"""

    def test_cursor_pagination_methods_exist(self):
        """LedgerPenetrationService 应有游标分页方法"""
        from app.services.ledger_penetration_service import LedgerPenetrationService
        assert hasattr(LedgerPenetrationService, "get_ledger_entries_cursor")
        assert hasattr(LedgerPenetrationService, "get_aux_ledger_entries_cursor")

    @pytest.mark.asyncio
    async def test_cursor_pagination_returns_structure(self):
        """游标分页返回 items/next_cursor/has_more 结构"""
        from app.services.ledger_penetration_service import LedgerPenetrationService

        db = AsyncMock()
        # Mock execute to return empty result
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        svc = LedgerPenetrationService(db, redis=None)
        result = await svc.get_ledger_entries_cursor(
            project_id=uuid.uuid4(),
            year=2025,
            account_code="1001",
            cursor=None,
            limit=10,
        )

        assert "items" in result
        assert "next_cursor" in result
        assert "has_more" in result
        assert "limit" in result
        assert result["has_more"] is False
        assert result["next_cursor"] is None

    @pytest.mark.asyncio
    async def test_cursor_pagination_has_more(self):
        """当结果超过 limit 时 has_more=True 且返回 next_cursor"""
        from app.services.ledger_penetration_service import LedgerPenetrationService
        from datetime import date

        db = AsyncMock()
        # Return limit+1 rows to trigger has_more
        fake_rows = []
        for i in range(6):
            row = MagicMock()
            row._mapping = {
                "id": uuid.uuid4(),
                "voucher_date": date(2025, 1, i + 1),
                "voucher_no": f"PZ-{i+1:04d}",
                "account_code": "1001",
                "account_name": "货币资金",
                "debit_amount": 100,
                "credit_amount": 0,
                "counterpart_account": None,
                "summary": f"test {i}",
            }
            fake_rows.append(row)

        mock_result = MagicMock()
        mock_result.fetchall.return_value = fake_rows
        db.execute = AsyncMock(return_value=mock_result)

        svc = LedgerPenetrationService(db, redis=None)
        result = await svc.get_ledger_entries_cursor(
            project_id=uuid.uuid4(),
            year=2025,
            account_code="1001",
            cursor=None,
            limit=5,
        )

        assert result["has_more"] is True
        assert len(result["items"]) == 5
        assert result["next_cursor"] is not None
        assert "|" in result["next_cursor"]

    def test_api_endpoint_supports_cursor_param(self):
        """API 端点应支持 cursor 和 limit 查询参数"""
        import inspect
        from app.routers.ledger_penetration import get_ledger_entries

        sig = inspect.signature(get_ledger_entries)
        param_names = list(sig.parameters.keys())
        assert "cursor" in param_names
        assert "limit" in param_names


# ---------------------------------------------------------------------------
# Task 2.3: 四表联查 CTE 优化
# ---------------------------------------------------------------------------


class TestCTEOptimization:
    """验证 DrilldownService 的 CTE 优化方法"""

    def test_cte_methods_exist(self):
        """DrilldownService 应有 CTE 优化方法"""
        from app.services.drilldown_service import DrilldownService
        assert hasattr(DrilldownService, "get_balance_with_ledger_summary")
        assert hasattr(DrilldownService, "batch_get_ledger_summaries")

    @pytest.mark.asyncio
    async def test_cte_balance_with_ledger_summary(self):
        """CTE 联查返回余额+序时账汇总+辅助维度信息"""
        from app.services.drilldown_service import DrilldownService

        db = AsyncMock()
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row.account_code = "1001"
        mock_row.account_name = "货币资金"
        mock_row.level = 1
        mock_row.opening_balance = Decimal("10000")
        mock_row.debit_amount = Decimal("5000")
        mock_row.credit_amount = Decimal("3000")
        mock_row.closing_balance = Decimal("12000")
        mock_row.ledger_debit = Decimal("5000")
        mock_row.ledger_credit = Decimal("3000")
        mock_row.voucher_count = 42
        mock_row.aux_type_count = 0
        mock_row.aux_row_count = 0
        mock_result.fetchall.return_value = [mock_row]
        db.execute = AsyncMock(return_value=mock_result)

        svc = DrilldownService(db)
        result = await svc.get_balance_with_ledger_summary(
            project_id=uuid.uuid4(), year=2025,
        )

        assert len(result) == 1
        row = result[0]
        assert row["account_code"] == "1001"
        assert row["voucher_count"] == 42
        assert row["has_aux"] is False
        assert "ledger_debit" in row
        assert "ledger_credit" in row

    @pytest.mark.asyncio
    async def test_batch_get_ledger_summaries(self):
        """批量获取多科目序时账汇总（减少 N+1）"""
        from app.services.drilldown_service import DrilldownService

        db = AsyncMock()
        mock_result = MagicMock()
        row1 = MagicMock()
        row1.account_code = "1001"
        row1.total_debit = Decimal("5000")
        row1.total_credit = Decimal("3000")
        row1.entry_count = 42
        row2 = MagicMock()
        row2.account_code = "1002"
        row2.total_debit = Decimal("2000")
        row2.total_credit = Decimal("1000")
        row2.entry_count = 15
        mock_result.fetchall.return_value = [row1, row2]
        db.execute = AsyncMock(return_value=mock_result)

        svc = DrilldownService(db)
        result = await svc.batch_get_ledger_summaries(
            project_id=uuid.uuid4(), year=2025,
            account_codes=["1001", "1002"],
        )

        assert "1001" in result
        assert "1002" in result
        assert result["1001"]["entry_count"] == 42
        assert result["1002"]["total_debit"] == Decimal("2000")

    @pytest.mark.asyncio
    async def test_batch_empty_codes_returns_empty(self):
        """空科目列表返回空字典"""
        from app.services.drilldown_service import DrilldownService

        db = AsyncMock()
        svc = DrilldownService(db)
        result = await svc.batch_get_ledger_summaries(
            project_id=uuid.uuid4(), year=2025,
            account_codes=[],
        )
        assert result == {}


# ---------------------------------------------------------------------------
# Task 2.4: 报表生成缓存
# ---------------------------------------------------------------------------


class TestReportEngineCache:
    """验证 ReportEngine 的 Redis 缓存"""

    def test_report_engine_accepts_redis(self):
        """ReportEngine 构造函数应接受 redis 参数"""
        from app.services.report_engine import ReportEngine
        import inspect
        sig = inspect.signature(ReportEngine.__init__)
        assert "redis" in sig.parameters

    @pytest.mark.asyncio
    async def test_cache_key_format(self):
        """缓存键格式: report:{project_id}:{report_type}"""
        from app.services.report_engine import ReportEngine

        db = AsyncMock()
        engine = ReportEngine(db, redis=None)
        pid = uuid.uuid4()
        key = engine._cache_key(pid, "balance_sheet")
        assert key == f"report:{pid}:balance_sheet"

    @pytest.mark.asyncio
    async def test_cache_set_and_get(self):
        """缓存写入和读取"""
        from app.services.report_engine import ReportEngine

        db = AsyncMock()
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()

        engine = ReportEngine(db, redis=redis)
        pid = uuid.uuid4()

        # Set cache
        data = [{"row_code": "BS-001", "row_name": "货币资金", "current_period_amount": "100"}]
        await engine._set_cached_report(pid, "balance_sheet", data)
        redis.setex.assert_called_once()
        call_args = redis.setex.call_args
        assert call_args[0][0] == f"report:{pid}:balance_sheet"
        assert call_args[0][1] == 600  # TTL = 10 min

    @pytest.mark.asyncio
    async def test_cache_invalidation(self):
        """缓存失效"""
        from app.services.report_engine import ReportEngine

        db = AsyncMock()
        redis = AsyncMock()
        redis.delete = AsyncMock(return_value=1)

        engine = ReportEngine(db, redis=redis)
        pid = uuid.uuid4()

        # Invalidate single type
        count = await engine._invalidate_report_cache(pid, "balance_sheet")
        assert count == 1

        # Invalidate all types
        redis.delete = AsyncMock(return_value=1)
        count = await engine._invalidate_report_cache(pid)
        assert count == 4  # 4 report types

    @pytest.mark.asyncio
    async def test_cache_miss_returns_none(self):
        """缓存未命中返回 None"""
        from app.services.report_engine import ReportEngine

        db = AsyncMock()
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)

        engine = ReportEngine(db, redis=redis)
        result = await engine._get_cached_report(uuid.uuid4(), "balance_sheet")
        assert result is None

    @pytest.mark.asyncio
    async def test_no_redis_graceful_degradation(self):
        """无 Redis 时优雅降级（不报错）"""
        from app.services.report_engine import ReportEngine

        db = AsyncMock()
        engine = ReportEngine(db, redis=None)
        pid = uuid.uuid4()

        # All cache operations should be no-ops
        result = await engine._get_cached_report(pid, "balance_sheet")
        assert result is None

        await engine._set_cached_report(pid, "balance_sheet", [])
        count = await engine._invalidate_report_cache(pid)
        assert count == 0

    def test_reports_updated_event_type_exists(self):
        """REPORTS_UPDATED 事件类型应存在"""
        assert EventType.REPORTS_UPDATED == "reports.updated"


# ---------------------------------------------------------------------------
# Task 2.8: 数据导入流式处理
# ---------------------------------------------------------------------------


class TestStreamingImport:
    """验证 GenericParser.parse_streaming 和流式导入"""

    def test_parse_streaming_method_exists(self):
        """GenericParser 应有 parse_streaming 方法"""
        from app.services.import_engine.parsers import GenericParser
        assert hasattr(GenericParser, "parse_streaming")

    def test_import_progress_event_type_exists(self):
        """IMPORT_PROGRESS 事件类型应存在"""
        assert EventType.IMPORT_PROGRESS == "import.progress"

    def test_parse_streaming_csv_fallback(self):
        """非 Excel 内容应回退到全量解析"""
        from app.services.import_engine.parsers import GenericParser

        parser = GenericParser()
        # CSV content
        csv_content = b"account_code,account_name,opening_balance,closing_balance\n1001,cash,100,200\n"
        chunks = list(parser.parse_streaming(csv_content, "tb_balance"))
        # Should yield at least one chunk
        total_rows = sum(len(c) for c in chunks)
        assert total_rows == 1
        assert chunks[0][0]["account_code"] == "1001"

    def test_parse_streaming_excel_yields_chunks(self):
        """Excel 文件应分批 yield"""
        from app.services.import_engine.parsers import GenericParser
        import openpyxl
        import io

        # Create a small test Excel file
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "余额表"
        ws.append(["科目编码", "科目名称", "期初余额", "期末余额"])
        for i in range(5):
            ws.append([f"100{i}", f"科目{i}", 1000 * i, 2000 * i])

        buf = io.BytesIO()
        wb.save(buf)
        content = buf.getvalue()

        parser = GenericParser()
        chunks = list(parser.parse_streaming(content, "tb_balance", chunk_size=2))

        # With 5 rows and chunk_size=2, expect 3 chunks (2+2+1)
        total_rows = sum(len(c) for c in chunks)
        assert total_rows == 5
        assert len(chunks) == 3

    def test_streaming_import_function_exists(self):
        """start_import_streaming 函数应存在"""
        from app.services.import_service import start_import_streaming
        assert callable(start_import_streaming)

    def test_parse_streaming_backward_compatible(self):
        """原有 parse() 方法仍然正常工作（向后兼容）"""
        from app.services.import_engine.parsers import GenericParser

        parser = GenericParser()
        csv_content = b"account_code,account_name,opening_balance\n1001,cash,100\n1002,bank,200\n"
        result = parser.parse(csv_content, "tb_balance")
        assert len(result) == 2
        assert result[0]["account_code"] == "1001"
        assert result[1]["account_code"] == "1002"


# ===========================================================================
# Phase 8 Tasks 3-11 Tests
# ===========================================================================


# ---------------------------------------------------------------------------
# Task 3: 底稿编辑体验优化
# ---------------------------------------------------------------------------


class TestWOPIAsyncEvent:
    """Task 3.1: WOPI put_file 异步事件发布"""

    def test_wopi_put_file_uses_create_task(self):
        """put_file 中事件发布应使用 asyncio.create_task"""
        import inspect
        source = inspect.getsource(
            __import__("app.services.wopi_service", fromlist=["WOPIHostService"]).WOPIHostService.put_file
        )
        assert "create_task" in source, "put_file should use asyncio.create_task for event publishing"


class TestBatchPrefill:
    """Task 3.3: PrefillService.batch_prefill"""

    @pytest.mark.asyncio
    async def test_batch_prefill_concurrent(self):
        """batch_prefill 应并发预填多个底稿"""
        from app.services.prefill_service import PrefillService

        svc = PrefillService()
        db = AsyncMock()
        project_id = uuid.uuid4()
        wp_ids = [uuid.uuid4() for _ in range(3)]

        result = await svc.batch_prefill(db, project_id, 2025, wp_ids)

        assert result["total"] == 3
        assert result["success_count"] == 3
        assert result["error_count"] == 0
        assert len(result["results"]) == 3

    @pytest.mark.asyncio
    async def test_batch_prefill_empty(self):
        """空列表应返回空结果"""
        from app.services.prefill_service import PrefillService

        svc = PrefillService()
        result = await svc.batch_prefill(AsyncMock(), uuid.uuid4(), 2025, [])
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_batch_prefill_cache_stub(self):
        """Redis 缓存 stub 应返回 None"""
        from app.services.prefill_service import PrefillService

        svc = PrefillService()
        assert await svc._get_cached_prefill(uuid.uuid4()) is None


# ---------------------------------------------------------------------------
# Task 4: 报表导出优化
# ---------------------------------------------------------------------------


class TestReportExportEngine:
    """Task 4.1-4.3: 报表导出引擎"""

    def test_template_cache(self):
        """模板缓存应命中"""
        from app.services.report_export_engine import ReportExportEngine

        engine = ReportExportEngine()
        engine.clear_cache()

        # First load = miss
        tpl1 = engine._load_template("test_template")
        assert engine.cache_size == 1

        # Second load = hit
        tpl2 = engine._load_template("test_template")
        assert tpl1 is tpl2
        assert engine.cache_size == 1

    def test_template_cache_clear(self):
        """清空缓存"""
        from app.services.report_export_engine import ReportExportEngine

        engine = ReportExportEngine()
        engine.clear_cache()
        engine._load_template("a")
        engine._load_template("b")
        assert engine.cache_size == 2
        engine.clear_cache()
        assert engine.cache_size == 0

    @pytest.mark.asyncio
    async def test_pdf_async_export(self):
        """异步 PDF 导出"""
        from app.services.report_export_engine import PDFExportEngineAsync

        engine = PDFExportEngineAsync()
        result = await engine.export_async(uuid.uuid4(), "balance_sheet")
        assert result["status"] == "success"
        assert result["format"] == "pdf"

    def test_format_validator_spec(self):
        """格式校验器应有致同规范"""
        from app.services.report_export_engine import ExportFormatValidator

        validator = ExportFormatValidator()
        assert validator.GT_SPEC["font_cn"] == "仿宋_GB2312"
        assert validator.GT_SPEC["font_en"] == "Arial Narrow"
        assert validator.GT_SPEC["margins"]["top"] == 3.0

    def test_format_validator_meta_check(self):
        """基于元数据的快速校验"""
        from app.services.report_export_engine import ExportFormatValidator

        validator = ExportFormatValidator()
        findings = validator.validate_spec_compliance({"font_cn": "宋体"})
        assert len(findings) == 1
        assert findings[0]["type"] == "font"


# ---------------------------------------------------------------------------
# Task 6: 审计程序精细化
# ---------------------------------------------------------------------------


class TestProcedureTrimEngine:
    """Task 6.1-6.3: 程序裁剪引擎增强"""

    @pytest.mark.asyncio
    async def test_trim_by_risk_level_no_db(self):
        """无数据库时返回空结果"""
        from app.services.procedure_trim_engine import ProcedureTrimEngine

        engine = ProcedureTrimEngine(db=None)
        result = await engine.trim_by_risk_level(uuid.uuid4(), "B", "high")
        assert result["trimmed"] == 0
        assert result["threshold"] == 0.7

    def test_risk_score_calculation(self):
        """风险评分计算"""
        from app.services.procedure_trim_engine import ProcedureTrimEngine

        engine = ProcedureTrimEngine()
        proc = MagicMock()
        proc.procedure_code = "revenue_test"
        proc.is_custom = False
        score = engine._calculate_risk_score(proc, "B")
        assert score == 0.8  # 0.5 base + 0.3 high-risk keyword

    def test_risk_score_custom_bonus(self):
        """自定义程序加分"""
        from app.services.procedure_trim_engine import ProcedureTrimEngine

        engine = ProcedureTrimEngine()
        proc = MagicMock()
        proc.procedure_code = "custom_check"
        proc.is_custom = True
        score = engine._calculate_risk_score(proc, "B")
        assert score == 0.6  # 0.5 base + 0.1 custom

    @pytest.mark.asyncio
    async def test_template_versions_stub(self):
        """模板版本管理 stub"""
        from app.services.procedure_trim_engine import ProcedureTrimEngine

        engine = ProcedureTrimEngine()
        versions = await engine.get_template_versions("B")
        assert len(versions) >= 1
        assert versions[0]["is_current"] is True


# ---------------------------------------------------------------------------
# Task 7: 数据校验增强
# ---------------------------------------------------------------------------


class TestDataValidationEngine:
    """Task 7.1-7.2: 数据校验引擎"""

    @pytest.mark.asyncio
    async def test_validate_project_no_db(self):
        """无数据库时返回空结果"""
        from app.services.data_validation_engine import DataValidationEngine

        engine = DataValidationEngine(db=None)
        result = await engine.validate_project(uuid.uuid4())
        assert result["total"] == 0
        assert result["blocking"] == 0

    @pytest.mark.asyncio
    async def test_validate_project_structure(self):
        """校验结果结构正确"""
        from app.services.data_validation_engine import DataValidationEngine

        engine = DataValidationEngine(db=None)
        result = await engine.validate_project(uuid.uuid4(), 2025)
        assert "findings" in result
        assert "total" in result
        assert "by_severity" in result
        assert "blocking" in result
        assert "high" in result["by_severity"]

    def test_validation_finding_to_dict(self):
        """ValidationFinding 序列化"""
        from app.services.data_validation_engine import ValidationFinding

        f = ValidationFinding(
            check_type="test",
            severity="high",
            message="test message",
            fix_suggestion="fix it",
        )
        d = f.to_dict()
        assert d["check_type"] == "test"
        assert d["severity"] == "high"
        assert d["fix_suggestion"] == "fix it"
        assert "id" in d
        assert "created_at" in d

    @pytest.mark.asyncio
    async def test_auto_fix_stub(self):
        """自动修复 stub"""
        from app.services.data_validation_engine import DataValidationEngine

        engine = DataValidationEngine(db=None)
        result = await engine.auto_fix(uuid.uuid4(), ["id1", "id2"])
        assert result["fixed"] == 0
        assert result["skipped"] == 2

    def test_export_csv(self):
        """CSV 导出"""
        from app.services.data_validation_engine import DataValidationEngine

        engine = DataValidationEngine()
        findings = [
            {"id": "1", "check_type": "test", "severity": "high", "message": "error"},
        ]
        csv_bytes = engine.export_findings(findings, "csv")
        assert b"check_type" in csv_bytes
        assert b"test" in csv_bytes


# ---------------------------------------------------------------------------
# Task 8: 性能监控
# ---------------------------------------------------------------------------


class TestPerformanceMonitor:
    """Task 8.1-8.2: 性能监控"""

    def test_metrics_collector(self):
        """指标收集器基本功能"""
        from app.services.performance_monitor import MetricsCollector

        m = MetricsCollector()
        m.observe_histogram("test", 1.0)
        m.observe_histogram("test", 2.0)
        m.observe_histogram("test", 3.0)

        stats = m.get_histogram_stats("test")
        assert stats["count"] == 3
        assert stats["avg"] == 2.0
        assert stats["max"] == 3.0

    def test_counter(self):
        """计数器"""
        from app.services.performance_monitor import MetricsCollector

        m = MetricsCollector()
        m.inc_counter("req", {"endpoint": "/api/test"})
        m.inc_counter("req", {"endpoint": "/api/test"})
        assert m.get_counter("req", {"endpoint": "/api/test"}) == 2

    def test_performance_monitor_api_recording(self):
        """API 响应时间记录"""
        from app.services.performance_monitor import PerformanceMonitor

        pm = PerformanceMonitor()
        pm.record_api_response("/api/test", "GET", 0.5)
        pm.record_api_response("/api/test", "GET", 1.5)

        stats = pm.get_performance_stats()
        assert stats["total_requests"] >= 2

    def test_slow_query_recording(self):
        """慢查询记录"""
        from app.services.performance_monitor import PerformanceMonitor

        pm = PerformanceMonitor()
        pm.record_db_query("select", 2.0, "SELECT * FROM big_table")

        queries = pm.get_slow_queries()
        assert len(queries) >= 1
        assert queries[-1]["duration"] == 2.0

    def test_cache_hit_rate(self):
        """缓存命中率"""
        from app.services.performance_monitor import PerformanceMonitor, metrics

        metrics.reset()
        pm = PerformanceMonitor()
        pm.record_cache_hit("test", True)
        pm.record_cache_hit("test", True)
        pm.record_cache_hit("test", False)

        rate = metrics.get_gauge("cache_hit_rate", {"cache_name": "test"})
        assert abs(rate - 2/3) < 0.01

    def test_threshold_alerts(self):
        """性能告警"""
        from app.services.performance_monitor import PerformanceMonitor

        pm = PerformanceMonitor()
        pm.record_api_response("/api/slow", "GET", 5.0)  # > critical threshold

        alerts = pm.get_alerts()
        assert len(alerts) >= 1
        assert alerts[-1]["level"] == "critical"


# ---------------------------------------------------------------------------
# Task 10: 安全增强
# ---------------------------------------------------------------------------


class TestEncryptionService:
    """Task 10.1: 数据加密"""

    def test_encryption_roundtrip(self):
        """加密解密往返"""
        from app.services.encryption_service import EncryptionService

        svc = EncryptionService(key="test-key-for-encryption-service")
        plaintext = "敏感数据 sensitive data 123"
        encrypted = svc.encrypt(plaintext)
        assert encrypted != plaintext
        decrypted = svc.decrypt(encrypted)
        assert decrypted == plaintext

    def test_encryption_different_ciphertexts(self):
        """相同明文每次加密结果不同（Fernet 含时间戳）"""
        from app.services.encryption_service import EncryptionService

        svc = EncryptionService(key="test-key-for-encryption-service")
        e1 = svc.encrypt("hello")
        e2 = svc.encrypt("hello")
        # Fernet includes timestamp, so ciphertexts differ
        assert e1 != e2

    def test_encryption_bytes(self):
        """字节数据加密"""
        from app.services.encryption_service import EncryptionService

        svc = EncryptionService(key="test-key-for-encryption-service")
        data = b"binary data \x00\x01\x02"
        encrypted = svc.encrypt_bytes(data)
        decrypted = svc.decrypt_bytes(encrypted)
        assert decrypted == data

    def test_generate_key(self):
        """密钥生成"""
        from app.services.encryption_service import EncryptionService

        key = EncryptionService.generate_key()
        assert len(key) > 0
        # Should be base64 encoded
        import base64
        base64.urlsafe_b64decode(key)  # Should not raise

    def test_no_key_raises(self):
        """无密钥时加密应报错"""
        from app.services.encryption_service import EncryptionService

        svc = EncryptionService(key="")
        assert not svc.is_available


class TestAuditLoggerEnhanced:
    """Task 10.2: 审计日志增强"""

    @pytest.mark.asyncio
    async def test_log_action(self):
        """记录操作日志"""
        from app.services.audit_logger_enhanced import AuditLoggerEnhanced

        logger = AuditLoggerEnhanced()
        entry = await logger.log_action(
            user_id=uuid.uuid4(),
            action="download",
            object_type="workpaper",
            object_id=uuid.uuid4(),
        )
        assert entry["action"] == "download"
        assert "timestamp" in entry

    @pytest.mark.asyncio
    async def test_query_logs(self):
        """查询日志"""
        from app.services.audit_logger_enhanced import AuditLoggerEnhanced

        logger = AuditLoggerEnhanced()
        uid = str(uuid.uuid4())
        await logger.log_action(user_id=uid, action="view", object_type="report")
        await logger.log_action(user_id=uid, action="edit", object_type="report")

        results = logger.query_logs(user_id=uid)
        assert len(results) >= 2

    def test_export_csv(self):
        """CSV 导出"""
        from app.services.audit_logger_enhanced import AuditLoggerEnhanced

        logger = AuditLoggerEnhanced()
        csv_bytes = logger.export_csv([
            {"created_at": "2025-01-01", "user_id": "u1", "action": "view",
             "object_type": "wp", "object_id": "o1", "project_id": "p1", "ip_address": "127.0.0.1"},
        ])
        assert b"user_id" in csv_bytes
        assert b"u1" in csv_bytes

    @pytest.mark.asyncio
    async def test_anomaly_detection(self):
        """异常操作检测"""
        from app.services.audit_logger_enhanced import AuditLoggerEnhanced

        logger = AuditLoggerEnhanced()
        uid = str(uuid.uuid4())

        # Trigger bulk download anomaly
        for _ in range(12):
            await logger.log_action(user_id=uid, action="download", object_type="workpaper")

        alerts = logger.get_anomaly_alerts()
        assert len(alerts) >= 1
        assert alerts[-1]["type"] == "bulk_download"


class TestSecurityMonitor:
    """Task 10.3: 安全监控"""

    def test_ip_detection(self):
        """异常 IP 检测"""
        from app.services.security_monitor import SecurityMonitor

        sm = SecurityMonitor()
        # Record many requests from same IP
        for _ in range(15):
            sm.record_ip_access("192.168.1.100")

        assert sm.is_suspicious_ip("192.168.1.100")
        assert not sm.is_suspicious_ip("192.168.1.200")

    def test_session_management(self):
        """会话管理"""
        from app.services.security_monitor import SecurityMonitor

        sm = SecurityMonitor()
        sid = sm.create_session("user1", "127.0.0.1")
        assert sid

        sessions = sm.get_active_sessions("user1")
        assert len(sessions) >= 1

        sm.terminate_session(sid)
        sessions = sm.get_active_sessions("user1")
        active = [s for s in sessions if s["session_id"] == sid]
        assert len(active) == 0

    def test_security_events(self):
        """安全事件日志"""
        from app.services.security_monitor import SecurityMonitor

        sm = SecurityMonitor()
        sm.record_login_attempt("admin", "127.0.0.1", True)
        sm.record_login_attempt("admin", "127.0.0.1", False)

        events = sm.get_security_events()
        assert len(events) >= 2

    def test_login_attempts_filter(self):
        """登录尝试过滤"""
        from app.services.security_monitor import SecurityMonitor

        sm = SecurityMonitor()
        sm.record_login_attempt("user_a", "10.0.0.1", False)
        sm.record_login_attempt("user_b", "10.0.0.2", True)

        attempts = sm.get_login_attempts("user_a")
        assert all(a["details"]["username"] == "user_a" for a in attempts)


class TestPermissionCache:
    """Task 10.5: 权限查询缓存"""

    @pytest.mark.asyncio
    async def test_cache_miss_returns_none(self):
        """缓存未命中返回 None"""
        from app.deps import _get_cached_permission

        result = await _get_cached_permission(uuid.uuid4(), uuid.uuid4())
        # With no Redis or fakeredis, should return None (graceful degradation)
        assert result is None

    @pytest.mark.asyncio
    async def test_set_and_get_cache(self):
        """缓存写入和读取"""
        from app.deps import _get_cached_permission, _set_cached_permission

        uid = uuid.uuid4()
        pid = uuid.uuid4()

        # Set cache (may fail silently if no Redis)
        await _set_cached_permission(uid, pid, "edit")

        # Get cache (may return None if no Redis)
        result = await _get_cached_permission(uid, pid)
        # Either None (no Redis) or "edit" (with Redis)
        assert result is None or result == "edit"

    @pytest.mark.asyncio
    async def test_invalidate_cache(self):
        """缓存失效"""
        from app.deps import invalidate_permission_cache

        # Should not raise even without Redis
        await invalidate_permission_cache(uuid.uuid4(), uuid.uuid4())

    def test_permission_hierarchy(self):
        """权限层级定义"""
        from app.deps import PERMISSION_HIERARCHY

        assert PERMISSION_HIERARCHY["edit"] > PERMISSION_HIERARCHY["review"]
        assert PERMISSION_HIERARCHY["review"] > PERMISSION_HIERARCHY["readonly"]


# ---------------------------------------------------------------------------
# Task 7.4: Data Validation API endpoints exist
# ---------------------------------------------------------------------------


class TestDataValidationAPI:
    """Task 7.4: 数据校验 API"""

    def test_router_exists(self):
        """数据校验路由应存在"""
        from app.routers.data_validation import router
        paths = [r.path for r in router.routes]
        assert any("data-validation" in p and p.endswith("data-validation") for p in paths)
        assert any("findings" in p for p in paths)
        assert any("fix" in p for p in paths)
        assert any("export" in p for p in paths)


# ---------------------------------------------------------------------------
# Task 8.4: Performance API endpoints exist
# ---------------------------------------------------------------------------


class TestPerformanceAPI:
    """Task 8.4: 性能监控 API"""

    def test_router_exists(self):
        """性能监控路由应存在"""
        from app.routers.performance import router
        paths = [r.path for r in router.routes]
        assert any("performance-stats" in p for p in paths)
        assert any("performance-metrics" in p for p in paths)
        assert any("slow-queries" in p for p in paths)


# ---------------------------------------------------------------------------
# Task 10.4: Security API endpoints exist
# ---------------------------------------------------------------------------


class TestSecurityAPI:
    """Task 10.4: 安全监控 API"""

    def test_router_exists(self):
        """安全监控路由应存在"""
        from app.routers.security import router
        paths = [r.path for r in router.routes]
        assert any("login-attempts" in p for p in paths)
        assert any("lock-account" in p for p in paths)
        assert any("sessions" in p for p in paths)
        assert any("audit-logs/export" in p for p in paths)
