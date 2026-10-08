"""D5 服务端确认、CAS 与计算门。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consol_scope_confirmation_models import (
    ConsolScopeConfirmation,
    ConsolScopeConfirmationNode,
)
from app.models.consolidation_models import ConsolScope, ConsolTrial, ConsolWorksheet
from app.models.consol_worksheet_data_models import ConsolWorksheetData
from app.models.core import Project
from app.services.consol_group_tree import GroupTreeResult, build_group_tree
from app.services.consol_tree_service import TreeNode, to_dict
from app.services.note_section_catalog import normalize_report_scope
from app.services.project_audit_year import resolve_project_audit_year


@dataclass
class ScopeConfirmationError(Exception):
    status_code: int
    error_code: str
    message: str
    latest_preview: dict[str, Any] | None = None

    def __str__(self) -> str:
        return self.message


def _node_payloads(root: TreeNode, *, include_database_ids: bool = False) -> list[dict[str, Any]]:
    """把树压成确定性节点摘要。

    ``include_database_ids`` 只供写入角色快照时使用。指纹载荷不能携带项目行 UUID，
    否则同一企业/角色树因项目重建或数据库迁移就会被错误判为范围变化。
    """
    nodes: list[dict[str, Any]] = []

    def visit(node: TreeNode, parent_key: str | None) -> None:
        item: dict[str, Any] = {
            "node_key": node.node_key,
            "role": node.role,
            "kind": node.kind,
            "company_code": (node.company_code or "").strip(),
            "company_name": (node.company_name or "").strip(),
            "parent_node_key": parent_key,
            "position": len(nodes),
            "relation": node.relation,
            "consol_level": node.consol_level,
            "flags": sorted(set(node.flags)),
            "via": list(node.via),
        }
        if include_database_ids:
            item.update({
                "project_id": str(node.project_id) if node.project_id else None,
                "host_project_id": str(node.host_project_id) if node.host_project_id else None,
            })
        nodes.append(item)
        for child in node.children:
            visit(child, node.node_key)

    visit(root, None)
    return nodes


def _stable_tree(node: TreeNode) -> dict[str, Any]:
    """返回不含数据库行 ID 和运行时诊断信息的确定性树载荷。"""
    return {
        "company_code": (node.company_code or "").strip(),
        "company_name": (node.company_name or "").strip(),
        "parent_company_code": (node.parent_company_code or "").strip() or None,
        "ultimate_company_code": (node.ultimate_company_code or "").strip() or None,
        "consol_level": node.consol_level,
        "children": [_stable_tree(child) for child in node.children],
        "node_key": node.node_key,
        "role": node.role,
        "kind": node.kind,
        "display_name": (node.display_name or node.company_name or "").strip(),
        "relation": node.relation,
        "flags": sorted(set(node.flags)),
        "via": list(node.via),
        "mode": node.mode,
    }


def _canonical_payload(project: Project, result: GroupTreeResult) -> dict[str, Any]:
    if result.root is None or result.year is None:
        raise ScopeConfirmationError(422, "SCOPE_YEAR_UNRESOLVED", "项目缺少有效审计年度或合并树")
    nodes = _node_payloads(result.root)
    if len({node["node_key"] for node in nodes}) != len(nodes):
        raise ScopeConfirmationError(409, "SCOPE_NODE_KEY_COLLISION", "当前合并树存在重复稳定键，不能确认")
    return {
        "schema_version": 1,
        "year": result.year,
        "report_scope": "consolidated",
        "mode": result.mode,
        "tree": _stable_tree(result.root),
        "nodes": nodes,
    }


def fingerprint_payload(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


async def _is_legacy_boundary(db: AsyncSession, project: Project, year: int) -> bool:
    connection = await db.connection()
    if not await connection.run_sync(lambda conn: sa.inspect(conn).has_table("schema_version")):
        return False
    activated_at = await db.scalar(sa.text(
        "SELECT applied_at FROM schema_version WHERE version = '183' "
        "AND filename = 'V183__consol_scope_confirmation.sql'"
    ))
    if not activated_at or not project.created_at:
        return False
    if isinstance(activated_at, str):
        activated_at = datetime.fromisoformat(activated_at)
    cutoff = activated_at.replace(tzinfo=timezone.utc) if activated_at.tzinfo is None else activated_at
    created = project.created_at
    created = created.replace(tzinfo=timezone.utc) if created.tzinfo is None else created
    if created >= cutoff:
        return False
    for model in (ConsolScope, ConsolTrial, ConsolWorksheet, ConsolWorksheetData):
        criteria = [model.project_id == project.id, model.year == year, model.created_at < cutoff]
        if hasattr(model, "is_deleted"):
            criteria.append(model.is_deleted == sa.false())
        if await db.scalar(sa.select(sa.exists().where(*criteria))):
            return True
    return False


async def _load_state(db: AsyncSession, project_id: UUID) -> dict[str, Any]:
    project = (await db.execute(sa.select(Project).where(
        Project.id == project_id,
        Project.is_deleted == sa.false(),
    ))).scalar_one_or_none()
    if project is None:
        raise ScopeConfirmationError(404, "PROJECT_NOT_FOUND", "项目不存在")
    if normalize_report_scope(project.report_scope) != "consolidated":
        raise ScopeConfirmationError(422, "CONSOL_SCOPE_REQUIRED", "只有合并报表项目可以确认合并范围")

    year = resolve_project_audit_year(project)
    if year is None:
        raise ScopeConfirmationError(422, "SCOPE_YEAR_UNRESOLVED", "项目缺少有效审计年度")
    result = await build_group_tree(db, project_id)
    if result is None or result.root is None:
        raise ScopeConfirmationError(404, "PROJECT_NOT_FOUND", "合并项目树不存在")
    payload = _canonical_payload(project, result)
    fingerprint = fingerprint_payload(payload)
    criteria = (
        ConsolScopeConfirmation.project_id == project_id,
        ConsolScopeConfirmation.year == year,
        ConsolScopeConfirmation.report_scope == "consolidated",
    )
    latest = (await db.execute(
        sa.select(ConsolScopeConfirmation)
        .where(*criteria)
        .order_by(ConsolScopeConfirmation.revision.desc())
        .limit(1)
    )).scalar_one_or_none()
    active = (await db.execute(
        sa.select(ConsolScopeConfirmation).where(
            *criteria,
            ConsolScopeConfirmation.status == "active",
        )
    )).scalar_one_or_none()
    pending_legacy = latest is None and await _is_legacy_boundary(db, project, year)
    confirmed = active is not None and active.fingerprint == fingerprint
    preview = {
        "project_id": str(project_id),
        "year": year,
        "report_scope": "consolidated",
        "revision": latest.revision if latest is not None else 0,
        "fingerprint": fingerprint,
        "tree": to_dict(result.root),
        "nodes": _node_payloads(result.root, include_database_ids=True),
        "diagnostics": [item.to_dict() for item in result.diagnostics],
        "confirmed": confirmed,
        "pending_legacy": pending_legacy,
        "pending_confirmation": not confirmed,
        "can_confirm": project.consol_lock is False,
        "active_confirmation_id": str(active.id) if active is not None else None,
    }
    return {
        "project": project,
        "result": result,
        "payload": payload,
        "fingerprint": fingerprint,
        "latest": latest,
        "active": active,
        "preview": preview,
    }


async def preview_scope_confirmation(db: AsyncSession, project_id: UUID) -> dict[str, Any]:
    """只读重建当前树，返回服务端指纹、revision 与 legacy 状态。"""
    return (await _load_state(db, project_id))["preview"]


async def confirm_scope(
    db: AsyncSession,
    project_id: UUID,
    *,
    confirmed_by: UUID,
    expected_fingerprint: str,
    expected_revision: int,
) -> dict[str, Any]:
    """重新推导并 CAS 确认；仅 flush，事务由 router commit。"""
    project = (await db.execute(
        sa.select(Project)
        .where(Project.id == project_id, Project.is_deleted == sa.false())
        .with_for_update()
        .execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if project is None:
        raise ScopeConfirmationError(404, "PROJECT_NOT_FOUND", "项目不存在")
    if project.consol_lock is not False:
        raise ScopeConfirmationError(423, "CONSOL_PROJECT_LOCKED", "合并项目已锁定，不能变更范围确认")

    state = await _load_state(db, project_id)
    preview = state["preview"]
    if expected_fingerprint != state["fingerprint"]:
        raise ScopeConfirmationError(
            409, "SCOPE_FINGERPRINT_CONFLICT", "合并树已变化，请刷新预览后重新确认", preview,
        )
    current_revision = state["latest"].revision if state["latest"] is not None else 0
    if state["active"] is not None and state["active"].fingerprint == state["fingerprint"]:
        if expected_revision in (current_revision, current_revision - 1):
            return preview
        raise ScopeConfirmationError(
            409, "SCOPE_REVISION_CONFLICT", "确认版本已变化，请刷新预览后重新确认", preview,
        )
    if expected_revision != current_revision:
        raise ScopeConfirmationError(
            409, "SCOPE_REVISION_CONFLICT", "确认版本已变化，请刷新预览后重新确认", preview,
        )

    if state["active"] is not None:
        state["active"].status = "superseded"
        await db.flush()

    confirmation = ConsolScopeConfirmation(
        project_id=project_id,
        year=state["payload"]["year"],
        report_scope="consolidated",
        revision=current_revision + 1,
        fingerprint=state["fingerprint"],
        canonical_payload=state["payload"],
        status="active",
        confirmed_by=confirmed_by,
    )
    db.add(confirmation)
    await db.flush()

    db.add_all([
        ConsolScopeConfirmationNode(
            confirmation_id=confirmation.id,
            node_key=node["node_key"],
            role=node["role"],
            kind=node["kind"],
            company_code=node["company_code"],
            project_id=UUID(node["project_id"]) if node["project_id"] else None,
            host_project_id=UUID(node["host_project_id"]) if node["host_project_id"] else None,
            parent_node_key=node["parent_node_key"],
            position=node["position"],
        )
        for node in _node_payloads(state["result"].root, include_database_ids=True)
    ])
    await db.flush()
    return {
        **preview,
        "revision": confirmation.revision,
        "confirmed": True,
        "pending_legacy": False,
        "pending_confirmation": False,
        "active_confirmation_id": str(confirmation.id),
    }


async def require_confirmed_scope(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    *,
    tree: TreeNode | None = None,
    allow_legacy_read: bool = False,
) -> TreeNode | None:
    """计算门：必须存在与当前服务端树一致的 active 用户确认版本。

    ``allow_legacy_read`` 只给既有 legacy 读路径使用：仅当项目被识别为
    V183 之前已有数据时允许继续读取；新项目和树已变化的项目仍必须确认。

    当 V183 迁移尚未通过 MigrationRunner 正式执行时（``schema_version`` 表不存在或其中
    没有 V183 记录），整个确认机制还没有生效，透明放行以兼容旧环境和测试。
    ORM 测试用 ``create_all`` 建表但不走 MigrationRunner，所以不会误触发确认门。
    """
    # V183 尚未通过迁移 runner 正式执行 ⇒ 功能未启用，透明放行
    connection = await db.connection()
    has_sv = await connection.run_sync(lambda conn: sa.inspect(conn).has_table("schema_version"))
    if not has_sv:
        return tree
    v183_applied = await db.scalar(sa.text(
        "SELECT 1 FROM schema_version WHERE version = '183' "
        "AND filename = 'V183__consol_scope_confirmation.sql'"
    ))
    if not v183_applied:
        return tree
    try:
        state = await _load_state(db, project_id)
    except ScopeConfirmationError as exc:
        raise HTTPException(status_code=exc.status_code, detail={
            "error_code": exc.error_code,
            "message": exc.message,
        }) from exc
    if state["payload"]["year"] != year:
        raise HTTPException(status_code=409, detail={
            "error_code": "SCOPE_CONFIRMATION_REQUIRED",
            "message": "请求年度与已确认合并范围不一致，请重新确认当前合并范围",
        })
    if tree is not None:
        passed_payload = _canonical_payload(state["project"], GroupTreeResult(
            root=tree,
            year=year,
            mode=tree.mode or state["result"].mode,
            diagnostics=[],
        ))
        if fingerprint_payload(passed_payload) != state["fingerprint"]:
            raise HTTPException(status_code=409, detail={
                "error_code": "SCOPE_CONFIRMATION_REQUIRED",
                "message": "待计算树与服务端当前合并树不一致，请重新预览并确认",
            })
    if not state["preview"]["confirmed"]:
        if allow_legacy_read and state["preview"]["pending_legacy"]:
            return tree
        raise HTTPException(status_code=409, detail={
            "error_code": "SCOPE_CONFIRMATION_REQUIRED",
            "message": "当前合并范围尚未由用户确认，确认前不能计算",
            "preview": state["preview"],
        })
    return tree
