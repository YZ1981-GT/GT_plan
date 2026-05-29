"""PBT P-3: disclosure sync consistency. Validates: Requirements US-3 P-3"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, AsyncMock
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from app.services.wp_disclosure_sync_service import WpDisclosureSyncService, ConflictError

cell_val = st.one_of(st.integers(-9999, 9999), st.text(min_size=0, max_size=10), st.none())
row_st = st.dictionaries(keys=st.from_regex(r"[a-z]{1,5}", fullmatch=True), values=cell_val, min_size=1, max_size=3)
sub_table_st = st.dictionaries(keys=st.from_regex(r"st_[a-z]{2,4}", fullmatch=True), values=st.lists(row_st, min_size=1, max_size=2), min_size=1, max_size=2)


class FakeNote:
    def __init__(self, section="五-1-1", is_stale=True, updated_at=None, last_sync_at=None):
        self.id = uuid.uuid4()
        self.project_id = uuid.uuid4()
        self.note_section = section
        self.table_data = {}
        self.is_stale = is_stale
        self.updated_at = updated_at or datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.last_sync_at = last_sync_at
        self.last_sync_source = None
        self.last_sync_wp_id = None
        self.last_sync_user_id = None
        self.updated_by = None
        self.is_deleted = False


class FakeUser:
    def __init__(self):
        self.id = uuid.uuid4()


class FakeDB:
    def __init__(self):
        self.added = []
        self.committed = False
    async def execute(self, stmt):
        return MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    def add(self, obj):
        self.added.append(obj)
    async def flush(self):
        pass
    async def commit(self):
        self.committed = True
    async def rollback(self):
        pass
