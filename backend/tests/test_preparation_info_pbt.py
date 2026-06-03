# Feature: custom-workpaper-formula-binding, Property 7/8: 编制信息降级 + 无会计期间
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from hypothesis import given, settings, strategies as st

from app.routers.wp_render_config import _build_preparation_info

REQUIRED = {
    "entity_name",
    "period_end",
    "preparer",
    "prep_date",
    "reviewer",
    "review_date",
    "index_no",
}


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _render(v: str) -> str:
    return v if v and str(v).strip() else "—"


@settings(max_examples=5)
@given(
    entity=st.one_of(st.none(), st.just(""), st.just("致同测试"), st.just("中文公司")),
    period=st.one_of(st.none(), st.just(""), st.just("2025-12-31")),
    preparer=st.one_of(st.none(), st.just(""), st.just("张三")),
)
def test_p7_preparation_info_never_null_and_degrades(entity, period, preparer):
    project_id = uuid.uuid4()
    wp_id = uuid.uuid4()

    async def fake_execute(stmt, params=None):
        sql = str(stmt)
        if "projects" in sql:
            r = MagicMock()
            r.first.return_value = (entity, period)
            return r
        if "project_assignments" in sql:

            class _Rows:
                def __iter__(self):
                    if preparer:
                        yield ("preparer", preparer)
                    return self

            return _Rows()
        r = MagicMock()
        r.first.return_value = (datetime(2026, 1, 1, tzinfo=timezone.utc), "D1-1")
        return r

    db = AsyncMock()
    db.execute = fake_execute
    db.get = AsyncMock(return_value=None)

    info = _run(_build_preparation_info(db, project_id, wp_id))

    assert set(info.keys()) == REQUIRED
    assert "accounting_period" not in info
    for k, v in info.items():
        rendered = _render(v)
        assert rendered is not None
        assert rendered != "null"


