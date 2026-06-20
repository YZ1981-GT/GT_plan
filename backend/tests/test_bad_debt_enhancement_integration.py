"""坏账准备明细表增强端点集成测试（Sprint 5 Task 9.2）。

使用 httpx AsyncClient + in-process ASGI 模式测试新增 7 个端点：
- GET  export-template → 200, xlsx content-type, non-empty body
- GET  export-data → 200, xlsx content-type, non-empty body
- POST import-parse → 422 (invalid) / 200 (valid)
- POST import-commit → 200 with updated_count
- GET  aging-segments → 200 (null when none)
- PUT  aging-segments → 200 / 422
- GET  aging-segments/has-amounts → 200 with has_amounts bool

Mock: NestedTableService.get_tree → 简单树(2 parents × 2 children each)

Validates: Requirements 1.1, 2.1, 3.1, 3.8, 4.7
"""

from __future__ import annotations

import io
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from openpyxl import Workbook
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.bad_debt_models import BadDebtDetailRow, ProvisionMethod
from app.models.base import Base
from app.models.workpaper_models import WorkingPaper
from app.schemas.bad_debt_schemas import (
    BadDebtTreeResponse,
    BalanceCheck,
    ChildRowResponse,
    ParentRowResponse,
    RowAmounts,
    SummaryRowResponse,
)

# ─── 常量 ────────────────────────────────────────────────────────────────────

XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ─── Fixtures ─────────────────────────────────────────────────────────────────


def _make_tree_fixture(wp_index_id: uuid.UUID) -> BadDebtTreeResponse:
    """构造简单树：2 parents × 2 children each。"""
    parent1_id = uuid.uuid4()
    parent2_id = uuid.uuid4()

    child1a = ChildRowResponse(
        id=uuid.uuid4(),
        parent_row_id=parent1_id,
        sort_order=10,
        row_label="甲公司",
        amounts=RowAmounts(amount_n=Decimal("100.00"), amount_k=Decimal("80.00")),
        version=1,
    )
    child1b = ChildRowResponse(
        id=uuid.uuid4(),
        parent_row_id=parent1_id,
        sort_order=20,
        row_label="乙公司",
        amounts=RowAmounts(amount_n=Decimal("50.00"), amount_k=Decimal("40.00")),
        version=1,
    )
    child2a = ChildRowResponse(
        id=uuid.uuid4(),
        parent_row_id=parent2_id,
        sort_order=10,
        row_label="1年以内",
        amounts=RowAmounts(amount_n=Decimal("200.00")),
        version=1,
    )
    child2b = ChildRowResponse(
        id=uuid.uuid4(),
        parent_row_id=parent2_id,
        sort_order=20,
        row_label="1-2年",
        amounts=RowAmounts(amount_n=Decimal("300.00")),
        version=1,
    )

    parent1 = ParentRowResponse(
        id=parent1_id,
        provision_method=ProvisionMethod.INDIVIDUAL,
        provision_method_label="按单项评估计提",
        sort_order=10,
        row_label="按单项评估计提",
        amounts=RowAmounts(amount_n=Decimal("150.00"), amount_k=Decimal("120.00")),
        children=[child1a, child1b],
        version=1,
        is_editable=False,
    )
    parent2 = ParentRowResponse(
        id=parent2_id,
        provision_method=ProvisionMethod.CREDIT_RISK_AGING,
        provision_method_label="按信用风险特征组合计提（账龄分析法）",
        sort_order=20,
        row_label="按信用风险特征组合计提（账龄分析法）",
        amounts=RowAmounts(amount_n=Decimal("500.00")),
        children=[child2a, child2b],
        version=1,
        is_editable=False,
    )

    summary = SummaryRowResponse(
        amounts=RowAmounts(amount_n=Decimal("650.00"), amount_k=Decimal("120.00")),
        balance_check=BalanceCheck(
            is_balanced=True,
            expected_n=Decimal("650.00"),
            actual_n=Decimal("650.00"),
            diff=Decimal("0"),
        ),
    )

    return BadDebtTreeResponse(
        wp_index_id=wp_index_id,
        summary=summary,
        parents=[parent1, parent2],
        prefill_source=None,
    )


@pytest_asyncio.fixture
async def client():
    """最小 FastAPI app + in-process 内存 SQLite + mock get_tree。

    返回 (AsyncClient, wp_id)。
    """
    from app.core.database import get_db
    from app.deps import get_current_user
    from app.routers.bad_debt_rows import router as bad_debt_rows_router

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[BadDebtDetailRow.__table__, WorkingPaper.__table__],
        )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = factory()

    app = FastAPI()
    app.include_router(bad_debt_rows_router)

    wp_id = uuid.uuid4()
    tree_fixture = _make_tree_fixture(wp_id)

    async def override_get_db():
        yield session

    class _FakeUser:
        id = uuid.uuid4()
        username = "admin"

        class _Role:
            value = "admin"

        role = _Role()

    async def override_user():
        return _FakeUser()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        with patch(
            "app.services.bad_debt_nested_table_service.NestedTableService.get_tree",
            new_callable=AsyncMock,
            return_value=tree_fixture,
        ):
            yield c, wp_id, tree_fixture

    app.dependency_overrides.clear()
    await session.close()
    await engine.dispose()


def _base(wp_id: uuid.UUID) -> str:
    return f"/api/workpapers/{wp_id}/bad-debt-rows"


def _make_valid_xlsx(labels: list[str], amounts: list[list] | None = None) -> bytes:
    """构造合法的 14 列 xlsx 文件（含 11 行表头 + 数据行从 R12 开始）。"""
    wb = Workbook()
    ws = wb.active
    # R1-R11 表头占位
    for r in range(1, 12):
        ws.cell(row=r, column=1, value=f"Header row {r}")
        # 确保至少 14 列
        for col in range(2, 15):
            ws.cell(row=r, column=col, value="")

    # R12+ 数据行
    for idx, label in enumerate(labels):
        row_idx = 12 + idx
        ws.cell(row=row_idx, column=1, value=label)
        if amounts and idx < len(amounts):
            for col_offset, val in enumerate(amounts[idx]):
                ws.cell(row=row_idx, column=2 + col_offset, value=val)
        else:
            for col in range(2, 15):
                ws.cell(row=row_idx, column=col, value=None)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


def _make_invalid_xlsx_too_few_columns() -> bytes:
    """构造列数不足的 xlsx（只有 5 列）。"""
    wb = Workbook()
    ws = wb.active
    for r in range(1, 15):
        for col in range(1, 6):  # 只有 5 列
            ws.cell(row=r, column=col, value="x")
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


# ─────────────────────────────────────────────────────────────────────────────
# 1. GET export-template → 200, xlsx content-type, non-empty body
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_template_returns_xlsx(client):
    c, wp_id, _ = client
    resp = await c.get(f"{_base(wp_id)}/export-template")
    assert resp.status_code == 200, resp.text
    assert XLSX_CONTENT_TYPE in resp.headers.get("content-type", "")
    assert len(resp.content) > 0


# ─────────────────────────────────────────────────────────────────────────────
# 2. GET export-data → 200, xlsx content-type, non-empty body
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_data_returns_xlsx(client):
    c, wp_id, _ = client
    resp = await c.get(f"{_base(wp_id)}/export-data")
    assert resp.status_code == 200, resp.text
    assert XLSX_CONTENT_TYPE in resp.headers.get("content-type", "")
    assert len(resp.content) > 0


# ─────────────────────────────────────────────────────────────────────────────
# 3. POST import-parse → 422 on invalid file (too few columns)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_import_parse_invalid_file_422(client):
    c, wp_id, _ = client
    invalid_xlsx = _make_invalid_xlsx_too_few_columns()
    resp = await c.post(
        f"{_base(wp_id)}/import-parse",
        files={"file": ("bad.xlsx", invalid_xlsx, XLSX_CONTENT_TYPE)},
    )
    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert "detail" in body


# ─────────────────────────────────────────────────────────────────────────────
# 4. POST import-parse → 200 on valid file with matched rows
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_import_parse_valid_file_200(client):
    c, wp_id, tree = client
    # 使用树中的实际标签（匹配子行）
    labels = ["甲公司", "乙公司", "未知行"]
    amounts = [
        [100, None, None, None, None, None, None, None, None, None, None, None, None],
        [200, None, None, None, None, None, None, None, None, None, None, None, None],
        [300, None, None, None, None, None, None, None, None, None, None, None, None],
    ]
    valid_xlsx = _make_valid_xlsx(labels, amounts)
    resp = await c.post(
        f"{_base(wp_id)}/import-parse",
        files={"file": ("data.xlsx", valid_xlsx, XLSX_CONTENT_TYPE)},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "rows" in body
    assert "matched_count" in body
    assert "unmatched_count" in body
    # 甲公司 + 乙公司 matched, 未知行 unmatched
    assert body["matched_count"] == 2
    assert body["unmatched_count"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# 5. POST import-commit → 200 with updated_count
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_import_commit_returns_updated_count(client):
    c, wp_id, tree = client
    # 准备匹配结果数据（模拟 import-parse 返回的行数据）
    child1a = tree.parents[0].children[0]
    rows = [
        {
            "excel_row_index": 12,
            "excel_label": "甲公司",
            "status": "matched",
            "matched_row_id": str(child1a.id),
            "matched_row_label": "甲公司",
            "is_parent": False,
            "amounts": {"amount_b": "999.00"},
        },
        {
            "excel_row_index": 13,
            "excel_label": "未知行",
            "status": "unmatched",
            "matched_row_id": None,
            "matched_row_label": None,
            "is_parent": False,
            "amounts": {},
        },
    ]

    # 因为 commit 需要真实 DB 行，我们 mock commit_matched_rows 返回 1
    with patch(
        "app.services.bad_debt_import_service.BadDebtImportService.commit_matched_rows",
        new_callable=AsyncMock,
        return_value=1,
    ):
        resp = await c.post(
            f"{_base(wp_id)}/import-commit",
            json={"rows": rows},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "updated_count" in body
    assert body["updated_count"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# 6. GET aging-segments → 200 (null when none set)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_aging_segments_null_when_none(client):
    c, wp_id, _ = client
    with patch(
        "app.services.aging_segment_service.AgingSegmentService.get_config",
        new_callable=AsyncMock,
        return_value=None,
    ):
        resp = await c.get(f"{_base(wp_id)}/aging-segments")
    assert resp.status_code == 200, resp.text
    assert resp.json() is None


# ─────────────────────────────────────────────────────────────────────────────
# 7. PUT aging-segments → 200 on valid config
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_put_aging_segments_valid_200(client):
    c, wp_id, _ = client
    with patch(
        "app.services.aging_segment_service.AgingSegmentService.save_config",
        new_callable=AsyncMock,
        return_value=None,
    ):
        resp = await c.put(
            f"{_base(wp_id)}/aging-segments",
            json={"preset": "THREE_YEAR", "segments": ["1年以内", "1-2年", "2-3年", "3年以上"]},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("saved") is True


# ─────────────────────────────────────────────────────────────────────────────
# 8. PUT aging-segments → 422 on empty segment name
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_put_aging_segments_empty_name_422(client):
    c, wp_id, _ = client
    resp = await c.put(
        f"{_base(wp_id)}/aging-segments",
        json={"preset": "CUSTOM", "segments": ["1年以内", "", "2-3年"]},
    )
    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert "EMPTY_SEGMENT_NAME" in body["detail"]["error_code"]


# ─────────────────────────────────────────────────────────────────────────────
# 9. PUT aging-segments → 422 on duplicate segment name
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_put_aging_segments_duplicate_name_422(client):
    c, wp_id, _ = client
    resp = await c.put(
        f"{_base(wp_id)}/aging-segments",
        json={"preset": "CUSTOM", "segments": ["1年以内", "1-2年", "1年以内"]},
    )
    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert "DUPLICATE_SEGMENT_NAME" in body["detail"]["error_code"]


# ─────────────────────────────────────────────────────────────────────────────
# 10. GET aging-segments/has-amounts → 200 with has_amounts bool
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aging_segments_has_amounts_returns_bool(client):
    c, wp_id, _ = client
    with patch(
        "app.services.aging_segment_service.AgingSegmentService.check_has_amounts",
        new_callable=AsyncMock,
        return_value=False,
    ):
        resp = await c.get(f"{_base(wp_id)}/aging-segments/has-amounts")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "has_amounts" in body
    assert isinstance(body["has_amounts"], bool)
    assert body["has_amounts"] is False
