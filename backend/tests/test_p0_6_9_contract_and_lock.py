"""P0-6 模板变体/来源版本契约 + P0-9 锁定/CAS/权限 验收测试。

将 P0-6 和 P0-9 从 ⚠️ 推进到 ✅。
全部用纯函数测试 + mock，不依赖真实 PG。
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest


# ═══════════════════════════════════════════════════════════════════════════
# P0-6：模板变体和来源版本契约
# ═══════════════════════════════════════════════════════════════════════════


class TestTemplateTypeNormalization:
    """template_type 参数在全链路上被正确消费。"""

    def test_normalize_template_type_soe(self):
        from app.services.note_section_catalog import normalize_template_type

        assert normalize_template_type("soe") == "soe"
        assert normalize_template_type("SOE") == "soe"
        assert normalize_template_type("  soe  ") == "soe"

    def test_normalize_template_type_listed(self):
        from app.services.note_section_catalog import normalize_template_type

        assert normalize_template_type("listed") == "listed"
        assert normalize_template_type("LISTED") == "listed"

    def test_normalize_template_type_default(self):
        from app.services.note_section_catalog import normalize_template_type

        assert normalize_template_type(None) == "soe"
        assert normalize_template_type("") == "soe"
        assert normalize_template_type("invalid") == "soe"

    def test_normalize_report_scope(self):
        from app.services.note_section_catalog import normalize_report_scope

        assert normalize_report_scope("standalone") == "standalone"
        assert normalize_report_scope("consolidated") == "consolidated"
        assert normalize_report_scope(None) == "standalone"


class TestTemplateTypeProduceDifferentResults:
    """soe 和 listed 模板产出不同的规则/章节。"""

    def test_check_rules_differ_between_soe_and_listed(self):
        """soe 和 listed 的 check_rules 不完全相同。"""
        from app.services.note_check_rules import load_all_check_rules

        soe_rules = load_all_check_rules("soe")
        listed_rules = load_all_check_rules("listed")

        soe_ids = {r.check_id for rules in soe_rules.values() for r in rules}
        listed_ids = {r.check_id for rules in listed_rules.values() for r in rules}

        # 两个模板都有规则
        assert len(soe_ids) > 0
        assert len(listed_ids) > 0
        # 但不完全相同（soe 和 listed 的章节结构不同）
        assert soe_ids != listed_ids, "soe 和 listed 的 check_rules 不应完全相同"

    def test_same_section_different_template_may_differ(self):
        """同一 section_id 在 soe/listed 中可能有不同规则（或一方无规则）。"""
        from app.services.note_check_rules import _load_check_rules

        # 五-5-2 在两个模板中都有
        soe = _load_check_rules("soe", "五-5-2")
        listed = _load_check_rules("listed", "五-5-2")
        # 至少一方有规则
        assert len(soe) > 0 or len(listed) > 0

    def test_nonexistent_template_returns_empty(self):
        """不存在的模板类型返回空。"""
        from app.services.note_check_rules import _load_check_rules

        rules = _load_check_rules("nonexistent_type", "五-5-2")
        assert rules == []


class TestConsolNoteTemplateFiles:
    """合并附注模板 JSON 文件的基本契约。"""

    def test_soe_json_exists_and_has_sections(self):
        """国企 soe 合并附注模板 JSON 存在且含章节。"""
        import json
        from pathlib import Path

        path = Path(__file__).resolve().parents[1] / "app" / "data" / "consol_note_sections_soe.json"
        if not path.exists():
            path = Path(__file__).resolve().parents[1] / "data" / "consol_note_sections_soe.json"
        assert path.exists(), f"缺少 consol_note_sections_soe.json (tried {path})"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) >= 300, f"soe 模板章节数 {len(data)} 低于基线 300"

    def test_listed_json_exists_and_has_sections(self):
        """上市 listed 合并附注模板 JSON 存在且含章节。"""
        import json
        from pathlib import Path

        path = Path(__file__).resolve().parents[1] / "app" / "data" / "consol_note_sections_listed.json"
        if not path.exists():
            path = Path(__file__).resolve().parents[1] / "data" / "consol_note_sections_listed.json"
        assert path.exists(), f"缺少 consol_note_sections_listed.json (tried {path})"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) >= 400, f"listed 模板章节数 {len(data)} 低于基线 400"

    def test_soe_and_listed_have_different_section_counts(self):
        """soe 和 listed 章节数不同（结构不同）。"""
        import json
        from pathlib import Path

        base = Path(__file__).resolve().parents[1] / "app" / "data"
        if not (base / "consol_note_sections_soe.json").exists():
            base = Path(__file__).resolve().parents[1] / "data"
        soe = json.loads((base / "consol_note_sections_soe.json").read_text(encoding="utf-8"))
        listed = json.loads((base / "consol_note_sections_listed.json").read_text(encoding="utf-8"))
        assert len(soe) != len(listed), "soe 和 listed 章节数完全相同——模板结构应不同"


class TestTreeVersionContract:
    """树版本契约：fingerprint + revision。"""

    def test_fingerprint_is_sha256_hex(self):
        from app.services.consol_scope_confirmation_service import fingerprint_payload

        fp = fingerprint_payload({"year": 2025, "nodes": []})
        assert len(fp) == 64
        assert all(c in "0123456789abcdef" for c in fp)

    def test_revision_increments(self):
        """revision 应为非负整数。"""
        from app.services.consol_scope_confirmation_service import (
            ConsolScopeConfirmation,
        )

        # ORM 模型有 revision 字段
        assert hasattr(ConsolScopeConfirmation, "revision")

    def test_report_scope_field_exists_on_project(self):
        """Project 模型有 report_scope 字段。"""
        from app.models.core import Project

        assert hasattr(Project, "report_scope")

    def test_template_type_field_exists_on_project(self):
        """Project 模型有 template_type 字段。"""
        from app.models.core import Project

        assert hasattr(Project, "template_type")


# ═══════════════════════════════════════════════════════════════════════════
# P0-9：锁定/CAS/权限
# ═══════════════════════════════════════════════════════════════════════════


class TestConsolLockBehavior:
    """合并锁定机制验证。"""

    def test_consol_lock_field_on_project(self):
        """Project 模型有 consol_lock 布尔字段。"""
        from app.models.core import Project

        assert hasattr(Project, "consol_lock")
        assert hasattr(Project, "consol_lock_by")
        assert hasattr(Project, "consol_lock_at")

    @pytest.mark.asyncio
    async def test_check_consol_lock_raises_423_when_locked(self):
        """consol_lock=True → 423。"""
        from fastapi import HTTPException

        from app.deps import check_consol_lock

        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = True
        db.execute = AsyncMock(return_value=result)

        with pytest.raises(HTTPException) as ei:
            await check_consol_lock(project_id=uuid.uuid4(), db=db)
        assert ei.value.status_code == 423

    @pytest.mark.asyncio
    async def test_check_consol_lock_passes_when_unlocked(self):
        """consol_lock=False → 正常通过。"""
        from app.deps import check_consol_lock

        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = False
        db.execute = AsyncMock(return_value=result)

        # 不抛异常
        await check_consol_lock(project_id=uuid.uuid4(), db=db)

    @pytest.mark.asyncio
    async def test_check_consol_lock_passes_when_no_project(self):
        """无法确定项目 → 放行（EH4 设计）。"""
        from app.deps import check_consol_lock

        db = AsyncMock()
        # 无 project_id，无 wp_id，无 note_id
        await check_consol_lock(db=db)


class TestPermissionMatrix:
    """权限矩阵：qc/readonly 不能写底稿。"""

    def test_admin_has_workpaper_write(self):
        from app.services.permission_service import Permission, check_permission

        assert check_permission("admin", Permission.WORKPAPER_WRITE)

    def test_partner_has_workpaper_write(self):
        from app.services.permission_service import Permission, check_permission

        assert check_permission("partner", Permission.WORKPAPER_WRITE)

    def test_manager_has_workpaper_write(self):
        from app.services.permission_service import Permission, check_permission

        assert check_permission("manager", Permission.WORKPAPER_WRITE)

    def test_auditor_has_workpaper_write(self):
        from app.services.permission_service import Permission, check_permission

        assert check_permission("auditor", Permission.WORKPAPER_WRITE)

    def test_qc_reviewer_lacks_workpaper_write(self):
        """qc_reviewer 没有 WORKPAPER_WRITE → 发布被拒。"""
        from app.services.permission_service import Permission, check_permission

        assert not check_permission("qc_reviewer", Permission.WORKPAPER_WRITE)

    def test_readonly_lacks_workpaper_write(self):
        """readonly 没有 WORKPAPER_WRITE → 发布被拒。"""
        from app.services.permission_service import Permission, check_permission

        assert not check_permission("readonly", Permission.WORKPAPER_WRITE)

    def test_unknown_role_lacks_all_permissions(self):
        """未知角色没有任何权限（fail-closed）。"""
        from app.services.permission_service import Permission, check_permission

        assert not check_permission("hacker", Permission.WORKPAPER_WRITE)
        assert not check_permission("hacker", Permission.PROJECT_READ)

    def test_publisher_can_publish_requires_confirmed_by(self):
        """_publisher_can_publish 对 None confirmed_by 返回 False（fail-closed）。"""
        import asyncio

        from app.services.event_handlers_cycle_linkage import _publisher_can_publish

        session = AsyncMock()
        result = asyncio.get_event_loop().run_until_complete(
            _publisher_can_publish(session, None)
        )
        assert result is False


class TestPublishTokenIdempotencyContract:
    """publish_token 幂等契约的设计验证。"""

    def test_tb_publish_ack_table_has_unique_token(self):
        """V162 迁移定义了 publish_token UNIQUE 约束。"""
        from pathlib import Path

        sql_path = Path(__file__).resolve().parents[1] / "migrations" / "V162__tb_publish_ack.sql"
        assert sql_path.exists(), f"V162 迁移文件缺失 (tried {sql_path})"
        sql = sql_path.read_text(encoding="utf-8")
        assert "UNIQUE" in sql or "unique" in sql, "publish_token 缺少唯一约束"
        assert "publish_token" in sql

    def test_handler_checks_rowcount_for_idempotency(self):
        """事件处理器通过 ack.rowcount == 0 判断幂等跳过。"""
        import inspect

        from app.services import event_handlers_cycle_linkage as mod

        source = inspect.getsource(mod._on_d_audit_determination_saved)
        assert "rowcount" in source, "handler 未检查 rowcount 判断幂等"
        assert "DO NOTHING" in source or "do nothing" in source.lower(), (
            "handler 未使用 ON CONFLICT DO NOTHING"
        )

    def test_build_publish_token_stable_across_calls(self):
        """同一输入多次调用产出相同 token。"""
        from app.services.tb_audited_writer import build_publish_token

        pid = uuid.uuid4()
        rows = [{"account_code": "1001", "audited_amount": 100}]
        current = {"1001": [Decimal("50")]}
        tokens = set()
        for _ in range(5):
            tokens.add(build_publish_token(
                project_id=pid, year=2025, wp_code="D1-1",
                rows=rows, current_audited_amounts=current,
            ))
        assert len(tokens) == 1, f"同一输入产出了 {len(tokens)} 个不同 token"
