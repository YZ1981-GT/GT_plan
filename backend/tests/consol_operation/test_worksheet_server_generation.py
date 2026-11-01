from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401
from app.models.base import Base
from app.models.consol_worksheet_data_models import ConsolWorksheetData
from app.services.consol_tree_service import TreeNode
from app.services.consol_worksheet_generation_service import (
    WorksheetGenerationError,
    issue_preview_token,
    load_snapshot,
    verify_preview_token,
)
from app.services.consol_worksheet_group_builder import build_groups_from_worksheet

YEAR = 2025


def tree() -> TreeNode:
    return TreeNode(
        project_id=uuid.uuid4(), company_code="G", company_name="集团",
        parent_company_code=None, ultimate_company_code="G", consol_level=2,
        node_key="G:consol", role="consol", kind="aggregate",
        children=[
            TreeNode(
                project_id=uuid.uuid4(), company_code="A", company_name="甲公司",
                parent_company_code="G", ultimate_company_code="G", consol_level=1,
                node_key="A:subsidiary", role="subsidiary", kind="data",
            ),
            TreeNode(
                project_id=uuid.uuid4(), company_code="B", company_name="乙公司",
                parent_company_code="G", ultimate_company_code="G", consol_level=1,
                node_key="B:subsidiary", role="subsidiary", kind="data",
            ),
        ],
    )


def contents() -> dict:
    return {
        "info": {"rows": [
            {"company_code": "A", "company_name": "甲公司", "non_common_ratio": 60},
            {"company_code": "B", "company_name": "乙公司", "common_ratio": 80},
        ]},
        "equity_sim": {"rows": {"direct": [
            {"isStep": True, "step": "期初长投模拟", "values": []},
            {"direction": "借", "subject": "长期股权投资", "detail": "损益调整", "values": [10, 20]},
            {"direction": "贷", "subject": "年初未分配利润", "detail": "", "values": [10, 20]},
            {"isStep": True, "step": "模拟当期长期股权投资", "values": []},
        ]}},
        "internal_arap": {"rows": [{
            "localCompany": "甲公司", "localSubject": "应收账款", "localAmounts": [100],
            "localImpairments": [5], "remoteCompany": "乙公司", "remoteSubject": "应付账款",
            "remoteAmounts": [90], "remoteImpairments": [0],
        }]},
        "internal_trade": {"rows": [{
            "sellerCompany": "甲公司", "buyerCompany": "乙公司",
            "sellerAmount": 80, "buyerAmount": 70,
            "unrealizedProfit": 20, "inventoryRatio": 50,
        }]},
    }


def test_server_builder_matches_canonical_origin_keys_and_amounts():
    groups, origins, summary = build_groups_from_worksheet(contents(), tree())
    by_key = {group.origin_key: group for group in groups}
    assert origins == ["ws_equity_sim", "ws_internal_arap", "ws_internal_trade"]
    assert set(by_key) == {
        "equity_sim:step1:A", "equity_sim:step1:B",
        "internal_arap:pair:应收账款|应付账款",
        "internal_arap:bad_debt_local:应收账款|应付账款",
        "internal_trade:revenue", "internal_trade:unrealized",
    }
    assert [line.amount for line in by_key["equity_sim:step1:A"].lines] == [10, 10]
    pair = by_key["internal_arap:pair:应收账款|应付账款"]
    assert [(line.subject, line.direction, line.amount) for line in pair.lines] == [
        ("应付账款", "借", 90), ("应收账款", "贷", 90),
    ]
    assert by_key["internal_trade:unrealized"].lines[0].amount == 10
    assert summary == {
        "company_count": 2,
        "group_count": 6,
        "groups_by_origin": {
            "ws_equity_sim": 2, "ws_internal_arap": 2, "ws_internal_trade": 2,
        },
    }


def test_preview_token_binds_project_year_versions_and_digest(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.services.consol_worksheet_generation_service._secret", lambda: b"test-secret")
    payload = {"project_id": str(uuid.uuid4()), "year": YEAR, "versions": {"equity_sim": 3}, "source_digest": "a" * 64}
    token = issue_preview_token(payload)
    verify_preview_token(token, payload)
    with pytest.raises(WorksheetGenerationError) as changed:
        verify_preview_token(token, {**payload, "versions": {"equity_sim": 4}})
    assert changed.value.code == "PREVIEW_CHANGED"
    with pytest.raises(WorksheetGenerationError) as tampered:
        verify_preview_token(token + "x", payload)
    assert tampered.value.code == "PREVIEW_INVALID"


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[ConsolWorksheetData.__table__])
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_snapshot_rejects_version_conflict_before_generation(db: AsyncSession):
    project_id = uuid.uuid4()
    db.add_all([
        ConsolWorksheetData(project_id=project_id, year=YEAR, sheet_key="info", data=contents()["info"], version=1),
        ConsolWorksheetData(project_id=project_id, year=YEAR, sheet_key="equity_sim", data=contents()["equity_sim"], version=3),
    ])
    await db.commit()
    with patch("app.services.consol_worksheet_generation_service.build_tree", new=AsyncMock(return_value=tree())):
        snapshot = await load_snapshot(
            db, project_id=project_id, year=YEAR, source_sheet_keys=["equity_sim"],
            expected_versions={"equity_sim": 3}, for_update=True,
        )
        assert snapshot.versions == {"equity_sim": 3}
        assert [group.origin_key for group in snapshot.groups] == ["equity_sim:step1:A", "equity_sim:step1:B"]
        with pytest.raises(WorksheetGenerationError) as conflict:
            await load_snapshot(
                db, project_id=project_id, year=YEAR, source_sheet_keys=["equity_sim"],
                expected_versions={"equity_sim": 2}, for_update=True,
            )
    assert conflict.value.status == 409
    assert conflict.value.detail["changed_sheets"] == ["equity_sim"]
