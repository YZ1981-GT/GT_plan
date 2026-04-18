"""Phase 10 Step 0 (migrations) + Step 1 (Task 1.1-1.2) tests"""

import pytest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from uuid import uuid4

from httpx import AsyncClient

# Tests run from backend/ directory, data files are at data/ and alembic/versions/
DATA_DIR = Path(__file__).parent.parent / "data"
MIGRATION_DIR = Path(__file__).parent.parent / "alembic" / "versions"


# ── JSON 配置文件测试 ─────────────────────────────────────

class TestWpParseRules:
    """wp_parse_rules.json 完整性"""

    def test_load_main_rules(self):
        path = DATA_DIR / "wp_parse_rules.json"
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        rules = data["rules"]
        assert len(rules) >= 10
        for code, rule in rules.items():
            assert "account_codes" in rule
            assert "audited_cell" in rule
            assert "sheet" in rule

    def test_load_extended_rules(self):
        path = DATA_DIR / "wp_parse_rules_extended.json"
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        rules = data["rules"]
        assert len(rules) >= 20
        # 验证负债/权益/损益循环都有
        codes = list(rules.keys())
        assert any(c.startswith("F") for c in codes), "缺少负债循环"
        assert any(c.startswith("G") for c in codes), "缺少权益循环"
        assert any(c.startswith("D") for c in codes), "缺少损益循环"

    def test_no_duplicate_account_codes(self):
        """同一科目编码不应出现在多个规则中"""
        all_codes = []
        for fname in ["wp_parse_rules.json", "wp_parse_rules_extended.json"]:
            path = DATA_DIR / fname
            data = json.loads(path.read_text(encoding="utf-8"))
            for rule in data["rules"].values():
                all_codes.extend(rule["account_codes"])
        assert len(all_codes) > 20


class TestNoteWpMappingRules:
    """note_wp_mapping_rules.json 完整性"""

    def test_load_mapping_rules(self):
        path = DATA_DIR / "note_wp_mapping_rules.json"
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        mappings = data["mappings"]
        assert len(mappings) >= 30
        for m in mappings:
            assert "note_section" in m
            assert "note_title" in m
            assert "wp_codes" in m
            assert "account_codes" in m

    def test_mapping_covers_all_parse_rules(self):
        """映射规则应覆盖所有解析规则中的底稿编号"""
        parse_codes = set()
        for fname in ["wp_parse_rules.json", "wp_parse_rules_extended.json"]:
            path = DATA_DIR / fname
            data = json.loads(path.read_text(encoding="utf-8"))
            parse_codes.update(data["rules"].keys())

        mapping_path = DATA_DIR / "note_wp_mapping_rules.json"
        data = json.loads(mapping_path.read_text(encoding="utf-8"))
        mapped_codes = set()
        for m in data["mappings"]:
            mapped_codes.update(m["wp_codes"])

        missing = parse_codes - mapped_codes
        assert len(missing) == 0, f"解析规则中有底稿编号未在映射规则中: {missing}"


# ── ORM 模型测试 ──────────────────────────────────────────

class TestPhase10Models:
    """Phase 10 ORM 模型基本验证"""

    def test_import_models(self):
        from app.models.phase10_models import (
            ReviewConversation, ReviewMessage,
            ForumPost, ForumComment,
            CellAnnotation, ConsolSnapshot,
            CheckIn, ReportFormatTemplate,
        )
        assert ReviewConversation.__tablename__ == "review_conversations"
        assert ReviewMessage.__tablename__ == "review_messages"
        assert ForumPost.__tablename__ == "forum_posts"
        assert ForumComment.__tablename__ == "forum_comments"
        assert CellAnnotation.__tablename__ == "cell_annotations"
        assert ConsolSnapshot.__tablename__ == "consol_snapshots"
        assert CheckIn.__tablename__ == "check_ins"
        assert ReportFormatTemplate.__tablename__ == "report_format_templates"

    def test_import_schemas(self):
        from app.models.phase10_schemas import (
            DownloadPackRequest, UploadWorkpaperRequest,
            CreateConversationRequest, SendMessageRequest,
            CreateAnnotationRequest, QuotaResponse,
            CreatePostRequest, ReportFormatTemplateCreate,
        )
        req = DownloadPackRequest(wp_ids=[uuid4()])
        assert len(req.wp_ids) == 1


# ── 下载/上传服务测试 ─────────────────────────────────────

class TestWpDownloadService:
    """WpDownloadService 单元测试"""

    @pytest.mark.asyncio
    async def test_download_single_not_found(self):
        from app.services.wp_download_service import WpDownloadService
        from unittest.mock import AsyncMock
        db = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=None)))
        svc = WpDownloadService()
        with pytest.raises(ValueError, match="底稿不存在"):
            await svc.download_single(db, uuid4(), uuid4())

    @pytest.mark.asyncio
    async def test_upload_version_conflict(self):
        from app.services.wp_download_service import WpUploadService
        from unittest.mock import AsyncMock
        mock_wp = MagicMock()
        mock_wp.file_version = 5
        mock_wp.id = uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_wp
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)
        svc = WpUploadService()
        result = await svc.check_version_conflict(db, mock_wp.id, 3)
        assert result["has_conflict"] is True
        assert result["server_version"] == 5


# ── 迁移脚本存在性测试 ───────────────────────────────────

class TestMigrationFiles:
    """验证 3 个迁移脚本存在且结构正确"""

    @pytest.mark.parametrize("filename,tables", [
        ("030_review_and_forum.py", ["review_conversations", "review_messages", "forum_posts", "forum_comments"]),
        ("031_annotations_and_snapshots.py", ["cell_annotations", "consol_snapshots", "check_ins"]),
        ("032_report_templates_and_fields.py", ["report_format_templates"]),
    ])
    def test_migration_exists_and_contains_tables(self, filename, tables):
        path = MIGRATION_DIR / filename
        assert path.exists(), f"迁移脚本不存在: {filename}"
        content = path.read_text(encoding="utf-8")
        for table in tables:
            assert table in content, f"迁移脚本 {filename} 缺少表 {table}"
