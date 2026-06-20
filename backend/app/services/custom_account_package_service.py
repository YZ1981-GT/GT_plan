"""用户自定义科目工作包服务

spec workpaper-account-multifile-aggregation 需求 6：
- 导出科目模板（含 sheet 结构 + sheet_type + 字段定义）为可编辑 YAML
- 导入自定义模板：校验（sheet_type 合法 / componentType 可渲染 / 必填字段）→ 写
  custom_account_packages 表（项目级/事务所级）
- 优先级解析：项目级 > 事务所级 > 内置行业 > 通用

校验失败返回明确错误清单（不静默失败，需求 6.6）。
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import sqlalchemy as sa
import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.account_package_registry_service import (
    AccountPackageRegistryService,
    VALID_SHEET_TYPES,
)
from app.services.wp_account_package_resolver import (
    _SHEET_TYPE_TO_CLASS,
    _sheet_type_to_component,
)

logger = logging.getLogger(__name__)

VALID_SCOPES = ("project", "firm")


class CustomPackageValidationError(Exception):
    """自定义模板校验错误（携带明确错误清单）。"""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"自定义模板校验失败: {errors}")


# ─── 导出 ────────────────────────────────────────────────────────────────


def export_package_template(wp_code: str, *, registry: AccountPackageRegistryService | None = None) -> str | None:
    """导出科目工作包结构为可编辑 YAML 文本。

    含 account_name/industry + 每个 sheet 的 sheet_name/sheet_type/source_wp_code +
    sheet_type 合法值提示，供用户编辑后重新导入。无该科目返回 None。
    """
    registry = registry or AccountPackageRegistryService()
    pkg = None
    for p in registry.get_packages():
        if p.get("primary_wp_code") == wp_code:
            pkg = p
            break
    if pkg is None:
        return None

    export_doc = {
        "_说明": "编辑后通过 import-template 端点导入。sheet_type 合法值见 _valid_sheet_types。",
        "_valid_sheet_types": list(VALID_SHEET_TYPES),
        "wp_code": pkg.get("primary_wp_code"),
        "account_name": pkg.get("account_name"),
        "industry": pkg.get("industry", ["通用"]),
        "sheets": [
            {
                "sheet_name": s.get("sheet_name"),
                "sheet_type": s.get("sheet_type"),
                "source_wp_code": s.get("source_wp_code", pkg.get("primary_wp_code")),
            }
            for s in pkg.get("sheets", [])
        ],
    }
    return yaml.safe_dump(export_doc, allow_unicode=True, sort_keys=False)


# ─── 校验 ────────────────────────────────────────────────────────────────


def validate_package_json(package_json: dict) -> list[str]:
    """校验自定义模板结构，返回错误清单（空=通过）。

    规则（需求 6.3/6.6）：
    - wp_code / account_name 必填
    - sheets 非空
    - 每个 sheet：sheet_name 必填 + sheet_type 在白名单 + 能映射到可渲染 HTML 组件
    """
    errors: list[str] = []
    if not isinstance(package_json, dict):
        return ["模板根节点必须是对象"]

    if not package_json.get("wp_code"):
        errors.append("缺少必填字段: wp_code")
    if not package_json.get("account_name"):
        errors.append("缺少必填字段: account_name")

    sheets = package_json.get("sheets")
    if not isinstance(sheets, list) or not sheets:
        errors.append("sheets 必须是非空列表")
        return errors

    for i, sheet in enumerate(sheets):
        if not isinstance(sheet, dict):
            errors.append(f"sheets[{i}] 必须是对象")
            continue
        name = sheet.get("sheet_name")
        if not name:
            errors.append(f"sheets[{i}] 缺少 sheet_name")
        stype = sheet.get("sheet_type")
        if not stype:
            errors.append(f"sheets[{i}]({name}) 缺少 sheet_type")
        elif stype not in VALID_SHEET_TYPES:
            errors.append(
                f"sheets[{i}]({name}) sheet_type='{stype}' 非法，合法值: {VALID_SHEET_TYPES}"
            )
        elif stype not in _SHEET_TYPE_TO_CLASS or _sheet_type_to_component(stype) is None:
            errors.append(
                f"sheets[{i}]({name}) sheet_type='{stype}' 无法映射到可渲染 HTML 组件"
            )

    return errors


def parse_and_validate(content: str) -> dict:
    """解析 YAML/JSON 文本 → 校验 → 返回 package_json。失败抛 CustomPackageValidationError。"""
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        raise CustomPackageValidationError([f"YAML/JSON 解析失败: {e}"]) from e

    if not isinstance(data, dict):
        raise CustomPackageValidationError(["模板内容必须是对象"])

    # 剔除导出时的辅助说明键
    package_json = {k: v for k, v in data.items() if not str(k).startswith("_")}
    errors = validate_package_json(package_json)
    if errors:
        raise CustomPackageValidationError(errors)
    return package_json


# ─── 持久化 ──────────────────────────────────────────────────────────────


async def import_custom_package(
    db: AsyncSession,
    *,
    scope: str,
    scope_id: UUID,
    package_json: dict,
    created_by: UUID | None = None,
) -> dict:
    """写入/更新 custom_account_packages（按 scope+scope_id+wp_code 唯一）。"""
    if scope not in VALID_SCOPES:
        raise CustomPackageValidationError([f"scope 非法: {scope}，合法值: {VALID_SCOPES}"])

    wp_code = package_json["wp_code"]
    industry = package_json.get("industry")
    industry_val = industry[0] if isinstance(industry, list) and industry else (industry or "通用")

    await db.execute(
        sa.text(
            """
            INSERT INTO custom_account_packages
                (scope, scope_id, wp_code, industry, package_json, created_by)
            VALUES (:scope, :scope_id, :wp_code, :industry, CAST(:pkg AS JSONB), :created_by)
            ON CONFLICT (scope, scope_id, wp_code) DO UPDATE SET
                industry = EXCLUDED.industry,
                package_json = EXCLUDED.package_json,
                updated_at = now(),
                is_deleted = false
            """
        ),
        {
            "scope": scope,
            "scope_id": str(scope_id),
            "wp_code": wp_code,
            "industry": industry_val,
            "pkg": _json_dumps(package_json),
            "created_by": str(created_by) if created_by else None,
        },
    )
    await db.commit()
    return {"wp_code": wp_code, "scope": scope, "scope_id": str(scope_id)}


async def get_custom_package(
    db: AsyncSession,
    *,
    wp_code: str,
    project_id: UUID | None,
    firm_id: UUID | None = None,
) -> dict | None:
    """按优先级查自定义工作包：项目级 > 事务所级（需求 6.5）。命中返回 package_json。"""
    # 项目级优先
    if project_id is not None:
        row = (await db.execute(
            sa.text(
                "SELECT package_json FROM custom_account_packages "
                "WHERE scope='project' AND scope_id=:sid AND wp_code=:wp AND is_deleted=false LIMIT 1"
            ),
            {"sid": str(project_id), "wp": wp_code},
        )).first()
        if row:
            return row[0]
    # 事务所级
    if firm_id is not None:
        row = (await db.execute(
            sa.text(
                "SELECT package_json FROM custom_account_packages "
                "WHERE scope='firm' AND scope_id=:sid AND wp_code=:wp AND is_deleted=false LIMIT 1"
            ),
            {"sid": str(firm_id), "wp": wp_code},
        )).first()
        if row:
            return row[0]
    return None


def _json_dumps(obj: Any) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False)
