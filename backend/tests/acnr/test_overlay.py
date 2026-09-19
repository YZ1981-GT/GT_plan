"""Unit tests for ACNR L2 overlay.py — ProjectOverlay patch application + ownership validation.

Requirements: 5.2, 5.8, 24.1
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.acnr.overlay import (
    OverlayOwnershipError,
    OverlayPatch,
    ProjectOverlay,
    clear_all_overlays,
    clear_project_overlays,
    get_overlay,
    get_project_overlay,
    get_project_overlays,
    remove_overlay,
    set_overlay,
    validate_ownership,
    write_overlay,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clean_overlays():
    """每个测试前后清空 overlay store。"""
    clear_all_overlays()
    yield
    clear_all_overlays()


def _mock_db_session(
    *,
    project_exists: bool = True,
    wp_exists: bool = True,
) -> AsyncMock:
    """构造 mock db session，控制 ownership 校验结果。

    Uses side_effect to return different results for project vs wp queries.
    """
    db = AsyncMock()

    call_count = {"n": 0}

    async def _execute_side_effect(*args, **kwargs):
        call_count["n"] += 1
        result = MagicMock()
        if call_count["n"] == 1:
            # First call: project existence check
            result.scalar_one_or_none.return_value = 1 if project_exists else None
        else:
            # Second call: wp_index ownership check
            result.scalar_one_or_none.return_value = 1 if wp_exists else None
        return result

    db.execute.side_effect = _execute_side_effect
    return db


# ─── Tests: OverlayPatch ────────────────────────────────────────────────────


class TestOverlayPatch:
    def test_not_expired_no_date(self):
        """无 expires_at 永不过期。"""
        patch = OverlayPatch(project_id="p1", addr_id="D2/D2-2")
        assert patch.is_expired() is False

    def test_not_expired_future_date(self):
        """expires_at 在未来则未过期。"""
        future = (date.today() + timedelta(days=30)).isoformat()
        patch = OverlayPatch(project_id="p1", addr_id="D2/D2-2", expires_at=future)
        assert patch.is_expired() is False

    def test_expired_past_date(self):
        """expires_at 在过去则已过期。"""
        past = (date.today() - timedelta(days=1)).isoformat()
        patch = OverlayPatch(project_id="p1", addr_id="D2/D2-2", expires_at=past)
        assert patch.is_expired() is True

    def test_expired_invalid_date_format(self):
        """无效日期格式视为未过期（保守策略）。"""
        patch = OverlayPatch(project_id="p1", addr_id="D2/D2-2", expires_at="invalid")
        assert patch.is_expired() is False


# ─── Tests: Store Management ────────────────────────────────────────────────


class TestStoreManagement:
    def test_set_and_get_overlay(self):
        """写入后可读取。"""
        patch = OverlayPatch(
            project_id="proj-1",
            addr_id="D2/D2-2",
            overrides={"sheet_name_alias_add": ["临时叫法"]},
            reason="项目模板差异",
            owner="zhangsan",
        )
        set_overlay(patch)

        retrieved = get_overlay("proj-1", "D2/D2-2")
        assert retrieved is not None
        assert retrieved.reason == "项目模板差异"
        assert retrieved.owner == "zhangsan"

    def test_get_nonexistent_returns_none(self):
        """不存在的 overlay 返回 None。"""
        assert get_overlay("no-proj", "no-addr") is None

    def test_get_project_overlays(self):
        """获取指定项目全部 overlay。"""
        set_overlay(OverlayPatch(project_id="proj-1", addr_id="D2/D2-2"))
        set_overlay(OverlayPatch(project_id="proj-1", addr_id="D3/D3-1"))
        set_overlay(OverlayPatch(project_id="proj-2", addr_id="D4/D4-1"))

        overlays = get_project_overlays("proj-1")
        assert len(overlays) == 2
        assert "D2/D2-2" in overlays
        assert "D3/D3-1" in overlays

    def test_remove_overlay(self):
        """移除已有 overlay 返回 True。"""
        set_overlay(OverlayPatch(project_id="proj-1", addr_id="D2/D2-2"))
        assert remove_overlay("proj-1", "D2/D2-2") is True
        assert get_overlay("proj-1", "D2/D2-2") is None

    def test_remove_nonexistent_returns_false(self):
        """移除不存在的 overlay 返回 False。"""
        assert remove_overlay("no-proj", "no-addr") is False

    def test_clear_project_overlays(self):
        """清除单个项目不影响其他项目。"""
        set_overlay(OverlayPatch(project_id="proj-1", addr_id="D2/D2-2"))
        set_overlay(OverlayPatch(project_id="proj-2", addr_id="D3/D3-1"))

        clear_project_overlays("proj-1")
        assert get_project_overlays("proj-1") == {}
        assert len(get_project_overlays("proj-2")) == 1


# ─── Tests: ProjectOverlay.apply ─────────────────────────────────────────────


class TestProjectOverlayApply:
    def test_apply_no_project_id(self):
        """无 project_id 时直接返回原始条目。"""
        overlay = ProjectOverlay()
        entries = [{"addr_id": "D2/D2-2", "sheet_name": "明细表D2-2"}]
        result = overlay.apply("", entries)
        assert result is entries  # 同引用

    def test_apply_no_patches(self):
        """无 overlay 补丁时返回原始条目。"""
        overlay = ProjectOverlay()
        entries = [{"addr_id": "D2/D2-2", "sheet_name": "明细表D2-2"}]
        result = overlay.apply("proj-no-patches", entries)
        assert result is entries

    def test_apply_alias_add(self):
        """sheet_name_alias_add 追加别名（R5.2 核心行为）。"""
        overlay = ProjectOverlay()
        set_overlay(OverlayPatch(
            project_id="proj-1",
            addr_id="D2/D2-2",
            overrides={"sheet_name_alias_add": ["现场临时叫法", "D2明细"]},
            reason="项目模板差异",
            owner="zhangsan",
        ))

        entries = [{
            "addr_id": "D2/D2-2",
            "sheet_name": "明细表D2-2",
            "sheet_name_aliases": ["D2-2明细表"],
        }]

        result = overlay.apply("proj-1", entries)
        assert len(result) == 1
        aliases = result[0]["sheet_name_aliases"]
        assert "D2-2明细表" in aliases  # 原有保留
        assert "现场临时叫法" in aliases  # 新增
        assert "D2明细" in aliases  # 新增

    def test_apply_does_not_mutate_original(self):
        """应用 overlay 不修改原始条目（深拷贝）。"""
        overlay = ProjectOverlay()
        set_overlay(OverlayPatch(
            project_id="proj-1",
            addr_id="D2/D2-2",
            overrides={"sheet_name_alias_add": ["新别名"]},
        ))

        original = {
            "addr_id": "D2/D2-2",
            "sheet_name_aliases": ["原有别名"],
        }
        entries = [original]

        result = overlay.apply("proj-1", entries)
        # 原始条目不变
        assert original["sheet_name_aliases"] == ["原有别名"]
        # 返回新条目包含新别名
        assert "新别名" in result[0]["sheet_name_aliases"]

    def test_apply_alias_remove(self):
        """sheet_name_alias_remove 移除别名。"""
        overlay = ProjectOverlay()
        set_overlay(OverlayPatch(
            project_id="proj-1",
            addr_id="D2/D2-2",
            overrides={"sheet_name_alias_remove": ["旧叫法"]},
        ))

        entries = [{
            "addr_id": "D2/D2-2",
            "sheet_name_aliases": ["旧叫法", "保留叫法"],
        }]

        result = overlay.apply("proj-1", entries)
        assert "旧叫法" not in result[0]["sheet_name_aliases"]
        assert "保留叫法" in result[0]["sheet_name_aliases"]

    def test_apply_field_override(self):
        """直接字段覆盖（如 component_type）。"""
        overlay = ProjectOverlay()
        set_overlay(OverlayPatch(
            project_id="proj-1",
            addr_id="D2/D2-2",
            overrides={"component_type": "custom-d2-detail"},
        ))

        entries = [{
            "addr_id": "D2/D2-2",
            "component_type": "d2-accounts-receivable",
        }]

        result = overlay.apply("proj-1", entries)
        assert result[0]["component_type"] == "custom-d2-detail"

    def test_apply_expired_patch_skipped(self):
        """过期补丁不应用。"""
        overlay = ProjectOverlay()
        past = (date.today() - timedelta(days=1)).isoformat()
        set_overlay(OverlayPatch(
            project_id="proj-1",
            addr_id="D2/D2-2",
            overrides={"sheet_name_alias_add": ["不应出现"]},
            expires_at=past,
        ))

        entries = [{
            "addr_id": "D2/D2-2",
            "sheet_name_aliases": ["原有"],
        }]

        result = overlay.apply("proj-1", entries)
        # 过期补丁不生效
        assert result[0]["sheet_name_aliases"] == ["原有"]

    def test_apply_multiple_entries_selective(self):
        """多条目中只有匹配 addr_id 的被 patch。"""
        overlay = ProjectOverlay()
        set_overlay(OverlayPatch(
            project_id="proj-1",
            addr_id="D2/D2-2",
            overrides={"sheet_name_alias_add": ["新别名"]},
        ))

        entries = [
            {"addr_id": "D2/D2-2", "sheet_name_aliases": []},
            {"addr_id": "D3/D3-1", "sheet_name_aliases": []},
        ]

        result = overlay.apply("proj-1", entries)
        assert "新别名" in result[0]["sheet_name_aliases"]
        assert result[1]["sheet_name_aliases"] == []  # 未被 patch

    def test_apply_even_on_ambiguous_entries(self):
        """即使多个条目匹配（将来产生 ambiguous），overlay 仍先应用（R5.8）。"""
        overlay = ProjectOverlay()
        set_overlay(OverlayPatch(
            project_id="proj-1",
            addr_id="D2/D2-2",
            overrides={"sheet_name_alias_add": ["额外别名"]},
        ))
        set_overlay(OverlayPatch(
            project_id="proj-1",
            addr_id="D2/D2-3",
            overrides={"sheet_name_alias_add": ["另一个别名"]},
        ))

        # 两个条目都会被 patch（即使后续 resolve 可能返回 ambiguous）
        entries = [
            {"addr_id": "D2/D2-2", "sheet_name_aliases": []},
            {"addr_id": "D2/D2-3", "sheet_name_aliases": []},
        ]

        result = overlay.apply("proj-1", entries)
        assert "额外别名" in result[0]["sheet_name_aliases"]
        assert "另一个别名" in result[1]["sheet_name_aliases"]

    def test_apply_alias_add_deduplication(self):
        """追加别名去重：已存在的不重复添加。"""
        overlay = ProjectOverlay()
        set_overlay(OverlayPatch(
            project_id="proj-1",
            addr_id="D2/D2-2",
            overrides={"sheet_name_alias_add": ["已有别名", "新别名"]},
        ))

        entries = [{
            "addr_id": "D2/D2-2",
            "sheet_name_aliases": ["已有别名"],
        }]

        result = overlay.apply("proj-1", entries)
        aliases = result[0]["sheet_name_aliases"]
        assert aliases.count("已有别名") == 1  # 不重复
        assert "新别名" in aliases


# ─── Tests: ProjectOverlay.apply_to_single ───────────────────────────────────


class TestProjectOverlayApplyToSingle:
    def test_apply_to_single_with_patch(self):
        """单条目 apply 正常工作。"""
        overlay = ProjectOverlay()
        set_overlay(OverlayPatch(
            project_id="proj-1",
            addr_id="D2/D2-2",
            overrides={"display_label": "自定义标签"},
        ))

        entry = {"addr_id": "D2/D2-2", "display_label": "原标签"}
        result = overlay.apply_to_single("proj-1", entry)
        assert result["display_label"] == "自定义标签"
        # 原始不变
        assert entry["display_label"] == "原标签"

    def test_apply_to_single_no_patch(self):
        """无对应 patch 时返回原条目。"""
        overlay = ProjectOverlay()
        entry = {"addr_id": "D2/D2-2", "display_label": "原标签"}
        result = overlay.apply_to_single("proj-1", entry)
        assert result is entry  # 同引用


# ─── Tests: get_project_aliases ──────────────────────────────────────────────


class TestGetProjectAliases:
    def test_get_aliases_from_overlays(self):
        """提取项目级别名映射。"""
        overlay = ProjectOverlay()
        set_overlay(OverlayPatch(
            project_id="proj-1",
            addr_id="D2/D2-2",
            overrides={"sheet_name_alias_add": ["别名A", "别名B"]},
        ))
        set_overlay(OverlayPatch(
            project_id="proj-1",
            addr_id="D3/D3-1",
            overrides={"sheet_name_alias_add": ["别名C"]},
        ))

        aliases = overlay.get_project_aliases("proj-1")
        assert aliases == {
            "D2/D2-2": ["别名A", "别名B"],
            "D3/D3-1": ["别名C"],
        }

    def test_get_aliases_empty_project(self):
        """无 overlay 的项目返回空 dict。"""
        overlay = ProjectOverlay()
        assert overlay.get_project_aliases("no-proj") == {}

    def test_get_aliases_excludes_expired(self):
        """过期的 patch 的别名不返回。"""
        overlay = ProjectOverlay()
        past = (date.today() - timedelta(days=1)).isoformat()
        set_overlay(OverlayPatch(
            project_id="proj-1",
            addr_id="D2/D2-2",
            overrides={"sheet_name_alias_add": ["不该出现"]},
            expires_at=past,
        ))

        aliases = overlay.get_project_aliases("proj-1")
        assert aliases == {}

    def test_get_aliases_excludes_non_alias_overrides(self):
        """非 alias 类的 override 不出现在 aliases 结果中。"""
        overlay = ProjectOverlay()
        set_overlay(OverlayPatch(
            project_id="proj-1",
            addr_id="D2/D2-2",
            overrides={"component_type": "custom"},
        ))

        aliases = overlay.get_project_aliases("proj-1")
        assert aliases == {}


# ─── Tests: validate_ownership (R24.1) ──────────────────────────────────────


class TestValidateOwnership:
    @pytest.mark.asyncio
    async def test_valid_ownership(self):
        """项目存在且 wp 归属正确时校验通过。"""
        db = _mock_db_session(project_exists=True, wp_exists=True)
        result = await validate_ownership(db, "proj-1", "D2/D2-2")
        assert result is True

    @pytest.mark.asyncio
    async def test_project_not_found(self):
        """项目不存在时抛出 OverlayOwnershipError。"""
        db = _mock_db_session(project_exists=False, wp_exists=True)
        with pytest.raises(OverlayOwnershipError) as exc_info:
            await validate_ownership(db, "bad-proj", "D2/D2-2")
        assert "not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_wp_not_in_project(self):
        """项目存在但 wp 不归属时抛出 OverlayOwnershipError。"""
        db = _mock_db_session(project_exists=True, wp_exists=False)
        with pytest.raises(OverlayOwnershipError) as exc_info:
            await validate_ownership(db, "proj-1", "D2/D2-2")
        assert "D2" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_single_segment_addr_id_only_checks_project(self):
        """单段 addr_id（无 sheet 级别信息）只验证项目存在。"""
        db = _mock_db_session(project_exists=True, wp_exists=True)
        # 单段 addr_id 例如 "D2"（无 /）→ 仅验证项目
        result = await validate_ownership(db, "proj-1", "D2")
        assert result is True
        # 只调用了一次（项目检查）
        assert db.execute.call_count == 1


# ─── Tests: write_overlay (R24.1 带校验写入) ────────────────────────────────


class TestWriteOverlay:
    @pytest.mark.asyncio
    async def test_write_with_valid_ownership(self):
        """归属校验通过后写入成功。"""
        db = _mock_db_session(project_exists=True, wp_exists=True)
        patch = await write_overlay(
            db,
            project_id="proj-1",
            addr_id="D2/D2-2",
            overrides={"sheet_name_alias_add": ["新叫法"]},
            reason="项目模板差异",
            owner="zhangsan",
            expires_at="2026-12-31",
        )

        assert patch.project_id == "proj-1"
        assert patch.addr_id == "D2/D2-2"
        assert patch.reason == "项目模板差异"
        assert patch.owner == "zhangsan"
        assert patch.expires_at == "2026-12-31"

        # R9 (acnr-invalidation-overlay-hardening)：write_overlay 写 PG 后**清缓存**
        # （不再 set_overlay_in_cache 未提交状态）→ get_overlay 返回 None，
        # 下次读经 read-through 从已提交 PG 重载。外层回滚不留脏缓存。
        assert get_overlay("proj-1", "D2/D2-2") is None

    @pytest.mark.asyncio
    async def test_write_rejects_bad_project(self):
        """项目不存在时写入失败且 store 不变。"""
        db = _mock_db_session(project_exists=False, wp_exists=True)
        with pytest.raises(OverlayOwnershipError):
            await write_overlay(
                db,
                project_id="bad-proj",
                addr_id="D2/D2-2",
                overrides={"sheet_name_alias_add": ["不该存"]},
                reason="test",
                owner="test",
            )

        assert get_overlay("bad-proj", "D2/D2-2") is None

    @pytest.mark.asyncio
    async def test_write_rejects_bad_wp(self):
        """wp 不归属该项目时写入失败。"""
        db = _mock_db_session(project_exists=True, wp_exists=False)
        with pytest.raises(OverlayOwnershipError):
            await write_overlay(
                db,
                project_id="proj-1",
                addr_id="D2/D2-2",
                overrides={"sheet_name_alias_add": ["不该存"]},
                reason="test",
                owner="test",
            )

        assert get_overlay("proj-1", "D2/D2-2") is None


# ─── Tests: get_project_overlay singleton ────────────────────────────────────


class TestProjectOverlaySingleton:
    def test_singleton_returns_instance(self):
        """get_project_overlay 返回 ProjectOverlay 实例。"""
        overlay = get_project_overlay()
        assert isinstance(overlay, ProjectOverlay)

    def test_singleton_same_instance(self):
        """多次调用返回同一实例。"""
        a = get_project_overlay()
        b = get_project_overlay()
        assert a is b
