"""合并计算链路的上下文构造、树指纹和一致性校验。"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project
from app.schemas.consol_context import ConsolContext
from app.services.consol_tree_service import TreeNode, build_tree, iter_nodes
from app.services.project_audit_year import resolve_project_audit_year


class ConsolContextError(ValueError):
    """合并计算上下文与当前目标边界不一致。"""


def _stable_node(node: TreeNode) -> dict[str, Any]:
    """只取影响计算身份的节点字段；展示名称和诊断信息不参与指纹。

    运行时传入的是真实 ``TreeNode``；这里仍对轻量替身保留安全默认值，
    让编排器测试和迁移期兼容调用不会因为缺少展示字段而在指纹阶段崩溃。
    """
    project_id = getattr(node, "project_id", None)
    company_code = getattr(node, "company_code", None)
    node_key = getattr(node, "node_key", None) or company_code
    return {
        "project_id": str(project_id) if project_id else None,
        "company_code": company_code,
        "node_key": node_key,
        "role": getattr(node, "role", None),
        "kind": getattr(node, "kind", None),
        "host_project_id": (
            str(getattr(node, "host_project_id", None))
            if getattr(node, "host_project_id", None)
            else None
        ),
        "report_scope": getattr(node, "report_scope", None),
        "children": [
            _stable_node(child)
            for child in (getattr(node, "children", None) or ())
        ],
    }


def tree_fingerprint(tree: TreeNode | None) -> str | None:
    """计算确定性企业树快照指纹，保留子节点顺序。"""
    if tree is None:
        return None
    payload = json.dumps(
        _stable_node(tree), ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _non_blank(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _tree_node_keys(tree: TreeNode | None) -> tuple[str, ...]:
    if tree is None:
        return ()
    keys: list[str] = []
    stack = [tree]
    while stack:
        node = stack.pop()
        company_code = getattr(node, "company_code", None)
        keys.append(getattr(node, "node_key", None) or company_code)
        stack.extend(reversed(getattr(node, "children", None) or ()))
    return tuple(keys)


def context_from_tree(
    project_id: UUID,
    year: int,
    tree: TreeNode | None,
    *,
    template_type: str | None = None,
    report_scope: str | None = None,
    period_end: date | None = None,
    seed: ConsolContext | None = None,
) -> ConsolContext:
    """用已构建的树和已解析项目字段生成不可变上下文。"""
    if seed is None:
        seed = ConsolContext(project_id=project_id, year=year)
    elif seed.project_id != project_id or seed.year != year:
        raise ConsolContextError("合并上下文与目标项目或年度不一致")
    root_key = None if tree is None else (
        getattr(tree, "node_key", None)
        or getattr(tree, "company_code", None)
    )
    return seed.with_resolution(
        node_key=root_key,
        node_keys=_tree_node_keys(tree),
        template_type=_non_blank(template_type),
        report_scope=_non_blank(report_scope),
        period_end=period_end,
        tree_fingerprint=tree_fingerprint(tree),
    )


def validate_context(
    context: ConsolContext | None,
    project_id: UUID,
    year: int,
    *,
    tree: TreeNode | None = None,
    node_key: str | None = None,
) -> None:
    """验证服务入口收到的上下文边界与当前目标一致。"""
    if context is None:
        return
    if context.project_id != project_id:
        raise ConsolContextError("合并上下文项目与计算目标不一致")
    if context.year != year:
        raise ConsolContextError("合并上下文年度与计算目标不一致")
    actual_fingerprint = tree_fingerprint(tree)
    if context.tree_fingerprint and actual_fingerprint != context.tree_fingerprint:
        raise ConsolContextError("合并上下文树指纹与当前企业树不一致")
    if node_key is not None and context.node_keys and node_key not in context.node_keys:
        raise ConsolContextError("合并上下文不包含请求的 node_key")


async def build_consol_context(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    *,
    tree: TreeNode | None = None,
    seed: ConsolContext | None = None,
) -> ConsolContext:
    """查询目标项目并用目标树构造上下文；版本字段不在此处伪造。"""
    project = await db.get(Project, project_id)
    if project is None or project.is_deleted:
        raise ValueError(f"找不到合并项目 {project_id}")
    actual_year = resolve_project_audit_year(project)
    if actual_year is not None and actual_year != year:
        raise ValueError(f"项目 {project_id} 的审计年度为 {actual_year}，请求年度为 {year}")
    resolved_tree = tree if tree is not None else await build_tree(db, project_id)
    return context_from_tree(
        project_id,
        year,
        resolved_tree,
        template_type=project.template_type,
        report_scope=project.report_scope,
        period_end=project.audit_period_end,
        seed=seed,
    )


async def build_target_consol_context(
    db: AsyncSession,
    seed: ConsolContext,
    project_id: UUID,
    requested_year: int,
    *,
    tree: TreeNode | None = None,
) -> ConsolContext:
    """为 push 的一个 target 重新解析项目、年度和树，保留同一 run 身份。"""
    target_seed = seed.for_target(project_id, year=requested_year)
    return await build_consol_context(
        db,
        project_id,
        requested_year,
        tree=tree,
        seed=target_seed,
    )
