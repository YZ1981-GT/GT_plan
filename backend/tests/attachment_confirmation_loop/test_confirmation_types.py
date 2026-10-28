"""函证类型补齐与校验（spec attachment-confirmation-evidence-loop 需求 5.1，ADR-ACE-05）。

改造前：类型只有应收 / 应付 / 银行 / 借款，创建 / 更新 / 批量同步都不校验，任意字符串都能落库；
A12-1 律师询证函进不了函证中心。经 HTTP 真发请求（权限世界：真实成员行与生产门禁）。
"""
from __future__ import annotations

import pytest
import pytest_asyncio
import sqlalchemy as sa

from app.models.confirmation_models import Confirmation, ConfirmationType
from app.routers import confirmations as confirmations_router_module
from app.services import confirmation_service
from app.services.confirmation_types import CONFIRM_TYPE_LABELS, VALID_CONFIRM_TYPES, check_confirm_type
from tests.attachment_security_baseline._world import add_confirmation, sqlite_attachment_world

ROUTER = confirmations_router_module.router


@pytest_asyncio.fixture
async def world(monkeypatch):
    async with sqlite_attachment_world(monkeypatch) as w:
        yield w


def _base(world) -> str:
    return f"/api/projects/{world.target.id}/confirmations"


def test_labels_cover_enum_exactly():
    assert set(CONFIRM_TYPE_LABELS) == set(VALID_CONFIRM_TYPES) == {t.value for t in ConfirmationType}
    assert {"legal", "other"} <= set(VALID_CONFIRM_TYPES)
    assert CONFIRM_TYPE_LABELS["legal"] == "律师"


def test_check_strips_and_rejects():
    assert check_confirm_type(" legal ") == "legal"
    with pytest.raises(ValueError, match="不支持的函证类型"):
        check_confirm_type("customer")


@pytest.mark.asyncio
@pytest.mark.parametrize("confirm_type", sorted(VALID_CONFIRM_TYPES))
async def test_create_accepts_all_six(world, confirm_type):
    user = (await world.edit_member()).user
    async with world.client(ROUTER, user=user) as client:
        resp = await client.post(_base(world), json={"confirm_type": confirm_type, "counterparty": "某律师事务所"})
    assert resp.status_code == 200, resp.text
    rows = (await world.db.execute(sa.select(Confirmation.confirm_type))).scalars().all()
    assert rows == [confirm_type]


@pytest.mark.asyncio
async def test_unknown_type_is_422_everywhere_and_writes_nothing(world):
    user = (await world.edit_member()).user
    existing = await add_confirmation(world, world.target)
    async with world.client(ROUTER, user=user) as client:
        created = await client.post(_base(world), json={"confirm_type": "customer", "counterparty": "甲"})
        updated = await client.put(f"{_base(world)}/{existing.id}", json={"confirm_type": "lawyer"})
        synced = await client.post(
            f"{_base(world)}/batch-sync", json={"items": [{"confirm_type": "x", "counterparty": "乙"}]},
        )
    assert (created.status_code, updated.status_code, synced.status_code) == (422, 422, 422)
    assert "不支持的函证类型" in created.text
    types = (await world.db.execute(sa.select(Confirmation.confirm_type))).scalars().all()
    assert types == ["receivable"]  # 只有造数那一笔，且没被改


@pytest.mark.asyncio
@pytest.mark.parametrize("confirm_type", ["legal", "other"])
async def test_legal_and_other_have_no_candidates(confirm_type):
    # 候选按科目前缀从辅助余额表取；没有前缀的类型在查库前返回空
    assert await confirmation_service.list_confirmation_candidates(None, None, confirm_type, 2025) == []
