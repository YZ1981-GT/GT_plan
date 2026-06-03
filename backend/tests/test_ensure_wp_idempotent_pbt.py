# Feature: custom-workpaper-formula-binding, Property 14: working_paper 幂等生成
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from hypothesis import given, settings, strategies as st

from app.models.workpaper_models import WpSourceType
from app.services.workpaper_generation_service import WorkpaperGenerationService

_cn_names = st.sampled_from(["自定义底稿", "应收账款表", "固定资产台账"])


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@settings(max_examples=5)
@given(calls=st.integers(min_value=2, max_value=4), wp_name=_cn_names)
def test_p14_ensure_idempotent(calls: int, wp_name: str):
    project_id = uuid.uuid4()
    wp_index_id = uuid.uuid4()
    mock_index = MagicMock()
    mock_index.wp_code = "CUST-P14"
    mock_index.wp_name = wp_name
    mock_index.audit_cycle = "A"
    mock_index.project_id = project_id

    stored: list = []
    exec_n = 0

    async def fake_execute(_stmt):
        nonlocal exec_n
        exec_n += 1
        r = MagicMock()
        if stored:
            r.scalar_one_or_none.return_value = stored[0]
        elif exec_n == 1:
            r.scalar_one_or_none.return_value = None
        else:
            r.scalar_one_or_none.return_value = mock_index
        return r

    db = AsyncMock()
    db.execute = fake_execute
    db.add = lambda wp: stored.append(wp) if not stored else None
    db.flush = AsyncMock()

    svc = WorkpaperGenerationService()

    async def _inner():
        results = []
        for _ in range(calls):
            results.append(
                await svc.ensure_working_paper(
                    db, project_id, wp_index_id, source_type=WpSourceType.manual
                )
            )
        return results

    with patch.object(Path, "mkdir"), patch.object(Path, "exists", return_value=True):
        results = _run(_inner())
    assert len(stored) == 1
    assert all(r is results[0] for r in results)
