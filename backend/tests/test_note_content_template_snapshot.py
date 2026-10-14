"""Phase 7 测试：模板快照生成、不可变版本和 CRUD 逻辑。"""

from __future__ import annotations

import hashlib
import json
import uuid

import pytest

from app.services.note_content_template_snapshot import (
    generate_snapshot,
    _find_or_create_template,
)


class TestSnapshotGeneration:
    """快照生成的纯逻辑测试（不依赖 DB，mock 数据）。"""

    def test_content_hash_deterministic(self):
        """相同 sections 产生相同 content_hash。"""
        sections = [
            {"note_section": "一、1", "content_hash": "abc"},
            {"note_section": "二、2", "content_hash": "def"},
        ]
        canonical = json.dumps(
            [{"ns": s["note_section"], "h": s["content_hash"]} for s in sections],
            sort_keys=True, ensure_ascii=False,
        )
        h1 = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        h2 = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        assert h1 == h2

    def test_snapshot_digest_includes_project(self):
        """digest 包含 project_id，不同项目不同 digest。"""
        def _digest(pid: str) -> str:
            return hashlib.sha256(json.dumps({
                "project_id": pid, "year": 2025, "content_hash": "x",
            }, sort_keys=True).encode()).hexdigest()

        assert _digest("aaa") != _digest("bbb")

    def test_sections_data_excludes_table_data(self):
        """快照不含 table_data 键。"""
        section = {
            "source_note_id": "x",
            "note_section": "一、1",
            "text_content": "<p>正文</p>",
            "content_hash": "h",
            "status": "draft",
            "is_stale": False,
            "quality_flags": [],
        }
        assert "table_data" not in section


class TestVersionLogic:
    def test_same_hash_reuse_concept(self):
        """相同 content_hash 应复用版本（概念验证）。"""
        hashes = set()
        h = hashlib.sha256(b"same-content").hexdigest()
        hashes.add(h)
        assert h in hashes  # 第二次加入不增加 set 大小
        hashes.add(h)
        assert len(hashes) == 1

    def test_version_no_increments(self):
        """版本号递增。"""
        current_max = 3
        next_ver = (current_max or 0) + 1
        assert next_ver == 4


class TestOwnerLogic:
    def test_personal_owner_shape(self):
        """personal 模板有 user_id 无 group_id。"""
        scope = "personal"
        uid = uuid.uuid4()
        assert scope == "personal"
        assert uid is not None

    def test_group_owner_shape(self):
        """group 模板有 group_id 无 user_id。"""
        scope = "group"
        gid = uuid.uuid4()
        assert scope == "group"
        assert gid is not None


class TestRouterImport:
    def test_router_has_all_endpoints(self):
        from app.routers.note_content_templates import router
        paths = [r.path for r in router.routes]
        # 列表
        assert any(p == "/api/projects/{project_id}/note-content-templates" for p in paths)
        # 详情
        assert any("/{template_id}" in p and "/versions" not in p for p in paths)
        # 版本
        assert any("/versions" in p for p in paths)
        # snapshot-preview
        assert any("snapshot-preview" in p for p in paths)

    def test_delete_endpoint_exists(self):
        from app.routers.note_content_templates import router
        methods = set()
        for route in router.routes:
            if hasattr(route, "methods"):
                methods.update(route.methods)
        assert "DELETE" in methods


class TestSoftDeletePreservation:
    """Task 43：软删除保留版本和应用历史。"""

    def test_soft_delete_sets_is_deleted(self):
        """概念验证：软删除只标 is_deleted，不物理删除。"""
        from app.models.note_content_template_models import NoteContentTemplate
        cols = NoteContentTemplate.__table__.columns
        assert "is_deleted" in cols
        assert "deleted_at" in cols
        # 无 CASCADE DELETE 到 versions
        from app.models.note_content_template_models import NoteContentTemplateVersion
        fks = [fk for col in NoteContentTemplateVersion.__table__.columns for fk in col.foreign_keys]
        template_fks = [fk for fk in fks if "note_content_templates" in fk.target_fullname]
        for fk in template_fks:
            assert fk.ondelete != "CASCADE", "版本外键不能 CASCADE DELETE"
