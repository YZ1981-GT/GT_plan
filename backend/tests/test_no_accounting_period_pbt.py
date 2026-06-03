# Feature: custom-workpaper-formula-binding, Property 8: "会计期间"恒不渲染
"""编制信息 API / B-Index 自动生成 / 表头契约：永不暴露 accounting_period。"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from hypothesis import given, settings, strategies as st

from app.routers.wp_render_config import (
    _build_preparation_info,
    _generate_b_index_data,
)
from app.services.wp_classification_service import (
    ClassificationResult,
    derive_component_type,
)

PREP_FIELDS = {
    "entity_name",
    "period_end",
    "preparer",
    "prep_date",
    "reviewer",
    "review_date",
    "index_no",
}

B_INDEX_PREP_LABELS = {
    "被审计单位",
    "截止日",
    "编制人",
    "编制日期",
    "复核人",
    "复核日期",
    "索引号",
}

FORBIDDEN_LABELS = {"会计期间", "accounting_period"}


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _mock_db_for_prep(entity, period, preparer="张三"):
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
        r.first.return_value = (datetime(2026, 1, 1, tzinfo=timezone.utc), "CUST-01")
        return r

    db = AsyncMock()
    db.execute = fake_execute
    db.get = AsyncMock(return_value=None)
    return db, project_id, wp_id


@settings(max_examples=5)
@given(
    entity=st.one_of(st.none(), st.just(""), st.just("致同中文项目")),
    period=st.one_of(st.none(), st.just(""), st.just("2025-12-31")),
)
def test_p8_build_preparation_info_excludes_accounting_period(entity, period):
    db, project_id, wp_id = _mock_db_for_prep(entity, period)
    info = _run(_build_preparation_info(db, project_id, wp_id))
    assert set(info.keys()) == PREP_FIELDS
    assert "accounting_period" not in info


@settings(max_examples=5)
@given(wp_name=st.sampled_from(["自定义底稿", "应收账款明细", "CUST表"]))
def test_p8_b_index_auto_prep_has_no_accounting_period(wp_name: str):
    project_id = uuid.uuid4()
    wp_id = uuid.uuid4()
    db, _, _ = _mock_db_for_prep("测试单位", "2025-12-31")

    classifications = [
        ClassificationResult(
            wp_code="CUST-01",
            sheet_name=wp_name,
            class_code="CUSTOM",
            class_="自定义底稿",
            scope="standalone",
            is_real_workpaper=True,
            delegated_module=None,
            render_schema_path=None,
            template_version_id=None,
        )
    ]

    data = _run(_generate_b_index_data(db, project_id, wp_id, classifications))
    prep = data.get("preparation_info") or {}
    assert "accounting_period" not in prep
    assert set(prep.keys()) == PREP_FIELDS


def test_p8_frontend_label_set_never_includes_accounting_period():
    """表头/B-Index 展示字段集合（中文 label + 英文 key）不含会计期间。"""
    rendered = set(PREP_FIELDS) | B_INDEX_PREP_LABELS
    assert not (FORBIDDEN_LABELS & rendered)


def test_custom_class_code_maps_to_custom_component():
    cls = ClassificationResult(
        wp_code="CUST-01",
        sheet_name="测试",
        class_code="CUSTOM",
        class_="自定义底稿",
        scope="standalone",
        is_real_workpaper=True,
        delegated_module=None,
        render_schema_path=None,
        template_version_id=None,
    )
    assert derive_component_type(cls) == "custom"
