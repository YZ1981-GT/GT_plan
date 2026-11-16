"""test_regulatory_letter_service — A18-2 监管沟通函 service 单元测试

覆盖:
- check_completeness：未选适用性 / 不适用 / 适用+有内容 / 适用但无内容
- a18_check_incomplete：统一 check 契约 {complete, missing_fields, wp_code, reason}
- export_word：模板调用（mock filler）
- get_a8_step_suggestion：映射逻辑

🔴 夹具形状必须等于真实写入方（``useA182RegulatoryCommunication.ts``）：item_id 前缀
``a182-``，适用性与内容分开两行（``-applicability`` / ``-content``），值在 ``remark``，
``conclusion`` 恒 ``null``（spec ``api-prefix-fix-recovery`` 任务 4）。
"""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.regulatory_letter_service import (
    RegulatoryLetterService,
    a18_check_incomplete,
    a18_export_word,
    get_a8_step_suggestion,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


def _rows(**matters):
    """按真实写入形状构造 checklist_responses 行。

    ``_rows(m1="Y", c1="内容", m2="N", m3="NA", m4="Y", c4="其他内容")``
    """
    rows: list[dict] = []
    for i in range(1, 5):
        applicability = matters.get(f"m{i}")
        if applicability is not None:
            rows.append(
                {
                    "item_id": f"a182-matter{i}-applicability",
                    "conclusion": None,
                    "remark": applicability,
                }
            )
        content = matters.get(f"c{i}")
        if content is not None:
            rows.append(
                {
                    "item_id": f"a182-matter{i}-content",
                    "conclusion": None,
                    "remark": content,
                }
            )
    return rows


def _make_db(responses: list[dict] | None = None, project_row: dict | None = None):
    """创建 mock AsyncSession（按 SQL 文本分流）。"""
    db = AsyncMock()

    async def _execute(stmt, params=None):
        result = MagicMock()
        sql_text = str(stmt.text) if hasattr(stmt, "text") else str(stmt)

        if "FROM checklist_responses" in sql_text:
            result.mappings.return_value.all.return_value = responses or []
        elif "FROM projects" in sql_text:
            result.mappings.return_value.first.return_value = (
                project_row
                if project_row is not None
                else {"client_name": "测试公司", "audit_period_end": MagicMock(year=2025)}
            )
        else:
            result.mappings.return_value.all.return_value = []
        return result

    db.execute = _execute
    return db


# ─── check_completeness ──────────────────────────────────────────────────────


class TestCheckCompleteness:
    """完整性检查测试（判据与前端 updateMatter 的写入口径一致）"""

    @pytest.mark.asyncio
    async def test_all_unset_returns_4_incomplete(self):
        """四题都未选适用性 → 4 项 incomplete"""
        db = _make_db(responses=[])
        svc = RegulatoryLetterService()
        result = await svc.check_completeness(db, uuid4(), uuid4())
        assert result["has_incomplete"] is True
        assert result["count"] == 4
        assert len(result["incomplete_topics"]) == 4
        assert "未选择适用性" in result["incomplete_topics"][0]

    @pytest.mark.asyncio
    async def test_all_not_applicable_returns_complete(self):
        """四题都标不适用/不涉及 → complete（无需内容）"""
        db = _make_db(responses=_rows(m1="N", m2="NA", m3="N", m4="NA"))
        svc = RegulatoryLetterService()
        result = await svc.check_completeness(db, uuid4(), uuid4())
        assert result["has_incomplete"] is False
        assert result["count"] == 0
        assert result["incomplete_topics"] == []

    @pytest.mark.asyncio
    async def test_applicable_with_content_is_complete(self):
        """适用且填了内容 → complete"""
        db = _make_db(responses=_rows(m1="Y", c1="发现舞弊线索", m2="N", m3="N", m4="N"))
        svc = RegulatoryLetterService()
        result = await svc.check_completeness(db, uuid4(), uuid4())
        assert result["has_incomplete"] is False

    @pytest.mark.asyncio
    async def test_applicable_without_content_is_incomplete(self):
        """适用但内容为空 → 该项 incomplete"""
        db = _make_db(responses=_rows(m1="Y", c1="", m2="N", m3="N", m4="N"))
        svc = RegulatoryLetterService()
        result = await svc.check_completeness(db, uuid4(), uuid4())
        assert result["has_incomplete"] is True
        assert result["count"] == 1
        assert "舞弊" in result["incomplete_topics"][0]
        assert "未填写沟通内容" in result["incomplete_topics"][0]

    @pytest.mark.asyncio
    async def test_reads_a182_prefix_only(self):
        """SQL 参数必须是 ``a182-%``（``A18-2-%`` 在真库 0 行，读它等于永远读不到）"""
        captured: list[tuple[str, dict]] = []

        db = AsyncMock()

        async def _execute(stmt, params=None):
            captured.append((str(stmt.text), dict(params or {})))
            result = MagicMock()
            result.mappings.return_value.all.return_value = []
            return result

        db.execute = _execute
        await RegulatoryLetterService().check_completeness(db, uuid4(), uuid4())
        assert captured, "未发出任何查询"
        assert any(params.get("prefix") == "a182-%" for _, params in captured), captured


# ─── a18_check_incomplete（统一 check 契约） ──────────────────────────────────


class TestA18CheckIncompleteContract:
    """分发端点用 ``CheckIncompleteResponse(**result)`` 回包 ⇒ 字段必须对得上"""

    @pytest.mark.asyncio
    async def test_returns_unified_contract(self):
        """返回 {complete, missing_fields, wp_code, reason}，且能被 CheckIncompleteResponse 回包"""
        from app.routers.wp_export_word import CheckIncompleteResponse

        db = _make_db(responses=[])
        result = await a18_check_incomplete(db, uuid4(), uuid4())

        assert set(result) == {"complete", "missing_fields", "wp_code", "reason"}
        assert result["wp_code"] == "A18-2"
        assert result["complete"] is False
        assert len(result["missing_fields"]) == 4
        assert result["reason"] == "4 项议题未完成"
        # 🔴 不靠放宽 pydantic 藏 ValidationError：真映射后必须能实例化
        assert CheckIncompleteResponse(**result).complete is False

    @pytest.mark.asyncio
    async def test_complete_has_no_reason(self):
        """全部完成时 complete=True 且 reason 为 None"""
        from app.routers.wp_export_word import CheckIncompleteResponse

        db = _make_db(responses=_rows(m1="N", m2="N", m3="N", m4="N"))
        result = await a18_check_incomplete(db, uuid4(), uuid4())

        assert result["complete"] is True
        assert result["missing_fields"] == []
        assert result["reason"] is None
        assert CheckIncompleteResponse(**result).complete is True


# ─── export_word ─────────────────────────────────────────────────────────────


class TestExportWord:
    """导出 Word 测试（mock filler）"""

    @pytest.mark.asyncio
    async def test_export_calls_fill_and_export(self):
        """验证 export_word 调用 fill_and_export + export_to_bytes，且 context 取项目信息"""
        responses = _rows(
            m1="Y", c1="舞弊描述",
            m2="N",
            m3="Y", c3="一致",
            m4="N",
            **{}
        )
        responses += [
            {"item_id": "a182-recipient-authority", "conclusion": None, "remark": "中国证券监督管理委员会"},
        ]
        db = _make_db(responses=responses)

        mock_doc = MagicMock()
        mock_doc.add_paragraph = MagicMock(return_value=MagicMock())
        mock_doc.paragraphs = []

        with patch("app.services.regulatory_letter_service._TEMPLATE_PATH") as mock_path:
            mock_path.exists.return_value = True
            with patch("app.services.regulatory_letter_service.fill_and_export") as mock_fill:
                from app.services.docx_template_filler import FillResult
                mock_fill.return_value = (mock_doc, FillResult())
                with patch("app.services.regulatory_letter_service.export_to_bytes", return_value=b"PK\x03\x04fake") as mock_export:
                    with patch("docx.Document", return_value=mock_doc):
                        svc = RegulatoryLetterService()
                        result = await svc.export_word(db, uuid4(), uuid4())

        assert result == b"PK\x03\x04fake"
        mock_fill.assert_called_once()
        context_arg = mock_fill.call_args[0][1]
        # 没人手填表头时取项目信息（真库 projects.audit_period_end 年份）
        assert context_arg["client_name"] == "测试公司"
        assert context_arg["audit_year"] == "2025"
        # 模板「与XX监管机构的沟通函」按收件人替换
        assert context_arg["placeholders"]["XX监管机构"] == "中国证券监督管理委员会"
        mock_export.assert_called_once_with(mock_doc)


# ─── 真模板导出（SQLite 用例测不到的模板填充路径） ─────────────────────────────


class TestRealTemplateExport:
    """用**真实** ``A18-2 与监管层沟通函 (通用)2019.docx`` 跑导出。

    为什么必须用真模板：模板把占位符**拆在多个 run 里**（``201X年度`` = ``20``/``1``/``X年度``），
    而 ``docx_template_filler`` 的替换是逐 run 的 ⇒ 假 doc 的用例永远发现不了「年份没填进去」。
    2026-11-12 用真模板实测到两处真实缺陷，本类钉住它们的修复：
    ① ``201X`` 残留在正文；② 议题 4 的序号 ``4`` 是蓝色 run，被蓝删带走后只剩「、其他事项」。
    """

    ROWS = [
        {"item_id": "a182-recipient-authority", "conclusion": None, "remark": "中国证券监督管理委员会"},
        {"item_id": "a182-matter1-applicability", "conclusion": None, "remark": "Y"},
        {"item_id": "a182-matter1-content", "conclusion": None, "remark": "议题一内容"},
        {"item_id": "a182-matter2-applicability", "conclusion": None, "remark": "N"},
        {"item_id": "a182-matter3-applicability", "conclusion": None, "remark": "Y"},
        {"item_id": "a182-matter3-content", "conclusion": None, "remark": "议题三内容"},
        {"item_id": "a182-matter4-applicability", "conclusion": None, "remark": "Y"},
        {"item_id": "a182-matter4-content", "conclusion": None, "remark": "议题四内容"},
    ]

    @pytest.mark.asyncio
    async def test_real_template_export_renders_year_and_all_four_matters(self):
        from docx import Document

        data = await RegulatoryLetterService().export_word(
            _make_db(responses=self.ROWS), uuid4(), uuid4()
        )
        assert data[:2] == b"PK", data[:16]

        doc = Document(io.BytesIO(data))
        text = "\n".join(p.text for p in doc.paragraphs)

        # ① 年份进了正文，占位符没残留
        assert "2025" in text
        assert "201X" not in text, "模板把 201X年度 拆成多个 run，逐 run 替换漏掉了"
        assert "202X" not in text
        # ② 内容占位段被填充（蓝色提示已被 filler 删除）
        assert "【请描述" not in text
        assert "议题一内容" in text
        assert "议题三内容" in text
        assert "议题四内容" in text
        # ③ 4 个议题的序号都在（议题 4 的序号是蓝色 run，会被蓝删带走）
        for seq in ("1、舞弊", "2、重大违反法律法规行为", "4、其他事项"):
            assert seq in text, f"议题标题 {seq!r} 缺失"
        assert "3、年度报告" in text
        # ④ 收件机构替换掉了 XX 占位符
        assert "中国证券监督管理委员会" in text
        assert "XX监管机构" not in text


# ─── get_a8_step_suggestion ──────────────────────────────────────────────────


class TestA8Suggestion:
    """A8 步骤建议映射"""

    @pytest.mark.asyncio
    async def test_all_completed_suggests_no_inconsistency(self):
        """A8 seq 3/4/5 全 completed → no_inconsistency"""
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.mappings.return_value.all.return_value = [
            {"item_id": "A8-seq-3", "conclusion": "completed"},
            {"item_id": "A8-seq-4", "conclusion": "completed"},
            {"item_id": "A8-seq-5", "conclusion": "completed"},
        ]
        db.execute = AsyncMock(return_value=result_mock)

        result = await get_a8_step_suggestion(db, uuid4())
        assert result["suggested_radio"] == "no_inconsistency"

    @pytest.mark.asyncio
    async def test_in_progress_suggests_minor(self):
        """有 in_progress → minor_uncorrected"""
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.mappings.return_value.all.return_value = [
            {"item_id": "A8-seq-3", "conclusion": "completed"},
            {"item_id": "A8-seq-4", "conclusion": "in_progress"},
            {"item_id": "A8-seq-5", "conclusion": "completed"},
        ]
        db.execute = AsyncMock(return_value=result_mock)

        result = await get_a8_step_suggestion(db, uuid4())
        assert result["suggested_radio"] == "minor_uncorrected"

    @pytest.mark.asyncio
    async def test_no_rows_returns_none(self):
        """无数据 → None"""
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.mappings.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)

        result = await get_a8_step_suggestion(db, uuid4())
        assert result["suggested_radio"] is None


# ─── convenience functions ───────────────────────────────────────────────────


class TestConvenience:
    """模块级快捷函数"""

    @pytest.mark.asyncio
    async def test_a18_export_word_delegates(self):
        """``a18_export_word`` 走 ``export_word``（分发表用）"""
        with patch.object(
            RegulatoryLetterService, "export_word", new=AsyncMock(return_value=b"bytes")
        ) as mock_export:
            result = await a18_export_word(_make_db(), uuid4(), uuid4())
        assert result == b"bytes"
        mock_export.assert_awaited_once()
