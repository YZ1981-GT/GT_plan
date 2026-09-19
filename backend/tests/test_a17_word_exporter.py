"""A17-1 Word 导出编排 + 完整性检查 单元测试。

验证:
- check_completeness: 空章节/红色占位符/蓝色提示检测
- export_word: 正常导出 + 模板不存在降级
- 分发注册: a17_export_word / a17_check_incomplete 正确注册
"""

from __future__ import annotations

import uuid
from collections import namedtuple
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.a17_word_exporter import (
    A17WordExporter,
    _BLUE_GUIDANCE_PATTERN,
    _RED_PLACEHOLDER_PATTERNS,
    a17_check_incomplete,
    a17_export_word,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def exporter():
    return A17WordExporter()


@pytest.fixture
def project_id():
    return uuid.uuid4()


@pytest.fixture
def wp_id():
    return uuid.uuid4()


def _mock_db_with_responses(responses: dict[str, str], project_row=None):
    """创建 mock db, 模拟 checklist_responses 查询和 project 查询。"""
    db = AsyncMock()

    # 模拟 checklist_responses 查询结果
    Row = namedtuple("Row", ["item_id", "remark"])
    response_rows = [Row(item_id=k, remark=v) for k, v in responses.items()]

    # 模拟 project 查询结果
    ProjectRow = namedtuple("ProjectRow", ["client_name", "audit_period_end"])
    if project_row is None:
        project_row = ProjectRow(client_name="测试公司", audit_period_end=None)

    # execute 被调用两次: 一次查 responses, 一次查 project
    call_count = [0]

    async def mock_execute(stmt, params=None):
        call_count[0] += 1
        result = MagicMock()
        if call_count[0] == 1:
            # First call: checklist_responses
            result.fetchall.return_value = response_rows
        else:
            # Second call: projects
            result.fetchone.return_value = project_row
        return result

    db.execute = mock_execute
    return db


def _mock_db_completeness_only(responses: dict[str, str]):
    """创建 mock db, 仅模拟 checklist_responses 查询（用于 completeness check）。"""
    db = AsyncMock()

    Row = namedtuple("Row", ["item_id", "remark"])
    response_rows = [Row(item_id=k, remark=v) for k, v in responses.items()]

    async def mock_execute(stmt, params=None):
        result = MagicMock()
        result.fetchall.return_value = response_rows
        return result

    db.execute = mock_execute
    return db


# ─── 正则模式单元测试 ────────────────────────────────────────────────────────


class TestPatternDetection:
    """红色/蓝色模式检测。"""

    def test_red_placeholder_XX(self):
        assert any(p.search("本公司XX部门") for p in _RED_PLACEHOLDER_PATTERNS)

    def test_red_placeholder_201X(self):
        assert any(p.search("201X年度") for p in _RED_PLACEHOLDER_PATTERNS)

    def test_red_placeholder_202X(self):
        assert any(p.search("202X年度") for p in _RED_PLACEHOLDER_PATTERNS)

    def test_no_red_in_clean_text(self):
        text = "本公司2024年度审计已完成"
        assert not any(p.search(text) for p in _RED_PLACEHOLDER_PATTERNS)

    def test_blue_guidance_detected(self):
        assert _BLUE_GUIDANCE_PATTERN.search("【注：此处填写审计范围说明】")

    def test_no_blue_in_clean_text(self):
        assert not _BLUE_GUIDANCE_PATTERN.search("本公司审计范围包括全部业务")


# ─── check_completeness 测试 ─────────────────────────────────────────────────


class TestCheckCompleteness:
    """完整性检查逻辑。"""

    @pytest.mark.asyncio
    async def test_all_empty_returns_incomplete(self, exporter, project_id, wp_id):
        """无任何填写 → 16 章全部缺失。"""
        db = _mock_db_completeness_only({})
        report = await exporter.check_completeness(db, project_id, wp_id)

        assert report["complete"] is False
        assert len(report["missing_chapters"]) == 16
        assert report["wp_code"] == "A17-1"

    @pytest.mark.asyncio
    async def test_all_filled_clean_returns_complete(self, exporter, project_id, wp_id):
        """所有必填章节都有干净内容 → complete=True。"""
        responses = {
            f"A17-1-ch{i:02d}": f"第{i}章正文内容已填写完毕"
            for i in range(1, 17)
        }
        db = _mock_db_completeness_only(responses)
        report = await exporter.check_completeness(db, project_id, wp_id)

        assert report["complete"] is True
        assert report["missing_chapters"] == []
        assert report["red_placeholder_chapters"] == []

    @pytest.mark.asyncio
    async def test_red_placeholder_detected(self, exporter, project_id, wp_id):
        """含 XX 占位符 → incomplete + 报告含红色章节。"""
        responses = {
            f"A17-1-ch{i:02d}": f"第{i}章正文" for i in range(1, 17)
        }
        # ch03 含红色占位符
        responses["A17-1-ch03"] = "本公司XX部门的审计计划已于202X年修订"
        db = _mock_db_completeness_only(responses)
        report = await exporter.check_completeness(db, project_id, wp_id)

        assert report["complete"] is False
        assert len(report["red_placeholder_chapters"]) >= 1
        assert any("3." in ch for ch in report["red_placeholder_chapters"])

    @pytest.mark.asyncio
    async def test_blue_guidance_detected(self, exporter, project_id, wp_id):
        """含 【注：...】 → 提示蓝色（不影响 complete 判定）。"""
        responses = {
            f"A17-1-ch{i:02d}": f"第{i}章正文" for i in range(1, 17)
        }
        # ch05 含蓝色提示
        responses["A17-1-ch05"] = "咨询记录【注：填写具体咨询事项及结论】"
        db = _mock_db_completeness_only(responses)
        report = await exporter.check_completeness(db, project_id, wp_id)

        # 蓝色提示不影响 complete（导出时自动删除）
        assert report["complete"] is True
        assert len(report["blue_guidance_chapters"]) == 1


# ─── export_word 测试 ─────────────────────────────────────────────────────────


class TestExportWord:
    """Word 导出逻辑。"""

    @pytest.mark.asyncio
    async def test_export_returns_bytes(self, exporter, project_id, wp_id):
        """正常导出返回 bytes（即使内容为空）。"""
        db = _mock_db_with_responses({})

        with patch(
            "app.services.a17_word_exporter._TEMPLATE_PATH",
            MagicMock(is_file=MagicMock(return_value=False)),
        ):
            result = await exporter.export_word(db, project_id, wp_id)
            assert isinstance(result, bytes)
            assert len(result) > 0
            # docx 文件以 PK 开头（ZIP）
            assert result[:2] == b"PK"

    @pytest.mark.asyncio
    async def test_export_with_chapter_content(self, exporter, project_id, wp_id):
        """含章节内容的导出也返回有效 docx。"""
        responses = {
            "A17-1-ch01": "被审计单位：测试公司\n审计期间：2024年1月1日至12月31日",
            "A17-1-ch02": "项目组全员已签署独立性声明。",
        }
        db = _mock_db_with_responses(responses)

        with patch(
            "app.services.a17_word_exporter._TEMPLATE_PATH",
            MagicMock(is_file=MagicMock(return_value=False)),
        ):
            result = await exporter.export_word(db, project_id, wp_id)
            assert isinstance(result, bytes)
            assert result[:2] == b"PK"


# ─── 分发接口测试 ─────────────────────────────────────────────────────────────


class TestDispatchInterface:
    """分发注册接口返回正确格式。"""

    @pytest.mark.asyncio
    async def test_a17_check_incomplete_schema(self, project_id, wp_id):
        """a17_check_incomplete 返回统一 schema。"""
        db = _mock_db_completeness_only({})
        result = await a17_check_incomplete(db, project_id, wp_id)

        assert "complete" in result
        assert "missing_fields" in result
        assert "wp_code" in result
        assert result["wp_code"] == "A17-1"
        assert isinstance(result["missing_fields"], list)

    @pytest.mark.asyncio
    async def test_a17_export_word_returns_bytes(self, project_id, wp_id):
        """a17_export_word 返回 docx bytes。"""
        db = _mock_db_with_responses({})

        with patch(
            "app.services.a17_word_exporter._TEMPLATE_PATH",
            MagicMock(is_file=MagicMock(return_value=False)),
        ):
            result = await a17_export_word(db, project_id, wp_id)
            assert isinstance(result, bytes)
            assert result[:2] == b"PK"



# ═══════════════════════════════════════════════════════════════════════════════
# A17-2-1 KAM Word 导出测试
# ═══════════════════════════════════════════════════════════════════════════════

import json

from app.services.a17_word_exporter import (
    A17KamExporter,
    KamRemarkParsed,
    _parse_kam_remark,
    a17_kam_check_incomplete,
    a17_kam_export_word,
)


# ─── KAM remark 解析测试 ─────────────────────────────────────────────────────


class TestParseKamRemark:
    """KAM remark JSON 解析。"""

    def test_valid_json_parsed(self):
        data = json.dumps({
            "situation": "收入确认复杂",
            "reason": "重大风险",
            "response": "扩大实质性测试范围",
            "refs": "D4-1",
            "wording_review": "done",
            "governance_confirmed": True,
        })
        result = _parse_kam_remark(data)
        assert result.situation == "收入确认复杂"
        assert result.reason == "重大风险"
        assert result.response == "扩大实质性测试范围"
        assert result.refs == "D4-1"
        assert result.wording_review == "done"
        assert result.governance_confirmed is True

    def test_empty_string_returns_defaults(self):
        result = _parse_kam_remark("")
        assert result.situation == ""
        assert result.wording_review == "pending"
        assert result.governance_confirmed is False

    def test_none_returns_defaults(self):
        result = _parse_kam_remark(None)
        assert result == KamRemarkParsed()

    def test_invalid_json_returns_defaults(self):
        result = _parse_kam_remark("{invalid json")
        assert result == KamRemarkParsed()

    def test_partial_json_fills_missing_with_defaults(self):
        data = json.dumps({"situation": "仅情况描述"})
        result = _parse_kam_remark(data)
        assert result.situation == "仅情况描述"
        assert result.reason == ""
        assert result.governance_confirmed is False


# ─── KAM 完整性检查测试 ──────────────────────────────────────────────────────


def _mock_db_kam_entries(entries: list[tuple[str, str, str, str]]):
    """创建 mock db 返回 KAM entries: (item_id, conclusion, remark, wp_ref)。"""
    db = AsyncMock()

    Row = namedtuple("Row", ["item_id", "conclusion", "remark", "wp_ref"])
    response_rows = [Row(*e) for e in entries]

    async def mock_execute(stmt, params=None):
        result = MagicMock()
        result.fetchall.return_value = response_rows
        return result

    db.execute = mock_execute
    return db


class TestKamCheckCompleteness:
    """A17-2-1 KAM 完整性检查。"""

    @pytest.fixture
    def kam_exporter(self):
        return A17KamExporter()

    @pytest.mark.asyncio
    async def test_no_entries_incomplete(self, kam_exporter, project_id, wp_id):
        """无 KAM 记录 → incomplete。"""
        db = _mock_db_kam_entries([])
        report = await kam_exporter.check_completeness(db, project_id, wp_id)

        assert report["complete"] is False
        assert report["wp_code"] == "A17-2-1"
        assert "至少需要 1 条 KAM 记录" in report["missing_fields"]

    @pytest.mark.asyncio
    async def test_complete_entry(self, kam_exporter, project_id, wp_id):
        """完整 KAM → complete=True。"""
        remark = json.dumps({
            "situation": "desc",
            "reason": "reason",
            "response": "response",
            "refs": "D4",
            "wording_review": "done",
            "governance_confirmed": True,
        })
        entries = [("A17-2-1-KAM-001", "收入确认", remark, "D4")]
        db = _mock_db_kam_entries(entries)
        report = await kam_exporter.check_completeness(db, project_id, wp_id)

        assert report["complete"] is True
        assert report["missing_fields"] == []

    @pytest.mark.asyncio
    async def test_missing_fields_detected(self, kam_exporter, project_id, wp_id):
        """KAM 缺 situation + reason → 2 项 missing。"""
        remark = json.dumps({
            "situation": "",
            "reason": "",
            "response": "审计应对措施",
            "refs": "",
            "wording_review": "pending",
            "governance_confirmed": False,
        })
        entries = [("A17-2-1-KAM-001", "收入确认", remark, "D4")]
        db = _mock_db_kam_entries(entries)
        report = await kam_exporter.check_completeness(db, project_id, wp_id)

        assert report["complete"] is False
        assert len(report["missing_fields"]) == 2


# ─── KAM Word 导出测试 ───────────────────────────────────────────────────────


class TestKamExportWord:
    """A17-2-1 KAM Word 导出。"""

    @pytest.fixture
    def kam_exporter(self):
        return A17KamExporter()

    @pytest.mark.asyncio
    async def test_export_empty_returns_valid_docx(self, kam_exporter, project_id, wp_id):
        """无 KAM 条目也能导出有效 docx。"""
        # Mock: KAM 查询返空 + project 查询
        db = AsyncMock()
        call_count = [0]
        ProjectRow = namedtuple("ProjectRow", ["client_name", "audit_period_end"])

        async def mock_execute(stmt, params=None):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.fetchall.return_value = []
            else:
                result.fetchone.return_value = ProjectRow("测试公司", None)
            return result

        db.execute = mock_execute

        with patch(
            "app.services.a17_word_exporter._KAM_TEMPLATE_PATH",
            MagicMock(is_file=MagicMock(return_value=False)),
        ):
            result = await kam_exporter.export_word(db, project_id, wp_id)
            assert isinstance(result, bytes)
            assert result[:2] == b"PK"

    @pytest.mark.asyncio
    async def test_export_with_entries(self, kam_exporter, project_id, wp_id):
        """含 KAM 条目导出有效 docx。"""
        remark = json.dumps({
            "situation": "收入确认方法复杂",
            "reason": "重大错报风险",
            "response": "执行实质性程序",
            "refs": "见 D4-1",
            "wording_review": "done",
            "governance_confirmed": True,
        })
        kam_rows = [
            namedtuple("Row", ["item_id", "conclusion", "remark", "wp_ref"])(
                "A17-2-1-KAM-001", "收入确认", remark, "D4,B50"
            )
        ]
        ProjectRow = namedtuple("ProjectRow", ["client_name", "audit_period_end"])

        db = AsyncMock()
        call_count = [0]

        async def mock_execute(stmt, params=None):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.fetchall.return_value = kam_rows
            else:
                result.fetchone.return_value = ProjectRow("测试公司", None)
            return result

        db.execute = mock_execute

        with patch(
            "app.services.a17_word_exporter._KAM_TEMPLATE_PATH",
            MagicMock(is_file=MagicMock(return_value=False)),
        ):
            result = await kam_exporter.export_word(db, project_id, wp_id)
            assert isinstance(result, bytes)
            assert result[:2] == b"PK"
            # 验证 docx 中包含 KAM 内容
            from docx import Document
            import io
            doc = Document(io.BytesIO(result))
            full_text = "\n".join(p.text for p in doc.paragraphs)
            assert "KAM 1: 收入确认" in full_text


# ─── KAM 分发接口测试 ─────────────────────────────────────────────────────────


class TestKamDispatchInterface:
    """KAM 分发注册接口。"""

    @pytest.mark.asyncio
    async def test_kam_check_incomplete_schema(self, project_id, wp_id):
        """a17_kam_check_incomplete 返回统一 schema。"""
        db = _mock_db_kam_entries([])
        result = await a17_kam_check_incomplete(db, project_id, wp_id)

        assert "complete" in result
        assert "missing_fields" in result
        assert "wp_code" in result
        assert result["wp_code"] == "A17-2-1"

    @pytest.mark.asyncio
    async def test_kam_export_word_returns_bytes(self, project_id, wp_id):
        """a17_kam_export_word 返回 docx bytes。"""
        db = AsyncMock()
        call_count = [0]
        ProjectRow = namedtuple("ProjectRow", ["client_name", "audit_period_end"])

        async def mock_execute(stmt, params=None):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.fetchall.return_value = []
            else:
                result.fetchone.return_value = ProjectRow("测试公司", None)
            return result

        db.execute = mock_execute

        with patch(
            "app.services.a17_word_exporter._KAM_TEMPLATE_PATH",
            MagicMock(is_file=MagicMock(return_value=False)),
        ):
            result = await a17_kam_export_word(db, project_id, wp_id)
            assert isinstance(result, bytes)
            assert result[:2] == b"PK"


class TestDispatchRegistration:
    """验证 A17-2-1 在 EXPORT_DISPATCH/CHECK_DISPATCH 中已注册。"""

    def test_a17_2_1_in_export_dispatch(self):
        from app.services.wp_export_word_service import EXPORT_DISPATCH
        assert "A17-2-1" in EXPORT_DISPATCH

    def test_a17_2_1_in_check_dispatch(self):
        from app.services.wp_export_word_service import CHECK_DISPATCH
        assert "A17-2-1" in CHECK_DISPATCH
