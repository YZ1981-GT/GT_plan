"""Phase 10 Step 4-21 tests — 过程记录/LLM底稿/抽样增强/合并增强/复核对话/批注/论坛/溯源/打卡/汇总/权限/快照/推荐/差异/分类/排版"""

import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date, datetime


# ── Task 4: 过程记录 ─────────────────────────────────────

class TestProcessRecordService:

    @pytest.mark.asyncio
    async def test_record_workpaper_edit(self):
        from app.services.process_record_service import ProcessRecordService
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        svc = ProcessRecordService()
        result = await svc.record_workpaper_edit(
            db, uuid4(), uuid4(), uuid4(), 3, "更新了审定数"
        )
        assert result["action"] == "workpaper_edit"
        assert "log_id" in result

    @pytest.mark.asyncio
    async def test_get_edit_history_empty(self):
        from app.services.process_record_service import ProcessRecordService
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)
        svc = ProcessRecordService()
        result = await svc.get_edit_history(db, uuid4(), uuid4())
        assert result == []


class TestAIContentTagService:

    @pytest.mark.asyncio
    async def test_confirm_invalid_status(self):
        from app.services.process_record_service import AIContentTagService
        db = AsyncMock()
        svc = AIContentTagService()
        with pytest.raises(ValueError, match="无效状态"):
            await svc.confirm_ai_content(db, uuid4(), "invalid", uuid4())

    @pytest.mark.asyncio
    async def test_check_unconfirmed(self):
        from app.services.process_record_service import AIContentTagService
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 3
        db.execute = AsyncMock(return_value=mock_result)
        svc = AIContentTagService()
        result = await svc.check_unconfirmed(db, uuid4(), uuid4())
        assert result["has_unconfirmed"] is True
        assert result["unconfirmed_count"] == 3
        assert result["can_submit_review"] is False


# ── Task 5: LLM 底稿对话 ─────────────────────────────────

class TestWpChatService:

    def test_extract_fill_suggestion(self):
        from app.services.wp_chat_service import WpChatService
        svc = WpChatService()
        text = "建议填入 [FILL:B5=12345.67] 和 [FILL:C10=审计已确认]"
        result = svc._extract_fill_suggestion(text)
        assert len(result) == 2
        assert result[0]["cell_ref"] == "B5"
        assert result[0]["value"] == "12345.67"

    def test_extract_fill_suggestion_none(self):
        from app.services.wp_chat_service import WpChatService
        svc = WpChatService()
        result = svc._extract_fill_suggestion("没有填充建议的普通回复")
        assert result is None

    def test_build_system_prompt(self):
        from app.services.wp_chat_service import WpChatService
        svc = WpChatService()
        wp_info = {"wp_code": "E9-1", "wp_name": "固定资产审定表", "audit_cycle": "E"}
        prompt = svc._build_system_prompt(wp_info, {"selected_cell": "B15"})
        assert "E9-1" in prompt
        assert "B15" in prompt

    @pytest.mark.asyncio
    async def test_generate_ledger_analysis_empty(self):
        from app.services.wp_chat_service import WpChatService
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)
        svc = WpChatService()
        result = await svc.generate_ledger_analysis(db, uuid4())
        assert result["entries_analyzed"] == 0


# ── Task 6: 抽样增强 ─────────────────────────────────────

class TestCutoffTestService:

    @pytest.mark.asyncio
    async def test_cutoff_test_empty(self):
        from app.services.sampling_enhanced_service import CutoffTestService
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)
        svc = CutoffTestService()
        result = await svc.run_cutoff_test(db, uuid4(), 2025, ["6001"])
        assert result["total_entries"] == 0
        assert "2025-12-31" in result["period_end"]


class TestAgingAnalysisService:

    def test_fifo_aging_basic(self):
        from app.services.sampling_enhanced_service import AgingAnalysisService
        svc = AgingAnalysisService()
        # 模拟借贷记录
        entries = []
        for d, debit, credit in [
            (date(2024, 6, 1), 10000, 0),
            (date(2024, 9, 1), 5000, 0),
            (date(2025, 1, 1), 0, 8000),  # 核销最早的借方
        ]:
            e = MagicMock()
            e.debit_amount = debit
            e.credit_amount = credit
            e.voucher_date = d
            entries.append(e)

        brackets = [
            {"label": "1年以内", "min_days": 0, "max_days": 365},
            {"label": "1-2年", "min_days": 366, "max_days": 730},
        ]
        result = svc._fifo_aging(entries, date(2025, 12, 31), brackets)
        # 10000 借方被核销 8000，剩余 2000（2024-06-01，账龄 ~579天）
        # 5000 借方未核销（2024-09-01，账龄 ~487天）
        assert result["total"] == 7000.0
        assert len(result["brackets"]) == 2

    def test_fifo_aging_all_settled(self):
        from app.services.sampling_enhanced_service import AgingAnalysisService
        svc = AgingAnalysisService()
        entries = []
        e1 = MagicMock()
        e1.debit_amount = 1000
        e1.credit_amount = 0
        e1.voucher_date = date(2025, 1, 1)
        entries.append(e1)
        e2 = MagicMock()
        e2.debit_amount = 0
        e2.credit_amount = 1000
        e2.voucher_date = date(2025, 6, 1)
        entries.append(e2)
        brackets = [{"label": "1年以内", "min_days": 0, "max_days": 365}]
        result = svc._fifo_aging(entries, date(2025, 12, 31), brackets)
        assert result["total"] == 0.0

    @pytest.mark.asyncio
    async def test_analyze_aging_empty(self):
        from app.services.sampling_enhanced_service import AgingAnalysisService
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)
        svc = AgingAnalysisService()
        result = await svc.analyze_aging(
            db, uuid4(), "1122",
            [{"label": "1年以内", "min_days": 0, "max_days": 365}],
            "2025-12-31",
        )
        assert result["details"] == []


class TestMonthlyDetailService:

    @pytest.mark.asyncio
    async def test_monthly_detail_empty(self):
        from app.services.sampling_enhanced_service import MonthlyDetailService
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        db.execute = AsyncMock(return_value=mock_result)
        svc = MonthlyDetailService()
        result = await svc.generate_monthly_detail(db, uuid4(), "6001", 2025)
        assert result["months"] == []


# ── Task 8: 复核对话 ─────────────────────────────────────

class TestReviewConversationService:

    @pytest.mark.asyncio
    async def test_create_conversation(self):
        from app.services.review_conversation_service import ReviewConversationService
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        svc = ReviewConversationService()
        result = await svc.create_conversation(
            db, uuid4(), uuid4(), uuid4(), "workpaper", uuid4(), None, "测试对话"
        )
        assert result["title"] == "测试对话"
        assert result["status"] == "open"

    @pytest.mark.asyncio
    async def test_close_conversation_not_found(self):
        from app.services.review_conversation_service import ReviewConversationService
        db = AsyncMock()
        db.get = AsyncMock(return_value=None)
        svc = ReviewConversationService()
        with pytest.raises(ValueError, match="对话不存在"):
            await svc.close_conversation(db, uuid4(), uuid4())

    @pytest.mark.asyncio
    async def test_close_conversation_permission(self):
        from app.services.review_conversation_service import ReviewConversationService
        db = AsyncMock()
        conv = MagicMock()
        conv.initiator_id = uuid4()
        db.get = AsyncMock(return_value=conv)
        svc = ReviewConversationService()
        with pytest.raises(PermissionError, match="仅发起人"):
            await svc.close_conversation(db, uuid4(), uuid4())  # 不同 user_id

    @pytest.mark.asyncio
    async def test_send_message(self):
        from app.services.review_conversation_service import ReviewConversationService
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.get = AsyncMock(return_value=None)  # event_bus 查询
        svc = ReviewConversationService()
        result = await svc.send_message(db, uuid4(), uuid4(), "测试消息")
        assert result["content"] == "测试消息"
        assert result["message_type"] == "text"


# ── Task 11: 论坛 ────────────────────────────────────────

class TestForumService:

    @pytest.mark.asyncio
    async def test_create_post(self):
        from app.services.forum_service import ForumService
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        svc = ForumService()
        result = await svc.create_post(db, uuid4(), "测试帖子", "内容", "share")
        assert result["title"] == "测试帖子"
        assert result["category"] == "share"

    @pytest.mark.asyncio
    async def test_create_anonymous_post(self):
        from app.services.forum_service import ForumService
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        svc = ForumService()
        result = await svc.create_post(db, uuid4(), "匿名帖", "内容", "vent", True)
        assert result["is_anonymous"] is True
        assert result["author_id"] is None

    @pytest.mark.asyncio
    async def test_like_post_not_found(self):
        from app.services.forum_service import ForumService
        db = AsyncMock()
        db.get = AsyncMock(return_value=None)
        svc = ForumService()
        with pytest.raises(ValueError, match="帖子不存在"):
            await svc.like_post(db, uuid4())


# ── Task 15: 批注 ────────────────────────────────────────

class TestAnnotationService:

    @pytest.mark.asyncio
    async def test_create_annotation(self):
        from app.services.annotation_service import AnnotationService
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        svc = AnnotationService()
        result = await svc.create_annotation(
            db, uuid4(), uuid4(), "workpaper", uuid4(), "测试批注", "B15", "high"
        )
        assert result["content"] == "测试批注"
        assert result["priority"] == "high"

    @pytest.mark.asyncio
    async def test_update_annotation_invalid_status(self):
        from app.services.annotation_service import AnnotationService
        db = AsyncMock()
        ann = MagicMock()
        ann.id = uuid4()
        db.get = AsyncMock(return_value=ann)
        svc = AnnotationService()
        with pytest.raises(ValueError, match="无效状态"):
            await svc.update_annotation(db, ann.id, "invalid_status")

    @pytest.mark.asyncio
    async def test_update_annotation_not_found(self):
        from app.services.annotation_service import AnnotationService
        db = AsyncMock()
        db.get = AsyncMock(return_value=None)
        svc = AnnotationService()
        with pytest.raises(ValueError, match="批注不存在"):
            await svc.update_annotation(db, uuid4(), "resolved")


# ── Task 7: 合并增强 ─────────────────────────────────────

class TestConsolLockService:

    @pytest.mark.asyncio
    async def test_lock_project(self):
        from app.services.consol_enhanced_service import ConsolLockService
        db = AsyncMock()
        db.execute = AsyncMock()
        db.flush = AsyncMock()
        svc = ConsolLockService()
        result = await svc.lock_project(db, uuid4(), uuid4())
        assert result["locked"] is True

    @pytest.mark.asyncio
    async def test_unlock_project(self):
        from app.services.consol_enhanced_service import ConsolLockService
        db = AsyncMock()
        db.execute = AsyncMock()
        db.flush = AsyncMock()
        svc = ConsolLockService()
        result = await svc.unlock_project(db, uuid4())
        assert result["locked"] is False


class TestIndependentModuleService:

    @pytest.mark.asyncio
    async def test_create_temp_project_invalid(self):
        from app.services.consol_enhanced_service import IndependentModuleService
        db = AsyncMock()
        svc = IndependentModuleService()
        with pytest.raises(ValueError, match="不支持的模块"):
            await svc.create_temp_project(db, "invalid", uuid4())


# ── Task 9: 溯源 ─────────────────────────────────────────

class TestReportTraceService:

    @pytest.mark.asyncio
    async def test_trace_section_basic(self):
        from app.services.report_trace_service import ReportTraceService
        db = AsyncMock()
        # 模拟所有查询返回空
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)
        svc = ReportTraceService()
        result = await svc.trace_section(db, uuid4(), "五、9")
        assert result["section_number"] == "五、9"


# ── 模型导入测试 ──────────────────────────────────────────

class TestPhase10Imports:

    def test_import_services(self):
        from app.services.process_record_service import ProcessRecordService, AttachmentLinkService, AIContentTagService
        from app.services.wp_chat_service import WpChatService
        from app.services.sampling_enhanced_service import CutoffTestService, AgingAnalysisService, MonthlyDetailService
        from app.services.review_conversation_service import ReviewConversationService
        from app.services.annotation_service import AnnotationService
        from app.services.forum_service import ForumService
        from app.services.consol_enhanced_service import ConsolLockService, IndependentModuleService
        from app.services.report_trace_service import ReportTraceService
        assert True

    def test_import_routers(self):
        from app.routers.process_record import router
        from app.routers.wp_chat import router
        from app.routers.sampling_enhanced import router
        from app.routers.review_conversations import router
        from app.routers.annotations import router
        from app.routers.forum import router
        from app.routers.report_trace import router
        assert True
