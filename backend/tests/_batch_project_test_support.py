"""批量建项相关测试的共享常量、工作簿与授权夹具。

本文件是已归档 spec ``batch-project-authorization-and-lock-hardening`` 的测试交付物；
相关测试已提交但该支持模块曾漏提交，导致干净检出在收集期失败。
"""
from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from typing import Any

from openpyxl import Workbook

from app.services.batch_project_service import _TEMPLATE_COLUMNS
from app.services.project_creation_grant_service import grant_many

ROOT = "91110000100000000R"
PARENT = "911100002000000005"
CHILD = "91110000300000000G"
BRANCH = "91110000400000000U"


def make_excel(rows: list[list[Any]], *, columns: list[str] | None = None) -> bytes:
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
) -> list[Any]:
    return [
        name, code, name[:20], year, "年报审计", "企业会计准则", scope,
        parent, ultimate, relation, "新建", "", "",
    ]


async def grant_manager_codes(db, manager, *codes: str, valid_until=None):
    """给测试经理授予精确代码；只 flush，事务边界由测试控制。"""
    return await grant_many(
        db,
        manager_user_id=manager.id,
        company_codes=list(codes),
        valid_until=valid_until,
        reason="测试建项授权",
        actor=SimpleNamespace(id=None, role=SimpleNamespace(value="admin")),
    )


__all__ = [
    "BRANCH", "CHILD", "PARENT", "ROOT", "grant_manager_codes", "make_excel", "row",
]
