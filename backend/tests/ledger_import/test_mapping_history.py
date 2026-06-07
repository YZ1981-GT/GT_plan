"""历史映射保存与复用单元测试。

测试覆盖：
- 7.1: save_mapping 创建记录（fingerprint 正确存储）
- 7.2: override_parent_id 形成父子链
- 7.3: detect 找到历史映射 → 标记 auto_applied_from_history
- 7.4: 跨项目匹配必须 requires_user_confirmation=True
- 7.5: 超过 30 天的记录不返回
"""

import pytest
from datetime import datetime, timedelta, timezone

from app.services.ledger_import.mapping_history_service import (
    MappingHistoryService,
    MappingHistoryRecord,
)


@pytest.fixture
def service() -> MappingHistoryService:
    return MappingHistoryService()


SAMPLE_ENTRIES = [
    {"column_index": 0, "original_header": "科目编码", "canonical_header": "科目编码", "standard_field": "account_code"},
    {"column_index": 1, "original_header": "借方", "canonical_header": "借方", "standard_field": "debit_amount"},
]


# ---------------------------------------------------------------------------
# 7.1: save_mapping 创建记录
# ---------------------------------------------------------------------------


class TestSaveMapping:
    """7.1: save_mapping creates record with fingerprints."""

    @pytest.mark.asyncio
    async def test_save_creates_record_with_fingerprints(self, service: MappingHistoryService):
        record = await service.save_mapping(
            project_id="proj-001",
            file_fingerprint="sha256:abc123",
            software_fingerprint="yonyou-u8",
            mapping_entries=SAMPLE_ENTRIES,
        )
        assert record.id is not None
        assert record.project_id == "proj-001"
        assert record.file_fingerprint == "sha256:abc123"
        assert record.software_fingerprint == "yonyou-u8"
        assert record.mapping_entries == SAMPLE_ENTRIES
        assert record.override_parent_id is None
        assert record.created_at is not None

    @pytest.mark.asyncio
    async def test_save_without_software_fingerprint(self, service: MappingHistoryService):
        record = await service.save_mapping(
            project_id="proj-001",
            file_fingerprint="sha256:def456",
            software_fingerprint=None,
            mapping_entries=SAMPLE_ENTRIES,
        )
        assert record.software_fingerprint is None


# ---------------------------------------------------------------------------
# 7.2: override_parent_id 父子链
# ---------------------------------------------------------------------------


class TestOverrideParentChain:
    """7.2: override_parent_id creates parent chain."""

    @pytest.mark.asyncio
    async def test_override_parent_creates_chain(self, service: MappingHistoryService):
        # First record (original)
        parent = await service.save_mapping(
            project_id="proj-001",
            file_fingerprint="sha256:abc",
            software_fingerprint="yonyou",
            mapping_entries=SAMPLE_ENTRIES,
        )

        # Second record overrides the first
        child = await service.save_mapping(
            project_id="proj-001",
            file_fingerprint="sha256:abc",
            software_fingerprint="yonyou",
            mapping_entries=[{"column_index": 0, "standard_field": "account_name"}],
            override_parent_id=parent.id,
        )

        assert child.override_parent_id == parent.id
        assert child.id != parent.id

    @pytest.mark.asyncio
    async def test_multi_level_chain(self, service: MappingHistoryService):
        r1 = await service.save_mapping(
            project_id="proj-001",
            file_fingerprint="sha256:x",
            software_fingerprint=None,
            mapping_entries=SAMPLE_ENTRIES,
        )
        r2 = await service.save_mapping(
            project_id="proj-001",
            file_fingerprint="sha256:x",
            software_fingerprint=None,
            mapping_entries=SAMPLE_ENTRIES,
            override_parent_id=r1.id,
        )
        r3 = await service.save_mapping(
            project_id="proj-001",
            file_fingerprint="sha256:x",
            software_fingerprint=None,
            mapping_entries=SAMPLE_ENTRIES,
            override_parent_id=r2.id,
        )

        # Verify chain: r3 → r2 → r1
        assert r3.override_parent_id == r2.id
        assert r2.override_parent_id == r1.id
        assert r1.override_parent_id is None


# ---------------------------------------------------------------------------
# 7.3: detect 命中历史 → auto_applied_from_history
# ---------------------------------------------------------------------------


class TestAutoApplyHistory:
    """7.3: detect finds history → marks auto_applied_from_history."""

    @pytest.mark.asyncio
    async def test_find_and_apply_same_project(self, service: MappingHistoryService):
        await service.save_mapping(
            project_id="proj-001",
            file_fingerprint="sha256:target",
            software_fingerprint="kingdee",
            mapping_entries=SAMPLE_ENTRIES,
        )

        # Find within same project
        found = await service.find_matching_history(
            file_fingerprint="sha256:target",
            software_fingerprint="kingdee",
            project_id="proj-001",
        )
        assert found is not None

        # Apply to same project
        result = await service.apply_history_mapping(found, target_project_id="proj-001")
        assert result["auto_applied_from_history"] is True
        assert result["history_mapping_id"] == found.id
        assert result["requires_user_confirmation"] is False
        assert result["mapping_entries"] == SAMPLE_ENTRIES

    @pytest.mark.asyncio
    async def test_find_prefers_software_fingerprint_match(self, service: MappingHistoryService):
        # Save two records with same file_fingerprint but different software
        await service.save_mapping(
            project_id="proj-001",
            file_fingerprint="sha256:same",
            software_fingerprint="generic",
            mapping_entries=[{"field": "a"}],
        )
        await service.save_mapping(
            project_id="proj-001",
            file_fingerprint="sha256:same",
            software_fingerprint="yonyou",
            mapping_entries=[{"field": "b"}],
        )

        found = await service.find_matching_history(
            file_fingerprint="sha256:same",
            software_fingerprint="yonyou",
            project_id="proj-001",
        )
        assert found is not None
        assert found.software_fingerprint == "yonyou"
        assert found.mapping_entries == [{"field": "b"}]


# ---------------------------------------------------------------------------
# 7.4: 跨项目匹配必须显式确认
# ---------------------------------------------------------------------------


class TestCrossProjectConfirmation:
    """7.4: cross-project match requires explicit confirmation."""

    @pytest.mark.asyncio
    async def test_cross_project_requires_confirmation(self, service: MappingHistoryService):
        # Save in project A
        await service.save_mapping(
            project_id="proj-A",
            file_fingerprint="sha256:shared",
            software_fingerprint="yonyou",
            mapping_entries=SAMPLE_ENTRIES,
        )

        # Find without project filter (cross-project search)
        found = await service.find_matching_history(
            file_fingerprint="sha256:shared",
            software_fingerprint="yonyou",
            project_id=None,
        )
        assert found is not None

        # Apply to different project B → must require confirmation
        result = await service.apply_history_mapping(found, target_project_id="proj-B")
        assert result["requires_user_confirmation"] is True
        assert result["auto_applied_from_history"] is True
        assert result["source_project_id"] == "proj-A"

    @pytest.mark.asyncio
    async def test_same_project_no_confirmation_needed(self, service: MappingHistoryService):
        await service.save_mapping(
            project_id="proj-A",
            file_fingerprint="sha256:local",
            software_fingerprint=None,
            mapping_entries=SAMPLE_ENTRIES,
        )

        found = await service.find_matching_history(
            file_fingerprint="sha256:local",
            project_id="proj-A",
        )
        assert found is not None

        result = await service.apply_history_mapping(found, target_project_id="proj-A")
        assert result["requires_user_confirmation"] is False

    @pytest.mark.asyncio
    async def test_project_filter_excludes_other_projects(self, service: MappingHistoryService):
        await service.save_mapping(
            project_id="proj-X",
            file_fingerprint="sha256:filtered",
            software_fingerprint=None,
            mapping_entries=SAMPLE_ENTRIES,
        )

        # Search restricted to proj-Y → should not find
        found = await service.find_matching_history(
            file_fingerprint="sha256:filtered",
            project_id="proj-Y",
        )
        assert found is None


# ---------------------------------------------------------------------------
# 7.5: 30 天窗口 / 过期不复用
# ---------------------------------------------------------------------------


class TestExpiryWindow:
    """7.5: records older than 30 days not returned."""

    @pytest.mark.asyncio
    async def test_expired_record_not_returned(self, service: MappingHistoryService):
        # Manually insert an old record
        old_record = MappingHistoryRecord(
            id="old-001",
            project_id="proj-001",
            file_fingerprint="sha256:old",
            software_fingerprint="yonyou",
            mapping_entries=SAMPLE_ENTRIES,
            created_at=datetime.now(timezone.utc) - timedelta(days=31),
        )
        service._store[old_record.id] = old_record

        found = await service.find_matching_history(
            file_fingerprint="sha256:old",
            project_id="proj-001",
        )
        assert found is None

    @pytest.mark.asyncio
    async def test_record_within_window_returned(self, service: MappingHistoryService):
        # Record 29 days old → still valid
        recent_record = MappingHistoryRecord(
            id="recent-001",
            project_id="proj-001",
            file_fingerprint="sha256:recent",
            software_fingerprint=None,
            mapping_entries=SAMPLE_ENTRIES,
            created_at=datetime.now(timezone.utc) - timedelta(days=29),
        )
        service._store[recent_record.id] = recent_record

        found = await service.find_matching_history(
            file_fingerprint="sha256:recent",
            project_id="proj-001",
        )
        assert found is not None
        assert found.id == "recent-001"

    @pytest.mark.asyncio
    async def test_exactly_30_days_is_expired(self, service: MappingHistoryService):
        # Record exactly at 30-day boundary → expired (cutoff is strict <)
        boundary_record = MappingHistoryRecord(
            id="boundary-001",
            project_id="proj-001",
            file_fingerprint="sha256:boundary",
            software_fingerprint=None,
            mapping_entries=SAMPLE_ENTRIES,
            created_at=datetime.now(timezone.utc) - timedelta(days=30, seconds=1),
        )
        service._store[boundary_record.id] = boundary_record

        found = await service.find_matching_history(
            file_fingerprint="sha256:boundary",
            project_id="proj-001",
        )
        assert found is None

    @pytest.mark.asyncio
    async def test_find_returns_most_recent(self, service: MappingHistoryService):
        # Two valid records, should return the most recent
        older = MappingHistoryRecord(
            id="older-001",
            project_id="proj-001",
            file_fingerprint="sha256:multi",
            software_fingerprint=None,
            mapping_entries=[{"field": "old"}],
            created_at=datetime.now(timezone.utc) - timedelta(days=10),
        )
        newer = MappingHistoryRecord(
            id="newer-001",
            project_id="proj-001",
            file_fingerprint="sha256:multi",
            software_fingerprint=None,
            mapping_entries=[{"field": "new"}],
            created_at=datetime.now(timezone.utc) - timedelta(days=2),
        )
        service._store[older.id] = older
        service._store[newer.id] = newer

        found = await service.find_matching_history(
            file_fingerprint="sha256:multi",
            project_id="proj-001",
        )
        assert found is not None
        assert found.id == "newer-001"
