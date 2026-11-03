"""质控分类组别读者收口（spec trim-followup-residual-findings-closure R3，后端部分）。

原状（可打红）：A17 一致性按首字母 ``startswith("A")`` 判 A 类（未登记值 ``ABC`` 也算 A），复核上下文与 A17-1 的
project_context 只给分类原值，前端各自按 ``=== 'A'`` / 首字母 / 下标再判一遍（A1~A8 项目在 A1-11 被当成非 A 类）。
现：两处下发 ``project_classification``（project_classification 单一解释），A17 一致性经 ``resolve`` 判组别。
"""
from __future__ import annotations

import asyncio
import types
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.project_classification import resolve


@pytest.mark.parametrize(("value", "expected"), [
    ("A", True), ("A1", True), (" a8 ", True), ("上市公司", True), ("A股上市公司", True),
    ("ABC", False), ("A9", False), ("IPO", False), ("B1", False), ("C", False), ("", False), (None, False),
])
def test_a17_is_a_class_or_listed_uses_single_classification(value, expected):
    from app.services.a17_consistency_checker import is_a_class_or_listed

    assert is_a_class_or_listed(value) is expected


def _review_db(project_row):
    """get_review_context 的查询顺序：项目行 → 组成部分 EXISTS → IT EXISTS。"""
    first = MagicMock()
    first.first.return_value = project_row
    exists = MagicMock()
    exists.scalar.return_value = False
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[first, exists, exists])
    return db


@pytest.mark.parametrize(("row", "group", "code", "defaulted"), [
    (("A1", "financial", False, "listed", "listed"), "A", "A1", False),
    (("B2", "financial", False, "normal", "soe"), "B", "B2", False),
    ((None, None, False, "normal", "soe"), "C", None, True),
    (("IPO", "financial", False, "normal", "soe"), "C", None, True),  # 迁移前残留的旧场景值
])
def test_review_context_carries_project_classification(row, group, code, defaulted):
    from app.services.review_checklist_service import get_review_context

    ctx = asyncio.run(get_review_context(_review_db(row), uuid.uuid4()))
    pc = ctx["project_classification"]
    assert (pc["category_group"], pc["category_code"], pc["defaulted"]) == (group, code, defaulted)
    assert pc == resolve(row[0], row[3], row[4]).as_dict()
    assert ctx["business_category"] == (code or group)  # 旧键保留，口径不变


def test_review_context_missing_project_defaults_to_c():
    from app.services.review_checklist_service import get_review_context

    db = MagicMock()
    missing = MagicMock()
    missing.first.return_value = None
    db.execute = AsyncMock(return_value=missing)
    ctx = asyncio.run(get_review_context(db, uuid.uuid4()))
    assert ctx["project_classification"] == resolve(None).as_dict()


@pytest.mark.parametrize(("category", "group"), [("A1", "A"), ("B3", "B"), (None, "C")])
def test_a171_project_context_carries_project_classification(category, group):
    """签字栏组别由前端读 project_context.project_classification（原按 business_category 首字母）。"""
    from app.routers.wp_render_strategies import _a171_audit_summary as a171

    empty = MagicMock()
    empty.fetchall.return_value = []
    proj = MagicMock()
    proj.fetchone.return_value = types.SimpleNamespace(client_name="客户", audit_year=2025, business_category=category)
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[empty, proj, empty])
    ctx = types.SimpleNamespace(wp_id=uuid.uuid4(), db=db, project_id=uuid.uuid4(), business_category=category,
                                project_classification=None)
    out = asyncio.run(a171.render(ctx))
    pc = out["project_context"]["project_classification"]
    assert pc["category_group"] == group
    assert pc == resolve(category).as_dict()
