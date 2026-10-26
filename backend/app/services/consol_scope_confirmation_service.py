"""合并企业树版本（V183 起名「范围确认」；V206 起推送时自动记录，spec consol-autotree-linkage-closure R1）。

- 计算不再要求用户确认：``require_calc_year`` 只校验年度边界；
- 推送写路径 ``record_scope_version`` 自动记录（树指纹变化才新建一版）；
- 手动「记录为新版本」沿用 CAS 接口 ``confirm_scope``（记录方式 user）；
- 企业树接口附 ``scope_version_info``，结构差异见 ``structural_diff``（改名不算结构变化）。
"""

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


async def _load_state(
    db: AsyncSession, project_id: UUID, *, result: GroupTreeResult | None = None,
) -> dict[str, Any]:
    project = (await db.execute(sa.select(Project).where(
        Project.id == project_id,
        Project.is_deleted == sa.false(),
    ))).scalar_one_or_none()
    if project is None:
        raise ScopeConfirmationError(404, "PROJECT_NOT_FOUND", "项目不存在")
    if normalize_report_scope(project.report_scope) != "consolidated":
        raise ScopeConfirmationError(422, "CONSOL_SCOPE_REQUIRED", "只有合并报表项目才有企业树版本")

    year = resolve_project_audit_year(project)
    if year is None:
        raise ScopeConfirmationError(422, "SCOPE_YEAR_UNRESOLVED", "项目缺少有效审计年度")
    if result is None:
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
    matches = active is not None and active.fingerprint == fingerprint
    diff = None
    if active is not None and not matches:
        diff = structural_diff((active.canonical_payload or {}).get("nodes") or [], payload["nodes"])
    preview = {
        "project_id": str(project_id),
        "year": year,
        "report_scope": "consolidated",
        "revision": latest.revision if latest is not None else 0,
        "fingerprint": fingerprint,
        "tree": to_dict(result.root),
        "nodes": _node_payloads(result.root, include_database_ids=True),
        "diagnostics": [item.to_dict() for item in result.diagnostics],
        # 兼容旧字段：confirmed = 当前树与已记录的版本一致（V206 起计算不再需要确认）
        "confirmed": matches,
        "matches_recorded": matches,
        "pending_confirmation": False,
        "can_confirm": project.consol_lock is False,
        "active_confirmation_id": str(active.id) if active is not None else None,
        "recorded_revision": active.revision if active is not None else 0,
        "recorded_mode": active.confirmation_mode if active is not None else None,
        "recorded_at": _iso_utc(active.confirmed_at) if active is not None else None,
        "structural_change": bool(diff and diff["structural"]),
        "diff": diff,
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


def _iso_utc(value: datetime | None) -> str | None:
    """记录时间统一按 UTC 带时区输出（SQLite 读回是无时区值，PG 是带时区值）。"""
    if value is None:
        return None
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()


def structural_diff(old_nodes: list[dict[str, Any]], new_nodes: list[dict[str, Any]]) -> dict[str, Any]:
    """两版企业树的节点差异（spec consol-autotree-linkage-closure R1.3 / ADR-CAL-002）。

    按 ``node_key`` 比较：新增 / 移除 / 上级变化（``parent_node_key``）/ 类型或与上级关系变化；
    名称变化单列为 ``renamed``，**不算结构变化**（改展示名、改企业名称不弹「树已变化」提示）。
    结果顺序确定：新增、上级、类型与改名按新树先序，移除按旧树先序。
    """
    old = {n["node_key"]: n for n in old_nodes or [] if n.get("node_key")}
    new = {n["node_key"]: n for n in new_nodes or [] if n.get("node_key")}

    def label(node: dict[str, Any] | None, key: str | None) -> str | None:
        if key is None:
            return None
        if node is None:
            return key
        return (node.get("company_name") or "").strip() or node.get("company_code") or key

    added, moved, changed, renamed = [], [], [], []
    for key, node in new.items():
        if key not in old:
            added.append({"node_key": key, "label": label(node, key), "role": node.get("role")})
            continue
        before = old[key]
        if before.get("parent_node_key") != node.get("parent_node_key"):
            moved.append({
                "node_key": key, "label": label(node, key),
                "from": before.get("parent_node_key"), "from_label": label(old.get(before.get("parent_node_key") or ""), before.get("parent_node_key")),
                "to": node.get("parent_node_key"), "to_label": label(new.get(node.get("parent_node_key") or ""), node.get("parent_node_key")),
            })
        fields = [f for f in ("kind", "relation") if before.get(f) != node.get(f)]
        if fields:
            changed.append({"node_key": key, "label": label(node, key), "fields": fields,
                            "before": {f: before.get(f) for f in fields}, "after": {f: node.get(f) for f in fields}})
        if (before.get("company_name") or "").strip() != (node.get("company_name") or "").strip():
            renamed.append({"node_key": key, "from": before.get("company_name"), "to": node.get("company_name")})
    removed = [
        {"node_key": key, "label": label(node, key), "role": node.get("role")}
        for key, node in old.items() if key not in new
    ]
    return {
        "added": added, "removed": removed, "moved": moved, "changed": changed, "renamed": renamed,
        "structural": bool(added or removed or moved or changed),
    }


async def preview_scope_confirmation(db: AsyncSession, project_id: UUID) -> dict[str, Any]:
    """只读重建当前树，返回服务端指纹、版本号、与已记录版本的差异。"""
    return (await _load_state(db, project_id))["preview"]


async def _write_version(
    db: AsyncSession, state: dict[str, Any], *, recorded_by: UUID | None, mode: str,
) -> ConsolScopeConfirmation:
    """旧 active 置 superseded，写新修订与节点快照（只 flush）。"""
    current_revision = state["latest"].revision if state["latest"] is not None else 0
    if state["active"] is not None:
        state["active"].status = "superseded"
        await db.flush()
    confirmation = ConsolScopeConfirmation(
        project_id=state["project"].id,
        year=state["payload"]["year"],
        report_scope="consolidated",
        revision=current_revision + 1,
        fingerprint=state["fingerprint"],
        canonical_payload=state["payload"],
        status="active",
        confirmed_by=recorded_by,
        confirmation_mode=mode,
        confirmed_at=datetime.now(timezone.utc),
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
    return confirmation


async def _lock_project(db: AsyncSession, project_id: UUID) -> Project | None:
    return (await db.execute(
        sa.select(Project)
        .where(Project.id == project_id, Project.is_deleted == sa.false())
        .with_for_update()
        .execution_options(populate_existing=True)
    )).scalar_one_or_none()


async def confirm_scope(
    db: AsyncSession,
    project_id: UUID,
    *,
    confirmed_by: UUID,
    expected_fingerprint: str,
    expected_revision: int,
) -> dict[str, Any]:
    """手动「记录为新版本」（CAS，记录方式 user）；仅 flush，事务由 router commit。"""
    project = await _lock_project(db, project_id)
    if project is None:
        raise ScopeConfirmationError(404, "PROJECT_NOT_FOUND", "项目不存在")
    if project.consol_lock is not False:
        raise ScopeConfirmationError(423, "CONSOL_PROJECT_LOCKED", "合并项目已锁定，不能记录企业树版本")

    state = await _load_state(db, project_id)
    preview = state["preview"]
    if expected_fingerprint != state["fingerprint"]:
        raise ScopeConfirmationError(
            409, "SCOPE_FINGERPRINT_CONFLICT", "企业树已变化，请刷新后再记录", preview,
        )
    current_revision = state["latest"].revision if state["latest"] is not None else 0
    if state["active"] is not None and state["active"].fingerprint == state["fingerprint"]:
        if expected_revision in (current_revision, current_revision - 1):
            return preview
        raise ScopeConfirmationError(
            409, "SCOPE_REVISION_CONFLICT", "企业树版本已变化，请刷新后再记录", preview,
        )
    if expected_revision != current_revision:
        raise ScopeConfirmationError(
            409, "SCOPE_REVISION_CONFLICT", "企业树版本已变化，请刷新后再记录", preview,
        )

    confirmation = await _write_version(db, state, recorded_by=confirmed_by, mode="user")
    return {
        **preview,
        "revision": confirmation.revision,
        "confirmed": True,
        "matches_recorded": True,
        "pending_confirmation": False,
        "active_confirmation_id": str(confirmation.id),
        "recorded_revision": confirmation.revision,
        "recorded_mode": "user",
        "recorded_at": _iso_utc(confirmation.confirmed_at),
        "structural_change": False,
        "diff": None,
    }


async def record_scope_version(
    db: AsyncSession, project_id: UUID, *, recorded_by: UUID | None = None, mode: str = "auto",
) -> dict[str, Any]:
    """推送时自动记录树版本（R1.2 / ADR-CAL-001）；只 flush，事务由调用方提交。

    当前树指纹与 active 版本相同 ⇒ 不新建；不同 ⇒ 新建一版（旧版 superseded）。
    合并锁定 ⇒ 不记录（锁定后范围不应再变）。非合并项目 ⇒ 不记录。
    """
    project = await _lock_project(db, project_id)
    if project is None:
        raise ScopeConfirmationError(404, "PROJECT_NOT_FOUND", "项目不存在")
    if normalize_report_scope(project.report_scope) != "consolidated":
        return {"created": False, "skipped": "not_consolidated", "revision": 0}
    state = await _load_state(db, project_id)
    active = state["active"]
    if project.consol_lock is not False:
        return {"created": False, "skipped": "locked", "revision": active.revision if active else 0}
    if active is not None and active.fingerprint == state["fingerprint"]:
        return {"created": False, "skipped": None, "revision": active.revision,
                "mode": active.confirmation_mode, "fingerprint": state["fingerprint"]}
    confirmation = await _write_version(db, state, recorded_by=recorded_by, mode=mode)
    return {"created": True, "skipped": None, "revision": confirmation.revision, "mode": mode,
            "fingerprint": state["fingerprint"],
            "structural_change": bool(state["preview"]["structural_change"])}


async def scope_version_info(
    db: AsyncSession, project_id: UUID, *, result: GroupTreeResult | None = None,
) -> dict[str, Any] | None:
    """企业树接口附带的版本信息（R1.3）：只读；取不到（非合并 / 无年度）返回 None。"""
    try:
        state = await _load_state(db, project_id, result=result)
    except ScopeConfirmationError:
        return None
    preview = state["preview"]
    return {
        "revision": preview["recorded_revision"],
        "latest_revision": preview["revision"],
        "mode": preview["recorded_mode"],
        "recorded_at": preview["recorded_at"],
        "matches": preview["matches_recorded"],
        "structural_change": preview["structural_change"],
        "diff": preview["diff"],
        "fingerprint": preview["fingerprint"],
        "can_record": preview["can_confirm"],
    }


async def require_calc_year(db: AsyncSession, project_id: UUID, year: int) -> None:
    """计算口径的年度边界（V206 起替代「必须先确认合并范围」的计算门）。

    合并树按合并项目的审计年度推导；请求另一年度会拿本年树去配那一年的试算表与分录 ⇒ 拒绝。
    """
    project = (await db.execute(sa.select(Project).where(
        Project.id == project_id, Project.is_deleted == sa.false(),
    ))).scalar_one_or_none()
    if project is None:
        return
    project_year = resolve_project_audit_year(project)
    if project_year is None:
        raise HTTPException(status_code=422, detail={
            "error_code": "SCOPE_YEAR_UNRESOLVED", "message": "合并项目缺少有效审计年度，无法计算合并数",
        })
    if project_year != year:
        raise HTTPException(status_code=409, detail={
            "error_code": "SCOPE_YEAR_MISMATCH",
            "message": f"请求年度 {year} 与合并项目审计年度 {project_year} 不一致，不能用本年度企业树计算",
        })
