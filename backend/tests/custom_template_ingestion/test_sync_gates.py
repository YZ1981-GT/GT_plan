"""Task 14 守卫：四 sync gate 当前必须诚实报 BLOCKED。"""
from __future__ import annotations

import pytest

from app.services.custom_template_ingestion.sync_gates import (
    assert_all_sync_gates_clear,
    probe_all_sync_gates,
)


def test_sync_gates_currently_blocked():
    report = probe_all_sync_gates()
    assert report.all_clear is False
    assert report.multi_resolver is False
    assert report.entry_namespace is False
    assert report.unified_room is False
    assert report.durable_application is False
    assert len(report.blockers) >= 2
    with pytest.raises(RuntimeError, match="SYNC gates"):
        assert_all_sync_gates_clear()
