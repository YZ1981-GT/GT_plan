"""Shared fixtures and workbook builders for batch-project tests."""
from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

from openpyxl import Workbook

from app.services.batch_project_service import _TEMPLATE_COLUMNS

ROOT = "91110000100000000R"
PARENT = "911100002000000005"
CHILD = "91110000300000000G"
BRANCH = "91110000400000000U"


def make_excel(rows: list[list], *, columns: list[str] | None = None) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "数据"
    sheet.append(columns or _TEMPLATE_COLUMNS)
    for values in rows:
        sheet.append(values)
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def row(
    name: str,
    code: str,
    year: int | float,
    scope: str = "单户",
    *,
    parent: str = "",
    ultimate: str = "",
    relation: str = "",
) -> list:
    return [
        name, code, name[:20], year, "年报审计", "企业会计准则", scope,
        parent, ultimate, relation, "新建", "", "",
    ]


def admin():
    return SimpleNamespace(id=uuid4(), role=SimpleNamespace(value="admin"))


async def grant_manager_codes(db, manager, *codes: str) -> None:
    """给 SQLite 场景建立精确授权；授权 CRUD 本身由独立测试覆盖。"""
    from app.models.project_creation_grant_models import ProjectCreationGrant

    db.add_all([
        ProjectCreationGrant(
            grantee_user_id=manager.id,
            company_code=code,
            source="test_fixture",
            reason="批量建项测试授权",
        )
        for code in codes
    ])
    await db.flush()
